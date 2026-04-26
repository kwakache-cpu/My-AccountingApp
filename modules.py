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
SUBSCRIPTION_PLANS = {
    "Basic": {
        "plan_name": "Basic",
        "amount": 50.0,
        "currency": "GHS",
        "duration_months": 1,
        "duration_days": None,
        "features": ["Core ERP access", "Single-company subscription", "Standard support"],
    },
    "Pro": {
        "plan_name": "Pro",
        "amount": 120.0,
        "currency": "GHS",
        "duration_months": 1,
        "duration_days": None,
        "features": ["Advanced accounting workflows", "Priority support", "Enhanced admin visibility"],
    },
    "Enterprise": {
        "plan_name": "Enterprise",
        "amount": 500.0,
        "currency": "GHS",
        "duration_months": 12,
        "duration_days": None,
        "features": ["Annual enterprise plan", "Multi-branch scaling", "Premium support"],
    },
}
ALL_ENTERPRISE_PERMISSIONS = {
    "view_dashboard",
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
    "close_cash_drawer",
    "view_cashier_closings",
    "manage_cashier_closings",
}
ROLE_NAME_ALIASES = {
    "Gatekeeper": "Dev",
    "Branch Admin": "Sub-Admin",
    "Manager": "Sub-Admin",
    "Branch Manager": "Sub-Admin",
    "Branch Bookkeeper": "Branch_Bookkeeper",
    "Cashier": "Staff",
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
}
ENTERPRISE_ROLE_PERMISSIONS = {
    "Dev": set(ALL_ENTERPRISE_PERMISSIONS),
    "Master Admin": {
        "view_dashboard",
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
        "close_cash_drawer",
        "view_cashier_closings",
        "manage_cashier_closings",
    },
    "Sub-Admin": {
        "view_dashboard",
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
        "close_cash_drawer",
        "view_cashier_closings",
        "manage_cashier_closings",
    },
    "Bookkeeper": {
        "view_dashboard",
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
        "close_cash_drawer",
        "view_cashier_closings",
        "manage_cashier_closings",
    },
    "Branch_Bookkeeper": {
        "view_dashboard",
        "create_customer",
        "create_supplier",
        "create_invoice",
        "create_bill",
        "receive_customer_payment",
        "make_supplier_payment",
        "post_accounting_document",
        "view_reports",
        "use_ai_assistant",
        "close_cash_drawer",
    },
    "Staff": {
        "view_dashboard",
        "create_customer",
        "create_supplier",
        "create_invoice",
        "receive_customer_payment",
        "view_reports",
        "close_cash_drawer",
    },
    "Demo": {"view_dashboard"},
}

# Setup Logger
logger = logging.getLogger(__name__)

# Import shared utilities from database
from database import (
    activate_company_subscription,
    create_company_record,
    ensure_company_trial_subscription,
    ensure_cashier_closings_schema,
    ensure_inventory_schema_integrity,
    force_backup_after_company_creation,
    get_firebase_service_account_info,
    get_connection,
    get_company_subscription_snapshot,
    get_recovery_source_diagnostics,
    get_subscription_billing_diagnostics,
    get_subscription_billing_summary,
    log_audit_action as database_log_audit_action,
)
from accounting_engine import (
    compare_legacy_and_journal_totals,
    get_account_total,
    get_ap_aging_report,
    get_ar_aging_report,
    get_chart_of_accounts_diagnostics,
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
)


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
        """
        INSERT INTO vouchers (company_key, branch_id, date, v_type, ledger, credit, reference_no, narration, payment_method, status, approval_status, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Posted', ?)
        """,
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
    return int(cursor.lastrowid)


def get_company_branches(company_key):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT branch_id, branch_name, location, branch_type FROM branches WHERE company_key = ? ORDER BY branch_name",
            (company_key,),
        ).fetchall()
        return [dict(row) for row in rows]
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
    return {plan_name: dict(plan_data) for plan_name, plan_data in SUBSCRIPTION_PLANS.items()}


def get_subscription_plan(plan_name):
    normalized = str(plan_name or "").strip()
    if normalized in SUBSCRIPTION_PLANS:
        return dict(SUBSCRIPTION_PLANS[normalized])
    return dict(SUBSCRIPTION_PLANS["Basic"])


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


def _upsert_license_payment_transaction(
    conn,
    *,
    reference,
    company_key,
    company_name,
    payer_email,
    payment_context,
    plan_name=None,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(reference) DO UPDATE SET
            company_key = excluded.company_key,
            company_name = excluded.company_name,
            payer_email = excluded.payer_email,
            payment_context = excluded.payment_context,
            plan_name = COALESCE(excluded.plan_name, license_payment_transactions.plan_name),
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
    subscription_months = max(int(metadata.get("subscription_months") or 0), 0)
    subscription_days = max(int(metadata.get("subscription_days") or 0), 0)
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

    expected_amount = int(round(float(amount or 0) * 100))
    if expected_amount <= 0:
        return {"ok": False, "reason": "Payment amount must be greater than zero."}

    metadata = {
        "company_key": company_key,
        "company_name": company_name,
        "plan_name": str(plan_name or "").strip() or None,
        "license_context": payment_context,
        "subscription_months": int(subscription_months or 0),
        "subscription_days": int(subscription_days or 0),
        "user_id": user_id,
        "user_email": user_email or email,
    }
    if phone_number:
        metadata["phone_number"] = phone_number
    if metadata_extra:
        metadata.update(metadata_extra)

    payload = {
        "email": str(email or "").strip(),
        "amount": expected_amount,
        "currency": config["currency"],
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
            expected_amount=expected_amount,
            currency=config["currency"],
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
            "currency": config["currency"],
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
        currency_ok = str(data.get("currency") or "").upper() == str(transaction_row["currency"] or config["currency"]).upper() == "GHS"
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
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


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
        payroll_rows = conn.execute(
            """
            SELECT created_at, emp_name, basic_salary, allowances, paye, net_salary, month, year, payment_status
            FROM payroll
            WHERE company_key = ? AND date(COALESCE(created_at, CURRENT_TIMESTAMP)) >= date(?) AND COALESCE(status, 'Active') != 'Void'
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (client_id, since_date),
        ).fetchall()
        records["payroll"] = [dict(row) for row in payroll_rows]

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
    return dict(row) if row is not None else {}


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
    return st.session_state.get("currency_symbol", "GH₵")


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
        row = conn.execute(
            "SELECT COALESCE(display_currency, base_currency, 'GHS') AS currency FROM system_settings WHERE id = 1"
        ).fetchone()
        return str(row["currency"] or BASE_CURRENCY) if row else BASE_CURRENCY
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
        row = conn.execute(
            "SELECT COALESCE(display_currency, 'GHS') AS display_currency, COALESCE(exchange_rate, 1.0) AS exchange_rate FROM system_settings WHERE id = 1"
        ).fetchone()
        if row:
            display_currency = str(row["display_currency"] or BASE_CURRENCY).upper()
            fallback_rate = BOG_DISPLAY_RATES.get(display_currency, 1.0)
            rate = float(row["exchange_rate"]) if row["exchange_rate"] not in (None, "") else fallback_rate
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
            inventory = conn.execute(
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
            journal_entries = conn.execute(
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
        tx_summary = [dict(row) for row in transactions] if transactions else []
        inventory_summary = [dict(row) for row in inventory] if inventory else []
        journal_summary = [dict(row) for row in journal_entries] if journal_entries else []
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
        account_rows = chart_conn.execute(
            """
            SELECT COALESCE(account_code, '') AS account_code,
                   COALESCE(name, account_name) AS account_name
            FROM chart_of_accounts
            ORDER BY COALESCE(account_code, ''), COALESCE(name, account_name)
            """
        ).fetchall()
        account_options = [
            f"{str(row['account_code']).strip()} - {str(row['account_name']).strip()}".strip(" -")
            for row in account_rows
            if str(row["account_name"] or "").strip()
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
        transactions_df = pd.read_sql_query(query, conn, params=params)
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
        f"INSERT INTO {table_name} (company_key, name, currency) VALUES (?, ?, 'GHS')",
        (company_key, party_name),
    )
    return int(cursor.lastrowid)


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
        """
        INSERT INTO customers (company_key, name, phone, email, customer_id, current_balance, currency)
        VALUES (?, ?, ?, ?, NULL, 0, 'GHS')
        """,
        (company_key, name.strip(), phone.strip(), email.strip()),
    )
    customer_row_id = int(cursor.lastrowid)
    conn.execute(
        "UPDATE customers SET customer_id = COALESCE(NULLIF(customer_id, ''), ?) WHERE id = ? AND company_key = ?",
        (f"CUST-{customer_row_id:06d}", customer_row_id, company_key),
    )
    return customer_row_id


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
    try:
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
        conn.execute(
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
    if receipt_data.get("payment_method") == "Cash":
        lines.append(f"Amount Tendered: {format_currency(float(receipt_data.get('amount_tendered') or 0.0))}")
        lines.append(f"Change Due: {format_currency(float(receipt_data.get('change_due') or 0.0))}")
    elif receipt_data.get("payment_reference"):
        lines.append(f"Reference: {receipt_data['payment_reference']}")
    return "\n".join(lines)


def _build_receipt_html(receipt_data):
    rows = []
    for item in receipt_data.get("items", []):
        rows.append(
            f"<tr>"
            f"<td style='padding: 0.4rem 0.2rem; border-bottom:1px dashed #ddd;'>{item.get('name') or ''}</td>"
            f"<td style='padding: 0.4rem 0.2rem; border-bottom:1px dashed #ddd; text-align:center;'>{int(item.get('qty') or 0)}</td>"
            f"<td style='padding: 0.4rem 0.2rem; border-bottom:1px dashed #ddd; text-align:right;'>{format_currency(float(item.get('price') or 0.0))}</td>"
            f"<td style='padding: 0.4rem 0.2rem; border-bottom:1px dashed #ddd; text-align:right;'>{format_currency(float(item.get('line_total') or 0.0))}</td>"
            f"</tr>"
        )
    payment_reference_html = ""
    if receipt_data.get("payment_reference"):
        payment_reference_html = (
            f"<div style='font-size:0.8rem; color:#444;'>Reference: {receipt_data['payment_reference']}</div>"
        )
    amount_tendered_html = ""
    change_due_html = ""
    if receipt_data.get("payment_method") == "Cash":
        amount_tendered_html = (
            f"<div style='display:flex; justify-content:space-between;'><span>Amount Tendered</span><strong>{format_currency(float(receipt_data.get('amount_tendered') or 0.0))}</strong></div>"
        )
        change_due_html = (
            f"<div style='display:flex; justify-content:space-between;'><span>Change Due</span><strong>{format_currency(float(receipt_data.get('change_due') or 0.0))}</strong></div>"
        )
    return f"""
    <div class='receipt-preview printable' style='font-family: Arial, sans-serif; color: #111; max-width: 360px; margin: 0 auto;'>
        <div style='text-align:center; margin-bottom:0.75rem;'>
            <h3 style='margin:0;'>{receipt_data.get("company_name") or ""}</h3>
            <div style='font-size:0.85rem; color:#555;'>{receipt_data.get("branch_name") or "Main Branch"}</div>
            <div style='font-size:0.8rem; margin-top:0.3rem;'>Receipt: {receipt_data.get("receipt_number") or "N/A"}</div>
            <div style='font-size:0.8rem;'>Date: {receipt_data.get("sale_datetime") or ""}</div>
            <div style='font-size:0.8rem;'>Cashier: {receipt_data.get("cashier") or ""}</div>
        </div>
        <table style='width:100%; border-collapse: collapse; margin-bottom:0.75rem; font-size:0.85rem;'>
            <thead>
                <tr>
                    <th style='text-align:left; padding:0.35rem 0.2rem; border-bottom:2px solid #333;'>Item</th>
                    <th style='text-align:center; padding:0.35rem 0.2rem; border-bottom:2px solid #333;'>Qty</th>
                    <th style='text-align:right; padding:0.35rem 0.2rem; border-bottom:2px solid #333;'>Unit</th>
                    <th style='text-align:right; padding:0.35rem 0.2rem; border-bottom:2px solid #333;'>Total</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        <div style='border-top:1px dashed #999; padding-top:0.6rem; font-size:0.85rem;'>
            <div style='display:flex; justify-content:space-between;'><span>Subtotal</span><strong>{format_currency(float(receipt_data.get("subtotal") or 0.0))}</strong></div>
            <div style='display:flex; justify-content:space-between;'><span>Discount</span><strong>{format_currency(float(receipt_data.get("discount_total") or 0.0))}</strong></div>
            <div style='display:flex; justify-content:space-between;'><span>Tax</span><strong>{format_currency(float(receipt_data.get("tax_total") or 0.0))}</strong></div>
            <div style='display:flex; justify-content:space-between; font-size:1rem; margin-top:0.35rem;'><span>Grand Total</span><strong>{format_currency(float(receipt_data.get("grand_total") or 0.0))}</strong></div>
            <div style='margin-top:0.5rem; font-size:0.8rem;'>Payment Method: {receipt_data.get("payment_method") or ""}</div>
            {payment_reference_html}
            {amount_tendered_html}
            {change_due_html}
        </div>
    </div>
    """


def _get_pos_cashier_identity(role):
    current_user = st.session_state.get("user", {}) if isinstance(st.session_state.get("user", {}), dict) else {}
    return (
        str(current_user.get("role") or role or "").strip()
        or str(current_user.get("login_key") or "").strip()
        or str(current_user.get("full_name") or "").strip()
        or "Unknown"
    )


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


def _lookup_inventory_by_barcode(conn, company_key, barcode_value):
    return conn.execute(
        """
        SELECT id, item_name, item_code, category, qty, price, cost_price, barcode
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
        """
        SELECT id, item_name, item_code, category, qty, price, cost_price, barcode
        FROM inventory
        WHERE company_key = ?
          AND (
              barcode = ?
              OR item_code = ?
              OR LOWER(item_name) = LOWER(?)
          )
        ORDER BY item_name
        LIMIT 1
        """,
        (company_key, normalized_value, normalized_value, normalized_value),
    ).fetchone()
    if exact_match:
        if str(exact_match["barcode"] or "").strip() == normalized_value:
            return exact_match, "barcode", "in_company"
        if str(exact_match["item_code"] or "").strip() == normalized_value:
            return exact_match, "item_code", "in_company"
        return exact_match, "item_name", "in_company"

    fallback_match = conn.execute(
        """
        SELECT id, item_name, item_code, category, qty, price, cost_price, barcode
        FROM inventory
        WHERE company_key = ?
          AND (
              LOWER(item_name) LIKE LOWER(?)
              OR LOWER(COALESCE(item_code, '')) LIKE LOWER(?)
              OR COALESCE(barcode, '') LIKE ?
          )
        ORDER BY item_name
        LIMIT 1
        """,
        (company_key, f"%{normalized_value}%", f"%{normalized_value}%", f"%{normalized_value}%"),
    ).fetchone()
    if fallback_match:
        return fallback_match, "manual_search", "in_company"

    other_company_match = conn.execute(
        """
        SELECT id, item_name, item_code, category, qty, price, cost_price, barcode, company_key
        FROM inventory
        WHERE company_key <> ?
          AND (
              barcode = ?
              OR item_code = ?
              OR LOWER(item_name) = LOWER(?)
              OR LOWER(item_name) LIKE LOWER(?)
              OR LOWER(COALESCE(item_code, '')) LIKE LOWER(?)
              OR COALESCE(barcode, '') LIKE ?
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
        """
        SELECT id, item_name, item_code, category, qty, price, cost_price, barcode
        FROM inventory
        WHERE company_key = ?
          AND qty > 0
          AND (
              LOWER(item_name) LIKE LOWER(?)
              OR LOWER(COALESCE(item_code, '')) LIKE LOWER(?)
              OR COALESCE(barcode, '') LIKE ?
          )
        ORDER BY item_name
        LIMIT 25
        """,
        (company_key, f"%{normalized_value}%", f"%{normalized_value}%", f"%{normalized_value}%"),
    ).fetchall()


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


def _add_item_to_pos_cart(company_key, item_row):
    cart_key = f"pos_cart_{company_key}"
    cart = st.session_state.setdefault(cart_key, [])
    item_id = int(item_row["id"])
    item_code = item_row["item_code"] if hasattr(item_row, "keys") and "item_code" in item_row.keys() else item_row.get("item_code", "")
    tax_rate = item_row["tax_rate"] if hasattr(item_row, "keys") and "tax_rate" in item_row.keys() else item_row.get("tax_rate", 0.0)
    for existing_line in cart:
        if int(existing_line["inventory_item_id"]) == item_id:
            existing_line["qty"] += 1
            existing_line["line_total"] = max(
                (existing_line["qty"] * existing_line["price"]) - float(existing_line.get("line_discount") or 0.0),
                0.0,
            )
            return existing_line

    new_line = {
        "inventory_item_id": item_id,
        "name": item_row["item_name"],
        "item_code": item_code or "",
        "barcode": item_row["barcode"] or "",
        "price": float(item_row["price"] or 0.0),
        "cost_price": float(item_row["cost_price"] or 0.0),
        "tax_rate": float(tax_rate or 0.0),
        "available_qty": float(item_row["qty"] or 0.0),
        "qty": 1,
        "line_discount": 0.0,
        "line_total": float(item_row["price"] or 0.0),
    }
    cart.append(new_line)
    return new_line


def _recalculate_pos_line(line):
    qty = max(int(line.get("qty") or 0), 1)
    price = max(float(line.get("price") or 0.0), 0.0)
    gross = qty * price
    discount = max(float(line.get("line_discount") or 0.0), 0.0)
    if discount > gross:
        discount = gross
    line["qty"] = qty
    line["price"] = price
    line["line_discount"] = discount
    line["line_total"] = gross - discount
    return line


def _get_pos_cart_summary(company_key):
    cart = st.session_state.setdefault(f"pos_cart_{company_key}", [])
    item_count = int(sum(int(line.get("qty") or 0) for line in cart))
    subtotal = 0.0
    discount_total = 0.0
    tax_total = 0.0
    for line in cart:
        qty = max(float(line.get("qty") or 0.0), 0.0)
        price = max(float(line.get("price") or 0.0), 0.0)
        gross = qty * price
        discount = max(float(line.get("line_discount") or 0.0), 0.0)
        discount = min(discount, gross)
        taxable_base = gross - discount
        subtotal += gross
        discount_total += discount
        tax_total += taxable_base * (max(float(line.get("tax_rate") or 0.0), 0.0) / 100.0)
    grand_total = round((subtotal - discount_total) + tax_total, 2)
    return {
        "item_count": item_count,
        "line_count": len(cart),
        "subtotal": round(subtotal, 2),
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
        amount = st.number_input("Amount (GH₵)", min_value=0.0, value=0.0)
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

    with st.form("accounts_payable_form"):
        supplier_name = st.text_input("Supplier Name")
        bill_category = st.selectbox("Bill Posting", ["Expense", "Inventory"])
        amount = st.number_input("Amount (GH₵)", min_value=0.0, value=0.0)
        status = st.selectbox("Bill Status", ["Pending", "Received"])
        posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=3)
        description = st.text_input("Description")
        payable_date = st.date_input("Bill Date", value=datetime.now().date())
        submitted = st.form_submit_button("Create Bill")
        if submitted and supplier_name and amount > 0:
            supplier_id = _get_or_create_party(conn, "suppliers", company_key, supplier_name.strip())
            bill_number = f"BILL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            posting_account_name = "Inventory" if bill_category == "Inventory" else "Purchases"
            posting_account_type = "Asset" if bill_category == "Inventory" else "Expense"
            cursor = conn.execute(
                """
                INSERT INTO bills (company_key, supplier_id, bill_number, bill_date, due_date, status, approval_status, amount, currency, description, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                """,
                (
                    company_key,
                    supplier_id,
                    bill_number,
                    payable_date.isoformat(),
                    payable_date.isoformat(),
                    status,
                    posting_state,
                    amount,
                    description.strip() or f"{bill_category} bill",
                    role,
                ),
            )
            bill_id = int(cursor.lastrowid)
            if posting_state == "Posted":
                post_journal_entry(
                    company_key=company_key,
                    date=payable_date,
                    description=description.strip() or f"{bill_category} bill for {supplier_name.strip()}",
                    reference=bill_number,
                    lines=[
                        {
                            "account_id": get_account_id(conn, posting_account_name, posting_account_type),
                            "debit": float(amount),
                            "credit": 0,
                        },
                        {
                            "account_id": get_account_id(conn, "Accounts Payable", "Liability"),
                            "debit": 0,
                            "credit": float(amount),
                        },
                    ],
                    created_by=role,
                    branch_id=branch_id,
                    supplier_id=supplier_id,
                    source_module="Accounts Payable",
                    source_table="bills",
                    source_type="Bill",
                    source_id=bill_id,
                    approval_status="Posted",
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
        st.subheader("Create Bill")
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

        st.markdown(f"**Total Amount: GH₵ {total_amount:.2f}**")

        with st.form("create_bill_form"):
            supplier_name = st.selectbox("Supplier", supplier_options)
            bill_date = st.date_input("Bill Date", value=datetime.now().date())
            bill_category = st.selectbox("Bill Posting", ["Expense", "Inventory"])
            posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=1)
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
                posting_account_name = "Inventory" if bill_category == "Inventory" else "Purchases"
                posting_account_type = "Asset" if bill_category == "Inventory" else "Expense"

                cursor = conn.execute(
                    """
                    INSERT INTO bills (company_key, supplier_id, bill_number, bill_date, due_date, status, approval_status, amount, currency, description, created_by)
                    VALUES (?, ?, ?, ?, ?, 'Pending', ?, ?, 'GHS', ?, ?)
                    """,
                    (
                        company_key,
                        supplier_id,
                        bill_number,
                        bill_date.isoformat(),
                        bill_date.isoformat(),
                        posting_state,
                        total_amount,
                        description.strip() or f"{bill_category} bill",
                        role,
                    ),
                )
                bill_id = int(cursor.lastrowid)

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
                    post_journal_entry(
                        company_key=company_key,
                        date=bill_date,
                        description=description.strip() or f"{bill_category} bill for {supplier_name}",
                        reference=bill_number,
                        lines=[
                            {
                                "account_id": get_account_id(conn, posting_account_name, posting_account_type),
                                "debit": total_amount,
                                "credit": 0,
                            },
                            {
                                "account_id": get_account_id(conn, "Accounts Payable", "Liability"),
                                "debit": 0,
                                "credit": total_amount,
                            },
                        ],
                        created_by=role,
                        branch_id=branch_id,
                        supplier_id=supplier_id,
                        source_module="Create Bill",
                        source_table="bills",
                        source_type="Bill",
                        source_id=bill_id,
                        approval_status="Posted",
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
        balance = st.number_input("Opening Balance (GH₵)", value=0.0)
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

    rows = conn.execute("SELECT account_name, account_type, balance FROM chart_of_accounts ORDER BY account_name").fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["Account Name", "Account Type", "Balance"])
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
        amount = st.number_input("Amount (GH₵)", min_value=0.0, value=0.0)
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

    plan_labels = list(SUBSCRIPTION_PLANS.keys())
    selected_plan_name = st.selectbox("Choose Subscription Plan", plan_labels, key=f"subscription_plan_{company_key}")
    selected_plan = get_subscription_plan(selected_plan_name)
    st.caption(
        "Plan amount: GH₵ {amount:,.2f} | Duration: {duration}".format(
            amount=float(selected_plan["amount"]),
            duration=(
                f"{selected_plan['duration_months']} month(s)"
                if selected_plan.get("duration_months")
                else f"{selected_plan.get('duration_days', 0)} day(s)"
            ),
        )
    )
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
        if not company_email:
            st.warning("A contact email is required on the company profile before starting subscription payment.")
        else:
            reference = _generate_paystack_reference("SUB")
            payment_result = initialize_paystack_payment(
                company_email,
                selected_plan["amount"],
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
            selected_plan_name = st.selectbox("Subscription Plan", list(SUBSCRIPTION_PLANS.keys()), index=0)

        selected_plan = get_subscription_plan(selected_plan_name)
        amount = float(selected_plan["amount"])

        st.caption(
            "7-day trial is created immediately. Selected plan: {plan} | Amount Due: GH₵ {amount:,.2f}".format(
                plan=selected_plan_name,
                amount=amount,
            )
        )
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
    st.header("📦 Inventory Management")
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
            st.rerun()

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
                query = """
                    SELECT id, item_code, barcode, item_name, category, description, brand, supplier_name,
                           expiry_date, batch_number, vat_category, unit, min_stock_level, tax_rate,
                           warehouse_location, is_active, opening_balance, qty as quantity,
                           price as unit_price, cost_price, (qty * cost_price) as total_value
                    FROM inventory WHERE company_key = ?
                """
                df = pd.read_sql_query(query, conn, params=(company_key,))
            conn.close()

            if not df.empty:
                st.dataframe(format_currency_dataframe(df), use_container_width=True)
                excel_bin = get_excel_bin(df)
                if excel_bin:
                    st.download_button(
                        "📥 Export to Excel",
                        data=excel_bin,
                        file_name=f"inventory_{company_key}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"inventory_export_{company_key}",
                    )
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Items", len(df))
                col2.metric(f"Total Value ({get_currency_symbol()})", format_currency(df["total_value"].sum()))
                col3.metric("Low Stock Alerts", len(df[df['quantity'] < 10]))
                if role in ("Master Admin", "Bookkeeper", "Branch_Bookkeeper", "Sub-Admin") and "id" in df.columns:
                    st.markdown("Edit Stock Item")
                    selected_edit_key = f"inventory_edit_selected_{company_key}"
                    delete_confirm_key = f"inventory_delete_confirm_{company_key}"
                    for _, stock_row in df.iterrows():
                        name_col, edit_col, delete_col = st.columns([4, 1, 1])
                        name_col.caption(
                            f"{stock_row['item_name']} | Barcode {stock_row.get('barcode') or 'N/A'} | Qty {float(stock_row['quantity']):,.2f} | "
                            f"Sell GH₵ {float(stock_row['unit_price']):,.2f}"
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
                            _clear_streamlit_state(delete_confirm_key, selected_edit_key)
                            st.session_state[delete_success_key] = True
                            st.rerun()
                        if cancel_col.button("Cancel", key=f"inventory_delete_cancel_btn_{company_key}_{delete_item_id}"):
                            _clear_streamlit_state(delete_confirm_key)
                            st.rerun()
                    edit_item_id = st.session_state.get(selected_edit_key, int(df["id"].iloc[0]))
                    edit_row = df.loc[df["id"] == edit_item_id].iloc[0]
                    with st.form(f"inventory_edit_form_{company_key}_{edit_item_id}", clear_on_submit=True):
                        edit_item_code = st.text_input("Item Code (SKU)", value=str(edit_row.get("item_code") or ""))
                        edit_barcode = st.text_input("Barcode", value=str(edit_row.get("barcode") or ""))
                        edit_unit = st.text_input("Unit", value=str(edit_row.get("unit") or "pcs"))
                        edit_category = st.text_input("Category", value=str(edit_row["category"] or ""))
                        edit_description = st.text_area("Description", value=str(edit_row.get("description") or ""))
                        edit_brand = st.text_input("Brand", value=str(edit_row.get("brand") or ""))
                        edit_supplier_name = st.text_input("Supplier Name", value=str(edit_row.get("supplier_name") or ""))
                        existing_expiry_value = str(edit_row.get("expiry_date") or "").strip()
                        try:
                            default_expiry_date = (
                                datetime.fromisoformat(existing_expiry_value).date()
                                if existing_expiry_value
                                else None
                            )
                        except ValueError:
                            default_expiry_date = None
                        edit_expiry_enabled = st.checkbox(
                            "Set Expiry Date",
                            value=default_expiry_date is not None,
                            key=f"inventory_edit_expiry_enabled_{company_key}_{edit_item_id}",
                        )
                        edit_expiry_date = st.date_input(
                            "Expiry Date",
                            value=default_expiry_date or datetime.now().date(),
                            key=f"inventory_edit_expiry_date_{company_key}_{edit_item_id}",
                            disabled=not edit_expiry_enabled,
                        )
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
                    stock_options = [
                        (
                            f"{row['item_name']} | Barcode {row['barcode'] or 'N/A'} | Available {float(row['qty'] or 0):,.2f}",
                            int(row["id"]),
                        )
                        for row in stock_items
                    ]
                    option_labels = [label for label, _ in stock_options]
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
                                movement_cursor = conn.execute(
                                    """
                                    INSERT INTO stock_movements (
                                        company_key, branch_id, inventory_item_id, item_name,
                                        movement_type, quantity, reason, previous_qty, new_qty,
                                        status, approval_status, created_by
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        company_key,
                                        branch_id,
                                        selected_item_id,
                                        selected_item["item_name"],
                                        movement_type,
                                        movement_qty,
                                        reason,
                                        current_qty,
                                        new_qty,
                                        movement_status,
                                        movement_status,
                                        role,
                                    ),
                                )
                                movement_id = int(movement_cursor.lastrowid)
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
                                st.rerun()

                    movement_rows = conn.execute(
                        """
                        SELECT created_at, item_name, movement_type, quantity, reason, previous_qty, new_qty, created_by
                        FROM stock_movements
                        WHERE company_key = ?
                        ORDER BY created_at DESC, id DESC
                        LIMIT 25
                        """,
                        (company_key,),
                    ).fetchall()
                    if movement_rows:
                        st.markdown("Recent Stock Movements")
                        movement_df = pd.DataFrame(
                            movement_rows,
                            columns=["Date", "Item", "Type", "Qty", "Reason", "Previous Qty", "New Qty", "Recorded By"],
                        )
                        st.dataframe(movement_df, use_container_width=True, hide_index=True)
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
        with st.form("add_inventory_form", clear_on_submit=True):
            item_code = st.text_input("Item Code (SKU)")
            barcode = st.text_input("New Barcode", value=str(st.session_state.get(inventory_new_barcode_key, "") or ""))
            item_name = st.text_input("Item Name")
            unit = st.text_input("Unit", value="pcs")
            category = st.text_input("Category")
            description = st.text_area("Description")
            brand = st.text_input("Brand")
            supplier_name = st.text_input("Supplier Name")
            expiry_enabled = st.checkbox("Set Expiry Date", key=f"inventory_expiry_enabled_{company_key}")
            expiry_date = st.date_input(
                "Expiry Date",
                value=datetime.now().date(),
                key=f"inventory_expiry_date_{company_key}",
                disabled=not expiry_enabled,
            )
            batch_number = st.text_input("Batch Number")
            vat_category = st.text_input("VAT Category")
            transaction_date = st.date_input("Transaction Date", value=datetime.now().date(), key=f"inventory_transaction_date_{company_key}")
            opening_stock = st.number_input("Opening Stock Quantity", min_value=0.0, value=0.0)
            min_stock_level = st.number_input("Reorder Level", min_value=0.0, value=10.0)
            funding_source = st.selectbox("Inventory Funding Source", ["Cash", "Bank", "Mobile Money", "Accounts Payable"])
            price = st.number_input(f"Selling Price ({st.session_state.currency_symbol})", min_value=0.0, value=0.0)
            cost_price = st.number_input(f"Cost Price ({st.session_state.currency_symbol})", min_value=0.0, value=0.0)
            tax_rate = st.number_input("Tax Rate", min_value=0.0, value=0.0)
            warehouse_location = st.text_input("Shelf / Location")
            is_active = st.checkbox("Active", value=True)
            submitted = st.form_submit_button("➕ Add New Item")
            if submitted and item_name:
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
                            expiry_date.isoformat() if expiry_enabled else None,
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
                    st.session_state.pop(inventory_new_barcode_key, None)
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
                amount = st.number_input("Amount (GH₵)", min_value=0.0, step=0.01)
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
        rows = conn.execute(
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
            """
        ).fetchall()
        if rows:
            df = pd.DataFrame(
                rows,
                columns=[
                    "Account Code",
                    "Account Name",
                    "Account Type",
                    "Posting Allowed",
                    "Control Account",
                    "Manual Posting Allowed",
                    "Active",
                ],
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
def show_company_setup(company_key, company_name, role):
    st.header("⚙️ System Configuration")
    if not require_permission(role, "manage_company", action_label="manage company settings", company_key=company_key):
        return
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
                try:
                    conn = get_connection()
                    branch_count = conn.execute("SELECT COUNT(*) FROM branches WHERE company_key = ?", (company_key,)).fetchone()[0] or 0
                    max_branches_row = conn.execute("SELECT COALESCE(max_branches, 1) FROM companies WHERE key = ?", (company_key,)).fetchone()
                    max_branches = int(max_branches_row[0]) if max_branches_row and max_branches_row[0] is not None else 1
                    branches = conn.execute(
                        "SELECT branch_id, branch_name, location, branch_access_key, branch_manager, created_at FROM branches WHERE company_key = ? ORDER BY created_at DESC",
                        (company_key,),
                    ).fetchall()
                    conn.close()
                except Exception as exc:
                    st.error(build_user_safe_error(exc, role))
                    branches = []
                    branch_count = 0
                    max_branches = 1

                if branches:
                    branch_df = pd.DataFrame(branches, columns=["Branch ID", "Branch Name", "Location", "Access Key", "Manager", "Created At"])
                    st.dataframe(branch_df, use_container_width=True)

                st.info(f"Current Branches: {branch_count} / {max_branches}")
                if branch_count >= max_branches:
                    st.warning("You have reached the maximum branch deployment limit. Contact your developer or system administrator to increase your limit.")
                else:
                    with st.form("branch_deployment_form"):
                        branch_name = st.text_input("Branch Name", key="deploy_branch_name")
                        location = st.text_input("Location / Physical Address", key="deploy_branch_location")
                        branch_manager = st.text_input("Branch Manager Name", key="deploy_branch_manager")
                        branch_type = st.selectbox("Branch Type", ["Retail", "Warehouse", "Office", "Other"], key="deploy_branch_type")
                        if st.form_submit_button("Deploy Branch"):
                            if not require_permission(
                                role,
                                "manage_branches",
                                action_label="manage branches",
                                company_key=company_key,
                            ):
                                return
                            if not branch_name.strip():
                                st.error("Enter a branch name.")
                            else:
                                conn = get_connection()
                                try:
                                    branch_id = f"{company_key}-{branch_name.replace(' ', '_').lower()}"
                                    existing_branch = conn.execute("SELECT branch_access_key FROM branches WHERE branch_id = ?", (branch_id,)).fetchone()
                                    if existing_branch and existing_branch[0]:
                                        branch_access_key = existing_branch[0]
                                    else:
                                        branch_access_key = f"{branch_id}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=12))}"
                                    conn.execute(
                                        """
                                        INSERT OR REPLACE INTO branches
                                        (branch_id, company_key, branch_name, location, branch_type, branch_access_key, branch_manager)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """,
                                        (
                                            branch_id,
                                            company_key,
                                            branch_name,
                                            location or "",
                                            branch_type,
                                            branch_access_key,
                                            branch_manager or "Branch Manager",
                                        ),
                                    )
                                    hashed_password = _hash_security_answer("default123")
                                    conn.execute(
                                        """
                                        INSERT OR IGNORE INTO users
                                        (company_key, branch_id, full_name, login_key, password_hash, role, status)
                                        VALUES (?, ?, ?, ?, ?, ?, 'Active')
                                        """,
                                        (
                                            company_key,
                                            branch_id,
                                            branch_manager or "Branch Manager",
                                            branch_access_key,
                                            hashed_password,
                                            "Branch_Bookkeeper",
                                        ),
                                    )
                                    conn.commit()
                                    log_audit_action(
                                        conn,
                                        company_key,
                                        role,
                                        f"Deployed branch {branch_name}",
                                        "Branch Deployment",
                                        branch_id=branch_id,
                                    )
                                    st.success(f"Branch {branch_name} deployed successfully. Access Key: {branch_access_key}")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(build_user_safe_error(exc, role))
                                finally:
                                    conn.close()

                st.markdown("---")
                st.subheader("Staff Management")
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
                            conn=conn,
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
                                existing_key = conn.execute(
                                    "SELECT 1 FROM users WHERE login_key = ? LIMIT 1",
                                    (manual_login_key.strip(),),
                                ).fetchone()
                                if existing_key:
                                    st.error("This staff login key already exists. Choose a different manual key.")
                                    return
                                user_id = _generate_user_id(company_key, staff_name, manual_login_key)
                                conn.execute(
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
                                conn.commit()
                                log_audit_action(
                                    conn,
                                    company_key,
                                    role,
                                    "Staff Login Created",
                                    "Company Setup",
                                    f"{staff_name.strip()} created as {staff_role} with user_id {user_id[:12]}...",
                                )
                                st.success("Staff login created successfully.")
                            except Exception as exc:
                                st.error(build_user_safe_error(exc, role))

                users = conn.execute(
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
    st.header("🛒 Point of Sale")
    receipt_key = f"pos_receipt_{company_key}"
    last_receipt_data_key = f"pos_last_receipt_data_{company_key}"
    checkout_complete_key = f"pos_checkout_complete_{company_key}"
    pos_success_key = f"pos_sale_success_{company_key}"
    void_success_key = f"pos_void_success_{company_key}"
    pos_message_key = f"pos_message_{company_key}"
    pos_scan_beep_key = f"pos_scan_beep_{company_key}"
    pos_scan_input_key = "pos_barcode_input"
    pos_pending_scan_key = f"pos_pending_scan_{company_key}"
    pos_product_search_key = f"pos_product_search_{company_key}"
    pos_product_select_key = f"pos_product_select_{company_key}"
    cart_key = f"pos_cart_{company_key}"
    if role == "Demo":
        _demo_notice()
        st.info("Demo POS: Select items and process a mock sale.")
        demo_items = ["Product A - GH₵ 120.00", "Product B - GH₵ 75.00", "Product C - GH₵ 200.00"]
        selected = st.multiselect("Select Items", demo_items)
        if selected:
            st.success(f"Demo sale: {len(selected)} item(s) selected. Total: GH₵ {len(selected) * 120:.2f}")
        return

    if st.session_state.get(pos_success_key):
        _trigger_scan_feedback(pos_message_key, "Sale processed successfully.")
        st.session_state.pop(pos_success_key, None)
    if st.session_state.get(void_success_key):
        _trigger_scan_feedback(pos_message_key, "Transaction voided")
        st.session_state.pop(void_success_key, None)

    _render_flash_message(pos_message_key, pos_scan_beep_key)

    try:
        conn = get_connection()
        ensure_cashier_closings_schema(conn)
        company_row = conn.execute("SELECT name, barcode_input_source FROM companies WHERE key = ?", (company_key,)).fetchone()
        active_branch_id = st.session_state.get("active_branch_id")
        branch_row = None
        if active_branch_id:
            branch_row = conn.execute(
                "SELECT branch_name FROM branches WHERE company_key = ? AND branch_id = ?",
                (company_key, active_branch_id),
            ).fetchone()
        items = conn.execute(
            "SELECT id, item_name, item_code, barcode, price, cost_price, tax_rate, qty FROM inventory WHERE company_key = ? AND qty > 0",
            (company_key,),
        ).fetchall()
        customers = get_customer_balances(company_key, conn=conn)
        conn.close()

        company_label = company_row[0] if company_row else company_name
        branch_label = branch_row["branch_name"] if branch_row and "branch_name" in branch_row.keys() else ""
        barcode_input_source = company_row[1] if company_row and company_row[1] else "Keyboard Entry"
        items_df = (
            pd.DataFrame(items, columns=["ID", "Item Name", "Item Code", "Barcode", "Price", "Cost Price", "Tax Rate", "Qty"])
            if items
            else pd.DataFrame()
        )
        receipt_html_key = f"pos_receipt_html_{company_key}"
        receipt_print_trigger_key = f"pos_receipt_print_trigger_{company_key}"
        do_print_key = "do_print"

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

        st.caption(f"Barcode input mode: {barcode_input_source}")
        scanner_cart_summary = _get_pos_cart_summary(company_key)
        scan_summary_col1, scan_summary_col2, scan_summary_col3 = st.columns([1, 1, 1])
        scan_summary_col1.metric("Cart Items", scanner_cart_summary["item_count"])
        scan_summary_col2.metric("Cart Total", format_currency(scanner_cart_summary["grand_total"]))
        if scan_summary_col3.button("Quick Clear Cart", key=f"pos_quick_clear_cart_{company_key}", use_container_width=True):
            st.session_state[cart_key] = []
            st.session_state[checkout_complete_key] = False
            _trigger_scan_feedback(pos_message_key, "Cart cleared.", "info")
            st.rerun()

        with st.form(key=f"pos_form_{company_key}", clear_on_submit=True):
            st.text_input(
                "Scan Barcode",
                key=pos_scan_input_key,
                placeholder="Scan barcode and press Enter",
            )
            _focus_text_input("Scan Barcode")
            if barcode_input_source == "Camera Scanner":
                _render_camera_scanner(f"pos_{company_key}", pos_pending_scan_key)
            submitted = st.form_submit_button("Scan Barcode")
            if submitted:
                pending_pos_barcode = str(st.session_state.get(pos_scan_input_key, "") or "").strip()
                if pending_pos_barcode:
                    conn = None
                    try:
                        conn = get_connection()
                        matched_item, lookup_source, match_scope = _lookup_inventory_for_pos(conn, company_key, pending_pos_barcode)
                        if matched_item and match_scope == "in_company" and float(matched_item["qty"] or 0) > 0:
                            st.session_state[checkout_complete_key] = False
                            st.session_state.pop(receipt_key, None)
                            st.session_state.pop(receipt_html_key, None)
                            cart_line = _add_item_to_pos_cart(company_key, matched_item)
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
                        elif matched_item and match_scope == "in_company":
                            logger.info(
                                "POS scanner found item '%s' with zero stock for company %s",
                                matched_item["item_name"],
                                company_key,
                            )
                            _trigger_scan_feedback(
                                pos_message_key,
                                "Product found but stock is zero. Please add stock before sale.",
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
                        st.rerun()

        st.subheader("Manual Item Entry")
        manual_item_name = st.text_input("New Item Name", key=f"manual_pos_item_{company_key}")
        manual_price = st.number_input(f"Manual Price ({st.session_state.currency_symbol})", min_value=0.0, value=0.0, key=f"manual_pos_price_{company_key}")
        manual_qty = st.number_input("Quantity", min_value=1, value=1, key=f"manual_pos_qty_{company_key}")
        if st.button("Add Manual Item", key=f"pos_add_manual_{company_key}"):
            if manual_item_name and float(manual_price) > 0:
                st.session_state[checkout_complete_key] = False
                st.session_state.pop(receipt_key, None)
                st.session_state.pop(receipt_html_key, None)
                cart = st.session_state.setdefault(cart_key, [])
                cart.append(
                    {
                        "inventory_item_id": None,
                        "name": manual_item_name.strip(),
                        "item_code": "",
                        "barcode": "",
                        "price": float(manual_price),
                        "cost_price": 0.0,
                        "tax_rate": 0.0,
                        "available_qty": None,
                        "qty": int(manual_qty),
                        "line_discount": 0.0,
                        "line_total": int(manual_qty) * float(manual_price),
                    }
                )
                _trigger_scan_feedback(pos_message_key, f"Added manual item {manual_item_name.strip()} to the cart.")
                st.rerun()
            else:
                st.warning("Enter a valid manual item and price before adding it.")

        with st.container():
            item_mode = st.radio(
                "Item Entry Mode",
                ["From Stock", "Manual Entry"],
                horizontal=True,
                key=f"pos_item_mode_{company_key}",
            )
            if item_mode == "From Stock":
                if items_df.empty:
                    st.info("No stock available for sale. Switch to Manual Entry to continue.")
                else:
                    product_search_term = st.text_input(
                        "Search Product",
                        key=pos_product_search_key,
                        placeholder="Search by name, barcode, or item code",
                    ).strip()
                    manual_search_options = []
                    if product_search_term:
                        conn = None
                        try:
                            conn = get_connection()
                            manual_search_options = _search_inventory_for_pos(conn, company_key, product_search_term)
                        except Exception as exc:
                            st.warning(build_user_safe_error(exc, role))
                        finally:
                            if conn:
                                conn.close()
                        if not manual_search_options:
                            st.info("No matching stock items found for that search.")
                    if manual_search_options:
                        manual_option_labels = [
                            "{name} | Code {item_code} | Barcode {barcode} | Qty {qty:,.2f}".format(
                                name=row["item_name"],
                                item_code=row["item_code"] or "N/A",
                                barcode=row["barcode"] or "N/A",
                                qty=float(row["qty"] or 0.0),
                            )
                            for row in manual_search_options
                        ]
                        selected_search_label = st.selectbox(
                            "Manual Product Search Results",
                            manual_option_labels,
                            key=pos_product_select_key,
                        )
                        if st.button("Add Search Result", key=f"pos_add_search_result_{company_key}"):
                            selected_search_row = manual_search_options[manual_option_labels.index(selected_search_label)]
                            st.session_state[checkout_complete_key] = False
                            st.session_state.pop(receipt_key, None)
                            st.session_state.pop(receipt_html_key, None)
                            _add_item_to_pos_cart(company_key, selected_search_row)
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
                            st.rerun()
                    selected_item = st.selectbox("Select Item", items_df["Item Name"].tolist(), key=f"pos_item_{company_key}")
                    qty_to_sell = st.number_input("Quantity", min_value=1, value=1, key=f"pos_qty_{company_key}")
                    if st.button("Add Selected Item", key=f"pos_add_selected_{company_key}"):
                        st.session_state[checkout_complete_key] = False
                        st.session_state.pop(receipt_key, None)
                        st.session_state.pop(receipt_html_key, None)
                        item_row = items_df.loc[items_df["Item Name"] == selected_item].iloc[0]
                        for _ in range(int(qty_to_sell)):
                            _add_item_to_pos_cart(
                                company_key,
                                {
                                    "id": int(item_row["ID"]),
                                    "item_name": item_row["Item Name"],
                                    "item_code": item_row["Item Code"],
                                    "barcode": item_row["Barcode"],
                                    "price": float(item_row["Price"] or 0.0),
                                    "cost_price": float(item_row["Cost Price"] or 0.0),
                                    "tax_rate": float(item_row["Tax Rate"] or 0.0),
                                    "qty": float(item_row["Qty"] or 0.0),
                                },
                            )
                        _trigger_scan_feedback(pos_message_key, f"Added {selected_item} x{int(qty_to_sell)} to the cart.")
                        st.rerun()
            else:
                st.info("No stock available for sale. Switch to Manual Entry to continue.")

        payment_method = st.selectbox("Payment Method", ["Cash", "Mobile Money", "Card", "Bank Transfer", "On Credit"])
        selected_credit_customer_id = None
        selected_credit_customer_label = None
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
        cart = st.session_state.setdefault(cart_key, [])
        cart_summary = _get_pos_cart_summary(company_key)
        cash_tendered = 0.0
        payment_reference = ""
        if cart:
            st.subheader("Active Sale Cart")
            header_cols = st.columns([3, 2, 1, 1, 1, 1, 1, 1, 1])
            header_cols[0].markdown("**Item**")
            header_cols[1].markdown("**Barcode / Code**")
            header_cols[2].markdown("**Qty**")
            header_cols[3].markdown("**Unit Price**")
            header_cols[4].markdown("**Discount**")
            header_cols[5].markdown("**Line Total**")
            header_cols[6].markdown("**+**")
            header_cols[7].markdown("**-**")
            header_cols[8].markdown("**Remove**")

            for index, line in enumerate(list(cart)):
                _recalculate_pos_line(line)
                identifier = line.get("barcode") or line.get("item_code") or "Manual"
                row_cols = st.columns([3, 2, 1, 1, 1, 1, 1, 1, 1])
                row_cols[0].write(str(line.get("name") or ""))
                row_cols[1].caption(str(identifier))
                updated_qty = row_cols[2].number_input(
                    "Qty",
                    min_value=1,
                    value=int(line.get("qty") or 1),
                    step=1,
                    key=f"pos_line_qty_{company_key}_{index}",
                    label_visibility="collapsed",
                )
                updated_discount = row_cols[4].number_input(
                    "Discount",
                    min_value=0.0,
                    value=float(line.get("line_discount") or 0.0),
                    step=0.01,
                    key=f"pos_line_discount_{company_key}_{index}",
                    label_visibility="collapsed",
                )
                line["qty"] = int(updated_qty)
                line["line_discount"] = float(updated_discount)
                _recalculate_pos_line(line)
                row_cols[3].write(format_currency(float(line.get("price") or 0.0)))
                row_cols[5].write(format_currency(float(line.get("line_total") or 0.0)))
                if row_cols[6].button("+", key=f"pos_line_inc_{company_key}_{index}", use_container_width=True):
                    line["qty"] = int(line.get("qty") or 1) + 1
                    _recalculate_pos_line(line)
                    st.rerun()
                if row_cols[7].button("-", key=f"pos_line_dec_{company_key}_{index}", use_container_width=True):
                    line["qty"] = max(int(line.get("qty") or 1) - 1, 1)
                    _recalculate_pos_line(line)
                    st.rerun()
                if row_cols[8].button("Remove", key=f"pos_line_remove_{company_key}_{index}", use_container_width=True):
                    cart.pop(index)
                    st.session_state[cart_key] = cart
                    st.rerun()

            st.session_state[cart_key] = cart
            cart_summary = _get_pos_cart_summary(company_key)
            totals_col1, totals_col2 = st.columns([1, 1])
            with totals_col1:
                st.markdown("### Totals")
                st.caption(f"Item Count: {cart_summary['item_count']}")
                st.caption(f"Subtotal: {format_currency(cart_summary['subtotal'])}")
                st.caption(f"Discount Total: {format_currency(cart_summary['discount_total'])}")
                st.caption(f"Tax / VAT Total: {format_currency(cart_summary['tax_total'])}")
                st.markdown(f"**Grand Total: {format_currency(cart_summary['grand_total'])}**")
            with totals_col2:
                st.markdown("### Payment")
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

            clear_col, checkout_col = st.columns([1, 1])
            if clear_col.button("Clear Cart", key=f"pos_clear_cart_{company_key}", use_container_width=True):
                st.session_state[cart_key] = []
                st.session_state[checkout_complete_key] = False
                st.rerun()
            if checkout_col.button("Final Checkout", key=f"pos_final_checkout_{company_key}", use_container_width=True):
                st.session_state[checkout_complete_key] = True
                process_pos_sale(print_receipt=True)
        else:
            st.info("Scan a barcode or add an item manually to start the sale.")

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
            if payment_method == "Cash" and float(cash_tendered or 0.0) < float(current_summary["grand_total"] or 0.0):
                st.session_state[checkout_complete_key] = False
                st.warning("Cash tendered cannot be less than the grand total.")
                return

            try:
                conn = get_connection()
                line_items = []
                total = 0.0
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
                    gross_line_total = float(sale_line["qty"]) * float(sale_line["price"])
                    discount_amount = float(sale_line.get("line_discount") or 0.0)
                    taxable_base = max(gross_line_total - discount_amount, 0.0)
                    line_tax = taxable_base * (float(sale_line.get("tax_rate") or 0.0) / 100.0)
                    total += taxable_base + line_tax
                    cost_of_goods_sold += float(sale_line["qty"]) * float(sale_line.get("cost_price") or 0.0)
                    if sale_line["inventory_item_id"] is not None:
                        current_item = conn.execute(
                            "SELECT qty FROM inventory WHERE id = ? AND company_key = ?",
                            (int(sale_line["inventory_item_id"]), company_key),
                        ).fetchone()
                        current_qty = float(current_item["qty"] or 0) if current_item else 0.0
                        if float(sale_line["qty"]) > current_qty:
                            st.error(f"Insufficient stock for {sale_line['name']}.")
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
                post_journal_entry(
                    company_key=company_key,
                    date=sale_date,
                    description="POS sale",
                    reference=sale_reference,
                    lines=[
                        {"account_id": get_account_id(conn, receipt_account, receipt_category), "debit": total, "credit": 0},
                        {"account_id": get_account_id(conn, "Sales Revenue", "Income"), "debit": 0, "credit": total},
                    ],
                    created_by=role,
                    branch_id=branch_id,
                    customer_id=selected_credit_customer_id if payment_method == "On Credit" else None,
                    source_module="POS",
                    source_table="vouchers" if legacy_sale_id else "journal_entries",
                    source_id=int(legacy_sale_id) if legacy_sale_id else None,
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
                        source_table="inventory",
                        conn=conn,
                    )
                conn.commit()
                log_audit_action(
                    conn,
                    company_key,
                    role,
                    "POS Sale",
                    "POS",
                    f"Sold {narration} for GH₵{float(total):.2f}" + (
                        f" on credit to {ledger_result['customer_name']}" if ledger_result else ""
                    ),
                    branch_id=branch_id,
                )
                conn.close()
                if print_receipt:
                    sale_datetime = f"{sale_date.isoformat()} {datetime.now().strftime('%H:%M:%S')}"
                    receipt_data = {
                        "company_key": company_key,
                        "company_name": company_label,
                        "branch_name": branch_label,
                        "receipt_number": sale_reference,
                        "sale_datetime": sale_datetime,
                        "cashier": role,
                        "payment_method": payment_method,
                        "payment_reference": payment_reference,
                        "subtotal": float(current_summary["subtotal"] or 0.0),
                        "discount_total": float(current_summary["discount_total"] or 0.0),
                        "tax_total": float(current_summary["tax_total"] or 0.0),
                        "grand_total": float(current_summary["grand_total"] or 0.0),
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
                    st.session_state["last_receipt_data"] = receipt_data
                    st.session_state[last_receipt_data_key] = receipt_data
                    st.session_state[receipt_key] = _build_receipt(receipt_data)
                    st.session_state[receipt_html_key] = _build_receipt_html(receipt_data)
                st.session_state[checkout_complete_key] = True
                st.session_state[cart_key] = []
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

        action_col1, action_col2 = st.columns(2)
        if action_col1.button("Final Checkout", key=f"final_checkout_{company_key}"):
            st.session_state[checkout_complete_key] = True
            process_pos_sale(print_receipt=True)
        if action_col2.button("Clear Cart", key=f"clear_cart_post_{company_key}"):
            st.session_state[cart_key] = []
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

        if st.session_state.get(checkout_complete_key) and st.session_state.get(receipt_html_key):
            _inject_print_styles()
            receipt_data = st.session_state.get(last_receipt_data_key) or st.session_state.get("last_receipt_data") or {}
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
            st.subheader("Receipt Preview")
            st.markdown(st.session_state[receipt_html_key], unsafe_allow_html=True)
            receipt_action_col1, receipt_action_col2, receipt_action_col3 = st.columns(3)
            if receipt_action_col1.button("Print Receipt", key=f"receipt_print_btn_{company_key}", use_container_width=True):
                st.session_state[do_print_key] = True
            if receipt_action_col2.button("Reprint Last Receipt", key=f"receipt_reprint_btn_{company_key}", use_container_width=True):
                last_receipt_data = st.session_state.get(last_receipt_data_key) or st.session_state.get("last_receipt_data")
                if last_receipt_data:
                    st.session_state[receipt_key] = _build_receipt(last_receipt_data)
                    st.session_state[receipt_html_key] = _build_receipt_html(last_receipt_data)
                    st.session_state[checkout_complete_key] = True
                    st.session_state[do_print_key] = True
                    st.rerun()
                st.warning("No previous receipt is available for reprint.")
            if receipt_action_col3.button("New Sale", key=f"receipt_new_sale_btn_{company_key}", use_container_width=True):
                st.session_state[cart_key] = []
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
            st.download_button(
                "Download Receipt",
                data=st.session_state.get(receipt_key, ""),
                file_name=f"receipt_{company_key}.txt",
                mime="text/plain",
                key=f"receipt_download_{company_key}",
            )
        if st.session_state.get('do_print'):
            components.html("<script>window.print();</script>", height=0)
            st.session_state['do_print'] = False
    except Exception as e:
        st.error(build_user_safe_error(e, role))
# ==========================================
# SALES & PURCHASE
# ==========================================
def show_sales_purchase(company_key, role, doc_type="Sales"):
    st.header(f"{'🧾 Sales Invoicing' if doc_type == 'Sales' else '📦 Purchase Orders'}")
    branch_id = st.session_state.get("active_branch_id")
    if role == "Demo":
        _demo_notice()
        demo_data = pd.DataFrame({
            "Customer/Supplier": ["Demo Client Ltd", "Demo Supplier Co."],
            "Amount (GH₵)": [5000.0, 2000.0],
            "Status": ["Paid", "Pending"],
            "Date": [datetime.now().date().isoformat()] * 2,
        })
        st.dataframe(format_currency_dataframe(demo_data), use_container_width=True)
        return

    with st.form(f"{doc_type.lower()}_form"):
        col1, col2 = st.columns(2)
        with col1:
            party_name = st.text_input("Customer Name" if doc_type == "Sales" else "Supplier Name")
            amount = st.number_input("Amount (GH₵)", min_value=0.0, step=0.01)
        with col2:
            status = st.selectbox("Status", ["Paid", "Pending", "Draft"] if doc_type == "Sales" else ["Received", "Pending", "Cancelled"])
            posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=3)
            doc_date = st.date_input("Date", datetime.now().date())
        city_region = st.text_input("City / Region")
        narration = st.text_input("Description / Reference")
        submitted = st.form_submit_button(f"Save {doc_type}")

        if submitted and party_name and amount > 0:
            try:
                conn = get_connection()
                tx_reference = f"{doc_type[:3].upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                if doc_type == "Sales":
                    customer_id = _register_customer(conn, company_key, party_name)
                    invoice_cursor = conn.execute(
                        """
                        INSERT INTO invoices (company_key, customer_id, invoice_number, invoice_date, due_date, status, approval_status, amount, currency, description, created_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                        """,
                        (company_key, customer_id, tx_reference, doc_date.isoformat(), doc_date.isoformat(), status, posting_state, amount, narration, role),
                    )
                    debit_account = "Cash" if status == "Paid" else "Accounts Receivable"
                    if posting_state == "Posted":
                        post_journal_entry(
                            company_key=company_key,
                            date=doc_date,
                            description="Sales transaction",
                            reference=tx_reference,
                            lines=[
                                {"account_id": get_account_id(conn, debit_account, "Asset"), "debit": amount, "credit": 0},
                                {"account_id": get_account_id(conn, "Sales Revenue", "Income"), "debit": 0, "credit": amount},
                            ],
                            created_by=role,
                            branch_id=branch_id,
                            customer_id=customer_id,
                            source_module="Sales Invoicing",
                            source_table="invoices",
                            source_type="Invoice",
                            source_id=int(invoice_cursor.lastrowid),
                            approval_status="Posted",
                            conn=conn,
                        )
                else:
                    supplier_id = _get_or_create_party(conn, "suppliers", company_key, party_name)
                    bill_cursor = conn.execute(
                        """
                        INSERT INTO bills (company_key, supplier_id, bill_number, bill_date, due_date, status, approval_status, amount, currency, description, created_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                        """,
                        (company_key, supplier_id, tx_reference, doc_date.isoformat(), doc_date.isoformat(), status, posting_state, amount, narration, role),
                    )
                    credit_account = "Cash" if status == "Received" else "Accounts Payable"
                    credit_category = "Asset" if credit_account == "Cash" else "Liability"
                    if posting_state == "Posted":
                        post_journal_entry(
                            company_key=company_key,
                            date=doc_date,
                            description="Purchase transaction",
                            reference=tx_reference,
                            lines=[
                                {"account_id": get_account_id(conn, "Inventory", "Asset"), "debit": amount, "credit": 0},
                                {"account_id": get_account_id(conn, credit_account, credit_category), "debit": 0, "credit": amount},
                            ],
                            created_by=role,
                            branch_id=branch_id,
                            supplier_id=supplier_id,
                            source_module="Purchase Orders",
                            source_table="bills",
                            source_type="Bill",
                            source_id=int(bill_cursor.lastrowid),
                            approval_status="Posted",
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
                log_audit_action(conn, company_key, role, f"{doc_type} Recorded", doc_type, f"{party_name} - GH₵{amount:.2f}", branch_id=branch_id)
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
            df = pd.DataFrame(data, columns=["Date", "Description", "Amount (GH₵)"])
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
    st.header("🏦 Banking & Cash")
    if role == "Demo":
        _demo_notice()
        st.metric(f"Cash Balance ({get_currency_symbol()})", format_currency(8300.0))
        st.metric(f"Bank Balance ({get_currency_symbol()})", format_currency(15000.0))
        return

    try:
        conn = get_connection()
        trial_balance = engine_get_trial_balance(company_key)
        cash_total = sum(row["balance"] for row in trial_balance if row["account_name"] == "Cash")
        bank_total = sum(row["balance"] for row in trial_balance if row["account_name"] in ("Bank", "Mobile Money"))
        customers = get_customer_balances(company_key, conn=conn)
        suppliers = conn.execute("SELECT id, name FROM suppliers WHERE company_key = ? ORDER BY name", (company_key,)).fetchall()

        col1, col2 = st.columns(2)
        col1.metric(f"Cash Balance ({get_currency_symbol()})", format_currency(cash_total))
        col2.metric(f"Bank Balance ({get_currency_symbol()})", format_currency(bank_total))

        with st.expander("Record Payment", expanded=True):
            with st.form(f"banking_payment_form_{company_key}", clear_on_submit=True):
                payment_type = st.selectbox("Payment Type", ["Customer Receipt", "Supplier Payment"])
                payment_method = st.selectbox("Method", ["Cash", "Bank", "Mobile Money"])
                amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01)
                payment_date = st.date_input("Payment Date", value=datetime.now().date(), key=f"banking_payment_date_{company_key}")
                reference = st.text_input("Reference")
                if payment_type == "Customer Receipt":
                    customer_labels = [f"{row['name']} ({row['customer_id']})" for row in customers]
                    selected_party = st.selectbox("Customer", customer_labels if customer_labels else [""])
                else:
                    supplier_labels = [f"{row['name']}" for row in suppliers]
                    selected_party = st.selectbox("Supplier", supplier_labels if supplier_labels else [""])
                submitted = st.form_submit_button("Post Payment")

            if submitted:
                if amount <= 0:
                    st.warning("Enter an amount greater than zero.")
                elif payment_type == "Customer Receipt" and not customers:
                    st.warning("Create a customer before posting a receipt.")
                elif payment_type == "Supplier Payment" and not suppliers:
                    st.warning("Create a supplier before posting a supplier payment.")
                else:
                    cash_account = "Cash" if payment_method == "Cash" else ("Bank" if payment_method == "Bank" else "Mobile Money")
                    payment_cursor = conn.execute(
                        """
                        INSERT INTO payments (company_key, payment_date, payment_type, customer_id, supplier_id, amount, currency, method, reference, status, approval_status, created_by)
                        VALUES (?, ?, ?, ?, ?, ?, 'GHS', ?, ?, 'Posted', 'Posted', ?)
                        """,
                        (
                            company_key,
                            payment_date.isoformat(),
                            payment_type,
                            int(customers[[f"{row['name']} ({row['customer_id']})" for row in customers].index(selected_party)]["id"]) if payment_type == "Customer Receipt" else None,
                            int(suppliers[supplier_labels.index(selected_party)]["id"]) if payment_type == "Supplier Payment" else None,
                            amount,
                            payment_method,
                            reference,
                            role,
                        ),
                    )
                    if payment_type == "Customer Receipt":
                        selected_customer = customers[[f"{row['name']} ({row['customer_id']})" for row in customers].index(selected_party)]
                        lines = [
                            {"account_id": get_account_id(conn, cash_account, "Asset"), "debit": amount, "credit": 0},
                            {"account_id": get_account_id(conn, "Accounts Receivable", "Asset"), "debit": 0, "credit": amount},
                        ]
                        post_journal_entry(
                            company_key=company_key,
                            date=payment_date,
                            description=f"Customer receipt - {selected_customer['name']}",
                            reference=reference or f"PAY-{int(payment_cursor.lastrowid)}",
                            lines=lines,
                            created_by=role,
                            branch_id=st.session_state.get("active_branch_id"),
                            customer_id=int(selected_customer["id"]),
                            payment_id=int(payment_cursor.lastrowid),
                            source_module="Banking",
                            source_table="payments",
                            source_id=int(payment_cursor.lastrowid),
                            conn=conn,
                        )
                    else:
                        selected_supplier = suppliers[supplier_labels.index(selected_party)]
                        lines = [
                            {"account_id": get_account_id(conn, "Accounts Payable", "Liability"), "debit": amount, "credit": 0},
                            {"account_id": get_account_id(conn, cash_account, "Asset"), "debit": 0, "credit": amount},
                        ]
                        post_journal_entry(
                            company_key=company_key,
                            date=payment_date,
                            description=f"Supplier payment - {selected_supplier['name']}",
                            reference=reference or f"PAY-{int(payment_cursor.lastrowid)}",
                            lines=lines,
                            created_by=role,
                            branch_id=st.session_state.get("active_branch_id"),
                            supplier_id=int(selected_supplier["id"]),
                            payment_id=int(payment_cursor.lastrowid),
                            source_module="Banking",
                            source_table="payments",
                            source_id=int(payment_cursor.lastrowid),
                            conn=conn,
                        )
                    conn.commit()
                    st.success("Payment posted successfully.")
                    st.rerun()

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
    st.header(f"📋 Accounts {aging_type}")
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
                    with st.form(f"supplier_register_form_{company_key}", clear_on_submit=True):
                        supplier_name = st.text_input("Supplier Name")
                        supplier_phone = st.text_input("Phone")
                        supplier_email = st.text_input("Email")
                        supplier_address = st.text_area("Address")
                        supplier_category = st.text_input("Category")
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
                            st.success("Supplier saved.")
                            conn.close()
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

    try:
        conn = get_connection()
        total_sales = get_account_total(company_key, "Sales", balance_side="credit", conn=conn)
        compare_legacy_and_journal_totals(company_key, logger_instance=logger, conn=conn)
        conn.close()

        vat = total_sales * VAT_RATE
        nhil = total_sales * NHIL_RATE
        getfund = total_sales * GETFUND_RATE
        total_tax = vat + nhil + getfund

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"Total Sales ({get_currency_symbol()})", format_currency(total_sales))
        col2.metric(f"VAT ({VAT_RATE*100:.1f}%) {get_currency_symbol()}", format_currency(vat))
        col3.metric(f"NHIL ({NHIL_RATE*100:.1f}%) {get_currency_symbol()}", format_currency(nhil))
        col4.metric(f"Total Tax Due ({get_currency_symbol()})", format_currency(total_tax))
    except Exception as e:
        st.error(build_user_safe_error(e, st.session_state.get("user", {}).get("role")))


# ==========================================
# GHANA PAYROLL (SSNIT)
# ==========================================
def show_payroll(company_key, role):
    st.header("💳 Payroll & Salaries")
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

    with st.expander("➕ Add Payroll Entry", expanded=True):
        with st.form("payroll_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                emp_name = st.text_input("Employee Name")
                basic_salary = st.number_input(f"Basic Salary ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                allowances = st.number_input(f"Allowances ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                deductions = st.number_input(f"Deductions ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
            with col2:
                month = st.selectbox("Month", ["January","February","March","April","May","June",
                                               "July","August","September","October","November","December"])
                year = st.selectbox("Year", [str(y) for y in range(2023, 2030)],
                                    index=[str(y) for y in range(2023, 2030)].index(str(datetime.now().year)))
                payment_status = st.selectbox("Payment Status", ["Paid", "Unpaid"])

            submitted = st.form_submit_button("Calculate & Save")
            if submitted and emp_name and basic_salary > 0:
                payroll_values = _calculate_payroll_values(basic_salary, allowances, deductions)
                try:
                    conn = get_connection()
                    conn.execute(
                        """INSERT INTO payroll
                           (company_key, emp_name, basic_salary, allowances, ssnit_t1, ssnit_t2,
                            taxable_income, paye, net_salary, deductions, month, year, payment_status, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active')""",
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
                        ),
                    )
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
                            basic_salary + allowances,
                            deductions,
                            payroll_values["net_salary"],
                            payment_status,
                        ),
                    )
                    salary_credit_account = "Cash" if payment_status == "Paid" else "Payroll Payable"
                    salary_credit_type = "Asset" if salary_credit_account == "Cash" else "Liability"
                    post_journal_entry(
                        company_key=company_key,
                        date=datetime(int(year), ['January','February','March','April','May','June','July','August','September','October','November','December'].index(month)+1, 1).date(),
                        description="Payroll accrual",
                        reference=f"PAY-{emp_name}-{month}-{year}",
                        lines=[
                            {"account_id": get_account_id(conn, "Salary Expense", "Expense"), "debit": payroll_values["net_salary"], "credit": 0},
                            {"account_id": get_account_id(conn, salary_credit_account, salary_credit_type), "debit": 0, "credit": payroll_values["net_salary"]},
                        ],
                        created_by=role,
                        branch_id=st.session_state.get("active_branch_id"),
                        source_module="Payroll",
                        source_table="payroll",
                        conn=conn,
                    )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Payroll Entry Added", "Payroll", f"{emp_name} - {month} {year}")
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
                      payment_status, COALESCE(status, 'Active')
               FROM payroll WHERE company_key = ? ORDER BY year DESC, month DESC""",
            (company_key,),
        ).fetchall()
        if data:
            df = pd.DataFrame(data, columns=["ID", "Employee", "Basic Salary", "Allowances", "Deductions",
                                              "SSNIT T1", "PAYE", "Net Salary", "Month", "Year", "Payment Status", "Status"])
            st.dataframe(format_currency_dataframe(df), use_container_width=True)
            if role == "Master Admin":
                selected_payroll_key = f"payroll_edit_selected_{company_key}"
                void_payroll_key = f"payroll_void_selected_{company_key}"
                for _, payroll_list_row in df.iterrows():
                    info_cols = st.columns([3, 1, 1, 1])
                    name_col, edit_col, void_col, print_col = info_cols
                    name_col.caption(
                        f"{payroll_list_row['Employee']} | Salary GH₵ {float(payroll_list_row['Basic Salary']):,.2f} | "
                        f"Net GH₵ {float(payroll_list_row['Net Salary']):,.2f} | {payroll_list_row['Status']}"
                    )
                    if edit_col.button("Edit", key=f"payroll_edit_btn_{company_key}_{int(payroll_list_row['ID'])}"):
                        st.session_state[selected_payroll_key] = int(payroll_list_row["ID"])
                    if payroll_list_row["Status"] != "Void" and void_col.button("Void", key=f"payroll_void_btn_{company_key}_{int(payroll_list_row['ID'])}"):
                        st.session_state[void_payroll_key] = int(payroll_list_row["ID"])
                    if print_col.button("Print", key=f"payroll_print_btn_{company_key}_{int(payroll_list_row['ID'])}"):
                        st.session_state[payroll_print_preview_key] = _build_payslip_html(payroll_list_row)
                        st.session_state[f"payroll_print_record_id_{company_key}"] = int(payroll_list_row['ID'])
                        st.rerun()
                void_payroll_id = st.session_state.get(void_payroll_key)
                if void_payroll_id is not None:
                    st.warning("Are you sure you want to void this payroll entry?")
                    confirm_col, cancel_col = st.columns(2)
                    if confirm_col.button("Confirm Void", key=f"payroll_void_confirm_btn_{company_key}_{void_payroll_id}"):
                        conn.execute(
                            "UPDATE payroll SET status = 'Void' WHERE id = ? AND company_key = ?",
                            (int(void_payroll_id), company_key),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Payroll Voided", "Payroll", f"Voided payroll ID {int(void_payroll_id)}")
                        _clear_streamlit_state(void_payroll_key, selected_payroll_key)
                        st.success("Entry Updated")
                        st.rerun()
                    if cancel_col.button("Cancel", key=f"payroll_void_cancel_btn_{company_key}_{void_payroll_id}"):
                        _clear_streamlit_state(void_payroll_key)
                        st.rerun()
                payroll_record_id = st.session_state.get(selected_payroll_key, int(df["ID"].iloc[0]))
                edit_row = df.loc[df["ID"] == payroll_record_id].iloc[0]
                with st.form(f"payroll_edit_form_{company_key}_{payroll_record_id}", clear_on_submit=True):
                    edit_salary = st.number_input("Salary", min_value=0.0, value=float(edit_row["Basic Salary"] or 0.0))
                    edit_bonus = st.number_input("Bonus", min_value=0.0, value=float(edit_row["Allowances"] or 0.0))
                    edit_deductions = st.number_input("Deductions", min_value=0.0, value=float(edit_row["Deductions"] or 0.0))
                    edit_status = st.selectbox("Payment Status", ["Paid", "Unpaid"], index=0 if edit_row["Payment Status"] == "Paid" else 1)
                    if st.form_submit_button("Update Payroll"):
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
                                taxable_income = ?, paye = ?, net_salary = ?, deductions = ?, payment_status = ?
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
                        f"{payroll_list_row['Employee']} | Salary GH₵ {float(payroll_list_row['Basic Salary']):,.2f} | "
                        f"Net GH₵ {float(payroll_list_row['Net Salary']):,.2f} | {payroll_list_row['Status']}"
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
            "Cost (GH₵)": [85000.0, 5500.0],
            "Depreciation Rate (%)": [20.0, 33.3],
            "Book Value (GH₵)": [68000.0, 3685.0],
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
                cost = st.number_input("Cost (GH₵)", min_value=0.0, step=0.01)
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
                    log_audit_action(conn, company_key, role, "Fixed Asset Added", "Fixed Assets", f"{asset_name} - GH₵{cost:,.2f}")
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
                        f"{asset_row['Asset Name']} | Current GH₵ {float(asset_row['Current Value']):,.2f} | "
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
                    edit_cost = st.number_input("Cost (GH₵)", min_value=0.0, value=float(edit_asset_row["Cost (GH₵)"] or 0.0))
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

    action_col1, action_col2 = st.columns(2)
    if action_col1.button("Post Current Depreciation", key=f"run_depreciation_{company_key}"):
        try:
            posted_entries = run_straight_line_depreciation(company_key, created_by=role)
            st.success(f"Depreciation run complete. Posted {posted_entries} journal entr{'y' if posted_entries == 1 else 'ies'}.")
            st.rerun()
        except Exception as exc:
            st.error(build_user_safe_error(exc, st.session_state.get("user", {}).get("role")))
    action_col2.caption("Straight-line depreciation posts to Depreciation Expense and Accumulated Depreciation.")

    with st.expander("Add Fixed Asset", expanded=True):
        with st.form("fixed_asset_form_override", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                asset_name = st.text_input("Asset Name")
                asset_category = st.selectbox("Category", ["Vehicle", "Equipment", "Building", "Furniture", "Land", "Other"])
                purchase_date = st.date_input("Purchase Date", datetime.now().date())
            with col2:
                cost = st.number_input(f"Cost ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                opening_book_value = st.number_input("Opening Book Value", min_value=0.0, step=0.01)
                useful_life_years = st.number_input("Useful Life (Years)", min_value=0.0, step=1.0)
                residual_value = st.number_input(f"Residual Value ({st.session_state.currency_symbol})", min_value=0.0, step=0.01)
                location = st.text_input("Location")

            if st.form_submit_button("Add Asset") and asset_name and cost > 0:
                book_value = opening_book_value if opening_book_value > 0 else cost
                depreciation_rate = round((100.0 / useful_life_years), 4) if useful_life_years > 0 else 0.0
                try:
                    conn = get_connection()
                    asset_cursor = conn.execute(
                        """
                        INSERT INTO fixed_assets
                           (company_key, asset_name, asset_category, purchase_date, cost,
                            opening_book_value, useful_life_years, residual_value, depreciation_method,
                            depreciation_rate, accumulated_depreciation, book_value, last_depreciation_date, location)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Straight-line', ?, 0, ?, NULL, ?)
                        """,
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
                        ),
                    )
                    create_journal_entry(
                        "Fixed asset acquisition",
                        [
                            {"account_name": "Fixed Assets", "category": "Asset", "debit": cost, "credit": 0},
                            {"account_name": "Opening Balance Equity", "category": "Equity", "debit": 0, "credit": cost},
                        ],
                        company_key=company_key,
                        reference=f"FA-{int(asset_cursor.lastrowid)}",
                        entry_date=purchase_date,
                        conn=conn,
                    )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Fixed Asset Added", "Fixed Assets", f"{asset_name} - GHS{cost:,.2f}")
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
                   book_value, location, status
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
                "Status",
            ],
        )
        st.dataframe(format_currency_dataframe(df), use_container_width=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Assets", len(df))
        col2.metric("Total Cost", format_currency(df["Cost (GHS)"].sum()))
        col3.metric("Total Book Value", format_currency(df["Current Value"].sum()))

        if role in ("Master Admin", "Bookkeeper", "Branch_Bookkeeper", "Sub-Admin"):
            selected_asset_key = f"asset_edit_selected_{company_key}"
            delete_asset_key = f"asset_delete_selected_{company_key}"
            for _, asset_row in df.iterrows():
                name_col, edit_col, delete_col = st.columns([4, 1, 1])
                name_col.caption(
                    f"{asset_row['Asset Name']} | Current {format_currency(asset_row['Current Value'])} | "
                    f"Purchase Date {asset_row['Purchase Date']}"
                )
                if edit_col.button("Edit", key=f"asset_edit_btn_override_{company_key}_{int(asset_row['ID'])}"):
                    st.session_state[selected_asset_key] = int(asset_row["ID"])
                if delete_col.button("Delete Record", key=f"asset_delete_btn_override_{company_key}_{int(asset_row['ID'])}"):
                    st.session_state[delete_asset_key] = int(asset_row["ID"])

            delete_asset_id = st.session_state.get(delete_asset_key)
            if delete_asset_id is not None:
                st.warning("Are you sure you want to permanently delete this item?")
                confirm_col, cancel_col = st.columns(2)
                if confirm_col.button("Delete Record", key=f"asset_delete_confirm_override_{company_key}_{delete_asset_id}"):
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
            with st.form(f"asset_edit_form_override_{company_key}_{edit_asset_id}", clear_on_submit=True):
                edit_asset_name = st.text_input("Asset Name", value=str(edit_asset_row["Asset Name"] or ""))
                edit_purchase_date = st.date_input("Purchase Date", value=pd.to_datetime(edit_asset_row["Purchase Date"]).date())
                edit_cost = st.number_input("Cost (GHS)", min_value=0.0, value=float(edit_asset_row["Cost (GHS)"] or 0.0))
                edit_opening_book = st.number_input("Opening Book Value", min_value=0.0, value=float(edit_asset_row["Opening Book Value"] or 0.0))
                edit_useful_life = st.number_input("Useful Life (Years)", min_value=0.0, value=float(edit_asset_row["Useful Life (Years)"] or 0.0))
                edit_residual_value = st.number_input("Residual Value (GHS)", min_value=0.0, value=float(edit_asset_row["Residual Value"] or 0.0))
                edit_location = st.text_input("Location", value=str(edit_asset_row["Location"] or ""))
                if st.form_submit_button("Update Asset"):
                    edit_depr_rate = round((100.0 / edit_useful_life), 4) if edit_useful_life > 0 else 0.0
                    conn.execute(
                        """
                        UPDATE fixed_assets
                        SET asset_name = ?, purchase_date = ?, cost = ?, opening_book_value = ?,
                            useful_life_years = ?, residual_value = ?, depreciation_method = 'Straight-line',
                            depreciation_rate = ?, book_value = ?, location = ?
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
    pdf_bin = _build_simple_pdf(title, summary_lines)
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


def show_dashboard(company_key, company_name, role):
    """Primary business dashboard restored in modules.py for safe routing."""
    st.header(f"📊 Dashboard: {company_name}")

    if role == "Demo":
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
                recent_txns = recent_txns.drop(columns=[column for column in ["amount"] if column in recent_txns.columns]).rename(
                    columns={"date": "Date", "activity_type": "Type", "description": "Description", "reference": "Reference"}
                )
                st.dataframe(format_currency_dataframe(recent_txns), use_container_width=True)
        compare_legacy_and_journal_totals(company_key, logger_instance=logger, conn=conn)

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
                st.dataframe(format_currency_dataframe(low_stock), use_container_width=True)

        st.subheader("Quick Actions")
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
    finally:
        if conn:
            conn.close()


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
        "INSERT INTO suppliers (company_key, name, phone, email, address, category) VALUES (?, ?, ?, ?, ?, ?)",
        (
            company_key,
            name.strip(),
            phone.strip() if phone else "",
            email.strip() if email else "",
            address.strip() if address else "",
            category.strip() if category else "",
        ),
    )
    return cursor.lastrowid


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
        if company_key == "ADMIN" or company_key == "DEMO":
            query = "SELECT timestamp, company_key, branch_id, user_role, action, module_name, details FROM audit_logs ORDER BY timestamp DESC LIMIT 100"
            params = ()
        elif role == "Master Admin":
            if branch_id:
                query = "SELECT timestamp, company_key, branch_id, user_role, action, module_name, details FROM audit_logs WHERE company_key = ? AND branch_id = ? ORDER BY timestamp DESC LIMIT 100"
                params = (company_key, branch_id)
            else:
                query = "SELECT timestamp, company_key, branch_id, user_role, action, module_name, details FROM audit_logs WHERE company_key = ? ORDER BY timestamp DESC LIMIT 100"
                params = (company_key,)
        else:
            query = "SELECT timestamp, company_key, branch_id, user_role, action, module_name, details FROM audit_logs WHERE company_key = ? ORDER BY timestamp DESC LIMIT 100"
            params = (company_key,)

        data = conn.execute(query, params).fetchall()
        conn.close()

        if data:
            df = pd.DataFrame(data, columns=["Timestamp", "Company", "Branch", "Role", "Action", "Module", "Details"])
            st.dataframe(format_currency_dataframe(df), use_container_width=True)
            excel_bin = get_excel_bin(df)
            if excel_bin:
                st.download_button("📥 Export Audit Trail", data=excel_bin, file_name="audit_trail.xlsx")
        else:
            st.info("No audit records found.")
    except Exception as e:
        st.error(build_user_safe_error(e, role))


def show_branch_management(company_key, role):
    if not require_permission(role, "manage_branches", action_label="manage branches", company_key=company_key):
        return

    from financials import get_income_statement

    st.header("🏢 Branch Management")

    tabs = st.tabs(["Branch List & Configuration", "Staff Assignment", "Branch Performance"])

    with tabs[0]:
        # Branch List
        st.subheader("Current Branches")
        conn = get_connection()
        try:
            branches = conn.execute("SELECT branch_id, branch_name, location, branch_type, branch_access_key, contact_number, branch_manager, created_at FROM branches WHERE company_key = ? ORDER BY created_at DESC", (company_key,)).fetchall()
            if branches:
                df = pd.DataFrame(branches, columns=["Branch ID", "Branch Name", "Location", "Type", "Access Key", "Contact Number", "Branch Manager", "Created At"])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No branches found. Add your first branch below.")
        except Exception as e:
            st.error(build_user_safe_error(e, role))
        finally:
            conn.close()

        # Configuration Form
        st.subheader("Add/Edit Branch")
        conn = get_connection()
        try:
            current_count = conn.execute("SELECT COUNT(*) FROM branches WHERE company_key = ?", (company_key,)).fetchone()[0]
            max_branches_row = conn.execute("SELECT max_branches FROM companies WHERE key = ?", (company_key,)).fetchone()
            max_branches = max_branches_row[0] if max_branches_row else 1
            if current_count >= max_branches:
                st.warning(f"You have reached the maximum number of branches ({max_branches}). Contact support to increase your limit.")
                can_add = False
            else:
                can_add = True
        except Exception as e:
            st.error(build_user_safe_error(e, role))
            can_add = False
        finally:
            conn.close()

        if can_add:
            with st.form("branch_form"):
                branch_name = st.text_input("Branch Name", key="branch_name")
                location = st.text_input("Location/Physical Address", key="branch_location")
                contact_number = st.text_input("Contact Number", key="branch_contact")
                branch_manager = st.text_input("Branch Manager Name", key="branch_manager")
                branch_type = st.selectbox("Branch Type", ["Retail", "Warehouse", "Office", "Other"], key="branch_type")

                submitted = st.form_submit_button("Save Branch")
                if submitted:
                    if branch_name:
                        conn = get_connection()
                        try:
                            branch_id = f"{company_key}-{branch_name.replace(' ', '_').lower()}"
                            existing_branch = conn.execute("SELECT branch_access_key FROM branches WHERE branch_id = ?", (branch_id,)).fetchone()
                            if existing_branch and existing_branch[0]:
                                branch_access_key = existing_branch[0]
                            else:
                                branch_access_key = f"{branch_id}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=12))}"
                            conn.execute("""
                                INSERT OR REPLACE INTO branches (branch_id, company_key, branch_name, location, branch_type, branch_access_key, contact_number, branch_manager)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (branch_id, company_key, branch_name, location or "", branch_type, branch_access_key, contact_number or "", branch_manager or ""))
                            # Generate Branch Bookkeeper User
                            hashed_password = _hash_security_answer("default123")  # Default password
                            conn.execute("""
                                INSERT OR IGNORE INTO users (company_key, branch_id, full_name, login_key, password_hash, role, status)
                                VALUES (?, ?, ?, ?, ?, ?, 'Active')
                            """, (company_key, branch_id, branch_manager or "Branch Manager", branch_access_key, hashed_password, 'Branch_Bookkeeper'))
                            conn.commit()
                            log_audit_action(conn, company_key, "Master Admin", f"Added branch: {branch_name} with access key: {branch_access_key}", "Branch Management", branch_id=branch_id)
                            st.success(f"Branch '{branch_name}' saved successfully. Access Key: {branch_access_key}")
                            # Sync to Firebase - TODO: implement
                            # _sync_to_firebase(conn, company_key)
                            st.rerun()
                        except Exception as e:
                            st.error(build_user_safe_error(e, role))
                        finally:
                            conn.close()
                    else:
                        st.error("Branch Name is required.")
        else:
            st.info("Cannot add more branches. Limit reached.")

    with tabs[1]:
        # Staff Assignment
        st.subheader("Assign Staff to Branches")
        conn = get_connection()
        try:
            # Get branches
            branches = conn.execute("SELECT branch_id, branch_name FROM branches WHERE company_key = ? ORDER BY branch_name", (company_key,)).fetchall()
            branch_options = {b[0]: b[1] for b in branches}
            branch_options[""] = "Unassigned"

            # Get users
            users = conn.execute("SELECT id, full_name, role, branch_id FROM users WHERE company_key = ? AND role IN ('Bookkeeper', 'Staff') ORDER BY full_name", (company_key,)).fetchall()
            for user in users:
                user_id, full_name, user_role, current_branch = user
                with st.expander(f"{full_name} ({user_role})"):
                    selected_branch = st.selectbox(f"Assign {full_name} to branch", options=list(branch_options.keys()), format_func=lambda x: branch_options.get(x, "Unassigned"), index=list(branch_options.keys()).index(current_branch or ""), key=f"assign_{user_id}")
                    if st.button(f"Update Assignment for {full_name}", key=f"update_{user_id}"):
                        conn.execute("UPDATE users SET branch_id = ? WHERE id = ?", (selected_branch or None, user_id))
                        conn.commit()
                        log_audit_action(conn, company_key, "Master Admin", f"Assigned {full_name} to branch {selected_branch}", "Branch Management")
                        st.success(f"Updated assignment for {full_name}.")
                        st.rerun()
        except Exception as e:
            st.error(build_user_safe_error(e, role))
        finally:
            conn.close()

    with tabs[2]:
        # Branch Performance
        st.subheader("Branch Performance Comparison")
        conn = get_connection()
        try:
            branches = conn.execute("SELECT branch_id, branch_name FROM branches WHERE company_key = ? ORDER BY branch_name", (company_key,)).fetchall()
            branch_options = [b[1] for b in branches]
            if len(branches) >= 2:
                col1, col2 = st.columns(2)
                with col1:
                    branch1 = st.selectbox("Select Branch 1", branch_options, key="perf_branch1")
                with col2:
                    branch2 = st.selectbox("Select Branch 2", branch_options, index=1 if len(branch_options) > 1 else 0, key="perf_branch2")

                if branch1 and branch2 and branch1 != branch2:
                    branch1_id = next(b[0] for b in branches if b[1] == branch1)
                    branch2_id = next(b[0] for b in branches if b[1] == branch2)

                    # Get income statements
                    inc1 = get_income_statement(company_key, branch_id=branch1_id)
                    inc2 = get_income_statement(company_key, branch_id=branch2_id)

                    if not inc1.empty and not inc2.empty:
                        def _branch_metrics(df):
                            revenue = float(df.loc[df["Category"] == "Revenue", "Amount (GHS)"].sum()) if not df.empty else 0.0
                            expense = float(df.loc[df["Category"] == "Operating Expenses", "Amount (GHS)"].sum()) if not df.empty else 0.0
                            profit = float(df.loc[df["Account"] == "Net Profit", "Amount (GHS)"].sum()) if not df.empty else 0.0
                            return revenue, expense, profit

                        revenue1, expense1, profit1 = _branch_metrics(inc1)
                        revenue2, expense2, profit2 = _branch_metrics(inc2)

                        ar1 = get_account_total(company_key, "Accounts Receivable", branch_id=branch1_id, balance_side="debit", conn=conn)
                        ar2 = get_account_total(company_key, "Accounts Receivable", branch_id=branch2_id, balance_side="debit", conn=conn)
                        inventory_summary = conn.execute(
                            "SELECT COUNT(*) AS item_count, COALESCE(SUM(qty * cost_price), 0) AS inventory_value FROM inventory WHERE company_key = ?",
                            (company_key,),
                        ).fetchone()
                        inventory_items = int(inventory_summary[0] or 0)
                        inventory_value = float(inventory_summary[1] or 0.0)

                        st.subheader(f"Revenue vs Expenses: {branch1} vs {branch2}")
                        chart_df = pd.DataFrame(
                            {
                                "Revenue": [revenue1, revenue2],
                                "Expenses": [expense1, expense2],
                            },
                            index=[branch1, branch2],
                        )
                        st.bar_chart(chart_df)

                        st.markdown("### Branch Comparison Summary")
                        summary_df = pd.DataFrame(
                            [
                                {
                                    "Branch": branch1,
                                    "Revenue": revenue1,
                                    "Expenses": expense1,
                                    "Net Profit": profit1,
                                    "Accounts Receivable": ar1,
                                },
                                {
                                    "Branch": branch2,
                                    "Revenue": revenue2,
                                    "Expenses": expense2,
                                    "Net Profit": profit2,
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
                        st.markdown("**Company-wide inventory values are consolidated. Branch-specific A/R is displayed for the selected branches.**")
                    else:
                        st.info("No data available for selected branches.")
                else:
                    st.info("Select two different branches to compare.")
            else:
                st.info("At least two branches are required for comparison.")
        except Exception as e:
            st.error(build_user_safe_error(e, role))
        finally:
            conn.close()

