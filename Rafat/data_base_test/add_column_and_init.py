#!/usr/bin/env python3
"""
Add a new column to an existing table and initialize all rows with a default value.
"""

import psycopg2

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
# COLUMN TYPES EXAMPLES
# ----------------------------

# VARCHAR(n) : Variable-length string, max length n
# Example: VARCHAR(50) -> can store up to 50 characters
# Good for names, emails, short descriptions

# TEXT : Variable-length string, unlimited size
# Example: transcription TEXT
# Good for long text, notes, comments

# INT / INTEGER : Whole numbers
# Example: INT -> 1, 25, 1000
# Good for IDs, counters, quantities

# BIGINT : Very large whole numbers
# Example: BIGINT -> 9223372036854775807
# Good for big counters or bytes sent

# FLOAT / REAL / DOUBLE PRECISION : Numbers with decimals
# Example: FLOAT -> 3.14, 36.5
# Good for temperature, voltage, percentage, sensor readings

# BOOLEAN : True / False
# Example: ai_control_enabled BOOLEAN -> True or False
# Good for switches, yes/no values, flags

# DATE / TIME / TIMESTAMP : Date and time values
# Example: last_login TIMESTAMP -> 2026-03-01 18:45:00
# Good for logging when something happened

# SERIAL : Auto-increment integer (used for primary keys)
# Example: id SERIAL PRIMARY KEY
# Automatically generates a unique number for each new row

# INET / CIDR : Stores IP addresses
# Example: device_ip INET -> 192.168.1.10
# Good for IP address columns

# UNIQUE : Ensures no duplicate values in this column
# Example: device_serial_number VARCHAR(100) UNIQUE
# Prevents inserting same serial number twice
# ----------------------------
# SETTINGS: change these
# ----------------------------
TABLE = "human_users"          # Table to modify "human_users" or "embedded_devices"
NEW_COLUMN = "last_record"       # Name of new column
COLUMN_TYPE = "BYTEA"    # Column type (e.g., VARCHAR(50), INT, BOOLEAN)
DEFAULT_VALUE = "order"         # Initial value for all existing rows

# ----------------------------
# CONNECT TO DATABASE
# ----------------------------
conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# ----------------------------
# ADD COLUMN
# ----------------------------
try:
    cursor.execute(f"ALTER TABLE {TABLE} ADD COLUMN {NEW_COLUMN} {COLUMN_TYPE};")
    print(f"[INFO] Column '{NEW_COLUMN}' added to '{TABLE}'")
except psycopg2.errors.DuplicateColumn:
    print(f"[INFO] Column '{NEW_COLUMN}' already exists")
    conn.rollback()

# ----------------------------
# INITIALIZE ALL ROWS
# ----------------------------
cursor.execute(f"UPDATE {TABLE} SET {NEW_COLUMN} = %s;", (DEFAULT_VALUE,))
conn.commit()
print(f"[INFO] Initialized '{NEW_COLUMN}' for all rows with '{DEFAULT_VALUE}'")

# ----------------------------
# CLOSE CONNECTION
# ----------------------------
cursor.close()
conn.close()
