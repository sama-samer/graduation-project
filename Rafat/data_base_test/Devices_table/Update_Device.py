import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

# ==========================
# Validate machine exists
# ==========================
def get_valid_machine_id(cur):
    while True:
        mid = input("Enter machine_id_range to update: ")

        cur.execute('SELECT 1 FROM "Device_3101" WHERE machine_id_range = %s', (mid,))
        if cur.fetchone():
            return mid

        print("❌ Invalid ID! Try again.")

# ==========================
# Update Device
# ==========================
def update_device():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # old ID (used to find row)
        old_machine_id = get_valid_machine_id(cur)

        print("Leave field empty if you don't want to change it.")

        # NEW: allow changing ID
        new_machine_id = input("New machine_id_range (leave empty to keep same): ")

        id_employee_response = input("New id_empluyee_response: ")
        analysis_volte = input("New analysis_volte (FLOAT): ")
        analysis_amper = input("New analysis_amper (FLOAT): ")
        analysis_productivity = input("New analysis_productivity: ")
        analysis_stat = input("New analysis_stat (INT): ")
        analysis_temperature = input("New analysis_temperature (FLOAT): ")
        order_stat = input("New order_stat (INT): ")
        order_production = input("New order_production: ")

        updates = []
        values = []

        # ✅ allow ID update
        if new_machine_id:
            updates.append("machine_id_range = %s")
            values.append(new_machine_id)

        if id_employee_response:
            updates.append("id_empluyee_response = %s")
            values.append(id_employee_response)

        if analysis_volte:
            updates.append("analysis_volte = %s")
            values.append(analysis_volte)

        if analysis_amper:
            updates.append("analysis_amper = %s")
            values.append(analysis_amper)

        if analysis_productivity:
            updates.append("analysis_productivity = %s")
            values.append(analysis_productivity)

        if analysis_stat:
            updates.append("analysis_stat = %s")
            values.append(analysis_stat)

        if analysis_temperature:
            updates.append("analysis_temperature = %s")
            values.append(analysis_temperature)

        if order_stat:
            updates.append("order_stat = %s")
            values.append(order_stat)

        if order_production:
            updates.append("order_production = %s")
            values.append(order_production)

        if not updates:
            print("⚠️ Nothing to update.")
            return

        values.append(old_machine_id)

        query = f"""
            UPDATE "Device_3101"
            SET {', '.join(updates)}
            WHERE machine_id_range = %s
        """

        cur.execute(query, values)
        conn.commit()

        print("✅ Device updated successfully")

        cur.close()
        conn.close()

    except Exception as e:
        print("[DB ERROR]", str(e))


if __name__ == "__main__":
    update_device()
