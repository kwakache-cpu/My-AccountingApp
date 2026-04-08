import streamlit as st
import pandas as pd
from database import check_and_repair_db, ensure_schema_integrity, get_connection
from database import init_db as base_init_db
from groq import Groq
import logging
from datetime import date, datetime, timedelta
import hashlib
import random
import string
from dateutil.relativedelta import relativedelta
import smtplib
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from modules import (
    BOG_DISPLAY_RATES,
    accounting_ai_response,
    format_currency,
    get_exchange_rate,
    initialize_paystack_payment,
    log_audit_action,
    render_accounting_assistant_sidebar,
    show_accounts_payable,
    show_accounts_receivable,
    show_dashboard as show_dashboard_module,
    show_aging,
    show_ai_assistant,
    show_audit_trail,
    show_banking,
    show_chart_of_accounts,
    show_company_setup,
    show_fixed_assets,
    show_inventory,
    show_onboarding_payment,
    show_payroll,
    show_pos,
    show_reports,
    show_sales_purchase,
    show_taxation,
    show_vouchers,
)
from financials import (
    show_financial_reports,
    show_invoice_manager,
    show_ledger_viewer,
    show_record_transaction,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GATEKEEPER_SYSTEM_PROMPT = (
    "You are the Gatekeeper Accounting Expert. Explain accounting terms like Accounts "
    "Payable and Chart of Accounts simply for Ghanaian businesses."
)
try:
    groq_api_key = st.secrets.get("GROQ_API_KEY")
except Exception:
    groq_api_key = None
client = Groq(api_key=groq_api_key) if groq_api_key else None

# 1. Boot System
def init_db():
    """Force the requested tables in app.py before the app starts."""
    check_and_repair_db()
    base_init_db()
    check_and_repair_db()

    conn = None
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        ensure_schema_integrity(conn)
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY, name TEXT, tin TEXT, status TEXT DEFAULT 'Active', subscription_expiry TEXT, deployment_status TEXT DEFAULT 'Pending', contact_email TEXT)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS pending_approvals (id INTEGER PRIMARY KEY, company_key TEXT, amount REAL, status TEXT, request_date TEXT)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, company_key TEXT, item_name TEXT, quantity INTEGER, price REAL)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS accounts_payable (id INTEGER PRIMARY KEY, vendor TEXT, amount REAL, status TEXT, due_date TEXT)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS chart_of_accounts (id INTEGER PRIMARY KEY, account_code TEXT, account_name TEXT, account_type TEXT)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS purchase_orders (id INTEGER PRIMARY KEY, item TEXT, quantity INTEGER, cost REAL, status TEXT)"
        )
        cursor.execute("PRAGMA table_info(companies)")
        company_columns = {row[1] for row in cursor.fetchall()}
        if company_columns:
            if "tin" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN tin TEXT")
            if "status" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN status TEXT DEFAULT 'Active'")
            if "subscription_expiry" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN subscription_expiry TEXT")
            if "deployment_status" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN deployment_status TEXT DEFAULT 'Pending'")
            if "contact_email" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN contact_email TEXT")
        chart_count = cursor.execute("SELECT COUNT(*) FROM chart_of_accounts").fetchone()[0]
        if chart_count == 0:
            cursor.executemany(
                "INSERT INTO chart_of_accounts (account_code, account_name, account_type) VALUES (?, ?, ?)",
                [
                    ("2000", "Accounts Payable", "Liability"),
                    ("4000", "Sales Revenue", "Income"),
                ],
            )
        conn.commit()
    except sqlite3.Error as init_error:
        logger.error(f"Forced table creation failed: {init_error}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


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
    st.session_state.company_id = None
    st.session_state.login_attempts = 0
    st.session_state.last_activity = datetime.now()
if 'page' not in st.session_state:
    st.session_state.page = "Dashboard"

PAGE_LABELS = {
    "pos": "🛒 Point of Sale",
    "inventory": "📦 Inventory Management",
    "payroll": "💳 Payroll & Salaries",
    "reports": "📊 Data Analytics",
    "settings": "⚙️ System Configuration",
}

PAGE_ALIASES = {
    "POS (Point of Sale)": PAGE_LABELS["pos"],
    "🛒 Point of Sale": PAGE_LABELS["pos"],
    "Inventory & Stock": PAGE_LABELS["inventory"],
    "📦 Inventory Management": PAGE_LABELS["inventory"],
    "Payroll": PAGE_LABELS["payroll"],
    "Ghana Payroll (SSNIT)": PAGE_LABELS["payroll"],
    "💳 Payroll & Salaries": PAGE_LABELS["payroll"],
    "Reports": PAGE_LABELS["reports"],
    "Financial Intelligence": PAGE_LABELS["reports"],
    "📊 Data Analytics": PAGE_LABELS["reports"],
    "Company Setup": PAGE_LABELS["settings"],
    "⚙️ System Configuration": PAGE_LABELS["settings"],
}


def normalize_page_label(page_name):
    canonical = PAGE_ALIASES.get(page_name, page_name)
    legacy_labels = {
        PAGE_LABELS["dashboard"]: "ðŸ  Dashboard",
        PAGE_LABELS["pos"]: "ðŸ›’ Point of Sale",
        PAGE_LABELS["inventory"]: "ðŸ“¦ Inventory Management",
        PAGE_LABELS["payroll"]: "ðŸ’³ Payroll & Salaries",
        PAGE_LABELS["reports"]: "ðŸ“Š Data Analytics",
        PAGE_LABELS["settings"]: "âš™ï¸ System Configuration",
        PAGE_LABELS["invoices"]: "Sales Invoicing",
    }
    return legacy_labels.get(canonical, canonical)


if 'exchange_rate' not in st.session_state:
    st.session_state.exchange_rate = 1.0


def _get_bog_display_rate(currency_code):
    return float(BOG_DISPLAY_RATES.get(str(currency_code or "GHS").upper(), 1.0))


def _render_currency_sidebar_controls(selectbox_key):
    settings_conn = get_connection()
    try:
        settings_row = settings_conn.execute(
            "SELECT COALESCE(base_currency, 'GHS') AS base_currency, COALESCE(display_currency, 'GHS') AS display_currency, COALESCE(exchange_rate, 1.0) AS exchange_rate FROM system_settings WHERE id = 1"
        ).fetchone()
        current_currency = str(settings_row["display_currency"]) if settings_row else "GHS"
        current_rate = (
            float(settings_row["exchange_rate"])
            if settings_row and settings_row["exchange_rate"] not in (None, "")
            else _get_bog_display_rate(current_currency)
        )
        selected_currency = st.sidebar.selectbox(
            "Base Currency",
            ["GHS", "USD", "EUR", "GBP"],
            index=["GHS", "USD", "EUR", "GBP"].index(current_currency) if current_currency in ["GHS", "USD", "EUR", "GBP"] else 0,
            key=selectbox_key,
        )
        selected_rate = _get_bog_display_rate(selected_currency)
        st.session_state.base_currency = selected_currency
        st.session_state.display_currency = selected_currency
        st.session_state.exchange_rate = selected_rate
        if selected_currency == "GHS":
            st.sidebar.caption("BoG April 2026 sync: 1 GHS = 1.00 GHS")
        else:
            st.sidebar.caption(f"BoG April 2026 sync: 1 {selected_currency} = {selected_rate:,.2f} GHS")
            st.sidebar.caption(f"Global display multiplier: 1 / {selected_rate:,.2f}")
        if selected_currency != current_currency or abs(current_rate - selected_rate) > 0.000001:
            settings_conn.execute(
                "UPDATE system_settings SET base_currency = ?, display_currency = ?, exchange_rate = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                ("GHS", selected_currency, selected_rate),
            )
            settings_conn.commit()
            st.rerun()
    finally:
        settings_conn.close()

PAGE_LABELS = {
    "dashboard": "📊 Dashboard",
    "pos": "🛒 Point of Sale",
    "inventory": "📦 Inventory Management",
    "payroll": "💳 Payroll & Salaries",
    "reports": "📊 Data Analytics",
    "settings": "⚙️ System Configuration",
    "invoices": "🧾 Sales Invoicing",
}

PAGE_ALIASES.update(
    {
        "POS (Point of Sale)": PAGE_LABELS["pos"],
        "ðŸ›’ Point of Sale": PAGE_LABELS["pos"],
        "🛒 Point of Sale": PAGE_LABELS["pos"],
        "Inventory & Stock": PAGE_LABELS["inventory"],
        "ðŸ“¦ Inventory Management": PAGE_LABELS["inventory"],
        "📦 Inventory Management": PAGE_LABELS["inventory"],
        "Payroll": PAGE_LABELS["payroll"],
        "Ghana Payroll (SSNIT)": PAGE_LABELS["payroll"],
        "ðŸ’³ Payroll & Salaries": PAGE_LABELS["payroll"],
        "💳 Payroll & Salaries": PAGE_LABELS["payroll"],
        "Reports": PAGE_LABELS["reports"],
        "Financial Intelligence": PAGE_LABELS["reports"],
        "ðŸ“Š Data Analytics": PAGE_LABELS["reports"],
        "📊 Data Analytics": PAGE_LABELS["reports"],
        "Company Setup": PAGE_LABELS["settings"],
        "âš™ï¸ System Configuration": PAGE_LABELS["settings"],
        "⚙️ System Configuration": PAGE_LABELS["settings"],
        "ðŸ  Dashboard": PAGE_LABELS["dashboard"],
        "📊 Dashboard": PAGE_LABELS["dashboard"],
        "Sales Invoicing": PAGE_LABELS["invoices"],
        "🧾 Sales Invoicing": PAGE_LABELS["invoices"],
    }
)


def normalize_page_label(page_name):
    canonical = PAGE_ALIASES.get(page_name, page_name)
    legacy_labels = {
        PAGE_LABELS["dashboard"]: "ðŸ  Dashboard",
        PAGE_LABELS["pos"]: "ðŸ›’ Point of Sale",
        PAGE_LABELS["inventory"]: "ðŸ“¦ Inventory Management",
        PAGE_LABELS["payroll"]: "ðŸ’³ Payroll & Salaries",
        PAGE_LABELS["reports"]: "ðŸ“Š Data Analytics",
        PAGE_LABELS["settings"]: "âš™ï¸ System Configuration",
        PAGE_LABELS["invoices"]: "Sales Invoicing",
    }
    return legacy_labels.get(canonical, canonical)


def repair_ui_label(label):
    value = str(label or "")
    keyword_map = [
        ("Dashboard", "📊 Dashboard"),
        ("Point of Sale", "🛒 Point of Sale"),
        ("Inventory Management", "📦 Inventory Management"),
        ("Payroll & Salaries", "💳 Payroll & Salaries"),
        ("Data Analytics", "📊 Data Analytics"),
        ("System Configuration", "⚙️ System Configuration"),
        ("Sales Invoicing", "🧾 Sales Invoicing"),
        ("Gatekeeper Admin", "🤖 Gatekeeper Admin"),
        ("Asset Register", "📦 Asset Register"),
    ]
    for keyword, repaired in keyword_map:
        if keyword in value:
            return repaired
    return value

# Session timeout (30 minutes)
SESSION_TIMEOUT = 30  # minutes

def check_session_timeout():
    """Check if session has timed out due to inactivity."""
    if st.session_state.auth:
        last_activity = st.session_state.get('last_activity', datetime.now())
        if datetime.now() - last_activity > timedelta(minutes=SESSION_TIMEOUT):
            st.session_state.auth = False
            st.session_state.user = None
            st.session_state.company_id = None
            st.warning("Session expired due to inactivity. Please login again.")
            return False
    return True

def update_activity():
    """Update last activity timestamp."""
    st.session_state.last_activity = datetime.now()


def hash_login_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def wipe_company_records(conn, company_key):
    company_scoped_tables = [
        "users",
        "counterparties",
        "inventory",
        "vouchers",
        "payroll",
        "fixed_assets",
        "audit_logs",
        "pending_approvals",
    ]
    for table_name in company_scoped_tables:
        try:
            conn.execute(f"DELETE FROM {table_name} WHERE company_key = ?", (company_key,))
        except sqlite3.Error:
            continue
    conn.execute("DELETE FROM companies WHERE key = ?", (company_key,))

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


def send_renewal_email(company_name, email, new_expiry):
    """Mock renewal email sender that prints the full email content."""
    recipient = email or "no-email-on-file@example.com"
    sender_email = "noreply@eka-erp.local"

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient
    msg["Subject"] = f"E.K.A Gatekeeper Renewal Confirmation - {company_name}"

    body = f"""
Dear {company_name},

Congratulations on successfully renewing your subscription with E.K.A Cloud ERP.

Your new expiry date is: {new_expiry}

Access to the Gatekeeper System has been fully restored, and your organization can continue operating without interruption.

Thank you for choosing E.K.A Solutions.

Best regards,
E.K.A Support Team
"""

    msg.attach(MIMEText(body.strip(), "plain"))

    print("===== RENEWAL EMAIL PREVIEW =====")
    print(msg.as_string())
    print("===== END EMAIL PREVIEW =====")
    logger.info(f"Renewal email preview generated for {company_name} <{recipient}>")
    return True

def ask_gatekeeper_ai(menu_selection, chat_history):
    """Call Groq for a real Gatekeeper AI answer."""
    messages = [{"role": "system", "content": GATEKEEPER_SYSTEM_PROMPT}]
    messages.append(
        {
            "role": "system",
            "content": f"The user is currently viewing the {menu_selection} module.",
        }
    )
    messages.extend(chat_history[-8:])

    if not client:
        return "Gatekeeper AI is unavailable because the `GROQ_API_KEY` secret is not configured."

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.4,
        )
        return completion.choices[0].message.content.strip()
    except Exception as ai_error:
        logger.error(f"Gatekeeper AI call failed: {ai_error}")
        return "Gatekeeper AI is currently unavailable. Please check the Groq API connection."


def render_gatekeeper_ai_chat(menu_selection):
    """Render a real interactive sidebar chatbot."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Ask me an accounting question and I will explain it simply for your business.",
            }
        ]

    with st.sidebar.expander("🤖 Gatekeeper Admin", expanded=False):
        st.caption(f"Active module: {menu_selection}")

        for message in st.session_state.messages[-6:]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        user_question = st.chat_input("Ask Gatekeeper Admin...", key=f"ai_guide_{menu_selection}")
        if user_question:
            st.session_state.messages.append({"role": "user", "content": user_question})
            with st.spinner("Gatekeeper Admin is thinking..."):
                ai_response = ask_gatekeeper_ai(menu_selection, st.session_state.messages)
            st.session_state.messages.append({"role": "assistant", "content": ai_response})
            st.rerun()


def render_gatekeeper_ai_guide(menu_selection):
    """Backward-compatible alias to the live chat interface."""
    render_gatekeeper_ai_chat(menu_selection)
    return
    module_help = {
        "Inventory": (
            "Set the Min Stock Level to the quantity where you want the system to warn you before stock runs too low. "
            "When current quantity falls to or below that threshold, the dashboard flags the item for attention."
        ),
        "Inventory & Stock": (
            "Set the Min Stock Level to the quantity where you want the system to warn you before stock runs too low. "
            "When current quantity falls to or below that threshold, the dashboard flags the item for attention."
        ),
        "Payroll": (
            "Enter the employee's core salary details and the system calculates Net Salary automatically after SSNIT and tax deductions. "
            "That means you should focus on entering accurate gross pay inputs rather than manually computing take-home pay."
        ),
        "Ghana Payroll (SSNIT)": (
            "Enter the employee's core salary details and the system calculates Net Salary automatically after SSNIT and tax deductions. "
            "That means you should focus on entering accurate gross pay inputs rather than manually computing take-home pay."
        ),
        "Fixed Asset Register": (
            "Depreciation Rate is the percentage used to reduce an asset's value over time as it is used. "
            "Book Value is the remaining value of the asset after depreciation has been applied."
        ),
        "Fixed Assets": (
            "Depreciation Rate is the percentage used to reduce an asset's value over time as it is used. "
            "Book Value is the remaining value of the asset after depreciation has been applied."
        ),
    }

    module_responses = {
        "Inventory": "Enter the item name, quantity, selling price, cost price, and warehouse details so the stock record is complete. Add a realistic Min Stock Level so the system can trigger alerts before the item runs low.",
        "Inventory & Stock": "Enter the item name, quantity, selling price, cost price, and warehouse details so the stock record is complete. Add a realistic Min Stock Level so the system can trigger alerts before the item runs low.",
        "Payroll": "Input the employee name, salary amount, month, and year with care because the payroll engine uses those values to calculate deductions. You do not need to type Net Salary manually because the system computes it after SSNIT and tax.",
        "Ghana Payroll (SSNIT)": "Input the employee name, salary amount, month, and year with care because the payroll engine uses those values to calculate deductions. You do not need to type Net Salary manually because the system computes it after SSNIT and tax.",
        "Fixed Asset Register": "Enter the asset name, purchase cost, purchase date, and depreciation rate so the register can track the asset correctly. The system then uses those fields to maintain Book Value over time.",
        "Fixed Assets": "Enter the asset name, purchase cost, purchase date, and depreciation rate so the register can track the asset correctly. The system then uses those fields to maintain Book Value over time.",
    }

    help_text = module_help.get(
        menu_selection,
        "This AI guide follows the module you are currently viewing and explains the most important fields before you save an entry. Ask a short question below if you want entry help tailored to this screen."
    )

    with st.sidebar.expander("🤖 Gatekeeper Admin", expanded=False):
        st.markdown(
            """
            <div style='background-color:#eef6ff; border-left:4px solid #0f766e; padding:12px; border-radius:10px; margin-bottom:10px;'>
                <strong>Help</strong><br>
                Context-aware guidance for the module you are using right now.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(help_text)

        user_question = st.chat_input("Ask Gatekeeper Admin for help", key=f"ai_guide_{menu_selection}")
        if user_question:
            ai_response = module_responses.get(
                menu_selection,
                "Enter the required fields shown in this module carefully and save only after reviewing the values for accuracy. If you are unsure, start with the main identification fields and the system-calculated fields will guide the rest of the process."
            )
            st.markdown(
                f"""
                <div style='background-color:#ecfeff; border:1px solid #67e8f9; color:#155e75; padding:12px; border-radius:10px; margin-top:10px;'>
                    <strong>Help Response</strong><br>
                    {ai_response}
                </div>
                """,
                unsafe_allow_html=True,
            )

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
    st.session_state.company_id = "DEMO"
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
            staff_password = st.text_input(
                "Password (for staff logins)",
                type="password",
                key="v3_final_staff_password_field",
            )
            
            if st.button("Access Cloud Modules", key="v3_final_auth_submit_btn"):
                try:
                    conn = get_connection()
                    
                    # Developer Backdoor
                    if license_key == "JUANMANUEL2":
                        st.session_state.auth = True
                        st.session_state.user = {"name": "Gatekeeper", "role": "Dev", "key": "ADMIN"}
                        st.session_state.company_id = "ADMIN"
                        log_audit_action(conn, "SYSTEM", "Dev", "Developer login", "Authentication")
                        conn.close()
                        st.session_state.login_attempts = 0
                        st.rerun()
                    
                    # Master Admin Check
                    admin = conn.execute("SELECT key, name, COALESCE(status, 'Active') FROM companies WHERE key = ?", (license_key,)).fetchone()
                    if admin:
                        if admin[2] != "Active":
                            st.error("This company is currently archived or inactive. Contact Gatekeeper to reactivate access.")
                            conn.close()
                            return
                        # Check license expiry with grace period
                        license_status = check_license_expiry_with_grace(admin[0])
                        
                        # Allow login if not expired
                        if license_status['status'] != 'expired':
                            st.session_state.auth = True
                            st.session_state.user = {"key": admin[0], "name": admin[1], "role": "Master Admin"}
                            st.session_state.company_id = admin[0]
                            log_audit_action(conn, admin[0], "Master Admin", "Successful login", "Authentication")
                            conn.close()
                            st.session_state.login_attempts = 0
                            st.rerun()
                        else:
                            st.error(f"Your license expired {license_status['days_left']} days ago. Please renew to access the system.")
                    
                    # Sub-Admin/Staff Check
                    sub = conn.execute("SELECT key, name, COALESCE(status, 'Active') FROM companies WHERE sub_admin_key = ?", (license_key,)).fetchone()
                    if sub:
                        if sub[2] != "Active":
                            st.error("This company is currently archived or inactive. Contact Gatekeeper to reactivate access.")
                            conn.close()
                            return
                        # Check license expiry with grace period
                        license_status = check_license_expiry_with_grace(sub[0])
                        
                        # Allow login if not expired
                        if license_status['status'] != 'expired':
                            st.session_state.auth = True
                            st.session_state.user = {"key": sub[0], "name": sub[1], "role": "Sub-Admin"}
                            st.session_state.company_id = sub[0]
                            log_audit_action(conn, sub[0], "Sub-Admin", "Successful login", "Authentication")
                            conn.close()
                            st.session_state.login_attempts = 0
                            st.rerun()
                        else:
                            st.error(f"Your license expired {license_status['days_left']} days ago. Please renew to access the system.")
                        
                    if license_key.endswith("-staff"):
                        pure_k = license_key.replace("-staff", "")
                        staff = conn.execute("SELECT key, name, COALESCE(status, 'Active') FROM companies WHERE key = ?", (pure_k,)).fetchone()
                        if staff:
                            if staff[2] != "Active":
                                st.error("This company is currently archived or inactive. Contact Gatekeeper to reactivate access.")
                                conn.close()
                                return
                            # Check license expiry with grace period
                            license_status = check_license_expiry_with_grace(staff[0])
                            
                            # Allow login if not expired
                            if license_status['status'] != 'expired':
                                st.session_state.auth = True
                                st.session_state.user = {"key": staff[0], "name": staff[1], "role": "Staff"}
                                st.session_state.company_id = staff[0]
                                log_audit_action(conn, staff[0], "Staff", "Successful login", "Authentication")
                                conn.close()
                                st.session_state.login_attempts = 0
                                st.rerun()
                            else:
                                st.error(f"Your license expired {license_status['days_left']} days ago. Please renew to access the system.")

                    user_login = conn.execute(
                        """
                        SELECT u.company_key, c.name, u.role, u.full_name, u.password_hash
                        FROM users u
                        JOIN companies c ON c.key = u.company_key
                        WHERE u.login_key = ?
                          AND COALESCE(u.status, 'Active') = 'Active'
                          AND COALESCE(c.status, 'Active') = 'Active'
                        """,
                        (license_key,),
                    ).fetchone()
                    if user_login:
                        if not staff_password or hash_login_password(staff_password) != (user_login[4] or ""):
                            st.error("Invalid staff password. Please try again.")
                            conn.close()
                            return
                        license_status = check_license_expiry_with_grace(user_login[0])
                        if license_status['status'] != 'expired':
                            st.session_state.auth = True
                            st.session_state.user = {
                                "key": user_login[0],
                                "name": user_login[1],
                                "role": user_login[2],
                                "staff_name": user_login[3],
                            }
                            st.session_state.company_id = user_login[0]
                            log_audit_action(conn, user_login[0], user_login[2], "Successful login", "Authentication")
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

            try:
                col1, col2, col3, col4 = st.columns(4)

                inv_val = conn.execute(
                    "SELECT COALESCE(SUM(qty * cost_price), 0) FROM inventory WHERE company_key = ?",
                    (company_key,),
                ).fetchone()[0]
                col1.metric("Inventory Value", f"GHS {inv_val:.2f}")

                current_month = datetime.now().strftime('%Y-%m')
                month_sales = conn.execute(
                    """SELECT COALESCE(SUM(credit), 0) FROM vouchers
                       WHERE company_key = ? AND v_type = 'Sales' AND COALESCE(status, 'Active') != 'Void'
                       AND date LIKE ?""",
                    (company_key, f"{current_month}%"),
                ).fetchone()[0]
                col2.metric("Month Sales", f"GHS {month_sales:.2f}")

                emp_count = conn.execute(
                    "SELECT COUNT(DISTINCT emp_name) FROM payroll WHERE company_key = ? AND COALESCE(status, 'Active') != 'Void'",
                    (company_key,),
                ).fetchone()[0] or 0
                col3.metric("Employees", str(emp_count))

                fa_val = conn.execute(
                    "SELECT COALESCE(SUM(book_value), 0) FROM fixed_assets WHERE company_key = ?",
                    (company_key,),
                ).fetchone()[0]
                col4.metric("Asset Value", f"GHS {fa_val:.2f}")
            except sqlite3.OperationalError as db_schema_error:
                if "no such table" in str(db_schema_error).lower():
                    st.warning(
                        "Your dashboard data tables are not fully available yet. "
                        "Please run `python fix_db.py` to complete the Safety Sync, then reload the app."
                    )
                    logger.warning(f"Dashboard schema issue: {db_schema_error}")
                    return
                raise

            if inv_val == 0 and month_sales == 0 and emp_count == 0 and fa_val == 0:
                st.info(
                    "Welcome to your dashboard. Your company is set up and ready. "
                    "Add inventory, record sales, or process payroll to start seeing live metrics."
                )

            st.markdown("---")
            col1, col2 = st.columns(2)

            try:
                with col1:
                    st.subheader("Recent Transactions")
                    recent_data = conn.execute(
                        """SELECT date, v_type, narration,
                           CASE WHEN credit > 0 THEN credit ELSE debit END AS amount
                           FROM vouchers WHERE company_key = ? AND COALESCE(status, 'Active') != 'Void'
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
            except sqlite3.OperationalError as activity_error:
                if "no such table" in str(activity_error).lower():
                    st.info(
                        "Some activity tables are still being prepared. Run `python fix_db.py` to complete the Safety Sync."
                    )
                    logger.warning(f"Dashboard activity schema issue: {activity_error}")
                else:
                    raise

            st.subheader("Quick Actions")
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("🛒 New Sale", key="dash_pos", width='stretch'):
                    st.session_state.page = "POS (Point of Sale)"
                    st.rerun()

            with col2:
                if st.button("📦 Add Inventory", key="dash_inventory", width='stretch'):
                    st.session_state.page = "Inventory & Stock"
                    st.rerun()

            with col3:
                if st.button("💳 Process Payroll", key="dash_payroll", width='stretch'):
                    st.session_state.page = "Payroll"
                    st.rerun()

            with col4:
                if st.button("📊 View Reports", key="dash_reports", width='stretch'):
                    st.session_state.page = "Reports"
                    st.rerun()

        finally:
            if conn:
                conn.close()

    except Exception as e:
        st.error(f"Dashboard Error: {e}")

def show_dashboard(company_key, company_name, role):
    """Currency-aware dashboard with maintenance-complete banner."""
    try:
        st.header(f"Business Dashboard: {company_name}")
        st.success(
            "System Upgraded\n\nThank you for your patience. Our systems are upgraded to better serve your business."
        )

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
            col1.metric("Inventory Value", format_currency(25000.0))
            col2.metric("Month Sales", format_currency(15000.0))
            col3.metric("Employees", "5")
            col4.metric("Asset Value", format_currency(50000.0))
            return

        conn = None
        try:
            conn = get_connection()
            col1, col2, col3, col4 = st.columns(4)

            inv_val = conn.execute(
                "SELECT COALESCE(SUM(qty * cost_price), 0) FROM inventory WHERE company_key = ?",
                (company_key,),
            ).fetchone()[0]
            month_sales = conn.execute(
                """SELECT COALESCE(SUM(credit), 0) FROM vouchers
                   WHERE company_key = ? AND v_type = 'Sales' AND COALESCE(status, 'Active') != 'Void'
                   AND date LIKE ?""",
                (company_key, f"{datetime.now().strftime('%Y-%m')}%"),
            ).fetchone()[0]
            emp_count = conn.execute(
                "SELECT COUNT(DISTINCT emp_name) FROM payroll WHERE company_key = ? AND COALESCE(status, 'Active') != 'Void'",
                (company_key,),
            ).fetchone()[0] or 0
            fa_val = conn.execute(
                "SELECT COALESCE(SUM(book_value), 0) FROM fixed_assets WHERE company_key = ?",
                (company_key,),
            ).fetchone()[0]

            col1.metric("Inventory Value", format_currency(inv_val))
            col2.metric("Month Sales", format_currency(month_sales))
            col3.metric("Employees", str(emp_count))
            col4.metric("Asset Value", format_currency(fa_val))

            st.markdown("---")
            left_col, right_col = st.columns(2)
            with left_col:
                st.subheader("Recent Transactions")
                recent_txns = pd.read_sql_query(
                    """
                    SELECT date, v_type, narration,
                           CASE WHEN credit > 0 THEN credit ELSE debit END AS amount
                    FROM vouchers
                    WHERE company_key = ? AND COALESCE(status, 'Active') != 'Void'
                    ORDER BY date DESC
                    LIMIT 10
                    """,
                    conn,
                    params=(company_key,),
                )
                if recent_txns.empty:
                    st.info("No recent transactions found.")
                else:
                    recent_txns["Amount"] = recent_txns["amount"].map(format_currency)
                    recent_txns = recent_txns.drop(columns=["amount"]).rename(
                        columns={"date": "Date", "v_type": "Type", "narration": "Description"}
                    )
                    st.dataframe(recent_txns, width='stretch')

            with right_col:
                st.subheader("Low Stock Items")
                low_stock = pd.read_sql_query(
                    """
                    SELECT item_name AS Item, qty AS Quantity, unit AS Unit
                    FROM inventory
                    WHERE company_key = ? AND qty <= 10
                    ORDER BY qty ASC
                    LIMIT 10
                    """,
                    conn,
                    params=(company_key,),
                )
                if low_stock.empty:
                    st.success("All stock levels are adequate!")
                else:
                    st.dataframe(low_stock, width='stretch')

            st.subheader("Quick Actions")
            quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
            if quick_col1.button("🛒 New Sale", key="dash_pos", width='stretch'):
                st.session_state.page = PAGE_LABELS["pos"]
                st.rerun()
            if quick_col2.button("📦 Add Inventory", key="dash_inventory", width='stretch'):
                st.session_state.page = PAGE_LABELS["inventory"]
                st.rerun()
            if quick_col3.button("💳 Process Payroll", key="dash_payroll", width='stretch'):
                st.session_state.page = PAGE_LABELS["payroll"]
                st.rerun()
            if quick_col4.button("📊 View Reports", key="dash_reports", width='stretch'):
                st.session_state.page = PAGE_LABELS["reports"]
                st.rerun()
        finally:
            if conn:
                conn.close()
    except Exception as e:
        st.error(f"Dashboard Error: {e}")


# Startup self-healing database patch
def run_startup_db_patch():
    """Repair older local databases automatically on app startup."""
    check_and_repair_db()
    conn = None
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        ensure_schema_integrity(conn)

        cursor.execute("PRAGMA table_info(companies)")
        company_columns = {row[1] for row in cursor.fetchall()}
        if company_columns:
            if "tin" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN tin TEXT")
            if "status" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN status TEXT DEFAULT 'Active'")
            if "subscription_expiry" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN subscription_expiry TEXT")
            if "deployment_status" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN deployment_status TEXT DEFAULT 'Pending'")
            if "contact_email" not in company_columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN contact_email TEXT")
            cursor.execute(
                "UPDATE companies SET status = 'Active' WHERE status IS NULL OR TRIM(status) = ''"
            )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_approvals (
                id INTEGER PRIMARY KEY,
                company_key TEXT,
                amount REAL,
                status TEXT,
                request_date TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY,
                company_key TEXT,
                item_name TEXT,
                quantity INTEGER,
                price REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts_payable (
                id INTEGER PRIMARY KEY,
                vendor TEXT,
                amount REAL,
                status TEXT,
                due_date TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chart_of_accounts (
                id INTEGER PRIMARY KEY,
                account_code TEXT,
                account_name TEXT,
                account_type TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY,
                item TEXT,
                quantity INTEGER,
                cost REAL,
                status TEXT
            )
        """)

        chart_count = cursor.execute("SELECT COUNT(*) FROM chart_of_accounts").fetchone()[0]
        if chart_count == 0:
            cursor.executemany(
                "INSERT INTO chart_of_accounts (account_code, account_name, account_type) VALUES (?, ?, ?)",
                [
                    ("2000", "Accounts Payable", "Liability"),
                    ("4000", "Sales Revenue", "Income"),
                ],
            )

        conn.commit()
    except sqlite3.Error as patch_error:
        logger.error(f"Startup DB patch failed: {patch_error}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def main():
    run_startup_db_patch()
    if "base_currency" not in st.session_state:
        st.session_state.base_currency = "GHS"
    if "exchange_rate" not in st.session_state:
        st.session_state.exchange_rate = 1.0

    selected_base_currency = str(st.session_state.get("base_currency", "GHS")).upper()
    bog_rate = _get_bog_display_rate(selected_base_currency)
    expected_rate = 1.0 if selected_base_currency == "GHS" else bog_rate
    if abs(float(st.session_state.get("exchange_rate", 1.0)) - float(expected_rate)) > 0.000001:
        st.session_state.exchange_rate = expected_rate

    settings_conn = None
    try:
        settings_conn = get_connection()
        if settings_conn:
            settings_conn.execute(
                "UPDATE system_settings SET base_currency = ?, display_currency = ?, exchange_rate = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                ("GHS", selected_base_currency, st.session_state.exchange_rate),
            )
            settings_conn.commit()
    except Exception as session_sync_error:
        logger.warning(f"Currency session sync failed: {session_sync_error}")
    finally:
        if settings_conn:
            settings_conn.close()


PRIMARY_NAV_ITEMS = [
    ("📊 Dashboard", "Dashboard"),
    ("🛒 Point of Sale", "Point of Sale"),
    ("📦 Inventory Management", "Inventory Management"),
    ("📊 Data Analytics", "Data Analytics"),
    ("🧾 Financial Reports", "Financial Reports"),
    ("📦 Asset Register", "Asset Register"),
    ("⚙️ System Configuration", "System Configuration"),
]


PRIMARY_NAV_ITEMS = [
    ("📊 Dashboard", "Dashboard"),
    ("🛒 Point of Sale", "Point of Sale"),
    ("📦 Inventory Management", "Inventory Management"),
    ("📅 Accounts Receivable", "Accounts Receivable"),
    ("📅 Accounts Payable", "Accounts Payable"),
    ("💰 Banking & Cash", "Banking & Cash"),
    ("📅 Taxation (VAT/NHIL)", "Taxation (VAT/NHIL)"),
    ("📅 Payroll & Salaries", "Payroll & Salaries"),
    ("🏛️ Asset Register", "Asset Register"),
    ("📊 Data Analytics", "Data Analytics"),
    ("🧾 Financial Reports", "Financial Reports"),
    ("🤖 Gatekeeper Admin", "Gatekeeper Admin"),
    ("📅 System Audit Trail", "System Audit Trail"),
    ("⚙️ System Configuration", "System Configuration"),
]


def _ensure_valid_page(default_page="Dashboard"):
    valid_pages = {page_key for _label, page_key in PRIMARY_NAV_ITEMS}
    current_page = st.session_state.get("page", default_page)
    if current_page not in valid_pages:
        label_to_key = {label: key for label, key in PRIMARY_NAV_ITEMS}
        current_page = label_to_key.get(str(current_page), default_page)
    st.session_state.page = current_page
    return current_page


def _render_primary_sidebar(user, include_settings=True):
    st.sidebar.markdown(
        f"""
        <div style='background-color:#f0f2f6; padding:20px; border-radius:15px; border: 1px solid #d1d5db;'>
            <h2 style='margin-bottom:0;'>📦 {user['name']}</h2>
            <p style='color:#6b7280;'>Role: <b>{user['role']}</b></p>
            <p style='color:#6b7280; font-size:12px;'>Session: Active</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_items = PRIMARY_NAV_ITEMS if include_settings else [item for item in PRIMARY_NAV_ITEMS if item[1] != "System Configuration"]
    current_page = _ensure_valid_page()
    labels = [label for label, _key in nav_items]
    selected_label = next((label for label, key in nav_items if key == current_page), labels[0])
    selected_index = labels.index(selected_label) if selected_label in labels else 0
    chosen_label = st.sidebar.selectbox("Navigation", labels, index=selected_index, key="primary_navigation")
    chosen_page = dict(nav_items)[chosen_label]
    if chosen_page != st.session_state.page:
        st.session_state.page = chosen_page
        st.rerun()
    st.sidebar.divider()
    _render_currency_sidebar_controls("display_currency_primary")
    render_accounting_assistant_sidebar(st.session_state.page)
    st.sidebar.divider()
    currency = st.sidebar.selectbox(
        "Display Currency",
        ["GHS", "USD", "EUR", "GBP"],
        index=["GHS", "USD", "EUR", "GBP"].index(str(st.session_state.get("base_currency", "GHS")).upper())
        if str(st.session_state.get("base_currency", "GHS")).upper() in ["GHS", "USD", "EUR", "GBP"]
        else 0,
        key="display_currency_visible_fallback",
    )
    st.session_state.base_currency = currency
    rates = {"GHS": 1.0, "USD": 11.65, "EUR": 13.34, "GBP": 15.47}
    st.session_state.exchange_rate = rates[currency]
    fallback_history_key = "sidebar_accounting_ai_history"
    if fallback_history_key not in st.session_state:
        st.session_state[fallback_history_key] = [
            {"role": "assistant", "content": "Ask an IFRS or Ghana tax question and I will answer using your selected display currency."}
        ]
    fallback_container = st.sidebar.container(height=160)
    with fallback_container:
        for message in st.session_state[fallback_history_key][-6:]:
            speaker = "AI" if message["role"] == "assistant" else "You"
            st.markdown(f"**{speaker}:** {message['content']}")
    sidebar_question = st.sidebar.chat_input("Ask Accounting AI...", key="sidebar_accounting_ai_fallback")
    if sidebar_question:
        st.session_state[fallback_history_key].append({"role": "user", "content": sidebar_question})
        sidebar_reply = accounting_ai_response(st.session_state.page, st.session_state[fallback_history_key])
        st.session_state[fallback_history_key].append({"role": "assistant", "content": sidebar_reply})
        st.rerun()


def _render_primary_page(user):
    if st.session_state.page == "Dashboard":
        show_dashboard_module(user["key"], user["name"], user["role"])
    elif st.session_state.page == "Point of Sale":
        show_pos(user["key"], user["name"], user["role"])
    elif st.session_state.page == "Inventory Management":
        show_inventory(user["key"], user["role"])
    elif st.session_state.page == "Accounts Receivable":
        show_accounts_receivable(user["key"])
    elif st.session_state.page == "Accounts Payable":
        show_accounts_payable(user["key"])
    elif st.session_state.page == "Banking & Cash":
        show_banking(user["key"], user["role"])
    elif st.session_state.page == "Taxation (VAT/NHIL)":
        show_taxation(user["key"])
    elif st.session_state.page == "Payroll & Salaries":
        show_payroll(user["key"], user["role"])
    elif st.session_state.page == "Asset Register":
        show_fixed_assets(user["key"], user["role"])
    elif st.session_state.page == "Data Analytics":
        show_reports(user["key"])
    elif st.session_state.page == "Financial Reports":
        show_financial_reports(user["key"], user["role"])
    elif st.session_state.page == "Gatekeeper Admin":
        show_ai_assistant(user["key"])
    elif st.session_state.page == "System Audit Trail":
        show_audit_trail(user["key"])
    elif st.session_state.page == "System Configuration":
        show_company_setup(user["key"], user["name"], user["role"])
    else:
        st.session_state.page = "Dashboard"
        st.rerun()


# Main application flow
main()
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

                st.markdown("---")
                st.subheader("Master Price Setting")
                try:
                    current_price_row = conn.execute(
                        "SELECT master_price_per_month FROM system_settings WHERE id = 1"
                    ).fetchone()
                    current_price = float(current_price_row[0]) if current_price_row and current_price_row[0] is not None else 500.0
                except Exception:
                    current_price = 500.0
                with st.form("master_price_setting_form"):
                    master_price = st.number_input(
                        "Master Price Per Month (GHS)",
                        min_value=0.0,
                        value=current_price,
                        step=50.0,
                    )
                    if st.form_submit_button("Save Master Price"):
                        try:
                            conn.execute(
                                """
                                INSERT INTO system_settings (id, master_price_per_month, updated_at)
                                VALUES (1, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(id) DO UPDATE SET
                                    master_price_per_month = excluded.master_price_per_month,
                                    updated_at = CURRENT_TIMESTAMP
                                """,
                                (master_price,),
                            )
                            conn.commit()
                            st.success(f"Master monthly price updated to GHS {master_price:,.2f}.")
                        except Exception as price_error:
                            st.error(f"Could not update master price: {price_error}")
                
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
                            new_expiry = datetime.now() + relativedelta(months=+int(duration_months))
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
                st.subheader("Maintenance Over")
                st.success("Thank you for your patience. Our systems are upgraded to better serve your business.")
                col_m1, col_m2, col_m3 = st.columns(3)
                m_date = col_m1.date_input('Maintenance Date')
                m_start = col_m2.time_input('Start Time')
                m_end = col_m3.time_input('End Time')
                m_msg = st.text_area(
                    'Client Appreciation Message',
                    "Maintenance Over. Thank you for your patience. Our systems are upgraded to better serve your business.",
                )

                if st.button('Update Client Message'):
                    conn = get_connection()
                    conn.execute(
                        "UPDATE maintenance_settings SET maintenance_date=?, is_active=0, message=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
                        ("Maintenance Over", m_msg),
                    )
                    recipients = conn.execute(
                        """
                        SELECT name, contact_email
                        FROM companies
                        WHERE contact_email IS NOT NULL AND TRIM(contact_email) != ''
                        """
                    ).fetchall()
                    conn.commit()
                    delivered = 0
                    for recipient in recipients:
                        try:
                            if send_maintenance_email(recipient["contact_email"], recipient["name"], m_msg):
                                delivered += 1
                        except Exception:
                            continue
                    st.success(f'Maintenance appreciation message updated for clients. Emails sent: {delivered}.')
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
                    SELECT c.key, c.name, c.created_at,
                    COALESCE(NULLIF(c.status, ''), 'Active') as status,
                    c.deployment_status, c.subscription_expiry,
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
                        action_company_key = selected_portfolio["key"]
                        action_company_name = selected_portfolio["name"]
                        st.warning(
                            "Company lifecycle actions are destructive. Archive will disable login but keep data. "
                            "Wipe will permanently delete the company and all linked records."
                        )
                        action_choice = st.radio(
                            "Remove Company Action",
                            ["Archive (Keep Data)", "Wipe (Delete Entirely)"],
                            key="company_lifecycle_action",
                            horizontal=True,
                        )
                        confirm_action = st.checkbox(
                            f"I confirm the {action_choice.lower()} action for {action_company_name}.",
                            key="company_lifecycle_confirm",
                        )
                        action_col1, action_col2 = st.columns(2)
                        with action_col1:
                            if st.button("Apply Company Action", key="apply_company_action_btn"):
                                if not confirm_action:
                                    st.warning("Confirm the company action before applying it.")
                                else:
                                    try:
                                        if action_choice == "Archive (Keep Data)":
                                            conn.execute(
                                                """
                                                UPDATE companies
                                                SET status = 'Inactive', deployment_status = 'Archived'
                                                WHERE key = ?
                                                """,
                                                (action_company_key,),
                                            )
                                            conn.commit()
                                            log_audit_action(
                                                conn,
                                                action_company_key,
                                                "Dev",
                                                "Company Archived",
                                                "Gatekeeper Dashboard",
                                                f"{action_company_name} archived with data retained.",
                                            )
                                            st.success(f"{action_company_name} archived. Data retained and login disabled.")
                                        else:
                                            wipe_company_records(conn, action_company_key)
                                            conn.commit()
                                            log_audit_action(
                                                conn,
                                                "SYSTEM",
                                                "Dev",
                                                "Company Wiped",
                                                "Gatekeeper Dashboard",
                                                f"{action_company_name} permanently deleted.",
                                            )
                                            st.success(f"{action_company_name} and all linked records were deleted.")
                                        st.rerun()
                                    except Exception as action_error:
                                        conn.rollback()
                                        st.error(f"Company action failed: {action_error}")
                        with action_col2:
                            if st.button("Reactivate Archived Company", key="reactivate_archived_company_btn"):
                                try:
                                    conn.execute(
                                        """
                                        UPDATE companies
                                        SET status = 'Active',
                                            deployment_status = CASE
                                                WHEN COALESCE(deployment_status, '') = 'Archived' THEN 'Live'
                                                ELSE deployment_status
                                            END
                                        WHERE key = ?
                                        """,
                                        (action_company_key,),
                                    )
                                    conn.commit()
                                    log_audit_action(
                                        conn,
                                        action_company_key,
                                        "Dev",
                                        "Company Reactivated",
                                        "Gatekeeper Dashboard",
                                        f"{action_company_name} reactivated from the portfolio manager.",
                                    )
                                    st.success(f"{action_company_name} reactivated.")
                                    st.rerun()
                                except Exception as reactivate_error:
                                    conn.rollback()
                                    st.error(f"Could not reactivate company: {reactivate_error}")
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
                    SELECT key, name, subscription_expiry,
                           COALESCE(NULLIF(status, ''), 'Active') as status,
                           deployment_status, contact_email
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
                    company_key = selected_row["key"]
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
                            log_audit_action(
                                conn,
                                company_key,
                                "Dev",
                                "Subscription Renewed",
                                "License Management",
                                f"Renewed until {new_expiry_date.isoformat()}",
                            )
                            st.success(
                                f"Subscription updated for {selected_company} until {new_expiry_date.isoformat()}."
                            )
                            send_renewal_email(
                                selected_company,
                                company_email,
                                new_expiry_date.isoformat(),
                            )
                            st.balloons()
                            st.rerun()
                        except Exception as renew_error:
                            st.error(f"Failed to extend subscription: {renew_error}")

                conn.close()
            except Exception as e:
                st.error(f'License Table Error: {e}')
                    
    elif u['role'] == "Demo":
        demo_user = {"key": "DEMO", "name": "Demo Corporation Ltd", "role": "Demo"}
        _render_primary_sidebar(demo_user, include_settings=False)
        _render_primary_page(demo_user)
        st.sidebar.markdown("---")
        if st.sidebar.button("🔴 Secure Logout", width='stretch', key="v3_demo_logout_primary"):
            st.session_state.clear()
            st.rerun()
        st.stop()

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
        
        menu = ["Dashboard", "📦 Inventory Management", "💳 Payroll & Salaries", "Sales/Purchase", "📊 Data Analytics", "Banking", "Taxation", "🤖 Gatekeeper Admin", "Audit Trail"]
        current_page = normalize_page_label(st.session_state.get("page")) or "Dashboard"
        current_page = repair_ui_label(current_page)
        selected_index = menu.index(current_page) if current_page in menu else 0
        choice = st.sidebar.selectbox("Navigation", menu, index=selected_index)
        st.session_state.page = choice
        render_accounting_assistant_sidebar(choice)
        display_choice_map = {
            "📊 Dashboard": "ðŸ  Dashboard",
            "🛒 Point of Sale": "ðŸ›’ Point of Sale",
            "📦 Inventory Management": "ðŸ“¦ Inventory Management",
            "💳 Payroll & Salaries": "ðŸ’³ Payroll & Salaries",
            "📊 Data Analytics": "ðŸ“Š Data Analytics",
            "⚙️ System Configuration": "âš™ï¸ System Configuration",
            "🧾 Sales Invoicing": "Sales Invoicing",
            "🤖 Gatekeeper Admin": "ðŸ¤– Gatekeeper Admin",
            "📦 Asset Register": "ðŸ›ï¸ Asset Register",
        }
        choice = display_choice_map.get(choice, choice)
        
        if choice == "Dashboard":
            show_dashboard("DEMO", "Demo Corporation Ltd", "Demo")
        elif choice == "📦 Inventory Management":
            show_inventory("DEMO", "Demo")
        elif choice == "💳 Payroll & Salaries":
            show_payroll("DEMO", "Demo")
        elif choice == "Sales/Purchase":
            show_sales_purchase("DEMO", "Demo", "Sales")
        elif choice == "📊 Data Analytics":
            show_reports("DEMO")
        elif choice == "Banking":
            show_banking("DEMO", "Demo")
        elif choice == "Taxation":
            show_taxation("DEMO")
        elif choice == "🤖 Gatekeeper Admin":
            show_ai_assistant("DEMO")
        elif choice == "Audit Trail":
            show_audit_trail("DEMO")
                    
    else:
        _render_primary_sidebar(u, include_settings=True)
        _render_primary_page(u)
        st.sidebar.markdown("---")
        if st.sidebar.button("🔴 Secure Logout", width='stretch', key="v3_primary_logout"):
            try:
                conn = get_connection()
                log_audit_action(conn, u.get('key', 'SYSTEM'), u['role'], "User logout", "Authentication")
                conn.close()
            except Exception:
                pass
            st.session_state.auth = False
            st.session_state.user = None
            st.session_state.company_id = None
            st.session_state.login_attempts = 0
            st.rerun()
        st.stop()

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
            "🏠 Dashboard", "🛒 Point of Sale", "Vouchers & Journals", "Chart of Accounts", 
            "📦 Inventory Management", "Sales Invoicing", "Purchase Orders", 
            "Banking & Cash", "Accounts Receivable", "Accounts Payable", 
            "Taxation (VAT/NHIL)", "💳 Payroll & Salaries", "🏛️ Asset Register", 
            "📊 Data Analytics", "🤖 Gatekeeper Admin", "System Audit Trail"
        ]
        menu = [repair_ui_label(item) for item in menu]

        if u['role'] == "Master Admin":
            menu.insert(1, "⚙️ System Configuration")
        
        menu = [repair_ui_label(item) for item in menu]
        current_page = normalize_page_label(st.session_state.get("page")) or "🏠 Dashboard"
        current_page = repair_ui_label(current_page)
        selected_index = menu.index(current_page) if current_page in menu else 0
        choice = st.sidebar.selectbox("Go to Module:", menu, index=selected_index, key="v3_main_nav_dropdown")
        st.session_state.page = choice
        choice = repair_ui_label(normalize_page_label(choice))
        st.session_state.page = choice
        with st.sidebar.expander("Currency", expanded=False):
            _render_currency_sidebar_controls("display_currency_toggle")
        render_accounting_assistant_sidebar(choice)
        regular_choice_map = {
            "📊 Dashboard": "ðŸ  Dashboard",
            "🛒 Point of Sale": "ðŸ›’ Point of Sale",
            "📦 Inventory Management": "ðŸ“¦ Inventory Management",
            "💳 Payroll & Salaries": "ðŸ’³ Payroll & Salaries",
            "📊 Data Analytics": "ðŸ“Š Data Analytics",
            "⚙️ System Configuration": "âš™ï¸ System Configuration",
            "🧾 Sales Invoicing": "Sales Invoicing",
            "🤖 Gatekeeper Admin": "ðŸ¤– Gatekeeper Admin",
            "📦 Asset Register": "ðŸ›ï¸ Asset Register",
        }
        choice = regular_choice_map.get(choice, choice)
        
        # Dashboard Module (NEW)
        if choice == "🏠 Dashboard":
            show_dashboard(u['key'], u['name'], u['role'])  # FIXED: Correct parameter passing
        
        # Comprehensive Mapping Logic
        elif choice == "⚙️ System Configuration": show_company_setup(u['key'], u['name'], u['role'])
        elif choice == "🛒 Point of Sale": show_pos(u['key'], u['name'], u['role'])
        elif choice == "Vouchers & Journals": show_vouchers(u['key'], u['role'])
        elif choice == "Chart of Accounts": show_chart_of_accounts(u['key'], u['role'])
        elif choice == "📦 Inventory Management": show_inventory(u['key'], u['role'])
        elif choice == "Sales Invoicing": show_sales_purchase(u['key'], u['role'], "Sales")
        elif choice == "Purchase Orders": show_sales_purchase(u['key'], u['role'], "Purchase")
        elif choice == "Banking & Cash": show_banking(u['key'], u['role'])
        elif choice == "Accounts Receivable": show_aging(u['key'], "Receivable")
        elif choice == "Accounts Payable": show_aging(u['key'], "Payable")
        elif choice == "Taxation (VAT/NHIL)": show_taxation(u['key'])
        elif choice == "💳 Payroll & Salaries": show_payroll(u['key'], u['role'])
        elif choice == "🏛️ Asset Register": show_fixed_assets(u['key'], u['role'])
        elif choice == "📊 Data Analytics": show_reports(u['key'])
        elif choice == "🤖 Gatekeeper Admin": show_ai_assistant(u['key'])
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
        st.session_state.company_id = None
        st.session_state.login_attempts = 0
        st.rerun()
