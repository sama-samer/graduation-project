import paho.mqtt.client as mqtt
import sounddevice as sd
import socket
import threading
import time
import numpy as np

# -----------------------
# CONFIGURATION
# -----------------------
MQTT_BROKER = "192.168.215.76"
MQTT_PORT = 1884
MQTT_TOPIC_BASE = "pbx/voice/live"

SAMPLE_RATE = 32000
CHANNELS = 1
CHUNK = 1024
DTYPE = "int16"
AMPLIFY = 5.0  # amplify microphone input

# -----------------------
# USER INPUT
# -----------------------
own_number = input("Enter your number: ").strip()
destination = input("Enter destination number: ").strip()

TOPIC_SEND = f"{MQTT_TOPIC_BASE}/{destination}"
call_active = True

# -----------------------
# MQTT CLIENT
# -----------------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connected to broker {MQTT_BROKER}")

client.on_connect = on_connect
client.connect(MQTT_BROKER, MQTT_PORT, 60)
threading.Thread(target=client.loop_forever, daemon=True).start()

# -----------------------
# AUDIO CALLBACK
# -----------------------
def audio_callback(indata, frames, time_info, status):
    if status:
        print("Stream status:", status)
    # Amplify and send audio
    data = indata.astype(np.float32) * AMPLIFY
    data = np.clip(data, -32768, 32767).astype(np.int16)
    client.publish(TOPIC_SEND, data.tobytes())

# -----------------------
# START STREAMING
# -----------------------
def stream_audio():
    print("Streaming audio... Press Ctrl+C to stop.")
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=CHUNK,
        callback=audio_callback
    ):
        while call_active:
            time.sleep(0.05)

try:
    stream_audio()
except KeyboardInterrupt:
    call_active = False
    print("Call ended.")

