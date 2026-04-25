import psycopg2
import bcrypt

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

# ==========================
# Validate Employee ID
# ==========================
def get_valid_employee_id(cur):
    while True:
        emp_id = input("Enter employee ID to update: ")

        cur.execute("SELECT 1 FROM employees_users WHERE id = %s", (emp_id,))
        if cur.fetchone():
            return emp_id
        else:
            print("❌ Invalid ID! Please try again.")

# ==========================
# Validate Devices Range
# ==========================
def get_valid_devices():
    while True:
        devices = input("New devices range: ")

        if devices == "":
            return ""

        # Single number (e.g. 5)
        if devices.isdigit():
            return devices

        # Range (e.g. 1-20)
        if "-" in devices:
            parts = devices.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                if int(parts[0]) <= int(parts[1]):
                    return devices

        print("❌ Invalid format! Use '5' or '1-20'")

# ==========================
# Validate Role
# ==========================
def get_valid_role():
    while True:
        role = input("New role (employee/manager): ").lower()

        if role == "":
            return ""

        if role in ["employee", "manager"]:
            return role

        print("❌ Invalid role! Choose 'employee' or 'manager'")

# ==========================
# Update Employee
# ==========================
def update_employee():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Get valid ID
        emp_id = get_valid_employee_id(cur)

        print("Leave field empty if you don't want to change it.")

        username = input("New username: ")
        password = input("New password: ")
        devices = get_valid_devices()
        role = get_valid_role()

        updates = []
        values = []

        if username:
            updates.append("user_name = %s")
            values.append(username)

        if password:
            hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            updates.append("user_password = %s")
            values.append(hashed_password)

        if devices:
            updates.append("devices_assigned = %s")
            values.append(devices)

        if role:
            updates.append("role_commend = %s")
            values.append(role)

        if not updates:
            print("⚠️ Nothing to update.")
            return

        values.append(emp_id)

        query = f"""
            UPDATE employees_users
            SET {', '.join(updates)}
            WHERE id = %s
        """

        cur.execute(query, values)
        conn.commit()

        print("✅ Employee updated successfully")

        cur.close()
        conn.close()

    except Exception as e:
        print("[DB ERROR]", str(e))


# ==========================
# Run البرنامج
# ==========================
if __name__ == "__main__":
    update_employee()
