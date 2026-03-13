import sqlite3

def get_connection():
    # Using a versioned DB name to ensure fresh tables for the new modules
    return sqlite3.connect("eka_enterprise_v3.db", check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Company & Security Table
    c.execute('''CREATE TABLE IF NOT EXISTS companies 
                 (key TEXT PRIMARY KEY, name TEXT, tin TEXT, 
                  sub_admin_key TEXT, recovery_answer TEXT)''')
    
    # 2. Chart of Accounts Table
    c.execute('''CREATE TABLE IF NOT EXISTS accounts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  name TEXT, account_group TEXT, opening_balance REAL DEFAULT 0.0)''')

    # 3. Inventory Table
    c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  item_name TEXT, unit TEXT, qty REAL, expiry TEXT, warehouse TEXT)''')

    # 4. Comprehensive Voucher Table
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  date TEXT, v_type TEXT, ledger TEXT, amount REAL, narration TEXT)''')

    # 5. Payroll Table
    c.execute('''CREATE TABLE IF NOT EXISTS payroll 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, emp_name TEXT, 
                  basic_salary REAL, ssnit_tier1 REAL, paye REAL, net_salary REAL)''')

    # 6. Audit Logs Table
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                  company_key TEXT, action TEXT)''')

    conn.commit()
    conn.close()

init_db()