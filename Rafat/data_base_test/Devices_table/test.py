import json
import paho.mqtt.client as mqtt

BROKER = "10.151.68.76"
PORT = 1884
TOPIC = "employees/15792/recorder"

client = mqtt.Client()
client.connect(BROKER, PORT, 60)

message = {
    "employee_id": 15792,
    "machine_id": 3101,
    "speech_text": "open machine",
    "intent": "open",
    "Action": "yes"
}

client.publish(TOPIC, json.dumps(message))
client.disconnect()
