import sqlite3
import os
from pathlib import Path
import logging

# Setup logging to see exactly what happens
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Force the path to be the local directory to avoid Windows Pathing issues
DB_PATH = Path(__file__).resolve().parent / "database.db"

def main():
    print(f"🚀 INITIALIZING DATABASE ARCHITECT...")
    print(f"📍 TARGET PATH: {DB_PATH}")

    # STEP 1: NUCLEAR RESET
    # If the database exists but is "broken" or missing tables, we wipe it for a clean start.
    if DB_PATH.exists():
        try:
            os.remove(DB_PATH)
            print("🗑️  Old database wiped to prevent 'No Such Table' conflicts.")
        except PermissionError:
            print("⚠️  Database is currently locked by another process (Streamlit?).")
            print("⚠️  Please stop your Streamlit app in the terminal (Ctrl+C) and run this again.")
            return

    # STEP 2: ESTABLISH CONNECTION
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Enable Write-Ahead Logging for better performance on Windows
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        # --- COMPANIES TABLE ---
        print("🔨 Building [companies]...")
        cursor.execute("""
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
        """)

        # --- INVENTORY TABLE ---
        print("🔨 Building [inventory]...")
        cursor.execute("""
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
        """)

        # --- VOUCHERS TABLE ---
        print("🔨 Building [vouchers]...")
        cursor.execute("""
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
        """)

        # --- PAYROLL TABLE ---
        print("🔨 Building [payroll]...")
        cursor.execute("""
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
        """)

        # --- FIXED ASSETS TABLE ---
        print("🔨 Building [fixed_assets]...")
        cursor.execute("""
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
        """)

        # --- AUDIT LOGS ---
        print("🔨 Building [audit_logs]...")
        cursor.execute("""
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
        """)

        # --- MAINTENANCE SETTINGS ---
        print("🔨 Building [maintenance_settings]...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_settings (
                id INTEGER PRIMARY KEY,
                maintenance_date TEXT,
                start_time TEXT,
                end_time TEXT,
                is_active INTEGER DEFAULT 0,
                message TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Ensure the default ID 1 exists for the app to read
        cursor.execute("""
            INSERT OR IGNORE INTO maintenance_settings (id, maintenance_date, start_time, end_time, is_active, message)
            VALUES (1, '', '', '', 0, 'System operating normally')
        """)

        # --- PENDING APPROVALS ---
        print("🔨 Building [pending_approvals]...")
        cursor.execute("""
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
        """)

        # Commit and Finalize
        conn.commit()
        print("✅ FULL DATABASE ARCHITECTURE BUILT SUCCESSFULLY")
        print(f"👉 Now you can run: streamlit run app.py")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()