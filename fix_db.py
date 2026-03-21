import os
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "database.db"


def main():
    db_path_str = str(DB_PATH)
    print(f"Opening database at: {db_path_str}")

    if os.path.exists(db_path_str):
        os.remove(db_path_str)
        print("Existing database deleted.")

    conn = sqlite3.connect(db_path_str)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    print("Checking Table companies...")
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name)")

    print("Checking Table inventory...")
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
            warehouse TEXT,
            warehouse_location TEXT,
            barcode TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_comp ON inventory(company_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_name ON inventory(item_name)")

    print("Checking Table vouchers...")
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
            ref_no TEXT,
            narration TEXT,
            is_cleared INTEGER DEFAULT 1,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vouch_date ON vouchers(date)")

    print("Checking Table payroll...")
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

    print("Checking Table fixed_assets...")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fixed_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            asset_name TEXT NOT NULL,
            asset_category TEXT,
            purchase_date TEXT,
            cost REAL DEFAULT 0,
            purchase_cost REAL DEFAULT 0,
            depreciation_rate REAL DEFAULT 0,
            dep_rate REAL DEFAULT 0,
            accumulated_depreciation REAL DEFAULT 0,
            accum_dep REAL DEFAULT 0,
            book_value REAL NOT NULL DEFAULT 0,
            location TEXT,
            status TEXT DEFAULT 'Active',
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )

    print("Checking Table audit_logs...")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            company_key TEXT,
            user_role TEXT,
            role TEXT,
            action TEXT NOT NULL,
            module_name TEXT,
            details TEXT,
            ip_address TEXT
        )
        """
    )

    print("Checking Table maintenance_settings...")
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

    print("Checking Table pending_approvals...")
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
    print("--- NUCLEAR RESET COMPLETE: NEW DATABASE READY ---")


if __name__ == "__main__":
    main()
