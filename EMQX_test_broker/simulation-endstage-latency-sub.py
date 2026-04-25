import paho.mqtt.client as mqtt
import json
import time
import statistics
import csv
import atexit

# --- Configuration ---
broker_address = "127.0.0.1"
broker_port = 1883
topic = "voice/test"
client_id = f"RX_{int(time.time())}"
REPORT_INTERVAL = 100  # report every N frames

# --- Globals ---
received_frames = 0
lost_frames = 0
expected_seq = 0
last_rx_time = None
latencies = []
jitter_list = []
frame_sizes = []

# --- CSV Logging ---
csv_file = open("voice_latency_log.csv", "w", newline="")
csv_writer = csv.writer(csv_file)
csv_writer.writerow(["seq","tx_timestamp","rx_timestamp","latency_ms","jitter_ms","frame_size_bytes"])

# --- Final report ---
def print_final_stats():
    if received_frames == 0:
        print("No frames received.")
        return

    avg_latency = statistics.mean(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)

    avg_jitter = statistics.mean(jitter_list)
    min_jitter = min(jitter_list)
    max_jitter = max(jitter_list)

    avg_frame = statistics.mean(frame_sizes)
    min_frame = min(frame_sizes)
    max_frame = max(frame_sizes)

    print("\n=== Final Detailed Voice Latency Report ===")
    print(f"Total frames received : {received_frames}")
    print(f"Total packets lost    : {lost_frames}")
    print(f"Latency (ms)          : min={min_latency:.2f}, avg={avg_latency:.2f}, max={max_latency:.2f}")
    print(f"Jitter (ms)           : min={min_jitter:.2f}, avg={avg_jitter:.2f}, max={max_jitter:.2f}")
    print(f"Frame size (bytes)    : min={min_frame}, avg={avg_frame:.1f}, max={max_frame}")
    print("=========================================\n")
    csv_file.close()
    print("📄 CSV log saved as 'voice_latency_log.csv'")

atexit.register(print_final_stats)

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to broker {broker_address}:{broker_port}")
        client.subscribe(topic, qos=0)
        print(f"📡 Listening for voice frames...")
    else:
        print(f"❌ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    global received_frames, lost_frames, expected_seq, last_rx_time

    now = time.time()
    try:
        data = json.loads(msg.payload.decode())
        seq = data["seq"]
        tx_time = data["timestamp"]
        frame_size = data["size_bytes"]

        # Simulate decoding + jitter buffer at RX
        decode_delay = 0.003  # 3 ms
        jitter_buffer = 0.02  # 20 ms
        time.sleep(decode_delay + jitter_buffer)

        # End-to-end latency
        latency_ms = (time.time() - tx_time) * 1000
        latencies.append(latency_ms)
        frame_sizes.append(frame_size)

        # Jitter
        if last_rx_time is not None:
            jitter_ms = abs((time.time() - last_rx_time)*1000 - 20)
        else:
            jitter_ms = 0
        last_rx_time = time.time()
        jitter_list.append(jitter_ms)

        # Packet loss detection
        if seq > expected_seq:
            lost_frames += seq - expected_seq
        expected_seq = seq + 1

        received_frames += 1

        # CSV log
        csv_writer.writerow([seq, tx_time, time.time(), f"{latency_ms:.2f}", f"{jitter_ms:.2f}", frame_size])

        # Intermediate report
        if received_frames % REPORT_INTERVAL == 0:
            avg_lat = statistics.mean(latencies[-REPORT_INTERVAL:])
            avg_jit = statistics.mean(jitter_list[-REPORT_INTERVAL:])
            print(f"\n--- Stats after {received_frames} frames ---")
            print(f"Avg Latency: {avg_lat:.2f} ms | Avg Jitter: {avg_jit:.2f} ms | Lost frames: {lost_frames}")
            print("----------------------------------\n")

    except Exception as e:
        print(f"⚠️ Error parsing message: {e}")

# --- Main ---
client = mqtt.Client(client_id=client_id)
client.on_connect = on_connect
client.on_message = on_message

print(f"🔗 Connecting to broker {broker_address}:{broker_port}...")
client.connect(broker_address, broker_port, 60)
client.loop_forever()
