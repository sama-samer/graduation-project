import paho.mqtt.client as mqtt

BROKER = "192.168.183.138"   # EMQX host (change if remote)
PORT = 1883
TOPIC1 = "test/topic1"
TOPIC2 = "test/topic2"

# When connected to the broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected to EMQX broker!")
        client.subscribe(TOPIC1)
        client.subscribe(TOPIC2)
        print(f"📡 Subscribed to topic: {TOPIC1}")
        print(f"📡 Subscribed to topic: {TOPIC2}")
    else:
        print(f"❌ Connection failed. Code: {rc}")

# When a message arrives
def on_message(client, userdata, msg):
    print(f"📩 Received from {msg.topic}: {msg.payload.decode()}")

# Create client instance
client = mqtt.Client()

client.on_connect = on_connect
client.on_message = on_message

# Connect to EMQX broker
client.connect(BROKER, PORT, 60)

print("🕓 Waiting for messages...")
client.loop_forever()
