import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool  # ✅ REQUIRED for Supabase
from datetime import datetime
import logging

# Configure logging to catch cloud connection handshakes
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_engine():
    """Establish a robust SQLAlchemy engine connection to Supabase.

    This explicitly tries the Supavisor pooler (port 6543) first to bypass 
    IPv6 issues on Streamlit Cloud, then falls back to direct Postgres (port 5432).
    """
    # 1. Retrieve the Secret
    db_url = st.secrets.get('DATABASE_URL')  # ✅ FIXED SECRET NAME
    if not db_url:
        logger.error("DATABASE_URL is missing from Streamlit Secrets.")
        raise RuntimeError("DATABASE_URL is not set in Streamlit secrets.")

    # 2. Normalize: strip whitespace and ensure scheme is postgresql
    db_url = db_url.strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    def _normalize(url: str, port: int) -> str:
        """Injects the correct port and forces SSL mode."""
        # Split URL to safely inject port into the host section
        if ":" in url.split("//", 1)[1].split("@")[-1]:
            # Replace existing port (5432 or 6543) with the target port
            url = url.replace(":5432", f":{port}").replace(":6543", f":{port}")
        else:
            # Append port if none present
            if "@" in url:
                parts = url.split("@")
                url = f"{parts[0]}@{parts[1]}:{port}"
            else:
                url = f"{url}:{port}"
        
        # Ensure SSL mode is REQUIRED for Supabase
        if "sslmode=" not in url:
            sep = '&' if '?' in url else '?'
            url = f"{url}{sep}sslmode=require"
        return url

    # Generate both connection paths
    pooler_url = _normalize(db_url, 6543)
    direct_url = _normalize(db_url, 5432)

    # Professional Engine Configuration
    connect_args = {
        "sslmode": "require",
        "connect_timeout": 20
    }
    
    engine_kwargs = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 3600,
        "poolclass": NullPool  # ✅ CRITICAL FIX FOR SUPABASE
    }

    def _create(url: str):
        """Internal helper to attempt a physical connection."""
        engine = create_engine(url, echo=False, **engine_kwargs)
        # Test the connection immediately
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine

    # EXECUTION: Try pooler first (Best for Cloud), then direct fallback
    try:
        logger.info("Attempting connection via Supavisor Pooler (Port 6543)...")
        return _create(pooler_url)
    except Exception as e:
        logger.warning(f"Pooler failed. Attempting Direct Connection (Port 5432): {e}")
        try:
            return _create(direct_url)
        except Exception as e2:
            logger.error(f"All database connection attempts failed: {e2}")
            raise e2

def get_connection():
    """Get a live connection with automatic error logging."""
    try:
        engine = get_engine()
        return engine.connect()
    except Exception as e:
        logger.error(f"Final Connection Error: {e}")
        raise

def log_audit_action(conn, company_key, user_role, action, module_name):
    """Log audit trail entries for security and compliance."""
    try:
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
    """Initialize full schema for Ghana compliance. NO LOGIC REMOVED."""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # 1. Company Identity
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
            
            # 2. System Settings
            conn.execute(text('''CREATE TABLE IF NOT EXISTS system_settings 
                         (id SERIAL PRIMARY KEY, 
                          company_key TEXT UNIQUE, 
                          software_fee REAL DEFAULT 0.0, 
                          subscription_months INTEGER DEFAULT 12,
                          setup_fee_paid REAL DEFAULT 0.0,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))
            
            # 3. Maintenance
            conn.execute(text('''CREATE TABLE IF NOT EXISTS maintenance_settings 
                         (id SERIAL PRIMARY KEY, 
                          maintenance_date TEXT,
                          is_active BOOLEAN DEFAULT TRUE)'''))

            conn.execute(text("""INSERT INTO maintenance_settings (id, maintenance_date) 
                         VALUES (1, 'None') ON CONFLICT DO NOTHING"""))

            # 4. Inventory
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

            # 5. Vouchers
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

            # 6. Ghana Payroll
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

            # 7. Fixed Assets
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

            # 8. Audit logs
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
            logger.info("Database structure verified and initialized via SQLAlchemy.")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

if __name__ == "__main__":
    init_db()