import os
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "database.db"


def main():
    db_path_str = str(DB_PATH)

    if os.path.exists(db_path_str):
        os.remove(db_path_str)

    conn = sqlite3.connect(db_path_str)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

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
            barcode_input_source TEXT DEFAULT 'Keyboard Entry',
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

    cursor.execute(
        """
        CREATE TABLE inventory (
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE vouchers (
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

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

    conn.commit()
    conn.close()

    print("--- DATABASE DELETED AND REBUILT WITH STATUS COLUMN ---")


if __name__ == "__main__":
    main()
