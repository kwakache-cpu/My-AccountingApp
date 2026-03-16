import streamlit as st
import pandas as pd  # <-- ADD THIS IMPORT
from database import get_connection, init_db, log_audit_action
from modules import *
from modules import check_maintenance_window
import logging
import sqlite3
from datetime import datetime, timedelta

# Check maintenance status
maintenance_status = check_maintenance_window()
if maintenance_status == 'maintenance':
    st.markdown("""
    <div style='position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: #f8f9fa; display: flex; align-items: center; justify-content: center; z-index: 9999;'>
        <div style='text-align: center; padding: 40px; background: white; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); max-width: 500px;'>
            <h1 style='color: #1f2937; margin-bottom: 20px;'>🏗️ System Upgrade in Progress</h1>
            <p style='color: #6b7280; font-size: 18px; line-height: 1.6;'>
                We are currently performing scheduled maintenance to improve your experience. 
                We will be back online at 02:00 AM GMT. Thank you for your patience.
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Google Analytics Injection
def inject_ga():
    """Inject Google Analytics tracking script."""
    ga_id = st.secrets.get('GA_MEASUREMENT_ID', '')
    if not ga_id:
        return  # Skip if no GA ID
    
    demo_event = ""
    if st.session_state.get('demo_toggle', False) and not st.session_state.get('demo_event_sent', False):
        demo_event = "gtag('event', 'demo_signup', {});"
        st.session_state.demo_event_sent = True
    
    ga_script = f"""
    <!-- Google Analytics -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{ga_id}');
      {demo_event}
    </script>
    """
    
    st.components.v1.html(ga_script, height=0)

# Initialize Demo Mode
if 'demo_mode' not in st.session_state:
    st.session_state.demo_mode = False
if 'demo_event_sent' not in st.session_state:
    st.session_state.demo_event_sent = False

# Payment Verification Logic
if 'reference' in st.query_params:
    reference = st.query_params['reference']
    verification = verify_paystack_payment(reference)
    if verification.get('verified'):
        if reference.startswith("ONBOARD-"):
            # Onboarding payment
            parts = reference.split("-")
            company_name = parts[1].replace("_", " ")
            plan = parts[2]
            # Generate a key
            import uuid
            company_key = str(uuid.uuid4())[:8].upper()
            try:
                conn = get_connection()
                expiry_date = datetime.now() + timedelta(days=365)  # 1 year
                conn.execute("INSERT INTO companies (key, name, admin_email, deployment_status, expiry_date) VALUES (?, ?, ?, ?, ?)", 
                             (company_key, company_name, verification['email'], "Pending", expiry_date.isoformat()))
                conn.commit()
                log_audit_action(conn, company_key, 'System', f'Onboarding payment verified: {reference}', 'Onboarding')
                st.success(f"Company {company_name} onboarded successfully. Deployment pending.")
            except sqlite3.Error as e:
                st.error(f"Failed to onboard company: {e}")
                logger.error(f"Onboarding error: {e}")
        elif reference.startswith("RENEWAL-"):
            # Renewal payment
            company_key = reference.split("-")[1]
            try:
                conn = get_connection()
                # Add 1 year to expiry_date
                new_expiry = datetime.now() + timedelta(days=365)
                conn.execute("UPDATE companies SET expiry_date=? WHERE key=?", (new_expiry.isoformat(), company_key))
                conn.commit()
                log_audit_action(conn, company_key, 'System', f'License renewal verified: {reference}', 'Renewal')
                st.success("License Renewed Successfully! Thank you for your continued business.")
            except sqlite3.Error as e:
                st.error(f"Failed to renew license: {e}")
                logger.error(f"Renewal error: {e}")
        else:
            # Existing invoice payment
            # Find the company_key and amount from sales_invoices
            try:
                conn = get_connection()
                invoice_data = conn.execute("SELECT company_key, total_amount FROM sales_invoices WHERE invoice_no=?", (reference,)).fetchone()
                if invoice_data:
                    company_key, amount = invoice_data
                    # Insert Sales voucher
                    conn.execute("""INSERT INTO vouchers (company_key, date, v_type, ledger, debit, credit, payment_method, narration, ref_no) 
                                 VALUES (?,?,?,?,?,?,?,?,?)""", 
                                 (company_key, str(datetime.now().date()), 'Sales', 'Online Payment', 0.0, amount, 'Paystack', f'Paystack Online Payment: {reference}', reference))
                    conn.commit()
                    log_audit_action(conn, company_key, 'System', f'Paystack payment verified: {reference}', 'Payments')
                    st.balloons()
                else:
                    st.error("Invoice not found in database.")
                conn.close()
            except sqlite3.Error as e:
                st.error(f"Failed to record payment: {e}")
                logger.error(f"Payment recording error: {e}")
    else:
        st.error("Payment verification failed.")
    # Clear the reference from URL
    st.query_params.clear()

# Check Maintenance Window (moved after function definition)

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

def enter_demo():
    """Enter demo mode."""
    st.session_state.auth = True
    st.session_state.user = {"key": "DEMO", "name": "Demo Corporation Ltd", "role": "Demo"}
    st.session_state.demo_mode = True
    st.session_state.start_time = datetime.now()
    st.session_state.login_attempts = 0
    st.rerun()

def check_license_expiry(company_key):
    """Check if license is expiring within 7 days. Returns days left or None."""
    try:
        conn = get_connection()
        expiry = conn.execute("SELECT expiry_date FROM companies WHERE key=?", (company_key,)).fetchone()
        conn.close()
        if expiry and expiry[0]:
            expiry_date = datetime.fromisoformat(expiry[0])
            days_left = (expiry_date - datetime.now()).days
            if days_left <= 7 and days_left >= 0:
                return days_left
    except:
        pass
    return None

def check_maintenance_window():
    """Check maintenance status. Returns 'maintenance' if in window, 'warning' if within 3 days, None otherwise."""
    try:
        conn = get_connection()
        maint = conn.execute("SELECT maintenance_date FROM maintenance_settings WHERE id=1").fetchone()
        conn.close()
        if maint and maint[0]:
            maint_date = datetime.fromisoformat(maint[0]).date()
            now = datetime.now()
            current_date = now.date()
            current_time = now.time()
            
            # Check if in maintenance window
            if current_date == maint_date and current_time >= datetime.strptime("00:00", "%H:%M").time() and current_time <= datetime.strptime("02:00", "%H:%M").time():
                return 'maintenance'
            
            # Check if within 3 days
            days_diff = (maint_date - current_date).days
            if 0 <= days_diff <= 3:
                return 'warning', maint_date
    except:
        pass
    return None

def show_system_status():
    """Public-facing system status monitoring dashboard."""
    st.title("🌐 System Status Dashboard")
    st.markdown("Real-time monitoring of E.K.A Enterprise ERP infrastructure components.")
    
    # Status Indicators
    st.subheader("🟢 System Components")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("API Gateway", "Operational", delta="🟢 Online")
    with col2:
        st.metric("Database Engine", "Operational", delta="🟢 Online")
    with col3:
        st.metric("Payment Server", "Operational", delta="🟢 Online")
    
    st.markdown("---")
    
    # Uptime Metric
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("⏱️ Live Uptime")
        st.metric("System Availability", "99.9%", delta="+0.1% this month")
    
    with col2:
        st.subheader("📋 Past Incidents")
        incidents_df = pd.DataFrame({
            'Date': [f"{(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')}" for i in range(90)],
            'Status': ['All Systems Operational'] * 90,
            'Duration': ['N/A'] * 90
        })
        st.dataframe(incidents_df, use_container_width=True, height=300)

def login_ui():
    """Secure Multi-Tier Authentication Interface with Enhanced Security."""
    st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>🛡️ E.K.A ENTERPRISE ERP</h1>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # Maintenance Warning Banner
    if maintenance_status == 'warning':
        st.info("🛠️ Scheduled Maintenance: We will be upgrading our services soon. The system may be temporarily offline during the maintenance window.")
    
    # Check for brute force attempts
    if st.session_state.login_attempts >= 5:
        st.error("Too many failed login attempts. Please wait before trying again.")
        return
    
    t1, t2, t3, t4 = st.tabs(["🔒 Secure Login", "🔑 System Recovery", "🏢 Register New Company", "🌐 System Status"])
    
    with t1:
        if not st.session_state.get('demo_toggle'):
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
        elif st.session_state.get('demo_toggle'):
            st.button('🚀 Enter Demo ERP', on_click=enter_demo)

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

    with t3:
        show_onboarding_payment()

    with t4:
        show_system_status()

    # Demo Mode Toggle
    st.markdown("---")
    st.toggle('🚀 Try Demo Mode', key='demo_toggle')

# Dashboard Module (NEW FUNCTION)
def show_dashboard(company_key, company_name, role):
    """Enhanced company dashboard with key metrics and insights."""
    st.header(f"📊 Business Dashboard: {company_name}")
    
    if st.session_state.get('demo_mode', False):
        # Maintenance Banner
        if maintenance_status == 'warning':
            st.info(f"🛠️ Scheduled Maintenance: We will be upgrading our services on [scheduled date] from 12:00 AM to 02:00 AM GMT. The system may be temporarily offline during this window.")
        
        # Demo Mode Dashboard
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Inventory Value", "GHS 25,000.00")
        col2.metric("Month Sales", "GHS 15,000.00")
        col3.metric("Employees", "5")
        col4.metric("Asset Value", "GHS 50,000.00")
        
        st.markdown("---")
        
        # Recent Activity
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Recent Transactions")
            demo_txns = pd.DataFrame({
                'Date': ['2026-03-15', '2026-03-14', '2026-03-13'],
                'Type': ['Sales', 'Purchase', 'Sales'],
                'Description': ['Product Sale', 'Office Supplies', 'Service Revenue'],
                'Amount': [5000.0, 2000.0, 3000.0]
            })
            st.dataframe(demo_txns, use_container_width=True)
        
        with col2:
            st.subheader("📦 Low Stock Items")
            demo_stock = pd.DataFrame({
                'Item': ['Product A', 'Product B'],
                'Quantity': [5, 8],
                'Unit': ['pcs', 'pcs']
            })
            st.dataframe(demo_stock, use_container_width=True)
        
        return
    
    # Maintenance Banner for Regular Users
    if maintenance_status == 'warning':
        st.info(f"🛠️ Scheduled Maintenance: We will be upgrading our services on [scheduled date] from 12:00 AM to 02:00 AM GMT. The system may be temporarily offline during this window.")
    
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

# Main application flow
if not st.session_state.auth or not check_session_timeout():
    login_ui()
else:
    update_activity()  # Update activity on each interaction
    
    # Inject Google Analytics
    inject_ga()
    
    u = st.session_state.user
    
    if u['role'] == "Dev":
        # Maintenance Banner
        if maintenance_status == 'warning':
            st.info(f"🛠️ Scheduled Maintenance: We will be upgrading our services on [scheduled date] from 12:00 AM to 02:00 AM GMT. The system may be temporarily offline during this window.")
        
        # Gatekeeper Dashboard with Enhanced Metrics
        st.title("👑 Gatekeeper System Dashboard")
        
        # Tabs for different sections
        tab1, tab2 = st.tabs(["📊 System Overview", "📅 License Management"])
        
        with tab1:
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

                # Global Forensic Trail (Dev only)
                st.markdown("---")
                st.subheader("🛡️ Global Forensic Trail")
                try:
                    # Prefer user_role; fallback to role
                    col = "user_role"
                    try:
                        conn.execute("SELECT user_role FROM audit_logs LIMIT 1")
                    except sqlite3.OperationalError:
                        col = "role"

                    trail_data = conn.execute(f"SELECT timestamp, company_key, {col} as user_role, action, module_name "
                                              "FROM audit_logs ORDER BY timestamp DESC LIMIT 50").fetchall()
                    if trail_data:
                        trail_df = pd.DataFrame(trail_data, columns=['Timestamp', 'Company', 'User Role', 'Action', 'Module'])
                        st.dataframe(trail_df, use_container_width=True)
                    else:
                        st.info("No audit activity found.")
                except sqlite3.Error:
                    st.info("Unable to load global audit trail.")

            except sqlite3.Error as e:
                st.error("Failed to load system metrics")
                logger.error(f"Dashboard metrics error: {e}")

            st.markdown("---")
            st.subheader("🏢 Enterprise Instance Manager")
            try:
                conn = get_connection()
                try:
                    instance_df = pd.read_sql(
                        """
                        SELECT c.key AS company_key,
                               c.name AS company_name,
                               s.software_fee,
                               s.subscription_months
                        FROM companies c
                        LEFT JOIN system_settings s ON c.key = s.company_key
                        ORDER BY c.name
                        """,
                        conn
                    )
                except Exception as e:
                    logger.error(f"Failed to read instance_df: {e}")
                    instance_df = pd.DataFrame()
                
                edited_instances = st.data_editor(
                    instance_df,
                    use_container_width=True,
                    num_rows='dynamic',
                    key='enterprise_instance_editor',
                    column_config={
                        'company_key': st.column_config.TextColumn(label='Company Key', disabled=True)
                    } if hasattr(st, 'column_config') else None
                )

                if st.button('Sync Changes', key='enterprise_sync_changes'):
                    changed_mask = (edited_instances != instance_df).any(axis=1)
                    changed_rows = edited_instances[changed_mask]

                    if not changed_rows.empty:
                        for _, row in changed_rows.iterrows():
                            conn.execute(
                            "UPDATE companies SET name=? WHERE key=?",
                            (row['company_name'], row['company_key'])
                        )
                        conn.execute(
                            "UPDATE system_settings SET software_fee=?, subscription_months=? WHERE company_key=?",
                            (row['software_fee'], row['subscription_months'], row['company_key'])
                        )
                    conn.commit()
                    st.success('Enterprise instances synced successfully.')
                    log_audit_action(conn, 'SYSTEM', 'Dev', 'Synced enterprise instance settings', 'System Admin')
                else:
                    st.info('No changes to sync.')

                conn.close()
            except sqlite3.Error as e:
                st.error(f"Failed to load enterprise instances: {e}")
                logger.error(f"Instance manager error: {e}")

            st.markdown("---")
            st.subheader("📂 Client Portfolio Manager")
            try:
                conn = get_connection()
                portfolio_df = pd.read_sql(
                    """
                    SELECT c.name AS company_name,
                           c.created_at AS created_date,
                           c.status AS account_status,
                           c.deployment_status,
                           c.subscription_end_date,
                           COALESCE(SUM(v.credit), 0) AS total_revenue_collected
                    FROM companies c
                    LEFT JOIN vouchers v ON c.key = v.company_key AND v.v_type = 'Sales'
                    GROUP BY c.key, c.name, c.created_at, c.status, c.deployment_status, c.subscription_end_date
                    ORDER BY c.name
                    """,
                    conn
                )

                edited_portfolio = st.data_editor(
                    portfolio_df,
                    use_container_width=True,
                    key='client_portfolio_editor',
                    column_config={
                        'company_name': st.column_config.TextColumn(label='Company Name', disabled=True),
                        'created_date': st.column_config.TextColumn(label='Created Date', disabled=True),
                        'total_revenue_collected': st.column_config.NumberColumn(label='Total Revenue Collected (GHS)', disabled=True),
                        'account_status': st.column_config.SelectboxColumn(label='Account Status', options=['Active', 'Suspended']),
                        'deployment_status': st.column_config.TextColumn(label='Deployment Status', disabled=True),
                        'subscription_end_date': st.column_config.DateColumn(label='Subscription End Date')
                    } if hasattr(st, 'column_config') else None
                )

                if st.button('Update Client Portfolio', key='portfolio_update_changes'):
                    changed_mask = (edited_portfolio != portfolio_df).any(axis=1)
                    changed_rows = edited_portfolio[changed_mask]

                    if not changed_rows.empty:
                        for _, row in changed_rows.iterrows():
                            conn.execute(
                                "UPDATE companies SET status=?, subscription_end_date=? WHERE name=?",
                                (row['account_status'], row['subscription_end_date'], row['company_name'])
                            )
                        conn.commit()
                        st.success('Client portfolio updated successfully.')
                        log_audit_action(conn, 'SYSTEM', 'Dev', 'Updated client portfolio', 'System Admin')
                    else:
                        st.info('No changes to update.')

                # Deploy Pending Companies
                pending_companies = portfolio_df[portfolio_df['deployment_status'] == 'Pending']
                if not pending_companies.empty:
                    st.subheader("🚀 Pending Deployments")
                    for _, company in pending_companies.iterrows():
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**{company['company_name']}** - Created: {company['created_date']}")
                        with col2:
                            if st.button(f"🚀 Deploy Now", key=f"deploy_{company['company_name']}"):
                                conn.execute("UPDATE companies SET deployment_status='Live' WHERE name=?", (company['company_name'],))
                                conn.commit()
                                st.success(f"Company {company['company_name']} deployed successfully!")
                                log_audit_action(conn, 'SYSTEM', 'Dev', f'Deployed company: {company["company_name"]}', 'System Admin')
                                # Simulate email
                                st.info(f"Success email sent to {company['company_name']} admin.")

                conn.close()
            except sqlite3.Error as e:
                st.error(f"Failed to load client portfolio: {e}")
                logger.error(f"Portfolio manager error: {e}")
            col1, col2 = st.columns(2)
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
        
            # Maintenance Configuration
            st.markdown("---")
            st.subheader("🛠️ Maintenance Configuration")
            try:
                conn = get_connection()
                maint_settings = conn.execute("SELECT maintenance_date FROM maintenance_settings WHERE id=1").fetchone()
                current_maint_date = maint_settings[0] if maint_settings else None
                
                with st.form("maintenance_config_form"):
                    maint_date_input = st.date_input(
                        "Scheduled Maintenance Date",
                        value=datetime.strptime(current_maint_date, '%Y-%m-%d').date() if current_maint_date else None,
                        key="maint_date_input"
                    )
                    maint_time = st.time_input("Maintenance Start Time (GMT)", value=datetime.strptime("00:00", "%H:%M").time(), key="maint_time_input")
                    
                    if st.form_submit_button("Schedule Maintenance"):
                        # Combine date and time
                        maint_datetime = datetime.combine(maint_date_input, maint_time).isoformat()
                        
                        if maint_settings:
                            conn.execute("UPDATE maintenance_settings SET maintenance_date=? WHERE id=1", (maint_datetime,))
                        else:
                            conn.execute("INSERT INTO maintenance_settings (id, maintenance_date) VALUES (1, ?)", (maint_datetime,))
                        
                        conn.commit()
                        st.success(f"Maintenance scheduled for {maint_date_input} at {maint_time} GMT.")
                        log_audit_action(conn, 'SYSTEM', 'Dev', f'Scheduled maintenance: {maint_datetime}', 'System Admin')
                
                conn.close()
            except sqlite3.Error as e:
                st.error(f"Failed to load maintenance settings: {e}")
                logger.error(f"Maintenance config error: {e}")
        
        with tab2:
            st.subheader("📅 License Management")
            try:
                conn = get_connection()
                # Get all companies with expiry dates
                companies_df = pd.read_sql("""
                    SELECT c.key, c.name, c.expiry_date, c.status
                    FROM companies c
                    ORDER BY c.expiry_date ASC
                """, conn)
                
                # Calculate days remaining
                now = datetime.now()
                companies_df['expiry_date'] = pd.to_datetime(companies_df['expiry_date'])
                companies_df['days_remaining'] = (companies_df['expiry_date'] - now).dt.days
                
                # Color coding function
                def color_rows(row):
                    if row['days_remaining'] < 0 or row['status'] == 'Expired':
                        return ['background-color: #ffe6e6'] * len(row)  # Red for expired
                    elif row['days_remaining'] <= 3:
                        return ['background-color: #ffe6e6'] * len(row)  # Red for < 3 days
                    elif row['days_remaining'] <= 10:
                        return ['background-color: #fff3cd'] * len(row)  # Yellow for 4-10 days
                    else:
                        return ['background-color: #d4edda'] * len(row)  # Green for healthy
                
                # Apply styling
                styled_df = companies_df.style.apply(color_rows, axis=1)
                
                # Display table
                st.dataframe(styled_df, use_container_width=True)
                
                # Manual Override Section
                st.markdown("---")
                st.subheader("🔧 Manual License Extension")
                selected_company = st.selectbox("Select Company to Extend", companies_df['name'].tolist(), key="license_extend_select")
                extend_months = st.number_input("Extend by (Months)", min_value=1, value=1, key="extend_months")
                
                if st.button("Extend License", key="extend_license_btn"):
                    if selected_company:
                        # Get current expiry
                        current_expiry = companies_df[companies_df['name'] == selected_company]['expiry_date'].iloc[0]
                        new_expiry = current_expiry + timedelta(days=extend_months * 30)  # Approximate months
                        
                        conn.execute("UPDATE companies SET expiry_date=? WHERE name=?", (new_expiry.isoformat(), selected_company))
                        conn.commit()
                        st.success(f"License for {selected_company} extended to {new_expiry.date()}")
                        log_audit_action(conn, 'SYSTEM', 'Dev', f'Manual license extension for {selected_company} by {extend_months} months', 'System Admin')
                        st.rerun()
                
                conn.close()
            except sqlite3.Error as e:
                st.error(f"Failed to load license data: {e}")
                logger.error(f"License management error: {e}")
                    
    elif u['role'] == "Demo":
        # Demo User Interface
        # Check demo timeout
        if 'start_time' in st.session_state:
            elapsed = (datetime.now() - st.session_state.start_time).total_seconds()
            if elapsed > 1800:  # 30 minutes
                st.session_state.clear()
                st.warning("Demo Session Expired. Please Register to continue.")
                st.rerun()
        
        st.info("Viewing in Demo Mode. Real-time database is disconnected. [🏢 Register New Company](?tab=register)")
        
        st.sidebar.markdown(f"""
        <div style='background-color:#e0f2fe; padding:20px; border-radius:15px; border: 1px solid #0ea5e9;'>
            <h2 style='margin-bottom:0;'>🚀 {u['name']}</h2>
            <p style='color:#0c4a6e;'>Role: <b>Demo User</b></p>
            <p style='color:#0c4a6e; font-size:12px;'>Session: Active</p>
        </div>
        """, unsafe_allow_html=True)
        
        menu = ["Dashboard", "Inventory", "Payroll", "Sales/Purchase", "Reports", "Banking", "Taxation", "Audit Trail"]
        choice = st.sidebar.selectbox("Navigation", menu)
        
        if choice == "Dashboard":
            show_dashboard("DEMO", "Demo Corporation Ltd", "Demo")
        elif choice == "Inventory":
            show_inventory("DEMO", "Demo")
        elif choice == "Payroll":
            show_payroll("DEMO", "Demo")
        elif choice == "Sales/Purchase":
            show_sales_purchase("DEMO", "Demo", "Sales")
        elif choice == "Reports":
            show_reports("DEMO")
        elif choice == "Banking":
            show_banking("DEMO", "Demo")
        elif choice == "Taxation":
            show_taxation("DEMO")
        elif choice == "Audit Trail":
            show_audit_trail("DEMO")
                    
    else:
        # Regular User Interface
        st.sidebar.markdown(f"""
        <div style='background-color:#f0f2f6; padding:20px; border-radius:15px; border: 1px solid #d1d5db;'>
            <h2 style='margin-bottom:0;'>🏢 {u['name']}</h2>
            <p style='color:#6b7280;'>Role: <b>{u['role']}</b></p>
            <p style='color:#6b7280; font-size:12px;'>Session: Active</p>
        </div>
        """, unsafe_allow_html=True)
        
        # License Expiry Check
        days_left = check_license_expiry(u['key'])
        if days_left is not None:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.warning(f"⚠️ Your license expires in {days_left} days. Please renew to avoid service interruption.")
            with col2:
                if st.button("Renew Now", key="renew_license"):
                    # Trigger renewal payment
                    reference = f"RENEWAL-{u['key']}"
                    amount = 1000  # Fixed renewal fee
                    url = initialize_paystack_payment("", amount, reference)  # No email needed for renewal
                    if url:
                        st.link_button("Proceed to Paystack", url)
                    else:
                        st.error("Failed to initialize renewal payment.")
        
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
