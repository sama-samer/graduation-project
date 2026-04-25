import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

def add_device():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        machine_id_range = input("Enter machine_id_range (1-N): ")
        device_ip = input("Enter device_ip: ")
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
            (machine_id_range, device_ip, id_empluyee_response, analysis_volte, analysis_amper,
             analysis_productivity, analysis_stat, analysis_temperature, order_stat, order_production)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
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
        ))

        conn.commit()
        print("✅ Device added successfully")

        cur.close()
        conn.close()

    except Exception as e:
        print("[DB ERROR]", str(e))


if __name__ == "__main__":
    add_device()
