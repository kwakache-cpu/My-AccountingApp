import html
import logging
import json
import logging
import os
import random
import string
import hashlib
import hmac
import sqlite3
import base64
import uuid
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from dateutil.relativedelta import relativedelta
from PIL import Image
from security_utils import build_user_safe_error, sanitize_error_message
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import cv2
    from pyzbar import pyzbar
except ImportError:
    cv2 = None
    pyzbar = None

try:
    import firebase_admin
    from firebase_admin import credentials, db
except Exception:
    firebase_admin = None
    credentials = None
    db = None

pos_success_key = "pos_transaction_success"
scanner_active = True
OPENAI_MODEL = "gpt-4o-mini"
GEMINI_MODEL = "gemini-2.0-flash"
AI_TEMPORARY_UNAVAILABLE_MESSAGE = "AI Assistant is temporarily unavailable. Core ERP functions remain fully operational."
AI_RATE_LIMIT_MESSAGE = "Too many AI requests. Please wait a moment."
AI_RATE_LIMIT_MAX_CALLS = 5
AI_RATE_LIMIT_WINDOW_SECONDS = 60
DOCUMENT_WORKFLOW_STATUSES = ["Draft", "Submitted", "Approved", "Posted", "Cancelled", "Voided"]
POS_DISCOUNT_APPROVAL_PERCENT_THRESHOLD = 10.0
POS_DISCOUNT_APPROVAL_AMOUNT_THRESHOLD = 50.0
SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE = "Subscription pricing has not been configured. Please contact administrator."
SUBSCRIPTION_PLANS = {
    "Basic": {
        "plan_name": "Basic",
        "features": ["Core ERP access", "Single-company subscription", "Standard support"],
    },
    "Pro": {
        "plan_name": "Pro",
        "features": ["Advanced accounting workflows", "Priority support", "Enhanced admin visibility"],
    },
    "Enterprise": {
        "plan_name": "Enterprise",
        "features": ["Annual enterprise plan", "Multi-branch scaling", "Premium support"],
    },
}
PRINTABLE_DOCUMENT_FOOTER = "SOFTWARE BY: E.K.A RIGHTWAY CONSULT. 0507017767. VISIT kay-accounting.streamlit.app"
ALL_ENTERPRISE_PERMISSIONS = {
    "view_dashboard",
    "view_banking",
    "manage_owner_equity_transactions",
    "manage_loan_transactions",
    "manage_cash_bank_transfers",
    "manage_company",
    "manage_branches",
    "manage_users",
    "manage_chart_of_accounts",
    "create_customer",
    "create_supplier",
    "create_invoice",
    "create_bill",
    "receive_customer_payment",
    "make_supplier_payment",
    "post_accounting_document",
    "void_or_reverse_document",
    "close_period",
    "reopen_period",
    "lock_period",
    "view_reports",
    "view_audit_trail",
    "view_system_health",
    "export_backup",
    "restore_backup",
    "manage_integrations",
    "use_ai_assistant",
    "manual_license_override",
    "sell_pos",
    "view_own_cashier_session",
    "view_inventory",
    "manage_inventory",
    "view_payroll",
    "manage_payroll",
    "view_fixed_assets",
    "manage_fixed_assets",
    "close_cash_drawer",
    "view_cashier_closings",
    "manage_cashier_closings",
    "process_pos_return",
    "apply_pos_discount",
    "approve_pos_discount",
    "manage_branch_users",
    "view_branch_configuration",
}
# ------------------
# UI Standardization Helpers
# ------------------
def render_ui_standard_styles():
    """Inject consistent UI styles used across enterprise pages."""
    st.markdown(
        """
        <style>
        /* Card */
        .eka-card { background: #ffffff; border: 1px solid #e6eef6; border-radius: 10px; padding: 12px 16px; box-shadow: 0 6px 18px rgba(15,118,110,0.04); margin-bottom: 12px; }
        .eka-card-title { font-weight:600; margin-bottom:8px; color:#0f172a; }
        .eka-page-header h1 { margin: 0 0 6px 0; font-size: 1.6rem; }
        .eka-subtitle { margin:0 0 10px 0; color:#6b7280; }
        .eka-section { margin-top:18px; margin-bottom:8px; color:#0f172a; }
        .dashboard-kpi-grid [data-testid="stMetric"] {
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 10px 12px;
        }
        .dashboard-chart-card { min-height: 280px; }
        .dashboard-empty-state {
            min-height: 180px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            padding: 24px 16px;
            margin-top: 8px;
            border: 1px dashed #cbd5e1;
            border-radius: 8px;
            background: #f8fafc;
            color: #475569;
            font-size: 0.92rem;
            line-height: 1.45;
        }
        .dashboard-empty-hint {
            margin-top: 8px;
            font-size: 0.82rem;
            color: #64748b;
        }
        .dashboard-section-title {
            margin: 18px 0 10px 0;
            color: #0f172a;
            font-size: 1.05rem;
            font-weight: 700;
        }
        /* Table */
        .stDataFrame table { border-collapse: collapse; }
        .stDataFrame thead th { background:#f8fafc; color:#0f172a; }
        /* Buttons */
        .stButton>button { padding: 10px 14px !important; border-radius: 8px !important; }
        .pos-checkout-panel .pos-checkout-actions .stButton>button {
            min-height: 48px !important;
            font-size: 1rem !important;
        }
        .pos-checkout-panel .pos-checkout-actions [data-testid="stButton"]:first-child button {
            font-weight: 600 !important;
        }
        .pos-checkout-panel.pos-checkout-highlight {
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.35), 0 10px 26px rgba(15, 23, 42, 0.10) !important;
            transition: box-shadow 120ms ease-in-out;
        }
        /* POS checkout actions — sticky footer */
        @supports (position: sticky) {
            .pos-checkout-panel {
                /* Reserve space so the sticky bar doesn't cover content below */
                padding-bottom: 110px;
            }
            .pos-checkout-panel .pos-checkout-actions {
                position: sticky;
                bottom: 0.5rem;
                z-index: 60;
                background: rgba(255, 255, 255, 0.96);
                backdrop-filter: blur(6px);
                -webkit-backdrop-filter: blur(6px);
                border: 1px solid #e6eef6;
                border-radius: 12px;
                padding: 10px 10px;
                box-shadow: 0 10px 26px rgba(15, 23, 42, 0.10);
            }
        }
        @media (max-width: 760px) {
            @supports (position: sticky) {
                .pos-checkout-panel { padding-bottom: 130px; }
                .pos-checkout-panel .pos-checkout-actions {
                    bottom: 0.35rem;
                    padding: 10px 8px;
                }
            }
        }
        .pos-suspended-panel {
            position: sticky;
            top: 0.75rem;
            align-self: flex-start;
        }
        .pos-suspended-panel .pos-suspended-list-item {
            margin: 0 0 0.35rem 0;
            font-size: 0.78rem;
            color: #475569;
            line-height: 1.35;
        }
        .pos-receipt-live-label {
            margin: 0 0 10px 0;
            padding: 8px 10px;
            border-radius: 6px;
            background: #fff7ed;
            color: #9a3412;
            font-size: 0.9rem;
            text-align: center;
        }
        .pos-receipt-shell {
            background: #f8fafc;
            padding: 0.75rem;
            border-radius: 8px;
            margin: 0 auto;
            max-width: 320px;
        }
        .pos-receipt-shell-live {
            border: 2px dashed #d97706;
        }
        .pos-receipt-shell-final {
            border: 2px solid #059669;
            box-shadow: 0 4px 14px rgba(5, 150, 105, 0.12);
        }
        .receipt-preview.receipt-thermal {
            max-width: 280px !important;
            font-family: "Courier New", Consolas, monospace !important;
            font-size: 12px !important;
            line-height: 1.35 !important;
        }
        .receipt-preview-banner {
            margin-bottom: 0.65rem;
            padding: 0.45rem 0.35rem;
            border: 1px dashed #d97706;
            border-radius: 4px;
            background: #fff7ed;
            color: #9a3412;
            font-size: 0.72rem;
            font-weight: 700;
            text-align: center;
            letter-spacing: 0.04em;
        }
        /* POS active cart — touch-friendly line rows */
        .pos-cart-panel { padding-bottom: 4px; }
        .pos-cart-line {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 12px 14px;
            margin-bottom: 12px;
            background: #f8fafc;
        }
        .pos-cart-line-header {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            justify-content: space-between;
            gap: 6px 12px;
            margin-bottom: 4px;
        }
        .pos-cart-line-name {
            font-size: 1.08rem;
            font-weight: 600;
            color: #0f172a;
            line-height: 1.3;
        }
        .pos-cart-line-meta {
            color: #64748b;
            font-size: 0.88rem;
            margin-bottom: 10px;
        }
        .pos-cart-line-qty {
            margin: 8px 0 10px 0;
        }
        .pos-cart-panel .pos-cart-line-qty .stButton>button {
            min-height: 48px !important;
            min-width: 48px !important;
            font-size: 1.35rem !important;
            font-weight: 700 !important;
            padding: 8px 12px !important;
        }
        .pos-cart-panel .pos-cart-line-qty [data-testid="stNumberInput"] input {
            min-height: 48px !important;
            font-size: 1.15rem !important;
            font-weight: 600 !important;
            text-align: center !important;
        }
        .pos-cart-line-total-row {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin: 8px 0 10px 0;
            padding-top: 8px;
            border-top: 1px dashed #e2e8f0;
        }
        .pos-cart-line-total-label {
            font-size: 0.82rem;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .pos-cart-line-total-value {
            font-size: 1.15rem;
            font-weight: 700;
            color: #0f766e;
        }
        .pos-cart-discount-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 6px;
            background: #ecfdf5;
            color: #047857;
            font-size: 0.85rem;
            font-weight: 600;
        }
        .pos-cart-warning-badges {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 4px 0 6px;
        }
        .pos-cart-warning-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 6px;
            background: #fff7ed;
            color: #c2410c;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .pos-cart-line-remove {
            margin-top: 4px;
        }
        .pos-cart-panel .pos-cart-line-remove .stButton>button {
            min-height: 48px !important;
            border: 2px solid #dc2626 !important;
            color: #dc2626 !important;
            background: #fef2f2 !important;
            font-weight: 600 !important;
            font-size: 1rem !important;
        }
        .pos-cart-panel .pos-cart-line-remove .stButton>button:hover {
            background: #fee2e2 !important;
            border-color: #b91c1c !important;
            color: #b91c1c !important;
        }
        .pos-cart-panel [data-testid="stExpander"] {
            margin-bottom: 4px;
        }
        @media (max-width: 640px) {
            .eka-card { padding: 10px 12px; }
            .stButton>button { width: 100% !important; }
            .pos-cart-line { padding: 10px 12px; margin-bottom: 10px; }
            .pos-cart-line-name { font-size: 1rem; }
            .pos-cart-line-meta { font-size: 0.82rem; }
            .pos-cart-panel .pos-cart-line-qty .stButton>button {
                min-height: 52px !important;
                width: 100% !important;
            }
            .pos-cart-panel .pos-cart-line-qty [data-testid="stNumberInput"] input {
                min-height: 52px !important;
            }
            .pos-cart-line-total-value { font-size: 1.2rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title, subtitle=None):
    """Render a consistent page header with optional subtitle."""
    st.markdown(f"<div class=\"eka-page-header\"><h1>{title}</h1>" + (f"<p class=\"eka-subtitle\">{subtitle}</p>" if subtitle else "") + "</div>", unsafe_allow_html=True)


def section_header(title):
    st.markdown(f"<div class=\"eka-section\"><h3>{title}</h3></div>", unsafe_allow_html=True)


def card_container(title=None):
    """Return a Streamlit container representing a card; use `with card_container():`."""
    container = st.container()
    if title:
        container.markdown(f"<div class=\"eka-card\"><div class=\"eka-card-title\">{title}</div>", unsafe_allow_html=True)
    else:
        container.markdown(f"<div class=\"eka-card\">", unsafe_allow_html=True)
    return container


def ui_table(df):
    """Render a dataframe consistently (currency formatting handled elsewhere)."""
    try:
        st.dataframe(format_currency_dataframe(df), use_container_width=True, hide_index=True)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True)

ROLE_NAME_ALIASES = {
    "Gatekeeper": "Dev",
    "Branch Admin": "Sub-Admin",
    "Manager": "Sub-Admin",
    "Branch Manager": "Branch Manager",
    "Branch Bookkeeper": "Branch_Bookkeeper",
    "System Admin": "System Admin",
    "Owner": "Owner / CEO",
    "CEO": "Owner / CEO",
    "Owner / CEO": "Owner / CEO",
    "Accountant": "Accountant",
    "Cashier": "Cashier",
    "Sales Officer": "Sales Officer",
    "Inventory Officer": "Inventory Officer",
    "HR Officer": "HR / Payroll Officer",
    "Payroll Officer": "HR / Payroll Officer",
    "HR / Payroll Officer": "HR / Payroll Officer",
    "Auditor": "Auditor / Read Only",
    "Auditor / Read Only": "Auditor / Read Only",
    "Read Only": "Auditor / Read Only",
}
PERMISSION_ALIASES = {
    "system_health": {"view_system_health"},
    "backup_export": {"export_backup"},
    "restore_diagnostics": {"restore_backup", "view_system_health"},
    "company_deploy": {"manage_company"},
    "company_lifecycle": {"manage_company"},
    "period_control": {"close_period", "reopen_period", "lock_period"},
    "post_journal": {"post_accounting_document"},
    "system_configuration": {"manage_company", "manage_integrations"},
    "payroll": {"view_payroll", "manage_payroll"},
    "fixed_assets": {"view_fixed_assets", "manage_fixed_assets"},
    "inventory": {"view_inventory", "manage_inventory"},
    "manage_company_branches": {"manage_branches"},
}
ENTERPRISE_ROLE_PERMISSIONS = {
    "Dev": set(ALL_ENTERPRISE_PERMISSIONS),
    # Dev and Master Admin preserve the historical superuser behavior relied on by
    # internal support. System Admin below is deliberately narrower for user/config admin.
    "Master Admin": {
        "view_dashboard",
        "view_banking",
        "manage_owner_equity_transactions",
        "manage_loan_transactions",
        "manage_cash_bank_transfers",
        "manage_company",
        "manage_branches",
        "manage_users",
        "manage_chart_of_accounts",
        "create_customer",
        "create_supplier",
        "create_invoice",
        "create_bill",
        "receive_customer_payment",
        "make_supplier_payment",
        "post_accounting_document",
        "void_or_reverse_document",
        "close_period",
        "reopen_period",
        "lock_period",
        "view_reports",
        "view_audit_trail",
        "view_system_health",
        "export_backup",
        "restore_backup",
        "manage_integrations",
        "use_ai_assistant",
        "sell_pos",
        "view_own_cashier_session",
        "view_inventory",
        "manage_inventory",
        "view_payroll",
        "manage_payroll",
        "view_fixed_assets",
        "manage_fixed_assets",
        "close_cash_drawer",
        "view_cashier_closings",
        "manage_cashier_closings",
        "process_pos_return",
        "apply_pos_discount",
        "approve_pos_discount",
        "manage_branch_users",
        "view_branch_configuration",
    },
    "System Admin": {
        "view_dashboard",
        "manage_company",
        "manage_branches",
        "manage_users",
        "view_audit_trail",
        "view_system_health",
        "export_backup",
        "restore_backup",
        "manage_integrations",
        "use_ai_assistant",
    },
    "Owner / CEO": {
        "view_dashboard",
        "view_banking",
        "manage_owner_equity_transactions",
        "manage_loan_transactions",
        "manage_cash_bank_transfers",
        "manage_company",
        "manage_branches",
        "manage_users",
        "manage_chart_of_accounts",
        "create_customer",
        "create_supplier",
        "create_invoice",
        "create_bill",
        "receive_customer_payment",
        "make_supplier_payment",
        "post_accounting_document",
        "void_or_reverse_document",
        "close_period",
        "reopen_period",
        "lock_period",
        "view_reports",
        "view_audit_trail",
        "view_system_health",
        "use_ai_assistant",
        "sell_pos",
        "view_inventory",
        "manage_inventory",
        "view_payroll",
        "view_fixed_assets",
        "manage_fixed_assets",
        "close_cash_drawer",
        "view_cashier_closings",
        "manage_cashier_closings",
        "process_pos_return",
        "apply_pos_discount",
        "approve_pos_discount",
    },
    "Accountant": {
        "view_dashboard",
        "view_banking",
        "manage_chart_of_accounts",
        "create_customer",
        "create_supplier",
        "create_invoice",
        "create_bill",
        "receive_customer_payment",
        "make_supplier_payment",
        "post_accounting_document",
        "void_or_reverse_document",
        "close_period",
        "reopen_period",
        "lock_period",
        "view_reports",
        "view_audit_trail",
        "view_system_health",
        "use_ai_assistant",
        "view_inventory",
        "view_fixed_assets",
        "manage_fixed_assets",
        "view_cashier_closings",
        "manage_cashier_closings",
        "process_pos_return",
        "approve_pos_discount",
    },
    "Cashier": {
        "view_dashboard",
        "sell_pos",
        "view_own_cashier_session",
        "create_customer",
        "receive_customer_payment",
        "close_cash_drawer",
        "apply_pos_discount",
    },
    "Sales Officer": {
        "view_dashboard",
        "sell_pos",
        "create_customer",
        "create_invoice",
        "receive_customer_payment",
        "apply_pos_discount",
    },
    "Inventory Officer": {
        "view_dashboard",
        "view_inventory",
        "manage_inventory",
        "create_supplier",
    },
    "HR / Payroll Officer": {
        "view_dashboard",
        "view_payroll",
        "manage_payroll",
        "post_accounting_document",
        "void_or_reverse_document",
        "view_reports",
        "view_audit_trail",
    },
    "Auditor / Read Only": {
        "view_dashboard",
        "view_reports",
        "view_audit_trail",
        "view_system_health",
    },
    "Branch Manager": {
        "view_dashboard",
        "view_banking",
        "create_customer",
        "create_supplier",
        "create_invoice",
        "create_bill",
        "receive_customer_payment",
        "make_supplier_payment",
        "post_accounting_document",
        "view_reports",
        "view_audit_trail",
        "use_ai_assistant",
        "sell_pos",
        "view_inventory",
        "manage_inventory",
        "view_fixed_assets",
        "close_cash_drawer",
        "view_cashier_closings",
        "manage_cashier_closings",
        "process_pos_return",
        "apply_pos_discount",
        "approve_pos_discount",
        "manage_branch_users",
        "view_branch_configuration",
    },
    "Sub-Admin": {
        "view_dashboard",
        "view_banking",
        "manage_owner_equity_transactions",
        "manage_loan_transactions",
        "manage_cash_bank_transfers",
        "manage_company",
        "manage_branches",
        "manage_users",
        "manage_chart_of_accounts",
        "create_customer",
        "create_supplier",
        "create_invoice",
        "create_bill",
        "receive_customer_payment",
        "make_supplier_payment",
        "post_accounting_document",
        "close_period",
        "view_reports",
        "view_audit_trail",
        "use_ai_assistant",
        "sell_pos",
        "view_inventory",
        "manage_inventory",
        "view_fixed_assets",
        "manage_fixed_assets",
        "close_cash_drawer",
        "view_cashier_closings",
        "manage_cashier_closings",
        "process_pos_return",
        "apply_pos_discount",
        "approve_pos_discount",
    },
    "Bookkeeper": {
        "view_dashboard",
        "view_banking",
        "manage_chart_of_accounts",
        "create_customer",
        "create_supplier",
        "create_invoice",
        "create_bill",
        "receive_customer_payment",
        "make_supplier_payment",
        "post_accounting_document",
        "view_reports",
        "use_ai_assistant",
        "sell_pos",
        "view_inventory",
        "view_fixed_assets",
        "manage_fixed_assets",
        "close_cash_drawer",
        "view_cashier_closings",
        "manage_cashier_closings",
        "process_pos_return",
        "apply_pos_discount",
        "approve_pos_discount",
    },
    "Branch_Bookkeeper": {
        "view_dashboard",
        "view_banking",
        "create_customer",
        "create_supplier",
        "create_invoice",
        "create_bill",
        "receive_customer_payment",
        "make_supplier_payment",
        "post_accounting_document",
        "view_reports",
        "use_ai_assistant",
        "sell_pos",
        "view_inventory",
        "view_fixed_assets",
        "close_cash_drawer",
        "process_pos_return",
        "apply_pos_discount",
    },
    "Staff": {
        "view_dashboard",
        "create_customer",
        "receive_customer_payment",
        "sell_pos",
        "close_cash_drawer",
        "apply_pos_discount",
    },
    "Demo": {"view_dashboard", "view_banking"},
}

# Setup Logger
logger = logging.getLogger(__name__)

# Import shared utilities from database
from database import (
    activate_company_subscription,
    assign_branch_manager,
    BRANCH_MANAGER_CREATABLE_ROLES,
    PRIVILEGED_COMPANY_USER_ROLES,
    create_branch_scoped_user,
    create_company_branch,
    create_company_record,
    db_table_exists,
    ensure_company_trial_subscription,
    ensure_branch_licensing_schema_integrity,
    execute_portable_query,
    execute_portable_write,
    execute_write_transaction,
    fetch_branch_manager_candidates,
    fetch_branch_manager_select_options,
    get_branch_enabled_modules,
    get_branch_type_catalog,
    get_company_branch_license_snapshot,
    list_branch_users,
    list_company_branches_with_grants,
    list_company_staff_for_assignment,
    repair_branch_module_grants,
    refresh_branch_module_grants_for_type_change,
    update_branch_user_status,
    update_company_branch,
    update_company_staff_branch_assignment,
    ensure_cashier_closings_schema,
    ensure_inventory_schema_integrity,
    ensure_stock_movements_schema_integrity,
    ensure_pos_sales_schema,
    force_backup_after_company_creation,
    get_firebase_service_account_info,
    get_connection,
    get_inserted_id,
    ensure_insert_sql_returning,
    get_database_health_snapshot,
    get_postgres_readiness_diagnostics,
    get_persistence_diagnostics,
    get_schema_manifest_diagnostics,
    get_subscription_plan_setting,
    get_subscription_plan_settings,
    get_company_subscription_snapshot,
    get_recovery_source_diagnostics,
    get_subscription_billing_diagnostics,
    get_subscription_billing_summary,
    is_postgres_backend,
    list_columns,
    row_get,
    row_to_dict,
    rows_to_dicts,
    upsert_subscription_plan_setting,
    log_audit_action as database_log_audit_action,
)
from accounting_engine import (
    compare_legacy_and_journal_totals,
    get_account_total,
    get_ap_aging_report,
    get_ar_aging_report,
    get_chart_of_accounts_diagnostics,
    get_reporting_trust_diagnostics,
    get_unified_posting_engine_diagnostics,
    generate_balance_sheet,
    generate_cash_flow_statement,
    generate_income_statement,
    get_account_id,
    get_month_sales_total,
    get_recent_accounting_activity,
    get_customer_balance,
    get_customer_balances,
    get_general_ledger as engine_get_general_ledger,
    get_bank_reconciliation,
    get_or_create_account as engine_get_or_create_account,
    get_supplier_balance,
    get_supplier_balances,
    get_trial_balance as engine_get_trial_balance,
    is_legacy_mirroring_enabled,
    post_accounting_impact as post_journal_entry,
    reverse_journal_entry,
)

import migration_cleanup as migration_cleanup_service


def _portable_read_dataframe(conn, query, params=()):
    rows = execute_portable_query(conn, query, params or ()).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def can_access_migration_cleanup(role):
    return migration_cleanup_service.can_access_migration_cleanup(role)


def log_audit_action(
    conn,
    company_key,
    user_role,
    action,
    module_name,
    details=None,
    branch_id=None,
    action_type=None,
    document_ref=None,
    before_after_summary=None,
):
    """Proxy audit logging so app.py can import the shared action from this module."""
    return database_log_audit_action(
        conn,
        company_key,
        user_role,
        action,
        module_name,
        details,
        branch_id,
        action_type=action_type,
        document_ref=document_ref,
        before_after_summary=before_after_summary,
    )


def _normalize_role_name(role):
    normalized = str(role or "").strip()
    return ROLE_NAME_ALIASES.get(normalized, normalized)


def _resolve_permission_targets(permission):
    permission_name = str(permission or "").strip()
    targets = PERMISSION_ALIASES.get(permission_name, permission_name)
    if isinstance(targets, (set, list, tuple)):
        return {str(item).strip() for item in targets if str(item).strip()}
    return {permission_name} if permission_name else set()


def _record_permission_security_event(role, permission, action_label=None, company_key=None, conn=None, branch_id=None):
    event_role = _normalize_role_name(role) or "Unknown"
    permission_targets = sorted(_resolve_permission_targets(permission))
    permission_label = ", ".join(permission_targets) or str(permission or "unknown")
    message = (
        f"Permission denied for role={event_role} permission={permission_label} "
        f"action={action_label or permission_label}"
    )
    owned_connection = conn is None
    local_conn = conn
    try:
        if local_conn is None:
            local_conn = get_connection()
        local_conn.execute(
            """
            INSERT INTO system_logs (timestamp, level, module_name, message)
            VALUES (CURRENT_TIMESTAMP, 'WARNING', 'Security', ?)
            """,
            (message,),
        )
        if company_key:
            database_log_audit_action(
                local_conn,
                company_key,
                event_role,
                f"Permission denied: {action_label or permission_label}",
                "Security",
                details=f"permission={permission_label}",
                branch_id=branch_id,
                action_type="admin",
                document_ref=str(company_key),
            )
        if owned_connection:
            local_conn.commit()
    except Exception:
        logger.debug("Permission security logging skipped.", exc_info=True)
    finally:
        if owned_connection and local_conn:
            local_conn.close()


def user_has_permission(role, permission):
    normalized_role = _normalize_role_name(role)
    granted_permissions = ENTERPRISE_ROLE_PERMISSIONS.get(normalized_role, set())
    permission_targets = _resolve_permission_targets(permission)
    if not granted_permissions or not permission_targets:
        return False
    return any(target in granted_permissions for target in permission_targets)


def _extract_role_from_user(user_or_role):
    if isinstance(user_or_role, dict):
        return user_or_role.get("role") or user_or_role.get("user_role") or user_or_role.get("type")
    return user_or_role


def has_permission(user, permission_key):
    """Compatibility wrapper for role strings and session/user dictionaries."""
    return user_has_permission(_extract_role_from_user(user), permission_key)


BRANCH_SCOPED_ROLES = frozenset({"Branch_Bookkeeper", "Cashier", "Staff", "Branch Manager"})

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
    "Taxation (VAT/NHIL)": "view_reports",
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

PAGE_MODULE_KEY_MAP = {
    "Dashboard": "Dashboard",
    "Point of Sale": "Point of Sale",
    "Inventory Management": "Inventory",
    "Create Invoice": "Create Invoice",
    "Sales Invoicing": "Create Invoice",
    "Sales History": "Create Invoice",
    "Sales/Purchase": "Create Invoice",
    "Receive Payment (Customer)": "Receive Payment",
    "Create Bill": "Create Bill",
    "Purchase Invoicing": "Create Bill",
    "Purchase History": "Create Bill",
    "Purchase Orders": "Create Bill",
    "Supplier Payment": "Supplier Payment",
    "Customers": "Customers",
    "Suppliers": "Suppliers",
    "General Journal": "Reports",
    "General Ledger": "Reports",
    "Chart of Accounts": "Reports",
    "Customer Ledger": "Reports",
    "Supplier Ledger": "Reports",
    "Accounts Receivable": "Reports",
    "Accounts Payable": "Reports",
    "Taxation (VAT/NHIL)": "Reports",
    "Vouchers & Journals": "Reports",
    "Data Analytics": "Reports",
    "Financial Reports": "Financial Reports",
    "Banking & Cash": "Banking & Cash",
    "Banking": "Banking & Cash",
    "Asset Register": "Asset Register",
    "Payroll & Salaries": "Payroll & Salaries",
    "System Configuration": "System Configuration",
    "System Audit Trail": "Reports",
    "Gatekeeper Admin": "Gatekeeper Admin",
    "branch_management": "branch_management",
}

COMPANY_STAFF_ASSIGNABLE_ROLES = frozenset(
    {
        "Cashier",
        "Sales Officer",
        "Inventory Officer",
        "Branch_Bookkeeper",
        "Staff",
        "Auditor / Read Only",
        "Bookkeeper",
        "Accountant",
        "Branch Manager",
    }
)


def _extract_user_branch_id(user):
    if isinstance(user, dict):
        return user.get("branch_id") or user.get("active_branch_id") or user.get("assigned_branch_id")
    return None


def is_branch_scoped_user(user):
    normalized_role = _normalize_role_name(_extract_role_from_user(user))
    if normalized_role in BRANCH_SCOPED_ROLES:
        return True
    assigned_branch_id = _extract_user_branch_id(user)
    return bool(assigned_branch_id) and normalized_role not in {
        "Dev",
        "Master Admin",
        "System Admin",
        "Owner / CEO",
        "Sub-Admin",
        "Bookkeeper",
        "Accountant",
    }


def resolve_effective_branch_id(user=None):
    """Resolve the branch filter for queries: assigned branch wins for branch-scoped users."""
    user = user or st.session_state.get("user") or {}
    assigned_branch_id = _extract_user_branch_id(user)
    if is_branch_scoped_user(user):
        if assigned_branch_id:
            return str(assigned_branch_id).strip()
        return None
    session_branch_id = st.session_state.get("active_branch_id")
    return str(session_branch_id).strip() if session_branch_id else None


def enforce_branch_session_lock(user=None):
    """Pin branch-scoped sessions to their assigned branch; never fall back to all branches."""
    user = user or st.session_state.get("user") or {}
    if not isinstance(user, dict):
        return None
    assigned_branch_id = _extract_user_branch_id(user)
    if is_branch_scoped_user(user):
        if assigned_branch_id:
            locked_branch_id = str(assigned_branch_id).strip()
            st.session_state.active_branch_id = locked_branch_id
            if not user.get("branch_id"):
                user["branch_id"] = locked_branch_id
            st.session_state.user = user
            return locked_branch_id
        st.session_state.active_branch_id = None
        return None
    return st.session_state.get("active_branch_id")


def get_user_allowed_branch_ids(company_key, user=None):
    user = user or st.session_state.get("user") or {}
    assigned_branch_id = _extract_user_branch_id(user)
    if is_branch_scoped_user(user):
        return [str(assigned_branch_id).strip()] if assigned_branch_id else []
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT branch_id FROM branches WHERE company_key = ? ORDER BY branch_name",
                (company_key,),
            ).fetchall()
            return [str(row["branch_id"]) for row in rows]
        finally:
            conn.close()
    except Exception:
        return []


def render_branch_session_diagnostics(user=None, company_key=None):
    user = user or st.session_state.get("user") or {}
    company_key = company_key or user.get("key") or st.session_state.get("company_id")
    with st.sidebar.expander("Session context", expanded=False):
        st.caption(f"User key: {user.get('key') or company_key or '—'}")
        st.caption(f"Role: {user.get('role') or '—'}")
        st.caption(f"Company: {company_key or '—'}")
        st.caption(f"Active branch: {st.session_state.get('active_branch_id') or '—'}")
        allowed = get_user_allowed_branch_ids(company_key, user=user)
        st.caption(f"Allowed branches: {', '.join(allowed) if allowed else '—'}")


def can_access_branch(user, branch_id):
    normalized_role = _normalize_role_name(_extract_role_from_user(user))
    if normalized_role in {"Dev", "Master Admin", "System Admin", "Owner / CEO"}:
        return True
    assigned_branch_id = _extract_user_branch_id(user)
    if normalized_role in BRANCH_SCOPED_ROLES or (assigned_branch_id and normalized_role not in {
        "Dev",
        "Master Admin",
        "System Admin",
        "Owner / CEO",
        "Sub-Admin",
        "Bookkeeper",
        "Accountant",
    }):
        if not assigned_branch_id:
            return False
        if not branch_id:
            return False
        return str(assigned_branch_id).strip() == str(branch_id).strip()
    if not branch_id:
        return True
    if not assigned_branch_id:
        return True
    return str(assigned_branch_id).strip() == str(branch_id).strip()


def is_branch_module_gating_exempt(user):
    normalized_role = _normalize_role_name(_extract_role_from_user(user))
    if normalized_role in {"Dev", "Master Admin", "System Admin", "Owner / CEO"}:
        return True
    return user_has_permission(normalized_role, "manage_branches")


def can_manage_branch_users_role(role):
    normalized_role = _normalize_role_name(role)
    return (
        user_has_permission(normalized_role, "manage_branch_users")
        or user_has_permission(normalized_role, "manage_users")
        or user_has_permission(normalized_role, "manage_branches")
    )


def is_company_branch_admin(role):
    """Master Admin and other company-wide branch administrators."""
    normalized_role = _normalize_role_name(role)
    return user_has_permission(normalized_role, "manage_branches") or user_has_permission(
        normalized_role, "manage_users"
    )


def _close_sqlite_connection(conn):
    """Release a read connection before an exclusive write (avoids SQLite lock errors)."""
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


def _run_branch_db_write(operation_name, callback, *, release_conn=None):
    """Single lock-safe write transaction for branch governance actions."""
    if release_conn is not None:
        _close_sqlite_connection(release_conn)

    def _operation(conn):
        ensure_branch_licensing_schema_integrity(conn)
        return callback(conn)

    return execute_write_transaction(_operation, operation_name=operation_name)


def _safe_select_index(options, value, default_value=None):
    if value in options:
        return options.index(value)
    if default_value is not None and default_value in options:
        return options.index(default_value)
    return 0


def page_key_to_module_key(page_key):
    return PAGE_MODULE_KEY_MAP.get(str(page_key or "").strip(), str(page_key or "").strip())


def branch_allows_page(user, page_key, company_key=None, conn=None):
    if is_branch_module_gating_exempt(user):
        return True
    if not is_branch_scoped_user(user):
        return True
    company_key = company_key or (user.get("key") if isinstance(user, dict) else None) or st.session_state.get("company_id")
    branch_id = resolve_effective_branch_id(user)
    if not company_key or not branch_id:
        return False
    module_key = page_key_to_module_key(page_key)
    if module_key == "branch_management":
        return can_access_branch_management(_extract_role_from_user(user))
    if module_key == "Gatekeeper Admin":
        return _normalize_role_name(_extract_role_from_user(user)) == "Dev"
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        enabled_modules = get_branch_enabled_modules(conn, company_key, branch_id)
    finally:
        if close_conn and conn:
            conn.close()
    return module_key in enabled_modules


def user_can_access_page(user, page_name, company_key=None, conn=None):
    if not user:
        return False
    role = _extract_role_from_user(user)
    if isinstance(user, dict) and user.get("role") == "Demo":
        return page_name in {"Dashboard", "Point of Sale", "Inventory Management"}
    if page_name == "branch_management":
        return can_access_branch_management(role)
    permission = PAGE_PERMISSION_MAP.get(page_name)
    role_allowed = True if not permission else user_has_permission(role, permission)
    if not role_allowed:
        return False
    if is_branch_module_gating_exempt(user):
        return True
    if page_name == "Gatekeeper Admin" and _normalize_role_name(role) == "Dev":
        return True
    if not is_branch_scoped_user(user):
        return True
    return branch_allows_page(user, page_name, company_key=company_key, conn=conn)


def filter_by_user_branch(records, user, branch_key="branch_id"):
    if records is None:
        return records
    normalized_role = _normalize_role_name(_extract_role_from_user(user))
    if normalized_role in {"Dev", "Master Admin", "System Admin", "Owner / CEO"}:
        return records
    assigned_branch_id = _extract_user_branch_id(user)
    if normalized_role in BRANCH_SCOPED_ROLES and not assigned_branch_id:
        if isinstance(records, pd.DataFrame):
            return records.iloc[0:0]
        return []
    if not assigned_branch_id:
        return records
    if isinstance(records, pd.DataFrame):
        if branch_key not in records.columns:
            return records
        branch_values = records[branch_key].fillna("")
        return records[(branch_values == "") | (branch_values.astype(str) == str(assigned_branch_id))]
    if isinstance(records, list):
        filtered = []
        for row in records:
            row_branch_id = row.get(branch_key) if isinstance(row, dict) else getattr(row, branch_key, None)
            if not row_branch_id or str(row_branch_id).strip() == str(assigned_branch_id):
                filtered.append(row)
        return filtered
    return records


def require_permission(role, permission, action_label=None, company_key=None, conn=None, branch_id=None):
    if user_has_permission(role, permission):
        return True
    _record_permission_security_event(
        role,
        permission,
        action_label=action_label,
        company_key=company_key,
        conn=conn,
        branch_id=branch_id,
    )
    st.warning("You do not have permission to perform this action.")
    return False


def execute_manual_license_override(
    *,
    conn,
    actor_role,
    actor_user,
    company_name,
    company_key,
    duration_months,
    number_of_branches,
    max_branches,
    branch_price_per_month,
    override_reason,
    confirmation_checked,
    logger_instance=None,
):
    logger_instance = logger_instance or logger
    normalized_role = str(actor_role or "").strip()
    normalized_user = str(actor_user or normalized_role or "SYSTEM").strip()
    normalized_company_name = str(company_name or "").strip()
    normalized_company_key = str(company_key or "").strip()
    normalized_reason = str(override_reason or "").strip()
    if not user_has_permission(normalized_role, "manual_license_override"):
        _record_permission_security_event(
            normalized_role,
            "manual_license_override",
            action_label="perform a manual license override",
            company_key=normalized_company_key or None,
            conn=conn,
        )
        return {"ok": False, "reason": "You do not have permission to perform this action.", "permission_denied": True}
    if not confirmation_checked:
        return {
            "ok": False,
            "reason": "Confirm that this is an internal/admin-only Paystack bypass before continuing.",
        }
    if not normalized_reason:
        return {"ok": False, "reason": "A manual override reason is required."}
    if not normalized_company_name or not normalized_company_key:
        return {"ok": False, "reason": "Company Name and System License Key are required."}

    new_expiry = datetime.now() + relativedelta(months=+int(duration_months))
    try:
        created_company_key = create_company_record(
            conn=conn,
            company_key=normalized_company_key,
            company_name=normalized_company_name,
            subscription_expiry=new_expiry.isoformat(),
            status="Active",
            deployment_status="Live",
            number_of_branches=int(number_of_branches),
            max_branches=int(max_branches),
            branch_price_per_month=float(branch_price_per_month),
        )
        conn.commit()
        backup_result = force_backup_after_company_creation(
            company_name=normalized_company_name,
            company_key=created_company_key,
            logger_instance=logger_instance,
        )
        database_log_audit_action(
            conn,
            "SYSTEM",
            normalized_role,
            f"Manual license override for {normalized_company_name}",
            "System Admin",
            details=(
                f"company_key={created_company_key}; expiry={new_expiry.isoformat()}; "
                f"reason={normalized_reason}"
            ),
            action_type="admin/license_override",
            document_ref=created_company_key,
        )
        conn.execute(
            """
            INSERT INTO system_logs (timestamp, level, module_name, message)
            VALUES (?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                "WARNING",
                "License Override",
                (
                    f"Manual license override executed by {normalized_user} role={normalized_role} "
                    f"company_key={created_company_key} reason={normalized_reason}"
                ),
            ),
        )
        conn.commit()
        return {
            "ok": True,
            "company_key": created_company_key,
            "company_name": normalized_company_name,
            "new_expiry": new_expiry.date().isoformat(),
            "backup_result": backup_result,
        }
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "reason": build_user_safe_error(exc, normalized_role)}


def _hash_security_answer(answer):
    return hashlib.sha256(str(answer or "").strip().lower().encode("utf-8")).hexdigest()


def _legacy_write_enabled(conn):
    try:
        return is_legacy_mirroring_enabled(conn)
    except Exception:
        return False


def _create_legacy_voucher_if_enabled(
    conn,
    company_key,
    branch_id,
    entry_date,
    v_type,
    ledger,
    amount,
    created_by,
    narration=None,
    reference_no=None,
    payment_method=None,
    status="Posted",
):
    if not _legacy_write_enabled(conn):
        return None
    cursor = conn.execute(
        ensure_insert_sql_returning(
            """
            INSERT INTO vouchers (company_key, branch_id, date, v_type, ledger, credit, reference_no, narration, payment_method, status, approval_status, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Posted', ?)
            """
        ),
        (
            company_key,
            branch_id,
            entry_date,
            v_type,
            ledger,
            amount,
            reference_no,
            narration,
            payment_method,
            status,
            created_by,
        ),
    )
    return get_inserted_id(cursor)


def get_company_branches(company_key):
    conn = get_connection()
    try:
        rows = execute_portable_query(
            conn,
            "SELECT branch_id, branch_name, location, branch_type FROM branches WHERE company_key = ? ORDER BY branch_name",
            (company_key,),
        ).fetchall()
        return rows_to_dicts(rows)
    finally:
        conn.close()


# ==========================================
# PAYSTACK PAYMENT
# ==========================================
def _read_secret_or_env(*candidate_keys):
    for key in candidate_keys:
        if not key:
            continue
        try:
            if st is not None and hasattr(st, "secrets") and key in st.secrets:
                value = st.secrets[key]
                if value is not None and str(value).strip():
                    return str(value).strip()
        except Exception:
            pass
        env_value = os.getenv(key)
        if env_value and str(env_value).strip():
            return str(env_value).strip()
    return None


def get_paystack_runtime_config():
    secret_key = _read_secret_or_env("PAYSTACK_SECRET_KEY", "paystack_secret_key")
    public_key = _read_secret_or_env("PAYSTACK_PUBLIC_KEY", "paystack_public_key")
    currency = (_read_secret_or_env("PAYSTACK_CURRENCY", "paystack_currency") or "GHS").upper()
    callback_url = _read_secret_or_env("PAYSTACK_CALLBACK_URL", "paystack_callback_url")
    webhook_secret = _read_secret_or_env("PAYSTACK_WEBHOOK_SECRET", "paystack_webhook_secret")
    return {
        "secret_key": secret_key,
        "public_key": public_key,
        "currency": currency,
        "callback_url": callback_url,
        "webhook_secret": webhook_secret,
        "secret_key_present": bool(secret_key),
        "public_key_present": bool(public_key),
        "callback_url_configured": bool(callback_url),
    }


def get_paystack_diagnostics():
    config = get_paystack_runtime_config()
    return {
        "secret_key_present": config["secret_key_present"],
        "public_key_present": config["public_key_present"],
        "currency": config["currency"],
        "callback_url_configured": config["callback_url_configured"],
        "webhook_secret_present": bool(config.get("webhook_secret")),
    }


def get_subscription_plans():
    configured_plans = get_subscription_plan_settings()
    plans = {}
    for plan_name, plan_data in SUBSCRIPTION_PLANS.items():
        configured = configured_plans.get(plan_name) or {}
        amount = configured.get("configured_amount")
        duration_months = max(int(configured.get("duration_months") or 0), 0)
        duration_days = max(int(configured.get("duration_days") or 0), 0)
        normalized_amount = float(amount) if amount not in (None, "") else None
        plans[plan_name] = {
            "plan_name": plan_name,
            "amount": normalized_amount,
            "currency": str(configured.get("currency") or "GHS").strip().upper() or "GHS",
            "duration_months": duration_months,
            "duration_days": duration_days,
            "features": list(plan_data.get("features", [])),
            "configured": bool(
                normalized_amount is not None
                and normalized_amount > 0
                and ((duration_months > 0) or (duration_days > 0))
            ),
            "updated_at": configured.get("updated_at"),
            "updated_by": configured.get("updated_by"),
        }
    return plans


def get_subscription_plan(plan_name):
    normalized = str(plan_name or "").strip()
    plans = get_subscription_plans()
    if normalized and normalized in plans:
        return dict(plans[normalized])
    first_plan_name = next(iter(plans.keys()), "Basic")
    return dict(
        plans.get(
            first_plan_name,
            {
                "plan_name": normalized or first_plan_name,
                "amount": None,
                "currency": "GHS",
                "duration_months": 0,
                "duration_days": 0,
                "features": [],
                "configured": False,
            },
        )
    )


def get_subscription_plan_pricing_snapshot():
    plans = get_subscription_plans()
    active_plan_prices = []
    missing_price_warnings = []
    for plan_name, plan_data in plans.items():
        active_plan_prices.append(
            {
                "plan_name": plan_name,
                "configured_amount": plan_data.get("amount"),
                "currency": plan_data.get("currency") or "GHS",
                "duration_months": int(plan_data.get("duration_months") or 0),
                "duration_days": int(plan_data.get("duration_days") or 0),
                "configured": bool(plan_data.get("configured")),
                "updated_at": plan_data.get("updated_at"),
                "updated_by": plan_data.get("updated_by"),
            }
        )
        if not plan_data.get("configured"):
            missing_price_warnings.append(f"{plan_name} pricing is incomplete or missing.")
    return {
        "active_plan_prices": active_plan_prices,
        "missing_price_warnings": missing_price_warnings,
    }


def save_subscription_plan_pricing_settings(plan_rows, actor=None):
    conn = None
    try:
        conn = get_connection()
        for row in plan_rows or []:
            upsert_subscription_plan_setting(
                conn,
                plan_name=row.get("plan_name"),
                configured_amount=row.get("configured_amount"),
                currency=row.get("currency") or "GHS",
                duration_months=row.get("duration_months"),
                duration_days=row.get("duration_days"),
                features_json=json.dumps(row.get("features", []), default=str) if row.get("features") is not None else None,
                updated_by=actor,
            )
        conn.commit()
        return {"ok": True}
    except Exception as exc:
        if conn:
            conn.rollback()
        logger.warning("Subscription pricing save failed: %s", sanitize_error_message(exc))
        return {
            "ok": False,
            "reason": "Subscription pricing could not be saved right now.",
        }
    finally:
        if conn:
            conn.close()


def create_trial_company_registration(company_name, contact_email=None, company_key=None, trial_days=7):
    normalized_name = str(company_name or "").strip()
    normalized_email = str(contact_email or "").strip() or None
    normalized_key = str(company_key or _generate_company_key()).strip()
    if not normalized_name:
        return {"ok": False, "reason": "Company name is required."}
    conn = None
    try:
        conn = get_connection()
        existing_company = conn.execute(
            "SELECT key FROM companies WHERE lower(name) = lower(?) OR key = ? LIMIT 1",
            (normalized_name, normalized_key),
        ).fetchone()
        if existing_company:
            return {"ok": False, "reason": "A company with this name or key already exists."}
        trial_result = ensure_company_trial_subscription(
            conn,
            company_key=normalized_key,
            company_name=normalized_name,
            contact_email=normalized_email,
            trial_days=trial_days,
        )
        conn.commit()
        database_log_audit_action(
            conn,
            normalized_key,
            "System",
            "Trial company created",
            "Subscription Billing",
            details=f"trial_end={trial_result['end_date']}",
            action_type="subscription/trial_created",
            document_ref=normalized_key,
        )
        conn.execute(
            """
            INSERT INTO system_logs (timestamp, level, module_name, message)
            VALUES (?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                "INFO",
                "Subscription Billing",
                f"Created trial company company_key={normalized_key} trial_end={trial_result['end_date']}",
            ),
        )
        conn.commit()
        return {"ok": True, **trial_result}
    except Exception as exc:
        if conn:
            conn.rollback()
        return {"ok": False, "reason": build_user_safe_error(exc, st.session_state.get('user', {}).get('role'))}
    finally:
        if conn:
            conn.close()


def test_paystack_connection():
    config = get_paystack_runtime_config()
    config_ready = bool(
        config["secret_key_present"]
        and config["public_key_present"]
        and config["callback_url_configured"]
        and str(config.get("currency") or "").upper() == "GHS"
    )
    missing_parts = []
    if not config["secret_key_present"]:
        missing_parts.append("PAYSTACK_SECRET_KEY")
    if not config["public_key_present"]:
        missing_parts.append("PAYSTACK_PUBLIC_KEY")
    if not config["callback_url_configured"]:
        missing_parts.append("PAYSTACK_CALLBACK_URL")
    if str(config.get("currency") or "").upper() != "GHS":
        missing_parts.append("PAYSTACK_CURRENCY must be GHS")

    return {
        "secret_key_present": config["secret_key_present"],
        "public_key_present": config["public_key_present"],
        "callback_url_present": config["callback_url_configured"],
        "currency": config["currency"],
        "config_ready": config_ready,
        "webhook_secret_present": bool(config.get("webhook_secret")),
        "calls_paystack": False,
        "success": config_ready,
        "error": "" if config_ready else "Missing or invalid Paystack configuration: " + ", ".join(missing_parts),
        "message": (
            "Configuration ready. Live payment test requires initializing checkout."
            if config_ready
            else "Paystack configuration is incomplete."
        ),
    }


def _generate_paystack_reference(prefix="ONB"):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"


def _generate_company_key():
    return (
        f"EKA-PAY-"
        f"{''.join(random.choices(string.ascii_uppercase, k=4))}-"
        f"{''.join(random.choices(string.digits, k=4))}"
    )
def _serialize_paystack_gateway_summary(response_payload):
    response_data = response_payload.get("data") if isinstance(response_payload, dict) else {}
    summary = {
        "status": response_payload.get("status") if isinstance(response_payload, dict) else None,
        "gateway_status": response_data.get("status") if isinstance(response_data, dict) else None,
        "gateway_response": response_data.get("gateway_response") if isinstance(response_data, dict) else None,
        "channel": response_data.get("channel") if isinstance(response_data, dict) else None,
        "paid_at": response_data.get("paid_at") if isinstance(response_data, dict) else None,
    }
    return json.dumps(summary, default=str)


def _resolve_subscription_plan_payment_snapshot(plan_name):
    normalized_plan_name = str(plan_name or "").strip()
    if not normalized_plan_name:
        return {"ok": False, "reason": SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE}
    configured_plan = get_subscription_plan(normalized_plan_name)
    if not configured_plan.get("configured"):
        return {"ok": False, "reason": SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE}
    return {
        "ok": True,
        "plan_name": normalized_plan_name,
        "configured_amount": float(configured_plan.get("amount") or 0),
        "currency": str(configured_plan.get("currency") or "GHS").strip().upper() or "GHS",
        "duration_months": max(int(configured_plan.get("duration_months") or 0), 0),
        "duration_days": max(int(configured_plan.get("duration_days") or 0), 0),
        "features": list(configured_plan.get("features", [])),
    }


def _upsert_license_payment_transaction(
    conn,
    *,
    reference,
    company_key,
    company_name,
    payer_email,
    payment_context,
    plan_name=None,
    configured_amount=None,
    configured_duration_months=None,
    configured_duration_days=None,
    expected_amount,
    currency,
    status,
    authorization_url=None,
    callback_url=None,
    metadata_json=None,
    gateway_status_summary=None,
    paid_at=None,
    verified_at=None,
    activated_at=None,
):
    conn.execute(
        """
        INSERT INTO license_payment_transactions (
            reference,
            company_key,
            company_name,
            payer_email,
            payment_context,
            plan_name,
            configured_amount,
            configured_duration_months,
            configured_duration_days,
            expected_amount,
            currency,
            status,
            authorization_url,
            callback_url,
            metadata_json,
            gateway_status_summary,
            paid_at,
            verified_at,
            activated_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(reference) DO UPDATE SET
            company_key = excluded.company_key,
            company_name = excluded.company_name,
            payer_email = excluded.payer_email,
            payment_context = excluded.payment_context,
            plan_name = COALESCE(excluded.plan_name, license_payment_transactions.plan_name),
            configured_amount = COALESCE(excluded.configured_amount, license_payment_transactions.configured_amount),
            configured_duration_months = COALESCE(excluded.configured_duration_months, license_payment_transactions.configured_duration_months),
            configured_duration_days = COALESCE(excluded.configured_duration_days, license_payment_transactions.configured_duration_days),
            expected_amount = excluded.expected_amount,
            currency = excluded.currency,
            status = excluded.status,
            authorization_url = COALESCE(excluded.authorization_url, license_payment_transactions.authorization_url),
            callback_url = COALESCE(excluded.callback_url, license_payment_transactions.callback_url),
            metadata_json = COALESCE(excluded.metadata_json, license_payment_transactions.metadata_json),
            gateway_status_summary = COALESCE(excluded.gateway_status_summary, license_payment_transactions.gateway_status_summary),
            paid_at = COALESCE(excluded.paid_at, license_payment_transactions.paid_at),
            verified_at = COALESCE(excluded.verified_at, license_payment_transactions.verified_at),
            activated_at = COALESCE(excluded.activated_at, license_payment_transactions.activated_at),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            reference,
            company_key,
            company_name,
            payer_email,
            payment_context,
            str(plan_name or "").strip() or None,
            float(configured_amount) if configured_amount not in (None, "") else None,
            max(int(configured_duration_months or 0), 0),
            max(int(configured_duration_days or 0), 0),
            int(expected_amount or 0),
            currency,
            status,
            authorization_url,
            callback_url,
            metadata_json,
            gateway_status_summary,
            paid_at,
            verified_at,
            activated_at,
        ),
    )


def _activate_verified_license_payment(conn, transaction_row):
    if not transaction_row:
        return {"ok": False, "reason": "payment transaction record not found"}
    if transaction_row["activated_at"]:
        return {
            "ok": True,
            "already_activated": True,
            "company_key": transaction_row["company_key"],
            "company_name": transaction_row["company_name"],
        }

    metadata = {}
    try:
        metadata = json.loads(transaction_row["metadata_json"] or "{}")
    except Exception:
        metadata = {}

    company_key = str(transaction_row["company_key"] or metadata.get("company_key") or "").strip()
    company_name = str(transaction_row["company_name"] or metadata.get("company_name") or "").strip()
    payer_email = str(transaction_row["payer_email"] or metadata.get("user_email") or metadata.get("admin_email") or "").strip() or None
    subscription_months = max(int(transaction_row["configured_duration_months"] or metadata.get("subscription_months") or 0), 0)
    subscription_days = max(int(transaction_row["configured_duration_days"] or metadata.get("subscription_days") or 0), 0)
    plan_name = str(transaction_row["plan_name"] or metadata.get("plan_name") or "Basic").strip() or "Basic"
    payment_context = str(transaction_row["payment_context"] or metadata.get("license_context") or "license_activation").strip().lower()
    if not company_key or not company_name:
        return {"ok": False, "reason": "payment metadata is missing company activation details"}

    company_row = conn.execute(
        "SELECT key, name, subscription_expiry FROM companies WHERE key = ? OR lower(name) = lower(?) LIMIT 1",
        (company_key, company_name),
    ).fetchone()
    backup_result = None
    if company_row:
        resolved_company_key = company_row["key"]
        resolved_company_name = company_row["name"]
    else:
        create_company_record(
            conn=conn,
            company_key=company_key,
            company_name=company_name,
            subscription_expiry=datetime.now().date().isoformat(),
            status="Active",
            deployment_status="Live",
            contact_email=payer_email,
            subscription_plan_name=plan_name,
            subscription_status="trial",
            subscription_start_date=datetime.now().date().isoformat(),
            subscription_end_date=datetime.now().date().isoformat(),
        )
        resolved_company_key = company_key
        resolved_company_name = company_name
        conn.commit()
        backup_result = force_backup_after_company_creation(
            company_name=resolved_company_name,
            company_key=resolved_company_key,
            logger_instance=logger,
        )

    if subscription_months <= 0 and subscription_days <= 0:
        subscription_months = 1
    activation_result = activate_company_subscription(
        conn,
        company_key=resolved_company_key,
        plan_name=plan_name,
        payment_reference=transaction_row["reference"],
        duration_months=subscription_months,
        duration_days=subscription_days,
    )
    new_expiry = activation_result["end_date"]

    activated_at = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE license_payment_transactions
        SET activated_at = ?, status = 'success', updated_at = CURRENT_TIMESTAMP
        WHERE reference = ?
        """,
        (activated_at, transaction_row["reference"]),
    )
    database_log_audit_action(
        conn,
        resolved_company_key,
        "System",
        f"Verified Paystack payment: {transaction_row['reference']}",
        "Payments",
        details=(
            f"context={payment_context} plan={plan_name} amount={transaction_row['expected_amount']} "
            f"currency={transaction_row['currency']} new_expiry={new_expiry}"
        ),
        action_type="payment",
        document_ref=transaction_row["reference"],
    )
    conn.execute(
        """
        INSERT INTO system_logs (timestamp, level, module_name, message)
        VALUES (?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            "INFO",
            "Paystack",
            f"Verified and activated payment reference={transaction_row['reference']} company_key={resolved_company_key} plan={plan_name}",
        ),
    )
    return {
        "ok": True,
        "company_key": resolved_company_key,
        "company_name": resolved_company_name,
        "new_expiry": new_expiry,
        "backup_result": backup_result,
    }


def initialize_paystack_payment(
    email,
    amount,
    reference,
    *,
    company_key=None,
    company_name=None,
    plan_name=None,
    payment_context="license_activation",
    subscription_months=None,
    subscription_days=None,
    user_id=None,
    user_email=None,
    phone_number=None,
    metadata_extra=None,
):
    """Initialize a live Paystack checkout for card or Ghana mobile money."""
    config = get_paystack_runtime_config()
    if not config["secret_key_present"]:
        return {"ok": False, "reason": "Paystack secret key is not configured yet."}
    if not config["public_key_present"]:
        return {"ok": False, "reason": "Paystack public key is not configured yet."}
    if not config["callback_url_configured"]:
        return {"ok": False, "reason": "Paystack callback URL is not configured yet."}

    resolved_amount = float(amount or 0)
    resolved_currency = str(config["currency"] or "GHS").strip().upper() or "GHS"
    resolved_duration_months = max(int(subscription_months or 0), 0)
    resolved_duration_days = max(int(subscription_days or 0), 0)
    plan_snapshot = None
    normalized_plan_name = str(plan_name or "").strip() or None
    if normalized_plan_name:
        plan_snapshot = _resolve_subscription_plan_payment_snapshot(normalized_plan_name)
        if not plan_snapshot.get("ok"):
            return {"ok": False, "reason": plan_snapshot.get("reason") or SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE}
        resolved_amount = float(plan_snapshot["configured_amount"])
        resolved_currency = plan_snapshot["currency"]
        resolved_duration_months = int(plan_snapshot["duration_months"] or 0)
        resolved_duration_days = int(plan_snapshot["duration_days"] or 0)

    expected_amount = int(round(float(resolved_amount or 0) * 100))
    if expected_amount <= 0:
        return {"ok": False, "reason": "Payment amount must be greater than zero."}

    metadata = {
        "company_key": company_key,
        "company_name": company_name,
        "plan_name": normalized_plan_name,
        "license_context": payment_context,
        "subscription_months": resolved_duration_months,
        "subscription_days": resolved_duration_days,
        "configured_amount": float(resolved_amount or 0),
        "configured_currency": resolved_currency,
        "user_id": user_id,
        "user_email": user_email or email,
    }
    if plan_snapshot and plan_snapshot.get("features"):
        metadata["plan_features"] = list(plan_snapshot.get("features") or [])
    if phone_number:
        metadata["phone_number"] = phone_number
    if metadata_extra:
        metadata.update(metadata_extra)

    payload = {
        "email": str(email or "").strip(),
        "amount": expected_amount,
        "currency": resolved_currency,
        "reference": str(reference or "").strip(),
        "callback_url": config["callback_url"],
        "channels": ["card", "mobile_money"],
        "metadata": metadata,
    }
    if not payload["email"] or not payload["reference"]:
        return {"ok": False, "reason": "Missing Paystack payment details."}

    headers = {
        "Authorization": f"Bearer {config['secret_key']}",
        "Content-Type": "application/json",
    }
    conn = None
    try:
        response = requests.post(
            "https://api.paystack.co/transaction/initialize",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response_data = response.json()
        if response.status_code >= 400 or not response_data.get("status"):
            gateway_message = response_data.get("message") if isinstance(response_data, dict) else "Paystack initialization failed."
            logger.warning("Paystack initialize failed for reference=%s status_code=%s", reference, response.status_code)
            return {"ok": False, "reason": str(gateway_message or "Paystack initialization failed.")}
        authorization_url = response_data.get("data", {}).get("authorization_url")
        if not authorization_url:
            return {"ok": False, "reason": "Paystack did not return a checkout URL."}
        conn = get_connection()
        _upsert_license_payment_transaction(
            conn,
            reference=payload["reference"],
            company_key=company_key,
            company_name=company_name,
            payer_email=payload["email"],
            payment_context=payment_context,
            plan_name=metadata.get("plan_name"),
            configured_amount=resolved_amount,
            configured_duration_months=resolved_duration_months,
            configured_duration_days=resolved_duration_days,
            expected_amount=expected_amount,
            currency=resolved_currency,
            status="initialized",
            authorization_url=authorization_url,
            callback_url=config["callback_url"],
            metadata_json=json.dumps(metadata, default=str),
            gateway_status_summary=_serialize_paystack_gateway_summary(response_data),
        )
        conn.commit()
        log_system_event("INFO", "Paystack", f"Initialized payment reference={payload['reference']} context={payment_context}")
        return {
            "ok": True,
            "reference": payload["reference"],
            "authorization_url": authorization_url,
            "currency": resolved_currency,
            "expected_amount": expected_amount,
        }
    except Exception as exc:
        logger.warning("Paystack initialize request failed for reference=%s: %s", reference, sanitize_error_message(exc))
        return {"ok": False, "reason": "Paystack checkout could not be initialized right now. Please try again."}
    finally:
        if conn:
            conn.close()


def verify_paystack_payment(reference, activate_license=True):
    config = get_paystack_runtime_config()
    if not config["secret_key_present"]:
        return {"ok": False, "reason": "Paystack secret key is not configured yet."}
    normalized_reference = str(reference or "").strip()
    if not normalized_reference:
        return {"ok": False, "reason": "Payment reference is required for verification."}

    conn = None
    try:
        conn = get_connection()
        transaction_row = conn.execute(
            "SELECT * FROM license_payment_transactions WHERE reference = ? LIMIT 1",
            (normalized_reference,),
        ).fetchone()
        if not transaction_row:
            return {"ok": False, "reason": "No initialized Paystack payment was found for that reference."}
        metadata = {}
        try:
            metadata = json.loads(transaction_row["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        headers = {"Authorization": f"Bearer {config['secret_key']}"}
        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{normalized_reference}",
            headers=headers,
            timeout=30,
        )
        response_data = response.json()
        data = response_data.get("data") if isinstance(response_data, dict) else {}
        gateway_ok = bool(response_data.get("status")) and str(data.get("status") or "").lower() == "success"
        reference_ok = str(data.get("reference") or "").strip() == normalized_reference
        amount_ok = int(data.get("amount") or 0) == int(transaction_row["expected_amount"] or 0)
        currency_ok = str(data.get("currency") or "").upper() == str(transaction_row["currency"] or config["currency"]).upper()
        metadata_company_ok = (
            not metadata.get("company_key")
            or str(metadata.get("company_key") or "").strip() == str(transaction_row["company_key"] or "").strip()
        )
        if not (gateway_ok and reference_ok and amount_ok and currency_ok and metadata_company_ok):
            _upsert_license_payment_transaction(
                conn,
                reference=normalized_reference,
                company_key=transaction_row["company_key"],
                company_name=transaction_row["company_name"],
                payer_email=transaction_row["payer_email"],
                payment_context=transaction_row["payment_context"],
                plan_name=transaction_row["plan_name"],
                configured_amount=transaction_row["configured_amount"],
                configured_duration_months=transaction_row["configured_duration_months"],
                configured_duration_days=transaction_row["configured_duration_days"],
                expected_amount=transaction_row["expected_amount"],
                currency=transaction_row["currency"],
                status="failed",
                authorization_url=transaction_row["authorization_url"],
                callback_url=transaction_row["callback_url"],
                metadata_json=transaction_row["metadata_json"],
                gateway_status_summary=_serialize_paystack_gateway_summary(response_data),
            )
            conn.commit()
            return {
                "ok": False,
                "reason": "Paystack payment verification failed. Please confirm the payment completed before trying again.",
                "checks": {
                    "gateway_ok": gateway_ok,
                    "reference_ok": reference_ok,
                    "amount_ok": amount_ok,
                    "currency_ok": currency_ok,
                    "metadata_company_ok": metadata_company_ok,
                },
            }

        paid_at = data.get("paid_at") or datetime.now().isoformat(timespec="seconds")
        verified_at = datetime.now().isoformat(timespec="seconds")
        _upsert_license_payment_transaction(
            conn,
            reference=normalized_reference,
            company_key=transaction_row["company_key"],
            company_name=transaction_row["company_name"],
            payer_email=transaction_row["payer_email"],
            payment_context=transaction_row["payment_context"],
            plan_name=transaction_row["plan_name"],
            configured_amount=transaction_row["configured_amount"],
            configured_duration_months=transaction_row["configured_duration_months"],
            configured_duration_days=transaction_row["configured_duration_days"],
            expected_amount=transaction_row["expected_amount"],
            currency=transaction_row["currency"],
            status="success",
            authorization_url=transaction_row["authorization_url"],
            callback_url=transaction_row["callback_url"],
            metadata_json=transaction_row["metadata_json"],
            gateway_status_summary=_serialize_paystack_gateway_summary(response_data),
            paid_at=paid_at,
            verified_at=verified_at,
            activated_at=transaction_row["activated_at"],
        )
        activation_result = {"ok": True}
        if activate_license:
            refreshed_row = conn.execute(
                "SELECT * FROM license_payment_transactions WHERE reference = ? LIMIT 1",
                (normalized_reference,),
            ).fetchone()
            activation_result = _activate_verified_license_payment(conn, refreshed_row)
        conn.commit()
        return {
            "ok": bool(activation_result.get("ok")),
            "reason": activation_result.get("reason"),
            "reference": normalized_reference,
            "company_key": activation_result.get("company_key") or transaction_row["company_key"],
            "company_name": activation_result.get("company_name") or transaction_row["company_name"],
            "new_expiry": activation_result.get("new_expiry"),
            "already_activated": activation_result.get("already_activated", False),
        }
    except Exception as exc:
        logger.warning("Paystack verify request failed for reference=%s: %s", normalized_reference, sanitize_error_message(exc))
        return {"ok": False, "reason": "Paystack verification could not be completed right now. Please try again."}
    finally:
        if conn:
            conn.close()


def verify_paystack_webhook_signature(payload_bytes, signature_header):
    config = get_paystack_runtime_config()
    secret = config.get("webhook_secret") or config.get("secret_key")
    if not secret or not signature_header:
        return False
    computed_signature = hmac.new(
        secret.encode("utf-8"),
        payload_bytes if isinstance(payload_bytes, bytes) else str(payload_bytes or "").encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(computed_signature, str(signature_header or "").strip())


def process_paystack_webhook_event(payload_bytes, signature_header):
    if not verify_paystack_webhook_signature(payload_bytes, signature_header):
        return {"ok": False, "reason": "invalid webhook signature"}
    try:
        event_payload = json.loads(
            payload_bytes.decode("utf-8") if isinstance(payload_bytes, bytes) else str(payload_bytes or "{}")
        )
    except Exception:
        return {"ok": False, "reason": "invalid webhook payload"}
    if str(event_payload.get("event") or "").strip().lower() != "charge.success":
        return {"ok": False, "reason": "unsupported webhook event"}
    reference = (
        event_payload.get("data", {}).get("reference")
        if isinstance(event_payload.get("data"), dict)
        else None
    )
    if not reference:
        return {"ok": False, "reason": "webhook event missing payment reference"}
    return verify_paystack_payment(reference, activate_license=True)


def get_master_price_per_month():
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT master_price_per_month FROM system_settings WHERE id = 1"
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else 500.0
    except Exception as exc:
        logger.warning("Falling back to default master price: %s", sanitize_error_message(exc))
        return 500.0
    finally:
        if conn:
            conn.close()


def _get_active_company_id(expected_company_id=None):
    active_company_id = st.session_state.get("company_id")
    if not active_company_id:
        active_company_id = st.session_state.get("user", {}).get("key")
    if expected_company_id and active_company_id and expected_company_id != active_company_id:
        logger.warning(
            "Blocked cross-tenant access attempt: requested=%s active=%s",
            expected_company_id,
            active_company_id,
        )
    return active_company_id


def _safe_session_set(key, value):
    try:
        st.session_state[key] = value
    except Exception:
        return


def _get_secret_value(secret_name, section_name=None):
    value = None
    source = "missing"
    try:
        secrets_obj = st.secrets
    except Exception:
        secrets_obj = None

    if secrets_obj is not None:
        try:
            value = secrets_obj.get(secret_name)
        except Exception:
            value = None
        if value:
            return value, "top_level"

        if section_name:
            try:
                section_obj = secrets_obj.get(section_name, {})
            except Exception:
                section_obj = {}
            if section_obj:
                try:
                    value = section_obj.get(secret_name)
                except AttributeError:
                    value = None
                if value:
                    return value, f"nested_{section_name}_section"

    env_value = os.getenv(secret_name)
    if env_value:
        return env_value, "environment"

    return None, source


def _get_ai_runtime_config():
    diagnostics = {
        "streamlit_imported": st is not None,
        "secrets_accessible": False,
        "top_level_secret_keys": [],
        "top_level_key_present": False,
        "openai_section_present": False,
        "nested_key_present": False,
        "gemini_top_level_key_present": False,
        "gemini_section_present": False,
        "gemini_nested_key_present": False,
        "openai_secret_source": "missing",
        "gemini_secret_source": "missing",
        "provided_length": 0,
        "gemini_provided_length": 0,
        "provider_source": "default",
        "selected_provider": "openai",
        "fallback_used": False,
        "last_safe_error": "",
    }

    try:
        secrets_obj = st.secrets
        diagnostics["secrets_accessible"] = True
        try:
            diagnostics["top_level_secret_keys"] = sorted(str(key) for key in secrets_obj.keys())
        except Exception:
            diagnostics["top_level_secret_keys"] = []
        diagnostics["openai_section_present"] = "openai" in diagnostics["top_level_secret_keys"]
        diagnostics["gemini_section_present"] = "gemini" in diagnostics["top_level_secret_keys"]
    except Exception:
        secrets_obj = None

    openai_key, openai_source = _get_secret_value("OPENAI_API_KEY", section_name="openai")
    gemini_key, gemini_source = _get_secret_value("GEMINI_API_KEY", section_name="gemini")
    provider_value, provider_source = _get_secret_value("AI_PROVIDER")
    provider_name = str(provider_value or "openai").strip().lower()
    if provider_name not in {"openai", "gemini", "auto"}:
        provider_name = "openai"
        provider_source = "default_invalid"
    diagnostics["provider_source"] = provider_source if provider_source != "missing" else "default"
    diagnostics["selected_provider"] = provider_name
    diagnostics["top_level_key_present"] = bool(openai_source == "top_level")
    diagnostics["nested_key_present"] = bool(openai_source == "nested_openai_section")
    diagnostics["gemini_top_level_key_present"] = bool(gemini_source == "top_level")
    diagnostics["gemini_nested_key_present"] = bool(gemini_source == "nested_gemini_section")
    diagnostics["openai_secret_source"] = openai_source
    diagnostics["gemini_secret_source"] = gemini_source
    diagnostics["provided_length"] = len(str(openai_key or ""))
    diagnostics["gemini_provided_length"] = len(str(gemini_key or ""))

    return {
        "provider_name": provider_name,
        "openai_key": openai_key,
        "gemini_key": gemini_key,
        "diagnostics": diagnostics,
    }


def _is_openai_quota_error(exc):
    error_text = str(exc or "").lower()
    error_code = str(getattr(exc, "code", "") or "").lower()
    status_code = str(getattr(exc, "status_code", "") or "").lower()
    return (
        "insufficient_quota" in error_text
        or "quota" in error_text
        or error_code == "insufficient_quota"
        or status_code == "429"
    )


def _safe_ai_error_message(exc):
    error_text = str(exc or "")
    if _is_openai_quota_error(exc):
        return "OpenAI quota is unavailable right now."
    if exc is None:
        return ""
    lowered_error_text = error_text.lower()
    if "generativelanguage.googleapis.com" in lowered_error_text or "generatecontent" in lowered_error_text or "gemini" in lowered_error_text:
        return "Gemini request failed (rate limit or quota reached)"
    return sanitize_error_message(f"{type(exc).__name__}: {exc}")


def _call_gemini_chat(api_key, messages, temperature=0.3, max_tokens=1024):
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        f"?key={api_key}"
    )
    system_parts = []
    conversation_parts = []
    for message in messages:
        role = (message or {}).get("role", "user")
        content = str((message or {}).get("content", "") or "").strip()
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        conversation_parts.append(
            {
                "role": gemini_role,
                "parts": [{"text": content}],
            }
        )

    payload = {
        "contents": conversation_parts or [{"role": "user", "parts": [{"text": "ping"}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_parts:
        payload["systemInstruction"] = {
            "parts": [{"text": "\n\n".join(system_parts)}],
        }

    response = requests.post(endpoint, json=payload, timeout=30)
    response.raise_for_status()
    response_data = response.json()
    candidates = response_data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    response_text = "".join(str(part.get("text") or "") for part in parts).strip()
    if not response_text:
        raise RuntimeError("Gemini returned an empty response")
    return response_text


def get_ai_client_status():
    """Return the shared AI provider status without exposing any API key values."""
    runtime = _get_ai_runtime_config()
    diagnostics = dict(runtime["diagnostics"])
    openai_key = runtime["openai_key"]
    gemini_key = runtime["gemini_key"]
    preferred_provider = runtime["provider_name"]
    logger.info(
        "AI provider diagnostics: preferred_provider=%s openai_present=%s gemini_present=%s openai_source=%s gemini_source=%s top_level_keys=%s",
        preferred_provider,
        "Yes" if bool(openai_key) else "No",
        "Yes" if bool(gemini_key) else "No",
        diagnostics["openai_secret_source"],
        diagnostics["gemini_secret_source"],
        ",".join(diagnostics["top_level_secret_keys"]) or "none",
    )

    if preferred_provider == "gemini":
        if not gemini_key:
            _safe_session_set("ai_active", False)
            diagnostics["last_safe_error"] = "Gemini API key is not configured."
            return {
                "client": None,
                "provider": "gemini",
                "selected_provider": "gemini",
                "fallback_used": False,
                "key_present": False,
                "client_initialized": False,
                "error_type": "missing_key",
                "message": "AI assistant is not configured yet.",
                "openai_key_present": bool(openai_key),
                "gemini_key_present": False,
                **diagnostics,
            }
        _safe_session_set("ai_active", True)
        _safe_session_set("ai_provider_selected", "gemini")
        return {
            "client": "gemini",
            "provider": "gemini",
            "selected_provider": "gemini",
            "fallback_used": False,
            "key_present": True,
            "client_initialized": True,
            "error_type": None,
            "message": "",
            "openai_key_present": bool(openai_key),
            "gemini_key_present": True,
            **diagnostics,
        }

    openai_error = None
    if openai_key:
        try:
            if OpenAI is None:
                raise RuntimeError("OpenAI SDK is not installed")
            openai_client = OpenAI(api_key=openai_key)
            _safe_session_set("ai_active", True)
            _safe_session_set("ai_provider_selected", "openai")
            return {
                "client": openai_client,
                "provider": "openai",
                "selected_provider": "openai",
                "fallback_used": False,
                "key_present": True,
                "client_initialized": True,
                "error_type": None,
                "message": "",
                "openai_key_present": True,
                "gemini_key_present": bool(gemini_key),
                **diagnostics,
            }
        except Exception as exc:
            openai_error = exc
            diagnostics["last_safe_error"] = _safe_ai_error_message(exc)
            logger.warning("OpenAI client initialization failed; AI assistant disabled: %s", sanitize_error_message(exc))

    if preferred_provider == "auto" and gemini_key:
        diagnostics["fallback_used"] = bool(openai_error)
        diagnostics["last_safe_error"] = diagnostics["last_safe_error"] or ""
        _safe_session_set("ai_active", True)
        _safe_session_set("ai_provider_selected", "gemini")
        _safe_session_set("ai_provider_fallback_used", diagnostics["fallback_used"])
        return {
            "client": "gemini",
            "provider": "gemini",
            "selected_provider": "gemini",
            "fallback_used": diagnostics["fallback_used"],
            "key_present": True,
            "client_initialized": True,
            "error_type": None,
            "message": "",
            "openai_key_present": bool(openai_key),
            "gemini_key_present": True,
            **diagnostics,
        }

    _safe_session_set("ai_active", False)
    _safe_session_set("ai_provider_selected", "none")
    _safe_session_set("ai_provider_fallback_used", False)
    if preferred_provider == "auto":
        failure_message = "AI assistant is not configured yet."
        error_type = "missing_key"
        if openai_error and not gemini_key:
            failure_message = "AI assistant could not initialize."
            error_type = "client_init_failed"
    elif preferred_provider == "openai":
        failure_message = "AI assistant is not configured yet." if not openai_key else "AI assistant could not initialize."
        error_type = "missing_key" if not openai_key else "client_init_failed"
    else:
        failure_message = "AI assistant is not configured yet."
        error_type = "missing_key"
    return {
        "client": None,
        "provider": preferred_provider,
        "selected_provider": preferred_provider,
        "fallback_used": False,
        "key_present": bool(openai_key or gemini_key),
        "client_initialized": False,
        "error_type": error_type,
        "message": failure_message,
        "openai_key_present": bool(openai_key),
        "gemini_key_present": bool(gemini_key),
        **diagnostics,
    }


def get_openai_client_status():
    """Backward-compatible wrapper around the shared AI provider status."""
    return get_ai_client_status()


def get_openai_client_from_secrets():
    """Create an OpenAI client only when the API key is available."""
    return get_openai_client_status()["client"]


def get_openai_unavailable_message(openai_status):
    error_type = (openai_status or {}).get("error_type")
    if error_type == "client_init_failed":
        return "AI assistant could not initialize."
    if error_type == "missing_key":
        return "AI assistant is not configured yet."
    return "AI assistant is temporarily unavailable."


def _get_openai_client():
    """Backward-compatible wrapper for the shared OpenAI loader."""
    return get_openai_client_from_secrets()


def _get_ai_rate_limit_identity():
    user = st.session_state.get("user") or {}
    session_identity = st.session_state.setdefault("ai_rate_limit_session_id", str(uuid.uuid4()))
    return (
        user.get("key")
        or user.get("email")
        or user.get("username")
        or user.get("company_key")
        or session_identity
    )


def _consume_ai_rate_limit(purpose="general"):
    if purpose == "health_test":
        return True, 0

    now_ts = datetime.utcnow().timestamp()
    window_start = now_ts - AI_RATE_LIMIT_WINDOW_SECONDS
    identity = _get_ai_rate_limit_identity()
    tracker = st.session_state.setdefault("ai_rate_limit_tracker", {})
    recent_calls = [
        float(ts)
        for ts in tracker.get(identity, [])
        if isinstance(ts, (int, float)) and float(ts) >= window_start
    ]
    if len(recent_calls) >= AI_RATE_LIMIT_MAX_CALLS:
        tracker[identity] = recent_calls
        return False, len(recent_calls)
    recent_calls.append(now_ts)
    tracker[identity] = recent_calls
    return True, len(recent_calls)


def call_ai_assistant(messages, temperature=0.3, max_tokens=1024, purpose="general"):
    allowed, _ = _consume_ai_rate_limit(purpose=purpose)
    if not allowed:
        ai_status = get_ai_client_status()
        provider = ai_status.get("provider") or ai_status.get("selected_provider", "none")
        return {
            "ok": False,
            "success": False,
            "content": "",
            "provider": provider,
            "provider_used": provider,
            "fallback_used": False,
            "status": ai_status,
            "error": AI_RATE_LIMIT_MESSAGE,
            "openai_error_safe": "",
            "gemini_error_safe": "",
            "response_preview": "",
            "purpose": purpose,
        }

    ai_status = get_ai_client_status()
    active_client = ai_status["client"]
    provider = ai_status.get("provider")
    if active_client is None:
        return {
            "ok": False,
            "success": False,
            "content": "",
            "provider": provider or ai_status.get("selected_provider", "none"),
            "provider_used": provider or ai_status.get("selected_provider", "none"),
            "fallback_used": ai_status.get("fallback_used", False),
            "status": ai_status,
            "error": ai_status.get("message") or "AI assistant is not configured yet.",
            "openai_error_safe": ai_status.get("last_safe_error", "") if provider == "openai" else "",
            "gemini_error_safe": ai_status.get("last_safe_error", "") if provider == "gemini" else "",
            "response_preview": "",
            "purpose": purpose,
        }

    openai_error_safe = ""
    gemini_error_safe = ""
    try:
        if provider == "gemini":
            response_text = _call_gemini_chat(
                _get_ai_runtime_config()["gemini_key"],
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if not response_text:
                raise RuntimeError("Gemini returned an empty response")
        else:
            completion = active_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            response_text = (completion.choices[0].message.content or "").strip()
            if not response_text:
                raise RuntimeError("OpenAI returned an empty response")
        _safe_session_set("ai_provider_selected", provider)
        _safe_session_set("ai_provider_fallback_used", ai_status.get("fallback_used", False))
        _safe_session_set("ai_provider_last_error", "")
        return {
            "ok": True,
            "success": True,
            "content": response_text,
            "provider": provider,
            "provider_used": provider,
            "fallback_used": ai_status.get("fallback_used", False),
            "status": ai_status,
            "error": "",
            "openai_error_safe": openai_error_safe,
            "gemini_error_safe": gemini_error_safe,
            "response_preview": response_text[:120],
            "purpose": purpose,
        }
    except Exception as exc:
        runtime = _get_ai_runtime_config()
        gemini_key = runtime["gemini_key"]
        if provider == "openai" and runtime["provider_name"] == "auto" and gemini_key:
            openai_failure = _safe_ai_error_message(exc)
            openai_error_safe = openai_failure
            logger.warning("OpenAI request failed; attempting Gemini fallback: %s", sanitize_error_message(openai_failure))
            try:
                response_text = _call_gemini_chat(
                    gemini_key,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if not response_text:
                    raise RuntimeError("Gemini returned an empty response")
                _safe_session_set("ai_provider_selected", "gemini")
                _safe_session_set("ai_provider_fallback_used", True)
                _safe_session_set("ai_provider_last_error", openai_failure)
                return {
                    "ok": True,
                    "success": True,
                    "content": response_text,
                    "provider": "gemini",
                    "provider_used": "gemini",
                    "fallback_used": True,
                    "status": {
                        **ai_status,
                        "provider": "gemini",
                        "selected_provider": "gemini",
                        "fallback_used": True,
                        "last_safe_error": openai_failure,
                    },
                    "error": "",
                    "openai_error_safe": openai_failure,
                    "gemini_error_safe": "",
                    "response_preview": response_text[:120],
                    "purpose": purpose,
                }
            except Exception as fallback_exc:
                gemini_error_safe = _safe_ai_error_message(fallback_exc)
                exc = fallback_exc
        elif provider == "openai":
            openai_error_safe = _safe_ai_error_message(exc)
        elif provider == "gemini":
            gemini_error_safe = _safe_ai_error_message(exc)
        safe_error = _safe_ai_error_message(exc)
        _safe_session_set("ai_provider_last_error", safe_error)
        return {
            "ok": False,
            "success": False,
            "content": "",
            "provider": provider,
            "provider_used": "gemini" if gemini_error_safe else provider,
            "fallback_used": ai_status.get("fallback_used", False),
            "status": {
                **ai_status,
                "last_safe_error": safe_error,
            },
            "error": AI_TEMPORARY_UNAVAILABLE_MESSAGE,
            "openai_error_safe": openai_error_safe,
            "gemini_error_safe": gemini_error_safe,
            "response_preview": "",
            "purpose": purpose,
        }


def request_ai_chat_completion(messages, temperature=0.3, max_tokens=1024):
    return call_ai_assistant(messages, temperature=temperature, max_tokens=max_tokens, purpose="general")


def _table_exists(conn, table_name):
    return db_table_exists(conn, table_name)


def _fetch_ai_assistant_records(conn, client_id):
    """Collect the last 30 days of invoice, expense, and payroll activity for a client."""
    since_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    records = {"invoices": [], "expenses": [], "payroll": []}

    try:
        journal_rows = get_recent_accounting_activity(client_id, limit=50, conn=conn)
        records["invoices"] = [
            row for row in journal_rows
            if str(row.get("date") or "") >= since_date
            and any(token in str(row.get("activity_type") or "").lower() for token in ("invoice", "sale", "pos"))
        ]
        records["expenses"] = [
            row for row in journal_rows
            if str(row.get("date") or "") >= since_date
            and any(token in str(row.get("description") or "").lower() for token in ("expense", "purchase", "bill"))
        ]
    except Exception as exc:
        logger.warning("AI assistant journal activity fallback failed for company %s: %s", client_id, sanitize_error_message(exc))

    if _table_exists(conn, "payroll"):
        payroll_rows = execute_portable_query(
            conn,
            """
            SELECT created_at, emp_name, basic_salary, allowances, paye, net_salary, month, year, payment_status
            FROM payroll
            WHERE company_key = ? AND date(COALESCE(created_at, CURRENT_TIMESTAMP)) >= date(?) AND COALESCE(status, 'Active') != 'Void'
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (client_id, since_date),
        ).fetchall()
        records["payroll"] = [row_to_dict(row) for row in payroll_rows]

    return records


def _summarize_ai_assistant_data(records):
    invoice_total = sum(float(row.get("credit") or 0) for row in records["invoices"])
    expense_total = sum(
        float(row.get("debit") or row.get("credit") or 0) for row in records["expenses"]
    )
    payroll_total = sum(float(row.get("net_salary") or 0) for row in records["payroll"])

    lines = [
        f"Invoices in last 30 days: {len(records['invoices'])}, total value GHs {invoice_total:,.2f}.",
        f"Expenses in last 30 days: {len(records['expenses'])}, total value GHs {expense_total:,.2f}.",
        f"Payroll entries in last 30 days: {len(records['payroll'])}, net payroll GHs {payroll_total:,.2f}.",
    ]

    for label, rows in (
        ("Recent invoices", records["invoices"][:5]),
        ("Recent expenses", records["expenses"][:5]),
        ("Recent payroll", records["payroll"][:5]),
    ):
        if rows:
            lines.append(f"{label}: {rows}")

    return "\n".join(lines)


def _row_to_dict(row):
    return row_to_dict(row) or {}


def _generate_staff_login_key(company_key, role_name):
    suffix = "BK" if role_name == "Bookkeeper" else "STF"
    return f"{company_key}-{suffix}-{random.randint(1000, 9999)}"


def _hash_staff_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _generate_user_id(company_key, staff_name, login_key):
    seed = f"{company_key}|{staff_name.strip()}|{login_key.strip()}|{datetime.now().isoformat()}|{random.randint(1000,9999)}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _clear_streamlit_state(*keys):
    for key in keys:
        st.session_state.pop(key, None)


def _get_form_reset_nonce(counter_key):
    return int(st.session_state.get(counter_key, 0) or 0)


def _increment_form_reset(counter_key):
    st.session_state[counter_key] = _get_form_reset_nonce(counter_key) + 1
    return st.session_state[counter_key]


def _form_widget_key(base_key, counter_key):
    return f"{base_key}_{_get_form_reset_nonce(counter_key)}"


def _load_registered_supplier_names(company_key):
    conn = None
    try:
        conn = get_connection()
        rows = execute_portable_query(
            conn,
            "SELECT name FROM suppliers WHERE company_key = ? ORDER BY name",
            (company_key,),
        ).fetchall()
        return [str(row_get(row, "name", row_get(row, 0)) or "").strip() for row in rows if str(row_get(row, "name", row_get(row, 0)) or "").strip()]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


FIREBASE_MODULE_APP = None


def _init_modules_firebase_app():
    global FIREBASE_MODULE_APP
    if firebase_admin is None or credentials is None or db is None:
        return None
    if FIREBASE_MODULE_APP is not None:
        return FIREBASE_MODULE_APP
    try:
        credentials_result = get_firebase_service_account_info()
        diagnostics = get_recovery_source_diagnostics()
        if not credentials_result.get("ok"):
            logger.warning("Modules Firebase client could not load credentials: %s", sanitize_error_message(credentials_result.get("reason")))
            return None
        if not diagnostics.get("bucket_name"):
            logger.warning("Modules Firebase client could not determine a storage bucket name.")
            return None
        if not diagnostics.get("database_url"):
            logger.warning("Modules Firebase client is missing a database URL configuration.")
            return None
        FIREBASE_MODULE_APP = firebase_admin.initialize_app(
            credentials.Certificate(credentials_result["service_account_info"]),
            {
                "databaseURL": diagnostics["database_url"],
                "storageBucket": diagnostics["bucket_name"],
            },
            name="eka-modules-sync",
        )
        return FIREBASE_MODULE_APP
    except ValueError:
        try:
            FIREBASE_MODULE_APP = firebase_admin.get_app("eka-modules-sync")
            return FIREBASE_MODULE_APP
        except Exception:
            return None
    except Exception:
        return None


def _push_transaction_to_cloud(entry_id, payload):
    firebase_app = _init_modules_firebase_app()
    if firebase_app is None or db is None:
        return False
    try:
        company_key = str(payload.get("company_key") or "SYSTEM")
        payload = dict(payload)
        payload["local_entry_id"] = entry_id
        pushed_ref = db.reference(
            f"journal_entries/{company_key}",
            app=firebase_app,
        ).push(payload)
        return bool(getattr(pushed_ref, "key", None))
    except Exception:
        return False


BASE_CURRENCY = "GHS"
BOG_DISPLAY_RATES = {
    "GHS": 1.0,
    "USD": 11.65,
    "EUR": 13.34,
    "GBP": 15.47,
}
ACCOUNTING_ASSISTANT_SYSTEM_PROMPT = (
    "You are a Senior Chartered Accountant for a Ghanaian enterprise. Provide direct, professional financial analysis using the company's ledger and journal data."
)


def get_currency_symbol():
    return st.session_state.get("currency_symbol", "GHS")


def _normalize_account_category(category):
    normalized = str(category or "").strip().title()
    if normalized == "Revenue":
        return "Income"
    return normalized


def _resolve_entry_date(entry_date=None):
    value = entry_date or datetime.now().date()
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def get_display_currency():
    conn = None
    try:
        conn = get_connection()
        row = execute_portable_query(
            conn,
            "SELECT COALESCE(display_currency, base_currency, 'GHS') AS currency FROM system_settings WHERE id = 1"
        ).fetchone()
        return str(row_get(row, "currency", row_get(row, 0, BASE_CURRENCY)) or BASE_CURRENCY) if row else BASE_CURRENCY
    except Exception:
        return BASE_CURRENCY
    finally:
        if conn:
            conn.close()


def get_exchange_rate():
    session_rate = st.session_state.get("exchange_rate")
    if session_rate not in (None, "", 0):
        try:
            return max(float(session_rate), 0.000001)
        except (TypeError, ValueError):
            pass

    conn = None
    try:
        conn = get_connection()
        row = execute_portable_query(
            conn,
            "SELECT COALESCE(display_currency, 'GHS') AS display_currency, COALESCE(exchange_rate, 1.0) AS exchange_rate FROM system_settings WHERE id = 1"
        ).fetchone()
        if row:
            display_currency = str(row_get(row, "display_currency", row_get(row, 0, BASE_CURRENCY)) or BASE_CURRENCY).upper()
            fallback_rate = BOG_DISPLAY_RATES.get(display_currency, 1.0)
            exchange_rate_value = row_get(row, "exchange_rate", row_get(row, 1))
            rate = float(exchange_rate_value) if exchange_rate_value not in (None, "") else fallback_rate
        else:
            rate = 1.0
        st.session_state.exchange_rate = rate
        return max(rate, 0.000001)
    except Exception:
        return 1.0
    finally:
        if conn:
            conn.close()


def convert_amount_from_base(amount):
    value = float(amount or 0.0)
    currency = get_display_currency()
    rate = get_exchange_rate()
    if currency == BASE_CURRENCY or rate <= 0:
        return value
    return value * (1.0 / rate)


def format_currency(amount, currency=None):
    converted = convert_amount_from_base(amount)
    return f"{get_currency_symbol()} {converted:,.2f}"


def format_currency_dataframe(dataframe):
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        return dataframe
    df = dataframe.copy()
    cols_to_fix = [
        'Price',
        'Cost',
        'Amount',
        'Total',
        'Balance',
        'Value',
        'Salary',
        'Net',
        'Debit',
        'Credit',
        'Movement',
        'Residual',
        'Accumulated',
        'Book',
        'Revenue',
        'Expense',
        'Tax',
        'Cash',
    ]
    exchange_rate = st.session_state.get("exchange_rate") or get_exchange_rate()
    safe_rate = float(exchange_rate) if float(exchange_rate or 0) > 0 else 1.0
    currency_symbol = get_currency_symbol()
    for column_name in df.columns:
        if any(key.lower() in str(column_name).lower() for key in cols_to_fix):
            numeric_series = pd.to_numeric(df[column_name], errors="coerce")
            if numeric_series.notna().any():
                df[column_name] = numeric_series.fillna(0.0).apply(
                    lambda x: f"{currency_symbol}{float(x)/safe_rate:,.2f}"
                )
    return df


def get_reporting_multiplier():
    currency = get_display_currency()
    rate = get_exchange_rate()
    return 1.0 if currency == BASE_CURRENCY or rate <= 0 else (1.0 / rate)


def _selected_currency_context():
    display_currency = get_display_currency()
    exchange_rate = get_exchange_rate()
    currency_symbol = get_currency_symbol()
    return (
        f"Base ledger currency: {BASE_CURRENCY}. "
        f"Selected presentation currency: {display_currency}. "
        f"Selected currency symbol: {currency_symbol}. "
        f"Display conversion basis: 1 {display_currency} = {exchange_rate:,.4f} GHS."
        if display_currency != BASE_CURRENCY
        else f"Base ledger currency and presentation currency are both {BASE_CURRENCY}, using symbol {currency_symbol}."
    )


def _load_accounting_ai_context(company_key):
    if not company_key:
        return "No company context is currently loaded."
    conn = None
    try:
        conn = get_connection()
        transactions = []
        inventory = []
        try:
            transactions = get_recent_accounting_activity(company_key, limit=8, conn=conn)
        except Exception:
            transactions = []
        try:
            inventory = execute_portable_query(
                conn,
                """
                SELECT item_name, qty, cost_price, price
                FROM inventory
                WHERE company_key = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 8
                """,
                (company_key,),
            ).fetchall()
        except sqlite3.Error:
            inventory = []
        journal_entries = []
        try:
            journal_entries = execute_portable_query(
                conn,
                """
                SELECT je.date, je.description, je.reference, jl.debit, jl.credit, c.name as account_name
                FROM journal_entries je
                JOIN journal_lines jl ON jl.entry_id = je.id
                JOIN chart_of_accounts c ON c.id = jl.account_id
                WHERE je.company_key = ?
                ORDER BY je.date DESC, je.id DESC
                LIMIT 5
                """,
                (company_key,),
            ).fetchall()
        except sqlite3.Error:
            journal_entries = []
        tx_summary = rows_to_dicts(transactions) if transactions else []
        inventory_summary = rows_to_dicts(inventory) if inventory else []
        journal_summary = rows_to_dicts(journal_entries) if journal_entries else []
        return (
            f"Recent transactions: {tx_summary if tx_summary else 'None available'}. "
            f"Recent inventory rows: {inventory_summary if inventory_summary else 'None available'}. "
            f"Recent General Journal entries: {journal_summary if journal_summary else 'None available'}."
        )
    except Exception:
        return "Company transaction and inventory context is currently unavailable."
    finally:
        if conn:
            conn.close()


def accounting_ai_response(module_selection, chat_history):
    role = st.session_state.get("user", {}).get("role", "System")
    ai_status = get_ai_client_status()
    if ai_status["client"] is None:
        return f"{get_openai_unavailable_message(ai_status)} You can still use the module data and reports normally."

    company_key = (
        st.session_state.get("company_id")
        or st.session_state.get("user", {}).get("key")
        or st.session_state.get("user", {}).get("company_key")
    )
    if not require_permission(
        role,
        "use_ai_assistant",
        action_label="use the AI assistant",
        company_key=company_key,
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return "You do not have permission to perform this action."
    messages = [
        {"role": "system", "content": ACCOUNTING_ASSISTANT_SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                f"Current module: {module_selection}. "
                f"{_selected_currency_context()} "
                f"{_load_accounting_ai_context(company_key)} "
                "Assume the user operates in Ghana unless they specify otherwise."
            ),
        },
    ]
    messages.extend(chat_history[-8:])

    response = request_ai_chat_completion(messages=messages, temperature=0.3, max_tokens=1024)
    if response["ok"]:
        return response["content"].strip()
    logger.error("Accounting assistant request failed via provider %s: %s", response.get("provider"), sanitize_error_message(response.get("error")))
    return response.get("error") or "AI assistant request failed. Please try again."


def render_accounting_assistant_sidebar(module_selection):
    role = st.session_state.get("user", {}).get("role", "System")
    company_key = (
        st.session_state.get("company_id")
        or st.session_state.get("user", {}).get("key")
        or st.session_state.get("user", {}).get("company_key")
    )
    history_key = "accounting_ai_sidebar_history"
    if history_key not in st.session_state:
        st.session_state[history_key] = [
            {
                "role": "assistant",
                "content": (
                    "Ask an accounting question about IFRS, Ghana taxes, payroll, VAT, NHIL, GETFund, "
                    "or how the current module should be used."
                ),
            }
        ]
    st.sidebar.markdown(f"**AI Assistant ({get_currency_symbol()})**")
    st.sidebar.caption(module_selection)
    st.sidebar.caption(_selected_currency_context())
    if not require_permission(
        role,
        "use_ai_assistant",
        action_label="use the AI assistant",
        company_key=company_key,
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return
    history_container = st.sidebar.container(height=220)
    with history_container:
        for message in st.session_state[history_key][-8:]:
            speaker = "AI" if message["role"] == "assistant" else "You"
            st.markdown(f"**{speaker}:** {message['content']}")

    user_question = st.sidebar.chat_input(
        "Ask Accounting AI...",
        key=f"accounting_sidebar_input_{module_selection}",
    )
    if user_question:
        st.session_state[history_key].append({"role": "user", "content": user_question})
        with st.spinner("Accounting AI is reviewing your question..."):
            answer = accounting_ai_response(module_selection, st.session_state[history_key])
        st.session_state[history_key].append({"role": "assistant", "content": answer})
        st.rerun()


def is_period_locked(company_key, entry_date, conn=None):
    if not company_key:
        return False
    entry_date_iso = _resolve_entry_date(entry_date)
    owns_connection = conn is None
    conn = conn or get_connection()
    if conn is None:
        return False
    try:
        period_columns = {row[1] for row in conn.execute("PRAGMA table_info(accounting_periods)").fetchall()}
        status_clause = ""
        if "status" in period_columns:
            status_clause = " OR lower(COALESCE(status, 'Open')) IN ('closed', 'locked')"
        row = conn.execute(
            f"""
            SELECT 1
            FROM accounting_periods
            WHERE company_key = ?
              AND (COALESCE(is_locked, 0) = 1{status_clause})
              AND date(?) BETWEEN date(start_date) AND date(end_date)
            LIMIT 1
            """,
            (company_key, entry_date_iso),
        ).fetchone()
        return bool(row)
    finally:
        if owns_connection and conn:
            conn.close()


def set_period_lock(company_key, period_date, locked, locked_by=None):
    return set_period_status(company_key, period_date, "Locked" if locked else "Open", changed_by=locked_by)


def set_period_status(company_key, period_date, status, changed_by=None):
    normalized_status = str(status or "Open").strip().title()
    required_permission = {
        "Closed": "close_period",
        "Locked": "lock_period",
        "Open": "reopen_period",
    }.get(normalized_status)
    if changed_by and required_permission and not user_has_permission(changed_by, required_permission):
        _record_permission_security_event(
            changed_by,
            required_permission,
            action_label=f"{normalized_status.lower()} accounting period",
            company_key=company_key,
        )
        raise PermissionError("This role cannot change accounting period controls.")
    period_dt = pd.to_datetime(period_date).date()
    start_date = period_dt.replace(day=1)
    next_month = (pd.Timestamp(start_date) + pd.offsets.MonthBegin(1)).date()
    end_date = (pd.Timestamp(next_month) - pd.Timedelta(days=1)).date()
    period_label = start_date.strftime("%Y-%m")
    if normalized_status not in {"Open", "Closed", "Locked"}:
        raise ValueError("Accounting period status must be Open, Closed, or Locked.")
    is_locked = normalized_status == "Locked"
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO accounting_periods (
                company_key, period_label, start_date, end_date, status, is_locked,
                closed_at, closed_by, locked_at, locked_by, reopened_at, reopened_by
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                CASE WHEN ? = 'Closed' THEN CURRENT_TIMESTAMP ELSE NULL END,
                CASE WHEN ? = 'Closed' THEN ? ELSE NULL END,
                CASE WHEN ? = 'Locked' THEN CURRENT_TIMESTAMP ELSE NULL END,
                CASE WHEN ? = 'Locked' THEN ? ELSE NULL END,
                CASE WHEN ? = 'Open' THEN CURRENT_TIMESTAMP ELSE NULL END,
                CASE WHEN ? = 'Open' THEN ? ELSE NULL END
            )
            ON CONFLICT(company_key, period_label) DO UPDATE SET
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                status = excluded.status,
                is_locked = excluded.is_locked,
                closed_at = CASE WHEN excluded.status = 'Closed' THEN CURRENT_TIMESTAMP ELSE closed_at END,
                closed_by = CASE WHEN excluded.status = 'Closed' THEN excluded.closed_by ELSE closed_by END,
                locked_at = CASE WHEN excluded.status = 'Locked' THEN CURRENT_TIMESTAMP ELSE locked_at END,
                locked_by = CASE WHEN excluded.status = 'Locked' THEN excluded.locked_by ELSE locked_by END,
                reopened_at = CASE WHEN excluded.status = 'Open' THEN CURRENT_TIMESTAMP ELSE reopened_at END,
                reopened_by = CASE WHEN excluded.status = 'Open' THEN excluded.reopened_by ELSE reopened_by END
            """,
            (
                company_key,
                period_label,
                start_date.isoformat(),
                end_date.isoformat(),
                normalized_status,
                int(is_locked),
                normalized_status,
                normalized_status,
                changed_by,
                normalized_status,
                normalized_status,
                changed_by,
                normalized_status,
                normalized_status,
                changed_by,
            ),
        )
        conn.commit()
        if changed_by:
            log_audit_action(
                conn,
                company_key,
                _normalize_role_name(changed_by),
                f"Accounting Period {normalized_status}",
                "Period Control",
                details=f"period_label={period_label}; status={normalized_status}",
                action_type="admin",
                document_ref=period_label,
            )
    finally:
        conn.close()


def _get_or_create_account(conn, account_name, category, parent_name=None):
    normalized_name = str(account_name or "").strip()
    normalized_category = _normalize_account_category(category)
    parent_id = None
    if parent_name:
        parent_row = conn.execute(
            "SELECT id FROM chart_of_accounts WHERE lower(COALESCE(name, account_name)) = lower(?) LIMIT 1",
            (str(parent_name).strip(),),
        ).fetchone()
        parent_id = int(parent_row["id"]) if parent_row else None
    return engine_get_or_create_account(conn, normalized_name, normalized_category, parent_id=parent_id)


def _normalize_account_name(value):
    return " ".join(str(value or "").strip().lower().split())


CORE_FINANCIAL_ACCOUNT_SPECS = [
    {"canonical_name": "Cash", "account_type": "Asset", "aliases": ["Cash"], "require_posting_account": True},
    {"canonical_name": "Bank", "account_type": "Asset", "aliases": ["Bank"], "require_posting_account": True},
    {"canonical_name": "Mobile Money", "account_type": "Asset", "aliases": ["Mobile Money", "MoMo", "MobileMoney"], "require_posting_account": True},
    {"canonical_name": "Owner Capital", "account_type": "Equity", "aliases": ["Owner Capital", "Capital Account", "Capital"], "require_posting_account": True},
    {"canonical_name": "Owner Drawings", "account_type": "Equity", "aliases": ["Owner Drawings", "Drawings", "Owner Withdrawal", "Owner Withdrawals"], "require_posting_account": True},
    {"canonical_name": "Opening Balance Equity", "account_type": "Equity", "aliases": ["Opening Balance Equity"], "require_posting_account": True},
    {"canonical_name": "Loan Payable", "account_type": "Liability", "aliases": ["Loan Payable", "Loans Payable"], "require_posting_account": True},
    {"canonical_name": "General Expenses", "account_type": "Expense", "aliases": ["General Expenses", "General Expense"], "require_posting_account": True},
    {"canonical_name": "Fixed Assets", "account_type": "Asset", "aliases": ["Fixed Assets", "Fixed Asset", "Equipment"], "require_posting_account": True},
]


TAX_CONTROL_ACCOUNT_SPECS = [
    {
        "canonical_name": "VAT Payable",
        "account_type": "Liability",
        "aliases": ["VAT Payable", "VAT Output Payable", "Output VAT Payable"],
    },
    {
        "canonical_name": "VAT Receivable",
        "account_type": "Asset",
        "aliases": ["VAT Receivable", "VAT Input Receivable", "Input VAT Receivable"],
    },
    {
        "canonical_name": "NHIL Payable",
        "account_type": "Liability",
        "aliases": ["NHIL Payable", "National Health Insurance Levy Payable"],
    },
    {
        "canonical_name": "GETFund Levy Payable",
        "account_type": "Liability",
        "aliases": ["GETFund Levy Payable", "GETFund Payable", "GETFund Levy"],
    },
]


def _find_matching_account_row(conn, account_names, require_posting_account=False):
    normalized_targets = {
        _normalize_account_name(name)
        for name in account_names
        if _normalize_account_name(name)
    }
    if not normalized_targets:
        return None
    rows = conn.execute(
        """
        SELECT
            id,
            COALESCE(NULLIF(name, ''), NULLIF(account_name, ''), '') AS account_name,
            COALESCE(NULLIF(type, ''), NULLIF(account_type, ''), NULLIF(category, ''), 'Asset') AS account_type,
            COALESCE(posting_allowed, 1) AS posting_allowed
        FROM chart_of_accounts
        ORDER BY id
        """
    ).fetchall()
    first_match = None
    for row in rows:
        normalized_existing = _normalize_account_name(row["account_name"])
        if normalized_existing in normalized_targets:
            if not first_match:
                first_match = row
            if require_posting_account and not bool(int(row["posting_allowed"] or 0)):
                continue
            return row
    return first_match


def get_or_create_account(company_key, account_name, account_type, conn=None):
    normalized_name = " ".join(str(account_name or "").strip().split())
    normalized_type = _normalize_account_category(account_type)
    if not normalized_name or not normalized_type:
        raise ValueError("Account name and type are required.")
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        existing_row = _find_matching_account_row(conn, [normalized_name], require_posting_account=False)
        if existing_row:
            existing_type = str(existing_row["account_type"] or "").strip().title()
            if existing_type and existing_type != normalized_type:
                logger.warning(
                    "Account type mismatch detected for company_key=%s account=%s existing_type=%s requested_type=%s",
                    company_key,
                    normalized_name,
                    existing_type,
                    normalized_type,
                )
                log_system_event(
                    "WARNING",
                    "Chart of Accounts",
                    "Account mismatch detected company_key={company_key} account={account} existing_type={existing_type} requested_type={requested_type}".format(
                        company_key=company_key,
                        account=normalized_name,
                        existing_type=existing_type,
                        requested_type=normalized_type,
                    ),
                )
            logger.info("Reused chart account company_key=%s account=%s account_id=%s", company_key, normalized_name, int(existing_row["id"]))
            log_system_event(
                "INFO",
                "Chart of Accounts",
                "Reused chart account company_key={company_key} account={account} account_id={account_id}".format(
                    company_key=company_key,
                    account=normalized_name,
                    account_id=int(existing_row["id"]),
                ),
            )
            return int(existing_row["id"])
        account_id = engine_get_or_create_account(conn, normalized_name, normalized_type)
        logger.info("Created chart account company_key=%s account=%s account_id=%s", company_key, normalized_name, int(account_id))
        log_system_event(
            "INFO",
            "Chart of Accounts",
            "Created chart account company_key={company_key} account={account} account_id={account_id} type={account_type}".format(
                company_key=company_key,
                account=normalized_name,
                account_id=int(account_id),
                account_type=normalized_type,
            ),
        )
        if owns_connection:
            conn.commit()
        return int(account_id)
    finally:
        if owns_connection and conn:
            conn.close()


def ensure_core_financial_accounts(company_key, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    ensured_accounts = []
    try:
        for spec in CORE_FINANCIAL_ACCOUNT_SPECS:
            canonical_name = spec["canonical_name"]
            account_type = _normalize_account_category(spec["account_type"])
            aliases = spec.get("aliases") or [canonical_name]
            matched_row = _find_matching_account_row(
                conn,
                [canonical_name, *aliases],
                require_posting_account=bool(spec.get("require_posting_account")),
            )
            if matched_row:
                existing_name = str(matched_row["account_name"] or "").strip() or canonical_name
                existing_type = str(matched_row["account_type"] or "").strip().title()
                if existing_type and existing_type != account_type:
                    logger.warning(
                        "Core account type mismatch detected for company_key=%s canonical=%s existing_name=%s existing_type=%s expected_type=%s",
                        company_key,
                        canonical_name,
                        existing_name,
                        existing_type,
                        account_type,
                    )
                    log_system_event(
                        "WARNING",
                        "Chart of Accounts",
                        "Core account mismatch company_key={company_key} canonical={canonical} existing_name={existing_name} existing_type={existing_type} expected_type={expected_type}".format(
                            company_key=company_key,
                            canonical=canonical_name,
                            existing_name=existing_name,
                            existing_type=existing_type,
                            expected_type=account_type,
                        ),
                    )
                else:
                    logger.info(
                        "Reused core financial account company_key=%s canonical=%s existing_name=%s account_id=%s",
                        company_key,
                        canonical_name,
                        existing_name,
                        int(matched_row["id"]),
                    )
                    log_system_event(
                        "INFO",
                        "Chart of Accounts",
                        "Reused core financial account company_key={company_key} canonical={canonical} existing_name={existing_name} account_id={account_id}".format(
                            company_key=company_key,
                            canonical=canonical_name,
                            existing_name=existing_name,
                            account_id=int(matched_row["id"]),
                        ),
                    )
                ensured_accounts.append(
                    {
                        "canonical_name": canonical_name,
                        "resolved_name": existing_name,
                        "account_type": existing_type or account_type,
                        "account_id": int(matched_row["id"]),
                        "status": "reused",
                    }
                )
                continue
            created_account_id = get_or_create_account(company_key, canonical_name, account_type, conn=conn)
            ensured_accounts.append(
                {
                    "canonical_name": canonical_name,
                    "resolved_name": canonical_name,
                    "account_type": account_type,
                    "account_id": int(created_account_id),
                    "status": "created",
                }
            )
        if owns_connection:
            conn.commit()
        return ensured_accounts
    finally:
        if owns_connection and conn:
            conn.close()


def ensure_tax_control_accounts(company_key, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    ensured_accounts = []
    try:
        for spec in TAX_CONTROL_ACCOUNT_SPECS:
            canonical_name = spec["canonical_name"]
            account_type = _normalize_account_category(spec["account_type"])
            aliases = spec.get("aliases") or [canonical_name]
            matched_row = _find_matching_account_row(conn, [canonical_name, *aliases], require_posting_account=True)
            if matched_row:
                existing_name = str(matched_row["account_name"] or "").strip() or canonical_name
                existing_type = str(matched_row["account_type"] or "").strip().title()
                status = "reused"
                if existing_type and existing_type != account_type:
                    status = "type_mismatch_reused"
                    logger.warning(
                        "Tax account type mismatch detected for company_key=%s canonical=%s existing_name=%s existing_type=%s expected_type=%s",
                        company_key,
                        canonical_name,
                        existing_name,
                        existing_type,
                        account_type,
                    )
                    log_system_event(
                        "WARNING",
                        "Chart of Accounts",
                        "Tax account mismatch company_key={company_key} canonical={canonical} existing_name={existing_name} existing_type={existing_type} expected_type={expected_type}".format(
                            company_key=company_key,
                            canonical=canonical_name,
                            existing_name=existing_name,
                            existing_type=existing_type,
                            expected_type=account_type,
                        ),
                    )
                ensured_accounts.append(
                    {
                        "canonical_name": canonical_name,
                        "resolved_name": existing_name,
                        "account_type": existing_type or account_type,
                        "account_id": int(matched_row["id"]),
                        "status": status,
                    }
                )
                continue
            created_account_id = get_or_create_account(company_key, canonical_name, account_type, conn=conn)
            ensured_accounts.append(
                {
                    "canonical_name": canonical_name,
                    "resolved_name": canonical_name,
                    "account_type": account_type,
                    "account_id": int(created_account_id),
                    "status": "created",
                }
            )
        if owns_connection:
            conn.commit()
        return ensured_accounts
    finally:
        if owns_connection and conn:
            conn.close()


def _tax_account_map(company_key, conn):
    return {row["canonical_name"]: row for row in ensure_tax_control_accounts(company_key, conn=conn)}


def _tax_amount(base_amount, rate_percent):
    return round(float(base_amount or 0.0) * float(rate_percent or 0.0) / 100.0, 2)


def build_sales_tax_journal_lines(
    conn,
    company_key,
    *,
    receipt_account_name,
    receipt_account_type,
    amount,
    output_vat=0.0,
    nhil=0.0,
    getfund=0.0,
):
    net_amount = round(float(amount or 0.0), 2)
    vat_amount = round(float(output_vat or 0.0), 2)
    nhil_amount = round(float(nhil or 0.0), 2)
    getfund_amount = round(float(getfund or 0.0), 2)
    if net_amount <= 0:
        raise ValueError("Sales amount must be greater than 0.")
    tax_accounts = _tax_account_map(company_key, conn)
    total_receivable = round(net_amount + vat_amount + nhil_amount + getfund_amount, 2)
    journal_lines = [
        {
            "account_id": get_account_id(conn, receipt_account_name, receipt_account_type),
            "debit": total_receivable,
            "credit": 0,
        },
        {
            "account_id": get_account_id(conn, "Sales Revenue", "Income"),
            "debit": 0,
            "credit": net_amount,
        },
    ]
    if vat_amount > 0:
        journal_lines.append({"account_id": int(tax_accounts["VAT Payable"]["account_id"]), "debit": 0, "credit": vat_amount})
    if nhil_amount > 0:
        journal_lines.append({"account_id": int(tax_accounts["NHIL Payable"]["account_id"]), "debit": 0, "credit": nhil_amount})
    if getfund_amount > 0:
        journal_lines.append({"account_id": int(tax_accounts["GETFund Levy Payable"]["account_id"]), "debit": 0, "credit": getfund_amount})
    return journal_lines, {
        "net_amount": net_amount,
        "output_vat": vat_amount,
        "nhil": nhil_amount,
        "getfund": getfund_amount,
        "total_receivable": total_receivable,
    }


def _tax_account_journal_totals(conn, company_key, account_id):
    row = conn.execute(
        """
        SELECT COALESCE(SUM(jl.debit), 0) AS debit_total,
               COALESCE(SUM(jl.credit), 0) AS credit_total
        FROM journal_entries je
        JOIN journal_lines jl ON jl.entry_id = je.id
        WHERE je.company_key = ?
          AND jl.account_id = ?
          AND COALESCE(je.is_voided, 0) = 0
          AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """,
        (company_key, int(account_id)),
    ).fetchone()
    debit_total = round(float(row["debit_total"] or 0.0), 2) if row else 0.0
    credit_total = round(float(row["credit_total"] or 0.0), 2) if row else 0.0
    return debit_total, credit_total


def _tax_control_balance(conn, company_key, account_info):
    debit_total, credit_total = _tax_account_journal_totals(conn, company_key, int(account_info["account_id"]))
    account_type = str(account_info.get("account_type") or "").strip().title()
    if account_type == "Asset":
        balance = round(debit_total - credit_total, 2)
    else:
        balance = round(credit_total - debit_total, 2)
    return {
        "Account": account_info["resolved_name"],
        "Expected Type": account_info["account_type"],
        "Debit Total": debit_total,
        "Credit Total": credit_total,
        "Journal Balance": balance,
        "Status": account_info["status"],
    }


def post_transaction(description, lines, company_key=None, reference=None, created_by=None, entry_date=None, branch_id=None, conn=None):
    if not lines:
        raise ValueError("Transaction lines are required.")

    entry_date_iso = _resolve_entry_date(entry_date)
    owns_connection = conn is None
    conn = conn or get_connection()
    if conn is None:
        raise RuntimeError("Database connection unavailable for transaction posting.")
    if is_period_locked(company_key, entry_date_iso, conn=conn):
        raise ValueError(f"The accounting period for {entry_date_iso[:7]} is locked.")

    try:
        normalized_lines = []
        for line in lines:
            account_name = str(line.get("account_name") or line.get("name") or "").strip()
            category = _normalize_account_category(line.get("category") or line.get("type"))
            debit = round(float(line.get("debit") or 0), 2)
            credit = round(float(line.get("credit") or 0), 2)
            if not account_name or not category or (debit == 0 and credit == 0):
                continue
            account_id = _get_or_create_account(conn, account_name, category, line.get("parent_name"))
            normalized_lines.append({"account_id": account_id, "debit": debit, "credit": credit})
        entry_id = post_journal_entry(
            company_key=company_key,
            date=entry_date_iso,
            description=description,
            reference=reference,
            lines=normalized_lines,
            created_by=created_by,
                branch_id=branch_id,
                source_module="Operational Posting",
                source_table="journal_entries",
                manual_entry=True,
                conn=conn,
            )
        if owns_connection:
            conn.commit()
        return entry_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def create_journal_entry(description, lines, company_key=None, reference=None, entry_date=None, branch_id=None, conn=None):
    return post_transaction(
        description,
        lines,
        company_key=company_key,
        reference=reference,
        created_by=st.session_state.get("user", {}).get("role", "System"),
        entry_date=entry_date,
        branch_id=branch_id,
        conn=conn,
    )


def save_transaction(description, lines, company_key=None, reference=None, created_by=None, entry_date=None, branch_id=None, conn=None):
    return post_transaction(
        description,
        lines,
        company_key=company_key,
        reference=reference,
        created_by=created_by or st.session_state.get("user", {}).get("role", "System"),
        entry_date=entry_date,
        branch_id=branch_id,
        conn=conn,
    )


def show_journal_entries(company_key, role):
    st.header("🧾 General Journal")
    if not require_permission(
        role,
        "view_reports",
        action_label="view general journal",
        company_key=company_key,
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return
    can_post_manual_entries = user_has_permission(role, "post_accounting_document")

    branch_id = st.session_state.get("active_branch_id")
    branches = get_company_branches(company_key)
    if branches:
        branch_options = [("All Branches", None)] + [
            (f"{branch['branch_name']} ({branch['branch_type']})", branch['branch_id'])
            for branch in branches
        ]
        branch_labels = [label for label, _ in branch_options]
        if role == "Branch_Bookkeeper":
            branch_id = st.session_state.get("active_branch_id")
            selected_label = next((label for label, bid in branch_options if bid == branch_id), branch_labels[1] if len(branch_labels) > 1 else branch_labels[0])
            st.markdown(f"**Branch-restricted view:** {selected_label}")
            st.session_state.active_branch_id = branch_id
        else:
            selected_label = next((label for label, bid in branch_options if bid == branch_id), branch_labels[0])
            selected_index = branch_labels.index(selected_label)
            chosen_label = st.selectbox("Select Branch", branch_labels, index=selected_index, key=f"journal_branch_selector_{company_key}")
            branch_id = branch_options[branch_labels.index(chosen_label)][1]
            st.session_state.active_branch_id = branch_id
            if branch_id:
                st.info(f"Filtered to branch: {chosen_label}")
            else:
                st.info("Showing consolidated entries across all branches.")

    account_options = []
    chart_conn = None
    try:
        chart_conn = get_connection()
        account_rows = execute_portable_query(
            chart_conn,
            """
            SELECT COALESCE(account_code, '') AS account_code,
                   COALESCE(name, account_name) AS account_name
            FROM chart_of_accounts
            ORDER BY COALESCE(account_code, ''), COALESCE(name, account_name)
            """,
        ).fetchall()
        account_options = [
            f"{str(row_get(row, 'account_code', '')).strip()} - {str(row_get(row, 'account_name', '')).strip()}".strip(" -")
            for row in account_rows
            if str(row_get(row, "account_name", "") or "").strip()
        ]
    except Exception:
        account_options = []
    finally:
        if chart_conn:
            chart_conn.close()

    conn = None
    try:
        conn = get_connection()
        query = """
            SELECT je.date AS "Transaction Date",
                   COALESCE(c.code, c.account_code, '') AS "Account Code",
                   COALESCE(c.name, c.account_name) AS "Account",
                   je.description AS "Description",
                   COALESCE(je.approval_status, 'Posted') AS "Posting State",
                   jl.debit AS "Debit",
                   jl.credit AS "Credit",
                   je.reference AS "Reference",
                   je.created_by AS "Created By",
                   je.posted_by AS "Posted By",
                   je.posted_at AS "Posted At",
                   je.created_at AS "Created At"
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
        """
        params = [company_key]
        if branch_id:
            query += "\n            AND je.branch_id = ?"
            params.append(branch_id)
        query += "\n            ORDER BY date(je.date) DESC, je.id DESC"
        transactions_df = _portable_read_dataframe(conn, query, tuple(params))
    except Exception:
        transactions_df = pd.DataFrame(
            columns=[
                "Transaction Date",
                "Account",
                "Description",
                "Debit",
                "Credit",
                "Reference",
                "Created By",
                "Created At",
            ]
        )
    finally:
        if conn:
            conn.close()

    st.subheader("Journal Entries")
    st.warning("Posted journal entries cannot be edited directly. Use reversal or void workflows to correct accounting records.")
    if transactions_df.empty:
        st.info("No journal entries have been posted yet.")
    else:
        st.dataframe(format_currency_dataframe(transactions_df), use_container_width=True)

    # Initialize form state
    form_key = f"show_manual_journal_form_{company_key}"
    if form_key not in st.session_state:
        st.session_state[form_key] = False

    if can_post_manual_entries:
        if st.button("Add Manual Entry", key=f"btn_manual_journal_{company_key}"):
            st.session_state[form_key] = not st.session_state[form_key]
    else:
        st.caption("You can review journal entries, but you do not have permission to add manual entries.")

    if st.session_state.get(form_key, False):
        with st.form(f"manual_journal_entry_form_{company_key}"):
            col1, col2 = st.columns(2)
            with col1:
                entry_date = st.date_input(
                    "Transaction Date",
                    value=datetime.now().date(),
                    key=f"journal_entry_date_{company_key}"
                )
            with col2:
                account = st.selectbox(
                    "Account",
                    account_options if account_options else ["Suspense"],
                    key=f"journal_entry_account_{company_key}",
                )
            description = st.text_input(
                "Description",
                key=f"journal_entry_description_{company_key}"
            )
            branch_for_entry = branch_id
            if branches:
                branch_names = ["All Branches"] + [b["branch_name"] for b in branches]
                branch_choice = st.selectbox(
                    "Branch",
                    branch_names,
                    index=0 if branch_id is None else next((i + 1 for i, b in enumerate(branches) if b["branch_id"] == branch_id), 0),
                    key=f"journal_entry_branch_{company_key}",
                )
                if branch_choice != "All Branches":
                    branch_for_entry = next((b["branch_id"] for b in branches if b["branch_name"] == branch_choice), branch_id)
            debit_col, credit_col = st.columns(2)
            with debit_col:
                debit = st.number_input(
                    "Debit",
                    min_value=0.0,
                    step=0.01,
                    key=f"journal_entry_debit_{company_key}"
                )
            with credit_col:
                credit = st.number_input(
                    "Credit",
                    min_value=0.0,
                    step=0.01,
                    key=f"journal_entry_credit_{company_key}"
                )
            submitted = st.form_submit_button("Save Manual Entry")

            if submitted:
                if not require_permission(
                    role,
                    "post_accounting_document",
                    action_label="post accounting documents",
                    company_key=company_key,
                    branch_id=branch_for_entry,
                ):
                    if conn:
                        conn.close()
                    return
                selected_account = str(account or "").split(" - ", 1)[-1].strip()
                if not selected_account:
                    st.warning("Enter an account before saving the manual entry.")
                elif debit <= 0 and credit <= 0:
                    st.warning("Enter either a debit or a credit amount.")
                elif debit > 0 and credit > 0:
                    st.warning("Enter a debit or a credit amount for this manual line, not both.")
                else:
                    suspense_amount = float(debit or credit)
                    try:
                        conn = get_connection()
                        reference = f"JRN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        selected_account_id = get_account_id(conn, selected_account, "Expense" if debit > 0 else "Income")
                        suspense_account_id = get_account_id(conn, "Suspense", "Equity")
                        if debit > 0 and credit == 0:
                            journal_lines = [
                                {"account_id": selected_account_id, "debit": float(debit), "credit": 0},
                                {"account_id": suspense_account_id, "debit": 0, "credit": float(debit)},
                            ]
                        elif credit > 0 and debit == 0:
                            journal_lines = [
                                {"account_id": suspense_account_id, "debit": float(credit), "credit": 0},
                                {"account_id": selected_account_id, "debit": 0, "credit": float(credit)},
                            ]
                        else:
                            raise ValueError("Manual entry requires a valid one-sided amount.")
                        post_journal_entry(
                            company_key=company_key,
                            date=entry_date,
                            description=description.strip() or "Manual journal entry",
                            reference=reference,
                            lines=journal_lines,
                            created_by=role,
                            branch_id=branch_for_entry,
                            source_module="Manual Journal",
                            source_table="journal_entries",
                            conn=conn,
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Manual Journal Entry", "Journals", f"{selected_account} saved for {format_currency(suspense_amount)}", branch_id=branch_for_entry)
                        conn.close()
                        st.session_state[form_key] = False
                        st.success("Manual journal entry saved.")
                        st.rerun()
                    except Exception as exc:
                        if conn:
                            conn.rollback()
                            conn.close()
                        st.error(build_user_safe_error(exc, role))


def _inventory_offset_account(funding_source):
    normalized = str(funding_source or "").strip().lower()
    if normalized in {"cash", "bank", "mobile money"}:
        account_name = "Cash" if normalized == "cash" else ("Bank" if normalized == "bank" else "Mobile Money")
        return account_name, "Asset"
    return "Accounts Payable", "Liability"


def _voucher_posting_lines(conn, v_type, amount):
    normalized = str(v_type or "").strip().title()
    amount = float(amount or 0.0)
    if normalized in {"Sales", "Receipt"}:
        return [
            {"account_id": get_account_id(conn, "Cash", "Asset"), "debit": amount, "credit": 0},
            {"account_id": get_account_id(conn, "Sales Revenue", "Income"), "debit": 0, "credit": amount},
        ]
    if normalized == "Payment":
        return [
            {"account_id": get_account_id(conn, "Accounts Payable", "Liability"), "debit": amount, "credit": 0},
            {"account_id": get_account_id(conn, "Cash", "Asset"), "debit": 0, "credit": amount},
        ]
    if normalized == "Purchase":
        return [
            {"account_id": get_account_id(conn, "Inventory", "Asset"), "debit": amount, "credit": 0},
            {"account_id": get_account_id(conn, "Accounts Payable", "Liability"), "debit": 0, "credit": amount},
        ]
    if normalized == "Expense":
        return [
            {"account_id": get_account_id(conn, "Repairs and Maintenance", "Expense"), "debit": amount, "credit": 0},
            {"account_id": get_account_id(conn, "Cash", "Asset"), "debit": 0, "credit": amount},
        ]
    return [
        {"account_id": get_account_id(conn, "Suspense", "Equity"), "debit": amount, "credit": 0},
        {"account_id": get_account_id(conn, "Opening Balance Equity", "Equity"), "debit": 0, "credit": amount},
    ]


def _journal_reference_exists(conn, company_key, reference):
    if not reference:
        return False
    row = conn.execute(
        """
        SELECT 1
        FROM journal_entries
        WHERE company_key = ? AND reference = ?
        LIMIT 1
        """,
        (company_key, reference),
    ).fetchone()
    return bool(row)


def run_straight_line_depreciation(company_key, as_of_date=None, conn=None, created_by=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    if conn is None:
        raise RuntimeError("Database connection unavailable for depreciation run.")

    depreciation_date = pd.to_datetime(as_of_date or datetime.now().date()).date()
    month_end = (pd.Timestamp(depreciation_date).to_period("M").end_time).date()
    asset_rows = conn.execute(
        """
        SELECT id, asset_name, purchase_date, cost, opening_book_value, useful_life_years,
               residual_value, depreciation_rate, accumulated_depreciation, book_value,
               depreciation_method, last_depreciation_date, status
        FROM fixed_assets
        WHERE company_key = ? AND COALESCE(status, 'Active') = 'Active'
        """,
        (company_key,),
    ).fetchall()

    posted_entries = 0
    for asset in asset_rows:
        purchase_date_raw = asset["purchase_date"] or depreciation_date.isoformat()
        purchase_date = pd.to_datetime(purchase_date_raw, errors="coerce")
        if pd.isna(purchase_date):
            purchase_date = pd.Timestamp(depreciation_date)
        if purchase_date.date() > month_end:
            continue

        useful_life_years = float(asset["useful_life_years"] or 0)
        depreciation_rate = float(asset["depreciation_rate"] or 0)
        if useful_life_years <= 0 and depreciation_rate > 0:
            useful_life_years = round(100.0 / depreciation_rate, 6)
        useful_life_months = int(round(useful_life_years * 12))
        if useful_life_months <= 0:
            continue

        cost = float(asset["cost"] or 0)
        residual_value = float(asset["residual_value"] or 0)
        depreciable_base = max(cost - residual_value, 0.0)
        if depreciable_base <= 0:
            continue

        monthly_depreciation = round(depreciable_base / useful_life_months, 2)
        if monthly_depreciation <= 0:
            continue

        last_dep = pd.to_datetime(asset["last_depreciation_date"], errors="coerce")
        period_start = pd.Timestamp(purchase_date.date()).replace(day=1)
        if not pd.isna(last_dep):
            period_start = (last_dep + pd.offsets.MonthBegin(1)).normalize()
        current_period = pd.Timestamp(month_end).replace(day=1)

        while period_start <= current_period:
            period_label = period_start.strftime("%Y%m")
            reference = f"DEPR-{int(asset['id'])}-{period_label}"
            if _journal_reference_exists(conn, company_key, reference):
                period_start = (period_start + pd.offsets.MonthBegin(1)).normalize()
                continue

            accumulated = float(asset["accumulated_depreciation"] or 0)
            remaining = max(depreciable_base - accumulated, 0.0)
            amount = round(min(monthly_depreciation, remaining), 2)
            if amount <= 0:
                break

            create_journal_entry(
                f"Monthly depreciation - {asset['asset_name']}",
                [
                    {"account_name": "Depreciation Expense", "category": "Expense", "debit": amount, "credit": 0},
                    {"account_name": "Accumulated Depreciation", "category": "Asset", "debit": 0, "credit": amount},
                ],
                company_key=company_key,
                reference=reference,
                entry_date=period_start.date(),
                conn=conn,
            )
            accumulated += amount
            opening_book = float(asset["opening_book_value"] or cost)
            book_value = max(opening_book - accumulated, residual_value)
            conn.execute(
                """
                UPDATE fixed_assets
                SET accumulated_depreciation = ?,
                    book_value = ?,
                    last_depreciation_date = ?
                WHERE id = ? AND company_key = ?
                """,
                (accumulated, book_value, period_start.date().isoformat(), int(asset["id"]), company_key),
            )
            asset = dict(asset)
            asset["accumulated_depreciation"] = accumulated
            posted_entries += 1
            period_start = (period_start + pd.offsets.MonthBegin(1)).normalize()

    if owns_connection:
        conn.commit()
        conn.close()
    return posted_entries


def _ensure_counterparty(conn, company_key, party_name, party_type, city_region, tx_date, balance_delta):
    existing = conn.execute(
        """
        SELECT id, balance
        FROM counterparties
        WHERE company_key = ? AND party_name = ? AND party_type = ?
        """,
        (company_key, party_name, party_type),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE counterparties
            SET city_region = COALESCE(NULLIF(?, ''), city_region),
                last_transaction = ?,
                balance = COALESCE(balance, 0) + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (city_region, tx_date, balance_delta, existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO counterparties
                (company_key, party_name, party_type, city_region, last_transaction, balance)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (company_key, party_name, party_type, city_region, tx_date, balance_delta),
        )


def _get_or_create_party(conn, table_name, company_key, party_name):
    existing = conn.execute(
        f"SELECT id FROM {table_name} WHERE company_key = ? AND name = ?",
        (company_key, party_name),
    ).fetchone()
    if existing:
        return int(existing["id"])
    cursor = conn.execute(
        ensure_insert_sql_returning(
            f"INSERT INTO {table_name} (company_key, name, currency) VALUES (?, ?, 'GHS')"
        ),
        (company_key, party_name),
    )
    return get_inserted_id(cursor)


def _register_customer(conn, company_key, name, phone="", email="", branch_id=None):
    existing = conn.execute(
        """
        SELECT id, customer_id, name, phone, email, current_balance
        FROM customers
        WHERE company_key = ? AND name = ?
        """,
        (company_key, name.strip()),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE customers
            SET phone = COALESCE(NULLIF(?, ''), phone),
                email = COALESCE(NULLIF(?, ''), email)
            WHERE id = ? AND company_key = ?
            """,
            (phone.strip(), email.strip(), int(existing["id"]), company_key),
        )
        return int(existing["id"])

    cursor = conn.execute(
        ensure_insert_sql_returning(
            """
            INSERT INTO customers (company_key, name, phone, email, customer_id, current_balance, currency)
            VALUES (?, ?, ?, ?, NULL, 0, 'GHS')
            """
        ),
        (company_key, name.strip(), phone.strip(), email.strip()),
    )
    customer_row_id = get_inserted_id(cursor)
    conn.execute(
        "UPDATE customers SET customer_id = COALESCE(NULLIF(customer_id, ''), ?) WHERE id = ? AND company_key = ?",
        (f"CUST-{customer_row_id:06d}", customer_row_id, company_key),
    )
    return customer_row_id


def _get_invoice_inventory_items(conn, company_key):
    rows = conn.execute(
        """
        SELECT id, item_name, item_code, barcode, qty, price, cost_price
        FROM inventory
        WHERE company_key = ?
          AND COALESCE(is_active, 1) = 1
        ORDER BY item_name
        """,
        (company_key,),
    ).fetchall()
    return [dict(row) for row in rows]


def render_invoice_line_editor(company_key, editor_key_prefix, conn):
    inventory_rows = _get_invoice_inventory_items(conn, company_key)
    inventory_options = {
        "{name} | Price {price} | Stock {qty:,.2f}".format(
            name=str(row["item_name"] or "").strip(),
            price=format_currency(float(row["price"] or 0.0)),
            qty=float(row["qty"] or 0.0),
        ): row
        for row in inventory_rows
    }
    line_count = int(
        st.number_input(
            "Invoice Line Count",
            min_value=0,
            max_value=5,
            value=int(st.session_state.get(f"{editor_key_prefix}_line_count", 1) or 1),
            step=1,
            key=f"{editor_key_prefix}_line_count",
        )
    )
    st.caption("Optional: add stock-linked lines for inventory invoices. Manual/non-stock lines remain revenue-only.")
    invoice_items = []
    for line_index in range(line_count):
        st.markdown(f"Line {line_index + 1}")
        row_col1, row_col2, row_col3 = st.columns(3)
        line_mode = row_col1.selectbox(
            "Line Type",
            ["Manual / Non-stock", "Stock Item"],
            key=f"{editor_key_prefix}_mode_{line_index}",
        )
        quantity = float(
            row_col2.number_input(
                "Quantity",
                min_value=0.0,
                value=float(st.session_state.get(f"{editor_key_prefix}_qty_{line_index}", 1.0) or 1.0),
                step=1.0,
                key=f"{editor_key_prefix}_qty_{line_index}",
            )
        )
        if line_mode == "Stock Item":
            selected_label = row_col3.selectbox(
                "Inventory Item",
                [""] + list(inventory_options.keys()),
                key=f"{editor_key_prefix}_stock_{line_index}",
            )
            selected_row = inventory_options.get(selected_label)
            unit_price = float(
                st.number_input(
                    "Unit Price",
                    min_value=0.0,
                    value=float(selected_row["price"] or 0.0) if selected_row else 0.0,
                    step=0.01,
                    key=f"{editor_key_prefix}_price_{line_index}",
                )
            )
            if selected_row and quantity > 0:
                invoice_items.append(
                    {
                        "inventory_item_id": int(selected_row["id"]),
                        "item_name": str(selected_row["item_name"] or "").strip(),
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "line_total": round(quantity * unit_price, 2),
                        "cost_price": float(selected_row.get("cost_price") or 0.0),
                    }
                )
        else:
            item_name = row_col3.text_input("Item Name", key=f"{editor_key_prefix}_manual_{line_index}").strip()
            unit_price = float(
                st.number_input(
                    "Unit Price",
                    min_value=0.0,
                    value=float(st.session_state.get(f"{editor_key_prefix}_price_{line_index}", 0.0) or 0.0),
                    step=0.01,
                    key=f"{editor_key_prefix}_price_{line_index}",
                )
            )
            if item_name and quantity > 0:
                invoice_items.append(
                    {
                        "inventory_item_id": None,
                        "item_name": item_name,
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "line_total": round(quantity * unit_price, 2),
                        "cost_price": 0.0,
                    }
                )
    invoice_total = round(sum(float(item.get("line_total") or 0.0) for item in invoice_items), 2)
    if invoice_items:
        st.caption(f"Invoice items total: {format_currency(invoice_total)}")
    return invoice_items, invoice_total


def save_invoice_lines(conn, invoice_id, invoice_items):
    conn.execute("DELETE FROM invoice_lines WHERE invoice_id = ?", (int(invoice_id),))
    for item in invoice_items:
        conn.execute(
            """
            INSERT INTO invoice_lines (
                invoice_id, inventory_item_id, item_name, quantity, unit_price, line_total, cost_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(invoice_id),
                int(item["inventory_item_id"]) if item.get("inventory_item_id") is not None else None,
                str(item.get("item_name") or "").strip(),
                float(item.get("quantity") or 0.0),
                float(item.get("unit_price") or 0.0),
                float(item.get("line_total") or 0.0),
                float(item.get("cost_price") or 0.0),
            ),
        )


def _inventory_has_average_cost(conn):
    return "average_cost" in {column["name"] for column in list_columns(conn, "inventory")}


def apply_invoice_stock_effects(
    conn,
    *,
    company_key,
    invoice_reference,
    invoice_items,
    role,
    branch_id=None,
):
    stock_linked_items = [item for item in (invoice_items or []) if item.get("inventory_item_id") is not None]
    if not stock_linked_items:
        return {"invoice_items": invoice_items or [], "cogs_total": 0.0, "stock_deduction_applied": False}

    average_cost_available = _inventory_has_average_cost(conn)
    enriched_items = []
    cogs_total = 0.0
    for item in stock_linked_items:
        inventory_row = conn.execute(
            """
            SELECT id, item_name, qty, cost_price {average_cost_clause}
            FROM inventory
            WHERE id = ? AND company_key = ?
            LIMIT 1
            """.format(average_cost_clause=", average_cost" if average_cost_available else ""),
            (int(item["inventory_item_id"]), company_key),
        ).fetchone()
        if not inventory_row:
            raise ValueError(f"Inventory item for {item['item_name']} could not be found.")
        quantity_sold = round(float(item.get("quantity") or 0.0), 4)
        if quantity_sold <= 0:
            continue
        available_qty = float(inventory_row["qty"] or 0.0)
        if quantity_sold > available_qty:
            raise ValueError(f"Insufficient stock for invoice item {inventory_row['item_name']}.")
        unit_cost = float(inventory_row["cost_price"] or 0.0)
        if unit_cost <= 0 and average_cost_available:
            unit_cost = float(inventory_row["average_cost"] or 0.0)
        if unit_cost <= 0:
            unit_cost = float(item.get("cost_price") or 0.0)
        total_cost = round(quantity_sold * unit_cost, 2)
        new_qty = round(available_qty - quantity_sold, 4)
        conn.execute(
            "UPDATE inventory SET qty = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND company_key = ?",
            (new_qty, int(inventory_row["id"]), company_key),
        )
        conn.execute(
            """
            INSERT INTO stock_movements (
                company_key, branch_id, inventory_item_id, item_name, movement_type,
                quantity, reason, previous_qty, new_qty, created_by, created_at, reference
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
            (
                company_key,
                branch_id,
                int(inventory_row["id"]),
                str(inventory_row["item_name"] or item["item_name"]),
                "Invoice Sale",
                quantity_sold,
                f"Invoice sale {invoice_reference}",
                available_qty,
                new_qty,
                role,
                invoice_reference,
            ),
        )
        enriched_item = dict(item)
        enriched_item["cost_price"] = unit_cost
        enriched_item["inventory_total_cost"] = total_cost
        enriched_items.append(enriched_item)
        if total_cost > 0:
            cogs_total = round(cogs_total + total_cost, 2)

    non_stock_items = [dict(item) for item in (invoice_items or []) if item.get("inventory_item_id") is None]
    return {
        "invoice_items": non_stock_items + enriched_items,
        "cogs_total": cogs_total,
        "stock_deduction_applied": bool(stock_linked_items),
    }


def _record_customer_ledger_transaction(
    conn,
    company_key,
    customer_row_id,
    transaction_type,
    amount,
    description,
    created_by,
    branch_id=None,
    reference=None,
    transaction_date=None,
    post_to_gl=False,
    source_module="Accounts Receivable",
):
    transaction_type = str(transaction_type or "").strip().title()
    if transaction_type not in {"Debit", "Credit"}:
        raise ValueError("Transaction type must be Debit or Credit.")

    amount = float(amount or 0.0)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    tx_date = transaction_date.isoformat() if hasattr(transaction_date, "isoformat") else (transaction_date or datetime.now().date().isoformat())
    customer = conn.execute(
        "SELECT id, name, current_balance FROM customers WHERE id = ? AND company_key = ?",
        (int(customer_row_id), company_key),
    ).fetchone()
    if not customer:
        raise ValueError("Selected customer could not be found.")

    current_balance = float(customer["current_balance"] or 0.0)
    if post_to_gl:
        ar_account_id = get_account_id(conn, "Accounts Receivable", "Asset")
        contra_account_id = get_account_id(conn, "Sales Revenue", "Income") if transaction_type == "Debit" else get_account_id(conn, "Cash", "Asset")
        lines = (
            [
                {"account_id": ar_account_id, "debit": amount, "credit": 0},
                {"account_id": contra_account_id, "debit": 0, "credit": amount},
            ]
            if transaction_type == "Debit"
            else [
                {"account_id": contra_account_id, "debit": amount, "credit": 0},
                {"account_id": ar_account_id, "debit": 0, "credit": amount},
            ]
        )
        post_journal_entry(
            company_key=company_key,
            date=tx_date,
            description=description,
            reference=reference,
            lines=lines,
            created_by=created_by,
            branch_id=branch_id,
            customer_id=int(customer_row_id),
            source_module=source_module,
            source_table="customer_transactions",
            conn=conn,
        )

    conn.execute(
        """
        INSERT INTO customer_transactions (
            company_key, customer_id, branch_id, transaction_type, amount,
            description, reference, transaction_date, created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_key,
            int(customer_row_id),
            branch_id,
            transaction_type,
            amount,
            description,
            reference,
            tx_date,
            created_by,
        ),
    )
    new_balance = get_customer_balance(company_key, int(customer_row_id), as_of_date=tx_date, conn=conn)
    previous_balance = round(new_balance - (amount if transaction_type == "Debit" else -amount), 2)
    return {
        "customer_name": customer["name"],
        "previous_balance": previous_balance,
        "new_balance": new_balance,
        "delta": amount if transaction_type == "Debit" else -amount,
        "transaction_date": tx_date,
    }


def show_debtors_by_city_report(company_key):
    st.subheader("Debtors by City")
    conn = None
    try:
        conn = get_connection()
        city_rows = conn.execute(
            """
            SELECT DISTINCT COALESCE(NULLIF(city_region, ''), 'Unassigned') AS city_region
            FROM counterparties
            WHERE company_key = ? AND party_type = 'Customer'
            ORDER BY city_region
            """,
            (company_key,),
        ).fetchall()
        city_options = ["All Cities"] + [row[0] for row in city_rows]
        selected_city = st.selectbox("Filter by City / Region", city_options, key=f"debtor_city_{company_key}")

        customer_balance_map = {row["name"]: float(row["balance"] or 0.0) for row in get_customer_balances(company_key, conn=conn)}
        query = """
            SELECT party_name, last_transaction, COALESCE(NULLIF(city_region, ''), 'Unassigned') AS city_region
            FROM counterparties
            WHERE company_key = ? AND party_type = 'Customer'
        """
        params = [company_key]
        if selected_city != "All Cities":
            query += " AND COALESCE(NULLIF(city_region, ''), 'Unassigned') = ?"
            params.append(selected_city)
        query += " ORDER BY city_region, party_name"

        debtors = [
            (row["party_name"], row["last_transaction"], customer_balance_map.get(row["party_name"], 0.0), row["city_region"])
            for row in conn.execute(query, tuple(params)).fetchall()
            if customer_balance_map.get(row["party_name"], 0.0) > 0
        ]
        if not debtors:
            st.info("No debtor balances are available for the selected city.")
            return

        report_df = pd.DataFrame(
            debtors,
            columns=["Customer Name", "Last Transaction", "Balance", "City / Region"],
        )
        road_df = report_df[["Customer Name", "Last Transaction", "Balance"]].copy()
        road_df["Balance"] = road_df["Balance"].map(lambda value: f"GHs {float(value):,.2f}")

        st.dataframe(format_currency_dataframe(report_df), use_container_width=True)
        st.markdown("Road Summary")
        st.dataframe(format_currency_dataframe(road_df), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
    finally:
        if conn:
            conn.close()


def init_db():
    from database import startup_database
    return startup_database()


def log_system_event(level, module_name, message):
    conn = get_connection()
    if conn is None:
        return
    try:
        if not is_postgres_backend():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    level TEXT,
                    module_name TEXT,
                    message TEXT
                )
                """
            )
        elif not db_table_exists(conn, "system_logs"):
            return
        execute_portable_write(
            conn,
            "INSERT INTO system_logs (timestamp, level, module_name, message) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), level, module_name, message),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("System event logging failed for module=%s level=%s: %s", module_name, level, sanitize_error_message(exc))
    finally:
        if conn:
            conn.close()


def get_excel_bin(df):
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Export")
            worksheet = writer.sheets.get("Export")
            if worksheet is not None:
                worksheet.set_footer(PRINTABLE_DOCUMENT_FOOTER)
        return output.getvalue()
    except Exception:
        return b""


def _build_receipt(receipt_data):
    lines = [
        str(receipt_data.get("company_name") or ""),
        "SALE COMPLETED SUCCESSFULLY",
    ]
    if receipt_data.get("branch_name"):
        lines.append(f"Branch: {receipt_data['branch_name']}")
    lines.extend(
        [
            f"Receipt No: {receipt_data.get('receipt_number') or 'N/A'}",
            f"Date: {receipt_data.get('sale_datetime') or ''}",
            f"Cashier: {receipt_data.get('cashier') or ''}",
            f"Payment: {receipt_data.get('payment_method') or ''}",
            "-" * 40,
            "Item                     Qty   Unit    Total",
            "-" * 40,
        ]
    )
    for item in receipt_data.get("items", []):
        lines.append(
            f"{str(item.get('name') or '')[:20]:<20} {int(item.get('qty') or 0):>3} {float(item.get('price') or 0.0):>6.2f} {float(item.get('line_total') or 0.0):>8.2f}"
        )
    lines.extend(
        [
            "-" * 40,
            f"Subtotal: {format_currency(float(receipt_data.get('subtotal') or 0.0))}",
            f"Discount: {format_currency(float(receipt_data.get('discount_total') or 0.0))}",
            f"Tax: {format_currency(float(receipt_data.get('tax_total') or 0.0))}",
            f"Grand Total: {format_currency(float(receipt_data.get('grand_total') or 0.0))}",
        ]
    )
    if receipt_data.get("discount_approved_by"):
        lines.append(f"Discount Approved By: {receipt_data['discount_approved_by']}")
    if receipt_data.get("payment_method") == "Cash":
        lines.append(f"Amount Tendered: {format_currency(float(receipt_data.get('amount_tendered') or 0.0))}")
        lines.append(f"Change Due: {format_currency(float(receipt_data.get('change_due') or 0.0))}")
    elif receipt_data.get("payment_reference"):
        lines.append(f"Reference: {receipt_data['payment_reference']}")
    lines.append("-" * 40)
    lines.append(PRINTABLE_DOCUMENT_FOOTER)
    return "\n".join(lines)


def _build_receipt_html(receipt_data):
    is_preview = bool(receipt_data.get("is_preview"))
    rows = []
    for item in receipt_data.get("items", []):
        item_name = html.escape(str(item.get("name") or ""))
        rows.append(
            "<tr>"
            f"<td style=\"padding:0.25rem 0.1rem;border-bottom:1px dashed #bbb;\">{item_name}</td>"
            f"<td style=\"padding:0.25rem 0.1rem;border-bottom:1px dashed #bbb;text-align:center;\">{int(item.get('qty') or 0)}</td>"
            f"<td style=\"padding:0.25rem 0.1rem;border-bottom:1px dashed #bbb;text-align:right;\">{html.escape(format_currency(float(item.get('price') or 0.0)))}</td>"
            f"<td style=\"padding:0.25rem 0.1rem;border-bottom:1px dashed #bbb;text-align:right;\">{html.escape(format_currency(float(item.get('line_total') or 0.0)))}</td>"
            "</tr>"
        )
    payment_reference_html = ""
    if receipt_data.get("payment_reference"):
        payment_reference_html = (
            f"<div style=\"font-size:0.75rem;color:#444;\">Reference: {html.escape(str(receipt_data['payment_reference']))}</div>"
        )
    discount_approval_html = ""
    if receipt_data.get("discount_approved_by"):
        discount_approval_html = (
            f"<div style=\"font-size:0.75rem;color:#444;\">Discount Approved By: {html.escape(str(receipt_data['discount_approved_by']))}</div>"
        )
    amount_tendered_html = ""
    change_due_html = ""
    if receipt_data.get("payment_method") == "Cash":
        amount_tendered_html = (
            f"<div style=\"display:flex;justify-content:space-between;\"><span>Amount Tendered</span><strong>{html.escape(format_currency(float(receipt_data.get('amount_tendered') or 0.0)))}</strong></div>"
        )
        change_due_html = (
            f"<div style=\"display:flex;justify-content:space-between;\"><span>Change Due</span><strong>{html.escape(format_currency(float(receipt_data.get('change_due') or 0.0)))}</strong></div>"
        )
    preview_banner_html = ""
    if is_preview:
        preview_banner_html = (
            "<div class=\"receipt-preview-banner\">SALE PREVIEW — NOT FINAL RECEIPT</div>"
        )
    company_name = html.escape(str(receipt_data.get("company_name") or ""))
    branch_name = html.escape(str(receipt_data.get("branch_name") or "Main Branch"))
    receipt_number = html.escape(str(receipt_data.get("receipt_number") or ("SALE PREVIEW" if is_preview else "N/A")))
    sale_datetime = html.escape(str(receipt_data.get("sale_datetime") or ""))
    cashier = html.escape(str(receipt_data.get("cashier") or ""))
    payment_method = html.escape(str(receipt_data.get("payment_method") or ""))
    footer = html.escape(PRINTABLE_DOCUMENT_FOOTER)
    receipt_heading = "Sale Preview" if is_preview else "Receipt"
    return (
        "<div class=\"receipt-preview printable receipt-thermal\" "
        "style=\"color:#111;max-width:280px;width:100%;margin:0 auto;"
        "font-family:'Courier New',Consolas,monospace;font-size:12px;line-height:1.35;\">"
        f"{preview_banner_html}"
        "<div style=\"text-align:center;margin-bottom:0.6rem;\">"
        f"<h3 style=\"margin:0;font-size:14px;\">{company_name}</h3>"
        f"<div style=\"font-size:11px;color:#555;\">{branch_name}</div>"
        f"<div style=\"font-size:11px;margin-top:0.25rem;\">{receipt_heading}: {receipt_number}</div>"
        f"<div style=\"font-size:11px;\">Date: {sale_datetime}</div>"
        f"<div style=\"font-size:11px;\">Cashier: {cashier}</div>"
        "</div>"
        "<table style=\"width:100%;border-collapse:collapse;margin-bottom:0.6rem;font-size:11px;\">"
        "<thead><tr>"
        "<th style=\"text-align:left;padding:0.25rem 0.1rem;border-bottom:2px solid #333;\">Item</th>"
        "<th style=\"text-align:center;padding:0.25rem 0.1rem;border-bottom:2px solid #333;\">Qty</th>"
        "<th style=\"text-align:right;padding:0.25rem 0.1rem;border-bottom:2px solid #333;\">Unit</th>"
        "<th style=\"text-align:right;padding:0.25rem 0.1rem;border-bottom:2px solid #333;\">Total</th>"
        "</tr></thead><tbody>"
        f"{''.join(rows)}"
        "</tbody></table>"
        "<div style=\"border-top:1px dashed #999;padding-top:0.5rem;font-size:11px;\">"
        f"<div style=\"display:flex;justify-content:space-between;\"><span>Subtotal</span><strong>{html.escape(format_currency(float(receipt_data.get('subtotal') or 0.0)))}</strong></div>"
        f"<div style=\"display:flex;justify-content:space-between;\"><span>Discount</span><strong>{html.escape(format_currency(float(receipt_data.get('discount_total') or 0.0)))}</strong></div>"
        f"<div style=\"display:flex;justify-content:space-between;\"><span>Tax</span><strong>{html.escape(format_currency(float(receipt_data.get('tax_total') or 0.0)))}</strong></div>"
        f"<div style=\"display:flex;justify-content:space-between;font-size:13px;margin-top:0.3rem;\"><span>Grand Total</span><strong>{html.escape(format_currency(float(receipt_data.get('grand_total') or 0.0)))}</strong></div>"
        f"<div style=\"margin-top:0.4rem;font-size:10px;\">Payment Method: {payment_method}</div>"
        f"{discount_approval_html}{payment_reference_html}{amount_tendered_html}{change_due_html}"
        "</div>"
        f"<div style=\"margin-top:0.65rem;font-size:10px;color:#555;text-align:center;\">{footer}</div>"
        "</div>"
    )


def _build_pos_live_receipt_data(company_key, company_label, branch_label, role):
    """Build draft receipt payload from the active cart (no sale posting)."""
    cart = st.session_state.get(f"pos_cart_{company_key}", [])
    cart_summary = _get_pos_cart_summary(company_key)
    preview_items = []
    for line in cart:
        _recalculate_pos_line(line)
        preview_items.append(
            {
                "name": str(line.get("name") or line.get("item_name") or ""),
                "qty": int(line.get("qty") or 0),
                "price": float(line.get("price") or 0.0),
                "line_total": float(line.get("line_total") or 0.0),
            }
        )
    preview_payment_method = str(st.session_state.get(f"pos_payment_method_{company_key}") or "Pending")
    preview_cash_tendered = float(st.session_state.get(f"pos_cash_tendered_{company_key}") or cart_summary.get("grand_total") or 0.0)
    preview_payment_reference = str(st.session_state.get(f"pos_payment_reference_{company_key}") or "").strip()
    return {
        "company_key": company_key,
        "company_name": company_label,
        "branch_name": branch_label,
        "receipt_number": "SALE PREVIEW",
        "sale_reference": "SALE PREVIEW",
        "sale_date": datetime.now().date().isoformat(),
        "sale_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cashier": _get_pos_cashier_identity(role),
        "payment_method": preview_payment_method,
        "payment_reference": preview_payment_reference,
        "subtotal": float(cart_summary.get("subtotal") or 0.0),
        "discount_total": float(cart_summary.get("discount_total") or 0.0),
        "tax_total": float(cart_summary.get("tax_total") or 0.0),
        "grand_total": float(cart_summary.get("grand_total") or 0.0),
        "amount_tendered": preview_cash_tendered if preview_payment_method == "Cash" else None,
        "change_due": max(preview_cash_tendered - float(cart_summary.get("grand_total") or 0.0), 0.0)
        if preview_payment_method == "Cash"
        else 0.0,
        "items": preview_items,
        "is_preview": True,
    }


def _render_pos_receipt_html_panel(receipt_html_fragment, variant="final", height=500):
    fragment = str(receipt_html_fragment or "").strip()
    shell_class = "pos-receipt-shell-live" if variant == "live" else "pos-receipt-shell-final"
    components.html(
        f'<div class="pos-receipt-shell {shell_class}">{fragment}</div>',
        height=height,
        scrolling=True,
    )


def _build_pos_receipt_print_document(receipt_html_fragment):
    body = str(receipt_html_fragment or "").strip()
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\">"
        "<title>POS Receipt</title>"
        "<style>"
        "body{margin:8px;font-family:'Courier New',Consolas,monospace;font-size:12px;}"
        ".receipt-preview,.receipt-thermal{max-width:280px;width:100%;margin:0 auto;}"
        ".receipt-preview table{font-size:11px;}"
        "@media print{body{margin:0;}}"
        "</style>"
        "</head><body>"
        f"{body}"
        "<script>window.onload=function(){try{window.focus();window.print();}catch(e){}};</script>"
        "</body></html>"
    )


def _fetch_pos_receipt_data(conn, *, company_key, sale_id, branch_id=None, cashier=None):
    """
    Fetch a POS sale from the additive POS tables and rebuild a receipt_data dict compatible with:
    - _build_receipt()
    - _build_receipt_html()

    Phase 2E limitation: payment_reference and discount_approved_by may be unavailable and are omitted.
    """
    ensure_pos_sales_schema(conn)
    params = [company_key, int(sale_id)]
    query = """
        SELECT *
        FROM pos_sales
        WHERE company_key = ?
          AND id = ?
    """
    if branch_id:
        query += " AND COALESCE(branch_id, '') = ?"
        params.append(str(branch_id))
    if cashier:
        query += " AND COALESCE(cashier, '') = ?"
        params.append(str(cashier))
    query += " LIMIT 1"
    sale_row = conn.execute(query, tuple(params)).fetchone()
    if not sale_row:
        return None

    sale = dict(sale_row)
    company_row = conn.execute(
        "SELECT name FROM companies WHERE key = ? LIMIT 1",
        (company_key,),
    ).fetchone()
    company_name = str(company_row["name"] if company_row and "name" in company_row.keys() else "")

    branch_name = ""
    normalized_branch_id = str(sale.get("branch_id") or "").strip()
    if normalized_branch_id:
        branch_row = conn.execute(
            "SELECT branch_name FROM branches WHERE company_key = ? AND branch_id = ? LIMIT 1",
            (company_key, normalized_branch_id),
        ).fetchone()
        if branch_row and "branch_name" in branch_row.keys():
            branch_name = str(branch_row["branch_name"] or "")

    line_rows = conn.execute(
        """
        SELECT item_name, qty_sold, unit_price, line_total
        FROM pos_sale_lines
        WHERE company_key = ?
          AND pos_sale_id = ?
        ORDER BY id ASC
        """,
        (company_key, int(sale["id"])),
    ).fetchall()

    items = [
        {
            "name": str(row["item_name"] or ""),
            "qty": int(float(row["qty_sold"] or 0.0)),
            "price": float(row["unit_price"] or 0.0),
            "line_total": float(row["line_total"] or 0.0),
        }
        for row in line_rows
    ]

    receipt_number = str(sale.get("receipt_number") or sale.get("sale_reference") or "")
    return {
        "company_key": company_key,
        "company_name": company_name,
        "branch_name": branch_name,
        "receipt_number": receipt_number,
        "sale_reference": str(sale.get("sale_reference") or receipt_number),
        "sale_date": str(sale.get("sale_date") or ""),
        "sale_datetime": str(sale.get("sale_datetime") or ""),
        "cashier": str(sale.get("cashier") or ""),
        "payment_method": str(sale.get("payment_method") or ""),
        "subtotal": float(sale.get("subtotal") or 0.0),
        "discount_total": float(sale.get("discount_total") or 0.0),
        "tax_total": float(sale.get("tax_total") or 0.0),
        "grand_total": float(sale.get("grand_total") or 0.0),
        "amount_tendered": float(sale.get("amount_tendered") or 0.0),
        "change_due": float(sale.get("change_due") or 0.0),
        "items": items,
    }


def _get_pos_cashier_identity(role):
    current_user = st.session_state.get("user", {}) if isinstance(st.session_state.get("user", {}), dict) else {}
    return (
        str(current_user.get("role") or role or "").strip()
        or str(current_user.get("login_key") or "").strip()
        or str(current_user.get("full_name") or "").strip()
        or "Unknown"
    )


def _get_pos_discount_authority(role, subtotal, line_discount_total, cart_discount_total):
    total_discount = round(float(line_discount_total or 0.0) + float(cart_discount_total or 0.0), 2)
    subtotal = max(float(subtotal or 0.0), 0.0)
    discount_percent = (total_discount / subtotal * 100.0) if subtotal > 0 else 0.0
    requires_approval = (
        total_discount > POS_DISCOUNT_APPROVAL_AMOUNT_THRESHOLD
        or discount_percent > POS_DISCOUNT_APPROVAL_PERCENT_THRESHOLD
    )
    can_apply = user_has_permission(role, "apply_pos_discount") or user_has_permission(role, "approve_pos_discount")
    can_approve = user_has_permission(role, "approve_pos_discount")
    return {
        "total_discount": total_discount,
        "discount_percent": round(discount_percent, 2),
        "requires_approval": requires_approval,
        "can_apply": can_apply,
        "can_approve": can_approve,
        "approved": (not requires_approval and can_apply) or can_approve or total_discount <= 0,
    }


def _get_pos_discount_approval_state(company_key):
    return st.session_state.setdefault(
        f"pos_discount_approval_{company_key}",
        {
            "approved": False,
            "approver_identifier": "",
            "approver_name": "",
            "reason": "",
            "discount_amount": 0.0,
            "cart_signature": "",
            "approved_at": "",
        },
    )


def _clear_pos_discount_approval_state(company_key):
    st.session_state[f"pos_discount_approval_{company_key}"] = {
        "approved": False,
        "approver_identifier": "",
        "approver_name": "",
        "reason": "",
        "discount_amount": 0.0,
        "cart_signature": "",
        "approved_at": "",
    }


def _get_pos_cart_signature(company_key):
    cart = st.session_state.setdefault(f"pos_cart_{company_key}", [])
    discount_state = _get_pos_cart_discount_state(company_key)
    normalized_lines = []
    for line in cart:
        _recalculate_pos_line(line)
        normalized_lines.append(
            {
                "inventory_item_id": line.get("inventory_item_id"),
                "item_id": line.get("item_id"),
                "name": str(line.get("item_name") or line.get("name") or ""),
                "item_code": str(line.get("item_code") or ""),
                "barcode": str(line.get("barcode") or ""),
                "qty": int(line.get("qty") or 0),
                "price": round(float(line.get("price") or 0.0), 2),
                "line_discount_type": str(line.get("line_discount_type") or "amount"),
                "line_discount_value": round(float(line.get("line_discount_value", line.get("line_discount") or 0.0) or 0.0), 2),
                "tax_rate": round(float(line.get("tax_rate") or 0.0), 4),
                "is_manual": bool(line.get("is_manual")),
            }
        )
    payload = {
        "cart": normalized_lines,
        "cart_discount_type": str(discount_state.get("type") or "amount"),
        "cart_discount_value": round(float(discount_state.get("value") or 0.0), 2),
    }
    return json.dumps(payload, sort_keys=True)


def _generate_suspended_sale_reference():
    return f"SUS-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def _serialize_pos_cart_payload(company_key, cashier, note=""):
    cart = st.session_state.setdefault(f"pos_cart_{company_key}", [])
    discount_state = dict(_get_pos_cart_discount_state(company_key))
    return json.dumps(
        {
            "cart": cart,
            "discount_state": discount_state,
            "cashier": cashier,
            "note": note,
            "sale_date": str(st.session_state.get(f"pos_sale_date_{company_key}") or datetime.now().date()),
        }
    )


def _restore_pos_cart_payload(company_key, payload_json, conn=None):
    payload = json.loads(str(payload_json or "{}") or "{}")
    restored_cart = payload.get("cart") or []
    for line in restored_cart:
        line.setdefault("line_discount_type", "amount")
        line.setdefault("line_discount_value", float(line.get("line_discount") or 0.0))
        _recalculate_pos_line(line)
    if conn is not None:
        restored_cart, adjustment_messages = _revalidate_pos_cart_inventory(conn, company_key, restored_cart)
        if adjustment_messages:
            payload["revalidation_messages"] = adjustment_messages
    st.session_state[f"pos_cart_{company_key}"] = restored_cart
    discount_state = payload.get("discount_state") or {"type": "amount", "value": 0.0, "computed": 0.0}
    st.session_state[f"pos_cart_discount_{company_key}"] = {
        "type": str(discount_state.get("type") or "amount"),
        "value": float(discount_state.get("value") or 0.0),
        "computed": float(discount_state.get("computed") or 0.0),
        "threshold_requires_approval": bool(discount_state.get("threshold_requires_approval", False)),
    }
    return payload


def _clear_pos_cart_state(company_key):
    st.session_state[f"pos_cart_{company_key}"] = []
    st.session_state[f"pos_cart_discount_{company_key}"] = {
        "type": "amount",
        "value": 0.0,
        "computed": 0.0,
        "threshold_requires_approval": False,
    }
    _clear_pos_discount_approval_state(company_key)


def _fetch_pos_suspended_sale_rows(company_key, active_branch_id, cashier_identity):
    suspended_conn = None
    try:
        suspended_conn = get_connection()
        ensure_pos_sales_schema(suspended_conn)
        suspend_query = """
            SELECT id, suspend_reference, cashier, note, created_at
            FROM pos_suspended_sales
            WHERE company_key = ?
              AND status = 'suspended'
        """
        suspend_params = [company_key]
        if active_branch_id:
            suspend_query += " AND COALESCE(branch_id, '') = ?"
            suspend_params.append(str(active_branch_id))
        suspend_query += " AND cashier = ? ORDER BY created_at DESC"
        suspend_params.append(cashier_identity)
        return suspended_conn.execute(suspend_query, tuple(suspend_params)).fetchall()
    finally:
        if suspended_conn:
            suspended_conn.close()


def _resume_pos_suspended_sale(company_key, role, active_branch_id, checkout_complete_key, suspended_row):
    resume_conn = None
    try:
        resume_conn = get_connection()
        ensure_pos_sales_schema(resume_conn)
        payload_row = resume_conn.execute(
            "SELECT cart_json FROM pos_suspended_sales WHERE id = ? AND company_key = ? AND status = 'suspended' LIMIT 1",
            (int(suspended_row["id"]), company_key),
        ).fetchone()
        if not payload_row:
            st.warning("This suspended sale is no longer available.")
            return
        restored_payload = _restore_pos_cart_payload(company_key, payload_row["cart_json"], conn=resume_conn)
        revalidation_messages = restored_payload.get("revalidation_messages") or []
        if revalidation_messages:
            st.warning("Suspended sale adjusted: " + " ".join(revalidation_messages))
        resume_conn.execute(
            "UPDATE pos_suspended_sales SET status = 'resumed', resumed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(suspended_row["id"]),),
        )
        log_audit_action(
            resume_conn,
            company_key,
            role,
            "POS Sale Resumed",
            "POS",
            details=f"suspend_reference={suspended_row['suspend_reference']}",
            branch_id=active_branch_id,
            action_type="admin",
            document_ref=suspended_row["suspend_reference"],
        )
        resume_conn.commit()
        log_system_event(
            "INFO",
            "POS",
            f"Resumed suspended sale {suspended_row['suspend_reference']} for company_key={company_key}",
        )
        st.session_state[checkout_complete_key] = False
        st.rerun()
    except Exception as exc:
        if resume_conn:
            resume_conn.rollback()
        st.error(build_user_safe_error(exc, role))
    finally:
        if resume_conn:
            resume_conn.close()


def _cancel_pos_suspended_sale(company_key, role, active_branch_id, suspended_row):
    cancel_conn = None
    try:
        cancel_conn = get_connection()
        ensure_pos_sales_schema(cancel_conn)
        cancel_conn.execute(
            "UPDATE pos_suspended_sales SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP WHERE id = ? AND company_key = ? AND status = 'suspended'",
            (int(suspended_row["id"]), company_key),
        )
        log_audit_action(
            cancel_conn,
            company_key,
            role,
            "POS Suspended Sale Cancelled",
            "POS",
            details=f"suspend_reference={suspended_row['suspend_reference']}",
            branch_id=active_branch_id,
            action_type="admin",
            document_ref=suspended_row["suspend_reference"],
        )
        cancel_conn.commit()
        log_system_event(
            "INFO",
            "POS",
            f"Cancelled suspended sale {suspended_row['suspend_reference']} for company_key={company_key}",
        )
        st.rerun()
    except Exception as exc:
        if cancel_conn:
            cancel_conn.rollback()
        st.error(build_user_safe_error(exc, role))
    finally:
        if cancel_conn:
            cancel_conn.close()


def _render_pos_suspended_sales_side_panel(company_key, role, active_branch_id, checkout_complete_key):
    st.markdown('<div class="eka-card pos-suspended-panel">', unsafe_allow_html=True)
    st.markdown("#### Suspended Sales")
    cashier_identity = _get_pos_cashier_identity(role)
    suspended_rows = []
    try:
        suspended_rows = _fetch_pos_suspended_sale_rows(company_key, active_branch_id, cashier_identity)
    except Exception as exc:
        st.warning(build_user_safe_error(exc, role))
    if suspended_rows:
        st.caption(f"{len(suspended_rows)} held sale(s) — newest first.")
        for row in suspended_rows[:5]:
            note_preview = (row["note"] or "No note")[:32]
            st.markdown(
                (
                    f'<p class="pos-suspended-list-item"><strong>{html.escape(str(row["suspend_reference"]))}</strong><br>'
                    f'{html.escape(str(row["created_at"] or ""))} · {html.escape(note_preview)}</p>'
                ),
                unsafe_allow_html=True,
            )
        latest_row = suspended_rows[0]
        if st.button("Resume Latest", key=f"pos_resume_latest_sale_{company_key}", use_container_width=True, type="primary"):
            _resume_pos_suspended_sale(company_key, role, active_branch_id, checkout_complete_key, latest_row)
        suspended_options = [
            "{ref} | {cashier} | {created} | {note}".format(
                ref=row["suspend_reference"],
                cashier=row["cashier"] or "Unknown",
                created=row["created_at"],
                note=(row["note"] or "No note")[:40],
            )
            for row in suspended_rows
        ]
        selected_suspended_label = st.selectbox(
            "Resume Suspended Sale",
            suspended_options,
            key=f"pos_suspended_select_{company_key}",
        )
        selected_suspended_row = suspended_rows[suspended_options.index(selected_suspended_label)]
        if st.button("Resume Selected", key=f"pos_resume_sale_{company_key}", use_container_width=True):
            _resume_pos_suspended_sale(company_key, role, active_branch_id, checkout_complete_key, selected_suspended_row)
        cancel_confirm = st.checkbox(
            "Confirm Cancel",
            key=f"pos_cancel_suspend_confirm_{company_key}",
        )
        if st.button("Cancel Selected", key=f"pos_cancel_suspend_{company_key}", use_container_width=True):
            if not cancel_confirm:
                st.warning("Confirm the suspended sale cancellation first.")
            else:
                _cancel_pos_suspended_sale(company_key, role, active_branch_id, selected_suspended_row)
    else:
        st.caption("No suspended sales for this cashier at this branch.")
    st.markdown("</div>", unsafe_allow_html=True)


def _get_pos_cashier_summary(conn, company_key, sale_date, cashier=None, branch_id=None):
    params = [company_key, str(sale_date)]
    query = """
        SELECT
            COUNT(*) AS receipt_count,
            COALESCE(SUM(credit), 0) AS total_revenue,
            COALESCE(SUM(CASE WHEN COALESCE(payment_method, 'Cash') = 'Cash' THEN credit ELSE 0 END), 0) AS cash_sales,
            COALESCE(SUM(CASE WHEN COALESCE(payment_method, '') = 'Mobile Money' THEN credit ELSE 0 END), 0) AS mobile_money_sales,
            COALESCE(SUM(CASE WHEN COALESCE(payment_method, '') = 'Card' THEN credit ELSE 0 END), 0) AS card_sales,
            COALESCE(SUM(CASE WHEN COALESCE(payment_method, '') = 'Bank Transfer' THEN credit ELSE 0 END), 0) AS bank_transfer_sales,
            COALESCE(SUM(CASE WHEN COALESCE(payment_method, '') = 'On Credit' THEN credit ELSE 0 END), 0) AS credit_sales
        FROM vouchers
        WHERE company_key = ?
          AND v_type = 'Sales'
          AND date = ?
          AND COALESCE(status, 'Posted') != 'Void'
    """
    if branch_id:
        query += " AND COALESCE(branch_id, '') = ?"
        params.append(str(branch_id))
    if cashier:
        query += " AND COALESCE(created_by, '') = ?"
        params.append(str(cashier))
    row = conn.execute(query, tuple(params)).fetchone()
    row = dict(row) if row else {}
    total_revenue = float(row.get("total_revenue") or 0.0)
    return {
        "receipt_count": int(row.get("receipt_count") or 0),
        "total_completed_sales": int(row.get("receipt_count") or 0),
        "total_revenue": total_revenue,
        "cash_sales": float(row.get("cash_sales") or 0.0),
        "mobile_money_sales": float(row.get("mobile_money_sales") or 0.0),
        "card_sales": float(row.get("card_sales") or 0.0),
        "bank_transfer_sales": float(row.get("bank_transfer_sales") or 0.0),
        "credit_sales": float(row.get("credit_sales") or 0.0),
    }


def _get_pos_cashier_options(conn, company_key, branch_id=None):
    params = [company_key]
    voucher_query = """
        SELECT DISTINCT COALESCE(created_by, '') AS cashier
        FROM vouchers
        WHERE company_key = ?
          AND v_type = 'Sales'
          AND COALESCE(created_by, '') != ''
    """
    if branch_id:
        voucher_query += " AND COALESCE(branch_id, '') = ?"
        params.append(str(branch_id))
    voucher_rows = conn.execute(voucher_query, tuple(params)).fetchall()
    closing_params = [company_key]
    closing_query = """
        SELECT DISTINCT COALESCE(cashier, '') AS cashier
        FROM cashier_closings
        WHERE company_key = ?
          AND COALESCE(cashier, '') != ''
    """
    if branch_id:
        closing_query += " AND COALESCE(branch_id, '') = ?"
        closing_params.append(str(branch_id))
    closing_rows = conn.execute(closing_query, tuple(closing_params)).fetchall()
    options = {str(row["cashier"]).strip() for row in voucher_rows + closing_rows if str(row["cashier"]).strip()}
    return sorted(options)


def _persist_pos_sale(conn, company_key, branch_id, sale_reference, receipt_data, sale_cart, customer_id=None):
    existing = conn.execute(
        "SELECT id FROM pos_sales WHERE company_key = ? AND sale_reference = ? LIMIT 1",
        (company_key, sale_reference),
    ).fetchone()
    if existing:
        return int(existing["id"])

    cursor = conn.execute(
        ensure_insert_sql_returning(
            """
            INSERT INTO pos_sales (
                company_key, branch_id, sale_reference, receipt_number, sale_date, sale_datetime,
                cashier, payment_method, customer_id, subtotal, discount_total, tax_total,
                grand_total, amount_tendered, change_due
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (
            company_key,
            str(branch_id or ""),
            sale_reference,
            receipt_data.get("receipt_number") or sale_reference,
            str(receipt_data.get("sale_date") or ""),
            str(receipt_data.get("sale_datetime") or ""),
            str(receipt_data.get("cashier") or ""),
            str(receipt_data.get("payment_method") or ""),
            int(customer_id) if customer_id else None,
            float(receipt_data.get("subtotal") or 0.0),
            float(receipt_data.get("discount_total") or 0.0),
            float(receipt_data.get("tax_total") or 0.0),
            float(receipt_data.get("grand_total") or 0.0),
            float(receipt_data.get("amount_tendered") or 0.0),
            float(receipt_data.get("change_due") or 0.0),
        ),
    )
    pos_sale_id = get_inserted_id(cursor)
    for sale_line in sale_cart:
        _recalculate_pos_line(sale_line)
        conn.execute(
            """
            INSERT INTO pos_sale_lines (
                pos_sale_id, company_key, inventory_item_id, item_name, item_code, barcode,
                qty_sold, unit_price, line_discount, tax_rate, line_total, cost_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pos_sale_id,
                company_key,
                int(sale_line["inventory_item_id"]) if sale_line.get("inventory_item_id") is not None else None,
                str(sale_line.get("name") or ""),
                str(sale_line.get("item_code") or ""),
                str(sale_line.get("barcode") or ""),
                float(sale_line.get("qty") or 0.0),
                float(sale_line.get("price") or 0.0),
                float(sale_line.get("line_discount") or 0.0),
                float(sale_line.get("tax_rate") or 0.0),
                float(sale_line.get("line_total") or 0.0),
                float(sale_line.get("cost_price") or 0.0),
            ),
        )
    return pos_sale_id


def _lookup_pos_sale_for_return(conn, company_key, sale_reference, branch_id=None):
    normalized_reference = str(sale_reference or "").strip()
    if not normalized_reference:
        return None
    params = [company_key, normalized_reference, normalized_reference]
    query = """
        SELECT *
        FROM pos_sales
        WHERE company_key = ?
          AND (sale_reference = ? OR receipt_number = ?)
    """
    if branch_id:
        query += " AND COALESCE(branch_id, '') = ?"
        params.append(str(branch_id))
    query += " ORDER BY id DESC LIMIT 1"
    sale_row = conn.execute(query, tuple(params)).fetchone()
    if sale_row:
        sale_data = dict(sale_row)
        return_rows = conn.execute(
            """
            SELECT
                psl.*,
                COALESCE(SUM(CASE WHEN COALESCE(pr.status, 'Posted') != 'Voided' THEN pr.qty_returned ELSE 0 END), 0) AS qty_returned
            FROM pos_sale_lines psl
            LEFT JOIN pos_returns pr
              ON pr.company_key = psl.company_key
             AND pr.pos_sale_line_id = psl.id
            WHERE psl.pos_sale_id = ?
            GROUP BY psl.id
            ORDER BY psl.id ASC
            """,
            (int(sale_row["id"]),),
        ).fetchall()
        items = []
        for row in return_rows:
            sold_qty = float(row["qty_sold"] or 0.0)
            already_returned = float(row["qty_returned"] or 0.0)
            refundable_qty = max(sold_qty - already_returned, 0.0)
            items.append(
                {
                    "pos_sale_line_id": int(row["id"]),
                    "item_id": int(row["inventory_item_id"]) if row["inventory_item_id"] is not None else None,
                    "item_name": row["item_name"],
                    "item_code": row["item_code"] or "",
                    "barcode": row["barcode"] or "",
                    "qty_sold": sold_qty,
                    "qty_returned": already_returned,
                    "refundable_qty": refundable_qty,
                    "unit_price": float(row["unit_price"] or 0.0),
                    "line_discount": float(row["line_discount"] or 0.0),
                    "tax_rate": float(row["tax_rate"] or 0.0),
                    "cost_price": float(row["cost_price"] or 0.0),
                }
            )
        sale_data["items"] = items
        sale_data["line_items_available"] = True
        return sale_data

    voucher_row = conn.execute(
        """
        SELECT id, company_key, branch_id, reference_no, date, created_by, payment_method, credit
        FROM vouchers
        WHERE company_key = ?
          AND v_type = 'Sales'
          AND (reference_no = ? OR narration LIKE ?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (company_key, normalized_reference, f"%{normalized_reference}%"),
    ).fetchone()
    if not voucher_row:
        return None
    return {
        "id": None,
        "company_key": voucher_row["company_key"],
        "branch_id": voucher_row["branch_id"] or "",
        "sale_reference": voucher_row["reference_no"] or normalized_reference,
        "receipt_number": voucher_row["reference_no"] or normalized_reference,
        "sale_date": voucher_row["date"],
        "sale_datetime": voucher_row["date"],
        "cashier": voucher_row["created_by"] or "",
        "payment_method": voucher_row["payment_method"] or "",
        "grand_total": float(voucher_row["credit"] or 0.0),
        "subtotal": float(voucher_row["credit"] or 0.0),
        "discount_total": 0.0,
        "tax_total": 0.0,
        "items": [],
        "line_items_available": False,
    }


def _generate_pos_return_reference():
    return f"RET-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def _payment_account_for_refund_method(refund_method):
    mapping = {
        "Cash": ("Cash", "Asset"),
        "Mobile Money": ("Mobile Money", "Asset"),
        "Card": ("Bank", "Asset"),
        "Bank Transfer": ("Bank", "Asset"),
        "Store Credit": ("Customer Store Credit", "Liability"),
    }
    return mapping.get(str(refund_method or "").strip(), ("Cash", "Asset"))


def _process_pos_return(
    conn,
    *,
    company_key,
    branch_id,
    role,
    original_sale,
    return_items,
    refund_method,
    reason,
    return_reference,
):
    if not return_items:
        raise ValueError("Select at least one item to return.")
    if not reason:
        raise ValueError("Return reason is required.")

    sale_reference = str(original_sale.get("sale_reference") or original_sale.get("receipt_number") or "").strip()
    if not sale_reference:
        raise ValueError("Original sale reference is required.")

    refund_method = str(refund_method or "").strip()
    if refund_method not in {"Cash", "Mobile Money", "Card", "Bank Transfer", "Store Credit"}:
        raise ValueError("Choose a valid refund method.")

    if conn.execute(
        "SELECT id FROM pos_returns WHERE company_key = ? AND return_reference = ? LIMIT 1",
        (company_key, return_reference),
    ).fetchone():
        raise ValueError("This return reference has already been processed.")

    total_refund_amount = 0.0
    total_inventory_cost = 0.0
    recorded_rows = []
    refund_customer_id = original_sale.get("customer_id")
    refund_account_name, refund_account_type = _payment_account_for_refund_method(refund_method)
    refund_account_id = engine_get_or_create_account(conn, refund_account_name, refund_account_type)
    sales_returns_account_id = engine_get_or_create_account(conn, "Sales Returns and Refunds", "Expense")
    inventory_account_id = engine_get_or_create_account(conn, "Inventory", "Asset")
    cogs_account_id = engine_get_or_create_account(conn, "Cost of Goods Sold", "Expense")

    for selected_item in return_items:
        pos_sale_line_id = int(selected_item["pos_sale_line_id"])
        qty_requested = float(selected_item["qty_returned"])
        if qty_requested <= 0:
            raise ValueError("Return quantity must be greater than zero.")
        line_row = conn.execute(
            """
            SELECT *
            FROM pos_sale_lines
            WHERE id = ? AND company_key = ?
            LIMIT 1
            """,
            (pos_sale_line_id, company_key),
        ).fetchone()
        if not line_row:
            raise ValueError("One of the selected sale lines could not be found.")
        already_returned_row = conn.execute(
            """
            SELECT COALESCE(SUM(qty_returned), 0) AS qty_returned
            FROM pos_returns
            WHERE company_key = ?
              AND pos_sale_line_id = ?
              AND COALESCE(status, 'Posted') != 'Voided'
            """,
            (company_key, pos_sale_line_id),
        ).fetchone()
        sold_qty = float(line_row["qty_sold"] or 0.0)
        already_returned = float(already_returned_row["qty_returned"] or 0.0) if already_returned_row else 0.0
        refundable_qty = max(sold_qty - already_returned, 0.0)
        if qty_requested > refundable_qty:
            raise ValueError(f"Return quantity for {line_row['item_name']} exceeds refundable quantity.")

        unit_price = float(line_row["unit_price"] or 0.0)
        cost_price = float(line_row["cost_price"] or 0.0)
        refund_amount = round(qty_requested * unit_price, 2)
        inventory_cost = round(qty_requested * cost_price, 2)
        inventory_item_id = int(line_row["inventory_item_id"]) if line_row["inventory_item_id"] is not None else None

        if inventory_item_id is not None:
            current_item = conn.execute(
                "SELECT qty, item_name FROM inventory WHERE id = ? AND company_key = ? LIMIT 1",
                (inventory_item_id, company_key),
            ).fetchone()
            if not current_item:
                raise ValueError(f"Inventory item for {line_row['item_name']} could not be found.")
            previous_qty = float(current_item["qty"] or 0.0)
            new_qty = previous_qty + qty_requested
            conn.execute(
                "UPDATE inventory SET qty = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND company_key = ?",
                (new_qty, inventory_item_id, company_key),
            )
            conn.execute(
                """
                INSERT INTO stock_movements (
                    company_key, branch_id, inventory_item_id, item_name, movement_type,
                    quantity, reason, previous_qty, new_qty, created_by, created_at, reference
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (
                    company_key,
                    branch_id,
                    inventory_item_id,
                    line_row["item_name"],
                    "Return / Refund Restock",
                    qty_requested,
                    reason,
                    previous_qty,
                    new_qty,
                    role,
                    return_reference,
                ),
            )

        cursor = conn.execute(
            ensure_insert_sql_returning(
                """
                INSERT INTO pos_returns (
                    company_key, branch_id, original_sale_reference, return_reference,
                    pos_sale_line_id, item_id, item_name, qty_returned, unit_price,
                    refund_amount, reason, refund_method, returned_by, returned_at, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'Posted')
                """
            ),
            (
                company_key,
                str(branch_id or ""),
                sale_reference,
                return_reference,
                pos_sale_line_id,
                inventory_item_id,
                line_row["item_name"],
                qty_requested,
                unit_price,
                refund_amount,
                reason,
                refund_method,
                role,
            ),
        )
        pos_return_id = get_inserted_id(cursor)
        line_description = f"POS return for {line_row['item_name']} from {sale_reference}"
        accounting_lines = [
            {"account_id": sales_returns_account_id, "debit": refund_amount, "credit": 0},
            {"account_id": refund_account_id, "debit": 0, "credit": refund_amount},
        ]
        if inventory_cost > 0:
            accounting_lines.extend(
                [
                    {"account_id": inventory_account_id, "debit": inventory_cost, "credit": 0},
                    {"account_id": cogs_account_id, "debit": 0, "credit": inventory_cost},
                ]
            )

        posted_entry_id = post_journal_entry(
            company_key=company_key,
            date=datetime.now().date(),
            description=line_description,
            reference=return_reference,
            lines=accounting_lines,
            created_by=role,
            branch_id=branch_id,
            customer_id=int(refund_customer_id) if refund_customer_id else None,
            source_module="POS Return",
            source_table="pos_returns",
            source_type="pos_return_refund",
            source_id=pos_return_id,
            approval_status="Posted",
            user_role=role,
            conn=conn,
        )
        conn.execute(
            "UPDATE pos_returns SET posted_entry_id = ? WHERE id = ?",
            (int(posted_entry_id), pos_return_id),
        )
        if refund_method == "Store Credit" and refund_customer_id:
            _record_customer_ledger_transaction(
                conn,
                company_key,
                int(refund_customer_id),
                "Credit",
                refund_amount,
                f"Store credit issued for POS return {return_reference}",
                role,
                branch_id=branch_id,
                reference=return_reference,
                transaction_date=datetime.now().date(),
                post_to_gl=False,
                source_module="POS Return",
            )

        total_refund_amount += refund_amount
        total_inventory_cost += inventory_cost
        recorded_rows.append(
            {
                "item_name": line_row["item_name"],
                "qty_returned": qty_requested,
                "refund_amount": refund_amount,
                "posted_entry_id": int(posted_entry_id),
            }
        )

    log_audit_action(
        conn,
        company_key,
        role,
        "POS Return Processed",
        "POS Return",
        details=f"return_reference={return_reference} original_sale_reference={sale_reference} refund_total={total_refund_amount:.2f}",
        branch_id=branch_id,
        action_type="return",
        document_ref=return_reference,
    )
    log_system_event(
        "INFO",
        "POS Return",
        f"Processed POS return company_key={company_key} branch_id={branch_id or ''} original_sale_reference={sale_reference} return_reference={return_reference} refund_total={total_refund_amount:.2f} user={role}",
    )
    return {
        "return_reference": return_reference,
        "original_sale_reference": sale_reference,
        "refund_total": round(total_refund_amount, 2),
        "inventory_cost_total": round(total_inventory_cost, 2),
        "items": recorded_rows,
    }


def _build_payslip_html(payroll_row):
    return f"""
    <div class='payslip-preview printable' style='font-family:sans-serif;'>
        <div style='margin-bottom:1rem;'>
            <h2 style='margin:0;padding:0;'>Payslip</h2>
            <div>Employee: {payroll_row['Employee']}</div>
            <div>Period: {payroll_row['Month']} {int(payroll_row['Year'])}</div>
            <div>Status: {payroll_row['Payment Status']}</div>
        </div>
        <table style='width:100%; border-collapse: collapse; margin-bottom:1rem;'>
            <tr><td style='border-bottom:1px solid #333;'>Basic Salary</td><td style='text-align:right;border-bottom:1px solid #333;'>{format_currency(payroll_row['Basic Salary'])}</td></tr>
            <tr><td style='border-bottom:1px solid #333;'>Allowances</td><td style='text-align:right;border-bottom:1px solid #333;'>{format_currency(payroll_row['Allowances'])}</td></tr>
            <tr><td style='border-bottom:1px solid #333;'>Deductions</td><td style='text-align:right;border-bottom:1px solid #333;'>{format_currency(payroll_row['Deductions'])}</td></tr>
            <tr><td style='border-bottom:1px solid #333;'>SSNIT T1</td><td style='text-align:right;border-bottom:1px solid #333;'>{format_currency(payroll_row['SSNIT T1'])}</td></tr>
            <tr><td style='border-bottom:1px solid #333;'>PAYE</td><td style='text-align:right;border-bottom:1px solid #333;'>{format_currency(payroll_row['PAYE'])}</td></tr>
            <tr><td style='font-weight:bold;'>Net Salary</td><td style='text-align:right;font-weight:bold;'>{format_currency(payroll_row['Net Salary'])}</td></tr>
        </table>
            <div style='font-size:0.75rem; color:#555; margin-bottom:0.85rem; text-align:center;'>{PRINTABLE_DOCUMENT_FOOTER}</div>
        <button class='print-button' onclick='window.print()'>Print Payslip</button>
    </div>
    """


def _inject_print_styles():
    st.markdown(
        """
        <style>
            @media print {
                body * { visibility: hidden !important; }
                .printable, .printable * { visibility: visible !important; }
                .printable { position: absolute !important; top: 0; left: 0; width: 100% !important; }
                .css-1d391kg, .css-1y0tads, .css-1d391kg, .css-1q8dd3j, header, section, nav, aside { display: none !important; }
            }
            .receipt-preview, .payslip-preview {
                background: #fff;
                padding: 1rem;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            .print-button {
                background-color: #2563eb;
                color: #fff;
                border: none;
                padding: 0.65rem 1rem;
                border-radius: 4px;
                cursor: pointer;
            }
            .print-button:hover { background-color: #1d4ed8; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _calculate_payroll_values(basic_salary, allowances, deductions=0.0):
    ssnit_t1_rate = 0.055
    ssnit_t2_rate = 0.05
    bands = [
        (319, 0.0),
        (110, 0.05),
        (130, 0.10),
        (3000, 0.175),
        (16441, 0.25),
        (float("inf"), 0.30),
    ]

    taxable = max(float(basic_salary) + float(allowances) - float(deductions), 0.0)
    ssnit_t1 = float(basic_salary) * ssnit_t1_rate
    ssnit_t2 = float(basic_salary) * ssnit_t2_rate
    chargeable = max(taxable - ssnit_t1, 0.0)

    monthly_taxable = chargeable / 12 if chargeable > 0 else 0.0
    paye = 0.0
    remaining = monthly_taxable
    for band, rate in bands:
        if remaining <= 0:
            break
        chunk = min(remaining, band)
        paye += chunk * rate
        remaining -= chunk
    paye *= 12
    net_salary = float(basic_salary) + float(allowances) - float(deductions) - ssnit_t1 - paye

    return {
        "ssnit_t1": ssnit_t1,
        "ssnit_t2": ssnit_t2,
        "taxable_income": taxable,
        "paye": paye,
        "net_salary": net_salary,
    }


def _payroll_payment_account_name(payment_method):
    normalized_method = str(payment_method or "").strip()
    if normalized_method == "Bank":
        return "Bank"
    if normalized_method == "Mobile Money":
        return "Mobile Money"
    return "Cash"


def _get_payroll_posted_entry_id(conn, company_key, payroll_id, payroll_reference=None):
    payroll_row = conn.execute(
        """
        SELECT posted_entry_id
        FROM payroll
        WHERE id = ? AND company_key = ?
        LIMIT 1
        """,
        (int(payroll_id), company_key),
    ).fetchone()
    if not payroll_row:
        return None
    if payroll_row["posted_entry_id"] not in (None, "", 0):
        return int(payroll_row["posted_entry_id"])
    linked_row = conn.execute(
        """
        SELECT id
        FROM journal_entries
        WHERE company_key = ?
          AND lower(COALESCE(source_table, '')) = 'payroll'
          AND source_id = ?
          AND COALESCE(is_voided, 0) = 0
          AND COALESCE(approval_status, 'Posted') = 'Posted'
        LIMIT 1
        """,
        (company_key, int(payroll_id)),
    ).fetchone()
    if linked_row:
        return int(linked_row["id"])
    if payroll_reference:
        legacy_row = conn.execute(
            """
            SELECT id
            FROM journal_entries
            WHERE company_key = ?
              AND reference = ?
              AND COALESCE(is_voided, 0) = 0
              AND COALESCE(approval_status, 'Posted') = 'Posted'
            LIMIT 1
            """,
            (company_key, str(payroll_reference)),
        ).fetchone()
        if legacy_row:
            return int(legacy_row["id"])
    return None


def _build_payroll_journal_lines(
    conn,
    company_key,
    *,
    gross_salary,
    paye_amount,
    ssnit_amount,
    other_deductions,
    net_salary,
    payment_status,
    payment_method=None,
):
    gross_amount = round(float(gross_salary or 0.0), 2)
    paye_credit = round(float(paye_amount or 0.0), 2)
    ssnit_credit = round(float(ssnit_amount or 0.0), 2)
    other_credit = round(float(other_deductions or 0.0), 2)
    net_credit = round(float(net_salary or 0.0), 2)
    if gross_amount <= 0:
        raise ValueError("Gross salary must be greater than 0.")
    if any(value < 0 for value in (paye_credit, ssnit_credit, other_credit, net_credit)):
        raise ValueError("Payroll components cannot be negative.")
    credited_total = round(paye_credit + ssnit_credit + other_credit + net_credit, 2)
    if abs(gross_amount - credited_total) > 0.01:
        raise ValueError("Payroll journal is not balanced.")

    ensure_core_financial_accounts(company_key, conn=conn)
    lines = [
        {
            "account_id": get_or_create_account(company_key, "Salary Expense", "Expense", conn=conn),
            "debit": gross_amount,
            "credit": 0,
        }
    ]
    if paye_credit > 0:
        lines.append(
            {
                "account_id": get_or_create_account(company_key, "PAYE Payable", "Liability", conn=conn),
                "debit": 0,
                "credit": paye_credit,
            }
        )
    if ssnit_credit > 0:
        lines.append(
            {
                "account_id": get_or_create_account(company_key, "SSNIT Payable", "Liability", conn=conn),
                "debit": 0,
                "credit": ssnit_credit,
            }
        )
    if other_credit > 0:
        lines.append(
            {
                "account_id": get_or_create_account(company_key, "Other Payroll Deductions Payable", "Liability", conn=conn),
                "debit": 0,
                "credit": other_credit,
            }
        )
    settlement_account_name = (
        _payroll_payment_account_name(payment_method)
        if str(payment_status or "").strip() == "Paid"
        else "Payroll Payable"
    )
    settlement_account_type = "Asset" if str(payment_status or "").strip() == "Paid" else "Liability"
    if net_credit > 0:
        lines.append(
            {
                "account_id": get_or_create_account(company_key, settlement_account_name, settlement_account_type, conn=conn),
                "debit": 0,
                "credit": net_credit,
            }
        )
    return lines


def _import_inventory_from_excel(conn, company_key, file_obj):
    imported_df = pd.read_excel(file_obj)
    if imported_df.empty:
        return 0

    column_map = {column.lower().strip(): column for column in imported_df.columns}
    required = ["item_name", "category", "quantity"]
    missing = [column for column in required if column not in column_map]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    changed_rows = 0
    for _, row in imported_df.iterrows():
        row_id = row[column_map["id"]] if "id" in column_map and not pd.isna(row[column_map["id"]]) else None
        item_name = str(row[column_map["item_name"]]).strip()
        if not item_name:
            continue
        category = str(row[column_map["category"]]).strip()
        opening_column = column_map.get("opening_stock") or column_map.get("opening_balance")
        barcode_column = column_map.get("barcode")
        qty = float(row[column_map["quantity"]] or 0)
        opening_balance = float(row[opening_column] or qty) if opening_column else qty
        price_column = column_map.get("selling_price") or column_map.get("unit_price") or column_map.get("price")
        cost_column = column_map.get("cost_price")
        barcode = str(row[barcode_column]).strip() if barcode_column and not pd.isna(row[barcode_column]) else ""
        price = float(row[price_column] or 0) if price_column else 0.0
        cost_price = float(row[cost_column] or 0) if cost_column else 0.0
        if row_id is not None:
            existing = conn.execute(
                "SELECT id FROM inventory WHERE company_key = ? AND id = ?",
                (company_key, int(row_id)),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE inventory
                    SET item_name = ?, barcode = ?, category = ?, opening_balance = ?, qty = ?, price = ?, cost_price = ?
                    WHERE company_key = ? AND id = ?
                    """,
                    (item_name, barcode, category, opening_balance, qty, price, cost_price, company_key, int(row_id)),
                )
                changed_rows += 1
                continue
        existing = conn.execute(
            """
            SELECT id FROM inventory
            WHERE company_key = ? AND item_name = ? AND COALESCE(category, '') = ?
            """,
            (company_key, item_name, category),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE inventory
                SET barcode = COALESCE(NULLIF(?, ''), barcode), opening_balance = ?, qty = ?, price = ?, cost_price = ?
                WHERE company_key = ? AND id = ?
                """,
                (barcode, opening_balance, qty, price, cost_price, company_key, existing["id"]),
            )
            changed_rows += 1
            continue
        conn.execute(
            """
            INSERT INTO inventory (company_key, item_name, barcode, category, opening_balance, qty, price, cost_price, inventory_account_id, cogs_account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_key,
                item_name,
                barcode,
                category,
                opening_balance,
                qty,
                price,
                cost_price,
                get_account_id(conn, "Inventory", "Asset"),
                get_account_id(conn, "Cost of Goods Sold", "Expense"),
            ),
        )
        opening_stock_value = round(float(opening_balance or 0) * float(cost_price or 0), 2)
        if opening_stock_value > 0:
            offset_account, offset_type = _inventory_offset_account("Accounts Payable")
            post_journal_entry(
                company_key=company_key,
                date=datetime.now().date(),
                description="Opening inventory balance",
                reference=f"INV-IMPORT-{item_name}-{changed_rows + 1}",
                lines=[
                    {"account_id": get_account_id(conn, "Inventory", "Asset"), "debit": opening_stock_value, "credit": 0},
                    {"account_id": get_account_id(conn, offset_account, offset_type), "debit": 0, "credit": opening_stock_value},
                ],
                created_by=st.session_state.get("user", {}).get("role", "System"),
                branch_id=st.session_state.get("active_branch_id"),
                source_module="Inventory Import",
                source_table="inventory",
                conn=conn,
            )
        changed_rows += 1
    return changed_rows


SCANNER_BEEP_BASE64 = (
    "UklGRlQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YTAAAAAAAP//AAD//wAA//8AAP//"
    "AAD//wAA//8AAP//AAD//wAA"
)


def _set_input_pending(source_key, pending_key):
    pending_value = str(st.session_state.get(source_key, "") or "").strip()
    if pending_value:
        st.session_state[pending_key] = pending_value


def _sync_data_editor_to_session(editor_key, session_key):
    """Syncs a Streamlit data_editor (by key) back into a session_state list.

    Args:
        editor_key: the st.data_editor widget key
        session_key: the session_state key to write the records to
    """
    try:
        val = st.session_state.get(editor_key)
        if val is None:
            st.session_state[session_key] = []
            return
        # If the data_editor stores a DataFrame-like object, convert to records
        if hasattr(val, "to_dict"):
            st.session_state[session_key] = val.to_dict("records")
        else:
            st.session_state[session_key] = val
    except Exception:
        # Fallback: ensure session key exists
        existing = st.session_state.get(session_key)
        if existing is None:
            st.session_state[session_key] = []


def save_bill_state():
    """Save bill items from data_editor to session_state."""
    _sync_data_editor_to_session("bill_items_editor", "bill_items")


def _normalize_bill_items(raw_items):
    if raw_items is None:
        return []
    if hasattr(raw_items, "to_dict"):
        rows = raw_items.to_dict("records")
    elif isinstance(raw_items, list):
        rows = raw_items
    else:
        rows = []

    normalized_items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_name = str(row.get("item_name") or "").strip()
        quantity_raw = row.get("quantity")
        unit_price_raw = row.get("unit_price")
        if not item_name and quantity_raw in (None, "", 0, 0.0) and unit_price_raw in (None, "", 0, 0.0):
            continue
        try:
            quantity = float(quantity_raw or 0)
            unit_price = float(unit_price_raw or 0)
        except (TypeError, ValueError):
            continue
        if item_name and quantity > 0 and unit_price >= 0:
            normalized_items.append(
                {
                    "item_name": item_name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                }
            )
    return normalized_items


PURCHASE_CLASSIFICATION_OPTIONS = [
    "Inventory Purchase",
    "Expense Purchase",
    "Fixed Asset Purchase",
]

FIXED_ASSET_PURCHASE_CATEGORIES = ["Vehicle", "Equipment", "Building", "Furniture", "Land", "Other"]
FIXED_ASSET_ACQUISITION_TYPES = [
    "Opening Balance Asset",
    "Purchased with Cash/Bank/Mobile Money",
    "Purchased on Credit",
    "Owner-Contributed Asset",
]


def _normalize_purchase_classification(value):
    normalized_value = " ".join(str(value or "").strip().split()).lower()
    if normalized_value in {"inventory", "inventory purchase"}:
        return "Inventory Purchase"
    if normalized_value in {"expense", "expense purchase"}:
        return "Expense Purchase"
    if normalized_value in {"fixed asset", "fixed asset purchase", "asset purchase"}:
        return "Fixed Asset Purchase"
    return "Inventory Purchase"


def _purchase_payment_account_name(payment_method):
    normalized_method = str(payment_method or "").strip()
    if normalized_method == "Bank":
        return "Bank"
    if normalized_method == "Mobile Money":
        return "Mobile Money"
    return "Cash"


def get_purchase_expense_account_options(company_key, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        ensure_core_financial_accounts(company_key, conn=conn)
        rows = conn.execute(
            """
            SELECT DISTINCT COALESCE(name, account_name) AS account_name
            FROM chart_of_accounts
            WHERE lower(COALESCE(type, account_type, category, '')) = 'expense'
            ORDER BY COALESCE(name, account_name)
            """
        ).fetchall()
        options = []
        seen = set()
        for row in rows:
            account_name = " ".join(str(row["account_name"] or "").strip().split())
            if not account_name:
                continue
            normalized_name = account_name.lower()
            if normalized_name in seen:
                continue
            seen.add(normalized_name)
            options.append(account_name)
        if "general expenses" not in seen:
            options.append("General Expenses")
        return options or ["General Expenses"]
    finally:
        if owns_connection and conn:
            conn.close()


def build_purchase_journal_lines(
    conn,
    company_key,
    *,
    classification,
    amount,
    input_vat=0.0,
    status="Pending",
    payment_method="Cash",
    expense_account_name=None,
):
    normalized_classification = _normalize_purchase_classification(classification)
    purchase_amount = round(float(amount or 0.0), 2)
    vat_amount = round(float(input_vat or 0.0), 2)
    if purchase_amount <= 0:
        raise ValueError("Purchase amount must be greater than 0.")

    ensure_core_financial_accounts(company_key, conn=conn)

    if normalized_classification == "Expense Purchase":
        debit_account_name = " ".join(str(expense_account_name or "").strip().split()) or "General Expenses"
        debit_account_type = "Expense"
    elif normalized_classification == "Fixed Asset Purchase":
        debit_account_name = "Fixed Assets"
        debit_account_type = "Asset"
    else:
        debit_account_name = "Inventory"
        debit_account_type = "Asset"

    is_immediately_paid = str(status or "").strip() == "Received"
    credit_account_name = _purchase_payment_account_name(payment_method) if is_immediately_paid else "Accounts Payable"
    credit_account_type = "Asset" if is_immediately_paid else "Liability"
    total_credit = round(purchase_amount + vat_amount, 2)

    journal_lines = [
        {
            "account_id": get_or_create_account(company_key, debit_account_name, debit_account_type, conn=conn),
            "debit": purchase_amount,
            "credit": 0,
        },
        {
            "account_id": get_or_create_account(company_key, "VAT Receivable", "Asset", conn=conn),
            "debit": vat_amount,
            "credit": 0,
        } if vat_amount > 0 else None,
        {
            "account_id": get_or_create_account(company_key, credit_account_name, credit_account_type, conn=conn),
            "debit": 0,
            "credit": total_credit,
        },
    ]
    return [line for line in journal_lines if line], {
        "classification": normalized_classification,
        "debit_account_name": debit_account_name,
        "debit_account_type": debit_account_type,
        "credit_account_name": credit_account_name,
        "credit_account_type": credit_account_type,
        "total_credit": total_credit,
    }


def _normalize_fixed_asset_acquisition_type(value):
    normalized_value = " ".join(str(value or "").strip().split()).lower()
    if normalized_value == "purchased on credit":
        return "Purchased on Credit"
    if normalized_value == "owner-contributed asset":
        return "Owner-Contributed Asset"
    if normalized_value == "purchased with cash/bank/mobile money":
        return "Purchased with Cash/Bank/Mobile Money"
    return "Opening Balance Asset"


def _fixed_asset_has_posted_acquisition(conn, company_key, asset_id):
    return _get_fixed_asset_posted_entry_id(conn, company_key, asset_id) is not None


def _get_fixed_asset_posted_entry_id(conn, company_key, asset_id):
    asset_row = conn.execute(
        """
        SELECT posted_entry_id
        FROM fixed_assets
        WHERE id = ? AND company_key = ?
        LIMIT 1
        """,
        (int(asset_id), company_key),
    ).fetchone()
    if not asset_row:
        return None
    if asset_row["posted_entry_id"] not in (None, "", 0):
        return int(asset_row["posted_entry_id"])
    linked_row = conn.execute(
        """
        SELECT id
        FROM journal_entries
        WHERE company_key = ?
          AND lower(COALESCE(source_table, '')) = 'fixed_assets'
          AND source_id = ?
          AND COALESCE(is_voided, 0) = 0
          AND COALESCE(approval_status, 'Posted') = 'Posted'
        LIMIT 1
        """,
        (company_key, int(asset_id)),
    ).fetchone()
    if linked_row:
        return int(linked_row["id"])
    legacy_reference_row = conn.execute(
        """
        SELECT id
        FROM journal_entries
        WHERE company_key = ?
          AND reference = ?
          AND COALESCE(is_voided, 0) = 0
          AND COALESCE(approval_status, 'Posted') = 'Posted'
        LIMIT 1
        """,
        (company_key, f"FA-{int(asset_id)}"),
    ).fetchone()
    return int(legacy_reference_row["id"]) if legacy_reference_row else None


def _build_fixed_asset_acquisition_lines(
    conn,
    company_key,
    *,
    acquisition_type,
    cost,
    payment_method=None,
):
    normalized_type = _normalize_fixed_asset_acquisition_type(acquisition_type)
    asset_cost = round(float(cost or 0.0), 2)
    if asset_cost <= 0:
        raise ValueError("Asset cost must be greater than 0.")
    ensure_core_financial_accounts(company_key, conn=conn)
    debit_account_id = get_or_create_account(company_key, "Fixed Assets", "Asset", conn=conn)
    if normalized_type == "Purchased with Cash/Bank/Mobile Money":
        credit_account_name = _purchase_payment_account_name(payment_method)
        credit_account_type = "Asset"
    elif normalized_type == "Purchased on Credit":
        credit_account_name = "Accounts Payable"
        credit_account_type = "Liability"
    elif normalized_type == "Owner-Contributed Asset":
        credit_account_name = "Owner Capital"
        credit_account_type = "Equity"
    else:
        credit_account_name = "Opening Balance Equity"
        credit_account_type = "Equity"
    return [
        {"account_id": debit_account_id, "debit": asset_cost, "credit": 0},
        {
            "account_id": get_or_create_account(company_key, credit_account_name, credit_account_type, conn=conn),
            "debit": 0,
            "credit": asset_cost,
        },
    ], {
        "acquisition_type": normalized_type,
        "credit_account_name": credit_account_name,
        "credit_account_type": credit_account_type,
    }


def _trigger_scan_feedback(message_key, message, level="success", beep_key=None):
    st.session_state[message_key] = {"level": level, "text": message}
    if beep_key:
        st.session_state[beep_key] = True


def _render_flash_message(message_key, beep_key=None):
    payload = st.session_state.pop(message_key, None)
    if not payload:
        return
    level = payload.get("level", "info")
    text = payload.get("text", "")
    getattr(st, level, st.info)(text)
    if beep_key and st.session_state.pop(beep_key, False):
        components.html(
            f"""
            <audio autoplay>
                <source src="data:audio/wav;base64,{SCANNER_BEEP_BASE64}" type="audio/wav">
            </audio>
            """,
            height=0,
        )


def _focus_text_input(input_label):
    components.html(
        f"""
        <script>
        const focusTarget = () => {{
            const parentDoc = window.parent.document;
            const input = parentDoc.querySelector('input[aria-label="{input_label}"]');
            if (input) {{
                input.focus();
                input.select();
            }}
        }};
        focusTarget();
        setTimeout(focusTarget, 150);
        setTimeout(focusTarget, 500);
        setTimeout(focusTarget, 1000);
        const focusInterval = setInterval(focusTarget, 1500);
        setTimeout(() => clearInterval(focusInterval), 10000);
        </script>
        """,
        height=0,
    )


def _inject_pos_keyboard_shortcuts(company_key):
    """
    Safe keyboard UX helpers for POS.
    - F1: focus Scan Barcode input
    - F2: switch to Manual Entry mode (clicks the radio option)
    - F3: focus Search Product input
    - F4: scroll/focus attention to checkout panel (no posting)
    """
    components.html(
        f"""
        <script>
        (function () {{
            const parentDoc = window.parent.document;
            if (parentDoc.__ekaPosShortcutsInstalled) {{
                return;
            }}
            parentDoc.__ekaPosShortcutsInstalled = true;

            const focusWithRetries = (selector) => {{
                const attempt = () => {{
                    const el = parentDoc.querySelector(selector);
                    if (el) {{
                        el.focus();
                        try {{ el.select(); }} catch (e) {{}}
                    }}
                }};
                [0, 80, 180, 320].forEach((delay) => setTimeout(attempt, delay));
            }};

            const focusSearch = () => focusWithRetries('input[aria-label="Search Product"]');
            const focusScan = () => focusWithRetries('input[aria-label="Scan Barcode"]');

            const switchManualEntry = () => {{
                // Streamlit radio renders as labels with nested inputs. We pick the option label text.
                const labels = Array.from(parentDoc.querySelectorAll('label')).filter((l) => {{
                    const text = (l.innerText || '').trim();
                    return text === 'Manual Entry';
                }});
                if (labels.length) {{
                    labels[0].click();
                }}
            }};

            const focusCheckoutPanel = () => {{
                const anchor = parentDoc.getElementById('pos-checkout-anchor-{company_key}');
                const panel = parentDoc.querySelector('.pos-checkout-panel');
                const target = anchor || panel;
                if (target && target.scrollIntoView) {{
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                }}
                if (panel) {{
                    panel.classList.add('pos-checkout-highlight');
                    setTimeout(() => panel.classList.remove('pos-checkout-highlight'), 1200);
                }}
            }};

            parentDoc.addEventListener('keydown', (e) => {{
                const key = (e.key || '').toLowerCase();
                const active = parentDoc.activeElement;
                const activeTag = active ? (active.tagName || '').toLowerCase() : '';
                const inTypingField = activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select';

                if (key === 'f1') {{
                    e.preventDefault();
                    focusScan();
                    return;
                }}

                if (key === 'f3') {{
                    e.preventDefault();
                    focusSearch();
                    return;
                }}

                if (key === 'f2') {{
                    if (inTypingField) {{
                        e.preventDefault();
                    }}
                    switchManualEntry();
                    return;
                }}

                if (key === 'f4') {{
                    if (inTypingField) {{
                        e.preventDefault();
                    }}
                    focusCheckoutPanel();
                    return;
                }}
            }}, true);
        }})();
        </script>
        """,
        height=0,
    )


def _request_pos_barcode_scan_focus(company_key):
    st.session_state[f"pos_scan_focus_request_{company_key}"] = True


def _focus_pos_barcode_scanner():
    """Focus barcode scan input only when idle — skip cart, search, payment, and manual fields."""
    components.html(
        """
        <script>
        (function () {
            const parentDoc = window.parent.document;
            const shouldSkipFocus = () => {
                const active = parentDoc.activeElement;
                if (!active) {
                    return false;
                }
                const tag = (active.tagName || "").toLowerCase();
                const label = (active.getAttribute("aria-label") || "").toLowerCase();
                if (label === "scan barcode") {
                    return false;
                }
                if (tag === "button" || tag === "select" || tag === "textarea") {
                    return true;
                }
                if (tag === "input") {
                    const inputType = (active.getAttribute("type") || "text").toLowerCase();
                    if (inputType === "checkbox" || inputType === "radio") {
                        return true;
                    }
                    return true;
                }
                const skipLabels = [
                    "new item name", "manual price", "search product", "manual product",
                    "select item", "quantity", "qty", "disc type", "discount", "credit customer",
                    "transaction / reference", "amount tendered", "suspend sale note",
                    "cart discount", "manager username", "approval reason", "item code",
                    "new barcode", "supplier name", "custom supplier", "expiry date",
                    "payment method", "transaction date", "final checkout", "remove"
                ];
                return skipLabels.some((token) => label.includes(token));
            };
            const focusScanInput = () => {
                if (shouldSkipFocus()) {
                    return;
                }
                const scanInput = parentDoc.querySelector('input[aria-label="Scan Barcode"]');
                if (!scanInput) {
                    return;
                }
                scanInput.focus();
                if (parentDoc.activeElement === scanInput) {
                    scanInput.select();
                }
            };
            [150, 400].forEach((delay) => setTimeout(focusScanInput, delay));
        })();
        </script>
        """,
        height=0,
    )


def process_scan(image):
    """Decode a barcode/QR value from a camera image and return the scanned text."""
    if pyzbar is None:
        return None
    decoded = pyzbar.decode(image)
    if not decoded:
        return None
    return decoded[0].data.decode("utf-8").strip()


def _render_camera_scanner(module_key, pending_key):
    toggle_key = f"{module_key}_camera_open"
    nonce_key = f"{module_key}_camera_nonce"
    image_sig_key = f"{module_key}_camera_image_sig"
    button_label = "❌ Close Camera" if st.session_state.get(toggle_key) else "🔍 Tap to Scan"

    if st.button(button_label, key=f"{module_key}_camera_toggle_btn"):
        st.session_state[toggle_key] = not st.session_state.get(toggle_key, False)
        if not st.session_state[toggle_key]:
            st.session_state.pop(image_sig_key, None)
        st.rerun()

    if not st.session_state.get(toggle_key):
        return

    st.session_state["scanner_active"] = scanner_active

    nonce = st.session_state.get(nonce_key, 0)
    camera_file = st.camera_input("Scanner", key=f"{module_key}_camera_input_{nonce}")
    if camera_file is None:
        return

    image_signature = f"{camera_file.name}:{len(camera_file.getvalue())}"
    if image_signature == st.session_state.get(image_sig_key):
        return

    image = Image.open(BytesIO(camera_file.getvalue())).convert("RGB")
    decoded_value = process_scan(image)
    st.session_state[image_sig_key] = image_signature
    if decoded_value:
        st.session_state[pending_key] = decoded_value
        st.session_state[toggle_key] = False
        st.session_state[nonce_key] = nonce + 1
        st.rerun()
    st.info("No barcode or QR code was detected in that image yet.")


INVENTORY_POS_LOOKUP_COLUMNS = (
    "id, item_name, item_code, category, brand, qty, price, cost_price, barcode, "
    "min_stock_level, tax_rate, expiry_date"
)
INVENTORY_EXPIRY_WARNING_DAYS = 30


def _parse_inventory_expiry_date(expiry_value):
    expiry_text = str(expiry_value or "").strip()
    if not expiry_text:
        return None
    try:
        return datetime.fromisoformat(expiry_text).date()
    except ValueError:
        try:
            return datetime.strptime(expiry_text, "%Y-%m-%d").date()
        except ValueError:
            return None


def _compute_days_to_expiry(expiry_value):
    validation = _get_inventory_expiry_validation(expiry_value)
    return validation.get("days_to_expiry")


def _get_inventory_expiry_validation(expiry_value):
    expiry_text = str(expiry_value or "").strip()
    if not expiry_text:
        return {"status": "OK", "days_to_expiry": None, "parsed_date": None}
    parsed_date = _parse_inventory_expiry_date(expiry_value)
    if parsed_date is None:
        return {"status": "INVALID", "days_to_expiry": None, "parsed_date": None}
    days_to_expiry = (parsed_date - datetime.now().date()).days
    if days_to_expiry <= 0:
        return {"status": "EXPIRED", "days_to_expiry": days_to_expiry, "parsed_date": parsed_date}
    if days_to_expiry <= INVENTORY_EXPIRY_WARNING_DAYS:
        return {"status": "EXPIRING_SOON", "days_to_expiry": days_to_expiry, "parsed_date": parsed_date}
    return {"status": "OK", "days_to_expiry": days_to_expiry, "parsed_date": parsed_date}


def _get_inventory_stock_status(quantity, reorder_level):
    qty = max(float(quantity or 0.0), 0.0)
    reorder = max(float(reorder_level or 0.0), 0.0)
    if qty <= 0:
        return "OUT OF STOCK"
    if qty <= reorder:
        return "LOW STOCK"
    return "OK"


def _get_inventory_expiry_status(expiry_value):
    status_map = {
        "EXPIRING_SOON": "EXPIRING SOON",
        "EXPIRED": "EXPIRED",
        "INVALID": "INVALID",
        "OK": "OK",
    }
    return status_map.get(_get_inventory_expiry_validation(expiry_value)["status"], "OK")


def _inventory_stock_status_badge(stock_status):
    if stock_status == "OUT OF STOCK":
        return "⛔ OUT OF STOCK"
    if stock_status == "LOW STOCK":
        return "🔴 LOW STOCK"
    return ""


def _inventory_expiry_status_badge(expiry_status):
    if expiry_status == "EXPIRED":
        return "⛔ EXPIRED"
    if expiry_status == "INVALID":
        return "⚠ INVALID EXPIRY"
    if expiry_status == "EXPIRING SOON":
        return "⚠ EXPIRING SOON"
    return ""


def _format_pos_search_status_suffix(item_row):
    item_row = _normalize_pos_item_row(item_row)
    stock_status = _get_inventory_stock_status(item_row.get("qty"), item_row.get("min_stock_level"))
    expiry_status = _get_inventory_expiry_status(item_row.get("expiry_date"))
    suffix_parts = []
    if stock_status == "OUT OF STOCK":
        suffix_parts.append("⛔ OUT OF STOCK")
    elif stock_status == "LOW STOCK":
        suffix_parts.append("⚠ LOW STOCK")
    if expiry_status == "EXPIRED":
        suffix_parts.append("⛔ EXPIRED")
    elif expiry_status == "INVALID":
        suffix_parts.append("⚠ INVALID EXPIRY")
    elif expiry_status == "EXPIRING SOON":
        suffix_parts.append("⚠ EXPIRING SOON")
    return f" | {' | '.join(suffix_parts)}" if suffix_parts else ""


def _get_pos_add_block_reason(item_row):
    item_row = _normalize_pos_item_row(item_row)
    stock_status = _get_inventory_stock_status(item_row.get("qty"), item_row.get("min_stock_level"))
    if stock_status == "OUT OF STOCK":
        return "Out of stock — cannot add to cart."
    expiry_validation = _get_inventory_expiry_validation(item_row.get("expiry_date"))
    if expiry_validation["status"] == "EXPIRED":
        return "Expired item — cannot add to cart."
    if expiry_validation["status"] == "INVALID":
        return "Invalid expiry date — cannot add to cart."
    return None


def _fetch_live_inventory_row_for_pos(conn, company_key, inventory_item_id):
    return conn.execute(
        f"""
        SELECT {INVENTORY_POS_LOOKUP_COLUMNS}
        FROM inventory
        WHERE id = ? AND company_key = ?
        LIMIT 1
        """,
        (int(inventory_item_id), company_key),
    ).fetchone()


def _validate_pos_checkout_inventory_line(conn, company_key, sale_line):
    if bool(sale_line.get("is_manual")) or sale_line.get("inventory_item_id") is None:
        return None
    item_name = str(sale_line.get("item_name") or sale_line.get("name") or "Item")
    live_row = _fetch_live_inventory_row_for_pos(conn, company_key, int(sale_line["inventory_item_id"]))
    if not live_row:
        return f"{item_name} is no longer in inventory."
    live_item = _normalize_pos_item_row(live_row)
    cart_qty = float(sale_line.get("qty") or 0.0)
    available_qty = float(live_item.get("qty") or 0.0)
    if cart_qty > available_qty:
        return (
            f"Insufficient stock for {item_name}. "
            f"Available: {available_qty:,.2f}, in cart: {cart_qty:,.0f}."
        )
    add_block_reason = _get_pos_add_block_reason(live_item)
    if add_block_reason:
        return f"{item_name}: {add_block_reason}"
    return None


def _validate_pos_cart_at_checkout(conn, company_key, sale_cart):
    for sale_line in sale_cart:
        checkout_error = _validate_pos_checkout_inventory_line(conn, company_key, sale_line)
        if checkout_error:
            return checkout_error
    return None


def _revalidate_pos_cart_inventory(conn, company_key, cart_lines):
    validated_lines = []
    adjustment_messages = []
    for line in cart_lines or []:
        if bool(line.get("is_manual")) or line.get("inventory_item_id") is None:
            validated_lines.append(line)
            continue
        item_name = str(line.get("item_name") or line.get("name") or "Item")
        live_row = _fetch_live_inventory_row_for_pos(conn, company_key, int(line["inventory_item_id"]))
        if not live_row:
            adjustment_messages.append(f"Removed {item_name}: no longer in inventory.")
            continue
        live_item = _normalize_pos_item_row(live_row)
        expiry_validation = _get_inventory_expiry_validation(live_item.get("expiry_date"))
        if expiry_validation["status"] == "EXPIRED":
            adjustment_messages.append(f"Removed {item_name}: expired.")
            continue
        if expiry_validation["status"] == "INVALID":
            adjustment_messages.append(f"Removed {item_name}: invalid expiry date.")
            continue
        if float(live_item.get("qty") or 0.0) <= 0:
            adjustment_messages.append(f"Removed {item_name}: out of stock.")
            continue
        line["available_qty"] = float(live_item.get("qty") or 0.0)
        line["expiry_date"] = live_item.get("expiry_date")
        line["tax_rate"] = float(live_item.get("tax_rate") or 0.0)
        line["price"] = float(live_item.get("price") or line.get("price") or 0.0)
        line["cost_price"] = float(live_item.get("cost_price") or line.get("cost_price") or 0.0)
        line["min_stock_level"] = float(live_item.get("min_stock_level") or 0.0)
        line["item_name"] = live_item.get("item_name") or line.get("item_name")
        line["name"] = line["item_name"]
        cart_qty = max(int(line.get("qty") or 1), 1)
        max_available_qty = max(int(float(live_item.get("qty") or 0.0)), 1)
        if cart_qty > max_available_qty:
            line["qty"] = max_available_qty
            adjustment_messages.append(
                f"Reduced {item_name} quantity to {max_available_qty} (available stock)."
            )
        _recalculate_pos_line(line)
        validated_lines.append(line)
    return validated_lines, adjustment_messages


def _get_pos_line_max_qty(line):
    if bool(line.get("is_manual")) or line.get("inventory_item_id") is None:
        return None
    available_qty = float(line.get("available_qty") or 0.0)
    if available_qty <= 0:
        return 1
    return max(int(available_qty), 1)


def _apply_pos_cart_line_qty_limit(line, requested_qty):
    if bool(line.get("is_manual")) or line.get("inventory_item_id") is None:
        return max(int(requested_qty or 1), 1), False, None
    requested = max(int(requested_qty or 1), 1)
    max_qty = _get_pos_line_max_qty(line)
    if max_qty is not None and requested > max_qty:
        item_name = str(line.get("item_name") or line.get("name") or "Item")
        return max_qty, True, f"{item_name}: quantity limited to available stock ({max_qty})."
    return requested, False, None


def _get_pos_cart_line_warning_badges(cart_line):
    if not cart_line or bool(cart_line.get("is_manual")) or cart_line.get("inventory_item_id") is None:
        return []
    badges = []
    stock_status = _get_inventory_stock_status(
        cart_line.get("available_qty"),
        cart_line.get("min_stock_level"),
    )
    if stock_status == "LOW STOCK":
        badges.append("LOW STOCK")
    expiry_status = _get_inventory_expiry_status(cart_line.get("expiry_date"))
    if expiry_status == "EXPIRING SOON":
        badges.append("EXPIRING SOON")
    elif expiry_status == "INVALID":
        badges.append("INVALID EXPIRY")
    return badges


def _render_pos_cart_warning_badges(cart_line):
    badges = _get_pos_cart_line_warning_badges(cart_line)
    if not badges:
        return
    badge_html = " ".join(
        f'<span class="pos-cart-warning-badge">{html.escape(badge)}</span>' for badge in badges
    )
    st.markdown(f'<div class="pos-cart-warning-badges">{badge_html}</div>', unsafe_allow_html=True)


def _compute_inventory_health_metrics(df):
    if df is None or df.empty:
        return {
            "total_items": 0,
            "low_stock_items": 0,
            "expiring_soon": 0,
            "out_of_stock": 0,
            "inventory_value": 0.0,
        }
    quantity_series = df["quantity"] if "quantity" in df.columns else df.get("qty", pd.Series(dtype=float))
    reorder_series = df["min_stock_level"] if "min_stock_level" in df.columns else pd.Series([0.0] * len(df))
    expiry_series = df["expiry_date"] if "expiry_date" in df.columns else pd.Series([None] * len(df))
    total_value_series = df["total_value"] if "total_value" in df.columns else pd.Series([0.0] * len(df))
    stock_statuses = [
        _get_inventory_stock_status(quantity_series.iloc[index], reorder_series.iloc[index])
        for index in range(len(df))
    ]
    expiry_statuses = [_get_inventory_expiry_status(expiry_series.iloc[index]) for index in range(len(df))]
    return {
        "total_items": int(len(df)),
        "low_stock_items": int(sum(status == "LOW STOCK" for status in stock_statuses)),
        "expiring_soon": int(sum(status == "EXPIRING SOON" for status in expiry_statuses)),
        "out_of_stock": int(sum(status == "OUT OF STOCK" for status in stock_statuses)),
        "inventory_value": float(total_value_series.fillna(0).sum()),
    }


STOCK_MOVEMENT_TYPE_ALIASES = {
    "in": "STOCK_IN",
    "stock_in": "STOCK_IN",
    "out": "STOCK_OUT",
    "stock_out": "STOCK_OUT",
    "invoice sale": "POS_SALE",
    "pos sale": "POS_SALE",
    "return_refund_restock": "POS_RETURN",
    "pos return": "POS_RETURN",
    "adjustment": "ADJUSTMENT",
    "import": "IMPORT",
    "transfer": "TRANSFER",
}


def _normalize_stock_movement_type(movement_type):
    normalized = str(movement_type or "").strip()
    if not normalized:
        return "ADJUSTMENT"
    lowered = " ".join(
        normalized.lower().replace("/", " ").replace("-", " ").replace("_", " ").split()
    ).replace(" ", "_")
    if lowered in STOCK_MOVEMENT_TYPE_ALIASES:
        return STOCK_MOVEMENT_TYPE_ALIASES[lowered]
    spaced = lowered.replace("_", " ")
    if spaced in STOCK_MOVEMENT_TYPE_ALIASES:
        return STOCK_MOVEMENT_TYPE_ALIASES[spaced]
    return normalized.upper().replace(" ", "_")


def _stock_movement_qty_change(movement_type, quantity):
    normalized_type = _normalize_stock_movement_type(movement_type)
    qty = abs(float(quantity or 0.0))
    if normalized_type in {"STOCK_OUT", "POS_SALE"}:
        return -qty
    return qty


def _insert_stock_movement_record(
    conn,
    *,
    company_key,
    inventory_item_id,
    item_name,
    movement_type,
    quantity,
    previous_qty,
    new_qty,
    created_by,
    branch_id=None,
    reason=None,
    reference=None,
    notes=None,
):
    movement_cursor = conn.execute(
        ensure_insert_sql_returning(
            """
            INSERT INTO stock_movements (
                company_key, branch_id, inventory_item_id, item_name, movement_type,
                quantity, reason, previous_qty, new_qty, created_by, created_at,
                reference, notes, status, approval_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, 'Approved', 'Approved')
            """
        ),
        (
            company_key,
            str(branch_id) if branch_id else None,
            int(inventory_item_id),
            str(item_name or ""),
            _normalize_stock_movement_type(movement_type),
            abs(float(quantity or 0.0)),
            str(reason or "").strip() or None,
            float(previous_qty or 0.0),
            float(new_qty or 0.0),
            str(created_by or ""),
            str(reference or "").strip() or None,
            str(notes or "").strip() or None,
        ),
    )
    return get_inserted_id(movement_cursor)


def _fetch_recent_inventory_movement_rows(conn, company_key, branch_id=None, limit=50):
    query = """
        SELECT
            created_at,
            item_name,
            movement_type,
            quantity,
            previous_qty,
            new_qty,
            created_by,
            reference,
            COALESCE(notes, reason) AS notes
        FROM stock_movements
        WHERE company_key = ?
    """
    params = [company_key]
    if branch_id:
        query += " AND COALESCE(branch_id, '') = ?"
        params.append(str(branch_id))
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(int(limit))
    rows = conn.execute(query, tuple(params)).fetchall()
    movement_rows = []
    for row in rows:
        movement_row = dict(row)
        movement_row["movement_type"] = _normalize_stock_movement_type(movement_row.get("movement_type"))
        movement_row["qty_change"] = _stock_movement_qty_change(
            movement_row.get("movement_type"),
            movement_row.get("quantity"),
        )
        movement_rows.append(movement_row)
    return movement_rows


def _receive_inventory_stock(
    conn,
    company_key,
    role,
    *,
    inventory_item_id,
    qty_received,
    unit_cost=None,
    supplier_name=None,
    batch_number=None,
    expiry_date=None,
    reference_number=None,
    notes=None,
    branch_id=None,
):
    qty_value = float(qty_received or 0.0)
    if qty_value <= 0:
        raise ValueError("Quantity received must be greater than zero.")
    expiry_value = None
    if expiry_date is not None:
        if hasattr(expiry_date, "isoformat"):
            expiry_value = expiry_date.isoformat()
        else:
            expiry_value = str(expiry_date).strip() or None
        if expiry_value and _get_inventory_expiry_validation(expiry_value)["status"] == "INVALID":
            raise ValueError("Invalid expiry date.")

    item_row = conn.execute(
        """
        SELECT id, item_name, qty, cost_price, supplier_name, batch_number, expiry_date
        FROM inventory
        WHERE id = ? AND company_key = ?
        LIMIT 1
        """,
        (int(inventory_item_id), company_key),
    ).fetchone()
    if not item_row:
        raise ValueError("Inventory item could not be found.")

    previous_qty = float(item_row["qty"] or 0.0)
    new_qty = previous_qty + qty_value
    update_fields = ["qty = ?", "updated_at = CURRENT_TIMESTAMP"]
    update_values = [new_qty]
    if unit_cost is not None and float(unit_cost or 0.0) > 0:
        update_fields.append("cost_price = ?")
        update_values.append(float(unit_cost))
    if supplier_name:
        update_fields.append("supplier_name = ?")
        update_values.append(str(supplier_name).strip())
    if batch_number:
        update_fields.append("batch_number = ?")
        update_values.append(str(batch_number).strip())
    if expiry_value:
        update_fields.append("expiry_date = ?")
        update_values.append(expiry_value)
    update_values.extend([int(inventory_item_id), company_key])
    conn.execute(
        f"""
        UPDATE inventory
        SET {", ".join(update_fields)}
        WHERE id = ? AND company_key = ?
        """,
        tuple(update_values),
    )
    movement_reference = str(reference_number or "").strip() or f"RCV-{int(inventory_item_id)}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    movement_notes = str(notes or "").strip()
    if supplier_name:
        movement_notes = (movement_notes + f" | Supplier: {supplier_name}").strip(" |")
    _insert_stock_movement_record(
        conn,
        company_key=company_key,
        inventory_item_id=int(inventory_item_id),
        item_name=item_row["item_name"],
        movement_type="STOCK_IN",
        quantity=qty_value,
        previous_qty=previous_qty,
        new_qty=new_qty,
        created_by=role,
        branch_id=branch_id,
        reason="Receive Stock",
        reference=movement_reference,
        notes=movement_notes or None,
    )
    return {
        "item_name": item_row["item_name"],
        "previous_qty": previous_qty,
        "new_qty": new_qty,
        "reference": movement_reference,
    }


def _filter_inventory_overview_dataframe(overview_df, filter_label):
    if overview_df is None or overview_df.empty or str(filter_label or "All").strip() == "All":
        return overview_df
    label = str(filter_label or "").strip().upper()
    if label == "OK":
        return overview_df[
            (overview_df["stock_status"] == "OK") & (overview_df["expiry_status"] == "OK")
        ]
    if label == "LOW STOCK":
        return overview_df[overview_df["stock_status"] == "LOW STOCK"]
    if label == "OUT OF STOCK":
        return overview_df[overview_df["stock_status"] == "OUT OF STOCK"]
    if label == "EXPIRING SOON":
        return overview_df[overview_df["expiry_status"] == "EXPIRING SOON"]
    if label == "EXPIRED":
        return overview_df[overview_df["expiry_status"] == "EXPIRED"]
    if label == "INVALID EXPIRY":
        return overview_df[overview_df["expiry_status"] == "INVALID"]
    return overview_df


def _render_recent_inventory_movements_panel(company_key, role, branch_id=None):
    if role == "Demo":
        st.caption("Movement history is disabled in Demo mode.")
        return
    with st.expander("Recent Inventory Movements", expanded=False):
        movement_conn = None
        try:
            movement_conn = get_connection()
            ensure_stock_movements_schema_integrity(movement_conn)
            movement_rows = _fetch_recent_inventory_movement_rows(
                movement_conn,
                company_key,
                branch_id=branch_id,
                limit=50,
            )
        except Exception as exc:
            st.warning(build_user_safe_error(exc, role))
            return
        finally:
            if movement_conn:
                movement_conn.close()
        if not movement_rows:
            st.caption("No inventory movements recorded yet.")
            return
        movement_df = pd.DataFrame(
            [
                {
                    "Date/Time": row.get("created_at"),
                    "Item": row.get("item_name"),
                    "Movement Type": row.get("movement_type"),
                    "Qty Change": row.get("qty_change"),
                    "Before Qty": row.get("previous_qty"),
                    "After Qty": row.get("new_qty"),
                    "User/Cashier": row.get("created_by"),
                    "Reference": row.get("reference"),
                    "Notes": row.get("notes"),
                }
                for row in movement_rows
            ]
        )
        st.dataframe(movement_df, use_container_width=True, hide_index=True)


def _prepare_inventory_overview_dataframe(df):
    if df is None or df.empty:
        return df
    enriched = df.copy()
    enriched["stock_status"] = [
        _get_inventory_stock_status(row.get("quantity"), row.get("min_stock_level"))
        for _, row in enriched.iterrows()
    ]
    enriched["expiry_status"] = [
        _get_inventory_expiry_status(row.get("expiry_date")) for _, row in enriched.iterrows()
    ]
    enriched["days_to_expiry"] = [
        _compute_days_to_expiry(row.get("expiry_date")) for _, row in enriched.iterrows()
    ]
    enriched["Status"] = enriched["stock_status"]
    enriched["Expiry Alert"] = [
        _inventory_expiry_status_badge(status) or "OK"
        for status in enriched["expiry_status"]
    ]
    return enriched


def _invalidate_inventory_search_cache():
    _cached_pos_inventory_search_rows.clear()


@st.cache_data(ttl=60)
def _cached_pos_inventory_search_rows(company_key, search_value):
    normalized_search = str(search_value or "").strip()
    if not normalized_search:
        return []
    conn = get_connection()
    try:
        return [
            dict(row) if not isinstance(row, dict) else row
            for row in _pos_inventory_search_rows(conn, company_key, normalized_search)
        ]
    finally:
        conn.close()


def _lookup_inventory_by_barcode(conn, company_key, barcode_value):
    return conn.execute(
        f"""
        SELECT {INVENTORY_POS_LOOKUP_COLUMNS}
        FROM inventory
        WHERE company_key = ? AND barcode = ?
        """,
        (company_key, barcode_value),
    ).fetchone()


def _lookup_inventory_for_pos(conn, company_key, search_value):
    normalized_value = str(search_value or "").strip()
    if not normalized_value:
        return None, None, None

    exact_match = conn.execute(
        f"""
        SELECT {INVENTORY_POS_LOOKUP_COLUMNS}
        FROM inventory
        WHERE company_key = ?
          AND (
              barcode = ?
              OR item_code = ?
              OR LOWER(item_name) = LOWER(?)
              OR LOWER(COALESCE(category, '')) = LOWER(?)
              OR LOWER(COALESCE(brand, '')) = LOWER(?)
          )
        ORDER BY item_name
        LIMIT 1
        """,
        (company_key, normalized_value, normalized_value, normalized_value, normalized_value, normalized_value),
    ).fetchone()
    if exact_match:
        if str(exact_match["barcode"] or "").strip() == normalized_value:
            return exact_match, "barcode", "in_company"
        if str(exact_match["item_code"] or "").strip() == normalized_value:
            return exact_match, "item_code", "in_company"
        return exact_match, "item_name", "in_company"

    fallback_match = conn.execute(
        f"""
        SELECT {INVENTORY_POS_LOOKUP_COLUMNS}
        FROM inventory
        WHERE company_key = ?
          AND (
              LOWER(item_name) LIKE LOWER(?)
              OR LOWER(COALESCE(item_code, '')) LIKE LOWER(?)
              OR COALESCE(barcode, '') LIKE ?
              OR LOWER(COALESCE(category, '')) LIKE LOWER(?)
              OR LOWER(COALESCE(brand, '')) LIKE LOWER(?)
          )
        ORDER BY item_name
        LIMIT 1
        """,
        (
            company_key,
            f"%{normalized_value}%",
            f"%{normalized_value}%",
            f"%{normalized_value}%",
            f"%{normalized_value}%",
            f"%{normalized_value}%",
        ),
    ).fetchone()
    if fallback_match:
        return fallback_match, "manual_search", "in_company"

    other_company_match = conn.execute(
        """
        SELECT id, item_name, item_code, category, brand, qty, price, cost_price, barcode, min_stock_level, company_key
        FROM inventory
        WHERE company_key <> ?
          AND (
              barcode = ?
              OR item_code = ?
              OR LOWER(item_name) = LOWER(?)
              OR LOWER(item_name) LIKE LOWER(?)
              OR LOWER(COALESCE(item_code, '')) LIKE LOWER(?)
              OR COALESCE(barcode, '') LIKE ?
              OR LOWER(COALESCE(category, '')) LIKE LOWER(?)
              OR LOWER(COALESCE(brand, '')) LIKE LOWER(?)
          )
        ORDER BY item_name
        LIMIT 1
        """,
        (
            company_key,
            normalized_value,
            normalized_value,
            normalized_value,
            f"%{normalized_value}%",
            f"%{normalized_value}%",
            f"%{normalized_value}%",
            f"%{normalized_value}%",
            f"%{normalized_value}%",
        ),
    ).fetchone()
    if other_company_match:
        return other_company_match, "other_company", "other_company"
    return None, None, None


def _search_inventory_for_pos(conn, company_key, search_value):
    normalized_value = str(search_value or "").strip()
    if not normalized_value:
        return []
    return conn.execute(
        f"""
        SELECT {INVENTORY_POS_LOOKUP_COLUMNS}
        FROM inventory
        WHERE company_key = ?
          AND (
              LOWER(item_name) LIKE LOWER(?)
              OR LOWER(COALESCE(item_code, '')) LIKE LOWER(?)
              OR COALESCE(barcode, '') LIKE ?
              OR LOWER(item_name) LIKE LOWER(?)
              OR LOWER(COALESCE(item_code, '')) LIKE LOWER(?)
              OR COALESCE(barcode, '') LIKE ?
              OR LOWER(COALESCE(category, '')) LIKE LOWER(?)
              OR LOWER(COALESCE(brand, '')) LIKE LOWER(?)
          )
        ORDER BY
            CASE
                WHEN LOWER(item_name) = LOWER(?) THEN 0
                WHEN COALESCE(barcode, '') = ? THEN 1
                WHEN LOWER(COALESCE(item_code, '')) = LOWER(?) THEN 2
                WHEN LOWER(item_name) LIKE LOWER(?) THEN 3
                WHEN COALESCE(barcode, '') LIKE ? THEN 4
                WHEN LOWER(COALESCE(item_code, '')) LIKE LOWER(?) THEN 5
                ELSE 6
            END,
            item_name
        LIMIT 15
        """,
        (
            company_key,
            f"%{normalized_value}%",
            f"%{normalized_value}%",
            f"%{normalized_value}%",
            f"{normalized_value}%",
            f"{normalized_value}%",
            f"{normalized_value}%",
            f"%{normalized_value}%",
            f"%{normalized_value}%",
            normalized_value,
            normalized_value,
            normalized_value,
            f"{normalized_value}%",
            f"{normalized_value}%",
            f"{normalized_value}%",
        ),
    ).fetchall()


def _pos_inventory_search_rows(conn, company_key, search_value):
    return [_normalize_pos_item_row(row) for row in _search_inventory_for_pos(conn, company_key, search_value)]


STOCK_IMPORT_MAPPING_FIELDS = {
    "item_name": "Item Name",
    "barcode": "Barcode",
    "item_code": "Item Code / SKU",
    "category": "Category",
    "brand": "Brand",
    "supplier_name": "Supplier Name",
    "unit": "Unit",
    "qty": "Quantity",
    "cost_price": "Cost Price",
    "price": "Selling Price",
    "min_stock_level": "Reorder Level",
    "tax_rate": "Tax Rate",
    "warehouse_location": "Shelf / Location",
    "expiry_date": "Expiry Date",
    "batch_number": "Batch Number",
    "vat_category": "VAT Category",
    "description": "Description",
    "is_active": "Active Status",
}


STOCK_IMPORT_COLUMN_CANDIDATES = {
    "item_name": ["item name", "product name", "name", "item", "product"],
    "barcode": ["barcode", "bar code", "ean", "upc", "scan code"],
    "item_code": ["item code", "product code", "code", "sku", "stock code"],
    "category": ["category", "group", "product category"],
    "brand": ["brand", "manufacturer"],
    "supplier_name": ["supplier", "vendor", "supplier name"],
    "unit": ["unit", "uom", "unit of measure", "measure"],
    "qty": ["quantity", "qty", "stock", "opening stock", "stock qty"],
    "cost_price": ["cost price", "cost", "unit cost", "buying price", "purchase price"],
    "price": ["selling price", "sale price", "price", "unit price", "retail price"],
    "min_stock_level": ["reorder level", "min stock", "minimum stock", "min stock level"],
    "tax_rate": ["tax rate", "vat rate", "tax", "vat"],
    "warehouse_location": ["warehouse location", "location", "shelf", "shelf location", "rack"],
    "expiry_date": ["expiry date", "expiration date", "exp date", "expiry"],
    "batch_number": ["batch number", "batch no", "batch", "lot number", "lot no"],
    "vat_category": ["vat category", "tax category", "vat class"],
    "description": ["description", "details", "product description"],
    "is_active": ["active", "is active", "status", "enabled"],
}


def _normalize_import_column_name(column_name):
    normalized = str(column_name or "").strip().lower()
    normalized = normalized.replace("_", " ").replace("-", " ")
    return " ".join(normalized.split())


def _detect_stock_import_columns(columns):
    normalized_columns = {_normalize_import_column_name(column): str(column) for column in columns}
    detected = {}
    for target_field, aliases in STOCK_IMPORT_COLUMN_CANDIDATES.items():
        for alias in aliases:
            if alias in normalized_columns:
                detected[target_field] = normalized_columns[alias]
                break
        if target_field in detected:
            continue
        for normalized_name, original_name in normalized_columns.items():
            if any(alias in normalized_name for alias in aliases):
                detected[target_field] = original_name
                break
    return detected


def _build_stock_import_preview(uploaded_file):
    file_name = str(getattr(uploaded_file, "name", "") or "").strip()
    lower_name = file_name.lower()
    try:
        if lower_name.endswith(".csv"):
            uploaded_file.seek(0)
            preview_df = pd.read_csv(uploaded_file)
            file_type = "csv"
        elif lower_name.endswith(".xlsx"):
            uploaded_file.seek(0)
            preview_df = pd.read_excel(uploaded_file)
            file_type = "xlsx"
        else:
            raise ValueError("Unsupported file format. Please upload an Excel (.xlsx) or CSV (.csv) file.")
    except ImportError as exc:
        if "openpyxl" in str(exc).lower():
            raise ValueError("Excel support is not installed. Please contact the system administrator or upload CSV.") from exc
        raise

    if preview_df is None or preview_df.empty:
        raise ValueError("The uploaded file is empty or has no readable rows.")

    preview_df.columns = [str(column) for column in preview_df.columns]
    detected_columns = _detect_stock_import_columns(preview_df.columns)
    important_columns = ["item_name", "qty", "cost_price", "price"]
    missing_important = [column for column in important_columns if column not in detected_columns]
    return {
        "file_name": file_name or "uploaded_file",
        "file_type": file_type,
        "total_rows": int(len(preview_df.index)),
        "detected_columns": list(preview_df.columns),
        "mapping_suggestion": detected_columns,
        "missing_important_columns": missing_important,
        "preview_rows": preview_df.head(20).fillna("").to_dict(orient="records"),
        "all_rows": preview_df.fillna("").to_dict(orient="records"),
    }


def _parse_import_numeric(value, field_label, required=False):
    normalized = str(value or "").strip()
    if not normalized:
        if required:
            raise ValueError(f"{field_label} is required.")
        return None
    try:
        return float(normalized.replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_label} must be numeric.") from exc


def _parse_import_date(value, field_label):
    normalized = str(value or "").strip()
    if not normalized:
        return None
    parsed = pd.to_datetime(normalized, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"{field_label} must be a valid date.")
    return parsed.date().isoformat()


def _parse_import_bool(value):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return 1
    if normalized in {"1", "true", "yes", "y", "active", "enabled"}:
        return 1
    if normalized in {"0", "false", "no", "n", "inactive", "disabled"}:
        return 0
    raise ValueError("Active Status must be Yes/No, True/False, 1/0, or Active/Inactive.")


def _build_stock_import_row_error(row_number, reasons):
    return {"row_number": row_number, "error_reason": "; ".join(reasons)}


def _validate_stock_import_rows(raw_rows, column_mapping):
    validated_rows = []
    invalid_rows = []
    seen_barcodes = {}
    seen_item_codes = {}
    duplicate_barcode_rows = set()
    duplicate_item_code_rows = set()

    for row_index, raw_row in enumerate(raw_rows, start=2):
        clean_row = {}
        errors = []

        def mapped_value(field_name):
            source_column = column_mapping.get(field_name)
            if not source_column:
                return ""
            return raw_row.get(source_column, "")

        item_name = str(mapped_value("item_name") or "").strip()
        if not item_name:
            errors.append("Item Name is required.")
        clean_row["item_name"] = item_name

        barcode = str(mapped_value("barcode") or "").strip()
        item_code = str(mapped_value("item_code") or "").strip()
        clean_row["barcode"] = barcode
        clean_row["item_code"] = item_code
        clean_row["category"] = str(mapped_value("category") or "").strip()
        clean_row["brand"] = str(mapped_value("brand") or "").strip()
        clean_row["supplier_name"] = str(mapped_value("supplier_name") or "").strip()
        clean_row["unit"] = str(mapped_value("unit") or "").strip() or "pcs"
        clean_row["vat_category"] = str(mapped_value("vat_category") or "").strip()
        clean_row["description"] = str(mapped_value("description") or "").strip()
        clean_row["batch_number"] = str(mapped_value("batch_number") or "").strip()
        clean_row["warehouse_location"] = str(mapped_value("warehouse_location") or "").strip()

        try:
            qty_value = _parse_import_numeric(mapped_value("qty"), "Quantity", required=True)
            if qty_value is not None and qty_value < 0:
                errors.append("Quantity must be zero or greater.")
            clean_row["qty"] = qty_value
        except ValueError as exc:
            errors.append(str(exc))

        try:
            price_value = _parse_import_numeric(mapped_value("price"), "Selling Price", required=True)
            if price_value is not None and price_value < 0:
                errors.append("Selling Price must be zero or greater.")
            clean_row["price"] = price_value
        except ValueError as exc:
            errors.append(str(exc))

        try:
            cost_price_value = _parse_import_numeric(mapped_value("cost_price"), "Cost Price", required=False)
            if cost_price_value is not None and cost_price_value < 0:
                errors.append("Cost Price must be zero or greater.")
            clean_row["cost_price"] = cost_price_value
        except ValueError as exc:
            errors.append(str(exc))

        try:
            reorder_value = _parse_import_numeric(mapped_value("min_stock_level"), "Reorder Level", required=False)
            if reorder_value is not None and reorder_value < 0:
                errors.append("Reorder Level must be zero or greater.")
            clean_row["min_stock_level"] = reorder_value
        except ValueError as exc:
            errors.append(str(exc))

        try:
            tax_rate_value = _parse_import_numeric(mapped_value("tax_rate"), "Tax Rate", required=False)
            if tax_rate_value is not None and tax_rate_value < 0:
                errors.append("Tax Rate must be zero or greater.")
            clean_row["tax_rate"] = tax_rate_value
        except ValueError as exc:
            errors.append(str(exc))

        try:
            clean_row["expiry_date"] = _parse_import_date(mapped_value("expiry_date"), "Expiry Date")
        except ValueError as exc:
            errors.append(str(exc))

        try:
            clean_row["is_active"] = _parse_import_bool(mapped_value("is_active"))
        except ValueError as exc:
            errors.append(str(exc))

        if barcode:
            if barcode in seen_barcodes:
                duplicate_barcode_rows.update({seen_barcodes[barcode], row_index})
                errors.append("Duplicate barcode found in uploaded file.")
            else:
                seen_barcodes[barcode] = row_index
        if item_code:
            if item_code in seen_item_codes:
                duplicate_item_code_rows.update({seen_item_codes[item_code], row_index})
                errors.append("Duplicate item code found in uploaded file.")
            else:
                seen_item_codes[item_code] = row_index

        if errors:
            invalid_rows.append(_build_stock_import_row_error(row_index, errors))
        else:
            clean_row["row_number"] = row_index
            validated_rows.append(clean_row)

    summary = {
        "total_rows": len(raw_rows),
        "valid_rows": len(validated_rows),
        "invalid_rows": len(invalid_rows),
        "duplicate_barcodes": len(duplicate_barcode_rows),
        "duplicate_item_codes": len(duplicate_item_code_rows),
    }
    return validated_rows, invalid_rows, summary


def _generate_inventory_import_reference(company_key):
    normalized_company = str(company_key or "INV").strip().upper().replace(" ", "")
    return "IMP-{company}-{stamp}".format(
        company=normalized_company[:12] or "INV",
        stamp=datetime.now().strftime("%Y%m%d%H%M%S"),
    )


def _find_existing_inventory_for_import(conn, company_key, row_data):
    barcode = str(row_data.get("barcode") or "").strip()
    item_code = str(row_data.get("item_code") or "").strip()
    if barcode:
        existing_row = conn.execute(
            """
            SELECT id, item_name, qty, barcode, item_code
            FROM inventory
            WHERE company_key = ? AND barcode = ?
            LIMIT 1
            """,
            (company_key, barcode),
        ).fetchone()
        if existing_row:
            return existing_row, "barcode"
    if item_code:
        existing_row = conn.execute(
            """
            SELECT id, item_name, qty, barcode, item_code
            FROM inventory
            WHERE company_key = ? AND item_code = ?
            LIMIT 1
            """,
            (company_key, item_code),
        ).fetchone()
        if existing_row:
            return existing_row, "item_code"
    return None, None


def _summarize_stock_import_targets(conn, company_key, validated_rows):
    create_count = 0
    update_count = 0
    for row_data in validated_rows:
        existing_row, _ = _find_existing_inventory_for_import(conn, company_key, row_data)
        if existing_row:
            update_count += 1
        else:
            create_count += 1
    return {
        "total_rows": len(validated_rows),
        "valid_rows": len(validated_rows),
        "items_to_create": create_count,
        "items_that_may_update": update_count,
    }


def _import_validated_stock_rows(conn, company_key, validated_rows, existing_item_behavior):
    result = {
        "import_reference": _generate_inventory_import_reference(company_key),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "posted_opening_value": 0.0,
    }

    inventory_account_id = get_account_id(conn, "Inventory", "Asset")
    cogs_account_id = get_account_id(conn, "Cost of Goods Sold", "Expense")

    for row_data in validated_rows:
        try:
            existing_row, matched_by = _find_existing_inventory_for_import(conn, company_key, row_data)
            quantity_to_apply = max(float(row_data.get("qty") or 0.0), 0.0)
            if existing_row:
                if existing_item_behavior == "skip":
                    result["skipped"] += 1
                    continue
                new_qty = max(float(existing_row["qty"] or 0.0), 0.0) + quantity_to_apply
                conn.execute(
                    """
                    UPDATE inventory
                    SET qty = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND company_key = ?
                    """,
                    (new_qty, int(existing_row["id"]), company_key),
                )
                result["updated"] += 1
                result["posted_opening_value"] += quantity_to_apply * float(row_data.get("cost_price") or 0.0)
                continue

            conn.execute(
                """
                INSERT INTO inventory (
                    company_key, item_name, barcode, item_code, category, brand, supplier_name, unit, qty,
                    cost_price, price, min_stock_level, tax_rate, warehouse_location, expiry_date,
                    batch_number, vat_category, description, is_active, opening_balance,
                    inventory_account_id, cogs_account_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_key,
                    str(row_data.get("item_name") or "").strip(),
                    str(row_data.get("barcode") or "").strip(),
                    str(row_data.get("item_code") or "").strip(),
                    str(row_data.get("category") or "").strip(),
                    str(row_data.get("brand") or "").strip(),
                    str(row_data.get("supplier_name") or "").strip(),
                    str(row_data.get("unit") or "").strip() or "pcs",
                    quantity_to_apply,
                    float(row_data.get("cost_price") or 0.0),
                    float(row_data.get("price") or 0.0),
                    float(row_data.get("min_stock_level") or 0.0),
                    float(row_data.get("tax_rate") or 0.0),
                    str(row_data.get("warehouse_location") or "").strip(),
                    str(row_data.get("expiry_date") or "").strip() or None,
                    str(row_data.get("batch_number") or "").strip(),
                    str(row_data.get("vat_category") or "").strip(),
                    str(row_data.get("description") or "").strip(),
                    int(row_data.get("is_active") if row_data.get("is_active") is not None else 1),
                    quantity_to_apply,
                    inventory_account_id,
                    cogs_account_id,
                ),
            )
            result["created"] += 1
            result["posted_opening_value"] += quantity_to_apply * float(row_data.get("cost_price") or 0.0)
        except Exception as exc:
            result["errors"].append(
                {
                    "row_number": row_data.get("row_number"),
                    "item_name": row_data.get("item_name"),
                    "error_reason": sanitize_error_message(exc),
                }
            )
    result["posted_opening_value"] = round(float(result.get("posted_opening_value") or 0.0), 2)
    conn.execute(
        """
        INSERT INTO inventory_import_batches (
            import_reference, company_key, branch_id, imported_item_count, created_count, updated_count,
            skipped_count, error_count, total_opening_value, imported_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result["import_reference"],
            company_key,
            st.session_state.get("active_branch_id"),
            int(result.get("created", 0) + result.get("updated", 0)),
            int(result.get("created") or 0),
            int(result.get("updated") or 0),
            int(result.get("skipped") or 0),
            int(len(result.get("errors") or [])),
            float(result.get("posted_opening_value") or 0.0),
            str(st.session_state.get("user", {}).get("role") or "System"),
        ),
    )
    return result


def _post_inventory_import_opening_value(conn, company_key, import_reference, role):
    batch_row = conn.execute(
        """
        SELECT id, import_reference, imported_item_count, total_opening_value,
               COALESCE(opening_posted, 0) AS opening_posted,
               opening_posted_entry_id
        FROM inventory_import_batches
        WHERE company_key = ? AND import_reference = ?
        LIMIT 1
        """,
        (company_key, import_reference),
    ).fetchone()
    if not batch_row:
        raise ValueError("Inventory import batch could not be found.")
    if bool(int(batch_row["opening_posted"] or 0)) or batch_row["opening_posted_entry_id"]:
        raise ValueError("Opening inventory accounting has already been posted for this import batch.")

    total_opening_value = round(float(batch_row["total_opening_value"] or 0.0), 2)
    if total_opening_value <= 0:
        raise ValueError("Opening inventory value is zero, so there is nothing to post.")

    entry_id = post_journal_entry(
        company_key=company_key,
        date=datetime.now().date(),
        description=f"Opening inventory import value for {import_reference}",
        reference=import_reference,
        lines=[
            {"account_id": get_account_id(conn, "Inventory", "Asset"), "debit": total_opening_value, "credit": 0},
            {"account_id": get_account_id(conn, "Opening Balance Equity", "Equity"), "debit": 0, "credit": total_opening_value},
        ],
        created_by=role,
        branch_id=st.session_state.get("active_branch_id"),
        source_module="Inventory Import",
        source_table="inventory_import_batches",
        source_type="stock_import_opening_inventory",
        source_id=int(batch_row["id"]),
        approval_status="Posted",
        user_role=role,
        conn=conn,
    )
    conn.execute(
        """
        UPDATE inventory_import_batches
        SET opening_posted = 1,
            opening_posted_entry_id = ?,
            opening_posted_at = CURRENT_TIMESTAMP,
            opening_posted_by = ?
        WHERE id = ?
        """,
        (int(entry_id), str(role or "System"), int(batch_row["id"])),
    )
    log_system_event(
        "INFO",
        "Inventory Import Opening Posting",
        "Posted opening inventory value import_reference={reference} company_key={company_key} amount={amount:.2f} user={user}".format(
            reference=import_reference,
            company_key=company_key,
            amount=total_opening_value,
            user=role,
        ),
    )
    try:
        log_audit_action(
            conn,
            company_key,
            role,
            "Opening Inventory Import Posted",
            "Inventory",
            f"{import_reference} posted for {total_opening_value:,.2f}",
            branch_id=st.session_state.get("active_branch_id"),
            action_type="post",
            document_ref=import_reference,
        )
    except Exception:
        logger.debug("Inventory import opening posting audit logging skipped.", exc_info=True)

    return {
        "entry_id": int(entry_id),
        "import_reference": import_reference,
        "amount": total_opening_value,
        "item_count": int(batch_row["imported_item_count"] or 0),
    }


def _normalize_pos_item_row(item_row):
    if isinstance(item_row, dict):
        return item_row
    if item_row is None:
        return {}
    try:
        return dict(item_row)
    except Exception:
        return {key: item_row[key] for key in item_row.keys()}


def _add_item_to_pos_cart(company_key, item_row):
    item_row = _normalize_pos_item_row(item_row)
    cart_key = f"pos_cart_{company_key}"
    cart = st.session_state.setdefault(cart_key, [])
    item_id = int(item_row["id"])
    item_code = str(item_row.get("item_code") or "")
    tax_rate = float(item_row.get("tax_rate") or 0.0)
    min_stock_level = float(item_row.get("min_stock_level") or 0.0)
    for existing_line in cart:
        existing_inventory_id = existing_line.get("inventory_item_id")
        if existing_inventory_id is not None and int(existing_inventory_id) == item_id:
            existing_line["qty"] += 1
            existing_line["line_total"] = max(
                (existing_line["qty"] * existing_line["price"]) - float(existing_line.get("line_discount") or 0.0),
                0.0,
            )
            return existing_line

    new_line = {
        "inventory_item_id": item_id,
        "item_id": item_id,
        "name": item_row["item_name"],
        "item_name": item_row["item_name"],
        "item_code": item_code or "",
        "barcode": item_row["barcode"] or "",
        "price": float(item_row["price"] or 0.0),
        "cost_price": float(item_row["cost_price"] or 0.0),
        "tax_rate": float(tax_rate or 0.0),
        "available_qty": float(item_row["qty"] or 0.0),
        "min_stock_level": float(min_stock_level or 0.0),
        "expiry_date": item_row.get("expiry_date"),
        "qty": 1,
        "is_manual": False,
        "line_discount_type": "amount",
        "line_discount_value": 0.0,
        "line_discount": 0.0,
        "line_total": float(item_row["price"] or 0.0),
    }
    cart.append(new_line)
    return new_line


def _get_pos_low_stock_warning(cart_line):
    if not cart_line or bool(cart_line.get("is_manual")) or cart_line.get("inventory_item_id") is None:
        return None
    available_qty = float(cart_line.get("available_qty") or 0.0)
    min_stock_level = max(float(cart_line.get("min_stock_level") or 0.0), 0.0)
    remaining_qty = round(available_qty - float(cart_line.get("qty") or 0.0), 2)
    if remaining_qty <= min_stock_level:
        return "Low stock warning: {item} remaining stock will be {qty:,.2f}.".format(
            item=str(cart_line.get("item_name") or cart_line.get("name") or "Item"),
            qty=remaining_qty,
        )
    return None


def _get_pos_cart_discount_state(company_key):
    state_key = f"pos_cart_discount_{company_key}"
    return st.session_state.setdefault(
        state_key,
        {
            "type": "amount",
            "value": 0.0,
            "computed": 0.0,
            "threshold_requires_approval": False,
        },
    )


def _normalize_pos_discount(value, maximum):
    discount = max(float(value or 0.0), 0.0)
    return min(discount, max(float(maximum or 0.0), 0.0))


def _resolve_line_discount_amount(line):
    qty = max(int(line.get("qty") or 0), 1)
    price = max(float(line.get("price") or 0.0), 0.0)
    gross = qty * price
    discount_type = str(line.get("line_discount_type") or "amount").strip().lower()
    discount_value = max(float(line.get("line_discount_value", line.get("line_discount") or 0.0) or 0.0), 0.0)
    if discount_type == "percent":
        discount = gross * (discount_value / 100.0)
    else:
        discount = discount_value
    return _normalize_pos_discount(discount, gross)


def _recalculate_pos_line(line):
    qty = max(int(line.get("qty") or 0), 1)
    price = max(float(line.get("price") or 0.0), 0.0)
    gross = qty * price
    line.setdefault("line_discount_type", "amount")
    if "line_discount_value" not in line:
        line["line_discount_value"] = float(line.get("line_discount") or 0.0)
    discount = _resolve_line_discount_amount(line)
    line["qty"] = qty
    line["price"] = price
    line["line_discount"] = discount
    line["line_total"] = gross - discount
    return line


def _get_pos_cart_summary(company_key):
    cart = st.session_state.setdefault(f"pos_cart_{company_key}", [])
    discount_state = _get_pos_cart_discount_state(company_key)
    item_count = int(sum(int(line.get("qty") or 0) for line in cart))
    subtotal = 0.0
    line_discount_total = 0.0
    tax_total = 0.0
    taxable_bases = []
    for line in cart:
        qty = max(float(line.get("qty") or 0.0), 0.0)
        price = max(float(line.get("price") or 0.0), 0.0)
        gross = qty * price
        discount = _normalize_pos_discount(_resolve_line_discount_amount(line), gross)
        taxable_base = gross - discount
        subtotal += gross
        line_discount_total += discount
        taxable_bases.append(
            {
                "taxable_base": taxable_base,
                "tax_rate": max(float(line.get("tax_rate") or 0.0), 0.0),
            }
        )
    subtotal_after_line_discounts = max(subtotal - line_discount_total, 0.0)
    cart_discount_type = str(discount_state.get("type") or "amount").strip().lower()
    cart_discount_value = max(float(discount_state.get("value") or 0.0), 0.0)
    if cart_discount_type == "percent":
        cart_discount_amount = subtotal_after_line_discounts * (cart_discount_value / 100.0)
    else:
        cart_discount_amount = cart_discount_value
    cart_discount_amount = _normalize_pos_discount(cart_discount_amount, subtotal_after_line_discounts)
    discount_state["computed"] = round(cart_discount_amount, 2)
    total_taxable_base = sum(item["taxable_base"] for item in taxable_bases)
    for item in taxable_bases:
        allocated_cart_discount = 0.0
        if total_taxable_base > 0 and cart_discount_amount > 0:
            allocated_cart_discount = cart_discount_amount * (item["taxable_base"] / total_taxable_base)
        effective_taxable_base = max(item["taxable_base"] - allocated_cart_discount, 0.0)
        tax_total += effective_taxable_base * (item["tax_rate"] / 100.0)
    discount_total = line_discount_total + cart_discount_amount
    grand_total = round((subtotal - discount_total) + tax_total, 2)
    return {
        "item_count": item_count,
        "line_count": len(cart),
        "subtotal": round(subtotal, 2),
        "line_discount_total": round(line_discount_total, 2),
        "cart_discount_total": round(cart_discount_amount, 2),
        "discount_total": round(discount_total, 2),
        "tax_total": round(tax_total, 2),
        "grand_total": grand_total,
    }


def _import_sales_from_excel(conn, company_key, doc_type, file_obj, created_by):
    imported_df = pd.read_excel(file_obj)
    if imported_df.empty:
        return 0

    column_map = {column.lower().strip(): column for column in imported_df.columns}
    required = ["date", "description", "amount"]
    missing = [column for column in required if column not in column_map]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    changed_rows = 0
    ledger = "Sales Revenue" if doc_type == "Sales" else "Accounts Payable"
    branch_id = st.session_state.get("active_branch_id")
    for _, row in imported_df.iterrows():
        row_id = row[column_map["id"]] if "id" in column_map and not pd.isna(row[column_map["id"]]) else None
        tx_date = pd.to_datetime(row[column_map["date"]], errors="coerce")
        narration = str(row[column_map["description"]]).strip()
        amount = float(row[column_map["amount"]] or 0)
        if pd.isna(tx_date) or not narration or amount <= 0:
            continue
        tx_date_str = tx_date.date().isoformat()
        if row_id is not None:
            existing = conn.execute(
                "SELECT id FROM vouchers WHERE company_key = ? AND id = ?",
                (company_key, int(row_id)),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE vouchers
                    SET date = ?, v_type = ?, ledger = ?, credit = ?, narration = ?, created_by = ?, branch_id = ?
                    WHERE company_key = ? AND id = ?
                    """,
                    (tx_date_str, doc_type, ledger, amount, narration, created_by, branch_id, company_key, int(row_id)),
                )
                changed_rows += 1
                continue
        existing = conn.execute(
            """
            SELECT id FROM vouchers
            WHERE company_key = ? AND v_type = ? AND date = ? AND narration = ?
            """,
            (company_key, doc_type, tx_date_str, narration),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE vouchers
                SET credit = ?, created_by = ?, branch_id = ?
                WHERE company_key = ? AND id = ?
                """,
                (amount, created_by, branch_id, company_key, existing["id"]),
            )
            changed_rows += 1
            continue
        conn.execute(
            """
            INSERT INTO vouchers (company_key, branch_id, date, v_type, ledger, credit, narration, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (company_key, branch_id, tx_date_str, doc_type, ledger, amount, narration, created_by),
        )
        changed_rows += 1
    return changed_rows


def get_financial_metrics():
    conn = get_connection()
    try:
        revenue = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM sales_invoices WHERE status = 'Paid'"
        ).fetchone()[0] or 0.0
        payables = conn.execute(
            """
            SELECT COALESCE(SUM(jl.credit - jl.debit), 0)
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE lower(COALESCE(NULLIF(c.name, ''), NULLIF(c.account_name, ''), '')) LIKE 'accounts payable%'
            """
        ).fetchone()[0] or 0.0
        has_data = (
            (conn.execute("SELECT COUNT(*) FROM sales_invoices").fetchone()[0] or 0)
            + (conn.execute("SELECT COUNT(*) FROM bills").fetchone()[0] or 0)
        ) > 0
    finally:
        conn.close()

    metrics = {
        "revenue": float(revenue),
        "payables": float(payables),
        "net_health": float(revenue) - float(payables),
        "has_data": has_data,
    }
    chart_df = pd.DataFrame(
        {"Amount": [metrics["revenue"], metrics["payables"]]},
        index=["Income", "Expenses"],
    )
    return metrics, chart_df


def get_demo_financial_metrics():
    metrics = {
        "revenue": 12500.0,
        "payables": 4200.0,
        "net_health": 8300.0,
        "has_data": True,
    }
    chart_df = pd.DataFrame(
        {"Amount": [metrics["revenue"], metrics["payables"]]},
        index=["Income", "Expenses"],
    )
    return metrics, chart_df


def get_system_health_snapshot():
    conn = get_connection()
    try:
        company_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] or 0
        active_licenses = conn.execute(
            "SELECT COUNT(*) FROM companies WHERE status = 'Active'"
        ).fetchone()[0] or 0
        db_status = "Online"
    except Exception:
        company_count = 0
        active_licenses = 0
        db_status = "Offline"
    finally:
        conn.close()

    return {
        "api_status": "Operational",
        "db_status": db_status,
        "company_count": company_count,
        "active_licenses": active_licenses,
    }


def get_deployment_readiness_diagnostics():
    conn = None
    recommendations = []
    diagnostics = {
        "database_backend": "SQLite",
        "db_label": "Unavailable",
        "company_count": 0,
        "cloud_vault_status": "Unknown",
        "runtime_db_valid": False,
        "last_local_backup": "Unknown",
        "last_cloud_backup": "Unknown",
        "cloud_backup_count": "Unknown",
        "schema_self_heal_status": "Unknown",
        "journal_integrity_status": "Unknown",
        "trial_balance_balanced": "Unknown",
        "pos_source_document_control": "Unknown",
        "sqlite_concurrency_warning": "SQLite is suitable for pilot/small-client use but not high-concurrency enterprise deployment.",
        "recommended_action": "Review diagnostics before client rollout.",
    }
    try:
        db_health = get_database_health_snapshot()
        persistence = get_persistence_diagnostics()
        postgres_diag = get_postgres_readiness_diagnostics()
        schema_diag = get_schema_manifest_diagnostics()
        diagnostics.update(
            {
                "database_backend": postgres_diag.get("active_backend", "sqlite").upper(),
                "db_label": db_health.get("db_path") or "SQLite runtime database",
                "company_count": int(db_health.get("company_count") or 0),
                "cloud_vault_status": str(persistence.get("latest_cloud_backup_status") or "Unknown"),
                "runtime_db_valid": bool(db_health.get("structural_valid")),
                "last_local_backup": str(persistence.get("last_local_backup_timestamp") or persistence.get("latest_local_backup_status") or "Unknown"),
                "last_cloud_backup": str(persistence.get("last_cloud_backup_timestamp") or persistence.get("latest_cloud_backup_status") or "Unknown"),
                "cloud_backup_count": str(persistence.get("cloud_backup_count") if persistence.get("cloud_backup_count") is not None else "Unknown"),
                "schema_self_heal_status": "OK" if schema_diag.get("ok") else "Needs Attention",
                "sqlite_concurrency_warning": postgres_diag.get("sqlite_concurrency_warning") or "",
            }
        )
        if postgres_diag.get("switch_blocked"):
            recommendations.append("PostgreSQL/Supabase migration is not ready; review backend readiness diagnostics.")
        if not diagnostics["runtime_db_valid"]:
            recommendations.append("Repair or restore the runtime database before deployment.")
        if not schema_diag.get("ok"):
            recommendations.append("Run startup migration/self-heal and review missing schema columns.")

        conn = get_connection()
        company_row = None
        if conn:
            company_row = conn.execute(
                "SELECT key FROM companies ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if company_row:
            company_key = company_row["key"]
            trust = get_reporting_trust_diagnostics(company_key, conn=conn)
            posting_diag = get_unified_posting_engine_diagnostics(company_key, conn=conn)
            diagnostics["journal_integrity_status"] = "OK" if not trust.get("reconciliation", {}).get("unbalanced_journal_count") else "Unbalanced Journals"
            diagnostics["trial_balance_balanced"] = "Yes" if trust.get("trial_balance", {}).get("balanced") else "No"
            controlled_tables = set(posting_diag.get("controlled_source_tables") or [])
            diagnostics["pos_source_document_control"] = "Protected" if "pos_sales" in controlled_tables else "Not Protected"
            if diagnostics["trial_balance_balanced"] != "Yes":
                recommendations.append("Resolve Trial Balance imbalance before deployment.")
            if diagnostics["pos_source_document_control"] != "Protected":
                recommendations.append("Enable POS sale source-document controls before POS rollout.")
        else:
            diagnostics["journal_integrity_status"] = "No company data"
            diagnostics["trial_balance_balanced"] = "No company data"
            diagnostics["pos_source_document_control"] = "Protected by engine configuration"
        if not recommendations:
            recommendations.append("Proceed with pilot deployment monitoring.")
    except Exception as exc:
        diagnostics["recommended_action"] = build_user_safe_error(exc, st.session_state.get("user", {}).get("role"))
        return diagnostics
    finally:
        if conn:
            conn.close()
    diagnostics["recommended_action"] = " ".join(recommendations)
    return diagnostics


def _demo_notice():
    st.info("Enterprise Demo Mode is active. These values are virtual and are not written to the vault database.")


def format_money(value):
    return f"{get_currency_symbol()} {convert_amount_from_base(value):,.2f}"


def show_vault_dashboard_module(demo_on):
    st.subheader("EKA Vault / Dashboard")
    metrics, chart_df = get_demo_financial_metrics() if demo_on else get_financial_metrics()

    with st.container():
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Revenue", format_money(metrics["revenue"]), "Healthy")
        col2.metric("Outstanding Payables", format_money(metrics["payables"]), "Controlled", delta_color="inverse")
        col3.metric("Net Health", format_money(metrics["net_health"]), "Good")
        if not metrics["has_data"] and not demo_on:
            st.caption("Add your first invoice to activate vault metrics.")

    st.bar_chart(chart_df)

    if demo_on:
        _demo_notice()


def show_company_registration_module():
    st.subheader("New Company Registration")
    with st.form("company_registration_form"):
        company_name = st.text_input("Company Name")
        admin_name = st.text_input("Admin Contact")
        contact_email = st.text_input("Contact Email")
        duration_months = st.number_input("Subscription Length (Months)", min_value=1, value=12)
        submitted = st.form_submit_button("Register Company")

        if submitted and company_name and admin_name:
            expiry_date = datetime.now() + relativedelta(months=+int(duration_months))
            conn = get_connection()
            try:
                company_key = (
                    f"EKA-REG-"
                    f"{''.join(random.choices(string.ascii_uppercase, k=4))}-"
                    f"{''.join(random.choices(string.digits, k=4))}"
                )
                create_company_record(
                    conn=conn,
                    company_key=company_key,
                    company_name=company_name,
                    subscription_expiry=expiry_date.date().isoformat(),
                    status="Active",
                    deployment_status="Live",
                    contact_email=contact_email,
                )
                conn.commit()
                backup_result = force_backup_after_company_creation(
                    company_name=company_name,
                    company_key=company_key,
                    logger_instance=logger,
                )
                if backup_result.get("ok"):
                    st.success(f"{company_name} registered successfully.")
                else:
                    st.warning(
                        f"{company_name} registered, but post-create backup needs attention: {backup_result.get('reason')}"
                    )
                log_system_event("INFO", "New Company Registration", f"Registered company: {company_name}")
                st.rerun()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name, contact_email, status, subscription_expiry FROM companies ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()

    if rows:
        st.dataframe(
            format_currency_dataframe(pd.DataFrame(rows, columns=["Company Name", "Contact Email", "Status", "Subscription Expiry"])),
            use_container_width=True,
        )
    else:
        st.caption("No companies registered yet.")


def show_system_health_module():
    st.subheader("System Health & Logs")
    snapshot = get_system_health_snapshot()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("API Status", snapshot["api_status"])
    col2.metric("Database Status", snapshot["db_status"])
    col3.metric("Companies", str(snapshot["company_count"]))
    col4.metric("Active Licenses", str(snapshot["active_licenses"]))

    deployment = get_deployment_readiness_diagnostics()
    st.subheader("Deployment Readiness")
    diag_rows = [
        {"Check": "Database Backend", "Status": deployment["database_backend"], "Detail": deployment["db_label"]},
        {"Check": "Runtime DB Valid", "Status": "Yes" if deployment["runtime_db_valid"] else "No", "Detail": ""},
        {"Check": "Company Count", "Status": str(deployment["company_count"]), "Detail": ""},
        {"Check": "Cloud Vault", "Status": deployment["cloud_vault_status"], "Detail": ""},
        {"Check": "Last Local Backup", "Status": deployment["last_local_backup"], "Detail": ""},
        {"Check": "Last Cloud Backup", "Status": deployment["last_cloud_backup"], "Detail": ""},
        {"Check": "Cloud Backup Count", "Status": deployment["cloud_backup_count"], "Detail": ""},
        {"Check": "Schema Self-Heal", "Status": deployment["schema_self_heal_status"], "Detail": ""},
        {"Check": "Journal Integrity", "Status": deployment["journal_integrity_status"], "Detail": ""},
        {"Check": "Trial Balance", "Status": deployment["trial_balance_balanced"], "Detail": ""},
        {"Check": "POS Source Control", "Status": deployment["pos_source_document_control"], "Detail": "source_table=pos_sales"},
    ]
    st.dataframe(pd.DataFrame(diag_rows), use_container_width=True, hide_index=True)
    st.warning(deployment["sqlite_concurrency_warning"])
    st.caption(deployment["recommended_action"])

    conn = get_connection()
    try:
        logs = conn.execute(
            "SELECT timestamp, level, module_name, message FROM system_logs ORDER BY id DESC LIMIT 50"
        ).fetchall()
    finally:
        conn.close()

    if logs:
        logs_df = pd.DataFrame(logs, columns=["Timestamp", "Level", "Module", "Message"])
        st.dataframe(format_currency_dataframe(logs_df), use_container_width=True)
        excel_bin = get_excel_bin(logs_df)
        if excel_bin:
            st.download_button("Export Logs", data=excel_bin, file_name="eka_gatekeeper_logs.xlsx")
    else:
        st.caption("System logs will appear here after activity begins.")


def show_license_renewal_module():
    st.subheader("Renew License")
    conn = get_connection()
    try:
        companies = conn.execute(
            "SELECT id, company_name, status, subscription_expiry FROM companies ORDER BY company_name"
        ).fetchall()
    finally:
        conn.close()

    if not companies:
        st.info("No companies are available for renewal yet.")
        return

    companies_df = pd.DataFrame(companies, columns=["ID", "Company Name", "Status", "Subscription Expiry"])
    st.dataframe(format_currency_dataframe(companies_df), use_container_width=True)

    selected_name = st.selectbox("Select Company", companies_df["Company Name"].tolist())
    duration_months = st.number_input("Extend By (Months)", min_value=1, value=12, key="renew_duration_months")

    if st.button("Renew License", key="renew_license_action"):
        selected_row = companies_df.loc[companies_df["Company Name"] == selected_name].iloc[0]
        existing_expiry = selected_row["Subscription Expiry"]
        base_date = datetime.now()
        if existing_expiry:
            try:
                base_date = datetime.fromisoformat(str(existing_expiry))
            except ValueError:
                base_date = datetime.now()
        new_expiry = base_date + relativedelta(months=+int(duration_months))

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE companies SET subscription_expiry = ?, status = 'Active' WHERE id = ?",
                (new_expiry.date().isoformat(), int(selected_row["ID"])),
            )
            conn.commit()
            st.success(f"License renewed for {selected_name} until {new_expiry.date().isoformat()}.")
            log_system_event("INFO", "Renew License", f"Renewed license for {selected_name}")
            st.rerun()
        finally:
            conn.close()


def show_sales_invoices_page(conn, demo_on):
    st.subheader("Sales Invoices")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [{"Customer Name": "Accra Retail Ltd", "Amount": 12500.0, "Status": "Paid", "Date": datetime.now().date().isoformat()}]
        )
        st.dataframe(format_currency_dataframe(demo_df), use_container_width=True)
        return

    with st.form("sales_invoice_form"):
        customer_name = st.text_input("Customer Name")
        amount = st.number_input("Amount (GHS)", min_value=0.0, value=0.0)
        status = st.selectbox("Status", ["Paid", "Pending", "Draft"])
        invoice_date = st.date_input("Date", value=datetime.now().date())
        submitted = st.form_submit_button("Save Invoice")
        if submitted and customer_name and amount > 0:
            conn.execute(
                "INSERT INTO sales_invoices (customer_name, amount, status, date) VALUES (?, ?, ?, ?)",
                (customer_name, amount, status, invoice_date.isoformat()),
            )
            conn.commit()
            log_system_event("INFO", "Sales Invoices", f"Saved invoice for {customer_name}")
            st.success("Invoice saved.")
            st.rerun()

    rows = conn.execute("SELECT customer_name, amount, status, date FROM sales_invoices ORDER BY date DESC, id DESC").fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["Customer Name", "Amount", "Status", "Date"])
        st.dataframe(format_currency_dataframe(df), use_container_width=True)
    else:
        st.caption("No invoices yet.")


def show_accounts_payable_page(conn, demo_on):
    st.subheader("Accounts Payable")
    st.caption("Legacy notice: `accounts_payable` is now read-only. New supplier liabilities are created as bills and posted to the journal.")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [{"Supplier Name": "Tema Supplier Co.", "Amount": 4200.0, "Status": "Unpaid", "Date": datetime.now().date().isoformat()}]
        )
        st.dataframe(format_currency_dataframe(demo_df), use_container_width=True)
        return

    company_key = (
        st.session_state.get("company_id")
        or st.session_state.get("user", {}).get("key")
        or st.session_state.get("user", {}).get("company_key")
    )
    role = st.session_state.get("user", {}).get("role", "System")
    branch_id = st.session_state.get("active_branch_id")
    if not company_key:
        st.warning("No active company was found for Accounts Payable.")
        return

    expense_account_options = get_purchase_expense_account_options(company_key, conn=conn)

    with st.form("accounts_payable_form"):
        supplier_name = st.text_input("Supplier Name")
        purchase_classification = st.selectbox("Purchase Classification", PURCHASE_CLASSIFICATION_OPTIONS)
        amount = st.number_input("Amount (GHS)", min_value=0.0, value=0.0)
        input_vat_rate = st.number_input("Input VAT Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0)
        status = st.selectbox("Bill Status", ["Pending", "Received"])
        payment_method = st.selectbox("Payment Method", ["Cash", "Bank", "Mobile Money"], disabled=status != "Received")
        posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=3)
        expense_account_name = None
        asset_name = ""
        asset_category = ""
        if purchase_classification == "Expense Purchase":
            expense_account_name = st.selectbox("Expense Account", expense_account_options)
        elif purchase_classification == "Fixed Asset Purchase":
            asset_name = st.text_input("Asset Name")
            asset_category = st.selectbox("Asset Category", FIXED_ASSET_PURCHASE_CATEGORIES)
        description = st.text_input("Description")
        payable_date = st.date_input("Bill Date", value=datetime.now().date())
        submitted = st.form_submit_button("Create Bill")
        if submitted and supplier_name and amount > 0:
            supplier_id = _get_or_create_party(conn, "suppliers", company_key, supplier_name.strip())
            bill_number = f"BILL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            input_vat = round(float(amount or 0.0) * float(input_vat_rate or 0.0) / 100.0, 2)
            cursor = conn.execute(
                ensure_insert_sql_returning(
                    """
                    INSERT INTO bills (
                        company_key, supplier_id, bill_number, bill_date, due_date, status, approval_status,
                        amount, input_vat, purchase_classification, payment_method, expense_account_name, asset_name,
                        asset_category, currency, description, created_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                    """
                ),
                (
                    company_key,
                    supplier_id,
                    bill_number,
                    payable_date.isoformat(),
                    payable_date.isoformat(),
                    status,
                    posting_state,
                    amount,
                    input_vat,
                    _normalize_purchase_classification(purchase_classification),
                    payment_method if status == "Received" else None,
                    expense_account_name if purchase_classification == "Expense Purchase" else None,
                    asset_name.strip() or None,
                    asset_category or None,
                    description.strip() or f"{purchase_classification} bill",
                    role,
                ),
            )
            bill_id = get_inserted_id(cursor)
            if posting_state == "Posted":
                journal_lines, _ = build_purchase_journal_lines(
                    conn,
                    company_key,
                    classification=purchase_classification,
                    amount=amount,
                    input_vat=input_vat,
                    status=status,
                    payment_method=payment_method,
                    expense_account_name=expense_account_name,
                )
                post_journal_entry(
                    company_key=company_key,
                    date=payable_date,
                    description=description.strip() or f"{purchase_classification} bill for {supplier_name.strip()}",
                    reference=bill_number,
                    lines=journal_lines,
                    created_by=role,
                    branch_id=branch_id,
                    supplier_id=supplier_id,
                    source_module="Accounts Payable",
                    source_table="bills",
                    source_type="Bill",
                    source_id=bill_id,
                    approval_status="Posted",
                    user_role=role,
                    conn=conn,
                )
            conn.commit()
            log_system_event("INFO", "Accounts Payable", f"Created bill {bill_number} for {supplier_name}")
            if posting_state == "Posted":
                st.success("Bill created and posted to the journal.")
            else:
                st.success("Bill created without ledger impact. Move Posting State to Posted when it is approved.")
            st.rerun()

    rows = conn.execute(
        """
        SELECT b.bill_number, b.bill_date, s.id AS supplier_id, s.name AS supplier_name, b.description, b.amount, b.status
        FROM bills b
        JOIN suppliers s ON s.id = b.supplier_id
        WHERE b.company_key = ?
        ORDER BY date(b.bill_date) DESC, b.id DESC
        """,
        (company_key,),
    ).fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["Bill Number", "Date", "Supplier ID", "Supplier Name", "Description", "Amount", "Status"])
        df["Supplier Balance"] = df["Supplier ID"].map(lambda supplier_id: get_supplier_balance(company_key, int(supplier_id), conn=conn))
        df = df.drop(columns=["Supplier ID"])
        st.dataframe(format_currency_dataframe(df), use_container_width=True)
        aging_rows = get_ap_aging_report(company_key, as_of_date=datetime.now().date())
        if aging_rows:
            st.markdown("Supplier Aging")
            st.dataframe(format_currency_dataframe(pd.DataFrame(aging_rows)), use_container_width=True, hide_index=True)
    else:
        st.caption("No bills created yet.")


def show_create_bill_page(company_key):
    conn = get_connection()
    try:
        demo_on = st.session_state.get("demo_mode", False)
        render_ui_standard_styles()
        page_header("Create Bill")
        if demo_on:
            _demo_notice()
            return

        role = st.session_state.get("user", {}).get("role", "System")
        branch_id = st.session_state.get("active_branch_id")
        if not company_key:
            st.warning("No active company was found.")
            return
        if not require_permission(
            role,
            "create_bill",
            action_label="create bills",
            company_key=company_key,
            conn=conn,
            branch_id=branch_id,
        ):
            return

        suppliers = conn.execute("SELECT id, name FROM suppliers WHERE company_key = ? ORDER BY name", (company_key,)).fetchall()
        supplier_options = [""] + [row["name"] for row in suppliers]
        expense_account_options = get_purchase_expense_account_options(company_key, conn=conn)

        # Initialize items in session state
        if "bill_items" not in st.session_state or not isinstance(st.session_state.bill_items, list):
            st.session_state.bill_items = [{"item_name": "", "quantity": 1.0, "unit_price": 0.0}]

        # Convert to dataframe for editing
        items_df = pd.DataFrame(st.session_state.bill_items)
        if items_df.empty:
            items_df = pd.DataFrame(columns=["item_name", "quantity", "unit_price"])

        edited_df = st.data_editor(
            items_df,
            column_config={
                "item_name": st.column_config.TextColumn("Item Name", width="large"),
                "quantity": st.column_config.NumberColumn("Quantity", min_value=0.0, step=0.01),
                "unit_price": st.column_config.NumberColumn("Unit Price", min_value=0.0, step=0.01),
            },
            hide_index=True,
            num_rows="dynamic",
            on_change=save_bill_state,
            key="bill_items_editor"
        )

        # Calculate totals
        valid_rows = edited_df['item_name'].fillna('').str.strip() != ''
        total_amount = (edited_df.loc[valid_rows, 'quantity'].fillna(0) * edited_df.loc[valid_rows, 'unit_price'].fillna(0)).sum()

        st.markdown(f"**Total Amount: GHS {total_amount:.2f}**")

        with card_container():
            with st.form("create_bill_form"):
                supplier_name = st.selectbox("Supplier", supplier_options)
                bill_date = st.date_input("Bill Date", value=datetime.now().date())
                purchase_classification = st.selectbox("Purchase Classification", PURCHASE_CLASSIFICATION_OPTIONS)
                input_vat_rate = st.number_input("Input VAT Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0)
                status = st.selectbox("Payment Status", ["Pending", "Received"])
                payment_method = st.selectbox("Payment Method", ["Cash", "Bank", "Mobile Money"], disabled=status != "Received")
                posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=1)
                expense_account_name = None
                asset_name = ""
                asset_category = ""
                if purchase_classification == "Expense Purchase":
                    expense_account_name = st.selectbox("Expense Account", expense_account_options)
                elif purchase_classification == "Fixed Asset Purchase":
                    asset_name = st.text_input("Asset Name")
                    asset_category = st.selectbox("Asset Category", FIXED_ASSET_PURCHASE_CATEGORIES)
                description = st.text_input("Description")
                submitted = st.form_submit_button("Submit")
        
            if submitted:
                if not require_permission(
                    role,
                    "create_bill",
                    action_label="create bills",
                    company_key=company_key,
                    conn=conn,
                    branch_id=branch_id,
                ):
                    return
                if not supplier_name:
                    st.error("Supplier is required.")
                    return
                valid_items = _normalize_bill_items(edited_df)
                if not valid_items:
                    st.error("At least one valid item is required.")
                    return
                st.session_state.bill_items = valid_items
                total_amount = sum(item["quantity"] * item["unit_price"] for item in valid_items)
                if total_amount <= 0:
                    st.error("Total amount must be greater than 0.")
                    return

                supplier_id = next((row["id"] for row in suppliers if row["name"] == supplier_name), None)
                if not supplier_id:
                    st.error("Invalid supplier.")
                    return

                bill_number = f"BILL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                input_vat = round(total_amount * float(input_vat_rate or 0.0) / 100.0, 2)

                cursor = conn.execute(
                    ensure_insert_sql_returning(
                        """
                        INSERT INTO bills (
                            company_key, supplier_id, bill_number, bill_date, due_date, status, approval_status,
                            amount, input_vat, purchase_classification, payment_method, expense_account_name, asset_name,
                            asset_category, currency, description, created_by
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                        """
                    ),
                    (
                        company_key,
                        supplier_id,
                        bill_number,
                        bill_date.isoformat(),
                        bill_date.isoformat(),
                        status,
                        posting_state,
                        total_amount,
                        input_vat,
                        _normalize_purchase_classification(purchase_classification),
                        payment_method if status == "Received" else None,
                        expense_account_name if purchase_classification == "Expense Purchase" else None,
                        asset_name.strip() or None,
                        asset_category or None,
                        description.strip() or f"{purchase_classification} bill",
                        role,
                    ),
                )
                bill_id = get_inserted_id(cursor)

                # Insert bill lines
                for item in valid_items:
                    line_total = item["quantity"] * item["unit_price"]
                    conn.execute(
                        """
                        INSERT INTO bill_lines (bill_id, item_name, quantity, unit_price, line_total)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (bill_id, item["item_name"].strip(), item["quantity"], item["unit_price"], line_total),
                    )

                if posting_state == "Posted":
                    if not require_permission(
                        role,
                        "post_accounting_document",
                        action_label="post accounting documents",
                        company_key=company_key,
                        conn=conn,
                        branch_id=branch_id,
                    ):
                        conn.rollback()
                        return
                    journal_lines, _ = build_purchase_journal_lines(
                        conn,
                        company_key,
                        classification=purchase_classification,
                        amount=total_amount,
                        input_vat=input_vat,
                        status=status,
                        payment_method=payment_method,
                        expense_account_name=expense_account_name,
                    )
                    post_journal_entry(
                        company_key=company_key,
                        date=bill_date,
                        description=description.strip() or f"{purchase_classification} bill for {supplier_name}",
                        reference=bill_number,
                        lines=journal_lines,
                        created_by=role,
                        branch_id=branch_id,
                        supplier_id=supplier_id,
                        source_module="Create Bill",
                        source_table="bills",
                        source_type="Bill",
                        source_id=bill_id,
                        approval_status="Posted",
                        user_role=role,
                        conn=conn,
                    )

                conn.commit()
                log_system_event("INFO", "Create Bill", f"Created bill {bill_number} for {supplier_name}")
                if posting_state == "Posted":
                    st.success(f"Bill created and posted successfully with ID {bill_id}.")
                else:
                    st.success(f"Bill created with ID {bill_id}. Accounting impact will begin when Posting State becomes Posted.")
                # Reset items
                st.session_state.bill_items = [{"item_name": "", "quantity": 1.0, "unit_price": 0.0}]
                st.rerun()
    finally:
        conn.close()


def show_chart_of_accounts_page(conn, demo_on):
    st.subheader("Chart of Accounts")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [
                {"Account Name": "Sales Revenue", "Account Type": "Income", "Balance": 12500.0},
                {"Account Name": "Accounts Payable", "Account Type": "Liability", "Balance": 4200.0},
            ]
        )
        st.dataframe(format_currency_dataframe(demo_df), use_container_width=True)
        return

    with st.form("chart_of_accounts_form"):
        account_name = st.text_input("Account Name")
        account_type = st.selectbox("Account Type", ["Asset", "Liability", "Equity", "Income", "Expense"])
        balance = st.number_input("Opening Balance (GHS)", value=0.0)
        submitted = st.form_submit_button("Add Account")
        if submitted and account_name:
            conn.execute(
                "INSERT INTO chart_of_accounts (account_name, account_type, balance) VALUES (?, ?, ?)",
                (account_name, account_type, balance),
            )
            conn.commit()
            log_system_event("INFO", "Chart of Accounts", f"Added account: {account_name}")
            st.success("Account saved.")
            st.rerun()

    rows = execute_portable_query(
        conn,
        "SELECT account_name, account_type, balance FROM chart_of_accounts ORDER BY account_name",
    ).fetchall()
    if rows:
        df = pd.DataFrame(rows_to_dicts(rows))
        df = df.rename(columns={"account_name": "Account Name", "account_type": "Account Type", "balance": "Balance"})
        st.dataframe(format_currency_dataframe(df), use_container_width=True)
    else:
        st.caption("No chart of accounts records yet.")


def show_vouchers_page(conn, demo_on):
    st.subheader("Vouchers")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [{"Narration": "Demo voucher", "Amount": 12500.0, "Reference": "DEMO-001", "Date": datetime.now().date().isoformat()}]
        )
        st.dataframe(format_currency_dataframe(demo_df), use_container_width=True)
        return

    with st.form("voucher_form"):
        narration = st.text_area("Narration")
        amount = st.number_input("Amount (GHS)", min_value=0.0, value=0.0)
        ref_no = st.text_input("Reference Number")
        voucher_date = st.date_input("Date", value=datetime.now().date())
        submitted = st.form_submit_button("Post Voucher")
        if submitted and narration and amount > 0:
            try:
                company_key = st.session_state.get("company_id") or st.session_state.get("user", {}).get("key")
                legacy_voucher_id = _create_legacy_voucher_if_enabled(
                    conn,
                    company_key,
                    st.session_state.get("active_branch_id"),
                    voucher_date.isoformat(),
                    "Journal",
                    "Journal",
                    amount,
                    st.session_state.get("user", {}).get("role", "System"),
                    narration=narration,
                    reference_no=ref_no,
                )
                post_journal_entry(
                    company_key=company_key,
                    date=voucher_date,
                    description=narration,
                    reference=ref_no or (f"VCH-{legacy_voucher_id}" if legacy_voucher_id else f"JRN-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
                    lines=_voucher_posting_lines(conn, "Journal", amount),
                    created_by=st.session_state.get("user", {}).get("role", "System"),
                    branch_id=st.session_state.get("active_branch_id"),
                    source_module="Vouchers" if legacy_voucher_id else "Journal Voucher",
                    source_table="vouchers" if legacy_voucher_id else "journal_entries",
                    source_id=int(legacy_voucher_id) if legacy_voucher_id else None,
                    conn=conn,
                )
                conn.commit()
                log_system_event("INFO", "Vouchers", f"Posted voucher: {ref_no or narration}")
                st.success("Voucher saved.")
                st.rerun()
            except Exception as exc:
                conn.rollback()
                st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))

    rows = get_recent_accounting_activity(
        st.session_state.get("company_id") or st.session_state.get("user", {}).get("key"),
        branch_id=st.session_state.get("active_branch_id"),
        limit=50,
        conn=conn,
    )
    if rows:
        df = pd.DataFrame(
            [
                {
                    "Narration": row.get("description"),
                    "Amount": row.get("amount", 0.0),
                    "Reference": row.get("reference"),
                    "Date": row.get("date"),
                }
                for row in rows
            ]
        )
        st.dataframe(format_currency_dataframe(df), use_container_width=True)
    else:
        st.caption("No vouchers yet.")


# ==========================================
# ONBOARDING & NEW COMPANY REGISTRATION
# ==========================================
def _render_onboarding_payment_verification():
    pending_reg = st.session_state.get("pending_reg") or {}
    callback_reference = str(st.query_params.get("reference", "") or st.query_params.get("trxref", "") or "").strip()
    reference = callback_reference or str(pending_reg.get("reference") or "").strip()
    if not reference:
        return

    st.markdown("---")
    st.subheader("Verify Paystack Payment")
    if callback_reference:
        st.info("Paystack returned you to the ERP. Verify the payment below to activate your company license.")
    else:
        st.caption("After completing Card or Mobile Money checkout, return here and verify the transaction.")
    st.text_input("Payment Reference", value=reference, disabled=True, key="onboarding_verify_reference_display")
    if st.button("I have paid / Verify Payment", key="verify_onboarding_paystack_payment_btn"):
        verification_result = verify_paystack_payment(reference, activate_license=True)
        if verification_result.get("ok"):
            company_name = verification_result.get("company_name") or pending_reg.get("company_name") or "your company"
            company_key = verification_result.get("company_key") or pending_reg.get("company_key") or "pending"
            st.success(f"Payment verified and license activated for {company_name}. Company Key: {company_key}")
            st.session_state.pop("pending_reg", None)
        else:
            st.warning(verification_result.get("reason") or "Payment verification did not succeed yet.")


def get_subscription_billing_admin_snapshot():
    conn = None
    try:
        conn = get_connection()
        return get_subscription_billing_summary(conn=conn)
    finally:
        if conn:
            conn.close()


def get_subscription_billing_health_snapshot():
    conn = None
    try:
        conn = get_connection()
        paystack = get_paystack_diagnostics()
        billing = get_subscription_billing_diagnostics(conn=conn)
        billing["plan_pricing"] = get_subscription_plan_pricing_snapshot()
        return {
            "ok": True,
            "paystack": paystack,
            "billing": billing,
        }
    finally:
        if conn:
            conn.close()


def show_subscription_renewal_page(company_key, role="Master Admin"):
    snapshot = get_company_subscription_snapshot(company_key)
    if not snapshot.get("ok"):
        st.error("Subscription details could not be loaded right now.")
        return

    st.header("Subscription Renewal")
    if snapshot.get("is_trial"):
        st.info(
            "Your 7-day trial is active until {end_date}. Choose a plan below to keep access uninterrupted.".format(
                end_date=snapshot.get("end_date") or "unknown",
            )
        )
    elif snapshot.get("status") in {"expired", "cancelled"}:
        st.warning("Your subscription is not active. Complete payment verification to restore ERP access.")
    else:
        st.info(
            "Current plan: {plan_name} | Status: {status} | Ends: {end_date}".format(
                plan_name=snapshot.get("plan_name") or "Unspecified",
                status=str(snapshot.get("status") or "").title(),
                end_date=snapshot.get("end_date") or "Open-ended",
            )
        )

    available_plans = get_subscription_plans()
    plan_labels = list(available_plans.keys())
    selected_plan_name = st.selectbox("Choose Subscription Plan", plan_labels, key=f"subscription_plan_{company_key}")
    selected_plan = get_subscription_plan(selected_plan_name)
    if selected_plan.get("configured"):
        st.caption(
            "Plan amount: {currency} {amount:,.2f} | Duration: {duration}".format(
                currency=selected_plan.get("currency") or "GHS",
                amount=float(selected_plan["amount"]),
                duration=(
                    f"{selected_plan['duration_months']} month(s)"
                    if selected_plan.get("duration_months")
                    else f"{selected_plan.get('duration_days', 0)} day(s)"
                ),
            )
        )
    else:
        st.warning(SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE)
    if selected_plan.get("features"):
        st.caption("Features: " + ", ".join(selected_plan["features"]))

    renewal_state_key = f"subscription_payment_{company_key}"
    company_email = None
    conn = None
    try:
        conn = get_connection()
        row = conn.execute("SELECT contact_email, name FROM companies WHERE key = ? LIMIT 1", (company_key,)).fetchone()
        if row:
            company_email = row["contact_email"]
    finally:
        if conn:
            conn.close()

    button_label = "Start Payment"
    if st.button(button_label, key=f"subscription_start_payment_{company_key}"):
        if not selected_plan.get("configured"):
            st.warning(SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE)
        elif not company_email:
            st.warning("A contact email is required on the company profile before starting subscription payment.")
        else:
            reference = _generate_paystack_reference("SUB")
            payment_result = initialize_paystack_payment(
                company_email,
                selected_plan.get("amount"),
                reference,
                company_key=company_key,
                company_name=snapshot.get("company_name"),
                plan_name=selected_plan_name,
                payment_context="subscription_renewal",
                subscription_months=selected_plan.get("duration_months"),
                subscription_days=selected_plan.get("duration_days"),
                user_email=company_email,
                metadata_extra={"features": selected_plan.get("features", [])},
            )
            if payment_result.get("ok"):
                st.session_state[renewal_state_key] = {
                    "reference": reference,
                    "plan_name": selected_plan_name,
                    "authorization_url": payment_result.get("authorization_url"),
                }
                st.success("Subscription payment initialized successfully.")
            else:
                st.warning(payment_result.get("reason") or "Subscription payment could not be initialized.")

    renewal_state = st.session_state.get(renewal_state_key) or {}
    if renewal_state.get("authorization_url"):
        st.link_button("Continue to Secure Paystack Checkout", renewal_state["authorization_url"])
    verify_reference = str(st.query_params.get("reference", "") or renewal_state.get("reference") or "").strip()
    if verify_reference:
        st.text_input(
            "Payment Reference",
            value=verify_reference,
            disabled=True,
            key=f"subscription_reference_{company_key}",
        )
        if st.button("Verify Subscription Payment", key=f"verify_subscription_payment_{company_key}"):
            verification = verify_paystack_payment(verify_reference, activate_license=True)
            if verification.get("ok"):
                st.success(
                    "Subscription activated. New expiry: {expiry}".format(
                        expiry=verification.get("new_expiry") or "updated",
                    )
                )
                st.session_state.pop(renewal_state_key, None)
            else:
                st.warning(verification.get("reason") or "Subscription payment has not been verified yet.")


def show_onboarding_payment():
    """Handle the onboarding payment process for new companies."""
    st.header("🏢 New Company Registration")
    st.info("Create a 7-day trial company and optionally complete Paystack payment to activate a paid subscription plan immediately.")

    with st.form("onboarding_form"):
        col1, col2 = st.columns(2)
        with col1:
            company_name = st.text_input("Company Name")
            admin_email = st.text_input("Admin Email Address")
            admin_phone = st.text_input("Admin Phone Number (Optional)")
        with col2:
            sector = st.selectbox("Business Sector", ["Retail", "Manufacturing", "Services", "Construction", "Other"])
            available_plans = get_subscription_plans()
            selected_plan_name = st.selectbox("Subscription Plan", list(available_plans.keys()), index=0)

        selected_plan = get_subscription_plan(selected_plan_name)
        amount = float(selected_plan["amount"] or 0) if selected_plan.get("configured") else 0.0

        if selected_plan.get("configured"):
            st.caption(
                "7-day trial is created immediately. Selected plan: {plan} | Amount Due: {currency} {amount:,.2f}".format(
                    plan=selected_plan_name,
                    currency=selected_plan.get("currency") or "GHS",
                    amount=amount,
                )
            )
        else:
            st.warning(SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE)
        submit = st.form_submit_button("Create Trial Company & Proceed to Payment")

        if submit:
            if not company_name or not admin_email:
                st.error("Please fill in all required fields.")
            else:
                conn = None
                try:
                    conn = get_connection()
                    existing_company = conn.execute(
                        "SELECT key FROM companies WHERE lower(name) = lower(?) LIMIT 1",
                        (company_name.strip(),),
                    ).fetchone()
                    if existing_company:
                        st.warning("A company with this name already exists. Please use a different company name.")
                    else:
                        company_key = _generate_company_key()
                        trial_result = ensure_company_trial_subscription(
                            conn,
                            company_key=company_key,
                            company_name=company_name.strip(),
                            contact_email=admin_email.strip(),
                            trial_days=7,
                        )
                        conn.commit()
                        if not selected_plan.get("configured"):
                            st.success(
                                "Trial company created successfully. Trial ends on {trial_end}.".format(
                                    trial_end=trial_result["end_date"],
                                )
                            )
                            st.warning(
                                SUBSCRIPTION_PRICING_NOT_CONFIGURED_MESSAGE
                                + f" Trial access remains active until {trial_result['end_date']}."
                            )
                            st.caption(f"Company Key: {company_key}")
                        else:
                            reference = _generate_paystack_reference("ONB")
                            payment_result = initialize_paystack_payment(
                                admin_email,
                                amount,
                                reference,
                                company_key=company_key,
                                company_name=company_name.strip(),
                                payment_context="onboarding",
                                plan_name=selected_plan_name,
                                subscription_months=selected_plan.get("duration_months"),
                                subscription_days=selected_plan.get("duration_days"),
                                user_email=admin_email.strip(),
                                phone_number=admin_phone.strip(),
                                metadata_extra={"sector": sector, "trial_end_date": trial_result["end_date"]},
                            )
                            if payment_result.get("ok"):
                                st.success(
                                    "Trial company created successfully. Trial ends on {trial_end}. You can continue to Paystack now or use the trial first.".format(
                                        trial_end=trial_result["end_date"],
                                    )
                                )
                                st.session_state.pending_reg = {
                                    'company_name': company_name.strip(),
                                    'company_key': company_key,
                                    'email': admin_email.strip(),
                                    'phone_number': admin_phone.strip(),
                                    'amount': amount,
                                    'plan_name': selected_plan_name,
                                    'months': int(selected_plan.get("duration_months") or 0),
                                    'reference': reference,
                                    'authorization_url': payment_result.get("authorization_url"),
                                    'trial_end_date': trial_result["end_date"],
                                }
                                st.caption(f"Company Key: {company_key}")
                                st.link_button(
                                    "Continue to Secure Paystack Checkout",
                                    payment_result["authorization_url"],
                                )
                                st.caption("Supported checkout channels: Card and Ghana Mobile Money.")
                            else:
                                st.warning(
                                    (payment_result.get("reason") or "Payment could not be initialized yet.")
                                    + f" Trial access remains active until {trial_result['end_date']}."
                                )
                except Exception as exc:
                    if conn:
                        conn.rollback()
                    st.warning("Onboarding payment could not be started right now. Please try again.")
                    logger.warning("Onboarding payment error: %s", sanitize_error_message(exc))
                finally:
                    if conn:
                        conn.close()
    _render_onboarding_payment_verification()


# ==========================================
# INVENTORY MANAGEMENT
# ==========================================
def show_inventory(company_key, role):
    render_ui_standard_styles()
    page_header("📦 Inventory Management", "Track inventory levels, update stock, and manage items")
    if role != "Demo" and not require_permission(
        role,
        "view_inventory",
        action_label="view inventory",
        company_key=company_key,
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return
    success_key = f"inventory_add_success_{company_key}"
    delete_success_key = f"inventory_delete_success_{company_key}"
    inventory_message_key = f"inventory_message_{company_key}"
    inventory_scan_beep_key = f"inventory_scan_beep_{company_key}"
    inventory_scan_input_key = f"inventory_scan_input_{company_key}"
    inventory_pending_scan_key = f"inventory_pending_scan_{company_key}"
    inventory_new_barcode_key = f"inventory_new_barcode_{company_key}"
    inventory_import_preview_key = f"inventory_import_preview_{company_key}"
    inventory_import_mapping_key = f"inventory_import_mapping_{company_key}"
    inventory_import_validation_key = f"inventory_import_validation_{company_key}"
    inventory_import_result_key = f"inventory_import_result_{company_key}"
    if st.session_state.get(success_key):
        _trigger_scan_feedback(inventory_message_key, "Item added successfully!")
        st.session_state.pop(success_key, None)
    if st.session_state.get(delete_success_key):
        _trigger_scan_feedback(inventory_message_key, "Item deleted")
        st.session_state.pop(delete_success_key, None)

    schema_conn = None
    try:
        schema_conn = get_connection()
        ensure_inventory_schema_integrity(schema_conn)
        schema_conn.commit()
    except Exception as exc:
        if schema_conn:
            schema_conn.rollback()
        logger.warning("Inventory schema integrity check failed: %s", sanitize_error_message(exc))
        st.error(build_user_safe_error(exc, role))
        return
    finally:
        if schema_conn:
            schema_conn.close()

    _render_flash_message(inventory_message_key, inventory_scan_beep_key)
    st.text_input(
        "Scan Barcode",
        key=inventory_scan_input_key,
        placeholder="Scan or type a barcode and press Enter",
        on_change=_set_input_pending,
        args=(inventory_scan_input_key, inventory_pending_scan_key),
    )
    _render_camera_scanner(f"inventory_{company_key}", inventory_pending_scan_key)

    pending_inventory_barcode = str(st.session_state.get(inventory_pending_scan_key, "") or "").strip()
    if pending_inventory_barcode and role != "Demo":
        conn = None
        try:
            conn = get_connection()
            matched_item = _lookup_inventory_by_barcode(conn, company_key, pending_inventory_barcode)
            if matched_item:
                updated_qty = float(matched_item["qty"] or 0) + 1
                conn.execute(
                    """
                    UPDATE inventory
                    SET qty = COALESCE(qty, 0) + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND company_key = ?
                    """,
                    (int(matched_item["id"]), company_key),
                )
                conn.commit()
                log_audit_action(
                    conn,
                    company_key,
                    role,
                    "Inventory Barcode Scan",
                    "Inventory",
                    f"Incremented {matched_item['item_name']} via barcode {pending_inventory_barcode}",
                )
                _trigger_scan_feedback(
                    inventory_message_key,
                    f"{matched_item['item_name']} quantity increased to {updated_qty:,.2f}.",
                    "success",
                    inventory_scan_beep_key,
                )
            else:
                st.session_state[inventory_new_barcode_key] = pending_inventory_barcode
                _trigger_scan_feedback(
                    inventory_message_key,
                    f"Barcode {pending_inventory_barcode} is new. Enter the item name and prices below to save it.",
                    "info",
                )
        except Exception as exc:
            st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
        finally:
            if conn:
                conn.close()
            st.session_state.pop(inventory_pending_scan_key, None)
            st.session_state[inventory_scan_input_key] = ""
            _invalidate_inventory_search_cache()
            st.rerun()

    inventory_metrics = None
    if role == "Demo":
        demo_metrics_df = pd.DataFrame({
            "quantity": [50, 8, 0],
            "min_stock_level": [10, 10, 5],
            "expiry_date": [None, (datetime.now().date() + timedelta(days=12)).isoformat(), None],
            "total_value": [6000.0, 600.0, 0.0],
        })
        inventory_metrics = _compute_inventory_health_metrics(demo_metrics_df)
    else:
        metrics_conn = None
        try:
            metrics_conn = get_connection()
            metrics_df = _portable_read_dataframe(
                metrics_conn,
                """
                SELECT qty as quantity, min_stock_level, expiry_date, (qty * cost_price) as total_value
                FROM inventory
                WHERE company_key = ?
                """,
                (company_key,),
            )
            inventory_metrics = _compute_inventory_health_metrics(metrics_df)
        except Exception as exc:
            logger.warning("Inventory metrics load failed: %s", sanitize_error_message(exc))
        finally:
            if metrics_conn:
                metrics_conn.close()

    if inventory_metrics is not None:
        metrics_col1, metrics_col2, metrics_col3, metrics_col4, metrics_col5 = st.columns(5)
        metrics_col1.metric("Total Items", inventory_metrics["total_items"])
        metrics_col2.metric("Low Stock Items", inventory_metrics["low_stock_items"])
        metrics_col3.metric("Expiring Soon", inventory_metrics["expiring_soon"])
        metrics_col4.metric("Out of Stock", inventory_metrics["out_of_stock"])
        metrics_col5.metric(
            f"Inventory Value ({get_currency_symbol()})",
            format_currency(inventory_metrics["inventory_value"]),
        )

    _render_recent_inventory_movements_panel(
        company_key,
        role,
        branch_id=st.session_state.get("active_branch_id"),
    )

    tabs = st.tabs(["Stock Overview", "Stock In/Out", "Items Management"])

    with tabs[0]:
        st.subheader("Current Stock Levels")
        try:
            conn = get_connection()
            if role == "Demo":
                df = pd.DataFrame({
                    "item_code": ["INV-001", "INV-002"],
                    "barcode": ["1234567890123", "0987654321098"],
                    "item_name": ["Product A", "Product B"],
                    "category": ["General", "General"],
                    "quantity": [50, 8],
                    "unit_price": [120.0, 75.0],
                    "total_value": [6000.0, 600.0],
                })
            else:
                df = _portable_read_dataframe(
                    conn,
                    """
                    SELECT id, item_code, barcode, item_name, category, description, brand, supplier_name,
                           expiry_date, batch_number, vat_category, unit, min_stock_level, tax_rate,
                           warehouse_location, is_active, opening_balance, qty as quantity,
                           price as unit_price, cost_price, (qty * cost_price) as total_value
                    FROM inventory WHERE company_key = ?
                    """,
                    (company_key,),
                )
            conn.close()

            if not df.empty:
                overview_df = _prepare_inventory_overview_dataframe(df)
                inventory_health_filter_key = f"inventory_health_filter_{company_key}"
                inventory_receive_prefill_key = f"inventory_receive_prefill_id_{company_key}"
                health_filter = st.radio(
                    "Inventory Health Filter",
                    ["All", "OK", "LOW STOCK", "OUT OF STOCK", "EXPIRING SOON", "EXPIRED", "INVALID EXPIRY"],
                    horizontal=True,
                    key=inventory_health_filter_key,
                )
                filtered_overview_df = _filter_inventory_overview_dataframe(overview_df, health_filter)
                low_stock_df = overview_df[overview_df["stock_status"].isin(["LOW STOCK", "OUT OF STOCK"])]
                with st.expander("Low Stock Action Center", expanded=not low_stock_df.empty):
                    if low_stock_df.empty:
                        st.caption("No low-stock or out-of-stock items right now.")
                    else:
                        for _, low_stock_row in low_stock_df.iterrows():
                            action_cols = st.columns([3, 1, 1, 1])
                            action_cols[0].markdown(
                                f"**{low_stock_row['item_name']}** — Qty {float(low_stock_row['quantity']):,.2f} "
                                f"(reorder {float(low_stock_row.get('min_stock_level') or 0):,.2f})"
                            )
                            action_cols[1].caption(
                                f"Supplier: {low_stock_row.get('supplier_name') or 'N/A'}"
                            )
                            action_cols[2].caption(_inventory_stock_status_badge(low_stock_row.get("stock_status")))
                            if action_cols[3].button(
                                "Quick Stock-In",
                                key=f"inventory_quick_stock_in_{company_key}_{int(low_stock_row['id'])}",
                            ):
                                st.session_state[inventory_receive_prefill_key] = int(low_stock_row["id"])
                                st.info(
                                    f"{low_stock_row['item_name']} is ready in Stock In/Out → Receive Stock."
                                )
                display_columns = [
                    column
                    for column in filtered_overview_df.columns
                    if column not in {"stock_status", "expiry_status", "days_to_expiry"}
                ]
                if filtered_overview_df.empty:
                    st.info(f"No items match the selected filter: {health_filter}.")
                else:
                    st.dataframe(
                        format_currency_dataframe(filtered_overview_df[display_columns]),
                        use_container_width=True,
                    )
                excel_bin = get_excel_bin(filtered_overview_df[display_columns])
                if excel_bin:
                    st.download_button(
                        "📥 Export to Excel",
                        data=excel_bin,
                        file_name=f"inventory_{company_key}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"inventory_export_{company_key}",
                    )
                if user_has_permission(role, "manage_inventory") and "id" in df.columns:
                    st.markdown("Edit Stock Item")
                    selected_edit_key = f"inventory_edit_selected_{company_key}"
                    delete_confirm_key = f"inventory_delete_confirm_{company_key}"
                    for _, stock_row in overview_df.iterrows():
                        name_col, edit_col, delete_col = st.columns([4, 1, 1])
                        stock_badge = _inventory_stock_status_badge(stock_row.get("stock_status"))
                        expiry_badge = _inventory_expiry_status_badge(stock_row.get("expiry_status"))
                        badge_text = " ".join(part for part in (stock_badge, expiry_badge) if part)
                        name_col.caption(
                            f"{stock_row['item_name']} | Barcode {stock_row.get('barcode') or 'N/A'} | Qty {float(stock_row['quantity']):,.2f} | "
                            f"Sell GHS {float(stock_row['unit_price']):,.2f}"
                            + (f" | {badge_text}" if badge_text else "")
                        )
                        if edit_col.button("Edit", key=f"inventory_edit_btn_{company_key}_{int(stock_row['id'])}"):
                            st.session_state[selected_edit_key] = int(stock_row["id"])
                        if delete_col.button("🗑️ Delete Record", key=f"inventory_delete_btn_{company_key}_{int(stock_row['id'])}"):
                            st.session_state[delete_confirm_key] = int(stock_row["id"])
                    delete_item_id = st.session_state.get(delete_confirm_key)
                    if delete_item_id is not None:
                        st.warning("Are you sure you want to permanently delete this item?")
                        confirm_col, cancel_col = st.columns(2)
                        if confirm_col.button("🗑️ Delete Record", key=f"inventory_delete_confirm_btn_{company_key}_{delete_item_id}"):
                            conn = get_connection()
                            conn.execute(
                                "DELETE FROM inventory WHERE id = ? AND company_key = ?",
                                (int(delete_item_id), company_key),
                            )
                            conn.commit()
                            log_audit_action(conn, company_key, role, "Inventory Item Deleted", "Inventory", f"Deleted item ID {int(delete_item_id)}")
                            conn.close()
                            _invalidate_inventory_search_cache()
                            _clear_streamlit_state(delete_confirm_key, selected_edit_key)
                            st.session_state[delete_success_key] = True
                            st.rerun()
                        if cancel_col.button("Cancel", key=f"inventory_delete_cancel_btn_{company_key}_{delete_item_id}"):
                            _clear_streamlit_state(delete_confirm_key)
                            st.rerun()
                    edit_item_id = st.session_state.get(selected_edit_key, int(df["id"].iloc[0]))
                    edit_row = df.loc[df["id"] == edit_item_id].iloc[0]
                    existing_expiry_value = str(edit_row.get("expiry_date") or "").strip()
                    try:
                        default_expiry_date = (
                            datetime.fromisoformat(existing_expiry_value).date()
                            if existing_expiry_value
                            else None
                        )
                    except ValueError:
                        default_expiry_date = None
                    edit_expiry_enabled_key = f"inventory_edit_expiry_enabled_{company_key}_{edit_item_id}"
                    edit_expiry_date_key = f"inventory_edit_expiry_date_{company_key}_{edit_item_id}"
                    st.checkbox(
                        "Set Expiry Date",
                        value=default_expiry_date is not None,
                        key=edit_expiry_enabled_key,
                    )
                    edit_expiry_enabled = bool(st.session_state.get(edit_expiry_enabled_key, False))
                    if edit_expiry_enabled:
                        st.date_input(
                            "Expiry Date",
                            value=default_expiry_date or datetime.now().date(),
                            key=edit_expiry_date_key,
                        )
                    else:
                        st.caption("Expiry date will be cleared for this item.")
                    with st.form(f"inventory_edit_form_{company_key}_{edit_item_id}", clear_on_submit=True):
                        edit_item_code = st.text_input("Item Code (SKU)", value=str(edit_row.get("item_code") or ""))
                        edit_barcode = st.text_input("Barcode", value=str(edit_row.get("barcode") or ""))
                        edit_unit = st.text_input("Unit", value=str(edit_row.get("unit") or "pcs"))
                        edit_category = st.text_input("Category", value=str(edit_row["category"] or ""))
                        edit_description = st.text_area("Description", value=str(edit_row.get("description") or ""))
                        edit_brand = st.text_input("Brand", value=str(edit_row.get("brand") or ""))
                        edit_supplier_name = st.text_input("Supplier Name", value=str(edit_row.get("supplier_name") or ""))
                        edit_batch_number = st.text_input("Batch Number", value=str(edit_row.get("batch_number") or ""))
                        edit_vat_category = st.text_input("VAT Category", value=str(edit_row.get("vat_category") or ""))
                        edit_qty = st.number_input("Quantity", min_value=0.0, value=float(edit_row["quantity"] or 0.0))
                        edit_reorder_level = st.number_input("Reorder Level", min_value=0.0, value=float(edit_row.get("min_stock_level") or 0.0))
                        edit_price = st.number_input(f"Selling Price ({st.session_state.currency_symbol})", min_value=0.0, value=float(edit_row["unit_price"] or 0.0))
                        edit_cost_price = st.number_input(f"Cost Price ({st.session_state.currency_symbol})", min_value=0.0, value=float(edit_row["cost_price"] or 0.0))
                        edit_tax_rate = st.number_input("Tax Rate", min_value=0.0, value=float(edit_row.get("tax_rate") or 0.0))
                        edit_warehouse_location = st.text_input("Shelf / Location", value=str(edit_row.get("warehouse_location") or ""))
                        edit_is_active = st.checkbox("Active", value=bool(edit_row.get("is_active", 1)))
                        if st.form_submit_button("Edit Item"):
                            edit_expiry_enabled = bool(st.session_state.get(edit_expiry_enabled_key, False))
                            edit_expiry_date = (
                                st.session_state.get(edit_expiry_date_key) if edit_expiry_enabled else None
                            )
                            try:
                                conn = get_connection()
                                conn.execute(
                                    """
                                    UPDATE inventory
                                    SET item_code = ?, barcode = ?, unit = ?, category = ?, description = ?, brand = ?,
                                        supplier_name = ?, expiry_date = ?, batch_number = ?, vat_category = ?,
                                        qty = ?, min_stock_level = ?, price = ?, cost_price = ?, tax_rate = ?,
                                        warehouse_location = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                                    WHERE id = ? AND company_key = ?
                                    """,
                                    (
                                        edit_item_code.strip(),
                                        edit_barcode.strip(),
                                        edit_unit.strip() or "pcs",
                                        edit_category.strip(),
                                        edit_description.strip(),
                                        edit_brand.strip(),
                                        edit_supplier_name.strip(),
                                        edit_expiry_date.isoformat() if edit_expiry_enabled else None,
                                        edit_batch_number.strip(),
                                        edit_vat_category.strip(),
                                        edit_qty,
                                        edit_reorder_level,
                                        edit_price,
                                        edit_cost_price,
                                        edit_tax_rate,
                                        edit_warehouse_location.strip(),
                                        1 if edit_is_active else 0,
                                        int(edit_item_id),
                                        company_key,
                                    ),
                                )
                                conn.commit()
                                log_audit_action(conn, company_key, role, "Inventory Item Updated", "Inventory", f"Updated item ID {int(edit_item_id)}")
                                conn.close()
                                _invalidate_inventory_search_cache()
                                _clear_streamlit_state(selected_edit_key, delete_confirm_key)
                                st.success("Entry Updated")
                                st.rerun()
                            except Exception as exc:
                                st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
            else:
                st.info("No items in inventory.")
        except Exception as e:
            st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))

    with tabs[1]:
        st.subheader("Stock In / Out")
        if role == "Demo":
            st.info("Stock movement recording is disabled in Demo mode.")
        else:
            conn = None
            try:
                conn = get_connection()
                stock_items = conn.execute(
                    """
                    SELECT id, item_name, barcode, qty, cost_price, inventory_account_id, cogs_account_id
                    FROM inventory
                    WHERE company_key = ?
                    ORDER BY item_name
                    """,
                    (company_key,),
                ).fetchall()
                movement_reasons = ["Restock", "Damage", "Sale", "Return", "Adjustment", "Transfer", "Other"]
                branch_id = st.session_state.get("active_branch_id")

                if not stock_items:
                    st.info("Add inventory items first before recording stock movements.")
                else:
                    ensure_stock_movements_schema_integrity(conn)
                    stock_options = [
                        (
                            f"{row['item_name']} | Barcode {row['barcode'] or 'N/A'} | Available {float(row['qty'] or 0):,.2f}",
                            int(row["id"]),
                        )
                        for row in stock_items
                    ]
                    option_labels = [label for label, _ in stock_options]
                    inventory_receive_prefill_key = f"inventory_receive_prefill_id_{company_key}"
                    inventory_receive_form_reset_key = f"inventory_receive_form_reset_{company_key}"
                    receive_prefill_id = st.session_state.get(inventory_receive_prefill_key)
                    receive_default_index = 0
                    if receive_prefill_id is not None:
                        for option_index, (_, option_item_id) in enumerate(stock_options):
                            if int(option_item_id) == int(receive_prefill_id):
                                receive_default_index = option_index
                                break
                        st.info("Item pre-selected from Low Stock Action Center.")
                    supplier_options = _load_registered_supplier_names(company_key)
                    st.markdown("### Receive Stock")
                    with st.form(f"inventory_receive_stock_form_{company_key}", clear_on_submit=True):
                        receive_supplier_key = _form_widget_key(
                            f"inventory_receive_supplier_{company_key}",
                            inventory_receive_form_reset_key,
                        )
                        receive_item_key = _form_widget_key(
                            f"inventory_receive_item_{company_key}",
                            inventory_receive_form_reset_key,
                        )
                        receive_qty_key = _form_widget_key(
                            f"inventory_receive_qty_{company_key}",
                            inventory_receive_form_reset_key,
                        )
                        receive_cost_key = _form_widget_key(
                            f"inventory_receive_unit_cost_{company_key}",
                            inventory_receive_form_reset_key,
                        )
                        receive_batch_key = _form_widget_key(
                            f"inventory_receive_batch_{company_key}",
                            inventory_receive_form_reset_key,
                        )
                        receive_expiry_enabled_key = _form_widget_key(
                            f"inventory_receive_expiry_enabled_{company_key}",
                            inventory_receive_form_reset_key,
                        )
                        receive_expiry_date_key = _form_widget_key(
                            f"inventory_receive_expiry_date_{company_key}",
                            inventory_receive_form_reset_key,
                        )
                        receive_reference_key = _form_widget_key(
                            f"inventory_receive_reference_{company_key}",
                            inventory_receive_form_reset_key,
                        )
                        receive_notes_key = _form_widget_key(
                            f"inventory_receive_notes_{company_key}",
                            inventory_receive_form_reset_key,
                        )
                        if supplier_options:
                            st.selectbox(
                                "Supplier (optional)",
                                [""] + supplier_options,
                                key=receive_supplier_key,
                            )
                        else:
                            st.text_input("Supplier (optional)", key=receive_supplier_key)
                        receive_item_label = st.selectbox(
                            "Item",
                            option_labels,
                            index=receive_default_index,
                            key=receive_item_key,
                        )
                        receive_qty = st.number_input(
                            "Qty Received",
                            min_value=0.01,
                            value=1.0,
                            step=1.0,
                            key=receive_qty_key,
                        )
                        receive_unit_cost = st.number_input(
                            f"Unit Cost ({get_currency_symbol()})",
                            min_value=0.0,
                            value=0.0,
                            step=0.01,
                            key=receive_cost_key,
                        )
                        receive_batch_number = st.text_input("Batch Number", key=receive_batch_key)
                        st.checkbox("Set Expiry Date", key=receive_expiry_enabled_key)
                        if bool(st.session_state.get(receive_expiry_enabled_key, False)):
                            st.date_input(
                                "Expiry Date",
                                value=datetime.now().date(),
                                key=receive_expiry_date_key,
                            )
                        receive_reference_number = st.text_input("Reference Number", key=receive_reference_key)
                        receive_notes = st.text_area("Notes", key=receive_notes_key)
                        receive_submitted = st.form_submit_button("Receive Stock")

                    if receive_submitted:
                        if not require_permission(
                            role,
                            "manage_inventory",
                            action_label="receive inventory stock",
                            company_key=company_key,
                            branch_id=branch_id,
                        ):
                            return
                        try:
                            receive_item_id = next(
                                item_id for label, item_id in stock_options if label == receive_item_label
                            )
                            receive_supplier_value = str(st.session_state.get(receive_supplier_key, "") or "").strip()
                            receive_expiry_value = (
                                st.session_state.get(receive_expiry_date_key)
                                if bool(st.session_state.get(receive_expiry_enabled_key, False))
                                else None
                            )
                            receive_result = _receive_inventory_stock(
                                conn,
                                company_key,
                                role,
                                inventory_item_id=int(receive_item_id),
                                qty_received=float(receive_qty or 0.0),
                                unit_cost=float(receive_unit_cost or 0.0),
                                supplier_name=receive_supplier_value or None,
                                batch_number=str(st.session_state.get(receive_batch_key, "") or "").strip(),
                                expiry_date=receive_expiry_value,
                                reference_number=str(st.session_state.get(receive_reference_key, "") or "").strip(),
                                notes=str(st.session_state.get(receive_notes_key, "") or "").strip(),
                                branch_id=branch_id,
                            )
                            conn.commit()
                            log_audit_action(
                                conn,
                                company_key,
                                role,
                                "Inventory Stock Received",
                                "Inventory",
                                (
                                    f"{receive_result['item_name']} | +{float(receive_qty or 0.0):,.2f} | "
                                    f"{receive_result['previous_qty']:,.2f} -> {receive_result['new_qty']:,.2f} | "
                                    f"Ref {receive_result['reference']}"
                                ),
                                branch_id=branch_id,
                            )
                            st.session_state.pop(inventory_receive_prefill_key, None)
                            _invalidate_inventory_search_cache()
                            _increment_form_reset(inventory_receive_form_reset_key)
                            st.success(
                                f"Received stock for {receive_result['item_name']}. "
                                f"New quantity: {receive_result['new_qty']:,.2f}."
                            )
                            st.rerun()
                        except Exception as exc:
                            conn.rollback()
                            st.error(build_user_safe_error(exc, role))

                    st.markdown("### Adjust Stock (In/Out)")
                    selected_label = st.selectbox(
                        "Select Item",
                        option_labels,
                        key=f"stock_movement_item_{company_key}",
                    )
                    selected_item_id = next(item_id for label, item_id in stock_options if label == selected_label)
                    selected_item = next(row for row in stock_items if int(row["id"]) == selected_item_id)

                    with st.form(f"stock_movement_form_{company_key}", clear_on_submit=True):
                        movement_type = st.selectbox("Movement Type", ["In", "Out"], key=f"stock_movement_type_{company_key}")
                        quantity = st.number_input("Quantity", min_value=0.01, value=1.0, step=1.0, key=f"stock_movement_qty_{company_key}")
                        reason = st.selectbox("Reason", movement_reasons, key=f"stock_movement_reason_{company_key}")
                        submitted = st.form_submit_button("Record Movement")

                    if submitted:
                        if not require_permission(
                            role,
                            "manage_inventory",
                            action_label="record stock movements",
                            company_key=company_key,
                            branch_id=branch_id,
                        ):
                            return
                        current_qty = float(selected_item["qty"] or 0.0)
                        movement_qty = float(quantity or 0.0)
                        if movement_qty <= 0:
                            st.warning("Enter a quantity greater than zero.")
                        else:
                            delta = movement_qty if movement_type == "In" else -movement_qty
                            new_qty = current_qty + delta
                            if movement_type == "Out" and new_qty < 0:
                                st.error(f"Cannot record stock out of {movement_qty:,.2f}. Available quantity is {current_qty:,.2f}.")
                            else:
                                conn.execute(
                                    """
                                    UPDATE inventory
                                    SET qty = ?, updated_at = CURRENT_TIMESTAMP
                                    WHERE id = ? AND company_key = ?
                                    """,
                                    (new_qty, selected_item_id, company_key),
                                )
                                movement_value = round(float(selected_item["cost_price"] or 0.0) * movement_qty, 2)
                                movement_status = "Posted" if movement_value > 0 else "Approved"
                                reason_key = str(reason or "").strip().lower()
                                if reason_key == "transfer":
                                    recorded_movement_type = "TRANSFER"
                                elif reason_key == "adjustment":
                                    recorded_movement_type = "ADJUSTMENT"
                                else:
                                    recorded_movement_type = "STOCK_IN" if movement_type == "In" else "STOCK_OUT"
                                movement_id = _insert_stock_movement_record(
                                    conn,
                                    company_key=company_key,
                                    inventory_item_id=selected_item_id,
                                    item_name=selected_item["item_name"],
                                    movement_type=recorded_movement_type,
                                    quantity=movement_qty,
                                    previous_qty=current_qty,
                                    new_qty=new_qty,
                                    created_by=role,
                                    branch_id=branch_id,
                                    reason=reason,
                                    reference=f"STK-{selected_item_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                                )
                                if movement_value > 0:
                                    inventory_account_id = int(selected_item["inventory_account_id"] or get_account_id(conn, "Inventory", "Asset"))
                                    cogs_account_id = int(selected_item["cogs_account_id"] or get_account_id(conn, "Cost of Goods Sold", "Expense"))
                                    if movement_type == "In":
                                        offset_account_id = get_account_id(
                                            conn,
                                            "Accounts Payable" if reason == "Restock" else "Opening Balance Equity",
                                            "Liability" if reason == "Restock" else "Equity",
                                        )
                                        journal_lines = [
                                            {"account_id": inventory_account_id, "debit": movement_value, "credit": 0},
                                            {"account_id": offset_account_id, "debit": 0, "credit": movement_value},
                                        ]
                                    else:
                                        journal_lines = [
                                            {"account_id": cogs_account_id, "debit": movement_value, "credit": 0},
                                            {"account_id": inventory_account_id, "debit": 0, "credit": movement_value},
                                        ]
                                    post_journal_entry(
                                        company_key=company_key,
                                        date=datetime.now().date(),
                                        description=f"Inventory movement - {selected_item['item_name']} ({reason})",
                                        reference=f"STK-{selected_item_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                                        lines=journal_lines,
                                        created_by=role,
                                        branch_id=branch_id,
                                        inventory_item_id=selected_item_id,
                                        source_module="Inventory",
                                        source_table="stock_movements",
                                        source_type="Stock Movement",
                                        source_id=movement_id,
                                        approval_status="Posted",
                                        conn=conn,
                                    )
                                conn.commit()
                                log_audit_action(
                                    conn,
                                    company_key,
                                    role,
                                    f"Inventory Stock {movement_type}",
                                    "Inventory",
                                    f"{selected_item['item_name']} | Qty {movement_qty:,.2f} | Reason: {reason} | {current_qty:,.2f} -> {new_qty:,.2f}",
                                    branch_id=branch_id,
                                )
                                st.success(f"Recorded stock {movement_type.lower()} for {selected_item['item_name']}. New quantity: {new_qty:,.2f}.")
                                _invalidate_inventory_search_cache()
                                st.rerun()
            except Exception as exc:
                st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
            finally:
                if conn:
                    conn.close()

    with tabs[2]:
        st.subheader("Items Management")
        if role == "Demo":
            st.info("Items management is disabled in Demo mode.")
            return
        inventory_form_reset_key = f"inventory_add_form_reset_{company_key}"
        inventory_supplier_options = _load_registered_supplier_names(company_key)
        pending_inventory_barcode_value = str(st.session_state.pop(inventory_new_barcode_key, "") or "")
        inventory_expiry_enabled_key = _form_widget_key(
            f"inventory_expiry_enabled_{company_key}", inventory_form_reset_key
        )
        inventory_expiry_date_key = _form_widget_key(
            f"inventory_expiry_date_{company_key}", inventory_form_reset_key
        )
        st.checkbox("Set Expiry Date", key=inventory_expiry_enabled_key)
        expiry_enabled = bool(st.session_state.get(inventory_expiry_enabled_key, False))
        if expiry_enabled:
            st.date_input(
                "Expiry Date",
                value=datetime.now().date(),
                key=inventory_expiry_date_key,
            )
        else:
            st.caption("Expiry date will not be saved for this item.")

        with st.form("add_inventory_form", clear_on_submit=True):
            item_code = st.text_input("Item Code (SKU)", key=_form_widget_key(f"inventory_item_code_{company_key}", inventory_form_reset_key))
            barcode = st.text_input(
                "New Barcode",
                value=pending_inventory_barcode_value,
                key=_form_widget_key(f"inventory_form_barcode_{company_key}", inventory_form_reset_key),
            )
            item_name = st.text_input("Item Name", key=_form_widget_key(f"inventory_item_name_{company_key}", inventory_form_reset_key))
            unit = st.text_input("Unit", value="pcs", key=_form_widget_key(f"inventory_unit_{company_key}", inventory_form_reset_key))
            category = st.text_input("Category", key=_form_widget_key(f"inventory_category_{company_key}", inventory_form_reset_key))
            description = st.text_area("Description", key=_form_widget_key(f"inventory_description_{company_key}", inventory_form_reset_key))
            brand = st.text_input("Brand", key=_form_widget_key(f"inventory_brand_{company_key}", inventory_form_reset_key))
            if inventory_supplier_options:
                selected_supplier_name = st.selectbox(
                    "Supplier Name",
                    inventory_supplier_options,
                    key=_form_widget_key(f"inventory_supplier_select_{company_key}", inventory_form_reset_key),
                )
                use_custom_supplier = st.checkbox(
                    "Use custom supplier name",
                    key=_form_widget_key(f"inventory_supplier_custom_enabled_{company_key}", inventory_form_reset_key),
                )
                if use_custom_supplier:
                    supplier_name = st.text_input(
                        "Custom Supplier Name",
                        key=_form_widget_key(f"inventory_supplier_custom_{company_key}", inventory_form_reset_key),
                    ).strip()
                else:
                    supplier_name = str(selected_supplier_name or "").strip()
            else:
                supplier_name = st.text_input(
                    "Supplier Name",
                    key=_form_widget_key(f"inventory_supplier_name_{company_key}", inventory_form_reset_key),
                )
            batch_number = st.text_input("Batch Number", key=_form_widget_key(f"inventory_batch_{company_key}", inventory_form_reset_key))
            vat_category = st.text_input("VAT Category", key=_form_widget_key(f"inventory_vat_category_{company_key}", inventory_form_reset_key))
            transaction_date = st.date_input(
                "Transaction Date",
                value=datetime.now().date(),
                key=_form_widget_key(f"inventory_transaction_date_{company_key}", inventory_form_reset_key),
            )
            opening_stock = st.number_input(
                "Opening Stock Quantity",
                min_value=0.0,
                value=0.0,
                key=_form_widget_key(f"inventory_opening_stock_{company_key}", inventory_form_reset_key),
            )
            min_stock_level = st.number_input(
                "Reorder Level",
                min_value=0.0,
                value=10.0,
                key=_form_widget_key(f"inventory_min_stock_{company_key}", inventory_form_reset_key),
            )
            funding_source = st.selectbox(
                "Inventory Funding Source",
                ["Cash", "Bank", "Mobile Money", "Accounts Payable"],
                key=_form_widget_key(f"inventory_funding_source_{company_key}", inventory_form_reset_key),
            )
            price = st.number_input(
                f"Selling Price ({st.session_state.currency_symbol})",
                min_value=0.0,
                value=0.0,
                key=_form_widget_key(f"inventory_price_{company_key}", inventory_form_reset_key),
            )
            cost_price = st.number_input(
                f"Cost Price ({st.session_state.currency_symbol})",
                min_value=0.0,
                value=0.0,
                key=_form_widget_key(f"inventory_cost_price_{company_key}", inventory_form_reset_key),
            )
            tax_rate = st.number_input(
                "Tax Rate",
                min_value=0.0,
                value=0.0,
                key=_form_widget_key(f"inventory_tax_rate_{company_key}", inventory_form_reset_key),
            )
            warehouse_location = st.text_input(
                "Shelf / Location",
                key=_form_widget_key(f"inventory_warehouse_{company_key}", inventory_form_reset_key),
            )
            is_active = st.checkbox(
                "Active",
                value=True,
                key=_form_widget_key(f"inventory_is_active_{company_key}", inventory_form_reset_key),
            )
            submitted = st.form_submit_button("➕ Add New Item")
            if submitted and item_name:
                expiry_enabled = bool(st.session_state.get(inventory_expiry_enabled_key, False))
                expiry_date_value = (
                    st.session_state.get(inventory_expiry_date_key) if expiry_enabled else None
                )
                if not require_permission(
                    role,
                    "manage_inventory",
                    action_label="manage inventory items",
                    company_key=company_key,
                    branch_id=st.session_state.get("active_branch_id"),
                ):
                    return
                try:
                    conn = get_connection()
                    normalized_barcode = barcode.strip()
                    if normalized_barcode:
                        existing_barcode = _lookup_inventory_by_barcode(conn, company_key, normalized_barcode)
                        if existing_barcode:
                            st.error(f"Barcode {normalized_barcode} is already assigned to {existing_barcode['item_name']}.")
                            conn.close()
                            return
                    conn.execute(
                        """
                        INSERT INTO inventory (
                            company_key, item_name, item_code, barcode, unit, category, description, brand,
                            supplier_name, expiry_date, batch_number, vat_category, opening_balance, qty,
                            min_stock_level, price, cost_price, tax_rate, warehouse_location, is_active,
                            inventory_account_id, cogs_account_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            company_key,
                            item_name,
                            item_code.strip(),
                            normalized_barcode,
                            unit.strip() or "pcs",
                            category,
                            description.strip(),
                            brand.strip(),
                            supplier_name.strip(),
                            expiry_date_value.isoformat() if expiry_date_value else None,
                            batch_number.strip(),
                            vat_category.strip(),
                            opening_stock,
                            opening_stock,
                            min_stock_level,
                            price,
                            cost_price,
                            tax_rate,
                            warehouse_location.strip(),
                            1 if is_active else 0,
                            get_account_id(conn, "Inventory", "Asset"),
                            get_account_id(conn, "Cost of Goods Sold", "Expense"),
                        ),
                    )
                    opening_stock_value = round(float(opening_stock or 0) * float(cost_price or 0), 2)
                    if opening_stock_value > 0:
                        offset_account, offset_type = _inventory_offset_account(funding_source)
                        post_journal_entry(
                            company_key=company_key,
                            date=transaction_date,
                            description="Opening inventory balance",
                            reference=f"INV-OPEN-{item_name}",
                            lines=[
                                {"account_id": get_account_id(conn, "Inventory", "Asset"), "debit": opening_stock_value, "credit": 0},
                                {"account_id": get_account_id(conn, offset_account, offset_type), "debit": 0, "credit": opening_stock_value},
                            ],
                            created_by=role,
                            branch_id=st.session_state.get("active_branch_id"),
                            source_module="Inventory",
                            source_table="inventory",
                            conn=conn,
                        )
                    conn.commit()
                    conn.close()
                    _invalidate_inventory_search_cache()
                    _increment_form_reset(inventory_form_reset_key)
                    st.session_state[success_key] = True
                    st.rerun()
                except Exception as e:
                    st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))

        st.markdown("---")
        st.subheader("Stock Import Wizard")
        st.caption("Preview only. No inventory has been imported yet.")
        import_file = st.file_uploader(
            "Upload stock file",
            type=["xlsx", "csv"],
            key=f"inventory_import_{company_key}",
            help="Upload an Excel or CSV file to preview stock items and suggested column mappings.",
        )
        if import_file and st.button("Analyze Stock File", key=f"inventory_import_btn_{company_key}"):
            try:
                preview_payload = _build_stock_import_preview(import_file)
                st.session_state[inventory_import_preview_key] = preview_payload
                st.session_state[inventory_import_mapping_key] = preview_payload.get("mapping_suggestion") or {}
                st.session_state.pop(inventory_import_validation_key, None)
                st.session_state.pop(inventory_import_result_key, None)
                st.session_state["validated_stock_rows"] = []
                st.session_state["invalid_stock_rows"] = []
                logger.info(
                    "Stock import preview prepared for company %s file=%s rows=%s",
                    company_key,
                    st.session_state[inventory_import_preview_key]["file_name"],
                    st.session_state[inventory_import_preview_key]["total_rows"],
                )
            except Exception as exc:
                st.session_state.pop(inventory_import_preview_key, None)
                st.session_state.pop(inventory_import_mapping_key, None)
                st.session_state.pop(inventory_import_validation_key, None)
                st.session_state.pop(inventory_import_result_key, None)
                st.session_state["validated_stock_rows"] = []
                st.session_state["invalid_stock_rows"] = []
                st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))

        stock_import_preview = st.session_state.get(inventory_import_preview_key)
        if stock_import_preview:
            st.caption(
                "File: {file_name} | Format: {file_type} | Total rows: {total_rows}".format(
                    file_name=stock_import_preview.get("file_name") or "uploaded_file",
                    file_type=(stock_import_preview.get("file_type") or "unknown").upper(),
                    total_rows=stock_import_preview.get("total_rows") or 0,
                )
            )
            st.caption(
                "Detected columns: {columns}".format(
                    columns=", ".join(stock_import_preview.get("detected_columns") or []) or "none",
                )
            )
            mapping_suggestion = stock_import_preview.get("mapping_suggestion") or {}
            if mapping_suggestion:
                mapping_rows = [
                    {"ERP Field": field_name.replace("_", " ").title(), "Detected File Column": column_name}
                    for field_name, column_name in mapping_suggestion.items()
                ]
                st.dataframe(pd.DataFrame(mapping_rows), hide_index=True, use_container_width=True)
            else:
                st.info("No likely stock column mappings were detected yet.")

            missing_important_columns = stock_import_preview.get("missing_important_columns") or []
            if missing_important_columns:
                st.warning(
                    "Missing important columns: "
                    + ", ".join(column.replace("_", " ").title() for column in missing_important_columns)
                )
            else:
                st.success("Important stock columns were detected in the uploaded file.")

            preview_rows = stock_import_preview.get("preview_rows") or []
            if preview_rows:
                st.markdown("Preview of first 20 rows")
                st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)

            st.markdown("Column Mapping")
            current_mapping = dict(st.session_state.get(inventory_import_mapping_key) or {})
            available_columns = ["-- Not mapped --"] + list(stock_import_preview.get("detected_columns") or [])
            mapping_updates = {}
            mapping_columns_left, mapping_columns_right = st.columns(2)
            mapping_items = list(STOCK_IMPORT_MAPPING_FIELDS.items())
            midpoint = (len(mapping_items) + 1) // 2
            for column_group, group_items in (
                (mapping_columns_left, mapping_items[:midpoint]),
                (mapping_columns_right, mapping_items[midpoint:]),
            ):
                with column_group:
                    for field_name, field_label in group_items:
                        suggested_column = current_mapping.get(field_name)
                        selected_index = (
                            available_columns.index(suggested_column)
                            if suggested_column in available_columns
                            else 0
                        )
                        selected_column = st.selectbox(
                            field_label,
                            available_columns,
                            index=selected_index,
                            key=f"inventory_import_map_{company_key}_{field_name}",
                        )
                        mapping_updates[field_name] = "" if selected_column == "-- Not mapped --" else selected_column
            st.session_state[inventory_import_mapping_key] = mapping_updates

            if st.button("Validate Stock Import Data", key=f"inventory_import_validate_{company_key}"):
                try:
                    validated_rows, invalid_rows, validation_summary = _validate_stock_import_rows(
                        stock_import_preview.get("all_rows") or [],
                        mapping_updates,
                    )
                    validation_payload = {
                        "summary": validation_summary,
                        "invalid_rows": invalid_rows,
                    }
                    st.session_state[inventory_import_validation_key] = validation_payload
                    st.session_state.pop(inventory_import_result_key, None)
                    st.session_state["validated_stock_rows"] = validated_rows
                    st.session_state["invalid_stock_rows"] = invalid_rows
                    logger.info(
                        "Stock import validation completed for company %s: valid=%s invalid=%s",
                        company_key,
                        validation_summary.get("valid_rows"),
                        validation_summary.get("invalid_rows"),
                    )
                except Exception as exc:
                    st.session_state.pop(inventory_import_validation_key, None)
                    st.session_state["validated_stock_rows"] = []
                    st.session_state["invalid_stock_rows"] = []
                    st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))

            validation_payload = st.session_state.get(inventory_import_validation_key) or {}
            validation_summary = validation_payload.get("summary") or {}
            invalid_rows = validation_payload.get("invalid_rows") or []
            if validation_summary:
                st.markdown("Validation Results")
                vr1, vr2, vr3, vr4, vr5 = st.columns(5)
                vr1.metric("Total Rows", int(validation_summary.get("total_rows") or 0))
                vr2.metric("Valid Rows", int(validation_summary.get("valid_rows") or 0))
                vr3.metric("Invalid Rows", int(validation_summary.get("invalid_rows") or 0))
                vr4.metric("Duplicate Barcodes", int(validation_summary.get("duplicate_barcodes") or 0))
                vr5.metric("Duplicate Item Codes", int(validation_summary.get("duplicate_item_codes") or 0))
                if invalid_rows:
                    st.warning("Some rows need attention before import can continue.")
                    st.dataframe(pd.DataFrame(invalid_rows), use_container_width=True, hide_index=True)
                else:
                    st.success("All validated rows passed the current checks.")
                st.caption("Validation complete. No inventory has been imported yet.")

                validated_stock_rows = st.session_state.get("validated_stock_rows") or []
                if validated_stock_rows:
                    import_summary_conn = None
                    try:
                        import_summary_conn = get_connection()
                        import_summary = _summarize_stock_import_targets(import_summary_conn, company_key, validated_stock_rows)
                    except Exception as exc:
                        import_summary = None
                        st.warning(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
                    finally:
                        if import_summary_conn:
                            import_summary_conn.close()

                    if import_summary:
                        st.markdown("Import Confirmation")
                        ic1, ic2, ic3, ic4 = st.columns(4)
                        ic1.metric("Total Rows", int(import_summary.get("total_rows") or 0))
                        ic2.metric("Valid Rows", int(import_summary.get("valid_rows") or 0))
                        ic3.metric("Items to Create", int(import_summary.get("items_to_create") or 0))
                        ic4.metric("Items That May Update", int(import_summary.get("items_that_may_update") or 0))

                        existing_item_behavior = st.radio(
                            "Existing item handling",
                            ["Increase stock (default)", "Skip existing items"],
                            index=0,
                            key=f"inventory_import_existing_behavior_{company_key}",
                        )
                        confirmed_import = st.checkbox(
                            "I confirm I want to import these items",
                            key=f"inventory_import_confirm_{company_key}",
                        )
                        if st.button("Import Valid Inventory", key=f"inventory_import_execute_{company_key}"):
                            if not confirmed_import:
                                st.warning("Please confirm the inventory import before continuing.")
                            else:
                                conn = None
                                try:
                                    conn = get_connection()
                                    import_result = _import_validated_stock_rows(
                                        conn,
                                        company_key,
                                        validated_stock_rows,
                                        "increase_stock" if existing_item_behavior == "Increase stock (default)" else "skip",
                                    )
                                    conn.commit()
                                    log_system_event(
                                        "INFO",
                                        "Stock Import",
                                        "Imported inventory for company_key={company_key} created={created} updated={updated} skipped={skipped}".format(
                                            company_key=company_key,
                                            created=import_result.get("created") or 0,
                                            updated=import_result.get("updated") or 0,
                                            skipped=import_result.get("skipped") or 0,
                                        ),
                                    )
                                    try:
                                        log_audit_action(
                                            conn,
                                            company_key,
                                            role,
                                            "Inventory Import",
                                            "Inventory",
                                            "Created {created}, Updated {updated}, Skipped {skipped}".format(
                                                created=import_result.get("created") or 0,
                                                updated=import_result.get("updated") or 0,
                                                skipped=import_result.get("skipped") or 0,
                                            ),
                                            branch_id=st.session_state.get("active_branch_id"),
                                        )
                                    except Exception:
                                        logger.debug("Inventory import audit logging skipped.", exc_info=True)
                                    st.session_state[inventory_import_result_key] = import_result
                                    st.session_state["validated_stock_rows"] = []
                                    st.session_state["invalid_stock_rows"] = []
                                    st.session_state.pop(inventory_import_validation_key, None)
                                    st.session_state.pop(inventory_import_preview_key, None)
                                    st.session_state.pop(inventory_import_mapping_key, None)
                                    _invalidate_inventory_search_cache()
                                except Exception as exc:
                                    if conn:
                                        conn.rollback()
                                    st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
                                finally:
                                    if conn:
                                        conn.close()

            import_result = st.session_state.get(inventory_import_result_key) or {}
            if import_result:
                st.markdown("Import Result Summary")
                ir1, ir2, ir3 = st.columns(3)
                ir1.metric("Items Created", int(import_result.get("created") or 0))
                ir2.metric("Items Updated", int(import_result.get("updated") or 0))
                ir3.metric("Items Skipped", int(import_result.get("skipped") or 0))
                st.caption(
                    "Import Reference: {reference} | Imported Items: {items} | Opening Value: {value}".format(
                        reference=import_result.get("import_reference") or "unknown",
                        items=int((import_result.get("created") or 0) + (import_result.get("updated") or 0)),
                        value=format_currency(float(import_result.get("posted_opening_value") or 0.0)),
                    )
                )
                if import_result.get("errors"):
                    st.warning("Some rows could not be imported.")
                    st.dataframe(pd.DataFrame(import_result.get("errors") or []), use_container_width=True, hide_index=True)
                else:
                    st.success("Inventory import completed successfully.")

                st.markdown("Post Opening Inventory Value to Accounts?")
                total_opening_value = round(float(import_result.get("posted_opening_value") or 0.0), 2)
                imported_item_count = int((import_result.get("created") or 0) + (import_result.get("updated") or 0))
                st.caption(
                    "Imported items: {items} | Total imported stock value: {value}".format(
                        items=imported_item_count,
                        value=format_currency(total_opening_value),
                    )
                )
                st.caption(
                    "Proposed entry: Debit Inventory | Credit Opening Balance Equity"
                )
                confirmed_opening_post = st.checkbox(
                    "I confirm I want to post opening inventory value to accounting",
                    key=f"inventory_import_opening_post_confirm_{company_key}",
                )
                if st.button("Post Opening Inventory Value", key=f"inventory_import_opening_post_btn_{company_key}"):
                    if total_opening_value <= 0:
                        st.warning("Opening inventory value is zero, so no accounting entry will be posted.")
                    elif not confirmed_opening_post:
                        st.warning("Please confirm the opening inventory posting before continuing.")
                    elif not require_permission(
                        role,
                        "post_accounting_document",
                        action_label="post opening inventory value",
                        company_key=company_key,
                        branch_id=st.session_state.get("active_branch_id"),
                    ):
                        pass
                    else:
                        conn = None
                        try:
                            conn = get_connection()
                            posting_result = _post_inventory_import_opening_value(
                                conn,
                                company_key,
                                str(import_result.get("import_reference") or "").strip(),
                                role,
                            )
                            conn.commit()
                            st.success(
                                "Opening inventory value posted successfully for {reference}.".format(
                                    reference=posting_result["import_reference"],
                                )
                            )
                            st.caption(
                                "Journal Entry ID: {entry_id} | Amount: {amount}".format(
                                    entry_id=posting_result["entry_id"],
                                    amount=format_currency(posting_result["amount"]),
                                )
                            )
                            import_result["opening_posted"] = True
                            import_result["opening_posted_entry_id"] = posting_result["entry_id"]
                            st.session_state[inventory_import_result_key] = import_result
                        except Exception as exc:
                            if conn:
                                conn.rollback()
                            st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
                        finally:
                            if conn:
                                conn.close()
                if import_result.get("opening_posted"):
                    st.info("Opening inventory accounting has already been posted for this import batch.")


# ==========================================
# VOUCHERS & JOURNALS
# ==========================================
def show_vouchers(company_key, role):
    st.header("📑 Vouchers & Journals")
    branch_id = st.session_state.get("active_branch_id")

    with st.expander("➕ Create New Voucher", expanded=True):
        with st.form("voucher_entry_form"):
            col1, col2 = st.columns(2)
            with col1:
                v_type = st.selectbox("Voucher Type", ["Payment", "Receipt", "Journal", "Sales", "Purchase", "Expense"])
                narration = st.text_area("Narration")
            with col2:
                amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01)
                ref_no = st.text_input("Reference Number")
                v_date = st.date_input("Date", datetime.now())

            if st.form_submit_button("Post Voucher"):
                if role == "Demo":
                    st.info("Voucher posting is disabled in Demo mode.")
                elif amount <= 0 or not narration:
                    st.warning("Please provide a valid amount and narration.")
                else:
                    try:
                        conn = get_connection()
                        legacy_voucher_id = _create_legacy_voucher_if_enabled(
                            conn,
                            company_key,
                            branch_id,
                            v_date.isoformat(),
                            v_type,
                            v_type,
                            amount,
                            role,
                            narration=narration,
                            reference_no=ref_no,
                        )
                        post_journal_entry(
                            company_key=company_key,
                            date=v_date,
                            description=narration,
                            reference=ref_no or (f"VCH-{legacy_voucher_id}" if legacy_voucher_id else f"JRN-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
                            lines=_voucher_posting_lines(conn, v_type, amount),
                            created_by=role,
                            branch_id=branch_id,
                            source_module="Vouchers" if legacy_voucher_id else "Journal Voucher",
                            source_table="vouchers" if legacy_voucher_id else "journal_entries",
                            source_id=int(legacy_voucher_id) if legacy_voucher_id else None,
                            conn=conn,
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Voucher Created", "Vouchers & Journals", f"Posted {v_type} voucher: {ref_no}", branch_id=branch_id)
                        conn.close()
                        st.success("Voucher posted successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))

    st.subheader("Voucher Ledger")
    try:
        conn = get_connection()
        if role == "Demo":
            rows = [
                {"Date": "2026-03-15", "Type": "Sales", "Narration": "Product Sale", "Amount": 5000.0, "Ref": "DEMO-001"},
            ]
            df = pd.DataFrame(rows)
        else:
            rows = get_recent_accounting_activity(company_key, branch_id=branch_id, limit=100, conn=conn)
            df = pd.DataFrame(
                [
                    {
                        "Date": row.get("date"),
                        "Type": row.get("activity_type"),
                        "Narration": row.get("description"),
                        "Amount": row.get("amount", 0.0),
                        "Ref": row.get("reference"),
                    }
                    for row in rows
                ]
            ) if rows else pd.DataFrame()
        conn.close()
        if not df.empty:
            st.dataframe(format_currency_dataframe(df), use_container_width=True)
        else:
            st.info("No vouchers found.")
    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))


# ==========================================
# CHART OF ACCOUNTS
# ==========================================
def show_chart_of_accounts(company_key, role):
    st.header("🗂️ Chart of Accounts")
    try:
        conn = get_connection()
        coa_diagnostics = get_chart_of_accounts_diagnostics(conn=conn)
        rows = execute_portable_query(
            conn,
            """
            SELECT
                COALESCE(account_code, '') AS account_code,
                COALESCE(name, account_name) AS account_name,
                COALESCE(category, account_type) AS account_type,
                COALESCE(posting_allowed, 1) AS posting_allowed,
                COALESCE(control_account, 0) AS control_account,
                COALESCE(allow_manual_posting, 1) AS allow_manual_posting,
                COALESCE(is_active, 1) AS is_active
            FROM chart_of_accounts
            ORDER BY COALESCE(account_code, ''), COALESCE(name, account_name)
            """,
        ).fetchall()
        if rows:
            df = pd.DataFrame(rows_to_dicts(rows))
            df = df.rename(
                columns={
                    "account_code": "Account Code",
                    "account_name": "Account Name",
                    "account_type": "Account Type",
                    "posting_allowed": "Posting Allowed",
                    "control_account": "Control Account",
                    "allow_manual_posting": "Manual Posting Allowed",
                    "is_active": "Active",
                }
            )
            st.dataframe(format_currency_dataframe(df), use_container_width=True)
        else:
            st.info("No chart of accounts entries found.")
        if coa_diagnostics.get("warnings"):
            st.warning("Account structure warnings: " + "; ".join(coa_diagnostics["warnings"]))
        else:
            st.success("Account structure checks passed.")
    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    if user_has_permission(role, "manage_chart_of_accounts"):
        with st.form("add_coa_form"):
            acc_code = st.text_input("Account Code")
            acc_name = st.text_input("Account Name")
            acc_type = st.selectbox("Account Type", ["Asset", "Liability", "Equity", "Income", "Expense"])
            if st.form_submit_button("Add Account"):
                if acc_name:
                    try:
                        if not require_permission(
                            role,
                            "manage_chart_of_accounts",
                            action_label="manage the chart of accounts",
                            company_key=company_key,
                        ):
                            return
                        conn = get_connection()
                        engine_get_or_create_account(conn, acc_name, _normalize_account_category(acc_type), account_code=acc_code)
                        conn.commit()
                        conn.close()
                        st.success("Account added.")
                        st.rerun()
                    except Exception as e:
                        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))


# ==========================================
# COMPANY SETUP
# ==========================================
def _render_migration_cleanup_review(role, session_company_key):
    """Dev / Master Admin panel for Phase 5B migration data cleanup."""
    st.subheader("Migration Cleanup Review")
    st.caption(
        "Review and fix migration warnings. POS branch and manager links are manual; "
        "payment reference uses a guarded apply with backup."
    )
    try:
        readiness = migration_cleanup_service.build_readiness_snapshot()
    except OSError as exc:
        st.warning(f"Could not read migration reports: {exc}")
        readiness = migration_cleanup_service.ReadinessSnapshot(
            refresh_hint="Run audit to refresh reports.",
            reports_stale=True,
        )
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Readiness", readiness.overall_score)
    with col2:
        st.metric("Go / No-Go", readiness.go_status)
    with col3:
        st.metric("Cleanup items", readiness.display_warning_total)
    st.markdown(
        f"- Summary: `{readiness.summary_path}`\n"
        f"- Audit: `{readiness.audit_path}`\n"
        f"- Cleanup plan: `{readiness.plan_path}`"
    )
    if readiness.plan_item_counts:
        st.caption(f"Plan breakdown: {readiness.plan_item_counts}")
    if readiness.summary_warning_total and readiness.summary_warning_total != readiness.display_warning_total:
        st.caption(f"Audit summary warnings: {readiness.warning_counts}")
    if readiness.reports_stale and readiness.refresh_hint:
        st.warning(readiness.refresh_hint)
    elif readiness.refresh_hint:
        st.info(readiness.refresh_hint)

    if st.button("Re-run Migration Integrity Audit (read-only)", key="migration_rerun_audit"):
        with st.spinner("Running integrity audit…"):
            audit_result = migration_cleanup_service.run_readonly_audit_subprocess()
            plan_result = migration_cleanup_service.run_readonly_plan_subprocess()
        if audit_result.get("ok") and plan_result.get("ok"):
            st.success("Audit and cleanup plan regenerated.")
            if audit_result.get("stdout"):
                st.code(audit_result["stdout"][-2000:])
        else:
            st.error("Audit/plan script failed.")
            if audit_result.get("stderr"):
                st.code(audit_result["stderr"])
            if plan_result.get("stderr"):
                st.code(plan_result["stderr"])
        st.info(
            "After manual fixes, re-run:\n"
            "`python scripts/run_migration_integrity_audit.py`\n"
            "`python scripts/plan_migration_data_cleanup.py`"
        )
        st.rerun()

    plan = migration_cleanup_service.load_cleanup_plan_json()
    scope_key = None if _normalize_role_name(role) == "Dev" else session_company_key
    tab_pos, tab_mgr, tab_pay = st.tabs(
        ["POS branch assignment", "Branch managers", "Payment reference"]
    )

    def _readonly_db_unavailable_message(exc):
        if migration_cleanup_service.is_database_locked_error(exc):
            return (
                "Database is temporarily locked (another process or open connection). "
                "Close other ERP sessions and retry, or refresh after a few seconds."
            )
        return build_user_safe_error(exc, role)

    with tab_pos:
        st.markdown(
            "Assign `branch_id` on POS sales only. Receipt numbers and journals are not modified."
        )
        try:
            with migration_cleanup_service.readonly_connection() as conn:
                sales = migration_cleanup_service.list_pos_sales_missing_branch(
                    conn, role=role, company_key=scope_key
                )
                branch_cache: dict[str, list] = {}
                for sale in sales:
                    ck = sale["company_key"]
                    if ck not in branch_cache:
                        branch_cache[ck] = conn.execute(
                            """
                            SELECT branch_id, branch_name, branch_code
                            FROM branches
                            WHERE company_key = ? AND COALESCE(is_active, 1) = 1
                            ORDER BY branch_name
                            """,
                            (ck,),
                        ).fetchall()
        except sqlite3.OperationalError as exc:
            st.warning(_readonly_db_unavailable_message(exc))
            sales = []
            branch_cache = {}
        if not sales:
            st.success("No POS sales missing branch_id in scope.")
        for sale in sales:
            sale_id = int(sale["id"])
            ck = sale["company_key"]
            branches = branch_cache.get(ck, [])
            branch_labels = [
                f"{b[1]} ({b[2] or b[0]})" if not isinstance(b, sqlite3.Row) else
                f"{b['branch_name']} ({b['branch_code'] or b['branch_id']})"
                for b in branches
            ]
            branch_ids = [
                b[0] if not isinstance(b, sqlite3.Row) else b["branch_id"] for b in branches
            ]
            suggested = sale.get("suggested_branch_id")
            default_index = branch_ids.index(suggested) if suggested in branch_ids else 0
            with st.expander(
                f"Sale #{sale_id} — {sale.get('receipt_number')} — {sale.get('company_name') or ck}",
                expanded=False,
            ):
                st.write(
                    f"Date: {sale.get('sale_datetime') or sale.get('sale_date')} | "
                    f"Cashier: {sale.get('cashier')} | Total: {sale.get('grand_total')}"
                )
                if suggested:
                    st.caption(f"Suggested branch (single active branch): {suggested}")
                if not branch_ids:
                    st.warning("No active branches for this company.")
                else:
                    selected_label = st.selectbox(
                        "Target branch",
                        branch_labels,
                        index=default_index,
                        key=f"mig_pos_branch_{sale_id}",
                    )
                    target_branch = branch_ids[branch_labels.index(selected_label)]
                    confirm = st.checkbox(
                        "I confirm assigning this branch to the POS sale",
                        key=f"mig_pos_confirm_{sale_id}",
                    )
                    if st.button("Save branch assignment", key=f"mig_pos_save_{sale_id}"):
                        write_conn = get_connection()
                        if not write_conn:
                            st.error("Could not open database for update.")
                        else:
                            try:
                                result = migration_cleanup_service.assign_pos_sale_branch_id(
                                    write_conn,
                                    company_key=ck,
                                    sale_id=sale_id,
                                    branch_id=target_branch,
                                    actor_role=role,
                                    confirmed=confirm,
                                )
                                if result.get("ok"):
                                    st.success(f"Assigned branch {target_branch} to sale #{sale_id}.")
                                    st.rerun()
                                else:
                                    st.error(result.get("reason", "Update failed."))
                            except sqlite3.OperationalError as exc:
                                st.error(_readonly_db_unavailable_message(exc))
                            finally:
                                write_conn.close()

    with tab_mgr:
        st.markdown("Link `manager_user_id` using existing branch manager assignment rules.")
        try:
            with migration_cleanup_service.readonly_connection() as conn:
                branches_missing = migration_cleanup_service.list_branches_missing_manager(
                    conn, role=role, company_key=scope_key
                )
                manager_options_cache = {
                    (b["company_key"], b["branch_id"]): fetch_branch_manager_select_options(
                        conn, b["company_key"], b["branch_id"]
                    )
                    for b in branches_missing
                }
        except sqlite3.OperationalError as exc:
            st.warning(_readonly_db_unavailable_message(exc))
            branches_missing = []
            manager_options_cache = {}
        if not branches_missing:
            st.success("No branches missing manager_user_id in scope.")
        for branch in branches_missing:
            bid = branch["branch_id"]
            ck = branch["company_key"]
            with st.expander(
                f"{branch.get('branch_name')} — {branch.get('company_name') or ck}",
                expanded=False,
            ):
                st.write(
                    f"Branch code: {branch.get('branch_code') or '—'} | "
                    f"Display manager text: {branch.get('branch_manager') or '—'}"
                )
                options = manager_options_cache.get((ck, bid), [])
                eligible = [o for o in options if o.get("user_id")]
                if not eligible:
                    st.warning(
                        "No eligible users with user_id. Create or repair the user record in Staff Management."
                    )
                else:
                    labels = [
                        f"{o.get('full_name')} ({o.get('role')}) — {o.get('user_id')[:12]}…"
                        if len(str(o.get("user_id") or "")) > 12
                        else f"{o.get('full_name')} ({o.get('role')}) — {o.get('user_id')}"
                        for o in eligible
                    ]
                    selected = st.selectbox(
                        "Manager user",
                        labels,
                        key=f"mig_mgr_select_{bid}",
                    )
                    manager_user_id = eligible[labels.index(selected)]["user_id"]
                    promote = st.checkbox(
                        "Promote to Branch Manager role",
                        value=True,
                        key=f"mig_mgr_promote_{bid}",
                    )
                    confirm = st.checkbox(
                        "I confirm assigning this branch manager",
                        key=f"mig_mgr_confirm_{bid}",
                    )
                    if st.button("Save manager", key=f"mig_mgr_save_{bid}"):
                        if not confirm:
                            st.error("Confirmation required.")
                        else:
                            write_conn = get_connection()
                            if not write_conn:
                                st.error("Could not open database for update.")
                            else:
                                try:
                                    result = assign_branch_manager(
                                        write_conn,
                                        ck,
                                        bid,
                                        manager_user_id,
                                        promote_to_branch_manager=promote,
                                    )
                                    if result.get("ok"):
                                        log_audit_action(
                                            write_conn,
                                            ck,
                                            role,
                                            "Migration cleanup: branch manager assigned",
                                            "Migration Cleanup",
                                            details=f"branch_id={bid} manager_user_id={manager_user_id}",
                                            branch_id=bid,
                                            action_type="data_cleanup",
                                        )
                                        write_conn.commit()
                                        st.success("Branch manager linked.")
                                        st.rerun()
                                    else:
                                        st.error(result.get("reason", "Assignment failed."))
                                except sqlite3.OperationalError as exc:
                                    st.error(_readonly_db_unavailable_message(exc))
                                finally:
                                    write_conn.close()

    with tab_pay:
        st.markdown(
            "Guarded fix for payment customer/reference only. Requires backup and explicit confirmation."
        )
        try:
            with migration_cleanup_service.readonly_connection() as conn:
                payments = migration_cleanup_service.list_payment_reference_candidates(
                    conn, plan, role=role, company_key=scope_key
                )
        except sqlite3.OperationalError as exc:
            st.warning(_readonly_db_unavailable_message(exc))
            payments = []
        if not payments:
            st.info("No auto-fix-safe payment candidates in the current plan.")
        for payment in payments:
            pid = int(payment["id"])
            ck = payment["company_key"]
            proposed = payment.get("proposed_values") or {}
            with st.expander(
                f"Payment #{pid} — {payment.get('company_name') or ck} — GHS {payment.get('amount')}",
                expanded=True,
            ):
                st.write(f"Type: {payment.get('payment_type')}")
                st.write(f"Current customer_id: {payment.get('customer_id')}")
                st.write(f"Current reference: {payment.get('reference')!r}")
                st.write(
                    f"Proposed customer_id: {proposed.get('customer_id')} | "
                    f"reference: {proposed.get('reference')!r}"
                )
                if not payment.get("still_needs_fix"):
                    st.warning("Payment no longer matches expected bad state.")
                else:
                    confirm = st.checkbox(
                        "I confirm applying the payment reference fix",
                        key=f"mig_pay_confirm_{pid}",
                    )
                    confirm_text = st.text_input(
                        "Type confirmation phrase",
                        key=f"mig_pay_text_{pid}",
                        placeholder=migration_cleanup_service.CONFIRM_PAYMENT_APPLY_TEXT,
                    )
                    if st.button("Apply payment fix (creates backup)", key=f"mig_pay_apply_{pid}"):
                        write_conn = get_connection()
                        if not write_conn:
                            st.error("Could not open database for update.")
                        else:
                            try:
                                result = migration_cleanup_service.apply_payment_reference_fix(
                                    write_conn,
                                    company_key=ck,
                                    payment_id=pid,
                                    customer_id=int(proposed["customer_id"]),
                                    reference=str(proposed["reference"]),
                                    actor_role=role,
                                    confirmed=confirm,
                                    confirmation_text=confirm_text,
                                    create_backup=True,
                                )
                                if result.get("ok"):
                                    st.success(
                                        f"Payment updated. Backup: {result.get('backup_path') or 'n/a'}"
                                    )
                                    st.rerun()
                                else:
                                    st.error(result.get("reason", "Apply failed."))
                            except sqlite3.OperationalError as exc:
                                st.error(_readonly_db_unavailable_message(exc))
                            finally:
                                write_conn.close()

    st.caption(
        "Journal entries are not updated by this panel. After POS branch fixes, review linked journals manually if needed."
    )


def show_company_setup(company_key, company_name, role):
    st.header("⚙️ System Configuration")
    if not require_permission(role, "manage_company", action_label="manage company settings", company_key=company_key):
        return
    if can_access_migration_cleanup(role):
        _render_migration_cleanup_review(role, company_key)
        st.markdown("---")
    st.subheader("Company Profile")
    conn = None
    try:
        conn = get_connection()
        conn.execute("ALTER TABLE users ADD COLUMN user_id TEXT")
    except sqlite3.Error:
        pass
    try:
        if conn:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_user_id_runtime ON users(user_id)")
    except sqlite3.Error:
        pass
    try:
        company = conn.execute("SELECT * FROM companies WHERE key = ?", (company_key,)).fetchone()
        company_data = dict(company) if company is not None else {}
        if company:
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Company Name", value=company_data["name"], disabled=True)
                st.text_input("License Key", value=company_data["key"], disabled=True)
                st.text_input("ERP Access", value="Full ERP Access", disabled=True)
            with col2:
                expiry_value = company_data.get("subscription_expiry") or company_data.get("subscription_end_date") or "N/A"
                st.text_input("Subscription Expiry", value=str(expiry_value), disabled=True)
                st.text_input("Status", value=company_data.get("status", "Active"), disabled=True)
                st.text_input("Contact Email", value=str(company_data.get("contact_email") or company_data.get("admin_email") or ""), disabled=True)

            if role in ("Master Admin", "Sub-Admin"):
                edit_settings_key = f"company_settings_edit_{company_key}"
                settings_col, button_col = st.columns([4, 1])
                settings_col.caption(
                    f"{company_data.get('name')} | {company_data.get('contact_email') or company_data.get('admin_email') or 'No email'}"
                )
                if button_col.button("Edit", key=f"company_settings_edit_btn_{company_key}"):
                    st.session_state[edit_settings_key] = True
                if st.session_state.get(edit_settings_key):
                    with st.form(f"company_settings_form_{company_key}", clear_on_submit=True):
                        updated_contact_email = st.text_input(
                            "Edit Contact Email",
                            value=str(company_data.get("contact_email") or company_data.get("admin_email") or ""),
                        )
                        updated_barcode_input_source = st.selectbox(
                            "Default Barcode Input Mode",
                            ["Keyboard Entry", "Camera Scanner", "Physical Scanner"],
                            index=["Keyboard Entry", "Camera Scanner", "Physical Scanner"].index(
                                company_data.get("barcode_input_source", "Keyboard Entry")
                                if company_data.get("barcode_input_source", "Keyboard Entry") in ["Keyboard Entry", "Camera Scanner", "Physical Scanner"]
                                else "Keyboard Entry"
                            ),
                        )
                        if st.form_submit_button("Update Client Settings"):
                            if not require_permission(
                                role,
                                "manage_company",
                                action_label="update company settings",
                                company_key=company_key,
                                conn=conn,
                            ):
                                return
                            conn.execute(
                                """
                                UPDATE companies
                                SET contact_email = ?, barcode_input_source = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE key = ?
                                """,
                                (updated_contact_email, updated_barcode_input_source, company_key),
                            )
                            conn.commit()
                            log_audit_action(
                                conn,
                                company_key,
                                role,
                                "Client Settings Updated",
                                "Company Setup",
                                f"contact_email={updated_contact_email}, full_erp_access=enabled",
                            )
                            st.session_state.pop(edit_settings_key, None)
                            st.success("Entry Updated")
                            st.rerun()

            if user_has_permission(role, "manage_branches") or user_has_permission(role, "manage_users"):
                st.markdown("---")
                st.subheader("Branch Deployment")
                deploy_conn = get_connection()
                try:
                    ensure_branch_licensing_schema_integrity(deploy_conn)
                    _render_branch_list_with_grants(deploy_conn, company_key, role)
                    license_snapshot = get_company_branch_license_snapshot(deploy_conn, company_key)
                    if license_snapshot.get("can_create_active_branch"):
                        _render_branch_creation_form(
                            deploy_conn,
                            company_key,
                            role,
                            form_key_prefix="company_setup_deploy",
                        )
                    else:
                        _render_branch_license_status(deploy_conn, company_key)
                        st.warning(
                            "Active branch license limit reached. Add an inactive branch below or contact support to increase max_branches."
                        )
                        with st.expander("Deploy inactive branch"):
                            _render_branch_creation_form(
                                deploy_conn,
                                company_key,
                                role,
                                form_key_prefix="company_setup_deploy_inactive",
                                default_active=False,
                            )
                except Exception as exc:
                    st.error(build_user_safe_error(exc, role))
                finally:
                    deploy_conn.close()

                st.markdown("---")
                st.subheader("Staff Management")
                staff_conn = get_connection()
                try:
                    with st.form("company_setup_staff_form"):
                        staff_name = st.text_input("Full Name")
                        staff_role = st.selectbox("Role", ["Bookkeeper", "Staff"])
                        manual_login_key = st.text_input("Staff Login Key (Manual)", type="password")
                        staff_password = st.text_input("Assign Password", type="password")
                        submitted = st.form_submit_button("Create Staff Login")

                        if submitted:
                            if not require_permission(
                                role,
                                "manage_users",
                                action_label="manage users",
                                company_key=company_key,
                                conn=staff_conn,
                            ):
                                return
                            if not staff_name.strip():
                                st.warning("Enter a staff name before creating a login.")
                            elif not manual_login_key.strip():
                                st.warning("Enter a manual staff login key before creating the staff login.")
                            elif not staff_password:
                                st.warning("Assign a password before creating the staff login.")
                            else:
                                try:
                                    existing_key = staff_conn.execute(
                                        "SELECT 1 FROM users WHERE login_key = ? LIMIT 1",
                                        (manual_login_key.strip(),),
                                    ).fetchone()
                                    if existing_key:
                                        st.error("This staff login key already exists. Choose a different manual key.")
                                        return
                                    user_id = _generate_user_id(company_key, staff_name, manual_login_key)
                                    staff_conn.execute(
                                        """
                                        INSERT INTO users (company_key, full_name, user_id, login_key, password_hash, role, status)
                                        VALUES (?, ?, ?, ?, ?, ?, 'Active')
                                        """,
                                        (
                                            company_key,
                                            staff_name.strip(),
                                            user_id,
                                            manual_login_key.strip(),
                                            _hash_staff_password(staff_password),
                                            staff_role,
                                        ),
                                    )
                                    log_audit_action(
                                        staff_conn,
                                        company_key,
                                        role,
                                        "Staff Login Created",
                                        "Company Setup",
                                        f"{staff_name.strip()} created as {staff_role} with user_id {user_id[:12]}...",
                                    )
                                    staff_conn.commit()
                                    st.success("Staff login created successfully.")
                                except Exception as exc:
                                    staff_conn.rollback()
                                    st.error(build_user_safe_error(exc, role))

                    users = staff_conn.execute(
                        """
                        SELECT full_name, role, user_id, status, created_at
                        FROM users
                        WHERE company_key = ?
                        ORDER BY created_at DESC
                        """,
                        (company_key,),
                    ).fetchall()
                    if users:
                        users_df = pd.DataFrame(
                            users,
                            columns=["Full Name", "Role", "User ID", "Status", "Created At"],
                        )
                        users_df["User ID"] = users_df["User ID"].fillna("").map(
                            lambda value: f"{str(value)[:8]}..." if str(value) else ""
                        )
                        st.dataframe(format_currency_dataframe(users_df), use_container_width=True)
                    else:
                        st.caption("No staff logins created yet.")
                finally:
                    staff_conn.close()
        else:
            st.info("Company profile not found.")
    except Exception as e:
        st.error(build_user_safe_error(e, role))
    finally:
        if conn:
            conn.close()


# ==========================================
# POINT OF SALE (POS)
# ==========================================
def show_pos(company_key, company_name, role):
    render_ui_standard_styles()
    page_header("🛒 Point of Sale", subtitle="Fast checkout and inventory-aware POS")
    receipt_key = f"pos_receipt_{company_key}"
    last_receipt_data_key = f"pos_last_receipt_data_{company_key}"
    checkout_complete_key = f"pos_checkout_complete_{company_key}"
    checkout_request_key = f"pos_checkout_request_{company_key}"
    pos_success_key = f"pos_sale_success_{company_key}"
    void_success_key = f"pos_void_success_{company_key}"
    pos_message_key = f"pos_message_{company_key}"
    pos_scan_beep_key = f"pos_scan_beep_{company_key}"
    pos_scan_input_key = "pos_barcode_input"
    pos_pending_scan_key = f"pos_pending_scan_{company_key}"
    pos_product_search_key = f"pos_product_search_{company_key}"
    pos_product_select_key = f"pos_product_select_{company_key}"
    pos_scan_focus_key = f"pos_scan_focus_request_{company_key}"
    pos_return_lookup_result_key = f"pos_return_lookup_result_{company_key}"
    pos_manager_approval_identifier_key = f"pos_manager_approval_identifier_{company_key}"
    pos_manager_approval_reason_key = f"pos_manager_approval_reason_{company_key}"
    cart_key = f"pos_cart_{company_key}"
    if role == "Demo":
        _demo_notice()
        st.info("Demo POS: Select items and process a mock sale.")
        demo_items = ["Product A - GHS 120.00", "Product B - GHS 75.00", "Product C - GHS 200.00"]
        selected = st.multiselect("Select Items", demo_items)
        if selected:
            st.success(f"Demo sale: {len(selected)} item(s) selected. Total: GHS {len(selected) * 120:.2f}")
        return
    if not require_permission(
        role,
        "sell_pos",
        action_label="access point of sale",
        company_key=company_key,
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return

    if st.session_state.get(pos_success_key):
        _trigger_scan_feedback(pos_message_key, "Sale processed successfully.")
        st.session_state.pop(pos_success_key, None)
    if st.session_state.get(void_success_key):
        _trigger_scan_feedback(pos_message_key, "Transaction voided")
        st.session_state.pop(void_success_key, None)

    _render_flash_message(pos_message_key, pos_scan_beep_key)
    scanner_cart_summary = _get_pos_cart_summary(company_key)
    with card_container("Sale Summary"):
        sale_summary_col1, sale_summary_col2, sale_summary_col3, sale_summary_col4 = st.columns([1, 1, 1, 1])
        sale_summary_col1.metric("Cart Items", scanner_cart_summary["item_count"])
        sale_summary_col2.metric("Subtotal", format_currency(scanner_cart_summary["subtotal"]))
        sale_summary_col3.metric("Cart Total", format_currency(scanner_cart_summary["grand_total"]))
        sale_summary_col4.metric("Discount", format_currency(scanner_cart_summary["discount_total"]))
        if st.button("Quick Clear Cart", key=f"pos_quick_clear_cart_{company_key}", use_container_width=True):
            _clear_pos_cart_state(company_key)
            st.session_state[checkout_complete_key] = False
            _trigger_scan_feedback(pos_message_key, "Cart cleared.", "info")
            st.rerun()
    st.markdown(
        """
        <div class="eka-card" style="padding:10px 12px;">
            <div style="display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;">
                <strong style="color:#0f172a;">Keyboard</strong>
                <span style="color:#475569;">F1 = Scan</span>
                <span style="color:#475569;">F2 = Manual Entry</span>
                <span style="color:#475569;">F3 = Search</span>
                <span style="color:#475569;">F4 = Checkout Panel</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _inject_pos_keyboard_shortcuts(company_key)

    try:
        conn = get_connection()
        ensure_cashier_closings_schema(conn)
        ensure_pos_sales_schema(conn)
        company_row = execute_portable_query(
            conn,
            "SELECT name, barcode_input_source FROM companies WHERE key = ?",
            (company_key,),
        ).fetchone()
        active_branch_id = st.session_state.get("active_branch_id")
        branch_row = None
        if active_branch_id:
            branch_row = execute_portable_query(
                conn,
                "SELECT branch_name FROM branches WHERE company_key = ? AND branch_id = ?",
                (company_key, active_branch_id),
            ).fetchone()
        items = execute_portable_query(
            conn,
            f"SELECT {INVENTORY_POS_LOOKUP_COLUMNS} FROM inventory WHERE company_key = ? AND qty > 0",
            (company_key,),
        ).fetchall()
        customers = get_customer_balances(company_key, conn=conn)
        conn.close()

        company_label = row_get(company_row, "name", row_get(company_row, 0, company_name)) if company_row else company_name
        branch_label = row_get(branch_row, "branch_name", "") if branch_row else ""
        barcode_input_source = row_get(company_row, "barcode_input_source", row_get(company_row, 1, "Keyboard Entry")) if company_row else "Keyboard Entry"
        items_df = pd.DataFrame(rows_to_dicts(items)) if items else pd.DataFrame()
        if not items_df.empty:
            items_df = items_df.rename(
                columns={
                    "id": "ID",
                    "item_name": "Item Name",
                    "item_code": "Item Code",
                    "category": "Category",
                    "brand": "Brand",
                    "qty": "Qty",
                    "price": "Price",
                    "cost_price": "Cost Price",
                    "barcode": "Barcode",
                    "min_stock_level": "Min Stock Level",
                    "tax_rate": "Tax Rate",
                    "expiry_date": "Expiry Date",
                }
            )
        if not items_df.empty:
            items_df["Barcode"] = items_df["Barcode"].fillna("")
        receipt_html_key = f"pos_receipt_html_{company_key}"
        receipt_print_trigger_key = f"pos_receipt_print_trigger_{company_key}"
        do_print_key = "do_print"


        def _render_pos_workflow_column(barcode_input_source):
            section_header("Scan / Search / Add Item")
            st.markdown('<div class="eka-card">', unsafe_allow_html=True)
            source_options = ["Keyboard Entry", "Camera Scanner", "Physical Scanner"]
            source_index = source_options.index(barcode_input_source) if barcode_input_source in source_options else 0
            selected_barcode_source = st.selectbox(
                "Barcode Input Source",
                source_options,
                index=source_index,
                key=f"pos_barcode_source_{company_key}",
            )
            if selected_barcode_source != barcode_input_source:
                try:
                    conn = get_connection()
                    conn.execute(
                        "UPDATE companies SET barcode_input_source = ? WHERE key = ?",
                        (selected_barcode_source, company_key),
                    )
                    conn.commit()
                except Exception:
                    pass
                finally:
                    if conn:
                        conn.close()
                barcode_input_source = selected_barcode_source

            item_mode = st.radio(
                "Item Entry Mode",
                ["From Stock", "Manual Entry"],
                horizontal=True,
                key=f"pos_item_mode_{company_key}",
            )
            if item_mode == "From Stock":
                st.caption(f"Barcode input mode: {barcode_input_source}")
                with st.form(key=f"pos_form_{company_key}", clear_on_submit=True):
                    st.text_input(
                        "Scan Barcode",
                        key=pos_scan_input_key,
                        placeholder="Scan barcode and press Enter",
                    )
                    if barcode_input_source == "Camera Scanner":
                        _render_camera_scanner(f"pos_{company_key}", pos_pending_scan_key)
                    submitted = st.form_submit_button("Scan Barcode", use_container_width=True)
                    if submitted:
                        pending_pos_barcode = str(st.session_state.get(pos_scan_input_key, "") or "").strip()
                        if pending_pos_barcode:
                            scan_added = False
                            conn = None
                            try:
                                conn = get_connection()
                                matched_item, lookup_source, match_scope = _lookup_inventory_for_pos(conn, company_key, pending_pos_barcode)
                                normalized_match = _normalize_pos_item_row(matched_item) if matched_item else {}
                                add_block_reason = _get_pos_add_block_reason(normalized_match) if matched_item and match_scope == "in_company" else None
                                if matched_item and match_scope == "in_company" and not add_block_reason:
                                    st.session_state[checkout_complete_key] = False
                                    st.session_state.pop(receipt_key, None)
                                    st.session_state.pop(receipt_html_key, None)
                                    cart_line = _add_item_to_pos_cart(company_key, normalized_match)
                                    scan_added = True
                                    logger.info(
                                        "POS scanner input matched item '%s' via %s for company %s",
                                        matched_item["item_name"],
                                        lookup_source or "unknown",
                                        company_key,
                                    )
                                    _trigger_scan_feedback(
                                        pos_message_key,
                                        "{item_name} added at {price}. Qty in cart: {qty}.".format(
                                            item_name=matched_item["item_name"],
                                            price=format_currency(float(cart_line.get("price") or 0.0)),
                                            qty=int(cart_line.get("qty") or 0),
                                        ),
                                        "success",
                                        pos_scan_beep_key,
                                    )
                                    low_stock_warning = _get_pos_low_stock_warning(cart_line)
                                    if low_stock_warning:
                                        st.warning(low_stock_warning)
                                    _request_pos_barcode_scan_focus(company_key)
                                elif matched_item and match_scope == "in_company" and add_block_reason:
                                    logger.info(
                                        "POS scanner blocked add for item '%s' (%s) company %s",
                                        matched_item["item_name"],
                                        add_block_reason,
                                        company_key,
                                    )
                                    _trigger_scan_feedback(
                                        pos_message_key,
                                        add_block_reason,
                                        "warning",
                                    )
                                elif matched_item and match_scope == "other_company":
                                    logger.info(
                                        "POS scanner found matching item under another company context while active company is %s",
                                        company_key,
                                    )
                                    _trigger_scan_feedback(
                                        pos_message_key,
                                        "Product exists under another company context and is unavailable in this POS.",
                                        "warning",
                                    )
                                else:
                                    logger.info(
                                        "POS scanner input '%s' did not match any product for active company %s",
                                        pending_pos_barcode,
                                        company_key,
                                    )
                                    _trigger_scan_feedback(
                                        pos_message_key,
                                        "Product not found",
                                        "warning",
                                    )
                            except Exception as exc:
                                st.error(build_user_safe_error(exc, role))
                            finally:
                                if conn:
                                    conn.close()
                                if scan_added:
                                    st.rerun()

                if items_df.empty:
                    st.info("No stock available for sale. Switch to Manual Entry to continue.")
                else:
                    picker_reset_key = f"pos_picker_reset_{company_key}"
                    picker_nonce = int(st.session_state.get(picker_reset_key) or 0)
                    search_input_key = f"{pos_product_search_key}_{picker_nonce}"
                    search_results_key = f"{pos_product_select_key}_{picker_nonce}"
                    stock_item_key = f"pos_item_{company_key}_{picker_nonce}"
                    stock_qty_key = f"pos_qty_{company_key}_{picker_nonce}"

                    search_expanded = bool(str(st.session_state.get(search_input_key, "") or "").strip())
                    with st.expander("Search / pick item (optional)", expanded=search_expanded):
                        st.text_input(
                            "Search Product",
                            key=search_input_key,
                            placeholder="Search by name, barcode, or item code (starts after 1 character)",
                        )
                        product_search_term = str(st.session_state.get(search_input_key, "") or "").strip()
                        manual_search_options = []
                        if len(product_search_term) >= 1:
                            try:
                                manual_search_options = _cached_pos_inventory_search_rows(company_key, product_search_term)
                            except Exception as exc:
                                st.warning(build_user_safe_error(exc, role))
                            if not manual_search_options:
                                st.info("No matching stock items found for that search.")
                        if manual_search_options:
                            manual_option_labels = [
                                "{name} | {identifier} | {price} | Stock {qty:,.2f}{suffix}".format(
                                    name=row["item_name"],
                                    identifier=row["barcode"] or row["item_code"] or "N/A",
                                    price=format_currency(float(row["price"] or 0.0)),
                                    qty=float(row["qty"] or 0.0),
                                    suffix=_format_pos_search_status_suffix(row),
                                )
                                for row in manual_search_options
                            ]
                            selected_search_label = st.selectbox(
                                "Manual Product Search Results",
                                manual_option_labels,
                                key=search_results_key,
                            )
                            selected_search_row = manual_search_options[manual_option_labels.index(selected_search_label)]
                            preview_stock_status = _get_inventory_stock_status(
                                selected_search_row.get("qty"),
                                selected_search_row.get("min_stock_level"),
                            )
                            preview_expiry_status = _get_inventory_expiry_status(selected_search_row.get("expiry_date"))
                            preview_badges = " ".join(
                                part
                                for part in (
                                    _inventory_stock_status_badge(preview_stock_status),
                                    _inventory_expiry_status_badge(preview_expiry_status),
                                )
                                if part
                            )
                            if preview_badges:
                                st.caption(f"Selected item: {preview_badges}")
                            selected_add_block_reason = _get_pos_add_block_reason(selected_search_row)
                            if selected_add_block_reason:
                                st.warning(selected_add_block_reason)
                            if st.button(
                                "Add Search Result",
                                key=f"pos_add_search_result_{company_key}",
                                use_container_width=True,
                                disabled=bool(selected_add_block_reason),
                            ):
                                st.session_state[checkout_complete_key] = False
                                st.session_state.pop(receipt_key, None)
                                st.session_state.pop(receipt_html_key, None)
                                cart_line = _add_item_to_pos_cart(company_key, selected_search_row)
                                logger.info(
                                    "POS manual search added item '%s' for company %s",
                                    selected_search_row["item_name"],
                                    company_key,
                                )
                                _trigger_scan_feedback(
                                    pos_message_key,
                                    f"Added {selected_search_row['item_name']} to the active sale.",
                                    "success",
                                )
                                low_stock_warning = _get_pos_low_stock_warning(cart_line)
                                if low_stock_warning:
                                    st.warning(low_stock_warning)
                                _request_pos_barcode_scan_focus(company_key)
                                st.session_state[picker_reset_key] = picker_nonce + 1
                                st.rerun()
                        selected_item = st.selectbox("Select Item", items_df["Item Name"].tolist(), key=stock_item_key)
                        qty_to_sell = st.number_input("Quantity", min_value=1, value=1, key=stock_qty_key)
                        selected_picker_row = items_df.loc[items_df["Item Name"] == selected_item].iloc[0]
                        picker_payload = {
                            "id": int(selected_picker_row["ID"]),
                            "item_name": selected_picker_row["Item Name"],
                            "item_code": selected_picker_row["Item Code"],
                            "barcode": selected_picker_row["Barcode"],
                            "price": float(selected_picker_row["Price"] or 0.0),
                            "cost_price": float(selected_picker_row["Cost Price"] or 0.0),
                            "tax_rate": float(selected_picker_row["Tax Rate"] or 0.0),
                            "qty": float(selected_picker_row["Qty"] or 0.0),
                            "min_stock_level": float(selected_picker_row["Min Stock Level"] or 0.0),
                            "expiry_date": selected_picker_row.get("Expiry Date"),
                        }
                        picker_add_block_reason = _get_pos_add_block_reason(picker_payload)
                        if picker_add_block_reason:
                            st.warning(picker_add_block_reason)
                        if st.button(
                            "Add Selected Item",
                            key=f"pos_add_selected_{company_key}",
                            use_container_width=True,
                            disabled=bool(picker_add_block_reason),
                        ):
                            st.session_state[checkout_complete_key] = False
                            st.session_state.pop(receipt_key, None)
                            st.session_state.pop(receipt_html_key, None)
                            for _ in range(int(qty_to_sell)):
                                _add_item_to_pos_cart(company_key, picker_payload)
                            added_line = next((line for line in st.session_state.get(cart_key, []) if str(line.get("item_name") or line.get("name")) == str(selected_item)), None)
                            _trigger_scan_feedback(pos_message_key, f"Added {selected_item} x{int(qty_to_sell)} to the cart.")
                            low_stock_warning = _get_pos_low_stock_warning(added_line)
                            if low_stock_warning:
                                st.warning(low_stock_warning)
                            _request_pos_barcode_scan_focus(company_key)
                            st.session_state[picker_reset_key] = picker_nonce + 1
                            st.rerun()
                if st.session_state.pop(pos_scan_focus_key, False) and not st.session_state.get(checkout_complete_key):
                    _focus_pos_barcode_scanner()
            else:
                st.subheader("Manual Item Entry")
                manual_item_name = st.text_input("New Item Name", key=f"manual_pos_item_{company_key}")
                manual_price = st.number_input(
                    f"Manual Price ({st.session_state.currency_symbol})",
                    min_value=0.0,
                    value=0.0,
                    key=f"manual_pos_price_{company_key}",
                )
                manual_qty = st.number_input("Quantity", min_value=1, value=1, key=f"manual_pos_qty_{company_key}")
                if st.button("Add Manual Item", key=f"pos_add_manual_{company_key}", use_container_width=True):
                    if manual_item_name and float(manual_price) > 0:
                        st.session_state[checkout_complete_key] = False
                        st.session_state.pop(receipt_key, None)
                        st.session_state.pop(receipt_html_key, None)
                        cart = st.session_state.setdefault(cart_key, [])
                        manual_line = {
                            "inventory_item_id": None,
                            "item_id": None,
                            "name": manual_item_name.strip(),
                            "item_name": manual_item_name.strip(),
                            "item_code": "",
                            "barcode": "",
                            "price": float(manual_price),
                            "cost_price": 0.0,
                            "tax_rate": 0.0,
                            "available_qty": None,
                            "min_stock_level": 0.0,
                            "qty": int(manual_qty),
                            "is_manual": True,
                            "line_discount_type": "amount",
                            "line_discount_value": 0.0,
                            "line_discount": 0.0,
                            "line_total": 0.0,
                        }
                        _recalculate_pos_line(manual_line)
                        cart.append(manual_line)
                        st.session_state[cart_key] = cart
                        _trigger_scan_feedback(pos_message_key, f"Added manual item {manual_item_name.strip()} to the cart.")
                        _request_pos_barcode_scan_focus(company_key)
                        st.rerun()
                    else:
                        st.warning("Enter a valid manual item and price before adding it.")
            st.markdown("</div>", unsafe_allow_html=True)

            cart = st.session_state.setdefault(cart_key, [])
            cart_summary = _get_pos_cart_summary(company_key)
            discount_state = _get_pos_cart_discount_state(company_key)
            discount_approval_state = _get_pos_discount_approval_state(company_key)
            cash_tendered = 0.0
            payment_reference = ""
            section_header("Active Cart")
            st.markdown('<div class="eka-card pos-cart-panel">', unsafe_allow_html=True)
            if cart:
                pos_qty_clamp_notice_key = f"pos_qty_clamp_notice_{company_key}"
                clamp_notice = st.session_state.pop(pos_qty_clamp_notice_key, None)
                if clamp_notice:
                    st.warning(clamp_notice)
                st.markdown("**Line Items**")

                for index, line in enumerate(list(cart)):
                    _recalculate_pos_line(line)
                    identifier = line.get("barcode") or line.get("item_code") or "Manual"
                    item_name = str(line.get("name") or "")
                    unit_price = float(line.get("price") or 0.0)
                    qty_widget_key = f"pos_line_qty_{company_key}_{index}"
                    discount_type_key = f"pos_line_discount_type_{company_key}_{index}"
                    discount_value_key = f"pos_line_discount_value_{company_key}_{index}"
                    line_discount_preview = float(
                        line.get("line_discount_value", line.get("line_discount") or 0.0) or 0.0
                    )
                    discount_expander_key = f"pos_line_discount_expanded_{company_key}_{index}"
                    if line_discount_preview > 0:
                        st.session_state[discount_expander_key] = True
                    discount_expanded = bool(st.session_state.get(discount_expander_key, False))

                    st.markdown('<div class="pos-cart-line">', unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="pos-cart-line-header"><span class="pos-cart-line-name">{item_name}</span></div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="pos-cart-line-meta">{identifier} · {format_currency(unit_price)} each</div>',
                        unsafe_allow_html=True,
                    )
                    _render_pos_cart_warning_badges(line)

                    st.markdown('<div class="pos-cart-line-qty">', unsafe_allow_html=True)
                    qty_row = st.columns([1, 2, 1])
                    dec_clicked = qty_row[0].button(
                        "-",
                        key=f"pos_line_dec_{company_key}_{index}",
                        use_container_width=True,
                    )
                    cart_qty = int(line.get("qty") or 1)
                    qty_sync_key = f"pos_line_qty_sync_{company_key}_{index}"
                    if st.session_state.pop(qty_sync_key, False):
                        st.session_state[qty_widget_key] = cart_qty
                    if qty_widget_key not in st.session_state:
                        st.session_state[qty_widget_key] = cart_qty
                    line_max_qty = _get_pos_line_max_qty(line)
                    number_input_kwargs = {
                        "min_value": 1,
                        "step": 1,
                        "key": qty_widget_key,
                        "label_visibility": "collapsed",
                    }
                    if line_max_qty is not None:
                        number_input_kwargs["max_value"] = line_max_qty
                    updated_qty = qty_row[1].number_input("Qty", **number_input_kwargs)
                    inc_clicked = qty_row[2].button(
                        "+",
                        key=f"pos_line_inc_{company_key}_{index}",
                        use_container_width=True,
                    )
                    st.markdown("</div>", unsafe_allow_html=True)

                    with st.expander("Line discount", expanded=discount_expanded):
                        discount_cols = st.columns([1, 1])
                        updated_discount_type = discount_cols[0].selectbox(
                            "Disc Type",
                            ["Amount", "Percent"],
                            index=0 if str(line.get("line_discount_type") or "amount").lower() == "amount" else 1,
                            key=discount_type_key,
                            label_visibility="visible",
                        )
                        updated_discount = discount_cols[1].number_input(
                            "Discount",
                            min_value=0.0,
                            value=float(line.get("line_discount_value", line.get("line_discount") or 0.0) or 0.0),
                            step=0.01,
                            key=discount_value_key,
                            label_visibility="visible",
                        )

                    applied_qty, qty_clamped, qty_clamp_message = _apply_pos_cart_line_qty_limit(line, updated_qty)
                    line["qty"] = applied_qty
                    if qty_clamped and qty_clamp_message:
                        st.session_state[pos_qty_clamp_notice_key] = qty_clamp_message
                    line["line_discount_type"] = str(updated_discount_type or "Amount").lower()
                    line["line_discount_value"] = float(updated_discount)
                    _recalculate_pos_line(line)

                    line_total = float(line.get("line_total") or 0.0)
                    applied_discount = float(line.get("line_discount") or 0.0)
                    if applied_discount > 0:
                        total_html = (
                            f'<div class="pos-cart-line-total-row">'
                            f'<span class="pos-cart-discount-badge">Disc: {format_currency(applied_discount)}</span>'
                            f'<span class="pos-cart-line-total-value">{format_currency(line_total)}</span>'
                            f'</div>'
                        )
                    else:
                        total_html = (
                            f'<div class="pos-cart-line-total-row">'
                            f'<span class="pos-cart-line-total-label">Line total</span>'
                            f'<span class="pos-cart-line-total-value">{format_currency(line_total)}</span>'
                            f'</div>'
                        )
                    st.markdown(total_html, unsafe_allow_html=True)

                    st.markdown('<div class="pos-cart-line-remove">', unsafe_allow_html=True)
                    remove_clicked = st.button(
                        "Remove",
                        key=f"pos_line_remove_{company_key}_{index}",
                        use_container_width=True,
                    )
                    st.markdown("</div>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                    if inc_clicked:
                        requested_qty = int(line.get("qty") or 1) + 1
                        applied_qty, qty_clamped, qty_clamp_message = _apply_pos_cart_line_qty_limit(line, requested_qty)
                        line["qty"] = applied_qty
                        if qty_clamped and qty_clamp_message:
                            st.session_state[pos_qty_clamp_notice_key] = qty_clamp_message
                        st.session_state[qty_sync_key] = True
                        _recalculate_pos_line(line)
                        st.session_state[cart_key] = cart
                        st.rerun()
                    if dec_clicked:
                        new_qty = max(int(line.get("qty") or 1) - 1, 1)
                        line["qty"] = new_qty
                        st.session_state[qty_sync_key] = True
                        _recalculate_pos_line(line)
                        st.session_state[cart_key] = cart
                        st.rerun()
                    if remove_clicked:
                        cart.pop(index)
                        st.session_state[cart_key] = cart
                        st.rerun()

                st.session_state[cart_key] = cart
                cart_summary = _get_pos_cart_summary(company_key)
            else:
                st.info("Scan a barcode or add an item manually to start the sale.")
            st.markdown("</div>", unsafe_allow_html=True)
            if cart:
                section_header("Live Receipt Preview")
                with card_container():
                    st.markdown(
                        '<p class="pos-receipt-live-label"><strong>SALE PREVIEW</strong> — NOT FINAL RECEIPT</p>',
                        unsafe_allow_html=True,
                    )
                    live_receipt_data = _build_pos_live_receipt_data(company_key, company_label, branch_label, role)
                    _render_pos_receipt_html_panel(
                        _build_receipt_html(live_receipt_data),
                        variant="live",
                        height=440,
                    )
            section_header("Payment & Discounts")
            st.markdown(
                f'<div id="pos-checkout-anchor-{company_key}" style="position:relative;top:-6px;"></div>',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="eka-card pos-checkout-panel">', unsafe_allow_html=True)
            payment_method = "Cash"
            selected_credit_customer_id = None
            selected_credit_customer_label = None
            sale_date = datetime.now().date()
            suspend_note = ""
            if not cart:
                st.markdown("#### Payment")
                payment_method = st.selectbox(
                    "Payment Method",
                    ["Cash", "Mobile Money", "Card", "Bank Transfer", "On Credit"],
                    key=f"pos_payment_method_{company_key}",
                )
                if payment_method == "On Credit":
                    if customers:
                        customer_labels = [
                            f"{row['name']} ({row['customer_id']}) | Balance {format_currency(float(row['balance'] or 0))}"
                            for row in customers
                        ]
                        selected_credit_customer_label = st.selectbox("Credit Customer", customer_labels, key=f"pos_credit_customer_{company_key}")
                        selected_credit_customer_id = int(customers[customer_labels.index(selected_credit_customer_label)]["id"])
                    else:
                        st.warning("Register a customer in Accounts Receivable before using On Credit.")
                sale_date = st.date_input("Transaction Date", value=datetime.now().date(), key=f"pos_sale_date_{company_key}")
            else:
                cart_summary = _get_pos_cart_summary(company_key)
                discount_authority = _get_pos_discount_authority(
                    role,
                    cart_summary["subtotal"],
                    cart_summary["line_discount_total"],
                    cart_summary["cart_discount_total"],
                )
                current_cart_signature = _get_pos_cart_signature(company_key)
                if discount_approval_state.get("approved") and discount_approval_state.get("cart_signature") != current_cart_signature:
                    _clear_pos_discount_approval_state(company_key)
                    discount_approval_state = _get_pos_discount_approval_state(company_key)
                discount_state["threshold_requires_approval"] = bool(discount_authority["requires_approval"])

                st.markdown("#### Sale Totals")
                totals_metric_col1, totals_metric_col2, totals_metric_col3 = st.columns(3)
                totals_metric_col1.metric("Items", cart_summary["item_count"])
                totals_metric_col2.metric("Subtotal", format_currency(cart_summary["subtotal"]))
                totals_metric_col3.metric("Tax / VAT", format_currency(cart_summary["tax_total"]))
                st.markdown(f"### Grand Total: {format_currency(cart_summary['grand_total'])}")
                st.caption(
                    "Line discount: {line_discount} | Cart discount: {cart_discount} | Total discount: {discount_total}".format(
                        line_discount=format_currency(cart_summary["line_discount_total"]),
                        cart_discount=format_currency(cart_summary["cart_discount_total"]),
                        discount_total=format_currency(cart_summary["discount_total"]),
                    )
                )
                if discount_authority["total_discount"] > 0 and not discount_authority["can_apply"]:
                    st.warning("You do not have permission to apply POS discounts.")
                elif (
                    discount_authority["requires_approval"]
                    and not discount_authority["can_approve"]
                    and not (
                        discount_approval_state.get("approved")
                        and discount_approval_state.get("cart_signature") == current_cart_signature
                    )
                ):
                    st.warning("Manager approval required for this discount.")
                elif discount_authority["total_discount"] > 0:
                    st.caption(
                        "Discount applied: {amount} ({percent:.2f}% of subtotal)".format(
                            amount=format_currency(discount_authority["total_discount"]),
                            percent=discount_authority["discount_percent"],
                        )
                    )
                if (
                    discount_approval_state.get("approved")
                    and discount_approval_state.get("cart_signature") == current_cart_signature
                ):
                    st.success(
                        "Manager discount approval recorded: {approver}".format(
                            approver=discount_approval_state.get("approver_name") or discount_approval_state.get("approver_identifier") or "Approved",
                        )
                    )
                    if discount_approval_state.get("reason"):
                        st.caption(f"Approval reason: {discount_approval_state['reason']}")

                st.markdown("#### Payment")
                payment_method = st.selectbox(
                    "Payment Method",
                    ["Cash", "Mobile Money", "Card", "Bank Transfer", "On Credit"],
                    key=f"pos_payment_method_{company_key}",
                )
                if payment_method == "On Credit":
                    if customers:
                        customer_labels = [
                            f"{row['name']} ({row['customer_id']}) | Balance {format_currency(float(row['balance'] or 0))}"
                            for row in customers
                        ]
                        selected_credit_customer_label = st.selectbox("Credit Customer", customer_labels, key=f"pos_credit_customer_{company_key}")
                        selected_credit_customer_id = int(customers[customer_labels.index(selected_credit_customer_label)]["id"])
                    else:
                        st.warning("Register a customer in Accounts Receivable before using On Credit.")
                sale_date = st.date_input("Transaction Date", value=datetime.now().date(), key=f"pos_sale_date_{company_key}")
                if payment_method == "Cash":
                    cash_tendered = st.number_input(
                        f"Amount Tendered ({st.session_state.currency_symbol})",
                        min_value=0.0,
                        value=float(cart_summary["grand_total"] or 0.0),
                        step=0.01,
                        key=f"pos_cash_tendered_{company_key}",
                    )
                    change_due = round(float(cash_tendered or 0.0) - float(cart_summary["grand_total"] or 0.0), 2)
                    st.caption(f"Change Due: {format_currency(change_due if change_due > 0 else 0.0)}")
                elif payment_method in {"Mobile Money", "Card", "Bank Transfer"}:
                    payment_reference = st.text_input(
                        "Transaction / Reference",
                        key=f"pos_payment_reference_{company_key}",
                        placeholder="Optional reference",
                    ).strip()

                with st.expander("Discounts, suspend note & manager approval", expanded=False):
                    discount_cfg_col1, discount_cfg_col2, discount_cfg_col3 = st.columns([1, 1, 2])
                    discount_state["type"] = str(
                        discount_cfg_col1.selectbox(
                            "Cart Discount Type",
                            ["Amount", "Percent"],
                            index=0 if str(discount_state.get("type") or "amount").lower() == "amount" else 1,
                            key=f"pos_cart_discount_type_selector_{company_key}",
                        )
                    ).lower()
                    discount_state["value"] = float(
                        discount_cfg_col2.number_input(
                            "Cart Discount Value",
                            min_value=0.0,
                            value=float(discount_state.get("value") or 0.0),
                            step=0.01,
                            key=f"pos_cart_discount_value_input_{company_key}",
                        )
                    )
                    suspend_note = discount_cfg_col3.text_input(
                        "Suspend Sale Note",
                        key=f"pos_suspend_note_{company_key}",
                        placeholder="Optional note for suspended sale",
                    ).strip()
                    cart_summary = _get_pos_cart_summary(company_key)
                    discount_authority = _get_pos_discount_authority(
                        role,
                        cart_summary["subtotal"],
                        cart_summary["line_discount_total"],
                        cart_summary["cart_discount_total"],
                    )
                    current_cart_signature = _get_pos_cart_signature(company_key)
                    if discount_approval_state.get("approved") and discount_approval_state.get("cart_signature") != current_cart_signature:
                        _clear_pos_discount_approval_state(company_key)
                        discount_approval_state = _get_pos_discount_approval_state(company_key)
                    discount_state["threshold_requires_approval"] = bool(discount_authority["requires_approval"])
                    if discount_authority["requires_approval"] and not discount_authority["can_approve"]:
                        st.markdown("**Manager Approval Required**")
                        approval_col1, approval_col2 = st.columns([1, 2])
                        manager_identifier = approval_col1.text_input(
                            "Manager Username / Code",
                            key=pos_manager_approval_identifier_key,
                            placeholder="Login key, user ID, or full name",
                        ).strip()
                        approval_reason = approval_col2.text_input(
                            "Approval Reason",
                            key=pos_manager_approval_reason_key,
                            placeholder="Reason for high discount approval",
                        ).strip()
                        if st.button("Approve Discount", key=f"pos_discount_approve_btn_{company_key}", use_container_width=True):
                            if not manager_identifier:
                                st.warning("Enter the manager username or code for approval.")
                            elif not approval_reason:
                                st.warning("Enter an approval reason before continuing.")
                            else:
                                approval_conn = None
                                try:
                                    approval_conn = get_connection()
                                    approver_row = approval_conn.execute(
                                        """
                                        SELECT full_name, login_key, user_id, role, status
                                        FROM users
                                        WHERE company_key = ?
                                          AND COALESCE(status, 'Active') = 'Active'
                                          AND (
                                              login_key = ?
                                              OR user_id = ?
                                              OR LOWER(full_name) = LOWER(?)
                                          )
                                        LIMIT 1
                                        """,
                                        (company_key, manager_identifier, manager_identifier, manager_identifier),
                                    ).fetchone()
                                    if not approver_row:
                                        st.warning("Manager approver could not be found.")
                                    elif not user_has_permission(str(approver_row["role"] or ""), "approve_pos_discount"):
                                        st.warning("The selected approver does not have POS discount approval permission.")
                                    else:
                                        approved_at = datetime.now().isoformat()
                                        approval_state = _get_pos_discount_approval_state(company_key)
                                        approval_state.update(
                                            {
                                                "approved": True,
                                                "approver_identifier": str(approver_row["login_key"] or approver_row["user_id"] or manager_identifier),
                                                "approver_name": str(approver_row["full_name"] or approver_row["login_key"] or manager_identifier),
                                                "reason": approval_reason,
                                                "discount_amount": float(discount_authority["total_discount"] or 0.0),
                                                "cart_signature": current_cart_signature,
                                                "approved_at": approved_at,
                                            }
                                        )
                                        cashier_identity = _get_pos_cashier_identity(role)
                                        audit_details = (
                                            "cashier={cashier}; approver={approver}; discount_amount={amount}; reason={reason}; approved_at={approved_at}".format(
                                                cashier=cashier_identity,
                                                approver=approval_state["approver_name"],
                                                amount=format_currency(discount_authority["total_discount"]),
                                                reason=approval_reason,
                                                approved_at=approved_at,
                                            )
                                        )
                                        log_audit_action(
                                            approval_conn,
                                            company_key,
                                            role,
                                            "POS Discount Manager Override",
                                            "POS",
                                            details=audit_details,
                                            branch_id=active_branch_id,
                                            action_type="admin",
                                        )
                                        approval_conn.commit()
                                        log_system_event(
                                            "INFO",
                                            "POS",
                                            "Manager discount override approved for company_key={company_key} cashier={cashier} approver={approver}".format(
                                                company_key=company_key,
                                                cashier=cashier_identity,
                                                approver=approval_state["approver_name"],
                                            ),
                                        )
                                        st.success("Manager discount approval recorded for this sale.")
                                        st.rerun()
                                except Exception as exc:
                                    if approval_conn:
                                        approval_conn.rollback()
                                    st.error(build_user_safe_error(exc, role))
                                finally:
                                    if approval_conn:
                                        approval_conn.close()

                st.markdown('<div class="pos-checkout-actions">', unsafe_allow_html=True)
                st.markdown("#### Checkout Actions")
                checkout_primary_col, clear_action_col, suspend_action_col = st.columns([2, 1, 1])
                if checkout_primary_col.button("Final Checkout", key=f"pos_final_checkout_{company_key}", use_container_width=True, type="primary"):
                    st.session_state[checkout_request_key] = True
                    st.rerun()
                if clear_action_col.button("Clear Cart", key=f"pos_clear_cart_{company_key}", use_container_width=True):
                    _clear_pos_cart_state(company_key)
                    st.session_state[checkout_complete_key] = False
                    st.rerun()
                if suspend_action_col.button("Suspend Sale", key=f"pos_suspend_sale_{company_key}", use_container_width=True):
                    suspend_conn = None
                    try:
                        suspend_conn = get_connection()
                        ensure_pos_sales_schema(suspend_conn)
                        cashier_identity = _get_pos_cashier_identity(role)
                        suspend_reference = _generate_suspended_sale_reference()
                        suspend_payload = _serialize_pos_cart_payload(company_key, cashier_identity, suspend_note)
                        suspend_conn.execute(
                            """
                            INSERT INTO pos_suspended_sales (
                                company_key, branch_id, suspend_reference, cashier, cart_json, note, status, created_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, 'suspended', CURRENT_TIMESTAMP)
                            """,
                            (
                                company_key,
                                str(active_branch_id or ""),
                                suspend_reference,
                                cashier_identity,
                                suspend_payload,
                                suspend_note,
                            ),
                        )
                        log_audit_action(
                            suspend_conn,
                            company_key,
                            role,
                            "POS Sale Suspended",
                            "POS",
                            details=f"suspend_reference={suspend_reference} note={suspend_note or 'none'}",
                            branch_id=active_branch_id,
                            action_type="admin",
                            document_ref=suspend_reference,
                        )
                        suspend_conn.commit()
                        log_system_event("INFO", "POS", f"Suspended sale {suspend_reference} for company_key={company_key} cashier={cashier_identity}")
                        _clear_pos_cart_state(company_key)
                        st.session_state[checkout_complete_key] = False
                        st.success(f"Sale suspended successfully. Reference: {suspend_reference}")
                        st.rerun()
                    except Exception as exc:
                        if suspend_conn:
                            suspend_conn.rollback()
                        st.error(build_user_safe_error(exc, role))
                    finally:
                        if suspend_conn:
                            suspend_conn.close()
                st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            def process_pos_sale(print_receipt=False):
                sale_cart = st.session_state.get(cart_key, [])
                if not sale_cart:
                    st.session_state[checkout_complete_key] = False
                    st.warning("Add at least one item to the cart before processing the sale.")
                    return
                if payment_method == "On Credit" and not selected_credit_customer_id:
                    st.session_state[checkout_complete_key] = False
                    st.warning("Select a customer before processing an on-credit sale.")
                    return
                current_summary = _get_pos_cart_summary(company_key)
                if float(current_summary["grand_total"] or 0.0) <= 0.0:
                    st.session_state[checkout_complete_key] = False
                    st.warning("Total amount must be greater than zero. Reduce discount or remove item.")
                    return
                if payment_method == "Cash" and float(cash_tendered or 0.0) < float(current_summary["grand_total"] or 0.0):
                    st.session_state[checkout_complete_key] = False
                    st.warning("Cash tendered cannot be less than the grand total.")
                    return
                current_cart_signature = _get_pos_cart_signature(company_key)
                approval_state = _get_pos_discount_approval_state(company_key)
                discount_authority = _get_pos_discount_authority(
                    role,
                    current_summary["subtotal"],
                    current_summary["line_discount_total"],
                    current_summary["cart_discount_total"],
                )
                if float(discount_authority["total_discount"] or 0.0) > 0.0 and not discount_authority["can_apply"]:
                    st.session_state[checkout_complete_key] = False
                    st.warning("You do not have permission to apply POS discounts.")
                    return
                if discount_authority["requires_approval"] and not discount_authority["can_approve"]:
                    if not (
                        approval_state.get("approved")
                        and approval_state.get("cart_signature") == current_cart_signature
                    ):
                        st.session_state[checkout_complete_key] = False
                        st.warning("Manager approval required for this discount.")
                        return
                discount_approved_by = None
                discount_approval_reason = None
                if approval_state.get("approved") and approval_state.get("cart_signature") == current_cart_signature:
                    discount_approved_by = approval_state.get("approver_name") or approval_state.get("approver_identifier")
                    discount_approval_reason = approval_state.get("reason")

                try:
                    conn = get_connection()
                    ensure_pos_sales_schema(conn)
                    checkout_inventory_error = _validate_pos_cart_at_checkout(conn, company_key, sale_cart)
                    if checkout_inventory_error:
                        st.session_state[checkout_complete_key] = False
                        st.error(checkout_inventory_error)
                        conn.close()
                        return
                    line_items = []
                    total = round(float(current_summary["grand_total"] or 0.0), 2)
                    pos_tax_total = round(float(current_summary["tax_total"] or 0.0), 2)
                    pos_net_sales = round(total - pos_tax_total, 2)
                    cost_of_goods_sold = 0.0
                    for sale_line in sale_cart:
                        _recalculate_pos_line(sale_line)
                        line_items.append(
                            {
                                "name": sale_line["name"],
                                "qty": sale_line["qty"],
                                "price": sale_line["price"],
                            }
                        )
                        cost_of_goods_sold += float(sale_line["qty"]) * float(sale_line.get("cost_price") or 0.0)
                        if sale_line["inventory_item_id"] is not None:
                            current_item = conn.execute(
                                "SELECT qty FROM inventory WHERE id = ? AND company_key = ?",
                                (int(sale_line["inventory_item_id"]), company_key),
                            ).fetchone()
                            current_qty = float(current_item["qty"] or 0) if current_item else 0.0
                            if float(sale_line["qty"]) > current_qty:
                                st.warning(f"Insufficient stock for {sale_line['name']}.")
                                conn.close()
                                return
                            conn.execute(
                                "UPDATE inventory SET qty = qty - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND company_key = ?",
                                (sale_line["qty"], int(sale_line["inventory_item_id"]), company_key),
                            )
                    payment_account_map = {
                        "Cash": ("Cash", "Asset"),
                        "Mobile Money": ("Mobile Money", "Asset"),
                        "Bank Transfer": ("Bank", "Asset"),
                        "Card": ("Bank", "Asset"),
                        "On Credit": ("Accounts Receivable", "Asset"),
                    }
                    receipt_account, receipt_category = payment_account_map.get(payment_method, ("Cash", "Asset"))
                    narration = ", ".join(f"{item['name']} x{item['qty']}" for item in line_items)
                    branch_id = st.session_state.get("active_branch_id")
                    legacy_sale_id = _create_legacy_voucher_if_enabled(
                        conn,
                        company_key,
                        branch_id,
                        sale_date.isoformat(),
                        "Sales",
                        "Sales Revenue",
                        total,
                        role,
                        narration=f"POS Sale: {narration}",
                        payment_method=payment_method,
                    )
                    sale_reference = f"POS-{legacy_sale_id or datetime.now().strftime('%Y%m%d%H%M%S')}"
                    sale_datetime = f"{sale_date.isoformat()} {datetime.now().strftime('%H:%M:%S')}"
                    receipt_data = {
                        "company_key": company_key,
                        "company_name": company_label,
                        "branch_name": branch_label,
                        "receipt_number": sale_reference,
                        "sale_reference": sale_reference,
                        "sale_date": sale_date.isoformat(),
                        "sale_datetime": sale_datetime,
                        "cashier": role,
                        "payment_method": payment_method,
                        "payment_reference": payment_reference,
                        "subtotal": float(current_summary["subtotal"] or 0.0),
                        "discount_total": float(current_summary["discount_total"] or 0.0),
                        "tax_total": float(current_summary["tax_total"] or 0.0),
                        "grand_total": float(current_summary["grand_total"] or 0.0),
                        "discount_approved_by": discount_approved_by,
                        "amount_tendered": float(cash_tendered or 0.0) if payment_method == "Cash" else None,
                        "change_due": max(float(cash_tendered or 0.0) - float(current_summary["grand_total"] or 0.0), 0.0)
                        if payment_method == "Cash"
                        else 0.0,
                        "items": [
                            {
                                "name": sale_line["name"],
                                "qty": int(sale_line["qty"]),
                                "price": float(sale_line["price"] or 0.0),
                                "line_total": float(sale_line.get("line_total") or 0.0),
                            }
                            for sale_line in sale_cart
                        ],
                    }
                    pos_sale_id = _persist_pos_sale(
                        conn,
                        company_key,
                        branch_id,
                        sale_reference,
                        receipt_data,
                        sale_cart,
                        customer_id=selected_credit_customer_id if payment_method == "On Credit" else None,
                    )
                    journal_lines, _ = build_sales_tax_journal_lines(
                        conn,
                        company_key,
                        receipt_account_name=receipt_account,
                        receipt_account_type=receipt_category,
                        amount=pos_net_sales,
                        output_vat=pos_tax_total,
                    )
                    post_journal_entry(
                        company_key=company_key,
                        date=sale_date,
                        description="POS sale",
                        reference=sale_reference,
                        lines=journal_lines,
                        created_by=role,
                        branch_id=branch_id,
                        customer_id=selected_credit_customer_id if payment_method == "On Credit" else None,
                        source_module="POS",
                        source_table="pos_sales",
                        source_type="POS Sale",
                        source_id=int(pos_sale_id),
                        conn=conn,
                    )
                    if payment_method == "On Credit":
                        ledger_result = _record_customer_ledger_transaction(
                            conn,
                            company_key,
                            selected_credit_customer_id,
                            "Debit",
                            total,
                            f"POS sale on credit: {narration}",
                            role,
                            branch_id=branch_id,
                            reference=sale_reference,
                            transaction_date=sale_date,
                        )
                        _ensure_counterparty(
                            conn,
                            company_key,
                            ledger_result["customer_name"],
                            "Customer",
                            "",
                            sale_date.isoformat(),
                            total,
                        )
                    else:
                        ledger_result = None
                    if cost_of_goods_sold > 0:
                        post_journal_entry(
                            company_key=company_key,
                            date=sale_date,
                            description="Inventory issued to cost of goods sold",
                            reference=f"COGS-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            lines=[
                                {"account_id": get_account_id(conn, "Cost of Goods Sold", "Expense"), "debit": cost_of_goods_sold, "credit": 0},
                                {"account_id": get_account_id(conn, "Inventory", "Asset"), "debit": 0, "credit": cost_of_goods_sold},
                            ],
                            created_by=role,
                            branch_id=branch_id,
                            customer_id=selected_credit_customer_id if payment_method == "On Credit" else None,
                            source_module="POS",
                            source_table="pos_sales",
                            source_type="POS COGS",
                            source_id=int(pos_sale_id),
                            conn=conn,
                        )
                    conn.commit()
                    _invalidate_inventory_search_cache()
                    log_audit_action(
                        conn,
                        company_key,
                        role,
                        "POS Sale",
                        "POS",
                        f"Sold {narration} for GHS{float(total):.2f}" + (
                            f" on credit to {ledger_result['customer_name']}" if ledger_result else ""
                        ),
                        branch_id=branch_id,
                    )
                    if discount_authority["total_discount"] > 0:
                        discount_log_message = (
                            "Applied POS discount of {amount} ({percent:.2f}% of subtotal) on sale {reference}".format(
                                amount=format_currency(discount_authority["total_discount"]),
                                percent=discount_authority["discount_percent"],
                                reference=sale_reference,
                            )
                        )
                        log_system_event("INFO", "POS", f"{discount_log_message} for company_key={company_key}")
                        log_audit_action(
                            conn,
                            company_key,
                            role,
                            "POS Discount Applied",
                            "POS",
                            details=discount_log_message,
                            branch_id=branch_id,
                            action_type="admin",
                            document_ref=sale_reference,
                        )
                        if discount_authority["requires_approval"] and discount_authority["can_approve"]:
                            log_system_event("INFO", "POS", f"Manager-approved POS discount for sale {sale_reference} company_key={company_key}")
                            log_audit_action(
                                conn,
                                company_key,
                                role,
                                "POS Discount Approved",
                                "POS",
                                details=f"Manager-approved discount for sale {sale_reference}",
                                branch_id=branch_id,
                                action_type="admin",
                                document_ref=sale_reference,
                            )
                        elif discount_approved_by:
                            override_details = (
                                "cashier={cashier}; approver={approver}; discount_amount={amount}; reason={reason}".format(
                                    cashier=_get_pos_cashier_identity(role),
                                    approver=discount_approved_by,
                                    amount=format_currency(discount_authority["total_discount"]),
                                    reason=discount_approval_reason or "No reason provided",
                                )
                            )
                            log_system_event("INFO", "POS", f"Manager-approved POS discount completed on sale {sale_reference} company_key={company_key}")
                            log_audit_action(
                                conn,
                                company_key,
                                role,
                                "POS Discount Approved",
                                "POS",
                                details=override_details,
                                branch_id=branch_id,
                                action_type="admin",
                                document_ref=sale_reference,
                            )
                    if print_receipt:
                        conn.commit()
                        st.session_state["last_receipt_data"] = receipt_data
                        st.session_state[last_receipt_data_key] = receipt_data
                        st.session_state[receipt_key] = _build_receipt(receipt_data)
                        st.session_state[receipt_html_key] = _build_receipt_html(receipt_data)
                    conn.close()
                    st.session_state[checkout_complete_key] = True
                    _clear_pos_cart_state(company_key)
                    st.session_state[pos_success_key] = True
                    _clear_streamlit_state(
                        f"pos_item_{company_key}",
                        f"pos_qty_{company_key}",
                        f"manual_pos_item_{company_key}",
                        f"manual_pos_price_{company_key}",
                        f"manual_pos_qty_{company_key}",
                        pos_scan_input_key,
                    )
                    st.rerun()
                except Exception as e:
                    st.error(build_user_safe_error(e, role))

            if st.session_state.pop(checkout_request_key, False):
                st.session_state[checkout_complete_key] = True
                process_pos_sale(print_receipt=True)

            if cart:
                if st.button("Clear Cart", key=f"clear_cart_post_{company_key}", use_container_width=True):
                    _clear_pos_cart_state(company_key)
                    st.session_state[checkout_complete_key] = False
                    st.rerun()

            st.subheader("Recent POS Transactions")
            conn = get_connection()
            ensure_cashier_closings_schema(conn)
            sales_rows = get_recent_accounting_activity(company_key, branch_id=st.session_state.get("active_branch_id"), limit=20, conn=conn)
            conn.close()
            if sales_rows:
                sales_df = pd.DataFrame(
                    [
                        {
                            "Date": row.get("date"),
                            "Narration": row.get("description"),
                            "Amount": row.get("amount", 0.0),
                            "Status": "Posted",
                        }
                        for row in sales_rows
                        if any(token in str(row.get("activity_type") or "").lower() for token in ("sale", "pos"))
                    ]
                )
                st.dataframe(format_currency_dataframe(sales_df), use_container_width=True)
                if role in ("Master Admin", "Bookkeeper", "Branch_Bookkeeper", "Sub-Admin"):
                    st.caption("Legacy voucher-based POS void is disabled while Phase 2 journal posting is the operational source of truth.")

            if user_has_permission(role, "process_pos_return"):
                st.subheader("Returns / Refunds")
                lookup_col1, lookup_col2 = st.columns([3, 1])
                return_lookup_reference = lookup_col1.text_input(
                    "Receipt Number / Sale Reference",
                    key=f"pos_return_lookup_reference_{company_key}",
                    placeholder="Enter receipt number or sale reference",
                ).strip()
                if lookup_col2.button("Lookup Receipt", key=f"pos_return_lookup_btn_{company_key}", use_container_width=True):
                    lookup_conn = None
                    try:
                        lookup_conn = get_connection()
                        ensure_pos_sales_schema(lookup_conn)
                        lookup_result = _lookup_pos_sale_for_return(
                            lookup_conn,
                            company_key,
                            return_lookup_reference,
                            branch_id=active_branch_id,
                        )
                        if not lookup_result:
                            st.session_state.pop(pos_return_lookup_result_key, None)
                            st.warning("Receipt or sale reference was not found.")
                        else:
                            st.session_state[pos_return_lookup_result_key] = lookup_result
                            st.success("Receipt lookup completed.")
                    except Exception as exc:
                        st.error(build_user_safe_error(exc, role))
                    finally:
                        if lookup_conn:
                            lookup_conn.close()

                lookup_result = st.session_state.get(pos_return_lookup_result_key)
                if lookup_result:
                    st.caption(
                        "Sale Date: {date} | Cashier: {cashier} | Payment Method: {payment} | Total: {total}".format(
                            date=lookup_result.get("sale_datetime") or lookup_result.get("sale_date") or "N/A",
                            cashier=lookup_result.get("cashier") or "N/A",
                            payment=lookup_result.get("payment_method") or "N/A",
                            total=format_currency(float(lookup_result.get("grand_total") or 0.0)),
                        )
                    )
                    if lookup_result.get("line_items_available"):
                        st.markdown("**Sold Items**")
                        item_header = st.columns([3, 1, 1, 1, 1, 2])
                        item_header[0].markdown("**Item**")
                        item_header[1].markdown("**Qty Sold**")
                        item_header[2].markdown("**Returned**")
                        item_header[3].markdown("**Refundable**")
                        item_header[4].markdown("**Return Qty**")
                        item_header[5].markdown("**Select**")

                        refund_preview_total = 0.0
                        for item in lookup_result.get("items", []):
                            row_cols = st.columns([3, 1, 1, 1, 1, 2])
                            identifier = item.get("barcode") or item.get("item_code") or "Manual"
                            row_cols[0].write(f"{item['item_name']} ({identifier})")
                            row_cols[1].write(f"{float(item['qty_sold']):,.2f}")
                            row_cols[2].write(f"{float(item['qty_returned']):,.2f}")
                            row_cols[3].write(f"{float(item['refundable_qty']):,.2f}")
                            max_refundable = float(item.get("refundable_qty") or 0.0)
                            qty_key = f"pos_return_qty_{company_key}_{item['pos_sale_line_id']}"
                            select_key = f"pos_return_select_{company_key}_{item['pos_sale_line_id']}"
                            selected_for_return = row_cols[5].checkbox(
                                "Return",
                                key=select_key,
                                value=False,
                                label_visibility="collapsed",
                                disabled=max_refundable <= 0,
                            )
                            requested_qty = row_cols[4].number_input(
                                "Return Qty",
                                min_value=0.0,
                                max_value=max_refundable,
                                value=0.0,
                                step=1.0,
                                key=qty_key,
                                label_visibility="collapsed",
                                disabled=max_refundable <= 0,
                            )
                            if selected_for_return and requested_qty > 0:
                                refund_preview_total += float(requested_qty or 0.0) * float(item.get("unit_price") or 0.0)

                        refund_method = st.selectbox(
                            "Refund Method",
                            ["Cash", "Mobile Money", "Card", "Bank Transfer", "Store Credit"],
                            key=f"pos_refund_method_{company_key}",
                        )
                        return_reason = st.text_area(
                            "Return Reason",
                            key=f"pos_return_reason_{company_key}",
                            placeholder="Reason for the return/refund",
                        ).strip()
                        st.caption(f"Refund Total: {format_currency(refund_preview_total)}")
                        return_confirmed = st.checkbox(
                            "I confirm this return/refund is correct.",
                            key=f"pos_return_confirm_{company_key}",
                        )
                        if st.button("Process Return / Refund", key=f"pos_process_return_{company_key}", use_container_width=True):
                            return_conn = None
                            try:
                                if not require_permission(
                                    role,
                                    "process_pos_return",
                                    action_label="process POS return",
                                    company_key=company_key,
                                    branch_id=active_branch_id,
                                ):
                                    st.stop()
                                if not return_confirmed:
                                    st.warning("Confirm the return/refund before processing it.")
                                    st.stop()
                                selected_returns = []
                                for item in lookup_result.get("items", []):
                                    selected_flag = bool(st.session_state.get(f"pos_return_select_{company_key}_{item['pos_sale_line_id']}", False))
                                    selected_qty = float(st.session_state.get(f"pos_return_qty_{company_key}_{item['pos_sale_line_id']}", 0.0) or 0.0)
                                    if selected_flag and selected_qty > 0:
                                        selected_returns.append(
                                            {
                                                "pos_sale_line_id": item["pos_sale_line_id"],
                                                "qty_returned": selected_qty,
                                            }
                                        )
                                if not selected_returns:
                                    st.warning("Select at least one sale line and return quantity.")
                                    st.stop()
                                if not return_reason:
                                    st.warning("Return reason is required.")
                                    st.stop()
                                return_conn = get_connection()
                                ensure_pos_sales_schema(return_conn)
                                return_result = _process_pos_return(
                                    return_conn,
                                    company_key=company_key,
                                    branch_id=active_branch_id,
                                    role=role,
                                    original_sale=lookup_result,
                                    return_items=selected_returns,
                                    refund_method=refund_method,
                                    reason=return_reason,
                                    return_reference=_generate_pos_return_reference(),
                                )
                                return_conn.commit()
                                _invalidate_inventory_search_cache()
                                st.success(
                                    f"Return processed successfully. Return Reference: {return_result['return_reference']} | Refund Total: {format_currency(return_result['refund_total'])}"
                                )
                                st.session_state.pop(pos_return_lookup_result_key, None)
                                st.rerun()
                            except Exception as exc:
                                if return_conn:
                                    return_conn.rollback()
                                st.error(build_user_safe_error(exc, role))
                            finally:
                                if return_conn:
                                    return_conn.close()
                    else:
                        st.info("Receipt found, but line-item return details are unavailable for this older sale record.")

            st.subheader("Daily Sales Summary")
            cashier_identity = _get_pos_cashier_identity(role)
            can_view_all_closings = user_has_permission(role, "view_cashier_closings") or user_has_permission(role, "manage_cashier_closings")
            can_manage_closings = user_has_permission(role, "manage_cashier_closings")
            summary_conn = None
            try:
                summary_conn = get_connection()
                ensure_cashier_closings_schema(summary_conn)
                summary_date = st.date_input(
                    "Summary Date",
                    value=datetime.now().date(),
                    key=f"pos_summary_date_{company_key}",
                )
                cashier_options = _get_pos_cashier_options(summary_conn, company_key, active_branch_id)
                if cashier_identity and cashier_identity not in cashier_options:
                    cashier_options = [cashier_identity] + cashier_options
                if can_view_all_closings:
                    cashier_filter_options = ["All Cashiers"] + cashier_options
                    selected_cashier = st.selectbox(
                        "Cashier / User",
                        cashier_filter_options,
                        key=f"pos_summary_cashier_{company_key}",
                    )
                    summary_cashier = None if selected_cashier == "All Cashiers" else selected_cashier
                else:
                    summary_cashier = cashier_identity
                    st.caption(f"Cashier / User: {summary_cashier}")

                sales_summary = _get_pos_cashier_summary(
                    summary_conn,
                    company_key,
                    summary_date.isoformat(),
                    cashier=summary_cashier,
                    branch_id=active_branch_id,
                )
                summary_cols = st.columns(4)
                summary_cols[0].metric("Completed Sales", sales_summary["total_completed_sales"])
                summary_cols[1].metric("Total Revenue", format_currency(sales_summary["total_revenue"]))
                summary_cols[2].metric("Cash Sales", format_currency(sales_summary["cash_sales"]))
                summary_cols[3].metric("Receipts", sales_summary["receipt_count"])

                payment_cols = st.columns(4)
                payment_cols[0].caption(f"Mobile Money: {format_currency(sales_summary['mobile_money_sales'])}")
                payment_cols[1].caption(f"Card: {format_currency(sales_summary['card_sales'])}")
                payment_cols[2].caption(f"Bank Transfer: {format_currency(sales_summary['bank_transfer_sales'])}")
                payment_cols[3].caption(f"Credit Sales: {format_currency(sales_summary['credit_sales'])}")

                st.subheader("Cashier Closing")
                if user_has_permission(role, "close_cash_drawer"):
                    default_closing_cashier = summary_cashier or cashier_identity
                    closing_cashier_options = cashier_options or [cashier_identity]
                    if default_closing_cashier and default_closing_cashier not in closing_cashier_options:
                        closing_cashier_options = [default_closing_cashier] + closing_cashier_options
                    with st.form(f"cashier_closing_form_{company_key}"):
                        closing_date = st.date_input(
                            "Closing Date",
                            value=summary_date,
                            key=f"cashier_closing_date_{company_key}",
                        )
                        if can_manage_closings:
                            closing_cashier = st.selectbox(
                                "Cashier to Close",
                                closing_cashier_options,
                                index=max(closing_cashier_options.index(default_closing_cashier), 0) if default_closing_cashier in closing_cashier_options else 0,
                                key=f"cashier_closing_cashier_{company_key}",
                            )
                        else:
                            closing_cashier = default_closing_cashier
                            st.caption(f"Closing Cashier: {closing_cashier}")
                        expected_cash_total = _get_pos_cashier_summary(
                            summary_conn,
                            company_key,
                            closing_date.isoformat(),
                            cashier=closing_cashier,
                            branch_id=active_branch_id,
                        )["cash_sales"]
                        st.caption(f"Expected Cash Total: {format_currency(expected_cash_total)}")
                        counted_cash = st.number_input(
                            "Counted Cash",
                            min_value=0.0,
                            value=float(expected_cash_total or 0.0),
                            step=0.01,
                            key=f"cashier_closing_counted_cash_{company_key}",
                        )
                        closing_difference = round(float(counted_cash or 0.0) - float(expected_cash_total or 0.0), 2)
                        st.caption(f"Shortage / Overage: {format_currency(closing_difference)}")
                        closing_notes = st.text_area(
                            "Notes / Reason",
                            key=f"cashier_closing_notes_{company_key}",
                            placeholder="Optional drawer notes or explanation for shortage/overage",
                        ).strip()
                        closing_submitted = st.form_submit_button("Close Cashier Drawer")
                        if closing_submitted:
                            if not require_permission(
                                role,
                                "close_cash_drawer",
                                action_label="close cashier drawer",
                                company_key=company_key,
                                branch_id=active_branch_id,
                            ):
                                st.stop()
                            duplicate_row = summary_conn.execute(
                                """
                                SELECT id
                                FROM cashier_closings
                                WHERE company_key = ?
                                  AND COALESCE(branch_id, '') = ?
                                  AND cashier = ?
                                  AND closing_date = ?
                                """,
                                (company_key, str(active_branch_id or ""), str(closing_cashier), closing_date.isoformat()),
                            ).fetchone()
                            if duplicate_row:
                                st.warning("This cashier has already been closed for the selected date.")
                            else:
                                summary_conn.execute(
                                    """
                                    INSERT INTO cashier_closings (
                                        company_key, branch_id, cashier, closing_date,
                                        expected_cash, counted_cash, difference, notes,
                                        closed_by, closed_at
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                                    """,
                                    (
                                        company_key,
                                        str(active_branch_id or ""),
                                        str(closing_cashier),
                                        closing_date.isoformat(),
                                        float(expected_cash_total or 0.0),
                                        float(counted_cash or 0.0),
                                        float(closing_difference or 0.0),
                                        closing_notes,
                                        cashier_identity,
                                    ),
                                )
                                log_audit_action(
                                    summary_conn,
                                    company_key,
                                    role,
                                    "Cashier closing recorded",
                                    "POS Closing",
                                    details=(
                                        f"cashier={closing_cashier} date={closing_date.isoformat()} "
                                        f"expected_cash={expected_cash_total:.2f} counted_cash={float(counted_cash or 0.0):.2f} "
                                        f"difference={closing_difference:.2f}"
                                    ),
                                    branch_id=active_branch_id,
                                    action_type="admin",
                                    document_ref=closing_date.isoformat(),
                                )
                                summary_conn.commit()
                                log_system_event(
                                    "INFO",
                                    "POS Closing",
                                    (
                                        f"Cashier closing recorded company_key={company_key} branch_id={active_branch_id or ''} "
                                        f"cashier={closing_cashier} closing_date={closing_date.isoformat()} "
                                        f"expected_cash={expected_cash_total:.2f} counted_cash={float(counted_cash or 0.0):.2f}"
                                    ),
                                )
                                st.success("Cashier closing saved successfully.")
                                st.rerun()

                st.subheader("Recent Cashier Closings")
                closing_query = """
                    SELECT closing_date, cashier, expected_cash, counted_cash, difference, closed_by, notes, closed_at
                    FROM cashier_closings
                    WHERE company_key = ?
                """
                closing_params = [company_key]
                if active_branch_id:
                    closing_query += " AND COALESCE(branch_id, '') = ?"
                    closing_params.append(str(active_branch_id))
                if not can_view_all_closings and not can_manage_closings:
                    closing_query += " AND cashier = ?"
                    closing_params.append(cashier_identity)
                closing_query += " ORDER BY closing_date DESC, closed_at DESC LIMIT 20"
                recent_closings = summary_conn.execute(closing_query, tuple(closing_params)).fetchall()
                if recent_closings:
                    closings_df = pd.DataFrame(
                        [
                            {
                                "Date": row["closing_date"],
                                "Cashier": row["cashier"],
                                "Expected Cash": float(row["expected_cash"] or 0.0),
                                "Counted Cash": float(row["counted_cash"] or 0.0),
                                "Shortage / Overage": float(row["difference"] or 0.0),
                                "Closed By": row["closed_by"],
                                "Notes": row["notes"] or "",
                            }
                            for row in recent_closings
                        ]
                    )
                    st.dataframe(format_currency_dataframe(closings_df), use_container_width=True)
                else:
                    st.info("No cashier closings recorded yet.")
            except Exception as exc:
                st.error(build_user_safe_error(exc, role))
            finally:
                if summary_conn:
                    summary_conn.close()

            section_header("Receipt Actions")
            with card_container():
                _inject_print_styles()

                has_receipt_preview = bool(st.session_state.get(checkout_complete_key) and st.session_state.get(receipt_html_key))
                receipt_data = st.session_state.get(last_receipt_data_key) or st.session_state.get("last_receipt_data") or {}
                receipt_preview_html = str(st.session_state.get(receipt_html_key) or "").strip()

                if has_receipt_preview:
                    st.success("SALE COMPLETED SUCCESSFULLY")
                    summary_col1, summary_col2, summary_col3 = st.columns(3)
                    summary_col1.caption(f"Receipt No: {receipt_data.get('receipt_number') or 'N/A'}")
                    summary_col2.caption(f"Date / Time: {receipt_data.get('sale_datetime') or 'N/A'}")
                    summary_col3.caption(f"Cashier: {receipt_data.get('cashier') or role}")
                    st.caption(
                        "Payment: {payment} | Total: {total}".format(
                            payment=receipt_data.get("payment_method") or "N/A",
                            total=format_currency(float(receipt_data.get("grand_total") or 0.0)),
                        )
                    )
                    if receipt_data.get("payment_method") == "Cash":
                        st.caption(
                            "Amount Tendered: {tendered} | Change Due: {change}".format(
                                tendered=format_currency(float(receipt_data.get("amount_tendered") or 0.0)),
                                change=format_currency(float(receipt_data.get("change_due") or 0.0)),
                            )
                        )
                    if receipt_data.get("discount_approved_by"):
                        st.caption(f"Discount approved by manager: {receipt_data['discount_approved_by']}")
                    st.markdown("**Final Receipt Preview**")
                    st.caption(f"Receipt No: {receipt_data.get('receipt_number') or 'N/A'} — posted sale receipt")
                    _render_pos_receipt_html_panel(receipt_preview_html, variant="final", height=520)

                receipt_action_col1, receipt_action_col2, receipt_action_col3 = st.columns(3)
                if receipt_action_col1.button("Print Receipt", key=f"receipt_print_btn_{company_key}", use_container_width=True):
                    if receipt_preview_html:
                        st.session_state[do_print_key] = True
                    else:
                        st.warning("No receipt is available to print yet.")
                if receipt_action_col2.button("Reprint Last Receipt", key=f"receipt_reprint_btn_{company_key}", use_container_width=True):
                    last_receipt_data = st.session_state.get(last_receipt_data_key) or st.session_state.get("last_receipt_data")
                    if last_receipt_data:
                        st.session_state[receipt_key] = _build_receipt(last_receipt_data)
                        st.session_state[receipt_html_key] = _build_receipt_html(last_receipt_data)
                        st.session_state[checkout_complete_key] = True
                        st.session_state[do_print_key] = True
                        st.rerun()
                    else:
                        fallback_conn = None
                        try:
                            fallback_conn = get_connection()
                            ensure_pos_sales_schema(fallback_conn)
                            recent_cashier = _get_pos_cashier_identity(role)
                            fallback_query = """
                                SELECT id
                                FROM pos_sales
                                WHERE company_key = ?
                            """
                            fallback_params = [company_key]
                            if active_branch_id:
                                fallback_query += " AND COALESCE(branch_id, '') = ?"
                                fallback_params.append(str(active_branch_id))
                            fallback_query += " AND COALESCE(cashier, '') = ?"
                            fallback_params.append(str(recent_cashier))
                            fallback_query += " ORDER BY created_at DESC, id DESC LIMIT 1"
                            fallback_row = fallback_conn.execute(fallback_query, tuple(fallback_params)).fetchone()
                            if not fallback_row:
                                st.warning("No previous receipt is available for reprint.")
                            else:
                                db_receipt_data = _fetch_pos_receipt_data(
                                    fallback_conn,
                                    company_key=company_key,
                                    sale_id=int(fallback_row["id"]),
                                    branch_id=str(active_branch_id) if active_branch_id else None,
                                    cashier=_get_pos_cashier_identity(role),
                                )
                                if not db_receipt_data:
                                    st.warning("No previous receipt is available for reprint.")
                                else:
                                    st.session_state[receipt_key] = _build_receipt(db_receipt_data)
                                    st.session_state[receipt_html_key] = _build_receipt_html(db_receipt_data)
                                    st.session_state[checkout_complete_key] = True
                                    st.session_state[do_print_key] = True
                                    st.rerun()
                        except Exception as exc:
                            st.error(build_user_safe_error(exc, role))
                        finally:
                            if fallback_conn:
                                fallback_conn.close()
                if receipt_action_col3.button("New Sale", key=f"receipt_new_sale_btn_{company_key}", use_container_width=True):
                    _clear_pos_cart_state(company_key)
                    st.session_state[checkout_complete_key] = False
                    st.session_state.pop(receipt_key, None)
                    st.session_state.pop(receipt_html_key, None)
                    _clear_streamlit_state(
                        f"pos_item_{company_key}",
                        f"pos_qty_{company_key}",
                        f"manual_pos_item_{company_key}",
                        f"manual_pos_price_{company_key}",
                        f"manual_pos_qty_{company_key}",
                        pos_scan_input_key,
                    )
                    st.rerun()

                refresh_col, _ = st.columns([1, 3])
                refresh_col.button(
                    "Refresh Recent Receipts",
                    key=f"pos_recent_receipts_refresh_{company_key}",
                    use_container_width=True,
                )

                st.markdown("**Recent Receipts**")
                recent_conn = None
                recent_receipts = []
                try:
                    recent_conn = get_connection()
                    ensure_pos_sales_schema(recent_conn)
                    recent_cashier = _get_pos_cashier_identity(role)
                    recent_query = """
                        SELECT id, receipt_number, sale_datetime, grand_total, payment_method
                        FROM pos_sales
                        WHERE company_key = ?
                    """
                    recent_params = [company_key]
                    if active_branch_id:
                        recent_query += " AND COALESCE(branch_id, '') = ?"
                        recent_params.append(str(active_branch_id))
                    recent_query += " AND COALESCE(cashier, '') = ?"
                    recent_params.append(str(recent_cashier))
                    recent_query += " ORDER BY created_at DESC, id DESC LIMIT 10"
                    recent_receipts = recent_conn.execute(recent_query, tuple(recent_params)).fetchall()
                except Exception as exc:
                    st.warning(build_user_safe_error(exc, role))
                finally:
                    if recent_conn:
                        recent_conn.close()

                if recent_receipts:
                    for row in recent_receipts:
                        row_cols = st.columns([2, 2, 1, 1])
                        row_cols[0].caption(str(row["receipt_number"] or "N/A"))
                        row_cols[1].caption(str(row["sale_datetime"] or ""))
                        row_cols[2].caption(format_currency(float(row["grand_total"] or 0.0)))
                        if row_cols[3].button(
                            "Reprint",
                            key=f"pos_recent_receipt_reprint_{company_key}_{int(row['id'])}",
                            use_container_width=True,
                        ):
                            fetch_conn = None
                            try:
                                fetch_conn = get_connection()
                                db_receipt_data = _fetch_pos_receipt_data(
                                    fetch_conn,
                                    company_key=company_key,
                                    sale_id=int(row["id"]),
                                    branch_id=str(active_branch_id) if active_branch_id else None,
                                    cashier=_get_pos_cashier_identity(role),
                                )
                                if not db_receipt_data:
                                    st.warning("That receipt could not be found for reprint.")
                                else:
                                    st.session_state[receipt_key] = _build_receipt(db_receipt_data)
                                    st.session_state[receipt_html_key] = _build_receipt_html(db_receipt_data)
                                    st.session_state[checkout_complete_key] = True
                                    st.session_state[do_print_key] = True
                                    st.rerun()
                            except Exception as exc:
                                st.error(build_user_safe_error(exc, role))
                            finally:
                                if fetch_conn:
                                    fetch_conn.close()
                else:
                    st.caption("No recent receipts found for this cashier.")

                st.download_button(
                    "Download Receipt",
                    data=st.session_state.get(receipt_key, ""),
                    file_name=f"receipt_{company_key}.txt",
                    mime="text/plain",
                    key=f"receipt_download_{company_key}",
                    use_container_width=True,
                )
            if st.session_state.get(do_print_key):
                print_receipt_html = str(st.session_state.get(receipt_html_key) or "").strip()
                if print_receipt_html:
                    components.html(_build_pos_receipt_print_document(print_receipt_html), height=0)
                st.session_state[do_print_key] = False

        pos_suspended_col, pos_workflow_col = st.columns([1, 2])
        with pos_suspended_col:
            _render_pos_suspended_sales_side_panel(company_key, role, active_branch_id, checkout_complete_key)
        with pos_workflow_col:
            _render_pos_workflow_column(barcode_input_source)
    except Exception as e:
        st.error(build_user_safe_error(e, role))
# ==========================================
# SALES & PURCHASE
# ==========================================
def show_sales_purchase(company_key, role, doc_type="Sales"):
    st.header(f"{'🧾 Sales Invoicing' if doc_type == 'Sales' else '📦 Purchase Invoicing'}")
    branch_id = st.session_state.get("active_branch_id")
    if role == "Demo":
        _demo_notice()
        demo_data = pd.DataFrame({
            "Customer/Supplier": ["Demo Client Ltd", "Demo Supplier Co."],
            "Amount (GHS)": [5000.0, 2000.0],
            "Status": ["Paid", "Pending"],
            "Date": [datetime.now().date().isoformat()] * 2,
        })
        st.dataframe(format_currency_dataframe(demo_data), use_container_width=True)
        return

    invoice_editor_conn = None
    invoice_items = []
    invoice_items_total = 0.0
    purchase_render_conn = None
    purchase_expense_account_options = ["General Expenses"]
    if doc_type != "Sales":
        purchase_render_conn = get_connection()
        try:
            purchase_expense_account_options = get_purchase_expense_account_options(company_key, conn=purchase_render_conn)
        finally:
            if purchase_render_conn:
                purchase_render_conn.close()
    with st.form(f"{doc_type.lower()}_form"):
        col1, col2 = st.columns(2)
        with col1:
            party_name = st.text_input("Customer Name" if doc_type == "Sales" else "Supplier Name")
            amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01)
        with col2:
            status = st.selectbox("Status", ["Paid", "Pending", "Draft"] if doc_type == "Sales" else ["Received", "Pending", "Cancelled"])
            posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=3)
            doc_date = st.date_input("Date", datetime.now().date())
        city_region = st.text_input("City / Region")
        narration = st.text_input("Description / Reference")
        if doc_type == "Sales":
            output_vat_rate = st.number_input("Output VAT Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0)
            output_nhil_rate = st.number_input("Output NHIL Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0)
            output_getfund_rate = st.number_input("Output GETFund Levy Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0)
            st.markdown("Optional Invoice Items")
            invoice_editor_conn = get_connection()
            try:
                invoice_items, invoice_items_total = render_invoice_line_editor(
                    company_key,
                    f"sales_purchase_invoice_lines_{company_key}",
                    invoice_editor_conn,
                )
            finally:
                if invoice_editor_conn:
                    invoice_editor_conn.close()
        else:
            purchase_classification = st.selectbox("Purchase Classification", PURCHASE_CLASSIFICATION_OPTIONS)
            input_vat_rate = st.number_input("Input VAT Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0)
            payment_method = st.selectbox("Payment Method", ["Cash", "Bank", "Mobile Money"], disabled=status != "Received")
            expense_account_name = None
            asset_name = ""
            asset_category = ""
            if purchase_classification == "Expense Purchase":
                expense_account_name = st.selectbox("Expense Account", purchase_expense_account_options)
            elif purchase_classification == "Fixed Asset Purchase":
                asset_name = st.text_input("Asset Name")
                asset_category = st.selectbox("Asset Category", FIXED_ASSET_PURCHASE_CATEGORIES)
        submitted = st.form_submit_button(f"Save {doc_type}")

        if submitted and party_name and amount > 0:
            try:
                conn = get_connection()
                tx_reference = f"{doc_type[:3].upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                if doc_type == "Sales":
                    if invoice_items and abs(invoice_items_total - float(amount or 0.0)) >= 0.01:
                        conn.close()
                        st.warning("Invoice amount must match the total of the invoice items before posting.")
                        return
                    customer_id = _register_customer(conn, company_key, party_name)
                    output_vat = _tax_amount(amount, output_vat_rate)
                    output_nhil = _tax_amount(amount, output_nhil_rate)
                    output_getfund = _tax_amount(amount, output_getfund_rate)
                    invoice_cursor = conn.execute(
                        ensure_insert_sql_returning(
                            """
                            INSERT INTO invoices (company_key, customer_id, invoice_number, invoice_date, due_date, status, approval_status, amount, output_vat, currency, description, created_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                            """
                        ),
                        (company_key, customer_id, tx_reference, doc_date.isoformat(), doc_date.isoformat(), status, posting_state, amount, output_vat, narration, role),
                    )
                    invoice_id = get_inserted_id(invoice_cursor)
                    if invoice_items:
                        save_invoice_lines(conn, invoice_id, invoice_items)
                    debit_account = "Cash" if status == "Paid" else "Accounts Receivable"
                    if posting_state == "Posted":
                        stock_effects = apply_invoice_stock_effects(
                            conn,
                            company_key=company_key,
                            invoice_reference=tx_reference,
                            invoice_items=invoice_items,
                            role=role,
                            branch_id=branch_id,
                        )
                        cogs_total = round(float(stock_effects.get("cogs_total") or 0.0), 2)
                        journal_lines, _ = build_sales_tax_journal_lines(
                            conn,
                            company_key,
                            receipt_account_name=debit_account,
                            receipt_account_type="Asset",
                            amount=amount,
                            output_vat=output_vat,
                            nhil=output_nhil,
                            getfund=output_getfund,
                        )
                        if cogs_total > 0:
                            journal_lines.extend(
                                [
                                    {"account_id": get_account_id(conn, "Cost of Goods Sold", "Expense"), "debit": cogs_total, "credit": 0},
                                    {"account_id": get_account_id(conn, "Inventory", "Asset"), "debit": 0, "credit": cogs_total},
                                ]
                            )
                        post_journal_entry(
                            company_key=company_key,
                            date=doc_date,
                            description="Sales transaction",
                            reference=tx_reference,
                            lines=journal_lines,
                            created_by=role,
                            branch_id=branch_id,
                            customer_id=customer_id,
                            source_module="Sales Invoicing",
                            source_table="invoices",
                            source_type="Invoice",
                            source_id=invoice_id,
                            approval_status="Posted",
                            conn=conn,
                        )
                else:
                    supplier_id = _get_or_create_party(conn, "suppliers", company_key, party_name)
                    input_vat = round(float(amount or 0.0) * float(input_vat_rate or 0.0) / 100.0, 2)
                    bill_cursor = conn.execute(
                        ensure_insert_sql_returning(
                            """
                            INSERT INTO bills (
                                company_key, supplier_id, bill_number, bill_date, due_date, status, approval_status,
                                amount, input_vat, purchase_classification, payment_method, expense_account_name, asset_name,
                                asset_category, currency, description, created_by
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                            """
                        ),
                        (
                            company_key,
                            supplier_id,
                            tx_reference,
                            doc_date.isoformat(),
                            doc_date.isoformat(),
                            status,
                            posting_state,
                            amount,
                            input_vat,
                            _normalize_purchase_classification(purchase_classification),
                            payment_method if status == "Received" else None,
                            expense_account_name if purchase_classification == "Expense Purchase" else None,
                            asset_name.strip() or None,
                            asset_category or None,
                            narration,
                            role,
                        ),
                    )
                    bill_id = get_inserted_id(bill_cursor)
                    if posting_state == "Posted":
                        journal_lines, _ = build_purchase_journal_lines(
                            conn,
                            company_key,
                            classification=purchase_classification,
                            amount=amount,
                            input_vat=input_vat,
                            status=status,
                            payment_method=payment_method,
                            expense_account_name=expense_account_name,
                        )
                        post_journal_entry(
                            company_key=company_key,
                            date=doc_date,
                            description="Purchase transaction",
                            reference=tx_reference,
                            lines=journal_lines,
                            created_by=role,
                            branch_id=branch_id,
                            supplier_id=supplier_id,
                            source_module="Purchase Invoicing",
                            source_table="bills",
                            source_type="Bill",
                            source_id=bill_id,
                            approval_status="Posted",
                            user_role=role,
                            conn=conn,
                        )
                balance_delta = amount if status == "Pending" else 0.0
                _ensure_counterparty(
                    conn,
                    company_key,
                    party_name,
                    "Customer" if doc_type == "Sales" else "Vendor",
                    city_region,
                    doc_date.isoformat(),
                    balance_delta,
                )
                conn.commit()
                log_audit_action(conn, company_key, role, f"{doc_type} Recorded", doc_type, f"{party_name} - GHS{amount:.2f}", branch_id=branch_id)
                conn.close()
                if posting_state == "Posted":
                    st.success(f"{doc_type} saved and posted successfully!")
                else:
                    st.success(f"{doc_type} saved without ledger impact. Move Posting State to Posted when it is approved.")
                st.rerun()
            except Exception as e:
                st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))

    try:
        conn = get_connection()
        if doc_type == "Sales":
            data = conn.execute(
                "SELECT invoice_date AS date, description AS narration, amount AS credit FROM invoices WHERE company_key = ? ORDER BY invoice_date DESC, id DESC LIMIT 50",
                (company_key,),
            ).fetchall()
        else:
            data = conn.execute(
                "SELECT bill_date AS date, description AS narration, amount AS credit FROM bills WHERE company_key = ? ORDER BY bill_date DESC, id DESC LIMIT 50",
                (company_key,),
            ).fetchall()
        conn.close()
        if data:
            df = pd.DataFrame(data, columns=["Date", "Description", "Amount (GHS)"])
            st.dataframe(format_currency_dataframe(df), use_container_width=True)
            excel_bin = get_excel_bin(df)
            if excel_bin:
                st.download_button(
                    "📥 Export to Excel",
                    data=excel_bin,
                    file_name=f"{doc_type.lower()}_{company_key}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"{doc_type.lower()}_export_{company_key}",
                )
        else:
            st.info(f"No {doc_type} records found.")
    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))

    import_file = st.file_uploader(
        f"Import {doc_type} from Excel",
        type=["xlsx"],
        key=f"{doc_type.lower()}_import_{company_key}",
    )
    if import_file and st.button(f"Import {doc_type} File", key=f"{doc_type.lower()}_import_btn_{company_key}"):
        try:
            conn = get_connection()
            added_rows = _import_sales_from_excel(conn, company_key, doc_type, import_file, role)
            conn.commit()
            conn.close()
            st.success(f"Imported {added_rows} new {doc_type.lower()} row(s).")
            st.rerun()
        except Exception as exc:
            st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))


# ==========================================
# BANKING & CASH
# ==========================================
def show_banking(company_key, role):
    render_ui_standard_styles()
    page_header("🏦 Banking & Cash", "Manage cash and bank account transactions")
    if not require_permission(
        role,
        "view_banking",
        action_label="view banking",
        company_key=company_key,
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return
    if role == "Demo":
        _demo_notice()
        st.metric(f"Cash Balance ({get_currency_symbol()})", format_currency(8300.0))
        st.metric(f"Bank Balance ({get_currency_symbol()})", format_currency(15000.0))
        return

    try:
        conn = get_connection()
        feedback_key = f"banking_post_feedback_{company_key}"
        accounts_ready_key = f"banking_core_accounts_ready_{company_key}"
        branch_id = st.session_state.get("active_branch_id")
        pending_feedback = st.session_state.pop(feedback_key, None)
        trial_balance = engine_get_trial_balance(company_key, branch_id=branch_id)
        cash_total = sum(row["balance"] for row in trial_balance if row["account_name"] == "Cash")
        bank_total = sum(row["balance"] for row in trial_balance if row["account_name"] in ("Bank", "Mobile Money"))
        customers = get_customer_balances(company_key, conn=conn)
        suppliers = conn.execute("SELECT id, name FROM suppliers WHERE company_key = ? ORDER BY name", (company_key,)).fetchall()

        def _journal_method_balance(method_name):
            normalized_method = str(method_name or "").strip()
            if not normalized_method:
                return 0.0
            fresh_trial_balance = engine_get_trial_balance(company_key, branch_id=branch_id)
            for row in fresh_trial_balance:
                if str(row.get("account_name") or "").strip() == normalized_method:
                    return round(float(row.get("balance") or 0.0), 2)
            return 0.0

        col1, col2 = st.columns(2)
        col1.metric(f"Cash Balance ({get_currency_symbol()})", format_currency(cash_total))
        col2.metric(f"Bank Balance ({get_currency_symbol()})", format_currency(bank_total))
        if pending_feedback:
            if pending_feedback.get("status") == "success":
                st.success(str(pending_feedback.get("message") or "Transaction posted successfully."))
            elif pending_feedback.get("status") == "error":
                st.error(str(pending_feedback.get("message") or "Banking transaction failed."))

        with st.expander("Record Payment", expanded=True):
            enhanced_term_labels = {
                "Owner Capital": "Owner Capital (Equity Contribution)",
                "Owner Drawings": "Owner Drawings (Owner Withdrawals)",
                "Loan Payable": "Loan Payable (Outstanding Loans)",
                "Accounts Receivable": "Accounts Receivable (Customer Balances)",
                "Accounts Payable": "Accounts Payable (Supplier Balances)",
            }
            owner_payment_types = {
                "Owner Capital / Owner Investment",
                "Owner Drawings / Owner Withdrawal",
            }
            loan_payment_types = {
                "Loan Received",
                "Loan Repayment",
            }
            transfer_payment_types = {
                "Transfer Between Cash/Bank/Mobile Money",
            }
            sensitive_permission_map = {
                "Owner Capital / Owner Investment": "manage_owner_equity_transactions",
                "Owner Drawings / Owner Withdrawal": "manage_owner_equity_transactions",
                "Loan Received": "manage_loan_transactions",
                "Loan Repayment": "manage_loan_transactions",
                "Transfer Between Cash/Bank/Mobile Money": "manage_cash_bank_transfers",
            }
            payment_type_descriptions = {
                "Customer Receipt": "Record payments received from customers",
                "Supplier Payment": "Record payments made to suppliers",
                "Owner Capital / Owner Investment": "Record funds introduced by the owner into the business",
                "Owner Drawings / Owner Withdrawal": "Record funds withdrawn by the owner for personal use",
                "Loan Received": "Record borrowed funds received by the business",
                "Loan Repayment": "Record repayment of borrowed funds",
                "Transfer Between Cash/Bank/Mobile Money": "Move funds between Cash, Bank, or Mobile Money accounts",
            }
            payment_type_labels = {
                "Customer Receipt": "Customer Receipt",
                "Supplier Payment": "Supplier Payment",
                "Owner Capital / Owner Investment": "Owner Capital (Equity Contribution)",
                "Owner Drawings / Owner Withdrawal": "Owner Drawings (Owner Withdrawals)",
                "Loan Received": "Loan Received",
                "Loan Repayment": "Loan Repayment",
                "Transfer Between Cash/Bank/Mobile Money": "Transfer Between Cash/Bank/Mobile Money",
            }
            payment_type_key = f"banking_payment_type_{company_key}"
            customer_widget_key = f"banking_customer_{company_key}"
            supplier_widget_key = f"banking_supplier_{company_key}"
            owner_name_widget_key = f"banking_owner_name_{company_key}"
            owner_description_widget_key = f"banking_owner_description_{company_key}"
            lender_name_widget_key = f"banking_lender_name_{company_key}"
            transfer_from_widget_key = f"banking_transfer_from_{company_key}"
            transfer_to_widget_key = f"banking_transfer_to_{company_key}"
            payment_type = st.selectbox(
                "Payment Type",
                [
                    "Customer Receipt",
                    "Supplier Payment",
                    "Owner Capital / Owner Investment",
                    "Owner Drawings / Owner Withdrawal",
                    "Loan Received",
                    "Loan Repayment",
                    "Transfer Between Cash/Bank/Mobile Money",
                ],
                format_func=lambda value: payment_type_labels.get(value, value),
                key=payment_type_key,
            )
            st.caption(payment_type_descriptions.get(payment_type, ""))
            if payment_type != "Customer Receipt":
                st.session_state.pop(customer_widget_key, None)
            if payment_type != "Supplier Payment":
                st.session_state.pop(supplier_widget_key, None)
            if payment_type not in owner_payment_types:
                st.session_state.pop(owner_name_widget_key, None)
                st.session_state.pop(owner_description_widget_key, None)
            if payment_type not in loan_payment_types:
                st.session_state.pop(lender_name_widget_key, None)
            if payment_type not in transfer_payment_types:
                st.session_state.pop(transfer_from_widget_key, None)
                st.session_state.pop(transfer_to_widget_key, None)
            with st.form(f"banking_payment_form_{company_key}", clear_on_submit=False):
                money_methods = ["Cash", "Bank", "Mobile Money"]
                payment_method = None
                transfer_from_account = ""
                transfer_to_account = ""
                if payment_type in transfer_payment_types:
                    transfer_from_account = st.selectbox("From Account", money_methods, key=transfer_from_widget_key)
                    st.caption("Select the source account to reduce.")
                    transfer_to_account = st.selectbox("To Account", money_methods, key=transfer_to_widget_key)
                    st.caption("Select the destination account to increase.")
                elif payment_type == "Loan Received":
                    payment_method = st.selectbox("Destination Method", money_methods)
                    st.caption("Choose where the borrowed funds will be received.")
                elif payment_type == "Loan Repayment":
                    payment_method = st.selectbox("Source Method", money_methods)
                    st.caption("Choose which account will be used to repay the loan.")
                else:
                    payment_method = st.selectbox("Method", money_methods)
                    st.caption("Choose the cash-equivalent account affected by this transaction.")
                amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01)
                st.caption("Enter the transaction amount to be posted.")
                payment_date = st.date_input("Payment Date", value=datetime.now().date(), key=f"banking_payment_date_{company_key}")
                st.caption("This date determines the accounting period for the journal entry.")
                reference = st.text_input("Reference")
                st.caption("Optional external reference such as cheque number, transfer ID, or memo.")
                description = ""
                owner_name = ""
                lender_name = ""
                selected_party = None
                if payment_type == "Customer Receipt":
                    customer_labels = [f"{row['name']} ({row['customer_id']})" for row in customers]
                    selected_party = st.selectbox(
                        "Customer",
                        customer_labels if customer_labels else [""],
                        key=customer_widget_key,
                    )
                    st.caption(f"This posts against {enhanced_term_labels['Accounts Receivable']}.")
                elif payment_type == "Supplier Payment":
                    supplier_labels = [f"{row['name']}" for row in suppliers]
                    selected_party = st.selectbox(
                        "Supplier",
                        supplier_labels if supplier_labels else [""],
                        key=supplier_widget_key,
                    )
                    st.caption(f"This posts against {enhanced_term_labels['Accounts Payable']}.")
                elif payment_type in loan_payment_types:
                    lender_name = st.text_input("Lender Name (Optional)", key=lender_name_widget_key)
                    st.caption(f"Outstanding balances are tracked in {enhanced_term_labels['Loan Payable']}.")
                    description = st.text_area("Description")
                    st.caption("Add a short note for the borrowing or repayment purpose.")
                else:
                    description = st.text_area("Description", key=owner_description_widget_key)
                    st.caption("Add a short note describing the transaction.")
                    if payment_type in owner_payment_types:
                        owner_name = st.text_input("Owner Name (Optional)", key=owner_name_widget_key)
                        if payment_type == "Owner Capital / Owner Investment":
                            st.caption(f"This posts to {enhanced_term_labels['Owner Capital']}.")
                        else:
                            st.caption(f"This posts to {enhanced_term_labels['Owner Drawings']}.")
                submitted = st.form_submit_button("Post Transaction")

            if submitted:
                if amount <= 0:
                    st.warning("Enter an amount greater than zero.")
                elif payment_type in transfer_payment_types and not transfer_from_account:
                    st.warning("Select a source account before posting the transfer.")
                elif payment_type in transfer_payment_types and not transfer_to_account:
                    st.warning("Select a destination account before posting the transfer.")
                elif payment_type in transfer_payment_types and transfer_from_account == transfer_to_account:
                    st.warning("Transfer source and destination accounts must be different.")
                elif payment_type not in transfer_payment_types and not payment_method:
                    st.warning("Select a payment method before posting.")
                elif not payment_date:
                    st.warning("Select a payment date before posting.")
                elif payment_type == "Customer Receipt" and not customers:
                    st.warning("Create a customer before posting a receipt.")
                elif payment_type == "Customer Receipt" and not str(selected_party or "").strip():
                    st.warning("Select a customer before posting a receipt.")
                elif payment_type == "Supplier Payment" and not suppliers:
                    st.warning("Create a supplier before posting a supplier payment.")
                elif payment_type == "Supplier Payment" and not str(selected_party or "").strip():
                    st.warning("Select a supplier before posting a supplier payment.")
                else:
                    customer_labels = [f"{row['name']} ({row['customer_id']})" for row in customers]
                    supplier_labels = [f"{row['name']}" for row in suppliers]
                    if not require_permission(
                        role,
                        "post_accounting_document",
                        action_label="post banking transactions",
                        company_key=company_key,
                        conn=conn,
                        branch_id=branch_id,
                    ):
                        conn.close()
                        return
                    normalized_reference = str(reference or "").strip()
                    normalized_description = str(description or "").strip()
                    normalized_owner_name = str(owner_name or "").strip()
                    normalized_lender_name = str(lender_name or "").strip()
                    sensitive_permission = sensitive_permission_map.get(payment_type)
                    if sensitive_permission and not require_permission(
                        role,
                        sensitive_permission,
                        action_label=f"post {payment_type.lower()} transactions",
                        company_key=company_key,
                        conn=conn,
                        branch_id=branch_id,
                    ):
                        conn.close()
                        return
                    source_method = transfer_from_account if payment_type in transfer_payment_types else payment_method
                    destination_method = transfer_to_account if payment_type in transfer_payment_types else payment_method
                    cash_account = (
                        "Cash" if payment_method == "Cash"
                        else ("Bank" if payment_method == "Bank" else "Mobile Money")
                    ) if payment_method else ""
                    if payment_type in (owner_payment_types | loan_payment_types | transfer_payment_types) and not st.session_state.get(accounts_ready_key):
                        # Reuse the canonical account helpers to avoid duplicate equity or cash/bank accounts.
                        ensure_core_financial_accounts(company_key, conn=conn)
                        st.session_state[accounts_ready_key] = True
                    source_methods_requiring_balance = {
                        "Supplier Payment",
                        "Owner Drawings / Owner Withdrawal",
                        "Loan Repayment",
                        "Transfer Between Cash/Bank/Mobile Money",
                    }
                    if payment_type in source_methods_requiring_balance:
                        available_balance = _journal_method_balance(source_method)
                        if float(amount or 0.0) > float(available_balance or 0.0):
                            st.warning("Insufficient Cash/Bank/Mobile Money balance for this transaction.")
                            conn.rollback()
                            return
                    payment_cursor = conn.execute(
                        ensure_insert_sql_returning(
                            """
                            INSERT INTO payments (company_key, payment_date, payment_type, customer_id, supplier_id, amount, currency, method, reference, status, approval_status, created_by)
                            VALUES (?, ?, ?, ?, ?, ?, 'GHS', ?, ?, 'Posted', 'Posted', ?)
                            """
                        ),
                        (
                            company_key,
                            payment_date.isoformat(),
                            payment_type,
                            int(customers[[f"{row['name']} ({row['customer_id']})" for row in customers].index(selected_party)]["id"]) if payment_type == "Customer Receipt" else None,
                            int(suppliers[supplier_labels.index(selected_party)]["id"]) if payment_type == "Supplier Payment" else None,
                            amount,
                            f"{transfer_from_account} -> {transfer_to_account}" if payment_type in transfer_payment_types else payment_method,
                            normalized_reference,
                            role,
                        ),
                    )
                    payment_id = get_inserted_id(payment_cursor)
                    document_reference = normalized_reference or f"BANK-{payment_id}"
                    audit_transaction_type = payment_type
                    audit_owner_name = normalized_owner_name
                    audit_description = normalized_description
                    audit_lender_name = normalized_lender_name
                    audit_source_method = source_method or "N/A"
                    audit_destination_method = destination_method or "N/A"
                    posted_entry_id = None
                    try:
                        if payment_type == "Customer Receipt":
                            selected_customer = customers[[f"{row['name']} ({row['customer_id']})" for row in customers].index(selected_party)]
                            lines = [
                                {"account_id": get_account_id(conn, cash_account, "Asset"), "debit": amount, "credit": 0},
                                {"account_id": get_account_id(conn, "Accounts Receivable", "Asset"), "debit": 0, "credit": amount},
                            ]
                            posted_entry_id = post_journal_entry(
                                company_key=company_key,
                                date=payment_date,
                                description=f"Customer receipt - {selected_customer['name']}",
                                reference=document_reference,
                                lines=lines,
                                created_by=role,
                                branch_id=branch_id,
                                customer_id=int(selected_customer["id"]),
                                payment_id=payment_id,
                                source_module="Banking",
                                source_table="payments",
                                source_type=payment_type,
                                source_id=payment_id,
                                user_role=role,
                                conn=conn,
                            )
                        elif payment_type == "Supplier Payment":
                            selected_supplier = suppliers[supplier_labels.index(selected_party)]
                            lines = [
                                {"account_id": get_account_id(conn, "Accounts Payable", "Liability"), "debit": amount, "credit": 0},
                                {"account_id": get_account_id(conn, cash_account, "Asset"), "debit": 0, "credit": amount},
                            ]
                            posted_entry_id = post_journal_entry(
                                company_key=company_key,
                                date=payment_date,
                                description=f"Supplier payment - {selected_supplier['name']}",
                                reference=document_reference,
                                lines=lines,
                                created_by=role,
                                branch_id=branch_id,
                                supplier_id=int(selected_supplier["id"]),
                                payment_id=payment_id,
                                source_module="Banking",
                                source_table="payments",
                                source_type=payment_type,
                                source_id=payment_id,
                                user_role=role,
                                conn=conn,
                            )
                        elif payment_type == "Loan Received":
                            audit_transaction_type = "Loan Received"
                            destination_account_id = get_or_create_account(company_key, destination_method, "Asset", conn=conn)
                            loan_payable_account_id = get_or_create_account(company_key, "Loan Payable", "Liability", conn=conn)
                            lines = [
                                {"account_id": destination_account_id, "debit": amount, "credit": 0},
                                {"account_id": loan_payable_account_id, "debit": 0, "credit": amount},
                            ]
                            posted_entry_id = post_journal_entry(
                                company_key=company_key,
                                date=payment_date,
                                description=normalized_description or f"Loan received - {normalized_lender_name or 'Lender'}",
                                reference=document_reference,
                                lines=lines,
                                created_by=role,
                                branch_id=branch_id,
                                payment_id=payment_id,
                                source_module="Banking",
                                source_table="payments",
                                source_type=payment_type,
                                source_id=payment_id,
                                user_role=role,
                                conn=conn,
                            )
                        elif payment_type == "Loan Repayment":
                            audit_transaction_type = "Loan Repayment"
                            source_account_id = get_or_create_account(company_key, source_method, "Asset", conn=conn)
                            loan_payable_account_id = get_or_create_account(company_key, "Loan Payable", "Liability", conn=conn)
                            lines = [
                                {"account_id": loan_payable_account_id, "debit": amount, "credit": 0},
                                {"account_id": source_account_id, "debit": 0, "credit": amount},
                            ]
                            posted_entry_id = post_journal_entry(
                                company_key=company_key,
                                date=payment_date,
                                description=normalized_description or f"Loan repayment - {normalized_lender_name or 'Lender'}",
                                reference=document_reference,
                                lines=lines,
                                created_by=role,
                                branch_id=branch_id,
                                payment_id=payment_id,
                                source_module="Banking",
                                source_table="payments",
                                source_type=payment_type,
                                source_id=payment_id,
                                user_role=role,
                                conn=conn,
                            )
                        elif payment_type == "Transfer Between Cash/Bank/Mobile Money":
                            audit_transaction_type = "Transfer"
                            source_account_id = get_or_create_account(company_key, source_method, "Asset", conn=conn)
                            destination_account_id = get_or_create_account(company_key, destination_method, "Asset", conn=conn)
                            lines = [
                                {"account_id": destination_account_id, "debit": amount, "credit": 0},
                                {"account_id": source_account_id, "debit": 0, "credit": amount},
                            ]
                            posted_entry_id = post_journal_entry(
                                company_key=company_key,
                                date=payment_date,
                                description=normalized_description or f"Transfer {source_method} to {destination_method}",
                                reference=document_reference,
                                lines=lines,
                                created_by=role,
                                branch_id=branch_id,
                                payment_id=payment_id,
                                source_module="Banking",
                                source_table="payments",
                                source_type=payment_type,
                                source_id=payment_id,
                                user_role=role,
                                conn=conn,
                            )
                        elif payment_type == "Owner Capital / Owner Investment":
                            audit_transaction_type = "Owner Capital"
                            cash_account_id = get_or_create_account(company_key, cash_account, "Asset", conn=conn)
                            owner_capital_account_id = get_or_create_account(company_key, "Owner Capital", "Equity", conn=conn)
                            lines = [
                                {"account_id": cash_account_id, "debit": amount, "credit": 0},
                                {"account_id": owner_capital_account_id, "debit": 0, "credit": amount},
                            ]
                            posted_entry_id = post_journal_entry(
                                company_key=company_key,
                                date=payment_date,
                                description=normalized_description or f"Owner capital - {normalized_owner_name or 'Owner'}",
                                reference=document_reference,
                                lines=lines,
                                created_by=role,
                                branch_id=branch_id,
                                payment_id=payment_id,
                                source_module="Banking",
                                source_table="payments",
                                source_type=payment_type,
                                source_id=payment_id,
                                user_role=role,
                                conn=conn,
                            )
                        else:
                            audit_transaction_type = "Owner Drawings"
                            owner_drawings_account_id = get_or_create_account(company_key, "Owner Drawings", "Equity", conn=conn)
                            cash_account_id = get_or_create_account(company_key, cash_account, "Asset", conn=conn)
                            lines = [
                                {"account_id": owner_drawings_account_id, "debit": amount, "credit": 0},
                                {"account_id": cash_account_id, "debit": 0, "credit": amount},
                            ]
                            posted_entry_id = post_journal_entry(
                                company_key=company_key,
                                date=payment_date,
                                description=normalized_description or f"Owner drawings - {normalized_owner_name or 'Owner'}",
                                reference=document_reference,
                                lines=lines,
                                created_by=role,
                                branch_id=branch_id,
                                payment_id=payment_id,
                                source_module="Banking",
                                source_table="payments",
                                source_type=payment_type,
                                source_id=payment_id,
                                user_role=role,
                                conn=conn,
                            )
                        log_audit_action(
                            conn,
                            company_key,
                            role,
                            f"Banking Transaction Posted: {payment_type}",
                            "Banking",
                            details=(
                                f"transaction_type={audit_transaction_type}; amount={amount:.2f}; "
                                f"source_method={audit_source_method}; destination_method={audit_destination_method}; "
                                f"owner_name={audit_owner_name or 'N/A'}; lender_name={audit_lender_name or 'N/A'}; reference={document_reference}; "
                                f"description={audit_description or 'N/A'}; user={role}"
                            ),
                            branch_id=branch_id,
                            action_type="post",
                            document_ref=document_reference,
                        )
                        log_system_event(
                            "INFO",
                            "Banking",
                            (
                                "Posted banking transaction transaction_type={payment_type} amount={amount:.2f} "
                                "source_method={source_method} destination_method={destination_method} "
                                "owner_name={owner_name} lender_name={lender_name} reference={reference} description={description} "
                                "posting_result=ok user={user} payment_id={payment_id}"
                            ).format(
                                payment_type=audit_transaction_type,
                                amount=float(amount or 0.0),
                                source_method=audit_source_method,
                                destination_method=audit_destination_method,
                                owner_name=audit_owner_name or "N/A",
                                lender_name=audit_lender_name or "N/A",
                                reference=document_reference,
                                description=audit_description or "N/A",
                                user=role,
                                payment_id=payment_id,
                            ),
                        )
                        conn.commit()
                    except Exception as post_error:
                        conn.rollback()
                        log_system_event(
                            "WARNING",
                            "Banking",
                            (
                                "Blocked banking transaction transaction_type={payment_type} amount={amount:.2f} "
                                "source_method={source_method} destination_method={destination_method} "
                                "lender_name={lender_name} reference={reference} posting_result=fail reason={reason}"
                            ).format(
                                payment_type=payment_type,
                                amount=float(amount or 0.0),
                                source_method=audit_source_method,
                                destination_method=audit_destination_method,
                                lender_name=audit_lender_name or "N/A",
                                reference=document_reference,
                                reason=sanitize_error_message(post_error),
                            ),
                        )
                        st.session_state[feedback_key] = {
                            "status": "error",
                            "message": build_user_safe_error(post_error, role),
                        }
                        st.rerun()
                        st.session_state[feedback_key] = {
                            "status": "success",
                            "message": (
                                "Banking transaction posted successfully.\n\n"
                                f"Transaction Type: {audit_transaction_type}\n"
                                f"Amount: {format_currency(amount)}\n"
                                f"Source Method: {audit_source_method}\n"
                                f"Destination Method: {audit_destination_method}\n"
                                f"Reference: {document_reference}\n"
                                f"Journal Entry ID: {posted_entry_id or 'N/A'}"
                            ),
                        }
                        st.rerun()

        st.markdown("---")
        st.subheader("Banking Journal Control")
        st.warning("Posted journal entries cannot be edited directly. Use reversal or void workflows to correct accounting records.")
        if require_permission(
            role,
            "void_or_reverse_document",
            action_label="reverse banking journals",
            company_key=company_key,
            conn=conn,
            branch_id=branch_id,
        ):
            banking_entries = conn.execute(
                """
                SELECT id, date, description, reference, created_by, approval_status
                FROM journal_entries
                WHERE company_key = ?
                  AND lower(COALESCE(source_module, '')) = 'banking'
                  AND COALESCE(is_voided, 0) = 0
                  AND COALESCE(reversed_entry_id, 0) = 0
                  AND COALESCE(approval_status, 'Posted') = 'Posted'
                  {branch_filter}
                ORDER BY date(date) DESC, id DESC
                LIMIT 100
                """.format(branch_filter="AND branch_id = ?" if branch_id else ""),
                (company_key, branch_id) if branch_id else (company_key,),
            ).fetchall()
            if banking_entries:
                entry_options = [
                    (
                        int(row["id"]),
                        f"#{int(row['id'])} | {row['date']} | {str(row['reference'] or 'NO-REF')} | {str(row['description'] or '').strip()}",
                    )
                    for row in banking_entries
                ]
                selected_entry_id = st.selectbox(
                    "Select Posted Banking Journal",
                    options=[item[0] for item in entry_options],
                    format_func=lambda value: next((label for item_id, label in entry_options if item_id == value), str(value)),
                    key=f"banking_reversal_entry_{company_key}",
                )
                reversal_reason = st.text_input("Reversal Reason", key=f"banking_reversal_reason_{company_key}")
                reversal_confirmed = st.checkbox(
                    "I confirm this banking correction must be posted as a reversal entry.",
                    key=f"banking_reversal_confirm_{company_key}",
                )
                if st.button("Reverse Selected Banking Journal", key=f"banking_reversal_btn_{company_key}", use_container_width=True):
                    if not reversal_reason.strip():
                        st.warning("Enter a reversal reason before posting the correction.")
                    elif not reversal_confirmed:
                        st.warning("Confirm the reversal before proceeding.")
                    else:
                        reversal_conn = None
                        try:
                            reversal_conn = get_connection()
                            reversal_entry_id = reverse_journal_entry(
                                selected_entry_id,
                                created_by=role,
                                reversal_date=datetime.now().date(),
                                reason=reversal_reason.strip(),
                                branch_id=branch_id,
                                conn=reversal_conn,
                            )
                            log_audit_action(
                                reversal_conn,
                                company_key,
                                role,
                                "Banking Journal Reversed",
                                "Banking",
                                details=f"original_entry_id={selected_entry_id}; reversal_entry_id={reversal_entry_id}; reason={reversal_reason.strip()}",
                                branch_id=branch_id,
                                action_type="post",
                                document_ref=str(selected_entry_id),
                            )
                            log_system_event(
                                "INFO",
                                "Banking",
                                f"Reversed banking journal original_entry_id={selected_entry_id} reversal_entry_id={reversal_entry_id} user={role}",
                            )
                            reversal_conn.commit()
                            st.success(f"Banking journal reversed successfully. Reversal entry ID: {reversal_entry_id}")
                            st.rerun()
                        except Exception as reversal_error:
                            if reversal_conn:
                                reversal_conn.rollback()
                            st.error(build_user_safe_error(reversal_error, role))
                        finally:
                            if reversal_conn:
                                reversal_conn.close()
            else:
                st.info("No posted banking journal entries are currently available for reversal.")
        else:
            st.caption("Reversal controls are restricted to authorized administrators.")

        with st.expander("Bank Reconciliation", expanded=False):
            recon_start = st.date_input("Reconciliation Start", value=datetime.now().date().replace(day=1), key=f"bank_recon_start_{company_key}")
            recon_end = st.date_input("Reconciliation End", value=datetime.now().date(), key=f"bank_recon_end_{company_key}")
            reconciliation = get_bank_reconciliation(company_key, recon_start, recon_end)
            summary = reconciliation.get("summary", {})
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("Journal Total", format_currency(summary.get("journal_total", 0.0)))
            rc2.metric("Matched Total", format_currency(summary.get("matched_total", 0.0)))
            rc3.metric("Unmatched Total", format_currency(summary.get("unmatched_total", 0.0)))
            matched_df = pd.DataFrame(reconciliation.get("matched", []))
            unmatched_df = pd.DataFrame(reconciliation.get("unmatched_journal", []))
            if not matched_df.empty:
                st.markdown("Matched Bank Items")
                st.dataframe(format_currency_dataframe(matched_df), use_container_width=True, hide_index=True)
            if not unmatched_df.empty:
                st.markdown("Unmatched Journal Bank Items")
                st.dataframe(format_currency_dataframe(unmatched_df), use_container_width=True, hide_index=True)
            if matched_df.empty and unmatched_df.empty:
                st.info("No bank or mobile-money journal movements found for the selected period.")
        conn.close()
    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))


# ==========================================
# ACCOUNTS AGING (RECEIVABLE / PAYABLE)
# ==========================================
def show_aging(company_key, aging_type="Receivable"):
    render_ui_standard_styles()
    page_header(f"📋 Accounts {aging_type}", f"Manage {aging_type} accounts and customer/supplier transactions")
    branch_id = st.session_state.get("active_branch_id")
    active_user = st.session_state.get("user") or {}
    role = active_user.get("role", "User")
    if aging_type == "Receivable":
        v_type = "Sales"
        status_filter = "Pending"
    else:
        v_type = "Purchase"
        status_filter = "Pending"

    try:
        if aging_type == "Receivable":
            tabs = st.tabs(["Customer Ledger", "Aging View"])
        else:
            tabs = [st.container()]

        with tabs[0]:
            if aging_type == "Receivable":
                conn = get_connection()
                customer_rows = get_customer_balances(company_key, conn=conn)

                register_col, transaction_col = st.columns(2)
                with register_col:
                    st.subheader("Add Customer")
                    with st.form(f"customer_register_form_{company_key}", clear_on_submit=True):
                        customer_name = st.text_input("Customer Name")
                        customer_phone = st.text_input("Phone")
                        customer_email = st.text_input("Email")
                        register_submitted = st.form_submit_button("Save Customer")
                    if register_submitted:
                        if not customer_name.strip():
                            st.warning("Enter a customer name.")
                        else:
                            customer_row_id = _register_customer(conn, company_key, customer_name, customer_phone, customer_email, branch_id=branch_id)
                            conn.commit()
                            log_audit_action(
                                conn,
                                company_key,
                                role,
                                "Customer Registered",
                                "Accounts Receivable",
                                f"Registered customer {customer_name.strip()}",
                                branch_id=branch_id,
                            )
                            st.success("Customer saved.")
                            conn.close()
                            st.rerun()

                with transaction_col:
                    st.subheader("Credit Customer")
                    if not customer_rows:
                        st.info("Register at least one customer to start posting debits and credits.")
                    else:
                        customer_labels = [
                            f"{row['name']} ({row['customer_id']}) | Balance {format_currency(float(row['balance'] or 0))}"
                            for row in customer_rows
                        ]
                        with st.form(f"customer_transaction_form_{company_key}", clear_on_submit=True):
                            selected_customer_label = st.selectbox("Customer", customer_labels)
                            transaction_type = st.selectbox("Transaction Type", ["Debit", "Credit"])
                            amount = st.number_input(f"Amount ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                            description = st.text_input("Description")
                            transaction_date = st.date_input("Transaction Date", value=datetime.now().date(), key=f"customer_tx_date_{company_key}")
                            tx_submitted = st.form_submit_button("Post Transaction")
                        if tx_submitted:
                            if amount <= 0 or not description.strip():
                                st.warning("Enter a valid amount and description.")
                            else:
                                selected_customer = customer_rows[customer_labels.index(selected_customer_label)]
                                result = _record_customer_ledger_transaction(
                                    conn,
                                    company_key,
                                    int(selected_customer["id"]),
                                    transaction_type,
                                    amount,
                                    description.strip(),
                                    role,
                                    branch_id=branch_id,
                                    reference=None,
                                    transaction_date=transaction_date,
                                    post_to_gl=True,
                                )
                                conn.commit()
                                log_audit_action(
                                    conn,
                                    company_key,
                                    role,
                                    f"Customer Ledger {transaction_type}",
                                    "Accounts Receivable",
                                    f"{result['customer_name']} | {description.strip()} | {format_currency(amount)} | Balance {format_currency(result['previous_balance'])} -> {format_currency(result['new_balance'])}",
                                    branch_id=branch_id,
                                )
                                st.success(f"{transaction_type} posted for {result['customer_name']}.")
                                conn.close()
                                st.rerun()

                customer_summary_rows = get_customer_balances(company_key, conn=conn)
                if customer_summary_rows:
                    st.markdown("Customer Balances")
                    customer_df = pd.DataFrame(
                        [
                            (row["customer_id"], row["name"], row["phone"], row["email"], row["balance"])
                            for row in customer_summary_rows
                        ],
                        columns=["Customer ID", "Name", "Phone", "Email", "Current Balance"],
                    )
                    st.dataframe(format_currency_dataframe(customer_df), use_container_width=True, hide_index=True)

                    customer_tx_rows = conn.execute(
                        """
                        SELECT c.name, ct.transaction_date, ct.transaction_type, ct.amount, ct.description, ct.reference, ct.created_by
                        FROM customer_transactions ct
                        JOIN customers c ON c.id = ct.customer_id
                        WHERE ct.company_key = ?
                        ORDER BY ct.transaction_date DESC, ct.id DESC
                        LIMIT 100
                        """,
                        (company_key,),
                    ).fetchall()
                    if customer_tx_rows:
                        st.markdown("Ledger Transactions")
                        ledger_df = pd.DataFrame(
                            customer_tx_rows,
                            columns=["Customer", "Date", "Type", "Amount", "Description", "Reference", "Recorded By"],
                        )
                        st.dataframe(format_currency_dataframe(ledger_df), use_container_width=True, hide_index=True)
                conn.close()

            elif aging_type == "Payable":
                conn = get_connection()
                supplier_rows = get_supplier_balances(company_key, conn=conn)

                register_col, transaction_col = st.columns(2)
                with register_col:
                    st.subheader("Add Supplier")
                    supplier_form_reset_key = f"supplier_register_form_reset_{company_key}"
                    with st.form(f"supplier_register_form_{company_key}", clear_on_submit=True):
                        supplier_name = st.text_input(
                            "Supplier Name",
                            key=_form_widget_key(f"supplier_register_name_{company_key}", supplier_form_reset_key),
                        )
                        supplier_phone = st.text_input(
                            "Phone",
                            key=_form_widget_key(f"supplier_register_phone_{company_key}", supplier_form_reset_key),
                        )
                        supplier_email = st.text_input(
                            "Email",
                            key=_form_widget_key(f"supplier_register_email_{company_key}", supplier_form_reset_key),
                        )
                        supplier_address = st.text_area(
                            "Address",
                            key=_form_widget_key(f"supplier_register_address_{company_key}", supplier_form_reset_key),
                        )
                        supplier_category = st.text_input(
                            "Category",
                            key=_form_widget_key(f"supplier_register_category_{company_key}", supplier_form_reset_key),
                        )
                        register_submitted = st.form_submit_button("Save Supplier")
                    if register_submitted:
                        if not supplier_name.strip():
                            st.warning("Enter a supplier name.")
                        else:
                            supplier_row_id = _register_supplier(
                                conn,
                                company_key,
                                supplier_name,
                                supplier_phone,
                                supplier_email,
                                supplier_address,
                                supplier_category,
                            )
                            conn.commit()
                            log_audit_action(
                                conn,
                                company_key,
                                role,
                                "Supplier Registered",
                                "Accounts Payable",
                                f"Registered supplier {supplier_name.strip()}",
                                branch_id=None,
                            )
                            conn.close()
                            _increment_form_reset(supplier_form_reset_key)
                            st.success("Supplier saved.")
                            st.rerun()

                with transaction_col:
                    st.subheader("Credit Supplier")
                    if not supplier_rows:
                        st.info("Register at least one supplier to start posting debits and credits.")
                    else:
                        supplier_labels = [
                            f"{row['name']} | Balance {format_currency(float(row['balance'] or 0))}"
                            for row in supplier_rows
                        ]
                        with st.form(f"supplier_transaction_form_{company_key}", clear_on_submit=True):
                            selected_supplier_label = st.selectbox("Supplier", supplier_labels)
                            transaction_type = st.selectbox("Transaction Type", ["Debit", "Credit"])
                            amount = st.number_input(f"Amount ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                            description = st.text_input("Description")
                            transaction_date = st.date_input("Transaction Date", value=datetime.now().date(), key=f"supplier_tx_date_{company_key}")
                            tx_submitted = st.form_submit_button("Post Transaction")
                        if tx_submitted:
                            if amount <= 0 or not description.strip():
                                st.warning("Enter a valid amount and description.")
                            else:
                                selected_supplier = supplier_rows[supplier_labels.index(selected_supplier_label)]
                                result = _record_supplier_ledger_transaction(
                                    conn,
                                    company_key,
                                    int(selected_supplier["id"]),
                                    transaction_type,
                                    amount,
                                    description.strip(),
                                    role,
                                    reference=None,
                                    transaction_date=transaction_date,
                                    post_to_gl=True,
                                )
                                conn.commit()
                                log_audit_action(
                                    conn,
                                    company_key,
                                    role,
                                    f"Supplier Ledger {transaction_type}",
                                    "Accounts Payable",
                                    f"{result['supplier_name']} | {description.strip()} | {format_currency(amount)} | Balance {format_currency(result['previous_balance'])} -> {format_currency(result['new_balance'])}",
                                    branch_id=None,
                                )
                                st.success(f"{transaction_type} posted for {result['supplier_name']}.")
                                conn.close()
                                st.rerun()

                supplier_summary_rows = get_supplier_balances(company_key, conn=conn)
                if supplier_summary_rows:
                    st.markdown("Supplier Balances")
                    supplier_df = pd.DataFrame(
                        [
                            (row["name"], row["phone"], row["email"], row["balance"])
                            for row in supplier_summary_rows
                        ],
                        columns=["Name", "Phone", "Email", "Current Balance"],
                    )
                    st.dataframe(format_currency_dataframe(supplier_df), use_container_width=True, hide_index=True)

                    try:
                        supplier_tx_rows = conn.execute(
                            """
                            SELECT s.name, st.transaction_date, st.transaction_type, st.amount, st.description, st.reference, st.created_by
                            FROM supplier_transactions st
                            JOIN suppliers s ON s.id = st.supplier_id
                            WHERE st.company_key = ?
                            ORDER BY st.transaction_date DESC, st.id DESC
                            LIMIT 100
                            """,
                            (company_key,),
                        ).fetchall()
                    except sqlite3.OperationalError as tx_error:
                        if "supplier_transactions" in str(tx_error).lower():
                            supplier_tx_rows = []
                            st.warning(
                                "Supplier transaction history is being prepared. Supplier balances and registration remain available."
                            )
                            logger.warning("Supplier transaction history unavailable because supplier_transactions is missing: %s", sanitize_error_message(tx_error))
                        else:
                            raise
                    if supplier_tx_rows:
                        st.markdown("Ledger Transactions")
                        ledger_df = pd.DataFrame(
                            supplier_tx_rows,
                            columns=["Supplier", "Date", "Type", "Amount", "Description", "Reference", "Recorded By"],
                        )
                        st.dataframe(format_currency_dataframe(ledger_df), use_container_width=True, hide_index=True)
                conn.close()

        with tabs[-1]:
            data = get_ar_aging_report(company_key) if aging_type == "Receivable" else get_ap_aging_report(company_key)
            if data:
                if aging_type == "Receivable":
                    df = pd.DataFrame(data)
                    df = df.rename(
                        columns={
                            "customer_id": "Customer ID",
                            "customer_name": "Customer Name",
                            "days_outstanding": "Days Outstanding",
                            "bucket": "Bucket",
                            "balance": f"Amount ({get_currency_symbol()})",
                        }
                    )
                else:
                    df = pd.DataFrame(data)
                    df = df.rename(
                        columns={
                            "supplier_name": "Supplier Name",
                            "days_outstanding": "Days Outstanding",
                            "bucket": "Bucket",
                            "balance": f"Amount ({get_currency_symbol()})",
                        }
                    )
                st.dataframe(format_currency_dataframe(df), use_container_width=True)
                if aging_type == "Receivable":
                    show_debtors_by_city_report(company_key)
            else:
                st.info(f"No {aging_type} records found.")
    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))


# ==========================================
# TAXATION (VAT / NHIL)
# ==========================================
def show_taxation(company_key):
    st.header("🧮 Taxation (VAT / NHIL)")
    VAT_RATE = 0.125
    NHIL_RATE = 0.025
    GETFUND_RATE = 0.025

    role = st.session_state.get("user", {}).get("role", "System")
    branch_id = st.session_state.get("active_branch_id")
    conn = None
    try:
        conn = get_connection()
        ensured_accounts = ensure_tax_control_accounts(company_key, conn=conn)
        account_map = {row["canonical_name"]: row for row in ensured_accounts}
        total_sales = get_account_total(company_key, "Sales Revenue", balance_side="credit", conn=conn)
        compare_legacy_and_journal_totals(company_key, logger_instance=logger, conn=conn)

        vat = round(total_sales * VAT_RATE, 2)
        nhil = round(total_sales * NHIL_RATE, 2)
        getfund = round(total_sales * GETFUND_RATE, 2)
        total_tax = vat + nhil + getfund
        balances = {
            name: _tax_control_balance(conn, company_key, info)
            for name, info in account_map.items()
        }
        vat_output_balance = balances["VAT Payable"]["Journal Balance"]
        vat_input_balance = balances["VAT Receivable"]["Journal Balance"]
        net_vat = round(vat_output_balance - vat_input_balance, 2)
        nhil_balance = balances["NHIL Payable"]["Journal Balance"]
        getfund_balance = balances["GETFund Levy Payable"]["Journal Balance"]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"Total Sales ({get_currency_symbol()})", format_currency(total_sales))
        col2.metric("VAT Output Journal", format_currency(vat_output_balance))
        col3.metric("VAT Input Journal", format_currency(vat_input_balance))
        col4.metric("Net VAT Payable" if net_vat >= 0 else "Net VAT Receivable", format_currency(abs(net_vat)))

        levy_col1, levy_col2, levy_col3 = st.columns(3)
        levy_col1.metric("NHIL Payable Journal", format_currency(nhil_balance))
        levy_col2.metric("GETFund Levy Journal", format_currency(getfund_balance))
        levy_col3.metric("Statutory Math Total", format_currency(total_tax))

        report_rows = [
            {
                "Tax": "VAT Output",
                "Report Math": vat,
                "Journal Balance": vat_output_balance,
                "Difference": round(vat - vat_output_balance, 2),
                "Basis": f"{VAT_RATE * 100:.1f}% of Sales Revenue",
            },
            {
                "Tax": "VAT Input",
                "Report Math": 0.0,
                "Journal Balance": vat_input_balance,
                "Difference": round(0.0 - vat_input_balance, 2),
                "Basis": "Journal-backed purchase input tax",
            },
            {
                "Tax": "Net VAT Payable / (Receivable)",
                "Report Math": vat,
                "Journal Balance": net_vat,
                "Difference": round(vat - net_vat, 2),
                "Basis": "VAT Output less VAT Input",
            },
            {
                "Tax": "NHIL Payable",
                "Report Math": nhil,
                "Journal Balance": nhil_balance,
                "Difference": round(nhil - nhil_balance, 2),
                "Basis": f"{NHIL_RATE * 100:.1f}% of Sales Revenue",
            },
            {
                "Tax": "GETFund Levy Payable",
                "Report Math": getfund,
                "Journal Balance": getfund_balance,
                "Difference": round(getfund - getfund_balance, 2),
                "Basis": f"{GETFUND_RATE * 100:.1f}% of Sales Revenue",
            },
        ]
        st.subheader("Tax Report")
        st.dataframe(format_currency_dataframe(pd.DataFrame(report_rows)), use_container_width=True, hide_index=True)

        account_rows = [
            {
                "Account": row["resolved_name"],
                "Expected Type": row["account_type"],
                "Status": row["status"],
            }
            for row in ensured_accounts
        ]
        st.subheader("Tax Control Accounts")
        st.dataframe(pd.DataFrame(account_rows), use_container_width=True, hide_index=True)
        st.caption("COVID-19 Health Recovery Levy is not configured elsewhere in this app, so no journal account or settlement line is created for it in this phase.")

        st.subheader("Tax Settlement")
        payable_options = [
            ("VAT Payable", vat_output_balance),
            ("NHIL Payable", nhil_balance),
            ("GETFund Levy Payable", getfund_balance),
        ]
        payable_options = [(name, balance) for name, balance in payable_options if balance > 0]
        if not payable_options:
            st.info("No positive journal-backed tax liability is available for settlement.")
        else:
            with st.form(f"tax_settlement_form_{company_key}"):
                selected_label = st.selectbox(
                    "Tax Liability",
                    [f"{name} - {format_currency(balance)}" for name, balance in payable_options],
                )
                payment_method = st.selectbox("Payment Account", ["Cash", "Bank", "Mobile Money"])
                payment_date = st.date_input("Payment Date", value=datetime.now().date())
                amount = st.number_input(f"Settlement Amount ({get_currency_symbol()})", min_value=0.0, step=0.01)
                reference = st.text_input("Reference", value=f"TAX-{datetime.now().strftime('%Y%m%d%H%M%S')}")
                submitted = st.form_submit_button("Post Tax Settlement")
                if submitted:
                    if not require_permission(
                        role,
                        "post_accounting_document",
                        action_label="post tax settlement",
                        company_key=company_key,
                        conn=conn,
                        branch_id=branch_id,
                    ):
                        return
                    selected_account_name = selected_label.split(" - ", 1)[0]
                    selected_balance = dict(payable_options)[selected_account_name]
                    if amount <= 0:
                        st.warning("Settlement amount must be greater than zero.")
                        return
                    if amount - selected_balance > 0.01:
                        st.warning("Settlement amount cannot exceed the current journal-backed liability.")
                        return
                    payment_account_type = "Asset"
                    settlement_lines = [
                        {
                            "account_id": int(account_map[selected_account_name]["account_id"]),
                            "debit": round(float(amount), 2),
                            "credit": 0,
                        },
                        {
                            "account_id": get_account_id(conn, payment_method, payment_account_type),
                            "debit": 0,
                            "credit": round(float(amount), 2),
                        },
                    ]
                    post_journal_entry(
                        company_key=company_key,
                        date=payment_date,
                        description=f"Tax settlement payment - {selected_account_name}",
                        reference=reference.strip() or f"TAX-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        lines=settlement_lines,
                        created_by=role,
                        branch_id=branch_id,
                        source_module="Taxation",
                        source_table="journal_entries",
                        source_type="Tax Settlement",
                        approval_status="Posted",
                        user_role=role,
                        conn=conn,
                    )
                    conn.commit()
                    st.success("Tax settlement posted to the journal.")
                    st.rerun()
    except Exception as e:
        if conn:
            conn.rollback()
        st.error(build_user_safe_error(e, role))
    finally:
        if conn:
            conn.close()


# ==========================================
# GHANA PAYROLL (SSNIT)
# ==========================================
def show_payroll(company_key, role):
    render_ui_standard_styles()
    page_header("💳 Payroll & Salaries", "Manage employee payroll, salaries, and statutory deductions")
    payroll_print_preview_key = f"payroll_print_preview_{company_key}"

    if role == "Demo":
        _demo_notice()
        demo_df = pd.DataFrame({
            "Employee": ["John Mensah", "Ama Asante"],
            "Basic Salary": [2500.0, 3000.0],
            "SSNIT T1": [137.5, 165.0],
            "PAYE": [210.0, 280.0],
            "Net Salary": [2152.5, 2555.0],
            "Month": ["March 2026"] * 2,
        })
        st.dataframe(format_currency_dataframe(demo_df), use_container_width=True)
        return
    if not require_permission(
        role,
        "view_payroll",
        action_label="view payroll",
        company_key=company_key,
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return
    can_manage_payroll = user_has_permission(role, "manage_payroll")

    with st.expander("➕ Add Payroll Entry", expanded=True):
        with st.form("payroll_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                emp_name = st.text_input("Employee Name")
                basic_salary = st.number_input(f"Basic Salary ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                allowances = st.number_input(f"Allowances ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                deductions = st.number_input(f"Other Deductions ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                paye_override = st.number_input(f"PAYE Override ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                ssnit_override = st.number_input(f"SSNIT Employee Override ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
            with col2:
                month = st.selectbox("Month", ["January","February","March","April","May","June",
                                               "July","August","September","October","November","December"])
                year = st.selectbox("Year", [str(y) for y in range(2023, 2030)],
                                    index=[str(y) for y in range(2023, 2030)].index(str(datetime.now().year)))
                payment_status = st.selectbox("Payment Status", ["Paid", "Unpaid"])
                payment_method = st.selectbox("Payment Method", ["Cash", "Bank", "Mobile Money"], disabled=payment_status != "Paid")

            submitted = st.form_submit_button("Calculate & Save")
            if submitted and emp_name and basic_salary > 0:
                if not require_permission(
                    role,
                    "manage_payroll",
                    action_label="process payroll",
                    company_key=company_key,
                    branch_id=st.session_state.get("active_branch_id"),
                ):
                    return
                payroll_values = _calculate_payroll_values(basic_salary, allowances, deductions)
                if paye_override > 0:
                    payroll_values["paye"] = float(paye_override)
                if ssnit_override > 0:
                    payroll_values["ssnit_t1"] = float(ssnit_override)
                gross_salary = round(float(basic_salary or 0.0) + float(allowances or 0.0), 2)
                total_ssnit = round(float(payroll_values["ssnit_t1"] or 0.0) + float(payroll_values["ssnit_t2"] or 0.0), 2)
                other_deductions = round(float(deductions or 0.0), 2)
                payroll_values["net_salary"] = round(gross_salary - float(payroll_values["paye"] or 0.0) - total_ssnit - other_deductions, 2)
                if payroll_values["net_salary"] < 0:
                    st.warning("Payroll net salary cannot be negative.")
                    return
                try:
                    conn = get_connection()
                    payroll_cursor = conn.execute(
                        ensure_insert_sql_returning(
                            """INSERT INTO payroll
                               (company_key, emp_name, basic_salary, allowances, ssnit_t1, ssnit_t2,
                                taxable_income, paye, net_salary, deductions, month, year, payment_status, payment_method,
                                approval_status, created_by, status)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Posted', ?, 'Active')"""
                        ),
                        (
                            company_key,
                            emp_name,
                            basic_salary,
                            allowances,
                            payroll_values["ssnit_t1"],
                            payroll_values["ssnit_t2"],
                            payroll_values["taxable_income"],
                            payroll_values["paye"],
                            payroll_values["net_salary"],
                            deductions,
                            month,
                            year,
                            payment_status,
                            payment_method if payment_status == "Paid" else None,
                            role,
                        ),
                    )
                    payroll_id = get_inserted_id(payroll_cursor)
                    conn.execute(
                        """
                        INSERT INTO payroll_records
                            (company_key, period_start, period_end, employee_name, gross_pay, deductions, net_pay, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            company_key,
                            f"{year}-{str(['January','February','March','April','May','June','July','August','September','October','November','December'].index(month)+1).zfill(2)}-01",
                            f"{year}-{str(['January','February','March','April','May','June','July','August','September','October','November','December'].index(month)+1).zfill(2)}-28",
                            emp_name,
                            gross_salary,
                            deductions,
                            payroll_values["net_salary"],
                            payment_status,
                        ),
                    )
                    payroll_reference = f"PAY-{emp_name}-{month}-{year}"
                    payroll_lines = _build_payroll_journal_lines(
                        conn,
                        company_key,
                        gross_salary=gross_salary,
                        paye_amount=payroll_values["paye"],
                        ssnit_amount=total_ssnit,
                        other_deductions=other_deductions,
                        net_salary=payroll_values["net_salary"],
                        payment_status=payment_status,
                        payment_method=payment_method,
                    )
                    post_journal_entry(
                        company_key=company_key,
                        date=datetime(int(year), ['January','February','March','April','May','June','July','August','September','October','November','December'].index(month)+1, 1).date(),
                        description="Payroll accrual",
                        reference=payroll_reference,
                        lines=payroll_lines,
                        created_by=role,
                        branch_id=st.session_state.get("active_branch_id"),
                        source_module="Payroll",
                        source_table="payroll",
                        source_type="Payroll",
                        source_id=payroll_id,
                        approval_status="Posted",
                        user_role=role,
                        conn=conn,
                    )
                    conn.commit()
                    log_audit_action(
                        conn,
                        company_key,
                        role,
                        "Payroll Entry Added",
                        "Payroll",
                        f"{emp_name} - {month} {year} - gross={gross_salary:.2f} paye={float(payroll_values['paye'] or 0.0):.2f} ssnit={total_ssnit:.2f} net={float(payroll_values['net_salary'] or 0.0):.2f}",
                    )
                    conn.close()
                    st.success("Entry Updated")
                    st.rerun()
                except Exception as e:
                    st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))

    st.subheader("Payroll Register")
    conn = None
    try:
        conn = get_connection()
        data = conn.execute(
            """SELECT id, emp_name, basic_salary, allowances, deductions, ssnit_t1, paye, net_salary, month, year,
                      payment_status, payment_method, COALESCE(status, 'Active'), posted_entry_id
               FROM payroll WHERE company_key = ? ORDER BY year DESC, month DESC""",
            (company_key,),
        ).fetchall()
        if data:
            df = pd.DataFrame(data, columns=["ID", "Employee", "Basic Salary", "Allowances", "Deductions",
                                              "SSNIT T1", "PAYE", "Net Salary", "Month", "Year", "Payment Status", "Payment Method", "Status", "Posted Entry ID"])
            payroll_posted_entry_map = {
                int(row["ID"]): _get_payroll_posted_entry_id(
                    conn,
                    company_key,
                    int(row["ID"]),
                    payroll_reference=f"PAY-{row['Employee']}-{row['Month']}-{row['Year']}",
                )
                for _, row in df.iterrows()
            }
            st.dataframe(format_currency_dataframe(df), use_container_width=True)
            if can_manage_payroll:
                selected_payroll_key = f"payroll_edit_selected_{company_key}"
                void_payroll_key = f"payroll_void_selected_{company_key}"
                for _, payroll_list_row in df.iterrows():
                    info_cols = st.columns([3, 1, 1, 1])
                    name_col, edit_col, void_col, print_col = info_cols
                    has_posted_payroll = payroll_posted_entry_map.get(int(payroll_list_row["ID"])) is not None
                    name_col.caption(
                        f"{payroll_list_row['Employee']} | Salary GHS {float(payroll_list_row['Basic Salary']):,.2f} | "
                        f"Net GHS {float(payroll_list_row['Net Salary']):,.2f} | {payroll_list_row['Status']} | "
                        f"Method {payroll_list_row['Payment Method'] or 'N/A'}"
                    )
                    if edit_col.button("Edit", key=f"payroll_edit_btn_{company_key}_{int(payroll_list_row['ID'])}"):
                        st.session_state[selected_payroll_key] = int(payroll_list_row["ID"])
                    if payroll_list_row["Status"] not in {"Void", "Reversed"} and void_col.button("Void / Reverse", key=f"payroll_void_btn_{company_key}_{int(payroll_list_row['ID'])}"):
                        if not require_permission(
                            role,
                            "void_or_reverse_document",
                            action_label="reverse payroll",
                            company_key=company_key,
                        ):
                            continue
                        st.session_state[void_payroll_key] = int(payroll_list_row["ID"])
                    if print_col.button("Print", key=f"payroll_print_btn_{company_key}_{int(payroll_list_row['ID'])}"):
                        st.session_state[payroll_print_preview_key] = _build_payslip_html(payroll_list_row)
                        st.session_state[f"payroll_print_record_id_{company_key}"] = int(payroll_list_row['ID'])
                        st.rerun()
                    if has_posted_payroll:
                        st.caption("Posted payroll cannot be financially edited directly. Use reversal/void workflow.")
                void_payroll_id = st.session_state.get(void_payroll_key)
                if void_payroll_id is not None:
                    st.warning("Posted payroll entries cannot be edited directly. Use reversal/void workflow for corrections.")
                    reversal_reason = st.text_input("Reversal / Void Reason", key=f"payroll_void_reason_{company_key}_{void_payroll_id}")
                    confirm_col, cancel_col = st.columns(2)
                    if confirm_col.button("Confirm Void / Reverse", key=f"payroll_void_confirm_btn_{company_key}_{void_payroll_id}"):
                        if not reversal_reason.strip():
                            st.warning("Enter a reversal reason before voiding payroll.")
                        else:
                            payroll_row = df.loc[df["ID"] == int(void_payroll_id)].iloc[0]
                            posted_entry_id = payroll_posted_entry_map.get(int(void_payroll_id))
                            if posted_entry_id is not None:
                                reverse_journal_entry(
                                    int(posted_entry_id),
                                    created_by=role,
                                    reversal_date=datetime.now().date(),
                                    reason=reversal_reason.strip(),
                                    branch_id=st.session_state.get("active_branch_id"),
                                    conn=conn,
                                )
                                conn.execute(
                                    "UPDATE payroll SET status = 'Reversed' WHERE id = ? AND company_key = ?",
                                    (int(void_payroll_id), company_key),
                                )
                                log_audit_action(
                                    conn,
                                    company_key,
                                    role,
                                    "Payroll Reversed",
                                    "Payroll",
                                    f"Reversed payroll ID {int(void_payroll_id)} reason={reversal_reason.strip()}",
                                )
                            else:
                                conn.execute(
                                    "UPDATE payroll SET status = 'Void' WHERE id = ? AND company_key = ?",
                                    (int(void_payroll_id), company_key),
                                )
                                log_audit_action(
                                    conn,
                                    company_key,
                                    role,
                                    "Payroll Voided",
                                    "Payroll",
                                    f"Voided payroll ID {int(void_payroll_id)} reason={reversal_reason.strip()}",
                                )
                            conn.commit()
                            _clear_streamlit_state(void_payroll_key, selected_payroll_key, f"payroll_void_reason_{company_key}_{void_payroll_id}")
                            st.success("Entry Updated")
                            st.rerun()
                    if cancel_col.button("Cancel", key=f"payroll_void_cancel_btn_{company_key}_{void_payroll_id}"):
                        _clear_streamlit_state(void_payroll_key, f"payroll_void_reason_{company_key}_{void_payroll_id}")
                        st.rerun()
                payroll_record_id = st.session_state.get(selected_payroll_key, int(df["ID"].iloc[0]))
                edit_row = df.loc[df["ID"] == payroll_record_id].iloc[0]
                payroll_is_posted = payroll_posted_entry_map.get(int(payroll_record_id)) is not None
                with st.form(f"payroll_edit_form_{company_key}_{payroll_record_id}", clear_on_submit=True):
                    if payroll_is_posted:
                        st.warning("Posted payroll records cannot be financially edited directly. Use reversal/void workflow.")
                    edit_salary = st.number_input("Salary", min_value=0.0, value=float(edit_row["Basic Salary"] or 0.0), disabled=payroll_is_posted)
                    edit_bonus = st.number_input("Bonus", min_value=0.0, value=float(edit_row["Allowances"] or 0.0), disabled=payroll_is_posted)
                    edit_deductions = st.number_input("Other Deductions", min_value=0.0, value=float(edit_row["Deductions"] or 0.0), disabled=payroll_is_posted)
                    edit_status = st.selectbox("Payment Status", ["Paid", "Unpaid"], index=0 if edit_row["Payment Status"] == "Paid" else 1, disabled=payroll_is_posted)
                    edit_payment_method = st.selectbox(
                        "Payment Method",
                        ["Cash", "Bank", "Mobile Money"],
                        index=["Cash", "Bank", "Mobile Money"].index(edit_row["Payment Method"]) if edit_row["Payment Method"] in ["Cash", "Bank", "Mobile Money"] else 0,
                        disabled=payroll_is_posted or edit_status != "Paid",
                    )
                    if st.form_submit_button("Update Payroll"):
                        if payroll_is_posted:
                            st.warning("Posted payroll records cannot be financially edited directly. Use reversal/void workflow.")
                            return
                        updated_values = _calculate_payroll_values(edit_salary, edit_bonus, edit_deductions)
                        details = (
                            f"{edit_row['Employee']} salary {float(edit_row['Basic Salary']):,.2f}->{edit_salary:,.2f}; "
                            f"bonus {float(edit_row['Allowances']):,.2f}->{edit_bonus:,.2f}; "
                            f"deductions {float(edit_row['Deductions']):,.2f}->{edit_deductions:,.2f}"
                        )
                        conn.execute(
                            """
                            UPDATE payroll
                            SET basic_salary = ?, allowances = ?, ssnit_t1 = ?, ssnit_t2 = ?,
                                taxable_income = ?, paye = ?, net_salary = ?, deductions = ?, payment_status = ?, payment_method = ?
                            WHERE id = ? AND company_key = ?
                            """,
                            (
                                edit_salary,
                                edit_bonus,
                                updated_values["ssnit_t1"],
                                updated_values["ssnit_t2"],
                                updated_values["taxable_income"],
                                updated_values["paye"],
                                updated_values["net_salary"],
                                edit_deductions,
                                edit_status,
                                edit_payment_method if edit_status == "Paid" else None,
                                int(payroll_record_id),
                                company_key,
                            ),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Payroll Updated", "Payroll", details)
                        _clear_streamlit_state(selected_payroll_key, void_payroll_key)
                        st.success("Entry Updated")
                        st.rerun()
            if role != "Master Admin":
                for _, payroll_list_row in df.iterrows():
                    info_col, print_col = st.columns([4, 1])
                    info_col.caption(
                        f"{payroll_list_row['Employee']} | Salary GHS {float(payroll_list_row['Basic Salary']):,.2f} | "
                        f"Net GHS {float(payroll_list_row['Net Salary']):,.2f} | {payroll_list_row['Status']}"
                    )
                    if print_col.button("Print Payslip", key=f"payroll_print_btn_{company_key}_{int(payroll_list_row['ID'])}"):
                        st.session_state[payroll_print_preview_key] = _build_payslip_html(payroll_list_row)
                        st.session_state[f"payroll_print_record_id_{company_key}"] = int(payroll_list_row['ID'])
                        st.rerun()
        else:
            st.info("No payroll records found.")
        if st.session_state.get(payroll_print_preview_key):
            _inject_print_styles()
            st.subheader("Payslip Preview")
            st.markdown(st.session_state[payroll_print_preview_key], unsafe_allow_html=True)
    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))
    finally:
        if conn:
            conn.close()


# ==========================================
# FIXED ASSET REGISTER
# ==========================================
def _show_legacy_fixed_assets(company_key, role):
    st.header("🏛️ Asset Register")
    delete_success_key = f"asset_delete_success_{company_key}"
    if st.session_state.get(delete_success_key):
        st.success("Item deleted")
        st.session_state.pop(delete_success_key, None)

    if role == "Demo":
        _demo_notice()
        demo_df = pd.DataFrame({
            "Asset Name": ["Company Vehicle", "Office Computer"],
            "Category": ["Vehicle", "Equipment"],
            "Cost (GHS)": [85000.0, 5500.0],
            "Depreciation Rate (%)": [20.0, 33.3],
            "Book Value (GHS)": [68000.0, 3685.0],
            "Status": ["Active", "Active"],
        })
        st.dataframe(format_currency_dataframe(demo_df), use_container_width=True)
        return

    with st.expander("➕ Add Fixed Asset", expanded=True):
        with st.form("fixed_asset_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                asset_name = st.text_input("Asset Name")
                asset_category = st.selectbox("Category", ["Vehicle", "Equipment", "Building", "Furniture", "Land", "Other"])
                purchase_date = st.date_input("Purchase Date", datetime.now().date())
            with col2:
                cost = st.number_input("Cost (GHS)", min_value=0.0, step=0.01)
                opening_book_value = st.number_input("Opening Book Value", min_value=0.0, step=0.01)
                depreciation_rate = st.number_input("Depreciation Rate (%)", min_value=0.0, max_value=100.0, step=0.1)
                location = st.text_input("Location")

            submitted = st.form_submit_button("Add Asset")
            if submitted and asset_name and cost > 0:
                book_value = opening_book_value if opening_book_value > 0 else cost
                try:
                    conn = get_connection()
                    conn.execute(
                        """INSERT INTO fixed_assets
                           (company_key, asset_name, asset_category, purchase_date, cost,
                            opening_book_value, depreciation_rate, accumulated_depreciation, book_value, location)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                        (company_key, asset_name, asset_category, purchase_date.isoformat(),
                         cost, book_value, depreciation_rate, book_value, location),
                    )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Fixed Asset Added", "Fixed Assets", f"{asset_name} - GHS{cost:,.2f}")
                    conn.close()
                    st.success("Entry Updated")
                    st.rerun()
                except Exception as e:
                    st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))

    st.subheader("🏛️ Asset Register")
    try:
        conn = get_connection()
        data = conn.execute(
            """SELECT id, asset_name, asset_category, purchase_date, cost, opening_book_value,
                      depreciation_rate, accumulated_depreciation, book_value, location, status
               FROM fixed_assets WHERE company_key = ? ORDER BY asset_name""",
            (company_key,),
        ).fetchall()
        if data:
            df = pd.DataFrame(data, columns=["ID", "Asset Name", "Category", "Purchase Date", f"Cost ({get_currency_symbol()})",
                                              "Opening Book Value", "Dep. Rate (%)", "Accum. Dep.", "Current Value", "Location", "Status"])
            st.dataframe(format_currency_dataframe(df), use_container_width=True)

            total_cost = df[f"Cost ({get_currency_symbol()})"].sum()
            total_book = df["Current Value"].sum()
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Assets", len(df))
            col2.metric(f"Total Cost ({get_currency_symbol()})", format_currency(total_cost))
            col3.metric(f"Total Book Value ({get_currency_symbol()})", format_currency(total_book))
            if role in ("Master Admin", "Bookkeeper", "Branch_Bookkeeper", "Sub-Admin"):
                selected_asset_key = f"asset_edit_selected_{company_key}"
                delete_asset_key = f"asset_delete_selected_{company_key}"
                for _, asset_row in df.iterrows():
                    name_col, edit_col, delete_col = st.columns([4, 1, 1])
                    name_col.caption(
                        f"{asset_row['Asset Name']} | Current GHS {float(asset_row['Current Value']):,.2f} | "
                        f"Purchase Date {asset_row['Purchase Date']}"
                    )
                    if edit_col.button("Edit", key=f"asset_edit_btn_{company_key}_{int(asset_row['ID'])}"):
                        st.session_state[selected_asset_key] = int(asset_row["ID"])
                    if delete_col.button("🗑️ Delete Record", key=f"asset_delete_btn_{company_key}_{int(asset_row['ID'])}"):
                        st.session_state[delete_asset_key] = int(asset_row["ID"])
                delete_asset_id = st.session_state.get(delete_asset_key)
                if delete_asset_id is not None:
                    st.warning("Are you sure you want to permanently delete this item?")
                    confirm_col, cancel_col = st.columns(2)
                    if confirm_col.button("🗑️ Delete Record", key=f"asset_delete_confirm_btn_{company_key}_{delete_asset_id}"):
                        conn.execute(
                            "DELETE FROM fixed_assets WHERE id = ? AND company_key = ?",
                            (int(delete_asset_id), company_key),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Fixed Asset Deleted", "Fixed Assets", f"Deleted asset ID {int(delete_asset_id)}")
                        _clear_streamlit_state(delete_asset_key, selected_asset_key)
                        st.session_state[delete_success_key] = True
                        st.rerun()
                    if cancel_col.button("Cancel", key=f"asset_delete_cancel_btn_{company_key}_{delete_asset_id}"):
                        _clear_streamlit_state(delete_asset_key)
                        st.rerun()
                edit_asset_id = st.session_state.get(selected_asset_key, int(df["ID"].iloc[0]))
                edit_asset_row = df.loc[df["ID"] == edit_asset_id].iloc[0]
                with st.form(f"asset_edit_form_{company_key}_{edit_asset_id}", clear_on_submit=True):
                    edit_asset_name = st.text_input("Asset Name", value=str(edit_asset_row["Asset Name"] or ""))
                    edit_purchase_date = st.date_input("Purchase Date", value=pd.to_datetime(edit_asset_row["Purchase Date"]).date())
                    edit_cost = st.number_input("Cost (GHS)", min_value=0.0, value=float(edit_asset_row["Cost (GHS)"] or 0.0))
                    edit_opening_book = st.number_input("Opening Book Value", min_value=0.0, value=float(edit_asset_row["Opening Book Value"] or 0.0))
                    edit_depr_rate = st.number_input("Depreciation Rate (%)", min_value=0.0, max_value=100.0, value=float(edit_asset_row["Dep. Rate (%)"] or 0.0))
                    edit_location = st.text_input("Location", value=str(edit_asset_row["Location"] or ""))
                    if st.form_submit_button("Update Asset"):
                        conn.execute(
                            """
                            UPDATE fixed_assets
                            SET asset_name = ?, purchase_date = ?, cost = ?, opening_book_value = ?,
                                depreciation_rate = ?, book_value = ?, location = ?
                            WHERE id = ? AND company_key = ?
                            """,
                            (
                                edit_asset_name,
                                edit_purchase_date.isoformat(),
                                edit_cost,
                                edit_opening_book,
                                edit_depr_rate,
                                edit_opening_book if edit_opening_book > 0 else edit_cost,
                                edit_location,
                                int(edit_asset_id),
                                company_key,
                            ),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Fixed Asset Updated", "Fixed Assets", f"Updated asset ID {int(edit_asset_id)}")
                        _clear_streamlit_state(selected_asset_key, delete_asset_key)
                        st.success("Entry Updated")
                        st.rerun()
        else:
            st.info("No fixed assets registered yet.")
    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))
    finally:
        if 'conn' in locals() and conn:
            conn.close()


# Override the legacy fixed-assets screen with the IFRS-ready straight-line version.
def show_fixed_assets(company_key, role):
    st.header("📦 Asset Register")
    delete_success_key = f"asset_delete_success_{company_key}"
    if st.session_state.get(delete_success_key):
        st.success("Item deleted")
        st.session_state.pop(delete_success_key, None)

    if role == "Demo":
        _demo_notice()
        demo_df = pd.DataFrame(
            {
                "Asset Name": ["Company Vehicle", "Office Computer"],
                "Category": ["Vehicle", "Equipment"],
                "Cost (GHS)": [85000.0, 5500.0],
                "Useful Life (Years)": [5.0, 3.0],
                "Book Value (GHS)": [68000.0, 3685.0],
                "Status": ["Active", "Active"],
            }
        )
        st.dataframe(format_currency_dataframe(demo_df), use_container_width=True)
        return
    if not require_permission(
        role,
        "view_fixed_assets",
        action_label="view fixed assets",
        company_key=company_key,
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return
    can_manage_assets = user_has_permission(role, "manage_fixed_assets")

    action_col1, action_col2 = st.columns(2)
    if action_col1.button("Post Current Depreciation", key=f"run_depreciation_{company_key}"):
        if not require_permission(
            role,
            "manage_fixed_assets",
            action_label="post fixed asset depreciation",
            company_key=company_key,
            branch_id=st.session_state.get("active_branch_id"),
        ):
            return
        try:
            posted_entries = run_straight_line_depreciation(company_key, created_by=role)
            st.success(f"Depreciation run complete. Posted {posted_entries} journal entr{'y' if posted_entries == 1 else 'ies'}.")
            st.rerun()
        except Exception as exc:
            st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
    action_col2.caption("Straight-line depreciation posts to Depreciation Expense and Accumulated Depreciation.")

    supplier_options = [""]
    supplier_lookup = {}
    supplier_conn = None
    try:
        supplier_conn = get_connection()
        supplier_rows = supplier_conn.execute(
            "SELECT id, name FROM suppliers WHERE company_key = ? ORDER BY name",
            (company_key,),
        ).fetchall()
        supplier_lookup = {
            str(row["name"]).strip(): int(row["id"])
            for row in supplier_rows
            if str(row["name"] or "").strip()
        }
        supplier_options.extend(sorted(supplier_lookup.keys()))
    finally:
        if supplier_conn:
            supplier_conn.close()

    with st.expander("Add Fixed Asset", expanded=True):
        with st.form("fixed_asset_form_override", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                asset_name = st.text_input("Asset Name")
                asset_category = st.selectbox("Category", ["Vehicle", "Equipment", "Building", "Furniture", "Land", "Other"])
                purchase_date = st.date_input("Acquisition Date", datetime.now().date())
                acquisition_type = st.selectbox("Acquisition Type / Source", FIXED_ASSET_ACQUISITION_TYPES)
                payment_method = None
                supplier_name = ""
                owner_contributor_name = ""
                if acquisition_type == "Purchased with Cash/Bank/Mobile Money":
                    payment_method = st.selectbox("Payment Method", ["Cash", "Bank", "Mobile Money"])
                elif acquisition_type == "Purchased on Credit":
                    supplier_name = st.selectbox("Supplier", supplier_options)
                elif acquisition_type == "Owner-Contributed Asset":
                    owner_contributor_name = st.text_input("Owner / Investor Name")
            with col2:
                cost = st.number_input(f"Cost ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                opening_book_value = st.number_input("Opening Book Value", min_value=0.0, step=0.01)
                useful_life_years = st.number_input("Useful Life (Years)", min_value=0.0, step=1.0)
                residual_value = st.number_input(f"Residual Value ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                location = st.text_input("Location")
                custodian = st.text_input("Custodian")
                asset_description = st.text_input("Description")
                asset_notes = st.text_area("Notes")

            if st.form_submit_button("Add Asset") and asset_name and cost > 0:
                if not require_permission(
                    role,
                    "manage_fixed_assets",
                    action_label="create fixed assets",
                    company_key=company_key,
                    branch_id=st.session_state.get("active_branch_id"),
                ):
                    return
                book_value = opening_book_value if opening_book_value > 0 else cost
                depreciation_rate = round((100.0 / useful_life_years), 4) if useful_life_years > 0 else 0.0
                try:
                    conn = get_connection()
                    normalized_acquisition_type = _normalize_fixed_asset_acquisition_type(acquisition_type)
                    supplier_id = None
                    if normalized_acquisition_type == "Purchased on Credit":
                        supplier_id = supplier_lookup.get(str(supplier_name or "").strip())
                        if not supplier_id:
                            conn.close()
                            st.warning("Select a supplier for a credit asset purchase.")
                            return
                    asset_cursor = conn.execute(
                        ensure_insert_sql_returning(
                            """
                            INSERT INTO fixed_assets
                               (company_key, asset_name, asset_category, purchase_date, cost,
                                opening_book_value, useful_life_years, residual_value, depreciation_method,
                                depreciation_rate, accumulated_depreciation, book_value, last_depreciation_date, location,
                                custodian, description, notes, acquisition_type, payment_method, supplier_id,
                                owner_contributor_name, status, approval_status, created_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Straight-line', ?, 0, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', 'Posted', ?)
                            """
                        ),
                        (
                            company_key,
                            asset_name,
                            asset_category,
                            purchase_date.isoformat(),
                            cost,
                            book_value,
                            useful_life_years,
                            residual_value,
                            depreciation_rate,
                            book_value,
                            location,
                            custodian.strip() or None,
                            asset_description.strip() or None,
                            asset_notes.strip() or None,
                            normalized_acquisition_type,
                            payment_method if normalized_acquisition_type == "Purchased with Cash/Bank/Mobile Money" else None,
                            supplier_id,
                            owner_contributor_name.strip() or None,
                            role,
                        ),
                    )
                    asset_id = get_inserted_id(asset_cursor)
                    acquisition_lines, acquisition_meta = _build_fixed_asset_acquisition_lines(
                        conn,
                        company_key,
                        acquisition_type=normalized_acquisition_type,
                        cost=cost,
                        payment_method=payment_method,
                    )
                    post_journal_entry(
                        company_key=company_key,
                        date=purchase_date,
                        description="Fixed asset acquisition",
                        reference=f"FA-{asset_id}",
                        lines=acquisition_lines,
                        created_by=role,
                        branch_id=st.session_state.get("active_branch_id"),
                        supplier_id=supplier_id,
                        source_module="Fixed Assets",
                        source_table="fixed_assets",
                        source_type=acquisition_meta["acquisition_type"],
                        source_id=asset_id,
                        approval_status="Posted",
                        user_role=role,
                        conn=conn,
                    )
                    conn.commit()
                    log_audit_action(
                        conn,
                        company_key,
                        role,
                        "Fixed Asset Added",
                        "Fixed Assets",
                        f"{asset_name} - GHS{cost:,.2f} - acquisition_type={normalized_acquisition_type}",
                    )
                    conn.close()
                    st.success("Entry Updated")
                    st.rerun()
                except Exception as exc:
                    st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))

    st.subheader("📦 Asset Register")
    conn = None
    try:
        conn = get_connection()
        data = conn.execute(
            """
            SELECT id, asset_name, asset_category, purchase_date, cost, opening_book_value,
                   useful_life_years, residual_value, depreciation_rate, accumulated_depreciation,
                   book_value, location, custodian, description, notes, acquisition_type,
                   payment_method, owner_contributor_name, posted_entry_id, status
            FROM fixed_assets
            WHERE company_key = ?
            ORDER BY asset_name
            """,
            (company_key,),
        ).fetchall()
        if not data:
            st.info("No fixed assets registered yet.")
            return

        df = pd.DataFrame(
            data,
            columns=[
                "ID",
                "Asset Name",
                "Category",
                "Purchase Date",
                "Cost (GHS)",
                "Opening Book Value",
                "Useful Life (Years)",
                "Residual Value",
                "Dep. Rate (%)",
                "Accum. Dep.",
                "Current Value",
                "Location",
                "Custodian",
                "Description",
                "Notes",
                "Acquisition Type",
                "Payment Method",
                "Owner / Investor",
                "Posted Entry ID",
                "Status",
            ],
        )
        posted_asset_entry_map = {
            int(asset_id): _get_fixed_asset_posted_entry_id(conn, company_key, int(asset_id))
            for asset_id in df["ID"].tolist()
        }
        st.dataframe(format_currency_dataframe(df), use_container_width=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Assets", len(df))
        col2.metric("Total Cost", format_currency(df["Cost (GHS)"].sum()))
        col3.metric("Total Book Value", format_currency(df["Current Value"].sum()))

        if can_manage_assets:
            selected_asset_key = f"asset_edit_selected_{company_key}"
            delete_asset_key = f"asset_delete_selected_{company_key}"
            for _, asset_row in df.iterrows():
                name_col, edit_col, delete_col = st.columns([4, 1, 1])
                has_posted_acquisition = posted_asset_entry_map.get(int(asset_row["ID"])) is not None
                name_col.caption(
                    f"{asset_row['Asset Name']} | Current {format_currency(asset_row['Current Value'])} | "
                    f"Purchase Date {asset_row['Purchase Date']} | Acquisition {asset_row['Acquisition Type']}"
                )
                if edit_col.button("Edit", key=f"asset_edit_btn_override_{company_key}_{int(asset_row['ID'])}"):
                    st.session_state[selected_asset_key] = int(asset_row["ID"])
                if delete_col.button("Delete Record", key=f"asset_delete_btn_override_{company_key}_{int(asset_row['ID'])}"):
                    if has_posted_acquisition:
                        st.warning("Posted asset records cannot be financially edited directly. Use reversal/correction workflow.")
                    else:
                        st.session_state[delete_asset_key] = int(asset_row["ID"])

            st.warning("Posted asset records cannot be financially edited directly. Use reversal/correction workflow.")

            if user_has_permission(role, "void_or_reverse_document"):
                reversal_asset_options = [
                    asset_id
                    for asset_id, entry_id in posted_asset_entry_map.items()
                    if entry_id is not None and str(df.loc[df["ID"] == asset_id, "Status"].iloc[0]) != "Reversed"
                ]
                if reversal_asset_options:
                    reversal_asset_id = st.selectbox(
                        "Reverse Posted Asset Acquisition",
                        options=reversal_asset_options,
                        format_func=lambda asset_id: f"Asset #{asset_id} - {df.loc[df['ID'] == asset_id, 'Asset Name'].iloc[0]}",
                        key=f"asset_reversal_select_{company_key}",
                    )
                    reversal_reason = st.text_input("Reversal Reason", key=f"asset_reversal_reason_{company_key}")
                    reversal_confirm = st.checkbox(
                        "Confirm reversal of the posted acquisition journal",
                        key=f"asset_reversal_confirm_{company_key}",
                    )
                    if st.button("Reverse Asset Acquisition", key=f"asset_reverse_btn_{company_key}_{reversal_asset_id}"):
                        if not reversal_confirm or not reversal_reason.strip():
                            st.warning("Enter a reversal reason and confirm before reversing an asset acquisition.")
                        else:
                            reversal_entry_id = posted_asset_entry_map.get(int(reversal_asset_id)) or 0
                            if reversal_entry_id <= 0:
                                st.warning("No posted acquisition journal was found for that asset.")
                            else:
                                reverse_journal_entry(
                                    reversal_entry_id,
                                    created_by=role,
                                    reversal_date=datetime.now().date(),
                                    reason=reversal_reason.strip(),
                                    branch_id=st.session_state.get("active_branch_id"),
                                    conn=conn,
                                )
                                conn.execute(
                                    "UPDATE fixed_assets SET status = 'Reversed' WHERE id = ? AND company_key = ?",
                                    (int(reversal_asset_id), company_key),
                                )
                                conn.commit()
                                log_audit_action(
                                    conn,
                                    company_key,
                                    role,
                                    "Fixed Asset Acquisition Reversed",
                                    "Fixed Assets",
                                    f"Reversed asset acquisition for asset ID {int(reversal_asset_id)}",
                                )
                                st.success("Entry Updated")
                                st.rerun()

            delete_asset_id = st.session_state.get(delete_asset_key)
            if delete_asset_id is not None:
                st.warning("Are you sure you want to permanently delete this item?")
                confirm_col, cancel_col = st.columns(2)
                if confirm_col.button("Delete Record", key=f"asset_delete_confirm_override_{company_key}_{delete_asset_id}"):
                    if _fixed_asset_has_posted_acquisition(conn, company_key, int(delete_asset_id)):
                        _clear_streamlit_state(delete_asset_key)
                        st.warning("Posted asset records cannot be deleted directly. Use reversal/correction workflow.")
                        st.rerun()
                    conn.execute(
                        "DELETE FROM fixed_assets WHERE id = ? AND company_key = ?",
                        (int(delete_asset_id), company_key),
                    )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Fixed Asset Deleted", "Fixed Assets", f"Deleted asset ID {int(delete_asset_id)}")
                    _clear_streamlit_state(delete_asset_key, selected_asset_key)
                    st.session_state[delete_success_key] = True
                    st.rerun()
                if cancel_col.button("Cancel", key=f"asset_delete_cancel_override_{company_key}_{delete_asset_id}"):
                    _clear_streamlit_state(delete_asset_key)
                    st.rerun()

            edit_asset_id = st.session_state.get(selected_asset_key, int(df["ID"].iloc[0]))
            edit_asset_row = df.loc[df["ID"] == edit_asset_id].iloc[0]
            asset_is_posted = _fixed_asset_has_posted_acquisition(conn, company_key, int(edit_asset_id))
            with st.form(f"asset_edit_form_override_{company_key}_{edit_asset_id}", clear_on_submit=True):
                if asset_is_posted:
                    st.warning("Posted asset records cannot be financially edited directly. Use reversal/correction workflow.")
                edit_asset_name = st.text_input("Asset Name", value=str(edit_asset_row["Asset Name"] or ""), disabled=asset_is_posted)
                edit_purchase_date = st.date_input("Purchase Date", value=pd.to_datetime(edit_asset_row["Purchase Date"]).date(), disabled=asset_is_posted)
                edit_cost = st.number_input("Cost (GHS)", min_value=0.0, value=float(edit_asset_row["Cost (GHS)"] or 0.0), disabled=asset_is_posted)
                edit_opening_book = st.number_input("Opening Book Value", min_value=0.0, value=float(edit_asset_row["Opening Book Value"] or 0.0), disabled=asset_is_posted)
                edit_useful_life = st.number_input("Useful Life (Years)", min_value=0.0, value=float(edit_asset_row["Useful Life (Years)"] or 0.0), disabled=asset_is_posted)
                edit_residual_value = st.number_input("Residual Value (GHS)", min_value=0.0, value=float(edit_asset_row["Residual Value"] or 0.0), disabled=asset_is_posted)
                edit_location = st.text_input("Location", value=str(edit_asset_row["Location"] or ""))
                edit_custodian = st.text_input("Custodian", value=str(edit_asset_row["Custodian"] or ""))
                edit_description = st.text_input("Description", value=str(edit_asset_row["Description"] or ""))
                edit_notes = st.text_area("Notes", value=str(edit_asset_row["Notes"] or ""))
                if st.form_submit_button("Update Asset"):
                    if asset_is_posted:
                        conn.execute(
                            """
                            UPDATE fixed_assets
                            SET location = ?, custodian = ?, description = ?, notes = ?
                            WHERE id = ? AND company_key = ?
                            """,
                            (
                                edit_location,
                                edit_custodian,
                                edit_description,
                                edit_notes,
                                int(edit_asset_id),
                                company_key,
                            ),
                        )
                    else:
                        edit_depr_rate = round((100.0 / edit_useful_life), 4) if edit_useful_life > 0 else 0.0
                        conn.execute(
                            """
                            UPDATE fixed_assets
                            SET asset_name = ?, purchase_date = ?, cost = ?, opening_book_value = ?,
                                useful_life_years = ?, residual_value = ?, depreciation_method = 'Straight-line',
                                depreciation_rate = ?, book_value = ?, location = ?, custodian = ?, description = ?, notes = ?
                            WHERE id = ? AND company_key = ?
                            """,
                            (
                                edit_asset_name,
                                edit_purchase_date.isoformat(),
                                edit_cost,
                                edit_opening_book,
                                edit_useful_life,
                                edit_residual_value,
                                edit_depr_rate,
                                edit_opening_book if edit_opening_book > 0 else edit_cost,
                                edit_location,
                                edit_custodian,
                                edit_description,
                                edit_notes,
                                int(edit_asset_id),
                                company_key,
                            ),
                        )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Fixed Asset Updated", "Fixed Assets", f"Updated asset ID {int(edit_asset_id)}")
                    _clear_streamlit_state(selected_asset_key, delete_asset_key)
                    st.success("Entry Updated")
                    st.rerun()
    except Exception as exc:
        st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
    finally:
        if conn:
            conn.close()


# ==========================================
# FINANCIAL INTELLIGENCE / REPORTS
# ==========================================
def _pdf_escape(value):
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(title, lines):
    safe_lines = [title] + [str(line) for line in lines]
    content_lines = ["BT", "/F1 12 Tf", "50 780 Td"]
    first_line = True
    for line in safe_lines:
        if first_line:
            content_lines.append(f"({_pdf_escape(line)}) Tj")
            first_line = False
        else:
            content_lines.append("0 -16 Td")
            content_lines.append(f"({_pdf_escape(line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n")
    objects.append(f"4 0 obj<< /Length {len(stream)} >>stream\n".encode("latin-1") + stream + b"\nendstream endobj\n")
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("latin-1")
    )
    return bytes(pdf)


def _statement_export_buttons(statement_key, title, dataframe, summary_lines):
    excel_bin = get_excel_bin(dataframe)
    pdf_bin = _build_simple_pdf(title, summary_lines + [PRINTABLE_DOCUMENT_FOOTER])
    col1, col2 = st.columns(2)
    with col1:
        if excel_bin:
            st.download_button(
                "📥 Export to Excel",
                data=excel_bin,
                file_name=f"{statement_key}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{statement_key}_excel_export",
            )
    with col2:
        st.download_button(
            "📄 Export to PDF",
            data=pdf_bin,
            file_name=f"{statement_key}.pdf",
            mime="application/pdf",
            key=f"{statement_key}_pdf_export",
        )


def _get_reports_data(conn, company_key):
    inventory_value = conn.execute(
        "SELECT COALESCE(SUM(qty * cost_price), 0) FROM inventory WHERE company_key = ?",
        (company_key,),
    ).fetchone()[0] or 0.0
    asset_value = conn.execute(
        """
        SELECT COALESCE(SUM(COALESCE(book_value, opening_book_value, cost, 0)), 0)
        FROM fixed_assets
        WHERE company_key = ? AND COALESCE(status, 'Active') != 'Disposed'
        """,
        (company_key,),
    ).fetchone()[0] or 0.0
    cash_on_hand = get_account_total(company_key, "Cash", balance_side="debit", conn=conn)
    accounts_payable = conn.execute(
        """
        SELECT COALESCE(SUM(jl.credit - jl.debit), 0)
        FROM journal_entries je
        JOIN journal_lines jl ON jl.entry_id = je.id
        JOIN chart_of_accounts c ON c.id = jl.account_id
        WHERE je.company_key = ?
          AND lower(COALESCE(NULLIF(c.name, ''), NULLIF(c.account_name, ''), '')) LIKE 'accounts payable%'
        """,
        (company_key,),
    ).fetchone()[0] or 0.0
    outstanding_loans = get_account_total(company_key, "Loans Payable", balance_side="credit", conn=conn)
    total_revenue = get_account_total(company_key, "Sales", balance_side="credit", conn=conn)
    total_expenses = get_account_total(company_key, "Expense", balance_side="debit", conn=conn)
    payroll_total = conn.execute(
        """
        SELECT COALESCE(SUM(net_salary), 0)
        FROM payroll
        WHERE company_key = ? AND COALESCE(status, 'Active') != 'Void'
        """,
        (company_key,),
    ).fetchone()[0] or 0.0
    asset_purchases = conn.execute(
        """
        SELECT COALESCE(SUM(cost), 0)
        FROM fixed_assets
        WHERE company_key = ? AND COALESCE(status, 'Active') != 'Void'
        """,
        (company_key,),
    ).fetchone()[0] or 0.0
    asset_sales = get_account_total(company_key, "Fixed Assets", balance_side="credit", conn=conn)
    journal_activity = get_recent_accounting_activity(company_key, limit=200, conn=conn)
    sales_rows = [
        (
            row.get("date"),
            "Sales",
            row.get("description"),
            row.get("activity_type"),
            0.0,
            float(row.get("amount") or 0.0),
        )
        for row in journal_activity
        if any(token in str(row.get("activity_type") or "").lower() for token in ("sale", "invoice", "pos"))
    ]
    expense_rows = [
        (
            row.get("date"),
            "Expense",
            row.get("description"),
            row.get("activity_type"),
            float(row.get("amount") or 0.0),
            0.0,
        )
        for row in journal_activity
        if any(token in str(row.get("description") or "").lower() for token in ("expense", "purchase", "bill"))
    ]
    payroll_rows = conn.execute(
        """
        SELECT printf('%04d-%02d-01', CAST(year AS INTEGER), CAST(month AS INTEGER)) AS date,
               'Payroll' AS source,
               emp_name || ' payroll' AS narration,
               'Payroll' AS ledger,
               net_salary AS debit,
               0 AS credit
        FROM payroll
        WHERE company_key = ? AND COALESCE(status, 'Active') != 'Void'
        """,
        (company_key,),
    ).fetchall()
    return {
        "inventory_value": float(inventory_value),
        "asset_value": float(asset_value),
        "cash_on_hand": float(cash_on_hand),
        "accounts_payable": float(accounts_payable),
        "outstanding_loans": float(outstanding_loans),
        "total_revenue": float(total_revenue),
        "total_expenses": float(total_expenses),
        "payroll_total": float(payroll_total),
        "asset_purchases": float(asset_purchases),
        "asset_sales": float(asset_sales),
        "ledger_rows": [dict(row) for row in (sales_rows + expense_rows + payroll_rows)],
    }

def _show_legacy_analytics_reports(company_key, branch_id=None):
    st.header("📊 Data Analytics")
    branch_id = branch_id if branch_id is not None else st.session_state.get("active_branch_id")
    branch_clause = " AND je.branch_id = ?" if branch_id else ""
    conn = None
    try:
        conn = get_connection()
        trial_rows = conn.execute(
            """
            SELECT
                COALESCE(c.name, c.account_name) AS account_name,
                CASE
                    WHEN COALESCE(c.category, c.account_type) = 'Income' THEN 'Revenue'
                    ELSE COALESCE(c.category, c.account_type)
                END AS category,
                ROUND(SUM(jl.debit), 2) AS debit_total,
                ROUND(SUM(jl.credit), 2) AS credit_total,
                ROUND(
                    CASE
                        WHEN CASE
                            WHEN COALESCE(c.category, c.account_type) = 'Income' THEN 'Revenue'
                            ELSE COALESCE(c.category, c.account_type)
                        END IN ('Asset', 'Expense')
                        THEN SUM(jl.debit - jl.credit)
                        ELSE SUM(jl.credit - jl.debit)
                    END,
                    2
                ) AS balance
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?"""
            + branch_clause +
            """
            GROUP BY c.id, account_name, category
            HAVING ABS(SUM(jl.debit - jl.credit)) > 0.0001 OR ABS(SUM(jl.credit - jl.debit)) > 0.0001
            ORDER BY category, account_name
            """,
            (company_key,) + ((branch_id,) if branch_id else ()),
        ).fetchall()

        balance_sheet_rows = conn.execute(
            """
            SELECT
                CASE
                    WHEN COALESCE(c.category, c.account_type) = 'Income' THEN 'Revenue'
                    ELSE COALESCE(c.category, c.account_type)
                END AS category,
                COALESCE(c.name, c.account_name) AS account_name,
                ROUND(
                    CASE
                        WHEN CASE
                            WHEN COALESCE(c.category, c.account_type) = 'Income' THEN 'Revenue'
                            ELSE COALESCE(c.category, c.account_type)
                        END = 'Asset'
                        THEN SUM(jl.debit - jl.credit)
                        ELSE SUM(jl.credit - jl.debit)
                    END,
                    2
                ) AS amount
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?"""
            + branch_clause +
            """
              AND CASE
                    WHEN COALESCE(c.category, c.account_type) = 'Income' THEN 'Revenue'
                    ELSE COALESCE(c.category, c.account_type)
                  END IN ('Asset', 'Liability', 'Equity')
            GROUP BY c.id, category, account_name
            ORDER BY CASE category WHEN 'Asset' THEN 1 WHEN 'Liability' THEN 2 ELSE 3 END, account_name
            """,
            (company_key,) + ((branch_id,) if branch_id else ()),
        ).fetchall()

        pnl_rows = conn.execute(
            """
            SELECT
                CASE
                    WHEN COALESCE(c.category, c.account_type) = 'Income' THEN 'Revenue'
                    ELSE COALESCE(c.category, c.account_type)
                END AS category,
                COALESCE(c.name, c.account_name) AS account_name,
                ROUND(
                    CASE
                        WHEN CASE
                            WHEN COALESCE(c.category, c.account_type) = 'Income' THEN 'Revenue'
                            ELSE COALESCE(c.category, c.account_type)
                        END = 'Revenue'
                        THEN SUM(jl.credit - jl.debit)
                        ELSE SUM(jl.debit - jl.credit)
                    END,
                    2
                ) AS amount
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?"""
            + branch_clause +
            """
              AND CASE
                    WHEN COALESCE(c.category, c.account_type) = 'Income' THEN 'Revenue'
                    ELSE COALESCE(c.category, c.account_type)
                  END IN ('Revenue', 'Expense')
            GROUP BY c.id, category, account_name
            ORDER BY CASE category WHEN 'Revenue' THEN 1 ELSE 2 END, account_name
            """,
            (company_key,) + ((branch_id,) if branch_id else ()),
        ).fetchall()
    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))
        return
    finally:
        if conn:
            conn.close()

    trial_balance_df = pd.DataFrame(trial_rows, columns=["Account", "Category", "Debit (GHS)", "Credit (GHS)", "Balance (GHS)"])
    balance_sheet_df = pd.DataFrame(balance_sheet_rows, columns=["Category", "Account", "Amount (GHS)"])
    profit_loss_df = pd.DataFrame(pnl_rows, columns=["Category", "Account", "Amount (GHS)"])
    if not balance_sheet_df.empty:
        balance_sheet_df = balance_sheet_df[balance_sheet_df["Amount (GHS)"].abs() > 0.0001].reset_index(drop=True)
    if not profit_loss_df.empty:
        profit_loss_df = profit_loss_df[profit_loss_df["Amount (GHS)"].abs() > 0.0001].reset_index(drop=True)

    total_assets = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Asset", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    total_liabilities = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Liability", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    total_equity = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Equity", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    total_revenue = float(profit_loss_df.loc[profit_loss_df["Category"] == "Revenue", "Amount (GHS)"].sum()) if not profit_loss_df.empty else 0.0
    total_expenses = float(profit_loss_df.loc[profit_loss_df["Category"] == "Expense", "Amount (GHS)"].sum()) if not profit_loss_df.empty else 0.0
    net_profit = total_revenue - total_expenses

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Trial Balance Accounts", str(len(trial_balance_df)))
    metric_col2.metric("Total Assets", f"GHS {total_assets:,.2f}")
    metric_col3.metric("Net Profit", f"GHS {net_profit:,.2f}")

    tabs = st.tabs(["Trial Balance", "Balance Sheet", "Profit & Loss"])

    with tabs[0]:
        if trial_balance_df.empty:
            st.info("No posted journal balances were found for this company.")
        else:
            st.dataframe(format_currency_dataframe(trial_balance_df), use_container_width=True)
        _statement_export_buttons(
            "trial_balance",
            "Trial Balance",
            trial_balance_df if not trial_balance_df.empty else pd.DataFrame(columns=["Account", "Category", "Debit (GHS)", "Credit (GHS)", "Balance (GHS)"]),
            [
                f"Accounts with balances: {len(trial_balance_df)}",
                f"Total debits: GHS {float(trial_balance_df['Debit (GHS)'].sum()) if not trial_balance_df.empty else 0.0:,.2f}",
                f"Total credits: GHS {float(trial_balance_df['Credit (GHS)'].sum()) if not trial_balance_df.empty else 0.0:,.2f}",
            ],
        )

    with tabs[1]:
        if balance_sheet_df.empty:
            st.info("No balance sheet activity has been posted yet.")
        else:
            st.dataframe(format_currency_dataframe(balance_sheet_df), use_container_width=True)
        _statement_export_buttons(
            "balance_sheet",
            "Balance Sheet",
            balance_sheet_df if not balance_sheet_df.empty else pd.DataFrame(columns=["Category", "Account", "Amount (GHS)"]),
            [
                f"Total Assets: GHS {total_assets:,.2f}",
                f"Total Liabilities: GHS {total_liabilities:,.2f}",
                f"Total Equity: GHS {total_equity:,.2f}",
            ],
        )

    with tabs[2]:
        if profit_loss_df.empty:
            st.info("No profit and loss activity has been posted yet.")
        else:
            st.dataframe(format_currency_dataframe(profit_loss_df), use_container_width=True)
        _statement_export_buttons(
            "profit_and_loss",
            "Profit and Loss",
            profit_loss_df if not profit_loss_df.empty else pd.DataFrame(columns=["Category", "Account", "Amount (GHS)"]),
            [
                f"Revenue: GHS {total_revenue:,.2f}",
                f"Expenses: GHS {total_expenses:,.2f}",
                f"Net Profit: GHS {net_profit:,.2f}",
            ],
        )


# Final UI-safe reports override.
def show_reports(company_key, branch_id=None):
    """Route report navigation to the IFRS financial reporting suite."""
    from financials import show_financial_reports, show_ledger_viewer, show_record_transaction

    render_ui_standard_styles()
    role = st.session_state.get("user", {}).get("role", "System")
    if not require_permission(role, "view_reports", action_label="view reports", company_key=company_key, branch_id=branch_id):
        return
    if branch_id is not None:
        st.session_state.active_branch_id = branch_id
    tabs = st.tabs(["📊 Financial Statements", "📚 Ledger", "🧾 Record Transaction"])
    with tabs[0]:
        show_financial_reports(company_key, role)
    with tabs[1]:
        show_ledger_viewer(company_key, st.session_state.get("user", {}).get("role"))
    with tabs[2]:
        show_record_transaction(company_key, st.session_state.get("user", {}).get("role", "System"))


def _dashboard_pos_branch_sql(branch_id, alias=""):
    prefix = f"{alias}." if alias else ""
    if branch_id:
        return f" AND COALESCE({prefix}branch_id, '') = ? ", [str(branch_id)]
    return "", []


def _dashboard_stock_movement_branch_sql(conn, branch_id):
    try:
        movement_columns = {row[1] for row in conn.execute("PRAGMA table_info(stock_movements)").fetchall()}
    except Exception:
        movement_columns = set()
    if branch_id and "branch_id" in movement_columns:
        return " AND COALESCE(branch_id, '') = ? ", [str(branch_id)]
    return "", []


def _dashboard_branch_ledger_balance(conn, company_key, branch_id, account_name_patterns):
    if not branch_id:
        return 0.0
    pattern_sql = " OR ".join(
        [
            "lower(COALESCE(NULLIF(c.name, ''), NULLIF(c.account_name, ''), '')) LIKE ?"
            for _ in account_name_patterns
        ]
    )
    params = [company_key, str(branch_id)] + [f"%{pattern.lower()}%" for pattern in account_name_patterns]
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(jl.debit - jl.credit), 0) AS balance
        FROM journal_entries je
        JOIN journal_lines jl ON jl.entry_id = je.id
        JOIN chart_of_accounts c ON c.id = jl.account_id
        WHERE je.company_key = ?
          AND COALESCE(je.branch_id, '') = ?
          AND ({pattern_sql})
          AND COALESCE(je.is_voided, 0) = 0
          AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """,
        tuple(params),
    ).fetchone()
    return float(row["balance"] or 0.0) if row else 0.0


def _fetch_dashboard_kpi_snapshot(conn, company_key, branch_id=None):
    today = datetime.now().date()
    month_key = today.strftime("%Y-%m")
    month_start = today.replace(day=1)
    branch_sql, branch_params = _dashboard_pos_branch_sql(branch_id)
    inv_branch_sql, inv_branch_params = "", []
    try:
        inventory_columns = {row[1] for row in conn.execute("PRAGMA table_info(inventory)").fetchall()}
        if branch_id and "branch_id" in inventory_columns:
            inv_branch_sql = " AND COALESCE(branch_id, '') = ? "
            inv_branch_params = [str(branch_id)]
    except Exception:
        pass

    inv_row = conn.execute(
        f"SELECT COALESCE(SUM(qty * cost_price), 0) AS total FROM inventory WHERE company_key = ?{inv_branch_sql}",
        tuple([company_key, *inv_branch_params]),
    ).fetchone()
    inventory_value = float(inv_row["total"] or 0.0) if inv_row else 0.0

    inventory_rows = conn.execute(
        f"SELECT qty, min_stock_level FROM inventory WHERE company_key = ?{inv_branch_sql}",
        tuple([company_key, *inv_branch_params]),
    ).fetchall()
    low_stock_count = sum(
        1
        for row in inventory_rows
        if _get_inventory_stock_status(row["qty"], row["min_stock_level"]) in {"LOW STOCK", "OUT OF STOCK"}
    )

    month_sales = float(get_month_sales_total(company_key, year_month=month_key, branch_id=branch_id, conn=conn) or 0.0)
    today_sales = 0.0
    try:
        ensure_pos_sales_schema(conn)
        pos_today_sql = f"""
            SELECT COALESCE(SUM(grand_total), 0) AS total
            FROM pos_sales
            WHERE company_key = ?
              AND date(sale_date) = date(?)
              {branch_sql}
        """
        pos_today_params = [company_key, today.isoformat(), *branch_params]
        pos_today_row = conn.execute(pos_today_sql, tuple(pos_today_params)).fetchone()
        today_sales = float(pos_today_row["total"] or 0.0) if pos_today_row else 0.0
    except Exception:
        today_sales = 0.0
    if today_sales <= 0:
        journal_today_sql = """
            SELECT COALESCE(SUM(jl.credit), 0) AS sales_total
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND date(je.date) = date(?)
              AND lower(COALESCE(NULLIF(c.name, ''), NULLIF(c.account_name, ''), '')) LIKE 'sales%'
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """
        journal_params = [company_key, today.isoformat()]
        if branch_id:
            journal_today_sql += " AND je.branch_id = ?"
            journal_params.append(str(branch_id))
        journal_row = conn.execute(journal_today_sql, tuple(journal_params)).fetchone()
        today_sales = float(journal_row["sales_total"] or 0.0) if journal_row else 0.0

    gross_profit = 0.0
    try:
        income_rows = generate_income_statement(
            company_key,
            month_start.isoformat(),
            today.isoformat(),
            branch_id=branch_id,
        )
        gross_profit = float(
            next(
                (row["amount"] for row in income_rows if str(row.get("account_name") or "") == "Gross Profit"),
                0.0,
            )
        )
    except Exception:
        gross_profit = 0.0

    if branch_id:
        receivables_total = round(
            max(
                _dashboard_branch_ledger_balance(
                    conn,
                    company_key,
                    branch_id,
                    ("receivable", "debtor", "trade debtor"),
                ),
                0.0,
            ),
            2,
        )
        payables_total = round(
            max(
                -_dashboard_branch_ledger_balance(
                    conn,
                    company_key,
                    branch_id,
                    ("payable", "creditor", "trade creditor"),
                ),
                0.0,
            ),
            2,
        )
    else:
        receivables_total = round(
            sum(float(row.get("balance") or 0.0) for row in get_customer_balances(company_key, conn=conn) if float(row.get("balance") or 0.0) > 0),
            2,
        )
        payables_total = round(
            sum(float(row.get("balance") or 0.0) for row in get_supplier_balances(company_key, conn=conn) if float(row.get("balance") or 0.0) > 0),
            2,
        )

    cash_bank_row = conn.execute(
        """
        SELECT COALESCE(SUM(jl.debit - jl.credit), 0) AS balance
        FROM journal_entries je
        JOIN journal_lines jl ON jl.entry_id = je.id
        JOIN chart_of_accounts c ON c.id = jl.account_id
        WHERE je.company_key = ?
          AND lower(COALESCE(NULLIF(c.type, ''), NULLIF(c.account_type, ''), NULLIF(c.category, ''), '')) = 'asset'
          AND (
              lower(COALESCE(NULLIF(c.name, ''), NULLIF(c.account_name, ''), '')) LIKE 'cash%'
              OR lower(COALESCE(NULLIF(c.name, ''), NULLIF(c.account_name, ''), '')) LIKE 'bank%'
              OR lower(COALESCE(NULLIF(c.name, ''), NULLIF(c.account_name, ''), '')) LIKE 'mobile money%'
          )
          AND COALESCE(je.is_voided, 0) = 0
          AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """
        + (" AND je.branch_id = ?" if branch_id else ""),
        tuple([company_key, str(branch_id)] if branch_id else [company_key]),
    ).fetchone()
    cash_bank_balance = float(cash_bank_row["balance"] or 0.0) if cash_bank_row else 0.0

    return {
        "today_sales": round(today_sales, 2),
        "month_sales": round(month_sales, 2),
        "gross_profit": round(gross_profit, 2),
        "inventory_value": round(inventory_value, 2),
        "low_stock_count": int(low_stock_count),
        "receivables_total": receivables_total,
        "payables_total": payables_total,
        "cash_bank_balance": round(cash_bank_balance, 2),
    }


def _fetch_dashboard_sales_analytics(conn, company_key, branch_id=None):
    branch_sql, branch_params = _dashboard_pos_branch_sql(branch_id, alias="ps")
    analytics = {
        "daily_sales": [],
        "top_items": [],
        "payment_methods": [],
        "cashier_sales": [],
        "branch_sales": [],
        "has_pos_data": False,
    }
    try:
        ensure_pos_sales_schema(conn)
        window_start = (datetime.now().date() - timedelta(days=29)).isoformat()
        daily_rows = conn.execute(
            f"""
            SELECT sale_date AS sale_day, COALESCE(SUM(grand_total), 0) AS sales_total
            FROM pos_sales ps
            WHERE company_key = ?
              AND date(sale_date) >= date(?)
              {branch_sql}
            GROUP BY sale_date
            ORDER BY sale_date
            """,
            tuple([company_key, window_start, *branch_params]),
        ).fetchall()
        analytics["daily_sales"] = [
            {"sale_day": str(row["sale_day"]), "sales_total": float(row["sales_total"] or 0.0)} for row in daily_rows
        ]
        top_rows = conn.execute(
            f"""
            SELECT psl.item_name AS item_name,
                   COALESCE(SUM(psl.qty_sold), 0) AS qty_sold,
                   COALESCE(SUM(psl.line_total), 0) AS revenue
            FROM pos_sale_lines psl
            JOIN pos_sales ps ON ps.id = psl.pos_sale_id AND ps.company_key = psl.company_key
            WHERE ps.company_key = ?
              AND date(ps.sale_date) >= date(?)
              {branch_sql}
            GROUP BY psl.item_name
            ORDER BY qty_sold DESC, revenue DESC
            LIMIT 10
            """,
            tuple([company_key, window_start, *branch_params]),
        ).fetchall()
        analytics["top_items"] = [
            {
                "item_name": str(row["item_name"] or "Item"),
                "qty_sold": float(row["qty_sold"] or 0.0),
                "revenue": float(row["revenue"] or 0.0),
            }
            for row in top_rows
        ]
        payment_rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(payment_method, ''), 'Unknown') AS payment_method,
                   COALESCE(SUM(grand_total), 0) AS sales_total,
                   COUNT(*) AS sale_count
            FROM pos_sales ps
            WHERE company_key = ?
              AND date(sale_date) >= date(?)
              {branch_sql}
            GROUP BY COALESCE(NULLIF(payment_method, ''), 'Unknown')
            ORDER BY sales_total DESC
            """,
            tuple([company_key, window_start, *branch_params]),
        ).fetchall()
        analytics["payment_methods"] = [
            {
                "payment_method": str(row["payment_method"]),
                "sales_total": float(row["sales_total"] or 0.0),
                "sale_count": int(row["sale_count"] or 0),
            }
            for row in payment_rows
        ]
        cashier_rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(cashier, ''), 'Unknown') AS cashier,
                   COALESCE(SUM(grand_total), 0) AS sales_total
            FROM pos_sales ps
            WHERE company_key = ?
              AND date(sale_date) >= date(?)
              {branch_sql}
            GROUP BY COALESCE(NULLIF(cashier, ''), 'Unknown')
            ORDER BY sales_total DESC
            LIMIT 10
            """,
            tuple([company_key, window_start, *branch_params]),
        ).fetchall()
        analytics["cashier_sales"] = [
            {"cashier": str(row["cashier"]), "sales_total": float(row["sales_total"] or 0.0)} for row in cashier_rows
        ]
        branch_filter_sql, branch_filter_params = _dashboard_pos_branch_sql(branch_id)
        branch_rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(branch_id, ''), 'Unassigned') AS branch_id,
                   COALESCE(SUM(grand_total), 0) AS sales_total
            FROM pos_sales
            WHERE company_key = ?
              AND date(sale_date) >= date(?)
              {branch_filter_sql}
            GROUP BY COALESCE(NULLIF(branch_id, ''), 'Unassigned')
            ORDER BY sales_total DESC
            """,
            tuple([company_key, window_start, *branch_filter_params]),
        ).fetchall()
        analytics["branch_sales"] = [
            {"branch_id": str(row["branch_id"]), "sales_total": float(row["sales_total"] or 0.0)} for row in branch_rows
        ]
        analytics["has_pos_data"] = bool(
            analytics["daily_sales"] or analytics["top_items"] or analytics["payment_methods"]
        )
    except Exception as exc:
        logger.debug("Dashboard POS analytics skipped: %s", sanitize_error_message(exc))
    return analytics


def _fetch_dashboard_inventory_insights(conn, company_key, branch_id=None):
    window_start = (datetime.now().date() - timedelta(days=29)).isoformat()
    branch_sql, branch_params = _dashboard_pos_branch_sql(branch_id, alias="ps")
    inv_branch_sql, inv_branch_params = "", []
    try:
        inventory_columns = {row[1] for row in conn.execute("PRAGMA table_info(inventory)").fetchall()}
        if branch_id and "branch_id" in inventory_columns:
            inv_branch_sql = " AND COALESCE(branch_id, '') = ? "
            inv_branch_params = [str(branch_id)]
    except Exception:
        pass
    movement_branch_sql, movement_branch_params = _dashboard_stock_movement_branch_sql(conn, branch_id)
    insights = {
        "fast_moving": [],
        "dead_stock": [],
        "expiring_summary": {"expiring_soon": 0, "expired": 0, "invalid": 0},
        "most_profitable": [],
        "movement_trend": [],
    }
    try:
        ensure_pos_sales_schema(conn)
        fast_rows = conn.execute(
            f"""
            SELECT psl.item_name AS item_name, COALESCE(SUM(psl.qty_sold), 0) AS qty_sold
            FROM pos_sale_lines psl
            JOIN pos_sales ps ON ps.id = psl.pos_sale_id AND ps.company_key = psl.company_key
            WHERE ps.company_key = ? AND date(ps.sale_date) >= date(?)
              {branch_sql}
            GROUP BY psl.item_name
            HAVING qty_sold > 0
            ORDER BY qty_sold DESC
            LIMIT 8
            """,
            tuple([company_key, window_start, *branch_params]),
        ).fetchall()
        insights["fast_moving"] = [
            {"item_name": str(row["item_name"]), "qty_sold": float(row["qty_sold"] or 0.0)} for row in fast_rows
        ]
        profitable_rows = conn.execute(
            f"""
            SELECT psl.item_name AS item_name,
                   COALESCE(SUM(psl.line_total), 0) AS revenue,
                   COALESCE(SUM(psl.qty_sold * COALESCE(psl.cost_price, 0)), 0) AS cost_total
            FROM pos_sale_lines psl
            JOIN pos_sales ps ON ps.id = psl.pos_sale_id AND ps.company_key = psl.company_key
            WHERE ps.company_key = ? AND date(ps.sale_date) >= date(?)
              {branch_sql}
            GROUP BY psl.item_name
            ORDER BY (revenue - cost_total) DESC
            LIMIT 8
            """,
            tuple([company_key, window_start, *branch_params]),
        ).fetchall()
        insights["most_profitable"] = [
            {
                "item_name": str(row["item_name"]),
                "profit": round(float(row["revenue"] or 0.0) - float(row["cost_total"] or 0.0), 2),
            }
            for row in profitable_rows
        ]
    except Exception:
        pass

    inventory_rows = conn.execute(
        f"""
        SELECT item_name, qty, expiry_date
        FROM inventory
        WHERE company_key = ?
        {inv_branch_sql}
        """,
        tuple([company_key, *inv_branch_params]),
    ).fetchall()
    sold_names = set()
    try:
        sold_rows = conn.execute(
            f"""
            SELECT DISTINCT psl.item_name
            FROM pos_sale_lines psl
            JOIN pos_sales ps ON ps.id = psl.pos_sale_id AND ps.company_key = psl.company_key
            WHERE ps.company_key = ?
              AND date(ps.sale_date) >= date(?)
              {branch_sql}
            """,
            tuple([company_key, (datetime.now().date() - timedelta(days=90)).isoformat(), *branch_params]),
        ).fetchall()
        sold_names = {str(row["item_name"]) for row in sold_rows}
    except Exception:
        pass

    dead_stock_rows = []
    for row in inventory_rows:
        qty = float(row["qty"] or 0.0)
        if qty <= 0:
            continue
        item_name = str(row["item_name"] or "")
        if item_name not in sold_names:
            dead_stock_rows.append({"item_name": item_name, "qty": qty})
    insights["dead_stock"] = sorted(dead_stock_rows, key=lambda item: item["qty"], reverse=True)[:8]

    for row in inventory_rows:
        expiry_status = _get_inventory_expiry_status(row["expiry_date"])
        if expiry_status == "EXPIRING SOON":
            insights["expiring_summary"]["expiring_soon"] += 1
        elif expiry_status == "EXPIRED":
            insights["expiring_summary"]["expired"] += 1
        elif expiry_status == "INVALID":
            insights["expiring_summary"]["invalid"] += 1

    try:
        ensure_stock_movements_schema_integrity(conn)
        movement_rows = conn.execute(
            f"""
            SELECT date(created_at) AS movement_day,
                   COALESCE(SUM(
                       CASE
                           WHEN upper(COALESCE(movement_type, '')) IN ('STOCK_IN', 'IMPORT', 'POS_RETURN') THEN quantity
                           WHEN upper(COALESCE(movement_type, '')) IN ('STOCK_OUT', 'POS_SALE') THEN -quantity
                           ELSE 0
                       END
                   ), 0) AS net_qty
            FROM stock_movements
            WHERE company_key = ?
              AND date(created_at) >= date(?)
              {movement_branch_sql}
            GROUP BY date(created_at)
            ORDER BY movement_day
            """,
            tuple([company_key, window_start, *movement_branch_params]),
        ).fetchall()
        insights["movement_trend"] = [
            {"movement_day": str(row["movement_day"]), "net_qty": float(row["net_qty"] or 0.0)} for row in movement_rows
        ]
    except Exception:
        pass
    return insights


def _fetch_dashboard_receivable_payable_health(company_key, branch_id=None):
    as_of_date = datetime.now().date()
    ar_rows = get_ar_aging_report(company_key, as_of_date=as_of_date) or []
    ap_rows = get_ap_aging_report(company_key, as_of_date=as_of_date) or []
    if branch_id:
        branch_key = str(branch_id)
        ar_rows = [row for row in ar_rows if str(row.get("branch_id") or "") == branch_key]
        ap_rows = [row for row in ap_rows if str(row.get("branch_id") or "") == branch_key]
    ar_overdue = [row for row in ar_rows if int(row.get("days_overdue") or 0) > 0]
    ap_overdue = [row for row in ap_rows if int(row.get("days_overdue") or 0) > 0]

    def _bucket_summary(rows):
        summary = {"Current": 0.0, "1-30 Days": 0.0, "31-60 Days": 0.0, "61-90 Days": 0.0, "90+ Days": 0.0}
        for row in rows:
            bucket = str(row.get("bucket") or "Current")
            summary[bucket] = round(summary.get(bucket, 0.0) + float(row.get("remaining_balance") or row.get("balance") or 0.0), 2)
        return summary

    debtor_totals = {}
    for row in ar_rows:
        name = str(row.get("customer_name") or "Customer")
        debtor_totals[name] = round(debtor_totals.get(name, 0.0) + float(row.get("remaining_balance") or 0.0), 2)
    creditor_totals = {}
    for row in ap_rows:
        name = str(row.get("supplier_name") or "Supplier")
        creditor_totals[name] = round(creditor_totals.get(name, 0.0) + float(row.get("remaining_balance") or 0.0), 2)

    return {
        "ar_overdue_count": len(ar_overdue),
        "ar_overdue_total": round(sum(float(row.get("remaining_balance") or 0.0) for row in ar_overdue), 2),
        "ap_overdue_count": len(ap_overdue),
        "ap_overdue_total": round(sum(float(row.get("remaining_balance") or 0.0) for row in ap_overdue), 2),
        "ar_aging": _bucket_summary(ar_rows),
        "ap_aging": _bucket_summary(ap_rows),
        "top_debtors": sorted(
            [{"name": name, "balance": balance} for name, balance in debtor_totals.items() if balance > 0],
            key=lambda item: item["balance"],
            reverse=True,
        )[:5],
        "top_creditors": sorted(
            [{"name": name, "balance": balance} for name, balance in creditor_totals.items() if balance > 0],
            key=lambda item: item["balance"],
            reverse=True,
        )[:5],
    }


@st.cache_data(ttl=120, show_spinner=False)
def _cached_dashboard_analytics_bundle(company_key, branch_id_key, period_key):
    conn = get_connection()
    try:
        branch_id = branch_id_key or None
        kpis = _fetch_dashboard_kpi_snapshot(conn, company_key, branch_id=branch_id)
        sales = _fetch_dashboard_sales_analytics(conn, company_key, branch_id=branch_id)
        inventory = _fetch_dashboard_inventory_insights(conn, company_key, branch_id=branch_id)
        return {
            "kpis": kpis,
            "sales": sales,
            "inventory": inventory,
            "receivable_payable": _fetch_dashboard_receivable_payable_health(company_key, branch_id=branch_id),
        }
    finally:
        conn.close()


def _dashboard_chart_has_data(chart_df):
    if chart_df is None or chart_df.empty:
        return False
    numeric_columns = chart_df.select_dtypes(include="number")
    if numeric_columns.empty:
        return len(chart_df.index) > 0
    return bool((numeric_columns.fillna(0).abs().sum() > 0).any())


def _render_dashboard_empty_state(message, hint=None):
    hint_html = (
        f'<div class="dashboard-empty-hint">{html.escape(str(hint))}</div>'
        if hint
        else ""
    )
    st.markdown(
        (
            f'<div class="dashboard-empty-state">{html.escape(str(message or "No data available yet."))}'
            f"{hint_html}</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_dashboard_chart_card(
    title,
    caption,
    chart_df,
    chart_kind="bar",
    empty_message=None,
    empty_hint=None,
):
    st.markdown('<div class="eka-card dashboard-chart-card">', unsafe_allow_html=True)
    st.markdown(f"**{title}**")
    if caption:
        st.caption(caption)
    if not _dashboard_chart_has_data(chart_df):
        _render_dashboard_empty_state(
            empty_message or "No data available for this view yet.",
            empty_hint,
        )
    else:
        try:
            if chart_kind == "line":
                st.line_chart(chart_df, use_container_width=True)
            else:
                st.bar_chart(chart_df, use_container_width=True)
        except Exception:
            _render_dashboard_empty_state(
                empty_message or "Chart could not be rendered for the current dataset.",
                empty_hint,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_dashboard_balance_card(title, rows, *, empty_message, empty_hint=None, column_labels=None):
    st.markdown('<div class="eka-card dashboard-chart-card">', unsafe_allow_html=True)
    st.markdown(f"**{title}**")
    if rows:
        display_df = pd.DataFrame(rows)
        if column_labels:
            display_df = display_df.rename(columns=column_labels)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        _render_dashboard_empty_state(empty_message, empty_hint)
    st.markdown("</div>", unsafe_allow_html=True)


def show_dashboard(company_key, company_name, role):
    """Executive operational dashboard with cached analytics snapshots."""
    render_ui_standard_styles()
    page_header("📊 Enterprise Dashboard", f"Operational intelligence for {company_name}")
    enforce_branch_session_lock(st.session_state.get("user"))
    active_branch_id = resolve_effective_branch_id(st.session_state.get("user"))
    if active_branch_id:
        branch_label = active_branch_id
        try:
            conn = get_connection()
            branch_row = conn.execute(
                "SELECT branch_name FROM branches WHERE company_key = ? AND branch_id = ?",
                (company_key, active_branch_id),
            ).fetchone()
            conn.close()
            if branch_row and branch_row[0]:
                branch_label = f"{branch_row[0]} ({active_branch_id})"
        except Exception:
            pass
        st.caption(f"Branch context: {branch_label}")
    elif is_branch_scoped_user(st.session_state.get("user")):
        st.warning("No branch is assigned to this user. Contact your administrator.")

    if role == "Demo":
        st.markdown('<div class="dashboard-kpi-grid">', unsafe_allow_html=True)
        demo_row1 = st.columns(4)
        demo_row1[0].metric("Today Sales", format_currency(1250.0))
        demo_row1[1].metric("This Month Sales", format_currency(15000.0))
        demo_row1[2].metric("Gross Profit", format_currency(6200.0))
        demo_row1[3].metric("Inventory Value", format_currency(25000.0))
        demo_row2 = st.columns(4)
        demo_row2[0].metric("Low Stock Count", "3")
        demo_row2[1].metric("Outstanding Receivables", format_currency(4800.0))
        demo_row2[2].metric("Outstanding Payables", format_currency(2100.0))
        demo_row2[3].metric("Cash/Bank Balance", format_currency(18250.0))
        st.markdown("</div>", unsafe_allow_html=True)
        st.info("Demo mode shows sample executive metrics. Live analytics are available in company workspaces.")
        return

    try:
        analytics_bundle = _cached_dashboard_analytics_bundle(
            company_key,
            str(active_branch_id or ""),
            datetime.now().strftime("%Y-%m-%d"),
        )
        kpis = analytics_bundle.get("kpis") or {}
        sales = analytics_bundle.get("sales") or {}
        inventory = analytics_bundle.get("inventory") or {}
        receivable_payable = analytics_bundle.get("receivable_payable") or {}

        st.markdown('<div class="dashboard-section-title">Executive KPIs</div>', unsafe_allow_html=True)
        st.markdown('<div class="dashboard-kpi-grid">', unsafe_allow_html=True)
        kpi_row1 = st.columns(4)
        kpi_row1[0].metric("Today Sales", format_currency(kpis.get("today_sales", 0.0)))
        kpi_row1[1].metric("This Month Sales", format_currency(kpis.get("month_sales", 0.0)))
        kpi_row1[2].metric("Gross Profit (MTD)", format_currency(kpis.get("gross_profit", 0.0)))
        kpi_row1[3].metric("Inventory Value", format_currency(kpis.get("inventory_value", 0.0)))
        kpi_row2 = st.columns(4)
        kpi_row2[0].metric("Low Stock Count", str(kpis.get("low_stock_count", 0)))
        kpi_row2[1].metric("Outstanding Receivables", format_currency(kpis.get("receivables_total", 0.0)))
        kpi_row2[2].metric("Outstanding Payables", format_currency(kpis.get("payables_total", 0.0)))
        kpi_row2[3].metric("Cash/Bank Balance", format_currency(kpis.get("cash_bank_balance", 0.0)))
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="dashboard-section-title">Sales Analytics</div>', unsafe_allow_html=True)
        sales_col1, sales_col2 = st.columns(2)
        daily_sales_df = pd.DataFrame(sales.get("daily_sales") or [])
        if not daily_sales_df.empty:
            daily_sales_df = daily_sales_df.set_index("sale_day")[["sales_total"]]
            daily_sales_df.columns = ["Sales"]
        with sales_col1:
            _render_dashboard_chart_card(
                "Daily Sales Trend",
                "Last 30 days from POS sales.",
                daily_sales_df,
                chart_kind="line",
                empty_message="No sales recorded in the selected period.",
                empty_hint="Complete POS sales to populate this trend.",
            )
        top_items_df = pd.DataFrame(sales.get("top_items") or [])
        if not top_items_df.empty:
            top_items_df = top_items_df.set_index("item_name")[["qty_sold"]]
            top_items_df.columns = ["Qty Sold"]
        with sales_col2:
            _render_dashboard_chart_card(
                "Top Selling Items",
                "Last 30 days by quantity sold.",
                top_items_df,
                empty_message="No sales activity available yet.",
                empty_hint="Top sellers appear after items are sold through POS.",
            )

        sales_col3, sales_col4 = st.columns(2)
        payment_df = pd.DataFrame(sales.get("payment_methods") or [])
        if not payment_df.empty:
            payment_df = payment_df.set_index("payment_method")[["sales_total"]]
            payment_df.columns = ["Sales"]
        with sales_col3:
            _render_dashboard_chart_card(
                "Payment Method Breakdown",
                "Last 30 days POS totals.",
                payment_df,
                empty_message="No completed POS payments yet.",
                empty_hint="Payment mix is available after checkout activity is recorded.",
            )
        cashier_df = pd.DataFrame(sales.get("cashier_sales") or [])
        if not cashier_df.empty:
            cashier_df = cashier_df.set_index("cashier")[["sales_total"]]
            cashier_df.columns = ["Sales"]
        with sales_col4:
            _render_dashboard_chart_card(
                "Sales by Cashier",
                "Last 30 days POS totals.",
                cashier_df,
                empty_message="No cashier sales available yet.",
                empty_hint="Cashier totals appear once POS sales are posted.",
            )

        branch_df = pd.DataFrame(sales.get("branch_sales") or [])
        branch_chart_df = pd.DataFrame()
        branch_empty_message = "No completed POS payments yet."
        branch_empty_hint = "Branch analytics use posted POS sales from the last 30 days."
        if len(branch_df) > 1:
            branch_chart_df = branch_df.set_index("branch_id")[["sales_total"]]
            branch_chart_df.columns = ["Sales"]
        elif len(branch_df) == 1:
            branch_empty_message = "Branch comparison requires sales from multiple branches."
            branch_empty_hint = "Record sales in more than one branch to compare performance."
        _render_dashboard_chart_card(
            "Branch Comparison",
            "Last 30 days POS totals by branch.",
            branch_chart_df,
            empty_message=branch_empty_message,
            empty_hint=branch_empty_hint,
        )

        st.markdown('<div class="dashboard-section-title">Inventory Insights</div>', unsafe_allow_html=True)
        inv_col1, inv_col2 = st.columns(2)
        fast_df = pd.DataFrame(inventory.get("fast_moving") or [])
        if not fast_df.empty:
            fast_df = fast_df.set_index("item_name")[["qty_sold"]]
        with inv_col1:
            _render_dashboard_chart_card(
                "Fast-Moving Items",
                "Highest units sold in the last 30 days.",
                fast_df,
                empty_message="No sales activity available yet.",
                empty_hint="Fast movers are ranked from recent POS line sales.",
            )
        dead_df = pd.DataFrame(inventory.get("dead_stock") or [])
        if not dead_df.empty:
            dead_df = dead_df.set_index("item_name")[["qty"]]
            dead_df.columns = ["On Hand Qty"]
        with inv_col2:
            _render_dashboard_chart_card(
                "Dead Stock",
                "In stock but no POS sales in the last 90 days.",
                dead_df,
                empty_message="No dead stock detected.",
                empty_hint="Items with on-hand stock and no recent POS activity appear here.",
            )

        inv_col3, inv_col4 = st.columns(2)
        profit_df = pd.DataFrame(inventory.get("most_profitable") or [])
        if not profit_df.empty:
            profit_df = profit_df.set_index("item_name")[["profit"]]
        with inv_col3:
            _render_dashboard_chart_card(
                "Most Profitable Items",
                "Estimated POS margin last 30 days.",
                profit_df,
                empty_message="No sales activity available yet.",
                empty_hint="Profitability is estimated from POS revenue and cost price.",
            )
        movement_df = pd.DataFrame(inventory.get("movement_trend") or [])
        if not movement_df.empty:
            movement_df = movement_df.set_index("movement_day")[["net_qty"]]
            movement_df.columns = ["Net Qty"]
        with inv_col4:
            _render_dashboard_chart_card(
                "Stock Movement Trend",
                "Net stock movement last 30 days.",
                movement_df,
                chart_kind="line",
                empty_message="No inventory movement history yet.",
                empty_hint="Stock receipts, adjustments, and sales movements will appear here.",
            )

        expiring_summary = inventory.get("expiring_summary") or {}
        exp_col1, exp_col2, exp_col3 = st.columns(3)
        exp_col1.metric("Expiring Soon", int(expiring_summary.get("expiring_soon", 0)))
        exp_col2.metric("Expired", int(expiring_summary.get("expired", 0)))
        exp_col3.metric("Invalid Expiry", int(expiring_summary.get("invalid", 0)))

        st.markdown('<div class="dashboard-section-title">Receivable / Payable Health</div>', unsafe_allow_html=True)
        rp_col1, rp_col2, rp_col3, rp_col4 = st.columns(4)
        rp_col1.metric("Overdue Receivables", format_currency(receivable_payable.get("ar_overdue_total", 0.0)))
        rp_col2.metric("Overdue Payables", format_currency(receivable_payable.get("ap_overdue_total", 0.0)))
        rp_col3.metric("AR Documents Overdue", str(receivable_payable.get("ar_overdue_count", 0)))
        rp_col4.metric("AP Documents Overdue", str(receivable_payable.get("ap_overdue_count", 0)))

        aging_col1, aging_col2 = st.columns(2)
        ar_aging = receivable_payable.get("ar_aging") or {}
        ap_aging = receivable_payable.get("ap_aging") or {}
        with aging_col1:
            st.markdown('<div class="eka-card dashboard-chart-card">', unsafe_allow_html=True)
            st.markdown("**Receivables Aging**")
            if sum(float(amount or 0.0) for amount in ar_aging.values()) > 0:
                for bucket, amount in ar_aging.items():
                    st.caption(f"{bucket}: {format_currency(amount)}")
            else:
                _render_dashboard_empty_state(
                    "No receivable balances available yet.",
                    "Posted customer invoices and credits will populate aging buckets.",
                )
            st.markdown("</div>", unsafe_allow_html=True)
        with aging_col2:
            st.markdown('<div class="eka-card dashboard-chart-card">', unsafe_allow_html=True)
            st.markdown("**Payables Aging**")
            if sum(float(amount or 0.0) for amount in ap_aging.values()) > 0:
                for bucket, amount in ap_aging.items():
                    st.caption(f"{bucket}: {format_currency(amount)}")
            else:
                _render_dashboard_empty_state(
                    "No payable balances available yet.",
                    "Supplier bills and payments will populate aging buckets.",
                )
            st.markdown("</div>", unsafe_allow_html=True)

        debtor_col, creditor_col = st.columns(2)
        with debtor_col:
            _render_dashboard_balance_card(
                "Biggest Debtors",
                receivable_payable.get("top_debtors") or [],
                empty_message="No balances available.",
                empty_hint="Outstanding customer balances will appear here.",
                column_labels={"name": "Customer", "balance": "Balance"},
            )
        with creditor_col:
            _render_dashboard_balance_card(
                "Biggest Suppliers Owed",
                receivable_payable.get("top_creditors") or [],
                empty_message="No balances available.",
                empty_hint="Outstanding supplier balances will appear here.",
                column_labels={"name": "Supplier", "balance": "Balance"},
            )

        st.markdown('<div class="dashboard-section-title">Live Activity</div>', unsafe_allow_html=True)
        conn = None
        try:
            conn = get_connection()
            left_col, right_col = st.columns([2, 1])
            with left_col:
                st.markdown('<div class="eka-card">', unsafe_allow_html=True)
                st.markdown("**Recent Transactions**")
                st.caption("Latest posted journal activity (last 10 entries).")
                recent_txns = pd.DataFrame(
                    get_recent_accounting_activity(company_key, branch_id=active_branch_id, limit=10, conn=conn)
                )
                if recent_txns.empty:
                    st.info("No recent transactions found.")
                else:
                    recent_txns["Amount"] = recent_txns["amount"].map(format_currency)
                    recent_txns = recent_txns.drop(
                        columns=[column for column in ["amount"] if column in recent_txns.columns]
                    ).rename(
                        columns={
                            "date": "Date",
                            "activity_type": "Type",
                            "description": "Description",
                            "reference": "Reference",
                        }
                    )
                    recent_txns = recent_txns[
                        [col for col in ["Date", "Type", "Reference", "Description", "Amount"] if col in recent_txns.columns]
                    ]
                    st.dataframe(format_currency_dataframe(recent_txns), use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)
            compare_legacy_and_journal_totals(
                company_key,
                branch_id=active_branch_id,
                logger_instance=logger,
                conn=conn,
            )
            with right_col:
                st.markdown('<div class="eka-card">', unsafe_allow_html=True)
                st.markdown("**Low Stock Items**")
                low_stock_sql = """
                    SELECT item_name AS Item, qty AS Quantity, min_stock_level AS Reorder
                    FROM inventory
                    WHERE company_key = ?
                      AND (
                          qty <= 0
                          OR qty <= COALESCE(min_stock_level, 0)
                      )
                """
                low_stock_params = [company_key]
                try:
                    inventory_columns = {column["name"] for column in list_columns(conn, "inventory")}
                    if active_branch_id and "branch_id" in inventory_columns:
                        low_stock_sql += " AND COALESCE(branch_id, '') = ?"
                        low_stock_params.append(str(active_branch_id))
                except Exception:
                    pass
                low_stock_sql += " ORDER BY qty ASC LIMIT 10"
                low_stock = _portable_read_dataframe(conn, low_stock_sql, tuple(low_stock_params))
                if low_stock.empty:
                    st.success("All stock levels are adequate.")
                else:
                    st.dataframe(low_stock, use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)
        finally:
            if conn:
                conn.close()

        st.markdown('<div class="dashboard-section-title">Quick Actions</div>', unsafe_allow_html=True)
        action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns(5)
        if action_col1.button("🛒 New Sale", key=f"dashboard_pos_{company_key}", use_container_width=True):
            st.session_state.page = "Point of Sale"
            st.rerun()
        if action_col2.button("📦 Add Inventory", key=f"dashboard_inventory_{company_key}", use_container_width=True):
            st.session_state.page = "Inventory Management"
            st.rerun()
        if action_col3.button("📄 Create New Bill", key=f"dashboard_create_bill_{company_key}", use_container_width=True):
            st.session_state.page = "Create Bill"
            st.rerun()
        if action_col4.button("🧾 Financial Reports", key=f"dashboard_financial_reports_{company_key}", use_container_width=True):
            st.session_state.page = "Financial Reports"
            st.rerun()
        if action_col5.button("📊 Data Analytics", key=f"dashboard_reports_{company_key}", use_container_width=True):
            st.session_state.page = "Data Analytics"
            st.rerun()
    except Exception as exc:
        st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))


def show_accounts_receivable(company_key):
    """Dedicated Accounts Receivable page wrapper."""
    show_aging(company_key, "Receivable")


def show_accounts_payable(company_key):
    """Dedicated Accounts Payable page wrapper."""
    show_aging(company_key, "Payable")


# ==========================================
# AI DATA ASSESSMENT
# ==========================================
def show_ai_assistant(client_id):
    active_company_id = _get_active_company_id(client_id)
    if not active_company_id:
        st.warning("No active company context is available for the AI assistant.")
        return
    role = st.session_state.get("user", {}).get("role", "System")
    if not require_permission(
        role,
        "use_ai_assistant",
        action_label="use the AI assistant",
        company_key=active_company_id,
        branch_id=st.session_state.get("active_branch_id"),
    ):
        return

    st.header("🤖 Gatekeeper Admin")
    st.caption("Ask questions about your last 30 days of invoices, expenses, and payroll activity.")

    conn = None
    try:
        conn = get_connection()
        records = _fetch_ai_assistant_records(conn, active_company_id)
    except Exception as exc:
        logger.error("AI assistant data fetch failed: %s", sanitize_error_message(exc))
        st.error("The AI assistant could not load your accounting records.")
        return
    finally:
        if conn:
            conn.close()

    data_summary = _summarize_ai_assistant_data(records)
    col1, col2, col3 = st.columns(3)
    col1.metric("Invoices", str(len(records["invoices"])))
    col2.metric("Expenses", str(len(records["expenses"])))
    col3.metric("Payroll Entries", str(len(records["payroll"])))

    with st.expander("30-Day Data Snapshot", expanded=False):
        st.text(data_summary)

    history_key = f"ai_assistant_messages_{active_company_id}"
    if history_key not in st.session_state:
        st.session_state[history_key] = [
            {
                "role": "assistant",
                "content": (
                    "I can review your recent invoices, expenses, and payroll activity. "
                    "Ask about trends, missing records, unusual balances, or possible corrections."
                ),
            }
        ]

    for message in st.session_state[history_key]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_question = st.chat_input(
        "Ask about invoices, expenses, or payroll...",
        key=f"ai_assistant_input_{active_company_id}",
    )
    if not user_question:
        return

    st.session_state[history_key].append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)

    ai_status = get_ai_client_status()
    if ai_status["client"] is None:
        fallback_response = (
            f"{get_openai_unavailable_message(ai_status)} "
            "Your 30-day data snapshot is still available above for manual review."
        )
        st.session_state[history_key].append({"role": "assistant", "content": fallback_response})
        with st.chat_message("assistant"):
            st.markdown(fallback_response)
        return

    prompt = (
        f"{ACCOUNTING_ASSISTANT_SYSTEM_PROMPT}\n"
        "Use the supplied 30-day accounting summary to answer clearly, highlight anomalies, "
        "and suggest edits or follow-up checks when appropriate. "
        "Do not invent records that are not present.\n\n"
        f"{_selected_currency_context()}\n"
        f"Client ID: {active_company_id}\n"
        f"30-day data summary:\n{data_summary}\n\n"
        f"User question: {user_question}"
    )

    response = request_ai_chat_completion(
        messages=[
            {
                "role": "system",
                "content": ACCOUNTING_ASSISTANT_SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1024,
    )
    if response["ok"]:
        assistant_reply = response["content"].strip()
        with st.chat_message("assistant"):
            with st.spinner("Reviewing your accounting records..."):
                st.markdown(assistant_reply)
        st.session_state[history_key].append({"role": "assistant", "content": assistant_reply})
    else:
        logger.error("AI assistant request failed via provider %s: %s", response.get("provider"), sanitize_error_message(response.get("error")))
        failure_message = response.get("error") or "AI assistant request failed. Please try again."
        st.session_state[history_key].append({"role": "assistant", "content": failure_message})
        with st.chat_message("assistant"):
            st.markdown(failure_message)


# ==========================================
# SUPPLIER MANAGEMENT FUNCTIONS
# ==========================================
def _register_supplier(conn, company_key, name, phone, email, address, category):
    """Insert a new supplier into the suppliers table using the active connection."""
    cursor = conn.execute(
        ensure_insert_sql_returning(
            "INSERT INTO suppliers (company_key, name, phone, email, address, category) VALUES (?, ?, ?, ?, ?, ?)"
        ),
        (
            company_key,
            name.strip(),
            phone.strip() if phone else "",
            email.strip() if email else "",
            address.strip() if address else "",
            category.strip() if category else "",
        ),
    )
    return get_inserted_id(cursor)


def _record_supplier_ledger_transaction(conn, company_key, supplier_id, transaction_type, amount, description, role, reference=None, transaction_date=None, post_to_gl=True):
    """Record a debit/credit to a specific supplier's account."""
    transaction_type = str(transaction_type or "").strip().title()
    if transaction_type not in {"Debit", "Credit"}:
        raise ValueError("Transaction type must be Debit or Credit.")

    amount = float(amount or 0.0)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    tx_date = transaction_date.isoformat() if hasattr(transaction_date, "isoformat") else (transaction_date or datetime.now().date().isoformat())
    supplier = conn.execute(
        "SELECT id, name FROM suppliers WHERE id = ? AND company_key = ?",
        (int(supplier_id), company_key),
    ).fetchone()
    if not supplier:
        raise ValueError("Selected supplier could not be found.")

    if post_to_gl:
        ap_account_id = get_account_id(conn, "Accounts Payable", "Liability")
        contra_account_id = get_account_id(conn, "Cash", "Asset") if transaction_type == "Debit" else get_account_id(conn, "Purchases", "Expense")
        lines = (
            [
                {"account_id": ap_account_id, "debit": amount, "credit": 0},
                {"account_id": contra_account_id, "debit": 0, "credit": amount},
            ]
            if transaction_type == "Debit"
            else [
                {"account_id": contra_account_id, "debit": amount, "credit": 0},
                {"account_id": ap_account_id, "debit": 0, "credit": amount},
            ]
        )
        post_journal_entry(
            company_key=company_key,
            date=tx_date,
            description=f"{description} - {supplier['name']}",
            reference=reference or f"SUP-{supplier_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            lines=lines,
            created_by=role,
            supplier_id=int(supplier_id),
            source_module="Accounts Payable",
            source_table="supplier_transactions",
            conn=conn,
        )

    conn.execute(
        """
        INSERT INTO supplier_transactions (
            company_key, supplier_id, transaction_type, amount,
            description, reference, transaction_date, created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_key,
            int(supplier_id),
            transaction_type,
            amount,
            description,
            reference,
            tx_date,
            role,
        ),
    )
    new_balance = get_supplier_balance(company_key, int(supplier_id), as_of_date=tx_date, conn=conn)
    previous_balance = round(new_balance - (amount if transaction_type == "Credit" else -amount), 2)
    return {
        "supplier_name": supplier["name"],
        "previous_balance": previous_balance,
        "new_balance": new_balance,
        "delta": amount if transaction_type == "Credit" else -amount,
        "transaction_date": tx_date,
    }


# ==========================================
# SYSTEM AUDIT TRAIL
# ==========================================
def show_audit_trail(company_key, role="User", branch_id=None):
    st.header("🔍 System Audit Trail")
    if not require_permission(
        role,
        "view_audit_trail",
        action_label="view the audit trail",
        company_key=company_key,
        branch_id=branch_id,
    ):
        return
    try:
        conn = get_connection()
        audit_columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_logs)").fetchall()}
        action_type_expr = "COALESCE(NULLIF(action_type, ''), 'legacy')" if "action_type" in audit_columns else "'legacy'"
        document_ref_expr = "COALESCE(document_ref, '')" if "document_ref" in audit_columns else "''"
        if company_key == "ADMIN" or company_key == "DEMO":
            query = f"""
                SELECT timestamp, company_key, branch_id, user_role, action, module_name,
                       {action_type_expr} AS action_type,
                       {document_ref_expr} AS document_ref,
                       details
                FROM audit_logs
                ORDER BY timestamp DESC
                LIMIT 100
            """
            params = ()
        elif role == "Master Admin":
            if branch_id:
                query = f"""
                    SELECT timestamp, company_key, branch_id, user_role, action, module_name,
                           {action_type_expr} AS action_type,
                           {document_ref_expr} AS document_ref,
                           details
                    FROM audit_logs
                    WHERE company_key = ? AND branch_id = ?
                    ORDER BY timestamp DESC
                    LIMIT 100
                """
                params = (company_key, branch_id)
            else:
                query = f"""
                    SELECT timestamp, company_key, branch_id, user_role, action, module_name,
                           {action_type_expr} AS action_type,
                           {document_ref_expr} AS document_ref,
                           details
                    FROM audit_logs
                    WHERE company_key = ?
                    ORDER BY timestamp DESC
                    LIMIT 100
                """
                params = (company_key,)
        else:
            query = f"""
                SELECT timestamp, company_key, branch_id, user_role, action, module_name,
                       {action_type_expr} AS action_type,
                       {document_ref_expr} AS document_ref,
                       details
                FROM audit_logs
                WHERE company_key = ?
                ORDER BY timestamp DESC
                LIMIT 100
            """
            params = (company_key,)

        data = conn.execute(query, params).fetchall()
        conn.close()

        if data:
            df = pd.DataFrame(
                data,
                columns=["Timestamp", "Company", "Branch", "User", "Action", "Module", "Action Type", "Reference", "Details"],
            )
            if "Details" in df.columns:
                extracted_amount = df["Details"].astype(str).str.extract(r"amount=([0-9]+(?:\.[0-9]+)?)", expand=False)
                df["Amount"] = pd.to_numeric(extracted_amount, errors="coerce")
                df["Source"] = df["Module"]
            st.dataframe(format_currency_dataframe(df), use_container_width=True)
            excel_bin = get_excel_bin(df)
            if excel_bin:
                st.download_button("📥 Export Audit Trail", data=excel_bin, file_name="audit_trail.xlsx")
        else:
            st.info("No audit records found.")
    except Exception as e:
        st.error(build_user_safe_error(e, role))


def _branch_type_catalog_selectbox(conn, key, label="Branch Type"):
    catalog = get_branch_type_catalog(conn)
    if not catalog:
        ensure_branch_licensing_schema_integrity(conn)
        catalog = get_branch_type_catalog(conn)
    if not catalog:
        return st.selectbox(label, options=["other"], format_func=lambda value: "Other", key=key)
    options = [row["branch_type_key"] for row in catalog]
    labels = {row["branch_type_key"]: row["branch_type_name"] for row in catalog}
    return st.selectbox(label, options=options, format_func=lambda value: labels.get(value, value), key=key)


def _render_branch_license_status(conn, company_key):
    license_snapshot = get_company_branch_license_snapshot(conn, company_key, ensure_schema=False)
    st.info(
        "Licensed active branches: {active}/{max} "
        "(purchased/deployed: {purchased}; inactive branches do not count toward the active limit).".format(
            active=license_snapshot["active_branch_count"],
            max=license_snapshot["max_branches"],
            purchased=license_snapshot["number_of_branches"],
        )
    )
    return license_snapshot


def _branch_manager_display_label(branch):
    """Prefer full manager name, then user_id, then legacy branch_manager text."""
    full_name = str(branch.get("manager_user_name") or "").strip()
    user_id = str(branch.get("manager_user_id") or "").strip()
    legacy_name = str(branch.get("branch_manager") or "").strip()
    if full_name:
        return full_name
    if user_id:
        return user_id
    if legacy_name:
        return legacy_name
    return "—"


def _staff_branch_display(branch_id, branch_options):
    normalized_branch_id = str(branch_id or "").strip()
    if not normalized_branch_id:
        return "Unassigned"
    return branch_options.get(normalized_branch_id, normalized_branch_id)


def _branch_display_code(branch):
    return str(
        branch.get("branch_code")
        or branch.get("branch_name")
        or branch.get("branch_id")
        or ""
    ).strip()


def _render_branch_internal_id_diagnostics(conn, company_key, role):
    if _normalize_role_name(role) != "Dev":
        return
    rows = conn.execute(
        """
        SELECT branch_name,
               COALESCE(NULLIF(TRIM(branch_code), ''), branch_name, branch_id) AS branch_code,
               branch_id
        FROM branches
        WHERE company_key = ?
        ORDER BY branch_name
        """,
        (company_key,),
    ).fetchall()
    if not rows:
        return
    with st.expander("Developer diagnostics — internal branch IDs", expanded=False):
        st.caption("Internal branch_id values are stable foreign keys and are not shown in normal branch views.")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Branch Name": row[0],
                        "Branch Code": row[1],
                        "Internal branch_id": row[2],
                    }
                    for row in rows
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


def _render_branch_list_with_grants(conn, company_key, role):
    branches = list_company_branches_with_grants(conn, company_key)
    if not branches:
        st.info("No branches found. Add your first branch below.")
        return []
    display_rows = []
    for branch in branches:
        manager_label = _branch_manager_display_label(branch)
        display_rows.append(
            {
                "Branch Name": branch["branch_name"],
                "Branch Type": branch.get("branch_type_name") or branch.get("branch_type"),
                "Active": "Yes" if int(branch.get("is_active") or 0) else "No",
                "Deployment": branch.get("deployment_status"),
                "Tier": branch.get("branch_tier"),
                "Manager": manager_label,
                "Module Grants": int(branch.get("module_grant_count") or 0),
                "Branch Code": _branch_display_code(branch),
            }
        )
    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
    _render_branch_internal_id_diagnostics(conn, company_key, role)
    return branches


def _render_branch_creation_form(conn, company_key, role, *, form_key_prefix="branch_mgmt", default_active=True):
    license_snapshot = get_company_branch_license_snapshot(conn, company_key, ensure_schema=False)
    if default_active:
        _render_branch_license_status(conn, company_key)
    can_add_active = bool(license_snapshot.get("can_create_active_branch"))

    with st.form(f"{form_key_prefix}_branch_form"):
        branch_name = st.text_input("Branch Name", key=f"{form_key_prefix}_branch_name")
        branch_type_key = _branch_type_catalog_selectbox(conn, key=f"{form_key_prefix}_branch_type")
        branch_access_key = st.text_input(
            "Branch Access Key (optional — auto-generated if blank)",
            key=f"{form_key_prefix}_branch_access_key",
        )
        branch_manager = st.text_input("Branch Manager Display Name (optional)", key=f"{form_key_prefix}_branch_manager")
        location = st.text_input("Location / Physical Address", key=f"{form_key_prefix}_branch_location")
        contact_number = st.text_input("Contact Number", key=f"{form_key_prefix}_branch_contact")
        col_active, col_deploy, col_tier = st.columns(3)
        with col_active:
            is_active = st.checkbox("Active branch", value=default_active, key=f"{form_key_prefix}_is_active")
        with col_deploy:
            deployment_status = st.selectbox(
                "Deployment Status",
                ["active", "pending", "suspended"],
                index=0,
                key=f"{form_key_prefix}_deployment_status",
            )
        with col_tier:
            branch_tier = st.selectbox(
                "Branch Tier",
                ["standard", "premium", "enterprise"],
                index=0,
                key=f"{form_key_prefix}_branch_tier",
            )
        create_bookkeeper = st.checkbox(
            "Create default Branch Bookkeeper login (uses branch access key)",
            value=False,
            key=f"{form_key_prefix}_create_bookkeeper",
        )
        submitted = st.form_submit_button("Save Branch")

    if not submitted:
        return

    if not is_company_branch_admin(role):
        st.warning("You do not have permission to create branches.")
        return
    if not branch_name.strip():
        st.error("Branch Name is required.")
        return
    if is_active and not can_add_active:
        st.error(
            "Active branch limit reached. Deactivate an existing branch or increase the licensed branch count before adding another active branch."
        )
        return

    bookkeeper_password_hash = None
    if create_bookkeeper:
        bookkeeper_password_hash = _hash_security_answer("default123")

    def _create_branch(write_conn):
        result = create_company_branch(
            write_conn,
            company_key,
            branch_name=branch_name.strip(),
            branch_type_key=branch_type_key,
            branch_access_key=branch_access_key.strip() or None,
            manager_user_id=None,
            is_active=1 if is_active else 0,
            deployment_status=deployment_status,
            branch_tier=branch_tier,
            location=location,
            contact_number=contact_number,
            branch_manager=branch_manager,
            create_default_bookkeeper_user=bool(create_bookkeeper),
            bookkeeper_password_hash=bookkeeper_password_hash,
            ensure_schema=False,
        )
        if not result.get("ok"):
            return result
        grants_inserted = int((result.get("module_grants") or {}).get("inserted") or 0)
        log_audit_action(
            write_conn,
            company_key,
            role,
            f"Added branch: {result.get('branch_name')} ({result.get('branch_id')})",
            "Branch Management",
            branch_id=result.get("branch_id"),
            details=f"module_grants_inserted={grants_inserted}",
        )
        result["grants_inserted"] = grants_inserted
        return result

    try:
        result = _run_branch_db_write(
            f"create_branch_{form_key_prefix}",
            _create_branch,
            release_conn=conn,
        )
    except Exception as exc:
        st.error(build_user_safe_error(exc, role))
        return
    if not result or not result.get("ok"):
        st.error((result or {}).get("reason") or "Branch could not be created.")
        return
    st.success(
        "Branch '{name}' saved. Access key: {key}. Module grants created: {grants}.".format(
            name=result.get("branch_name"),
            key=result.get("branch_access_key"),
            grants=result.get("grants_inserted", 0),
        )
    )
    _clear_streamlit_state(f"{form_key_prefix}_branch_name", f"{form_key_prefix}_branch_access_key")
    _increment_form_reset(f"{form_key_prefix}_branch_form_reset")
    st.rerun()


def can_access_branch_management(role):
    return (
        user_has_permission(role, "manage_branches")
        or user_has_permission(role, "manage_branch_users")
        or user_has_permission(role, "view_branch_configuration")
    )


def _branch_user_creatable_roles(actor_role):
    normalized_role = _normalize_role_name(actor_role)
    if user_has_permission(normalized_role, "manage_branches") or user_has_permission(normalized_role, "manage_users"):
        return sorted(set(BRANCH_MANAGER_CREATABLE_ROLES) | {"Bookkeeper", "Accountant"})
    return sorted(BRANCH_MANAGER_CREATABLE_ROLES)


def _resolve_branch_manager_session_branch(user, company_key):
    normalized_role = _normalize_role_name(_extract_role_from_user(user))
    if user_has_permission(normalized_role, "manage_branches"):
        return None
    if normalized_role == "Branch Manager":
        branch_id = _extract_user_branch_id(user)
        if not branch_id:
            return None
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT branch_id FROM branches WHERE company_key = ? AND manager_user_id = ?",
                (company_key, user.get("user_id")),
            ).fetchone()
            if row:
                return str(row[0])
        except Exception:
            pass
        finally:
            conn.close()
        return str(branch_id).strip()
    return _extract_user_branch_id(user)


def _render_branch_users_panel(company_key, branch_id, role, *, panel_key_prefix="branch_users", conn=None):
    if not can_manage_branch_users_role(role):
        st.warning("You do not have permission to manage branch users.")
        return

    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    company_admin = is_company_branch_admin(role)
    try:
        branch_row = conn.execute(
            """
            SELECT branch_name,
                   COALESCE(NULLIF(TRIM(branch_code), ''), branch_name, branch_id) AS branch_code
            FROM branches
            WHERE company_key = ? AND branch_id = ?
            """,
            (company_key, branch_id),
        ).fetchone()
        branch_label = branch_row[0] if branch_row else branch_id
        branch_code = branch_row[1] if branch_row else branch_id
        st.subheader(f"Branch Users — {branch_label}")
        st.caption(f"Branch Code: {branch_code}")

        users = list_branch_users(conn, company_key, branch_id)
        if users:
            display_rows = [
                {
                    "Name": row["full_name"],
                    "Role": row["role"],
                    "Login Key": row["login_key"],
                    "Status": row.get("status") or "Active",
                    "User ID": row.get("user_id"),
                }
                for row in users
            ]
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No users have been created for this branch yet.")

        allowed_roles = _branch_user_creatable_roles(role)
        with st.form(f"{panel_key_prefix}_create_user_form"):
            full_name = st.text_input("Full Name", key=f"{panel_key_prefix}_full_name")
            staff_role = st.selectbox("Role", allowed_roles, key=f"{panel_key_prefix}_role")
            manual_login_key = st.text_input(
                "Login / Access Key (optional — auto-generated if blank)",
                key=f"{panel_key_prefix}_login_key",
            )
            if st.form_submit_button("Create Branch User"):
                form_full_name = full_name.strip()
                form_role = staff_role
                form_login_key = manual_login_key.strip() or None

                def _create_user(write_conn):
                    result = create_branch_scoped_user(
                        write_conn,
                        company_key,
                        branch_id,
                        full_name=form_full_name,
                        role=form_role,
                        login_key=form_login_key,
                        status="Active",
                        allowed_roles=set(allowed_roles),
                    )
                    if not result.get("ok"):
                        return result
                    log_audit_action(
                        write_conn,
                        company_key,
                        role,
                        f"Created branch user {result.get('full_name')} ({result.get('role')})",
                        "Branch User Administration",
                        branch_id=branch_id,
                        details=f"login_key={result.get('login_key')}",
                    )
                    return result

                try:
                    result = _run_branch_db_write(
                        f"create_branch_user_{panel_key_prefix}",
                        _create_user,
                        release_conn=None if owns_connection else conn,
                    )
                except Exception as exc:
                    st.error(build_user_safe_error(exc, role))
                    return
                if not result or not result.get("ok"):
                    st.error((result or {}).get("reason") or "User could not be created.")
                    return
                st.success("User created. Login key: {key}".format(key=result.get("login_key")))
                _clear_streamlit_state(
                    f"{panel_key_prefix}_full_name",
                    f"{panel_key_prefix}_login_key",
                )
                _increment_form_reset(f"{panel_key_prefix}_create_user_reset")
                st.rerun()

        st.markdown("#### Activate / Deactivate Users")
        if not users:
            st.caption("No users have been created for this branch yet.")
        for row in users:
            if str(row.get("role") or "") in PRIVILEGED_COMPANY_USER_ROLES:
                continue
            if str(row.get("role") or "") == "Branch Manager" and not company_admin:
                continue
            status_col, action_col = st.columns([3, 1])
            current_status = str(row.get("status") or "Active")
            status_col.write(
                f"{row['full_name']} ({row['role']}) — Login: {row.get('login_key')} — {current_status}"
            )
            next_status = "Deactivate" if current_status == "Active" else "Activate"
            if action_col.button(
                next_status,
                key=f"{panel_key_prefix}_toggle_{row['id']}",
            ):
                user_pk = row["id"]

                def _toggle_user(write_conn):
                    update_result = update_branch_user_status(
                        write_conn,
                        company_key,
                        branch_id,
                        user_pk,
                        "Inactive" if current_status == "Active" else "Active",
                        allowed_roles=set(_branch_user_creatable_roles(role)),
                        company_admin=company_admin,
                    )
                    if not update_result.get("ok"):
                        return update_result
                    log_audit_action(
                        write_conn,
                        company_key,
                        role,
                        f"Set {row['full_name']} to {'Inactive' if current_status == 'Active' else 'Active'}",
                        "Branch User Administration",
                        branch_id=branch_id,
                    )
                    return update_result

                try:
                    update_result = _run_branch_db_write(
                        f"toggle_branch_user_{panel_key_prefix}_{user_pk}",
                        _toggle_user,
                        release_conn=None if owns_connection else conn,
                    )
                except Exception as exc:
                    st.error(build_user_safe_error(exc, role))
                    return
                if not update_result or not update_result.get("ok"):
                    st.error((update_result or {}).get("reason") or "Status update failed.")
                    return
                st.success(f"{row['full_name']} is now {'Inactive' if current_status == 'Active' else 'Active'}.")
                st.rerun()
    except Exception as exc:
        st.error(build_user_safe_error(exc, role))
    finally:
        if owns_connection and conn:
            conn.close()


def _render_branch_edit_panels(conn, company_key, role, branches):
    if not is_company_branch_admin(role):
        return
    catalog = get_branch_type_catalog(conn)
    type_options = [row["branch_type_key"] for row in catalog] or ["other"]
    type_labels = {row["branch_type_key"]: row["branch_type_name"] for row in catalog}
    st.subheader("Edit Branches")
    for branch in branches:
        branch_id = branch["branch_id"]
        manager_options = fetch_branch_manager_select_options(
            conn,
            company_key,
            branch_id,
            branch.get("manager_user_id"),
        )
        manager_ids = [""] + [row["user_id"] for row in manager_options]
        manager_labels = {"": "No manager"}
        for candidate in manager_options:
            manager_labels[candidate["user_id"]] = (
                f"{candidate['full_name']} ({candidate['role']}) — {candidate['user_id']}"
            )
        current_manager_id = str(branch.get("manager_user_id") or "").strip()
        branch_code_label = _branch_display_code(branch)
        with st.expander(f"Edit: {branch['branch_name']} ({branch_code_label})"):
            with st.form(f"edit_branch_form_{branch_id}"):
                branch_name = st.text_input("Branch Name", value=branch.get("branch_name") or "", key=f"edit_name_{branch_id}")
                branch_code = st.text_input(
                    "Branch Code",
                    value=_branch_display_code(branch),
                    key=f"edit_code_{branch_id}",
                )
                location = st.text_input("Location", value=branch.get("location") or "", key=f"edit_location_{branch_id}")
                branch_type_key = st.selectbox(
                    "Branch Type",
                    type_options,
                    index=_safe_select_index(type_options, branch.get("branch_type_key") or "other", "other"),
                    format_func=lambda value: type_labels.get(value, value),
                    key=f"edit_type_{branch_id}",
                )
                branch_access_key = st.text_input(
                    "Branch Access Key",
                    value=branch.get("branch_access_key") or "",
                    key=f"edit_access_{branch_id}",
                )
                manager_user_id = st.selectbox(
                    "Branch Manager",
                    manager_ids,
                    index=_safe_select_index(manager_ids, current_manager_id, ""),
                    format_func=lambda value: manager_labels.get(value, "No manager"),
                    key=f"edit_manager_id_{branch_id}",
                )
                is_active = st.checkbox(
                    "Active",
                    value=bool(int(branch.get("is_active") or 0)),
                    key=f"edit_active_{branch_id}",
                )
                deployment_status = st.selectbox(
                    "Deployment Status",
                    ["active", "pending", "suspended"],
                    index=["active", "pending", "suspended"].index(branch.get("deployment_status") or "active")
                    if (branch.get("deployment_status") or "active") in {"active", "pending", "suspended"}
                    else 0,
                    key=f"edit_deploy_{branch_id}",
                )
                branch_tier = st.selectbox(
                    "Branch Tier",
                    ["standard", "premium", "enterprise"],
                    index=["standard", "premium", "enterprise"].index(branch.get("branch_tier") or "standard")
                    if (branch.get("branch_tier") or "standard") in {"standard", "premium", "enterprise"}
                    else 0,
                    key=f"edit_tier_{branch_id}",
                )
                promote_manager = st.checkbox(
                    "Promote manager to Branch Manager role",
                    value=False,
                    key=f"edit_promote_{branch_id}",
                )
                if st.form_submit_button("Save Branch Changes"):
                    save_payload = {
                        "branch_name": branch_name,
                        "branch_code": branch_code,
                        "location": location,
                        "branch_type_key": branch_type_key,
                        "branch_access_key": branch_access_key,
                        "manager_user_id": manager_user_id.strip() or None,
                        "is_active": 1 if is_active else 0,
                        "deployment_status": deployment_status,
                        "branch_tier": branch_tier,
                        "promote_manager": promote_manager,
                    }

                    def _save_branch(write_conn):
                        result = update_company_branch(
                            write_conn,
                            company_key,
                            branch_id,
                            **save_payload,
                        )
                        if not result.get("ok"):
                            return result
                        log_audit_action(
                            write_conn,
                            company_key,
                            role,
                            f"Updated branch {branch_name}",
                            "Branch Management",
                            branch_id=branch_id,
                        )
                        return result

                    try:
                        result = _run_branch_db_write(
                            f"update_branch_{branch_id}",
                            _save_branch,
                            release_conn=conn,
                        )
                    except Exception as exc:
                        st.error(build_user_safe_error(exc, role))
                        return
                    if not result or not result.get("ok"):
                        st.error((result or {}).get("reason") or "Branch update failed.")
                        return
                    if result.get("branch_type_changed"):
                        st.info("Module grants updated for new branch type.")
                    st.success("Branch updated successfully.")
                    _increment_form_reset(f"edit_branch_form_reset_{branch_id}")
                    st.rerun()


def _render_staff_assignment_tab(company_key, role):
    if not is_company_branch_admin(role):
        st.warning("Staff assignment is available to company branch administrators only.")
        return
    conn = get_connection()
    try:
        ensure_branch_licensing_schema_integrity(conn)
        branches = conn.execute(
            "SELECT branch_id, branch_name FROM branches WHERE company_key = ? ORDER BY branch_name",
            (company_key,),
        ).fetchall()
        branch_keys = [""] + [row[0] for row in branches]
        branch_options = {"": "Unassigned"}
        for row in branches:
            branch_options[row[0]] = row[1]
        staff_rows = list_company_staff_for_assignment(conn, company_key)
        if not staff_rows:
            st.info(
                "No assignable staff users found for this company. "
                "Create branch users on the Branch Users tab or add staff in System Configuration."
            )
            return

        display_df = pd.DataFrame(
            [
                {
                    "Name": row["full_name"],
                    "User ID": row.get("user_id_display"),
                    "Role": row["role"],
                    "Branch": _staff_branch_display(row.get("branch_id"), branch_options),
                    "Status": row.get("status") or "Active",
                    "Login Key": row.get("login_key_display"),
                }
                for row in staff_rows
            ]
        )
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        assignable_roles = sorted(COMPANY_STAFF_ASSIGNABLE_ROLES)
        st.markdown("#### Assign or Transfer Staff")
        staff_labels = {
            row["id"]: f"{row['full_name']} ({row['role']}) — {row.get('user_id_display', '(no user id)')}"
            for row in staff_rows
        }
        staff_ids = [row["id"] for row in staff_rows]
        with st.form("staff_assignment_bulk_form"):
            selected_user_id = st.selectbox(
                "Select user",
                staff_ids,
                format_func=lambda value: staff_labels.get(value, str(value)),
                key="staff_assign_user_select",
            )
            selected_row = next(row for row in staff_rows if row["id"] == selected_user_id)
            selected_branch = st.selectbox(
                "Target branch",
                branch_keys,
                index=_safe_select_index(branch_keys, selected_row.get("branch_id") or "", ""),
                format_func=lambda value: branch_options.get(value, value),
                key="staff_assign_branch_select",
            )
            selected_role = st.selectbox(
                "Role",
                assignable_roles,
                index=_safe_select_index(assignable_roles, selected_row.get("role"), assignable_roles[0]),
                key="staff_assign_role_select",
            )
            if st.form_submit_button("Save Assignment"):
                target_branch = selected_branch or None

                def _assign_staff(write_conn):
                    result = update_company_staff_branch_assignment(
                        write_conn,
                        company_key,
                        selected_user_id,
                        target_branch,
                        role=selected_role,
                        actor_role=role,
                    )
                    if not result.get("ok"):
                        return result
                    log_audit_action(
                        write_conn,
                        company_key,
                        role,
                        f"Updated staff assignment for {selected_row['full_name']}",
                        "Staff Assignment",
                        branch_id=target_branch,
                    )
                    return result

                try:
                    result = _run_branch_db_write(
                        "staff_assignment_save",
                        _assign_staff,
                        release_conn=conn,
                    )
                except Exception as exc:
                    st.error(build_user_safe_error(exc, role))
                    return
                if not result or not result.get("ok"):
                    st.error((result or {}).get("reason") or "Assignment failed.")
                    return
                st.success("Assignment updated.")
                _increment_form_reset("staff_assignment_bulk_reset")
                st.rerun()

        st.markdown("#### Per-User Quick Actions")
        for row in staff_rows:
            with st.expander(f"{row['full_name']} ({row['role']})"):
                current_branch = row.get("branch_id") or ""
                branch_key_list = list(branch_keys)
                selected_branch = st.selectbox(
                    "Branch assignment",
                    branch_key_list,
                    index=_safe_select_index(branch_key_list, current_branch, ""),
                    format_func=lambda value: branch_options.get(value, value),
                    key=f"staff_branch_{row['id']}",
                )
                selected_role = st.selectbox(
                    "Role",
                    assignable_roles,
                    index=_safe_select_index(assignable_roles, row.get("role"), assignable_roles[0]),
                    key=f"staff_role_{row['id']}",
                )
                col_save, col_clear = st.columns(2)
                if col_save.button("Save Assignment", key=f"staff_save_{row['id']}"):
                    user_pk = row["id"]
                    target_branch = selected_branch or None

                    def _assign_one(write_conn):
                        result = update_company_staff_branch_assignment(
                            write_conn,
                            company_key,
                            user_pk,
                            target_branch,
                            role=selected_role,
                            actor_role=role,
                        )
                        if not result.get("ok"):
                            return result
                        log_audit_action(
                            write_conn,
                            company_key,
                            role,
                            f"Updated staff assignment for {row['full_name']}",
                            "Staff Assignment",
                            branch_id=target_branch,
                        )
                        return result

                    try:
                        result = _run_branch_db_write(
                            f"staff_save_{user_pk}",
                            _assign_one,
                            release_conn=conn,
                        )
                    except Exception as exc:
                        st.error(build_user_safe_error(exc, role))
                        return
                    if not result or not result.get("ok"):
                        st.error((result or {}).get("reason") or "Assignment failed.")
                        return
                    st.success("Assignment updated.")
                    st.rerun()
                if col_clear.button("Remove from branch", key=f"staff_clear_{row['id']}"):
                    user_pk = row["id"]

                    def _clear_one(write_conn):
                        return update_company_staff_branch_assignment(
                            write_conn,
                            company_key,
                            user_pk,
                            None,
                            role=selected_role,
                            actor_role=role,
                        )

                    try:
                        result = _run_branch_db_write(
                            f"staff_clear_{user_pk}",
                            _clear_one,
                            release_conn=conn,
                        )
                    except Exception as exc:
                        st.error(build_user_safe_error(exc, role))
                        return
                    if not result or not result.get("ok"):
                        st.error((result or {}).get("reason") or "Could not remove branch assignment.")
                        return
                    st.success("User removed from branch.")
                    st.rerun()
    except Exception as exc:
        st.error(build_user_safe_error(exc, role))
    finally:
        conn.close()


def _render_branch_manager_assignment_section(conn, company_key, role):
    if not is_company_branch_admin(role):
        return
    branches = list_company_branches_with_grants(conn, company_key)
    if not branches:
        return
    st.subheader("Assign Branch Managers")
    for branch in branches:
        branch_id = branch["branch_id"]
        manager_label = _branch_manager_display_label(branch)
        with st.expander(f"{branch['branch_name']} — Manager: {manager_label}"):
            candidates = fetch_branch_manager_candidates(conn, company_key, branch_id)
            if not candidates:
                st.caption("No eligible users. Create a branch user first or unassign users from other branches.")
            else:
                candidate_ids = [row["user_id"] for row in candidates]
                candidate_labels = {
                    row["user_id"]: f"{row['full_name']} ({row['role']})" for row in candidates
                }
                default_index = 0
                current_manager_id = branch.get("manager_user_id")
                if current_manager_id in candidate_ids:
                    default_index = candidate_ids.index(current_manager_id)
                selected_user_id = st.selectbox(
                    "Manager user",
                    candidate_ids,
                    index=default_index,
                    format_func=lambda value: candidate_labels.get(value, value),
                    key=f"branch_manager_select_{branch_id}",
                )
                promote = st.checkbox(
                    "Promote selected user to Branch Manager role",
                    value=True,
                    key=f"branch_manager_promote_{branch_id}",
                )
                if st.button("Save Branch Manager", key=f"branch_manager_save_{branch_id}"):
                    selected_manager = selected_user_id

                    def _assign_mgr(write_conn):
                        result = assign_branch_manager(
                            write_conn,
                            company_key,
                            branch_id,
                            selected_manager,
                            promote_to_branch_manager=promote,
                        )
                        if not result.get("ok"):
                            return result
                        log_audit_action(
                            write_conn,
                            company_key,
                            role,
                            f"Assigned branch manager for {branch['branch_name']}",
                            "Branch Management",
                            branch_id=branch_id,
                            details=f"manager_user_id={selected_manager}",
                        )
                        return result

                    try:
                        result = _run_branch_db_write(
                            f"assign_manager_{branch_id}",
                            _assign_mgr,
                            release_conn=conn,
                        )
                    except Exception as exc:
                        st.error(build_user_safe_error(exc, role))
                        return
                    if not result or not result.get("ok"):
                        st.error((result or {}).get("reason") or "Could not assign branch manager.")
                        return
                    st.success("Branch manager updated.")
                    st.rerun()
            with st.expander("Manage users for this branch", expanded=False):
                _render_branch_users_panel(
                    company_key,
                    branch_id,
                    role,
                    panel_key_prefix=f"branch_users_{branch_id}",
                    conn=conn,
                )


def show_branch_management(company_key, role):
    if not can_access_branch_management(role):
        require_permission(role, "manage_branches", action_label="access branch management", company_key=company_key)
        return

    user = st.session_state.get("user") or {}
    normalized_role = _normalize_role_name(role)
    can_manage_company_branches = user_has_permission(role, "manage_branches")
    can_manage_branch_users = user_has_permission(role, "manage_branch_users")

    if can_manage_branch_users and not can_manage_company_branches:
        branch_id = _resolve_branch_manager_session_branch(user, company_key)
        if not branch_id:
            st.error(
                "Your Branch Manager account is not linked to a branch yet. "
                "Ask your Master Admin to assign you as branch manager."
            )
            return
        enforce_branch_session_lock(user)
        st.header("🏢 Branch Users")
        _render_branch_users_panel(company_key, branch_id, role, panel_key_prefix="branch_manager_users")
        return

    st.header("🏢 Branch Management")

    tabs = st.tabs(["Branch List & Configuration", "Branch Users", "Staff Assignment", "Branch Performance"])

    with tabs[0]:
        st.subheader("Current Branches")
        conn = get_connection()
        try:
            ensure_branch_licensing_schema_integrity(conn)
            branch_rows = _render_branch_list_with_grants(conn, company_key, role)
            if branch_rows:
                _render_branch_edit_panels(conn, company_key, role, branch_rows)
        except Exception as e:
            st.error(build_user_safe_error(e, role))
        finally:
            conn.close()

        st.markdown("---")
        if is_company_branch_admin(role) and st.button(
            "Repair / Generate Missing Module Grants",
            key="repair_branch_module_grants_btn",
        ):
            def _repair_grants(write_conn):
                repair_result = repair_branch_module_grants(
                    write_conn,
                    company_key,
                    ensure_schema=False,
                )
                log_audit_action(
                    write_conn,
                    company_key,
                    role,
                    "Repaired branch module grants",
                    "Branch Management",
                    details=(
                        f"branches_processed={repair_result.get('branches_processed')}; "
                        f"grants_inserted={repair_result.get('grants_inserted')}"
                    ),
                )
                return repair_result

            try:
                repair_result = _run_branch_db_write("repair_branch_module_grants", _repair_grants)
            except Exception as exc:
                st.error(build_user_safe_error(exc, role))
            else:
                st.success(
                    "Repair complete. Branches scanned: {branches}. New grants inserted: {grants}.".format(
                        branches=repair_result.get("branches_processed"),
                        grants=repair_result.get("grants_inserted"),
                    )
                )
                st.rerun()

        st.subheader("Add Branch")
        list_conn = get_connection()
        try:
            ensure_branch_licensing_schema_integrity(list_conn)
            license_snapshot = get_company_branch_license_snapshot(list_conn, company_key)
            if license_snapshot.get("can_create_active_branch"):
                _render_branch_creation_form(list_conn, company_key, role, form_key_prefix="branch_mgmt")
            else:
                _render_branch_license_status(list_conn, company_key)
                st.warning(
                    "Cannot add another active branch until the license limit is increased or an active branch is deactivated."
                )
                with st.expander("Add inactive branch (does not count toward active limit)"):
                    _render_branch_creation_form(
                        list_conn,
                        company_key,
                        role,
                        form_key_prefix="branch_mgmt_inactive",
                        default_active=False,
                    )
        except Exception as e:
            st.error(build_user_safe_error(e, role))
        finally:
            list_conn.close()

        manager_conn = get_connection()
        try:
            ensure_branch_licensing_schema_integrity(manager_conn)
            _render_branch_manager_assignment_section(manager_conn, company_key, role)
        except Exception as e:
            st.error(build_user_safe_error(e, role))
        finally:
            manager_conn.close()

    with tabs[1]:
        st.subheader("Branch Users by Branch")
        if not can_manage_branch_users_role(role):
            st.warning("You do not have permission to manage branch users.")
        else:
            branch_conn = get_connection()
            try:
                ensure_branch_licensing_schema_integrity(branch_conn)
                branch_rows = branch_conn.execute(
                    "SELECT branch_id, branch_name FROM branches WHERE company_key = ? ORDER BY branch_name",
                    (company_key,),
                ).fetchall()
                if not branch_rows:
                    st.info("Create a branch before managing branch users.")
                else:
                    branch_ids = [row[0] for row in branch_rows]
                    branch_name_map = {row[0]: row[1] for row in branch_rows}
                    selected_branch_id = st.selectbox(
                        "Select branch",
                        branch_ids,
                        format_func=lambda value: branch_name_map.get(value, value),
                        key="branch_users_admin_branch_select",
                    )
                    if selected_branch_id:
                        _render_branch_users_panel(
                            company_key,
                            selected_branch_id,
                            role,
                            panel_key_prefix="master_branch_users",
                            conn=branch_conn,
                        )
            except Exception as e:
                st.error(build_user_safe_error(e, role))
            finally:
                branch_conn.close()

    with tabs[2]:
        _render_staff_assignment_tab(company_key, role)

    with tabs[3]:
        _render_branch_performance_tab(company_key, role)


def _render_branch_performance_tab(company_key, role):
    st.subheader("Branch Performance Comparison")
    conn = get_connection()
    try:
        branches = conn.execute(
            """
            SELECT branch_id, branch_name,
                   COALESCE(NULLIF(TRIM(branch_code), ''), branch_name, branch_id) AS branch_code
            FROM branches
            WHERE company_key = ?
            ORDER BY branch_name
            """,
            (company_key,),
        ).fetchall()
        branch_options = [b[1] for b in branches]
        branch_code_map = {b[0]: b[2] for b in branches}
        if len(branches) < 2:
            st.info("At least two branches are required for comparison.")
            return

        st.info(
            "Branch-level financial comparison will be enabled after branch-aware financial reporting is completed."
        )
        col1, col2 = st.columns(2)
        with col1:
            branch1 = st.selectbox("Select Branch 1", branch_options, key="perf_branch1")
        with col2:
            branch2 = st.selectbox(
                "Select Branch 2",
                branch_options,
                index=1 if len(branch_options) > 1 else 0,
                key="perf_branch2",
            )
        if not branch1 or not branch2 or branch1 == branch2:
            st.info("Select two different branches to compare.")
            return

        branch1_id = next(b[0] for b in branches if b[1] == branch1)
        branch2_id = next(b[0] for b in branches if b[1] == branch2)

        ar1 = get_account_total(
            company_key,
            "Accounts Receivable",
            branch_id=branch1_id,
            balance_side="debit",
            conn=conn,
        )
        ar2 = get_account_total(
            company_key,
            "Accounts Receivable",
            branch_id=branch2_id,
            balance_side="debit",
            conn=conn,
        )
        inventory_summary = conn.execute(
            """
            SELECT COUNT(*) AS item_count, COALESCE(SUM(qty * cost_price), 0) AS inventory_value
            FROM inventory
            WHERE company_key = ?
            """,
            (company_key,),
        ).fetchone()
        inventory_items = int(inventory_summary[0] or 0)
        inventory_value = float(inventory_summary[1] or 0.0)

        st.markdown("### Branch Comparison Summary")
        summary_df = pd.DataFrame(
            [
                {
                    "Branch": branch1,
                    "Branch Code": branch_code_map.get(branch1_id, branch1),
                    "Accounts Receivable": ar1,
                },
                {
                    "Branch": branch2,
                    "Branch Code": branch_code_map.get(branch2_id, branch2),
                    "Accounts Receivable": ar2,
                },
            ]
        )
        st.dataframe(format_currency_dataframe(summary_df), use_container_width=True)

        st.markdown("### Consolidated Inventory & A/R Summary")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Inventory Items", f"{inventory_items:,}")
        col2.metric("Inventory Value", format_currency(inventory_value))
        col3.metric(f"A/R ({branch1})", format_currency(ar1))
        col4.metric(f"A/R ({branch2})", format_currency(ar2))
        st.markdown(
            "**Company-wide inventory values are consolidated. Branch-specific A/R is displayed for the selected branches.**"
        )
    except Exception as e:
        st.error(build_user_safe_error(e, role))
    finally:
        conn.close()

