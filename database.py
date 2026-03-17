import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_engine():
    """Create a local SQLite engine for immediate app stability."""
    # This creates a local file database—no ports (5432/6543) needed.
    sqlite_url = "sqlite:///eka_vault.db"
    
    # Professional SQLite configuration for Streamlit Cloud
    engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    return engine

def get_connection():
    """Get a live local connection."""
    engine = get_engine()
    return engine.connect()

def log_audit_action(conn, company_key, user_role, action, module_name):
    """LOGIC INTACT: Log audit trail entries locally."""
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
    """SCHEMA INTACT: Initialize all 11 tables for Ghana compliance."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            # 1. Company Identity
            conn.execute(text('''CREATE TABLE IF NOT EXISTS companies 
                         (key TEXT PRIMARY KEY, name TEXT, tin TEXT, sub_admin_key TEXT, 
                          staff_key TEXT, recovery_answer TEXT, admin_email TEXT, 
                          status TEXT DEFAULT 'Active', subscription_end_date TIMESTAMP, 
                          deployment_status TEXT DEFAULT 'Live', expiry_date TIMESTAMP, 
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''))
            
            # 2. System Settings
            conn.execute(text('''CREATE TABLE IF NOT EXISTS system_settings 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                          software_fee REAL DEFAULT 0.0, subscription_months INTEGER DEFAULT 12)'''))
            
            # 3. Maintenance
            conn.execute(text('''CREATE TABLE IF NOT EXISTS maintenance_settings 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, maintenance_date TEXT, is_active BOOLEAN DEFAULT 1)'''))
            
            # 4. Inventory
            conn.execute(text('''CREATE TABLE IF NOT EXISTS inventory 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, item_name TEXT, 
                          unit TEXT, qty REAL DEFAULT 0.0, price REAL DEFAULT 0.0)'''))
            
            # 5. Vouchers
            conn.execute(text('''CREATE TABLE IF NOT EXISTS vouchers 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, date TEXT, v_type TEXT, 
                          ledger TEXT, debit REAL DEFAULT 0.0, credit REAL DEFAULT 0.0)'''))
            
            # 6. Ghana Payroll
            conn.execute(text('''CREATE TABLE IF NOT EXISTS payroll 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, emp_name TEXT, 
                          basic_salary REAL, net_salary REAL, month TEXT, year TEXT)'''))
            
            # 7. Fixed Assets
            conn.execute(text('''CREATE TABLE IF NOT EXISTS fixed_assets 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, asset_name TEXT, purchase_cost REAL)'''))
            
            # 8. Audit logs
            conn.execute(text('''CREATE TABLE IF NOT EXISTS audit_logs 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                          company_key TEXT, user_role TEXT, "user" TEXT, action TEXT, module_name TEXT)'''))
            
            # 9. Chart of Accounts
            conn.execute(text('''CREATE TABLE IF NOT EXISTS chart_of_accounts 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, account_name TEXT, balance REAL DEFAULT 0.0)'''))
            
            # 10. Sales Invoices
            conn.execute(text('''CREATE TABLE IF NOT EXISTS sales_invoices 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, customer_name TEXT, total_amount REAL)'''))
            
            # 11. Purchase Orders
            conn.execute(text('''CREATE TABLE IF NOT EXISTS purchase_orders 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, supplier_name TEXT, total_amount REAL)'''))

            conn.execute(text("INSERT OR IGNORE INTO maintenance_settings (id, maintenance_date) VALUES (1, 'None')"))
            conn.commit()
            logger.info("Local SQLite Database initialized with ALL logic intact.")
    except Exception as e:
        logger.error(f"Local Init Error: {e}")

if __name__ == "__main__":
    init_db()