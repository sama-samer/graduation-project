import paho.mqtt.client as mqtt
import json
import time
import random

# === Configuration ===
broker_address = "127.0.0.1"   # Localhost or broker IP
broker_port = 1883
topic = "voice/test"
client_id = f"TX_{broker_address.replace('.', '_')}"
frame_interval = 0.05  # seconds (50 ms per frame)
frame_size = 160       # bytes typical for 20ms PCM frame
total_frames = 1000    # number of frames to send (for simulation)

# === MQTT Setup ===
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"\n✅ Connected to broker {broker_address}:{broker_port}")
        print(f"🎤 Starting simulated voice transmission on topic '{topic}'...\n")
    else:
        print(f"❌ Connection failed, code {rc}")

client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
client.on_connect = on_connect

# === Connect to Broker ===
try:
    client.connect(broker_address, broker_port, 60)
    client.loop_start()
except Exception as e:
    print(f"⚠️ Connection error: {e}")
    exit()

# === Simulate Voice Frames ===
try:
    for seq in range(1, total_frames + 1):
        payload = {
            "seq": seq,
            "timestamp": time.time(),
            "size_bytes": frame_size,
            "data_sample": [random.randint(0, 255) for _ in range(8)]  # sample pseudo-voice bytes
        }

        # Publish frame
        client.publish(topic, json.dumps(payload), qos=0)

        # Display progress every 50 packets
        if seq % 50 == 0:
            print(f"📡 Sent frame #{seq} at {time.strftime('%H:%M:%S')}")

        time.sleep(frame_interval)  # simulate real-time frame interval

    print("\n✅ Transmission complete.")
except KeyboardInterrupt:
    print("\n🛑 Transmission interrupted by user.")
finally:
    client.loop_stop()
    client.disconnect()
