import socket
import paho.mqtt.client as mqtt
import numpy as np
import sounddevice as sd

# --- Automatically detect your machine's local IP ---
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

broker_address = get_local_ip()  # dynamic local IP
broker_port = 1883
topic = "epbx/voice"
client_id = f"VoiceSubscriber_{broker_address.replace('.', '_')}"

SAMPLE_RATE = 16000
CHUNK_SIZE = 1024

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to MQTT Broker at {broker_address}:{broker_port}")
        client.subscribe(topic)
    else:
        print(f"❌ Connection failed: {rc}")

def on_message(client, userdata, msg):
    audio_bytes = msg.payload
    audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
    sd.play(audio_array, samplerate=SAMPLE_RATE)

client = mqtt.Client(client_id=client_id)
client.on_connect = on_connect
client.on_message = on_message

client.connect(broker_address, broker_port, 60)
client.loop_forever()
