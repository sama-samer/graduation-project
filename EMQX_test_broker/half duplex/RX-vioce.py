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
MQTT_BROKER = "192.168.1.3"
MQTT_PORT = 1884
MQTT_TOPIC_BASE = "pbx/voice/live"

SAMPLE_RATE = 32000
CHANNELS = 1
CHUNK = 1024
DTYPE = "int16"
AMPLIFY = 5.0  # amplify playback volume

# -----------------------
# USER INPUT
# -----------------------
own_number = input("Enter your number: ").strip()
TOPIC_RECEIVE = f"{MQTT_TOPIC_BASE}/{own_number}"

# -----------------------
# AUDIO QUEUE
# -----------------------
audio_queue = queue.Queue(maxsize=100)

# -----------------------
# MQTT CLIENT
# -----------------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connected to broker {MQTT_BROKER}")
    client.subscribe(TOPIC_RECEIVE)
    print(f"Listening on: {TOPIC_RECEIVE}")

def on_message(client, userdata, msg):
    try:
        pcm = np.frombuffer(msg.payload, dtype=np.int16)
        if not audio_queue.full():
            audio_queue.put(pcm)
    except Exception as e:
        print("Queue error:", e)

client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
threading.Thread(target=client.loop_forever, daemon=True).start()

# -----------------------
# AUDIO CALLBACK FOR SOUNDDEVICE
# -----------------------
def playback_callback(outdata, frames, time_info, status):
    try:
        if status:
            print("Stream status:", status)
        if not audio_queue.empty():
            data = audio_queue.get().astype(np.float32)
            data *= AMPLIFY
            np.clip(data, -32768, 32767, out=data)
            outdata[:len(data), 0] = data
        else:
            outdata.fill(0)
    except Exception as e:
        print("Playback callback error:", e)
        outdata.fill(0)

# -----------------------
# START PLAYBACK STREAM
# -----------------------
with sd.OutputStream(
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    dtype=DTYPE,
    blocksize=CHUNK,
    callback=playback_callback
):
    print("Ready to receive audio. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Exiting RX.")

