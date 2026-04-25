import socket
import paho.mqtt.client as mqtt
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

# --- Configuration ---
broker_address = get_local_ip()   # use your EMQX host IP if broker is remote
broker_port = 1883
topic = "python/messages"
client_id = f"Python_Publisher_{broker_address.replace('.', '_')}"

# --- Create MQTT client ---
client = mqtt.Client(client_id=client_id)

# --- Connect to broker ---
try:
    print(f"\n🚀 Connecting to broker {broker_address}:{broker_port} ...")
    client.connect(broker_address, broker_port, 60)
    print("✅ Connected successfully!\n")
except Exception as e:
    print(f"❌ Failed to connect: {e}")
    exit()

# --- Publish messages repeatedly ---
try:
    while True:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        message = f"Hello from {client_id} at {timestamp}"
        
        client.publish(topic, message)
        print(f"📤 Published: '{message}' → {topic}")
        
        time.sleep(3)  # send a message every 3 seconds

except KeyboardInterrupt:
    print("\n🛑 Publisher stopped manually.")
    client.disconnect()
