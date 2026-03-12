import sqlite3
import streamlit as st

def get_connection():
    # Moving to v3 to finalize the new security structure
    return sqlite3.connect("eka_vault_v3.db", check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Updated: master structure for all security features
    c.execute('''CREATE TABLE IF NOT EXISTS companies 
                 (key TEXT PRIMARY KEY, name TEXT, tin TEXT, 
                  sub_admin_key TEXT, recovery_answer TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS vouchers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  date TEXT, v_type TEXT, ledger TEXT, amount REAL, narration TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ledgers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  name TEXT, category TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS payroll 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT, 
                  emp_name TEXT, basic_salary REAL, ssnit_tier1 REAL, 
                  paye REAL, net_salary REAL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                  company_key TEXT, action TEXT)''')
    conn.commit()
    conn.close()

init_db()