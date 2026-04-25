import json
import re
import psycopg2
import paho.mqtt.client as mqtt
from psycopg2 import sql

BROKER = "192.168.1.8"
PORT = 1884

# Subscribe to all devices
SUB_TOPIC = "esp8266/+/analysis"

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

# Accept only numeric device IDs like 3101, 3102, 3103...
DEVICE_TOPIC_REGEX = re.compile(r"^esp8266/(\d+)/analysis$")


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def get_table_name(machine_id_range):
    return f"Device_{machine_id_range}"


def insert_analysis_row(data, machine_id_range):
    conn = None
    table_name = get_table_name(machine_id_range)

    try:
        conn = get_connection()
        cur = conn.cursor()

        device_ip = data.get("device_ip")
        id_empluyee_response = data.get("id_empluyee_response")
        analysis_volte = to_float(data.get("analysis_volte"))
        analysis_amper = to_float(data.get("analysis_amper"))
        analysis_productivity = data.get("analysis_productivity")
        analysis_stat = to_int(data.get("analysis_stat"))
        analysis_temperature = to_float(data.get("analysis_temperature"))
        order_stat = to_int(data.get("order_stat"))
        order_production = data.get("order_production")

        query = sql.SQL("""
            INSERT INTO {table}
            (
                machine_id_range,
                device_ip,
                id_empluyee_response,
                analysis_volte,
                analysis_amper,
                analysis_productivity,
                analysis_stat,
                analysis_temperature,
                order_stat,
                order_production,
                "timestamp"
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """).format(table=sql.Identifier(table_name))

        cur.execute(
            query,
            (
                machine_id_range,
                device_ip,
                id_empluyee_response,
                analysis_volte,
                analysis_amper,
                analysis_productivity,
                analysis_stat,
                analysis_temperature,
                order_stat,
                order_production
            )
        )

        conn.commit()
        cur.close()
        print(f"✅ New row inserted into {table_name}")

    except Exception as e:
        print(f"[DB INSERT ERROR] {table_name}: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def get_latest_order(machine_id_range):
    """
    Reads the latest order for the same device table.
    """
    conn = None
    table_name = get_table_name(machine_id_range)

    try:
        conn = get_connection()
        cur = conn.cursor()

        query = sql.SQL("""
            SELECT order_stat, order_production
            FROM {table}
            WHERE machine_id_range = %s
              AND (order_stat IS NOT NULL OR order_production IS NOT NULL)
            ORDER BY "timestamp" DESC
            LIMIT 1
        """).format(table=sql.Identifier(table_name))

        cur.execute(query, (machine_id_range,))
        row = cur.fetchone()
        cur.close()

        if row:
            return {
                "machine_id_range": machine_id_range,
                "order_stat": row[0],
                "order_production": row[1]
            }

        return None

    except Exception as e:
        print(f"[DB READ ERROR] {table_name}: {str(e)}")
        return None
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

        match = DEVICE_TOPIC_REGEX.match(msg.topic)
        if not match:
            print("⚠️ Topic format not recognized.")
            return

        machine_id_range = int(match.group(1))

        data = json.loads(payload_text)
        if not isinstance(data, dict):
            print("⚠️ Payload must be a JSON object.")
            return

        # If payload contains a machine_id_range, you can keep it consistent
        payload_machine_id = data.get("machine_id_range")
        if payload_machine_id is not None and int(payload_machine_id) != machine_id_range:
            print("⚠️ machine_id_range in payload does not match topic device ID.")
            return

        # Insert into the correct device table
        insert_analysis_row(data, machine_id_range)

        # Read latest order from the same device table
        order_data = get_latest_order(machine_id_range)
        if order_data is not None:
            order_payload = json.dumps(order_data)
            pub_topic = f"esp8266/{machine_id_range}/order"

            result = client.publish(pub_topic, order_payload)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"📤 Published to {pub_topic}: {order_payload}")
            else:
                print(f"❌ Failed to publish order to {pub_topic}")
        else:
            print(f"⚠️ No order found for device {machine_id_range}")

    except json.JSONDecodeError:
        print("❌ Invalid JSON message received")
    except Exception as e:
        print(f"[MQTT ERROR] {str(e)}")


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)

print("🕓 Waiting for messages from all devices...")
client.loop_forever()
