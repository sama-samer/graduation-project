import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}


def create_device_table(device_id):
    table_name = f'Device_{device_id}'

    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{table_name}" (

                id SERIAL PRIMARY KEY,

                machine_id_range INTEGER,
                id_empluyee_response VARCHAR(20),

                analysis_volte DOUBLE PRECISION,
                analysis_amper DOUBLE PRECISION,
                analysis_productivity TEXT,
                analysis_stat INTEGER,
                analysis_temperature DOUBLE PRECISION,

                order_stat INTEGER,
                order_production TEXT,

                "timestamp" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()
        cur.close()

        print(f"✅ Table {table_name} created successfully (FIXED KEY)")

    except Exception as e:
        print(f"[DB ERROR] {e}")
        if conn:
            conn.rollback()

    finally:
        if conn:
            conn.close()


# ================= RUN =================
if __name__ == "__main__":
    device_id = input("Enter device ID (e.g. 3101): ")
    create_device_table(device_id)
