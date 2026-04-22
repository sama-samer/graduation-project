#!/usr/bin/env python3
"""
Simple Database Monitor: Print & Save Table Data in Human-Readable Format
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import time
import os

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

TABLES = ["human_users", "embedded_devices", "voice_records"]
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)

def format_row(row):
    """Convert dict row to a simple string"""
    return " | ".join(f"{k}: {v}" for k, v in row.items())

def fetch_and_log():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    print("[Monitor] Connected to PostgreSQL")

    try:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n=== Snapshot: {timestamp} ===\n")
            
            for table in TABLES:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                log_file = os.path.join(LOG_DIR, f"{table}.txt")
                
                with open(log_file, "a") as f:
                    f.write(f"\n=== Snapshot: {timestamp} ===\n")
                    f.write(f"Table: {table}\n")
                
                print(f"Table: {table} ({len(rows)} rows)")
                for row in rows:
                    row_str = format_row(row)
                    print(row_str)
                    with open(log_file, "a") as f:
                        f.write(row_str + "\n")
            time.sleep(5)  # wait 5 seconds before next snapshot
    except KeyboardInterrupt:
        print("\n[Monitor] Stopped by user")
    finally:
        cursor.close()
        conn.close()
        print("[Monitor] Connection closed")

if __name__ == "__main__":
    fetch_and_log()
