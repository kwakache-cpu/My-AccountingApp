import streamlit as st
import pandas as pd  # <-- ADD THIS IMPORT
from database import get_connection, init_db, log_audit_action
from modules import *
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. Boot System
init_db()
st.set_page_config(
    page_title="E.K.A Cloud ERP v3", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# 2. Session Management with Enhanced Security
if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None
    st.session_state.login_attempts = 0
    st.session_state.last_activity = datetime.now()

# Session timeout (30 minutes)
SESSION_TIMEOUT = 30  # minutes

def check_session_timeout():
    """Check if session has timed out due to inactivity."""
    if st.session_state.auth:
        last_activity = st.session_state.get('last_activity', datetime.now())
        if datetime.now() - last_activity > timedelta(minutes=SESSION_TIMEOUT):
            st.session_state.auth = False
            st.session_state.user = None
            st.warning("Session expired due to inactivity. Please login again.")
            return False
    return True

def update_activity():
    """Update last activity timestamp."""
    st.session_state.last_activity = datetime.now()

def login_ui():
    """Secure Multi-Tier Authentication Interface with Enhanced Security."""
    st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>🛡️ E.K.A ENTERPRISE ERP</h1>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # Check for brute force attempts
    if st.session_state.login_attempts >= 5:
        st.error("Too many failed login attempts. Please wait before trying again.")
        return
    
    t1, t2 = st.tabs(["🔒 Secure Login", "🔑 System Recovery"])
    
    with t1:
        # Assigned unique keys to ensure no Duplicate ID errors
        license_key = st.text_input(
            "System License Key", 
            type="password", 
            key="v3_final_login_input_field"
        )
        
        if st.button("Access Cloud Modules", key="v3_final_auth_submit_btn"):
            try:
                conn = get_connection()
                
                # Developer Backdoor
                if license_key == "JUANMANUEL2":
                    st.session_state.auth = True
                    st.session_state.user = {"name": "Gatekeeper", "role": "Dev", "key": "ADMIN"}
                    log_audit_action(conn, "SYSTEM", "Dev", "Developer login", "Authentication")
                    conn.close()
                    st.session_state.login_attempts = 0
                    st.rerun()
                
                # Master Admin Check
                admin = conn.execute("SELECT key, name FROM companies WHERE key=?", (license_key,)).fetchone()
                if admin:
                    st.session_state.auth = True
                    st.session_state.user = {"key": admin[0], "name": admin[1], "role": "Master Admin"}
                    log_audit_action(conn, admin[0], "Master Admin", "Successful login", "Authentication")
                    conn.close()
                    st.session_state.login_attempts = 0
                    st.rerun()
                
                # Sub-Admin/Staff Check
                sub = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (license_key,)).fetchone()
                if sub:
                    st.session_state.auth = True
                    st.session_state.user = {"key": sub[0], "name": sub[1], "role": "Sub-Admin"}
                    log_audit_action(conn, sub[0], "Sub-Admin", "Successful login", "Authentication")
                    conn.close()
                    st.session_state.login_attempts = 0
                    st.rerun()
                    
                if license_key.endswith("-staff"):
                    pure_k = license_key.replace("-staff", "")
                    staff = conn.execute("SELECT key, name FROM companies WHERE key=?", (pure_k,)).fetchone()
                    if staff:
                        st.session_state.auth = True
                        st.session_state.user = {"key": staff[0], "name": staff[1], "role": "Staff"}
                        log_audit_action(conn, staff[0], "Staff", "Successful login", "Authentication")
                        conn.close()
                        st.session_state.login_attempts = 0
                        st.rerun()
                
                # Failed login attempt
                st.session_state.login_attempts += 1
                log_audit_action(conn, "SYSTEM", "Unknown", f"Failed login attempt {st.session_state.login_attempts}", "Authentication")
                conn.close()
                st.error(f"Access Denied. Please verify your License Key. Attempts: {st.session_state.login_attempts}/5")
                
            except sqlite3.Error as e:
                st.error("System error during authentication. Please try again.")
                logger.error(f"Login error: {e}")

    with t2:
        st.subheader("Cloud Recovery Protocol")
        rec_name = st.text_input("Company Registered Name", key="v3_rec_name_input")
        rec_ans = st.text_input("Security Recovery Answer", type="password", key="v3_rec_ans_input")
        if st.button("Retrieve Master Key", key="v3_rec_action_btn"):
            try:
                conn = get_connection()
                res = conn.execute("SELECT key FROM companies WHERE name=? AND recovery_answer=?", (rec_name, rec_ans)).fetchone()
                if res: 
                    st.success(f"Identity Verified. Your Master Key is: {res[0]}")
                    log_audit_action(conn, res[0], "Recovery", "Successful key recovery", "Authentication")
                else: 
                    st.error("Verification failed. Data does not match our records.")
                    log_audit_action(conn, "SYSTEM", "Recovery", f"Failed recovery attempt for {rec_name}", "Authentication")
                conn.close()
            except sqlite3.Error as e:
                st.error("System error during recovery. Please try again.")
                logger.error(f"Recovery error: {e}")

# Main application flow
if not st.session_state.auth or not check_session_timeout():
    login_ui()
else:
    update_activity()  # Update activity on each interaction
    u = st.session_state.user
    
    if u['role'] == "Dev":
        # Gatekeeper Dashboard with Enhanced Metrics
        st.title("👑 Gatekeeper System Dashboard")
        
        # Real-time system metrics
        try:
            conn = get_connection()
            
            # Get actual metrics from database
            total_companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
            active_subscriptions = conn.execute("SELECT COUNT(*) FROM system_settings WHERE subscription_months > 0").fetchone()[0]
            monthly_revenue = conn.execute("SELECT SUM(software_fee) FROM system_settings").fetchone()[0] or 0
            
            conn.close()
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Licenses", str(total_companies))
            m2.metric("Active Subscriptions", str(active_subscriptions))
            m3.metric("Monthly Revenue", f"GHS {monthly_revenue:.2f}")
            m4.metric("System Uptime", "100%")
            
        except sqlite3.Error as e:
            st.error("Failed to load system metrics")
            logger.error(f"Dashboard metrics error: {e}")

        st.markdown("---")
        with st.form("provision_new_client_v3"):
            st.subheader("Deploy New Enterprise Instance")
            cl_name = st.text_input("Client/Company Name", key="dev_client_name")
            cl_key = st.text_input("Assign Master Key", key="dev_client_key")
            cl_fee = st.number_input("Software Setup Fee (GHS)", value=1200.0, key="dev_setup_fee")
            cl_months = st.number_input("Subscription Period (Months)", value=12, key="dev_sub_months")
            cl_tin = st.text_input("Client TIN (Optional)", key="dev_client_tin")
            
            if st.form_submit_button("Initialize & Deploy"):
                if cl_name and cl_key:
                    try:
                        conn = get_connection()
                        conn.execute("INSERT INTO companies (key, name, tin) VALUES (?,?,?)", (cl_key, cl_name, cl_tin))
                        conn.execute("INSERT INTO system_settings (company_key, software_fee, subscription_months) VALUES (?,?,?)", (cl_key, cl_fee, cl_months))
                        conn.commit()
                        log_audit_action(conn, cl_key, "Dev", f"Provisioned new client: {cl_name}", "System Admin")
                        st.success(f"System Instance deployed for {cl_name} with {cl_months} months access.")
                        conn.close()
                    except sqlite3.Error as e:
                        st.error(f"Failed to deploy client: {e}")
                        logger.error(f"Client deployment error: {e}")
                else:
                    st.error("Client Name and Master Key are required.")
                    
        # System Administration Section
        st.markdown("---")
        st.subheader("🔧 System Administration")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Reinitialize Database", key="dev_reinit_db"):
                if st.checkbox("⚠️ Confirm database reinitialization (This will reset all data)"):
                    init_db()
                    st.success("Database reinitialized successfully.")
        
        with col2:
            if st.button("📊 System Health Check", key="dev_health_check"):
                try:
                    conn = get_connection()
                    
                    # Check database integrity
                    tables = ["companies", "system_settings", "inventory", "vouchers", "payroll", "fixed_assets", "audit_logs"]
                    health_status = {}
                    
                    for table in tables:
                        try:
                            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                            health_status[table] = f"✅ OK ({count} records)"
                        except sqlite3.Error:
                            health_status[table] = "❌ Error"
                    
                    st.json(health_status)
                    conn.close()
                except sqlite3.Error as e:
                    st.error(f"Health check failed: {e}")
                    logger.error(f"Health check error: {e}")
                    
    else:
        # Regular User Interface
        st.sidebar.markdown(f"""
        <div style='background-color:#f0f2f6; padding:20px; border-radius:15px; border: 1px solid #d1d5db;'>
            <h2 style='margin-bottom:0;'>🏢 {u['name']}</h2>
            <p style='color:#6b7280;'>Role: <b>{u['role']}</b></p>
            <p style='color:#6b7280; font-size:12px;'>Session: Active</p>
        </div>
        """, unsafe_allow_html=True)
        
        menu = [
            "🏠 Dashboard", "POS (Point of Sale)", "Vouchers & Journals", "Chart of Accounts", 
            "Inventory & Stock", "Sales Invoicing", "Purchase Orders", 
            "Banking & Cash", "Accounts Receivable", "Accounts Payable", 
            "Taxation (VAT/NHIL)", "Ghana Payroll (SSNIT)", "Fixed Asset Register", 
            "Financial Intelligence", "System Audit Trail"
        ]
        
        if u['role'] == "Master Admin":
            menu.insert(1, "Company Setup")
        
        choice = st.sidebar.selectbox("Go to Module:", menu, key="v3_main_nav_dropdown")
        
        # Dashboard Module (NEW)
        if choice == "🏠 Dashboard":
            show_dashboard(u['key'], u['name'], u['role'])  # FIXED: Correct parameter passing
        
        # Comprehensive Mapping Logic
        elif choice == "Company Setup": show_company_setup(u['key'], u['name'], u['role'])
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
        try:
            conn = get_connection()
            log_audit_action(conn, u.get('key', 'SYSTEM'), u['role'], "User logout", "Authentication")
            conn.close()
        except:
            pass  # Don't fail logout if audit logging fails
        
        st.session_state.auth = False
        st.session_state.user = None
        st.session_state.login_attempts = 0
        st.rerun()

# Dashboard Module (NEW FUNCTION)
def show_dashboard(company_key, company_name, role):
    """Enhanced company dashboard with key metrics and insights."""
    st.header(f"📊 Business Dashboard: {company_name}")
    
    try:
        conn = get_connection()
        
        # Key Business Metrics
        col1, col2, col3, col4 = st.columns(4)
        
        # Total Inventory Value
        inv_val = conn.execute("SELECT SUM(qty * cost_price) FROM inventory WHERE company_key=?", (company_key,)).fetchone()[0] or 0
        col1.metric("Inventory Value", f"GHS {inv_val:.2f}")
        
        # Total Sales (Current Month)
        current_month = datetime.now().strftime('%Y-%m')
        month_sales = conn.execute("""SELECT SUM(credit) FROM vouchers 
                                    WHERE company_key=? AND v_type='Sales' 
                                    AND date LIKE ?""", (company_key, f"{current_month}%")).fetchone()[0] or 0
        col2.metric("Month Sales", f"GHS {month_sales:.2f}")
        
        # Total Employees
        emp_count = conn.execute("SELECT COUNT(DISTINCT emp_name) FROM payroll WHERE company_key=?", (company_key,)).fetchone()[0] or 0
        col3.metric("Employees", str(emp_count))
        
        # Fixed Assets Value
        fa_val = conn.execute("SELECT SUM(book_value) FROM fixed_assets WHERE company_key=?", (company_key,)).fetchone()[0] or 0
        col4.metric("Asset Value", f"GHS {fa_val:.2f}")
        
        st.markdown("---")
        
        # Recent Activity
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Recent Transactions")
            # FIXED: Use direct SQL instead of pd.read_sql
            recent_data = conn.execute("""SELECT date, v_type, narration, 
                                        CASE WHEN credit > 0 THEN credit ELSE debit END as amount
                                        FROM vouchers WHERE company_key=? 
                                        ORDER BY date DESC LIMIT 10""", (company_key,)).fetchall()
            
            if recent_data:
                # Convert to DataFrame manually
                recent_txns = pd.DataFrame(recent_data, columns=['Date', 'Type', 'Description', 'Amount'])
                st.dataframe(recent_txns, use_container_width=True)
            else:
                st.info("No recent transactions found.")
        
        with col2:
            st.subheader("📦 Low Stock Items")
            # FIXED: Use direct SQL instead of pd.read_sql
            low_stock_data = conn.execute("""SELECT item_name, qty, unit FROM inventory 
                                           WHERE company_key=? AND qty <= 10 
                                           ORDER BY qty ASC LIMIT 10""", (company_key,)).fetchall()
            
            if low_stock_data:
                low_stock = pd.DataFrame(low_stock_data, columns=['Item', 'Quantity', 'Unit'])
                st.dataframe(low_stock, use_container_width=True)
            else:
                st.success("All stock levels are adequate!")
        
        # Quick Actions
        st.subheader("⚡ Quick Actions")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("➕ New Sale", use_container_width=True):
                st.session_state.selected_module = "POS (Point of Sale)"
                st.rerun()
        
        with col2:
            if st.button("📦 Add Inventory", use_container_width=True):
                st.session_state.selected_module = "Inventory & Stock"
                st.rerun()
        
        with col3:
            if st.button("💰 Process Payroll", use_container_width=True):
                st.session_state.selected_module = "Ghana Payroll (SSNIT)"
                st.rerun()
        
        with col4:
            if st.button("📊 View Reports", use_container_width=True):
                st.session_state.selected_module = "Financial Intelligence"
                st.rerun()
        
        conn.close()
        
    except sqlite3.Error as e:
        st.error("Failed to load dashboard data")
        logger.error(f"Dashboard error: {e}")
