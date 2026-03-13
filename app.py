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
    t1, t2 = st.tabs(["Login", "Recovery"])
    
    with t1:
        key_in = st.text_input("Enter License Key", type="password", key="login_key_input")
        if st.button("Unlock System", key="login_btn"):
            if key_in == "JUANMANUEL2":
                st.session_state.auth, st.session_state.user = True, {"name": "Developer", "role": "Dev", "key": "ADMIN"}
                st.rerun()
            
            conn = get_connection()
            # Check Master, Sub-Admin, and Staff
            res = conn.execute("SELECT key, name FROM companies WHERE key=?", (key_in,)).fetchone()
            if res:
                st.session_state.auth, st.session_state.user = True, {"key": res[0], "name": res[1], "role": "Master Admin"}
                st.rerun()
            
            res_s = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (key_in,)).fetchone()
            if res_s:
                st.session_state.auth, st.session_state.user = True, {"key": res_s[0], "name": res_s[1], "role": "Sub-Admin"}
                st.rerun()

            res_st = conn.execute("SELECT key, name FROM companies WHERE staff_key=?", (key_in,)).fetchone()
            if res_st:
                st.session_state.auth, st.session_state.user = True, {"key": res_st[0], "name": res_st[1], "role": "Staff"}
                st.rerun()
            
            st.error("Invalid Key.")

    with t2:
        c_name = st.text_input("Company Name", key="recov_cname")
        ans = st.text_input("Recovery Answer", type="password", key="recov_ans_input")
        if st.button("Recover Key", key="recov_btn"):
            conn = get_connection()
            res = conn.execute("SELECT key FROM companies WHERE name=? AND recovery_answer=?", (c_name, ans)).fetchone()
            if res: st.success(f"Your Master Key: {res[0]}")
            else: st.error("Verification failed.")

if not st.session_state.auth:
    login_ui()
else:
    u = st.session_state.user
    if u['role'] == "Dev":
        st.title("👑 Dev Center")
        with st.form("reg_form"):
            n, k, t = st.text_input("Name"), st.text_input("Key"), st.text_input("TIN")
            if st.form_submit_button("Register"):
                conn = get_connection()
                conn.execute("INSERT OR REPLACE INTO companies (key, name, tin) VALUES (?, ?, ?)", (k, n, t))
                conn.commit()
                st.success("Registered!")
    else:
        st.sidebar.title(f"🏢 {u['name']}")
        active_role = u['role']
        
        # Admin can toggle to Staff view
        if u['role'] == "Master Admin":
            v = st.sidebar.radio("View Mode", ["Master Admin", "Staff (Read-Only)"], key="view_toggle")
            active_role = "Staff" if "Staff" in v else "Master Admin"

        menu = ["POS (Point of Sale)", "Vouchers", "Chart of Accounts", "Inventory", "Sales", "Purchases", "Banking", "Receivables", "Payables", "Taxation", "Payroll", "Fixed Assets", "Financial Reports", "Audit Trail"]
        if active_role == "Master Admin": menu.insert(0, "Company Setup")
        
        choice = st.sidebar.selectbox("Navigate To", menu, key="nav_menu")
        
        # Route to modules
        if choice == "Company Setup": show_company_setup(u['key'], u['name'], active_role)
        elif choice == "POS (Point of Sale)": show_pos(u['key'], u['name'], active_role)
        elif choice == "Vouchers": show_vouchers(u['key'], active_role)
        elif choice == "Chart of Accounts": show_chart_of_accounts(u['key'], active_role)
        elif choice == "Inventory": show_inventory(u['key'], active_role)
        elif choice == "Sales": show_sales_purchase(u['key'], active_role, "Sales")
        elif choice == "Purchases": show_sales_purchase(u['key'], active_role, "Purchase")
        elif choice == "Banking": show_banking(u['key'], active_role)
        elif choice == "Receivables": show_aging_reports(u['key'], "Receivable")
        elif choice == "Payables": show_aging_reports(u['key'], "Payable")
        elif choice == "Taxation": show_tax_reports(u['key'])
        elif choice == "Payroll": show_payroll(u['key'], active_role)
        elif choice == "Fixed Assets": show_fixed_assets(u['key'], active_role)
        elif choice == "Financial Reports": show_reports(u['key'])
        elif choice == "Audit Trail": show_audit_trail(u['key'])

    if st.sidebar.button("Logout", key="logout_btn"):
        st.session_state.auth = False
        st.rerun()