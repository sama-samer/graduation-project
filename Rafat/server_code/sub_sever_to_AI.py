import json
import psycopg2
import paho.mqtt.client as mqtt
from psycopg2 import sql

# ==========================================
# CONFIGURATION
# ==========================================
BROKER = "192.168.1.8"
PORT = 1884
SUB_TOPIC = "employees/+/recorder"  # Listens to all employees' voice commands

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

# Mapping Intents & Actions to Database Columns
MEASURE_MAP = {
    "READ_VOLT": "analysis_volte",
    "READ_AMPERE": "analysis_amper",
    "READ_TEMPERATURE": "analysis_temperature",
    "READ_PRODUCTION": "analysis_productivity"
}

# ==========================================
# DATABASE HELPERS
# ==========================================
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def log_to_recorders(cur, data):
    """Step 1: Save the raw voice command to the Recorders table."""
    query = """
        INSERT INTO "Recorders"
        (empluyee_id, machine_id, speech_text, "timestamp", intent, "Action")
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, %s)
    """
    cur.execute(query, (
        str(data.get("employee_id")),
        data.get("machine_id"),
        data.get("speech_text"),
        data.get("intent"),
        data.get("Action")
    ))
    print(f"✅ Logged to Recorders: Emp {data.get('employee_id')} -> Mach {data.get('machine_id')}")

def check_table_exists(cur, machine_id):
    """Step 2: Ensure the target device table actually exists."""
    table_name = f"Device_{machine_id}"
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = %s OR table_name = %s
        )
    """, (table_name, table_name.lower()))
    return cur.fetchone()[0]

def check_permission(cur, employee_id, machine_id_str):
    """Step 3: Verify if the employee is assigned to this machine."""
    print(f"\n[DEBUG] Checking permission for Emp: '{employee_id}', Machine: '{machine_id_str}'")
    
    # We use TRIM(id) to ignore any accidental spaces saved in the database
    cur.execute("SELECT devices_assigned FROM employees_users WHERE TRIM(id) = %s", (str(employee_id).strip(),))
    row = cur.fetchone()
    
    if not row:
        print("[DEBUG] ❌ Employee ID not found in database! (Check if the ID exists)")
        return False
        
    assigned_str = row[0]
    print(f"[DEBUG] 🔎 Found assigned devices in DB: '{assigned_str}'")
    
    if not assigned_str:
        print("[DEBUG] ❌ The devices_assigned column is empty!")
        return False
        
    try:
        m_id = int(machine_id_str)
        
        # Split by comma in case there are multiple ranges like "3100-3102, 4000-4010"
        for part in assigned_str.split(','):
            part = part.strip()
            print(f"[DEBUG] 🧮 Evaluating rule: '{part}'")
            
            if '-' in part:
                start, end = part.split('-')
                if int(start) <= m_id <= int(end):
                    print(f"[DEBUG] ✅ SUCCESS! {m_id} is between {start} and {end}")
                    return True
                else:
                    print(f"[DEBUG] ❌ FAIL! {m_id} is NOT between {start} and {end}")
            elif part.isdigit():
                if int(part) == m_id:
                    print(f"[DEBUG] ✅ SUCCESS! {m_id} matches {part} exactly")
                    return True
                else:
                    print(f"[DEBUG] ❌ FAIL! {m_id} does not match {part}")
        
        print("[DEBUG] ❌ Exhausted all rules, no match found.")
        return False
        
    except ValueError as e:
        print(f"[DEBUG] ❌ Value Error during conversion: {e}")
        return False
# ==========================================
# INTENT HANDLERS
# ==========================================
def handle_measure(cur, machine_id, action):
    """Step 4a: Handle MEASURE intent by fetching latest data from device table."""
    table_name = f"Device_{machine_id}"
    
    if action == "READ_ALL_SENSORS":
        columns = ["analysis_volte", "analysis_amper", "analysis_temperature", "analysis_productivity"]
    else:
        columns = [MEASURE_MAP.get(action)]
        if not columns[0]:
            print(f"⚠️ Unknown measure action: {action}")
            return

    # Build dynamic SELECT query for the requested columns
    cols_sql = sql.SQL(', ').join(map(sql.Identifier, columns))
    query = sql.SQL("""
        SELECT {cols} FROM {table}
        ORDER BY "timestamp" DESC
        LIMIT 1
    """).format(
        cols=cols_sql,
        table=sql.Identifier(table_name)
    )
    
    cur.execute(query)
    result = cur.fetchone()
    
    if result:
        print(f"📊 MEASURE RESULT for {table_name}:")
        for col_name, val in zip(columns, result):
            print(f"   -> {col_name}: {val}")
    else:
        print(f"⚠️ No data found in {table_name}")

def handle_order(cur, machine_id, action, employee_id, quantity=None):
    """Step 4b: Handle ORDER intent by inserting a command row into device table."""
    table_name = f"Device_{machine_id}"
    
    order_stat = None
    order_production = None
    
    if action == "OPEN":
        order_stat = 1
    elif action == "CLOSE":
        order_stat = 0
    elif action == "PRODUCE":
        order_production = quantity if quantity else 1 # Default to 1 if no quantity given
    else:
        print(f"⚠️ Unknown order action: {action}")
        return

    query = sql.SQL("""
        INSERT INTO {table}
        (machine_id_range, id_empluyee_response, order_stat, order_production, "timestamp")
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
    """).format(table=sql.Identifier(table_name))
    
    cur.execute(query, (int(machine_id), str(employee_id), order_stat, order_production))
    print(f"⚙️ ORDER DISPATCHED: {action} applied to {table_name}")

# ==========================================
# MAIN PIPELINE PROCESSOR
# ==========================================
def process_command(data):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        employee_id = data.get("employee_id")
        machine_id = data.get("machine_id")
        intent = data.get("intent")
        action = data.get("Action")
        
        # 1. Log everything to Recorders table immediately
        log_to_recorders(cur, data)
        conn.commit() # Commit log regardless of what happens next

        # Basic validation
        if not employee_id or not machine_id or machine_id == "99999":
            print("❌ Invalid Employee ID or Machine ID. Aborting execution.")
            return

        # 2. Verify Table Exists
        if not check_table_exists(cur, machine_id):
            print(f"❌ Table Device_{machine_id} does not exist. Aborting.")
            return

        # 3. Verify Permissions
        if not check_permission(cur, employee_id, machine_id):
            print(f"⛔ PERMISSION DENIED: Employee {employee_id} cannot access Machine {machine_id}")
            return
            
        print(f"🔓 Permission Granted for Employee {employee_id} -> Machine {machine_id}")

        # 4. Route by Intent
        if intent == "MEASURE":
            handle_measure(cur, machine_id, action)
        elif intent == "ORDER":
            qty = data.get("quantity") # If your voice app passes quantity for "PRODUCE"
            handle_order(cur, machine_id, action, employee_id, qty)
        else:
            print(f"⚠️ Intent '{intent}' not recognized for execution.")

        conn.commit()
        cur.close()

    except Exception as e:
        print(f"[PROCESS ERROR] {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# ==========================================
# MQTT CALLBACKS
# ==========================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Main Server connected to MQTT Broker")
        client.subscribe(SUB_TOPIC)
        print(f"📡 Listening to Voice Commands on: {SUB_TOPIC}")
    else:
        print(f"❌ Connection failed, code: {rc}")

def on_message(client, userdata, msg):
    try:
        payload_text = msg.payload.decode().strip()
        print(f"\n--- 📩 New Command from {msg.topic} ---")
        
        data = json.loads(payload_text)
        if not isinstance(data, dict):
            print("⚠️ Payload must be JSON.")
            return

        # Pass parsed JSON straight into the pipeline
        process_command(data)

    except json.JSONDecodeError:
        print("❌ Invalid JSON received")
    except Exception as e:
        print(f"[MQTT ERROR] {e}")

# ==========================================
# INITIALIZATION
# ==========================================
if __name__ == "__main__":
    client = mqtt.Client(client_id="Industrial_Main_Server")
    client.on_connect = on_connect
    client.on_message = on_message

    print("🔌 Starting Industrial Main Server...")
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server Shutting Down.")
    except Exception as e:
        print(f"❌ Server Boot Error: {e}")
