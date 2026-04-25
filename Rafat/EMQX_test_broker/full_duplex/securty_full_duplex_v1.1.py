import paho.mqtt.client as mqtt
import sounddevice as sd
import threading
import queue
import numpy as np
import time
import os
import struct

# --- Crypto ---
from Crypto.Cipher import AES
from Crypto.Hash import HMAC, SHA256
from Crypto.Random import get_random_bytes

# -----------------------
# CONFIGURATION
# -----------------------
MQTT_BROKER = "172.20.10.2"  # your broker IP
MQTT_PORT = 1884
MQTT_TOPIC_BASE = "pbx/voice/live"

SAMPLE_RATE = 32000
CHANNELS = 1
CHUNK = 1024
DTYPE = "int16"
AMPLIFY_TX = 10.0   # amplify microphone input
AMPLIFY_RX = 10.0   # amplify received audio

# -----------------------
# KEYS (must match on both PCs)
# -----------------------
# AES_KEY must be exactly 16 bytes (AES-128)
AES_KEY = b"Doha_AES_16bytes"        # 16 bytes
HMAC_KEY = b"Doha_HMAC_secret_key"   # any length ok

IV_SIZE = 16
HMAC_SIZE = 32  # SHA-256 output size in bytes

# -----------------------
# PACKET FORMAT (wire format)
# -----------------------
# packet = VER(1) || SEQ(4) || IV(16) || CIPHERTEXT(N) || HMAC(32)
#
# HMAC = HMAC_SHA256(HMAC_KEY, VER||SEQ||IV||CIPHERTEXT)
#
# - VER: 1 byte, allows future upgrades
# - SEQ: uint32 big-endian, increments each packet
# - IV: random per packet (critical improvement)
# - CIPHERTEXT: AES-128-CFB encrypted PCM bytes (same length as plaintext)
# - HMAC: integrity + authentication

VER = 1
HEADER_STRUCT = struct.Struct("!BI")  # VER(uint8), SEQ(uint32) => 1 + 4 = 5 bytes
HEADER_SIZE = HEADER_STRUCT.size      # 5 bytes

def protect_payload(plaintext: bytes, seq: int) -> bytes:
    """
    Encrypt + authenticate:
      - Generate random IV
      - AES-128-CFB encrypt
      - HMAC-SHA256 over header + iv + ciphertext
    Returns: packet bytes
    """
    iv = get_random_bytes(IV_SIZE)
    cipher = AES.new(AES_KEY, AES.MODE_CFB, iv=iv)
    ciphertext = cipher.encrypt(plaintext)

    header = HEADER_STRUCT.pack(VER, seq)
    to_mac = header + iv + ciphertext

    h = HMAC.new(HMAC_KEY, digestmod=SHA256)
    h.update(to_mac)
    mac = h.digest()

    return to_mac + mac


def unprotect_payload(packet: bytes):
    """
    Verify + decrypt:
      - Parse header, IV, ciphertext, MAC
      - Verify HMAC(header||iv||ciphertext)
      - Decrypt AES-128-CFB
    Returns: (seq:int, plaintext:bytes)
    Raises: ValueError if invalid/tampered
    """
    if len(packet) < HEADER_SIZE + IV_SIZE + HMAC_SIZE:
        raise ValueError("Packet too short")

    mac = packet[-HMAC_SIZE:]
    body = packet[:-HMAC_SIZE]  # header||iv||ciphertext

    # Verify HMAC first (do NOT decrypt before verifying)
    h = HMAC.new(HMAC_KEY, digestmod=SHA256)
    h.update(body)
    h.verify(mac)  # raises ValueError on failure

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
audio_queue = queue.Queue(maxsize=200)

# TX sequence number
tx_seq = 0
tx_seq_lock = threading.Lock()

# Replay protection: accept only strictly increasing seq
# (simple model: one stream per topic)
last_rx_seq = -1
last_rx_seq_lock = threading.Lock()

# Optional: throttle logs
last_log_time = 0.0

# -----------------------
# MQTT CLIENT
# -----------------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] Connected to broker {MQTT_BROKER}:{MQTT_PORT}")
    client.subscribe(TOPIC_RECEIVE)
    print(f"[MQTT] Listening on topic: {TOPIC_RECEIVE}")
    print(f"[MQTT] Sending to topic:    {TOPIC_SEND}")

def on_message(client, userdata, msg):
    global last_rx_seq, last_log_time
    try:
        seq, decrypted = unprotect_payload(msg.payload)

        # Replay / ordering protection
        with last_rx_seq_lock:
            if seq <= last_rx_seq:
                # Drop old/duplicate/out-of-order packets
                return
            last_rx_seq = seq

        pcm = np.frombuffer(decrypted, dtype=np.int16)

        if not audio_queue.full():
            audio_queue.put(pcm)

        # Throttled logging (avoid printing too often)
        now = time.time()
        if now - last_log_time > 1.0:
            last_log_time = now
            print(f"[RX] OK seq={seq} bytes={len(msg.payload)} topic={msg.topic}")

    except Exception as e:
        # HMAC fail, parse error, decrypt error -> drop
        # Keep this minimal; high-frequency printing can cause audio glitches.
        # Uncomment if you want to see tamper events:
        # print("[SECURITY] Dropped packet:", e)
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
    if status:
        # Avoid noisy logging in callbacks; keep minimal
        pass

    if not call_active:
        return

    # Amplify and clip
    data = indata.astype(np.float32) * AMPLIFY_TX
    data = np.clip(data, -32768, 32767).astype(np.int16)

    plaintext = data.tobytes()

    with tx_seq_lock:
        seq = tx_seq
        tx_seq = (tx_seq + 1) & 0xFFFFFFFF  # uint32 wrap

    packet = protect_payload(plaintext, seq)
    # QoS=0 gives lowest latency; QoS=1 improves reliability but can add delay/jitter
    client.publish(TOPIC_SEND, packet, qos=0)

# -----------------------
# AUDIO RX CALLBACK
# -----------------------
def playback_callback(outdata, frames, time_info, status):
    if status:
        pass

    try:
        if not audio_queue.empty():
            data = audio_queue.get().astype(np.float32)
            data *= AMPLIFY_RX
            np.clip(data, -32768, 32767, out=data)

            # Output expects shape (frames, channels)
            outdata[:len(data), 0] = data
            if len(data) < len(outdata):
                outdata[len(data):].fill(0)
        else:
            outdata.fill(0)
    except Exception:
        outdata.fill(0)

# -----------------------
# START FULL-DUPLEX STREAM
# -----------------------
with sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    dtype=DTYPE,
    blocksize=CHUNK,
    callback=audio_callback
), sd.OutputStream(
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    dtype=DTYPE,
    blocksize=CHUNK,
    callback=playback_callback
):
    print("[INFO] Secure full-duplex PBX active (AES-128-CFB + HMAC-SHA256 + IV+SEQ). Ctrl+C to exit.")
    try:
        while call_active:
            time.sleep(0.05)
    except KeyboardInterrupt:
        call_active = False
        print("[INFO] Call ended.")
