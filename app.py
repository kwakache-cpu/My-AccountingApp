import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

# --- 1. DATABASE ENGINE (PERMANENT STORAGE) ---
def init_db():
    conn = sqlite3.connect('eka_accounting.db')
    c = conn.cursor()
    # Registry for companies and their unique codes/roles
    c.execute('''CREATE TABLE IF NOT EXISTS registry 
                 (key TEXT PRIMARY KEY, name TEXT, plan TEXT, expiry_date DATE, role TEXT)''')
    # Table for user roles (Admin vs Staff)
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT, password TEXT, company_key TEXT, role TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. SECURITY & LOGIN ---
if 'authorized' not in st.session_state:
    st.session_state['authorized'] = False
    st.session_state['user_data'] = None

def login_screen():
    st.title("🛡️ E.K.A Cloud Accounting - Portal")
    
    tab1, tab2 = st.tabs(["🔑 Company Login", "👤 Staff Login"])
    
    with tab1:
        key = st.text_input("Enter License Key", type="password", key="comp_key")
        if st.button("Unlock System", key="btn_unlock"):
            conn = sqlite3.connect('eka_accounting.db')
            df = pd.read_sql(f"SELECT * FROM registry WHERE key='{key}'", conn)
            conn.close()
            
            if not df.empty:
                st.session_state['authorized'] = True
                st.session_state['user_data'] = df.iloc[0].to_dict()
                st.session_state['user_role'] = "Administrator" # Key access is always Admin
                st.rerun()
            elif key == "KAY-ADMIN-MASTER":
                st.session_state['authorized'] = True
                st.session_state['user_data'] = {"key": "ADMIN", "name": "Master Owner", "role": "Owner", "expiry_date": "2099-12-31"}
                st.session_state['user_role'] = "Owner"
                st.rerun()
            else:
                st.error("Invalid Key. Contact +233546044673")

    with tab2:
        st.info("Staff: Log in with the credentials provided by your company Admin.")
        # Future logic for individual staff accounts goes here

# --- 3. OWNER'S REGISTRATION DASHBOARD ---
def owner_dashboard():
    st.title("👑 Owner's Registration Center")
    st.subheader("Register Paying Companies")
    
    with st.form("new_reg"):
        name = st.text_input("Company Name")
        key = st.text_input("Assign Unique Key")
        days = st.number_input("Subscription Days", value=30)
        if st.form_submit_button("Register & Save"):
            expiry = datetime.now().date() + timedelta(days=days)
            conn = sqlite3.connect('eka_accounting.db')
            conn.execute("INSERT OR REPLACE INTO registry VALUES (?, ?, ?, ?, ?)", 
                         (key, name, "Pro", expiry, "Client"))
            conn.commit()
            conn.close()
            st.success(f"Registered {name} with Key: {key}")

    st.divider()
    st.subheader("Managed Subscriptions")
    conn = sqlite3.connect('eka_accounting.db')
    st.write(pd.read_sql("SELECT name, key, expiry_date FROM registry WHERE role='Client'", conn))
    conn.close()

# --- 4. THE 18-MODULE ACCOUNTING ERP ---
def erp_dashboard():
    user = st.session_state['user_data']
    role = st.session_state['user_role']
    
    # Expiry Check
    expiry = datetime.strptime(user['expiry_date'], '%Y-%m-%d').date()
    days_left = (expiry - datetime.now().date()).days
    
    st.sidebar.title(f"🏢 {user['name']}")
    st.sidebar.write(f"Role: **{role}**")
    
    if days_left <= 7:
        st.warning(f"⚠️ Subscription Reminder: {days_left} days left.")

    menu = st.sidebar.selectbox("Navigation", [
        "1. Company Setup", "2. Chart of Accounts", "3. Groups", "4. Inventory",
        "5. Pricing", "6. Voucher Entry", "7. Tax Config", "8. Banking",
        "9. Receivables", "10. Payables", "11. Fixed Assets", "12. Payroll",
        "15. Financial Reports"
    ])

    can_edit = (role == "Administrator")

    if menu == "1. Company Setup":
        st.header("🏗️ Company Setup")
        st.text_input("Company Name", value=user['name'], disabled=not can_edit)
        st.text_input("Base Currency", value="Ghana Cedi (GHS)", disabled=True)
        st.text_area("Statutory Details (VAT/TIN)", disabled=not can_edit)
        if can_edit: st.button("Save Changes")

    elif menu == "2. Chart of Accounts":
        st.header("📚 Chart of Accounts")
        st.info("Structure: Assets | Liabilities | Equity | Income | Expenses")
        if can_edit:
            st.text_input("Create New Ledger Name")
            st.selectbox("Category", ["Cash", "Bank", "Inventory", "Loans", "Sales", "Salaries"])
            st.button("Add Ledger")
        else:
            st.write("View-Only Mode: Contact Admin to add ledgers.")

    elif menu == "6. Voucher Entry":
        st.header("✍️ Voucher Entry (Transactions)")
        if can_edit:
            vtype = st.selectbox("Voucher Type", ["Sales", "Purchase", "Receipt", "Payment", "Journal"])
            st.date_input("Date")
            st.number_input("Amount (GHS)")
            st.text_area("Narration")
            st.button("Post Transaction")
        else:
            st.error("Staff access: You are not authorized to post transactions.")

    elif menu == "15. Financial Reports":
        st.header("📊 Financial Reports")
        st.button("📄 Profit & Loss Statement")
        st.button("📄 Balance Sheet")
        st.button("📄 Cash Flow Statement")

# --- 5. MAIN LOGIC ---
if not st.session_state['authorized']:
    login_screen()
else:
    if st.session_state['user_data']['role'] == "Owner":
        owner_dashboard()
    else:
        erp_dashboard()

if st.sidebar.button("Log Out"):
    st.session_state['authorized'] = False
    st.rerun()