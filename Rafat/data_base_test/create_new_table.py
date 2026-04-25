import psycopg2
from psycopg2 import sql

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "graduation_project",
    "user": "postgres",
    "password": "graduation2026"
}

def create_table():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # ---- Table Name ----
        table_name = input("Enter table name: ")

        # ---- Number of Columns ----
        num_cols = int(input("Enter number of columns: "))

        columns = []

        # ---- Column Input ----
        for i in range(num_cols):
            col_name = input(f"Enter name of column {i+1}: ")
            col_type = input(f"Enter type of column {col_name} (e.g. VARCHAR(50), INT, BYTEA): ")
            columns.append(sql.SQL("{} {}").format(
                sql.Identifier(col_name),
                sql.SQL(col_type)
            ))

        # ---- Build Query ----
        query = sql.SQL("CREATE TABLE IF NOT EXISTS {} ({});").format(
            sql.Identifier(table_name),
            sql.SQL(", ").join(columns)
        )

        # ---- Execute ----
        cur.execute(query)
        conn.commit()

        print(f"[DB] Table '{table_name}' created successfully.")

        cur.close()
        conn.close()

    except Exception as e:
        print("[DB ERROR]", str(e))


# Run
create_table()
