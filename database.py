import streamlit as st
import sqlite3
import os
from datetime import datetime
import logging
from sqlalchemy import text

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
        conn.execute(text("""INSERT INTO audit_logs (company_key, user_role, action, module_name) 
                     VALUES (?,?,?,?)"""), (company_key, user_role, action, module_name))
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
                      email TEXT,
                      phone TEXT,
                      address TEXT,
                      subscription_expiry DATE,
                      maintenance_mode BOOLEAN DEFAULT 0,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        
        # 2. System Fees & Gatekeeper Settings
        c.execute('''CREATE TABLE IF NOT EXISTS system_settings 
                     (id INTEGER PRIMARY KEY, 
                      company_key TEXT,
                      software_fee REAL DEFAULT 0.0, 
                      maintenance_fee REAL DEFAULT 0.0, 
                      subscription_months INTEGER DEFAULT 12,
                      currency TEXT DEFAULT 'GHS',
                      vat_rate REAL DEFAULT 12.5,
                      nhil_rate REAL DEFAULT 2.5,
                      getfund_rate REAL DEFAULT 2.5,
                      covid_rate REAL DEFAULT 1.0,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

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
                      min_stock_level REAL DEFAULT 0.0,
                      supplier_name TEXT,
                      category TEXT,
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
                      emp_id TEXT,
                      emp_department TEXT,
                      basic_salary REAL, 
                      ssnit_t1 REAL, 
                      ssnit_t2 REAL, 
                      ssnit_t3 REAL DEFAULT 0.0,
                      taxable_income REAL, 
                      paye REAL, 
                      net_salary REAL, 
                      month TEXT, 
                      year TEXT,
                      bank_account TEXT,
                      payment_method TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 6. Fixed Asset Register
        c.execute('''CREATE TABLE IF NOT EXISTS fixed_assets 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      company_key TEXT, 
                      asset_name TEXT, 
                      asset_category TEXT,
                      purchase_cost REAL, 
                      dep_rate REAL, 
                      accum_dep REAL DEFAULT 0.0, 
                      book_value REAL, 
                      purchase_date TEXT,
                      disposal_date TEXT,
                      location TEXT,
                      responsible_person TEXT,
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
                      ip_address TEXT,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 8. Chart of Accounts (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS chart_of_accounts 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      account_code TEXT,
                      account_name TEXT,
                      account_type TEXT,
                      balance REAL DEFAULT 0.0,
                      parent_account TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 9. Sales Invoices (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS sales_invoices 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      invoice_no TEXT,
                      customer_name TEXT,
                      customer_email TEXT,
                      customer_phone TEXT,
                      invoice_date TEXT,
                      due_date TEXT,
                      total_amount REAL,
                      vat_amount REAL,
                      status TEXT DEFAULT 'Pending',
                      payment_status TEXT DEFAULT 'Unpaid',
                      sales_person TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 10. Purchase Orders (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS purchase_orders 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      po_no TEXT,
                      supplier_name TEXT,
                      supplier_email TEXT,
                      order_date TEXT,
                      delivery_date TEXT,
                      total_amount REAL,
                      status TEXT DEFAULT 'Pending',
                      approved_by TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 11. Customer Management (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS customers 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      customer_code TEXT,
                      customer_name TEXT,
                      email TEXT,
                      phone TEXT,
                      address TEXT,
                      credit_limit REAL DEFAULT 0.0,
                      balance REAL DEFAULT 0.0,
                      customer_type TEXT DEFAULT 'Regular',
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 12. Supplier Management (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS suppliers 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      supplier_code TEXT,
                      supplier_name TEXT,
                      email TEXT,
                      phone TEXT,
                      address TEXT,
                      payment_terms TEXT DEFAULT '30 Days',
                      vat_number TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 13. Maintenance Notices (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS maintenance_notices 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      notice_type TEXT,
                      title TEXT,
                      message TEXT,
                      start_date TEXT,
                      end_date TEXT,
                      status TEXT DEFAULT 'Scheduled',
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 14. System Notifications (NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS notifications 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      notification_type TEXT,
                      title TEXT,
                      message TEXT,
                      priority TEXT DEFAULT 'Medium',
                      is_read BOOLEAN DEFAULT 0,
                      expiry_date TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))''')

        # 15. Maintenance Settings (NEW for Gatekeeper)
        c.execute('''CREATE TABLE IF NOT EXISTS maintenance_settings 
                     (id INTEGER PRIMARY KEY,
                      maintenance_date TEXT,
                      is_active BOOLEAN DEFAULT 0,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # 16. Pending Approvals (NEW for Payment References)
        c.execute('''CREATE TABLE IF NOT EXISTS pending_approvals 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      payment_reference TEXT,
                      amount REAL,
                      payment_method TEXT,
                      submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      status TEXT DEFAULT 'Pending',
                      approved_at DATETIME,
                      approved_by TEXT,
                      notes TEXT,
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
