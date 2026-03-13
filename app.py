import streamlit as st
from database import get_connection, init_db
from modules import *

# Initialize database on startup
init_db()

st.set_page_config(page_title="E.K.A Cloud ERP", layout="wide")

if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None

def login_ui():
    st.title("🛡️ E.K.A Cloud Accounting - Access Portal")
    t1, t2 = st.tabs(["Login", "Forgot Password"])
    
    with t1:
        key_in = st.text_input("Enter License Key", type="password")
        if st.button("Unlock System"):
            # 1. DEVELOPER ACCESS (Priority)
            if key_in == "JUANMANUEL2":
                st.session_state.auth = True
                st.session_state.user = {"name": "Developer", "role": "Dev", "key": "ADMIN"}
                st.rerun()
            
            conn = get_connection()
            # 2. MASTER ADMIN CHECK
            res = conn.execute("SELECT key, name FROM companies WHERE key=?", (key_in,)).fetchone()
            if res:
                st.session_state.auth, st.session_state.user = True, {"key": res[0], "name": res[1], "role": "Master Admin"}
                st.rerun()
            
            # 3. SUB-ADMIN CHECK
            res_s = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (key_in,)).fetchone()
            if res_s:
                st.session_state.auth, st.session_state.user = True, {"key": res_s[0], "name": res_s[1], "role": "Sub-Admin"}
                st.rerun()
            
            # 4. STAFF CHECK
            if key_in.endswith("-staff"):
                k = key_in.replace("-staff", "")
                res_st = conn.execute("SELECT key, name FROM companies WHERE key=?", (k,)).fetchone()
                if res_st:
                    st.session_state.auth, st.session_state.user = True, {"key": res_st[0], "name": res_st[1], "role": "Staff"}
                    st.rerun()
            
            st.error("Access Denied. Please verify your key.")

    with t2:
        c_name = st.text_input("Registered Company Name")
        ans = st.text_input("Recovery Answer", type="password")
        if st.button("Recover Master Key"):
            conn = get_connection()
            res = conn.execute("SELECT key FROM companies WHERE name=? AND recovery_answer=?", (c_name, ans)).fetchone()
            if res: st.success(f"Verified. Your Master Key is: {res[0]}")
            else: st.error("Verification failed.")

if not st.session_state.auth:
    login_ui()
else:
    u = st.session_state.user
    
    if u['role'] == "Dev":
        st.title("👑 Developer Control Center")
        with st.form("reg"):
            n, k = st.text_input("New Company Name"), st.text_input("Set Master Key")
            if st.form_submit_button("Register Company"):
                conn = get_connection()
                conn.execute("INSERT OR REPLACE INTO companies (key, name) VALUES (?, ?)", (k, n))
                conn.commit()
                st.success(f"Registered {n} with key {k}")
    
    else:
        st.sidebar.title(f"🏢 {u['name']}")
        
        # LOCKED ROLE: No radio buttons, strict access level
        active_role = u['role']
        st.sidebar.info(f"📍 Mode: {active_role}")

        # FULL ERP MENU
        menu_opts = [
            "Vouchers", "Chart of Accounts", "Inventory", 
            "Sales", "Purchases", "Banking", 
            "Receivables", "Payables", "Taxation", 
            "Payroll", "Fixed Assets", "Financial Reports", "Audit Trail"
        ]
        
        # Security: Only Master Admin sees Company Setup
        if active_role == "Master Admin":
            menu_opts.insert(0, "Company Setup")
        
        choice = st.sidebar.selectbox("Navigate To", menu_opts)
        
        # ROUTING LOGIC
        if choice == "Company Setup": show_company_setup(u['key'], u['name'], active_role)
        elif choice == "Vouchers": show_vouchers(u['key'], active_role)
        elif choice == "Chart of Accounts": show_chart_of_accounts(u['key'], active_role)
        elif choice == "Inventory": show_inventory(u['key'], active_role)
        elif choice == "Sales": show_sales_purchase(u['key'], active_role, mode="Sales")
        elif choice == "Purchases": show_sales_purchase(u['key'], active_role, mode="Purchase")
        elif choice == "Banking": show_banking(u['key'], active_role)
        elif choice == "Receivables": show_aging_reports(u['key'], mode="Receivable")
        elif choice == "Payables": show_aging_reports(u['key'], mode="Payable")
        elif choice == "Taxation": show_tax_reports(u['key'])
        elif choice == "Payroll": show_payroll(u['key'], active_role)
        elif choice == "Fixed Assets": show_fixed_assets(u['key'], active_role)
        elif choice == "Financial Reports": show_reports(u['key'])
        elif choice == "Audit Trail": show_audit_trail(u['key'])
    
    if st.sidebar.button("Logout"):
        st.session_state.auth = False
        st.rerun()