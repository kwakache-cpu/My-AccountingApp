import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "database.db"

ALTERS = [
    "ALTER TABLE companies ADD COLUMN subscription_expiry TEXT",
    "ALTER TABLE companies ADD COLUMN deployment_status TEXT DEFAULT 'Pending'",
    "ALTER TABLE companies ADD COLUMN key TEXT",
]


def main():
    print(f"Opening database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for sql in ALTERS:
        try:
            cursor.execute(sql)
            print(f"Applied: {sql}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"Skipped existing column: {sql}")
            else:
                raise

    conn.commit()
    conn.close()
    print("Database fix complete.")


if __name__ == "__main__":
    main()
