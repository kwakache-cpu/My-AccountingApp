import sqlite3
from datetime import datetime

def get_connection():
    return sqlite3.connect('eka_vault.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Company Registry (Tenants)
    c.execute('''CREATE TABLE IF NOT EXISTS companies 
                 (key TEXT PRIMARY KEY, name TEXT, tin TEXT, expiry DATE)''')
    # Transactions (Vouchers)
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  date TEXT, v_type TEXT, ledger TEXT, amount REAL, narration TEXT)''')
    conn.commit()
    conn.close()

init_db()