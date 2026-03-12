import streamlit as st
from database import get_connection
from modules import *
from datetime import datetime, timedelta
import pandas as pd

st.set_page_config(page_title="E.K.A Cloud ERP", layout="wide")

if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None

def login():
    st.title("🛡️ E.K.A Cloud Accounting - Access Portal")
    MASTER_KEY = "JUANMANUEL2"
    user_input = st.text_input("Enter License Key", type="password")
    if st.button("Unlock System"):
        if user_input.strip() == MASTER_KEY:
            st.session_state.auth = True
            st.session_state.user = {"name": "Master Admin", "role": "Owner", "key": "ADMIN"}
            st.rerun()
        else:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM companies WHERE key=?", (user_input.strip(),))
            res = cur.fetchone()
            if res:
                st.session_state.auth = True
                st.session_state.user = {"key": res[0], "name": res[1], "role": "Client"}
                st.rerun()
            else:
                st.error("Invalid Key.")

if not st.session_state.auth:
    login()
else:
    user = st.session_state.user
    if user['role'] == "Owner":
        st.title("👑 Owner's Registration Center")
        with st.form("reg"):
            n = st.text_input("Company Name")
            k = st.text_input("Key")
            if st.form_submit_button("Register"):
                conn = get_connection()
                conn.execute("INSERT OR REPLACE INTO companies VALUES (?, ?, ?, ?)", (k, n, "", str(datetime.now().date())))
                conn.commit()
                st.success(f"Registered {n}")
    else:
        st.sidebar.title(f"🏢 {user['name']}")
        role = st.sidebar.radio("Role", ["Administrator", "Staff"])
        menu = st.sidebar.selectbox("Modules", ["Company Setup", "Chart of Accounts", "Inventory", "Vouchers", "Reports"])
        
        if menu == "Company Setup": show_company_setup(user['name'], role=="Administrator")
        elif menu == "Chart of Accounts": show_chart_of_accounts(user['key'], role=="Administrator")
        elif menu == "Vouchers": show_vouchers(user['key'], role=="Administrator")
        elif menu == "Reports": st.write("Financial Statements Generating...")

    if st.sidebar.button("Log Out"):
        st.session_state.auth = False
        st.rerun()