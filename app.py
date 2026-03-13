import streamlit as st
from database import get_connection, init_db
from modules import *

# 1. Boot System
init_db()
st.set_page_config(
    page_title="E.K.A Cloud ERP v3", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# 2. Session Management
if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None

def login_ui():
    """Secure Multi-Tier Authentication Interface."""
    st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>🛡️ E.K.A ENTERPRISE ERP</h1>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["🔒 Secure Login", "🔑 System Recovery"])
    
    with t1:
        # Assigned unique keys to ensure no Duplicate ID errors
        license_key = st.text_input(
            "System License Key", 
            type="password", 
            key="v3_final_login_input_field"
        )
        
        if st.button("Access Cloud Modules", key="v3_final_auth_submit_btn"):
            if license_key == "JUANMANUEL2":
                st.session_state.auth = True
                st.session_state.user = {"name": "Gatekeeper", "role": "Dev", "key": "ADMIN"}
                st.rerun()
            
            conn = get_connection()
            # Master Admin Check
            admin = conn.execute("SELECT key, name FROM companies WHERE key=?", (license_key,)).fetchone()
            if admin:
                st.session_state.auth = True
                st.session_state.user = {"key": admin[0], "name": admin[1], "role": "Master Admin"}
                st.rerun()
            
            # Sub-Admin/Staff Check
            sub = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (license_key,)).fetchone()
            if sub:
                st.session_state.auth = True
                st.session_state.user = {"key": sub[0], "name": sub[1], "role": "Sub-Admin"}
                st.rerun()
                
            if license_key.endswith("-staff"):
                pure_k = license_key.replace("-staff", "")
                staff = conn.execute("SELECT key, name FROM companies WHERE key=?", (pure_k,)).fetchone()
                if staff:
                    st.session_state.auth = True
                    st.session_state.user = {"key": staff[0], "name": staff[1], "role": "Staff"}
                    st.rerun()
            
            st.error("Access Denied. Please verify your License Key.")

    with t2:
        st.subheader("Cloud Recovery Protocol")
        rec_name = st.text_input("Company Registered Name", key="v3_rec_name_input")
        rec_ans = st.text_input("Security Recovery Answer", type="password", key="v3_rec_ans_input")
        if st.button("Retrieve Master Key", key="v3_rec_action_btn"):
            conn = get_connection()
            res = conn.execute("SELECT key FROM companies WHERE name=? AND recovery_answer=?", (rec_name, rec_ans)).fetchone()
            if res: 
                st.success(f"Identity Verified. Your Master Key is: {res[0]}")
            else: 
                st.error("Verification failed. Data does not match our records.")

if not st.session_state.auth:
    login_ui()
else:
    u = st.session_state.user
    if u['role'] == "Dev":
        # Gatekeeper Dashboard with Software Amounts and Payment Info
        st.title("👑 Gatekeeper System Dashboard")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Licenses", "12 Active")
        m2.metric("Pending Renewals", "3")
        m3.metric("Monthly Revenue", "GHS 4,500")
        m4.metric("System Uptime", "100%")

        st.markdown("---")
        with st.form("provision_new_client_v3"):
            st.subheader("Deploy New Enterprise Instance")
            cl_name = st.text_input("Client/Company Name")
            cl_key = st.text_input("Assign Master Key")
            cl_fee = st.number_input("Software Setup Fee (GHS)", value=1200.0)
            cl_months = st.number_input("Subscription Period (Months)", value=12)
            
            if st.form_submit_button("Initialize & Deploy"):
                conn = get_connection()
                conn.execute("INSERT INTO companies (key, name) VALUES (?,?)", (cl_key, cl_name))
                conn.execute("INSERT INTO system_settings (software_fee, subscription_months) VALUES (?,?)", (cl_fee, cl_months))
                conn.commit()
                st.success(f"System Instance deployed for {cl_name} with {cl_months} months access.")
    else:
        st.sidebar.markdown(f"""
        <div style='background-color:#f0f2f6; padding:20px; border-radius:15px; border: 1px solid #d1d5db;'>
            <h2 style='margin-bottom:0;'>🏢 {u['name']}</h2>
            <p style='color:#6b7280;'>Role: <b>{u['role']}</b></p>
        </div>
        """, unsafe_allow_html=True)
        
        menu = [
            "POS (Point of Sale)", "Vouchers & Journals", "Chart of Accounts", 
            "Inventory & Stock", "Sales Invoicing", "Purchase Orders", 
            "Banking & Cash", "Accounts Receivable", "Accounts Payable", 
            "Taxation (VAT/NHIL)", "Ghana Payroll (SSNIT)", "Fixed Asset Register", 
            "Financial Intelligence", "System Audit Trail"
        ]
        
        if u['role'] == "Master Admin":
            menu.insert(0, "Company Setup")
        
        choice = st.sidebar.selectbox("Go to Module:", menu, key="v3_main_nav_dropdown")
        
        # Comprehensive Mapping Logic
        if choice == "Company Setup": show_company_setup(u['key'], u['name'], u['role'])
        elif choice == "POS (Point of Sale)": show_pos(u['key'], u['name'], u['role'])
        elif choice == "Vouchers & Journals": show_vouchers(u['key'], u['role'])
        elif choice == "Chart of Accounts": show_chart_of_accounts(u['key'], u['role'])
        elif choice == "Inventory & Stock": show_inventory(u['key'], u['role'])
        elif choice == "Sales Invoicing": show_sales_purchase(u['key'], u['role'], "Sales")
        elif choice == "Purchase Orders": show_sales_purchase(u['key'], u['role'], "Purchase")
        elif choice == "Banking & Cash": show_banking(u['key'], u['role'])
        elif choice == "Accounts Receivable": show_aging(u['key'], "Receivable")
        elif choice == "Accounts Payable": show_aging(u['key'], "Payable")
        elif choice == "Taxation (VAT/NHIL)": show_taxation(u['key'])
        elif choice == "Ghana Payroll (SSNIT)": show_payroll(u['key'], u['role'])
        elif choice == "Fixed Asset Register": show_fixed_assets(u['key'], u['role'])
        elif choice == "Financial Intelligence": show_reports(u['key'])
        elif choice == "System Audit Trail": show_audit_trail(u['key'])

    st.sidebar.markdown("---")
    if st.sidebar.button("🔴 Secure Logout", use_container_width=True, key="v3_final_logout"):
        st.session_state.auth = False
        st.rerun()