import sqlite3

def get_connection():
    return sqlite3.connect("eka_vault_v2.db", check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Ensure the table exists
    c.execute('''CREATE TABLE IF NOT EXISTS companies 
                 (key TEXT PRIMARY KEY, name TEXT, tin TEXT, 
                  sub_admin_key TEXT, recovery_answer TEXT)''')
    
    # MIGRATION: Add columns if they are missing from an old version
    c.execute("PRAGMA table_info(companies)")
    cols = [column[1] for column in c.fetchall()]
    if "sub_admin_key" not in cols:
        c.execute("ALTER TABLE companies ADD COLUMN sub_admin_key TEXT")
    if "recovery_answer" not in cols:
        c.execute("ALTER TABLE companies ADD COLUMN recovery_answer TEXT")

    c.execute('''CREATE TABLE IF NOT EXISTS vouchers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  date TEXT, v_type TEXT, ledger TEXT, amount REAL, narration TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ledgers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, name TEXT, category TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payroll 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, emp_name TEXT, 
                  basic_salary REAL, ssnit_tier1 REAL, paye REAL, net_salary REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                  company_key TEXT, action TEXT)''')
    conn.commit()
    conn.close()

init_db()