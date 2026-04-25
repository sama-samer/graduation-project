#!/usr/bin/env python3
"""
Full CRUD for human_users and embedded_devices
- Supports all columns
- Easy to change parameters including TARGET_ID
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# ----------------------------
# DATABASE CONFIG
# ----------------------------
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

# ----------------------------
# OPERATION SETTINGS
# ----------------------------
OPERATION = "update"       # "add", "update", "delete"
TABLE = "human_users"   # "human_users" or "embedded_devices"
TARGET_ID = 2           # Set ID for update/delete. For add, leave None or remove

# ----------------------------
# TABLE-SPECIFIC PARAMETERS
# ----------------------------
# For ADD or UPDATE: specify values for all columns you want to set
TABLE_PARAMS = {
    "human_users": {
        "id": TARGET_ID,  # Optional: only for update if needed if no but TARGET_ID
        "full_name": "Ahmed Osama",
        "password": "hashed_pass",
        "phone_number": "01020",
        "department": "IT",
        "device_ip": "192.168.1.10",
        "device_mac": "AA:BB:CC:DD:EE:FF",
        "mqtt_client_id": "mqtt_user_1",
        "last_login": datetime.now(),
        "last_activity": datetime.now(),
        "total_records_sent": 0,
        "total_data_sent_bytes": 0,
        "transcription": "Start machine"
    },
    "embedded_devices": {
        "id": TARGET_ID,  # Optional: only for update if needed
        "device_name": "ESP32 Controller",
        "device_serial_number": "ESP32-010",
        "device_type": "ESP32",
        "hardware_version": "v1.0",
        "ip_address": "192.168.1.50",
        "mac_address": "FF:EE:DD:CC:BB:AA",
        "mqtt_client_id": "mqtt_device_1",
        "location": "Line A",
        "status": "online",
        "last_seen": datetime.now(),
        "temperature": 36.5,
        "voltage": 5.0,
        "current": 0.3,
        "cpu_usage": 12.5,
        "ai_control_enabled": True,
        "security_key": "secure123"
    }
}

PARAMS = TABLE_PARAMS[TABLE]

# ----------------------------
# DATABASE CONNECTION
# ----------------------------
conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor(cursor_factory=RealDictCursor)

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def add():
    # Remove id if present (SERIAL column)
    params_to_use = {k: v for k, v in PARAMS.items() if k != "id"}
    columns = ", ".join(params_to_use.keys())
    placeholders = ", ".join(["%s"] * len(params_to_use))
    values = list(params_to_use.values())
    query = f"INSERT INTO {TABLE} ({columns}) VALUES ({placeholders}) RETURNING id;"
    cursor.execute(query, values)
    conn.commit()
    print(f"[ADD] {TABLE} added with ID {cursor.fetchone()['id']}")

def update():
    if TARGET_ID is None:
        print("[ERROR] TARGET_ID must be set for update")
        return
    # Remove id from update fields
    params_to_use = {k: v for k, v in PARAMS.items() if k != "id"}
    fields = ", ".join(f"{k}=%s" for k in params_to_use.keys())
    values = list(params_to_use.values()) + [TARGET_ID]
    query = f"UPDATE {TABLE} SET {fields} WHERE id=%s"
    cursor.execute(query, values)
    conn.commit()
    print(f"[UPDATE] {TABLE} ID {TARGET_ID} updated")

def delete():
    if TARGET_ID is None:
        print("[ERROR] TARGET_ID must be set for delete")
        return
    query = f"DELETE FROM {TABLE} WHERE id=%s"
    cursor.execute(query, (TARGET_ID,))
    conn.commit()
    print(f"[DELETE] {TABLE} ID {TARGET_ID} deleted")

# ----------------------------
# RUN OPERATION
# ----------------------------
if OPERATION == "add":
    add()
elif OPERATION == "update":
    update()
elif OPERATION == "delete":
    delete()
else:
    print("[ERROR] Unknown operation. Use 'add', 'update', or 'delete'.")

cursor.close()
conn.close()
