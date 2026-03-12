import sqlite3
import streamlit as st

def get_connection():
    db_name = st.secrets.get("DB_NAME", "eka_vault.db")
    return sqlite3.connect(db_name, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # 1. Company Registry
    c.execute('''CREATE TABLE IF NOT EXISTS companies 
                 (key TEXT PRIMARY KEY, name TEXT, tin TEXT, expiry DATE)''')
    # 2. Universal Voucher Table
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  date TEXT, v_type TEXT, ledger TEXT, amount REAL, narration TEXT)''')
    # 3. Chart of Accounts
    c.execute('''CREATE TABLE IF NOT EXISTS ledgers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  name TEXT, category TEXT)''')
    # 4. Payroll Records
    c.execute('''CREATE TABLE IF NOT EXISTS payroll 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  emp_name TEXT, basic_salary REAL, ssnit_tier1 REAL, paye REAL, net_salary REAL)''')
    # 5. Security Audit Logs
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                  company_key TEXT, action TEXT)''')
    conn.commit()
    conn.close()

init_db()