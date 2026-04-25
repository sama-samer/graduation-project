
import paho.mqtt.client as mqtt
import sounddevice as sd
import threading
import queue
import numpy as np
import time
import struct

# --- Crypto ---
from Crypto.Cipher import AES
from Crypto.Hash import HMAC, SHA256
from Crypto.Random import get_random_bytes

# -----------------------
# CONFIGURATION (latency-tuned, same functionality)
# -----------------------
MQTT_BROKER = "172.20.10.2"
MQTT_PORT = 1884
MQTT_TOPIC_BASE = "pbx/voice/live"

SAMPLE_RATE = 32000
CHANNELS = 1

# ↓ Smaller chunk = lower latency (more packets/second)
CHUNK = 512              # was 1024 (32ms). Now 256 (8ms)
DTYPE = "int16"

AMPLIFY_TX = 3.0
AMPLIFY_RX = 10.0

# Queue: smaller buffer = lower latency. Prevents multi-second lag buildup.
AUDIO_QUEUE_MAX = 5     # was 200
# Keep only a few newest frames. If we fall behind, drop old audio (real-time feel).
QUEUE_TARGET = 4         # if qsize > this, drop oldest until back to target

# Optional: reduce logging overhead
LOG_EVERY_SEC = 1.0

# -----------------------
# KEYS (must match on both PCs)
# -----------------------
AES_KEY = b"Doha_AES_16bytes"        # 16 bytes
HMAC_KEY = b"Doha_HMAC_secret_key"   # any length ok

IV_SIZE = 16
HMAC_SIZE = 32  # SHA-256 output size in bytes

# -----------------------
# PACKET FORMAT (wire format)
# -----------------------
# packet = VER(1) || SEQ(4) || IV(16) || CIPHERTEXT(N) || HMAC(32)
VER = 1
HEADER_STRUCT = struct.Struct("!BI")  # VER(uint8), SEQ(uint32) => 5 bytes
HEADER_SIZE = HEADER_STRUCT.size

def protect_payload(plaintext: bytes, seq: int) -> bytes:
    iv = get_random_bytes(IV_SIZE)
    cipher = AES.new(AES_KEY, AES.MODE_CFB, iv=iv)
    ciphertext = cipher.encrypt(plaintext)

    header = HEADER_STRUCT.pack(VER, seq)
    body = header + iv + ciphertext

    h = HMAC.new(HMAC_KEY, digestmod=SHA256)
    h.update(body)
    mac = h.digest()
    return body + mac

def unprotect_payload(packet: bytes):
    if len(packet) < HEADER_SIZE + IV_SIZE + HMAC_SIZE:
        raise ValueError("Packet too short")

    mac = packet[-HMAC_SIZE:]
    body = packet[:-HMAC_SIZE]

    h = HMAC.new(HMAC_KEY, digestmod=SHA256)
    h.update(body)
    h.verify(mac)  # raises ValueError if invalid

    header = body[:HEADER_SIZE]
    iv = body[HEADER_SIZE:HEADER_SIZE + IV_SIZE]
    ciphertext = body[HEADER_SIZE + IV_SIZE:]

    ver, seq = HEADER_STRUCT.unpack(header)
    if ver != VER:
        raise ValueError(f"Unsupported version: {ver}")

    cipher = AES.new(AES_KEY, AES.MODE_CFB, iv=iv)
    plaintext = cipher.decrypt(ciphertext)
    return seq, plaintext

# -----------------------
# USER INPUT
# -----------------------
own_number = input("Enter your number: ").strip()
destination_number = input("Enter destination number: ").strip()

TOPIC_SEND = f"{MQTT_TOPIC_BASE}/{destination_number}"
TOPIC_RECEIVE = f"{MQTT_TOPIC_BASE}/{own_number}"

# -----------------------
# GLOBAL FLAGS & QUEUE
# -----------------------
call_active = True
audio_queue = queue.Queue(maxsize=AUDIO_QUEUE_MAX)

tx_seq = 0
tx_seq_lock = threading.Lock()

last_rx_seq = -1
last_rx_seq_lock = threading.Lock()

last_log_time = 0.0

# -----------------------
# MQTT CLIENT
# -----------------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] Connected to broker {MQTT_BROKER}:{MQTT_PORT}")
    client.subscribe(TOPIC_RECEIVE, qos=0)
    print(f"[MQTT] Listening on topic: {TOPIC_RECEIVE}")
    print(f"[MQTT] Sending to topic:    {TOPIC_SEND}")
    print(f"[TUNE] CHUNK={CHUNK} (~{CHUNK/SAMPLE_RATE*1000:.1f}ms), AUDIO_QUEUE_MAX={AUDIO_QUEUE_MAX}, QUEUE_TARGET={QUEUE_TARGET}")

def on_message(client, userdata, msg):
    global last_rx_seq, last_log_time
    try:
        seq, decrypted = unprotect_payload(msg.payload)

        # Replay / ordering protection
        with last_rx_seq_lock:
            if seq <= last_rx_seq:
                return
            last_rx_seq = seq

        pcm = np.frombuffer(decrypted, dtype=np.int16)

        # LATENCY CONTROL:
        # If we fall behind, drop oldest queued audio so we stay "live".
        # This reduces latency dramatically (trades occasional tiny skips).
        while audio_queue.qsize() > QUEUE_TARGET:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break

        # Non-blocking-ish put: if full, drop one old and put newest
        if audio_queue.full():
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            audio_queue.put_nowait(pcm)
        except queue.Full:
            pass

        # Throttled logging
        now = time.time()
        if now - last_log_time > LOG_EVERY_SEC:
            last_log_time = now
            print(f"[RX] OK seq={seq} bytes={len(msg.payload)} q={audio_queue.qsize()} topic={msg.topic}")

    except Exception:
        # drop invalid/tampered packets silently (avoid overhead)
        pass

client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
threading.Thread(target=client.loop_forever, daemon=True).start()

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

# -----------------------
# AUDIO RX CALLBACK
# -----------------------
def playback_callback(outdata, frames, time_info, status):
    try:
        pcm = audio_queue.get_nowait()
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
    print("[INFO] Secure full-duplex PBX active (AES-128-CFB + HMAC-SHA256 + IV+SEQ). Ctrl+C to exit.")
    try:
        while call_active:
            time.sleep(0.05)
    except KeyboardInterrupt:
        call_active = False
        print("[INFO] Call ended.")

