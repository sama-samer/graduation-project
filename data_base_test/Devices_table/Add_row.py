import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

# ==========================
# Add Device Row
# ==========================
def add_device_row():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 🔴 REQUIRED FIELD (cannot be empty)
        while True:
            machine_id_range = input("Enter machine_id_range (REQUIRED): ")
            if machine_id_range.strip() != "":
                break
            print("❌ machine_id_range is required!")

        # Optional fields
        id_empluyee_response = input("Enter id_empluyee_response: ")
        analysis_volte = input("Enter analysis_volte (FLOAT): ")
        analysis_amper = input("Enter analysis_amper (FLOAT): ")
        analysis_productivity = input("Enter analysis_productivity: ")
        analysis_stat = input("Enter analysis_stat (INT): ")
        analysis_temperature = input("Enter analysis_temperature (FLOAT): ")
        order_stat = input("Enter order_stat (INT): ")
        order_production = input("Enter order_production: ")

        cur.execute("""
            INSERT INTO "Device_3101"
            (machine_id_range, id_empluyee_response, analysis_volte, analysis_amper,
             analysis_productivity, analysis_stat, analysis_temperature, order_stat, order_production)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            machine_id_range,
            id_empluyee_response if id_empluyee_response else None,
            analysis_volte if analysis_volte else None,
            analysis_amper if analysis_amper else None,
            analysis_productivity if analysis_productivity else None,
            analysis_stat if analysis_stat else None,
            analysis_temperature if analysis_temperature else None,
            order_stat if order_stat else None,
            order_production if order_production else None
        ))

        conn.commit()
        print("✅ Device row added successfully")

        cur.close()
        conn.close()

    except Exception as e:
        print("[DB ERROR]", str(e))


if __name__ == "__main__":
    add_device_row()
