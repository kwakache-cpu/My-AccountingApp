import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

# --- 1. DATABASE SETUP (PERMANENT STORAGE) ---
def init_db():
    conn = sqlite3.connect('eka_accounting.db')
    c = conn.cursor()
    # Table for Company Access & Subscription
    c.execute('''CREATE TABLE IF NOT EXISTS registry 
                 (key TEXT PRIMARY KEY, name TEXT, plan TEXT, 
                  expiry_date DATE, role TEXT)''')
    # Table for Company Ledgers (Example of data saving)
    c.execute('''CREATE TABLE IF NOT EXISTS ledgers 
                 (company_key TEXT, category TEXT, ledger_name TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. AUTHENTICATION LOGIC ---
if 'authorized' not in st.session_state:
    st.session_state['authorized'] = False
    st.session_state['user_data'] = None

def login_screen():
    st.title("🛡️ E.K.A Cloud Accounting - Portal")
    key = st.text_input("Enter License Key", type="password")
    if st.button("Unlock System"):
        conn = sqlite3.connect('eka_accounting.db')
        df = pd.read_sql(f"SELECT * FROM registry WHERE key='{key}'", conn)
        conn.close()
        
        if not df.empty:
            st.session_state['authorized'] = True
            st.session_state['user_data'] = df.iloc[0].to_dict()
            st.rerun()
        elif key == "KAY-ADMIN-MASTER": # Hardcoded emergency admin key
            st.session_state['authorized'] = True
            st.session_state['user_data'] = {"key": "ADMIN", "name": "E.K.A Admin", "role": "Owner", "expiry_date": "2099-12-31"}
            st.rerun()
        else:
            st.error("Invalid Key. Contact Support: +233546044673")

# --- 3. MASTER ADMIN DASHBOARD (FOR YOU) ---
def admin_dashboard():
    st.title("👑 Owner's Registration Center")
    with st.form("reg_form"):
        c_name = st.text_input("New Company Name")
        c_key = st.text_input("Assign Unique Key")
        days = st.number_input("Subscription Days", value=30)
        submit = st.form_submit_button("Register & Save Data")
        
        if submit:
            expiry = datetime.now().date() + timedelta(days=days)
            conn = sqlite3.connect('eka_accounting.db')
            try:
                conn.execute("INSERT INTO registry VALUES (?, ?, ?, ?, ?)", 
                             (c_key, c_name, "Pro", expiry, "Client"))
                conn.commit()
                st.success(f"Company {c_name} saved permanently! Key: {c_key}")
            except:
                st.error("Key already exists!")
            conn.close()

    st.subheader("Managed Companies")
    conn = sqlite3.connect('eka_accounting.db')
    st.write(pd.read_sql("SELECT name, expiry_date FROM registry", conn))
    conn.close()

# --- 4. CLIENT ERP (WITH EXPIRY REMINDERS) ---
def erp_dashboard():
    user = st.session_state['user_data']
    expiry_date = datetime.strptime(user['expiry_date'], '%Y-%m-%d').date()
    today = datetime.now().date()
    days_left = (expiry_date - today).days

    # SIDEBAR MODULES
    st.sidebar.title(f"🏢 {user['name']}")
    menu = st.sidebar.selectbox("Modules", ["1. Company Setup", "2. Chart of Accounts", "4. Inventory", "15. Reports"])

    # 7-DAY EXPIRY REMINDER
    if 0 <= days_left <= 7:
        st.warning(f"⚠️ Subscription Reminder: Your access expires in {days_left} days. Please resubscribe to avoid lockout.")
    elif days_left < 0:
        st.error("🚫 Subscription Expired. Please renew to access your data.")
        st.stop()

    if menu == "1. Company Setup":
        st.header("🏗️ Permanent Company Configuration")
        st.info("Your data is securely saved in the E.K.A Cloud Database.")
        # Module logic continues here...

# --- 5. MAIN EXECUTION ---
if not st.session_state['authorized']:
    login_screen()
else:
    if st.session_state['user_data']['role'] == "Owner":
        admin_dashboard()
    else:
        erp_dashboard()

if st.sidebar.button("Log Out"):
    st.session_state['authorized'] = False
    st.rerun()