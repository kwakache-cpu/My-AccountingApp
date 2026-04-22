import sqlite3
import logging
from datetime import datetime
import os
import shutil
import json

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
    "journal_entries",
    "journal_lines",
    "chart_of_accounts",
    "system_settings",
    "schema_version",
)
DATABASE_PRODUCTION_REQUIRED_TABLES = DATABASE_REQUIRED_TABLES + (
    "database_identity",
)
FIREBASE_RECOVERY_APP = None
FIREBASE_RECOVERY_BUCKET_NAME = None


def get_firebase_runtime_config():
    return {
        "databaseURL": str(_read_runtime_secret("FIREBASE_DATABASE_URL", FIREBASE_DATABASE_URL) or "").strip(),
        "key_path": FIREBASE_KEY_PATH,
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


def get_firebase_service_account_info():
    firebase_key_path = str(FIREBASE_KEY_PATH or "").strip()
    inline_json = _read_runtime_secret("FIREBASE_SERVICE_ACCOUNT_JSON", None)
    invalid_secret_reason = (
        "invalid JSON in FIREBASE_SERVICE_ACCOUNT_JSON; likely cause: unescaped newline or control character in private_key"
    )
    secret_exists_in_streamlit = False
    if st is not None:
        try:
            secret_exists_in_streamlit = "FIREBASE_SERVICE_ACCOUNT_JSON" in st.secrets
        except Exception:
            secret_exists_in_streamlit = False
    inline_json_length = len(str(inline_json)) if inline_json not in (None, "") else 0
    logger.info(
        "Firebase secret diagnostics: secret_exists_in_streamlit=%s provided_length=%s",
        secret_exists_in_streamlit,
        inline_json_length,
    )

    if inline_json not in (None, ""):
        try:
            service_account_info = json.loads(str(inline_json))
            logger.info("Firebase secret diagnostics: json.loads succeeded")
            logger.info("Firebase credentials loaded from secrets")
            return {
                "ok": True,
                "source": "secrets",
                "service_account_info": service_account_info,
                "key_path": firebase_key_path,
            }
        except Exception as exc:
            logger.warning(
                "Firebase secret diagnostics: json.loads failed exception_type=%s message=%s",
                type(exc).__name__,
                str(exc),
            )
            logger.warning("Firebase credentials missing: %s", invalid_secret_reason)
            return {
                "ok": False,
                "source": "secrets",
                "reason": f"{invalid_secret_reason}. Parser detail: {exc}",
                "key_path": firebase_key_path,
            }

    if firebase_key_path and os.path.exists(firebase_key_path):
        try:
            with open(firebase_key_path, "r", encoding="utf-8") as firebase_file:
                service_account_info = json.load(firebase_file)
            logger.info("Firebase credentials loaded from file")
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
                "reason": f"Firebase credentials from file are invalid: {exc}",
                "key_path": firebase_key_path,
            }

    logger.warning("Firebase credentials missing")
    return {
        "ok": False,
        "source": "missing",
        "reason": "Firebase credentials not found in file or secrets",
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
            logger.warning("Firebase recovery credentials are unavailable: %s", credentials_result.get("reason"))
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
            logger.warning("Firebase recovery client lookup failed: %s", exc)
            return None
    except Exception as exc:
        logger.warning("Firebase recovery client initialization failed: %s", exc)
        return None


def _get_firebase_recovery_bucket():
    app = _init_firebase_recovery_client()
    if app is None or storage is None:
        return None
    try:
        return storage.bucket(app=app)
    except Exception as exc:
        logger.warning("Firebase recovery bucket unavailable: %s", exc)
        return None


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
        conn = sqlite3.connect(DB_PATH)
        conn.close()
        logger.info("Created local database file at: %s", DB_PATH)
    elif not os.path.exists(DB_PATH):
        logger.warning("Production mode detected missing database file; blank database creation is blocked at startup: %s", DB_PATH)


def _open_sqlite_connection(path=DB_PATH):
    if os.path.abspath(path) == os.path.abspath(DB_PATH) and ERP_PRODUCTION_MODE and not os.path.exists(path):
        raise sqlite3.OperationalError(
            f"Production database file is missing and cannot be recreated outside startup recovery: {path}"
        )
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


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
            last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO database_identity (instance_id)
        SELECT ?
        WHERE NOT EXISTS (SELECT 1 FROM database_identity)
        """,
        (f"{os.path.basename(DB_PATH)}::{int(datetime.now().timestamp())}",),
    )
    conn.execute("UPDATE database_identity SET last_verified_at = CURRENT_TIMESTAMP")


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
        "file_exists": bool(db_path and os.path.exists(db_path)),
        "structural_valid": False,
        "production_ready": False,
        "company_count": 0,
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
        required_tables = set(DATABASE_PRODUCTION_REQUIRED_TABLES)
        existing_tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        missing_tables = sorted(required_tables.difference(existing_tables))
        if missing_tables:
            report["failures"].append(f"missing required production tables: {', '.join(missing_tables)}")
        report["company_count"] = get_database_company_count(db_path=db_path, logger_instance=logger_instance)
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
        "file_exists": report["file_exists"],
        "structural_valid": report["structural_valid"],
        "production_ready": report["production_ready"],
        "company_count": report["company_count"],
        "readiness_failures": report["failures"],
    }


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
):
    return {
        "ok": bool(ok),
        "stage": str(stage),
        "reason": str(reason),
        "db_path": db_path,
        "file_exists": bool(file_exists),
        "structurally_valid": bool(structurally_valid),
        "production_ready": bool(production_ready),
        "company_count": int(company_count or 0),
        "recovery_attempted": bool(recovery_attempted),
        "recovery_succeeded": bool(recovery_succeeded),
    }


def attempt_production_database_recovery(force_restore=True):
    logger.info("Trusted backup recovery invoked: db_path=%s force_restore=%s", DB_PATH, force_restore)
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

    bucket = _get_firebase_recovery_bucket()
    if bucket is None:
        access_reason = diagnostics["credential_error"] or "firebase bucket is not accessible"
        logger.error("Trusted backup recovery unavailable because Firebase bucket is not accessible: %s", access_reason)
        return {
            "ok": False,
            "stage": "recovery_source",
            "reason": access_reason,
            "backend": diagnostics["backend"],
            "bucket_name": diagnostics["bucket_name"],
            "object_name": diagnostics["object_name"],
            "recovery_source_found": False,
            "temp_download_succeeded": False,
            "replacement_performed": False,
            "health": local_health,
        }

    temp_restore_path = f"{DB_PATH}.recovery_download"
    try:
        blob = bucket.blob(diagnostics["object_name"])
        try:
            backup_exists = bool(blob.exists())
        except Exception as exc:
            logger.error(
                "Trusted backup presence check failed: backend=%s bucket=%s object=%s error=%s",
                diagnostics["backend"],
                diagnostics["bucket_name"],
                diagnostics["object_name"],
                exc,
            )
            return {
                "ok": False,
                "stage": "recovery_source",
                "reason": f"network or storage permission failure while checking backup object: {exc}",
                "backend": diagnostics["backend"],
                "bucket_name": diagnostics["bucket_name"],
                "object_name": diagnostics["object_name"],
                "recovery_source_found": False,
                "temp_download_succeeded": False,
                "replacement_performed": False,
                "health": local_health,
            }
        logger.info(
            "Trusted backup presence check: backend=%s bucket=%s object=%s exists=%s",
            diagnostics["backend"],
            diagnostics["bucket_name"],
            diagnostics["object_name"],
            backup_exists,
        )
        if not backup_exists:
            logger.error(
                "Trusted backup recovery failed because the cloud backup object does not exist: bucket=%s object=%s",
                diagnostics["bucket_name"],
                diagnostics["object_name"],
            )
            return {
                "ok": False,
                "stage": "recovery_source",
                "reason": "trusted cloud backup object was not found",
                "backend": diagnostics["backend"],
                "bucket_name": diagnostics["bucket_name"],
                "object_name": diagnostics["object_name"],
                "recovery_source_found": False,
                "temp_download_succeeded": False,
                "replacement_performed": False,
                "health": local_health,
            }

        try:
            blob.download_to_filename(temp_restore_path)
        except Exception as exc:
            logger.error(
                "Trusted backup temp download failed: backend=%s bucket=%s object=%s error=%s",
                diagnostics["backend"],
                diagnostics["bucket_name"],
                diagnostics["object_name"],
                exc,
            )
            return {
                "ok": False,
                "stage": "recovery_download",
                "reason": f"backup object exists but download failed: {exc}",
                "backend": diagnostics["backend"],
                "bucket_name": diagnostics["bucket_name"],
                "object_name": diagnostics["object_name"],
                "recovery_source_found": True,
                "temp_download_succeeded": False,
                "replacement_performed": False,
                "health": local_health,
            }
        logger.info(
            "Trusted backup temp download succeeded: backend=%s bucket=%s object=%s temp_path=%s",
            diagnostics["backend"],
            diagnostics["bucket_name"],
            diagnostics["object_name"],
            temp_restore_path,
        )

        downloaded_health = get_database_health_snapshot(temp_restore_path, logger_instance=logger)
        logger.info(
            "Trusted backup validation: temp_path=%s db_exists=%s db_valid=%s production_ready=%s company_count=%s readiness_failures=%s",
            downloaded_health["db_path"],
            downloaded_health["file_exists"],
            downloaded_health["structural_valid"],
            downloaded_health["production_ready"],
            downloaded_health["company_count"],
            "; ".join(downloaded_health.get("readiness_failures", [])) or "none",
        )
        if not downloaded_health["production_ready"]:
            logger.error("Trusted backup recovery aborted because downloaded database is not production-ready.")
            return {
                "ok": False,
                "stage": "recovery_validation",
                "reason": "cloud backup downloaded but failed production-ready check",
                "backend": diagnostics["backend"],
                "bucket_name": diagnostics["bucket_name"],
                "object_name": diagnostics["object_name"],
                "recovery_source_found": True,
                "temp_download_succeeded": True,
                "replacement_performed": False,
                "health": downloaded_health,
            }

        replacement_performed = False
        if os.path.exists(DB_PATH):
            backup_path = create_timestamped_backup(DB_PATH, logger=logger, reason="trusted_recovery")
            logger.info("Created local backup before trusted recovery replacement: %s", backup_path)
            os.replace(temp_restore_path, DB_PATH)
            replacement_performed = True
        else:
            os.rename(temp_restore_path, DB_PATH)
            replacement_performed = True
        logger.info("Trusted backup recovery succeeded and promoted recovered database to %s", DB_PATH)
        final_health = get_database_health_snapshot(DB_PATH, logger_instance=logger)
        logger.info(
            "Trusted backup replacement performed: replaced=%s final_db_exists=%s final_db_valid=%s final_production_ready=%s final_company_count=%s",
            replacement_performed,
            final_health["file_exists"],
            final_health["structural_valid"],
            final_health["production_ready"],
            final_health["company_count"],
        )
        return {
            "ok": True,
            "stage": "recovery_complete",
            "reason": "trusted cloud backup restored successfully",
            "backend": diagnostics["backend"],
            "bucket_name": diagnostics["bucket_name"],
            "object_name": diagnostics["object_name"],
            "recovery_source_found": True,
            "temp_download_succeeded": True,
            "replacement_performed": replacement_performed,
            "health": final_health,
        }
    except Exception as exc:
        logger.error("Trusted backup recovery failed: %s", exc)
        return {
            "ok": False,
            "stage": "recovery_exception",
            "reason": str(exc),
            "backend": diagnostics["backend"],
            "bucket_name": diagnostics["bucket_name"],
            "object_name": diagnostics["object_name"],
            "recovery_source_found": True,
            "temp_download_succeeded": os.path.exists(temp_restore_path),
            "replacement_performed": False,
            "health": get_database_health_snapshot(DB_PATH, logger_instance=logger),
        }
    finally:
        if os.path.exists(temp_restore_path):
            try:
                os.remove(temp_restore_path)
            except OSError:
                pass


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
        logger.warning("Startup schema repair skipped: %s", exc)
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
        "audit_logs": {"details": "TEXT", "branch_id": "TEXT"},
        "customers": {"customer_id": "TEXT", "current_balance": "REAL DEFAULT 0"},
        "customer_transactions": {"branch_id": "TEXT", "reference": "TEXT", "created_by": "TEXT", "transaction_date": "TEXT"},
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
            "reversed_entry_id": "INTEGER",
            "is_voided": "INTEGER DEFAULT 0",
            "voided_at": "TIMESTAMP",
            "voided_by": "TEXT",
            "approval_status": "TEXT DEFAULT 'Posted'",
        },
        "stock_movements": {"branch_id": "TEXT", "reason": "TEXT", "created_by": "TEXT", "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
        "transactions": {"branch_id": "TEXT"},
        "users": {"branch_id": "TEXT"},
        "vouchers": {"status": "TEXT DEFAULT 'Active'", "branch_id": "TEXT", "approval_status": "TEXT DEFAULT 'Draft'", "is_voided": "INTEGER DEFAULT 0", "voided_at": "TIMESTAMP", "voided_by": "TEXT"},
        "payroll": {"status": "TEXT DEFAULT 'Active'"},
        "inventory": {"opening_balance": "REAL DEFAULT 0", "barcode": "TEXT", "inventory_account_id": "INTEGER", "cogs_account_id": "INTEGER"},
        "invoices": {"invoice_number": "TEXT", "input_vat": "REAL DEFAULT 0", "output_vat": "REAL DEFAULT 0", "approval_status": "TEXT DEFAULT 'Draft'"},
        "bills": {"bill_number": "TEXT", "input_vat": "REAL DEFAULT 0", "output_vat": "REAL DEFAULT 0", "approval_status": "TEXT DEFAULT 'Draft'"},
        "payments": {"invoice_id": "INTEGER", "bill_id": "INTEGER", "bank_account_id": "INTEGER", "approval_status": "TEXT DEFAULT 'Draft'"},
        "bank_accounts": {"company_key": "TEXT", "branch_id": "TEXT", "account_name": "TEXT", "account_number": "TEXT", "bank_name": "TEXT", "currency": "TEXT DEFAULT 'GHS'", "account_type": "TEXT", "balance": "REAL DEFAULT 0", "created_by": "TEXT", "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
        "payment_allocations": {"company_key": "TEXT", "payment_id": "INTEGER", "invoice_id": "INTEGER", "bill_id": "INTEGER", "amount": "REAL DEFAULT 0", "currency": "TEXT DEFAULT 'GHS'", "branch_id": "TEXT", "created_by": "TEXT", "allocated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
        "recurring_transactions": {"company_key": "TEXT", "branch_id": "TEXT", "description": "TEXT", "frequency": "TEXT", "next_run_date": "TEXT", "last_run_at": "TIMESTAMP", "is_active": "INTEGER DEFAULT 1", "created_by": "TEXT", "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "source_module": "TEXT", "source_table": "TEXT", "source_id": "INTEGER", "recurrence_payload": "TEXT"},
        "branches": {"contact_number": "TEXT", "branch_manager": "TEXT", "branch_access_key": "TEXT"},
        "fixed_assets": {"opening_book_value": "REAL DEFAULT 0"},
        "suppliers": {"address": "TEXT", "category": "TEXT", "currency": "TEXT DEFAULT 'GHS'", "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
    }

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

    # Specific check for journal_entries branch_id
    cursor.execute("PRAGMA table_info(journal_entries)")
    je_columns = {row[1] for row in cursor.fetchall()}
    if "branch_id" not in je_columns:
        cursor.execute("ALTER TABLE journal_entries ADD COLUMN branch_id TEXT")

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
            account_type = COALESCE(NULLIF(account_type, ''), NULLIF(type, ''), category)
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
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            customer_id INTEGER,
            invoice_number TEXT,
            invoice_date TEXT NOT NULL,
            due_date TEXT,
            status TEXT DEFAULT 'Draft',
            approval_status TEXT DEFAULT 'Draft',
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
            amount REAL DEFAULT 0,
            input_vat REAL DEFAULT 0,
            output_vat REAL DEFAULT 0,
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
            is_locked INTEGER DEFAULT 0,
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


def _ensure_app_compatibility_tables(conn):
    """
    Keep legacy app-facing tables readable during the migration-safe rollout.
    These tables remain additive only and are not used to destroy or replace data.
    """
    cursor = conn.cursor()
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


def _run_lightweight_integrity_checks(conn):
    """
    Lightweight startup validation and additive repairs only.
    This path intentionally avoids any reset-like behavior.
    """
    _ensure_migration_metadata_tables(conn)
    _ensure_database_identity_table(conn)
    ensure_schema_integrity(conn)
    _ensure_app_compatibility_tables(conn)


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
        return _open_sqlite_connection()
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
                plan_type TEXT DEFAULT 'Basic',
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
        cursor.execute("PRAGMA table_info(inventory)")
        inventory_columns = {row[1] for row in cursor.fetchall()}
        inventory_column_defs = {
            "company_key": "TEXT",
            "item_code": "TEXT",
            "barcode": "TEXT",
            "category": "TEXT",
            "description": "TEXT",
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
                month TEXT NOT NULL,
                year TEXT NOT NULL,
                payment_status TEXT DEFAULT 'Unpaid',
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
                useful_life_years REAL DEFAULT 0,
                residual_value REAL DEFAULT 0,
                depreciation_method TEXT DEFAULT 'Straight-line',
                depreciation_rate REAL DEFAULT 0,
                accumulated_depreciation REAL DEFAULT 0,
                book_value REAL NOT NULL,
                last_depreciation_date TEXT,
                location TEXT,
                status TEXT DEFAULT 'Active',
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
        """)
        cursor.execute("PRAGMA table_info(fixed_assets)")
        fixed_asset_columns = {row[1] for row in cursor.fetchall()}
        fixed_asset_column_defs = {
            "company_key": "TEXT",
            "asset_category": "TEXT",
            "purchase_date": "TEXT",
            "cost": "REAL DEFAULT 0",
            "opening_book_value": "REAL DEFAULT 0",
            "useful_life_years": "REAL DEFAULT 0",
            "residual_value": "REAL DEFAULT 0",
            "depreciation_method": "TEXT DEFAULT 'Straight-line'",
            "depreciation_rate": "REAL DEFAULT 0",
            "accumulated_depreciation": "REAL DEFAULT 0",
            "book_value": "REAL DEFAULT 0",
            "last_depreciation_date": "TEXT",
            "location": "TEXT",
            "status": "TEXT DEFAULT 'Active'",
        }
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
                ip_address TEXT
            )
        """)
        cursor.execute("PRAGMA table_info(audit_logs)")
        audit_columns = {row[1] for row in cursor.fetchall()}
        audit_column_defs = {
            "branch_id": "TEXT",
            "details": "TEXT",
            "ip_address": "TEXT",
        }
        for column_name, column_def in audit_column_defs.items():
            if column_name not in audit_columns:
                cursor.execute(f"ALTER TABLE audit_logs ADD COLUMN {column_name} {column_def}")

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
        logger.error(f"DATABASE INITIALIZATION ERROR: {e}")
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
    logger.info("Database startup entered: db_path=%s", DB_PATH)
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
            logger.warning("Preflight integrity preparation failed before production readiness evaluation: %s", exc)
        finally:
            if preflight_conn:
                preflight_conn.close()
    db_health_before_startup = get_database_health_snapshot(DB_PATH, logger_instance=logger)
    cloud_restore_used = False
    recovery_attempted = False
    failure_reason = "; ".join(db_health_before_startup.get("readiness_failures", [])) or "local database is not production-ready"
    failure_stage = "startup_validation"
    logger.info(
        "Database startup path selected: base_dir=%s db_dir=%s db_path=%s eka_data_dir=%s db_exists=%s db_valid=%s production_ready=%s company_count=%s readiness_failures=%s production_mode=%s safe_mode=%s advanced_helpers_available=%s db_upgrade_safety=%s erp_migrations=%s recovery_attempted=%s recovery_succeeded=%s cloud_restore_disabled=%s",
        BASE_DIR,
        DB_DIR,
        db_health_before_startup["db_path"],
        os.getenv("EKA_DATA_DIR"),
        db_health_before_startup["file_exists"],
        db_health_before_startup["structural_valid"],
        db_health_before_startup["production_ready"],
        db_health_before_startup["company_count"],
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
    if ERP_PRODUCTION_MODE and not db_health_before_startup["production_ready"]:
        logger.warning(
            "Production startup detected missing or non-production-ready database. Automatic recovery will be attempted: db_path=%s",
            DB_PATH,
        )
        recovery_attempted = True
        recovery_result = attempt_production_database_recovery(force_restore=True)
        cloud_restore_used = bool(recovery_result.get("ok"))
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
            conn.commit()
            logger.info(
                "Database startup completed in fallback mode: db_path=%s db_valid=%s production_ready=%s recovery_attempted=%s recovery_succeeded=%s",
                DB_PATH,
                is_database_valid(DB_PATH, logger_instance=logger),
                is_database_ready_for_production(DB_PATH, logger_instance=logger),
                recovery_attempted,
                cloud_restore_used,
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
            "Database startup completed: db_path=%s db_valid=%s production_ready=%s recovery_attempted=%s recovery_succeeded=%s",
            DB_PATH,
            is_database_valid(DB_PATH, logger_instance=logger),
            is_database_ready_for_production(DB_PATH, logger_instance=logger),
            recovery_attempted,
            cloud_restore_used,
        )
        final_health = get_database_health_snapshot(DB_PATH, logger_instance=logger)
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
        )
    except Exception as exc:
        failure_stage = "startup_exception"
        failure_reason = str(exc)
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

def log_audit_action(conn, company_key, user_role, action, module_name, details=None, branch_id=None):
    """Logs security events to the audit trail."""
    try:
        conn.execute("""
            INSERT INTO audit_logs (company_key, user_role, action, module_name, details, branch_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (company_key, user_role, action, module_name, details, branch_id))
        conn.commit()
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

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
        logger.error(f"Manual Query Error: {e}")
        return None
    finally:
        conn.close()

# Start Database on Script Load
if __name__ == "__main__":
    init_db()
