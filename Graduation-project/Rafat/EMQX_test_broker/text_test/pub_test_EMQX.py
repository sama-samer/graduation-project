import time
import paho.mqtt.client as mqtt

BROKER = "192.168.183.138"   # EMQX host (change if remote)
PORT = 1883
TOPIC = "test/topic1"

client = mqtt.Client()
client.connect(BROKER, PORT, 60)

for i in range(5):
    message = f"Hello EMQX! Message #{i+1}"
    result = client.publish(TOPIC, message)
    status = result[0]
    if status == 0:
        print(f"✅ Sent: {message}")
    else:
        print(f"❌ Failed to send message #{i+1}")
    time.sleep(1)

client.disconnect()
