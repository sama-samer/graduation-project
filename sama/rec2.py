import json
import time
import paho.mqtt.client as mqtt

# =========================
# MQTT CONFIG
# =========================
MQTT_BROKER = "172.20.10.2"
MQTT_PORT = 1884

COMMANDS_FILE = "commands.json"

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

def publish_message(topic, payload):
    try:
        result = client.publish(topic, payload, qos=1)
        result.wait_for_publish()
        print(f"[+] Sent to topic: {topic}")
    except Exception as e:
        print(f"[!] Publish error: {e}")

# =========================
# LOAD LAST COMMAND
# =========================
def get_last_command():
    try:
        with open(COMMANDS_FILE, "r") as f:
            data = json.load(f)

        if not data:
            print("[!] No commands found")
            return None

        last_command = data[-1]  

        return last_command

    except Exception as e:
        print(f"[!] Error reading JSON: {e}")
        return None

# =========================
# MARK AS DISPATCHED (optional)
# =========================
def mark_as_dispatched(command_id):
    try:
        with open(COMMANDS_FILE, "r") as f:
            data = json.load(f)

        for cmd in data:
            if cmd["id"] == command_id:
                cmd["dispatched"] = True

        with open(COMMANDS_FILE, "w") as f:
            json.dump(data, f, indent=4)

        print(f"[+] Command {command_id} marked as dispatched")

    except Exception as e:
        print(f"[!] Error updating JSON: {e}")

# =========================
# MAIN PIPELINE
# =========================
def main():
    connect_mqtt()

    command = get_last_command()

    if not command:
        return

    # Extract data
    topic = command.get("mqtt_topic", "test")
    payload = json.dumps(command)

    # Print result
    print("\n──── RESULT ────")
    print(f"ID       : {command['id']}")
    print(f"Intent   : {command['intent']}")
    print(f"Topic    : {topic}")
    print(f"Payload  : {payload}")

    # Publish to MQTT
    publish_message(topic, payload)

    # Mark as sent (optional but VERY useful)
    if not command.get("dispatched", False):
        mark_as_dispatched(command["id"])

    time.sleep(1)
    client.loop_stop()
    client.disconnect()

# =========================
# RUN
# =========================
if __name__ == "__main__":
    main()