import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "database.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # STEP 1: Create the table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # STEP 2: Add missing columns one by one
    columns_to_add = [
        ("subscription_expiry", "TEXT"),
        ("deployment_status", "TEXT DEFAULT 'Pending'"),
        ("status", "TEXT DEFAULT 'Active'"),
        ("plan_type", "TEXT DEFAULT 'Basic'"),
        ("currency", "TEXT DEFAULT 'GHS'")
    ]

    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}")
            print(f"✅ Added column: {col_name}")
        except sqlite3.OperationalError:
            print(f"ℹ️  Column {col_name} already exists, skipping.")

    # STEP 3: Ensure maintenance table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_settings (
            id INTEGER PRIMARY KEY,
            is_active INTEGER DEFAULT 0,
            message TEXT
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO maintenance_settings (id, message) VALUES (1, 'System Normal')")

    conn.commit()
    conn.close()
    print("\n🚀 DATABASE FIX COMPLETE. YOU CAN NOW RUN THE APP.")

if __name__ == "__main__":
    main()