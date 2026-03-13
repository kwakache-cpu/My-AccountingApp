import sqlite3

def get_connection():
    # Using v3 to ensure all new columns (Price, Cost, Tiers) are active
    return sqlite3.connect("eka_enterprise_v3.db", check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Company Security & Licensing
    c.execute('''CREATE TABLE IF NOT EXISTS companies 
                 (key TEXT PRIMARY KEY, name TEXT, tin TEXT, 
                  sub_admin_key TEXT, staff_key TEXT, recovery_answer TEXT)''')
    
    # 2. Chart of Accounts (Expanded for balances)
    c.execute('''CREATE TABLE IF NOT EXISTS accounts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  name TEXT, account_group TEXT, opening_balance REAL DEFAULT 0.0,
                  current_balance REAL DEFAULT 0.0)''')

    # 3. Inventory (Expanded for Cost vs Price)
    c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  item_name TEXT, unit TEXT, qty REAL, price REAL, 
                  cost_price REAL, expiry TEXT, warehouse TEXT, barcode TEXT)''')

    # 4. Global Voucher Journal (Debit/Credit logic)
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  date TEXT, v_type TEXT, ledger TEXT, debit REAL DEFAULT 0.0, 
                  credit REAL DEFAULT 0.0, narration TEXT, ref_no TEXT)''')

    # 5. Ghana Payroll (Tiers 1, 2, 3 + PAYE)
    c.execute('''CREATE TABLE IF NOT EXISTS payroll 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, emp_name TEXT, 
                  basic_salary REAL, ssnit_t1 REAL, ssnit_t2 REAL, ssnit_t3 REAL, 
                  taxable_income REAL, paye REAL, net_salary REAL, month TEXT, year TEXT)''')

    # 6. Fixed Assets (Depreciation Engine)
    c.execute('''CREATE TABLE IF NOT EXISTS fixed_assets 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, asset_name TEXT, 
                  purchase_cost REAL, dep_rate REAL, accum_dep REAL, book_value REAL, purchase_date TEXT)''')

    # 7. Audit Trail (Security Log)
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                  company_key TEXT, user_role TEXT, action TEXT, module TEXT)''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()