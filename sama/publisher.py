import paho.mqtt.client as mqtt
import time

BROKER = "172.20.10.2"
PORT = 1884
TOPIC = "test"

client = mqtt.Client()
client.connect(BROKER, PORT, 60)

print("Enter messages (type 'exit' to quit)\n")

while True:
    message = input("Message: ")

    if message.lower() == "exit":
        break

    timestamp = time.time()  # current time in seconds
    full_message = f"{timestamp}|{message}"

    client.publish(TOPIC, full_message)
    print("Sent at:", timestamp)

client.disconnect()