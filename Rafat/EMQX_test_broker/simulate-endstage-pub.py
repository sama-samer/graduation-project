import paho.mqtt.client as mqtt
import json
import time
import os
import random

# --- Configuration ---
broker_address = "127.0.0.1"
broker_port = 1883
topic = "voice/test"
client_id = f"TX_{os.getpid()}"

frame_duration = 0.02  # 20 ms per frame
frame_min_size = 50     # compressed voice frame min size in bytes
frame_max_size = 320    # max size
total_frames = 2000
drop_rate = 0.02        # 2% packet loss
jitter_range = (0, 0.04)  # network jitter in seconds

client = mqtt.Client(client_id=client_id)

def connect_broker():
    print(f"🔗 Connecting to broker {broker_address}:{broker_port} ...")
    client.connect(broker_address, broker_port, 60)
    print("✅ Connected — starting voice stream\n")

def send_voice_stream():
    for seq in range(total_frames):
        if random.random() < drop_rate:
            # simulate packet loss
            time.sleep(frame_duration)
            continue

        frame_size = random.randint(frame_min_size, frame_max_size)
        payload = os.urandom(frame_size)
        packet = {
            "seq": seq,
            "timestamp": time.time(),
            "size_bytes": frame_size,
            "data": payload.hex()
        }

        client.publish(topic, json.dumps(packet), qos=0)

        # Simulate capture + encode + network + random jitter
        capture_encode = 0.025  # 25 ms: capture + encode
        network_delay = random.uniform(0.01, 0.03)  # 10–30 ms
        jitter = random.uniform(*jitter_range)
        time.sleep(frame_duration + capture_encode + network_delay + jitter)

        if seq % 100 == 0:
            print(f"🎙️ Sent frame #{seq} | Size: {frame_size} bytes | Total simulated delay: {capture_encode*1000+network_delay*1000+jitter*1000:.1f} ms")

    print("\n✅ Transmission complete.")
    client.disconnect()

if __name__ == "__main__":
    connect_broker()
    send_voice_stream()
