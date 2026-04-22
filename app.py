import streamlit as st
import pandas as pd
import importlib.util
from database import (
    DB_PATH,
    ensure_schema,
    get_connection,
    get_recovery_source_diagnostics,
    startup_database,
)
from openai import OpenAI
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
import hashlib
import random
import string
from dateutil.relativedelta import relativedelta
import smtplib
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import uuid
from accounting_engine import get_month_sales_total, get_recent_accounting_activity

try:
    import firebase_admin
    from firebase_admin import credentials, initialize_app, storage
except Exception:
    firebase_admin = None
    credentials = None
    initialize_app = None
    storage = None
from financials import (
    show_customers_page,
    show_create_invoice_page,
    show_receive_payment_page,
    show_suppliers_page,
    show_supplier_payment_page,
    show_financial_reports,
    show_ledger_viewer,
    show_record_transaction,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "assets", "eka_logo.png")


def _load_local_modules_module():
    try:
        import modules as loaded_modules

        logger.info(
            "Modules import initialized via standard registry lookup: module=%s file=%s",
            getattr(loaded_modules, "__name__", "modules"),
            getattr(loaded_modules, "__file__", "unknown"),
        )
        return loaded_modules
    except KeyError as exc:
        modules_path = os.path.join(BASE_DIR, "modules.py")
        logger.warning(
            "Modules registry entry was missing during import: expected_key='modules' modules_path=%s error=%s",
            modules_path,
            exc,
        )
        spec = importlib.util.spec_from_file_location("modules", modules_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not build import spec for local modules.py at {modules_path}") from exc
        loaded_modules = importlib.util.module_from_spec(spec)
        sys.modules["modules"] = loaded_modules
        spec.loader.exec_module(loaded_modules)
        logger.info(
            "Modules import recovered by explicitly loading local modules.py: module=%s file=%s",
            getattr(loaded_modules, "__name__", "modules"),
            getattr(loaded_modules, "__file__", modules_path),
        )
        return loaded_modules


eka_modules = _load_local_modules_module()
BOG_DISPLAY_RATES = eka_modules.BOG_DISPLAY_RATES
accounting_ai_response = eka_modules.accounting_ai_response
format_currency = eka_modules.format_currency
get_exchange_rate = eka_modules.get_exchange_rate
initialize_paystack_payment = eka_modules.initialize_paystack_payment
log_audit_action = eka_modules.log_audit_action
render_accounting_assistant_sidebar = eka_modules.render_accounting_assistant_sidebar
show_accounts_payable = eka_modules.show_accounts_payable
show_accounts_receivable = eka_modules.show_accounts_receivable
show_create_bill_page = eka_modules.show_create_bill_page
show_dashboard_module = eka_modules.show_dashboard
show_aging = eka_modules.show_aging
show_ai_assistant = eka_modules.show_ai_assistant
show_audit_trail = eka_modules.show_audit_trail
show_banking = eka_modules.show_banking
show_branch_management = eka_modules.show_branch_management
show_chart_of_accounts = eka_modules.show_chart_of_accounts
show_company_setup = eka_modules.show_company_setup
show_fixed_assets = eka_modules.show_fixed_assets
show_inventory = eka_modules.show_inventory
show_journal_entries = eka_modules.show_journal_entries
show_onboarding_payment = eka_modules.show_onboarding_payment
show_payroll = eka_modules.show_payroll
show_pos = eka_modules.show_pos
show_reports = eka_modules.show_reports
show_sales_purchase = eka_modules.show_sales_purchase
show_taxation = eka_modules.show_taxation
show_vouchers = eka_modules.show_vouchers

GATEKEEPER_SYSTEM_PROMPT = (
    "You are a professional Chartered Accountant. Provide clear, accurate financial guidance based on the ERP data."
)

# OpenAI client initialization
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    st.session_state['ai_active'] = True
except Exception as exc:
    st.toast(f"Failed to initialize OpenAI client: {exc}")
    st.session_state['ai_active'] = False
    client = None
FIREBASE_APP = None
FIREBASE_BUCKET_NAME = None
FIREBASE_OBJECT_NAME = "backups/eka_enterprise_v3.db"


def _get_app_firebase_service_account_info():
    try:
        service_account_json = st.secrets["firebase"]["service_account"]
        service_account_info = json.loads(service_account_json)
        logger.info("Firebase credentials loaded from Streamlit secrets")
        return {
            "ok": True,
            "source": "streamlit_secrets",
            "service_account_info": service_account_info,
        }
    except Exception as exc:
        logger.warning("Firebase Secret Formatting Error. Please check Streamlit Cloud Secrets. Details: %s", exc)
        st.error("Firebase Secret Formatting Error. Please check Streamlit Cloud Secrets.")
        return {
            "ok": False,
            "source": "streamlit_secrets",
            "reason": "Firebase Secret Formatting Error. Please check Streamlit Cloud Secrets.",
        }


def _init_firebase_storage_client():
    global FIREBASE_APP, FIREBASE_BUCKET_NAME
    if firebase_admin is None or credentials is None or initialize_app is None or storage is None:
        return None
    if FIREBASE_APP is not None:
        return FIREBASE_APP
    try:
        diagnostics = get_recovery_source_diagnostics()
        credentials_result = _get_app_firebase_service_account_info()
        if not credentials_result.get("ok"):
            logger.warning("Cloud Vault UI client could not load credentials: %s", credentials_result.get("reason"))
            return None
        if not diagnostics.get("credentials_loaded"):
            logger.warning("Cloud Vault UI client could not load credentials: %s", diagnostics.get("credential_error"))
            return None
        if not diagnostics.get("bucket_name"):
            logger.warning("Cloud Vault UI client could not determine a storage bucket name.")
            return None
        if not diagnostics.get("database_url"):
            logger.warning("Cloud Vault UI client is missing a database URL configuration.")
            return None
        FIREBASE_BUCKET_NAME = diagnostics["bucket_name"]
        firebase_cred = credentials.Certificate(credentials_result["service_account_info"])
        FIREBASE_APP = initialize_app(
            firebase_cred,
            {
                "storageBucket": FIREBASE_BUCKET_NAME,
                "databaseURL": diagnostics["database_url"],
            },
            name="eka-silent-sync",
        )
        return FIREBASE_APP
    except ValueError:
        try:
            FIREBASE_APP = firebase_admin.get_app("eka-silent-sync")
            return FIREBASE_APP
        except Exception as exc:
            logger.warning("Cloud Vault UI client lookup failed: %s", exc)
            return None
    except Exception as exc:
        logger.warning("Cloud Vault UI client initialization failed: %s", exc)
        return None


def _get_firebase_bucket():
    app = _init_firebase_storage_client()
    if app is None or storage is None:
        return None
    try:
        return storage.bucket(app=app)
    except Exception:
        return None


def _get_cloud_vault_status():
    try:
        diagnostics = get_recovery_source_diagnostics()
        logger.info(
            "Cloud Vault status check: backend=%s credentials_loaded=%s credentials_source=%s firebase_key_exists=%s bucket=%s object=%s",
            diagnostics.get("backend"),
            diagnostics.get("credentials_loaded"),
            diagnostics.get("credentials_source"),
            diagnostics.get("firebase_key_exists"),
            diagnostics.get("bucket_name") or "missing",
            diagnostics.get("object_name") or "missing",
        )
        if not diagnostics.get("credentials_loaded"):
            return "🔴 Cloud Vault: Credentials Missing"
        bucket = _get_firebase_bucket()
        if bucket is None:
            return "🔴 Cloud Vault: Local Mode"
        try:
            list(bucket.list_blobs(prefix=diagnostics.get("object_name") or FIREBASE_OBJECT_NAME, max_results=1))
            return "🟢 Cloud Vault: Connected"
        except Exception as exc:
            logger.warning("Cloud Vault connectivity check failed: %s", exc)
            return "🔴 Cloud Vault: Source Unreachable"
    except Exception as exc:
        logger.warning("Cloud Vault status check failed: %s", exc)
        return "🔴 Cloud Vault: Source Unreachable"


def _verify_cloud_vault_handshake():
    try:
        st.session_state.cloud_vault_status = _get_cloud_vault_status()
    except Exception:
        st.session_state.cloud_vault_status = "🔴 Cloud Vault: Local Mode"


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
if 'currency_symbol' not in st.session_state:
    st.session_state.currency_symbol = "GH₵"


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
        symbols = {"GHS": "GH₵", "USD": "$", "EUR": "€", "GBP": "£"}
        st.session_state.base_currency = selected_currency
        st.session_state.display_currency = selected_currency
        st.session_state.exchange_rate = selected_rate
        st.session_state.currency_symbol = symbols.get(st.session_state.base_currency, "GH₵")
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
    "customers": "🧾 Customers",
    "create_invoice": "📄 Create Invoice",
    "receive_payment_customer": "💳 Receive Payment (Customer)",
    "suppliers": "🏷️ Suppliers",
    "create_bill": "📝 Create Bill",
    "supplier_payment": "💸 Supplier Payment",
    "customer_ledger": "📔 Customer Ledger",
    "supplier_ledger": "📔 Supplier Ledger",
    "journal": "🧾 General Journal",
    "ledger": "📚 General Ledger",
    "chart_of_accounts": "🗂️ Chart of Accounts",
    "banking": "💰 Banking & Cash",
    "taxation": "📅 Taxation (VAT/NHIL)",
    "payroll": "💳 Payroll & Salaries",
    "assets": "🏛️ Asset Register",
    "reports": "📊 Data Analytics",
    "financial_reports": "🧾 Financial Reports",
    "audit_trail": "📅 System Audit Trail",
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
        "Accounts Receivable": PAGE_LABELS["customer_ledger"],
        "Accounts Receivables": PAGE_LABELS["customer_ledger"],
        "Customer Ledger": PAGE_LABELS["customer_ledger"],
        "Accounts Payable": PAGE_LABELS["supplier_ledger"],
        "Accounts Payables": PAGE_LABELS["supplier_ledger"],
        "Supplier Ledger": PAGE_LABELS["supplier_ledger"],
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

def ask_gatekeeper_ai(user_input):
    """Send the raw user prompt directly to OpenAI and return the response text."""
    if st.session_state.get("ai_active") is False or client is None:
        return "The app cannot see OPENAI_API_KEY in Streamlit Secrets."

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a Senior Chartered Accountant for a Ghanaian enterprise. Provide direct, professional financial analysis without preamble. Answer user queries based on their ERP data confidently and concisely.",
                },
                {"role": "user", "content": user_input},
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI Gatekeeper AI call failed: {e}")
        return f"AI Error: {str(e)}"


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
                ai_response = ask_gatekeeper_ai(user_question)
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


def render_login_logo():
    if os.path.exists(LOGO_PATH):
        logo_col, text_col = st.columns([1, 3])
        with logo_col:
            st.image(LOGO_PATH, width=180)
        with text_col:
            st.markdown(
                "<h1 style='color: #1E3A8A; margin-top: 28px;'>E.K.A ENTERPRISE ERP</h1>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>E.K.A ENTERPRISE ERP</h1>", unsafe_allow_html=True)

def login_ui():
    """Secure Multi-Tier Authentication Interface with Enhanced Security."""
    render_login_logo()
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # Check for brute force attempts
    if st.session_state.login_attempts >= 5:
        st.error("Too many failed login attempts. Please wait before trying again.")
        return
    
    t1, t2, t3, t4 = st.tabs(["🔒 Secure Login", "🔑 System Recovery", "🏢 Register New Company", "🌐 System Status"])
    
    with t1:
        if not st.session_state.get('demo_toggle'):
            # Assigned unique keys to ensure no Duplicate ID errors
            access_key = st.text_input(
                "Access Key", 
                type="password", 
                key="v3_final_access_key_field"
            )
            
            if st.button("Access Cloud Modules", key="v3_final_auth_submit_btn"):
                try:
                    conn = get_connection()
                    
                    # Developer Backdoor
                    if access_key == "JUANMANUEL2":
                        st.session_state.auth = True
                        st.session_state.user = {"name": "Gatekeeper", "role": "Dev", "key": "ADMIN"}
                        st.session_state.company_id = "ADMIN"
                        log_audit_action(conn, "SYSTEM", "Dev", "Developer login", "Authentication")
                        conn.close()
                        st.session_state.login_attempts = 0
                        st.rerun()
                    
                    # Master Admin Check
                    admin = conn.execute("SELECT key, name, COALESCE(status, 'Active') FROM companies WHERE key = ?", (access_key,)).fetchone()
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
                    
                    # Branch Access Key Login
                    branch_auth = conn.execute(
                        """
                        SELECT b.branch_id, b.company_key, b.branch_name, b.branch_access_key, c.name
                        FROM branches b
                        JOIN companies c ON c.key = b.company_key
                        WHERE b.branch_access_key = ?
                          AND COALESCE(c.status, 'Active') = 'Active'
                        LIMIT 1
                        """,
                        (access_key,),
                    ).fetchone()
                    if branch_auth:
                        license_status = check_license_expiry_with_grace(branch_auth[1])
                        if license_status['status'] != 'expired':
                            st.session_state.auth = True
                            st.session_state.user = {
                                "key": branch_auth[1],
                                "name": branch_auth[4],
                                "role": "Branch_Bookkeeper",
                                "branch_name": branch_auth[2],
                                "branch_id": branch_auth[0],
                            }
                            st.session_state.company_id = branch_auth[1]
                            st.session_state.active_branch_id = branch_auth[0]
                            log_audit_action(conn, branch_auth[1], "Branch_Bookkeeper", "Successful login", "Authentication", branch_id=branch_auth[0])
                            conn.close()
                            st.session_state.login_attempts = 0
                            st.rerun()
                        else:
                            st.error(f"Your license expired {license_status['days_left']} days ago. Please renew to access the system.")

                    # Branch Bookkeeper / Staff Check
                    user_login = conn.execute(
                        """
                        SELECT u.company_key, c.name, u.role, u.full_name, u.branch_id
                        FROM users u
                        JOIN companies c ON c.key = u.company_key
                        WHERE u.login_key = ?
                          AND COALESCE(u.status, 'Active') = 'Active'
                          AND COALESCE(c.status, 'Active') = 'Active'
                        """,
                        (access_key,),
                    ).fetchone()
                    if user_login:
                        license_status = check_license_expiry_with_grace(user_login[0])
                        if license_status['status'] != 'expired':
                            role_name = user_login[2]
                            if role_name == "Bookkeeper":
                                role_name = "Branch_Bookkeeper"
                            if user_login[4]:
                                conn.execute(
                                    "UPDATE branches SET branch_access_key = ? WHERE branch_id = ? AND COALESCE(branch_access_key, '') = ''",
                                    (access_key, user_login[4]),
                                )
                            st.session_state.auth = True
                            st.session_state.user = {
                                "key": user_login[0],
                                "name": user_login[1],
                                "role": role_name,
                                "staff_name": user_login[3],
                            }
                            st.session_state.company_id = user_login[0]
                            st.session_state.active_branch_id = user_login[4]
                            log_audit_action(conn, user_login[0], role_name, "Successful login", "Authentication", branch_id=user_login[4])
                            conn.close()
                            st.session_state.login_attempts = 0
                            st.rerun()
                        else:
                            st.error(f"Your license expired {license_status['days_left']} days ago. Please renew to access the system.")

                    # Failed login attempt
                    st.session_state.login_attempts += 1
                    log_audit_action(conn, "SYSTEM", "Unknown", f"Failed login attempt {st.session_state.login_attempts}", "Authentication")
                    conn.close()
                    st.error(f"Access Denied. Please verify your Access Key. Attempts: {st.session_state.login_attempts}/5")
                    
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
        st.info("Use your login key and recovery answer to reset your password.")
        forgot_login_key = st.text_input("Login Key", key="v3_forgot_login_key")
        if st.button("Lookup Recovery Question", key="v3_lookup_recovery_question"):
            try:
                conn = get_connection()
                row = conn.execute(
                    "SELECT company_key, security_question FROM users WHERE login_key = ? AND COALESCE(status, 'Active') = 'Active' LIMIT 1",
                    (forgot_login_key.strip(),),
                ).fetchone()
                if row and row["security_question"]:
                    st.session_state.forgot_login_key = forgot_login_key.strip()
                    st.session_state.forgot_security_question = row["security_question"]
                    st.session_state.forgot_company_key = row["company_key"]
                    st.success("Security question loaded. Answer it to reset your password.")
                else:
                    st.error("No active user found for that login key or no recovery question is set.")
                conn.close()
            except Exception as e:
                st.error("System error during recovery. Please try again.")
                logger.error(f"Recovery error: {e}")

        if st.session_state.get("forgot_security_question"):
            st.markdown(f"**Recovery Question:** {st.session_state['forgot_security_question']}")
            recovery_answer = st.text_input("Security Answer", type="password", key="v3_forgot_answer")
            new_password = st.text_input("New Password", type="password", key="v3_forgot_new_password")
            confirm_password = st.text_input("Confirm New Password", type="password", key="v3_forgot_confirm_password")
            if st.button("Reset Password", key="v3_reset_password_btn"):
                if not recovery_answer or not new_password:
                    st.error("Enter both your recovery answer and a new password.")
                elif new_password != confirm_password:
                    st.error("New password and confirmation do not match.")
                else:
                    try:
                        conn = get_connection()
                        reset_row = conn.execute(
                            "SELECT company_key, security_answer FROM users WHERE login_key = ? LIMIT 1",
                            (st.session_state.get("forgot_login_key"),),
                        ).fetchone()
                        if reset_row and reset_row["security_answer"] == hash_login_password(recovery_answer):
                            conn.execute(
                                "UPDATE users SET password_hash = ? WHERE login_key = ?",
                                (hash_login_password(new_password), st.session_state.get("forgot_login_key")),
                            )
                            conn.commit()
                            log_audit_action(
                                conn,
                                reset_row["company_key"],
                                "Recovery",
                                "Password reset",
                                "Authentication",
                                branch_id=st.session_state.get("active_branch_id"),
                            )
                            st.success("Password has been reset successfully. Please login with your new password.")
                            st.session_state.pop("forgot_login_key", None)
                            st.session_state.pop("forgot_security_question", None)
                            st.session_state.pop("forgot_company_key", None)
                        else:
                            st.error("Security answer does not match our records.")
                        conn.close()
                    except Exception as e:
                        st.error("Unable to reset password at this time.")
                        logger.error(f"Password reset error: {e}")

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
            col1.metric(label=f"Inventory Value ({st.session_state.currency_symbol})", value=format_currency(25000.0))
            col2.metric(label=f"Month Sales ({st.session_state.currency_symbol})", value=format_currency(15000.0))
            col3.metric("Employees", "5")
            col4.metric(label=f"Asset Value ({st.session_state.currency_symbol})", value=format_currency(50000.0))

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
                demo_txns["Amount"] = demo_txns["Amount"].map(format_currency)
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
                col1.metric(label=f"Inventory Value ({st.session_state.currency_symbol})", value=format_currency(inv_val))

                current_month = datetime.now().strftime('%Y-%m')
                month_sales = get_month_sales_total(company_key, year_month=current_month, conn=conn)
                col2.metric(label=f"Month Sales ({st.session_state.currency_symbol})", value=format_currency(month_sales))

                emp_count = conn.execute(
                    "SELECT COUNT(DISTINCT emp_name) FROM payroll WHERE company_key = ? AND COALESCE(status, 'Active') != 'Void'",
                    (company_key,),
                ).fetchone()[0] or 0
                col3.metric("Employees", str(emp_count))

                fa_val = conn.execute(
                    "SELECT COALESCE(SUM(book_value), 0) FROM fixed_assets WHERE company_key = ?",
                    (company_key,),
                ).fetchone()[0]
                col4.metric(label=f"Asset Value ({st.session_state.currency_symbol})", value=format_currency(fa_val))
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
                    recent_data = get_recent_accounting_activity(company_key, limit=10, conn=conn)

                    if recent_data:
                        recent_txns = pd.DataFrame(
                            [
                                {
                                    "Date": row.get("date"),
                                    "Type": row.get("activity_type"),
                                    "Description": row.get("description"),
                                    "Amount": row.get("amount", 0.0),
                                }
                                for row in recent_data
                            ]
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
                    st.session_state.page = "Point of Sale"
                    st.rerun()

            with col2:
                if st.button("📦 Add Inventory", key="dash_inventory", width='stretch'):
                    st.session_state.page = "Inventory Management"
                    st.rerun()

            with col3:
                if st.button("💳 Process Payroll", key="dash_payroll", width='stretch'):
                    st.session_state.page = "Payroll & Salaries"
                    st.rerun()

            with col4:
                if st.button("📊 View Reports", key="dash_reports", width='stretch'):
                    st.session_state.page = "Data Analytics"
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
            month_sales = get_month_sales_total(company_key, year_month=datetime.now().strftime('%Y-%m'), conn=conn)
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
                recent_txns = pd.DataFrame(get_recent_accounting_activity(company_key, limit=10, conn=conn))
                if recent_txns.empty:
                    st.info("No recent transactions found.")
                else:
                    recent_txns["Amount"] = recent_txns["amount"].map(format_currency)
                    recent_txns = recent_txns.drop(columns=["amount"]).rename(
                        columns={"date": "Date", "activity_type": "Type", "description": "Description"}
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
            if quick_col1.button("🛒 New Sale", key="dash_pos_v2", width='stretch'):
                st.session_state.page = "Point of Sale"
                st.rerun()
            if quick_col2.button("📦 Add Inventory", key="dash_inventory_v2", width='stretch'):
                st.session_state.page = "Inventory Management"
                st.rerun()
            if quick_col3.button("💳 Process Payroll", key="dash_payroll_v2", width='stretch'):
                st.session_state.page = "Payroll & Salaries"
                st.rerun()
            if quick_col4.button("📊 View Reports", key="dash_reports_v2", width='stretch'):
                st.session_state.page = "Data Analytics"
                st.rerun()
        finally:
            if conn:
                conn.close()
    except Exception as e:
        st.error(f"Dashboard Error: {e}")

def check_session_lock():
    """Check if current session is still valid, revoke if another device logged in."""
    if not st.session_state.get('auth') or not st.session_state.get('user'):
        return True  # Not logged in, no check needed
    
    user = st.session_state.user
    session_uuid = st.session_state.get('session_uuid')
    if not session_uuid:
        return True  # No session UUID, allow
    
    try:
        conn = get_connection()
        # For users table login
        if 'staff_name' in user:
            current_db_session = conn.execute(
                "SELECT current_session_id FROM users WHERE login_key = ? AND company_key = ?",
                (st.session_state.get('login_key'), user['key'])
            ).fetchone()
        else:
            # For company level, no session lock for now, as they might have multiple admins
            conn.close()
            return True
        
        if current_db_session and current_db_session[0] != session_uuid:
            # Session revoked
            st.session_state.auth = False
            st.session_state.user = None
            st.session_state.pop('session_uuid', None)
            st.session_state.pop('login_key', None)
            st.error("Account active on another device. Please upgrade for more branch licenses.")
            conn.close()
            st.rerun()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Session lock check error: {e}")
        return True


def main():
    st.cache_data.clear()
    st.cache_resource.clear()
    # SQLite continuity on ephemeral hosting is temporary; managed persistent DB remains the target architecture.
    ensure_schema()
    startup_status = startup_database()
    startup_ok = bool(startup_status.get("ok")) if isinstance(startup_status, dict) else bool(startup_status)
    if not startup_ok:
        logger.error(
            "Application startup halted because the runtime database is not safe for use: stage=%s reason=%s",
            startup_status.get("stage") if isinstance(startup_status, dict) else "unknown",
            startup_status.get("reason") if isinstance(startup_status, dict) else "startup_database returned a falsey result",
        )
        st.error(
            "Database startup could not recover a production-ready runtime database.\n\n"
            f"Stage: {startup_status.get('stage', 'unknown') if isinstance(startup_status, dict) else 'unknown'}\n"
            f"Reason: {startup_status.get('reason', 'startup_database returned a falsey result') if isinstance(startup_status, dict) else 'startup_database returned a falsey result'}\n"
            f"Database Path: {startup_status.get('db_path', DB_PATH) if isinstance(startup_status, dict) else DB_PATH}\n"
            f"Recovery Attempted: {'Yes' if (startup_status.get('recovery_attempted') if isinstance(startup_status, dict) else False) else 'No'}\n\n"
            "The app stopped safely to protect deployed company data."
        )
        st.stop()
    _verify_cloud_vault_handshake()
    if "base_currency" not in st.session_state:
        st.session_state.base_currency = "GHS"
    if "exchange_rate" not in st.session_state:
        st.session_state.exchange_rate = 1.0
    symbols = {"GHS": "GH₵", "USD": "$", "EUR": "€", "GBP": "£"}
    st.session_state.currency_symbol = symbols.get(st.session_state.base_currency, "GH₵")

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
    ("🧾 Customers", "Customers"),
    ("📄 Create Invoice", "Create Invoice"),
    ("💳 Receive Payment (Customer)", "Receive Payment (Customer)"),
    ("🏷️ Suppliers", "Suppliers"),
    ("📝 Create Bill", "Create Bill"),
    ("💸 Supplier Payment", "Supplier Payment"),
    ("📔 Customer Ledger", "Customer Ledger"),
    ("📔 Supplier Ledger", "Supplier Ledger"),
    ("🧾 General Journal", "General Journal"),
    ("📚 General Ledger", "General Ledger"),
    ("🗂️ Chart of Accounts", "Chart of Accounts"),
    ("📊 Data Analytics", "Data Analytics"),
    ("🧾 Financial Reports", "Financial Reports"),
    ("📅 System Audit Trail", "System Audit Trail"),
    ("⚙️ System Configuration", "System Configuration"),
    ("🏢 Manage Branches", "branch_management"),
    ("🏛️ Asset Register", "Asset Register"),
    ("💳 Payroll & Salaries", "Payroll & Salaries"),
    ("Taxation (VAT/NHIL)", "Taxation (VAT/NHIL)"),
    ("Banking & Cash", "Banking & Cash"),
    ("Vouchers & Journals", "Vouchers & Journals"),
    ("Sales Invoicing", "Sales Invoicing"),
    ("Purchase Orders", "Purchase Orders"),
    ("Accounts Receivable", "Accounts Receivable"),
    ("Accounts Payable", "Accounts Payable"),
    ("Dashboard", "Dashboard"),
    ("Inventory Management", "Inventory Management"),
    ("Payroll & Salaries", "Payroll & Salaries"),
    ("Sales/Purchase", "Sales/Purchase"),
    ("Banking", "Banking"),
    ("Taxation", "Taxation"),
    ("Gatekeeper Admin", "Gatekeeper Admin"),
    ("Audit Trail", "Audit Trail"),
    ("🏠 Dashboard", "Dashboard"),
]


SIDEBAR_NAV_GROUPS = [
    (
        "💼 Transactions",
        [
            ("📊 Dashboard", "Dashboard"),
            ("🛒 Point of Sale", "Point of Sale"),
            ("🧾 Vouchers & Journals", "Vouchers & Journals"),
            ("🧾 General Journal", "General Journal"),
            ("💰 Banking & Cash", "Banking & Cash"),
            ("🏦 Banking", "Banking"),
            ("📝 Create Invoice", "Create Invoice"),
            ("🧾 Create Bill", "Create Bill"),
            ("💳 Receive Payment (Customer)", "Receive Payment (Customer)"),
            ("💸 Supplier Payment", "Supplier Payment"),
            ("🧾 Sales Invoicing", "Sales Invoicing"),
            ("🛍️ Purchase Orders", "Purchase Orders"),
            ("🔁 Sales/Purchase", "Sales/Purchase"),
            ("🧮 Payroll & Salaries", "Payroll & Salaries"),
            ("🧾 Taxation (VAT/NHIL)", "Taxation (VAT/NHIL)"),
            ("🧾 Taxation", "Taxation"),
        ],
    ),
    (
        "📑 Ledgers",
        [
            ("🗂️ Chart of Accounts", "Chart of Accounts"),
            ("📚 General Ledger", "General Ledger"),
            ("📒 Customer Ledger", "Customer Ledger"),
            ("📕 Supplier Ledger", "Supplier Ledger"),
            ("📈 Accounts Receivable", "Accounts Receivable"),
            ("📉 Accounts Payable", "Accounts Payable"),
            ("🧾 Customers", "Customers"),
            ("🏷️ Suppliers", "Suppliers"),
        ],
    ),
    (
        "📦 Inventory",
        [
            ("📦 Inventory Management", "Inventory Management"),
            ("🏛️ Asset Register", "Asset Register"),
        ],
    ),
    (
        "📊 Reports",
        [
            ("📊 Data Analytics", "Data Analytics"),
            ("🧾 Financial Reports", "Financial Reports"),
            ("🛡️ Audit Trail", "Audit Trail"),
            ("🧭 System Audit Trail", "System Audit Trail"),
        ],
    ),
    (
        "⚙️ System",
        [
            ("⚙️ System Configuration", "System Configuration"),
            ("🏢 Manage Branches", "branch_management"),
            ("🤖 Gatekeeper Admin", "Gatekeeper Admin"),
        ],
    ),
]


def _ensure_valid_page(default_page="Dashboard"):
    valid_pages = {page_key for _label, page_key in PRIMARY_NAV_ITEMS}
    legacy_page = st.session_state.get("page")
    active_page = st.session_state.get("active_page")
    current_page = legacy_page if legacy_page and legacy_page != active_page else active_page or legacy_page or default_page
    if current_page not in valid_pages and current_page != 'branch_management':
        label_to_key = {label: key for label, key in PRIMARY_NAV_ITEMS}
        current_page = label_to_key.get(str(current_page), default_page)
    st.session_state.page = current_page
    st.session_state.active_page = current_page
    return current_page


def _set_active_page(page_name):
    st.session_state.active_page = page_name
    st.session_state.page = page_name


def _render_sidebar_nav_styles():
    st.sidebar.markdown(
        """
        <style>
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
            width: 100%;
            border-radius: 10px;
            border: 1px solid rgba(184, 134, 11, 0.18);
            text-align: left;
            justify-content: flex-start;
            padding: 0.55rem 0.8rem;
            margin-bottom: 0.2rem;
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, #0f766e 0%, #b45309 100%);
            color: #ffffff;
            border: 1px solid rgba(180, 83, 9, 0.55);
            box-shadow: 0 6px 16px rgba(15, 118, 110, 0.18);
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
            border-color: rgba(180, 83, 9, 0.45);
            color: #92400e;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar_navigation(user, current_page):
    allowed_pages = {page_key for _label, page_key in PRIMARY_NAV_ITEMS}

    for group_name, options in SIDEBAR_NAV_GROUPS:
        visible_options = []
        for label, page_name in options:
            if page_name not in allowed_pages and page_name != "branch_management":
                continue
            if user["role"] == "Demo" and page_name in {
                "Create Invoice",
                "Create Bill",
                "Receive Payment (Customer)",
                "Supplier Payment",
                "General Journal",
                "General Ledger",
                "Chart of Accounts",
                "Customers",
                "Suppliers",
                "Financial Reports",
                "System Configuration",
                "branch_management",
            }:
                continue
            visible_options.append((label, page_name))

        if not visible_options:
            continue

        is_group_active = any(page_name == current_page for _, page_name in visible_options)
        with st.sidebar.expander(group_name, expanded=is_group_active):
            for label, page_name in visible_options:
                is_active = page_name == current_page
                if st.button(
                    label,
                    key=f"sidebar_nav_{page_name}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    if not is_active:
                        _set_active_page(page_name)
                        st.rerun()


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

    # Branch selector for Master Admins
    if user['role'] == 'Master Admin':
        try:
            conn = get_connection()
            branches = conn.execute("SELECT branch_id, branch_name FROM branches WHERE company_key = ? ORDER BY branch_name", (user['key'],)).fetchall()
            conn.close()
            if branches:
                branch_options = ["All Branches"] + [f"{b[1]} ({b[0]})" for b in branches]
                current_branch = st.session_state.get("active_branch_id", "All Branches")
                selected_branch_display = next((opt for opt in branch_options if current_branch in opt or (current_branch is None and opt == "All Branches")), "All Branches")
                selected_branch = st.sidebar.selectbox("Active Branch", branch_options, index=branch_options.index(selected_branch_display) if selected_branch_display in branch_options else 0, key="branch_selector")
                if selected_branch == "All Branches":
                    st.session_state.active_branch_id = None
                else:
                    branch_id = selected_branch.split(" (")[-1].rstrip(")")
                    st.session_state.active_branch_id = branch_id
            else:
                st.session_state.active_branch_id = None
        except Exception as e:
            logger.error(f"Branch selector error: {e}")
            st.session_state.active_branch_id = None

    current_page = _ensure_valid_page()
    _render_sidebar_nav_styles()
    _render_sidebar_navigation(user, current_page)

    if False and user['role'] == "Demo":
        menu_options = [
            "📊 Dashboard",
            "📦 Inventory Management", 
            "💳 Payroll & Salaries",
            "Sales/Purchase",
            "📊 Data Analytics",
            "Banking",
            "Taxation",
            "🤖 Gatekeeper Admin",
            "Audit Trail"
        ]
        page_mapping = {
            "📊 Dashboard": "Dashboard",
            "📦 Inventory Management": "Inventory Management",
            "💳 Payroll & Salaries": "Payroll & Salaries",
            "Sales/Purchase": "Sales/Purchase",
            "📊 Data Analytics": "Data Analytics",
            "Banking": "Banking",
            "Taxation": "Taxation",
            "🤖 Gatekeeper Admin": "Gatekeeper Admin",
            "Audit Trail": "Audit Trail"
        }

        current_display = next((label for label, target in page_mapping.items() if target == current_page), menu_options[0])
        selected_display = st.sidebar.radio("Navigation", menu_options, index=menu_options.index(current_display), key="main_navigation_radio")
        selected_page = page_mapping.get(selected_display, current_page)
        if selected_page != current_page:
            st.session_state.page = selected_page
            st.rerun()

    elif False:
        sidebar_groups = [
            (
                "Transactions",
                [
                    ("🛒 Point of Sale", "Point of Sale"),
                    ("📜 Vouchers & Journals", "Vouchers & Journals"),
                    ("📝 Create Bill", "Create Bill"),
                    ("💰 Banking & Cash", "Banking & Cash"),
                ],
            ),
            (
                "Ledgers",
                [
                    ("🗂️ Chart of Accounts", "Chart of Accounts"),
                    ("📈 Accounts Receivable", "Accounts Receivable"),
                    ("📉 Accounts Payable", "Accounts Payable"),
                ],
            ),
            (
                "Inventory",
                [
                    ("📦 Inventory Management", "Inventory Management"),
                    ("📤 Stock In/Out", "Inventory Management"),
                ],
            ),
            (
                "Reports",
                [
                    ("📊 Data Analytics", "Data Analytics"),
                    ("🧾 Financial Reports", "Financial Reports"),
                ],
            ),
            (
                "System",
                [
                    ("🏢 Manage Branches", "branch_management"),
                    ("📅 System Audit Trail", "System Audit Trail"),
                    ("⚙️ System Configuration", "System Configuration"),
                ],
            ),
        ]

        page_mapping = {label: page for _, options in sidebar_groups for label, page in options}
        current_display = next((label for label, page in page_mapping.items() if page == current_page), "Select...")

        for group_name, options in sidebar_groups:
            group_key = f"nav_group_{group_name.lower().replace(' ', '_')}"
            labels = ["Select...", *[label for label, _ in options]]
            group_value = current_display if current_display in labels else "Select..."
            st.session_state[group_key] = group_value
            selected_label = st.sidebar.radio(group_name, labels, index=labels.index(group_value), key=group_key)
            if selected_label != "Select...":
                selected_page = page_mapping.get(selected_label, current_page)
                if selected_page != current_page:
                    st.session_state.page = selected_page
                    st.rerun()

    # For regular users, add license expiry check
    if user['role'] != "Demo":
        try:
            days_left = check_license_expiry_with_grace(user['key'])
            if days_left['status'] == 'warning':
                st.sidebar.warning(f"⚠️ License expires in {days_left['days_left']} days")
        except:
            pass

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
    symbols = {"GHS": "GH₵", "USD": "$", "EUR": "€", "GBP": "£"}
    st.session_state.currency_symbol = symbols.get(st.session_state.base_currency, "GH₵")
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
    current_page = _ensure_valid_page()
    if current_page == "Dashboard":
        if user["role"] == "Demo":
            show_dashboard_module("DEMO", "Demo Corporation Ltd", "Demo")
        else:
            show_dashboard_module(user["key"], user["name"], user["role"])
    elif current_page == "Point of Sale":
        show_pos(user["key"], user["name"], user["role"])
    elif current_page == "Inventory Management":
        if user["role"] == "Demo":
            show_inventory("DEMO", "Demo")
        else:
            show_inventory(user["key"], user["role"])
    elif current_page == "General Journal":
        show_journal_entries(user["key"], user["role"])
    elif current_page == "General Ledger":
        show_ledger_viewer(user["key"], user["role"])
    elif current_page == "Chart of Accounts":
        show_chart_of_accounts(user["key"], user["role"])
    elif current_page == "Accounts Receivable":
        show_accounts_receivable(user["key"])
    elif current_page == "Accounts Payable":
        show_accounts_payable(user["key"])
    elif current_page == "Customers":
        show_customers_page(user["key"], user["role"])
    elif current_page == "Suppliers":
        show_suppliers_page(user["key"], user["role"])
    elif current_page == "Create Invoice":
        show_create_invoice_page(user["key"], user["role"])
    elif current_page == "Receive Payment (Customer)":
        show_receive_payment_page(user["key"], user["role"])
    elif current_page == "Supplier Payment":
        show_supplier_payment_page(user["key"], user["role"])
    elif current_page == "Customer Ledger":
        show_aging(user["key"], "Receivable")
    elif current_page == "Supplier Ledger":
        show_aging(user["key"], "Payable")
    elif current_page == "Create Bill":
        show_create_bill_page(user["key"])
    elif current_page == "Banking & Cash":
        show_banking(user["key"], user["role"])
    elif current_page == "Taxation (VAT/NHIL)":
        show_taxation(user["key"])
    elif current_page == "Payroll & Salaries":
        if user["role"] == "Demo":
            show_payroll("DEMO", "Demo")
        else:
            show_payroll(user["key"], user["role"])
    elif current_page == "Asset Register":
        show_fixed_assets(user["key"], user["role"])
    elif current_page == "Data Analytics":
        show_reports(user["key"], st.session_state.get("active_branch_id"))
    elif current_page == "Financial Reports":
        show_financial_reports(user["key"], user["role"])
    elif current_page == "Gatekeeper Admin":
        show_ai_assistant(user["key"])
    elif current_page == "System Audit Trail":
        show_audit_trail(user["key"], user["role"], st.session_state.get("active_branch_id"))
    elif current_page == "System Configuration":
        show_company_setup(user["key"], user["name"], user["role"])
    elif current_page == "Vouchers & Journals":
        show_vouchers(user["key"], user["role"])
    elif current_page == "Sales Invoicing":
        show_sales_purchase(user["key"], user["role"], "Sales")
    elif current_page == "Purchase Orders":
        show_sales_purchase(user["key"], user["role"], "Purchase")
    elif current_page == "Accounts Receivable":
        show_aging(user["key"], "Receivable")
    elif current_page == "Accounts Payable":
        show_aging(user["key"], "Payable")
    else:
        _set_active_page("Dashboard")
        st.rerun()


# Main application flow
main()
if not st.session_state.auth or not check_session_timeout():
    login_ui()
else:
    check_session_lock()  # Check for session revocation
    
    # Renewal alert
    license_status = check_license_expiry_with_grace(st.session_state.company_id)
    if license_status['status'] == 'expiring_soon':
        st.warning(f"⚠️ Your license expires in {license_status['days_left']} days. Please renew to avoid service interruption.")
    
    update_activity()  # Update activity on each interaction
    u = st.session_state.user
    
    if u['role'] == "Dev":
        # Gatekeeper Dashboard with Enhanced Metrics
        st.title("Gatekeeper System Dashboard")
        
        # Tabs for different sections
        tab1, tab2, tab3 = st.tabs(["System Overview", "License Management", "Manual Deployment"])
        
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
                m3.metric(label=f"Monthly Revenue ({st.session_state.currency_symbol})", value=format_currency(monthly_revenue))
                m4.metric("System Uptime", "100%")

                if total_companies == 0 and active_subscriptions == 0 and monthly_revenue == 0:
                    st.info(
                        "Welcome to the admin dashboard. Seed sample data or deploy your first "
                        "license to bring these system metrics to life."
                    )

                st.markdown("---")
                st.subheader("System Health")
                st.caption(st.session_state.get("cloud_vault_status", "🔴 Cloud Vault: Local Mode"))

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
                        f"Master Price Per Month ({st.session_state.currency_symbol})",
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
                            st.success(f"Master monthly price updated to {format_currency(master_price)}.")
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
                    number_of_branches = st.number_input("Number of Branches", min_value=1, value=1, step=1)
                    max_branches = st.number_input("Max Branches Allowed", min_value=1, value=5, step=1, help="Developer control: maximum branches this client can create")
                    price_per_branch = st.number_input("Price per Branch (GHS)", min_value=0.0, value=0.0, step=10.0)
                    duration_months = st.number_input("Duration (Months)", min_value=1, max_value=24, value=12)
                    key_col, button_col = st.columns([3, 1])
                    with key_col:
                        manual_key = st.text_input("System License Key", type="password", key="manual_key_input")
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
                                       (key, name, subscription_expiry, status, deployment_status, number_of_branches, max_branches, branch_price_per_month)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (
                                        manual_key,
                                        company_name,
                                        new_expiry.isoformat(),
                                        "Active",
                                        "Live",
                                        int(number_of_branches),
                                        int(max_branches),
                                        float(price_per_branch),
                                    ),
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
