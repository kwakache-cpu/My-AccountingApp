import streamlit as st
from database import get_connection, init_db
from modules import *

# Initialize Database on Startup
init_db()

# Page Configuration
st.set_page_config(
    page_title="E.K.A Cloud Accounting v3",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Authentication State Management
if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None

def login_ui():
    st.markdown("<h1 style='text-align: center; color: #003366;'>🛡️ E.K.A Enterprise ERP</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Cloud-Based Financial Intelligence System</p>", unsafe_allow_html=True)
    
    tab_login, tab_recover = st.tabs(["🔒 Secure Login", "🔑 System Recovery"])
    
    with tab_login:
        # Fixed Duplicate ID error with unique versioned keys
        license_key = st.text_input("System License Key", type="password", key="login_key_v3_final")
        
        if st.button("Authenticate System", key="auth_btn_v3_final"):
            # 1. Developer Access
            if license_key == "JUANMANUEL2":
                st.session_state.auth = True
                st.session_state.user = {"name": "System Dev", "role": "Dev", "key": "ADMIN"}
                st.rerun()
            
            conn = get_connection()
            # 2. Master Admin Access
            admin = conn.execute("SELECT key, name FROM companies WHERE key=?", (license_key,)).fetchone()
            if admin:
                st.session_state.auth = True
                st.session_state.user = {"key": admin[0], "name": admin[1], "role": "Master Admin"}
                st.rerun()
            
            # 3. Sub-Admin Access
            sub = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (license_key,)).fetchone()
            if sub:
                st.session_state.auth = True
                st.session_state.user = {"key": sub[0], "name": sub[1], "role": "Sub-Admin"}
                st.rerun()
                
            # 4. Staff Access (Read-Only)
            if license_key.endswith("-staff"):
                pure_key = license_key.replace("-staff", "")
                staff = conn.execute("SELECT key, name FROM companies WHERE key=?", (pure_key,)).fetchone()
                if staff:
                    st.session_state.auth = True
                    st.session_state.user = {"key": staff[0], "name": staff[1], "role": "Staff"}
                    st.rerun()
            
            st.error("Access Denied. Invalid or Expired License Key.")

    with tab_recover:
        st.subheader("Key Recovery Protocol")
        rec_name = st.text_input("Registered Company Name", key="recovery_name_field")
        rec_ans = st.text_input("Recovery Security Answer", type="password", key="recovery_ans_field")
        if st.button("Validate & Retrieve", key="recovery_submit_v3"):
            conn = get_connection()
            res = conn.execute("SELECT key FROM companies WHERE name=? AND recovery_answer=?", (rec_name, rec_ans)).fetchone()
            if res:
                st.success(f"Identity Verified. Your License Key is: {res[0]}")
            else:
                st.error("Security mismatch. Access to key recovery denied.")

if not st.session_state.auth:
    login_ui()
else:
    u = st.session_state.user
    if u['role'] == "Dev":
        st.title("👑 Developer Control Panel")
        with st.form("provision_company_form"):
            c_name = st.text_input("Enter Company Name")
            c_key = st.text_input("Generate Master Key")
            if st.form_submit_button("Deploy System Instance"):
                conn = get_connection()
                conn.execute("INSERT OR REPLACE INTO companies (key, name) VALUES (?, ?)", (c_key, c_name))
                conn.commit()
                st.success(f"System Instance deployed for {c_name}")
    else:
        st.sidebar.markdown(f"<div style='background-color:#f0f2f6; padding:10px; border-radius:5px;'><h2 style='text-align: center;'>🏢 {u['name']}</h2></div>", unsafe_allow_html=True)
        role = u['role']
        st.sidebar.markdown(f"**Access Level:** `{role}`")

        # Full ERP Navigation Menu
        nav_options = [
            "POS (Point of Sale)", "Vouchers & Journals", "Chart of Accounts", 
            "Inventory & Stock", "Sales Invoicing", "Purchase Orders", 
            "Banking & Cash", "Accounts Receivable", "Accounts Payable", 
            "Taxation (VAT/NHIL)", "Ghana Payroll (SSNIT)", "Fixed Asset Register", 
            "Financial Intelligence", "Audit Trail"
        ]
        
        if role == "Master Admin":
            nav_options.insert(0, "Company Setup")
        
        choice = st.sidebar.selectbox("Go to Module:", nav_options, key="main_navigation_select")
        
        # Unified Module Routing
        if choice == "Company Setup": show_company_setup(u['key'], u['name'], role)
        elif choice == "POS (Point of Sale)": show_pos(u['key'], u['name'], role)
        elif choice == "Vouchers & Journals": show_vouchers(u['key'], role)
        elif choice == "Chart of Accounts": show_chart_of_accounts(u['key'], role)
        elif choice == "Inventory & Stock": show_inventory(u['key'], role)
        elif choice == "Sales Invoicing": show_sales_purchase(u['key'], role, "Sales")
        elif choice == "Purchase Orders": show_sales_purchase(u['key'], role, "Purchase")
        elif choice == "Banking & Cash": show_banking(u['key'], role)
        elif choice == "Accounts Receivable": show_aging(u['key'], "Receivable")
        elif choice == "Accounts Payable": show_aging(u['key'], "Payable")
        elif choice == "Taxation (VAT/NHIL)": show_taxation(u['key'])
        elif choice == "Ghana Payroll (SSNIT)": show_payroll(u['key'], role)
        elif choice == "Fixed Asset Register": show_fixed_assets(u['key'], role)
        elif choice == "Financial Intelligence": show_reports(u['key'])
        elif choice == "Audit Trail": show_audit_trail(u['key'])

    if st.sidebar.button("🔴 Secure Logout", key="sidebar_logout_btn", use_container_width=True):
        st.session_state.auth = False
        st.rerun() 