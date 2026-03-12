import streamlit as st
from database import get_connection, init_db
from modules import *

init_db()
st.set_page_config(page_title="E.K.A Cloud ERP", layout="wide")

if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None

def login_ui():
    st.title("🛡️ E.K.A Cloud Accounting")
    t1, t2 = st.tabs(["Login", "Forgot Password"])
    with t1:
        key_in = st.text_input("License Key", type="password")
        if st.button("Unlock"):
            conn = get_connection()
            # 1. Master Admin
            res = conn.execute("SELECT key, name FROM companies WHERE key=?", (key_in,)).fetchone()
            if res:
                st.session_state.auth, st.session_state.user = True, {"key": res[0], "name": res[1], "role": "Master Admin"}
                st.rerun()
            # 2. Sub-Admin
            res_s = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (key_in,)).fetchone()
            if res_s:
                st.session_state.auth, st.session_state.user = True, {"key": res_s[0], "name": res_s[1], "role": "Sub-Admin"}
                st.rerun()
            # 3. Staff
            if key_in.endswith("-staff"):
                k = key_in.replace("-staff", "")
                res_st = conn.execute("SELECT key, name FROM companies WHERE key=?", (k,)).fetchone()
                if res_st:
                    st.session_state.auth, st.session_state.user = True, {"key": res_st[0], "name": res_st[1], "role": "Staff"}
                    st.rerun()
            st.error("Access Denied.")
    with t2:
        c_name = st.text_input("Company Name")
        ans = st.text_input("Recovery Answer", type="password")
        if st.button("Recover Key"):
            conn = get_connection()
            res = conn.execute("SELECT key FROM companies WHERE name=? AND recovery_answer=?", (c_name, ans)).fetchone()
            if res: st.success(f"Key: {res[0]}")
            else: st.error("Wrong details.")

if not st.session_state.auth:
    login_ui()
else:
    u = st.session_state.user
    st.sidebar.title(f"🏢 {u['name']}")
    
    # Permission Logic
    if u['role'] == "Master Admin":
        view = st.sidebar.radio("View As", ["Master Admin", "Staff (Read-Only)"])
        active_role = "Staff" if view == "Staff (Read-Only)" else "Master Admin"
    else:
        active_role = u['role']
        st.sidebar.info(f"Access: {active_role}")

    menu_opts = ["Vouchers", "Payroll", "Audit Trail", "Reports"]
    if active_role == "Master Admin": menu_opts.insert(0, "Company Setup")
    
    choice = st.sidebar.selectbox("Navigate To", menu_opts)
    
    if choice == "Company Setup": show_company_setup(u['key'], u['name'], active_role)
    elif choice == "Vouchers": show_vouchers(u['key'], active_role)
    elif choice == "Payroll": show_payroll(u['key'], active_role)
    elif choice == "Audit Trail": show_audit_trail(u['key'])
    elif choice == "Reports": show_reports(u['key'])
    
    if st.sidebar.button("Logout"):
        st.session_state.auth = False
        st.rerun()