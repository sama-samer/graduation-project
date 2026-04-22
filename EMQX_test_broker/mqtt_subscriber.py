import socket
import paho.mqtt.client as mqtt
import time

# --- Automatically detect your machine's local IP ---
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # connect to a public DNS
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"  # fallback if detection fails

# --- Configuration ---
broker_address = get_local_ip()
broker_port = 1883
topic = "python/messages"
client_id = f"Python_Subscriber_{broker_address.replace('.', '_')}"

# --- MQTT Event Handlers ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("\n✅ --- Subscriber Initialized ---")
        print(f"Status: Connected successfully to Broker!")
        print(f"Detected Local IP: {broker_address}")
        print(f"Broker: {broker_address}:{broker_port}")
        print(f"Client ID: {client_id}")
        client.subscribe(topic)
        print(f"Subscribed to topic '{topic}' — waiting for messages...")
    else:
        print(f"❌ Connection FAILED. Return code: {rc}")

def on_message(client, userdata, msg):
    message_payload = msg.payload.decode()
    print("\n📩 --- NEW MESSAGE RECEIVED ---")
    print(f"Topic:        {msg.topic}")
    print(f"QoS Level:    {msg.qos}")
    print(f"Timestamp:    {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Payload:      {message_payload}")
    print("-------------------------------")

# --- Setup MQTT Client ---
client = mqtt.Client(client_id=client_id)
client.on_connect = on_connect
client.on_message = on_message

# --- Connect and Loop ---
try:
    print(f"🔍 Attempting to connect to broker at {broker_address}:{broker_port}...")
    client.connect(broker_address, broker_port, 60)
    client.loop_forever()
except Exception as e:
    print(f"⚠️ Connection Error: {e}")
