import paho.mqtt.client as mqtt
import sounddevice as sd
import threading
import queue
import numpy as np
import time
import struct

# -----------------------
# CONFIGURATION (latency-tuned, same functionality)
# -----------------------
MQTT_BROKER = "172.20.10.2"
MQTT_PORT = 1884
MQTT_TOPIC_BASE = "pbx/voice/live"

SAMPLE_RATE = 32000
CHANNELS = 1

# ↓ Smaller chunk = lower latency (more packets/second)
CHUNK = 512
DTYPE = "int16"

AMPLIFY_TX = 10.0
AMPLIFY_RX = 2.0

# Queue: smaller buffer = lower latency. Prevents multi-second lag buildup.
AUDIO_QUEUE_MAX = 5
# Keep only a few newest frames. If we fall behind, drop old audio (real-time feel).
QUEUE_TARGET = 4

# Optional: reduce logging overhead
LOG_EVERY_SEC = 1.0

# -----------------------
# PACKET FORMAT (wire format) - NO SECURITY
# -----------------------
# packet = VER(1) || SEQ(4) || PCM_BYTES(N)
VER = 1
HEADER_STRUCT = struct.Struct("!BI")  # VER(uint8), SEQ(uint32) => 5 bytes
HEADER_SIZE = HEADER_STRUCT.size

def protect_payload(plaintext: bytes, seq: int) -> bytes:
    header = HEADER_STRUCT.pack(VER, seq)
    return header + plaintext

def unprotect_payload(packet: bytes):
    if len(packet) < HEADER_SIZE:
        raise ValueError("Packet too short")
    header = packet[:HEADER_SIZE]
    plaintext = packet[HEADER_SIZE:]
    ver, seq = HEADER_STRUCT.unpack(header)
    if ver != VER:
        raise ValueError(f"Unsupported version: {ver}")
    return seq, plaintext

# -----------------------
# LATENCY MEASUREMENT (Ping-Pong side-channel)
# Now improved to approximate "mic ADC capture -> speaker DAC output"
# using PortAudio timing estimates in sounddevice callbacks:
#  - inputBufferAdcTime: when first input sample hit ADC
#  - outputBufferDacTime: when first output sample hits DAC
#  - currentTime: callback time base (same clock as the above)
# -----------------------
LAT_EVERY_N_FRAMES = 50  # ~0.8s at 512/32000; adjust as desired

PING_TYPE = 1

# Keep same audio ping format (type, seq, t0_tx_ns)
LAT_PING_STRUCT = struct.Struct("!BIQ")  # type(uint8), seq(uint32), t0_ns(uint64)

# UPDATED play-event format:
# Send: seq + dac_delay_us (estimated remaining time until DAC)
LAT_PLAY_STRUCT = struct.Struct("!II")   # seq(uint32), dac_delay_us(uint32)

# -----------------------
# USER INPUT
# -----------------------
own_number = input("Enter your number: ").strip()
destination_number = input("Enter destination number: ").strip()

TOPIC_SEND = f"{MQTT_TOPIC_BASE}/{destination_number}"
TOPIC_RECEIVE = f"{MQTT_TOPIC_BASE}/{own_number}"

# Side-channel topics:
TOPIC_LAT_AUDIO_PING = f"{MQTT_TOPIC_BASE}/_lat/audio_ping/{destination_number}"
TOPIC_LAT_PLAY = f"{MQTT_TOPIC_BASE}/_lat/play/{own_number}"

# Baseline control RTT topics (no audio involvement):
TOPIC_LAT_CTL_PING = f"{MQTT_TOPIC_BASE}/_lat/ctl_ping/{destination_number}"
TOPIC_LAT_CTL_PONG = f"{MQTT_TOPIC_BASE}/_lat/ctl_pong/{own_number}"

# Each side must also listen for:
TOPIC_LAT_AUDIO_PING_IN = f"{MQTT_TOPIC_BASE}/_lat/audio_ping/{own_number}"
TOPIC_LAT_PLAY_IN = f"{MQTT_TOPIC_BASE}/_lat/play/{destination_number}"
TOPIC_LAT_CTL_PING_IN = f"{MQTT_TOPIC_BASE}/_lat/ctl_ping/{own_number}"
TOPIC_LAT_CTL_PONG_IN = f"{MQTT_TOPIC_BASE}/_lat/ctl_pong/{destination_number}"

# -----------------------
# GLOBAL FLAGS & QUEUE
# -----------------------
call_active = True

# Store (seq, pcm) so playback knows which seq is being played
audio_queue = queue.Queue(maxsize=AUDIO_QUEUE_MAX)

tx_seq = 0
tx_seq_lock = threading.Lock()

last_rx_seq = -1
last_rx_seq_lock = threading.Lock()

last_log_time = 0.0

# Latency state
# UPDATED: store (t_tx_send_ns, adc_delay_ms) per seq
pending_audio_pings = {}   # seq -> (t_tx_send_ns, adc_delay_ms)
pending_lock = threading.Lock()

rx_ping_seen = set()       # RX side: remember seq that had an audio ping
rx_ping_lock = threading.Lock()

ctl_rtt_ms_ema = None
alpha = 0.2

# -----------------------
# MQTT CLIENT
# -----------------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] Connected to broker {MQTT_BROKER}:{MQTT_PORT}")
    client.subscribe(TOPIC_RECEIVE, qos=0)

    # latency side-channel subscriptions
    client.subscribe(TOPIC_LAT_AUDIO_PING_IN, qos=0)
    client.subscribe(TOPIC_LAT_PLAY_IN, qos=0)
    client.subscribe(TOPIC_LAT_CTL_PING_IN, qos=0)
    client.subscribe(TOPIC_LAT_CTL_PONG, qos=0)  # our own ctl pong topic (we receive pongs here)

    print(f"[MQTT] Listening on topic: {TOPIC_RECEIVE}")
    print(f"[MQTT] Sending to topic:    {TOPIC_SEND}")
    print(f"[TUNE] CHUNK={CHUNK} (~{CHUNK/SAMPLE_RATE*1000:.1f}ms), AUDIO_QUEUE_MAX={AUDIO_QUEUE_MAX}, QUEUE_TARGET={QUEUE_TARGET}")
    print(f"[LAT] audio ping every {LAT_EVERY_N_FRAMES} frames (~{LAT_EVERY_N_FRAMES*CHUNK/SAMPLE_RATE:.2f}s)")
    print(f"[LAT] ctl baseline ping every 1.0s")
    print("[LAT] Improved: adds PortAudio ADC + DAC timing estimates (closer to mic->actual speaker sound).")

def on_message(client, userdata, msg):
    global last_rx_seq, last_log_time, ctl_rtt_ms_ema

    topic = msg.topic

    # -----------------------
    # LATENCY: RX receives audio-triggered ping
    # -----------------------
    if topic == TOPIC_LAT_AUDIO_PING_IN:
        try:
            mtype, seq, _t0 = LAT_PING_STRUCT.unpack(msg.payload)
            if mtype != PING_TYPE:
                return
            with rx_ping_lock:
                rx_ping_seen.add(seq)
        except Exception:
            pass
        return

    # -----------------------
    # LATENCY: RX receives control ping -> responds with control pong (echo t0)
    # -----------------------
    if topic == TOPIC_LAT_CTL_PING_IN:
        try:
            mtype, _seq0, t0 = LAT_PING_STRUCT.unpack(msg.payload)
            if mtype != PING_TYPE:
                return
            client.publish(TOPIC_LAT_CTL_PONG_IN, LAT_PING_STRUCT.pack(PING_TYPE, 0, t0), qos=0)
        except Exception:
            pass
        return

    # -----------------------
    # LATENCY: TX receives control pong -> update baseline RTT EMA
    # -----------------------
    if topic == TOPIC_LAT_CTL_PONG:
        try:
            mtype, _seq0, t0 = LAT_PING_STRUCT.unpack(msg.payload)
            if mtype != PING_TYPE:
                return
            rtt_ms = (time.monotonic_ns() - t0) / 1e6
            ctl_rtt_ms_ema = rtt_ms if ctl_rtt_ms_ema is None else (alpha * rtt_ms + (1 - alpha) * ctl_rtt_ms_ema)
        except Exception:
            pass
        return

    # -----------------------
    # LATENCY: TX receives play-event -> compute mic->spk estimate (improved)
    # -----------------------
    if topic == TOPIC_LAT_PLAY_IN:
        try:
            seq, dac_delay_us = LAT_PLAY_STRUCT.unpack(msg.payload)

            with pending_lock:
                item = pending_audio_pings.pop(seq, None)

            if item is None:
                return

            t_tx_send_ns, adc_delay_ms = item

            audio_rtt_ms = (time.monotonic_ns() - t_tx_send_ns) / 1e6
            dac_delay_ms = dac_delay_us / 1000.0

            if ctl_rtt_ms_ema is not None:
                # Original estimate + PortAudio timing corrections
                est_ms = (audio_rtt_ms - (ctl_rtt_ms_ema / 2.0)) + adc_delay_ms + dac_delay_ms
                print(
                    f"[LAT] mic->spk ~ {est_ms:.1f} ms | audioRTT={audio_rtt_ms:.1f} ms | "
                    f"ctlRTT(ema)={ctl_rtt_ms_ema:.1f} ms | adc={adc_delay_ms:.1f} ms | dac={dac_delay_ms:.1f} ms"
                )
            else:
                print(
                    f"[LAT] audioRTT={audio_rtt_ms:.1f} ms (ctl baseline not ready) | "
                    f"adc={adc_delay_ms:.1f} ms | dac={dac_delay_ms:.1f} ms"
                )
        except Exception:
            pass
        return

    # -----------------------
    # AUDIO RECEIVE PATH
    # -----------------------
    try:
        seq, decrypted = unprotect_payload(msg.payload)

        # Replay / ordering protection
        with last_rx_seq_lock:
            if seq <= last_rx_seq:
                return
            last_rx_seq = seq

        pcm = np.frombuffer(decrypted, dtype=np.int16)

        # LATENCY CONTROL: drop old queued audio so we stay "live"
        while audio_queue.qsize() > QUEUE_TARGET:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break

        # If full, drop one old and put newest
        if audio_queue.full():
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            audio_queue.put_nowait((seq, pcm))
        except queue.Full:
            pass

        # Throttled logging
        now = time.time()
        if now - last_log_time > LOG_EVERY_SEC:
            last_log_time = now
            print(f"[RX] OK seq={seq} bytes={len(msg.payload)} q={audio_queue.qsize()} topic={msg.topic}")

    except Exception:
        pass

client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
threading.Thread(target=client.loop_forever, daemon=True).start()

# -----------------------
# CONTROL BASELINE PING LOOP
# -----------------------
def control_ping_loop():
    while call_active:
        t0 = time.monotonic_ns()
        pkt = LAT_PING_STRUCT.pack(PING_TYPE, 0, t0)
        client.publish(TOPIC_LAT_CTL_PING, pkt, qos=0)
        time.sleep(1.0)

threading.Thread(target=control_ping_loop, daemon=True).start()

# -----------------------
# AUDIO TX CALLBACK
# -----------------------
def audio_callback(indata, frames, time_info, status):
    global tx_seq
    if not call_active:
        return

    # Amplify and clip
    data = indata.astype(np.float32) * AMPLIFY_TX
    data = np.clip(data, -32768, 32767).astype(np.int16)
    plaintext = data.tobytes()

    with tx_seq_lock:
        seq = tx_seq
        tx_seq = (tx_seq + 1) & 0xFFFFFFFF

    packet = protect_payload(plaintext, seq)
    client.publish(TOPIC_SEND, packet, qos=0)

    # NEW: estimate how long ago the ADC captured the first sample of this buffer
    adc_delay_ms = 0.0
    try:
        adc_delay_ms = max(0.0, (time_info["currentTime"] - time_info["inputBufferAdcTime"]) * 1000.0)
    except Exception:
        adc_delay_ms = 0.0

    # LATENCY PING (side-channel): keyed by the same seq, no PCM modification
    if (seq % LAT_EVERY_N_FRAMES) == 0:
        t_tx_send_ns = time.monotonic_ns()
        with pending_lock:
            pending_audio_pings[seq] = (t_tx_send_ns, adc_delay_ms)

        ping = LAT_PING_STRUCT.pack(PING_TYPE, seq, t_tx_send_ns)
        client.publish(TOPIC_LAT_AUDIO_PING, ping, qos=0)

# -----------------------
# AUDIO RX CALLBACK
# -----------------------
def playback_callback(outdata, frames, time_info, status):
    try:
        seq, pcm = audio_queue.get_nowait()

        # If this frame had a latency ping, publish play-event with DAC timing estimate
        do_play_evt = False
        with rx_ping_lock:
            if seq in rx_ping_seen:
                rx_ping_seen.discard(seq)
                do_play_evt = True

        if do_play_evt:
            # Estimate remaining time until DAC plays the first sample of the buffer
            dac_delay_us = 0
            try:
                dac_delay_s = time_info["outputBufferDacTime"] - time_info["currentTime"]
                dac_delay_us = int(max(0.0, dac_delay_s) * 1e6)
            except Exception:
                dac_delay_us = 0

            client.publish(TOPIC_LAT_PLAY, LAT_PLAY_STRUCT.pack(seq, dac_delay_us), qos=0)

        data = pcm.astype(np.float32)
        data *= AMPLIFY_RX
        np.clip(data, -32768, 32767, out=data)

        # Output expects shape (frames, channels)
        n = min(len(data), len(outdata))
        outdata[:n, 0] = data[:n]
        if n < len(outdata):
            outdata[n:].fill(0)

    except queue.Empty:
        outdata.fill(0)
    except Exception:
        outdata.fill(0)

# -----------------------
# START FULL-DUPLEX STREAM (low-latency hints)
# -----------------------
with sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    dtype=DTYPE,
    blocksize=CHUNK,
    latency="low",
    callback=audio_callback
), sd.OutputStream(
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    dtype=DTYPE,
    blocksize=CHUNK,
    latency="low",
    callback=playback_callback
):
    print("[INFO] Full-duplex PBX active (NO SECURITY). Ctrl+C to exit.")
    try:
        while call_active:
            time.sleep(0.05)
    except KeyboardInterrupt:
        call_active = False
        print("[INFO] Call ended.")
