import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

# ==========================
# Add Recorder
# ==========================
def add_recorder():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        empluyee_id = input("Enter empluyee_id: ")
        machine_id = input("Enter machine_id (INT): ")
        speech_text = input("Enter speech_text: ")
        timestamp = input("Enter timestamp (YYYY-MM-DD HH:MM:SS): ")
        intent = input("Enter intent: ")
        action = input("Enter action: ")

        cur.execute("""
            INSERT INTO "Recorders"
            (empluyee_id, machine_id, speech_text, timestamp, intent, "Action")
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            empluyee_id, machine_id, speech_text, timestamp, intent, action
        ))

        conn.commit()
        print("✅ Recorder added successfully")

        cur.close()
        conn.close()

    except Exception as e:
        print("[DB ERROR]", str(e))


if __name__ == "__main__":
    add_recorder()
