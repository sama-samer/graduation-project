import psycopg2
from psycopg2 import sql

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

def drop_table(table_name):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Safe dynamic query
        query = sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
            sql.Identifier(table_name)
        )

        cur.execute(query)
        conn.commit()

        print(f"[DB] Table '{table_name}' deleted successfully.")

        cur.close()
        conn.close()

    except Exception as e:
        print("[DB ERROR]", str(e))


# Example usage
table_to_delete = input("Enter table name to delete: ")
drop_table(table_to_delete)
