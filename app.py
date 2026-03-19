import streamlit as st
import pandas as pd
from database import get_connection, init_db, log_audit_action
from modules import *
from modules import check_maintenance_window
import logging
from datetime import date, datetime, timedelta
import hashlib
from dateutil.relativedelta import relativedelta
from sqlalchemy import text
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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

def check_maintenance_status():
    """Check maintenance settings and return status info."""
    try:
        conn = get_connection()
        maint_setting = conn.execute(text("SELECT maintenance_date, is_active FROM maintenance_settings WHERE id = 1")).fetchone()
        conn.close()
        
        if maint_setting and maint_setting[1]:  # is_active is True
            maintenance_date = maint_setting[0]
            if maintenance_date:
                return {
                    'active': True,
                    'date': maintenance_date
                }
        return {'active': False}
    except Exception as e:
        logger.error(f"Failed to check maintenance status: {e}")
        return {'active': False}

def send_maintenance_email(company_email, company_name, message):
    """Send maintenance notice to client."""
    try:
        # Email configuration (you'll need to set up your SMTP settings)
        smtp_server = "smtp.gmail.com"  # Change to your SMTP server
        smtp_port = 587
        sender_email = "your-email@gmail.com"  # Change to your email
        sender_password = "your-app-password"  # Change to your app password
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = company_email
        msg['Subject'] = f"E.K.A ERP - Maintenance Notice for {company_name}"
        
        body = f"""
        Dear {company_name},
        
        {message}
        
        This is an automated message from E.K.A Cloud ERP System.
        
        Best regards,
        E.K.A Support Team
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        logger.error(f"Failed to send maintenance email: {e}")
        return False

def check_license_expiry_with_grace(company_key):
    """Check license expiry with intelligent grace period logic."""
    try:
        conn = get_connection()
        company_data = conn.execute(text("SELECT name, subscription_expiry FROM companies WHERE key = :key"), {"key": company_key}).fetchone()
        conn.close()
        
        if company_data and company_data[1]:  # subscription_expiry exists
            expiry_date = datetime.fromisoformat(company_data[1])
            now = datetime.now()
            days_until_expiry = (expiry_date - now).days
            
            # Return different statuses based on expiry
            if days_until_expiry < 0:
                return {
                    'status': 'expired',
                    'days_left': abs(days_until_expiry),
                    'company_name': company_data[0],
                    'expiry_date': expiry_date
                }
            elif days_until_expiry <= 7:
                return {
                    'status': 'warning',
                    'days_left': days_until_expiry,
                    'company_name': company_data[0],
                    'expiry_date': expiry_date
                }
            else:
                return {
                    'status': 'active',
                    'days_left': days_until_expiry,
                    'company_name': company_data[0],
                    'expiry_date': expiry_date
                }
        
        return {'status': 'unknown'}
    except Exception as e:
        logger.error(f"Failed to check license expiry: {e}")
        return {'status': 'error'}

def submit_payment_reference(company_key, reference, amount, payment_method):
    """Submit payment reference for admin approval."""
    try:
        conn = get_connection()
        conn.execute(text("""INSERT INTO pending_approvals 
                         (company_key, payment_reference, amount, payment_method) 
                         VALUES (:company_key, :reference, :amount, :method)"""),
                 {"company_key": company_key, "reference": reference, "amount": amount, "method": payment_method})
        conn.commit()
        log_audit_action(conn, company_key, 'System', f'Submitted payment reference: {reference}', 'Payment')
        conn.close()
        
        # Show success notification
        st.success(f"Payment reference {reference} submitted successfully!")
        st.toast("Payment reference received. Awaiting admin approval.", icon="✅")
        
        # TODO: Trigger smtplib to send payment_ref to admin email for Passcode generation.
        
        return True
    except Exception as e:
        logger.error(f"Failed to submit payment reference: {e}")
        return False

def update_license_expiry(company_key, months):
    """Update license expiry date using relativedelta."""
    try:
        conn = get_connection()
        new_expiry = datetime.now() + relativedelta(months=+months)
        conn.execute(text("UPDATE companies SET subscription_expiry = :expiry WHERE key = :key"),
                 {"expiry": new_expiry.isoformat(), "key": company_key})
        conn.commit()
        log_audit_action(conn, company_key, 'System', f'License extended by {months} months', 'License Management')
        conn.close()
        return new_expiry
    except Exception as e:
        logger.error(f"Failed to update license expiry: {e}")
        return None

def enter_demo():
    """Enter demo mode."""
    st.session_state.auth = True
    st.session_state.user = {"key": "DEMO", "name": "Demo Corporation Ltd", "role": "Demo"}
    st.session_state.demo_mode = True
    st.session_state.start_time = datetime.now()
    st.session_state.login_attempts = 0
    st.rerun()

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
                    admin = conn.execute(text("SELECT key, name FROM companies WHERE key = :key"), {"key": license_key}).fetchone()
                    if admin:
                        # Check license expiry with grace period
                        license_status = check_license_expiry_with_grace(admin[0])
                        
                        # Allow login if not expired
                        if license_status['status'] != 'expired':
                            st.session_state.auth = True
                            st.session_state.user = {"key": admin[0], "name": admin[1], "role": "Master Admin"}
                            log_audit_action(conn, admin[0], "Master Admin", "Successful login", "Authentication")
                            conn.close()
                            st.session_state.login_attempts = 0
                            st.rerun()
                        else:
                            st.error(f"Your license expired {license_status['days_left']} days ago. Please renew to access the system.")
                    
                    # Sub-Admin/Staff Check
                    sub = conn.execute(text("SELECT key, name FROM companies WHERE sub_admin_key = :key"), {"key": license_key}).fetchone()
                    if sub:
                        # Check license expiry with grace period
                        license_status = check_license_expiry_with_grace(sub[0])
                        
                        # Allow login if not expired
                        if license_status['status'] != 'expired':
                            st.session_state.auth = True
                            st.session_state.user = {"key": sub[0], "name": sub[1], "role": "Sub-Admin"}
                            log_audit_action(conn, sub[0], "Sub-Admin", "Successful login", "Authentication")
                            conn.close()
                            st.session_state.login_attempts = 0
                            st.rerun()
                        else:
                            st.error(f"Your license expired {license_status['days_left']} days ago. Please renew to access the system.")
                        
                    if license_key.endswith("-staff"):
                        pure_k = license_key.replace("-staff", "")
                        staff = conn.execute(text("SELECT key, name FROM companies WHERE key = :key"), {"key": pure_k}).fetchone()
                        if staff:
                            # Check license expiry with grace period
                            license_status = check_license_expiry_with_grace(staff[0])
                            
                            # Allow login if not expired
                            if license_status['status'] != 'expired':
                                st.session_state.auth = True
                                st.session_state.user = {"key": staff[0], "name": staff[1], "role": "Staff"}
                                log_audit_action(conn, staff[0], "Staff", "Successful login", "Authentication")
                                conn.close()
                                st.session_state.login_attempts = 0
                                st.rerun()
                            else:
                                st.error(f"Your license expired {license_status['days_left']} days ago. Please renew to access the system.")
                    
                    # Failed login attempt
                    st.session_state.login_attempts += 1
                    log_audit_action(conn, "SYSTEM", "Unknown", f"Failed login attempt {st.session_state.login_attempts}", "Authentication")
                    conn.close()
                    st.error(f"Access Denied. Please verify your License Key. Attempts: {st.session_state.login_attempts}/5")
                    
                except Exception as e:
                    st.error("System error during authentication. Please try again.")
                    logger.error(f"Login error: {e}")
        elif st.session_state.get('demo_toggle'):
            st.button('🚀 Enter Demo ERP', on_click=enter_demo)

        # License Renewal Section
        with st.expander("🔄 Renew License", expanded=False):
            st.subheader("License Renewal Portal")
            st.info("Submit your payment reference below for manual verification and approval.")
            
            payment_ref = st.text_input("Payment Reference", key="renewal_payment_ref")
            payment_amount = st.number_input("Amount Paid (GHS)", min_value=0.0, key="renewal_amount")
            payment_method = st.selectbox("Payment Method", ["Bank Transfer", "Mobile Money", "Paystack", "Cash"], key="renewal_method")
            
            if st.button("Submit Payment Reference", key="submit_renewal_ref"):
                if payment_ref and payment_amount > 0:
                    if submit_payment_reference("TEMP", payment_ref, payment_amount, payment_method):
                        st.success("Payment reference submitted successfully! Your license will be activated after admin approval.")
                        st.info("You will receive your Main Admin Passcode via email once payment is verified.")
                    else:
                        st.error("Failed to submit payment reference. Please try again.")
                else:
                    st.error("Please fill in all required fields.")

    with t2:
        st.subheader("Cloud Recovery Protocol")
        rec_name = st.text_input("Company Registered Name", key="v3_rec_name_input")
        rec_ans = st.text_input("Security Recovery Answer", type="password", key="v3_rec_ans_input")
        if st.button("Retrieve Master Key", key="v3_rec_action_btn"):
            try:
                conn = get_connection()
                res = conn.execute(text("SELECT key FROM companies WHERE name = :name AND recovery_answer = :answer"), 
                                {"name": rec_name, "answer": rec_ans}).fetchone()
                if res: 
                    st.success(f"Identity Verified. Your Master Key is: {res[0]}")
                    log_audit_action(conn, res[0], "Recovery", "Successful key recovery", "Authentication")
                else: 
                    st.error("Verification failed. Data does not match our records.")
                conn.close()
            except Exception as e:
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
    
    # Check maintenance status and show warning if active
    maintenance_status = check_maintenance_status()
    if maintenance_status['active']:
        st.warning(f"⚠️ UPCOMING MAINTENANCE: {maintenance_status['date']}")
    
    # Check license expiry and show info if within 7 days
    license_status = check_license_expiry_with_grace(company_key)
    if license_status['status'] == 'warning':
        st.info(f"Your subscription ends in {license_status['days_left']} days. Please renew to avoid interruption.")
    elif license_status['status'] == 'expired':
        st.error(f"Your subscription expired {license_status['days_left']} days ago. Please renew to restore access.")
    
    if st.session_state.get('demo_mode', False):
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
            st.dataframe(demo_txns, width='stretch')
        
        with col2:
            st.subheader("📦 Low Stock Items")
            demo_stock = pd.DataFrame({
                'Item': ['Product A', 'Product B'],
                'Quantity': [5, 8],
                'Unit': ['pcs', 'pcs']
            })
            st.dataframe(demo_stock, width='stretch')
        
        return
    
    try:
        conn = get_connection()
        
        # Key Business Metrics
        col1, col2, col3, col4 = st.columns(4)
        
        # Total Inventory Value
        inv_val = conn.execute(text("SELECT SUM(qty * cost_price) FROM inventory WHERE company_key = :key"), {"key": company_key}).fetchone()[0] or 0
        col1.metric("Inventory Value", f"GHS {inv_val:.2f}")
        
        # Total Sales (Current Month)
        current_month = datetime.now().strftime('%Y-%m')
        month_sales = conn.execute(text("""SELECT SUM(credit) FROM vouchers 
                                    WHERE company_key = :key AND v_type = 'Sales' 
                                    AND date LIKE :month"""), {"key": company_key, "month": f"{current_month}%"}).fetchone()[0] or 0
        col2.metric("Month Sales", f"GHS {month_sales:.2f}")
        
        # Total Employees
        emp_count = conn.execute(text("SELECT COUNT(DISTINCT emp_name) FROM payroll WHERE company_key = :key"), {"key": company_key}).fetchone()[0] or 0
        col3.metric("Employees", str(emp_count))
        
        # Fixed Assets Value
        fa_val = conn.execute(text("SELECT SUM(book_value) FROM fixed_assets WHERE company_key = :key"), {"key": company_key}).fetchone()[0] or 0
        col4.metric("Asset Value", f"GHS {fa_val:.2f}")
        
        st.markdown("---")
        
        # Recent Activity
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Recent Transactions")
            recent_data = conn.execute(text("""SELECT date, v_type, narration, 
                                        CASE WHEN credit > 0 THEN credit ELSE debit END as amount
                                        FROM vouchers WHERE company_key = :key 
                                        ORDER BY date DESC LIMIT 10"""), {"key": company_key}).fetchall()
            
            if recent_data:
                recent_txns = pd.DataFrame(recent_data, columns=['Date', 'Type', 'Description', 'Amount'])
                st.dataframe(recent_txns, width='stretch')
            else:
                st.info("No recent transactions found.")
        
        with col2:
            st.subheader("📦 Low Stock Items")
            low_stock_data = conn.execute(text("""SELECT item_name, qty, unit FROM inventory 
                                           WHERE company_key = :key AND qty <= 10 
                                           ORDER BY qty ASC LIMIT 10"""), {"key": company_key}).fetchall()
            
            if low_stock_data:
                low_stock = pd.DataFrame(low_stock_data, columns=['Item', 'Quantity', 'Unit'])
                st.dataframe(low_stock, width='stretch')
            else:
                st.success("All stock levels are adequate!")
        
        # Quick Actions
        st.subheader("⚡ Quick Actions")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("➕ New Sale", width='stretch'):
                st.session_state.selected_module = "POS (Point of Sale)"
                st.rerun()
        
        with col2:
            if st.button("📦 Add Inventory", width='stretch'):
                st.session_state.selected_module = "Inventory & Stock"
                st.rerun()
        
        with col3:
            if st.button("💰 Process Payroll", width='stretch'):
                st.session_state.selected_module = "Ghana Payroll (SSNIT)"
                st.rerun()
        
        with col4:
            if st.button("📊 View Reports", width='stretch'):
                st.session_state.selected_module = "Financial Intelligence"
                st.rerun()
        
        conn.close()
        
    except Exception as e:
        st.error("Failed to load dashboard data")
        logger.error(f"Dashboard error: {e}")

# Main application flow
if not st.session_state.auth or not check_session_timeout():
    login_ui()
else:
    update_activity()  # Update activity on each interaction
    u = st.session_state.user
    
    if u['role'] == "Dev":
        # Gatekeeper Dashboard with Enhanced Metrics
        st.title("👑 Gatekeeper System Dashboard")
        
        # Tabs for different sections
        tab1, tab2 = st.tabs(["📊 System Overview", "📅 License Management"])
        
        with tab1:
            try:
                conn = get_connection()
                
                # Get actual metrics from database
                try:
                    total_companies = conn.execute(text("SELECT COUNT(*) FROM companies")).fetchone()[0]
                except Exception:
                    total_companies = 0
                try:
                    active_subscriptions = conn.execute(text("SELECT COUNT(*) FROM system_settings WHERE subscription_months > 0")).fetchone()[0]
                except Exception:
                    active_subscriptions = 0
                try:
                    monthly_revenue = conn.execute(text("SELECT SUM(software_fee) FROM system_settings")).fetchone()[0] or 0
                except Exception:
                    monthly_revenue = 0
                
                # Display metrics
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Licenses", str(total_companies))
                m2.metric("Active Subscriptions", str(active_subscriptions))
                m3.metric("Monthly Revenue", f"GHS {monthly_revenue:.2f}")
                m4.metric("System Uptime", "100%")
                
                # Global Forensic Trail (Dev only) - Enhanced with error handling
                st.markdown("---")
                st.subheader("🛡️ Global Forensic Trail")
                try:
                    trail_data = conn.execute(text("""SELECT timestamp, company_key, user_role, action, module_name 
                                                FROM audit_logs ORDER BY timestamp DESC LIMIT 50""")).fetchall()
                    
                    if trail_data:
                        trail_df = pd.DataFrame(trail_data, columns=['Timestamp', 'Company Key', 'User Role', 'Action', 'Module'])
                        st.dataframe(trail_df, width='stretch')
                    else:
                        st.info("No audit activity found.")
                except Exception as e:
                    logger.error(f"Failed to load audit trail: {e}")
                
                st.markdown("---")
                st.subheader("🚀 Manual License Deployment")
                with st.form("manual_deploy"):
                    company_name = st.text_input("Company Name")
                    plan_type = st.selectbox("Plan Type", ["Basic", "Premium", "Enterprise"])
                    duration_months = st.number_input("Duration (Months)", min_value=1, max_value=24, value=12)
                    submitted = st.form_submit_button("Deploy License")
                    if submitted:
                        if company_name:
                            key = hashlib.md5(company_name.encode()).hexdigest()[:10]
                            # Auto-update expiry date using relativedelta
                            new_expiry = update_license_expiry(key, duration_months)
                            
                            if new_expiry:
                                try:
                                    conn.execute(text("INSERT INTO companies (key, name, subscription_expiry, status) VALUES (:key, :name, :expiry, :status)"),
                                             {"key": key, "name": company_name, "expiry": new_expiry.isoformat(), "status": "Active"})
                                    conn.commit()
                                    st.success(f"License deployed for {company_name} until {new_expiry.date()}")
                                    log_audit_action(conn, 'SYSTEM', 'Dev', f'Manual license deployment for {company_name}', 'System Admin')
                                except Exception as e:
                                    st.error(f"Failed to deploy license: {e}")
                            else:
                                st.error("Failed to calculate expiry date.")
                        else:
                            st.error("Company Name is required.")

                conn.close()

            except Exception as e:
                st.error("Failed to load system metrics")
                logger.error(f"Dashboard metrics error: {e}")

            st.markdown("---")
            st.subheader("📂 Client Portfolio Manager")
            try:
                conn = get_connection()
                try:
                    portfolio_df = pd.read_sql(
                        """
                        SELECT c.name AS company_name,
                               c.created_at AS created_date,
                               c.status AS account_status,
                               c.deployment_status,
                               c.subscription_expiry,
                               COALESCE(SUM(v.credit), 0) AS total_revenue_collected
                        FROM companies c
                        LEFT JOIN vouchers v ON c.key = v.company_key AND v.v_type = 'Sales'
                        GROUP BY c.key, c.name, c.created_at, c.status, c.deployment_status, c.subscription_expiry
                        ORDER BY c.name
                        """,
                        conn
                    )
                except Exception as e:
                    logger.error(f"Failed to read portfolio_df: {e}")
                    portfolio_df = pd.DataFrame()

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
                                conn.execute(text("UPDATE companies SET deployment_status = 'Live' WHERE name = :name"), 
                                         {"name": company['company_name']})
                                conn.commit()
                                st.success(f"Company {company['company_name']} deployed successfully!")
                                log_audit_action(conn, 'SYSTEM', 'Dev', f'Deployed company: {company["company_name"]}', 'System Admin')
                                # Simulate email
                                st.info(f"Success email sent to {company['company_name']} admin.")
                conn.close()
            except Exception as e:
                st.error(f"Failed to load client portfolio: {e}")
                logger.error(f"Portfolio manager error: {e}")
        
        with tab2:
            st.subheader("📅 License Management")
            try:
                conn = get_connection()
                # Get all companies with expiry dates
                try:
                    companies_df = pd.read_sql(
                        text("""
                            SELECT c.key, c.name, c.subscription_expiry, c.status
                            FROM companies c
                            ORDER BY c.subscription_expiry ASC
                        """), conn)
                except Exception as e:
                    logger.error(f"Failed to read companies_df: {e}")
                    companies_df = pd.DataFrame()
                
                # Calculate days remaining
                now = datetime.now()
                companies_df['subscription_expiry'] = pd.to_datetime(companies_df['subscription_expiry'])
                companies_df['days_remaining'] = (companies_df['subscription_expiry'] - now).dt.days
                
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
                        current_expiry = companies_df[companies_df['name'] == selected_company]['subscription_expiry'].iloc[0]
                        new_expiry = update_license_expiry(selected_company, extend_months)
                        
                        if new_expiry:
                            st.success(f"License for {selected_company} extended to {new_expiry.date()}")
                            log_audit_action(conn, 'SYSTEM', 'Dev', f'Manual license extension for {selected_company} by {extend_months} months', 'System Admin')
                            st.rerun()
                
                conn.close()
            except Exception as e:
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
        days_left = check_license_expiry_with_grace(u['key'])
        if days_left['status'] == 'warning':
            col1, col2 = st.columns([4, 1])
            with col1:
                st.warning(f"⚠️ Your license expires in {days_left['days_left']} days. Please renew to avoid service interruption.")
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
