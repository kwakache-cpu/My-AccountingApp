import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "database.db"


def ensure_company_columns(cursor):
    existing_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(companies)").fetchall()
    }

    columns_to_add = [
        ("subscription_expiry", "ALTER TABLE companies ADD COLUMN subscription_expiry TEXT"),
        (
            "deployment_status",
            "ALTER TABLE companies ADD COLUMN deployment_status TEXT DEFAULT 'Pending'",
        ),
        ("key", "ALTER TABLE companies ADD COLUMN key TEXT"),
    ]

    for column_name, sql in columns_to_add:
        if column_name not in existing_columns:
            cursor.execute(sql)
            print(f"Added missing column: {column_name}")


def main():
    print(f"Opening database at: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS companies (
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

    ensure_company_columns(cursor)

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            item_name TEXT NOT NULL,
            item_code TEXT,
            category TEXT,
            description TEXT,
            qty REAL DEFAULT 0,
            min_stock_level REAL DEFAULT 10,
            unit TEXT DEFAULT 'pcs',
            cost_price REAL DEFAULT 0,
            price REAL DEFAULT 0,
            tax_rate REAL DEFAULT 0,
            warehouse_location TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_comp ON inventory(company_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_name ON inventory(item_name)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            date TEXT NOT NULL,
            v_type TEXT NOT NULL,
            ledger TEXT NOT NULL,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            balance_after REAL DEFAULT 0,
            payment_method TEXT,
            reference_no TEXT,
            narration TEXT,
            is_cleared INTEGER DEFAULT 1,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vouch_date ON vouchers(date)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            emp_name TEXT NOT NULL,
            emp_id TEXT,
            bank_name TEXT,
            account_number TEXT,
            basic_salary REAL NOT NULL,
            allowances REAL DEFAULT 0,
            ssnit_t1 REAL DEFAULT 0,
            ssnit_t2 REAL DEFAULT 0,
            taxable_income REAL DEFAULT 0,
            paye REAL DEFAULT 0,
            net_salary REAL DEFAULT 0,
            month TEXT NOT NULL,
            year TEXT NOT NULL,
            payment_status TEXT DEFAULT 'Unpaid',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fixed_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            asset_name TEXT NOT NULL,
            asset_category TEXT,
            purchase_date TEXT,
            cost REAL NOT NULL,
            depreciation_rate REAL DEFAULT 0,
            accumulated_depreciation REAL DEFAULT 0,
            book_value REAL NOT NULL,
            location TEXT,
            status TEXT DEFAULT 'Active',
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            company_key TEXT,
            user_role TEXT,
            action TEXT NOT NULL,
            module_name TEXT,
            details TEXT,
            ip_address TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS maintenance_settings (
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
        CREATE TABLE IF NOT EXISTS pending_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT,
            payment_reference TEXT UNIQUE,
            amount REAL,
            payment_method TEXT,
            plan_requested TEXT,
            status TEXT DEFAULT 'Pending',
            admin_notes TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key)
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

    conn.commit()
    conn.close()
    print("FULL DATABASE ARCHITECTURE BUILT SUCCESSFULLY")


if __name__ == "__main__":
    main()
