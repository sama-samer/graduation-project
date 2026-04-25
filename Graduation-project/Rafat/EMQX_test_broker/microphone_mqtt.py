import socket
import paho.mqtt.client as mqtt
import sounddevice as sd
import numpy as np
import time

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
client_id = f"VoicePublisher_{broker_address.replace('.', '_')}"

client = mqtt.Client(client_id=client_id)
client.connect(broker_address, broker_port, 60)
client.loop_start()

SAMPLE_RATE = 16000   # 16 kHz
CHUNK_SIZE = 1024     # samples per frame

def audio_callback(indata, frames, time_info, status):
    audio_bytes = indata.tobytes()
    client.publish(topic, audio_bytes, qos=0)  # qos=0 for low-latency

with sd.InputStream(channels=1, samplerate=SAMPLE_RATE,
                    blocksize=CHUNK_SIZE, callback=audio_callback):
    print(f"🎤 Streaming audio via MQTT to broker {broker_address}. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Streaming stopped.")
        client.loop_stop()
        client.disconnect()
