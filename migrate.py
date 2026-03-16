import sqlite3

# Connect to your database file (usually database.db)
conn = sqlite3.connect('database.db') 
cursor = conn.cursor()

try:
    # Run the migration command
    cursor.execute("ALTER TABLE companies ADD COLUMN deployment_status TEXT DEFAULT 'Pending'")
    conn.commit()
    print("✅ Migration successful: 'deployment_status' column added.")
except sqlite3.OperationalError:
    print("⚠️ Column already exists or table 'companies' not found.")
finally:
    conn.close()