import streamlit as st
from sqlalchemy import create_engine, text
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_engine():
    """Establish a SQLAlchemy engine connection to Supabase.

    If connecting via the default Postgres port (5432) fails, automatically retry using
    the Supavisor pooler port (6543) for improved compatibility on Streamlit Cloud.
    """
    db_url = st.secrets.get('DB_URL')
    if not db_url:
        raise RuntimeError("DB_URL is not set in Streamlit secrets.")

    def _create(url):
        engine = create_engine(url, echo=False)
        # Verify we can connect immediately (raises on failure)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine

    try:
        return _create(db_url)
    except Exception as e:
        logger.warning(f"Primary DB connection failed, retrying using Supavisor pooler (6543): {e}")
        # Attempt to replace :5432 with :6543 in the URL (common Supabase pooler port)
        if ":5432" in db_url:
            alt_url = db_url.replace(":5432", ":6543")
        else:
            alt_url = db_url
        try:
            return _create(alt_url)
        except Exception as e2:
            logger.error(f"Supabase connection failed (both direct and pooler): {e2}")
            raise

def get_connection():
    """Get a connection from the SQLAlchemy engine for backward compatibility."""
    try:
        engine = get_engine()
        return engine.connect()
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def log_audit_action(conn, company_key, user_role, action, module_name):
    """Log audit trail entries for security and compliance."""
    try:
        # Store legacy columns as well as the new structured fields for audit analysis
        conn.execute(
            text(
                """INSERT INTO audit_logs (company_key, user_role, "user", action, details, module_name) 
                     VALUES (:company_key, :user_role, :user, :action, :details, :module_name)"""
            ),
            {
                "company_key": company_key,
                "user_role": user_role,
                "user": user_role,
                "action": action,
                "details": module_name,
                "module_name": module_name,
            },
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Audit logging error: {e}")

def init_db():
    """Initialize the full multi-module schema for Ghana compliance (PostgreSQL syntax)."""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # 1. Company Identity & Security Keys
            conn.execute(text('''CREATE TABLE IF NOT EXISTS companies 
                         (key TEXT PRIMARY KEY, 
                          name TEXT, 
                          tin TEXT, 
                          sub_admin_key TEXT, 
                          staff_key TEXT, 
                          recovery_answer TEXT,
                          admin_email TEXT,
                          status TEXT DEFAULT 'Active',
                          subscription_end_date TIMESTAMP,
                          deployment_status TEXT DEFAULT 'Live',
                          expiry_date TIMESTAMP,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''))
            
            # 2. System Settings (Software Fee Management)
            conn.execute(text('''CREATE TABLE IF NOT EXISTS system_settings 
                         (id SERIAL PRIMARY KEY, 
                          company_key TEXT UNIQUE, 
                          software_fee REAL DEFAULT 0.0, 
                          subscription_months INTEGER DEFAULT 12,
                          setup_fee_paid REAL DEFAULT 0.0,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))
            
            # 3. Global Maintenance Settings
            conn.execute(text('''CREATE TABLE IF NOT EXISTS maintenance_settings 
                         (id SERIAL PRIMARY KEY, 
                          maintenance_date TEXT,
                          is_active BOOLEAN DEFAULT TRUE)'''))

            # Insert default if not exists
            conn.execute(text("""INSERT INTO maintenance_settings (id, maintenance_date) 
                         VALUES (1, 'None') ON CONFLICT DO NOTHING"""))

            # 4. Inventory & Warehouse Management
            conn.execute(text('''CREATE TABLE IF NOT EXISTS inventory 
                         (id SERIAL PRIMARY KEY, 
                          company_key TEXT, 
                          item_name TEXT, 
                          unit TEXT, 
                          qty REAL DEFAULT 0.0, 
                          price REAL DEFAULT 0.0, 
                          cost_price REAL DEFAULT 0.0, 
                          warehouse TEXT DEFAULT 'Main',
                          barcode TEXT,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))

            # 5. Universal Voucher Journal (With Payment Methods)
            conn.execute(text('''CREATE TABLE IF NOT EXISTS vouchers 
                         (id SERIAL PRIMARY KEY, 
                          company_key TEXT, 
                          date TEXT, 
                          v_type TEXT, 
                          ledger TEXT, 
                          debit REAL DEFAULT 0.0, 
                          credit REAL DEFAULT 0.0, 
                          payment_method TEXT, 
                          narration TEXT, 
                          ref_no TEXT,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))

            # 6. Ghana Payroll Tiers (SSNIT & PAYE)
            conn.execute(text('''CREATE TABLE IF NOT EXISTS payroll 
                         (id SERIAL PRIMARY KEY, 
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
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))

            # 7. Fixed Asset Register
            conn.execute(text('''CREATE TABLE IF NOT EXISTS fixed_assets 
                         (id SERIAL PRIMARY KEY, 
                          company_key TEXT, 
                          asset_name TEXT, 
                          purchase_cost REAL, 
                          dep_rate REAL, 
                          accum_dep REAL DEFAULT 0.0, 
                          book_value REAL, 
                          purchase_date TEXT,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))

            # 8. Security Audit Trail
            conn.execute(text('''CREATE TABLE IF NOT EXISTS audit_logs 
                         (id SERIAL PRIMARY KEY, 
                          timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                          company_key TEXT, 
                          user_role TEXT, 
                          "user" TEXT, 
                          action TEXT, 
                          details TEXT, 
                          module_name TEXT,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))

            # 9. Chart of Accounts
            conn.execute(text('''CREATE TABLE IF NOT EXISTS chart_of_accounts 
                         (id SERIAL PRIMARY KEY,
                          company_key TEXT,
                          account_code TEXT,
                          account_name TEXT,
                          account_type TEXT,
                          balance REAL DEFAULT 0.0,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))

            # 10. Sales Invoices
            conn.execute(text('''CREATE TABLE IF NOT EXISTS sales_invoices 
                         (id SERIAL PRIMARY KEY,
                          company_key TEXT,
                          invoice_no TEXT,
                          customer_name TEXT,
                          customer_email TEXT,
                          invoice_date TEXT,
                          due_date TEXT,
                          total_amount REAL,
                          status TEXT DEFAULT 'Pending',
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))

            # 11. Purchase Orders
            conn.execute(text('''CREATE TABLE IF NOT EXISTS purchase_orders 
                         (id SERIAL PRIMARY KEY,
                          company_key TEXT,
                          po_no TEXT,
                          supplier_name TEXT,
                          order_date TEXT,
                          total_amount REAL,
                          status TEXT DEFAULT 'Pending',
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))

            conn.commit()
            logger.info("Database structure verified and initialized (PostgreSQL).")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

if __name__ == "__main__":
    init_db()