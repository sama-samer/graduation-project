import paho.mqtt.client as mqtt

BROKER = "192.168.110.225"
PORT = 1884
TOPIC = "test"
print("port number:", PORT)
print("broker:", BROKER)
print("topic:", TOPIC)
def on_connect(client, userdata, flags, rc):
    print("Connected to broker with code:", rc)
    client.subscribe(TOPIC)
    print(f"Subscribed to topic: {TOPIC}")

def on_message(client, userdata, msg):
    message = msg.payload.decode()
    print("\n--- Message Received ---")
    print("Topic:", msg.topic)
    print("Message:", message)

client = mqtt.Client()

client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)

print("Listening for messages...\n")
client.loop_forever()
