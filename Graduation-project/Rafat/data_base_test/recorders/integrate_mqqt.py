import json
import psycopg2
import paho.mqtt.client as mqtt

BROKER = "192.168.1.8"
PORT = 1884

# One topic for all employees
SUB_TOPIC = "employees/15792/recorder"

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def insert_recorders_row(data):
    conn = None
    try:
        employee_id = data.get("employee_id")
        machine_id = data.get("machine_id")
        speech_text = data.get("speech_text")
        intent = data.get("intent")
        action = data.get("Action", data.get("action"))

        if employee_id is None:
            print("❌ employee_id is missing in the payload")
            return

        conn = get_connection()
        cur = conn.cursor()

        query = """
            INSERT INTO "Recorders"
            (
                empluyee_id,
                machine_id,
                speech_text,
                "timestamp",
                intent,
                "Action"
            )
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, %s)
        """

        cur.execute(query, (
            str(employee_id),
            machine_id,
            speech_text,
            intent,
            action
        ))

        conn.commit()
        cur.close()
        print("✅ New row inserted into Recorders")

    except Exception as e:
        print(f"[DB INSERT ERROR] Recorders: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected to MQTT broker")
        client.subscribe(SUB_TOPIC)
        print(f"📡 Subscribed to: {SUB_TOPIC}")
    else:
        print(f"❌ Connection failed, code: {rc}")


def on_message(client, userdata, msg):
    try:
        payload_text = msg.payload.decode().strip()
        print(f"📩 Received from {msg.topic}: {payload_text}")

        data = json.loads(payload_text)
        if not isinstance(data, dict):
            print("⚠️ Payload must be a JSON object.")
            return

        insert_recorders_row(data)

    except json.JSONDecodeError:
        print("❌ Invalid JSON message received")
    except Exception as e:
        print(f"[MQTT ERROR] {e}")


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)

print("🕓 Waiting for messages for Recorders table...")
client.loop_forever()
