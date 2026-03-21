import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "database.db"


def table_exists(cursor, table_name):
    row = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def get_existing_columns(cursor, table_name):
    if not table_exists(cursor, table_name):
        return []
    rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [row[1] for row in rows]


def fetch_companies_backup(cursor):
    if not table_exists(cursor, "companies"):
        return []

    columns = get_existing_columns(cursor, "companies")
    if not columns:
        return []

    rows = cursor.execute("SELECT * FROM companies").fetchall()
    backup = []

    for row in rows:
        row_map = dict(zip(columns, row))
        backup.append(
            {
                "key": row_map.get("key"),
                "name": row_map.get("name"),
                "sub_admin_key": row_map.get("sub_admin_key"),
                "staff_key": row_map.get("staff_key"),
                "recovery_answer": row_map.get("recovery_answer"),
                "tin": row_map.get("tin"),
                "subscription_expiry": row_map.get("subscription_expiry"),
                "status": row_map.get("status") or "Active",
                "deployment_status": row_map.get("deployment_status") or "Pending",
                "plan_type": row_map.get("plan_type") or "Basic",
                "contact_email": row_map.get("contact_email"),
                "phone_number": row_map.get("phone_number"),
                "physical_address": row_map.get("physical_address"),
                "industry": row_map.get("industry"),
                "currency": row_map.get("currency") or "GHS",
                "logo_url": row_map.get("logo_url"),
                "created_at": row_map.get("created_at"),
                "updated_at": row_map.get("updated_at"),
            }
        )

    return backup


def main():
    print(f"Opening database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF;")

    try:
        companies_backup = fetch_companies_backup(cursor)
        print(f"Backed up {len(companies_backup)} company rows.")

        if table_exists(cursor, "companies"):
            cursor.execute("DROP TABLE companies")
            print("Dropped old companies table.")

        cursor.execute(
            """
            CREATE TABLE companies (
                key TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                sub_admin_key TEXT,
                staff_key TEXT,
                recovery_answer TEXT,
                tin TEXT,
                subscription_expiry TEXT,
                status TEXT DEFAULT 'Active',
                deployment_status TEXT DEFAULT 'Pending',
                plan_type TEXT DEFAULT 'Basic',
                contact_email TEXT,
                phone_number TEXT,
                physical_address TEXT,
                industry TEXT,
                currency TEXT DEFAULT 'GHS',
                logo_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        print("Recreated companies table.")

        for company in companies_backup:
            if not company["key"] or not company["name"]:
                continue

            cursor.execute(
                """
                INSERT INTO companies (
                    key, name, sub_admin_key, staff_key, recovery_answer, tin,
                    subscription_expiry, status, deployment_status, plan_type,
                    contact_email, phone_number, physical_address, industry,
                    currency, logo_url, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company["key"],
                    company["name"],
                    company["sub_admin_key"],
                    company["staff_key"],
                    company["recovery_answer"],
                    company["tin"],
                    company["subscription_expiry"],
                    company["status"],
                    company["deployment_status"],
                    company["plan_type"],
                    company["contact_email"],
                    company["phone_number"],
                    company["physical_address"],
                    company["industry"],
                    company["currency"],
                    company["logo_url"],
                    company["created_at"],
                    company["updated_at"],
                ),
            )
        print("Restored company data.")

        cursor.execute("DROP TABLE IF EXISTS pending_approvals")
        cursor.execute(
            """
            CREATE TABLE pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT,
                payment_reference TEXT UNIQUE,
                amount REAL,
                payment_method TEXT,
                plan_requested TEXT,
                status TEXT DEFAULT 'Pending',
                admin_notes TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        print("Recreated pending_approvals table.")

        cursor.execute("DROP TABLE IF EXISTS maintenance_settings")
        cursor.execute(
            """
            CREATE TABLE maintenance_settings (
                id INTEGER PRIMARY KEY,
                maintenance_date TEXT,
                start_time TEXT,
                end_time TEXT,
                is_active INTEGER DEFAULT 0,
                message TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO maintenance_settings (
                id, maintenance_date, start_time, end_time, is_active, message
            )
            VALUES (1, '', '', '', 0, 'System operating normally')
            """
        )
        print("Recreated maintenance_settings table.")

        conn.commit()
        print("Nuclear sync complete.")
    except Exception as e:
        conn.rollback()
        print(f"Rebuild failed: {e}")
        raise
    finally:
        cursor.execute("PRAGMA foreign_keys = ON;")
        conn.close()


if __name__ == "__main__":
    main()
