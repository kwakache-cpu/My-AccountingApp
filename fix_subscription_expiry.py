import sqlite3

def add_subscription_expiry_column():
    """Add subscription_expiry column to companies table if it doesn't exist."""
    db_path = 'eka_enterprise_v3.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column exists
    cursor.execute("PRAGMA table_info(companies)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'subscription_expiry' not in columns:
        print("Adding subscription_expiry column to companies table...")
        cursor.execute("ALTER TABLE companies ADD COLUMN subscription_expiry TEXT")
        conn.commit()
        print("Column added successfully.")
    else:
        print("subscription_expiry column already exists.")

    conn.close()

if __name__ == "__main__":
    add_subscription_expiry_column()