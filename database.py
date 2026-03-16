import sqlite3
import os
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_connection():
    """Establish a professional connection to the E.K.A Enterprise Database."""
    try:
        conn = sqlite3.connect("eka_enterprise_v3.db", check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

def log_audit_action(conn, company_key, user_role, action, module_name):
    """Log audit trail entries for security and compliance."""
    try:
        conn.execute("""INSERT INTO audit_logs (company_key, user_role, action, module_name) 
                     VALUES (?,?,?,?)""", (company_key, user_role, action, module_name))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Audit logging error: {e}")

def init_db():
    """Initialize the full multi-module schema for Ghana compliance."""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # 1. Company Identity & Security Keys
        c.execute('''CREATE TABLE IF NOT EXISTS companies 
                     (key TEXT PRIMARY KEY, 
                      name TEXT, 
                      tin TEXT, 
                      sub_admin_key TEXT, 
                      staff_key TEXT, 
                      recovery_answer TEXT,
                      admin_email TEXT,
                      status TEXT DEFAULT 'Active',
                      subscription_end_date DATETIME,
                      deployment_status TEXT DEFAULT 'Live',
                      expiry_date DATETIME,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        
        # Ensure schema is up to date for existing databases
        try:
            c.execute("ALTER TABLE companies ADD COLUMN admin_email TEXT")
        except sqlite3.OperationalError:
            # Column already exists
            pass
        try:
            c.execute("ALTER TABLE companies ADD COLUMN status TEXT DEFAULT 'Active'")
        except sqlite3.OperationalError:
            # Column already exists
            pass
        try:
            c.execute("ALTER TABLE companies ADD COLUMN subscription_end_date DATETIME")
        except sqlite3.OperationalError:
            # Column already exists
            pass
        try:
            c.execute("ALTER TABLE companies ADD COLUMN deployment_status TEXT DEFAULT 'Live'")
        except sqlite3.OperationalError:
            # Column already exists
            pass
        try:
            c.execute("ALTER TABLE companies ADD COLUMN expiry_date DATETIME")
        except sqlite3.OperationalError:
            # Column already exists
            pass
        
        # 3. Global Maintenance Settings
        c.execute('''CREATE TABLE IF NOT EXISTS maintenance_settings 
                     (id INTEGER PRIMARY KEY, 
                      maintenance_date TEXT,
                      is_active BOOLEAN DEFAULT 1)''')

        # Insert default if not exists
        c.execute("INSERT OR IGNORE INTO maintenance_settings (id, maintenance_date) VALUES (1, 'None')")

        # 2. System Settings (Licensing & Payments)
        c.execute('''CREATE TABLE IF NOT EXISTS system_settings 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT UNIQUE,
                      software_fee REAL DEFAULT 0.0,
                      setup_fee_paid REAL DEFAULT 0.0,
                      subscription_months INTEGER DEFAULT 0,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # Ensure schema is up to date for existing databases
        try:
            c.execute("ALTER TABLE system_settings ADD COLUMN setup_fee_paid REAL DEFAULT 0.0")
        except sqlite3.OperationalError:
            # Column already exists
            pass

        # 3. Inventory & Warehouse Management
        c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      company_key TEXT, 
                      item_name TEXT, 
                      unit TEXT, 
                      qty REAL DEFAULT 0.0, 
                      price REAL DEFAULT 0.0, 
                      cost_price REAL DEFAULT 0.0, 
                      warehouse TEXT DEFAULT 'Main',
                      barcode TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 4. Universal Voucher Journal (With Payment Methods)
        c.execute('''CREATE TABLE IF NOT EXISTS vouchers 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      company_key TEXT, 
                      date TEXT, 
                      v_type TEXT, 
                      ledger TEXT, 
                      debit REAL DEFAULT 0.0, 
                      credit REAL DEFAULT 0.0, 
                      payment_method TEXT, 
                      narration TEXT, 
                      ref_no TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 5. Ghana Payroll Tiers (SSNIT & PAYE)
        c.execute('''CREATE TABLE IF NOT EXISTS payroll 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      company_key TEXT, 
                      emp_name TEXT, 
                      basic_salary REAL, 
                      ssnit_t1 REAL, 
                      ssnit_t2 REAL, 
                      ssnit_t3 REAL DEFAULT 0.0,
                      taxable_income REAL, 
                      paye REAL, 
                      net_salary REAL, 
                      month TEXT, 
                      year TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 6. Fixed Asset Register
        c.execute('''CREATE TABLE IF NOT EXISTS fixed_assets 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      company_key TEXT, 
                      asset_name TEXT, 
                      purchase_cost REAL, 
                      dep_rate REAL, 
                      accum_dep REAL DEFAULT 0.0, 
                      book_value REAL, 
                      purchase_date TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 7. Security Audit Trail
        c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                      company_key TEXT, 
                      user_role TEXT, 
                      action TEXT, 
                      module_name TEXT,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 8. Chart of Accounts (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS chart_of_accounts 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      account_code TEXT,
                      account_name TEXT,
                      account_type TEXT,
                      balance REAL DEFAULT 0.0,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 9. Sales Invoices (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS sales_invoices 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      invoice_no TEXT,
                      customer_name TEXT,
                      customer_email TEXT,
                      invoice_date TEXT,
                      due_date TEXT,
                      total_amount REAL,
                      status TEXT DEFAULT 'Pending',
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # Ensure schema is up to date for existing databases
        try:
            c.execute("ALTER TABLE sales_invoices ADD COLUMN customer_email TEXT")
        except sqlite3.OperationalError:
            # Column already exists
            pass

        # 10. Purchase Orders (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS purchase_orders 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      po_no TEXT,
                      supplier_name TEXT,
                      order_date TEXT,
                      total_amount REAL,
                      status TEXT DEFAULT 'Pending',
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        conn.commit()
        logger.info("Database structure verified and initialized.")
        
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()