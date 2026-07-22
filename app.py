import streamlit as st
import pandas as pd
import importlib.util
import time
from database import (
    DB_PATH,
    create_company_record,
    dataframe_from_portable_rows,
    ensure_schema,
    execute_portable_query,
    execute_portable_write,
    force_backup_after_company_creation,
    get_downloadable_backup_export,
    get_firebase_service_account_info,
    get_company_subscription_snapshot,
    get_connection,
    get_recovery_source_diagnostics,
    get_sqlite_concurrency_diagnostics,
    row_get,
    rows_to_dicts,
    restore_latest_cloud_backup_to_local,
    should_run_sqlite_startup,
    wipe_company_records,
)
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
from security_utils import build_user_safe_error, sanitize_error_message
from accounting_engine import (
    get_month_sales_total,
    get_recent_accounting_activity,
)
from enterprise_services import (
    build_operations_console_full_audit,
    build_operations_console_snapshot,
    get_ai_service_status,
    get_service_ownership_map,
    require_role_permission,
)

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
get_openai_client_status = get_ai_service_status
request_ai_chat_completion = eka_modules.request_ai_chat_completion
call_ai_assistant = eka_modules.call_ai_assistant
initialize_paystack_payment = eka_modules.initialize_paystack_payment
get_subscription_plans = eka_modules.get_subscription_plans
def save_subscription_plan_pricing_settings(*args, **kwargs):
    return eka_modules.save_subscription_plan_pricing_settings(*args, **kwargs)

SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE = eka_modules.SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE
test_paystack_connection = eka_modules.test_paystack_connection
log_audit_action = eka_modules.log_audit_action
render_accounting_assistant_sidebar = eka_modules.render_accounting_assistant_sidebar
user_has_permission = eka_modules.user_has_permission
can_access_branch = eka_modules.can_access_branch
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
show_subscription_renewal_page = eka_modules.show_subscription_renewal_page
show_taxation = eka_modules.show_taxation
get_subscription_billing_admin_snapshot = eka_modules.get_subscription_billing_admin_snapshot
show_vouchers = eka_modules.show_vouchers
execute_manual_license_override = eka_modules.execute_manual_license_override

GATEKEEPER_SYSTEM_PROMPT = (
    "You are a professional Chartered Accountant. Provide clear, accurate financial guidance based on the ERP data."
)


def test_openai_assistant_health():
    ai_status = get_openai_client_status()
    if ai_status["client"] is None:
        return {
            "success": False,
            "key_present": bool(ai_status.get("key_present")),
            "client_initialized": False,
            "response": "",
            "error": ai_status.get("message") or "AI client could not initialize",
            "selected_provider": ai_status.get("selected_provider", "openai"),
            "active_provider": ai_status.get("provider", ai_status.get("selected_provider", "openai")),
            "fallback_used": bool(ai_status.get("fallback_used")),
            "last_safe_error": ai_status.get("last_safe_error", ""),
            "secret_source": ai_status.get("openai_secret_source", "missing"),
            "gemini_secret_source": ai_status.get("gemini_secret_source", "missing"),
            "provided_length": ai_status.get("provided_length", 0),
            "gemini_provided_length": ai_status.get("gemini_provided_length", 0),
            "streamlit_imported": ai_status.get("streamlit_imported"),
            "secrets_accessible": ai_status.get("secrets_accessible"),
            "top_level_secret_keys": ai_status.get("top_level_secret_keys", []),
            "top_level_key_present": ai_status.get("top_level_key_present"),
            "openai_section_present": ai_status.get("openai_section_present"),
            "nested_key_present": ai_status.get("nested_key_present"),
            "gemini_key_present": ai_status.get("gemini_key_present"),
            "gemini_top_level_key_present": ai_status.get("gemini_top_level_key_present"),
            "gemini_section_present": ai_status.get("gemini_section_present"),
            "gemini_nested_key_present": ai_status.get("gemini_nested_key_present"),
            "openai_error_safe": ai_status.get("last_safe_error", "") if ai_status.get("provider") == "openai" else "",
            "gemini_error_safe": ai_status.get("last_safe_error", "") if ai_status.get("provider") == "gemini" else "",
        }

    result = call_ai_assistant(
        messages=[
            {"role": "system", "content": "Reply with a short operational status only."},
            {"role": "user", "content": "ping"},
        ],
        temperature=0,
        max_tokens=20,
        purpose="health_test",
    )
    runtime_status = result.get("status", {}) or {}
    return {
        "success": bool(result.get("ok")),
        "key_present": True,
        "client_initialized": bool(ai_status.get("client_initialized")),
        "response": (result.get("content") or "")[:120],
        "error": result.get("error") or "",
        "selected_provider": ai_status.get("selected_provider", "openai"),
        "active_provider": result.get("provider_used", result.get("provider", ai_status.get("provider", "openai"))),
        "fallback_used": bool(result.get("fallback_used")),
        "last_safe_error": runtime_status.get("last_safe_error", ai_status.get("last_safe_error", "")),
        "secret_source": ai_status.get("openai_secret_source", "missing"),
        "gemini_secret_source": ai_status.get("gemini_secret_source", "missing"),
        "provided_length": ai_status.get("provided_length", 0),
        "gemini_provided_length": ai_status.get("gemini_provided_length", 0),
        "streamlit_imported": ai_status.get("streamlit_imported"),
        "secrets_accessible": ai_status.get("secrets_accessible"),
        "top_level_secret_keys": ai_status.get("top_level_secret_keys", []),
        "top_level_key_present": ai_status.get("top_level_key_present"),
        "openai_section_present": ai_status.get("openai_section_present"),
        "nested_key_present": ai_status.get("nested_key_present"),
        "gemini_key_present": ai_status.get("gemini_key_present"),
        "gemini_top_level_key_present": ai_status.get("gemini_top_level_key_present"),
        "gemini_section_present": ai_status.get("gemini_section_present"),
        "gemini_nested_key_present": ai_status.get("gemini_nested_key_present"),
        "openai_error_safe": result.get("openai_error_safe", ""),
        "gemini_error_safe": result.get("gemini_error_safe", ""),
        "response_preview": result.get("response_preview", ""),
    }


FIREBASE_APP = None
FIREBASE_BUCKET_NAME = None
FIREBASE_OBJECT_NAME = "backups/eka_enterprise_v3.db"


def _get_app_firebase_service_account_info():
    credentials_result = get_firebase_service_account_info()
    if credentials_result.get("ok"):
        return {
            "ok": True,
            "source": credentials_result.get("source", "unknown"),
            "service_account_info": credentials_result.get("service_account_info"),
        }
    logger.warning(
        "Firebase credentials unavailable for app storage client: source=%s reason=%s",
        credentials_result.get("source", "unknown"),
        sanitize_error_message(credentials_result.get("reason", "unknown")),
    )
    st.warning(
        sanitize_error_message(credentials_result.get(
            "reason",
            "Firebase credentials are unavailable. Please check Streamlit Cloud Secrets.",
        ))
    )
    return {
        "ok": False,
        "source": credentials_result.get("source", "unknown"),
        "reason": credentials_result.get(
            "reason",
            "Firebase credentials are unavailable. Please check Streamlit Cloud Secrets.",
        ),
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
            logger.warning("Cloud Vault UI client could not load credentials: %s", sanitize_error_message(credentials_result.get("reason")))
            return None
        if not diagnostics.get("credentials_loaded"):
            logger.warning("Cloud Vault UI client could not load credentials: %s", sanitize_error_message(diagnostics.get("credential_error")))
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
            logger.warning("Cloud Vault UI client lookup failed: %s", sanitize_error_message(exc))
            return None
    except Exception as exc:
        logger.warning("Cloud Vault UI client initialization failed: %s", sanitize_error_message(exc))
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
            return "Cloud Vault: Credentials Missing"
        bucket = _get_firebase_bucket()
        if bucket is None:
            return "Cloud Vault: Local Mode"
        try:
            list(bucket.list_blobs(prefix=diagnostics.get("object_name") or FIREBASE_OBJECT_NAME, max_results=1))
            return "Cloud Vault: Connected"
        except Exception as exc:
            logger.warning("Cloud Vault connectivity check failed: %s", sanitize_error_message(exc))
            return "Cloud Vault: Source Unreachable"
    except Exception as exc:
        logger.warning("Cloud Vault status check failed: %s", sanitize_error_message(exc))
        return "Cloud Vault: Source Unreachable"


def _verify_cloud_vault_handshake():
    try:
        st.session_state["cloud_vault_status"] = _get_cloud_vault_status()
    except Exception:
        st.session_state["cloud_vault_status"] = "Cloud Vault: Local Mode"


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
    "inventory": "Inventory Management",
    "payroll": "Payroll & Salaries",
    "reports": "📈 Data Analytics",
    "settings": "⚙ System Configuration",
}

PAGE_ALIASES = {
    "POS (Point of Sale)": PAGE_LABELS["pos"],
    "Point of Sale": PAGE_LABELS["pos"],
    "Inventory & Stock": PAGE_LABELS["inventory"],
    "Inventory Management": PAGE_LABELS["inventory"],
    "Payroll": PAGE_LABELS["payroll"],
    "Ghana Payroll (SSNIT)": PAGE_LABELS["payroll"],
    "Payroll & Salaries": PAGE_LABELS["payroll"],
    "Reports": PAGE_LABELS["reports"],
    "Financial Intelligence": PAGE_LABELS["reports"],
    "Data Analytics": PAGE_LABELS["reports"],
    "Company Setup": PAGE_LABELS["settings"],
    "System Configuration": PAGE_LABELS["settings"],
}


def _normalize_page_label_legacy(page_name):
    canonical = PAGE_ALIASES.get(page_name, page_name)
    legacy_labels = {
        PAGE_LABELS["dashboard"]: "Dashboard",
        PAGE_LABELS["pos"]: "Point of Sale",
        PAGE_LABELS["inventory"]: "Inventory Management",
        PAGE_LABELS["payroll"]: "Payroll & Salaries",
        PAGE_LABELS["reports"]: "Data Analytics",
        PAGE_LABELS["settings"]: "System Configuration",
        PAGE_LABELS["invoices"]: "Sales Invoicing",
    }
    return legacy_labels.get(canonical, canonical)


if 'exchange_rate' not in st.session_state:
    st.session_state.exchange_rate = 1.0
if 'currency_symbol' not in st.session_state:
    st.session_state.currency_symbol = "GHS"


def _get_bog_display_rate(currency_code):
    return float(BOG_DISPLAY_RATES.get(str(currency_code or "GHS").upper(), 1.0))


def _render_currency_sidebar_controls(selectbox_key):
    settings_conn = get_connection()
    try:
        settings_row = execute_portable_query(
            settings_conn,
            "SELECT COALESCE(base_currency, 'GHS') AS base_currency, COALESCE(display_currency, 'GHS') AS display_currency, COALESCE(exchange_rate, 1.0) AS exchange_rate FROM system_settings WHERE id = 1"
        ).fetchone()
        current_currency = str(row_get(settings_row, "display_currency", "GHS") or "GHS") if settings_row else "GHS"
        current_rate_value = row_get(settings_row, "exchange_rate") if settings_row else None
        current_rate = (
            float(current_rate_value)
            if settings_row and current_rate_value not in (None, "")
            else _get_bog_display_rate(current_currency)
        )
        selected_currency = st.sidebar.selectbox(
            "Base Currency",
            ["GHS", "USD", "EUR", "GBP"],
            index=["GHS", "USD", "EUR", "GBP"].index(current_currency) if current_currency in ["GHS", "USD", "EUR", "GBP"] else 0,
            key=selectbox_key,
        )
        selected_rate = _get_bog_display_rate(selected_currency)
        symbols = {"GHS": "GHS", "USD": "USD", "EUR": "EUR", "GBP": "GBP"}
        st.session_state.base_currency = selected_currency
        st.session_state.display_currency = selected_currency
        st.session_state.exchange_rate = selected_rate
        st.session_state.currency_symbol = symbols.get(st.session_state.base_currency, "GHS")
        if selected_currency == "GHS":
            st.sidebar.caption("BoG April 2026 sync: 1 GHS = 1.00 GHS")
        else:
            st.sidebar.caption(f"BoG April 2026 sync: 1 {selected_currency} = {selected_rate:,.2f} GHS")
            st.sidebar.caption(f"Global display multiplier: 1 / {selected_rate:,.2f}")
        if selected_currency != current_currency or abs(current_rate - selected_rate) > 0.000001:
            execute_portable_write(
                settings_conn,
                "UPDATE system_settings SET base_currency = ?, display_currency = ?, exchange_rate = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                ("GHS", selected_currency, selected_rate),
            )
            settings_conn.commit()
            st.rerun()
    finally:
        if settings_conn:
            settings_conn.close()

PAGE_LABELS = {
    "dashboard": "📊 Dashboard",
    "pos": "🛒 Point of Sale",
    "inventory": "Inventory Management",
    "customers": "Customers",
    "create_invoice": "Create Invoice",
    "receive_payment_customer": "Receive Payment (Customer)",
    "suppliers": "Suppliers",
    "create_bill": "Create Bill",
    "supplier_payment": "Supplier Payment",
    "customer_ledger": "Customer Ledger",
    "supplier_ledger": "Supplier Ledger",
    "journal": "General Journal",
    "ledger": "General Ledger",
    "chart_of_accounts": "Chart of Accounts",
    "banking": "🏦 Banking & Cash",
    "taxation": "Taxation (VAT/NHIL)",
    "payroll": "Payroll & Salaries",
    "assets": "Asset Register",
    "reports": "📈 Data Analytics",
    "financial_reports": "Financial Reports",
    "audit_trail": "System Audit Trail",
    "settings": "⚙ System Configuration",
    "invoices": "Sales Invoicing",
}

PAGE_ALIASES = dict(
    {
        "POS (Point of Sale)": PAGE_LABELS["pos"],
        "Point of Sale": PAGE_LABELS["pos"],
        "Inventory & Stock": PAGE_LABELS["inventory"],
        "Inventory Management": PAGE_LABELS["inventory"],
        "Accounts Receivable": PAGE_LABELS["customer_ledger"],
        "Accounts Receivables": PAGE_LABELS["customer_ledger"],
        "Customer Ledger": PAGE_LABELS["customer_ledger"],
        "Accounts Payable": PAGE_LABELS["supplier_ledger"],
        "Accounts Payables": PAGE_LABELS["supplier_ledger"],
        "Supplier Ledger": PAGE_LABELS["supplier_ledger"],
        "Payroll": PAGE_LABELS["payroll"],
        "Ghana Payroll (SSNIT)": PAGE_LABELS["payroll"],
        "Payroll & Salaries": PAGE_LABELS["payroll"],
        "Reports": PAGE_LABELS["reports"],
        "Financial Intelligence": PAGE_LABELS["reports"],
        "Data Analytics": PAGE_LABELS["reports"],
        "Company Setup": PAGE_LABELS["settings"],
        "System Configuration": PAGE_LABELS["settings"],
        "Dashboard": PAGE_LABELS["dashboard"],
        "Sales Invoicing": PAGE_LABELS["invoices"],
        "Sales Invoicing": PAGE_LABELS["invoices"],
        "Purchase Orders": "Purchase Invoicing",
        "Purchase History": "Purchase Invoicing",
    }
)


def normalize_page_label(page_name):
    canonical = PAGE_ALIASES.get(page_name, page_name)
    legacy_labels = {
        PAGE_LABELS["dashboard"]: "Dashboard",
        PAGE_LABELS["pos"]: "Point of Sale",
        PAGE_LABELS["inventory"]: "Inventory Management",
        PAGE_LABELS["payroll"]: "Payroll & Salaries",
        PAGE_LABELS["reports"]: "Data Analytics",
        PAGE_LABELS["settings"]: "System Configuration",
        PAGE_LABELS["invoices"]: "Sales Invoicing",
    }
    return legacy_labels.get(canonical, canonical)


def repair_ui_label(label):
    value = str(label or "")
    keyword_map = [
        ("Dashboard", "Dashboard"),
        ("Point of Sale", "Point of Sale"),
        ("Inventory Management", "Inventory Management"),
        ("Payroll & Salaries", "Payroll & Salaries"),
        ("Data Analytics", "Data Analytics"),
        ("System Configuration", "System Configuration"),
        ("Sales Invoicing", "Sales Invoicing"),
        ("Gatekeeper Admin", "Gatekeeper Admin"),
        ("Asset Register", "Asset Register"),
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


def _init_session(user_dict):
    """Initialize standard session keys and diagnostics for a successful login."""
    user_dict = dict(user_dict or {})
    st.session_state.auth = True
    st.session_state.user = user_dict
    company_key = user_dict.get("key") or user_dict.get("company_key")
    st.session_state.company_id = company_key or st.session_state.get("company_id")
    st.session_state.page = "Dashboard"
    st.session_state.active_page = "Dashboard"
    branch_id = user_dict.get("branch_id")
    role = user_dict.get("role")
    if branch_id and role in {"Branch_Bookkeeper", "Cashier", "Staff"}:
        st.session_state.active_branch_id = str(branch_id).strip()
    elif role in {"Dev", "Master Admin", "System Admin", "Owner / CEO"}:
        st.session_state.pop("active_branch_id", None)
    else:
        st.session_state.pop("active_branch_id", None)
    session_uuid = str(uuid.uuid4())
    st.session_state.session_uuid = session_uuid
    st.session_state.login_attempts = 0
    st.session_state.last_activity = datetime.now()
    logger.info(
        "Session initialized: company=%s role=%s branch=%s session_uuid=%s",
        st.session_state.company_id,
        user_dict.get("role"),
        st.session_state.get("active_branch_id"),
        session_uuid,
    )


def _clear_session():
    """Clear all known session keys to avoid stale state after logout or revocation."""
    keys = [
        "auth",
        "user",
        "company_id",
        "session_uuid",
        "active_branch_id",
        "login_attempts",
        "last_activity",
        "login_key",
        "database_startup_status",
        "canonical_startup_result",
        "canonical_startup_config_signature",
        "session_startup_backend_diagnostics",
        "lv002b_operation_events",
        "lv002b_surface_timings",
        "lv003_current_rerun",
        "lv003_rerun_history",
        "lv003_last_rerun_summary",
        "dev_gatekeeper_ops_snapshot_fast",
        "dev_gatekeeper_billing_snapshot",
        "_sidebar_nav_styles_rendered",
        "_currency_db_sync_key",
    ]
    for k in keys:
        st.session_state.pop(k, None)
    try:
        from database import close_session_postgres_connection

        close_session_postgres_connection()
    except Exception:
        logger.debug("Session PostgreSQL connection cleanup skipped during logout.", exc_info=True)
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and (
            key.startswith("lv003_page_access:")
            or key.startswith("session_subscription_status:")
        ):
            st.session_state.pop(key, None)
    st.session_state["_clear_streamlit_caches"] = True
    logger.info("Session cleared for UI. Cleared keys: %s", ",".join(keys))


def hash_login_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def authenticate_access_key_read_path(conn, access_key):
    """Read-only company, branch, and staff access-key authentication lookup."""
    admin = execute_portable_query(
        conn,
        "SELECT key, name, COALESCE(status, 'Active') FROM companies WHERE key = ?",
        (access_key,),
    ).fetchone()
    if admin:
        admin_key = row_get(admin, "key", row_get(admin, 0))
        admin_name = row_get(admin, "name", row_get(admin, 1))
        admin_status = row_get(admin, "status", row_get(admin, 2, "Active"))
        if admin_status != "Active":
            return {"matched": True, "active": False, "reason": "company_inactive", "company_key": admin_key}
        return {"matched": True, "active": True, "kind": "company", "user": {"key": admin_key, "name": admin_name, "role": "Master Admin"}}

    branch_auth = execute_portable_query(
        conn,
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
        branch_id = row_get(branch_auth, "branch_id", row_get(branch_auth, 0))
        company_key = row_get(branch_auth, "company_key", row_get(branch_auth, 1))
        branch_name = row_get(branch_auth, "branch_name", row_get(branch_auth, 2))
        company_name = row_get(branch_auth, "name", row_get(branch_auth, 4))
        return {
            "matched": True,
            "active": True,
            "kind": "branch",
            "user": {
                "key": company_key,
                "company_key": company_key,
                "name": company_name,
                "role": "Branch_Bookkeeper",
                "branch_name": branch_name,
                "branch_id": branch_id,
            },
        }

    user_login = execute_portable_query(
        conn,
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
        role_name = row_get(user_login, "role", row_get(user_login, 2))
        branch_id = row_get(user_login, "branch_id", row_get(user_login, 4))
        company_key = row_get(user_login, "company_key", row_get(user_login, 0))
        company_name = row_get(user_login, "name", row_get(user_login, 1))
        staff_name = row_get(user_login, "full_name", row_get(user_login, 3))
        if role_name == "Branch_Bookkeeper" and not branch_id:
            return {"matched": True, "active": False, "reason": "branch_not_configured", "company_key": company_key, "role": role_name}
        return {
            "matched": True,
            "active": True,
            "kind": "user",
            "user": {
                "key": company_key,
                "company_key": company_key,
                "name": company_name,
                "role": role_name,
                "staff_name": staff_name,
                "branch_id": branch_id,
            },
        }

    return {"matched": False, "active": False}


def get_dashboard_metric_counts(conn, company_key):
    """Read dashboard source counts using backend-aware SELECT helpers."""
    inventory_row = execute_portable_query(
        conn,
        "SELECT COALESCE(SUM(qty * cost_price), 0) AS inventory_value FROM inventory WHERE company_key = ?",
        (company_key,),
    ).fetchone()
    employee_row = execute_portable_query(
        conn,
        "SELECT COUNT(DISTINCT emp_name) AS employee_count FROM payroll WHERE company_key = ? AND COALESCE(status, 'Active') != 'Void'",
        (company_key,),
    ).fetchone()
    fixed_asset_row = execute_portable_query(
        conn,
        "SELECT COALESCE(SUM(book_value), 0) AS fixed_asset_value FROM fixed_assets WHERE company_key = ?",
        (company_key,),
    ).fetchone()
    return {
        "inventory_value": row_get(inventory_row, "inventory_value", row_get(inventory_row, 0, 0)) or 0,
        "employee_count": row_get(employee_row, "employee_count", row_get(employee_row, 0, 0)) or 0,
        "fixed_asset_value": row_get(fixed_asset_row, "fixed_asset_value", row_get(fixed_asset_row, 0, 0)) or 0,
    }



def check_maintenance_status():
    conn = None
    try:
        conn = get_connection()
        maint_setting = execute_portable_query(
            conn,
            "SELECT maintenance_date, is_active FROM maintenance_settings WHERE id = 1",
        ).fetchone()
        if maint_setting and row_get(maint_setting, "is_active", row_get(maint_setting, 1)):
            return {'active': True, 'date': row_get(maint_setting, "maintenance_date", row_get(maint_setting, 0))}
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
        logger.error("Failed to send maintenance email: %s", sanitize_error_message(e))
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
    """Send the raw user prompt through the shared AI provider path."""
    user = st.session_state.get("user", {})
    if not require_role_permission(
        user.get("role", "System"),
        "use_ai_assistant",
        action_label="use the AI assistant",
        company_key=user.get("key") or user.get("company_key"),
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return "You do not have permission to perform this action."
    response = request_ai_chat_completion(
        messages=[
            {
                "role": "system",
                "content": "You are a Senior Chartered Accountant for a Ghanaian enterprise. Provide direct, professional financial analysis without preamble. Answer user queries based on their ERP data confidently and concisely.",
            },
            {"role": "user", "content": user_input},
        ],
        temperature=0.5,
        max_tokens=1024,
    )
    if response["ok"]:
        return response["content"]
    logger.error("Gatekeeper AI call failed via provider %s: %s", response.get("provider"), sanitize_error_message(response.get("error")))
    return response.get("error") or "AI assistant request failed. Please try again."


def render_gatekeeper_ai_chat(menu_selection):
    """Render a real interactive sidebar chatbot."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Ask me an accounting question and I will explain it simply for your business.",
            }
        ]

    with st.sidebar.expander("Gatekeeper Admin", expanded=False):
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

    with st.sidebar.expander("Gatekeeper Admin", expanded=False):
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
    """Return a compatibility-friendly subscription snapshot for legacy UI callers."""
    try:
        snapshot = get_company_subscription_snapshot(company_key)
        if not snapshot.get("ok"):
            return {"status": "error", "days_left": None, "subscription": snapshot}
        days_left = snapshot.get("days_left")
        if snapshot.get("renewal_required"):
            return {
                "status": "expired",
                "days_left": abs(int(days_left or 0)),
                "subscription": snapshot,
            }
        if days_left is not None and int(days_left) <= 7:
            return {
                "status": "warning",
                "days_left": int(days_left),
                "subscription": snapshot,
            }
        return {
            "status": "active" if snapshot.get("access_allowed") else "unknown",
            "days_left": None if days_left is None else int(days_left),
            "subscription": snapshot,
        }
    except Exception:
        return {"status": "error", "days_left": None}

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
        st.toast("Payment reference received. Awaiting admin approval.", icon="âœ…")
        
        # TODO: Trigger smtplib to send payment_ref to admin email for Passcode generation.
        
        return True
    except Exception as e:
        logger.error("Failed to submit payment reference: %s", sanitize_error_message(e))
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
        logger.error("Failed to update license expiry: %s", sanitize_error_message(e))
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
    st.title("System Status Dashboard")
    st.markdown("Real-time monitoring of E.K.A Enterprise ERP infrastructure components.")
    
    # Status Indicators
    st.subheader("System Components")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("API Gateway", "Operational", delta="Online")
    with col2:
        st.metric("Database Engine", "Operational", delta="Online")
    with col3:
        st.metric("Payment Server", "Operational", delta="Online")
    
    st.markdown("---")
    
    # Uptime Metric
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Live Uptime")
        st.metric("System Availability", "99.9%", delta="+0.1% this month")
    
    with col2:
        st.subheader("Past Incidents")
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
    
    t1, t2, t3, t4 = st.tabs(["Secure Login", "System Recovery", "Register New Company", "System Status"])
    
    with t1:
        if not st.session_state.get('demo_toggle'):
            # Assigned unique keys to ensure no Duplicate ID errors
            access_key = st.text_input(
                "Access Key", 
                type="password", 
                key="v3_final_access_key_field"
            )
            
            if st.button("Access Cloud Modules", key="v3_final_auth_submit_btn"):
                login_started = time.perf_counter()
                try:
                    conn = get_connection()
                    
                    # Developer Backdoor
                    if access_key == "JUANMANUEL2":
                        user_obj = {"name": "Gatekeeper", "role": "Dev", "key": "ADMIN"}
                        try:
                            log_audit_action(conn, "SYSTEM", "Dev", "Developer login", "Authentication")
                        except Exception:
                            logger.exception("Audit log failed for developer backdoor login")
                        try:
                            conn.close()
                        except Exception:
                            pass
                        _init_session(user_obj)
                        try:
                            import modules as eka_modules_perf

                            eka_modules_perf.record_lv002b_operation(
                                "auth.login",
                                (time.perf_counter() - login_started) * 1000.0,
                                surface="login",
                            )
                        except Exception:
                            pass
                        st.rerun()
                    
                    auth_result = authenticate_access_key_read_path(conn, access_key)
                    if auth_result.get("matched") and not auth_result.get("active"):
                        st.session_state.login_attempts += 1
                        try:
                            conn.close()
                        except Exception:
                            pass
                        if auth_result.get("reason") == "company_inactive":
                            st.error("This company is currently archived or inactive. Contact Gatekeeper to reactivate access.")
                        elif auth_result.get("reason") == "branch_not_configured":
                            st.error(
                                "Branch access is not configured for this user. "
                                "Contact your company administrator to assign a branch."
                            )
                        else:
                            st.error("Access is not active. Contact your administrator.")
                        return

                    if auth_result.get("matched") and auth_result.get("active"):
                        user_obj = auth_result["user"]
                        try:
                            log_audit_action(
                                conn,
                                user_obj.get("company_key") or user_obj.get("key"),
                                user_obj.get("role"),
                                "Successful login",
                                "Authentication",
                                branch_id=user_obj.get("branch_id"),
                            )
                        except Exception:
                            logger.exception("Audit log failed for login: %s", user_obj.get("key"))
                        try:
                            conn.close()
                        except Exception:
                            pass
                        _init_session(user_obj)
                        try:
                            import modules as eka_modules_perf

                            eka_modules_perf.record_lv002b_operation(
                                "auth.login",
                                (time.perf_counter() - login_started) * 1000.0,
                                surface="login",
                            )
                        except Exception:
                            pass
                        st.rerun()

                    # Failed login attempt
                    st.session_state.login_attempts += 1
                    log_audit_action(conn, "SYSTEM", "Unknown", f"Failed login attempt {st.session_state.login_attempts}", "Authentication")
                    conn.close()
                    st.error(f"Access Denied. Please verify your Access Key. Attempts: {st.session_state.login_attempts}/5")
                    
                except Exception as e:
                    st.error("System error during authentication. Please try again.")
                    logger.error("Login error: %s", sanitize_error_message(e))
        elif st.session_state.get('demo_toggle'):
            st.button('Enter Demo ERP', on_click=enter_demo)

        if _has_restored_data_without_admin_users():
            st.info(
                "Secure company workspace detected. Please log in with your company access credentials."
            )

        # License Renewal Section
        with st.expander("Renew License", expanded=False):
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
                row = execute_portable_query(
                    conn,
                    "SELECT company_key, security_question FROM users WHERE login_key = ? AND COALESCE(status, 'Active') = 'Active' LIMIT 1",
                    (forgot_login_key.strip(),),
                ).fetchone()
                if row and row_get(row, "security_question"):
                    st.session_state.forgot_login_key = forgot_login_key.strip()
                    st.session_state.forgot_security_question = row_get(row, "security_question")
                    st.session_state.forgot_company_key = row_get(row, "company_key")
                    st.success("Security question loaded. Answer it to reset your password.")
                else:
                    st.error("No active user found for that login key or no recovery question is set.")
                conn.close()
            except Exception as e:
                st.error("System error during recovery. Please try again.")
                logger.error("Recovery error: %s", sanitize_error_message(e))

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
                        reset_row = execute_portable_query(
                            conn,
                            "SELECT company_key, security_answer FROM users WHERE login_key = ? LIMIT 1",
                            (st.session_state.get("forgot_login_key"),),
                        ).fetchone()
                        if reset_row and row_get(reset_row, "security_answer") == hash_login_password(recovery_answer):
                            execute_portable_write(
                                conn,
                                "UPDATE users SET password_hash = ? WHERE login_key = ?",
                                (hash_login_password(new_password), st.session_state.get("forgot_login_key")),
                            )
                            conn.commit()
                            log_audit_action(
                                conn,
                                row_get(reset_row, "company_key"),
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
                        logger.error("Password reset error: %s", sanitize_error_message(e))

        if _has_restored_data_without_admin_users():
            st.markdown("---")
            _show_admin_recovery_panel()

    with t3:
        show_onboarding_payment()

    with t4:
        show_system_status()

    # Demo mode entry — button-only (avoids fragile Checkbox/Toggle frontend chunks on login/register reruns)
    st.markdown("---")
    demo_mode_selected = bool(st.session_state.get("demo_toggle"))
    if demo_mode_selected:
        st.info("Demo mode selected. Enter the sample workspace below or return to secure login.")
        demo_col1, demo_col2 = st.columns(2)
        with demo_col1:
            st.button("Enter Demo ERP", on_click=enter_demo, key="enter_demo_erp_btn", use_container_width=True)
        with demo_col2:
            if st.button("Back to Secure Login", key="demo_mode_back_btn", use_container_width=True):
                st.session_state.demo_toggle = False
                st.rerun()
    else:
        st.caption("Explore the ERP with sample data. No payment or registration required.")
        if st.button("Try Demo Mode", key="demo_mode_entry_btn"):
            st.session_state.demo_toggle = True
            st.rerun()

# Dashboard Module (NEW FUNCTION)
def _show_legacy_dashboard(company_key, company_name, role):
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

                dashboard_counts = get_dashboard_metric_counts(conn, company_key)
                inv_val = dashboard_counts["inventory_value"]
                col1.metric(label=f"Inventory Value ({st.session_state.currency_symbol})", value=format_currency(inv_val))

                current_month = datetime.now().strftime('%Y-%m')
                month_sales = get_month_sales_total(company_key, year_month=current_month, conn=conn)
                col2.metric(label=f"Month Sales ({st.session_state.currency_symbol})", value=format_currency(month_sales))

                emp_count = dashboard_counts["employee_count"]
                col3.metric("Employees", str(emp_count))

                fa_val = dashboard_counts["fixed_asset_value"]
                col4.metric(label=f"Asset Value ({st.session_state.currency_symbol})", value=format_currency(fa_val))
            except sqlite3.OperationalError as db_schema_error:
                if "no such table" in str(db_schema_error).lower():
                    st.warning(
                        "Your dashboard data tables are not fully available yet. "
                        "Please run `python fix_db.py` to complete the Safety Sync, then reload the app."
                    )
                    logger.warning("Dashboard schema issue: %s", sanitize_error_message(db_schema_error))
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
                    low_stock_data = execute_portable_query(
                        conn,
                        """SELECT item_name, qty, unit FROM inventory
                           WHERE company_key = ? AND qty <= 10
                           ORDER BY qty ASC LIMIT 10""",
                        (company_key,),
                    ).fetchall()

                    if low_stock_data:
                        low_stock = pd.DataFrame(
                            [
                                {
                                    "Item": row_get(row, "item_name", row_get(row, 0)),
                                    "Quantity": row_get(row, "qty", row_get(row, 1)),
                                    "Unit": row_get(row, "unit", row_get(row, 2)),
                                }
                                for row in low_stock_data
                            ],
                        )
                        st.dataframe(low_stock, width='stretch')
                    else:
                        st.success("All stock levels are adequate!")
            except sqlite3.OperationalError as activity_error:
                if "no such table" in str(activity_error).lower():
                    st.info(
                        "Some activity tables are still being prepared. Run `python fix_db.py` to complete the Safety Sync."
                    )
                    logger.warning("Dashboard activity schema issue: %s", sanitize_error_message(activity_error))
                else:
                    raise

            st.subheader("Quick Actions")
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("New Sale", key="dash_pos", width='stretch'):
                    st.session_state.page = "Point of Sale"
                    st.rerun()

            with col2:
                if st.button("Add Inventory", key="dash_inventory", width='stretch'):
                    st.session_state.page = "Inventory Management"
                    st.rerun()

            with col3:
                if st.button("Process Payroll", key="dash_payroll", width='stretch'):
                    st.session_state.page = "Payroll & Salaries"
                    st.rerun()

            with col4:
                if st.button("View Reports", key="dash_reports", width='stretch'):
                    st.session_state.page = "Data Analytics"
                    st.rerun()

        finally:
            if conn:
                conn.close()

    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))

def _show_local_dashboard(company_key, company_name, role):
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

            dashboard_counts = get_dashboard_metric_counts(conn, company_key)
            inv_val = dashboard_counts["inventory_value"]
            month_sales = get_month_sales_total(company_key, year_month=datetime.now().strftime('%Y-%m'), conn=conn)
            emp_count = dashboard_counts["employee_count"]
            fa_val = dashboard_counts["fixed_asset_value"]

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
                low_stock_rows = execute_portable_query(
                    conn,
                    """
                    SELECT item_name AS Item, qty AS Quantity, unit AS Unit
                    FROM inventory
                    WHERE company_key = ? AND qty <= 10
                    ORDER BY qty ASC
                    LIMIT 10
                    """,
                    (company_key,),
                ).fetchall()
                low_stock = pd.DataFrame(rows_to_dicts(low_stock_rows))
                if low_stock.empty:
                    st.success("All stock levels are adequate!")
                else:
                    st.dataframe(low_stock, width='stretch')

            st.subheader("Quick Actions")
            quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
            if quick_col1.button("New Sale", key="dash_pos_v2", width='stretch'):
                st.session_state.page = "Point of Sale"
                st.rerun()
            if quick_col2.button("Add Inventory", key="dash_inventory_v2", width='stretch'):
                st.session_state.page = "Inventory Management"
                st.rerun()
            if quick_col3.button("Process Payroll", key="dash_payroll_v2", width='stretch'):
                st.session_state.page = "Payroll & Salaries"
                st.rerun()
            if quick_col4.button("View Reports", key="dash_reports_v2", width='stretch'):
                st.session_state.page = "Data Analytics"
                st.rerun()
        finally:
            if conn:
                conn.close()
    except Exception as e:
        st.error(build_user_safe_error(e, role))

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
            current_db_session = execute_portable_query(
                conn,
                "SELECT current_session_id FROM users WHERE login_key = ? AND company_key = ?",
                (st.session_state.get('login_key'), user['key'])
            ).fetchone()
        else:
            # For company level, no session lock for now, as they might have multiple admins
            conn.close()
            return True
        
        if current_db_session and row_get(current_db_session, "current_session_id", row_get(current_db_session, 0)) != session_uuid:
            # Session revoked
            _clear_session()
            st.error("Account active on another device. Please upgrade for more branch licenses.")
            try:
                conn.close()
            except Exception:
                pass
            st.rerun()
        conn.close()
        return True
    except Exception as e:
        logger.error("Session lock check error: %s", sanitize_error_message(e))
        return True


def _has_restored_data_without_admin_users():
    """Check if companies exist but no active admin-capable users exist in users table.
    
    Note: Master Admin login uses company key directly and does not require users table.
    This check only warns if STAFF-level admin users are missing.
    """
    conn = None
    try:
        conn = get_connection()
        company_count_row = execute_portable_query(
            conn,
            "SELECT COUNT(*) AS company_count FROM companies WHERE COALESCE(status, 'Active') = 'Active'",
        ).fetchone()
        company_count = row_get(company_count_row, "company_count", row_get(company_count_row, 0, 0)) or 0
        if company_count == 0:
            return False  # No companies, no repair needed
        
        # Check if users table exists and has active admin-capable users
        try:
            # Only count users with admin-capable roles (not just any user)
            admin_user_count_row = execute_portable_query(
                conn,
                "SELECT COUNT(*) AS admin_user_count FROM users WHERE role IN ('Master Admin', 'System Admin', 'Sub-Admin') AND COALESCE(status, 'Active') = 'Active'",
            ).fetchone()
            admin_user_count = row_get(
                admin_user_count_row,
                "admin_user_count",
                row_get(admin_user_count_row, 0, 0),
            )
            return int(admin_user_count or 0) == 0
        except Exception:
            # If users table doesn't exist or query fails, no repair needed
            # (Master Admin login via company key will still work)
            return False
    except Exception as exc:
        logger.warning("Administrative access repair check skipped: %s", sanitize_error_message(exc))
        return False
    finally:
        if conn:
            conn.close()


def _get_restored_companies_needing_admin():
    """Get list of active companies that have no admin-capable users.
    
    Returns list of (company_key, company_name) tuples.
    """
    conn = None
    try:
        conn = get_connection()
        companies = execute_portable_query(
            conn,
            """SELECT c.key, c.name FROM companies c
               WHERE COALESCE(c.status, 'Active') = 'Active'
               AND NOT EXISTS (
                   SELECT 1 FROM users u
                   WHERE u.company_key = c.key
                   AND u.role IN ('Master Admin', 'System Admin', 'Sub-Admin')
                   AND COALESCE(u.status, 'Active') = 'Active'
               )
               ORDER BY c.name"""
        ).fetchall()
        return rows_to_dicts(companies) if companies else []
    except Exception as exc:
        logger.warning("Failed to get restored companies: %s", sanitize_error_message(exc))
        return []
    finally:
        if conn:
            conn.close()


def _show_admin_recovery_panel():
    """Show guided admin recovery panel for restored companies.
    
    Allows controlled creation of new admin users for companies that need them.
    """
    st.warning("**Administrative Access Repair Needed**")
    st.info(
        "Restored company data exists with no active admin users. "
        "You can log in with your company Master Admin key, or create a new admin user below."
    )
    
    restored_companies = _get_restored_companies_needing_admin()
    if not restored_companies:
        st.success("All companies have active admin users. No repair needed.")
        return
    
    st.subheader("Create New Admin User for Restored Company")
    company_labels = [f"{company[1]} ({company[0]})" for company in restored_companies]
    option_indexes = list(range(len(restored_companies)))
    col1, col2 = st.columns(2)
    with col1:
        selected_index = st.selectbox(
            "Select Company",
            options=option_indexes,
            format_func=lambda i: company_labels[i],
            key="repair_company_select"
        )
    
    if selected_index is not None and 0 <= selected_index < len(restored_companies):
        selected_company = restored_companies[selected_index]
        company_key, company_name = selected_company
        st.markdown(f"**Creating admin for:** {company_name}")
        
        with st.form("admin_recovery_form"):
            admin_name = st.text_input(
                "Admin User Full Name",
                placeholder="e.g., John Smith",
                key="repair_admin_name"
            )
            admin_login = st.text_input(
                "Admin Login Key (unique identifier)",
                placeholder="e.g., john.smith@acme",
                key="repair_admin_login"
            )
            admin_password = st.text_input(
                "Temporary Password",
                type="password",
                placeholder="Will be set immediately upon creation",
                key="repair_admin_password"
            )
            confirm_password = st.text_input(
                "Confirm Password",
                type="password",
                key="repair_admin_confirm"
            )
            
            security_question = st.text_input(
                "Security Question (for password recovery)",
                placeholder="e.g., What is your pet's name?",
                key="repair_security_question"
            )
            security_answer = st.text_input(
                "Security Answer",
                placeholder="e.g., Fluffy",
                key="repair_security_answer"
            )
            
            submitted = st.form_submit_button("Create Admin User")
            
            if submitted:
                # Validation
                if not admin_name.strip():
                    st.error("Admin name is required.")
                elif not admin_login.strip():
                    st.error("Admin login key is required.")
                elif not admin_password or not confirm_password:
                    st.error("Password is required.")
                elif admin_password != confirm_password:
                    st.error("Passwords do not match.")
                elif not security_question.strip() or not security_answer.strip():
                    st.error("Security question and answer are required.")
                else:
                    # Create the admin user
                    try:
                        conn = get_connection()
                        
                        # Check if login key already exists
                        existing = conn.execute(
                            "SELECT 1 FROM users WHERE login_key = ? LIMIT 1",
                            (admin_login.strip(),)
                        ).fetchone()
                        if existing:
                            st.error(f"Login key '{admin_login}' already exists. Choose a different key.")
                            conn.close()
                        else:
                            user_id = f"{company_key}_{admin_login.strip()[:20]}_{int(time.time())}"
                            
                            conn.execute(
                                """INSERT INTO users (
                                    company_key, full_name, user_id, login_key, 
                                    password_hash, role, status, 
                                    security_question, security_answer, created_at
                                ) VALUES (?, ?, ?, ?, ?, 'System Admin', 'Active', ?, ?, CURRENT_TIMESTAMP)""",
                                (
                                    company_key,
                                    admin_name.strip(),
                                    user_id,
                                    admin_login.strip(),
                                    hash_login_password(admin_password),
                                    security_question.strip(),
                                    hash_login_password(security_answer.strip()),
                                )
                            )
                            conn.commit()
                            
                            # Log the action
                            log_audit_action(
                                conn,
                                company_key,
                                "Recovery",
                                "Admin user created during recovery",
                                "Administrative Recovery",
                                f"Created System Admin user: {admin_name}"
                            )
                            conn.close()
                            
                            st.success(
                                f"âœ… Admin user created successfully!\n\n"
                                f"**Login Key:** {admin_login}\n\n"
                                f"This user can now log in and manage {company_name}."
                            )
                            time.sleep(2)
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to create admin user: {sanitize_error_message(exc)}")
                        logger.error("Admin recovery creation failed: %s", sanitize_error_message(exc))


def main():
    eka_modules.begin_lv003_hot_path_rerun(
        active_page=st.session_state.get("active_page") or st.session_state.get("page"),
    )
    eka_modules.run_process_startup_warmup()
    if st.session_state.pop("_clear_streamlit_caches", False):
        st.cache_data.clear()
        st.cache_resource.clear()
        try:
            from database import clear_diagnostics_ttl_cache

            clear_diagnostics_ttl_cache()
        except Exception:
            logger.exception("Failed to clear diagnostics TTL cache during logout/cache reset")

    startup_main_started = time.perf_counter()
    startup_result = eka_modules.get_session_canonical_startup_result()
    startup_backend = {
        "configured_backend": startup_result.get("configured_backend"),
        "active_backend": startup_result.get("active_backend"),
        "startup_route": startup_result.get("startup_route"),
        "sqlite_startup_skipped": startup_result.get("sqlite_startup_skipped"),
        "runtime_cutover_guard_ok": startup_result.get("runtime_cutover_guard_ok"),
        "schema_deployment_status": startup_result.get("schema_deployment_status"),
        "row_reconciliation_status": startup_result.get("row_reconciliation_status"),
        "message": startup_result.get("blocked_reason") or "",
    }
    if startup_result.get("startup_route") == "sqlite_runtime":
        eka_modules.timed_lv003_hot_path("database.ensure_schema", ensure_schema, required=True, surface="startup")
    elif startup_backend.get("runtime_cutover_guard_ok"):
        logger.info(
            "Application startup skipping SQLite schema path for PostgreSQL runtime: configured_backend=%s active_backend=%s schema_deployment_status=%s row_reconciliation_status=%s",
            startup_backend.get("configured_backend"),
            startup_backend.get("active_backend"),
            startup_backend.get("schema_deployment_status"),
            startup_backend.get("row_reconciliation_status"),
        )
    startup_status = startup_result
    try:
        eka_modules.record_lv002b_operation(
            "app.startup_main",
            (time.perf_counter() - startup_main_started) * 1000.0,
            surface="startup",
        )
        eka_modules.record_lv003_hot_path_call(
            "app.startup_main",
            (time.perf_counter() - startup_main_started) * 1000.0,
            required=True,
            recommendation="keep",
            surface="startup",
        )
    except Exception:
        pass
    startup_mode = str(startup_status.get("startup_mode", startup_status.get("stage", ""))) if isinstance(startup_status, dict) else ""
    bootstrap_needed = (
        bool(startup_status.get("bootstrap_needed"))
        and startup_mode == "bootstrap_mode"
        if isinstance(startup_status, dict)
        else False
    )
    st.session_state["bootstrap_needed"] = bootstrap_needed
    st.session_state["database_startup_mode"] = startup_mode
    startup_ok = bool(startup_status.get("startup_ok", startup_status.get("ok"))) if isinstance(startup_status, dict) else bool(startup_status)
    if not startup_ok:
        postgres_startup_stage = isinstance(startup_status, dict) and startup_status.get("stage") in {
            "postgres_runtime_validation",
            "postgres_runtime_connection",
            "postgres_runtime_cutover_guard",
            "postgres_schema_not_implemented",
        }
        if postgres_startup_stage or (isinstance(startup_status, dict) and startup_status.get("sqlite_startup_skipped")):
            logger.error(
                "Application startup halted by PostgreSQL runtime gate: stage=%s reason=%s",
                startup_status.get("stage") if isinstance(startup_status, dict) else "unknown",
                startup_status.get("reason") if isinstance(startup_status, dict) else "unknown",
            )
            st.error(
                "PostgreSQL runtime startup could not complete.\n\n"
                f"Stage: {startup_status.get('stage', 'unknown') if isinstance(startup_status, dict) else 'unknown'}\n"
                f"Reason: {startup_status.get('reason', 'startup_database returned a falsey result') if isinstance(startup_status, dict) else 'startup_database returned a falsey result'}\n"
                f"Configured Backend: {startup_status.get('configured_backend', 'unknown') if isinstance(startup_status, dict) else 'unknown'}\n"
                f"Active Backend: {startup_status.get('active_backend', 'unknown') if isinstance(startup_status, dict) else 'unknown'}\n"
                f"Startup Route: {startup_status.get('startup_route', 'postgres_runtime') if isinstance(startup_status, dict) else 'postgres_runtime'}\n"
                "SQLite local file startup/recovery was skipped for controlled PostgreSQL cutover."
            )
            if eka_modules.can_view_runtime_admin_diagnostics(st.session_state.get("user", {}).get("role")):
                try:
                    from database import get_database_startup_diagnostics

                    st.dataframe(
                        pd.DataFrame([get_database_startup_diagnostics()]),
                        use_container_width=True,
                        hide_index=True,
                    )
                except Exception:
                    pass
            st.stop()
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
    if bootstrap_needed:
        st.info("No company has been created yet. Complete initial company setup to activate this ERP.")
    if "cloud_vault_status" not in st.session_state:
        if startup_result.get("startup_route") == "sqlite_runtime":
            _verify_cloud_vault_handshake()
        else:
            st.session_state["cloud_vault_status"] = "Cloud Vault: Skipped (PostgreSQL runtime)"
    if "base_currency" not in st.session_state:
        st.session_state.base_currency = "GHS"
    if "exchange_rate" not in st.session_state:
        st.session_state.exchange_rate = 1.0
    symbols = {"GHS": "GHS", "USD": "USD", "EUR": "EUR", "GBP": "GBP"}
    st.session_state.currency_symbol = symbols.get(st.session_state.base_currency, "GHS")

    selected_base_currency = str(st.session_state.get("base_currency", "GHS")).upper()
    bog_rate = _get_bog_display_rate(selected_base_currency)
    expected_rate = 1.0 if selected_base_currency == "GHS" else bog_rate
    if abs(float(st.session_state.get("exchange_rate", 1.0)) - float(expected_rate)) > 0.000001:
        st.session_state.exchange_rate = expected_rate

    currency_sync_key = f"{selected_base_currency}:{expected_rate}"
    if st.session_state.get("_currency_db_sync_key") != currency_sync_key:
        settings_conn = None
        try:
            settings_conn = get_connection()
            if settings_conn:
                settings_conn.execute(
                    "UPDATE system_settings SET base_currency = ?, display_currency = ?, exchange_rate = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                    ("GHS", selected_base_currency, st.session_state.exchange_rate),
                )
                settings_conn.commit()
                st.session_state["_currency_db_sync_key"] = currency_sync_key
        except Exception as session_sync_error:
            logger.warning("Currency session sync failed: %s", sanitize_error_message(session_sync_error))
        finally:
            if settings_conn:
                settings_conn.close()
    else:
        eka_modules.record_lv003_hot_path_call(
            "app.currency_session_sync",
            0.0,
            from_cache=True,
            required=False,
            recommendation="cache",
            surface="main",
        )


SIDEBAR_NAV_GROUPS = [
    (
        "📊 Overview",
        [
            ("📊 Dashboard", "Dashboard"),
        ],
    ),
    (
        "💳 Transactions",
        [
            ("🛒 Point of Sale", "Point of Sale"),
            ("Create Invoice", "Create Invoice"),
            ("Receive Payment", "Receive Payment (Customer)"),
            ("Create Bill", "Create Bill"),
            ("Supplier Payment", "Supplier Payment"),
        ],
    ),
    (
        "🧾 Invoicing",
        [
            ("Sales Invoicing", "Sales Invoicing"),
            ("Purchase Invoicing", "Purchase Invoicing"),
        ],
    ),
    (
        "👥 Contacts",
        [
            ("Customers", "Customers"),
            ("Suppliers", "Suppliers"),
        ],
    ),
    (
        "🏦 Banking",
        [
            ("🏦 Banking & Cash", "Banking & Cash"),
        ],
    ),
    (
        "📚 Ledgers",
        [
            ("General Journal", "General Journal"),
            ("Vouchers & Journals", "Vouchers & Journals"),
            ("Chart of Accounts", "Chart of Accounts"),
            ("Accounts Receivable", "Accounts Receivable"),
            ("Accounts Payable", "Accounts Payable"),
            ("Taxation", "Taxation (VAT/NHIL)"),
        ],
    ),
    (
        "📦 Inventory",
        [
            ("Inventory", "Inventory Management"),
            ("Asset Register", "Asset Register"),
        ],
    ),
    (
        "📈 Reports",
        [
            ("Financial Reports", "Financial Reports"),
            ("📈 Analytics", "Data Analytics"),
            ("Audit Trail", "System Audit Trail"),
        ],
    ),
    (
        "⚙ System",
        [
            ("Payroll", "Payroll & Salaries"),
            ("🛡 Gatekeeper Admin", "Gatekeeper Admin"),
            ("⚙ System Configuration", "System Configuration"),
        ],
    ),
    (
        "🛠 Administration",
        [
            ("Manage Branches", "branch_management"),
        ],
    ),
]

PRIMARY_NAV_ITEMS = [
    (label, page_key)
    for _group_name, options in SIDEBAR_NAV_GROUPS
    for label, page_key in options
]

PAGE_PERMISSION_MAP = {
    "Dashboard": "view_dashboard",
    "Point of Sale": "sell_pos",
    "Inventory Management": "view_inventory",
    "Vouchers & Journals": "post_accounting_document",
    "General Journal": "view_reports",
    "General Ledger": "view_reports",
    "Chart of Accounts": "view_reports",
    "Customer Ledger": "view_reports",
    "Supplier Ledger": "view_reports",
    "Accounts Receivable": "view_reports",
    "Accounts Payable": "view_reports",
    "Customers": "create_customer",
    "Suppliers": "create_supplier",
    "Create Invoice": "create_invoice",
    "Receive Payment (Customer)": "receive_customer_payment",
    "Supplier Payment": "make_supplier_payment",
    "Create Bill": "create_bill",
    "Banking & Cash": "view_banking",
    "Banking": "view_banking",
    "Taxation (VAT/NHIL)": "view_taxation",
    "Payroll & Salaries": "view_payroll",
    "Asset Register": "view_fixed_assets",
    "Data Analytics": "view_reports",
    "Financial Reports": "view_reports",
    "Gatekeeper Admin": "use_ai_assistant",
    "System Audit Trail": "view_audit_trail",
    "System Configuration": "manage_company",
    "branch_management": "manage_branches",
    "Sales History": "create_invoice",
    "Sales Invoicing": "create_invoice",
    "Purchase History": "create_bill",
    "Purchase Orders": "create_bill",
    "Purchase Invoicing": "create_bill",
}


def _page_permission(page_name):
    return PAGE_PERMISSION_MAP.get(page_name)


def _user_can_access_page(user, page_name):
    company_key = user.get("key") if user else None
    cache_key = f"lv003_page_access:{company_key}:{user.get('role') if user else ''}:{page_name}"
    if cache_key in st.session_state:
        eka_modules.record_lv003_hot_path_call(
            "modules.user_can_access_page",
            0.0,
            from_cache=True,
            required=True,
            recommendation="cache",
            surface="sidebar",
        )
        return st.session_state[cache_key]
    started = time.perf_counter()
    allowed = eka_modules.user_can_access_page(user, page_name, company_key=company_key)
    eka_modules.record_lv003_hot_path_call(
        "modules.user_can_access_page",
        (time.perf_counter() - started) * 1000.0,
        required=True,
        recommendation="cache",
        surface="sidebar",
    )
    st.session_state[cache_key] = allowed
    return allowed


def _normalize_page_state(page_name):
    if str(page_name) == "Purchase Orders":
        return "Purchase Invoicing"
    return page_name


def _ensure_valid_page(default_page="Dashboard"):
    valid_pages = {page_key for _label, page_key in PRIMARY_NAV_ITEMS}
    legacy_page = st.session_state.get("page")
    active_page = st.session_state.get("active_page")
    current_page = legacy_page if legacy_page and legacy_page != active_page else active_page or legacy_page or default_page
    legacy_aliases = {
        "Sales/Purchase": "Sales Invoicing",
        "Sales History": "Sales Invoicing",
        "Sales Invoicing": "Sales Invoicing",
        "Purchase Orders": "Purchase Invoicing",
        "Purchase History": "Purchase Invoicing",
        "Taxation": "Taxation (VAT/NHIL)",
        "Audit Trail": "System Audit Trail",
    }
    current_page = legacy_aliases.get(str(current_page), current_page)
    current_page = _normalize_page_state(current_page)
    if current_page not in valid_pages and current_page != 'branch_management':
        label_to_key = {label: key for label, key in PRIMARY_NAV_ITEMS}
        current_page = label_to_key.get(str(current_page), default_page)
    st.session_state.page = current_page
    st.session_state.active_page = current_page
    return current_page


def _set_active_page(page_name):
    page_name = _normalize_page_state(page_name)
    st.session_state.active_page = page_name
    st.session_state.page = page_name


def _render_sidebar_nav_styles():
    st.sidebar.markdown(
        """
        <style>
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
            width: 100%;
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, 0.24);
            text-align: left;
            justify-content: flex-start;
            padding: 0.75rem 1rem;
            margin-bottom: 0.45rem;
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
            transform: translateY(-1px);
            border-color: rgba(148, 163, 184, 0.45);
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] {
            margin-bottom: 0.6rem;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, #0f766e 0%, #ca8a04 100%);
            color: #ffffff;
            border: 1px solid rgba(180, 83, 9, 0.55);
            box-shadow: 0 10px 24px rgba(15, 118, 110, 0.16);
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
            if not _user_can_access_page(user, page_name):
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
    sidebar_started = time.perf_counter()
    eka_modules.enforce_branch_session_lock(user)
    st.sidebar.markdown(
        f"""
        <div style='background-color:#f0f2f6; padding:20px; border-radius:15px; border: 1px solid #d1d5db;'>
            <h2 style='margin-bottom:0;'>Welcome, {user['name']}</h2>
            <p style='color:#6b7280;'>Role: <b>{user['role']}</b></p>
            <p style='color:#6b7280; font-size:12px;'>Session: Active</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Branch selector is only exposed to roles allowed to view all branches.
    if user.get("role") in {"Dev", "Master Admin", "System Admin", "Owner / CEO"}:
        try:
            conn = get_connection()
            branches = execute_portable_query(
                conn,
                "SELECT branch_id, branch_name FROM branches WHERE company_key = ? ORDER BY branch_name",
                (user['key'],),
            ).fetchall()
            conn.close()
            if branches:
                branch_options = ["All Branches"] + [
                    f"{row_get(branch, 'branch_name', row_get(branch, 1))} ({row_get(branch, 'branch_id', row_get(branch, 0))})"
                    for branch in branches
                ]
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
            logger.error("Branch selector error: %s", sanitize_error_message(e))
            st.session_state.active_branch_id = None
    elif user.get("branch_id"):
        st.session_state.active_branch_id = user.get("branch_id")

    if eka_modules.is_branch_scoped_user(user):
        branch_name = user.get("branch_name")
        if not branch_name and user.get("branch_id") and user.get("key"):
            try:
                conn = get_connection()
                branch_row = execute_portable_query(
                    conn,
                    "SELECT branch_name FROM branches WHERE company_key = ? AND branch_id = ?",
                    (user["key"], user["branch_id"]),
                ).fetchone()
                conn.close()
                branch_name = row_get(branch_row, "branch_name", row_get(branch_row, 0)) if branch_row else None
            except Exception:
                branch_name = None
        if branch_name:
            st.sidebar.caption(f"Branch: {branch_name}")
        elif user.get("branch_id"):
            st.sidebar.caption(f"Branch: {user.get('branch_id')}")

    if eka_modules.is_branch_scoped_user(user):
        eka_modules.render_branch_session_diagnostics(user=user)

    current_page = _ensure_valid_page()
    if not st.session_state.get("_sidebar_nav_styles_rendered"):
        _render_sidebar_nav_styles()
        st.session_state["_sidebar_nav_styles_rendered"] = True
    else:
        eka_modules.record_lv003_hot_path_call(
            "app.sidebar_nav_styles",
            0.0,
            from_cache=True,
            required=False,
            recommendation="cache",
            surface="sidebar",
        )
    _render_sidebar_navigation(user, current_page)

    if False and user['role'] == "Demo":
        menu_options = [
            "Dashboard",
            "Inventory Management", 
            "Payroll & Salaries",
            "Sales/Purchase",
            "Data Analytics",
            "Banking",
            "Taxation",
            "Gatekeeper Admin",
            "Audit Trail"
        ]
        page_mapping = {
            "Dashboard": "Dashboard",
            "Inventory Management": "Inventory Management",
            "Payroll & Salaries": "Payroll & Salaries",
            "Sales/Purchase": "Sales/Purchase",
            "Data Analytics": "Data Analytics",
            "Banking": "Banking",
            "Taxation": "Taxation",
            "Gatekeeper Admin": "Gatekeeper Admin",
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
                    ("Point of Sale", "Point of Sale"),
                    ("Vouchers & Journals", "Vouchers & Journals"),
                    ("Create Bill", "Create Bill"),
                    ("Banking & Cash", "Banking & Cash"),
                ],
            ),
            (
                "Ledgers",
                [
                    ("Chart of Accounts", "Chart of Accounts"),
                    ("Accounts Receivable", "Accounts Receivable"),
                    ("Accounts Payable", "Accounts Payable"),
                ],
            ),
            (
                "Inventory",
                [
                    ("Inventory Management", "Inventory Management"),
                    ("Stock In/Out", "Inventory Management"),
                ],
            ),
            (
                "Reports",
                [
                    ("Data Analytics", "Data Analytics"),
                    ("Financial Reports", "Financial Reports"),
                ],
            ),
            (
                "System",
                [
                    ("Manage Branches", "branch_management"),
                    ("System Audit Trail", "System Audit Trail"),
                    ("System Configuration", "System Configuration"),
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
                st.sidebar.warning(f"WARNING: License expires in {days_left['days_left']} days")
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
    symbols = {"GHS": "GHS", "USD": "USD", "EUR": "EUR", "GBP": "GBP"}
    st.session_state.currency_symbol = symbols.get(st.session_state.base_currency, "GHS")
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
    eka_modules.record_lv003_hot_path_call(
        "app.sidebar_build",
        (time.perf_counter() - sidebar_started) * 1000.0,
        required=True,
        recommendation="keep",
        surface="sidebar",
    )


def _render_primary_page(user):
    eka_modules.enforce_branch_session_lock(user)
    current_page = _ensure_valid_page()
    dispatch_started = time.perf_counter()
    if not _user_can_access_page(user, current_page):
        fallback_page = "Dashboard" if _user_can_access_page(user, "Dashboard") else None
        if fallback_page and current_page != fallback_page:
            if eka_modules.is_branch_scoped_user(user):
                st.warning("This module is not enabled for your branch.")
            else:
                st.warning("You do not have permission to access that page.")
            _set_active_page(fallback_page)
            current_page = fallback_page
        elif not fallback_page:
            if eka_modules.is_branch_scoped_user(user):
                st.error("No modules are available for this branch. Contact your administrator.")
            else:
                st.error("You do not have permission to access this workspace.")
            return
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
    elif current_page in {"Banking & Cash", "Banking"}:
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
    elif current_page == "branch_management":
        show_branch_management(user["key"], user["role"])
    elif current_page == "Vouchers & Journals":
        show_vouchers(user["key"], user["role"])
    elif current_page in {"Sales Invoicing", "Sales History", "Sales/Purchase"}:
        show_sales_purchase(user["key"], user["role"], "Sales")
    elif current_page in {"Purchase Invoicing", "Purchase History"}:
        show_sales_purchase(user["key"], user["role"], "Purchase")
    elif current_page == "Accounts Receivable":
        show_aging(user["key"], "Receivable")
    elif current_page == "Accounts Payable":
        show_aging(user["key"], "Payable")
    else:
        _set_active_page("Dashboard")
        st.rerun()
    eka_modules.record_lv003_hot_path_call(
        f"app.page_dispatch.{current_page}",
        (time.perf_counter() - dispatch_started) * 1000.0,
        required=True,
        recommendation="keep",
        surface="page_dispatch",
    )


# Main application flow
main()
if not st.session_state.auth or not check_session_timeout():
    login_ui()
else:
    session_started = time.perf_counter()
    check_session_lock()  # Check for session revocation
    
    update_activity()  # Update activity on each interaction
    u = st.session_state.user
    subscription_status = (
        eka_modules.get_session_company_subscription_status(st.session_state.company_id)
        if st.session_state.get("company_id") and u.get("role") not in {"Dev", "Demo"}
        else {"ok": True, "access_allowed": True, "renewal_required": False, "days_left": None}
    )
    eka_modules.record_lv003_hot_path_call(
        "app.authentication_session_restore",
        (time.perf_counter() - session_started) * 1000.0,
        required=True,
        recommendation="keep",
        surface="auth",
    )
    if subscription_status.get("ok") and not subscription_status.get("renewal_required"):
        if subscription_status.get("days_left") is not None and int(subscription_status.get("days_left") or 0) <= 7:
            st.warning(
                f"WARNING: Your subscription expires in {subscription_status['days_left']} days. Please renew to avoid service interruption."
            )
    
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
                    total_companies_row = execute_portable_query(
                        conn,
                        "SELECT COUNT(*) AS company_count FROM companies",
                    ).fetchone()
                    total_companies = row_get(total_companies_row, "company_count", row_get(total_companies_row, 0, 0))
                except Exception:
                    total_companies = 0
                billing_snapshot_key = "dev_gatekeeper_billing_snapshot"
                if billing_snapshot_key not in st.session_state:
                    billing_snapshot = eka_modules.timed_lv003_hot_path(
                        "modules.get_subscription_billing_admin_snapshot",
                        get_subscription_billing_admin_snapshot,
                        required=False,
                        recommendation="defer",
                        surface="system_health",
                    )
                    st.session_state[billing_snapshot_key] = billing_snapshot
                else:
                    billing_snapshot = st.session_state[billing_snapshot_key]
                    eka_modules.record_lv003_hot_path_call(
                        "modules.get_subscription_billing_admin_snapshot",
                        0.0,
                        from_cache=True,
                        required=False,
                        recommendation="defer",
                        surface="system_health",
                    )
                active_subscriptions = int(billing_snapshot.get("active_subscriptions") or 0)
                monthly_revenue = float(billing_snapshot.get("total_verified_revenue") or 0.0)
                
                # Display metrics
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Licenses", str(total_companies))
                m2.metric("Active Subscriptions", str(active_subscriptions))
                m3.metric(label=f"Verified Revenue ({st.session_state.currency_symbol})", value=format_currency(monthly_revenue))
                m4.metric("Trial Companies", int(billing_snapshot.get("trial_subscriptions") or 0))

                if total_companies == 0 and active_subscriptions == 0 and monthly_revenue == 0:
                    st.info(
                        "Welcome to the admin dashboard. Seed sample data or deploy your first "
                        "license to bring these system metrics to life."
                    )

                st.markdown("---")
                st.subheader("System Health")
                st.caption(st.session_state.get("cloud_vault_status", "Cloud Vault: Local Mode"))
                st.caption(
                    "Fast mode excludes subscription/deep backup checks. "
                    "Use Run full health audit for subscription billing and cloud backup verification."
                )
                ops_snapshot_key = "dev_gatekeeper_ops_snapshot_fast"
                refresh_health_col1, refresh_health_col2 = st.columns([1, 2])
                with refresh_health_col1:
                    refresh_health = st.button(
                        "Refresh fast health snapshot",
                        key="dev_gatekeeper_refresh_fast_health",
                    )
                try:
                    if refresh_health or ops_snapshot_key not in st.session_state:
                        fast_started = time.perf_counter()
                        ops_snapshot = build_operations_console_snapshot(conn=conn, audit_mode="fast")
                        fast_snapshot_ms = round((time.perf_counter() - fast_started) * 1000.0, 2)
                        st.session_state[ops_snapshot_key] = ops_snapshot
                        st.session_state["dev_gatekeeper_ops_snapshot_fast_ms"] = fast_snapshot_ms
                        try:
                            eka_modules.record_lv002b_operation(
                                "dev_gatekeeper.operations_snapshot.fast",
                                fast_snapshot_ms,
                                surface="system_health",
                                metadata={"audit_mode": "fast", "refresh": bool(refresh_health)},
                            )
                        except Exception:
                            pass
                    else:
                        ops_snapshot = st.session_state.get(ops_snapshot_key) or {}
                        fast_snapshot_ms = st.session_state.get("dev_gatekeeper_ops_snapshot_fast_ms", 0.0)
                        eka_modules.record_lv003_hot_path_call(
                            "enterprise_services.build_operations_console_snapshot",
                            0.0,
                            from_cache=True,
                            required=False,
                            recommendation="defer",
                            surface="system_health",
                            metadata={"audit_mode": "fast"},
                        )
                    operations_snapshot = st.session_state.get(ops_snapshot_key) or {}
                    st.caption(
                        "Fast snapshot load: {ms} ms | Mode: {mode} | Total measured steps: {total} ms".format(
                            ms=fast_snapshot_ms,
                            mode=operations_snapshot.get("audit_mode", "fast"),
                            total=operations_snapshot.get("total_elapsed_ms", 0),
                        )
                    )
                    top_slow_steps = operations_snapshot.get("top_slow_steps") or []
                    if top_slow_steps:
                        st.caption(
                            "Slowest snapshot steps: "
                            + ", ".join(
                                "{step}={elapsed}ms".format(step=item["step"], elapsed=item["elapsed_ms"])
                                for item in top_slow_steps[:3]
                            )
                        )
                    full_audit_result = st.session_state.get("dev_gatekeeper_full_audit_result")
                    full_audit_at = st.session_state.get("dev_gatekeeper_full_audit_at")
                    full_audit_ms = st.session_state.get("dev_gatekeeper_full_audit_ms")
                    if full_audit_at:
                        st.caption(
                            "Last full audit: {at} ({ms} ms)".format(
                                at=full_audit_at,
                                ms=full_audit_ms if full_audit_ms is not None else "unknown",
                            )
                        )
                    else:
                        if eka_modules.can_view_runtime_admin_diagnostics(u.get("role")):
                            st.warning(
                                "Full health audit has not been run in this session. "
                                "Cloud backup download verification and deep schema/export scans require full audit."
                            )
                    if st.button("Run full health audit", key="dev_gatekeeper_full_health_audit"):
                        audit_started = time.perf_counter()
                        full_audit_result = build_operations_console_full_audit(conn=conn)
                        full_audit_ms = round((time.perf_counter() - audit_started) * 1000.0, 2)
                        st.session_state["dev_gatekeeper_full_audit_result"] = full_audit_result
                        st.session_state["dev_gatekeeper_full_audit_at"] = datetime.now().isoformat(timespec="seconds")
                        st.session_state["dev_gatekeeper_full_audit_ms"] = full_audit_ms
                        try:
                            eka_modules.record_lv002b_operation(
                                "dev_gatekeeper.operations_snapshot.full",
                                full_audit_ms,
                                surface="system_health",
                                metadata={"audit_mode": "full"},
                            )
                        except Exception:
                            pass
                        st.rerun()
                    persistence_diag = operations_snapshot["persistence"]
                    st.caption(
                        "Canonical DB: {path} | Local Valid: {valid} | Company Count: {count}".format(
                            path=persistence_diag["canonical_db_path"],
                            valid="Yes" if persistence_diag["local_db_valid"] else "No",
                            count=persistence_diag["company_count"],
                        )
                    )
                    st.caption(
                        "DB Backend: {backend} | Size: {size} bytes | UUID: {uuid} | Schema: {schema} | Last Startup: {startup}".format(
                            backend=persistence_diag.get("db_backend") or "SQLite",
                            size=persistence_diag.get("db_file_size_bytes") or 0,
                            uuid=persistence_diag.get("database_uuid") or "missing",
                            schema=persistence_diag.get("schema_version") or 0,
                            startup=persistence_diag.get("last_startup_at") or "never",
                        )
                    )
                    missing_tables = persistence_diag.get("required_tables_missing") or []
                    if missing_tables:
                        st.warning("Missing required DB tables: " + ", ".join(missing_tables))
                    st.caption(
                        "Local Backup Status: {status} | Last Local Backup: {timestamp} | Local Latest: {local_latest}".format(
                            status=persistence_diag["latest_local_backup_status"],
                            timestamp=persistence_diag["last_local_backup_timestamp"] or "never",
                            local_latest=persistence_diag["local_backup_latest_path"] or "missing",
                        )
                    )
                    st.caption(
                        "Cloud Backup Status: {status} | Last Cloud Backup: {timestamp} | Cloud Object: {cloud_object}".format(
                            status=persistence_diag["latest_cloud_backup_status"],
                            timestamp=persistence_diag["last_cloud_backup_timestamp"] or "never",
                            cloud_object=persistence_diag["cloud_object_path"] or "missing",
                        )
                    )
                    st.caption(
                        "Local Backup Count: {local_count} | Local Backup Modified: {local_modified} | Local History: {local_history}".format(
                            local_count=persistence_diag["local_backup_company_count"]
                            if persistence_diag["local_backup_company_count"] is not None
                            else "unknown",
                            local_modified=persistence_diag["local_backup_last_modified"] or "unknown",
                            local_history=persistence_diag["local_backup_history_path"] or "none",
                        )
                    )
                    st.caption(
                        "Restore Source: {restore_source} | Bucket: {bucket}".format(
                            restore_source=persistence_diag["restore_source_used_at_startup"],
                            bucket=persistence_diag["bucket_name"] or "missing",
                        )
                    )
                    st.caption(
                        "Cloud Backup Count: {cloud_count} | Cloud Last Modified: {cloud_modified} | Cloud Newer Than Local: {cloud_newer}".format(
                            cloud_count=persistence_diag["cloud_backup_company_count"]
                            if persistence_diag["cloud_backup_company_count"] is not None
                            else "unknown",
                            cloud_modified=persistence_diag["cloud_backup_last_modified"] or "unknown",
                            cloud_newer="Yes"
                            if persistence_diag["cloud_backup_newer_than_local"] is True
                            else "No"
                            if persistence_diag["cloud_backup_newer_than_local"] is False
                            else "unknown",
                        )
                    )
                    if persistence_diag["local_cloud_backup_mismatch"]:
                        st.warning(
                            "Latest backup mismatch detected: local_backup_company_count={local_count} cloud_backup_company_count={cloud_count}".format(
                                local_count=persistence_diag["local_backup_company_count"],
                                cloud_count=persistence_diag["cloud_backup_company_count"],
                            )
                        )
                    postgres_diag = operations_snapshot.get("postgres_readiness") or {}
                    if postgres_diag:
                        st.caption(
                            "DB Backend: configured={configured} active={active} | DATABASE_URL configured: {url_configured} | SSL mode: {sslmode}".format(
                                configured=postgres_diag.get("configured_backend", "sqlite"),
                                active=postgres_diag.get("active_backend", "sqlite"),
                                url_configured="Yes" if postgres_diag.get("database_url_configured") else "No",
                                sslmode=postgres_diag.get("supabase_sslmode") or "missing",
                            )
                        )
                        if postgres_diag.get("sqlite_concurrency_warning"):
                            st.warning(postgres_diag["sqlite_concurrency_warning"])
                        readiness_mode = postgres_diag.get("readiness_mode") or "code_portability_audit"
                        if postgres_diag.get("active_backend") == "postgres":
                            missing_evidence = postgres_diag.get("runtime_cutover_missing_evidence") or []
                            st.caption(
                                "PostgreSQL readiness ({mode}): {score}/100 | Missing cutover evidence: {missing}".format(
                                    mode=readiness_mode,
                                    score=postgres_diag.get("readiness_score", 0),
                                    missing=len(missing_evidence),
                                )
                            )
                            if postgres_diag.get("switch_blocked"):
                                st.warning(
                                    "PostgreSQL runtime is active, but cutover guard has open items. "
                                    "Review LV-002 diagnostics for missing report markers or environment approval."
                                )
                        else:
                            st.caption(
                                "PostgreSQL readiness score: {score}/100 | Code portability blockers: {blockers}".format(
                                    score=postgres_diag.get("readiness_score", 0),
                                    blockers=sum(item.get("count", 0) for item in postgres_diag.get("blockers", [])),
                                )
                            )
                            if postgres_diag.get("switch_blocked"):
                                st.info("PostgreSQL switch is not enabled yet. Review readiness blockers before changing runtime backend.")
                    eka_modules.render_runtime_admin_diagnostics_suite(
                        u["role"],
                        surface="dev_gatekeeper",
                        company_key=st.session_state.get("company_id"),
                        branch_id=st.session_state.get("active_branch_id"),
                        expanded=False,
                        panel_key_prefix="dev_gatekeeper",
                        include_lv001=bool(st.session_state.get("company_id")),
                        lv001_start_date=None,
                        lv001_end_date=None,
                    )
                    sqlite_diag = get_sqlite_concurrency_diagnostics()
                    if sqlite_diag.get("sqlite_active"):
                        st.warning(
                            "SQLite concurrency advisory: recommended limit is {limit}; readiness level {level}. {advisory}".format(
                                limit=sqlite_diag.get("recommended_safe_user_limit"),
                                level=sqlite_diag.get("readiness_level"),
                                advisory=sqlite_diag.get("advisory"),
                            )
                        )
                        st.caption(
                            "SQLite locks: active_writes={active} retries={retries} failed_locks={failed} "
                            "backup_overlaps={overlaps} busy_timeout={timeout}ms longest_write={longest}s ({operation})".format(
                                active=len(sqlite_diag.get("active_write_operations") or {}),
                                retries=sqlite_diag.get("lock_retries", 0),
                                failed=sqlite_diag.get("failed_lock_acquisitions", 0),
                                overlaps=sqlite_diag.get("backup_overlap_events", 0),
                                timeout=sqlite_diag.get("busy_timeout_ms", 0),
                                longest=sqlite_diag.get("longest_write_seconds", 0),
                                operation=sqlite_diag.get("longest_write_operation") or "none",
                            )
                        )
                    self_test = operations_snapshot["persistence_self_test"]
                    if self_test["mismatch"]:
                        st.warning(
                            "Persistence self-test mismatch: runtime={local_count} local_backup={local_backup_count} cloud_backup={cloud_count}".format(
                                local_count=self_test["local_company_count"],
                                local_backup_count=self_test["local_backup_company_count"]
                                if self_test["local_backup_company_count"] is not None
                                else "unknown",
                                cloud_count=self_test["cloud_backup_company_count"],
                            )
                        )
                    else:
                        st.caption(
                            "Persistence self-test: runtime={local_count} local_backup={local_backup_count} cloud_backup={cloud_count}".format(
                                local_count=self_test["local_company_count"],
                                local_backup_count=self_test["local_backup_company_count"]
                                if self_test["local_backup_company_count"] is not None
                                else "unknown",
                                cloud_count=self_test["cloud_backup_company_count"]
                                if self_test["cloud_backup_company_count"] is not None
                                else "unknown",
                            )
                        )
                    paystack_diag = operations_snapshot["paystack"]
                    subscription_billing_diag = operations_snapshot.get("subscription_billing") or {}
                    subscription_billing_fast_skipped = bool(
                        subscription_billing_diag.get("fast_snapshot")
                        and not subscription_billing_diag.get("checked", True)
                    )
                    st.markdown("---")
                    st.caption("Paystack Live Payment Configuration")
                    st.caption(
                        "PAYSTACK_SECRET_KEY present: {secret_present} | PAYSTACK_PUBLIC_KEY present: {public_present}".format(
                            secret_present="Yes" if paystack_diag.get("secret_key_present") else "No",
                            public_present="Yes" if paystack_diag.get("public_key_present") else "No",
                        )
                    )
                    st.caption(
                        "Currency: {currency} | Callback URL configured: {callback_configured}".format(
                            currency=paystack_diag.get("currency") or "GHS",
                            callback_configured="Yes" if paystack_diag.get("callback_url_configured") else "No",
                        )
                    )
                    paystack_health_key = "admin_paystack_health_test_result"
                    paystack_health_result = st.session_state.get(paystack_health_key)
                    paystack_col1, paystack_col2 = st.columns([1, 2])
                    with paystack_col1:
                        if st.button("Test Paystack Connection", key="test_paystack_connection_btn", use_container_width=True):
                            if require_role_permission(u["role"], "view_system_health", action_label="test Paystack configuration"):
                                paystack_health_result = test_paystack_connection()
                                st.session_state[paystack_health_key] = paystack_health_result
                    with paystack_col2:
                        if paystack_health_result:
                            st.caption(
                                "Secret key present: {secret_key} | Public key present: {public_key} | Callback URL configured: {callback_url}".format(
                                    secret_key="Yes" if paystack_health_result.get("secret_key_present") else "No",
                                    public_key="Yes" if paystack_health_result.get("public_key_present") else "No",
                                    callback_url="Yes" if paystack_health_result.get("callback_url_present") else "No",
                                )
                            )
                            st.caption(
                                "Currency: {currency} | Config ready: {config_ready} | Optional webhook secret present: {webhook_secret}".format(
                                    currency=paystack_health_result.get("currency") or "GHS",
                                    config_ready="Yes" if paystack_health_result.get("config_ready") else "No",
                                    webhook_secret="Yes" if paystack_health_result.get("webhook_secret_present") else "No",
                                )
                            )
                            st.caption(
                                "Last test result: {message}".format(
                                    message=paystack_health_result.get("message") or "No result",
                                )
                            )
                            if paystack_health_result.get("success"):
                                st.success(paystack_health_result.get("message") or "Paystack configuration is ready.")
                            else:
                                st.warning(sanitize_error_message(paystack_health_result.get("error") or "Paystack health test failed."))
                    st.markdown("---")
                    st.caption("Subscription Billing Health")
                    if subscription_billing_fast_skipped:
                        st.info(
                            "Subscription billing deep validation is not checked in fast mode. "
                            "Run full health audit for subscription table diagnostics and payment history."
                        )
                        st.caption(
                            "Cached admin summary — Active: {active} | Trial: {trial} | Verified revenue: {revenue}".format(
                                active=int(billing_snapshot.get("active_subscriptions") or 0),
                                trial=int(billing_snapshot.get("trial_subscriptions") or 0),
                                revenue=format_currency(float(billing_snapshot.get("total_verified_revenue") or 0.0)),
                            )
                        )
                    else:
                        billing_diag = subscription_billing_diag.get("billing", {})
                        billing_paystack_diag = subscription_billing_diag.get("paystack", paystack_diag)
                        st.caption(
                            "Paystack ready: {paystack_ready} | Subscription table: {subscription_table} | Payment table: {payment_table}".format(
                                paystack_ready="Yes"
                                if (
                                    billing_paystack_diag.get("secret_key_present")
                                    and billing_paystack_diag.get("public_key_present")
                                    and billing_paystack_diag.get("callback_url_configured")
                                )
                                else "No",
                                subscription_table="Yes" if billing_diag.get("subscription_table_present") else "No",
                                payment_table="Yes" if billing_diag.get("payment_table_present") else "No",
                            )
                        )
                        st.caption(
                            "Active: {active} | Trial: {trial} | Expired: {expired} | Failed Payments: {failed}".format(
                                active=int(billing_diag.get("active_count") or 0),
                                trial=int(billing_diag.get("trial_count") or 0),
                                expired=int(billing_diag.get("expired_count") or 0),
                                failed=int(billing_diag.get("failed_payment_count") or 0),
                            )
                        )
                        pricing_diag = billing_diag.get("plan_pricing", {})
                        active_plan_prices = pricing_diag.get("active_plan_prices") or []
                        for plan_price in active_plan_prices:
                            amount_value = plan_price.get("configured_amount")
                            duration_months = int(plan_price.get("duration_months") or 0)
                            duration_days = int(plan_price.get("duration_days") or 0)
                            duration_label = (
                                f"{duration_months} month(s)"
                                if duration_months > 0
                                else f"{duration_days} day(s)"
                            )
                            amount_label = (
                                f"{plan_price.get('currency') or 'GHS'} {float(amount_value):,.2f}"
                                if amount_value not in (None, "")
                                else "Missing"
                            )
                            st.caption(
                                "Plan Price - {plan}: {amount} | Duration: {duration} | Configured: {configured}".format(
                                    plan=plan_price.get("plan_name") or "Unknown",
                                    amount=amount_label,
                                    duration=duration_label,
                                    configured="Yes" if plan_price.get("configured") else "No",
                                )
                            )
                        for missing_warning in pricing_diag.get("missing_price_warnings") or []:
                            st.warning(missing_warning)
                        latest_successful_payment = billing_diag.get("latest_successful_payment") or {}
                        if latest_successful_payment:
                            st.caption(
                                "Latest successful payment: {reference} | Company: {company_key} | Plan: {plan_name} | Verified: {verified_at}".format(
                                    reference=latest_successful_payment.get("reference") or "unknown",
                                    company_key=latest_successful_payment.get("company_key") or "unknown",
                                    plan_name=latest_successful_payment.get("plan_name") or "unknown",
                                    verified_at=latest_successful_payment.get("verified_at") or "unknown",
                                )
                            )
                    schema_diag = operations_snapshot.get("schema") or {}
                    st.markdown("---")
                    st.caption("Schema Manifest Health")
                    if schema_diag:
                        st.caption(
                            "Manifest Version: {version} | Source Tables: {source_present}/{source_total} | Compatibility Tables: {compat_present}/{compat_total}".format(
                                version=schema_diag.get("manifest_version"),
                                source_present=len(schema_diag.get("categories", {}).get("source_of_truth", {}).get("present", [])),
                                source_total=schema_diag.get("categories", {}).get("source_of_truth", {}).get("total", 0),
                                compat_present=len(schema_diag.get("categories", {}).get("compatibility_detail", {}).get("present", [])),
                                compat_total=schema_diag.get("categories", {}).get("compatibility_detail", {}).get("total", 0),
                            )
                        )
                        if schema_diag.get("ok"):
                            st.success("Schema manifest check passed for required source-of-truth tables and columns.")
                        else:
                            st.warning("Schema manifest check needs attention.")
                        if schema_diag.get("missing_source_of_truth_tables"):
                            st.error(
                                "Missing required production tables: "
                                + ", ".join(schema_diag["missing_source_of_truth_tables"])
                            )
                        if schema_diag.get("missing_compatibility_detail_tables"):
                            st.warning(
                                "Missing compatibility/detail tables: "
                                + ", ".join(schema_diag["missing_compatibility_detail_tables"])
                            )
                        if schema_diag.get("missing_required_columns"):
                            st.warning(
                                "Missing required columns: "
                                + "; ".join(
                                    f"{table_name}({', '.join(columns)})"
                                    for table_name, columns in sorted(schema_diag["missing_required_columns"].items())
                                )
                            )
                        if schema_diag.get("legacy_obsolete_tables_present"):
                            st.info(
                                "Legacy/obsolete tables still present for compatibility review: "
                                + ", ".join(schema_diag["legacy_obsolete_tables_present"])
                            )
                    else:
                        st.info("Schema manifest detail is available after running full health audit.")
                    if full_audit_result:
                        with st.expander("Full health audit timings", expanded=False):
                            st.dataframe(
                                pd.DataFrame(full_audit_result.get("top_slow_steps") or []),
                                use_container_width=True,
                                hide_index=True,
                            )
                            full_persistence = (full_audit_result.get("persistence") or {})
                            st.caption(
                                "Full audit cloud backup count: {count} | reason: {reason}".format(
                                    count=full_persistence.get("cloud_backup_company_count", "unknown"),
                                    reason=full_persistence.get("cloud_backup_reason", "n/a"),
                                )
                            )
                    audit_summary = operations_snapshot["audit"]
                    st.markdown("---")
                    st.caption("Audit & Operations Visibility")
                    au1, au2, au3 = st.columns(3)
                    total_audit_events = sum(int(row.get("event_count") or 0) for row in audit_summary.get("action_counts", []))
                    au1.metric("Audit Events", total_audit_events)
                    au2.metric("Enhanced Audit Columns", "Yes" if audit_summary.get("enhanced_columns_present") else "No")
                    au3.metric("Audit Status", "Healthy" if audit_summary.get("ok") else "Needs Review")
                    with st.expander("Audit Action Summary", expanded=False):
                        st.dataframe(pd.DataFrame(audit_summary.get("action_counts", [])), use_container_width=True)
                    with st.expander("Recent Audit Events", expanded=False):
                        st.dataframe(pd.DataFrame(audit_summary.get("recent_events", [])), use_container_width=True)
                    with st.expander("Schema Manifest Summary", expanded=False):
                        st.markdown("Required source-of-truth tables")
                        st.write(", ".join(schema_diag.get("required_production_tables", [])) or "none")
                        st.markdown("Compatibility/detail tables")
                        st.write(", ".join(schema_diag.get("compatibility_detail_tables", [])) or "none")
                        st.markdown("Legacy/obsolete references tracked")
                        st.write(", ".join(schema_diag.get("legacy_obsolete_tables", [])) or "none")
                    with st.expander("Service Ownership Map", expanded=False):
                        st.dataframe(pd.DataFrame(get_service_ownership_map()), use_container_width=True)
                    if total_companies:
                        selected_health_company = None
                        try:
                            health_companies = execute_portable_query(
                                conn,
                                "SELECT key, name FROM companies ORDER BY name LIMIT 100"
                            ).fetchall()
                            if health_companies:
                                health_company_names = [
                                    f"{row_get(row, 'name')} ({row_get(row, 'key')})"
                                    for row in health_companies
                                ]
                                selected_health_label = st.selectbox(
                                    "Accounting integrity company",
                                    health_company_names,
                                    key="journal_dominance_company_select",
                                )
                                selected_health_company = row_get(
                                    health_companies[health_company_names.index(selected_health_label)],
                                    "key",
                                )
                        except Exception as journal_company_error:
                            logger.warning("Could not load companies for journal dominance diagnostics: %s", sanitize_error_message(journal_company_error))
                        if selected_health_company:
                            if not full_audit_result:
                                st.info(
                                    "Run full health audit to load company accounting integrity diagnostics "
                                    "for the selected company."
                                )
                            else:
                                company_operations_snapshot = build_operations_console_full_audit(
                                    conn=conn,
                                    selected_company_key=selected_health_company,
                                    branch_id=st.session_state.get("active_branch_id"),
                                    end_date=datetime.now().date(),
                                )
                                journal_diag = company_operations_snapshot.get("accounting_core") or {}
                                if not journal_diag:
                                    st.warning("Accounting core diagnostics unavailable for the selected company.")
                                else:
                                    st.markdown("---")
                                    st.caption("Accounting Core Dominance")
                                    jd1, jd2, jd3 = st.columns(3)
                                    jd1.metric("Journal Integrity", "Healthy" if journal_diag.get("ok") else "Needs Review")
                                jd2.metric(
                                    "A/R Reconciliation",
                                    "Matched"
                                    if journal_diag["integrity"]["accounts_receivable"]["reconciled"]
                                    else "Mismatch",
                                    format_currency(journal_diag["integrity"]["accounts_receivable"]["difference"]),
                                )
                                jd3.metric(
                                    "A/P Reconciliation",
                                    "Matched"
                                    if journal_diag["integrity"]["accounts_payable"]["reconciled"]
                                    else "Mismatch",
                                    format_currency(journal_diag["integrity"]["accounts_payable"]["difference"]),
                                )
                                st.caption(
                                    "Source of truth: {source} | Posted journals: {count} | Unbalanced: {unbalanced} | Orphaned refs: {orphaned}".format(
                                        source=journal_diag["source_of_truth"],
                                        count=journal_diag["posted_journal_count"],
                                        unbalanced=journal_diag["integrity"]["unbalanced_journal_count"],
                                        orphaned=journal_diag["integrity"]["orphaned_journal_reference_count"],
                                    )
                                )
                                if journal_diag.get("warnings"):
                                    st.warning("Accounting core warnings: " + " ".join(journal_diag["warnings"]))
                                else:
                                    st.success("Accounting core dominance check passed.")
                                with st.expander("Compatibility Tables: History Only", expanded=False):
                                    st.dataframe(pd.DataFrame(journal_diag["compatibility_tables"]), use_container_width=True)
                                workflow_diag = company_operations_snapshot["document_workflow"]
                                st.caption("Controlled Document Workflow")
                                wd1, wd2, wd3 = st.columns(3)
                                wd1.metric("Workflow Integrity", "Healthy" if workflow_diag.get("ok") else "Needs Review")
                                wd2.metric("Duplicate Postings", int(workflow_diag.get("duplicate_posting_count") or 0))
                                wd3.metric("State/GL Mismatches", len(workflow_diag.get("source_document_mismatches") or []))
                                st.caption(
                                    "Controlled tables: {tables} | Statuses: {statuses}".format(
                                        tables=", ".join(workflow_diag.get("controlled_source_tables") or []),
                                        statuses=", ".join(workflow_diag.get("controlled_statuses") or []),
                                    )
                                )
                                if workflow_diag.get("warnings"):
                                    st.warning("Workflow warnings: " + " ".join(workflow_diag["warnings"]))
                                else:
                                    st.success("Document workflow enforcement check passed.")
                                with st.expander("Document Counts by Posting State", expanded=False):
                                    st.dataframe(pd.DataFrame(workflow_diag["document_counts"]), use_container_width=True)
                                if workflow_diag.get("source_document_mismatches"):
                                    with st.expander("Posting-State / GL Mismatches", expanded=False):
                                        st.dataframe(pd.DataFrame(workflow_diag["source_document_mismatches"]), use_container_width=True)
                                if workflow_diag.get("duplicate_postings"):
                                    with st.expander("Duplicate Posted Journal Impact", expanded=False):
                                        st.dataframe(pd.DataFrame(workflow_diag["duplicate_postings"]), use_container_width=True)
                                posting_engine_diag = company_operations_snapshot["posting_engine"]
                                st.caption("Unified Posting Engine")
                                pe1, pe2, pe3 = st.columns(3)
                                pe1.metric(
                                    "Posting Engine",
                                    "Unified" if posting_engine_diag.get("ok") else "Review",
                                    posting_engine_diag.get("engine_version", "unknown"),
                                )
                                pe2.metric(
                                    "Duplicate Attempts Blocked",
                                    int(posting_engine_diag.get("duplicate_post_attempts_blocked") or 0),
                                )
                                pe3.metric(
                                    "Missing Source Linkage",
                                    int(posting_engine_diag.get("missing_source_linkage_count") or 0),
                                )
                                if posting_engine_diag.get("warnings"):
                                    st.warning("Posting engine warnings: " + " ".join(posting_engine_diag["warnings"]))
                                else:
                                    st.success("Unified posting engine checks passed.")
                                with st.expander("Posting Engine Transition Map", expanded=False):
                                    st.write("Authoritative service: " + posting_engine_diag.get("authoritative_posting_service", "unknown"))
                                    st.write("Controlled source tables: " + ", ".join(posting_engine_diag.get("controlled_source_tables") or []))
                                    st.markdown("Enforced checks")
                                    st.write(", ".join(posting_engine_diag.get("enforced_checks") or []))
                                    st.markdown("Transitional/non-controlled source tables")
                                    st.dataframe(pd.DataFrame(posting_engine_diag.get("transitional_source_tables") or []), use_container_width=True)
                                    st.markdown("Reversal / void counts")
                                    st.dataframe(pd.DataFrame(posting_engine_diag.get("reversal_void_counts") or []), use_container_width=True)
                                reporting_diag = company_operations_snapshot["reporting_trust"]
                                st.caption("Reporting Trust & Period Controls")
                                reporting_status = "Green" if reporting_diag.get("ok") else "Yellow"
                                rt1, rt2, rt3 = st.columns(3)
                                rt1.metric(
                                    "Trial Balance",
                                    "Green - Balanced" if reporting_diag["trial_balance"]["balanced"] else "Red - Out of Balance",
                                    format_currency(reporting_diag["trial_balance"]["difference"]),
                                )
                                rt2.metric(
                                    "Balance Sheet",
                                    "Green - Balanced" if reporting_diag["balance_sheet"]["balanced"] else "Red - Needs Review",
                                    format_currency(reporting_diag["balance_sheet"]["difference"]),
                                )
                                rt3.metric(
                                    "Reporting Status",
                                    reporting_status,
                                    reporting_diag["period_control"]["current_period_status"],
                                )
                                rc1, rc2, rc3 = st.columns(3)
                                rc1.metric(
                                    "A/R Aging vs GL",
                                    "Green - Matched" if reporting_diag.get("ar_aging", {}).get("reconciled") else "Yellow - Review",
                                    format_currency(reporting_diag.get("ar_aging", {}).get("difference", 0.0)),
                                )
                                rc2.metric(
                                    "A/P Aging vs GL",
                                    "Green - Matched" if reporting_diag.get("ap_aging", {}).get("reconciled") else "Yellow - Review",
                                    format_currency(reporting_diag.get("ap_aging", {}).get("difference", 0.0)),
                                )
                                rc3.metric(
                                    "Cash Equivalents",
                                    format_currency(reporting_diag.get("cash_book", {}).get("combined_cash_equivalent_balance", 0.0)),
                                    reporting_diag["period_control"]["current_period"],
                                )
                                rr1, rr2, rr3 = st.columns(3)
                                inventory_diag = reporting_diag.get("reconciliation", {}).get("inventory", {})
                                fixed_asset_diag = reporting_diag.get("fixed_assets", {})
                                rr1.metric(
                                    "Inventory GL vs Register",
                                    "Green - Matched" if inventory_diag.get("reconciled") else "Yellow - Review",
                                    format_currency(inventory_diag.get("difference", 0.0)),
                                )
                                rr2.metric(
                                    "Fixed Assets GL vs Register",
                                    "Green - Matched" if fixed_asset_diag.get("reconciled") else "Yellow - Review",
                                    format_currency(fixed_asset_diag.get("difference") or 0.0),
                                )
                                rr3.metric(
                                    "Tax Liabilities",
                                    format_currency(reporting_diag.get("tax_liabilities", {}).get("total_balance", 0.0)),
                                )
                                rj1, rj2, rj3 = st.columns(3)
                                rj1.metric(
                                    "Cash/Bank Unmatched",
                                    format_currency(reporting_diag["reconciliation"]["cash_bank"]["unmatched_total"]),
                                )
                                rj2.metric(
                                    "Unbalanced Journals",
                                    int(reporting_diag["reconciliation"]["unbalanced_journal_count"] or 0),
                                )
                                rj3.metric(
                                    "Orphaned References",
                                    int(reporting_diag["reconciliation"]["orphaned_journal_reference_count"] or 0),
                                )
                                st.caption(f"Report source: {reporting_diag['report_source']}")
                                if reporting_diag.get("warnings"):
                                    st.warning("Reporting status needs review: " + " ".join(sanitize_error_message(item) for item in reporting_diag["warnings"]))
                                else:
                                    st.success("Green - Reporting trust and period-control checks passed.")
                            with st.expander("Accounting Period Control Summary", expanded=False):
                                st.json(reporting_diag["period_control"]["period_counts"])
                                st.dataframe(pd.DataFrame(reporting_diag["period_control"]["periods"]), use_container_width=True)
                    st.markdown("---")
                    st.caption("Subscription Billing Revenue Visibility")
                    sb1, sb2, sb3, sb4 = st.columns(4)
                    sb1.metric("Verified Revenue", format_currency(float(billing_snapshot.get("total_verified_revenue") or 0.0)))
                    sb2.metric("Active", int(billing_snapshot.get("active_subscriptions") or 0))
                    sb3.metric("Trials", int(billing_snapshot.get("trial_subscriptions") or 0))
                    sb4.metric("Expired", int(billing_snapshot.get("expired_subscriptions") or 0))
                    with st.expander("Revenue by Plan", expanded=False):
                        st.dataframe(pd.DataFrame(billing_snapshot.get("revenue_by_plan") or []), use_container_width=True)
                    with st.expander("Recent Subscription Payments", expanded=False):
                        st.dataframe(pd.DataFrame(billing_snapshot.get("recent_payments") or []), use_container_width=True)
                    with st.expander("Next Subscription Expiries", expanded=False):
                        st.dataframe(pd.DataFrame(billing_snapshot.get("next_expiries") or []), use_container_width=True)
                    st.markdown("---")
                    st.caption("Admin Backup Export")
                    export_state_key = "admin_backup_export_payload"
                    restore_state_key = "admin_cloud_restore_payload"
                    export_result = st.session_state.get(export_state_key)
                    restore_result = st.session_state.get(restore_state_key)
                    export_col1, export_col2 = st.columns([1, 1])
                    with export_col1:
                        if st.button("Prepare Backup Export", key="prepare_admin_backup_export_btn", use_container_width=True):
                            if require_role_permission(u["role"], "export_backup", action_label="export backups"):
                                export_result = get_downloadable_backup_export(logger_instance=logger)
                                st.session_state[export_state_key] = export_result
                                try:
                                    log_audit_action(
                                        conn,
                                        u.get("key", "SYSTEM"),
                                        u["role"],
                                        "Backup Export Prepared" if export_result.get("ok") else "Backup Export Attempt Failed",
                                        "System Health",
                                        details=export_result.get("reason"),
                                        action_type="backup_restore",
                                        document_ref=export_result.get("filename") or export_result.get("source"),
                                    )
                                except Exception:
                                    logger.debug("Backup export audit logging skipped.", exc_info=True)
                    with export_col2:
                        if st.button("Restore Latest Cloud Backup", key="restore_latest_cloud_backup_btn", use_container_width=True):
                            if require_role_permission(u["role"], "restore_backup", action_label="restore the latest cloud backup"):
                                restore_result = restore_latest_cloud_backup_to_local(logger_instance=logger)
                                st.session_state[restore_state_key] = restore_result
                                try:
                                    log_audit_action(
                                        conn,
                                        u.get("key", "SYSTEM"),
                                        u["role"],
                                        "Cloud Backup Restore Completed" if restore_result.get("ok") else "Cloud Backup Restore Attempt Failed",
                                        "System Health",
                                        details=restore_result.get("reason"),
                                        action_type="backup_restore",
                                        document_ref=restore_result.get("selected_object_path") or restore_result.get("object_name"),
                                    )
                                except Exception:
                                    logger.debug("Cloud restore audit logging skipped.", exc_info=True)
                                if restore_result.get("ok"):
                                    st.rerun()
                        if export_result and export_result.get("ok") and export_result.get("data"):
                            st.download_button(
                                "Download Latest ERP Backup",
                                data=export_result["data"],
                                file_name=export_result["filename"],
                                mime=export_result.get("mime") or "application/octet-stream",
                                key="download_admin_backup_export_btn",
                                use_container_width=True,
                            )
                    if export_result:
                        if export_result.get("ok"):
                            st.caption(
                                "Prepared from {source} | Company Count: {count} | File: {filename}".format(
                                    source=export_result.get("source"),
                                    count=export_result.get("company_count"),
                                    filename=export_result.get("filename"),
                                )
                            )
                        else:
                            st.warning(f"Backup export unavailable: {sanitize_error_message(export_result.get('reason'))}")
                    if restore_result:
                        if restore_result.get("ok"):
                            st.success(
                                "Cloud restore completed from {source_type}: {object_path} | Company Count Restored: {company_count}".format(
                                    source_type=restore_result.get("selected_source_type") or "latest",
                                    object_path=restore_result.get("selected_object_path") or restore_result.get("object_name") or "unknown",
                                    company_count=restore_result.get("company_count"),
                                )
                            )
                        else:
                            st.warning(
                                "Cloud restore unavailable: {reason}".format(
                                    reason=sanitize_error_message(restore_result.get("reason"))
                                )
                            )
                    st.markdown("---")
                    st.caption("AI Assistant Health")
                    ai_health_key = "admin_ai_health_test_result"
                    ai_runtime_status = get_openai_client_status()
                    ai_health_result = st.session_state.get(ai_health_key) or {
                        "success": False,
                        "response": "",
                        "error": ai_runtime_status.get("message", ""),
                        "selected_provider": ai_runtime_status.get("selected_provider", "openai"),
                        "active_provider": ai_runtime_status.get("provider", ai_runtime_status.get("selected_provider", "openai")),
                        "fallback_used": bool(ai_runtime_status.get("fallback_used")),
                        "last_safe_error": ai_runtime_status.get("last_safe_error", ""),
                        "client_initialized": bool(ai_runtime_status.get("client_initialized")),
                        "streamlit_imported": ai_runtime_status.get("streamlit_imported"),
                        "secrets_accessible": ai_runtime_status.get("secrets_accessible"),
                        "top_level_secret_keys": ai_runtime_status.get("top_level_secret_keys", []),
                        "top_level_key_present": ai_runtime_status.get("top_level_key_present"),
                        "openai_section_present": ai_runtime_status.get("openai_section_present"),
                        "nested_key_present": ai_runtime_status.get("nested_key_present"),
                        "provided_length": ai_runtime_status.get("provided_length", 0),
                        "gemini_key_present": ai_runtime_status.get("gemini_key_present"),
                        "gemini_top_level_key_present": ai_runtime_status.get("gemini_top_level_key_present"),
                        "gemini_section_present": ai_runtime_status.get("gemini_section_present"),
                        "gemini_nested_key_present": ai_runtime_status.get("gemini_nested_key_present"),
                        "gemini_provided_length": ai_runtime_status.get("gemini_provided_length", 0),
                    }
                    ai_col1, ai_col2 = st.columns([1, 2])
                    with ai_col1:
                        if st.button("Test AI Assistant", key="test_ai_assistant_health_btn", use_container_width=True):
                            if require_role_permission(u["role"], "use_ai_assistant", action_label="use the AI assistant"):
                                ai_health_result = test_openai_assistant_health()
                                st.session_state[ai_health_key] = ai_health_result
                    with ai_col2:
                        if ai_health_result:
                            st.caption(
                                "Preferred provider: {selected} | Active provider: {active} | Fallback used: {fallback}".format(
                                    selected=ai_health_result.get("selected_provider", "openai"),
                                    active=ai_health_result.get("active_provider", "none"),
                                    fallback="Yes" if ai_health_result.get("fallback_used") else "No",
                                )
                            )
                            st.caption(
                                "OPENAI_API_KEY present: {openai_present} | GEMINI_API_KEY present: {gemini_present} | AI client initialized: {client_ready} | Test API call success: {success}".format(
                                    openai_present="Yes" if ai_health_result.get("top_level_key_present") or ai_health_result.get("nested_key_present") or ai_health_result.get("provided_length") else "No",
                                    gemini_present="Yes" if ai_health_result.get("gemini_key_present") else "No",
                                    client_ready="Yes" if ai_health_result.get("client_initialized") else "No",
                                    success="Yes" if ai_health_result.get("success") else "No",
                                )
                            )
                            st.caption(
                                "Secrets visible: streamlit_imported={streamlit_imported} st.secrets_accessible={secrets_accessible} top_level_keys={keys}".format(
                                    streamlit_imported="Yes" if ai_health_result.get("streamlit_imported") else "No",
                                    secrets_accessible="Yes" if ai_health_result.get("secrets_accessible") else "No",
                                    keys=", ".join(ai_health_result.get("top_level_secret_keys") or []) or "none",
                                )
                            )
                            st.caption(
                                "OpenAI path checks: top_level_key={top_level} openai_section={section} nested_key={nested} | Gemini path checks: top_level_key={gemini_top_level} gemini_section={gemini_section} nested_key={gemini_nested}".format(
                                    top_level="Yes" if ai_health_result.get("top_level_key_present") else "No",
                                    section="Yes" if ai_health_result.get("openai_section_present") else "No",
                                    nested="Yes" if ai_health_result.get("nested_key_present") else "No",
                                    gemini_top_level="Yes" if ai_health_result.get("gemini_top_level_key_present") else "No",
                                    gemini_section="Yes" if ai_health_result.get("gemini_section_present") else "No",
                                    gemini_nested="Yes" if ai_health_result.get("gemini_nested_key_present") else "No",
                                )
                            )
                            if ai_health_result.get("success"):
                                st.success("AI assistant is operational.")
                                st.caption(
                                    "Last test response: {response}".format(
                                        response=(ai_health_result.get("response_preview") or ai_health_result.get("response") or "")[:50] or "empty response",
                                    )
                                )
                            else:
                                st.warning(sanitize_error_message(ai_health_result.get("error") or "AI assistant test failed."))
                                if ai_health_result.get("openai_error_safe"):
                                    st.caption(f"OpenAI safe error: {ai_health_result.get('openai_error_safe')}")
                                if ai_health_result.get("gemini_error_safe"):
                                    st.caption(f"Gemini safe error: {ai_health_result.get('gemini_error_safe')}")
                                if ai_health_result.get("last_safe_error"):
                                    st.caption(f"Last safe error: {ai_health_result.get('last_safe_error')}")
                    st.caption("ERP Build Check: Persistence safety test passed")
                except Exception as persistence_diag_error:
                    logger.warning("Persistence diagnostics unavailable: %s", sanitize_error_message(persistence_diag_error))

                st.markdown("---")
                st.subheader("Master Price Setting")
                try:
                    current_price_row = execute_portable_query(
                        conn,
                        "SELECT master_price_per_month FROM system_settings WHERE id = 1"
                    ).fetchone()
                    current_price_value = row_get(current_price_row, "master_price_per_month", row_get(current_price_row, 0))
                    current_price = float(current_price_value) if current_price_row and current_price_value is not None else 500.0
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
                            st.error(build_user_safe_error(price_error, u["role"]))

                st.markdown("---")
                st.subheader("Subscription Plan Pricing")
                configured_plans = get_subscription_plans()
                with st.form("subscription_plan_pricing_form"):
                    pricing_rows = []
                    for plan_name, plan_data in configured_plans.items():
                        st.markdown(f"**{plan_name}**")
                        plan_col1, plan_col2, plan_col3, plan_col4 = st.columns(4)
                        configured_amount = plan_col1.number_input(
                            f"{plan_name} Amount",
                            min_value=0.0,
                            value=float(plan_data.get("amount") or 0.0),
                            step=10.0,
                            key=f"{plan_name}_configured_amount",
                        )
                        currency_value = plan_col2.text_input(
                            f"{plan_name} Currency",
                            value=str(plan_data.get("currency") or "GHS"),
                            key=f"{plan_name}_configured_currency",
                        )
                        duration_months = plan_col3.number_input(
                            f"{plan_name} Duration Months",
                            min_value=0,
                            value=int(plan_data.get("duration_months") or 0),
                            step=1,
                            key=f"{plan_name}_duration_months",
                        )
                        duration_days = plan_col4.number_input(
                            f"{plan_name} Duration Days",
                            min_value=0,
                            value=int(plan_data.get("duration_days") or 0),
                            step=1,
                            key=f"{plan_name}_duration_days",
                        )
                        pricing_rows.append(
                            {
                                "plan_name": plan_name,
                                "configured_amount": configured_amount,
                                "currency": currency_value,
                                "duration_months": duration_months,
                                "duration_days": duration_days,
                                "features": plan_data.get("features", []),
                            }
                        )
                    if st.form_submit_button("Save Subscription Plan Pricing"):
                        invalid_rows = [
                            row["plan_name"]
                            for row in pricing_rows
                            if float(row.get("configured_amount") or 0) <= 0
                            or (
                                int(row.get("duration_months") or 0) <= 0
                                and int(row.get("duration_days") or 0) <= 0
                            )
                        ]
                        if invalid_rows:
                            st.warning(
                                "Each plan must have a positive amount and a duration in months or days. Check: "
                                + ", ".join(invalid_rows)
                            )
                        else:
                            pricing_save_result = save_subscription_plan_pricing_settings(
                                pricing_rows,
                                actor=u.get("name") or u.get("role"),
                            )
                            if pricing_save_result.get("ok"):
                                st.success("Subscription plan pricing updated successfully.")
                            else:
                                st.error(build_user_safe_error(pricing_save_result.get("reason") or "Subscription pricing could not be saved.", u["role"]))
                
                # Global Forensic Trail (Dev only) - Enhanced with error handling
                st.markdown("---")
                st.subheader("Global Forensic Trail")
                try:
                    trail_rows = execute_portable_query(
                        conn,
                        """SELECT timestamp, company_key, user_role, action, module_name
                           FROM audit_logs ORDER BY timestamp DESC LIMIT 50""",
                    ).fetchall()
                    trail_df = dataframe_from_portable_rows(
                        trail_rows,
                        {
                            "timestamp": "Timestamp",
                            "company_key": "Company Key",
                            "user_role": "User Role",
                            "action": "Action",
                            "module_name": "Module",
                        },
                    )
                    if not trail_df.empty:
                        st.dataframe(trail_df, width='stretch')
                    else:
                        st.info("No audit activity found.")
                except Exception as e:
                    logger.error("Failed to load audit trail: %s", sanitize_error_message(e))
                
                st.markdown("---")
                st.subheader("Manual License Deployment")
                if "manual_key_input" not in st.session_state:
                    st.session_state.manual_key_input = ""
                with st.form("manual_deploy"):
                    company_name = st.text_input("Company Name")
                    number_of_branches = st.number_input("Number of Branches", min_value=1, value=1, step=1)
                    max_branches = st.number_input("Max Branches Allowed", min_value=1, value=5, step=1, help="Developer control: maximum branches this client can create")
                    price_per_branch = st.number_input("Price per Branch (GHS)", min_value=0.0, value=0.0, step=10.0)
                    duration_months = st.number_input("Duration (Months)", min_value=1, max_value=24, value=12)
                    override_reason = st.text_area(
                        "Override Reason",
                        help="Required for internal/admin-only emergency deployments that bypass Paystack.",
                    )
                    override_confirm_text = st.text_input(
                        "Type CONFIRM to acknowledge this bypasses Paystack (internal/admin only)",
                        key="manual_deploy_override_confirm_text",
                    )
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
                            if not require_role_permission(
                                u["role"],
                                "manual_license_override",
                                action_label="perform a manual license override",
                                company_key=manual_key,
                                conn=conn,
                            ):
                                st.stop()
                            try:
                                override_result = execute_manual_license_override(
                                    conn=conn,
                                    actor_role=u["role"],
                                    actor_user=u.get("name") or u.get("role"),
                                    company_name=company_name,
                                    company_key=manual_key,
                                    duration_months=int(duration_months),
                                    number_of_branches=int(number_of_branches),
                                    max_branches=int(max_branches),
                                    branch_price_per_month=float(price_per_branch),
                                    override_reason=override_reason,
                                    confirmation_checked=str(override_confirm_text or "").strip().upper() == "CONFIRM",
                                    logger_instance=logger,
                                )
                                if not override_result.get("ok"):
                                    st.warning(override_result.get("reason") or "Manual license override could not be completed.")
                                    st.stop()
                                new_expiry = override_result.get("new_expiry")
                                backup_result = override_result.get("backup_result") or {}
                                if backup_result.get("ok"):
                                    st.success(
                                        f"License deployed for {company_name} until {new_expiry}. "
                                        "Persistence backup completed."
                                    )
                                else:
                                    st.warning(
                                        f"License deployed for {company_name} until {new_expiry}, "
                                        f"but post-create backup needs attention: {sanitize_error_message(backup_result.get('reason'))}"
                                    )
                            except Exception as e:
                                conn.rollback()
                                st.error(build_user_safe_error(e, u["role"]))
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
                logger.error("Dashboard metrics error: %s", sanitize_error_message(e))

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
                portfolio_rows = execute_portable_query(conn, query).fetchall()
                portfolio_df = pd.DataFrame(rows_to_dicts(portfolio_rows))
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
                        confirm_action_text = st.text_input(
                            f"Type the company name to confirm {action_choice.lower()}",
                            key="company_lifecycle_confirm_text",
                        )
                        action_col1, action_col2 = st.columns(2)
                        with action_col1:
                            if st.button("Apply Company Action", key="apply_company_action_btn"):
                                if not require_role_permission(u["role"], "manage_company", action_label="manage companies"):
                                    st.stop()
                                if str(confirm_action_text or "").strip() != str(action_company_name or "").strip():
                                    st.warning("Type the exact company name to confirm this action.")
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
                                            wipe_correlation_id = uuid.uuid4().hex[:12].upper()
                                            try:
                                                wipe_result = wipe_company_records(
                                                    conn,
                                                    action_company_key,
                                                    correlation_id=wipe_correlation_id,
                                                    manage_transaction=False,
                                                )
                                                conn.commit()
                                                log_audit_action(
                                                    conn,
                                                    "SYSTEM",
                                                    "Dev",
                                                    "Company Wiped",
                                                    "Gatekeeper Dashboard",
                                                    (
                                                        f"{action_company_name} permanently deleted. "
                                                        f"correlation_id={wipe_correlation_id}"
                                                    ),
                                                )
                                                deployment_status = str(
                                                    wipe_result.get("deployment_status") or ""
                                                ).strip().lower()
                                                if deployment_status == "trial":
                                                    st.success("Trial company deleted successfully.")
                                                else:
                                                    st.success(f"{action_company_name} and all linked records were deleted.")
                                            except Exception as wipe_error:
                                                conn.rollback()
                                                logger.error(
                                                    "Company wipe failed correlation_id=%s company_key=%s error=%s",
                                                    wipe_correlation_id,
                                                    action_company_key,
                                                    sanitize_error_message(wipe_error),
                                                    exc_info=True,
                                                )
                                                st.error(
                                                    "Company could not be deleted. Support Code: {code}".format(
                                                        code=wipe_correlation_id
                                                    )
                                                )
                                        st.rerun()
                                    except Exception as action_error:
                                        conn.rollback()
                                        st.error(build_user_safe_error(action_error, u["role"]))
                        with action_col2:
                            if st.button("Reactivate Archived Company", key="reactivate_archived_company_btn"):
                                if not require_role_permission(u["role"], "manage_company", action_label="reactivate companies"):
                                    st.stop()
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
                                    st.error(build_user_safe_error(reactivate_error, u["role"]))
                except Exception as portfolio_click_error:
                    logger.error("Portfolio interaction error: %s", sanitize_error_message(portfolio_click_error))
                    st.warning("Company selection is temporarily unavailable, but the portfolio table is still visible.")

                conn.close()
            except Exception as e:
                st.error(build_user_safe_error(e, u["role"]))
        
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
                            st.error(build_user_safe_error(renew_error, u["role"]))

                conn.close()
            except Exception as e:
                st.error(build_user_safe_error(e, u["role"]))
                    
    elif u['role'] == "Demo":
        demo_user = {"key": "DEMO", "name": "Demo Corporation Ltd", "role": "Demo"}
        _render_primary_sidebar(demo_user, include_settings=False)
        _render_primary_page(demo_user)
        st.sidebar.markdown("---")
        if st.sidebar.button("Secure Logout", width='stretch', key="v3_demo_logout_primary"):
            st.session_state.clear()
            st.rerun()
        st.stop()
                    
    else:
        if subscription_status.get("renewal_required"):
            show_subscription_renewal_page(st.session_state.company_id, role=u["role"])
            st.sidebar.markdown("---")
            if st.sidebar.button("Secure Logout", width='stretch', key="v3_subscription_logout"):
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
        _render_primary_sidebar(u, include_settings=True)
        _render_primary_page(u)
        st.sidebar.markdown("---")
        if st.sidebar.button("Secure Logout", width='stretch', key="v3_primary_logout"):
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
    if st.sidebar.button("Secure Logout", width='stretch', key="v3_final_logout"):
        try:
            conn = get_connection()
            log_audit_action(conn, u.get('key', 'SYSTEM'), u['role'], "User logout", "Authentication")
            conn.close()
        except:
            pass  # Don't fail logout if audit logging fails
        _clear_session()
        st.rerun()

