import json
import time
import paho.mqtt.client as mqtt

# =========================
# MQTT CONFIG
# =========================
MQTT_BROKER = "172.20.10.2"
MQTT_PORT = 1884
MQTT_TOPIC = "test"

# =========================
# MQTT CLIENT
# =========================
client = mqtt.Client()

def connect_mqtt():
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 10)
        client.loop_start()
        print("[+] Connected to MQTT broker")
    except Exception as e:
        print(f"[!] MQTT connection error: {e}")

def publish_message(payload):
    try:
        result = client.publish(MQTT_TOPIC, payload, qos=1)

        # Wait for publish confirmation (important for delay debugging)
        result.wait_for_publish()

        print("[+] Message sent to MQTT topic:", MQTT_TOPIC)

    except Exception as e:
        print(f"[!] Publish error: {e}")

# =========================
# YOUR EXISTING LOGIC (SIMPLIFIED)
# =========================
def analyze_text():
    """
    Replace this with your real NLP / intent logic
    """

    text = "Hello, can you please open the e-speed?"
    intent = "OPEN"
    valid = True

    record = {
        "text": text,
        "intent": intent,
        "valid": valid,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    return record

# =========================
# SEND FINAL RESULT
# =========================
def send_final_result(record, sent):
    payload = json.dumps({
        "text": record["text"],
        "intent": record["intent"],
        "valid": record["valid"],
        "sent": sent,
        "timestamp": record["timestamp"]
    })

    print("\n──── RESULT ────")
    print(f"Text     : {record['text']}")
    print(f"Intent   : {record['intent']}")
    print(f"Valid    : {record['valid']}")
    print(f"Sent     : {sent}")

    publish_message(payload)

# =========================
# MAIN PIPELINE
# =========================
def main():
    connect_mqtt()

    record = analyze_text()

    # Your logic to decide if message should be sent
    sent = False
    if record["valid"] and record["intent"] == "OPEN":
        sent = True

    send_final_result(record, sent)

    # Give time for MQTT to send before closing
    time.sleep(1)

    client.loop_stop()
    client.disconnect()

# =========================
# RUN
# =========================
if __name__ == "__main__":
    main()