import streamlit as st
from database import get_connection, init_db
from modules import *

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
            # 1. DEVELOPER ACCESS (The Priority)
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
        # Permission logic for the Sidebar
        if u['role'] == "Master Admin":
            view = st.sidebar.radio("View Mode", ["Master Admin", "Staff (Read-Only)"])
            active_role = "Staff" if view == "Staff (Read-Only)" else "Master Admin"
        else:
            active_role = u['role']
# FIXED ROLE: Users stay in the role they used to log in.
        active_role = u['role']
        st.sidebar.info(f"📍 Mode: {active_role}")

        # Define the menu
        menu_opts = ["Vouchers", "Payroll", "Audit Trail", "Reports"]
        
        # Only the Master Admin can see 'Company Setup'
        if active_role == "Master Admin":
            menu_opts.insert(0, "Company Setup")
        
        choice = st.sidebar.selectbox("Navigate To", menu_opts)
        
        # Call specific modules
        if choice == "Company Setup": show_company_setup(u['key'], u['name'], active_role)
        elif choice == "Vouchers": show_vouchers(u['key'], active_role)
        elif choice == "Payroll": show_payroll(u['key'], active_role)
        elif choice == "Audit Trail": show_audit_trail(u['key'])
        elif choice == "Reports": show_reports(u['key'])
    
    if st.sidebar.button("Logout"):
        st.session_state.auth = False
        st.rerun()