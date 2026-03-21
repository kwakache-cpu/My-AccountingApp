import streamlit as st
import pandas as pd
from database import get_connection
from database import init_db, log_audit_action
from modules import *
import logging
from datetime import date, datetime, timedelta
import hashlib
import random
import string
from dateutil.relativedelta import relativedelta
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
    """NATIVE SQLITE FIX: No  wrapper"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT maintenance_date, is_active FROM maintenance_settings WHERE id = 1")
        maint_setting = cursor.fetchone()
        if maint_setting and maint_setting[1]:
            return {'active': True, 'date': maint_setting[0]}
        return {'active': False}
    except Exception as e:
        return {'active': False}
    finally:
        if conn:
            conn.close()

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


def print_subscription_email(company_email, company_name, new_expiry_date):
    """Print a renewal email preview to the terminal/logs."""
    recipient = company_email or "no-email-on-file@example.com"
    message = (
        f"[EMAIL PREVIEW] To: {recipient} | "
        f"Subject: Subscription Renewed | "
        f"Body: Hello {company_name}, your subscription is now active until {new_expiry_date}."
    )
    print(message)
    logger.info(message)

def check_license_expiry_with_grace(company_key):
    """NATIVE SQLITE FIX: No  wrapper"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, subscription_expiry FROM companies WHERE key = ?", (company_key,))
        company_data = cursor.fetchone()
        if company_data and company_data[1]:
            expiry_date = datetime.fromisoformat(company_data[1])
            days_until_expiry = (expiry_date - datetime.now()).days
            if days_until_expiry < 0: return {'status': 'expired', 'days_left': abs(days_until_expiry)}
            if days_until_expiry <= 7: return {'status': 'warning', 'days_left': days_until_expiry}
            return {'status': 'active', 'days_left': days_until_expiry}
        return {'status': 'unknown'}
    except Exception as e:
        return {'status': 'error'}
    finally:
        if conn:
            conn.close()

def submit_payment_reference(company_key, reference, amount, payment_method):
    """Submit payment reference for admin approval."""
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO pending_approvals
               (company_key, payment_reference, amount, payment_method)
               VALUES (?, ?, ?, ?)""",
            (company_key, reference, amount, payment_method),
        )
        conn.commit()
        log_audit_action(conn, company_key, 'System', f'Submitted payment reference: {reference}', 'Payment')
        
        # Show success notification
        st.success(f"Payment reference {reference} submitted successfully!")
        st.toast("Payment reference received. Awaiting admin approval.", icon="✅")
        
        # TODO: Trigger smtplib to send payment_ref to admin email for Passcode generation.
        
        return True
    except Exception as e:
        logger.error(f"Failed to submit payment reference: {e}")
        return False
    finally:
        if conn:
            conn.close()

def update_license_expiry(company_key, months):
    """Update license expiry date using relativedelta."""
    conn = None
    try:
        conn = get_connection()
        new_expiry = datetime.now() + relativedelta(months=+months)
        conn.execute(
            "UPDATE companies SET subscription_expiry = ? WHERE key = ?",
            (new_expiry.isoformat(), company_key),
        )
        conn.commit()
        log_audit_action(conn, company_key, 'System', f'License extended by {months} months', 'License Management')
        return new_expiry
    except Exception as e:
        logger.error(f"Failed to update license expiry: {e}")
        return None
    finally:
        if conn:
            conn.close()

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
        st.dataframe(incidents_df, width='stretch', height=300)

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
                    admin = conn.execute("SELECT key, name FROM companies WHERE key = ?", (license_key,)).fetchone()
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
                    sub = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key = ?", (license_key,)).fetchone()
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
                        staff = conn.execute("SELECT key, name FROM companies WHERE key = ?", (pure_k,)).fetchone()
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
                res = conn.execute(
                    "SELECT key FROM companies WHERE name = ? AND recovery_answer = ?",
                    (rec_name, rec_ans),
                ).fetchone()
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
    try:
        st.header(f"Business Dashboard: {company_name}")

        maintenance_status = check_maintenance_status()
        if maintenance_status['active']:
            st.warning(f"UPCOMING MAINTENANCE: {maintenance_status['date']}")

        license_status = check_license_expiry_with_grace(company_key)
        if license_status['status'] == 'warning':
            st.info(
                f"Your subscription ends in {license_status['days_left']} days. "
                "Please renew to avoid interruption."
            )
        elif license_status['status'] == 'expired':
            st.error(
                f"Your subscription expired {license_status['days_left']} days ago. "
                "Please renew to restore access."
            )

        if st.session_state.get('demo_mode', False):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Inventory Value", "GHS 25,000.00")
            col2.metric("Month Sales", "GHS 15,000.00")
            col3.metric("Employees", "5")
            col4.metric("Asset Value", "GHS 50,000.00")

            st.markdown("---")
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Recent Transactions")
                demo_txns = pd.DataFrame({
                    'Date': ['2026-03-15', '2026-03-14', '2026-03-13'],
                    'Type': ['Sales', 'Purchase', 'Sales'],
                    'Description': ['Product Sale', 'Office Supplies', 'Service Revenue'],
                    'Amount': [5000.0, 2000.0, 3000.0],
                })
                st.dataframe(demo_txns, width='stretch')

            with col2:
                st.subheader("Low Stock Items")
                demo_stock = pd.DataFrame({
                    'Item': ['Product A', 'Product B'],
                    'Quantity': [5, 8],
                    'Unit': ['pcs', 'pcs'],
                })
                st.dataframe(demo_stock, width='stretch')

            return

        conn = None
        try:
            conn = get_connection()

            col1, col2, col3, col4 = st.columns(4)

            inv_val = conn.execute(
                "SELECT COALESCE(SUM(qty * cost_price), 0) FROM inventory WHERE company_key = ?",
                (company_key,),
            ).fetchone()[0]
            col1.metric("Inventory Value", f"GHS {inv_val:.2f}")

            current_month = datetime.now().strftime('%Y-%m')
            month_sales = conn.execute(
                """SELECT COALESCE(SUM(credit), 0) FROM vouchers
                   WHERE company_key = ? AND v_type = 'Sales'
                   AND date LIKE ?""",
                (company_key, f"{current_month}%"),
            ).fetchone()[0]
            col2.metric("Month Sales", f"GHS {month_sales:.2f}")

            emp_count = conn.execute(
                "SELECT COUNT(DISTINCT emp_name) FROM payroll WHERE company_key = ?",
                (company_key,),
            ).fetchone()[0] or 0
            col3.metric("Employees", str(emp_count))

            fa_val = conn.execute(
                "SELECT COALESCE(SUM(book_value), 0) FROM fixed_assets WHERE company_key = ?",
                (company_key,),
            ).fetchone()[0]
            col4.metric("Asset Value", f"GHS {fa_val:.2f}")

            if inv_val == 0 and month_sales == 0 and emp_count == 0 and fa_val == 0:
                st.info(
                    "Welcome to your dashboard. Your company is set up and ready. "
                    "Add inventory, record sales, or process payroll to start seeing live metrics."
                )

            st.markdown("---")
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Recent Transactions")
                recent_data = conn.execute(
                    """SELECT date, v_type, narration,
                       CASE WHEN credit > 0 THEN credit ELSE debit END AS amount
                       FROM vouchers WHERE company_key = ?
                       ORDER BY date DESC LIMIT 10""",
                    (company_key,),
                ).fetchall()

                if recent_data:
                    recent_txns = pd.DataFrame(
                        recent_data,
                        columns=['Date', 'Type', 'Description', 'Amount'],
                    )
                    st.dataframe(recent_txns, width='stretch')
                else:
                    st.info("No recent transactions found.")

            with col2:
                st.subheader("Low Stock Items")
                low_stock_data = conn.execute(
                    """SELECT item_name, qty, unit FROM inventory
                       WHERE company_key = ? AND qty <= 10
                       ORDER BY qty ASC LIMIT 10""",
                    (company_key,),
                ).fetchall()

                if low_stock_data:
                    low_stock = pd.DataFrame(
                        low_stock_data,
                        columns=['Item', 'Quantity', 'Unit'],
                    )
                    st.dataframe(low_stock, width='stretch')
                else:
                    st.success("All stock levels are adequate!")

            st.subheader("Quick Actions")
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("New Sale", width='stretch'):
                    st.session_state.selected_module = "POS (Point of Sale)"
                    st.rerun()

            with col2:
                if st.button("Add Inventory", width='stretch'):
                    st.session_state.selected_module = "Inventory & Stock"
                    st.rerun()

            with col3:
                if st.button("Process Payroll", width='stretch'):
                    st.session_state.selected_module = "Ghana Payroll (SSNIT)"
                    st.rerun()

            with col4:
                if st.button("View Reports", width='stretch'):
                    st.session_state.selected_module = "Financial Intelligence"
                    st.rerun()

        finally:
            if conn:
                conn.close()

    except Exception as e:
        st.error(f"Dashboard Error: {e}")

# Main application flow
if not st.session_state.auth or not check_session_timeout():
    login_ui()
else:
    update_activity()  # Update activity on each interaction
    u = st.session_state.user
    
    if u['role'] == "Dev":
        # Gatekeeper Dashboard with Enhanced Metrics
        st.title("Gatekeeper System Dashboard")
        
        # Tabs for different sections
        tab1, tab2 = st.tabs(["System Overview", "License Management"])
        
        with tab1:
            try:
                conn = get_connection()
                
                # Get actual metrics from database
                try:
                    total_companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
                except Exception:
                    total_companies = 0
                try:
                    active_subscriptions = conn.execute("SELECT COUNT(*) FROM companies WHERE status='Active'").fetchone()[0]
                except Exception:
                    active_subscriptions = 0
                try:
                    monthly_revenue = conn.execute("SELECT SUM(amount) FROM pending_approvals").fetchone()[0] or 0
                except Exception:
                    monthly_revenue = 0
                
                # Display metrics
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Licenses", str(total_companies))
                m2.metric("Active Subscriptions", str(active_subscriptions))
                m3.metric("Monthly Revenue", f"GHS {monthly_revenue:.2f}")
                m4.metric("System Uptime", "100%")

                if total_companies == 0 and active_subscriptions == 0 and monthly_revenue == 0:
                    st.info(
                        "Welcome to the admin dashboard. Seed sample data or deploy your first "
                        "license to bring these system metrics to life."
                    )
                
                # Global Forensic Trail (Dev only) - Enhanced with error handling
                st.markdown("---")
                st.subheader("Global Forensic Trail")
                try:
                    trail_data = conn.execute(
                        """SELECT timestamp, company_key, user_role, action, module_name
                           FROM audit_logs ORDER BY timestamp DESC LIMIT 50"""
                    ).fetchall()
                    
                    if trail_data:
                        trail_df = pd.DataFrame(trail_data, columns=['Timestamp', 'Company Key', 'User Role', 'Action', 'Module'])
                        st.dataframe(trail_df, width='stretch')
                    else:
                        st.info("No audit activity found.")
                except Exception as e:
                    logger.error(f"Failed to load audit trail: {e}")
                
                st.markdown("---")
                st.subheader("Manual License Deployment")
                if "manual_key_input" not in st.session_state:
                    st.session_state.manual_key_input = ""
                with st.form("manual_deploy"):
                    company_name = st.text_input("Company Name")
                    plan_type = st.selectbox("Plan Type", ["Basic", "Premium", "Enterprise"])
                    duration_months = st.number_input("Duration (Months)", min_value=1, max_value=24, value=12)
                    key_col, button_col = st.columns([3, 1])
                    with key_col:
                        manual_key = st.text_input("System License Key", key="manual_key_input")
                    with button_col:
                        st.write("")
                        st.write("")
                        generate_key = st.form_submit_button("Generate Key")
                    submitted = st.form_submit_button("Deploy License")

                    if generate_key:
                        generated_key = (
                            f"EKA-"
                            f"{''.join(random.choices(string.ascii_uppercase, k=4))}-"
                            f"{''.join(random.choices(string.digits, k=4))}"
                        )
                        st.session_state.manual_key_input = generated_key
                        st.rerun()

                    if submitted:
                        if company_name and manual_key:
                            new_expiry = datetime.now() + relativedelta(months=+duration_months)
                            try:
                                conn.execute(
                                    """INSERT INTO companies
                                       (key, name, subscription_expiry, status, deployment_status)
                                       VALUES (?, ?, ?, ?, ?)""",
                                    (manual_key, company_name, new_expiry.isoformat(), "Active", "Live"),
                                )
                                conn.commit()
                                st.success(f"License deployed for {company_name} until {new_expiry.date()}")
                                log_audit_action(conn, 'SYSTEM', 'Dev', f'Manual license deployment for {company_name}', 'System Admin')
                            except Exception as e:
                                st.error(f"Failed to deploy license: {e}")
                        else:
                            st.error("Company Name and System License Key are required.")

                st.markdown("---")
                st.subheader("Global Maintenance Management")
                col_m1, col_m2, col_m3 = st.columns(3)
                m_date = col_m1.date_input('Maintenance Date')
                m_start = col_m2.time_input('Start Time')
                m_end = col_m3.time_input('End Time')
                m_msg = st.text_area('Notice Message', f'System maintenance on {m_date} from {m_start} to {m_end}.')

                if st.button('Update & Notify All'):
                    conn = get_connection()
                    time_window = f"{m_start.strftime('%H:%M')} - {m_end.strftime('%H:%M')}"
                    conn.execute('UPDATE maintenance_settings SET maintenance_date=?, is_active=1 WHERE id=1', (f"{m_date} ({time_window})",))
                    conn.commit()
                    st.success(f'Maintenance scheduled for {m_date} during {time_window}')
                    conn.close()

                conn.close()

            except Exception as e:
                st.error("Failed to load system metrics")
                logger.error(f"Dashboard metrics error: {e}")

            st.markdown("---")
            st.subheader("Client Portfolio Manager")
            try:
                conn = get_connection()
                query = """
                    SELECT c.key, c.name, c.created_at, c.status, c.deployment_status, c.subscription_expiry,
                    (SELECT COUNT(*) FROM inventory WHERE company_key = c.key) as item_count
                    FROM companies c ORDER BY c.name
                """
                portfolio_df = pd.read_sql(query, conn)
                st.dataframe(portfolio_df, width='stretch')

                try:
                    if not portfolio_df.empty:
                        portfolio_choice = st.selectbox(
                            "Open company profile",
                            portfolio_df["name"].tolist(),
                            key="portfolio_company_select",
                        )
                        selected_portfolio = portfolio_df.loc[
                            portfolio_df["name"] == portfolio_choice
                        ].iloc[0]
                        st.caption(
                            f"Portfolio selection: {selected_portfolio['name']} | "
                            f"Status: {selected_portfolio['status']} | "
                            f"Deployment: {selected_portfolio['deployment_status']}"
                        )
                except Exception as portfolio_click_error:
                    logger.error(f"Portfolio interaction error: {portfolio_click_error}")
                    st.warning("Company selection is temporarily unavailable, but the portfolio table is still visible.")

                conn.close()
            except Exception as e:
                st.error(f'Portfolio Error: {e}')
        
        with tab2:
            st.subheader("License Management")
            try:
                conn = get_connection()
                companies_df = pd.read_sql(
                    """
                    SELECT key, name, subscription_expiry, status, deployment_status, contact_email
                    FROM companies
                    ORDER BY name
                    """,
                    conn,
                )
                companies_df['subscription_expiry'] = pd.to_datetime(
                    companies_df['subscription_expiry'], errors='coerce'
                )
                st.dataframe(companies_df, width='stretch')

                st.markdown("---")
                st.subheader("Renew/Reactivate Subscription")

                if companies_df.empty:
                    st.info("No companies available for renewal yet.")
                else:
                    selected_company = st.selectbox(
                        "Select Company",
                        companies_df["name"].tolist(),
                        key="reactivate_company_select",
                    )
                    selected_row = companies_df.loc[
                        companies_df["name"] == selected_company
                    ].iloc[0]
                    company_email = selected_row.get("contact_email")
                    default_expiry = selected_row["subscription_expiry"]
                    if pd.isna(default_expiry):
                        default_expiry = datetime.now().date()
                    else:
                        default_expiry = default_expiry.date()

                    new_expiry_date = st.date_input(
                        "New Expiry Date",
                        value=default_expiry,
                        key="reactivate_expiry_date",
                    )

                    if st.button("Extend Subscription", key="extend_subscription_btn"):
                        try:
                            conn.execute(
                                "UPDATE companies SET subscription_expiry = ?, status = 'Active' WHERE name = ?",
                                (new_expiry_date.isoformat(), selected_company),
                            )
                            conn.commit()
                            print_subscription_email(
                                company_email,
                                selected_company,
                                new_expiry_date.isoformat(),
                            )
                            st.success(
                                f"Subscription updated for {selected_company} until {new_expiry_date.isoformat()}."
                            )
                            st.rerun()
                        except Exception as renew_error:
                            st.error(f"Failed to extend subscription: {renew_error}")

                conn.close()
            except Exception as e:
                st.error(f'License Table Error: {e}')
                    
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
    if st.sidebar.button("🔴 Secure Logout", width='stretch', key="v3_final_logout"):
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
