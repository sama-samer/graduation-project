import paho.mqtt.client as mqtt
import sounddevice as sd
import threading
import queue
import numpy as np
import time

# --- Crypto ---
from Crypto.Cipher import AES
from Crypto.Hash import HMAC, SHA256

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
AMPLIFY_RX = 7.0   # amplify received audio

# -----------------------
# DATA SECURITY (PAYLOAD ONLY)
# -----------------------
# IMPORTANT:
# - These keys MUST be the same on both PCs (TX and RX).
# - AES_KEY must be exactly 16 bytes for AES-128.
AES_KEY = b"Doha_AES_16bytes"        # 16 bytes
HMAC_KEY = b"Doha_HMAC_secret_key"   # any length is ok

# NOTE (demo-friendly):
# Fixed IV keeps code simple. In a real system, use a random IV per packet and send it with the packet.
IV = b"\x00" * 16

HMAC_SIZE = 32  # SHA-256 output size in bytes

def protect_payload(plaintext: bytes) -> bytes:
    """AES-128 encrypt + HMAC-SHA256 over ciphertext. Returns: ciphertext || mac"""
    cipher = AES.new(AES_KEY, AES.MODE_CFB, iv=IV)
    ciphertext = cipher.encrypt(plaintext)

    h = HMAC.new(HMAC_KEY, digestmod=SHA256)
    h.update(ciphertext)
    mac = h.digest()

    return ciphertext + mac

def unprotect_payload(payload: bytes) -> bytes:
    """Verify HMAC then decrypt. Raises ValueError if HMAC fails."""
    if len(payload) < HMAC_SIZE:
        raise ValueError("Payload too short")

    ciphertext = payload[:-HMAC_SIZE]
    recv_mac = payload[-HMAC_SIZE:]

    h = HMAC.new(HMAC_KEY, digestmod=SHA256)
    h.update(ciphertext)
    h.verify(recv_mac)  # raises ValueError if tampered

    cipher = AES.new(AES_KEY, AES.MODE_CFB, iv=IV)
    plaintext = cipher.decrypt(ciphertext)
    return plaintext

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

# -----------------------
# MQTT CLIENT
# -----------------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] Connected to broker {MQTT_BROKER}")
    client.subscribe(TOPIC_RECEIVE)
    print(f"[MQTT] Listening on topic: {TOPIC_RECEIVE}")

def on_message(client, userdata, msg):
    try:
        # 1) Verify HMAC + decrypt
        decrypted = unprotect_payload(msg.payload)

        # 2) Convert back to PCM samples
        pcm = np.frombuffer(decrypted, dtype=np.int16)

        if not audio_queue.full():
            audio_queue.put(pcm)

        print(f"[RX] Received {len(msg.payload)} bytes (secure) from {msg.topic}")

    except Exception as e:
        # HMAC fail or decode issue -> drop packet
        print("[SECURITY] Dropped packet (tampered or invalid):", e)

client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
threading.Thread(target=client.loop_forever, daemon=True).start()

# -----------------------
# AUDIO TX CALLBACK
# -----------------------
def audio_callback(indata, frames, time_info, status):
    if status:
        print("[TX] Stream status:", status)
    if call_active:
        # PCM int16
        data = indata.astype(np.float32) * AMPLIFY_TX
        data = np.clip(data, -32768, 32767).astype(np.int16)

        # 1) Protect (encrypt + HMAC)
        secure_payload = protect_payload(data.tobytes())

        # 2) Publish secure payload
        client.publish(TOPIC_SEND, secure_payload)
        print(f"[TX] Sent {len(secure_payload)} bytes (secure) to {TOPIC_SEND}")

# -----------------------
# AUDIO RX CALLBACK
# -----------------------
def playback_callback(outdata, frames, time_info, status):
    if status:
        print("[RX] Stream status:", status)
    try:
        if not audio_queue.empty():
            data = audio_queue.get().astype(np.float32)
            data *= AMPLIFY_RX
            np.clip(data, -32768, 32767, out=data)
            outdata[:len(data), 0] = data
        else:
            outdata.fill(0)
    except Exception as e:
        print("[RX] Playback error:", e)
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
    print("[INFO] Full-duplex mini PBX active (AES-128 + HMAC-SHA256). Press Ctrl+C to exit.")
    try:
        while call_active:
            time.sleep(0.05)
    except KeyboardInterrupt:
        call_active = False
        print("[INFO] Call ended.")
