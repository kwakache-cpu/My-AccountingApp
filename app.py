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
            # 1. Check if it's a Master Admin Key
            res = conn.execute("SELECT key, name FROM companies WHERE key=?", (user_input,)).fetchone()
            if res:
                st.session_state.auth, st.session_state.user = True, {"key": res[0], "name": res[1], "role": "Master Admin"}
                st.rerun()
            
            # 2. Check if it's a Sub-Admin (Bookkeeper) Key
            res_sub = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (user_input,)).fetchone()
            if res_sub:
                st.session_state.auth, st.session_state.user = True, {"key": res_sub[0], "name": res_sub[1], "role": "Sub-Admin"}
                st.rerun()
            
            st.error("Invalid Key.")

    with tab2:
        st.subheader("Reset Access")
        comp_id = st.text_input("Company Name / TIN")
        answer = st.text_input("Your Secret Recovery Answer", type="password")
        if st.button("Reveal Master Key"):
            conn = get_connection()
            res = conn.execute("SELECT key FROM companies WHERE name=? AND recovery_answer=?", (comp_id, answer)).fetchone()
            if res: st.success(f"Your Master Key is: {res[0]}")
            else: st.error("Incorrect details.")

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
        # Staff role is selected here
        role_select = st.sidebar.radio("Session Type", ["Active Work", "Staff View (Read-Only)"])
        
        # Internal Logic: Staff can never be Sub-Admin or Master Admin
        final_role = "Staff" if role_select == "Staff View (Read-Only)" else u['role']
        
        menu = st.sidebar.selectbox("Modules", ["Company Setup", "Vouchers", "Payroll", "Audit Trail", "Reports"])
        
        if menu == "Company Setup": show_company_setup(u['key'], u['name'], final_role)
        elif menu == "Vouchers": show_vouchers(u['key'], final_role)
        elif menu == "Payroll": show_payroll(u['key'], final_role)
        elif menu == "Audit Trail": show_audit_trail(u['key'])
        elif menu == "Reports": show_reports(u['key'])

    if st.sidebar.button("Log Out"):
        st.session_state.auth = False
        st.rerun()