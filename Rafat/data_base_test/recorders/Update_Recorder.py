import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

# ==========================
# Validate employee_id exists
# ==========================
def get_valid_employee_id(cur):
    while True:
        emp_id = input("Enter empluyee_id to update: ")

        cur.execute('SELECT 1 FROM "Recorders" WHERE empluyee_id = %s', (emp_id,))
        if cur.fetchone():
            return emp_id
        else:
            print("❌ Invalid empluyee_id! Try again.")

# ==========================
# Update Recorder
# ==========================
def update_recorder():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 🔹 Search by employee_id
        empluyee_id = get_valid_employee_id(cur)

        print("Leave field empty if you don't want to change it.")

        # ---- Inputs ----
        new_machine_id = input("New machine_id (INT): ")
        speech_text = input("New speech_text: ")
        timestamp = input("New timestamp (YYYY-MM-DD HH:MM:SS): ")
        intent = input("New intent: ")
        action = input("New action: ")

        updates = []
        values = []

        if new_machine_id:
            updates.append("machine_id = %s")
            values.append(new_machine_id)

        if speech_text:
            updates.append("speech_text = %s")
            values.append(speech_text)

        if timestamp:
            updates.append("timestamp = %s")
            values.append(timestamp)

        if intent:
            updates.append("intent = %s")
            values.append(intent)

        if action:
            updates.append('"Action" = %s')
            values.append(action)

        if not updates:
            print("⚠️ Nothing to update.")
            return

        values.append(empluyee_id)

        query = f'''
            UPDATE "Recorders"
            SET {", ".join(updates)}
            WHERE empluyee_id = %s
        '''

        cur.execute(query, values)
        conn.commit()

        print("✅ Recorder updated successfully")

        cur.close()
        conn.close()

    except Exception as e:
        print("[DB ERROR]", str(e))


if __name__ == "__main__":
    update_recorder()
