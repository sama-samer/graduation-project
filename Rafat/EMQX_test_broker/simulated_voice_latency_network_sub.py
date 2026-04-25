import paho.mqtt.client as mqtt
import json
import time
import statistics

# === Configuration ===
broker_address = "127.0.0.1"
broker_port = 1883
topic = "voice/test"

client_id = f"RX_{broker_address.replace('.', '_')}"
latencies = []

# === MQTT Event Handlers ===
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"\n✅ Connected to broker {broker_address}:{broker_port}")
        client.subscribe(topic)
        print(f"📡 Subscribed to topic '{topic}' — measuring latency...\n")
    else:
        print(f"❌ Connection failed, code {rc}")

def on_message(client, userdata, msg):
    try:
        now = time.time()
        data = json.loads(msg.payload.decode())
        tx_time = data["timestamp"]
        latency_ms = (now - tx_time) * 1000.0
        latencies.append(latency_ms)

        # Show every 50 packets for voice simulation statistics
        if len(latencies) % 50 == 0:
            avg_lat = statistics.mean(latencies)
            min_lat = min(latencies)
            max_lat = max(latencies)
            print(f"\n🎧 --- LATENCY REPORT ---")
            print(f"Samples: {len(latencies)} packets")
            print(f"Avg: {avg_lat:.2f} ms | Min: {min_lat:.2f} ms | Max: {max_lat:.2f} ms")
            print(f"Seq: {data['seq']} | Frame size: {data['size_bytes']} bytes")
            print(f"Timestamp TX: {time.strftime('%H:%M:%S', time.localtime(tx_time))}")
            print(f"Timestamp RX: {time.strftime('%H:%M:%S', time.localtime(now))}")
            print(f"Latency: {latency_ms:.2f} ms")
            print("--------------------------")
    except Exception as e:
        print(f"⚠️ Parse error: {e}")

# === MQTT Client Setup (FIXED FOR PAHO v2.0) ===
client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
client.on_connect = on_connect
client.on_message = on_message

# === Connect and Start Loop ===
try:
    print(f"🔍 Attempting to connect to broker at {broker_address}:{broker_port}...")
    client.connect(broker_address, broker_port, 60)
    client.loop_forever()
except Exception as e:
    print(f"⚠️ Connection error: {e}")
