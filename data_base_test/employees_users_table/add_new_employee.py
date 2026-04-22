import psycopg2
import bcrypt

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

def add_employee():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # ---- Inputs ----
        emp_id = input("Enter ID: ")
        username = input("Enter username: ")
        password = input("Enter password: ")
        devices = input("Enter devices range (e.g. 1-10 or dev1,dev2): ")

        role = input("Enter role (employee/manager): ").lower()
        if role not in ["employee", "manager"]:
            print("❌ Invalid role!")
            return

        # ---- Hash password ----
        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # ---- Insert ----
        cur.execute("""
            INSERT INTO employees_users (id, user_name, user_password, devices_assigned, role_commend)
            VALUES (%s, %s, %s, %s, %s)
        """, (emp_id, username, hashed_password, devices, role))

        conn.commit()

        print("[DB] Employee added successfully ✅")

        cur.close()
        conn.close()

    except Exception as e:
        print("[DB ERROR]", str(e))


# Run
add_employee()
