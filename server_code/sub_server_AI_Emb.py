#!/usr/bin/env python3
"""
fully_debugged_industrial_server.py

This server includes extreme verbosity. It prints every single action, 
variable state, and database transaction to the terminal for deep debugging.
"""

import json
import re
import psycopg2
import paho.mqtt.client as mqtt
from psycopg2 import sql

# ==========================================
# CONFIGURATION
# ==========================================
BROKER = "192.168.1.8"
PORT = 1884

TOPIC_VOICE = "employees/+/recorder"
TOPIC_DEVICES = "esp8266/+/analysis"
DEVICE_TOPIC_REGEX = re.compile(r"^esp8266/(\d+)/analysis$")

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

MEASURE_MAP = {
    "READ_VOLT": "analysis_volte",
    "READ_AMPERE": "analysis_amper",
    "READ_TEMPERATURE": "analysis_temperature",
    "READ_PRODUCTION": "analysis_productivity"
}

# ==========================================
# UTILITY FUNCTIONS
# ==========================================
def get_connection():
    print("[DEBUG-DB] Attempting to connect to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    print("[DEBUG-DB] Connection successful.")
    return conn

def to_float(value):
    if value is None or value == "": return None
    try: return float(value)
    except ValueError: return None

def to_int(value):
    if value is None or value == "": return None
    try: return int(value)
    except ValueError: return None

def get_table_name(machine_id):
    return f"Device_{machine_id}"

# ==========================================
# DATABASE: COMMON SECURITY & CHECKS
# ==========================================
def check_table_exists(cur, machine_id):
    table_name = get_table_name(machine_id)
    print(f"[DEBUG-DB] Checking if table '{table_name}' exists in database...")
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = %s OR table_name = %s
        )
    """, (table_name, table_name.lower()))
    exists = cur.fetchone()[0]
    print(f"[DEBUG-DB] Table '{table_name}' exists: {exists}")
    return exists

def check_permission(cur, employee_id, machine_id_str):
    print(f"[DEBUG-AUTH] Verifying permissions for Employee: '{employee_id}', Machine: '{machine_id_str}'")
    cur.execute("SELECT devices_assigned FROM employees_users WHERE TRIM(id) = %s", (str(employee_id).strip(),))
    row = cur.fetchone()
    
    if not row or not row[0]:
        print("[DEBUG-AUTH] ❌ Employee ID not found or devices_assigned is empty.")
        return False
        
    assigned_str = row[0]
    print(f"[DEBUG-AUTH] 🔎 Found assigned devices in DB: '{assigned_str}'")
    
    try:
        m_id = int(machine_id_str)
        for part in assigned_str.split(','):
            part = part.strip()
            print(f"[DEBUG-AUTH] 🧮 Evaluating rule: '{part}' against target {m_id}")
            
            if '-' in part:
                start, end = part.split('-')
                if int(start) <= m_id <= int(end): 
                    print(f"[DEBUG-AUTH] ✅ Match! {m_id} is between {start} and {end}")
                    return True
            elif part.isdigit():
                if int(part) == m_id: 
                    print(f"[DEBUG-AUTH] ✅ Match! {m_id} matches {part} exactly")
                    return True
                    
        print("[DEBUG-AUTH] ❌ Exhausted all rules, no permission match found.")
        return False
    except ValueError as e:
        print(f"[DEBUG-AUTH] ❌ Value Error during conversion: {e}")
        return False

# ==========================================
# PATHWAY A: VOICE COMMAND LOGIC
# ==========================================
def process_voice_command(mqtt_client, data):
    print("\n" + "="*40)
    print("[DEBUG-VOICE] --- STARTING VOICE PIPELINE ---")
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        employee_id = data.get("employee_id")
        machine_id = data.get("machine_id")
        intent = data.get("intent")
        action = data.get("Action")
        
        print(f"[DEBUG-VOICE] Extracted Data -> Emp: {employee_id}, Mach: {machine_id}, Intent: {intent}, Action: {action}")

        # 1. Log to Recorders
        print("[DEBUG-VOICE] Executing INSERT into 'Recorders' table...")
        cur.execute("""
            INSERT INTO "Recorders" (empluyee_id, machine_id, speech_text, "timestamp", intent, "Action")
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, %s)
        """, (str(employee_id), machine_id, data.get("speech_text"), intent, action))
        conn.commit()
        print("[DEBUG-VOICE] ✅ Successfully logged to Recorders.")

        # Validation & Permissions
        if not employee_id or not machine_id or machine_id == "99999": 
            print("[DEBUG-VOICE] ❌ Invalid IDs detected. Aborting pipeline.")
            return
            
        if not check_table_exists(cur, machine_id):
            print(f"[DEBUG-VOICE] ❌ Aborting: Device table does not exist.")
            return
            
        if not check_permission(cur, employee_id, machine_id):
            print(f"[DEBUG-VOICE] ⛔ Aborting: Permission Denied.")
            return
            
        print("[DEBUG-VOICE] 🔓 Security cleared. Routing Intent...")

        # Route Intent
        if intent == "MEASURE":
            print("[DEBUG-VOICE] ➡️ Routing to MEASURE handler.")
            table_name = get_table_name(machine_id)
            cols = ["analysis_volte", "analysis_amper", "analysis_temperature", "analysis_productivity"] if action == "READ_ALL_SENSORS" else [MEASURE_MAP.get(action)]
            
            if cols[0]:
                print(f"[DEBUG-VOICE] Preparing to SELECT columns {cols} from {table_name}")
                cols_sql = sql.SQL(', ').join(map(sql.Identifier, cols))
                query = sql.SQL('SELECT {cols} FROM {table} ORDER BY "timestamp" DESC LIMIT 1').format(cols=cols_sql, table=sql.Identifier(table_name))
                cur.execute(query)
                res = cur.fetchone()
                if res:
                    print(f"📊 [VOICE-RESULT] MEASURE for {table_name}: {dict(zip(cols, res))}")
                else:
                    print(f"[DEBUG-VOICE] ⚠️ Query executed, but table {table_name} is empty.")

        elif intent == "ORDER":
            print("[DEBUG-VOICE] ➡️ Routing to ORDER handler.")
            table_name = get_table_name(machine_id)
            order_stat = 1 if action == "OPEN" else 0 if action == "CLOSE" else None
            qty = data.get("quantity") or 1 if action == "PRODUCE" else None
            
            print(f"[DEBUG-VOICE] Formulating Order -> Stat: {order_stat}, Qty: {qty}")
            
            # Insert order
            query = sql.SQL("""
                INSERT INTO {table} (machine_id_range, id_empluyee_response, order_stat, order_production, "timestamp")
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """).format(table=sql.Identifier(table_name))
            print(f"[DEBUG-VOICE] Executing INSERT into {table_name}...")
            cur.execute(query, (int(machine_id), str(employee_id), order_stat, qty))
            
            # Broadcast to machine instantly
            pub_topic = f"esp8266/{machine_id}/order"
            payload = json.dumps({"machine_id": int(machine_id), "action": action, "order_stat": order_stat})
            print(f"[DEBUG-VOICE] Preparing MQTT Publish to topic: {pub_topic}")
            print(f"[DEBUG-VOICE] Payload: {payload}")
            
            res = mqtt_client.publish(pub_topic, payload)
            if res.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"⚙️ [VOICE-RESULT] ✅ ORDER SAVED & BROADCASTED to {pub_topic}")
            else:
                print(f"[DEBUG-VOICE] ❌ Failed to publish to MQTT broker. Code: {res.rc}")

        conn.commit()
        print("[DEBUG-VOICE] --- END OF VOICE PIPELINE (Committed) ---")
    except Exception as e:
        print(f"❌ [VOICE PROCESS ERROR] Exception caught: {e}")
        if conn: 
            print("[DEBUG-VOICE] Rolling back database transactions.")
            conn.rollback()
    finally:
        if conn: 
            print("[DEBUG-DB] Closing DB connection.")
            conn.close()

# ==========================================
# PATHWAY B: ESP8266 DEVICE LOGIC
# ==========================================
def process_device_analysis(mqtt_client, payload_text, machine_id):
    print("\n" + "="*40)
    print(f"[DEBUG-DEVICE] --- STARTING DEVICE PIPELINE FOR MACHINE {machine_id} ---")
    data = json.loads(payload_text)
    table_name = get_table_name(machine_id)
    conn = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        print(f"[DEBUG-DEVICE] Formatting sensor data for table {table_name}...")
        v_volt = to_float(data.get("analysis_volte"))
        v_amp = to_float(data.get("analysis_amper"))
        v_temp = to_float(data.get("analysis_temperature"))
        
        print(f"[DEBUG-DEVICE] Parsed Sensors -> Volt: {v_volt}, Amp: {v_amp}, Temp: {v_temp}")

        # 1. Insert Sensor Data
        print(f"[DEBUG-DEVICE] Executing INSERT into {table_name}...")
        query = sql.SQL("""
            INSERT INTO {table}
            (machine_id_range, id_empluyee_response, analysis_volte, analysis_amper, 
             analysis_productivity, analysis_stat, analysis_temperature, order_stat, 
             order_production, "timestamp")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """).format(table=sql.Identifier(table_name))

        cur.execute(query, (
            machine_id,
            data.get("id_empluyee_response"),
            v_volt,
            v_amp,
            data.get("analysis_productivity"),
            to_int(data.get("analysis_stat")),
            v_temp,
            to_int(data.get("order_stat")),
            data.get("order_production")
        ))
        print(f"✅ [DEVICE-RESULT] Sensor data successfully inserted into {table_name}")

        # 2. Fetch Latest Order
        print(f"[DEBUG-DEVICE] Querying {table_name} for latest pending orders...")
        query_order = sql.SQL("""
            SELECT order_stat, order_production FROM {table}
            WHERE machine_id_range = %s AND (order_stat IS NOT NULL OR order_production IS NOT NULL)
            ORDER BY "timestamp" DESC LIMIT 1
        """).format(table=sql.Identifier(table_name))
        
        cur.execute(query_order, (machine_id,))
        row = cur.fetchone()

        if row:
            print(f"[DEBUG-DEVICE] Found pending order in DB -> Stat: {row[0]}, Prod: {row[1]}")
            order_payload = json.dumps({"machine_id_range": machine_id, "order_stat": row[0], "order_production": row[1]})
            pub_topic = f"esp8266/{machine_id}/order"
            print(f"[DEBUG-DEVICE] Publishing order back to ESP8266 on topic: {pub_topic} | Payload: {order_payload}")
            
            res = mqtt_client.publish(pub_topic, order_payload)
            if res.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"📤 [DEVICE-RESULT] ✅ Polled order returned to {pub_topic}")
            else:
                print(f"[DEBUG-DEVICE] ❌ Failed to publish to MQTT broker.")
        else:
            print("[DEBUG-DEVICE] No pending orders found for this machine.")

        conn.commit()
        print("[DEBUG-DEVICE] --- END OF DEVICE PIPELINE (Committed) ---")
    except Exception as e:
        print(f"❌ [DEVICE PROCESS ERROR] Exception caught: {e}")
        if conn: 
            print("[DEBUG-DEVICE] Rolling back database transactions.")
            conn.rollback()
    finally:
        if conn: 
            print("[DEBUG-DB] Closing DB connection.")
            conn.close()


# ==========================================
# MQTT CALLBACKS & ROUTING
# ==========================================
def on_connect(client, userdata, flags, rc):
    print(f"[DEBUG-MQTT] on_connect triggered. Return code: {rc}")
    if rc == 0:
        print("✅ [MQTT] Unified Main Server connected to MQTT Broker")
        client.subscribe(TOPIC_VOICE)
        client.subscribe(TOPIC_DEVICES)
        print(f"📡 [MQTT] Subscribed to Voice: {TOPIC_VOICE}")
        print(f"📡 [MQTT] Subscribed to Devices: {TOPIC_DEVICES}")
    else:
        print(f"❌ [MQTT] Connection failed, code: {rc}")

def on_message(client, userdata, msg):
    try:
        payload_text = msg.payload.decode().strip()
        topic = msg.topic
        print(f"\n[DEBUG-MQTT] 🔔 MESSAGE RECEIVED -> Topic: '{topic}' | Raw Payload: '{payload_text}'")
        
        # --- ROUTER ---
        if topic.startswith("employees/"):
            data = json.loads(payload_text)
            print(f"[DEBUG-MQTT] Parsed as Voice JSON: {data}")
            process_voice_command(client, data)
            
        elif topic.startswith("esp8266/"):
            match = DEVICE_TOPIC_REGEX.match(topic)
            if match:
                machine_id = int(match.group(1))
                print(f"[DEBUG-MQTT] Parsed as Device Sensor Data. Machine ID: {machine_id}")
                process_device_analysis(client, payload_text, machine_id)
            else:
                print(f"⚠️ [DEBUG-MQTT] Unrecognized device topic structure: {topic}")
        else:
            print(f"⚠️ [DEBUG-MQTT] Topic not handled by router: {topic}")

    except json.JSONDecodeError:
        print("❌ [DEBUG-MQTT] Invalid JSON received. Cannot parse.")
    except Exception as e:
        print(f"❌ [MQTT ROUTER ERROR] Exception: {e}")

# ==========================================
# SYSTEM BOOT
# ==========================================
if __name__ == "__main__":
    print("[DEBUG-SYSTEM] Initializing MQTT Client...")
    client = mqtt.Client(client_id="Unified_Industrial_Server_Debug")
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[DEBUG-SYSTEM] Attempting to connect to MQTT Broker at {BROKER}:{PORT}...")
    try:
        client.connect(BROKER, PORT, 60)
        print("[DEBUG-SYSTEM] Handing thread to MQTT loop_forever()...")
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n🛑 [DEBUG-SYSTEM] Keyboard Interrupt detected. Server Shutting Down.")
    except Exception as e:
        print(f"❌ [DEBUG-SYSTEM] Server Boot Error: {e}")
