import sqlite3
import os
from datetime import datetime

def get_connection():
    """Establish a professional connection to the E.K.A Enterprise Database."""
    return sqlite3.connect("eka_enterprise_v3.db", check_same_thread=False)

def init_db():
    """Initialize the full multi-module schema for Ghana compliance."""
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Company Identity & Security Keys
    c.execute('''CREATE TABLE IF NOT EXISTS companies 
                 (key TEXT PRIMARY KEY, 
                  name TEXT, 
                  tin TEXT, 
                  sub_admin_key TEXT, 
                  staff_key TEXT, 
                  recovery_answer TEXT,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # 2. System Fees & Gatekeeper Settings
    c.execute('''CREATE TABLE IF NOT EXISTS system_settings 
                 (id INTEGER PRIMARY KEY, 
                  software_fee REAL DEFAULT 0.0, 
                  maintenance_fee REAL DEFAULT 0.0, 
                  subscription_months INTEGER DEFAULT 12,
                  currency TEXT DEFAULT 'GHS')''')

    # 3. Inventory & Warehouse Management
    c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  company_key TEXT, 
                  item_name TEXT, 
                  unit TEXT, 
                  qty REAL DEFAULT 0.0, 
                  price REAL DEFAULT 0.0, 
                  cost_price REAL DEFAULT 0.0, 
                  warehouse TEXT, 
                  barcode TEXT)''')

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
                  ref_no TEXT)''')

    # 5. Ghana Payroll Tiers (SSNIT & PAYE)
    c.execute('''CREATE TABLE IF NOT EXISTS payroll 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  company_key TEXT, 
                  emp_name TEXT, 
                  basic_salary REAL, 
                  ssnit_t1 REAL, 
                  ssnit_t2 REAL, 
                  ssnit_t3 REAL, 
                  taxable_income REAL, 
                  paye REAL, 
                  net_salary REAL, 
                  month TEXT, 
                  year TEXT)''')

    # 6. Fixed Asset Register
    c.execute('''CREATE TABLE IF NOT EXISTS fixed_assets 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  company_key TEXT, 
                  asset_name TEXT, 
                  purchase_cost REAL, 
                  dep_rate REAL, 
                  accum_dep REAL, 
                  book_value REAL, 
                  purchase_date TEXT)''')

    # 7. Security Audit Trail
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                  company_key TEXT, 
                  user_role TEXT, 
                  action TEXT, 
                  module_name TEXT)''')

    conn.commit()
    conn.close()
    print("Database structure verified and initialized.")

if __name__ == "__main__":
    init_db()