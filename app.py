import streamlit as st
from database import get_connection
from modules import *
from datetime import datetime, timedelta

st.set_page_config(page_title="E.K.A Cloud Accounting", layout="wide")

if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None

def login():
    st.title("🛡️ E.K.A Cloud Accounting - Access Portal")
    key = st.text_input("Enter License Key", type="password")
    
    if st.button("Unlock System"):
        if key == "KAY-ADMIN-MASTER":
            st.session_state.auth = True
            st.session_state.user = {"name": "Master Admin", "role": "Owner", "key": "ADMIN"}
            st.rerun()
        else:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM companies WHERE key=?", (key,))
            res = cur.fetchone()
            if res:
                st.session_state.auth = True
                st.session_state.user = {"key": res[0], "name": res[1], "expiry": res[3], "role": "Client"}
                st.rerun()
            else:
                st.error("Invalid Key. Contact +233546044673")

def owner_admin():
    st.title("👑 Owner's Registration Center")
    with st.form("reg"):
        n = st.text_input("Company Name")
        k = st.text_input("Assign Unique Key")
        d = st.number_input("Subscription Days", value=30)
        if st.form_submit_button("Register & Save"):
            exp = (datetime.now() + timedelta(days=d)).date()
            conn = get_connection()
            conn.execute("INSERT OR REPLACE INTO companies VALUES (?, ?, ?, ?)", (k, n, "", str(exp)))
            conn.commit()
            st.success(f"Registered {n}! Give them key: {k}")

if not st.session_state.auth:
    login()
else:
    user = st.session_state.user
    if user['role'] == "Owner":
        owner_admin()
    else:
        st.sidebar.title(f"🏢 {user['name']}")
        role_type = st.sidebar.radio("Your Role", ["Administrator (Full Access)", "Staff (View Only)"])
        can_edit = (role_type == "Administrator (Full Access)")
        
        # 18-Module Sidebar
        menu = st.sidebar.selectbox("Modules", ["Company Setup", "Inventory", "Vouchers", "Reports"])
        
        if menu == "Company Setup": show_company_setup(user['name'], can_edit)
        elif menu == "Inventory": show_inventory(can_edit)
        elif menu == "Vouchers": show_vouchers(can_edit)
        elif menu == "Reports": show_reports()

    if st.sidebar.button("Log Out"):
        st.session_state.auth = False
        st.rerun()