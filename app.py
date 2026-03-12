import streamlit as st
from database import get_connection
from modules import *
from datetime import datetime, timedelta

st.set_page_config(page_title="E.K.A Cloud ERP", layout="wide")

if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None

def login():
    st.title("🛡️ E.K.A Cloud Accounting - Access Portal")
    
    # MASTER OVERRIDE: Hardcoded for immediate access
    MASTER_ADMIN_KEY = "JUANMANUEL2"
    
    user_input = st.text_input("Enter License Key", type="password")
    
    if st.button("Unlock System"):
        # Check against the override key first
        if user_input.strip() == MASTER_ADMIN_KEY:
            st.session_state.auth = True
            st.session_state.user = {"name": "Master Owner", "role": "Owner", "key": "ADMIN"}
            st.success("Master Access Granted!")
            st.rerun()
        else:
            # Check database for clients
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM companies WHERE key=?", (user_input.strip(),))
            res = cur.fetchone()
            if res:
                st.session_state.auth = True
                st.session_state.user = {"key": res[0], "name": res[1], "expiry": res[3], "role": "Client"}
                st.rerun()
            else:
                st.error("Invalid Key. Please contact support.")

# --- APP MAIN LOGIC ---
if not st.session_state.auth:
    login()
else:
    user = st.session_state.user
    if user['role'] == "Owner":
        st.sidebar.success("🔑 MASTER ADMIN MODE")
        st.title("👑 Owner's Registration Center")
        
        # Form to add new clients (like Star Bakery)
        with st.form("reg_form"):
            name = st.text_input("New Company Name")
            key = st.text_input("Assign Unique Key")
            days = st.number_input("Subscription Days", value=30)
            if st.form_submit_button("Register Company"):
                exp = (datetime.now() + timedelta(days=days)).date()
                conn = get_connection()
                conn.execute("INSERT OR REPLACE INTO companies VALUES (?, ?, ?, ?)", (key, name, "", str(exp)))
                conn.commit()
                st.success(f"Registered {name}! Access Key: {key}")
                
        # Show all registered companies
        st.subheader("Registered Clients")
        conn = get_connection()
        clients = pd.read_sql("SELECT name, key, expiry FROM companies", conn)
        st.table(clients)
    else:
        # Client ERP View
        st.sidebar.title(f"🏢 {user['name']}")
        role = st.sidebar.radio("Access Level", ["Administrator", "Staff"])
        can_edit = (role == "Administrator")
        
        menu = st.sidebar.selectbox("Modules", ["Company Setup", "Inventory", "Vouchers", "Reports"])
        
        if menu == "Company Setup": show_company_setup(user['name'], can_edit)
        elif menu == "Inventory": show_inventory(can_edit)
        elif menu == "Vouchers": show_vouchers(can_edit)
        elif menu == "Reports": show_reports()

    if st.sidebar.button("Log Out"):
        st.session_state.auth = False
        st.rerun()