import paho.mqtt.client as mqtt
import sounddevice as sd
import socket
import threading
import queue
import numpy as np
import time

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
AMPLIFY_TX = 5.0   # amplify microphone input
AMPLIFY_RX = 7.0   # amplify received audio

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
        pcm = np.frombuffer(msg.payload, dtype=np.int16)
        if not audio_queue.full():
            audio_queue.put(pcm)
        print(f"[RX] Received {len(msg.payload)} bytes from {msg.topic}")
    except Exception as e:
        print("[RX] Queue error:", e)

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
        data = indata.astype(np.float32) * AMPLIFY_TX
        data = np.clip(data, -32768, 32767).astype(np.int16)
        client.publish(TOPIC_SEND, data.tobytes())
        print(f"[TX] Sent {len(data.tobytes())} bytes to {TOPIC_SEND}")

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
    print("[INFO] Full-duplex mini PBX active. Press Ctrl+C to exit.")
    try:
        while call_active:
            time.sleep(0.05)
    except KeyboardInterrupt:
        call_active = False
        print("[INFO] Call ended.")

