import streamlit as st
from database import get_connection, init_db
from modules import *
import os

init_db() 

st.set_page_config(page_title="E.K.A Cloud ERP", layout="wide")

if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None

def login():
    st.title("🛡️ E.K.A Cloud Accounting - Access Portal")
    tab1, tab2 = st.tabs(["Login", "Forgot Password"])
    
    with tab1:
        user_input = st.text_input("Enter License Key", type="password")
        if st.button("Unlock System"):
            if user_input == "JUANMANUEL2":
                st.session_state.auth, st.session_state.user = True, {"name": "Developer", "role": "Dev", "key": "ADMIN"}
                st.rerun()
            
            conn = get_connection()
            # Path A: Master Admin Key
            res = conn.execute("SELECT key, name FROM companies WHERE key=?", (user_input,)).fetchone()
            if res:
                st.session_state.auth, st.session_state.user = True, {"key": res[0], "name": res[1], "role": "Master Admin"}
                st.rerun()
            
            # Path B: Sub-Admin (Data Entry) Key
            res_sub = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (user_input,)).fetchone()
            if res_sub:
                st.session_state.auth, st.session_state.user = True, {"key": res_sub[0], "name": res_sub[1], "role": "Sub-Admin"}
                st.rerun()

            # Path C: Staff (Read-Only) Key
            if user_input.endswith("-staff"):
                actual_key = user_input.replace("-staff", "")
                res_staff = conn.execute("SELECT key, name FROM companies WHERE key=?", (actual_key,)).fetchone()
                if res_staff:
                    st.session_state.auth, st.session_state.user = True, {"key": res_staff[0], "name": res_staff[1], "role": "Staff"}
                    st.rerun()
            
            st.error("Invalid Key. If you are Staff, ensure you use your assigned '-staff' suffix.")

    with tab2:
        st.subheader("Reset Access")
        comp_name = st.text_input("Company Registered Name")
        answer = st.text_input("Recovery Answer", type="password")
        if st.button("Reveal Master Key"):
            conn = get_connection()
            res = conn.execute("SELECT key FROM companies WHERE name=? AND recovery_answer=?", (comp_name, answer)).fetchone()
            if res: st.success(f"Verified. Your Master Key is: {res[0]}")
            else: st.error("Verification failed. Incorrect details.")

if not st.session_state.auth:
    login()
else:
    u = st.session_state.user
    if u['role'] == "Dev":
        st.title("👑 Developer Dashboard")
        with st.form("reg"):
            n, k = st.text_input("Company Name"), st.text_input("Master Key")
            if st.form_submit_button("Register"):
                conn = get_connection()
                conn.execute("INSERT OR REPLACE INTO companies (key, name) VALUES (?, ?)", (k, n))
                conn.commit()
                st.success(f"Registered {n}")
    else:
        st.sidebar.title(f"🏢 {u['name']}")
        
        # PERMISSION LOCK: Only Master Admin can toggle views
        if u['role'] == "Master Admin":
            role_select = st.sidebar.radio("View As", ["Master Admin", "Staff View (Read-Only)"])
            active_role = "Staff" if role_select == "Staff View (Read-Only)" else "Master Admin"
        else:
            # Sub-Admins and Staff are LOCKED into their specific roles
            active_role = u['role']
            st.sidebar.info(f"📍 Access Level: {active_role}")

        # Menu visibility logic
        menu_options = ["Vouchers", "Payroll", "Audit Trail", "Reports"]
        if active_role == "Master Admin":
            menu_options.insert(0, "Company Setup")
        
        menu = st.sidebar.selectbox("Navigate To:", menu_options)
        
        if menu == "Company Setup": show_company_setup(u['key'], u['name'], active_role)
        elif menu == "Vouchers": show_vouchers(u['key'], active_role)
        elif menu == "Payroll": show_payroll(u['key'], active_role)
        elif menu == "Audit Trail": show_audit_trail(u['key'])
        elif menu == "Reports": show_reports(u['key'])

    if st.sidebar.button("Log Out"):
        st.session_state.auth = False
        st.rerun()