import sqlite3
import logging
from datetime import datetime, timedelta
import os
import shutil
import json
import re
import tempfile
import time
import threading
from contextlib import contextmanager
from security_utils import sanitize_error_message
from urllib.parse import parse_qs, urlparse, urlunparse

try:
    import streamlit as st
except Exception:
    st = None

DB_UPGRADE_SAFETY_AVAILABLE = True
ERP_MIGRATIONS_AVAILABLE = True

try:
    from db_upgrade_safety import (
        collect_row_counts,
        create_timestamped_backup,
        is_sqlite_file,
        restore_database_from_backup,
        validate_row_counts,
    )
except Exception as exc:
    DB_UPGRADE_SAFETY_AVAILABLE = False

    def collect_row_counts(conn, table_names):
        counts = {}
        for table_name in table_names:
            try:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone()
                if not row:
                    counts[table_name] = 0
                    continue
                row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
                counts[table_name] = int(row_count[0] or 0) if row_count else 0
            except sqlite3.Error:
                counts[table_name] = 0
        return counts

    def create_timestamped_backup(db_path, logger=None, reason="migration"):
        if logger:
            logger.warning(
                "db_upgrade_safety unavailable; skipping automatic backup creation and using fallback startup mode."
            )
        return None

    def is_sqlite_file(path):
        return bool(path and os.path.exists(path) and os.path.isfile(path))

    def restore_database_from_backup(backup_path, db_path, logger=None):
        if logger:
            logger.warning("db_upgrade_safety unavailable; automatic restore is disabled in fallback mode.")
        return False

    def validate_row_counts(before_counts, after_counts):
        failures = []
        for table_name, before_count in (before_counts or {}).items():
            after_count = int((after_counts or {}).get(table_name, 0))
            if after_count < int(before_count):
                failures.append((table_name, int(before_count), after_count))
        return failures

    logging.getLogger(__name__).warning(
        "Optional module db_upgrade_safety failed to import; advanced startup protections are disabled. Error: %s",
        exc,
    )

try:
    from erp_migrations import run_foundation_migrations
except Exception as exc:
    ERP_MIGRATIONS_AVAILABLE = False

    def run_foundation_migrations(conn, logger=None):
        if logger:
            logger.warning(
                "Optional module erp_migrations failed to import; skipping advanced ERP foundation migrations."
            )
        return False

    logging.getLogger(__name__).warning(
        "Optional module erp_migrations failed to import; startup will continue in compatibility mode. Error: %s",
        exc,
    )

try:
    import firebase_admin
    from firebase_admin import credentials, initialize_app, storage
except Exception:
    firebase_admin = None
    credentials = None
    initialize_app = None
    storage = None

# =================================================================
# 1. SYSTEM LOGGING & CONFIGURATION
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_SUBSCRIPTION_TRIAL_DAYS = 7
SUBSCRIPTION_BILLING_STATUSES = {"trial", "active", "expired", "cancelled"}
logger.info("database module loaded successfully")

IFRS_CHART_OF_ACCOUNTS = [
    ("Assets", "Asset", None),
    ("Current Assets", "Asset", "Assets"),
    ("Cash", "Asset", "Current Assets"),
    ("Bank", "Asset", "Current Assets"),
    ("Mobile Money", "Asset", "Current Assets"),
    ("Accounts Receivable", "Asset", "Current Assets"),
    ("Inventory", "Asset", "Current Assets"),
    ("VAT Receivable", "Asset", "Current Assets"),
    ("Non-Current Assets", "Asset", "Assets"),
    ("Fixed Assets", "Asset", "Non-Current Assets"),
    ("Accumulated Depreciation", "Asset", "Non-Current Assets"),
    ("Liabilities", "Liability", None),
    ("Current Liabilities", "Liability", "Liabilities"),
    ("Accounts Payable", "Liability", "Current Liabilities"),
    ("Payroll Payable", "Liability", "Current Liabilities"),
    ("VAT Payable", "Liability", "Current Liabilities"),
    ("NHIL Payable", "Liability", "Current Liabilities"),
    ("GETFund Levy Payable", "Liability", "Current Liabilities"),
    ("Loans Payable", "Liability", "Current Liabilities"),
    ("Equity", "Equity", None),
    ("Owner Capital", "Equity", "Equity"),
    ("Retained Earnings", "Equity", "Equity"),
    ("Opening Balance Equity", "Equity", "Equity"),
    ("Income", "Income", None),
    ("Sales", "Income", "Income"),
    ("Sales Revenue", "Income", "Income"),
    ("Other Income", "Income", "Income"),
    ("Expenses", "Expense", None),
    ("Cost of Goods Sold", "Expense", "Expenses"),
    ("Purchases", "Expense", "Expenses"),
    ("Salary Expense", "Expense", "Expenses"),
    ("Rent Expense", "Expense", "Expenses"),
    ("Utilities Expense", "Expense", "Expenses"),
    ("Repairs and Maintenance", "Expense", "Expenses"),
    ("Depreciation Expense", "Expense", "Expenses"),
]

# Primary Database Path
DB_NAME = "eka_enterprise_v3.db"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "data")
DB_DIR = os.path.abspath(os.getenv("EKA_DATA_DIR", DEFAULT_DATA_DIR))
DB_PATH = os.path.join(DB_DIR, DB_NAME)
LEGACY_DB_PATH = os.path.abspath(DB_NAME)
FIREBASE_KEY_PATH = os.path.join(os.path.dirname(__file__), "firebase_key.json")
FIREBASE_DATABASE_URL = "https://eka-erp-cloud-vault-default-rtdb.firebaseio.com/"
FIREBASE_OBJECT_NAME = "backups/eka_enterprise_v3.db"
CURRENT_SCHEMA_VERSION = 2
ERP_SAFE_STARTUP_MODE = str(os.getenv("ERP_SAFE_STARTUP_MODE", "0")).strip().lower() in {"1", "true", "yes", "on"}
# Default to production-safe startup behavior so a redeploy does not silently create
# a fresh blank SQLite file. Local development can explicitly set ERP_PRODUCTION_MODE=0.
ERP_PRODUCTION_MODE = str(os.getenv("ERP_PRODUCTION_MODE", "1")).strip().lower() in {"1", "true", "yes", "on"}
CRITICAL_VALIDATION_TABLES = (
    "companies",
    "branches",
    "users",
    "inventory",
    "vouchers",
    "transactions",
    "journal_entries",
    "customers",
    "suppliers",
    "invoices",
    "bills",
    "payments",
)
DATABASE_REQUIRED_TABLES = (
    "companies",
    "company_subscriptions",
    "journal_entries",
    "journal_lines",
    "chart_of_accounts",
    "system_settings",
    "schema_version",
)
DATABASE_PRODUCTION_REQUIRED_TABLES = DATABASE_REQUIRED_TABLES + (
    "database_identity",
)
FIXED_ASSET_SCHEMA_COLUMN_DEFS = {
    "company_key": "TEXT",
    "asset_category": "TEXT",
    "purchase_date": "TEXT",
    "cost": "REAL DEFAULT 0",
    "opening_book_value": "REAL DEFAULT 0",
    "supplier_id": "INTEGER",
    "useful_life_years": "REAL DEFAULT 0",
    "residual_value": "REAL DEFAULT 0",
    "depreciation_method": "TEXT DEFAULT 'Straight-line'",
    "depreciation_rate": "REAL DEFAULT 0",
    "accumulated_depreciation": "REAL DEFAULT 0",
    "book_value": "REAL DEFAULT 0",
    "last_depreciation_date": "TEXT",
    "location": "TEXT",
    "custodian": "TEXT",
    "description": "TEXT",
    "notes": "TEXT",
    "acquisition_type": "TEXT DEFAULT 'Opening Balance Asset'",
    "acquisition_source": "TEXT",
    "payment_method": "TEXT",
    "owner_contributor_name": "TEXT",
    "owner_name": "TEXT",
    "status": "TEXT DEFAULT 'Active'",
    "approval_status": "TEXT DEFAULT 'Posted'",
    "approved_at": "TIMESTAMP",
    "approved_by": "TEXT",
    "posted_entry_id": "INTEGER",
    "acquisition_journal_entry_id": "INTEGER",
    "last_journal_sync_at": "TIMESTAMP",
    "created_by": "TEXT",
}

SCHEMA_MANIFEST = {
    "source_of_truth": {
        "companies": ("key", "name", "subscription_expiry", "status"),
        "company_subscriptions": ("company_key", "plan_name", "status", "start_date", "end_date"),
        "branches": ("branch_id", "company_key", "branch_name"),
        "users": ("company_key", "full_name", "login_key", "role", "status"),
        "chart_of_accounts": ("id", "name", "type", "account_name", "account_type", "posting_allowed", "control_account"),
        "journal_entries": ("id", "company_key", "date", "description", "approval_status"),
        "journal_lines": ("id", "entry_id", "account_id", "debit", "credit"),
        "customers": ("id", "company_key", "name", "currency"),
        "suppliers": ("id", "company_key", "name", "currency"),
        "invoices": ("id", "company_key", "invoice_number", "invoice_date", "approval_status", "amount"),
        "invoice_lines": ("id", "invoice_id", "item_name", "quantity", "unit_price", "line_total"),
        "bills": ("id", "company_key", "bill_number", "bill_date", "approval_status", "amount"),
        "payments": ("id", "company_key", "payment_date", "payment_type", "approval_status", "amount"),
        "payment_allocations": ("id", "company_key", "payment_id", "amount"),
        "inventory": ("id", "company_key", "item_name", "qty", "cost_price"),
        "stock_movements": ("id", "company_key", "inventory_item_id", "movement_type", "quantity"),
        "fixed_assets": ("id", "company_key", "asset_name", "asset_category", "purchase_date", "cost", "opening_book_value", "book_value", "location", "custodian", "description", "notes", "acquisition_type", "acquisition_source", "payment_method", "supplier_id", "owner_contributor_name", "owner_name", "posted_entry_id", "acquisition_journal_entry_id", "last_journal_sync_at", "status"),
        "payroll": ("id", "company_key", "emp_name", "net_salary", "status"),
        "vouchers": ("id", "company_key", "date", "v_type", "approval_status"),
        "bank_accounts": ("id", "company_key", "account_name", "currency"),
        "accounting_periods": ("id", "company_key", "period_label", "is_locked"),
        "system_settings": ("id", "base_currency", "display_currency", "exchange_rate"),
        "audit_logs": ("id", "company_key", "user_role", "action", "module_name"),
        "schema_version": ("version", "description", "applied_at"),
        "database_identity": ("instance_id", "created_at", "last_verified_at", "schema_version", "last_startup_at", "backend_label", "environment_label"),
    },
    "compatibility_detail": {
        "customer_transactions": ("id", "company_key", "customer_id", "transaction_type", "amount"),
        "supplier_transactions": ("id", "company_key", "supplier_id", "transaction_type", "amount"),
        "bill_lines": ("id", "bill_id", "item_name", "quantity", "unit_price", "line_total"),
        "payroll_records": ("id", "company_key", "employee_name", "net_pay", "status"),
        "recurring_transactions": ("id", "company_key", "description", "frequency", "next_run_date"),
        "transactions": ("id", "company_key", "transaction_date", "account", "debit", "credit"),
        "system_logs": ("id", "timestamp", "level", "module_name", "message"),
        "counterparties": ("id", "company_key", "party_name", "party_type"),
        "maintenance_settings": ("id", "maintenance_date", "is_active", "message"),
        "pending_approvals": ("id", "company_key", "payment_reference", "amount"),
        "license_payment_transactions": ("id", "reference", "company_key", "plan_name", "expected_amount", "currency", "status"),
        "accounts_payable": ("id", "vendor", "amount", "status", "due_date"),
        "purchase_orders": ("id", "item", "quantity", "cost", "status"),
    },
    "legacy_obsolete": {
        "sales_invoices": ("id", "customer_name", "amount", "status", "date"),
        "stock": ("id", "barcode"),
        "supplier_ledger": (),
    },
}
SCHEMA_MANIFEST_VERSION = 1
FIREBASE_RECOVERY_APP = None
FIREBASE_RECOVERY_BUCKET_NAME = None
BACKUP_HISTORY_PREFIX = "backups/history"
LOCAL_BACKUP_ROOT = os.path.join(DB_DIR, "backups")
LOCAL_LATEST_BACKUP_DIR = os.path.join(LOCAL_BACKUP_ROOT, "latest")
LOCAL_HISTORY_BACKUP_DIR = os.path.join(LOCAL_BACKUP_ROOT, "history")
LOCAL_LATEST_BACKUP_PATH = os.path.join(LOCAL_LATEST_BACKUP_DIR, DB_NAME)
LOCAL_RESTORE_GUARD_PATH = os.path.join(DB_DIR, "restore_guard.json")
BACKUP_TRIGGER_TABLES = {
    "companies",
    "branches",
    "users",
    "customers",
    "suppliers",
    "invoices",
    "bills",
    "payments",
    "journal_entries",
    "journal_lines",
    "inventory",
    "stock_movements",
    "transactions",
    "vouchers",
}
BACKUP_DEBOUNCE_SECONDS = max(int(os.getenv("EKA_BACKUP_DEBOUNCE_SECONDS", "20") or 20), 0)
LAST_BACKUP_STATUS = {
    "status": "not_started",
    "timestamp": None,
    "reason": "no backup attempted yet",
    "latest_object": FIREBASE_OBJECT_NAME,
    "history_object": None,
    "trigger_tables": [],
}
LAST_LOCAL_BACKUP_STATUS = {
    "status": "not_started",
    "timestamp": None,
    "reason": "no local backup attempted yet",
    "latest_path": LOCAL_LATEST_BACKUP_PATH,
    "history_path": None,
    "trigger_tables": [],
}
LAST_BACKUP_SIGNATURE = None
LAST_BACKUP_AT = 0.0
LAST_RESTORE_SOURCE = "local_runtime_database"
LAST_CLOUD_RESTORE_SKIP_REASON = None
LAST_CLOUD_UPLOAD_BLOCK_REASON = None
SQLITE_BUSY_TIMEOUT_MS = max(int(os.getenv("EKA_SQLITE_BUSY_TIMEOUT_MS", "10000") or 10000), 1000)
SQLITE_LOCK_RETRY_ATTEMPTS = max(int(os.getenv("EKA_SQLITE_LOCK_RETRY_ATTEMPTS", "5") or 5), 1)
SQLITE_LOCK_RETRY_BASE_SECONDS = max(float(os.getenv("EKA_SQLITE_LOCK_RETRY_BASE_SECONDS", "0.05") or 0.05), 0.01)
SQLITE_OPERATION_LOCK_TIMEOUT_SECONDS = max(
    float(os.getenv("EKA_SQLITE_OPERATION_LOCK_TIMEOUT_SECONDS", "15") or 15),
    1.0,
)
SQLITE_CRITICAL_OPERATION_NAMES = {
    "pos_finalization",
    "payroll_posting",
    "depreciation_run",
    "inventory_import",
    "cloud_backup_sync",
    "year_end_close",
}
SQLITE_CONCURRENCY_DIAGNOSTICS = {
    "connection_opened": 0,
    "connection_closed": 0,
    "active_connections": 0,
    "max_active_connections": 0,
    "write_transactions_started": 0,
    "write_transactions_committed": 0,
    "write_transactions_rolled_back": 0,
    "lock_retries": 0,
    "failed_lock_acquisitions": 0,
    "backup_overlap_events": 0,
    "active_write_operations": {},
    "longest_write_seconds": 0.0,
    "longest_write_operation": None,
    "total_lock_wait_seconds": 0.0,
    "last_lock_error": None,
    "last_write_failure": None,
}
SQLITE_DIAGNOSTICS_LOCK = threading.RLock()
SQLITE_OPERATION_LOCKS = {}
EMPTY_DB_LOCKDOWN_MESSAGE = (
    "No company data was loaded. A valid cloud backup could not be restored. "
    "Do not register a new company until recovery is completed."
)


def get_firebase_runtime_config():
    return {
        "databaseURL": str(_read_runtime_secret("FIREBASE_DATABASE_URL", FIREBASE_DATABASE_URL) or "").strip(),
        "storageBucket": str(_read_runtime_secret("FIREBASE_STORAGE_BUCKET", "") or "").strip(),
        "backupObject": str(_read_runtime_secret("FIREBASE_DB_BACKUP_OBJECT", FIREBASE_OBJECT_NAME) or FIREBASE_OBJECT_NAME).strip(),
        "key_path": FIREBASE_KEY_PATH,
    }


def get_schema_manifest():
    """Return the authoritative schema classification used by startup diagnostics."""
    return {
        classification: {
            table_name: tuple(required_columns)
            for table_name, required_columns in tables.items()
        }
        for classification, tables in SCHEMA_MANIFEST.items()
    }


def _get_existing_tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row[0]) for row in rows}


def _get_existing_columns(conn, table_name):
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    except sqlite3.Error:
        return set()


def _load_restore_guard_state():
    if not os.path.exists(LOCAL_RESTORE_GUARD_PATH):
        return {"active": False}
    try:
        with open(LOCAL_RESTORE_GUARD_PATH, "r", encoding="utf-8") as guard_file:
            payload = json.load(guard_file)
        payload["active"] = bool(payload.get("active"))
        return payload
    except Exception as exc:
        logger.warning("Restore guard state could not be read: %s", sanitize_error_message(exc))
        return {"active": False, "reason": "guard_read_failed"}


def _write_restore_guard_state(payload, logger_instance=None):
    logger_instance = logger_instance or logger
    os.makedirs(DB_DIR, exist_ok=True)
    with open(LOCAL_RESTORE_GUARD_PATH, "w", encoding="utf-8") as guard_file:
        json.dump(payload, guard_file, indent=2, default=str)
    logger_instance.info(
        "Restore guard state updated: active=%s source=%s restored_company_count=%s",
        payload.get("active"),
        payload.get("source_db_path"),
        payload.get("restored_company_count"),
    )


def _clear_restore_guard_state(logger_instance=None):
    logger_instance = logger_instance or logger
    if os.path.exists(LOCAL_RESTORE_GUARD_PATH):
        try:
            os.remove(LOCAL_RESTORE_GUARD_PATH)
            logger_instance.info("Restore guard state cleared: %s", LOCAL_RESTORE_GUARD_PATH)
        except OSError as exc:
            logger_instance.warning("Restore guard state could not be cleared: %s", sanitize_error_message(exc))


def get_schema_manifest_diagnostics(conn=None):
    """
    Compare the live database schema with the manifest.
    This is diagnostic-only and never creates, drops, or rewrites data.
    """
    owns_connection = conn is None
    diagnostics_conn = conn
    if diagnostics_conn is None:
        diagnostics_conn = get_connection()
    try:
        existing_tables = _get_existing_tables(diagnostics_conn)
        manifest = get_schema_manifest()
        categories = {}
        missing_required_columns = {}
        for classification, tables in manifest.items():
            present = []
            missing = []
            for table_name, required_columns in tables.items():
                if table_name in existing_tables:
                    present.append(table_name)
                    if classification != "legacy_obsolete":
                        existing_columns = _get_existing_columns(diagnostics_conn, table_name)
                        missing_columns = [
                            column_name
                            for column_name in required_columns
                            if column_name and column_name not in existing_columns
                        ]
                        if missing_columns:
                            missing_required_columns[table_name] = missing_columns
                else:
                    missing.append(table_name)
            categories[classification] = {
                "present": sorted(present),
                "missing": sorted(missing),
                "total": len(tables),
            }
        legacy_present = categories["legacy_obsolete"]["present"]
        warnings = []
        if categories["source_of_truth"]["missing"]:
            warnings.append(
                "Missing source-of-truth tables: " + ", ".join(categories["source_of_truth"]["missing"])
            )
        if missing_required_columns:
            warnings.append(
                "Missing required columns: "
                + "; ".join(
                    f"{table_name}({', '.join(columns)})"
                    for table_name, columns in sorted(missing_required_columns.items())
                )
            )
        if legacy_present:
            warnings.append("Legacy/obsolete tables still present: " + ", ".join(legacy_present))
        return {
            "manifest_version": SCHEMA_MANIFEST_VERSION,
            "db_path": DB_PATH,
            "categories": categories,
            "required_production_tables": sorted(manifest["source_of_truth"].keys()),
            "compatibility_detail_tables": sorted(manifest["compatibility_detail"].keys()),
            "legacy_obsolete_tables": sorted(manifest["legacy_obsolete"].keys()),
            "missing_source_of_truth_tables": categories["source_of_truth"]["missing"],
            "missing_compatibility_detail_tables": categories["compatibility_detail"]["missing"],
            "legacy_obsolete_tables_present": legacy_present,
            "missing_required_columns": missing_required_columns,
            "warnings": warnings,
            "ok": not categories["source_of_truth"]["missing"] and not missing_required_columns,
        }
    except sqlite3.Error as exc:
        return {
            "manifest_version": SCHEMA_MANIFEST_VERSION,
            "db_path": DB_PATH,
            "categories": {},
            "required_production_tables": sorted(SCHEMA_MANIFEST["source_of_truth"].keys()),
            "compatibility_detail_tables": sorted(SCHEMA_MANIFEST["compatibility_detail"].keys()),
            "legacy_obsolete_tables": sorted(SCHEMA_MANIFEST["legacy_obsolete"].keys()),
            "missing_source_of_truth_tables": [],
            "missing_compatibility_detail_tables": [],
            "legacy_obsolete_tables_present": [],
            "missing_required_columns": {},
            "warnings": [f"Schema diagnostics unavailable: {exc}"],
            "ok": False,
        }
    finally:
        if owns_connection and diagnostics_conn:
            diagnostics_conn.close()


def get_fixed_assets_schema_diagnostics(conn=None, repair=False):
    """
    Report the fixed_assets self-heal state and optionally apply additive repairs.

    This is intentionally limited to ALTER TABLE ADD COLUMN on existing tables.
    It never recreates fixed_assets and never deletes or overwrites asset records.
    """
    owns_connection = conn is None
    diagnostics_conn = conn or get_connection()
    table_name = "fixed_assets"
    expected_columns = dict(FIXED_ASSET_SCHEMA_COLUMN_DEFS)
    expected_columns.setdefault("id", "INTEGER")
    expected_columns.setdefault("asset_name", "TEXT")
    repaired_columns = []
    failed_repairs = []
    if diagnostics_conn is None:
        return {
            "table": table_name,
            "table_exists": False,
            "expected_columns": sorted(expected_columns),
            "existing_columns": [],
            "missing_columns": sorted(expected_columns),
            "repaired_columns": [],
            "failed_repairs": [{"column": None, "error": "Database connection unavailable."}],
            "ok": False,
        }
    try:
        table_exists = table_name in _get_existing_tables(diagnostics_conn)
        if not table_exists:
            return {
                "table": table_name,
                "table_exists": False,
                "expected_columns": sorted(expected_columns),
                "existing_columns": [],
                "missing_columns": sorted(expected_columns),
                "repaired_columns": [],
                "failed_repairs": [],
                "ok": False,
            }
        existing_columns = _get_existing_columns(diagnostics_conn, table_name)
        missing_columns = [
            column_name
            for column_name in expected_columns
            if column_name not in existing_columns and column_name not in {"id", "asset_name"}
        ]
        if repair:
            for column_name in list(missing_columns):
                column_def = expected_columns[column_name]
                try:
                    diagnostics_conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
                    repaired_columns.append(column_name)
                    existing_columns.add(column_name)
                except sqlite3.Error as exc:
                    failed_repairs.append(
                        {
                            "column": column_name,
                            "error": sanitize_error_message(exc),
                        }
                    )
            if owns_connection:
                diagnostics_conn.commit()
            missing_columns = [
                column_name
                for column_name in expected_columns
                if column_name not in existing_columns and column_name not in {"id", "asset_name"}
            ]
        return {
            "table": table_name,
            "table_exists": True,
            "expected_columns": sorted(expected_columns),
            "existing_columns": sorted(existing_columns),
            "missing_columns": sorted(missing_columns),
            "repaired_columns": sorted(repaired_columns),
            "failed_repairs": failed_repairs,
            "ok": not missing_columns and not failed_repairs,
        }
    except sqlite3.Error as exc:
        return {
            "table": table_name,
            "table_exists": False,
            "expected_columns": sorted(expected_columns),
            "existing_columns": [],
            "missing_columns": sorted(expected_columns),
            "repaired_columns": sorted(repaired_columns),
            "failed_repairs": [{"column": None, "error": sanitize_error_message(exc)}],
            "ok": False,
        }
    finally:
        if owns_connection and diagnostics_conn:
            diagnostics_conn.close()


def log_schema_manifest_diagnostics(conn):
    diagnostics = get_schema_manifest_diagnostics(conn)
    logger.info(
        "Schema manifest check: ok=%s source_missing=%s compatibility_missing=%s legacy_present=%s missing_columns=%s",
        diagnostics["ok"],
        diagnostics["missing_source_of_truth_tables"],
        diagnostics["missing_compatibility_detail_tables"],
        diagnostics["legacy_obsolete_tables_present"],
        diagnostics["missing_required_columns"],
    )
    for warning in diagnostics.get("warnings", []):
        logger.warning("Schema manifest warning: %s", warning)
    return diagnostics


POSTGRES_AUDIT_FILES = (
    "database.py",
    "accounting_engine.py",
    "financials.py",
    "modules.py",
    "enterprise_services.py",
    "app.py",
)


POSTGRES_READINESS_PATTERNS = {
    "direct_sqlite3_usage": "sqlite3",
    "pragma_usage": "PRAGMA",
    "sqlite_autoincrement": "AUTOINCREMENT",
    "insert_or_ignore": "INSERT OR IGNORE",
    "last_insert_rowid": "last_insert_rowid",
    "lastrowid_usage": "lastrowid",
    "sqlite_master_usage": "sqlite_master",
    "sqlite_date_function": "date(",
    "question_mark_placeholders": "?",
    "db_path_file_assumption": "DB_PATH",
}


def _scan_postgres_readiness_sources():
    findings = {key: [] for key in POSTGRES_READINESS_PATTERNS}
    for relative_path in POSTGRES_AUDIT_FILES:
        file_path = os.path.join(BASE_DIR, relative_path)
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as source_file:
                for line_number, line in enumerate(source_file, start=1):
                    for key, pattern in POSTGRES_READINESS_PATTERNS.items():
                        if pattern in line:
                            findings[key].append({"file": relative_path, "line": line_number})
        except OSError:
            continue
    return findings


def get_postgres_readiness_diagnostics(conn=None):
    findings = _scan_postgres_readiness_sources()
    blocker_keys = {
        "direct_sqlite3_usage",
        "pragma_usage",
        "sqlite_autoincrement",
        "insert_or_ignore",
        "last_insert_rowid",
        "lastrowid_usage",
        "sqlite_master_usage",
        "db_path_file_assumption",
    }
    blockers = [
        {
            "key": key,
            "count": len(rows),
            "examples": rows[:5],
        }
        for key, rows in sorted(findings.items())
        if rows and key in blocker_keys
    ]
    warning_count = sum(len(rows) for rows in findings.values())
    blocker_count = sum(item["count"] for item in blockers)
    score = max(0, 100 - min(85, blocker_count * 2) - min(15, max(0, warning_count - blocker_count) // 10))
    table_notes = {}
    owns_connection = conn is None
    diagnostics_conn = conn
    try:
        diagnostics_conn = diagnostics_conn or get_connection()
        if diagnostics_conn:
            tables = [
                row["name"]
                for row in diagnostics_conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                if not str(row["name"]).startswith("sqlite_")
            ]
            for table_name in tables:
                columns = diagnostics_conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                pk_columns = [row[1] for row in columns if int(row[5] or 0) > 0]
                column_names = {row[1] for row in columns}
                table_notes[table_name] = {
                    "has_primary_key": bool(pk_columns),
                    "primary_key_columns": pk_columns,
                    "has_created_at": "created_at" in column_names,
                    "has_updated_at": "updated_at" in column_names,
                }
    except Exception as exc:
        table_notes["_error"] = {"reason": sanitize_error_message(exc)}
    finally:
        if owns_connection and diagnostics_conn:
            diagnostics_conn.close()

    source_document_unique_constraints_needed = [
        "journal_entries(company_key, source_table, source_id, source_type)",
        "pos_sales(company_key, receipt_number)",
        "payments(company_key, reference)",
    ]
    journal_indexes_needed = [
        "journal_entries(company_key, date)",
        "journal_entries(company_key, source_table, source_id)",
        "journal_lines(entry_id)",
        "journal_lines(account_id)",
    ]
    return {
        "configured_backend": get_db_backend(),
        "active_backend": get_active_db_backend(),
        "database_url_configured": bool(_get_database_url()),
        "database_url_label": _redact_database_url(_get_database_url()),
        "supabase_sslmode": _postgres_sslmode(_get_database_url()) or "missing",
        "postgres_runtime_enabled": POSTGRES_RUNTIME_ENABLED,
        "sqlite_concurrency_warning": (
            "SQLite is suitable for pilot/small-client use but not high-concurrency enterprise deployment."
            if get_active_db_backend() == "sqlite"
            else ""
        ),
        "readiness_score": score,
        "blockers": blockers,
        "sqlite_only_constructs": {key: len(rows) for key, rows in findings.items() if rows},
        "table_readiness": table_notes,
        "source_document_unique_constraints_needed": source_document_unique_constraints_needed,
        "journal_indexes_needed": journal_indexes_needed,
        "switch_blocked": bool(blockers) or get_active_db_backend() != "postgres",
    }


def get_data_migration_export_plan(conn=None):
    owns_connection = conn is None
    diagnostics_conn = conn
    tables = []
    try:
        diagnostics_conn = diagnostics_conn or get_connection()
        if diagnostics_conn:
            for row in diagnostics_conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall():
                table_name = row["name"]
                if str(table_name).startswith("sqlite_"):
                    continue
                count_row = diagnostics_conn.execute(f"SELECT COUNT(*) AS row_count FROM {table_name}").fetchone()
                columns = [column[1] for column in diagnostics_conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
                tables.append(
                    {
                        "table": table_name,
                        "row_count": int(count_row["row_count"] or 0),
                        "columns": columns,
                    }
                )
    finally:
        if owns_connection and diagnostics_conn:
            diagnostics_conn.close()
    export_order = [
        "companies",
        "branches",
        "users",
        "chart_of_accounts",
        "customers",
        "suppliers",
        "inventory",
        "invoices",
        "bills",
        "payments",
        "journal_entries",
        "journal_lines",
        "stock_movements",
        "payroll",
        "fixed_assets",
        "tax_settlements",
        "audit_logs",
    ]
    return {
        "mode": "report_only",
        "tables": tables,
        "table_count": len(tables),
        "export_order": export_order,
        "foreign_key_risk_notes": [
            "Preserve company_key values before dependent operational rows.",
            "Load journal_entries before journal_lines.",
            "Load invoices/bills/payments before payment_allocations.",
            "Validate source-document IDs before enabling duplicate-post constraints.",
        ],
    }


def _read_runtime_secret(secret_name, default=None):
    env_value = os.getenv(secret_name)
    if env_value not in (None, ""):
        return env_value
    if st is None:
        return default
    try:
        if secret_name in st.secrets:
            return st.secrets[secret_name]
    except Exception:
        return default
    return default


SUPPORTED_DB_BACKENDS = {"sqlite", "postgres", "postgresql", "supabase"}
POSTGRES_RUNTIME_ENABLED = str(os.getenv("ERP_ENABLE_POSTGRES_RUNTIME", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_db_backend(value=None):
    normalized = str(value or "sqlite").strip().lower()
    if normalized in {"postgresql", "supabase"}:
        return "postgres"
    if normalized not in SUPPORTED_DB_BACKENDS:
        return "sqlite"
    return normalized


def get_db_backend():
    """Return the configured backend without exposing connection secrets."""
    return _normalize_db_backend(_read_runtime_secret("DB_BACKEND", os.getenv("DB_BACKEND", "sqlite")))


def get_active_db_backend():
    configured_backend = get_db_backend()
    if configured_backend == "postgres" and POSTGRES_RUNTIME_ENABLED:
        return "postgres"
    return "sqlite"


def is_sqlite():
    return get_active_db_backend() == "sqlite"


def is_postgres():
    return get_active_db_backend() == "postgres"


def is_test_runtime():
    """Detect whether the current process is running automated tests."""
    test_flag = str(os.getenv("EKA_TEST_MODE", "") or "").strip().lower()
    if test_flag in {"1", "true", "yes", "on"}:
        return True
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    if os.getenv("UNITTEST_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    db_path = str(globals().get("DB_PATH", "") or "").lower()
    temp_dir = str(tempfile.gettempdir()).lower()
    if temp_dir and temp_dir in db_path:
        return True
    if ".test-tmp" in db_path or "pytest" in db_path or "unittest" in db_path or os.path.basename(db_path).startswith("test_"):
        return True
    return False


def is_automated_test_runtime():
    """Explicit helper for automated test runtime detection."""
    test_flag = str(os.getenv("EKA_TEST_MODE", "") or "").strip().lower()
    if test_flag in {"1", "true", "yes", "on"}:
        return True
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    if os.getenv("UNITTEST_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return False


def is_local_development_runtime():
    """Return True when runtime is clearly local development and not tests."""
    return not ERP_PRODUCTION_MODE and not is_test_runtime()


def is_streamlit_cloud_production():
    """Return True when running on Streamlit Cloud in production mode."""
    return is_streamlit_cloud() and ERP_PRODUCTION_MODE and not is_test_runtime()


def is_production_runtime():
    """Return True when runtime is production and not automated tests."""
    return ERP_PRODUCTION_MODE and not is_test_runtime()


def get_runtime_mode():
    """Return a normalized runtime mode label."""
    if is_test_runtime():
        return "automated_test"
    if is_streamlit_cloud_production():
        return "streamlit_cloud_production"
    if ERP_PRODUCTION_MODE:
        return "production"
    return "local_development"


def is_streamlit_cloud():
    """Detect deployed Streamlit Cloud environments safely."""
    if os.getenv("STREAMLIT_SERVER_PORT"):
        return True
    home_dir = str(os.getenv("HOME", "")).lower()
    if "/home/appuser" in home_dir or "/mount/src" in home_dir:
        return True
    if st is not None:
        try:
            _ = st.secrets
            return True
        except Exception:
            pass
    return False


def is_force_cloud_restore_enabled():
    """Return whether explicit FORCE_CLOUD_RESTORE is enabled, but never during tests."""
    if is_test_runtime():
        return False
    force_flag = str(os.getenv("FORCE_CLOUD_RESTORE", "0") or "").strip().lower()
    return force_flag in {"1", "true", "yes", "on"}


def is_test_cloud_restore_allowed():
    """Return whether test code has explicitly enabled cloud restore during automated tests."""
    allow_flag = str(os.getenv("EKA_ALLOW_TEST_CLOUD_RESTORE", "0") or "").strip().lower()
    return allow_flag in {"1", "true", "yes", "on"}


def is_test_cloud_backup_allowed():
    """Return whether test code has explicitly enabled cloud backup during automated tests."""
    allow_flag = str(os.getenv("EKA_ALLOW_TEST_CLOUD_BACKUP", "0") or "").strip().lower()
    return allow_flag in {"1", "true", "yes", "on"}


def is_automatic_cloud_restore_allowed():
    """Return whether automatic cloud restore should be attempted in this runtime."""
    return is_production_runtime()


def _get_database_url():
    return str(_read_runtime_secret("DATABASE_URL", os.getenv("DATABASE_URL", "")) or "").strip()


def _redact_database_url(database_url):
    if not database_url:
        return ""
    try:
        parsed = urlparse(database_url)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        username = parsed.username or ""
        auth = f"{username}:***@" if username else ""
        return urlunparse((parsed.scheme, f"{auth}{host}{port}", parsed.path, "", "", ""))
    except Exception:
        return "[redacted-database-url]"


def _postgres_sslmode(database_url=None):
    database_url = database_url if database_url is not None else _get_database_url()
    try:
        query = parse_qs(urlparse(database_url).query)
        values = query.get("sslmode") or []
        return values[0] if values else ""
    except Exception:
        return ""


def get_engine():
    """Return an optional SQLAlchemy engine for future PostgreSQL/Supabase runtime use.

    SQLite remains the active runtime unless ERP_ENABLE_POSTGRES_RUNTIME=1 is set.
    """
    if get_active_db_backend() != "postgres":
        return None
    database_url = _get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required when PostgreSQL runtime is enabled.")
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool
    except Exception as exc:
        raise RuntimeError("SQLAlchemy is required for PostgreSQL runtime connections.") from exc
    connect_args = {}
    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"
    return create_engine(database_url, poolclass=NullPool, pool_pre_ping=True, connect_args=connect_args)


def db_param_placeholder(index=1, backend=None):
    backend = _normalize_db_backend(backend or get_active_db_backend())
    return f"${int(index)}" if backend == "postgres" else "?"


def db_placeholders(count, backend=None):
    backend = _normalize_db_backend(backend or get_active_db_backend())
    return ", ".join(db_param_placeholder(index + 1, backend=backend) for index in range(int(count or 0)))


def db_current_timestamp_sql(backend=None):
    return "CURRENT_TIMESTAMP"


def db_boolean_value(value, backend=None):
    backend = _normalize_db_backend(backend or get_active_db_backend())
    return bool(value) if backend == "postgres" else (1 if value else 0)


def db_limit_offset_clause(limit=None, offset=None, backend=None):
    parts = []
    if limit is not None:
        parts.append(f"LIMIT {int(limit)}")
    if offset is not None:
        parts.append(f"OFFSET {int(offset)}")
    return " ".join(parts)


def db_insert_ignore_sql(table_name, columns, conflict_columns=None, backend=None):
    backend = _normalize_db_backend(backend or get_active_db_backend())
    columns = [str(column).strip() for column in columns if str(column).strip()]
    placeholders = db_placeholders(len(columns), backend=backend)
    column_sql = ", ".join(columns)
    if backend == "postgres":
        conflict_sql = ""
        if conflict_columns:
            conflict_sql = " (" + ", ".join(str(column).strip() for column in conflict_columns) + ")"
        return f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders}) ON CONFLICT{conflict_sql} DO NOTHING"
    return f"INSERT OR IGNORE INTO {table_name} ({column_sql}) VALUES ({placeholders})"


def db_table_exists(conn, table_name):
    if conn is None:
        return False
    if is_postgres():
        row = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            (table_name,),
        ).fetchone()
        return bool(row[0] if row else False)
    return bool(
        conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)).fetchone()
    )


def db_column_exists(conn, table_name, column_name):
    if conn is None:
        return False
    if is_postgres():
        row = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
            )
            """,
            (table_name, column_name),
        ).fetchone()
        return bool(row[0] if row else False)
    return column_name in {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def db_create_index_sql(index_name, table_name, columns, unique=False, backend=None):
    unique_sql = "UNIQUE " if unique else ""
    column_sql = ", ".join(str(column).strip() for column in columns)
    return f"CREATE {unique_sql}INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_sql})"


def db_begin(conn):
    if conn is not None:
        conn.execute("BEGIN")


def db_commit(conn):
    if conn is not None:
        conn.commit()


def db_rollback(conn):
    if conn is not None:
        conn.rollback()


def _sqlite_lock_error(exc):
    if not isinstance(exc, sqlite3.Error):
        return False
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message or "sqlite_busy" in message


def _diagnostic_increment(key, amount=1):
    with SQLITE_DIAGNOSTICS_LOCK:
        SQLITE_CONCURRENCY_DIAGNOSTICS[key] = SQLITE_CONCURRENCY_DIAGNOSTICS.get(key, 0) + amount


def _diagnostic_set(key, value):
    with SQLITE_DIAGNOSTICS_LOCK:
        SQLITE_CONCURRENCY_DIAGNOSTICS[key] = value


def _diagnostic_connection_opened():
    with SQLITE_DIAGNOSTICS_LOCK:
        SQLITE_CONCURRENCY_DIAGNOSTICS["connection_opened"] += 1
        SQLITE_CONCURRENCY_DIAGNOSTICS["active_connections"] += 1
        SQLITE_CONCURRENCY_DIAGNOSTICS["max_active_connections"] = max(
            SQLITE_CONCURRENCY_DIAGNOSTICS["max_active_connections"],
            SQLITE_CONCURRENCY_DIAGNOSTICS["active_connections"],
        )


def _diagnostic_connection_closed():
    with SQLITE_DIAGNOSTICS_LOCK:
        SQLITE_CONCURRENCY_DIAGNOSTICS["connection_closed"] += 1
        SQLITE_CONCURRENCY_DIAGNOSTICS["active_connections"] = max(
            int(SQLITE_CONCURRENCY_DIAGNOSTICS.get("active_connections") or 0) - 1,
            0,
        )


def with_retry_on_lock(operation, operation_name="sqlite_operation", attempts=None, base_delay=None, logger_instance=None):
    attempts = int(attempts or SQLITE_LOCK_RETRY_ATTEMPTS)
    base_delay = float(base_delay or SQLITE_LOCK_RETRY_BASE_SECONDS)
    logger_instance = logger_instance or logger
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except sqlite3.Error as exc:
            if not _sqlite_lock_error(exc) or attempt >= attempts:
                _diagnostic_set("last_lock_error", sanitize_error_message(exc))
                raise
            last_error = exc
            wait_seconds = min(base_delay * (2 ** (attempt - 1)), 1.0)
            _diagnostic_increment("lock_retries")
            _diagnostic_increment("total_lock_wait_seconds", wait_seconds)
            logger_instance.warning(
                "SQLite lock retry: operation=%s attempt=%s/%s wait=%.3fs reason=%s",
                operation_name,
                attempt,
                attempts,
                wait_seconds,
                sanitize_error_message(exc),
            )
            time.sleep(wait_seconds)
    if last_error:
        raise last_error


def _operation_lock_for(name):
    normalized = str(name or "sqlite_write").strip() or "sqlite_write"
    with SQLITE_DIAGNOSTICS_LOCK:
        lock = SQLITE_OPERATION_LOCKS.get(normalized)
        if lock is None:
            lock = threading.RLock()
            SQLITE_OPERATION_LOCKS[normalized] = lock
        return lock


@contextmanager
def sqlite_operation_lock(name, timeout=None):
    normalized = str(name or "sqlite_write").strip() or "sqlite_write"
    lock = _operation_lock_for(normalized)
    start = time.monotonic()
    acquired = lock.acquire(timeout=float(timeout or SQLITE_OPERATION_LOCK_TIMEOUT_SECONDS))
    wait_seconds = time.monotonic() - start
    _diagnostic_increment("total_lock_wait_seconds", wait_seconds)
    if not acquired:
        _diagnostic_increment("failed_lock_acquisitions")
        raise TimeoutError(f"Could not acquire SQLite operation lock for {normalized}")
    with SQLITE_DIAGNOSTICS_LOCK:
        SQLITE_CONCURRENCY_DIAGNOSTICS["active_write_operations"][normalized] = {
            "started_at": datetime.utcnow().isoformat(timespec="seconds"),
            "wait_seconds": round(wait_seconds, 4),
        }
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        with SQLITE_DIAGNOSTICS_LOCK:
            SQLITE_CONCURRENCY_DIAGNOSTICS["active_write_operations"].pop(normalized, None)
            if elapsed > float(SQLITE_CONCURRENCY_DIAGNOSTICS.get("longest_write_seconds") or 0.0):
                SQLITE_CONCURRENCY_DIAGNOSTICS["longest_write_seconds"] = round(elapsed, 4)
                SQLITE_CONCURRENCY_DIAGNOSTICS["longest_write_operation"] = normalized
        lock.release()


class SQLiteWriteTransaction:
    def __init__(self, operation_name="sqlite_write", conn=None, immediate=True, retries=None):
        self.operation_name = operation_name
        self.conn = conn
        self.owns_connection = conn is None
        self.immediate = bool(immediate)
        self.retries = retries

    def __enter__(self):
        def begin():
            self.conn = self.conn or get_connection()
            if self.conn is None:
                raise RuntimeError("Database connection unavailable.")
            if not getattr(self.conn, "in_transaction", False):
                self.conn.execute("BEGIN IMMEDIATE" if self.immediate else "BEGIN")
            return self.conn

        _diagnostic_increment("write_transactions_started")
        return with_retry_on_lock(begin, operation_name=self.operation_name, attempts=self.retries)

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
                _diagnostic_increment("write_transactions_committed")
            else:
                try:
                    self.conn.rollback()
                finally:
                    _diagnostic_increment("write_transactions_rolled_back")
                    _diagnostic_set("last_write_failure", sanitize_error_message(exc))
        finally:
            if self.owns_connection and self.conn:
                self.conn.close()
        return False


def execute_write_transaction(callback, operation_name="sqlite_write", conn=None, immediate=True, retries=None):
    with sqlite_operation_lock(operation_name):
        with SQLiteWriteTransaction(operation_name=operation_name, conn=conn, immediate=immediate, retries=retries) as tx_conn:
            return callback(tx_conn)


def execute_readonly_query(callback, operation_name="sqlite_read", conn=None, retries=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        return with_retry_on_lock(lambda: callback(conn), operation_name=operation_name, attempts=retries)
    finally:
        if owns_connection and conn:
            conn.close()


def get_sqlite_concurrency_diagnostics():
    with SQLITE_DIAGNOSTICS_LOCK:
        active_operations = dict(SQLITE_CONCURRENCY_DIAGNOSTICS.get("active_write_operations") or {})
        diagnostics = dict(SQLITE_CONCURRENCY_DIAGNOSTICS)
        diagnostics["active_write_operations"] = active_operations
    diagnostics.update(
        {
            "sqlite_active": is_sqlite(),
            "busy_timeout_ms": SQLITE_BUSY_TIMEOUT_MS,
            "retry_attempts": SQLITE_LOCK_RETRY_ATTEMPTS,
            "operation_lock_timeout_seconds": SQLITE_OPERATION_LOCK_TIMEOUT_SECONDS,
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
            "recommended_safe_user_limit": "3-5 active users for write-heavy pilot/SME workloads",
            "readiness_level": "pilot / SME",
            "advisory": (
                "SQLite is safe for small teams with short writes, but high-write multi-user ERP usage "
                "should move to PostgreSQL/Supabase before enterprise rollout."
            ),
        }
    )
    return diagnostics


def get_db_diagnostics():
    health = get_database_health_snapshot(DB_PATH, logger_instance=logger)
    readiness = get_postgres_readiness_diagnostics()
    return {
        "configured_backend": get_db_backend(),
        "active_backend": get_active_db_backend(),
        "is_sqlite": is_sqlite(),
        "is_postgres": is_postgres(),
        "database_url_configured": bool(_get_database_url()),
        "database_url_label": _redact_database_url(_get_database_url()),
        "db_path": DB_PATH,
        "db_exists": health.get("file_exists"),
        "company_count": health.get("company_count"),
        "schema_version": health.get("schema_version"),
        "database_uuid": health.get("database_uuid"),
        "postgres_readiness": readiness,
        "sqlite_concurrency": get_sqlite_concurrency_diagnostics(),
    }


def get_firebase_service_account_info():
    firebase_key_path = str(FIREBASE_KEY_PATH or "").strip()
    source_attempt_order = "structured Streamlit secrets -> local firebase_key.json -> legacy FIREBASE_SERVICE_ACCOUNT_JSON"
    invalid_secret_reason = (
        "invalid JSON in FIREBASE_SERVICE_ACCOUNT_JSON; likely cause: unescaped newline or control character in private_key"
    )
    streamlit_available = st is not None
    secrets_accessible = False
    streamlit_secret_keys = []
    structured_secret_exists_in_streamlit = False
    secret_exists_in_streamlit = False
    database_url_exists_in_streamlit = False
    streamlit_failure_reason = None
    structured_secret_payload = None

    if streamlit_available:
        logger.info("Firebase secret diagnostics: streamlit import succeeded")
        try:
            streamlit_secret_keys = sorted(str(key) for key in st.secrets.keys())
            secrets_accessible = True
            structured_secret_exists_in_streamlit = "FIREBASE_SERVICE_ACCOUNT" in st.secrets
            secret_exists_in_streamlit = "FIREBASE_SERVICE_ACCOUNT_JSON" in st.secrets
            database_url_exists_in_streamlit = "FIREBASE_DATABASE_URL" in st.secrets
            if structured_secret_exists_in_streamlit:
                structured_secret_payload = dict(st.secrets["FIREBASE_SERVICE_ACCOUNT"])
        except Exception as exc:
            streamlit_failure_reason = sanitize_error_message(
                f"st.secrets unavailable at runtime: {type(exc).__name__}: {exc}"
            )
            logger.warning("st.secrets unavailable at runtime")
    else:
        streamlit_failure_reason = "streamlit import failed"
        logger.warning("streamlit import unavailable at runtime")

    inline_json = _read_runtime_secret("FIREBASE_SERVICE_ACCOUNT_JSON", None)
    inline_json_length = len(str(inline_json)) if inline_json not in (None, "") else 0
    logger.info(
        "Firebase secret diagnostics: streamlit_available=%s secrets_accessible=%s secret_keys=%s FIREBASE_SERVICE_ACCOUNT_exists=%s FIREBASE_SERVICE_ACCOUNT_JSON_exists=%s FIREBASE_DATABASE_URL_exists=%s provided_length=%s",
        streamlit_available,
        secrets_accessible,
        streamlit_secret_keys,
        structured_secret_exists_in_streamlit,
        secret_exists_in_streamlit,
        database_url_exists_in_streamlit,
        inline_json_length,
    )
    if structured_secret_exists_in_streamlit:
        logger.info("Firebase credentials loaded from structured secrets")
        return {
            "ok": True,
            "source": "structured_secrets",
            "service_account_info": structured_secret_payload,
            "key_path": firebase_key_path,
        }
    if not secret_exists_in_streamlit:
        logger.warning("FIREBASE_SERVICE_ACCOUNT_JSON not found in st.secrets")
    if not database_url_exists_in_streamlit:
        logger.warning("FIREBASE_DATABASE_URL not found in st.secrets")

    if not streamlit_available:
        logger.warning("Firebase credentials missing because streamlit import is unavailable")
    elif not secrets_accessible:
        logger.warning("Firebase credentials missing because st.secrets is unavailable at runtime")
    elif not structured_secret_exists_in_streamlit and not secret_exists_in_streamlit:
        logger.warning(
            "Firebase credentials missing because neither FIREBASE_SERVICE_ACCOUNT nor FIREBASE_SERVICE_ACCOUNT_JSON is present in st.secrets"
        )

    if firebase_key_path and os.path.exists(firebase_key_path):
        try:
            with open(firebase_key_path, "r", encoding="utf-8") as firebase_file:
                service_account_info = json.load(firebase_file)
            logger.info("Firebase credentials loaded from local file fallback")
            return {
                "ok": True,
                "source": "file",
                "service_account_info": service_account_info,
                "key_path": firebase_key_path,
            }
        except Exception as exc:
            logger.warning("Firebase credentials missing: local firebase_key.json could not be read")
            return {
                "ok": False,
                "source": "file",
                "reason": sanitize_error_message(f"Firebase credentials from file are invalid: {exc}"),
                "key_path": firebase_key_path,
            }

    if not os.path.exists(firebase_key_path):
        logger.warning(
            "Firebase credentials missing because firebase_key.json is not present locally at path=%s",
            firebase_key_path,
        )

    if inline_json not in (None, ""):
        try:
            service_account_info = json.loads(str(inline_json))
            logger.info("Firebase secret diagnostics: json.loads succeeded")
            logger.info("Firebase credentials loaded from legacy JSON fallback")
            return {
                "ok": True,
                "source": "json_secret_fallback",
                "service_account_info": service_account_info,
                "key_path": firebase_key_path,
            }
        except Exception as exc:
            logger.warning(
                "Firebase secret diagnostics: json.loads failed exception_type=%s message=%s",
                type(exc).__name__,
                sanitize_error_message(str(exc)),
            )
            logger.warning("Firebase credentials missing: %s", sanitize_error_message(invalid_secret_reason))
            return {
                "ok": False,
                "source": "json_secret_fallback",
                "reason": sanitize_error_message(
                    f"Legacy JSON fallback failed after {source_attempt_order}. "
                    f"{invalid_secret_reason}. Parser detail: {exc}"
                ),
                "key_path": firebase_key_path,
            }

    if not streamlit_available:
        failure_reason = (
            f"Firebase credentials unavailable after {source_attempt_order}: "
            "streamlit import failed and firebase_key.json is missing"
        )
    elif not secrets_accessible:
        failure_reason = (
            f"Firebase credentials unavailable after {source_attempt_order}: "
            "st.secrets unavailable at runtime and firebase_key.json is missing"
        )
    elif not structured_secret_exists_in_streamlit and not secret_exists_in_streamlit:
        failure_reason = (
            f"Firebase credentials unavailable after {source_attempt_order}: both FIREBASE_SERVICE_ACCOUNT "
            "and FIREBASE_SERVICE_ACCOUNT_JSON are missing from st.secrets and firebase_key.json is missing"
        )
    else:
        failure_reason = f"Firebase credentials not found after {source_attempt_order}"

    logger.warning("Firebase credentials missing")
    return {
        "ok": False,
        "source": "missing",
        "reason": failure_reason,
        "key_path": firebase_key_path,
    }


def get_recovery_source_diagnostics():
    firebase_config = get_firebase_runtime_config()
    firebase_key_path = str(firebase_config.get("key_path") or "").strip()
    firebase_key_exists = bool(firebase_key_path) and os.path.exists(firebase_key_path)
    database_url = str(
        _read_runtime_secret("FIREBASE_DATABASE_URL", firebase_config.get("databaseURL") or "")
    ).strip()
    bucket_override = str(_read_runtime_secret("FIREBASE_STORAGE_BUCKET", "") or "").strip()
    object_name = str(_read_runtime_secret("FIREBASE_DB_BACKUP_OBJECT", FIREBASE_OBJECT_NAME) or FIREBASE_OBJECT_NAME).strip()
    credentials_result = get_firebase_service_account_info()
    service_account_info = credentials_result.get("service_account_info")
    credentials_source = credentials_result.get("source", "missing")
    credential_error = None if credentials_result.get("ok") else credentials_result.get("reason")
    credential_error = sanitize_error_message(credential_error) if credential_error else None

    project_id = str((service_account_info or {}).get("project_id") or "").strip()
    bucket_name = bucket_override or (f"{project_id}.appspot.com" if project_id else "")

    diagnostics = {
        "backend": "firebase_storage",
        "credentials_loaded": bool(service_account_info),
        "credentials_source": credentials_source,
        "credential_error": credential_error,
        "firebase_key_path": firebase_key_path,
        "firebase_key_exists": firebase_key_exists,
        "database_url_configured": bool(database_url),
        "bucket_name": bucket_name,
        "object_name": object_name,
        "project_id_present": bool(project_id),
        "service_account_info": service_account_info,
        "database_url": database_url,
    }
    return diagnostics


def _init_firebase_recovery_client():
    global FIREBASE_RECOVERY_APP, FIREBASE_RECOVERY_BUCKET_NAME
    if firebase_admin is None or credentials is None or initialize_app is None or storage is None:
        logger.warning("Firebase recovery backend is unavailable because firebase_admin dependencies are not installed.")
        return None
    if FIREBASE_RECOVERY_APP is not None:
        return FIREBASE_RECOVERY_APP
    try:
        diagnostics = get_recovery_source_diagnostics()
        credentials_result = get_firebase_service_account_info()
        logger.info(
            "Recovery source configuration: backend=%s credentials_loaded=%s credentials_source=%s firebase_key_exists=%s database_url_configured=%s bucket=%s object=%s project_id_present=%s",
            diagnostics["backend"],
            diagnostics["credentials_loaded"],
            diagnostics["credentials_source"],
            diagnostics["firebase_key_exists"],
            diagnostics["database_url_configured"],
            diagnostics["bucket_name"] or "missing",
            diagnostics["object_name"] or "missing",
            diagnostics["project_id_present"],
        )
        if not credentials_result.get("ok"):
            logger.warning("Firebase recovery credentials are unavailable: %s", sanitize_error_message(credentials_result.get("reason")))
            return None
        if not diagnostics["bucket_name"]:
            logger.warning("Firebase recovery client could not determine a storage bucket name.")
            return None
        if not diagnostics["database_url"]:
            logger.warning("Firebase recovery client is missing a database URL configuration.")
            return None
        FIREBASE_RECOVERY_BUCKET_NAME = diagnostics["bucket_name"]
        firebase_cred = credentials.Certificate(credentials_result["service_account_info"])
        FIREBASE_RECOVERY_APP = initialize_app(
            firebase_cred,
            {
                "storageBucket": FIREBASE_RECOVERY_BUCKET_NAME,
                "databaseURL": diagnostics["database_url"],
            },
            name="eka-database-recovery",
        )
        return FIREBASE_RECOVERY_APP
    except ValueError:
        try:
            FIREBASE_RECOVERY_APP = firebase_admin.get_app("eka-database-recovery")
            return FIREBASE_RECOVERY_APP
        except Exception as exc:
            logger.warning("Firebase recovery client lookup failed: %s", sanitize_error_message(exc))
            return None
    except Exception as exc:
        logger.warning("Firebase recovery client initialization failed: %s", sanitize_error_message(exc))
        return None


def _get_firebase_recovery_bucket():
    app = _init_firebase_recovery_client()
    if app is None or storage is None:
        return None
    try:
        return storage.bucket(app=app)
    except Exception as exc:
        logger.warning("Firebase recovery bucket unavailable: %s", sanitize_error_message(exc))
        return None


def _build_history_backup_object_name(timestamp=None):
    timestamp = timestamp or datetime.utcnow()
    return f"{BACKUP_HISTORY_PREFIX}/eka_enterprise_v3_{timestamp.strftime('%Y%m%d_%H%M%S')}.db"


def _build_local_history_backup_path(timestamp=None):
    timestamp = timestamp or datetime.utcnow()
    return os.path.join(
        LOCAL_HISTORY_BACKUP_DIR,
        f"eka_enterprise_v3_{timestamp.strftime('%Y%m%d_%H%M%S')}.db",
    )


def _build_pre_cloud_restore_backup_path(timestamp=None):
    timestamp = timestamp or datetime.utcnow()
    return os.path.join(
        DB_DIR,
        f"eka_enterprise_v3_before_cloud_restore_{timestamp.strftime('%Y%m%d_%H%M%S')}.db",
    )


def _blob_sort_key(blob):
    updated = getattr(blob, "updated", None)
    normalized_updated = updated.replace(tzinfo=None) if hasattr(updated, "replace") else None
    return (
        normalized_updated or datetime.min,
        str(getattr(blob, "name", "") or ""),
    )


def _candidate_is_valid_production_backup(health_snapshot):
    health_snapshot = health_snapshot or {}
    return bool(health_snapshot.get("production_ready")) and int(health_snapshot.get("company_count") or 0) >= 1


def _evaluate_runtime_replacement(local_health, incoming_health, explicit_recovery_mode=False):
    local_health = local_health or {}
    incoming_health = incoming_health or {}
    local_count = int(local_health.get("company_count") or 0)
    incoming_count = int(incoming_health.get("company_count") or 0)
    local_valid = bool(local_health.get("structural_valid"))
    local_ready = bool(local_health.get("production_ready"))
    incoming_ready = bool(incoming_health.get("production_ready"))

    if not incoming_ready or incoming_count <= 0:
        return {
            "allowed": False,
            "reason": "incoming database is not production-ready or has no company rows",
        }
    if local_ready and local_count > 0 and not explicit_recovery_mode:
        if is_streamlit_cloud_production():
            if incoming_count > local_count:
                return {
                    "allowed": True,
                    "reason": (
                        f"Streamlit Cloud source-of-truth replacement allowed because incoming cloud backup has more companies "
                        f"({incoming_count} > {local_count})"
                    ),
                }
            if _has_suspicious_local_companies(DB_PATH, logger_instance=logger) and incoming_ready:
                return {
                    "allowed": True,
                    "reason": "Streamlit Cloud source-of-truth replacement allowed because local runtime database contains suspicious/test companies",
                }
        return {
            "allowed": False,
            "reason": "local runtime database is valid and populated; automatic replacement is blocked",
        }
    if local_valid and local_count > 0 and incoming_count < local_count and not explicit_recovery_mode:
        return {
            "allowed": False,
            "reason": (
                f"incoming database has fewer companies than local runtime "
                f"({incoming_count} < {local_count}); replacement is blocked"
            ),
        }
    return {"allowed": True, "reason": "runtime replacement passed safety checks"}


def _is_stale_local_db_compared_to_cloud(local_health, cloud_health):
    """Determine whether the local runtime DB should be considered stale compared to cloud."""
    local_health = local_health or {}
    cloud_health = cloud_health or {}
    local_count = int(local_health.get("company_count") or 0)
    cloud_count = int(cloud_health.get("company_count") or 0)
    if cloud_count > local_count and cloud_count > 0:
        return True
    local_uuid = str(local_health.get("database_uuid") or "")
    cloud_uuid = str(cloud_health.get("database_uuid") or "")
    if local_uuid and cloud_uuid and local_uuid != cloud_uuid:
        if cloud_health.get("production_ready") and local_count == 0:
            return True
    return False


def _find_suspicious_company_signals(db_path=DB_PATH, logger_instance=None):
    """Return suspicious company rows for runtime detection and diagnostics."""
    logger_instance = logger_instance or logger
    suspicious = []
    if not db_path or not os.path.exists(db_path):
        return suspicious
    conn = None
    try:
        conn = _open_sqlite_connection(path=db_path)
        if not _table_exists(conn, "companies"):
            return suspicious
        for row in conn.execute("SELECT key, name FROM companies").fetchall():
            company_key = str(row["key"] or "").strip()
            company_name = str(row["name"] or "").strip()
            key_upper = company_key.upper()
            name_lower = company_name.lower()
            reasons = []
            if key_upper in {"TESTCO", "PAYSTACK-ACTIVE-001"} or any(term in key_upper for term in ("TESTCO", "PAYSTACK", "DEMO", "SAMPLE")):
                reasons.append("suspicious_key")
            if any(term in name_lower for term in ("test", "demo", "paystack", "sample", "sandbox")):
                reasons.append("suspicious_name")
            if reasons:
                suspicious.append({
                    "company_key": company_key,
                    "company_name": company_name,
                    "reasons": sorted(set(reasons)),
                })
        return suspicious
    except sqlite3.Error as exc:
        logger_instance.warning("Suspicious company detection failed for %s: %s", db_path, sanitize_error_message(exc))
        return suspicious
    finally:
        if conn:
            conn.close()


def _has_suspicious_local_companies(db_path=DB_PATH, logger_instance=None):
    return bool(_find_suspicious_company_signals(db_path=db_path, logger_instance=logger_instance))


def _should_block_cloud_backup_upload(local_health, logger_instance=None):
    """Return whether uploading the current runtime DB should be blocked."""
    logger_instance = logger_instance or logger
    local_health = local_health or {}
    if is_test_runtime() and not is_test_cloud_backup_allowed():
        return True, "cloud backup upload disabled during automated tests"
    company_count = int(local_health.get("company_count") or 0)
    if company_count <= 0:
        return True, "companies table is empty; empty runtime DB cannot overwrite cloud backup"
    if not local_health.get("production_ready"):
        reason = "; ".join(local_health.get("readiness_failures", [])) or "runtime database is not production-ready"
        return True, reason
    if local_health.get("missing_tables"):
        return True, f"runtime database missing required tables: {', '.join(local_health.get('missing_tables') or [])}"
    try:
        diagnostics = get_recovery_source_diagnostics()
        if diagnostics.get("credentials_loaded"):
            bucket = _get_firebase_recovery_bucket()
            if bucket is not None:
                selected = _select_valid_cloud_backup(bucket, FIREBASE_OBJECT_NAME, logger_instance=logger_instance)
                if selected.get("ok"):
                    cloud_health = selected.get("health") or {}
                    cloud_count = int(cloud_health.get("company_count") or 0)
                    if cloud_count > company_count:
                        reason = (
                            f"runtime database company count ({company_count}) is less than current cloud backup ({cloud_count}); upload would cause data loss"
                        )
                        logger_instance.warning("Cloud backup upload blocked: %s", reason)
                        return True, reason
    except Exception as exc:
        logger_instance.debug("Could not verify cloud backup for upload guard: %s", sanitize_error_message(exc))
    return False, ""


def _download_blob_to_temp_path(blob, prefix, logger_instance=None):
    logger_instance = logger_instance or logger
    temp_fd, temp_path = tempfile.mkstemp(prefix=prefix, suffix=".db", dir=DB_DIR)
    os.close(temp_fd)
    try:
        blob.download_to_filename(temp_path)
        return temp_path
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


def _validate_cloud_backup_blob(blob, logger_instance=None):
    logger_instance = logger_instance or logger
    temp_path = None
    try:
        temp_path = _download_blob_to_temp_path(blob, "eka_cloud_restore_candidate_", logger_instance=logger_instance)
        health = get_database_health_snapshot(temp_path, logger_instance=logger_instance)
        logger_instance.info(
            "Cloud backup candidate validated: object=%s production_ready=%s company_count=%s missing_tables=%s readiness_failures=%s",
            getattr(blob, "name", "unknown"),
            health.get("production_ready"),
            health.get("company_count"),
            ", ".join(health.get("missing_tables", [])) or "none",
            "; ".join(health.get("readiness_failures", [])) or "none",
        )
        return {"ok": _candidate_is_valid_production_backup(health), "temp_path": temp_path, "health": health}
    except Exception as exc:
        logger_instance.warning(
            "Cloud backup candidate validation failed for object=%s: %s",
            getattr(blob, "name", "unknown"),
            sanitize_error_message(exc),
        )
        return {
            "ok": False,
            "temp_path": temp_path,
            "health": get_database_health_snapshot(temp_path, logger_instance=logger_instance) if temp_path and os.path.exists(temp_path) else None,
            "reason": str(exc),
        }


def _select_valid_cloud_backup(bucket, latest_object, logger_instance=None):
    logger_instance = logger_instance or logger
    latest_blob = bucket.blob(latest_object)
    candidates = []
    if latest_blob.exists():
        try:
            latest_blob.reload()
        except Exception:
            pass
        latest_validation = _validate_cloud_backup_blob(latest_blob, logger_instance=logger_instance)
        candidates.append(
            {
                "object_path": latest_object,
                "source_type": "latest",
                **latest_validation,
            }
        )
        if latest_validation.get("ok"):
            return {
                "ok": True,
                "object_path": latest_object,
                "source_type": "latest",
                "temp_path": latest_validation.get("temp_path"),
                "health": latest_validation.get("health"),
                "validation_attempts": candidates,
            }
    else:
        candidates.append(
            {
                "object_path": latest_object,
                "source_type": "latest",
                "ok": False,
                "temp_path": None,
                "health": None,
                "reason": "latest object missing",
            }
        )

    history_blobs = []
    try:
        history_blobs = list(bucket.list_blobs(prefix=f"{BACKUP_HISTORY_PREFIX}/"))
    except Exception as exc:
        logger_instance.warning("Cloud backup history listing failed: %s", sanitize_error_message(exc))
        return {
            "ok": False,
            "reason": f"history listing failed: {exc}",
            "validation_attempts": candidates,
        }

    for blob in sorted(history_blobs, key=_blob_sort_key, reverse=True):
        blob_name = str(getattr(blob, "name", "") or "")
        if not blob_name.endswith(".db"):
            continue
        validation = _validate_cloud_backup_blob(blob, logger_instance=logger_instance)
        candidate = {
            "object_path": blob_name,
            "source_type": "history",
            **validation,
        }
        candidates.append(candidate)
        if validation.get("ok"):
            return {
                "ok": True,
                "object_path": blob_name,
                "source_type": "history",
                "temp_path": validation.get("temp_path"),
                "health": validation.get("health"),
                "validation_attempts": candidates,
            }
        temp_path = validation.get("temp_path")
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    return {
        "ok": False,
        "reason": "no valid latest or history cloud backup satisfied production-ready validation",
        "validation_attempts": candidates,
    }


def _ensure_local_backup_directories():
    os.makedirs(LOCAL_LATEST_BACKUP_DIR, exist_ok=True)
    os.makedirs(LOCAL_HISTORY_BACKUP_DIR, exist_ok=True)


def _update_backup_status(status, reason, latest_object=FIREBASE_OBJECT_NAME, history_object=None, trigger_tables=None):
    LAST_BACKUP_STATUS.update(
        {
            "status": str(status),
            "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
            "reason": str(reason),
            "latest_object": latest_object,
            "history_object": history_object,
            "trigger_tables": sorted(str(table) for table in (trigger_tables or [])),
        }
    )


def _update_local_backup_status(status, reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=None, trigger_tables=None):
    LAST_LOCAL_BACKUP_STATUS.update(
        {
            "status": str(status),
            "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
            "reason": str(reason),
            "latest_path": latest_path,
            "history_path": history_path,
            "trigger_tables": sorted(str(table) for table in (trigger_tables or [])),
        }
    )


def _copy_snapshot_to_local_backups(snapshot_path, history_path, trigger_tables=None, logger_instance=None):
    logger_instance = logger_instance or logger
    _ensure_local_backup_directories()
    shutil.copy2(snapshot_path, LOCAL_LATEST_BACKUP_PATH)
    shutil.copy2(snapshot_path, history_path)

    latest_health = get_database_health_snapshot(LOCAL_LATEST_BACKUP_PATH, logger_instance=logger_instance)
    history_health = get_database_health_snapshot(history_path, logger_instance=logger_instance)
    if not latest_health["production_ready"] or not history_health["production_ready"]:
        reason = (
            "local backup copy validation failed: "
            f"latest_ready={latest_health['production_ready']} history_ready={history_health['production_ready']}"
        )
        logger_instance.warning("Local backup failed: %s", reason)
        _update_local_backup_status(
            "failed",
            reason,
            latest_path=LOCAL_LATEST_BACKUP_PATH,
            history_path=history_path,
            trigger_tables=trigger_tables,
        )
        return {"ok": False, "reason": reason, "latest_path": LOCAL_LATEST_BACKUP_PATH, "history_path": history_path}

    reason = (
        f"local backup updated latest={LOCAL_LATEST_BACKUP_PATH} "
        f"history={history_path} company_count={latest_health['company_count']}"
    )
    logger_instance.info("Local backup succeeded: %s", reason)
    _update_local_backup_status(
        "copied",
        reason,
        latest_path=LOCAL_LATEST_BACKUP_PATH,
        history_path=history_path,
        trigger_tables=trigger_tables,
    )
    return {"ok": True, "reason": reason, "latest_path": LOCAL_LATEST_BACKUP_PATH, "history_path": history_path}


def _extract_mutated_table_name(sql_text):
    normalized = str(sql_text or "").strip()
    if not normalized:
        return None
    match = re.match(
        r"^(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)",
        normalized,
        flags=re.IGNORECASE,
    )
    return str(match.group(1)).lower() if match else None


class TrackedSQLiteConnection(sqlite3.Connection):
    def close(self):
        try:
            super().close()
        finally:
            _diagnostic_connection_closed()


class ManagedSQLiteConnection(TrackedSQLiteConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._managed_db_path = None
        self._mutated_tables = set()
        self._persistence_hooks_enabled = True
        try:
            self.set_trace_callback(self._track_mutations)
        except Exception:
            pass

    def _track_mutations(self, sql_text):
        if not getattr(self, "_persistence_hooks_enabled", False):
            return
        table_name = _extract_mutated_table_name(sql_text)
        if table_name and table_name in BACKUP_TRIGGER_TABLES:
            self._mutated_tables.add(table_name)

    def commit(self):
        super().commit()
        _run_post_commit_persistence_hook(self)

    def rollback(self):
        super().rollback()
        self._mutated_tables.clear()

def _create_runtime_snapshot_file(source_db_path=DB_PATH):
    _ensure_db_directory()
    snapshot_fd, snapshot_path = tempfile.mkstemp(
        prefix="eka_runtime_snapshot_",
        suffix=".db",
        dir=DB_DIR,
    )
    os.close(snapshot_fd)
    source_conn = None
    snapshot_conn = None
    try:
        source_conn = sqlite3.connect(source_db_path, timeout=20, check_same_thread=False)
        source_conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")
        source_conn.execute("PRAGMA foreign_keys = ON;")
        source_conn.execute("PRAGMA journal_mode = WAL;")
        snapshot_conn = sqlite3.connect(snapshot_path, timeout=20, check_same_thread=False)
        snapshot_conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")
        source_conn.backup(snapshot_conn)
        return snapshot_path
    finally:
        if snapshot_conn:
            snapshot_conn.close()
        if source_conn:
            source_conn.close()


def backup_runtime_database_to_cloud(force=False, trigger_tables=None, logger_instance=None):
    global LAST_BACKUP_SIGNATURE, LAST_BACKUP_AT, LAST_CLOUD_UPLOAD_BLOCK_REASON
    logger_instance = logger_instance or logger
    LAST_CLOUD_UPLOAD_BLOCK_REASON = None
    if is_test_runtime() and not is_test_cloud_backup_allowed():
        reason = "cloud backup upload disabled during automated tests"
        LAST_CLOUD_UPLOAD_BLOCK_REASON = reason
        logger_instance.warning(reason)
        _update_backup_status("blocked", reason, latest_object=FIREBASE_OBJECT_NAME, history_object=None, trigger_tables=trigger_tables)
        snapshot_path = None
        local_history_path = _build_local_history_backup_path(datetime.utcnow())
        try:
            snapshot_path = _create_runtime_snapshot_file(DB_PATH)
            snapshot_health = get_database_health_snapshot(snapshot_path, logger_instance=logger_instance)
            if not snapshot_health["production_ready"]:
                snapshot_reason = "; ".join(snapshot_health.get("readiness_failures", [])) or "snapshot database is not production-ready"
                logger_instance.warning("Backup skipped because snapshot validation failed; latest backups protected: %s", snapshot_reason)
                _update_local_backup_status("failed", snapshot_reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=local_history_path, trigger_tables=trigger_tables)
                return {
                    "ok": False,
                    "reason": snapshot_reason,
                    "latest_object": FIREBASE_OBJECT_NAME,
                    "history_object": None,
                    "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
                    "history_local_path": local_history_path,
                    "cloud_ok": False,
                }
            local_backup_result = _copy_snapshot_to_local_backups(
                snapshot_path,
                local_history_path,
                trigger_tables=trigger_tables,
                logger_instance=logger_instance,
            )
            return {
                "ok": False,
                "reason": reason,
                "local_ok": bool(local_backup_result.get("ok")),
                "local_reason": local_backup_result.get("reason"),
                "cloud_ok": False,
                "latest_object": FIREBASE_OBJECT_NAME,
                "history_object": None,
                "latest_local_path": local_backup_result.get("latest_path"),
                "history_local_path": local_backup_result.get("history_path"),
            }
        except Exception as exc:
            failure_reason = f"{reason}; local snapshot failed: {exc}"
            logger_instance.warning("Backup local snapshot failed: %s", sanitize_error_message(exc))
            _update_local_backup_status("failed", failure_reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=local_history_path, trigger_tables=trigger_tables)
            return {
                "ok": False,
                "reason": failure_reason,
                "latest_object": FIREBASE_OBJECT_NAME,
                "history_object": None,
                "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
                "history_local_path": local_history_path,
                "cloud_ok": False,
            }
        finally:
            if snapshot_path and os.path.exists(snapshot_path):
                try:
                    os.remove(snapshot_path)
                except OSError:
                    pass
    restore_guard = _load_restore_guard_state()
    diagnostics = get_recovery_source_diagnostics()
    latest_object = diagnostics.get("object_name") or FIREBASE_OBJECT_NAME
    backup_timestamp = datetime.utcnow()
    history_object = _build_history_backup_object_name(backup_timestamp)
    local_history_path = _build_local_history_backup_path(backup_timestamp)
    trigger_tables = sorted(str(table) for table in (trigger_tables or []))

    if not os.path.exists(DB_PATH):
        reason = f"canonical runtime database is missing: {DB_PATH}"
        logger_instance.warning("Backup skipped: %s", reason)
        _update_local_backup_status("skipped", reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=None, trigger_tables=trigger_tables)
        _update_backup_status("skipped", reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
        return {
            "ok": False,
            "reason": reason,
            "latest_object": latest_object,
            "history_object": None,
            "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
            "history_local_path": None,
        }

    if restore_guard.get("active"):
        reason = (
            "backup temporarily disabled during first boot after local restore; "
            f"source={restore_guard.get('source_db_path', 'unknown')}"
        )
        logger_instance.warning("Backup skipped: %s", reason)
        _update_local_backup_status("skipped", reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=None, trigger_tables=trigger_tables)
        _update_backup_status("skipped", reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
        return {
            "ok": False,
            "reason": reason,
            "latest_object": latest_object,
            "history_object": None,
            "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
            "history_local_path": None,
        }

    local_health = get_database_health_snapshot(DB_PATH, logger_instance=logger_instance)
    logger_instance.info(
        "Backup preflight: db_path=%s db_exists=%s sqlite_open_success=%s db_valid=%s production_ready=%s company_count=%s missing_tables=%s trigger_tables=%s local_latest=%s cloud_latest=%s",
        local_health["db_path"],
        local_health["file_exists"],
        local_health.get("sqlite_open_success"),
        local_health["structural_valid"],
        local_health["production_ready"],
        local_health["company_count"],
        ", ".join(local_health.get("missing_tables", [])) or "none",
        ", ".join(trigger_tables) or "none",
        LOCAL_LATEST_BACKUP_PATH,
        latest_object,
    )
    company_count = int(local_health.get("company_count") or 0)
    missing_tables = list(local_health.get("missing_tables") or [])
    if company_count <= 0:
        reason = "companies table has no deployed company rows; empty databases cannot overwrite cloud backups"
        logger_instance.warning("Backup skipped because canonical database is empty: %s", reason)
        _update_local_backup_status("skipped", reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=None, trigger_tables=trigger_tables)
        _update_backup_status("skipped", reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
        return {
            "ok": False,
            "reason": reason,
            "latest_object": latest_object,
            "history_object": None,
            "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
            "history_local_path": None,
        }
    if missing_tables:
        reason = "canonical runtime database is missing required tables: " + ", ".join(missing_tables)
        logger_instance.warning("Backup skipped because canonical database is incomplete: %s", reason)
        _update_local_backup_status("skipped", reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=None, trigger_tables=trigger_tables)
        _update_backup_status("skipped", reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
        return {
            "ok": False,
            "reason": reason,
            "latest_object": latest_object,
            "history_object": None,
            "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
            "history_local_path": None,
        }
    if not local_health["production_ready"]:
        reason = "; ".join(local_health.get("readiness_failures", [])) or "canonical runtime database is not production-ready"
        logger_instance.warning("Backup skipped because canonical database is not production-ready; latest backups protected: %s", reason)
        _update_local_backup_status("skipped", reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=None, trigger_tables=trigger_tables)
        _update_backup_status("skipped", reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
        return {
            "ok": False,
            "reason": reason,
            "latest_object": latest_object,
            "history_object": None,
            "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
            "history_local_path": None,
        }

    should_block, block_reason = _should_block_cloud_backup_upload(local_health, logger_instance=logger_instance)
    if should_block:
        LAST_CLOUD_UPLOAD_BLOCK_REASON = block_reason
        logger_instance.warning("Backup skipped by enhanced upload guard: %s", block_reason)
        _update_local_backup_status("blocked", block_reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=None, trigger_tables=trigger_tables)
        _update_backup_status("blocked", block_reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
        return {
            "ok": False,
            "reason": block_reason,
            "latest_object": latest_object,
            "history_object": None,
            "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
            "history_local_path": None,
        }

    signature = (
        os.path.getsize(DB_PATH),
        int(os.path.getmtime(DB_PATH)),
        local_health["company_count"],
    )
    now = time.time()
    if not force and signature == LAST_BACKUP_SIGNATURE and (now - LAST_BACKUP_AT) < BACKUP_DEBOUNCE_SECONDS:
        reason = f"backup debounced for unchanged canonical database within {BACKUP_DEBOUNCE_SECONDS}s"
        logger_instance.info("Backup skipped: %s", reason)
        _update_local_backup_status("debounced", reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=None, trigger_tables=trigger_tables)
        _update_backup_status("debounced", reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
        return {
            "ok": True,
            "reason": reason,
            "latest_object": latest_object,
            "history_object": None,
            "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
            "history_local_path": None,
        }

    snapshot_path = None
    try:
        if SQLITE_CONCURRENCY_DIAGNOSTICS.get("active_write_operations"):
            _diagnostic_increment("backup_overlap_events")
        backup_lock_context = sqlite_operation_lock("cloud_backup_sync")
        backup_lock_context.__enter__()
        try:
            snapshot_path = _create_runtime_snapshot_file(DB_PATH)
            snapshot_health = get_database_health_snapshot(snapshot_path, logger_instance=logger_instance)
            if not snapshot_health["production_ready"]:
                reason = "; ".join(snapshot_health.get("readiness_failures", [])) or "snapshot database is not production-ready"
                logger_instance.warning("Backup skipped because snapshot validation failed; latest backups protected: %s", reason)
                _update_local_backup_status("failed", reason, latest_path=LOCAL_LATEST_BACKUP_PATH, history_path=None, trigger_tables=trigger_tables)
                _update_backup_status("failed", reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
                return {
                    "ok": False,
                    "reason": reason,
                    "latest_object": latest_object,
                    "history_object": None,
                    "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
                    "history_local_path": None,
                }

            logger_instance.info(
                "Validated backup snapshot created: snapshot=%s company_count=%s local_latest=%s local_history=%s cloud_latest=%s cloud_history=%s",
                snapshot_path,
                snapshot_health["company_count"],
                LOCAL_LATEST_BACKUP_PATH,
                local_history_path,
                latest_object,
                history_object,
            )
        finally:
            backup_lock_context.__exit__(None, None, None)

        try:
            local_backup_result = _copy_snapshot_to_local_backups(
                snapshot_path,
                local_history_path,
                trigger_tables=trigger_tables,
                logger_instance=logger_instance,
            )
        except Exception as exc:
            local_backup_result = {
                "ok": False,
                "reason": f"local backup copy failed: {exc}",
                "latest_path": LOCAL_LATEST_BACKUP_PATH,
                "history_path": local_history_path,
            }
            logger_instance.warning("Local backup failed: %s", local_backup_result["reason"])
            _update_local_backup_status(
                "failed",
                local_backup_result["reason"],
                latest_path=LOCAL_LATEST_BACKUP_PATH,
                history_path=local_history_path,
                trigger_tables=trigger_tables,
            )

        bucket = _get_firebase_recovery_bucket()
        if bucket is None:
            cloud_reason = diagnostics.get("credential_error") or "firebase backup bucket is not accessible"
            logger_instance.warning("Cloud backup skipped because Firebase bucket is unavailable: %s", cloud_reason)
            _update_backup_status("failed", cloud_reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
            return {
                "ok": False,
                "reason": f"local_ok={local_backup_result.get('ok')} cloud_failed={cloud_reason}",
                "local_ok": bool(local_backup_result.get("ok")),
                "cloud_ok": False,
                "latest_object": latest_object,
                "history_object": None,
                "latest_local_path": local_backup_result.get("latest_path"),
                "history_local_path": local_backup_result.get("history_path"),
            }

        bucket.blob(latest_object).upload_from_filename(snapshot_path)
        bucket.blob(history_object).upload_from_filename(snapshot_path)
        cloud_reason = f"uploaded canonical database backup to bucket={diagnostics.get('bucket_name')} latest={latest_object} history={history_object}"
        logger_instance.info("Cloud backup succeeded: %s", cloud_reason)
        _update_backup_status("uploaded", cloud_reason, latest_object=latest_object, history_object=history_object, trigger_tables=trigger_tables)

        all_ok = bool(local_backup_result.get("ok"))
        if all_ok:
            LAST_BACKUP_SIGNATURE = signature
            LAST_BACKUP_AT = now
        reason = (
            f"local_ok={local_backup_result.get('ok')} local_latest={local_backup_result.get('latest_path')} "
            f"local_history={local_backup_result.get('history_path')} cloud_ok=True cloud_latest={latest_object} cloud_history={history_object}"
        )
        logger_instance.info("Cloud backup succeeded: %s", reason)
        return {
            "ok": all_ok,
            "reason": reason,
            "local_ok": bool(local_backup_result.get("ok")),
            "cloud_ok": True,
            "latest_object": latest_object,
            "history_object": history_object,
            "latest_local_path": local_backup_result.get("latest_path"),
            "history_local_path": local_backup_result.get("history_path"),
        }
    except Exception as exc:
        reason = f"cloud backup upload failed: {exc}"
        logger_instance.warning("Cloud backup failed: %s", reason)
        _update_backup_status("failed", reason, latest_object=latest_object, history_object=None, trigger_tables=trigger_tables)
        return {
            "ok": False,
            "reason": reason,
            "latest_object": latest_object,
            "history_object": None,
            "latest_local_path": LOCAL_LATEST_BACKUP_PATH,
            "history_local_path": local_history_path,
        }
    finally:
        if snapshot_path and os.path.exists(snapshot_path):
            try:
                os.remove(snapshot_path)
            except OSError:
                pass


def _run_post_commit_persistence_hook(conn):
    try:
        if conn is None or not getattr(conn, "_persistence_hooks_enabled", False):
            return
        managed_db_path = os.path.abspath(getattr(conn, "_managed_db_path", "") or "")
        canonical_db_path = os.path.abspath(DB_PATH)
        mutated_tables = set(getattr(conn, "_mutated_tables", set()))
        conn._mutated_tables.clear()
        if managed_db_path != canonical_db_path or not mutated_tables:
            return
        backup_runtime_database_to_cloud(trigger_tables=sorted(mutated_tables), logger_instance=logger)
    except Exception as exc:
        logger.warning("Post-commit persistence hook failed: %s", sanitize_error_message(exc))


def get_persistence_diagnostics():
    local_health = get_database_health_snapshot(DB_PATH, logger_instance=logger)
    recovery_diagnostics = get_recovery_source_diagnostics()
    local_backup = get_local_backup_diagnostics(logger_instance=logger)
    cloud_backup = get_cloud_backup_diagnostics(logger_instance=logger)
    backup_counts_known = local_backup.get("company_count") is not None and cloud_backup.get("company_count") is not None
    local_cloud_mismatch = (
        int(local_backup.get("company_count") or 0) != int(cloud_backup.get("company_count") or 0)
        if backup_counts_known
        else False
    )
    suspicious_companies = []
    if local_health.get("companies_table_exists"):
        suspicious_companies = _find_suspicious_company_signals(DB_PATH, logger_instance=logger)
    return {
        "canonical_db_path": DB_PATH,
        "db_backend": local_health.get("backend_label") or local_health.get("backend") or "SQLite",
        "db_file_size_bytes": local_health.get("file_size_bytes"),
        "database_uuid": local_health.get("database_uuid"),
        "local_db_uuid": local_health.get("database_uuid"),
        "schema_version": local_health.get("schema_version"),
        "database_created_at": local_health.get("database_created_at"),
        "last_startup_at": local_health.get("last_startup_at"),
        "environment_label": local_health.get("environment_label"),
        "runtime_mode": get_runtime_mode(),
        "force_cloud_restore_enabled": is_force_cloud_restore_enabled(),
        "cloud_restore_disabled_due_to_tests": is_test_runtime(),
        "cloud_upload_disabled_due_to_tests": is_test_runtime(),
        "has_suspicious_companies": bool(suspicious_companies),
        "suspicious_companies": suspicious_companies,
        "suspicious_company_count": len(suspicious_companies),
        "local_db_valid": local_health["structural_valid"],
        "production_ready": local_health["production_ready"],
        "company_count": local_health["company_count"],
        "required_tables_missing": local_health.get("missing_tables", []),
        "latest_backup_upload_status": LAST_BACKUP_STATUS.get("status"),
        "last_backup_timestamp": LAST_BACKUP_STATUS.get("timestamp"),
        "last_backup_reason": LAST_BACKUP_STATUS.get("reason"),
        "latest_cloud_backup_status": LAST_BACKUP_STATUS.get("status"),
        "last_cloud_backup_timestamp": LAST_BACKUP_STATUS.get("timestamp"),
        "last_cloud_backup_reason": LAST_BACKUP_STATUS.get("reason"),
        "cloud_object_path": LAST_BACKUP_STATUS.get("latest_object") or recovery_diagnostics.get("object_name"),
        "history_object_path": LAST_BACKUP_STATUS.get("history_object"),
        "latest_local_backup_status": LAST_LOCAL_BACKUP_STATUS.get("status"),
        "last_local_backup_timestamp": LAST_LOCAL_BACKUP_STATUS.get("timestamp"),
        "last_local_backup_reason": LAST_LOCAL_BACKUP_STATUS.get("reason"),
        "local_backup_latest_path": LAST_LOCAL_BACKUP_STATUS.get("latest_path") or LOCAL_LATEST_BACKUP_PATH,
        "local_backup_history_path": LAST_LOCAL_BACKUP_STATUS.get("history_path"),
        "local_backup_company_count": local_backup.get("company_count"),
        "local_backup_last_modified": local_backup.get("last_modified"),
        "local_backup_production_ready": local_backup.get("production_ready"),
        "local_backup_reason": local_backup.get("reason"),
        "local_cloud_backup_mismatch": local_cloud_mismatch,
        "restore_source_used_at_startup": LAST_RESTORE_SOURCE,
        "restore_skipped_reason": LAST_CLOUD_RESTORE_SKIP_REASON,
        "upload_blocked_reason": LAST_CLOUD_UPLOAD_BLOCK_REASON,
        "bucket_name": recovery_diagnostics.get("bucket_name"),
        "cloud_backup_company_count": cloud_backup.get("company_count"),
        "cloud_backup_last_modified": cloud_backup.get("last_modified"),
        "cloud_backup_database_uuid": cloud_backup.get("database_uuid"),
        "cloud_db_uuid": cloud_backup.get("database_uuid"),
        "cloud_backup_newer_than_local": cloud_backup.get("newer_than_local"),
        "cloud_backup_reason": cloud_backup.get("reason"),
    }


def get_local_backup_diagnostics(logger_instance=None):
    logger_instance = logger_instance or logger
    latest_path = LAST_LOCAL_BACKUP_STATUS.get("latest_path") or LOCAL_LATEST_BACKUP_PATH
    result = {
        "ok": False,
        "latest_path": latest_path,
        "history_path": LAST_LOCAL_BACKUP_STATUS.get("history_path"),
        "last_modified": None,
        "company_count": None,
        "production_ready": False,
        "reason": "latest local backup diagnostics not available",
    }
    if not os.path.exists(latest_path):
        result["reason"] = f"latest local backup file was not found: {latest_path}"
        logger_instance.info("Local backup diagnostics: %s", result["reason"])
        return result

    try:
        local_backup_health = get_database_health_snapshot(latest_path, logger_instance=logger_instance)
        result["company_count"] = local_backup_health.get("company_count")
        result["production_ready"] = bool(local_backup_health.get("production_ready"))
        result["last_modified"] = datetime.utcfromtimestamp(os.path.getmtime(latest_path)).isoformat(timespec="seconds")
        result["ok"] = bool(local_backup_health.get("production_ready"))
        result["reason"] = (
            "latest local backup is production-ready"
            if result["ok"]
            else "; ".join(local_backup_health.get("readiness_failures", [])) or "latest local backup is not production-ready"
        )
        logger_instance.info(
            "Local backup diagnostics collected: latest=%s last_modified=%s company_count=%s production_ready=%s",
            latest_path,
            result["last_modified"],
            result["company_count"],
            result["production_ready"],
        )
        return result
    except Exception as exc:
        result["reason"] = f"latest local backup diagnostics failed: {exc}"
        logger_instance.warning("Local backup diagnostics failed: %s", result["reason"])
        return result


def get_downloadable_backup_export(logger_instance=None):
    logger_instance = logger_instance or logger
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if os.path.exists(DB_PATH):
        try:
            runtime_health = get_database_health_snapshot(DB_PATH, logger_instance=logger_instance)
            if runtime_health["production_ready"]:
                snapshot_path = _create_runtime_snapshot_file(DB_PATH)
                try:
                    snapshot_health = get_database_health_snapshot(snapshot_path, logger_instance=logger_instance)
                    if snapshot_health["production_ready"]:
                        with open(snapshot_path, "rb") as snapshot_file:
                            payload = snapshot_file.read()
                        logger_instance.info(
                            "Admin backup export prepared from runtime snapshot: db_path=%s company_count=%s bytes=%s",
                            DB_PATH,
                            snapshot_health["company_count"],
                            len(payload),
                        )
                        return {
                            "ok": True,
                            "source": "runtime_snapshot",
                            "filename": f"eka_enterprise_v3_runtime_{timestamp}.db",
                            "mime": "application/octet-stream",
                            "data": payload,
                            "company_count": snapshot_health["company_count"],
                            "reason": "download prepared from validated runtime snapshot",
                        }
                finally:
                    if os.path.exists(snapshot_path):
                        try:
                            os.remove(snapshot_path)
                        except OSError:
                            pass
        except Exception as exc:
            logger_instance.warning("Runtime backup export preparation failed: %s", exc)

    diagnostics = get_recovery_source_diagnostics()
    latest_object = diagnostics.get("object_name") or FIREBASE_OBJECT_NAME
    bucket = _get_firebase_recovery_bucket()
    if bucket is None:
        reason = diagnostics.get("credential_error") or "firebase backup bucket is not accessible"
        logger_instance.warning("Admin backup export unavailable: %s", reason)
        return {
            "ok": False,
            "source": "unavailable",
            "filename": None,
            "mime": "application/octet-stream",
            "data": None,
            "company_count": None,
            "reason": reason,
        }

    temp_download_path = None
    try:
        blob = bucket.blob(latest_object)
        if not blob.exists():
            reason = f"trusted cloud backup object was not found: bucket={diagnostics.get('bucket_name')} object={latest_object}"
            logger_instance.warning("Admin backup export unavailable: %s", reason)
            return {
                "ok": False,
                "source": "cloud_backup",
                "filename": None,
                "mime": "application/octet-stream",
                "data": None,
                "company_count": None,
                "reason": reason,
            }

        temp_fd, temp_download_path = tempfile.mkstemp(
            prefix="eka_backup_export_",
            suffix=".db",
            dir=DB_DIR,
        )
        os.close(temp_fd)
        blob.download_to_filename(temp_download_path)
        cloud_health = get_database_health_snapshot(temp_download_path, logger_instance=logger_instance)
        if not cloud_health["production_ready"]:
            reason = "; ".join(cloud_health.get("readiness_failures", [])) or "downloaded cloud backup is not production-ready"
            logger_instance.warning("Admin backup export blocked because cloud backup validation failed: %s", reason)
            return {
                "ok": False,
                "source": "cloud_backup",
                "filename": None,
                "mime": "application/octet-stream",
                "data": None,
                "company_count": cloud_health.get("company_count"),
                "reason": reason,
            }

        with open(temp_download_path, "rb") as download_file:
            payload = download_file.read()
        logger_instance.info(
            "Admin backup export prepared from cloud backup: bucket=%s object=%s company_count=%s bytes=%s",
            diagnostics.get("bucket_name"),
            latest_object,
            cloud_health["company_count"],
            len(payload),
        )
        return {
            "ok": True,
            "source": "cloud_backup",
            "filename": f"eka_enterprise_v3_cloud_{timestamp}.db",
            "mime": "application/octet-stream",
            "data": payload,
            "company_count": cloud_health["company_count"],
            "reason": f"download prepared from validated cloud backup object {latest_object}",
        }
    except Exception as exc:
        reason = f"cloud backup export failed: {exc}"
        logger_instance.warning("Admin backup export failed: %s", reason)
        return {
            "ok": False,
            "source": "cloud_backup",
            "filename": None,
            "mime": "application/octet-stream",
            "data": None,
            "company_count": None,
            "reason": reason,
        }
    finally:
        if temp_download_path and os.path.exists(temp_download_path):
            try:
                os.remove(temp_download_path)
            except OSError:
                pass


def restore_latest_cloud_backup_to_local(logger_instance=None, explicit_recovery_mode=False):
    global LAST_RESTORE_SOURCE, LAST_CLOUD_RESTORE_SKIP_REASON
    LAST_CLOUD_RESTORE_SKIP_REASON = None
    logger_instance = logger_instance or logger
    if is_test_runtime() and not is_test_cloud_restore_allowed():
        skip_reason = "cloud restore is disabled during automated tests"
        LAST_CLOUD_RESTORE_SKIP_REASON = skip_reason
        logger.warning(skip_reason)
        return {
            "ok": False,
            "stage": "recovery_disabled_in_tests",
            "reason": skip_reason,
            "bucket_name": None,
            "object_name": None,
            "selected_source_type": None,
            "selected_object_path": None,
            "replacement_performed": False,
            "temp_download_succeeded": False,
            "health": get_database_health_snapshot(DB_PATH, logger_instance=logger_instance),
            "validation_attempts": [],
            "restore_skipped_reason": skip_reason,
        }
    diagnostics = get_recovery_source_diagnostics()
    bucket = _get_firebase_recovery_bucket()
    local_health = get_database_health_snapshot(DB_PATH, logger_instance=logger_instance)
    if bucket is None:
        access_reason = diagnostics.get("credential_error") or "firebase backup bucket is not accessible"
        logger_instance.error(
            "Cloud restore unavailable because Firebase bucket is not accessible: bucket=%s object=%s reason=%s",
            diagnostics.get("bucket_name") or "missing",
            diagnostics.get("object_name") or "missing",
            sanitize_error_message(access_reason),
        )
        return {
            "ok": False,
            "stage": "recovery_source",
            "reason": access_reason,
            "bucket_name": diagnostics.get("bucket_name"),
            "object_name": diagnostics.get("object_name"),
            "selected_source_type": None,
            "selected_object_path": None,
            "replacement_performed": False,
            "temp_download_succeeded": False,
            "health": local_health,
        }

    selected_candidate = None
    pre_restore_path = None
    try:
        selected_candidate = _select_valid_cloud_backup(
            bucket,
            diagnostics.get("object_name") or FIREBASE_OBJECT_NAME,
            logger_instance=logger_instance,
        )
        if not selected_candidate.get("ok"):
            return {
                "ok": False,
                "stage": "recovery_validation",
                "reason": selected_candidate.get("reason") or "no valid cloud backup candidate was found",
                "bucket_name": diagnostics.get("bucket_name"),
                "object_name": diagnostics.get("object_name"),
                "selected_source_type": None,
                "selected_object_path": None,
                "replacement_performed": False,
                "temp_download_succeeded": False,
                "health": local_health,
                "validation_attempts": selected_candidate.get("validation_attempts") or [],
            }

        temp_restore_path = selected_candidate.get("temp_path")
        selected_health = selected_candidate.get("health") or {}
        if not temp_restore_path or not os.path.exists(temp_restore_path) or not _candidate_is_valid_production_backup(selected_health):
            return {
                "ok": False,
                "stage": "recovery_validation",
                "reason": "selected cloud backup candidate did not pass production-ready validation",
                "bucket_name": diagnostics.get("bucket_name"),
                "object_name": diagnostics.get("object_name"),
                "selected_source_type": selected_candidate.get("source_type"),
                "selected_object_path": selected_candidate.get("object_path"),
                "replacement_performed": False,
                "temp_download_succeeded": bool(temp_restore_path and os.path.exists(temp_restore_path)),
                "health": selected_health or local_health,
                "validation_attempts": selected_candidate.get("validation_attempts") or [],
            }

        replacement_check = _evaluate_runtime_replacement(
            local_health,
            selected_health,
            explicit_recovery_mode=explicit_recovery_mode,
        )
        if not replacement_check.get("allowed"):
            skip_reason = replacement_check.get("reason")
            LAST_CLOUD_RESTORE_SKIP_REASON = skip_reason
            logger_instance.warning(
                "Cloud restore replacement blocked: reason=%s local_company_count=%s incoming_company_count=%s local_ready=%s incoming_ready=%s explicit_recovery_mode=%s",
                skip_reason,
                local_health.get("company_count"),
                selected_health.get("company_count"),
                local_health.get("production_ready"),
                selected_health.get("production_ready"),
                explicit_recovery_mode,
            )
            return {
                "ok": False,
                "stage": "replacement_guard",
                "reason": skip_reason,
                "bucket_name": diagnostics.get("bucket_name"),
                "object_name": diagnostics.get("object_name"),
                "selected_source_type": selected_candidate.get("source_type"),
                "selected_object_path": selected_candidate.get("object_path"),
                "replacement_performed": False,
                "temp_download_succeeded": bool(temp_restore_path and os.path.exists(temp_restore_path)),
                "health": local_health,
                "incoming_health": selected_health,
                "company_count": int(local_health.get("company_count") or 0),
                "incoming_company_count": int(selected_health.get("company_count") or 0),
                "validation_attempts": selected_candidate.get("validation_attempts") or [],
                "restore_skipped_reason": skip_reason,
            }

        if os.path.exists(DB_PATH):
            pre_restore_path = _build_pre_cloud_restore_backup_path()
            shutil.copy2(DB_PATH, pre_restore_path)
            logger_instance.info(
                "Pre-cloud-restore local runtime database snapshot created: source=%s archive=%s",
                DB_PATH,
                pre_restore_path,
            )
            os.replace(temp_restore_path, DB_PATH)
        else:
            os.replace(temp_restore_path, DB_PATH)
        LAST_RESTORE_SOURCE = "cloud_restore:{bucket}::{object_path}".format(
            bucket=diagnostics.get("bucket_name") or "missing",
            object_path=selected_candidate.get("object_path") or diagnostics.get("object_name") or "missing",
        )
        final_health = get_database_health_snapshot(DB_PATH, logger_instance=logger_instance)
        _write_restore_guard_state(
            {
                "active": True,
                "source_db_path": selected_candidate.get("object_path"),
                "target_db_path": DB_PATH,
                "restored_at": datetime.utcnow().isoformat(timespec="seconds"),
                "restored_company_count": int(final_health.get("company_count") or 0),
                "restored_production_ready": bool(final_health.get("production_ready")),
                "pre_restore_backup_path": pre_restore_path,
            },
            logger_instance=logger_instance,
        )
        logger_instance.info(
            "Cloud restore completed: source_type=%s bucket=%s object=%s restored_company_count=%s production_ready=%s",
            selected_candidate.get("source_type"),
            diagnostics.get("bucket_name") or "missing",
            selected_candidate.get("object_path") or diagnostics.get("object_name") or "missing",
            final_health.get("company_count"),
            final_health.get("production_ready"),
        )
        return {
            "ok": True,
            "stage": "recovery_complete",
            "reason": "validated cloud backup restored successfully",
            "bucket_name": diagnostics.get("bucket_name"),
            "object_name": diagnostics.get("object_name"),
            "selected_source_type": selected_candidate.get("source_type"),
            "selected_object_path": selected_candidate.get("object_path"),
            "replacement_performed": True,
            "temp_download_succeeded": True,
            "health": final_health,
            "company_count": int(final_health.get("company_count") or 0),
            "pre_restore_backup_path": pre_restore_path,
            "validation_attempts": selected_candidate.get("validation_attempts") or [],
        }
    except Exception as exc:
        logger_instance.error("Cloud restore failed: %s", sanitize_error_message(exc))
        return {
            "ok": False,
            "stage": "recovery_exception",
            "reason": str(exc),
            "bucket_name": diagnostics.get("bucket_name"),
            "object_name": diagnostics.get("object_name"),
            "selected_source_type": selected_candidate.get("source_type") if selected_candidate else None,
            "selected_object_path": selected_candidate.get("object_path") if selected_candidate else None,
            "replacement_performed": False,
            "temp_download_succeeded": bool(selected_candidate and selected_candidate.get("temp_path") and os.path.exists(selected_candidate.get("temp_path"))),
            "health": get_database_health_snapshot(DB_PATH, logger_instance=logger_instance),
            "validation_attempts": selected_candidate.get("validation_attempts") if selected_candidate else [],
        }
    finally:
        temp_path = selected_candidate.get("temp_path") if selected_candidate else None
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def restore_runtime_database_from_local_file(source_db_path, logger_instance=None):
    logger_instance = logger_instance or logger
    normalized_source = os.path.abspath(str(source_db_path or "").strip())
    if not normalized_source:
        raise ValueError("source_db_path is required")
    if not os.path.exists(normalized_source):
        raise FileNotFoundError(f"Source database file does not exist: {normalized_source}")
    if not is_sqlite_file(normalized_source):
        raise RuntimeError(f"Source file is not a valid SQLite database: {normalized_source}")

    source_health = get_database_health_snapshot(normalized_source, logger_instance=logger_instance)
    pre_restore_backup = None
    if os.path.exists(DB_PATH):
        pre_restore_backup = create_timestamped_backup(DB_PATH, logger=logger_instance, reason="pre_local_restore")

    os.makedirs(DB_DIR, exist_ok=True)
    shutil.copy2(normalized_source, DB_PATH)
    restored_health = get_database_health_snapshot(DB_PATH, logger_instance=logger_instance)
    restored_company_count = int(restored_health.get("company_count") or 0)
    _write_restore_guard_state(
        {
            "active": True,
            "created_at": datetime.utcnow().isoformat(timespec="seconds"),
            "source_db_path": normalized_source,
            "target_db_path": DB_PATH,
            "restored_company_count": restored_company_count,
            "restored_production_ready": bool(restored_health.get("production_ready")),
            "pre_restore_backup_path": pre_restore_backup,
        },
        logger_instance=logger_instance,
    )
    logger_instance.info(
        "Local runtime database restored from file: source=%s target=%s company_count_after_restore=%s production_ready=%s",
        normalized_source,
        DB_PATH,
        restored_company_count,
        restored_health.get("production_ready"),
    )
    return {
        "ok": True,
        "source_db_path": normalized_source,
        "target_db_path": DB_PATH,
        "company_count_after_restore": restored_company_count,
        "production_ready_after_restore": bool(restored_health.get("production_ready")),
        "pre_restore_backup_path": pre_restore_backup,
        "restore_guard_path": LOCAL_RESTORE_GUARD_PATH,
        "source_health": source_health,
        "restored_health": restored_health,
    }


def get_cloud_backup_diagnostics(logger_instance=None):
    logger_instance = logger_instance or logger
    diagnostics = get_recovery_source_diagnostics()
    latest_object = diagnostics.get("object_name") or FIREBASE_OBJECT_NAME
    result = {
        "ok": False,
        "bucket_name": diagnostics.get("bucket_name"),
        "object_name": latest_object,
        "last_modified": None,
        "company_count": None,
        "database_uuid": None,
        "production_ready": None,
        "newer_than_local": None,
        "reason": diagnostics.get("credential_error") or "cloud backup diagnostics not available",
    }

    bucket = _get_firebase_recovery_bucket()
    if bucket is None:
        logger_instance.warning("Cloud backup diagnostics unavailable: bucket is not accessible")
        return result

    blob = bucket.blob(latest_object)
    try:
        backup_exists = bool(blob.exists())
    except Exception as exc:
        result["reason"] = f"cloud backup presence check failed: {exc}"
        logger_instance.warning(
            "Cloud backup diagnostics failed while checking object existence: bucket=%s object=%s error=%s",
            diagnostics.get("bucket_name"),
            latest_object,
            exc,
        )
        return result

    if not backup_exists:
        result["reason"] = f"trusted cloud backup object was not found: bucket={diagnostics.get('bucket_name')} object={latest_object}"
        logger_instance.info(
            "Cloud backup diagnostics: latest object missing bucket=%s object=%s",
            diagnostics.get("bucket_name"),
            latest_object,
        )
        return result

    try:
        blob.reload()
    except Exception:
        pass
    blob_updated = getattr(blob, "updated", None)
    if blob_updated is not None:
        result["last_modified"] = blob_updated.isoformat() if hasattr(blob_updated, "isoformat") else str(blob_updated)

    temp_download_path = None
    try:
        temp_fd, temp_download_path = tempfile.mkstemp(
            prefix="eka_cloud_backup_diag_",
            suffix=".db",
            dir=DB_DIR,
        )
        os.close(temp_fd)
        blob.download_to_filename(temp_download_path)
        downloaded_health = get_database_health_snapshot(temp_download_path, logger_instance=logger_instance)
        result["company_count"] = downloaded_health.get("company_count")
        result["database_uuid"] = downloaded_health.get("database_uuid")
        result["production_ready"] = downloaded_health.get("production_ready")
        if os.path.exists(DB_PATH):
            try:
                local_mtime = datetime.utcfromtimestamp(os.path.getmtime(DB_PATH))
                if blob_updated is not None:
                    newer_than_local = blob_updated.replace(tzinfo=None) > local_mtime
                    result["newer_than_local"] = bool(newer_than_local)
            except Exception:
                result["newer_than_local"] = None
        result["ok"] = True
        result["reason"] = "cloud backup diagnostics collected successfully"
        logger_instance.info(
            "Cloud backup diagnostics collected: bucket=%s object=%s last_modified=%s company_count=%s newer_than_local=%s",
            diagnostics.get("bucket_name"),
            latest_object,
            result["last_modified"] or "unknown",
            result["company_count"],
            result["newer_than_local"],
        )
        return result
    except Exception as exc:
        result["reason"] = f"cloud backup diagnostics download failed: {exc}"
        logger_instance.warning(
            "Cloud backup diagnostics failed while downloading latest object: bucket=%s object=%s error=%s",
            diagnostics.get("bucket_name"),
            latest_object,
            exc,
        )
        return result
    finally:
        if temp_download_path and os.path.exists(temp_download_path):
            try:
                os.remove(temp_download_path)
            except OSError:
                pass


def run_persistence_self_test(logger_instance=None):
    logger_instance = logger_instance or logger
    local_health = get_database_health_snapshot(DB_PATH, logger_instance=logger_instance)
    local_backup = get_local_backup_diagnostics(logger_instance=logger_instance)
    cloud_backup = get_cloud_backup_diagnostics(logger_instance=logger_instance)
    local_cloud_mismatch = (
        local_backup.get("company_count") is not None
        and cloud_backup.get("company_count") is not None
        and int(local_backup.get("company_count") or 0) != int(cloud_backup.get("company_count") or 0)
    )
    runtime_cloud_mismatch = (
        cloud_backup.get("company_count") is not None
        and int(local_health.get("company_count") or 0) != int(cloud_backup.get("company_count") or 0)
    )
    runtime_local_backup_mismatch = (
        local_backup.get("company_count") is not None
        and int(local_health.get("company_count") or 0) != int(local_backup.get("company_count") or 0)
    )
    result = {
        "ok": bool(local_backup.get("ok")) and bool(cloud_backup.get("ok")) and not local_cloud_mismatch,
        "local_company_count": int(local_health.get("company_count") or 0),
        "local_backup_company_count": local_backup.get("company_count"),
        "cloud_backup_company_count": cloud_backup.get("company_count"),
        "latest_local_backup_path": local_backup.get("latest_path"),
        "latest_backup_object_path": cloud_backup.get("object_name"),
        "last_local_backup_time": local_backup.get("last_modified"),
        "last_cloud_backup_time": cloud_backup.get("last_modified"),
        "last_backup_time": cloud_backup.get("last_modified"),
        "mismatch": bool(local_cloud_mismatch or runtime_cloud_mismatch or runtime_local_backup_mismatch),
        "local_cloud_mismatch": local_cloud_mismatch,
        "runtime_cloud_mismatch": runtime_cloud_mismatch,
        "runtime_local_backup_mismatch": runtime_local_backup_mismatch,
        "reason": f"local_backup={local_backup.get('reason')}; cloud_backup={cloud_backup.get('reason')}",
    }
    logger_instance.info(
        "Persistence self-test: local_company_count=%s local_backup_company_count=%s cloud_backup_company_count=%s mismatch=%s local_latest=%s cloud_latest=%s local_backup_time=%s cloud_backup_time=%s reason=%s",
        result["local_company_count"],
        result["local_backup_company_count"],
        result["cloud_backup_company_count"],
        result["mismatch"],
        result["latest_local_backup_path"],
        result["latest_backup_object_path"],
        result["last_local_backup_time"] or "unknown",
        result["last_cloud_backup_time"] or "unknown",
        result["reason"],
    )
    return result


def force_backup_after_company_creation(company_name, company_key=None, logger_instance=None):
    logger_instance = logger_instance or logger
    post_commit_health = get_database_health_snapshot(DB_PATH, logger_instance=logger_instance)
    company_count = int(post_commit_health.get("company_count") or 0)
    logger_instance.info(
        "Company creation committed: company_key=%s company_name=%s canonical_db_path=%s company_count=%s",
        company_key or "unknown",
        company_name,
        DB_PATH,
        company_count,
    )
    if company_count <= 0:
        reason = "forced backup blocked because canonical database still has company_count=0 after company creation commit"
        logger_instance.warning("Company creation backup blocked: %s", reason)
        return {"ok": False, "reason": reason, "company_count": company_count}

    logger_instance.info(
        "Company creation backup upload starting: company_key=%s company_name=%s latest_object=%s",
        company_key or "unknown",
        company_name,
        FIREBASE_OBJECT_NAME,
    )
    backup_result = backup_runtime_database_to_cloud(
        force=True,
        trigger_tables=["companies"],
        logger_instance=logger_instance,
    )
    if backup_result.get("ok"):
        logger_instance.info(
            "Company creation backup upload succeeded: company_key=%s company_name=%s local_latest_updated=%s local_history_created=%s latest_object_updated=%s history_snapshot_created=%s",
            company_key or "unknown",
            company_name,
            backup_result.get("latest_local_path"),
            backup_result.get("history_local_path"),
            backup_result.get("latest_object"),
            backup_result.get("history_object"),
        )
    else:
        logger_instance.warning(
            "Company creation backup upload failed: company_key=%s company_name=%s reason=%s",
            company_key or "unknown",
            company_name,
            backup_result.get("reason"),
        )
    return {
        "ok": bool(backup_result.get("ok")),
        "reason": backup_result.get("reason"),
        "company_count": company_count,
        "latest_local_path": backup_result.get("latest_local_path"),
        "history_local_path": backup_result.get("history_local_path"),
        "latest_object": backup_result.get("latest_object"),
        "history_object": backup_result.get("history_object"),
    }


def create_company_record(
    conn,
    company_key,
    company_name,
    subscription_expiry,
    status="Active",
    deployment_status="Live",
    number_of_branches=1,
    max_branches=1,
    branch_price_per_month=0.0,
    contact_email=None,
    subscription_plan_name=None,
    subscription_status=None,
    subscription_start_date=None,
    subscription_end_date=None,
    last_payment_reference=None,
):
    if conn is None:
        raise RuntimeError("Database connection is required to create a company record.")
    normalized_key = str(company_key or "").strip()
    normalized_name = str(company_name or "").strip()
    if not normalized_key or not normalized_name:
        raise ValueError("company_key and company_name are required")
    conn.execute(
        """
        INSERT INTO companies (
            key,
            name,
            subscription_expiry,
            status,
            deployment_status,
            number_of_branches,
            max_branches,
            branch_price_per_month,
            contact_email
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_key,
            normalized_name,
            str(subscription_expiry),
            str(status or "Active"),
            str(deployment_status or "Live"),
            int(number_of_branches or 1),
            int(max_branches or 1),
            float(branch_price_per_month or 0.0),
            str(contact_email or "").strip() or None,
        ),
    )
    resolved_status = str(subscription_status or "").strip().lower()
    resolved_plan_name = str(subscription_plan_name or "").strip() or "Manual"
    expiry_value = str(subscription_expiry or "").strip()
    derived_end_date = subscription_end_date
    if not derived_end_date and expiry_value and expiry_value.lower() != "permanent":
        derived_end_date = expiry_value
    derived_start_date = subscription_start_date or datetime.now().date().isoformat()
    if not resolved_status:
        if expiry_value.lower() == "permanent":
            resolved_status = "active"
            derived_end_date = None
        elif derived_end_date:
            parsed_end = _parse_datetime_like(derived_end_date)
            if parsed_end is not None and parsed_end.date() < datetime.now().date():
                resolved_status = "expired"
            else:
                resolved_status = "active"
        else:
            resolved_status = "trial"
    upsert_company_subscription(
        conn,
        company_key=normalized_key,
        plan_name=resolved_plan_name,
        status=resolved_status,
        start_date=derived_start_date,
        end_date=derived_end_date,
        last_payment_reference=last_payment_reference,
    )
    return normalized_key


def _parse_datetime_like(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        text = str(value).strip()
    except Exception:
        return None
    if not text:
        return None
    if text.lower() == "permanent":
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        try:
            return datetime.fromisoformat(f"{text}T00:00:00")
        except Exception:
            return None


def _normalize_subscription_status(status):
    normalized = str(status or "").strip().lower()
    if normalized not in SUBSCRIPTION_BILLING_STATUSES:
        if normalized in {"warning", "expiring_soon"}:
            return "active"
        return "trial"
    return normalized


def _ensure_subscription_billing_schema(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS company_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT UNIQUE,
            plan_name TEXT,
            status TEXT DEFAULT 'trial',
            start_date TEXT,
            end_date TEXT,
            last_payment_reference TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key)
        )
        """
    )
    cursor.execute("PRAGMA table_info(company_subscriptions)")
    subscription_columns = {row[1] for row in cursor.fetchall()}
    subscription_column_defs = {
        "company_key": "TEXT",
        "plan_name": "TEXT",
        "status": "TEXT DEFAULT 'trial'",
        "start_date": "TEXT",
        "end_date": "TEXT",
        "last_payment_reference": "TEXT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_def in subscription_column_defs.items():
        if column_name not in subscription_columns:
            cursor.execute(f"ALTER TABLE company_subscriptions ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_company_subscriptions_company_key ON company_subscriptions(company_key)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_subscriptions_status_end_date ON company_subscriptions(status, end_date)"
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_plan_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_name TEXT UNIQUE,
            configured_amount REAL,
            currency TEXT DEFAULT 'GHS',
            duration_months INTEGER DEFAULT 0,
            duration_days INTEGER DEFAULT 0,
            features_json TEXT,
            updated_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("PRAGMA table_info(subscription_plan_settings)")
    plan_settings_columns = {row[1] for row in cursor.fetchall()}
    plan_settings_column_defs = {
        "plan_name": "TEXT",
        "configured_amount": "REAL",
        "currency": "TEXT DEFAULT 'GHS'",
        "duration_months": "INTEGER DEFAULT 0",
        "duration_days": "INTEGER DEFAULT 0",
        "features_json": "TEXT",
        "updated_by": "TEXT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_def in plan_settings_column_defs.items():
        if column_name not in plan_settings_columns:
            cursor.execute(f"ALTER TABLE subscription_plan_settings ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_plan_settings_plan_name ON subscription_plan_settings(plan_name)"
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS license_payment_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT UNIQUE,
            company_key TEXT,
            company_name TEXT,
            payer_email TEXT,
            payment_context TEXT DEFAULT 'license_activation',
            plan_name TEXT,
            configured_amount REAL DEFAULT 0,
            configured_duration_months INTEGER DEFAULT 0,
            configured_duration_days INTEGER DEFAULT 0,
            expected_amount INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            status TEXT DEFAULT 'initialized',
            authorization_url TEXT,
            callback_url TEXT,
            metadata_json TEXT,
            gateway_status_summary TEXT,
            paid_at TIMESTAMP,
            verified_at TIMESTAMP,
            activated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("PRAGMA table_info(license_payment_transactions)")
    license_payment_columns = {row[1] for row in cursor.fetchall()}
    license_payment_column_defs = {
        "company_key": "TEXT",
        "company_name": "TEXT",
        "payer_email": "TEXT",
        "payment_context": "TEXT DEFAULT 'license_activation'",
        "plan_name": "TEXT",
        "configured_amount": "REAL DEFAULT 0",
        "configured_duration_months": "INTEGER DEFAULT 0",
        "configured_duration_days": "INTEGER DEFAULT 0",
        "expected_amount": "INTEGER DEFAULT 0",
        "currency": "TEXT DEFAULT 'GHS'",
        "status": "TEXT DEFAULT 'initialized'",
        "authorization_url": "TEXT",
        "callback_url": "TEXT",
        "metadata_json": "TEXT",
        "gateway_status_summary": "TEXT",
        "paid_at": "TIMESTAMP",
        "verified_at": "TIMESTAMP",
        "activated_at": "TIMESTAMP",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_def in license_payment_column_defs.items():
        if column_name not in license_payment_columns:
            cursor.execute(f"ALTER TABLE license_payment_transactions ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_license_payment_transactions_company_status ON license_payment_transactions(company_key, status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_license_payment_transactions_verified_at ON license_payment_transactions(verified_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_license_payment_transactions_plan_status ON license_payment_transactions(plan_name, status)"
    )


def upsert_subscription_plan_setting(
    conn,
    *,
    plan_name,
    configured_amount,
    currency="GHS",
    duration_months=None,
    duration_days=None,
    features_json=None,
    updated_by=None,
):
    if conn is None:
        raise RuntimeError("Database connection is required to save subscription pricing.")
    normalized_plan_name = str(plan_name or "").strip()
    if not normalized_plan_name:
        raise ValueError("plan_name is required")
    amount_value = float(configured_amount) if configured_amount not in (None, "") else None
    currency_value = str(currency or "GHS").strip().upper() or "GHS"
    months_value = max(int(duration_months or 0), 0)
    days_value = max(int(duration_days or 0), 0)
    cursor = conn.cursor()
    _ensure_subscription_billing_schema(cursor)
    conn.execute(
        """
        INSERT INTO subscription_plan_settings (
            plan_name,
            configured_amount,
            currency,
            duration_months,
            duration_days,
            features_json,
            updated_by,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(plan_name) DO UPDATE SET
            configured_amount = excluded.configured_amount,
            currency = excluded.currency,
            duration_months = excluded.duration_months,
            duration_days = excluded.duration_days,
            features_json = COALESCE(excluded.features_json, subscription_plan_settings.features_json),
            updated_by = excluded.updated_by,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            normalized_plan_name,
            amount_value,
            currency_value,
            months_value,
            days_value,
            features_json,
            str(updated_by or "").strip() or None,
        ),
    )


def get_subscription_plan_settings(conn=None):
    owns_connection = conn is None
    conn = conn or _open_sqlite_connection()
    try:
        cursor = conn.cursor()
        _ensure_subscription_billing_schema(cursor)
        rows = conn.execute(
            """
            SELECT plan_name, configured_amount, currency, duration_months, duration_days, features_json, updated_by, updated_at
            FROM subscription_plan_settings
            ORDER BY plan_name
            """
        ).fetchall()
        settings = {}
        for row in rows:
            settings[str(row["plan_name"] or "").strip()] = dict(row)
        return settings
    finally:
        if owns_connection and conn:
            conn.close()


def get_subscription_plan_setting(plan_name, conn=None):
    normalized_plan_name = str(plan_name or "").strip()
    if not normalized_plan_name:
        return None
    owns_connection = conn is None
    conn = conn or _open_sqlite_connection()
    try:
        cursor = conn.cursor()
        _ensure_subscription_billing_schema(cursor)
        row = conn.execute(
            """
            SELECT plan_name, configured_amount, currency, duration_months, duration_days, features_json, updated_by, updated_at
            FROM subscription_plan_settings
            WHERE plan_name = ?
            LIMIT 1
            """,
            (normalized_plan_name,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        if owns_connection and conn:
            conn.close()


def upsert_company_subscription(
    conn,
    *,
    company_key,
    plan_name,
    status,
    start_date,
    end_date=None,
    last_payment_reference=None,
):
    if conn is None:
        raise RuntimeError("Database connection is required to update company subscriptions.")
    normalized_key = str(company_key or "").strip()
    if not normalized_key:
        raise ValueError("company_key is required")
    normalized_status = _normalize_subscription_status(status)
    normalized_plan_name = str(plan_name or "Trial").strip() or "Trial"
    start_value = str(start_date or datetime.now().date().isoformat())
    end_value = str(end_date).strip() if end_date not in (None, "") else None
    conn.execute(
        """
        INSERT INTO company_subscriptions (
            company_key, plan_name, status, start_date, end_date, last_payment_reference, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(company_key) DO UPDATE SET
            plan_name = excluded.plan_name,
            status = excluded.status,
            start_date = excluded.start_date,
            end_date = excluded.end_date,
            last_payment_reference = COALESCE(excluded.last_payment_reference, company_subscriptions.last_payment_reference),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            normalized_key,
            normalized_plan_name,
            normalized_status,
            start_value,
            end_value,
            str(last_payment_reference or "").strip() or None,
        ),
    )


def ensure_company_trial_subscription(
    conn,
    *,
    company_key,
    company_name,
    contact_email=None,
    trial_days=DEFAULT_SUBSCRIPTION_TRIAL_DAYS,
):
    if conn is None:
        raise RuntimeError("Database connection is required to create a trial company.")
    normalized_key = str(company_key or "").strip()
    normalized_name = str(company_name or "").strip()
    if not normalized_key or not normalized_name:
        raise ValueError("company_key and company_name are required")
    today = datetime.now().date()
    end_date = today + timedelta(days=max(int(trial_days or DEFAULT_SUBSCRIPTION_TRIAL_DAYS), 1))
    company_row = conn.execute(
        "SELECT key FROM companies WHERE key = ? LIMIT 1",
        (normalized_key,),
    ).fetchone()
    if not company_row:
        create_company_record(
            conn=conn,
            company_key=normalized_key,
            company_name=normalized_name,
            subscription_expiry=end_date.isoformat(),
            status="Active",
            deployment_status="Trial",
            contact_email=contact_email,
            subscription_plan_name="Trial",
            subscription_status="trial",
            subscription_start_date=today.isoformat(),
            subscription_end_date=end_date.isoformat(),
        )
    else:
        conn.execute(
            "UPDATE companies SET subscription_expiry = ?, contact_email = COALESCE(?, contact_email), deployment_status = COALESCE(NULLIF(deployment_status, ''), 'Trial') WHERE key = ?",
            (end_date.isoformat(), str(contact_email or "").strip() or None, normalized_key),
        )
        upsert_company_subscription(
            conn,
            company_key=normalized_key,
            plan_name="Trial",
            status="trial",
            start_date=today.isoformat(),
            end_date=end_date.isoformat(),
        )
    return {
        "company_key": normalized_key,
        "company_name": normalized_name,
        "status": "trial",
        "start_date": today.isoformat(),
        "end_date": end_date.isoformat(),
        "days_left": max((end_date - today).days, 0),
    }


def get_company_subscription_snapshot(company_key, conn=None, as_of=None):
    normalized_key = str(company_key or "").strip()
    if not normalized_key:
        return {
            "ok": False,
            "company_key": normalized_key,
            "status": "unknown",
            "access_allowed": False,
            "renewal_required": True,
            "days_left": None,
        }
    owns_connection = conn is None
    conn = conn or _open_sqlite_connection()
    try:
        today = _parse_datetime_like(as_of) or datetime.now()
        row = conn.execute(
            """
            SELECT cs.company_key, cs.plan_name, cs.status, cs.start_date, cs.end_date, cs.last_payment_reference,
                   c.subscription_expiry, c.status AS company_status, c.name AS company_name
            FROM companies c
            LEFT JOIN company_subscriptions cs ON cs.company_key = c.key
            WHERE c.key = ?
            LIMIT 1
            """,
            (normalized_key,),
        ).fetchone()
        if not row:
            return {
                "ok": False,
                "company_key": normalized_key,
                "status": "unknown",
                "access_allowed": False,
                "renewal_required": True,
                "days_left": None,
            }

        status = _normalize_subscription_status(row["status"] or "active")
        plan_name = str(row["plan_name"] or "").strip() or ("Manual" if row["subscription_expiry"] else "Trial")
        start_date = row["start_date"]
        end_date = row["end_date"] or row["subscription_expiry"]
        if str(row["subscription_expiry"] or "").strip().lower() == "permanent":
            end_date = None
            status = "active"
            plan_name = plan_name or "Manual"
        parsed_end = _parse_datetime_like(end_date)
        parsed_start = _parse_datetime_like(start_date)
        access_allowed = status in {"trial", "active"}
        renewal_required = status in {"expired", "cancelled"}
        days_left = None
        if parsed_end is not None:
            days_left = (parsed_end.date() - today.date()).days
            if days_left < 0 and status in {"trial", "active"}:
                status = "expired"
                access_allowed = False
                renewal_required = True
                if row["status"] and row["status"] != "expired":
                    conn.execute(
                        """
                        UPDATE company_subscriptions
                        SET status = 'expired', updated_at = CURRENT_TIMESTAMP
                        WHERE company_key = ?
                        """,
                        (normalized_key,),
                    )
                    conn.execute(
                        "UPDATE companies SET subscription_expiry = ? WHERE key = ?",
                        (parsed_end.date().isoformat(), normalized_key),
                    )
                    if owns_connection:
                        conn.commit()
        elif status == "cancelled":
            access_allowed = False
            renewal_required = True
        return {
            "ok": True,
            "company_key": normalized_key,
            "company_name": row["company_name"],
            "plan_name": plan_name,
            "status": status,
            "start_date": parsed_start.date().isoformat() if parsed_start else (start_date or None),
            "end_date": parsed_end.date().isoformat() if parsed_end else None,
            "last_payment_reference": row["last_payment_reference"],
            "days_left": days_left,
            "access_allowed": access_allowed,
            "renewal_required": renewal_required,
            "is_trial": status == "trial",
            "is_active": status in {"trial", "active"} and access_allowed,
            "is_expired": status == "expired",
            "is_cancelled": status == "cancelled",
            "company_status": row["company_status"],
        }
    finally:
        if owns_connection and conn:
            conn.close()


def activate_company_subscription(
    conn,
    *,
    company_key,
    plan_name,
    payment_reference,
    duration_months=None,
    duration_days=None,
):
    if conn is None:
        raise RuntimeError("Database connection is required to activate subscriptions.")
    normalized_key = str(company_key or "").strip()
    if not normalized_key:
        raise ValueError("company_key is required")
    today = datetime.now().date()
    current = get_company_subscription_snapshot(normalized_key, conn=conn, as_of=today.isoformat())
    current_end = _parse_datetime_like(current.get("end_date")) if current.get("ok") else None
    if current.get("ok") and current.get("status") in {"trial", "active"} and current_end and current_end.date() >= today:
        effective_base = current_end.date()
        start_date = current.get("start_date") or today.isoformat()
    else:
        effective_base = today
        start_date = today.isoformat()

    new_end = datetime.combine(effective_base, datetime.min.time())
    if int(duration_months or 0) > 0:
        from dateutil.relativedelta import relativedelta

        new_end = new_end + relativedelta(months=+int(duration_months or 0))
    elif int(duration_days or 0) > 0:
        new_end = new_end + timedelta(days=int(duration_days or 0))
    else:
        raise ValueError("A subscription activation duration is required.")

    upsert_company_subscription(
        conn,
        company_key=normalized_key,
        plan_name=plan_name,
        status="active",
        start_date=start_date,
        end_date=new_end.date().isoformat(),
        last_payment_reference=payment_reference,
    )
    conn.execute(
        """
        UPDATE companies
        SET subscription_expiry = ?, status = 'Active', deployment_status = 'Live'
        WHERE key = ?
        """,
        (new_end.date().isoformat(), normalized_key),
    )
    return {
        "company_key": normalized_key,
        "plan_name": str(plan_name or "").strip() or "Subscription",
        "start_date": start_date,
        "end_date": new_end.date().isoformat(),
        "was_extension": bool(current.get("ok") and current.get("status") in {"trial", "active"} and current_end and current_end.date() >= today),
    }


def get_subscription_billing_summary(conn=None):
    owns_connection = conn is None
    conn = conn or _open_sqlite_connection()
    try:
        configured_plans = get_subscription_plan_settings(conn=conn)
        totals_row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN status = 'success' THEN expected_amount ELSE 0 END), 0) AS total_verified_revenue,
                COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_payment_count,
                COALESCE(SUM(CASE WHEN status = 'abandoned' THEN 1 ELSE 0 END), 0) AS abandoned_payment_count
            FROM license_payment_transactions
            """
        ).fetchone()
        subscription_counts = conn.execute(
            """
            SELECT status, COUNT(*) AS row_count
            FROM company_subscriptions
            GROUP BY status
            """
        ).fetchall()
        revenue_by_plan = conn.execute(
            """
            SELECT COALESCE(NULLIF(plan_name, ''), 'Unspecified') AS plan_name,
                   COUNT(*) AS payment_count,
                   COALESCE(SUM(CASE WHEN status = 'success' THEN expected_amount ELSE 0 END), 0) AS revenue
            FROM license_payment_transactions
            GROUP BY COALESCE(NULLIF(plan_name, ''), 'Unspecified')
            ORDER BY revenue DESC, plan_name
            """
        ).fetchall()
        recent_payments = conn.execute(
            """
            SELECT reference, company_key, company_name, plan_name, expected_amount, currency, status, verified_at, paid_at
            FROM license_payment_transactions
            ORDER BY COALESCE(verified_at, paid_at, created_at) DESC
            LIMIT 10
            """
        ).fetchall()
        next_expiries = conn.execute(
            """
            SELECT company_key, plan_name, status, end_date
            FROM company_subscriptions
            WHERE status IN ('trial', 'active') AND end_date IS NOT NULL
            ORDER BY end_date ASC
            LIMIT 10
            """
        ).fetchall()
        status_map = {str(row["status"] or "").strip().lower(): int(row["row_count"] or 0) for row in subscription_counts}
        latest_success = conn.execute(
            """
            SELECT reference, company_key, plan_name, expected_amount, currency, verified_at
            FROM license_payment_transactions
            WHERE status = 'success'
            ORDER BY COALESCE(verified_at, paid_at, created_at) DESC
            LIMIT 1
            """
        ).fetchone()
        return {
            "ok": True,
            "total_verified_revenue": int(totals_row["total_verified_revenue"] or 0),
            "failed_payment_count": int(totals_row["failed_payment_count"] or 0),
            "abandoned_payment_count": int(totals_row["abandoned_payment_count"] or 0),
            "active_subscriptions": status_map.get("active", 0),
            "trial_subscriptions": status_map.get("trial", 0),
            "expired_subscriptions": status_map.get("expired", 0),
            "cancelled_subscriptions": status_map.get("cancelled", 0),
            "revenue_by_plan": [dict(row) for row in revenue_by_plan],
            "recent_payments": [dict(row) for row in recent_payments],
            "next_expiries": [dict(row) for row in next_expiries],
            "latest_successful_payment": dict(latest_success) if latest_success else None,
            "configured_plan_prices": configured_plans,
        }
    finally:
        if owns_connection and conn:
            conn.close()


def get_subscription_billing_diagnostics(conn=None):
    owns_connection = conn is None
    conn = conn or _open_sqlite_connection()
    try:
        table_rows = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name IN ('company_subscriptions', 'license_payment_transactions', 'subscription_plan_settings')
            """
        ).fetchall()
        table_names = {row[0] for row in table_rows}
        summary = get_subscription_billing_summary(conn=conn)
        return {
            "ok": True,
            "subscription_table_present": "company_subscriptions" in table_names,
            "payment_table_present": "license_payment_transactions" in table_names,
            "pricing_table_present": "subscription_plan_settings" in table_names,
            "active_count": summary.get("active_subscriptions", 0),
            "trial_count": summary.get("trial_subscriptions", 0),
            "expired_count": summary.get("expired_subscriptions", 0),
            "failed_payment_count": summary.get("failed_payment_count", 0),
            "latest_successful_payment": summary.get("latest_successful_payment"),
            "configured_plan_prices": summary.get("configured_plan_prices", {}),
        }
    finally:
        if owns_connection and conn:
            conn.close()


def _ensure_db_directory():
    os.makedirs(DB_DIR, exist_ok=True)
    if (
        LEGACY_DB_PATH != DB_PATH
        and os.path.exists(LEGACY_DB_PATH)
        and not os.path.exists(DB_PATH)
        and is_sqlite_file(LEGACY_DB_PATH)
    ):
        shutil.copy2(LEGACY_DB_PATH, DB_PATH)
        logger.info("Migrated legacy database to persistent path without overwriting existing data: %s", DB_PATH)


def _ensure_local_db_file():
    """
    Ensure the local database file exists without overwriting an existing file.
    In production mode we do not silently create a blank SQLite file, because a path
    change after deployment can make the app point at a fresh empty database.
    """
    _ensure_db_directory()
    if not os.path.exists(DB_PATH) and not ERP_PRODUCTION_MODE:
        conn = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.close()
        logger.info("Created local database file at: %s", DB_PATH)
    elif not os.path.exists(DB_PATH):
        logger.warning("Production mode detected missing database file; blank database creation is blocked at startup: %s", DB_PATH)


def _open_sqlite_connection(path=DB_PATH, enable_persistence_hooks=False):
    if os.path.abspath(path) == os.path.abspath(DB_PATH) and ERP_PRODUCTION_MODE and not os.path.exists(path):
        raise sqlite3.OperationalError(
            f"Production database file is missing and cannot be recreated outside startup recovery: {path}"
        )
    connection_factory = ManagedSQLiteConnection if enable_persistence_hooks else TrackedSQLiteConnection
    conn = sqlite3.connect(path, timeout=20, check_same_thread=False, factory=connection_factory)
    _diagnostic_connection_opened()
    conn.row_factory = sqlite3.Row
    if isinstance(conn, ManagedSQLiteConnection):
        conn._managed_db_path = path
        conn._persistence_hooks_enabled = bool(enable_persistence_hooks)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def ensure_schema():
    """
    Additive schema safety guard for existing deployments.
    Never drops tables or deletes rows; only adds missing tables/columns if needed.
    """
    if not os.path.exists(DB_PATH):
        logger.warning("Schema safety skipped because the database file does not exist yet: %s", DB_PATH)
        return False

    conn = None
    try:
        conn = _open_sqlite_connection()
        company_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(companies)").fetchall()
        }
        if company_columns and "subscription_expiry" not in company_columns:
            conn.execute("ALTER TABLE companies ADD COLUMN subscription_expiry TEXT DEFAULT 'Permanent'")
        ensure_schema_integrity(conn)
        conn.commit()
        logger.info("Schema safety ensured for additive ERP tables and columns on %s", DB_PATH)
        return True
    except sqlite3.Error as exc:
        if conn:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
        logger.warning("Schema safety check failed: %s", sanitize_error_message(exc))
        return False
    finally:
        if conn:
            conn.close()


def _ensure_migration_metadata_tables(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER,
            description TEXT,
            status TEXT NOT NULL,
            backup_path TEXT,
            company_count_before INTEGER DEFAULT 0,
            company_count_after INTEGER DEFAULT 0,
            row_counts_before TEXT,
            row_counts_after TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _ensure_database_identity_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS database_identity (
            instance_id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            schema_version INTEGER DEFAULT 0,
            last_startup_at TIMESTAMP,
            backend_label TEXT DEFAULT 'SQLite',
            environment_label TEXT
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(database_identity)").fetchall()}
    for column_name, column_def in {
        "schema_version": "INTEGER DEFAULT 0",
        "last_startup_at": "TIMESTAMP",
        "backend_label": "TEXT DEFAULT 'SQLite'",
        "environment_label": "TEXT",
    }.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE database_identity ADD COLUMN {column_name} {column_def}")
    conn.execute(
        """
        INSERT INTO database_identity (instance_id)
        SELECT ?
        WHERE NOT EXISTS (SELECT 1 FROM database_identity)
        """,
        (f"{os.path.basename(DB_PATH)}::{int(datetime.now().timestamp())}",),
    )
    conn.execute(
        """
        UPDATE database_identity
        SET last_verified_at = CURRENT_TIMESTAMP,
            schema_version = COALESCE((SELECT MAX(version) FROM schema_version), schema_version, 0),
            backend_label = COALESCE(NULLIF(backend_label, ''), 'SQLite'),
            environment_label = ?,
            last_startup_at = COALESCE(last_startup_at, CURRENT_TIMESTAMP)
        """,
        ("production" if ERP_PRODUCTION_MODE else "development",),
    )


def _mark_database_startup_identity(conn):
    _ensure_database_identity_table(conn)
    conn.execute(
        """
        UPDATE database_identity
        SET last_startup_at = CURRENT_TIMESTAMP,
            last_verified_at = CURRENT_TIMESTAMP,
            schema_version = COALESCE((SELECT MAX(version) FROM schema_version), schema_version, 0),
            backend_label = COALESCE(NULLIF(backend_label, ''), 'SQLite'),
            environment_label = ?
        """,
        ("production" if ERP_PRODUCTION_MODE else "development",),
    )


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def is_database_valid(db_path=DB_PATH, logger_instance=None):
    logger_instance = logger_instance or logger
    if not db_path or not os.path.exists(db_path):
        return False
    if not is_sqlite_file(db_path):
        return False
    conn = None
    try:
        conn = _open_sqlite_connection(path=db_path)
        required_tables = set(DATABASE_REQUIRED_TABLES)
        existing_tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        if not required_tables.issubset(existing_tables):
            return False
        company_columns = {row[1] for row in conn.execute("PRAGMA table_info(companies)").fetchall()}
        if "key" not in company_columns or "name" not in company_columns:
            return False
        return True
    except sqlite3.Error as exc:
        logger_instance.warning("Database validity check failed for %s: %s", db_path, exc)
        return False
    finally:
        if conn:
            conn.close()


def get_database_company_count(db_path=DB_PATH, logger_instance=None):
    logger_instance = logger_instance or logger
    if not db_path or not os.path.exists(db_path):
        return 0
    conn = None
    try:
        conn = _open_sqlite_connection(path=db_path)
        if not _table_exists(conn, "companies"):
            return 0
        row = conn.execute("SELECT COUNT(*) AS company_count FROM companies").fetchone()
        return int(row["company_count"] or 0) if row else 0
    except sqlite3.Error as exc:
        logger_instance.warning("Database company count check failed for %s: %s", db_path, exc)
        return 0
    finally:
        if conn:
            conn.close()


def get_database_production_readiness_report(db_path=DB_PATH, logger_instance=None):
    logger_instance = logger_instance or logger
    report = {
        "db_path": db_path,
        "backend": "SQLite",
        "file_size_bytes": os.path.getsize(db_path) if db_path and os.path.exists(db_path) and os.path.isfile(db_path) else 0,
        "file_exists": bool(db_path and os.path.exists(db_path)),
        "sqlite_open_success": False,
        "structural_valid": False,
        "production_ready": False,
        "company_count": 0,
        "database_uuid": None,
        "schema_version": 0,
        "database_created_at": None,
        "last_startup_at": None,
        "backend_label": None,
        "environment_label": None,
        "required_tables_exist": False,
        "missing_tables": [],
        "companies_table_exists": False,
        "database_identity_exists": False,
        "schema_version_exists": False,
        "failures": [],
    }
    if not report["file_exists"]:
        report["failures"].append("database file is missing")
        return report
    if not is_sqlite_file(db_path):
        report["failures"].append("database file is not a valid SQLite file")
        return report
    report["structural_valid"] = is_database_valid(db_path=db_path, logger_instance=logger_instance)
    if not report["structural_valid"]:
        report["failures"].append("required structural tables or columns are missing")
        return report
    conn = None
    try:
        conn = _open_sqlite_connection(path=db_path)
        report["sqlite_open_success"] = True
        required_tables = set(DATABASE_PRODUCTION_REQUIRED_TABLES)
        existing_tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        report["companies_table_exists"] = "companies" in existing_tables
        report["database_identity_exists"] = "database_identity" in existing_tables
        report["schema_version_exists"] = "schema_version" in existing_tables
        missing_tables = sorted(required_tables.difference(existing_tables))
        report["missing_tables"] = missing_tables
        report["required_tables_exist"] = not missing_tables
        if missing_tables:
            report["failures"].append(f"missing required production tables: {', '.join(missing_tables)}")
        report["company_count"] = get_database_company_count(db_path=db_path, logger_instance=logger_instance)
        if "database_identity" in existing_tables:
            identity_row = conn.execute(
                """
                SELECT instance_id, created_at, last_verified_at, schema_version,
                       last_startup_at, backend_label, environment_label
                FROM database_identity
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if identity_row:
                report["database_uuid"] = identity_row["instance_id"]
                report["database_created_at"] = identity_row["created_at"]
                report["schema_version"] = int(identity_row["schema_version"] or 0)
                report["last_startup_at"] = identity_row["last_startup_at"] or identity_row["last_verified_at"]
                report["backend_label"] = identity_row["backend_label"]
                report["environment_label"] = identity_row["environment_label"]
        if "schema_version" in existing_tables:
            version_row = conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_version").fetchone()
            report["schema_version"] = max(int(report["schema_version"] or 0), int(version_row["version"] or 0))
        if report["company_count"] <= 0:
            report["failures"].append("companies table has no deployed company rows")
        report["production_ready"] = not report["failures"]
        return report
    except sqlite3.Error as exc:
        logger_instance.warning("Database production readiness report failed for %s: %s", db_path, exc)
        report["failures"].append(str(exc))
        return report
    finally:
        if conn:
            conn.close()


def is_database_ready_for_production(db_path=DB_PATH, logger_instance=None):
    report = get_database_production_readiness_report(db_path=db_path, logger_instance=logger_instance)
    return bool(report["production_ready"])


def is_database_production_ready(db_path=DB_PATH, logger_instance=None):
    return is_database_ready_for_production(db_path=db_path, logger_instance=logger_instance)


def get_database_health_snapshot(db_path=DB_PATH, logger_instance=None):
    report = get_database_production_readiness_report(db_path=db_path, logger_instance=logger_instance)
    return {
        "db_path": db_path,
        "backend": report["backend"],
        "file_size_bytes": report["file_size_bytes"],
        "file_exists": report["file_exists"],
        "sqlite_open_success": report["sqlite_open_success"],
        "structural_valid": report["structural_valid"],
        "production_ready": report["production_ready"],
        "company_count": report["company_count"],
        "database_uuid": report["database_uuid"],
        "schema_version": report["schema_version"],
        "database_created_at": report["database_created_at"],
        "last_startup_at": report["last_startup_at"],
        "backend_label": report["backend_label"],
        "environment_label": report["environment_label"],
        "required_tables_exist": report["required_tables_exist"],
        "missing_tables": report["missing_tables"],
        "companies_table_exists": report["companies_table_exists"],
        "database_identity_exists": report["database_identity_exists"],
        "schema_version_exists": report["schema_version_exists"],
        "readiness_failures": report["failures"],
    }


def _is_bootstrap_candidate(health_snapshot):
    health_snapshot = health_snapshot or {}
    return all(
        [
            bool(health_snapshot.get("file_exists")),
            bool(health_snapshot.get("sqlite_open_success")),
            bool(health_snapshot.get("structural_valid")),
            bool(health_snapshot.get("required_tables_exist")),
            bool(health_snapshot.get("companies_table_exists")),
            bool(health_snapshot.get("database_identity_exists")),
            bool(health_snapshot.get("schema_version_exists")),
            int(health_snapshot.get("company_count") or 0) == 0,
        ]
    )


def _is_empty_local_db_recovery_candidate(health_snapshot):
    health_snapshot = health_snapshot or {}
    return all(
        [
            bool(health_snapshot.get("file_exists")),
            bool(health_snapshot.get("sqlite_open_success")),
            bool(health_snapshot.get("structural_valid")),
            bool(health_snapshot.get("companies_table_exists")),
            int(health_snapshot.get("company_count") or 0) == 0,
        ]
    )


def _build_startup_result(
    ok,
    stage,
    reason,
    db_path=DB_PATH,
    file_exists=False,
    structurally_valid=False,
    production_ready=False,
    company_count=0,
    recovery_attempted=False,
    recovery_succeeded=False,
    bootstrap_needed=False,
    startup_mode=None,
    cloud_backup_company_count=None,
    restore_source=None,
    cloud_backup_object=None,
    runtime_mode=None,
    test_mode=False,
    restore_skipped_due_to_test_mode=False,
    restore_skipped_reason=None,
):
    final_startup_mode = startup_mode or stage
    test_mode_final = bool(test_mode or is_test_runtime())
    runtime_mode_final = runtime_mode or get_runtime_mode()
    return {
        "ok": bool(ok),
        "stage": str(stage),
        "reason": str(reason),
        "startup_mode": str(final_startup_mode),
        "db_path": db_path,
        "file_exists": bool(file_exists),
        "structurally_valid": bool(structurally_valid),
        "production_ready": bool(production_ready),
        "company_count": int(company_count or 0),
        "cloud_backup_company_count": cloud_backup_company_count,
        "recovery_attempted": bool(recovery_attempted),
        "recovery_succeeded": bool(recovery_succeeded),
        "bootstrap_needed": bool(bootstrap_needed),
        "restore_source": restore_source,
        "cloud_backup_object": cloud_backup_object,
        "runtime_mode": runtime_mode_final,
        "test_mode": test_mode_final,
        "restore_skipped_due_to_test_mode": bool(restore_skipped_due_to_test_mode),
        "restore_skipped_reason": restore_skipped_reason,
    }


def attempt_production_database_recovery(force_restore=True):
    global LAST_CLOUD_RESTORE_SKIP_REASON
    LAST_CLOUD_RESTORE_SKIP_REASON = None
    logger.info("Trusted backup recovery invoked: db_path=%s force_restore=%s", DB_PATH, force_restore)
    if is_test_runtime() and not is_test_cloud_restore_allowed():
        skip_reason = "cloud recovery is disabled during automated tests"
        LAST_CLOUD_RESTORE_SKIP_REASON = skip_reason
        logger.warning(skip_reason)
        return {
            "ok": False,
            "stage": "recovery_disabled_in_tests",
            "reason": skip_reason,
            "backend": "firebase_storage",
            "bucket_name": None,
            "object_name": None,
            "recovery_source_found": False,
            "temp_download_succeeded": False,
            "replacement_performed": False,
            "health": get_database_health_snapshot(DB_PATH, logger_instance=logger),
            "validation_attempts": [],
            "restore_skipped_reason": skip_reason,
        }
    local_health = get_database_health_snapshot(DB_PATH, logger_instance=logger)
    diagnostics = get_recovery_source_diagnostics()
    logger.info(
        "Trusted recovery source diagnostics: backend=%s credentials_loaded=%s credentials_source=%s firebase_key_exists=%s database_url_configured=%s bucket=%s object=%s",
        diagnostics["backend"],
        diagnostics["credentials_loaded"],
        diagnostics["credentials_source"],
        diagnostics["firebase_key_exists"],
        diagnostics["database_url_configured"],
        diagnostics["bucket_name"] or "missing",
        diagnostics["object_name"] or "missing",
    )
    if local_health["production_ready"] and not force_restore:
        logger.info("Trusted backup recovery skipped because local database is already production-ready: %s", DB_PATH)
        return {
            "ok": False,
            "stage": "recovery_skipped",
            "reason": "local database is already production-ready",
            "backend": diagnostics["backend"],
            "bucket_name": diagnostics["bucket_name"],
            "object_name": diagnostics["object_name"],
            "recovery_source_found": None,
            "temp_download_succeeded": False,
            "replacement_performed": False,
            "health": local_health,
        }
    restore_result = restore_latest_cloud_backup_to_local(
        logger_instance=logger,
        explicit_recovery_mode=force_restore,
    )
    return {
        "ok": bool(restore_result.get("ok")),
        "stage": restore_result.get("stage") or "recovery_validation",
        "reason": restore_result.get("reason") or "cloud restore did not complete",
        "backend": diagnostics["backend"],
        "bucket_name": restore_result.get("bucket_name", diagnostics["bucket_name"]),
        "object_name": restore_result.get("object_name", diagnostics["object_name"]),
        "recovery_source_found": bool(
            restore_result.get("selected_object_path")
            or restore_result.get("selected_source_type")
            or restore_result.get("temp_download_succeeded")
        ),
        "temp_download_succeeded": bool(restore_result.get("temp_download_succeeded")),
        "replacement_performed": bool(restore_result.get("replacement_performed")),
        "health": restore_result.get("health") or local_health,
        "selected_source_type": restore_result.get("selected_source_type"),
        "selected_object_path": restore_result.get("selected_object_path"),
        "validation_attempts": restore_result.get("validation_attempts") or [],
        "pre_restore_backup_path": restore_result.get("pre_restore_backup_path"),
        "company_count": restore_result.get("company_count"),
    }


def _get_schema_version(conn):
    _ensure_migration_metadata_tables(conn)
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_version").fetchone()
    return int(row["version"] or 0) if row else 0


def _log_migration_event(
    conn,
    version,
    description,
    status,
    backup_path=None,
    before_counts=None,
    after_counts=None,
    details=None,
):
    before_counts = before_counts or {}
    after_counts = after_counts or {}
    conn.execute(
        """
        INSERT INTO migration_logs (
            version,
            description,
            status,
            backup_path,
            company_count_before,
            company_count_after,
            row_counts_before,
            row_counts_after,
            details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version,
            description,
            status,
            backup_path,
            int(before_counts.get("companies", 0)),
            int(after_counts.get("companies", 0)),
            str(before_counts),
            str(after_counts),
            details,
        ),
    )


def _record_schema_version(conn, version, description):
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version, description) VALUES (?, ?)",
        (version, description),
    )


def _snapshot_critical_row_counts(conn):
    return collect_row_counts(conn, CRITICAL_VALIDATION_TABLES)


def _format_count_drop_message(count_failures):
    return "; ".join(
        f"{table_name}: before={before_count}, after={after_count}"
        for table_name, before_count, after_count in count_failures
    )


def repair_database_schema():
    """
    Lightweight startup repair that restores critical columns needed for app boot.
    Safe to call repeatedly and does not remove existing tables or data.
    """
    conn = None
    try:
        _ensure_local_db_file()
        conn = _open_sqlite_connection()
        _run_lightweight_integrity_checks(conn)
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("Startup schema repair skipped: %s", sanitize_error_message(exc))
    finally:
        if conn:
            conn.close()


def ensure_database_integrity():
    """Compatibility wrapper for startup safety checks."""
    return startup_database()


def ensure_schema_integrity(conn):
    """Protect critical columns during upgrades to avoid missing-column crashes."""
    cursor = conn.cursor()
    critical_columns = {
        "companies": {
            "contact_email": "TEXT",
            "barcode_input_source": "TEXT DEFAULT 'Keyboard Entry'",
            "subscription_expiry": "TEXT",
            "deployment_status": "TEXT DEFAULT 'Pending'",
            "phone_number": "TEXT",
            "physical_address": "TEXT",
            "industry": "TEXT",
            "currency": "TEXT DEFAULT 'GHS'",
            "logo_url": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        },
        "audit_logs": {
            "details": "TEXT",
            "branch_id": "TEXT",
            "action_type": "TEXT",
            "document_ref": "TEXT",
            "before_after_summary": "TEXT",
            "event_id": "TEXT",
        },
        "system_logs": {"timestamp": "TEXT", "level": "TEXT", "module_name": "TEXT", "message": "TEXT"},
        "customers": {"customer_id": "TEXT", "current_balance": "REAL DEFAULT 0"},
        "customer_transactions": {"branch_id": "TEXT", "reference": "TEXT", "created_by": "TEXT", "transaction_date": "TEXT"},
        "supplier_transactions": {"reference": "TEXT", "created_by": "TEXT", "transaction_date": "TEXT"},
        "journal_entries": {
            "branch_id": "TEXT",
            "customer_id": "INTEGER",
            "supplier_id": "INTEGER",
            "inventory_item_id": "INTEGER",
            "payment_id": "INTEGER",
            "source_module": "TEXT",
            "source_table": "TEXT",
            "source_type": "TEXT",
            "source_id": "INTEGER",
            "source_document_type": "TEXT",
            "source_document_id": "INTEGER",
            "document_type": "TEXT",
            "document_number": "TEXT",
            "posted_at": "TIMESTAMP",
            "posted_by": "TEXT",
            "reversed_entry_id": "INTEGER",
            "is_voided": "INTEGER DEFAULT 0",
            "voided_at": "TIMESTAMP",
            "voided_by": "TEXT",
            "approval_status": "TEXT DEFAULT 'Posted'",
        },
        "stock_movements": {"branch_id": "TEXT", "reason": "TEXT", "created_by": "TEXT", "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "status": "TEXT DEFAULT 'Draft'", "approval_status": "TEXT DEFAULT 'Draft'", "posted_entry_id": "INTEGER", "last_journal_sync_at": "TIMESTAMP", "submitted_at": "TIMESTAMP", "approved_at": "TIMESTAMP", "approved_by": "TEXT", "cancelled_at": "TIMESTAMP", "cancelled_by": "TEXT"},
        "transactions": {"branch_id": "TEXT"},
        "users": {"branch_id": "TEXT"},
        "vouchers": {"status": "TEXT DEFAULT 'Draft'", "branch_id": "TEXT", "approval_status": "TEXT DEFAULT 'Draft'", "is_voided": "INTEGER DEFAULT 0", "voided_at": "TIMESTAMP", "voided_by": "TEXT", "submitted_at": "TIMESTAMP", "approved_at": "TIMESTAMP", "approved_by": "TEXT", "posted_entry_id": "INTEGER", "last_journal_sync_at": "TIMESTAMP"},
        "payroll": {
            "status": "TEXT DEFAULT 'Active'",
            "payment_method": "TEXT",
            "approval_status": "TEXT DEFAULT 'Posted'",
            "approved_at": "TIMESTAMP",
            "approved_by": "TEXT",
            "posted_entry_id": "INTEGER",
            "last_journal_sync_at": "TIMESTAMP",
            "created_by": "TEXT",
        },
        "inventory": {"opening_balance": "REAL DEFAULT 0", "barcode": "TEXT", "inventory_account_id": "INTEGER", "cogs_account_id": "INTEGER"},
        "invoices": {"invoice_number": "TEXT", "input_vat": "REAL DEFAULT 0", "output_vat": "REAL DEFAULT 0", "approval_status": "TEXT DEFAULT 'Draft'", "submitted_at": "TIMESTAMP", "approved_at": "TIMESTAMP", "approved_by": "TEXT", "cancelled_at": "TIMESTAMP", "cancelled_by": "TEXT", "posted_entry_id": "INTEGER", "last_journal_sync_at": "TIMESTAMP"},
        "bills": {"bill_number": "TEXT", "input_vat": "REAL DEFAULT 0", "output_vat": "REAL DEFAULT 0", "approval_status": "TEXT DEFAULT 'Draft'", "submitted_at": "TIMESTAMP", "approved_at": "TIMESTAMP", "approved_by": "TEXT", "cancelled_at": "TIMESTAMP", "cancelled_by": "TEXT", "posted_entry_id": "INTEGER", "last_journal_sync_at": "TIMESTAMP"},
        "payments": {"status": "TEXT DEFAULT 'Draft'", "invoice_id": "INTEGER", "bill_id": "INTEGER", "bank_account_id": "INTEGER", "approval_status": "TEXT DEFAULT 'Draft'", "submitted_at": "TIMESTAMP", "approved_at": "TIMESTAMP", "approved_by": "TEXT", "cancelled_at": "TIMESTAMP", "cancelled_by": "TEXT", "posted_entry_id": "INTEGER", "last_journal_sync_at": "TIMESTAMP"},
        "bank_accounts": {"company_key": "TEXT", "branch_id": "TEXT", "account_name": "TEXT", "account_number": "TEXT", "bank_name": "TEXT", "currency": "TEXT DEFAULT 'GHS'", "account_type": "TEXT", "balance": "REAL DEFAULT 0", "created_by": "TEXT", "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
        "payment_allocations": {"company_key": "TEXT", "payment_id": "INTEGER", "invoice_id": "INTEGER", "bill_id": "INTEGER", "amount": "REAL DEFAULT 0", "currency": "TEXT DEFAULT 'GHS'", "branch_id": "TEXT", "created_by": "TEXT", "allocated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
        "recurring_transactions": {"company_key": "TEXT", "branch_id": "TEXT", "description": "TEXT", "frequency": "TEXT", "next_run_date": "TEXT", "last_run_at": "TIMESTAMP", "is_active": "INTEGER DEFAULT 1", "created_by": "TEXT", "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "source_module": "TEXT", "source_table": "TEXT", "source_id": "INTEGER", "recurrence_payload": "TEXT"},
        "accounting_periods": {"status": "TEXT DEFAULT 'Open'", "closed_at": "TIMESTAMP", "closed_by": "TEXT", "reopened_at": "TIMESTAMP", "reopened_by": "TEXT"},
        "branches": {"contact_number": "TEXT", "branch_manager": "TEXT", "branch_access_key": "TEXT"},
        "fixed_assets": FIXED_ASSET_SCHEMA_COLUMN_DEFS,
        "suppliers": {"address": "TEXT", "category": "TEXT", "currency": "TEXT DEFAULT 'GHS'", "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
    }

    cursor.execute(
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
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS license_payment_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT UNIQUE,
            company_key TEXT,
            company_name TEXT,
            payer_email TEXT,
            payment_context TEXT DEFAULT 'license_activation',
            expected_amount INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            status TEXT DEFAULT 'initialized',
            authorization_url TEXT,
            callback_url TEXT,
            metadata_json TEXT,
            gateway_status_summary TEXT,
            paid_at TIMESTAMP,
            verified_at TIMESTAMP,
            activated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_subscription_billing_schema(cursor)

    for table_name, columns in critical_columns.items():
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        )
        if not cursor.fetchone():
            continue
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column_name, column_def in columns.items():
            if column_name not in existing_columns:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")

    cursor.execute("PRAGMA table_info(license_payment_transactions)")
    license_payment_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_def in {
        "company_key": "TEXT",
        "company_name": "TEXT",
        "payer_email": "TEXT",
        "payment_context": "TEXT DEFAULT 'license_activation'",
        "expected_amount": "INTEGER DEFAULT 0",
        "currency": "TEXT DEFAULT 'GHS'",
        "status": "TEXT DEFAULT 'initialized'",
        "authorization_url": "TEXT",
        "callback_url": "TEXT",
        "metadata_json": "TEXT",
        "gateway_status_summary": "TEXT",
        "paid_at": "TIMESTAMP",
        "verified_at": "TIMESTAMP",
        "activated_at": "TIMESTAMP",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }.items():
        if column_name not in license_payment_columns:
            cursor.execute(f"ALTER TABLE license_payment_transactions ADD COLUMN {column_name} {column_def}")

    # Specific check for journal_entries branch_id on databases where the table already exists.
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = 'journal_entries'"
    )
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(journal_entries)")
        je_columns = {row[1] for row in cursor.fetchall()}
        if "branch_id" not in je_columns:
            cursor.execute("ALTER TABLE journal_entries ADD COLUMN branch_id TEXT")

    safe_indexes = (
        ("audit_logs", "CREATE INDEX IF NOT EXISTS idx_audit_logs_company_timestamp ON audit_logs(company_key, timestamp DESC)"),
        ("audit_logs", "CREATE INDEX IF NOT EXISTS idx_audit_logs_action_type ON audit_logs(action_type)"),
        ("journal_entries", "CREATE INDEX IF NOT EXISTS idx_journal_entries_reporting ON journal_entries(company_key, approval_status, is_voided, date)"),
        ("journal_entries", "CREATE INDEX IF NOT EXISTS idx_journal_entries_source ON journal_entries(company_key, source_table, source_id)"),
        ("journal_entries", "CREATE INDEX IF NOT EXISTS idx_journal_entries_customer ON journal_entries(company_key, customer_id, date)"),
        ("journal_entries", "CREATE INDEX IF NOT EXISTS idx_journal_entries_supplier ON journal_entries(company_key, supplier_id, date)"),
        ("invoices", "CREATE INDEX IF NOT EXISTS idx_invoices_company_status ON invoices(company_key, approval_status, invoice_date)"),
        ("bills", "CREATE INDEX IF NOT EXISTS idx_bills_company_status ON bills(company_key, approval_status, bill_date)"),
        ("payments", "CREATE INDEX IF NOT EXISTS idx_payments_company_status ON payments(company_key, approval_status, payment_date)"),
        ("accounting_periods", "CREATE INDEX IF NOT EXISTS idx_accounting_periods_company_status ON accounting_periods(company_key, status, is_locked)"),
    )
    existing_tables = {
        row[0]
        for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    for table_name, index_sql in safe_indexes:
        if table_name not in existing_tables:
            logger.info(
                "Enterprise index creation deferred: table '%s' does not exist yet during schema integrity pass.",
                table_name,
            )
            continue
        try:
            cursor.execute(index_sql)
        except sqlite3.Error as index_error:
            logger.warning("Enterprise index creation skipped for table '%s': %s", table_name, sanitize_error_message(index_error))
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_license_payment_transactions_company_status ON license_payment_transactions(company_key, status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_license_payment_transactions_verified_at ON license_payment_transactions(verified_at)"
    )

    cursor.execute("PRAGMA table_info(stock)")
    stock_columns = {row[1] for row in cursor.fetchall()}
    if stock_columns and "barcode" not in stock_columns:
        cursor.execute("ALTER TABLE stock ADD COLUMN barcode TEXT")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chart_of_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            parent_id INTEGER,
            category TEXT,
            account_code TEXT,
            account_name TEXT,
            account_type TEXT,
            FOREIGN KEY (parent_id) REFERENCES chart_of_accounts(id)
        )
        """
    )
    cursor.execute("PRAGMA table_info(chart_of_accounts)")
    coa_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_def in {
        "name": "TEXT",
        "type": "TEXT",
        "parent_id": "INTEGER",
        "code": "TEXT",
        "category": "TEXT",
        "account_code": "TEXT",
        "account_name": "TEXT",
        "account_type": "TEXT",
        "posting_allowed": "INTEGER DEFAULT 1",
        "control_account": "INTEGER DEFAULT 0",
        "allow_manual_posting": "INTEGER DEFAULT 1",
        "is_active": "INTEGER DEFAULT 1",
    }.items():
        if column_name not in coa_columns:
            cursor.execute(f"ALTER TABLE chart_of_accounts ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        """
        UPDATE chart_of_accounts
        SET name = COALESCE(NULLIF(name, ''), account_name),
            code = COALESCE(NULLIF(code, ''), NULLIF(account_code, '')),
            type = COALESCE(NULLIF(type, ''), NULLIF(account_type, ''), NULLIF(category, ''), 'Asset'),
            category = COALESCE(NULLIF(category, ''), NULLIF(type, ''), account_type),
            account_name = COALESCE(NULLIF(account_name, ''), name),
            account_type = COALESCE(NULLIF(account_type, ''), NULLIF(type, ''), category),
            posting_allowed = COALESCE(posting_allowed, 1),
            control_account = COALESCE(control_account, 0),
            allow_manual_posting = COALESCE(allow_manual_posting, 1),
            is_active = COALESCE(is_active, 1)
        """
    )
    existing_accounts = {
        str(row["name"]).strip().lower(): dict(row)
        for row in cursor.execute("SELECT id, name, type FROM chart_of_accounts").fetchall()
        if row["name"]
    }
    for account_name, account_type, parent_name in IFRS_CHART_OF_ACCOUNTS:
        existing = existing_accounts.get(account_name.lower())
        if existing:
            cursor.execute(
                """
                UPDATE chart_of_accounts
                SET type = ?, category = ?, account_name = COALESCE(NULLIF(account_name, ''), ?),
                    account_type = COALESCE(NULLIF(account_type, ''), ?)
                WHERE id = ?
                """,
                (account_type, account_type, account_name, account_type, existing["id"]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO chart_of_accounts (name, type, category, account_name, account_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (account_name, account_type, account_type, account_name, account_type),
            )
    chart_rows = cursor.execute("SELECT id, name FROM chart_of_accounts").fetchall()
    chart_ids = {str(row['name']).strip().lower(): row['id'] for row in chart_rows if row['name']}
    for account_name, _account_type, parent_name in IFRS_CHART_OF_ACCOUNTS:
        parent_id = chart_ids.get(str(parent_name).strip().lower()) if parent_name else None
        cursor.execute(
            "UPDATE chart_of_accounts SET parent_id = ? WHERE lower(name) = lower(?)",
            (parent_id, account_name),
        )
    cursor.execute(
        """
        UPDATE chart_of_accounts
        SET account_code = COALESCE(NULLIF(account_code, ''), NULLIF(code, '')),
            code = COALESCE(NULLIF(code, ''), NULLIF(account_code, ''))
        """
    )
    header_account_names = sorted(
        {
            str(parent_name).strip()
            for _account_name, _account_type, parent_name in IFRS_CHART_OF_ACCOUNTS
            if parent_name
        }
    )
    for header_name in header_account_names:
        cursor.execute(
            """
            UPDATE chart_of_accounts
            SET posting_allowed = 0
            WHERE lower(COALESCE(NULLIF(name, ''), NULLIF(account_name, ''), '')) = lower(?)
            """,
            (header_name,),
        )
    for control_name in ("Accounts Receivable", "Accounts Payable", "Inventory"):
        cursor.execute(
            """
            UPDATE chart_of_accounts
            SET control_account = 1,
                allow_manual_posting = 0,
                posting_allowed = 1,
                is_active = COALESCE(is_active, 1)
            WHERE lower(COALESCE(NULLIF(name, ''), NULLIF(account_name, ''), '')) = lower(?)
            """,
            (control_name,),
        )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chart_of_accounts_parent_id ON chart_of_accounts(parent_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chart_of_accounts_active ON chart_of_accounts(is_active)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chart_of_accounts_control_account ON chart_of_accounts(control_account)"
    )
    try:
        duplicate_code_rows = cursor.execute(
            """
            SELECT account_code
            FROM chart_of_accounts
            WHERE TRIM(COALESCE(account_code, '')) != ''
            GROUP BY account_code
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        if duplicate_code_rows:
            logger.warning(
                "Chart of accounts unique code hardening skipped because duplicate account codes already exist: %s",
                ", ".join(str(row[0]) for row in duplicate_code_rows),
            )
        else:
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_chart_of_accounts_account_code_unique
                ON chart_of_accounts(account_code)
                WHERE account_code IS NOT NULL AND TRIM(account_code) != ''
                """
            )
    except sqlite3.Error as exc:
        logger.warning("Chart of accounts unique code hardening could not be applied safely: %s", sanitize_error_message(exc))

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY,
            master_price_per_month REAL DEFAULT 500,
            base_currency TEXT DEFAULT 'GHS',
            display_currency TEXT DEFAULT 'GHS',
            exchange_rate REAL DEFAULT 1.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    cursor.execute("PRAGMA table_info(system_settings)")
    existing_system_columns = {row[1] for row in cursor.fetchall()}
    if existing_system_columns:
        if "base_currency" not in existing_system_columns:
            cursor.execute("ALTER TABLE system_settings ADD COLUMN base_currency TEXT DEFAULT 'GHS'")
        if "display_currency" not in existing_system_columns:
            cursor.execute("ALTER TABLE system_settings ADD COLUMN display_currency TEXT DEFAULT 'GHS'")
        if "exchange_rate" not in existing_system_columns:
            cursor.execute("ALTER TABLE system_settings ADD COLUMN exchange_rate REAL DEFAULT 1.0")
    cursor.execute(
        "INSERT OR IGNORE INTO system_settings (id, master_price_per_month, base_currency, display_currency, exchange_rate) VALUES (1, 500, 'GHS', 'GHS', 1.0)"
    )
    # Additive ERP migrations live here so upgrades stay idempotent and non-destructive.
    run_foundation_migrations(conn, logger=logger)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            reference TEXT,
            created_by TEXT,
            branch_id TEXT,
            customer_id INTEGER,
            supplier_id INTEGER,
            inventory_item_id INTEGER,
            payment_id INTEGER,
            source_module TEXT,
            source_table TEXT,
            source_type TEXT,
            source_id INTEGER,
            source_document_type TEXT,
            source_document_id INTEGER,
            document_type TEXT,
            document_number TEXT,
            posted_at TIMESTAMP,
            posted_by TEXT,
            reversed_entry_id INTEGER,
            is_voided INTEGER DEFAULT 0,
            voided_at TIMESTAMP,
            voided_by TEXT,
            approval_status TEXT DEFAULT 'Posted',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("PRAGMA table_info(journal_entries)")
    journal_entry_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_def in {
        "company_key": "TEXT",
        "date": "TEXT",
        "description": "TEXT",
        "reference": "TEXT",
        "created_by": "TEXT",
        "customer_id": "INTEGER",
        "supplier_id": "INTEGER",
        "inventory_item_id": "INTEGER",
        "payment_id": "INTEGER",
        "source_module": "TEXT",
        "source_table": "TEXT",
        "source_type": "TEXT",
        "source_id": "INTEGER",
        "source_document_type": "TEXT",
        "source_document_id": "INTEGER",
        "document_type": "TEXT",
        "document_number": "TEXT",
        "posted_at": "TIMESTAMP",
        "posted_by": "TEXT",
        "reversed_entry_id": "INTEGER",
        "is_voided": "INTEGER DEFAULT 0",
        "voided_at": "TIMESTAMP",
        "voided_by": "TEXT",
        "approval_status": "TEXT DEFAULT 'Posted'",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }.items():
        if column_name not in journal_entry_columns:
            cursor.execute(f"ALTER TABLE journal_entries ADD COLUMN {column_name} {column_def}")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            FOREIGN KEY (entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
            FOREIGN KEY (account_id) REFERENCES chart_of_accounts(id)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_entries_company_date ON journal_entries(company_key, date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_lines_entry ON journal_lines(entry_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_lines_entry_account ON journal_lines(entry_id, account_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chart_of_accounts_type ON chart_of_accounts(type)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT,
            inventory_item_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            movement_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            reason TEXT,
            previous_qty REAL DEFAULT 0,
            new_qty REAL DEFAULT 0,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory(id) ON DELETE CASCADE,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_company_created ON stock_movements(company_key, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_item ON stock_movements(inventory_item_id)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            customer_id TEXT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            current_balance REAL DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_key, name)
        )
        """
    )
    cursor.execute("PRAGMA table_info(customers)")
    customer_columns = {row[1] for row in cursor.fetchall()}
    customer_column_defs = {
        "company_key": "TEXT",
        "customer_id": "TEXT",
        "name": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "address": "TEXT",
        "current_balance": "REAL DEFAULT 0",
        "currency": "TEXT DEFAULT 'GHS'",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_def in customer_column_defs.items():
        if column_name not in customer_columns:
            cursor.execute(f"ALTER TABLE customers ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        """
        UPDATE customers
        SET customer_id = COALESCE(NULLIF(customer_id, ''), printf('CUST-%06d', id)),
            current_balance = COALESCE(current_balance, 0)
        """
    )
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_company_customer_id ON customers(company_key, customer_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_company_name ON customers(company_key, name)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            customer_id INTEGER NOT NULL,
            branch_id TEXT,
            transaction_type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            reference TEXT,
            transaction_date TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customer_transactions_customer_date ON customer_transactions(customer_id, transaction_date DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customer_transactions_company_date ON customer_transactions(company_key, transaction_date DESC)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            category TEXT,
            currency TEXT DEFAULT 'GHS',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_key, name)
        )
        """
    )
    cursor.execute("PRAGMA table_info(suppliers)")
    supplier_columns = {row[1] for row in cursor.fetchall()}
    supplier_column_defs = {
        "company_key": "TEXT",
        "name": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "address": "TEXT",
        "category": "TEXT",
        "currency": "TEXT DEFAULT 'GHS'",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_def in supplier_column_defs.items():
        if column_name not in supplier_columns:
            cursor.execute(f"ALTER TABLE suppliers ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS supplier_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            supplier_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            reference TEXT,
            transaction_date TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_supplier_transactions_supplier_date ON supplier_transactions(supplier_id, transaction_date DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_supplier_transactions_company_date ON supplier_transactions(company_key, transaction_date DESC)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            customer_id INTEGER,
            invoice_number TEXT,
            invoice_date TEXT NOT NULL,
            due_date TEXT,
            status TEXT DEFAULT 'Draft',
            approval_status TEXT DEFAULT 'Draft',
            submitted_at TIMESTAMP,
            approved_at TIMESTAMP,
            approved_by TEXT,
            cancelled_at TIMESTAMP,
            cancelled_by TEXT,
            posted_entry_id INTEGER,
            last_journal_sync_at TIMESTAMP,
            amount REAL DEFAULT 0,
            input_vat REAL DEFAULT 0,
            output_vat REAL DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            description TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
        """
    )
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_company_invoice_number ON invoices(company_key, invoice_number)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            supplier_id INTEGER,
            bill_number TEXT,
            bill_date TEXT NOT NULL,
            due_date TEXT,
            status TEXT DEFAULT 'Draft',
            approval_status TEXT DEFAULT 'Draft',
            submitted_at TIMESTAMP,
            approved_at TIMESTAMP,
            approved_by TEXT,
            cancelled_at TIMESTAMP,
            cancelled_by TEXT,
            posted_entry_id INTEGER,
            last_journal_sync_at TIMESTAMP,
            amount REAL DEFAULT 0,
            input_vat REAL DEFAULT 0,
            output_vat REAL DEFAULT 0,
            purchase_classification TEXT DEFAULT 'Inventory Purchase',
            payment_method TEXT,
            expense_account_name TEXT,
            asset_name TEXT,
            asset_category TEXT,
            currency TEXT DEFAULT 'GHS',
            description TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
        """
    )
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bills_company_bill_number ON bills(company_key, bill_number)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            inventory_item_id INTEGER,
            item_name TEXT NOT NULL,
            quantity REAL DEFAULT 1,
            unit_price REAL DEFAULT 0,
            line_total REAL DEFAULT 0,
            cost_price REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice_id ON invoice_lines(invoice_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoice_lines_inventory_item_id ON invoice_lines(inventory_item_id)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bill_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            quantity REAL DEFAULT 1,
            unit_price REAL DEFAULT 0,
            line_total REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bill_lines_bill_id ON bill_lines(bill_id)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT,
            account_name TEXT NOT NULL,
            account_number TEXT,
            bank_name TEXT,
            account_type TEXT DEFAULT 'Bank',
            currency TEXT DEFAULT 'GHS',
            balance REAL DEFAULT 0,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_accounts_company ON bank_accounts(company_key)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            payment_date TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            status TEXT DEFAULT 'Draft',
            customer_id INTEGER,
            supplier_id INTEGER,
            invoice_id INTEGER,
            bill_id INTEGER,
            bank_account_id INTEGER,
            amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            method TEXT,
            reference TEXT,
            approval_status TEXT DEFAULT 'Draft',
            submitted_at TIMESTAMP,
            approved_at TIMESTAMP,
            approved_by TEXT,
            cancelled_at TIMESTAMP,
            cancelled_by TEXT,
            posted_entry_id INTEGER,
            last_journal_sync_at TIMESTAMP,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bank_account_id) REFERENCES bank_accounts(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            payment_id INTEGER NOT NULL,
            invoice_id INTEGER,
            bill_id INTEGER,
            amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            branch_id TEXT,
            created_by TEXT,
            allocated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (payment_id) REFERENCES payments(id) ON DELETE CASCADE,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_allocations_payment ON payment_allocations(payment_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_allocations_invoice ON payment_allocations(invoice_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_allocations_bill ON payment_allocations(bill_id)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recurring_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT,
            description TEXT NOT NULL,
            frequency TEXT NOT NULL,
            amount REAL DEFAULT 0,
            next_run_date TEXT NOT NULL,
            last_run_at TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            source_module TEXT,
            source_table TEXT,
            source_id INTEGER,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            recurrence_payload TEXT,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recurring_transactions_company ON recurring_transactions(company_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recurring_transactions_next_run ON recurring_transactions(next_run_date)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            payroll_id INTEGER,
            period_start TEXT,
            period_end TEXT,
            employee_name TEXT NOT NULL,
            gross_pay REAL DEFAULT 0,
            deductions REAL DEFAULT 0,
            net_pay REAL DEFAULT 0,
            status TEXT DEFAULT 'Draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS accounting_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            period_label TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT DEFAULT 'Open',
            is_locked INTEGER DEFAULT 0,
            closed_at TIMESTAMP,
            closed_by TEXT,
            reopened_at TIMESTAMP,
            reopened_by TEXT,
            locked_at TIMESTAMP,
            locked_by TEXT,
            UNIQUE(company_key, period_label)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            account TEXT NOT NULL,
            description TEXT,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            reference TEXT,
            created_by TEXT,
            branch_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("PRAGMA table_info(transactions)")
    transaction_columns = {row[1] for row in cursor.fetchall()}
    if "branch_id" not in transaction_columns:
        cursor.execute("ALTER TABLE transactions ADD COLUMN branch_id TEXT")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY,
            master_price_per_month REAL DEFAULT 500,
            base_currency TEXT DEFAULT 'GHS',
            display_currency TEXT DEFAULT 'GHS',
            exchange_rate REAL DEFAULT 1.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("PRAGMA table_info(system_settings)")
    existing_system_columns = {row[1] for row in cursor.fetchall()}
    if existing_system_columns:
        if "base_currency" not in existing_system_columns:
            cursor.execute("ALTER TABLE system_settings ADD COLUMN base_currency TEXT DEFAULT 'GHS'")
        if "display_currency" not in existing_system_columns:
            cursor.execute("ALTER TABLE system_settings ADD COLUMN display_currency TEXT DEFAULT 'GHS'")
        if "exchange_rate" not in existing_system_columns:
            cursor.execute("ALTER TABLE system_settings ADD COLUMN exchange_rate REAL DEFAULT 1.0")
    cursor.execute(
        "INSERT OR IGNORE INTO system_settings (id, master_price_per_month, base_currency, display_currency, exchange_rate) VALUES (1, 500, 'GHS', 'GHS', 1.0)"
    )
    ensure_cashier_closings_schema(conn)
    ensure_pos_sales_schema(conn)


def ensure_inventory_schema_integrity(conn):
    """
    Ensure additive inventory master columns exist before inventory UI queries run.
    This helper never drops or recreates stock data.
    """
    if conn is None:
        raise RuntimeError("Database connection is required for inventory schema integrity checks.")

    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            item_name TEXT NOT NULL,
            item_code TEXT,
            category TEXT,
            description TEXT,
            brand TEXT,
            supplier_name TEXT,
            expiry_date TEXT,
            batch_number TEXT,
            vat_category TEXT,
            qty REAL DEFAULT 0,
            min_stock_level REAL DEFAULT 10,
            unit TEXT DEFAULT 'pcs',
            cost_price REAL DEFAULT 0,
            price REAL DEFAULT 0,
            tax_rate REAL DEFAULT 0,
            warehouse_location TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("PRAGMA table_info(inventory)")
    inventory_columns = {row[1] for row in cursor.fetchall()}
    inventory_column_defs = {
        "company_key": "TEXT",
        "item_code": "TEXT",
        "barcode": "TEXT",
        "category": "TEXT",
        "description": "TEXT",
        "brand": "TEXT",
        "supplier_name": "TEXT",
        "expiry_date": "TEXT",
        "batch_number": "TEXT",
        "vat_category": "TEXT",
        "opening_balance": "REAL DEFAULT 0",
        "qty": "REAL DEFAULT 0",
        "min_stock_level": "REAL DEFAULT 10",
        "unit": "TEXT DEFAULT 'pcs'",
        "cost_price": "REAL DEFAULT 0",
        "price": "REAL DEFAULT 0",
        "inventory_account_id": "INTEGER",
        "cogs_account_id": "INTEGER",
        "tax_rate": "REAL DEFAULT 0",
        "warehouse_location": "TEXT",
        "is_active": "INTEGER DEFAULT 1",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_def in inventory_column_defs.items():
        if column_name not in inventory_columns:
            cursor.execute(f"ALTER TABLE inventory ADD COLUMN {column_name} {column_def}")
    if "quantity" in inventory_columns and "qty" in (inventory_columns | set(inventory_column_defs)):
        cursor.execute("UPDATE inventory SET qty = COALESCE(qty, quantity, 0)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_reference TEXT UNIQUE,
            company_key TEXT NOT NULL,
            branch_id TEXT,
            imported_item_count INTEGER DEFAULT 0,
            created_count INTEGER DEFAULT 0,
            updated_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            total_opening_value REAL DEFAULT 0,
            imported_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            opening_posted INTEGER DEFAULT 0,
            opening_posted_entry_id INTEGER,
            opening_posted_at TIMESTAMP,
            opening_posted_by TEXT,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("PRAGMA table_info(inventory_import_batches)")
    batch_columns = {row[1] for row in cursor.fetchall()}
    batch_column_defs = {
        "import_reference": "TEXT",
        "company_key": "TEXT",
        "branch_id": "TEXT",
        "imported_item_count": "INTEGER DEFAULT 0",
        "created_count": "INTEGER DEFAULT 0",
        "updated_count": "INTEGER DEFAULT 0",
        "skipped_count": "INTEGER DEFAULT 0",
        "error_count": "INTEGER DEFAULT 0",
        "total_opening_value": "REAL DEFAULT 0",
        "imported_by": "TEXT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "opening_posted": "INTEGER DEFAULT 0",
        "opening_posted_entry_id": "INTEGER",
        "opening_posted_at": "TIMESTAMP",
        "opening_posted_by": "TEXT",
    }
    for column_name, column_def in batch_column_defs.items():
        if column_name not in batch_columns:
            cursor.execute(f"ALTER TABLE inventory_import_batches ADD COLUMN {column_name} {column_def}")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_import_batches_reference ON inventory_import_batches(import_reference)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_import_batches_company ON inventory_import_batches(company_key, created_at)")
    ensure_stock_movements_schema_integrity(conn)


def ensure_stock_movements_schema_integrity(conn):
    """
    Ensure additive stock movement audit columns exist for inventory intake traceability.
    """
    if conn is None:
        raise RuntimeError("Database connection is required for stock movement schema integrity checks.")

    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT,
            inventory_item_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            movement_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            reason TEXT,
            previous_qty REAL DEFAULT 0,
            new_qty REAL DEFAULT 0,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory(id) ON DELETE CASCADE,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("PRAGMA table_info(stock_movements)")
    stock_movement_columns = {row[1] for row in cursor.fetchall()}
    stock_movement_column_defs = {
        "branch_id": "TEXT",
        "reference": "TEXT",
        "notes": "TEXT",
        "status": "TEXT DEFAULT 'Approved'",
        "approval_status": "TEXT DEFAULT 'Approved'",
        "posted_entry_id": "INTEGER",
        "last_journal_sync_at": "TIMESTAMP",
        "submitted_at": "TIMESTAMP",
        "approved_at": "TIMESTAMP",
        "approved_by": "TEXT",
        "cancelled_at": "TIMESTAMP",
        "cancelled_by": "TEXT",
    }
    for column_name, column_def in stock_movement_column_defs.items():
        if column_name not in stock_movement_columns:
            cursor.execute(f"ALTER TABLE stock_movements ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_stock_movements_company_created ON stock_movements(company_key, created_at DESC)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_item ON stock_movements(inventory_item_id)")


def ensure_cashier_closings_schema(conn):
    """
    Ensure cashier closing control tables exist before POS closing queries run.
    This helper is additive only and never mutates sales, stock, or accounting history.
    """
    if conn is None:
        raise RuntimeError("Database connection is required for cashier closing schema integrity checks.")

    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cashier_closings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT DEFAULT '',
            cashier TEXT NOT NULL,
            closing_date TEXT NOT NULL,
            expected_cash REAL DEFAULT 0,
            counted_cash REAL DEFAULT 0,
            difference REAL DEFAULT 0,
            notes TEXT,
            closed_by TEXT,
            closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("PRAGMA table_info(cashier_closings)")
    closing_columns = {row[1] for row in cursor.fetchall()}
    closing_column_defs = {
        "company_key": "TEXT",
        "branch_id": "TEXT DEFAULT ''",
        "cashier": "TEXT",
        "closing_date": "TEXT",
        "expected_cash": "REAL DEFAULT 0",
        "counted_cash": "REAL DEFAULT 0",
        "difference": "REAL DEFAULT 0",
        "notes": "TEXT",
        "closed_by": "TEXT",
        "closed_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_def in closing_column_defs.items():
        if column_name not in closing_columns:
            cursor.execute(f"ALTER TABLE cashier_closings ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cashier_closings_unique_drawer ON cashier_closings(company_key, branch_id, cashier, closing_date)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cashier_closings_company_date ON cashier_closings(company_key, closing_date, closed_at)"
    )


def ensure_pos_sales_schema(conn):
    """
    Ensure additive POS sale and return control tables exist.
    This helper never rewrites original sales and only adds lookup/audit structures.
    """
    if conn is None:
        raise RuntimeError("Database connection is required for POS sale schema integrity checks.")

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(stock_movements)")
    stock_movement_columns = {row[1] for row in cursor.fetchall()}
    if stock_movement_columns and "reference" not in stock_movement_columns:
        cursor.execute("ALTER TABLE stock_movements ADD COLUMN reference TEXT")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pos_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT DEFAULT '',
            sale_reference TEXT NOT NULL,
            receipt_number TEXT NOT NULL,
            sale_date TEXT NOT NULL,
            sale_datetime TEXT,
            cashier TEXT,
            payment_method TEXT,
            customer_id INTEGER,
            subtotal REAL DEFAULT 0,
            discount_total REAL DEFAULT 0,
            tax_total REAL DEFAULT 0,
            grand_total REAL DEFAULT 0,
            amount_tendered REAL DEFAULT 0,
            change_due REAL DEFAULT 0,
            posted_entry_id INTEGER,
            cogs_posted_entry_id INTEGER,
            last_journal_sync_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("PRAGMA table_info(pos_sales)")
    pos_sale_columns = {row[1] for row in cursor.fetchall()}
    pos_sale_column_defs = {
        "company_key": "TEXT",
        "branch_id": "TEXT DEFAULT ''",
        "sale_reference": "TEXT",
        "receipt_number": "TEXT",
        "sale_date": "TEXT",
        "sale_datetime": "TEXT",
        "cashier": "TEXT",
        "payment_method": "TEXT",
        "customer_id": "INTEGER",
        "subtotal": "REAL DEFAULT 0",
        "discount_total": "REAL DEFAULT 0",
        "tax_total": "REAL DEFAULT 0",
        "grand_total": "REAL DEFAULT 0",
        "amount_tendered": "REAL DEFAULT 0",
        "change_due": "REAL DEFAULT 0",
        "posted_entry_id": "INTEGER",
        "cogs_posted_entry_id": "INTEGER",
        "last_journal_sync_at": "TIMESTAMP",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_def in pos_sale_column_defs.items():
        if column_name not in pos_sale_columns:
            cursor.execute(f"ALTER TABLE pos_sales ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pos_sales_reference ON pos_sales(company_key, sale_reference)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pos_sales_cashier_date ON pos_sales(company_key, sale_date, cashier)"
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pos_sale_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pos_sale_id INTEGER NOT NULL,
            company_key TEXT NOT NULL,
            inventory_item_id INTEGER,
            item_name TEXT NOT NULL,
            item_code TEXT,
            barcode TEXT,
            qty_sold REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            line_discount REAL DEFAULT 0,
            tax_rate REAL DEFAULT 0,
            line_total REAL DEFAULT 0,
            cost_price REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pos_sale_id) REFERENCES pos_sales (id) ON DELETE CASCADE,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("PRAGMA table_info(pos_sale_lines)")
    pos_sale_line_columns = {row[1] for row in cursor.fetchall()}
    pos_sale_line_defs = {
        "pos_sale_id": "INTEGER",
        "company_key": "TEXT",
        "inventory_item_id": "INTEGER",
        "item_name": "TEXT",
        "item_code": "TEXT",
        "barcode": "TEXT",
        "qty_sold": "REAL DEFAULT 0",
        "unit_price": "REAL DEFAULT 0",
        "line_discount": "REAL DEFAULT 0",
        "tax_rate": "REAL DEFAULT 0",
        "line_total": "REAL DEFAULT 0",
        "cost_price": "REAL DEFAULT 0",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for column_name, column_def in pos_sale_line_defs.items():
        if column_name not in pos_sale_line_columns:
            cursor.execute(f"ALTER TABLE pos_sale_lines ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pos_sale_lines_sale ON pos_sale_lines(pos_sale_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pos_sale_lines_item ON pos_sale_lines(company_key, inventory_item_id, barcode, item_code)"
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pos_returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT DEFAULT '',
            original_sale_reference TEXT NOT NULL,
            return_reference TEXT NOT NULL,
            pos_sale_line_id INTEGER,
            item_id INTEGER,
            item_name TEXT NOT NULL,
            qty_returned REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            refund_amount REAL DEFAULT 0,
            reason TEXT,
            refund_method TEXT,
            returned_by TEXT,
            returned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_entry_id INTEGER,
            status TEXT DEFAULT 'Posted',
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("PRAGMA table_info(pos_returns)")
    pos_return_columns = {row[1] for row in cursor.fetchall()}
    pos_return_defs = {
        "company_key": "TEXT",
        "branch_id": "TEXT DEFAULT ''",
        "original_sale_reference": "TEXT",
        "return_reference": "TEXT",
        "pos_sale_line_id": "INTEGER",
        "item_id": "INTEGER",
        "item_name": "TEXT",
        "qty_returned": "REAL DEFAULT 0",
        "unit_price": "REAL DEFAULT 0",
        "refund_amount": "REAL DEFAULT 0",
        "reason": "TEXT",
        "refund_method": "TEXT",
        "returned_by": "TEXT",
        "returned_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "posted_entry_id": "INTEGER",
        "status": "TEXT DEFAULT 'Posted'",
    }
    for column_name, column_def in pos_return_defs.items():
        if column_name not in pos_return_columns:
            cursor.execute(f"ALTER TABLE pos_returns ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pos_returns_reference_line ON pos_returns(company_key, return_reference, pos_sale_line_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pos_returns_sale_line ON pos_returns(company_key, original_sale_reference, pos_sale_line_id)"
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pos_suspended_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT DEFAULT '',
            suspend_reference TEXT NOT NULL,
            cashier TEXT,
            cart_json TEXT NOT NULL,
            note TEXT,
            status TEXT DEFAULT 'suspended',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resumed_at TIMESTAMP,
            cancelled_at TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("PRAGMA table_info(pos_suspended_sales)")
    suspended_columns = {row[1] for row in cursor.fetchall()}
    suspended_defs = {
        "company_key": "TEXT",
        "branch_id": "TEXT DEFAULT ''",
        "suspend_reference": "TEXT",
        "cashier": "TEXT",
        "cart_json": "TEXT",
        "note": "TEXT",
        "status": "TEXT DEFAULT 'suspended'",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "resumed_at": "TIMESTAMP",
        "cancelled_at": "TIMESTAMP",
    }
    for column_name, column_def in suspended_defs.items():
        if column_name not in suspended_columns:
            cursor.execute(f"ALTER TABLE pos_suspended_sales ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pos_suspended_sales_reference ON pos_suspended_sales(company_key, suspend_reference)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pos_suspended_sales_status ON pos_suspended_sales(company_key, status, created_at)"
    )


def _ensure_app_compatibility_tables(conn):
    """
    Keep legacy app-facing tables readable during the migration-safe rollout.
    These tables remain additive only and are not used to destroy or replace data.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            inventory_item_id INTEGER,
            item_name TEXT NOT NULL,
            quantity REAL DEFAULT 1,
            unit_price REAL DEFAULT 0,
            line_total REAL DEFAULT 0,
            cost_price REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute("PRAGMA table_info(invoice_lines)")
    invoice_line_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_def in {
        "invoice_id": "INTEGER",
        "inventory_item_id": "INTEGER",
        "item_name": "TEXT",
        "quantity": "REAL DEFAULT 1",
        "unit_price": "REAL DEFAULT 0",
        "line_total": "REAL DEFAULT 0",
        "cost_price": "REAL DEFAULT 0",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }.items():
        if column_name not in invoice_line_columns:
            cursor.execute(f"ALTER TABLE invoice_lines ADD COLUMN {column_name} {column_def}")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice_id ON invoice_lines(invoice_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoice_lines_inventory_item_id ON invoice_lines(inventory_item_id)")

    cursor.execute("PRAGMA table_info(bills)")
    bill_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_def in {
        "purchase_classification": "TEXT DEFAULT 'Inventory Purchase'",
        "payment_method": "TEXT",
        "expense_account_name": "TEXT",
        "asset_name": "TEXT",
        "asset_category": "TEXT",
    }.items():
        if column_name not in bill_columns:
            cursor.execute(f"ALTER TABLE bills ADD COLUMN {column_name} {column_def}")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts_payable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT,
            amount REAL,
            status TEXT,
            due_date TEXT
        )
        """
    )
    cursor.execute("PRAGMA table_info(accounts_payable)")
    accounts_payable_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_def in {
        "vendor": "TEXT",
        "amount": "REAL",
        "status": "TEXT",
        "due_date": "TEXT",
    }.items():
        if column_name not in accounts_payable_columns:
            cursor.execute(f"ALTER TABLE accounts_payable ADD COLUMN {column_name} {column_def}")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT,
            quantity INTEGER,
            cost REAL,
            status TEXT
        )
        """
    )
    cursor.execute("PRAGMA table_info(purchase_orders)")
    purchase_order_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_def in {
        "item": "TEXT",
        "quantity": "INTEGER",
        "cost": "REAL",
        "status": "TEXT",
    }.items():
        if column_name not in purchase_order_columns:
            cursor.execute(f"ALTER TABLE purchase_orders ADD COLUMN {column_name} {column_def}")


def _run_lightweight_integrity_checks(conn):
    """
    Lightweight startup validation and additive repairs only.
    This path intentionally avoids any reset-like behavior.
    """
    _ensure_migration_metadata_tables(conn)
    _ensure_database_identity_table(conn)
    ensure_schema_integrity(conn)
    fixed_asset_schema = get_fixed_assets_schema_diagnostics(conn, repair=False)
    if fixed_asset_schema.get("missing_columns") or fixed_asset_schema.get("failed_repairs"):
        logger.warning(
            "Fixed assets schema diagnostics: table_exists=%s missing_columns=%s failed_repairs=%s",
            fixed_asset_schema.get("table_exists"),
            fixed_asset_schema.get("missing_columns"),
            fixed_asset_schema.get("failed_repairs"),
        )
    _ensure_app_compatibility_tables(conn)
    log_schema_manifest_diagnostics(conn)


def _advanced_startup_available():
    return DB_UPGRADE_SAFETY_AVAILABLE and ERP_MIGRATIONS_AVAILABLE and not ERP_SAFE_STARTUP_MODE


def check_and_repair_db():
    """Compatibility wrapper for the canonical startup safety path."""
    return startup_database()

# =================================================================
# 2. CORE CONNECTION ENGINE
# =================================================================
def get_connection():
    """
    Establishes a high-performance native SQLite connection.
    Includes Row Factory for dictionary-style access and PRAGMA 
    settings for data integrity.
    """
    try:
        _ensure_local_db_file()
        return _open_sqlite_connection(enable_persistence_hooks=True)
    except sqlite3.Error as e:
        logger.critical(f"DATABASE CONNECTION FAILURE: {e}")
        return None

# =================================================================
# 3. DATABASE INITIALIZATION (FULL SCHEMA DEPLOYMENT)
# =================================================================
def _deploy_full_schema(conn):
    """
    Deploy the complete ERP database architecture additively.
    This function never drops or recreates existing tables.
    """
    try:
        if conn is None:
            raise RuntimeError("Database connection is required for schema deployment.")
        cursor = conn.cursor()

        # --- TABLE 1: CORPORATE ENTITIES & LICENSING ---
        # Stores master account data, license keys, and security answers
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                key TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                sub_admin_key TEXT,
                staff_key TEXT,
                recovery_answer TEXT,
                tin TEXT,
            subscription_expiry TEXT,
            status TEXT DEFAULT 'Active',
            deployment_status TEXT DEFAULT 'Pending',
            number_of_branches INTEGER DEFAULT 1,
            max_branches INTEGER DEFAULT 1,
            branch_price_per_month REAL DEFAULT 0.0,
                contact_email TEXT,
                phone_number TEXT,
                physical_address TEXT,
                industry TEXT,
                currency TEXT DEFAULT 'GHS',
                logo_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        ensure_schema_integrity(conn)
        cursor.execute("PRAGMA table_info(companies)")
        company_columns = {row[1] for row in cursor.fetchall()}
        company_column_defs = {
            "number_of_branches": "INTEGER DEFAULT 1",
            "max_branches": "INTEGER DEFAULT 1",
            "branch_price_per_month": "REAL DEFAULT 0.0",
        }
        for column_name, column_def in company_column_defs.items():
            if column_name not in company_columns:
                cursor.execute(f"ALTER TABLE companies ADD COLUMN {column_name} {column_def}")

        # --- TABLE 2: INVENTORY & STOCK MASTER ---
        # Manages product levels, costs, and warehouse locations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_code TEXT,
                category TEXT,
                description TEXT,
                brand TEXT,
                supplier_name TEXT,
                expiry_date TEXT,
                batch_number TEXT,
                vat_category TEXT,
                qty REAL DEFAULT 0,
                min_stock_level REAL DEFAULT 10,
                unit TEXT DEFAULT 'pcs',
                cost_price REAL DEFAULT 0,
                price REAL DEFAULT 0,
                tax_rate REAL DEFAULT 0,
                warehouse_location TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS branches (
                branch_id TEXT PRIMARY KEY,
                company_key TEXT NOT NULL,
                branch_name TEXT NOT NULL,
                location TEXT,
                branch_type TEXT,
                branch_access_key TEXT UNIQUE,
                contact_number TEXT,
                branch_manager TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_branches_company ON branches(company_key)")
        cursor.execute("PRAGMA table_info(branches)")
        branch_columns = {row[1] for row in cursor.fetchall()}
        branch_column_defs = {
            "branch_id": "TEXT",
            "company_key": "TEXT",
            "branch_name": "TEXT",
            "location": "TEXT",
            "branch_type": "TEXT",
            "branch_access_key": "TEXT",
            "contact_number": "TEXT",
            "branch_manager": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for column_name, column_def in branch_column_defs.items():
            if column_name not in branch_columns:
                cursor.execute(f"ALTER TABLE branches ADD COLUMN {column_name} {column_def}")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_branches_access_key ON branches(branch_access_key)")
        ensure_inventory_schema_integrity(conn)
        # Indexes for fast product searching
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_comp ON inventory(company_key);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_name ON inventory(item_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_barcode ON inventory(barcode);")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                branch_id TEXT,
                inventory_item_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                movement_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                reason TEXT,
                previous_qty REAL DEFAULT 0,
                new_qty REAL DEFAULT 0,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE,
                FOREIGN KEY (branch_id) REFERENCES branches (branch_id) ON DELETE SET NULL,
                FOREIGN KEY (inventory_item_id) REFERENCES inventory (id) ON DELETE CASCADE
            )
        """)
        cursor.execute("PRAGMA table_info(stock_movements)")
        stock_movement_columns = {row[1] for row in cursor.fetchall()}
        stock_movement_column_defs = {
            "company_key": "TEXT",
            "branch_id": "TEXT",
            "inventory_item_id": "INTEGER",
            "item_name": "TEXT",
            "movement_type": "TEXT",
            "quantity": "REAL DEFAULT 0",
            "reason": "TEXT",
            "previous_qty": "REAL DEFAULT 0",
            "new_qty": "REAL DEFAULT 0",
            "created_by": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for column_name, column_def in stock_movement_column_defs.items():
            if column_name not in stock_movement_columns:
                cursor.execute(f"ALTER TABLE stock_movements ADD COLUMN {column_name} {column_def}")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_company_created ON stock_movements(company_key, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_item ON stock_movements(inventory_item_id)")

        # --- TABLE 3: FINANCIAL VOUCHERS & GENERAL LEDGER ---
        # Central ledger for POS sales, expenses, and journals
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                branch_id TEXT,
                date TEXT NOT NULL,
                v_type TEXT NOT NULL, -- Sales, Purchase, Expense, Journal
                ledger TEXT NOT NULL,
                debit REAL DEFAULT 0,
                credit REAL DEFAULT 0,
                balance_after REAL DEFAULT 0,
                payment_method TEXT, -- Cash, MoMo, Bank, Cheque
                reference_no TEXT,
                narration TEXT,
                is_cleared INTEGER DEFAULT 1,
                status TEXT DEFAULT 'Draft',
                approval_status TEXT DEFAULT 'Draft',
                is_voided INTEGER DEFAULT 0,
                voided_at TIMESTAMP,
                voided_by TEXT,
                submitted_at TIMESTAMP,
                approved_at TIMESTAMP,
                approved_by TEXT,
                posted_entry_id INTEGER,
                last_journal_sync_at TIMESTAMP,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
        """)
        cursor.execute("PRAGMA table_info(vouchers)")
        voucher_columns = {row[1] for row in cursor.fetchall()}
        voucher_column_defs = {
            "company_key": "TEXT",
            "branch_id": "TEXT",
            "date": "TEXT",
            "v_type": "TEXT",
            "ledger": "TEXT",
            "debit": "REAL DEFAULT 0",
            "credit": "REAL DEFAULT 0",
            "balance_after": "REAL DEFAULT 0",
            "payment_method": "TEXT",
            "reference_no": "TEXT",
            "narration": "TEXT",
            "is_cleared": "INTEGER DEFAULT 1",
            "status": "TEXT DEFAULT 'Active'",
            "created_by": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for column_name, column_def in voucher_column_defs.items():
            if column_name not in voucher_columns:
                cursor.execute(f"ALTER TABLE vouchers ADD COLUMN {column_name} {column_def}")
        if "ref_no" in voucher_columns and "reference_no" in (voucher_columns | set(voucher_column_defs)):
            cursor.execute(
                "UPDATE vouchers SET reference_no = COALESCE(reference_no, ref_no) "
                "WHERE reference_no IS NULL OR reference_no = ''"
            )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vouch_date ON vouchers(date);")

        # --- TABLE 4: GHANA STATUTORY PAYROLL ENGINE ---
        # Handles SSNIT Tier 1 & 2 and Ghana Revenue Authority PAYE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payroll (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                emp_name TEXT NOT NULL,
                emp_id TEXT,
                bank_name TEXT,
                account_number TEXT,
                basic_salary REAL NOT NULL,
                allowances REAL DEFAULT 0,
                ssnit_t1 REAL DEFAULT 0,
                ssnit_t2 REAL DEFAULT 0,
                taxable_income REAL DEFAULT 0,
                paye REAL DEFAULT 0,
                net_salary REAL DEFAULT 0,
                deductions REAL DEFAULT 0,
                month TEXT NOT NULL,
                year TEXT NOT NULL,
                payment_status TEXT DEFAULT 'Unpaid',
                payment_method TEXT,
                approval_status TEXT DEFAULT 'Posted',
                approved_at TIMESTAMP,
                approved_by TEXT,
                posted_entry_id INTEGER,
                last_journal_sync_at TIMESTAMP,
                created_by TEXT,
                status TEXT DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
        """)
        cursor.execute("PRAGMA table_info(payroll)")
        payroll_columns = {row[1] for row in cursor.fetchall()}
        payroll_column_defs = {
            "company_key": "TEXT",
            "emp_id": "TEXT",
            "bank_name": "TEXT",
            "account_number": "TEXT",
            "allowances": "REAL DEFAULT 0",
            "deductions": "REAL DEFAULT 0",
            "status": "TEXT DEFAULT 'Active'",
            "payment_status": "TEXT DEFAULT 'Unpaid'",
            "payment_method": "TEXT",
            "approval_status": "TEXT DEFAULT 'Posted'",
            "approved_at": "TIMESTAMP",
            "approved_by": "TEXT",
            "posted_entry_id": "INTEGER",
            "last_journal_sync_at": "TIMESTAMP",
            "created_by": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for column_name, column_def in payroll_column_defs.items():
            if column_name not in payroll_columns:
                cursor.execute(f"ALTER TABLE payroll ADD COLUMN {column_name} {column_def}")

        # --- TABLE 5: FIXED ASSET REGISTER ---
        # Tracking long-term assets and depreciation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fixed_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                asset_category TEXT,
                purchase_date TEXT,
                cost REAL NOT NULL,
                supplier_id INTEGER,
                useful_life_years REAL DEFAULT 0,
                residual_value REAL DEFAULT 0,
                depreciation_method TEXT DEFAULT 'Straight-line',
                depreciation_rate REAL DEFAULT 0,
                accumulated_depreciation REAL DEFAULT 0,
                book_value REAL NOT NULL,
                last_depreciation_date TEXT,
                location TEXT,
                custodian TEXT,
                description TEXT,
                notes TEXT,
                acquisition_type TEXT DEFAULT 'Opening Balance Asset',
                acquisition_source TEXT,
                payment_method TEXT,
                owner_contributor_name TEXT,
                owner_name TEXT,
                status TEXT DEFAULT 'Active',
                approval_status TEXT DEFAULT 'Posted',
                approved_at TIMESTAMP,
                approved_by TEXT,
                posted_entry_id INTEGER,
                acquisition_journal_entry_id INTEGER,
                last_journal_sync_at TIMESTAMP,
                created_by TEXT,
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
        """)
        cursor.execute("PRAGMA table_info(fixed_assets)")
        fixed_asset_columns = {row[1] for row in cursor.fetchall()}
        fixed_asset_column_defs = FIXED_ASSET_SCHEMA_COLUMN_DEFS
        for column_name, column_def in fixed_asset_column_defs.items():
            if column_name not in fixed_asset_columns:
                cursor.execute(f"ALTER TABLE fixed_assets ADD COLUMN {column_name} {column_def}")
        if "opening_book_value" not in fixed_asset_columns and "book_value" in (fixed_asset_columns | set(fixed_asset_column_defs)):
            cursor.execute("UPDATE fixed_assets SET opening_book_value = COALESCE(book_value, cost, 0)")
        if "purchase_cost" in fixed_asset_columns and "cost" in (fixed_asset_columns | set(fixed_asset_column_defs)):
            cursor.execute("UPDATE fixed_assets SET cost = COALESCE(cost, purchase_cost, 0)")
        if "dep_rate" in fixed_asset_columns and "depreciation_rate" in (fixed_asset_columns | set(fixed_asset_column_defs)):
            cursor.execute(
                "UPDATE fixed_assets SET depreciation_rate = COALESCE(depreciation_rate, dep_rate, 0)"
            )
        if "accum_dep" in fixed_asset_columns and "accumulated_depreciation" in (fixed_asset_columns | set(fixed_asset_column_defs)):
            cursor.execute(
                "UPDATE fixed_assets SET accumulated_depreciation = COALESCE(accumulated_depreciation, accum_dep, 0)"
            )
        cursor.execute(
            """
            UPDATE fixed_assets
            SET depreciation_method = COALESCE(NULLIF(depreciation_method, ''), 'Straight-line'),
                residual_value = COALESCE(residual_value, 0),
                useful_life_years = CASE
                    WHEN COALESCE(useful_life_years, 0) > 0 THEN useful_life_years
                    WHEN COALESCE(depreciation_rate, 0) > 0 THEN ROUND(100.0 / depreciation_rate, 4)
                    ELSE 0
                END,
                book_value = COALESCE(book_value, opening_book_value, cost, 0),
                opening_book_value = COALESCE(opening_book_value, book_value, cost, 0)
            """
        )

        # --- TABLE 6: FORENSIC AUDIT TRAIL ---
        # Security table for tracking all user actions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                company_key TEXT,
                branch_id TEXT,
                user_role TEXT,
                action TEXT NOT NULL,
                module_name TEXT,
                details TEXT,
                action_type TEXT,
                document_ref TEXT,
                before_after_summary TEXT,
                event_id TEXT,
                ip_address TEXT
            )
        """)
        cursor.execute("PRAGMA table_info(audit_logs)")
        audit_columns = {row[1] for row in cursor.fetchall()}
        audit_column_defs = {
            "branch_id": "TEXT",
            "details": "TEXT",
            "action_type": "TEXT",
            "document_ref": "TEXT",
            "before_after_summary": "TEXT",
            "event_id": "TEXT",
            "ip_address": "TEXT",
        }
        for column_name, column_def in audit_column_defs.items():
            if column_name not in audit_columns:
                cursor.execute(f"ALTER TABLE audit_logs ADD COLUMN {column_name} {column_def}")
        cursor.execute(
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
        cursor.execute("PRAGMA table_info(system_logs)")
        system_log_columns = {row[1] for row in cursor.fetchall()}
        system_log_column_defs = {
            "timestamp": "TEXT",
            "level": "TEXT",
            "module_name": "TEXT",
            "message": "TEXT",
        }
        for column_name, column_def in system_log_column_defs.items():
            if column_name not in system_log_columns:
                cursor.execute(f"ALTER TABLE system_logs ADD COLUMN {column_name} {column_def}")

        # --- TABLE 7: MAINTENANCE & SYSTEM SETTINGS ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_settings (
                id INTEGER PRIMARY KEY,
                maintenance_date TEXT,
                start_time TEXT,
                end_time TEXT,
                is_active INTEGER DEFAULT 0,
                message TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("PRAGMA table_info(maintenance_settings)")
        maintenance_columns = {row[1] for row in cursor.fetchall()}
        maintenance_column_defs = {
            "maintenance_date": "TEXT",
            "start_time": "TEXT",
            "end_time": "TEXT",
            "is_active": "INTEGER DEFAULT 0",
            "message": "TEXT",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for column_name, column_def in maintenance_column_defs.items():
            if column_name not in maintenance_columns:
                cursor.execute(f"ALTER TABLE maintenance_settings ADD COLUMN {column_name} {column_def}")
        cursor.execute("INSERT OR IGNORE INTO maintenance_settings (id, is_active) VALUES (1, 0)")

        # --- TABLE 8: PENDING APPROVALS QUEUE ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT,
                payment_reference TEXT UNIQUE,
                amount REAL,
                payment_method TEXT,
                plan_requested TEXT,
                status TEXT DEFAULT 'Pending',
                admin_notes TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_key) REFERENCES companies (key)
            )
        """)
        cursor.execute("PRAGMA table_info(pending_approvals)")
        pending_columns = {row[1] for row in cursor.fetchall()}
        pending_column_defs = {
            "payment_reference": "TEXT",
            "payment_method": "TEXT",
            "plan_requested": "TEXT",
            "admin_notes": "TEXT",
            "timestamp": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for column_name, column_def in pending_column_defs.items():
            if column_name not in pending_columns:
                cursor.execute(f"ALTER TABLE pending_approvals ADD COLUMN {column_name} {column_def}")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS license_payment_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT UNIQUE,
                company_key TEXT,
                company_name TEXT,
                payer_email TEXT,
                payment_context TEXT DEFAULT 'license_activation',
                expected_amount INTEGER DEFAULT 0,
                currency TEXT DEFAULT 'GHS',
                status TEXT DEFAULT 'initialized',
                authorization_url TEXT,
                callback_url TEXT,
                metadata_json TEXT,
                gateway_status_summary TEXT,
                paid_at TIMESTAMP,
                verified_at TIMESTAMP,
                activated_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_key) REFERENCES companies (key)
            )
            """
        )
        _ensure_subscription_billing_schema(cursor)
        cursor.execute("PRAGMA table_info(license_payment_transactions)")
        license_payment_columns = {row[1] for row in cursor.fetchall()}
        license_payment_column_defs = {
            "company_key": "TEXT",
            "company_name": "TEXT",
            "payer_email": "TEXT",
            "payment_context": "TEXT DEFAULT 'license_activation'",
            "expected_amount": "INTEGER DEFAULT 0",
            "currency": "TEXT DEFAULT 'GHS'",
            "status": "TEXT DEFAULT 'initialized'",
            "authorization_url": "TEXT",
            "callback_url": "TEXT",
            "metadata_json": "TEXT",
            "gateway_status_summary": "TEXT",
            "paid_at": "TIMESTAMP",
            "verified_at": "TIMESTAMP",
            "activated_at": "TIMESTAMP",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for column_name, column_def in license_payment_column_defs.items():
            if column_name not in license_payment_columns:
                cursor.execute(f"ALTER TABLE license_payment_transactions ADD COLUMN {column_name} {column_def}")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_license_payment_transactions_company_status ON license_payment_transactions(company_key, status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_license_payment_transactions_verified_at ON license_payment_transactions(verified_at)"
        )

        # --- TABLE 9: COMPANY USERS ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                branch_id TEXT,
                full_name TEXT NOT NULL,
                user_id TEXT,
                login_key TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                security_question TEXT,
                security_answer TEXT,
                role TEXT NOT NULL,
                status TEXT DEFAULT 'Active',
                current_session_id TEXT,
                last_login_device TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE,
                FOREIGN KEY (branch_id) REFERENCES branches (branch_id) ON DELETE SET NULL
            )
        """)
        cursor.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cursor.fetchall()}
        user_column_defs = {
            "company_key": "TEXT",
            "branch_id": "TEXT",
            "full_name": "TEXT",
            "user_id": "TEXT",
            "login_key": "TEXT",
            "password_hash": "TEXT",
            "security_question": "TEXT",
            "security_answer": "TEXT",
            "role": "TEXT",
            "status": "TEXT DEFAULT 'Active'",
            "current_session_id": "TEXT",
            "last_login_device": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for column_name, column_def in user_column_defs.items():
            if column_name not in user_columns:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_login_key ON users(login_key)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)")

        # --- TABLE 10: CUSTOMER / VENDOR PROFILES ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS counterparties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                party_name TEXT NOT NULL,
                party_type TEXT NOT NULL,
                city_region TEXT,
                last_transaction TEXT,
                balance REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_key, party_name, party_type),
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
        """)
        cursor.execute("PRAGMA table_info(counterparties)")
        counterparty_columns = {row[1] for row in cursor.fetchall()}
        counterparty_column_defs = {
            "company_key": "TEXT",
            "party_name": "TEXT",
            "party_type": "TEXT",
            "city_region": "TEXT",
            "last_transaction": "TEXT",
            "balance": "REAL DEFAULT 0",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for column_name, column_def in counterparty_column_defs.items():
            if column_name not in counterparty_columns:
                cursor.execute(f"ALTER TABLE counterparties ADD COLUMN {column_name} {column_def}")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_counterparties_company_type ON counterparties(company_key, party_type)"
        )

        # --- TABLE 11: SYSTEM SETTINGS ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                id INTEGER PRIMARY KEY,
                master_price_per_month REAL DEFAULT 500,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "INSERT OR IGNORE INTO system_settings (id, master_price_per_month) VALUES (1, 500)"
        )

        logger.info("E.K.A CLOUD DATABASE: Full Architectural Sync Complete.")
    except sqlite3.Error as e:
        logger.error("DATABASE INITIALIZATION ERROR: %s", sanitize_error_message(e))
        raise


def _migration_bootstrap_full_schema(conn):
    _deploy_full_schema(conn)


def _migration_finalize_compatibility_schema(conn):
    _run_lightweight_integrity_checks(conn)


ORDERED_MIGRATIONS = (
    (1, "Bootstrap and synchronize the additive ERP schema.", _migration_bootstrap_full_schema),
    (2, "Apply startup safety compatibility checks and legacy table guards.", _migration_finalize_compatibility_schema),
)


def startup_database():
    """
    Canonical startup path for database bootstrap, backups, migrations, and validation.
    The flow is additive, idempotent, and restores from backup if validation detects data loss.
    """
    global LAST_RESTORE_SOURCE
    LAST_RESTORE_SOURCE = "local_runtime_database"
    logger.info("Database startup entered: db_path=%s", DB_PATH)
    restore_guard = _load_restore_guard_state()
    if restore_guard.get("active"):
        logger.warning(
            "Local restore guard is active; cloud/local backup uploads remain disabled for this first boot: source=%s target=%s restored_company_count=%s",
            restore_guard.get("source_db_path"),
            restore_guard.get("target_db_path"),
            restore_guard.get("restored_company_count"),
        )
    _ensure_local_db_file()
    preflight_conn = None
    if os.path.exists(DB_PATH) and is_database_valid(DB_PATH, logger_instance=logger):
        try:
            preflight_conn = _open_sqlite_connection()
            preflight_conn.execute("BEGIN")
            _run_lightweight_integrity_checks(preflight_conn)
            preflight_conn.commit()
        except Exception as exc:
            if preflight_conn:
                try:
                    preflight_conn.rollback()
                except sqlite3.Error:
                    pass
            logger.warning("Preflight integrity preparation failed before production readiness evaluation: %s", sanitize_error_message(exc))
        finally:
            if preflight_conn:
                preflight_conn.close()
    db_health_before_startup = get_database_health_snapshot(DB_PATH, logger_instance=logger)
    cloud_restore_used = False
    recovery_attempted = False
    startup_cloud_backup_company_count = None
    failure_reason = "; ".join(db_health_before_startup.get("readiness_failures", [])) or "local database is not production-ready"
    failure_stage = "startup_validation"
    logger.info(
        "Database startup path selected: base_dir=%s db_dir=%s db_path=%s backend=%s file_size_bytes=%s database_uuid=%s schema_version=%s last_startup_at=%s eka_data_dir=%s db_exists=%s db_valid=%s production_ready=%s company_count=%s missing_tables=%s readiness_failures=%s production_mode=%s safe_mode=%s advanced_helpers_available=%s db_upgrade_safety=%s erp_migrations=%s recovery_attempted=%s recovery_succeeded=%s cloud_restore_disabled=%s",
        BASE_DIR,
        DB_DIR,
        db_health_before_startup["db_path"],
        db_health_before_startup.get("backend_label") or db_health_before_startup.get("backend") or "SQLite",
        db_health_before_startup.get("file_size_bytes"),
        db_health_before_startup.get("database_uuid") or "missing",
        db_health_before_startup.get("schema_version"),
        db_health_before_startup.get("last_startup_at") or "never",
        os.getenv("EKA_DATA_DIR"),
        db_health_before_startup["file_exists"],
        db_health_before_startup["structural_valid"],
        db_health_before_startup["production_ready"],
        db_health_before_startup["company_count"],
        ", ".join(db_health_before_startup.get("missing_tables", [])) or "none",
        "; ".join(db_health_before_startup.get("readiness_failures", [])) or "none",
        ERP_PRODUCTION_MODE,
        ERP_SAFE_STARTUP_MODE,
        _advanced_startup_available(),
        DB_UPGRADE_SAFETY_AVAILABLE,
        ERP_MIGRATIONS_AVAILABLE,
        recovery_attempted,
        cloud_restore_used,
        False,
    )
    if False and _is_empty_local_db_recovery_candidate(db_health_before_startup):
        local_bootstrap_company_count = int(db_health_before_startup.get("company_count") or 0)
        logger.warning(
            "Empty local DB detected – forcing cloud restore: db_path=%s local_company_count=%s structural_valid=%s required_tables_exist=%s companies_table_exists=%s database_identity_exists=%s schema_version_exists=%s",
            db_health_before_startup["db_path"],
            local_bootstrap_company_count,
            db_health_before_startup.get("structural_valid"),
            db_health_before_startup.get("required_tables_exist"),
            db_health_before_startup.get("companies_table_exists"),
            db_health_before_startup.get("database_identity_exists"),
            db_health_before_startup.get("schema_version_exists"),
        )
        recovery_attempted = True
        recovery_result = attempt_production_database_recovery(force_restore=True)
        cloud_restore_used = bool(recovery_result.get("ok"))
        cloud_backup_health = recovery_result.get("health") or {}
        cloud_backup_company_count = (
            int(cloud_backup_health.get("company_count") or 0)
            if cloud_backup_health.get("company_count") is not None
            else None
        )
        startup_cloud_backup_company_count = cloud_backup_company_count
        db_health_before_startup = get_database_health_snapshot(DB_PATH, logger_instance=logger)
        if cloud_restore_used and db_health_before_startup["production_ready"]:
            logger.info(
                "Bootstrap mode bypassed in favor of trusted cloud restore: local_company_count=%s cloud_backup_company_count=%s replaced_local_empty_db=%s restore_source=%s final_company_count=%s final_startup_mode=%s",
                local_bootstrap_company_count,
                cloud_backup_company_count,
                recovery_result.get("replacement_performed"),
                LAST_RESTORE_SOURCE,
                db_health_before_startup["company_count"],
                "restored_from_cloud",
            )
        else:
            logger.warning(
                "Cloud restore did not replace bootstrap-empty database; startup will stop safely to prevent empty runtime activation: local_company_count=%s cloud_backup_company_count=%s recovery_attempted=%s recovery_succeeded=%s recovery_stage=%s recovery_reason=%s restore_source=%s final_startup_mode=%s",
                local_bootstrap_company_count,
                cloud_backup_company_count,
                recovery_attempted,
                cloud_restore_used,
                recovery_result.get("stage"),
                recovery_result.get("reason"),
                LAST_RESTORE_SOURCE,
                "bootstrap_mode",
            )
            return _build_startup_result(
                ok=False,
                stage="empty_db_lockdown",
                reason=(
                    f"{EMPTY_DB_LOCKDOWN_MESSAGE} "
                    f"cloud_recovery_reason={recovery_result.get('reason', 'unknown')}"
                ),
                db_path=db_health_before_startup["db_path"],
                file_exists=db_health_before_startup["file_exists"],
                structurally_valid=db_health_before_startup["structural_valid"],
                production_ready=db_health_before_startup["production_ready"],
                company_count=db_health_before_startup["company_count"],
                recovery_attempted=recovery_attempted,
                recovery_succeeded=cloud_restore_used,
                bootstrap_needed=False,
                startup_mode="locked_down",
                cloud_backup_company_count=cloud_backup_company_count,
            )
    if _is_bootstrap_candidate(db_health_before_startup):
        if False and ERP_PRODUCTION_MODE:
            logger.error(
                "Production startup blocked because the runtime database is empty after recovery evaluation: db_path=%s company_count=%s",
                db_health_before_startup["db_path"],
                db_health_before_startup["company_count"],
            )
            return _build_startup_result(
                ok=False,
                stage="empty_db_lockdown",
                reason=EMPTY_DB_LOCKDOWN_MESSAGE,
                db_path=db_health_before_startup["db_path"],
                file_exists=db_health_before_startup["file_exists"],
                structurally_valid=db_health_before_startup["structural_valid"],
                production_ready=db_health_before_startup["production_ready"],
                company_count=db_health_before_startup["company_count"],
                recovery_attempted=recovery_attempted,
                recovery_succeeded=cloud_restore_used,
                bootstrap_needed=False,
                startup_mode="locked_down",
                cloud_backup_company_count=startup_cloud_backup_company_count,
            )
        logger.info(
            "Database startup entering bootstrap mode for structurally valid empty database: db_path=%s company_count=%s production_ready=%s recovery_attempted=%s",
            db_health_before_startup["db_path"],
            db_health_before_startup["company_count"],
            db_health_before_startup["production_ready"],
            recovery_attempted,
        )
        return _build_startup_result(
            ok=True,
            stage="bootstrap_mode",
            reason="no company has been created yet; bootstrap mode is enabled",
            db_path=db_health_before_startup["db_path"],
            file_exists=db_health_before_startup["file_exists"],
            structurally_valid=db_health_before_startup["structural_valid"],
            production_ready=db_health_before_startup["production_ready"],
            company_count=db_health_before_startup["company_count"],
            recovery_attempted=recovery_attempted,
            recovery_succeeded=cloud_restore_used,
            bootstrap_needed=True,
            startup_mode="bootstrap_mode",
            cloud_backup_company_count=startup_cloud_backup_company_count,
        )
    if ERP_PRODUCTION_MODE and not db_health_before_startup["production_ready"]:
        logger.warning(
            "Production startup detected missing or non-production-ready database. Automatic recovery will be attempted: db_path=%s",
            DB_PATH,
        )
        recovery_attempted = True
        recovery_result = attempt_production_database_recovery(force_restore=True)
        cloud_restore_used = bool(recovery_result.get("ok"))
        recovery_health = recovery_result.get("health") or {}
        startup_cloud_backup_company_count = (
            int(recovery_health.get("company_count") or 0)
            if recovery_health.get("company_count") is not None
            else startup_cloud_backup_company_count
        )
        db_health_before_startup = get_database_health_snapshot(DB_PATH, logger_instance=logger)
        logger.info(
            "Database startup recovery result: db_path=%s db_exists=%s db_valid=%s production_ready=%s company_count=%s readiness_failures=%s recovery_attempted=%s recovery_source_found=%s temp_download_succeeded=%s replacement_performed=%s recovery_succeeded=%s",
            db_health_before_startup["db_path"],
            db_health_before_startup["file_exists"],
            db_health_before_startup["structural_valid"],
            db_health_before_startup["production_ready"],
            db_health_before_startup["company_count"],
            "; ".join(db_health_before_startup.get("readiness_failures", [])) or "none",
            recovery_attempted,
            recovery_result.get("recovery_source_found"),
            recovery_result.get("temp_download_succeeded"),
            recovery_result.get("replacement_performed"),
            cloud_restore_used,
        )
        if _is_bootstrap_candidate(db_health_before_startup):
            logger.error(
                "Production startup remained empty after recovery evaluation; startup will stop safely: db_path=%s company_count=%s",
                db_health_before_startup["db_path"],
                db_health_before_startup["company_count"],
            )
            return _build_startup_result(
                ok=False,
                stage="empty_db_lockdown",
                reason=EMPTY_DB_LOCKDOWN_MESSAGE,
                db_path=db_health_before_startup["db_path"],
                file_exists=db_health_before_startup["file_exists"],
                structurally_valid=db_health_before_startup["structural_valid"],
                production_ready=db_health_before_startup["production_ready"],
                company_count=db_health_before_startup["company_count"],
                recovery_attempted=recovery_attempted,
                recovery_succeeded=cloud_restore_used,
                bootstrap_needed=False,
                startup_mode="locked_down",
                cloud_backup_company_count=startup_cloud_backup_company_count,
            )
        if not db_health_before_startup["production_ready"]:
            failure_stage = str(recovery_result.get("stage") or "recovery_validation")
            failure_reason = str(
                recovery_result.get("reason")
                or ("; ".join(db_health_before_startup.get("readiness_failures", [])) or "recovery did not produce a production-ready database")
            )
            logger.error(
                "Production startup recovery did not produce a production-ready database. Startup will fail safely: db_path=%s final_reason=%s",
                DB_PATH,
                failure_reason,
            )
            return _build_startup_result(
                ok=False,
                stage=failure_stage,
                reason=failure_reason,
                db_path=db_health_before_startup["db_path"],
                file_exists=db_health_before_startup["file_exists"],
                structurally_valid=db_health_before_startup["structural_valid"],
                production_ready=db_health_before_startup["production_ready"],
                company_count=db_health_before_startup["company_count"],
                recovery_attempted=recovery_attempted,
                recovery_succeeded=cloud_restore_used,
                startup_mode="recovery_failed",
                cloud_backup_company_count=startup_cloud_backup_company_count,
            )
    conn = None
    backup_path = None
    before_counts = {}
    after_counts = {}
    try:
        conn = _open_sqlite_connection()
        _ensure_migration_metadata_tables(conn)
        if not _advanced_startup_available():
            logger.warning(
                "Startup running in fallback mode. Only minimal additive integrity checks will run; advanced migrations are skipped."
            )
            conn.execute("BEGIN")
            _run_lightweight_integrity_checks(conn)
            _mark_database_startup_identity(conn)
            conn.commit()
            logger.info(
                "Database startup completed in fallback mode: db_path=%s db_valid=%s production_ready=%s recovery_attempted=%s recovery_succeeded=%s final_startup_mode=%s",
                DB_PATH,
                is_database_valid(DB_PATH, logger_instance=logger),
                is_database_ready_for_production(DB_PATH, logger_instance=logger),
                recovery_attempted,
                cloud_restore_used,
                "restored_from_cloud" if cloud_restore_used else "local_production_ready",
            )
            final_health = get_database_health_snapshot(DB_PATH, logger_instance=logger)
            return _build_startup_result(
                ok=True,
                stage="fallback_complete",
                reason="startup completed in fallback mode",
                db_path=final_health["db_path"],
                file_exists=final_health["file_exists"],
                structurally_valid=final_health["structural_valid"],
                production_ready=final_health["production_ready"],
                company_count=final_health["company_count"],
                recovery_attempted=recovery_attempted,
                recovery_succeeded=cloud_restore_used,
                startup_mode="restored_from_cloud" if cloud_restore_used else "local_production_ready",
                cloud_backup_company_count=startup_cloud_backup_company_count,
            )

        current_version = _get_schema_version(conn)
        pending_migrations = [migration for migration in ORDERED_MIGRATIONS if migration[0] > current_version]
        before_counts = _snapshot_critical_row_counts(conn)
        logger.info(
            "Database startup validation before migrations: company_count=%s row_counts=%s",
            before_counts.get("companies", 0),
            before_counts,
        )
        conn.commit()
        conn.close()
        conn = None

        if pending_migrations:
            backup_path = create_timestamped_backup(DB_PATH, logger=logger, reason="pre_migration")
            if not backup_path or not os.path.exists(backup_path):
                raise RuntimeError("Backup was not created; aborting migration run.")

        conn = _open_sqlite_connection()
        _ensure_migration_metadata_tables(conn)
        for version, description, migration_fn in pending_migrations:
            migration_before_counts = _snapshot_critical_row_counts(conn)
            logger.info("Starting migration v%s: %s", version, description)
            try:
                conn.execute("BEGIN")
                migration_fn(conn)
                migration_after_counts = _snapshot_critical_row_counts(conn)
                count_failures = validate_row_counts(migration_before_counts, migration_after_counts)
                if count_failures:
                    raise RuntimeError(
                        f"Migration v{version} reduced protected row counts: {_format_count_drop_message(count_failures)}"
                    )
                _record_schema_version(conn, version, description)
                _log_migration_event(
                    conn,
                    version,
                    description,
                    "applied",
                    backup_path=backup_path,
                    before_counts=migration_before_counts,
                    after_counts=migration_after_counts,
                    details="Migration applied successfully.",
                )
                conn.commit()
                logger.info(
                    "Completed migration v%s: company_count_before=%s company_count_after=%s",
                    version,
                    migration_before_counts.get("companies", 0),
                    migration_after_counts.get("companies", 0),
                )
            except Exception as exc:
                conn.rollback()
                conn.execute("BEGIN")
                _log_migration_event(
                    conn,
                    version,
                    description,
                    "failed",
                    backup_path=backup_path,
                    before_counts=migration_before_counts,
                    after_counts=migration_before_counts,
                    details=str(exc),
                )
                conn.commit()
                raise

        conn.execute("BEGIN")
        _run_lightweight_integrity_checks(conn)
        _mark_database_startup_identity(conn)
        after_counts = _snapshot_critical_row_counts(conn)
        count_failures = validate_row_counts(before_counts, after_counts)
        if count_failures:
            raise RuntimeError(
                f"Startup validation detected row-count loss: {_format_count_drop_message(count_failures)}"
            )
        conn.commit()
        logger.info(
            "Database startup validation after migrations: company_count=%s row_counts=%s",
            after_counts.get("companies", 0),
            after_counts,
        )
        logger.info(
            "Database startup completed: db_path=%s db_valid=%s production_ready=%s recovery_attempted=%s recovery_succeeded=%s final_startup_mode=%s",
            DB_PATH,
            is_database_valid(DB_PATH, logger_instance=logger),
            is_database_ready_for_production(DB_PATH, logger_instance=logger),
            recovery_attempted,
            cloud_restore_used,
            "restored_from_cloud" if cloud_restore_used else "local_production_ready",
        )
        final_health = get_database_health_snapshot(DB_PATH, logger_instance=logger)
        final_schema_version = _get_schema_version(conn)
        logger.info(
            "Local restore post-startup validation: company_count_after_restore=%s migration_success=%s schema_version=%s",
            final_health["company_count"],
            "Yes",
            final_schema_version,
        )
        if restore_guard.get("active"):
            if int(final_health.get("company_count") or 0) > 0:
                _clear_restore_guard_state(logger_instance=logger)
                logger.info(
                    "Local restore guard cleared after successful startup validation: company_count=%s schema_version=%s",
                    final_health["company_count"],
                    final_schema_version,
                )
            else:
                logger.warning(
                    "Local restore guard remains active because company_count is still zero after startup: company_count=%s schema_version=%s",
                    final_health["company_count"],
                    final_schema_version,
                )
        return _build_startup_result(
            ok=True,
            stage="startup_complete",
            reason="database startup completed successfully",
            db_path=final_health["db_path"],
            file_exists=final_health["file_exists"],
            structurally_valid=final_health["structural_valid"],
            production_ready=final_health["production_ready"],
            company_count=final_health["company_count"],
            recovery_attempted=recovery_attempted,
            recovery_succeeded=cloud_restore_used,
            startup_mode="restored_from_cloud" if cloud_restore_used else "local_production_ready",
            cloud_backup_company_count=startup_cloud_backup_company_count,
        )
    except Exception as exc:
        failure_stage = "startup_exception"
        failure_reason = sanitize_error_message(exc)
        logger.error("Canonical database startup failed: stage=%s reason=%s", failure_stage, failure_reason)
        if conn:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            conn.close()
            conn = None
        logger.warning(
            "Automatic database restore is disabled in the hotfix path; existing database file has not been intentionally overwritten."
        )
        failed_health = get_database_health_snapshot(DB_PATH, logger_instance=logger)
        logger.error(
            "Database startup final failure reason: stage=%s reason=%s db_path=%s db_exists=%s db_valid=%s production_ready=%s company_count=%s recovery_attempted=%s recovery_succeeded=%s",
            failure_stage,
            failure_reason,
            failed_health["db_path"],
            failed_health["file_exists"],
            failed_health["structural_valid"],
            failed_health["production_ready"],
            failed_health["company_count"],
            recovery_attempted,
            cloud_restore_used,
        )
        return _build_startup_result(
            ok=False,
            stage=failure_stage,
            reason=failure_reason,
            db_path=failed_health["db_path"],
            file_exists=failed_health["file_exists"],
            structurally_valid=failed_health["structural_valid"],
            production_ready=failed_health["production_ready"],
            company_count=failed_health["company_count"],
            recovery_attempted=recovery_attempted,
            recovery_succeeded=cloud_restore_used,
            startup_mode="startup_failed",
            cloud_backup_company_count=startup_cloud_backup_company_count,
        )
    finally:
        if conn:
            conn.close()


def init_db():
    """
    Public compatibility entry point.
    Runs the canonical startup flow and never performs reset-style initialization.
    """
    return startup_database()

# =================================================================
# 4. UTILITY FUNCTIONS
# =================================================================

def _classify_audit_action(action):
    normalized = str(action or "").strip().lower()
    action_map = {
        "create": ("create", "created", "deploy", "register", "saved"),
        "edit": ("edit", "update", "updated", "modify", "modified"),
        "approve": ("approve", "approved"),
        "post": ("post", "posted", "journal", "payment"),
        "reverse": ("reverse", "reversal"),
        "void": ("void", "voided", "cancel", "cancelled", "archive", "wipe"),
        "auth": ("login", "logout", "authentication", "password"),
        "backup_restore": ("backup", "restore", "recovery", "vault"),
        "admin": ("admin", "license", "subscription", "system"),
    }
    for action_type, tokens in action_map.items():
        if any(token in normalized for token in tokens):
            return action_type
    return "other"


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
    """Logs security events to the audit trail without forcing caller transactions to commit early."""
    try:
        was_in_transaction = bool(getattr(conn, "in_transaction", False))
        columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_logs)").fetchall()}
        event_id = f"AUD-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        if {"action_type", "document_ref", "before_after_summary", "event_id"}.issubset(columns):
            conn.execute(
                """
                INSERT INTO audit_logs (
                    company_key, user_role, action, module_name, details, branch_id,
                    action_type, document_ref, before_after_summary, event_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_key,
                    user_role,
                    action,
                    module_name,
                    details,
                    branch_id,
                    action_type or _classify_audit_action(action),
                    document_ref,
                    before_after_summary,
                    event_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO audit_logs (company_key, user_role, action, module_name, details, branch_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (company_key, user_role, action, module_name, details, branch_id),
            )
        if not was_in_transaction:
            conn.commit()
    except Exception as e:
        logger.warning("Audit log failed: %s", sanitize_error_message(e))


def get_audit_operations_summary(conn=None, company_key=None, limit=50):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_logs)").fetchall()}
        action_type_expr = "COALESCE(NULLIF(action_type, ''), 'other')" if "action_type" in columns else "'legacy'"
        where_clause = "WHERE company_key = ?" if company_key else ""
        params = (company_key,) if company_key else ()
        action_rows = conn.execute(
            f"""
            SELECT {action_type_expr} AS action_type, COUNT(*) AS event_count
            FROM audit_logs
            {where_clause}
            GROUP BY {action_type_expr}
            ORDER BY event_count DESC
            """,
            params,
        ).fetchall()
        recent_rows = conn.execute(
            f"""
            SELECT timestamp, company_key, user_role, action, module_name,
                   {action_type_expr} AS action_type,
                   details
            FROM audit_logs
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            params + (int(limit),),
        ).fetchall()
        return {
            "ok": True,
            "action_counts": [dict(row) for row in action_rows],
            "recent_events": [dict(row) for row in recent_rows],
            "enhanced_columns_present": {"action_type", "document_ref", "before_after_summary", "event_id"}.issubset(columns),
        }
    except Exception as exc:
        logger.warning("Audit operations summary unavailable: %s", sanitize_error_message(exc))
        return {"ok": False, "reason": str(exc), "action_counts": [], "recent_events": [], "enhanced_columns_present": False}
    finally:
        if owns_connection and conn:
            conn.close()

def get_company_data(company_key):
    """Retrieves full profile for a specific license."""
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM companies WHERE key = ?", (company_key,)).fetchone()
    finally:
        conn.close()

def run_manual_query(query, params=(), commit=False):
    """Executes custom SQL for maintenance or debugging."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if commit:
            conn.commit()
            return True
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error("Manual Query Error: %s", sanitize_error_message(e))
        return None
    finally:
        conn.close()

# Start Database on Script Load
if __name__ == "__main__":
    init_db()
