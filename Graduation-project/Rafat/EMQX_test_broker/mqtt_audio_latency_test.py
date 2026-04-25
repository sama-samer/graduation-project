import socket
import paho.mqtt.client as mqtt
import numpy as np
import time

# --------------------------
# 1. Environment Setup
# --------------------------
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

broker_address = get_local_ip()
broker_port = 1883
topic = "epbx/voice_test"
client_id_pub = f"Publisher_{broker_address.replace('.', '_')}"
client_id_sub = f"Subscriber_{broker_address.replace('.', '_')}"

# --------------------------
# 2. Audio Simulation Settings
# --------------------------
SAMPLE_RATE = 16000    # 16 kHz
CHUNK_SIZE = 1024      # samples per frame
DURATION = 10          # test duration in seconds
QOS = 0                # low-latency typical for voice

# --------------------------
# 3. MQTT Publisher
# --------------------------
publisher = mqtt.Client(client_id=client_id_pub)
publisher.connect(broker_address, broker_port, 60)
publisher.loop_start()

# --------------------------
# 4. MQTT Subscriber
# --------------------------
latency_list = []

def on_message(client, userdata, msg):
    recv_time = time.time()
    send_time = float(msg.payload[:20].decode())
    latency = recv_time - send_time
    latency_list.append(latency)
    print(f"📩 Latency: {latency*1000:.2f} ms")

subscriber = mqtt.Client(client_id=client_id_sub)
subscriber.on_message = on_message
subscriber.connect(broker_address, broker_port, 60)
subscriber.subscribe(topic)
subscriber.loop_start()

# --------------------------
# 5. Simulate Real-Time Voice Streaming
# --------------------------
print(f"🚀 Starting simulated voice streaming for {DURATION} seconds...")
start_time = time.time()

while time.time() - start_time < DURATION:
    dummy_audio = np.random.rand(CHUNK_SIZE).astype(np.float32).tobytes()
    timestamp = f"{time.time():<20}".encode()  # embed timestamp
    publisher.publish(topic, timestamp + dummy_audio, qos=QOS)
    time.sleep(CHUNK_SIZE / SAMPLE_RATE)  # simulate real-time streaming

# Wait for last messages to arrive
time.sleep(1)

# --------------------------
# 6. Cleanup
# --------------------------
publisher.loop_stop()
subscriber.loop_stop()
publisher.disconnect()
subscriber.disconnect()

# --------------------------
# 7. Results
# --------------------------
if latency_list:
    print("\n📊 Latency Summary:")
    print(f"Average latency: {np.mean(latency_list)*1000:.2f} ms")
    print(f"Maximum latency: {np.max(latency_list)*1000:.2f} ms")
    print(f"Minimum latency: {np.min(latency_list)*1000:.2f} ms")
else:
    print("⚠️ No messages received. Check broker connection.")
