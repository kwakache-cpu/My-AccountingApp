import streamlit as st
from database import get_connection, init_db
from modules import *

# Initialize System
init_db()
st.set_page_config(page_title="E.K.A Cloud ERP", layout="wide", initial_sidebar_state="expanded")

# Session Management
if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None

def login_ui():
    st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>🛡️ E.K.A Cloud Accounting Portal</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Professional Enterprise Resource Planning System</p>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["🔒 System Access", "🔑 Recovery & Support"])
    
    with t1:
        key_in = st.text_input("Enter License Key", type="password", key="login_field_main")
        col_l1, col_l2 = st.columns([1, 4])
        if col_l1.button("Unlock System", key="unlock_btn_main"):
            # 1. DEVELOPER OVERRIDE
            if key_in == "JUANMANUEL2":
                st.session_state.auth, st.session_state.user = True, {"name": "Developer", "role": "Dev", "key": "ADMIN"}
                st.rerun()
            
            conn = get_connection()
            # 2. MASTER ADMIN
            res = conn.execute("SELECT key, name FROM companies WHERE key=?", (key_in,)).fetchone()
            if res:
                st.session_state.auth, st.session_state.user = True, {"key": res[0], "name": res[1], "role": "Master Admin"}
                st.rerun()
            
            # 3. SUB-ADMIN
            res_s = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (key_in,)).fetchone()
            if res_s:
                st.session_state.auth, st.session_state.user = True, {"key": res_s[0], "name": res_s[1], "role": "Sub-Admin"}
                st.rerun()
                
            # 4. STAFF (READ-ONLY)
            if key_in.endswith("-staff"):
                k = key_in.replace("-staff", "")
                res_st = conn.execute("SELECT key, name FROM companies WHERE key=?", (k,)).fetchone()
                if res_st:
                    st.session_state.auth, st.session_state.user = True, {"key": res_st[0], "name": res_st[1], "role": "Staff"}
                    st.rerun()
            st.error("Access Denied: Key not recognized by cloud server.")

    with t2:
        st.info("Verified Company Recovery Service")
        c_name = st.text_input("Registered Company Name", key="recover_cname")
        ans = st.text_input("Security Recovery Answer", type="password", key="recover_ans")
        if st.button("Retrieve Master Key", key="recover_btn"):
            conn = get_connection()
            res = conn.execute("SELECT key FROM companies WHERE name=? AND recovery_answer=?", (c_name, ans)).fetchone()
            if res: st.success(f"Verification Successful. Your Master Key is: {res[0]}")
            else: st.error("Verification failed. Data does not match records.")

if not st.session_state.auth:
    login_ui()
else:
    u = st.session_state.user
    if u['role'] == "Dev":
        st.title("👑 Developer Control Center")
        with st.form("provision_form"):
            n, k = st.text_input("Company Name"), st.text_input("Assign Master Key")
            if st.form_submit_button("Deploy System Instance"):
                conn = get_connection()
                conn.execute("INSERT OR REPLACE INTO companies (key, name) VALUES (?, ?)", (k, n))
                conn.commit()
                st.success(f"Successfully Deployed {n}")
    else:
        # SIDEBAR CONFIGURATION
        st.sidebar.markdown(f"<h2 style='text-align: center;'>🏢 {u['name']}</h2>", unsafe_allow_html=True)
        active_role = u['role']
        st.sidebar.success(f"📍 Mode: {active_role}")

        # FULL ERP NAVIGATION
        menu_items = [
            "POS (Point of Sale)", "Vouchers & Journals", "Chart of Accounts", 
            "Inventory & Stock", "Sales Invoicing", "Purchase Orders", 
            "Banking & Cash", "Accounts Receivable", "Accounts Payable", 
            "Taxation (VAT/NHIL)", "Ghana Payroll (SSNIT)", "Fixed Asset Register", 
            "Financial Intelligence", "System Audit Trail"
        ]
        
        if active_role == "Master Admin":
            menu_items.insert(0, "Company Setup")
        
        choice = st.sidebar.selectbox("Navigate To:", menu_items, key="main_navigation")
        
        # ROUTING LOGIC (Preserving all modules)
        if choice == "Company Setup": show_company_setup(u['key'], u['name'], active_role)
        elif choice == "POS (Point of Sale)": show_pos(u['key'], u['name'], active_role)
        elif choice == "Vouchers & Journals": show_vouchers(u['key'], active_role)
        elif choice == "Chart of Accounts": show_chart_of_accounts(u['key'], active_role)
        elif choice == "Inventory & Stock": show_inventory(u['key'], active_role)
        elif choice == "Sales Invoicing": show_sales_purchase(u['key'], active_role, "Sales")
        elif choice == "Purchase Orders": show_sales_purchase(u['key'], active_role, "Purchase")
        elif choice == "Banking & Cash": show_banking(u['key'], active_role)
        elif choice == "Accounts Receivable": show_aging_reports(u['key'], "Receivable")
        elif choice == "Accounts Payable": show_aging_reports(u['key'], "Payable")
        elif choice == "Taxation (VAT/NHIL)": show_tax_reports(u['key'])
        elif choice == "Ghana Payroll (SSNIT)": show_payroll(u['key'], active_role)
        elif choice == "Fixed Asset Register": show_fixed_assets(u['key'], active_role)
        elif choice == "Financial Intelligence": show_reports(u['key'])
        elif choice == "System Audit Trail": show_audit_trail(u['key'])

    if st.sidebar.button("🔴 Logout System", use_container_width=True):
        st.session_state.auth = False
        st.rerun()