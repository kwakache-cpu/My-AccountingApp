from __future__ import annotations

from datetime import datetime
import json
import logging
import sqlite3

import pandas as pd

from database import (
    db_column_exists,
    db_table_exists,
    execute_db_write_transaction,
    execute_portable_query,
    execute_portable_write,
    ensure_insert_sql_returning,
    fetch_scalar,
    get_active_db_backend,
    get_connection,
    get_inserted_id,
    list_columns,
    list_tables,
    log_audit_action as database_log_audit_action,
    row_get,
    row_to_dict,
    rows_to_dicts,
    sql_cast_as_date,
    sql_date_on_or_after,
    sql_date_on_or_before,
    sql_group_concat,
    sql_year_month_equals,
    with_retry_on_lock,
)


LEGACY_TABLES = {"vouchers", "transactions"}
LEGACY_MIRRORING_ENABLED = False
logger = logging.getLogger(__name__)


def _resolve_date(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _normal_balance(account_type):
    normalized = str(account_type or "").strip().title()
    return "debit" if normalized in ("Asset", "Expense") else "credit"


VALID_ACCOUNT_TYPES = {"Asset", "Liability", "Equity", "Income", "Expense"}
VALID_DOCUMENT_CONTROL_STATUSES = {"Draft", "Submitted", "Approved", "Posted", "Cancelled", "Voided", "Active"}
CONTROLLED_SOURCE_TABLES = {
    "invoices",
    "bills",
    "payments",
    "stock_movements",
    "vouchers",
    "fixed_assets",
    "payroll",
    "pos_sales",
    "pos_returns",
    "inventory_import_batches",
}
CONTROL_ACCOUNT_NAMES = {"Accounts Receivable", "Accounts Payable", "Inventory"}
UNIFIED_POSTING_ENGINE_VERSION = "phase7_unified_posting_engine_v1"
HEADER_ACCOUNT_NAMES = {
    "Assets",
    "Current Assets",
    "Non-Current Assets",
    "Liabilities",
    "Current Liabilities",
    "Equity",
    "Income",
    "Expenses",
}


def _normalize_account_lookup_name(value):
    return " ".join(str(value or "").strip().lower().split())


def _load_chart_account_rows(conn):
    return execute_portable_query(
        conn,
        f"""
        SELECT
            id,
            {_coa_name_expression()} AS account_name,
            {_coa_type_expression()} AS account_type,
            COALESCE(posting_allowed, 1) AS posting_allowed,
            COALESCE(control_account, 0) AS control_account,
            COALESCE(allow_manual_posting, 1) AS allow_manual_posting,
            COALESCE(is_active, 1) AS is_active
        FROM chart_of_accounts
        """
    ).fetchall()


def _find_account_row_by_normalized_name(conn, account_name, aliases=None):
    aliases = aliases or []
    candidate_names = []
    for value in [account_name, *aliases]:
        normalized_value = _normalize_account_lookup_name(value)
        if normalized_value and normalized_value not in candidate_names:
            candidate_names.append(normalized_value)
    if not candidate_names:
        return None
    for row in _load_chart_account_rows(conn):
        normalized_existing = _normalize_account_lookup_name(row["account_name"])
        if normalized_existing in candidate_names:
            return row
    return None


def _log_posting_engine_event(conn, level, message):
    try:
        conn.execute(
            """
            INSERT INTO system_logs (timestamp, level, module_name, message)
            VALUES (CURRENT_TIMESTAMP, ?, 'Unified Posting Engine', ?)
            """,
            (str(level or "INFO").upper(), str(message or "")),
        )
    except Exception:
        logger.debug("Posting engine event logging skipped.", exc_info=True)


def _persist_posting_engine_event(level, message):
    conn = None
    try:
        conn = get_connection()
        _log_posting_engine_event(conn, level, message)
        conn.commit()
    except Exception:
        logger.debug("Posting engine event persistence skipped.", exc_info=True)
    finally:
        if conn:
            conn.close()


def _assert_posting_role_allowed(user_role):
    if user_role is None:
        return
    normalized_role = str(user_role or "").strip()
    try:
        from enterprise_services import has_permission

        allowed = has_permission(normalized_role, "post_accounting_document")
    except Exception:
        allowed = normalized_role in {"Dev", "Master Admin", "Sub-Admin", "Bookkeeper", "Branch_Bookkeeper"}
    if not allowed:
        raise PermissionError(f"Role '{normalized_role or 'Unknown'}' is not allowed to post accounting impact.")


def _resolve_effective_posting_role(user_role, created_by):
    if user_role is not None:
        return user_role
    candidate_role = str(created_by or "").strip()
    if not candidate_role:
        return None
    try:
        from enterprise_services import has_permission

        return candidate_role if has_permission(candidate_role, "post_accounting_document") else None
    except Exception:
        return candidate_role if candidate_role in {"Dev", "Master Admin", "Sub-Admin", "Bookkeeper", "Branch_Bookkeeper"} else None


def normalize_document_status(value, default="Draft"):
    normalized = str(value or "").strip().title()
    return normalized if normalized in VALID_DOCUMENT_CONTROL_STATUSES else str(default)


def _is_posting_status(value):
    return normalize_document_status(value, default="Draft") == "Posted"


def _source_document_columns(conn, table_name):
    return {column["name"] for column in list_columns(conn, table_name)}


def _sync_source_document_posting(conn, source_table, source_id, entry_id, posting_user=None, source_type=None):
    if not source_table or not source_id:
        return
    normalized_source_table = str(source_table).strip().lower()
    if normalized_source_table not in CONTROLLED_SOURCE_TABLES:
        return
    source_columns = _source_document_columns(conn, normalized_source_table)
    update_parts = []
    params = []
    if (
        normalized_source_table == "pos_sales"
        and "cogs" in str(source_type or "").strip().lower()
        and "cogs_posted_entry_id" in source_columns
    ):
        update_parts.append("cogs_posted_entry_id = ?")
        params.append(int(entry_id))
    elif "posted_entry_id" in source_columns:
        update_parts.append("posted_entry_id = ?")
        params.append(int(entry_id))
    if "last_journal_sync_at" in source_columns:
        update_parts.append("last_journal_sync_at = CURRENT_TIMESTAMP")
    if "approval_status" in source_columns:
        update_parts.append("approval_status = 'Posted'")
    if "approved_at" in source_columns:
        update_parts.append("approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP)")
    if posting_user and "approved_by" in source_columns:
        update_parts.append("approved_by = COALESCE(approved_by, ?)")
        params.append(str(posting_user))
    if not update_parts:
        return
    params.append(int(source_id))
    conn.execute(
        f"UPDATE {normalized_source_table} SET {', '.join(update_parts)} WHERE id = ?",
        tuple(params),
    )


def _period_locked(conn, company_key, entry_date):
    if not company_key or not entry_date:
        return False
    period_columns = {column["name"] for column in list_columns(conn, "accounting_periods")}
    status_clause = ""
    if "status" in period_columns:
        status_clause = " OR lower(COALESCE(status, 'Open')) IN ('closed', 'locked')"
    row = execute_portable_query(
        conn,
        f"""
        SELECT 1
        FROM accounting_periods
        WHERE company_key = ?
          AND (COALESCE(is_locked, 0) = 1{status_clause})
          AND date(?) BETWEEN date(start_date) AND date(end_date)
        LIMIT 1
        """,
        (company_key, _resolve_date(entry_date)),
    ).fetchone()
    return bool(row)


def _period_label_for_date(entry_date):
    return pd.Timestamp(_resolve_date(entry_date)).strftime("%Y-%m")


def get_period_control_diagnostics(company_key, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        period_columns = {column["name"] for column in list_columns(conn, "accounting_periods")}
        has_status = "status" in period_columns
        current_period = _period_label_for_date(as_of_date or datetime.now().date())
        rows = execute_portable_query(
            conn,
            """
            SELECT period_label,
                   start_date,
                   end_date,
                   COALESCE(is_locked, 0) AS is_locked,
                   {status_expr} AS status,
                   locked_at,
                   locked_by
            FROM accounting_periods
            WHERE company_key = ?
            ORDER BY period_label DESC
            """.format(status_expr="COALESCE(NULLIF(status, ''), CASE WHEN COALESCE(is_locked, 0) = 1 THEN 'Locked' ELSE 'Open' END)" if has_status else "CASE WHEN COALESCE(is_locked, 0) = 1 THEN 'Locked' ELSE 'Open' END"),
            (company_key,),
        ).fetchall()
        period_counts = {"Open": 0, "Closed": 0, "Locked": 0}
        normalized_rows = []
        current_status = "Open"
        for row in rows:
            status = str(row_get(row, "status", "Open") or "Open").strip().title()
            if bool(int(row_get(row, "is_locked", 0) or 0)):
                status = "Locked"
            if status not in period_counts:
                status = "Open"
            period_counts[status] += 1
            item = {
                "period_label": row_get(row, "period_label"),
                "start_date": row_get(row, "start_date"),
                "end_date": row_get(row, "end_date"),
                "status": status,
                "is_locked": bool(int(row_get(row, "is_locked", 0) or 0)),
                "locked_at": row_get(row, "locked_at"),
                "locked_by": row_get(row, "locked_by"),
            }
            normalized_rows.append(item)
            if str(row_get(row, "period_label")) == current_period:
                current_status = status
        warnings = []
        if not has_status:
            warnings.append("accounting_periods.status column is missing; legacy is_locked fallback is in use.")
        if current_status in {"Closed", "Locked"}:
            warnings.append(f"Current reporting period {current_period} is {current_status}; posting is blocked.")
        return {
            "current_period": current_period,
            "current_period_status": current_status,
            "period_counts": period_counts,
            "periods": normalized_rows,
            "posting_blocked_for_statuses": ["Closed", "Locked"],
            "warnings": warnings,
            "ok": not warnings,
        }
    finally:
        if owns_connection and conn:
            conn.close()


def _system_setting_value(conn, column_name, default=None):
    try:
        columns = {column["name"] for column in list_columns(conn, "system_settings")}
        if column_name not in columns:
            return default
        row = execute_portable_query(
            conn,
            f"SELECT {column_name} AS value FROM system_settings WHERE id = 1",
        ).fetchone()
        return row_get(row, "value", row_get(row, 0, default)) if row else default
    except sqlite3.Error:
        return default


def _legacy_mirror_mode(conn):
    if not LEGACY_MIRRORING_ENABLED:
        return "off"
    return str(_system_setting_value(conn, "legacy_mirror_mode", "mirror") or "mirror").strip().lower()


def is_legacy_mirroring_enabled(conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        return _legacy_mirror_mode(conn) in {"mirror", "dual_write"}
    finally:
        if owns_connection and conn:
            conn.close()


def _assert_source_document_postable(conn, source_table, source_id):
    if not source_table or not source_id:
        return
    normalized_table = str(source_table).strip().lower()
    if normalized_table not in CONTROLLED_SOURCE_TABLES:
        return
    columns = _source_document_columns(conn, normalized_table)
    if "approval_status" not in columns and "status" not in columns:
        return
    approval_expr = "approval_status" if "approval_status" in columns else "status"
    row = conn.execute(
        f"SELECT {approval_expr} AS approval_status FROM {normalized_table} WHERE id = ? LIMIT 1",
        (int(source_id),),
    ).fetchone()
    status = normalize_document_status(row["approval_status"] if row else "", default="Draft")
    if status != "Posted":
        raise ValueError(
            f"{normalized_table[:-1].title() if normalized_table.endswith('s') else normalized_table.title()} "
            f"{source_id} cannot post to the journal while approval_status is '{status or 'Draft'}'. "
            "Only documents with Posting State 'Posted' can create ledger impact."
        )


def _assert_no_duplicate_source_posting(conn, company_key, source_table, source_id, branch_id=None, source_type=None):
    if not source_table or not source_id:
        return
    normalized_table = str(source_table).strip().lower()
    if normalized_table not in CONTROLLED_SOURCE_TABLES:
        return
    query = """
        SELECT id
        FROM journal_entries
        WHERE company_key = ?
          AND lower(COALESCE(source_table, '')) = lower(?)
          AND source_id = ?
          AND COALESCE(is_voided, 0) = 0
          AND COALESCE(approval_status, 'Posted') = 'Posted'
    """
    params = [company_key, normalized_table, int(source_id)]
    if normalized_table == "pos_sales" and source_type:
        query += " AND lower(COALESCE(source_type, '')) = lower(?)"
        params.append(str(source_type))
    if branch_id:
        query += " AND branch_id = ?"
        params.append(branch_id)
    query += " LIMIT 1"
    existing = conn.execute(query, tuple(params)).fetchone()
    if existing:
        raise ValueError(
            f"{normalized_table[:-1].title() if normalized_table.endswith('s') else normalized_table.title()} "
            f"{source_id} is already posted as journal entry {existing['id']}. Use a reversal, void, or controlled correction workflow."
        )


def _coa_name_expression():
    return "COALESCE(NULLIF(name, ''), NULLIF(account_name, ''), '')"


def _coa_type_expression():
    return "COALESCE(NULLIF(type, ''), NULLIF(account_type, ''), NULLIF(category, ''), 'Asset')"


def _coa_code_expression():
    return "COALESCE(NULLIF(account_code, ''), NULLIF(code, ''), '')"


DEFAULT_SYSTEM_ACCOUNT_CODE_MAP = {
    "accounts receivable": "1100",
    "accounts payable": "2100",
    "cash": "1000",
    "bank": "1010",
    "mobile money": "1020",
    "inventory": "1200",
    "sales revenue": "4000",
    "cost of goods sold": "5000",
    "vat payable": "2200",
    "owner capital": "3000",
    "loan payable": "2300",
    "salary expense": "5100",
}


def resolve_display_account_code(account_code):
    """Return a stable display code for reports; use em dash when no code exists."""
    code = str(account_code or "").strip()
    return code if code else "—"


def backfill_default_account_codes(conn, dry_run=False):
    """
    Populate blank code/account_code fields for known default system accounts only.

    Idempotent and non-destructive: never overwrites an existing code.
    """
    stats = {
        "updated": 0,
        "skipped_has_code": 0,
        "skipped_unknown_account": 0,
        "dry_run": bool(dry_run),
    }
    if conn is None or not db_table_exists(conn, "chart_of_accounts"):
        return stats
    rows = execute_portable_query(
        conn,
        f"""
        SELECT
            id,
            {_coa_name_expression()} AS account_name,
            {_coa_code_expression()} AS account_code
        FROM chart_of_accounts
        ORDER BY id
        """,
    ).fetchall()
    for row in rows:
        account_name = str(row_get(row, "account_name", "") or "").strip()
        existing_code = str(row_get(row, "account_code", "") or "").strip()
        if existing_code:
            stats["skipped_has_code"] += 1
            continue
        default_code = DEFAULT_SYSTEM_ACCOUNT_CODE_MAP.get(account_name.lower())
        if not default_code:
            stats["skipped_unknown_account"] += 1
            continue
        if not dry_run:
            execute_portable_write(
                conn,
                """
                UPDATE chart_of_accounts
                SET code = ?, account_code = ?
                WHERE id = ?
                  AND (code IS NULL OR TRIM(code) = '')
                  AND (account_code IS NULL OR TRIM(account_code) = '')
                """,
                (default_code, default_code, int(row_get(row, "id"))),
            )
        stats["updated"] += 1
    return stats


def ensure_default_account_codes_integrity(conn):
    """Startup-only helper to backfill blank codes on known default accounts."""
    try:
        return backfill_default_account_codes(conn, dry_run=False)
    except Exception as exc:
        logger.warning(
            "Default account code backfill skipped: %s",
            exc,
        )
        return {"updated": 0, "skipped_has_code": 0, "skipped_unknown_account": 0, "dry_run": False, "failed": True}


def _inventory_value_query(conn, company_key, branch_id=None):
    inventory_columns = {column["name"] for column in list_columns(conn, "inventory")}
    query = """
        SELECT COALESCE(SUM(COALESCE(qty, 0) * COALESCE(cost_price, 0)), 0) AS inventory_value
        FROM inventory
        WHERE company_key = ?
    """
    params = [company_key]
    if branch_id and "branch_id" in inventory_columns:
        query += " AND branch_id = ?"
        params.append(branch_id)
    return query, tuple(params)


def _safe_doc_status(row, columns):
    if "approval_status" in columns:
        return normalize_document_status(row["approval_status"], default="Draft")
    if "status" in columns:
        return normalize_document_status(row["status"], default="Draft")
    if "opening_posted" in columns:
        return "Posted" if bool(int(row["opening_posted"] or 0)) else "Draft"
    return "Draft"


def _controlled_source_table_sql_list():
    return ", ".join("'" + table_name.replace("'", "''") + "'" for table_name in sorted(CONTROLLED_SOURCE_TABLES))


def _chart_account_structure(conn):
    return rows_to_dicts(execute_portable_query(
        conn,
        f"""
        SELECT
            id,
            {_coa_code_expression()} AS account_code,
            {_coa_name_expression()} AS account_name,
            {_coa_type_expression()} AS account_type,
            parent_id,
            COALESCE(posting_allowed, 1) AS posting_allowed,
            COALESCE(control_account, 0) AS control_account,
            COALESCE(allow_manual_posting, 1) AS allow_manual_posting,
            COALESCE(is_active, 1) AS is_active
        FROM chart_of_accounts
        ORDER BY {_coa_code_expression()}, {_coa_name_expression()}
        """
    ).fetchall())


def get_chart_of_accounts_diagnostics(conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        rows = _chart_account_structure(conn)
        duplicate_codes = []
        invalid_types = []
        header_posting_allowed = []
        control_accounts_manual = []
        missing_account_codes = []
        seen_codes = {}
        parent_ids = {int(row["parent_id"]) for row in rows if row.get("parent_id") not in (None, "")}
        for row in rows:
            account_name = str(row.get("account_name") or "").strip()
            account_code = str(row.get("account_code") or "").strip()
            account_type = str(row.get("account_type") or "").strip().title()
            posting_allowed = bool(int(row.get("posting_allowed") or 0))
            control_account = bool(int(row.get("control_account") or 0))
            allow_manual_posting = bool(int(row.get("allow_manual_posting") or 0))
            if not account_code:
                missing_account_codes.append(account_name)
            if account_code:
                owner = seen_codes.get(account_code.lower())
                if owner and owner != account_name:
                    duplicate_codes.append({"account_code": account_code, "accounts": [owner, account_name]})
                else:
                    seen_codes[account_code.lower()] = account_name
            if account_type not in VALID_ACCOUNT_TYPES:
                invalid_types.append({"account_name": account_name, "account_type": account_type})
            if int(row["id"]) in parent_ids and posting_allowed:
                header_posting_allowed.append(account_name)
            if control_account and allow_manual_posting:
                control_accounts_manual.append(account_name)
        warnings = []
        if duplicate_codes:
            warnings.append(f"duplicate account codes detected: {len(duplicate_codes)}")
        if invalid_types:
            warnings.append(f"invalid account types detected: {len(invalid_types)}")
        if header_posting_allowed:
            warnings.append(f"header accounts still allow posting: {len(header_posting_allowed)}")
        if control_accounts_manual:
            warnings.append(f"control accounts still allow manual posting: {len(control_accounts_manual)}")
        if missing_account_codes:
            warnings.append(f"accounts missing codes: {len(missing_account_codes)}")
        return {
            "total_accounts": len(rows),
            "duplicate_account_codes": duplicate_codes,
            "invalid_account_types": invalid_types,
            "header_accounts_allowing_posting": header_posting_allowed,
            "control_accounts_allowing_manual_posting": control_accounts_manual,
            "missing_account_codes": missing_account_codes,
            "warnings": warnings,
        }
    finally:
        if owns_connection and conn:
            conn.close()


def _resolve_source_document_mismatches(conn, company_key, branch_id=None):
    mismatches = []
    for table_name in sorted(CONTROLLED_SOURCE_TABLES):
        if not db_table_exists(conn, table_name):
            continue
        columns = _source_document_columns(conn, table_name)
        if "id" not in columns:
            continue
        query = f"SELECT * FROM {table_name} WHERE company_key = ?"
        params = [company_key]
        if branch_id and "branch_id" in columns:
            query += " AND branch_id = ?"
            params.append(branch_id)
        rows = execute_portable_query(conn, query, tuple(params)).fetchall()
        for row in rows:
            status = _safe_doc_status(row, columns)
            row_id = int(row_get(row, "id", 0) or 0)
            posted_entry_id = (
                int(row_get(row, "posted_entry_id"))
                if "posted_entry_id" in columns and row_get(row, "posted_entry_id") not in (None, "")
                else None
            )
            journal_ref = execute_portable_query(
                conn,
                """
                SELECT id
                FROM journal_entries
                WHERE company_key = ?
                  AND COALESCE(is_voided, 0) = 0
                  AND COALESCE(approval_status, 'Posted') = 'Posted'
                  AND lower(COALESCE(source_table, '')) = lower(?)
                  AND source_id = ?
                  {branch_clause}
                LIMIT 1
                """.format(branch_clause="AND branch_id = ?" if branch_id else ""),
                tuple([company_key, table_name, row_id] + ([branch_id] if branch_id else [])),
            ).fetchone()
            has_gl_impact = bool(posted_entry_id or journal_ref)
            if status == "Posted" and not has_gl_impact:
                mismatches.append(
                    {
                        "table": table_name,
                        "source_id": row_id,
                        "issue": "posted source document is missing GL impact",
                    }
                )
            if status != "Posted" and has_gl_impact:
                mismatches.append(
                    {
                        "table": table_name,
                        "source_id": row_id,
                        "issue": f"source document status is {status} but GL impact exists",
                    }
                )
    return mismatches


def _source_document_duplicate_postings(conn, company_key, branch_id=None):
    branch_clause = "AND branch_id = ?" if branch_id else ""
    journal_ids_expr = sql_group_concat("id", backend=get_active_db_backend())
    rows = execute_portable_query(
        conn,
        """
        SELECT lower(COALESCE(source_table, '')) AS source_table,
               source_id,
               COUNT(*) AS journal_count,
               {journal_ids_expr} AS journal_ids
        FROM journal_entries
        WHERE company_key = ?
          AND COALESCE(is_voided, 0) = 0
          AND COALESCE(approval_status, 'Posted') = 'Posted'
          AND source_id IS NOT NULL
          AND lower(COALESCE(source_table, '')) IN ({controlled_tables})
          {branch_clause}
        GROUP BY lower(COALESCE(source_table, '')), source_id
        HAVING COUNT(*) > 1
        """.format(
            branch_clause=branch_clause,
            controlled_tables=_controlled_source_table_sql_list(),
            journal_ids_expr=journal_ids_expr,
        ),
        tuple([company_key] + ([branch_id] if branch_id else [])),
    ).fetchall()
    return [
        {
            "source_table": row_get(row, "source_table"),
            "source_id": int(row_get(row, "source_id", 0) or 0),
            "journal_count": int(row_get(row, "journal_count", 0) or 0),
            "journal_ids": str(row_get(row, "journal_ids", "") or ""),
        }
        for row in rows
    ]


def get_finance_integrity_diagnostics(company_key, as_of_date=None, branch_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        ar_subledger_total = round(
            sum(float(row.get("balance") or 0.0) for row in get_customer_balances(company_key, as_of_date=as_of_date, conn=conn)),
            2,
        )
        ar_control_balance = round(
            float(
                get_account_total(
                    company_key,
                    "Accounts Receivable",
                    end_date=as_of_date,
                    branch_id=branch_id,
                    balance_side="debit",
                    conn=conn,
                )
            ),
            2,
        )
        ap_subledger_total = round(
            sum(float(row.get("balance") or 0.0) for row in get_supplier_balances(company_key, as_of_date=as_of_date, conn=conn)),
            2,
        )
        ap_control_balance = round(
            float(
                get_account_total(
                    company_key,
                    "Accounts Payable",
                    end_date=as_of_date,
                    branch_id=branch_id,
                    balance_side="credit",
                    conn=conn,
                )
            ),
            2,
        )
        inventory_query, inventory_params = _inventory_value_query(conn, company_key, branch_id=branch_id)
        inventory_subledger_total = round(
            float(
                fetch_scalar(conn, inventory_query, inventory_params, default=0.0)
                or 0.0
            ),
            2,
        )
        inventory_gl_balance = round(
            float(
                get_account_total(
                    company_key,
                    "Inventory",
                    end_date=as_of_date,
                    branch_id=branch_id,
                    balance_side="debit",
                    conn=conn,
                )
            ),
            2,
        )
        unbalanced_journal_rows = execute_portable_query(
            conn,
            """
            SELECT je.id
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            WHERE je.company_key = ?
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
              {branch_clause}
            GROUP BY je.id
            HAVING ABS(COALESCE(SUM(jl.debit), 0) - COALESCE(SUM(jl.credit), 0)) >= 0.01
            """.format(branch_clause="AND je.branch_id = ?" if branch_id else ""),
            tuple([company_key] + ([branch_id] if branch_id else [])),
        ).fetchall()
        orphaned_journal_refs = []
        source_rows = execute_portable_query(
            conn,
            """
            SELECT id, source_table, source_id, reference
            FROM journal_entries
            WHERE company_key = ?
              AND source_table IS NOT NULL
              AND TRIM(COALESCE(source_table, '')) != ''
              AND source_id IS NOT NULL
              AND COALESCE(is_voided, 0) = 0
              AND COALESCE(approval_status, 'Posted') = 'Posted'
              {branch_clause}
            """.format(branch_clause="AND branch_id = ?" if branch_id else ""),
            tuple([company_key] + ([branch_id] if branch_id else [])),
        ).fetchall()
        known_tables = {table_name.lower() for table_name in list_tables(conn)}
        for row in source_rows:
            source_table = str(row_get(row, "source_table", "") or "").strip().lower()
            source_id = int(row_get(row, "source_id", 0) or 0)
            if source_table not in known_tables:
                orphaned_journal_refs.append(
                    {"entry_id": int(row_get(row, "id", 0) or 0), "source_table": source_table, "source_id": source_id, "reason": "source table missing"}
                )
                continue
            source_match = execute_portable_query(
                conn,
                f"SELECT id FROM {source_table} WHERE id = ? LIMIT 1",
                (source_id,),
            ).fetchone()
            if not source_match:
                orphaned_journal_refs.append(
                    {"entry_id": int(row_get(row, "id", 0) or 0), "source_table": source_table, "source_id": source_id, "reason": "source document missing"}
                )

        source_document_mismatches = _resolve_source_document_mismatches(conn, company_key, branch_id=branch_id)
        coa_diagnostics = get_chart_of_accounts_diagnostics(conn=conn)
        return {
            "accounts_receivable": {
                "subledger_total": ar_subledger_total,
                "control_account_balance": ar_control_balance,
                "difference": round(ar_subledger_total - ar_control_balance, 2),
                "reconciled": abs(ar_subledger_total - ar_control_balance) < 0.01,
            },
            "accounts_payable": {
                "subledger_total": ap_subledger_total,
                "control_account_balance": ap_control_balance,
                "difference": round(ap_subledger_total - ap_control_balance, 2),
                "reconciled": abs(ap_subledger_total - ap_control_balance) < 0.01,
            },
            "inventory": {
                "subledger_total": inventory_subledger_total,
                "control_account_balance": inventory_gl_balance,
                "difference": round(inventory_subledger_total - inventory_gl_balance, 2),
                "reconciled": abs(inventory_subledger_total - inventory_gl_balance) < 0.01,
            },
            "unbalanced_journal_count": len(unbalanced_journal_rows),
            "orphaned_journal_reference_count": len(orphaned_journal_refs),
            "orphaned_journal_references": orphaned_journal_refs,
            "source_documents_missing_gl_count": len(source_document_mismatches),
            "source_document_mismatches": source_document_mismatches,
            "chart_of_accounts": coa_diagnostics,
        }
    finally:
        if owns_connection and conn:
            conn.close()


def get_journal_dominance_diagnostics(company_key, as_of_date=None, branch_id=None, conn=None):
    """
    Report whether accounting outputs are journal-led.
    Compatibility tables are inspected only for warnings; they do not drive balances.
    """
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        integrity = get_finance_integrity_diagnostics(company_key, as_of_date=as_of_date, branch_id=branch_id, conn=conn)
        legacy_tables = ["transactions", "vouchers", "customer_transactions", "supplier_transactions"]
        legacy_usage = []
        for table_name in legacy_tables:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (table_name,),
            ).fetchone()
            row_count = 0
            if exists:
                try:
                    if table_name in {"transactions", "vouchers", "customer_transactions", "supplier_transactions"}:
                        company_column = "company_key"
                        row = conn.execute(
                            f"SELECT COUNT(*) AS row_count FROM {table_name} WHERE {company_column} = ?",
                            (company_key,),
                        ).fetchone()
                    else:
                        row = conn.execute(f"SELECT COUNT(*) AS row_count FROM {table_name}").fetchone()
                    row_count = int(row["row_count"] or 0) if row else 0
                except sqlite3.Error:
                    row_count = 0
            legacy_usage.append(
                {
                    "table": table_name,
                    "classification": "compatibility_history_only",
                    "exists": bool(exists),
                    "row_count": row_count,
                    "controls_balances": False,
                }
            )
        posted_journal_count = conn.execute(
            """
            SELECT COUNT(*) AS journal_count
            FROM journal_entries
            WHERE company_key = ?
              AND COALESCE(is_voided, 0) = 0
              AND COALESCE(approval_status, 'Posted') = 'Posted'
              {branch_clause}
            """.format(branch_clause="AND branch_id = ?" if branch_id else ""),
            tuple([company_key] + ([branch_id] if branch_id else [])),
        ).fetchone()
        warnings = []
        if not integrity["accounts_receivable"]["reconciled"]:
            warnings.append("A/R customer detail does not reconcile to the journal control account.")
        if not integrity["accounts_payable"]["reconciled"]:
            warnings.append("A/P supplier detail does not reconcile to the journal control account.")
        if integrity["unbalanced_journal_count"]:
            warnings.append(f"{integrity['unbalanced_journal_count']} posted journal(s) are unbalanced.")
        if integrity["orphaned_journal_reference_count"]:
            warnings.append(f"{integrity['orphaned_journal_reference_count']} posted journal source reference(s) are orphaned.")
        if integrity["source_documents_missing_gl_count"]:
            warnings.append(f"{integrity['source_documents_missing_gl_count']} source document posting-state issue(s) detected.")
        active_legacy = [item for item in legacy_usage if item["row_count"] > 0]
        if active_legacy:
            warnings.append(
                "Compatibility/history tables contain rows but are not used for balances: "
                + ", ".join(f"{item['table']}={item['row_count']}" for item in active_legacy)
            )
        return {
            "source_of_truth": "journal_entries + journal_lines",
            "posted_journal_count": int(posted_journal_count["journal_count"] or 0) if posted_journal_count else 0,
            "trial_balance_source": "journal_entries + journal_lines, Posted only",
            "general_ledger_source": "journal_entries + journal_lines, Posted only",
            "ar_balance_source": "journal_entries + journal_lines filtered by customer_id and Accounts Receivable",
            "ap_balance_source": "journal_entries + journal_lines filtered by supplier_id and Accounts Payable",
            "compatibility_tables": legacy_usage,
            "integrity": integrity,
            "warnings": warnings,
            "ok": not warnings,
        }
    finally:
        if owns_connection and conn:
            conn.close()


def get_document_workflow_diagnostics(company_key, branch_id=None, conn=None):
    """Summarize controlled document state and journal-link consistency."""
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        document_counts = []
        for table_name in sorted(CONTROLLED_SOURCE_TABLES | {"journal_entries"}):
            table_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (table_name,),
            ).fetchone()
            if not table_exists:
                document_counts.append({"document_type": table_name, "status": "missing_table", "count": 0})
                continue
            columns = _source_document_columns(conn, table_name)
            if "company_key" not in columns:
                continue
            status_expr = "approval_status" if "approval_status" in columns else ("status" if "status" in columns else "'Posted'")
            query = f"""
                SELECT COALESCE(NULLIF({status_expr}, ''), 'Draft') AS raw_status,
                       COUNT(*) AS row_count
                FROM {table_name}
                WHERE company_key = ?
            """
            params = [company_key]
            if branch_id and "branch_id" in columns:
                query += " AND branch_id = ?"
                params.append(branch_id)
            query += f" GROUP BY COALESCE(NULLIF({status_expr}, ''), 'Draft')"
            for row in conn.execute(query, tuple(params)).fetchall():
                document_counts.append(
                    {
                        "document_type": table_name,
                        "status": normalize_document_status(row["raw_status"], default="Draft"),
                        "count": int(row["row_count"] or 0),
                    }
                )

        source_mismatches = _resolve_source_document_mismatches(conn, company_key, branch_id=branch_id)
        duplicate_postings = _source_document_duplicate_postings(conn, company_key, branch_id=branch_id)
        warnings = []
        if source_mismatches:
            warnings.append(f"{len(source_mismatches)} document(s) have posting-state / GL-impact mismatches.")
        if duplicate_postings:
            warnings.append(f"{len(duplicate_postings)} document(s) have duplicate posted journal impact.")
        return {
            "controlled_statuses": sorted(VALID_DOCUMENT_CONTROL_STATUSES - {"Active"}),
            "controlled_source_tables": sorted(CONTROLLED_SOURCE_TABLES),
            "document_counts": document_counts,
            "source_document_mismatches": source_mismatches,
            "duplicate_postings": duplicate_postings,
            "duplicate_posting_count": len(duplicate_postings),
            "warnings": warnings,
            "ok": not warnings,
        }
    finally:
        if owns_connection and conn:
            conn.close()


def get_unified_posting_engine_diagnostics(company_key, branch_id=None, conn=None):
    """Report Phase 7 posting-engine convergence and remaining transitional paths."""
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        branch_clause = "AND branch_id = ?" if branch_id else ""
        params = [company_key] + ([branch_id] if branch_id else [])
        missing_linkage_row = conn.execute(
            f"""
            SELECT COUNT(*) AS row_count
            FROM journal_entries
            WHERE company_key = ?
              AND COALESCE(is_voided, 0) = 0
              AND COALESCE(approval_status, 'Posted') = 'Posted'
              AND (
                    TRIM(COALESCE(source_table, '')) = ''
                 OR source_id IS NULL
                 OR TRIM(COALESCE(source_document_type, '')) = ''
                 OR source_document_id IS NULL
              )
              {branch_clause}
            """,
            tuple(params),
        ).fetchone()
        duplicate_postings = _source_document_duplicate_postings(conn, company_key, branch_id=branch_id)
        duplicate_attempt_row = conn.execute(
            """
            SELECT COUNT(*) AS row_count
            FROM system_logs
            WHERE module_name = 'Unified Posting Engine'
              AND level IN ('WARNING', 'ERROR')
              AND lower(message) LIKE '%blocked posting%'
              AND lower(message) LIKE '%already posted%'
            """
        ).fetchone()
        reversal_rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(source_table, ''), 'journal_entries') AS source_table,
                   COUNT(*) AS row_count
            FROM journal_entries
            WHERE company_key = ?
              AND (
                    lower(COALESCE(source_type, '')) = 'reversal'
                 OR reversed_entry_id IS NOT NULL
                 OR COALESCE(is_voided, 0) = 1
              )
              {branch_clause}
            GROUP BY COALESCE(NULLIF(source_table, ''), 'journal_entries')
            ORDER BY source_table
            """,
            tuple(params),
        ).fetchall()
        legacy_rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(source_table, ''), 'missing') AS source_table,
                   COUNT(*) AS row_count
            FROM journal_entries
            WHERE company_key = ?
              AND COALESCE(is_voided, 0) = 0
              AND COALESCE(approval_status, 'Posted') = 'Posted'
              AND lower(COALESCE(source_table, '')) NOT IN ('invoices', 'bills', 'payments', 'stock_movements', 'vouchers')
              {branch_clause}
            GROUP BY COALESCE(NULLIF(source_table, ''), 'missing')
            ORDER BY row_count DESC
            """,
            tuple(params),
        ).fetchall()
        transitional_sources = [
            {"source_table": row["source_table"], "posted_journal_count": int(row["row_count"] or 0)}
            for row in legacy_rows
        ]
        warnings = []
        missing_linkage_count = int(missing_linkage_row["row_count"] or 0) if missing_linkage_row else 0
        if missing_linkage_count:
            warnings.append(f"{missing_linkage_count} posted journal(s) are missing complete source-document linkage.")
        if duplicate_postings:
            warnings.append(f"{len(duplicate_postings)} source document(s) have duplicate posted journal impact.")
        if transitional_sources:
            warnings.append("Some posted journals still use transitional/non-controlled source tables.")
        return {
            "engine_version": UNIFIED_POSTING_ENGINE_VERSION,
            "authoritative_posting_service": "accounting_engine.post_accounting_impact",
            "low_level_journal_writer": "accounting_engine.post_journal_entry",
            "controlled_source_tables": sorted(CONTROLLED_SOURCE_TABLES),
            "enforced_checks": [
                "Posted document status",
                "Posting role permission when role context is supplied",
                "Accounting period open",
                "Duplicate source-document prevention",
                "Balanced debits and credits",
                "Valid active posting accounts",
                "Source document linkage metadata",
                "Posted timestamp and posting user metadata",
            ],
            "missing_source_linkage_count": missing_linkage_count,
            "duplicate_posting_count": len(duplicate_postings),
            "duplicate_post_attempts_blocked": int(duplicate_attempt_row["row_count"] or 0) if duplicate_attempt_row else 0,
            "reversal_void_counts": [
                {"source_table": row["source_table"], "count": int(row["row_count"] or 0)}
                for row in reversal_rows
            ],
            "transitional_source_tables": transitional_sources,
            "warnings": warnings,
            "ok": not warnings,
        }
    finally:
        if owns_connection and conn:
            conn.close()


def get_or_create_account(conn, account_name, account_type, parent_id=None, account_code=None):
    account_name = str(account_name or "").strip()
    account_type = str(account_type or "").strip().title()
    account_code = str(account_code or "").strip()
    if not account_name or not account_type:
        raise ValueError("Account name and type are required.")
    if account_type not in VALID_ACCOUNT_TYPES:
        raise ValueError(f"Invalid account type '{account_type}'.")

    if account_code:
        code_owner = conn.execute(
            f"""
            SELECT id, {_coa_name_expression()} AS account_name
            FROM chart_of_accounts
            WHERE lower({_coa_code_expression()}) = lower(?)
            LIMIT 1
            """,
            (account_code,),
        ).fetchone()
        if code_owner and str(code_owner["account_name"]).strip().lower() != account_name.lower():
            raise ValueError(
                f"Account code '{account_code}' is already assigned to {code_owner['account_name']}."
            )

    row = _find_account_row_by_normalized_name(conn, account_name)
    if row:
        existing_type = str(row["account_type"] or "").strip().title()
        if existing_type and existing_type != account_type:
            logger.warning(
                "Chart of accounts type mismatch detected for account '%s': existing_type=%s requested_type=%s",
                account_name,
                existing_type,
                account_type,
            )
        conn.execute(
            """
            UPDATE chart_of_accounts
            SET name = COALESCE(NULLIF(name, ''), ?),
                account_name = COALESCE(NULLIF(account_name, ''), ?),
                type = CASE
                    WHEN NULLIF(type, '') IS NULL THEN ?
                    ELSE type
                END,
                account_type = CASE
                    WHEN NULLIF(account_type, '') IS NULL THEN ?
                    ELSE account_type
                END,
                category = CASE
                    WHEN NULLIF(category, '') IS NULL THEN ?
                    ELSE category
                END,
                code = COALESCE(NULLIF(code, ''), NULLIF(?, ''), code),
                account_code = COALESCE(NULLIF(account_code, ''), NULLIF(?, ''), account_code),
                parent_id = COALESCE(parent_id, ?),
                posting_allowed = COALESCE(posting_allowed, ?),
                control_account = COALESCE(control_account, ?),
                allow_manual_posting = COALESCE(allow_manual_posting, ?),
                is_active = COALESCE(is_active, 1)
            WHERE id = ?
            """,
            (
                account_name,
                account_name,
                account_type,
                account_type,
                account_type,
                account_code,
                account_code,
                parent_id,
                0 if account_name in HEADER_ACCOUNT_NAMES else 1,
                1 if account_name in CONTROL_ACCOUNT_NAMES else 0,
                0 if account_name in CONTROL_ACCOUNT_NAMES else 1,
                int(row["id"]),
            ),
        )
        return int(row["id"])

    cursor = conn.execute(
        ensure_insert_sql_returning(
            """
            INSERT INTO chart_of_accounts (
                name, type, parent_id, code, category, account_code, account_name, account_type,
                posting_allowed, control_account, allow_manual_posting, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (
            account_name,
            account_type,
            parent_id,
            account_code or None,
            account_type,
            account_code or None,
            account_name,
            account_type,
            0 if account_name in HEADER_ACCOUNT_NAMES else 1,
            1 if account_name in CONTROL_ACCOUNT_NAMES else 0,
            0 if account_name in CONTROL_ACCOUNT_NAMES else 1,
            1,
        ),
    )
    return get_inserted_id(cursor)


def get_account_id(conn, account_name, account_type=None):
    row = _find_account_row_by_normalized_name(conn, str(account_name or "").strip())
    if row:
        return int(row["id"])
    if account_type is None:
        raise ValueError(f"Account '{account_name}' does not exist.")
    return get_or_create_account(conn, account_name, account_type)


def _mirror_legacy_transactions(conn, company_key, entry_date, description, reference, created_by, branch_id, normalized_lines):
    if _legacy_mirror_mode(conn) not in {"mirror", "dual_write"}:
        return
    try:
        conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'transactions'").fetchone()
        for line in normalized_lines:
            conn.execute(
                """
                INSERT INTO transactions (company_key, transaction_date, account, description, debit, credit, reference, created_by, branch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_key,
                    entry_date,
                    line["account_name"],
                    f"{description} [legacy mirror]",
                    line["debit"],
                    line["credit"],
                    reference,
                    created_by,
                    branch_id,
                ),
            )
    except sqlite3.Error:
        return


def _legacy_voucher_insert(
    conn,
    company_key,
    branch_id,
    entry_date,
    description,
    reference,
    created_by,
    normalized_lines,
    source_module=None,
):
    if _legacy_mirror_mode(conn) not in {"mirror", "dual_write"}:
        return
    try:
        revenue = sum(line["credit"] for line in normalized_lines if line["account_type"] == "Income")
        if revenue <= 0:
            return
        conn.execute(
            """
            INSERT INTO vouchers (company_key, branch_id, date, v_type, ledger, credit, reference_no, narration, status, approval_status, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Posted', 'Posted', ?)
            """,
            (
                company_key,
                branch_id,
                entry_date,
                "Journal",
                source_module or "Legacy Mirror",
                revenue,
                reference,
                f"{description} [legacy mirror]",
                created_by,
            ),
        )
    except sqlite3.Error:
        return


def post_journal_entry(
    company_key,
    date,
    description,
    reference,
    lines,
    created_by,
    branch_id=None,
    customer_id=None,
    supplier_id=None,
    inventory_item_id=None,
    payment_id=None,
    source_module=None,
    source_table=None,
    source_type=None,
    source_id=None,
    approval_status="Posted",
    manual_entry=False,
    conn=None,
):
    if not lines:
        raise ValueError("Journal entry lines are required.")

    entry_date = _resolve_date(date)
    owns_connection = conn is None
    if owns_connection:
        operation_name = "journal_posting"
        if str(source_table or "").strip().lower() == "pos_sales":
            operation_name = "pos_finalization"
        elif str(source_table or "").strip().lower() == "payroll":
            operation_name = "payroll_posting"
        elif str(source_type or source_module or "").strip().lower().find("depreciation") >= 0:
            operation_name = "depreciation_run"
        return execute_db_write_transaction(
            lambda tx_conn: post_journal_entry(
                company_key=company_key,
                date=date,
                description=description,
                reference=reference,
                lines=lines,
                created_by=created_by,
                branch_id=branch_id,
                customer_id=customer_id,
                supplier_id=supplier_id,
                inventory_item_id=inventory_item_id,
                payment_id=payment_id,
                source_module=source_module,
                source_table=source_table,
                source_type=source_type,
                source_id=source_id,
                approval_status=approval_status,
                manual_entry=manual_entry,
                conn=tx_conn,
            ),
            operation_name=operation_name,
        )
    conn = conn or get_connection()
    if conn is None:
        raise RuntimeError("Database connection unavailable.")
    if _period_locked(conn, company_key, entry_date):
        raise ValueError(f"The accounting period for {entry_date[:7]} is locked.")
    _assert_source_document_postable(conn, source_table, source_id)
    _assert_no_duplicate_source_posting(conn, company_key, source_table, source_id, branch_id=branch_id, source_type=source_type)

    normalized_approval_status = normalize_document_status(approval_status, default="Posted")
    normalized_lines = []
    total_debit = 0.0
    total_credit = 0.0
    for line in lines:
        if "account_id" not in line:
            raise ValueError("Every journal line requires an explicit account selection.")
        account_id = int(line.get("account_id") or 0)
        debit = round(float(line.get("debit") or 0.0), 2)
        credit = round(float(line.get("credit") or 0.0), 2)
        if account_id <= 0:
            raise ValueError("Every journal line requires a valid account_id.")
        if debit < 0 or credit < 0:
            raise ValueError("Debit and credit amounts cannot be negative.")
        if debit == 0 and credit == 0:
            raise ValueError("Each journal line must contain a positive debit or credit amount.")
        if debit > 0 and credit > 0:
            raise ValueError("A journal line cannot contain both debit and credit values.")
        account_row = conn.execute(
            f"""
            SELECT id,
                   {_coa_name_expression()} AS account_name,
                   {_coa_type_expression()} AS account_type,
                   COALESCE(posting_allowed, 1) AS posting_allowed,
                   COALESCE(control_account, 0) AS control_account,
                   COALESCE(allow_manual_posting, 1) AS allow_manual_posting,
                   COALESCE(is_active, 1) AS is_active
            FROM chart_of_accounts
            WHERE id = ?
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()
        if not account_row:
            raise ValueError(f"Account ID {account_id} does not exist.")
        account_type = str(account_row["account_type"]).strip().title()
        if account_type not in VALID_ACCOUNT_TYPES:
            raise ValueError(f"Account ID {account_id} has invalid type '{account_type}'.")
        if not bool(int(account_row["is_active"] or 0)):
            raise ValueError(f"Account '{account_row['account_name']}' is inactive and cannot accept postings.")
        if not bool(int(account_row["posting_allowed"] or 0)):
            raise ValueError(f"Account '{account_row['account_name']}' is a header/non-posting account.")
        if manual_entry and bool(int(account_row["control_account"] or 0)) and not bool(int(account_row["allow_manual_posting"] or 0)):
            raise ValueError(
                f"Manual posting to control account '{account_row['account_name']}' is blocked. Use the source document workflow instead."
            )
        normalized_lines.append(
            {
                "account_id": account_id,
                "account_name": str(account_row["account_name"]),
                "account_type": account_type,
                "debit": debit,
                "credit": credit,
            }
        )
        total_debit += debit
        total_credit += credit

    total_debit = round(total_debit, 2)
    total_credit = round(total_credit, 2)
    if not normalized_lines:
        raise ValueError("Journal entry must include at least one non-zero line.")
    if total_debit != total_credit:
        raise ValueError(f"Unbalanced journal entry: debit={total_debit:.2f}, credit={total_credit:.2f}")

    try:
        cursor = conn.execute(
            ensure_insert_sql_returning(
                """
                INSERT INTO journal_entries (
                    company_key, date, description, reference, created_by, branch_id,
                    customer_id, supplier_id, inventory_item_id, payment_id,
                    source_module, source_table, source_type, source_id,
                    source_document_type, source_document_id, approval_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                company_key,
                entry_date,
                description,
                reference,
                created_by,
                branch_id,
                customer_id,
                supplier_id,
                inventory_item_id,
                payment_id,
                source_module,
                source_table,
                source_type,
                source_id,
                source_type or source_table or source_module,
                source_id,
                normalized_approval_status,
            ),
        )
        entry_id = get_inserted_id(cursor)
        document_type = source_type or source_table or source_module or "Journal"
        conn.execute(
            """
            UPDATE journal_entries
            SET document_number = COALESCE(document_number, reference),
                document_type = COALESCE(document_type, ?),
                source_document_type = COALESCE(source_document_type, ?),
                source_document_id = COALESCE(source_document_id, ?),
                posted_at = COALESCE(posted_at, CURRENT_TIMESTAMP),
                posted_by = COALESCE(posted_by, created_by)
            WHERE id = ?
            """,
            (document_type, document_type, source_id, entry_id),
        )
        for line in normalized_lines:
            conn.execute(
                """
                INSERT INTO journal_lines (entry_id, account_id, debit, credit)
                VALUES (?, ?, ?, ?)
                """,
                (entry_id, line["account_id"], line["debit"], line["credit"]),
            )
        if source_table and source_id:
            _sync_source_document_posting(
                conn,
                source_table=source_table,
                source_id=source_id,
                entry_id=entry_id,
                posting_user=created_by,
                source_type=source_type,
            )
        _mirror_legacy_transactions(conn, company_key, entry_date, description, reference, created_by, branch_id, normalized_lines)
        if source_module:
            _legacy_voucher_insert(conn, company_key, branch_id, entry_date, description, reference, created_by, normalized_lines, source_module=source_module)
        if owns_connection:
            with_retry_on_lock(conn.commit, operation_name="journal_posting_commit")
        return entry_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def post_accounting_impact(
    company_key,
    date,
    description,
    reference,
    lines,
    created_by,
    branch_id=None,
    customer_id=None,
    supplier_id=None,
    inventory_item_id=None,
    payment_id=None,
    source_module=None,
    source_table=None,
    source_type=None,
    source_id=None,
    approval_status="Posted",
    manual_entry=False,
    user_role=None,
    conn=None,
):
    """Authoritative Phase 7 posting service for document-to-ledger impact.

    Document-specific screens still build their business-specific journal lines,
    but final accounting impact should pass through this service boundary.
    """
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        effective_user_role = _resolve_effective_posting_role(user_role, created_by)
        _assert_posting_role_allowed(effective_user_role)
        entry_id = post_journal_entry(
            company_key=company_key,
            date=date,
            description=description,
            reference=reference,
            lines=lines,
            created_by=created_by,
            branch_id=branch_id,
            customer_id=customer_id,
            supplier_id=supplier_id,
            inventory_item_id=inventory_item_id,
            payment_id=payment_id,
            source_module=source_module,
            source_table=source_table,
            source_type=source_type,
            source_id=source_id,
            approval_status=approval_status,
            manual_entry=manual_entry,
            conn=conn,
        )
        _log_posting_engine_event(
            conn,
            "INFO",
            f"posted source_table={source_table or 'none'} source_id={source_id or 'none'} entry_id={entry_id}",
        )
        if owns_connection:
            conn.commit()
        return entry_id
    except Exception as exc:
        message = str(exc)
        level = "WARNING" if "already posted" in message.lower() or "duplicate" in message.lower() else "ERROR"
        event_prefix = "permission denied posting" if isinstance(exc, PermissionError) else "blocked posting"
        event_message = f"{event_prefix} source_table={source_table or 'none'} source_id={source_id or 'none'} reason={message}"
        try:
            database_log_audit_action(
                conn,
                company_key,
                str(effective_user_role or created_by or "System"),
                f"Permission denied: {source_table or 'accounting_document'} posting" if isinstance(exc, PermissionError) else f"Blocked posting: {source_table or 'accounting_document'}",
                "Security" if isinstance(exc, PermissionError) else "Unified Posting Engine",
                details=event_message,
                branch_id=branch_id,
                action_type="admin" if isinstance(exc, PermissionError) else "post",
                document_ref=str(source_id or reference or ""),
            )
        except Exception:
            logger.debug("Posting audit logging skipped.", exc_info=True)
        if owns_connection:
            conn.rollback()
            _persist_posting_engine_event(level, event_message)
        else:
            _log_posting_engine_event(conn, level, event_message)
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def reverse_journal_entry(entry_id, created_by=None, reversal_date=None, reason=None, branch_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        original = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
        if not original:
            raise ValueError(f"Journal entry {entry_id} not found.")
        if original["is_voided"]:
            raise ValueError(f"Journal entry {entry_id} is already voided.")
        if str(original["source_type"] or "").lower() == "reversal":
            raise ValueError("Cannot reverse a reversal entry.")
        if original["reversed_entry_id"]:
            raise ValueError(f"Journal entry {entry_id} has already been reversed.")

        reversal_date = _resolve_date(reversal_date or datetime.now().date())
        reversal_lines = []
        for row in conn.execute("SELECT account_id, debit, credit FROM journal_lines WHERE entry_id = ?", (entry_id,)):
            reversal_lines.append({"account_id": int(row["account_id"]), "debit": float(row["credit"] or 0.0), "credit": float(row["debit"] or 0.0)})
        if not reversal_lines:
            raise ValueError(f"Journal entry {entry_id} contains no lines to reverse.")

        reference = f"REV-{entry_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        description = f"Reversal of journal entry {entry_id}"
        if reason:
            description = f"{description}: {reason}"

        reversal_id = post_journal_entry(
            company_key=original["company_key"],
            date=reversal_date,
            description=description,
            reference=reference,
            lines=reversal_lines,
            created_by=created_by or original["created_by"],
            branch_id=branch_id or original["branch_id"],
            source_module="Journal Reversal",
            source_table="journal_entries",
            source_type="Reversal",
            source_id=entry_id,
            approval_status="Posted",
            conn=conn,
        )
        conn.execute(
            "UPDATE journal_entries SET reversed_entry_id = ? WHERE id = ?",
            (reversal_id, entry_id),
        )
        _log_posting_engine_event(
            conn,
            "INFO",
            f"reversed journal entry={entry_id} reversal_entry={reversal_id} reason={reason or 'not provided'}",
        )
        if owns_connection:
            conn.commit()
        return reversal_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def void_journal_entry(entry_id, voided_by=None, voided_at=None, reason=None, branch_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        original = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
        if not original:
            raise ValueError(f"Journal entry {entry_id} not found.")
        if original["is_voided"]:
            raise ValueError(f"Journal entry {entry_id} is already voided.")

        reversal_id = reverse_journal_entry(
            entry_id,
            created_by=voided_by or original["created_by"],
            reversal_date=voided_at or datetime.now().date(),
            reason=reason or "Voided by user",
            branch_id=branch_id or original["branch_id"],
            conn=conn,
        )
        voided_timestamp = _resolve_date(voided_at or datetime.now().date())
        conn.execute(
            "UPDATE journal_entries SET is_voided = 1, voided_at = ?, voided_by = ?, approval_status = 'Voided' WHERE id = ?",
            (voided_timestamp, voided_by or original["created_by"], entry_id),
        )
        _log_posting_engine_event(
            conn,
            "INFO",
            f"voided journal entry={entry_id} reversal_entry={reversal_id} reason={reason or 'not provided'}",
        )
        if owns_connection:
            conn.commit()
        return reversal_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def allocate_payment(payment_id, invoice_id=None, bill_id=None, amount=None, created_by=None, branch_id=None, conn=None):
    if amount is None or amount <= 0:
        raise ValueError("Allocation amount must be a positive number.")
    if not invoice_id and not bill_id:
        raise ValueError("Either invoice_id or bill_id must be provided for payment allocation.")
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not payment:
            raise ValueError(f"Payment {payment_id} does not exist.")

        if invoice_id:
            invoice = conn.execute("SELECT amount FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            if not invoice:
                raise ValueError(f"Invoice {invoice_id} does not exist.")
            outstanding = float(invoice["amount"] or 0.0) - float(
                fetch_scalar(
                    conn,
                    "SELECT COALESCE(SUM(amount), 0) FROM payment_allocations WHERE invoice_id = ?",
                    (invoice_id,),
                    default=0.0,
                )
                or 0.0
            )
            if amount > outstanding:
                raise ValueError(f"Allocation amount exceeds outstanding invoice balance ({outstanding:.2f}).")
        if bill_id:
            bill = conn.execute("SELECT amount FROM bills WHERE id = ?", (bill_id,)).fetchone()
            if not bill:
                raise ValueError(f"Bill {bill_id} does not exist.")
            outstanding = float(bill["amount"] or 0.0) - float(
                fetch_scalar(
                    conn,
                    "SELECT COALESCE(SUM(amount), 0) FROM payment_allocations WHERE bill_id = ?",
                    (bill_id,),
                    default=0.0,
                )
                or 0.0
            )
            if amount > outstanding:
                raise ValueError(f"Allocation amount exceeds outstanding bill balance ({outstanding:.2f}).")

        cursor = conn.execute(
            ensure_insert_sql_returning(
                "INSERT INTO payment_allocations (company_key, payment_id, invoice_id, bill_id, amount, currency, branch_id, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                payment["company_key"],
                payment_id,
                invoice_id,
                bill_id,
                amount,
                payment["currency"],
                branch_id or (payment["branch_id"] if "branch_id" in payment.keys() else None),
                created_by or payment["created_by"],
            ),
        )
        if owns_connection:
            conn.commit()
        return get_inserted_id(cursor)
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def get_payment_allocations(payment_id=None, invoice_id=None, bill_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = "SELECT * FROM payment_allocations WHERE 1=1"
        params = []
        if payment_id:
            query += " AND payment_id = ?"
            params.append(payment_id)
        if invoice_id:
            query += " AND invoice_id = ?"
            params.append(invoice_id)
        if bill_id:
            query += " AND bill_id = ?"
            params.append(bill_id)
        return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    finally:
        if owns_connection and conn:
            conn.close()


def create_bank_account(company_key, account_name, bank_name=None, account_number=None, currency="GHS", account_type="Bank", branch_id=None, opening_balance=0.0, created_by=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        cursor = conn.execute(
            ensure_insert_sql_returning(
                "INSERT INTO bank_accounts (company_key, branch_id, account_name, account_number, bank_name, account_type, currency, balance, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (company_key, branch_id, account_name, account_number, bank_name, account_type, currency, opening_balance, created_by),
        )
        if owns_connection:
            conn.commit()
        return get_inserted_id(cursor)
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def get_bank_account(account_id, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute("SELECT * FROM bank_accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None
    finally:
        if owns_connection and conn:
            conn.close()


def get_bank_accounts(company_key, branch_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = "SELECT * FROM bank_accounts WHERE company_key = ?"
        params = [company_key]
        if branch_id:
            query += " AND branch_id = ?"
            params.append(branch_id)
        return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    finally:
        if owns_connection and conn:
            conn.close()


def _next_recurrence_date(current_date, frequency):
    if frequency == "Daily":
        return current_date + pd.Timedelta(days=1)
    if frequency == "Weekly":
        return current_date + pd.Timedelta(weeks=1)
    if frequency == "Monthly":
        return current_date + pd.DateOffset(months=1)
    if frequency == "Quarterly":
        return current_date + pd.DateOffset(months=3)
    if frequency == "Yearly":
        return current_date + pd.DateOffset(years=1)
    raise ValueError(f"Unsupported recurrence frequency: {frequency}")


def schedule_recurring_transaction(company_key, description, frequency, amount, next_run_date, lines, created_by, branch_id=None, source_module=None, source_table=None, source_id=None, active=True, conn=None):
    if frequency not in {"Daily", "Weekly", "Monthly", "Quarterly", "Yearly"}:
        raise ValueError("Frequency must be one of Daily, Weekly, Monthly, Quarterly, Yearly.")
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        payload = json.dumps(lines)
        cursor = conn.execute(
            ensure_insert_sql_returning(
                "INSERT INTO recurring_transactions (company_key, branch_id, description, frequency, amount, next_run_date, is_active, source_module, source_table, source_id, created_by, recurrence_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (company_key, branch_id, description, frequency, amount, _resolve_date(next_run_date), 1 if active else 0, source_module, source_table, source_id, created_by, payload),
        )
        if owns_connection:
            conn.commit()
        return get_inserted_id(cursor)
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def get_due_recurring_transactions(company_key=None, run_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        today = _resolve_date(run_date or datetime.now().date())
        query = "SELECT * FROM recurring_transactions WHERE is_active = 1 AND date(next_run_date) <= date(?)"
        params = [today]
        if company_key:
            query = "SELECT * FROM recurring_transactions WHERE is_active = 1 AND company_key = ? AND date(next_run_date) <= date(?)"
            params = [company_key, today]
        return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    finally:
        if owns_connection and conn:
            conn.close()


def run_recurring_transactions(company_key=None, run_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        due = get_due_recurring_transactions(company_key=company_key, run_date=run_date, conn=conn)
        count = 0
        for row in due:
            payload = row.get("recurrence_payload")
            if not payload:
                continue
            lines = json.loads(payload)
            entry_date = _resolve_date(run_date or row["next_run_date"] or datetime.now().date())
            try:
                post_journal_entry(
                    company_key=row["company_key"],
                    date=entry_date,
                    description=f"Recurring: {row['description']}",
                    reference=f"REC-{row['id']}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    lines=lines,
                    created_by=row["created_by"],
                    branch_id=row["branch_id"],
                    source_module=row["source_module"],
                    source_table=row["source_table"],
                    source_type="Recurring",
                    source_id=row["source_id"],
                    conn=conn,
                )
                next_run = _next_recurrence_date(pd.Timestamp(entry_date), row["frequency"]).date()
                conn.execute(
                    "UPDATE recurring_transactions SET last_run_at = ?, next_run_date = ? WHERE id = ?",
                    (datetime.now().isoformat(), next_run.isoformat(), row["id"]),
                )
                count += 1
            except Exception:
                continue
        if owns_connection:
            conn.commit()
        return count
    finally:
        if owns_connection and conn:
            conn.close()


def post_vat_transaction(company_key, date, description, net_amount, vat_amount, vat_type, created_by, branch_id=None, source_module=None, source_table=None, source_id=None, conn=None):
    if vat_type not in {"InputVAT", "OutputVAT"}:
        raise ValueError("vat_type must be 'InputVAT' or 'OutputVAT'.")
    if vat_amount < 0:
        raise ValueError("VAT amount cannot be negative.")
    total_amount = net_amount + vat_amount
    vat_account = "VAT Payable" if vat_type == "OutputVAT" else "VAT Receivable"
    revenue_account = "Sales Revenue" if vat_type == "OutputVAT" else "Inventory"
    lines = [
        {"account_id": get_account_id(conn, revenue_account, "Income" if vat_type == "OutputVAT" else "Asset"), "debit": net_amount if vat_type == "InputVAT" else 0, "credit": net_amount if vat_type == "OutputVAT" else 0},
        {"account_id": get_account_id(conn, vat_account, "Liability" if vat_type == "OutputVAT" else "Asset"), "debit": vat_amount if vat_type == "InputVAT" else 0, "credit": vat_amount if vat_type == "OutputVAT" else 0},
        {"account_id": get_account_id(conn, "Cash" if vat_type == "OutputVAT" else "Accounts Payable", "Asset" if vat_type == "OutputVAT" else "Liability"), "debit": total_amount if vat_type == "OutputVAT" else 0, "credit": total_amount if vat_type == "InputVAT" else 0},
    ]
    return post_journal_entry(
        company_key=company_key,
        date=date,
        description=description,
        reference=f"VAT-{source_id}" if source_id else None,
        lines=lines,
        created_by=created_by,
        branch_id=branch_id,
        source_module=source_module,
        source_table=source_table,
        source_type="VAT",
        source_id=source_id,
        conn=conn,
    )


def _journal_base_query():
    return f"""
        SELECT
            je.id AS entry_id,
            je.date,
            je.description,
            je.reference,
            je.created_by,
            je.branch_id,
            je.customer_id,
            je.supplier_id,
            je.inventory_item_id,
            je.payment_id,
            je.source_module,
            je.source_table,
            je.source_type,
            je.source_id,
            je.reversed_entry_id,
            je.is_voided,
            je.voided_at,
            je.voided_by,
            je.approval_status,
            c.id AS account_id,
            COALESCE(NULLIF(c.code, ''), NULLIF(c.account_code, ''), '') AS account_code,
            {_coa_name_expression()} AS account_name,
            {_coa_type_expression()} AS account_type,
            jl.debit,
            jl.credit
        FROM journal_entries je
        JOIN journal_lines jl ON jl.entry_id = je.id
        JOIN chart_of_accounts c ON c.id = jl.account_id
        WHERE je.company_key = ?
          AND COALESCE(je.is_voided, 0) = 0
          AND COALESCE(je.approval_status, 'Posted') = 'Posted'
    """


def _journal_dataframe(company_key, start_date=None, end_date=None, branch_id=None, account_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = _journal_base_query()
        params = [company_key]
        if start_date:
            query += f" AND {sql_date_on_or_after('je.date')}"
            params.append(_resolve_date(start_date))
        if end_date:
            query += f" AND {sql_date_on_or_before('je.date')}"
            params.append(_resolve_date(end_date))
        if branch_id:
            query += " AND je.branch_id = ?"
            params.append(branch_id)
        if account_id:
            query += " AND c.id = ?"
            params.append(int(account_id))
        query += f" ORDER BY {sql_cast_as_date('je.date')}, je.id, jl.id"
        rows = execute_portable_query(conn, query, tuple(params)).fetchall()
        return pd.DataFrame(rows_to_dicts(rows))
    finally:
        if owns_connection and conn:
            conn.close()


def get_account_total(company_key, account_name_like, start_date=None, end_date=None, branch_id=None, balance_side=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = f"""
            SELECT COALESCE(SUM(jl.debit), 0) AS debit_total, COALESCE(SUM(jl.credit), 0) AS credit_total
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND lower({_coa_name_expression()}) LIKE lower(?)
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """
        params = [company_key, f"{str(account_name_like or '').strip()}%"]
        if start_date:
            query += f" AND {sql_date_on_or_after('je.date')}"
            params.append(_resolve_date(start_date))
        if end_date:
            query += f" AND {sql_date_on_or_before('je.date')}"
            params.append(_resolve_date(end_date))
        if branch_id:
            query += " AND je.branch_id = ?"
            params.append(branch_id)
        row = execute_portable_query(conn, query, tuple(params)).fetchone()
        debit_total = round(float(row_get(row, "debit_total", 0) or 0.0), 2)
        credit_total = round(float(row_get(row, "credit_total", 0) or 0.0), 2)
        if balance_side == "debit":
            return round(debit_total - credit_total, 2)
        if balance_side == "credit":
            return round(credit_total - debit_total, 2)
        return {"debit_total": debit_total, "credit_total": credit_total}
    finally:
        if owns_connection and conn:
            conn.close()


def get_month_sales_total(company_key, year_month=None, branch_id=None, conn=None):
    period_value = str(year_month or datetime.now().strftime("%Y-%m")).strip()
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        month_predicate = sql_year_month_equals("je.date", backend=get_active_db_backend())
        query = f"""
            SELECT COALESCE(SUM(jl.credit), 0) AS sales_total
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND {month_predicate}
              AND lower(COALESCE(NULLIF(c.name, ''), NULLIF(c.account_name, ''), '')) LIKE lower(?)
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """
        params = [company_key, period_value, "sales%"]
        if branch_id:
            query += " AND je.branch_id = ?"
            params.append(branch_id)
        return round(float(fetch_scalar(conn, query, tuple(params), default=0.0) or 0.0), 2)
    finally:
        if owns_connection and conn:
            conn.close()


def get_recent_accounting_activity(company_key, branch_id=None, limit=10, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        date_order = sql_cast_as_date("je.date")
        query = f"""
            SELECT
                je.date,
                COALESCE(je.document_type, je.source_type, je.source_table, je.source_module, 'Journal') AS activity_type,
                je.description,
                je.reference,
                COALESCE(SUM(CASE WHEN jl.debit > 0 THEN jl.debit ELSE jl.credit END), 0) AS amount
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            WHERE je.company_key = ?
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
            GROUP BY je.id, je.date, activity_type, je.description, je.reference
            ORDER BY {date_order} DESC, je.id DESC
            LIMIT ?
        """
        params = [company_key, int(limit)]
        if branch_id:
            query = query.replace(
                "WHERE je.company_key = ?",
                "WHERE je.company_key = ? AND je.branch_id = ?",
                1,
            )
            params = [company_key, branch_id, int(limit)]
        return [row_to_dict(row) for row in execute_portable_query(conn, query, tuple(params)).fetchall()]
    finally:
        if owns_connection and conn:
            conn.close()


def compare_legacy_and_journal_totals(company_key, branch_id=None, logger_instance=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    logger_instance = logger_instance or logger
    comparisons = []
    try:
        current_month = datetime.now().strftime("%Y-%m")
        journal_sales = get_month_sales_total(company_key, year_month=current_month, branch_id=branch_id, conn=conn)
        voucher_sales = 0.0
        try:
            voucher_query = """
                SELECT COALESCE(SUM(credit), 0) AS sales_total
                FROM vouchers
                WHERE company_key = ?
                  AND v_type = 'Sales'
                  AND COALESCE(status, 'Active') != 'Void'
                  AND date LIKE ?
            """
            voucher_params = [company_key, f"{current_month}%"]
            if branch_id:
                voucher_query += " AND branch_id = ?"
                voucher_params.append(branch_id)
            voucher_row = conn.execute(voucher_query, tuple(voucher_params)).fetchone()
            voucher_sales = round(float(voucher_row["sales_total"] or 0.0), 2) if voucher_row else 0.0
        except sqlite3.Error:
            voucher_sales = 0.0
        comparisons.append(
            {
                "metric": "monthly_sales",
                "journal_total": journal_sales,
                "legacy_total": voucher_sales,
                "difference": round(journal_sales - voucher_sales, 2),
            }
        )

        journal_ar = get_account_total(company_key, "Accounts Receivable", branch_id=branch_id, balance_side="debit", conn=conn)
        legacy_ar = 0.0
        try:
            tx_query = """
                SELECT COALESCE(SUM(debit - credit), 0) AS ar_total
                FROM transactions
                WHERE company_key = ?
                  AND lower(account) LIKE 'accounts receivable%'
            """
            tx_params = [company_key]
            if branch_id:
                tx_query += " AND branch_id = ?"
                tx_params.append(branch_id)
            tx_row = conn.execute(tx_query, tuple(tx_params)).fetchone()
            legacy_ar = round(float(tx_row["ar_total"] or 0.0), 2) if tx_row else 0.0
        except sqlite3.Error:
            legacy_ar = 0.0
        comparisons.append(
            {
                "metric": "accounts_receivable",
                "journal_total": journal_ar,
                "legacy_total": legacy_ar,
                "difference": round(journal_ar - legacy_ar, 2),
            }
        )

        for comparison in comparisons:
            if abs(float(comparison["difference"])) >= 0.01:
                logger_instance.warning(
                    "Phase 2 validation mismatch for %s company=%s branch=%s journal=%.2f legacy=%.2f diff=%.2f",
                    comparison["metric"],
                    company_key,
                    branch_id,
                    comparison["journal_total"],
                    comparison["legacy_total"],
                    comparison["difference"],
                )
        return comparisons
    finally:
        if owns_connection and conn:
            conn.close()


def get_trial_balance(company_key, start_date=None, end_date=None, branch_id=None):
    df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date, branch_id=branch_id)
    if df.empty:
        return []
    grouped = (
        df.groupby(["account_id", "account_code", "account_name", "account_type"], as_index=False)[["debit", "credit"]]
        .sum()
        .sort_values(["account_code", "account_name"], na_position="last")
    )
    rows = []
    for _, row in grouped.iterrows():
        debit_total = round(float(row["debit"] or 0.0), 2)
        credit_total = round(float(row["credit"] or 0.0), 2)
        balance = round(
            debit_total - credit_total if _normal_balance(row["account_type"]) == "debit" else credit_total - debit_total,
            2,
        )
        rows.append(
            {
                "account_id": int(row["account_id"]),
                "account_code": row["account_code"],
                "account_name": row["account_name"],
                "account_type": row["account_type"],
                "debit_total": debit_total,
                "credit_total": credit_total,
                "balance": balance,
            }
        )
    return rows


def get_general_ledger(company_key, account_id, start_date, end_date):
    df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date, account_id=account_id)
    if df.empty:
        return []
    running_balance = 0.0
    rows = []
    normal = _normal_balance(df["account_type"].iloc[0])
    for _, row in df.iterrows():
        debit = round(float(row["debit"] or 0.0), 2)
        credit = round(float(row["credit"] or 0.0), 2)
        movement = debit - credit if normal == "debit" else credit - debit
        running_balance = round(running_balance + movement, 2)
        rows.append(
            {
                "date": row["date"],
                "description": row["description"],
                "reference": row["reference"],
                "debit": debit,
                "credit": credit,
                "running_balance": running_balance,
            }
        )
    return rows


def generate_income_statement(company_key, start_date, end_date, branch_id=None):
    rows = []
    gross_revenue = 0.0
    sales_returns = 0.0
    cost_of_sales = 0.0
    operating_expenses = 0.0
    for row in get_trial_balance(company_key, start_date=start_date, end_date=end_date, branch_id=branch_id):
        account_type = str(row["account_type"]).title()
        account_name = str(row["account_name"] or "").strip()
        normalized_name = account_name.lower()
        if account_type == "Income":
            amount = round(row["credit_total"] - row["debit_total"], 2)
            gross_revenue += amount
            rows.append({"category": "Revenue", "account_id": row["account_id"], "account_code": row["account_code"], "account_name": account_name, "amount": amount})
        elif account_type == "Expense":
            amount = round(row["debit_total"] - row["credit_total"], 2)
            if normalized_name == "sales returns and refunds":
                sales_returns += amount
                rows.append({"category": "Sales Deductions", "account_id": row["account_id"], "account_code": row["account_code"], "account_name": "Less: Sales Returns and Refunds", "amount": -amount})
            elif normalized_name == "cost of goods sold":
                cost_of_sales += amount
                rows.append({"category": "Cost of Sales", "account_id": row["account_id"], "account_code": row["account_code"], "account_name": account_name, "amount": amount})
            else:
                operating_expenses += amount
                rows.append({"category": "Operating Expenses", "account_id": row["account_id"], "account_code": row["account_code"], "account_name": account_name, "amount": amount})
    net_sales = round(gross_revenue - sales_returns, 2)
    gross_profit = round(net_sales - cost_of_sales, 2)
    net_profit = round(gross_profit - operating_expenses, 2)
    rows.append({"category": "Revenue", "account_id": None, "account_code": "", "account_name": "Net Sales", "amount": net_sales})
    rows.append({"category": "Profit", "account_id": None, "account_code": "", "account_name": "Gross Profit", "amount": gross_profit})
    rows.append({"category": "Profit", "account_id": None, "account_code": "", "account_name": "Net Profit", "amount": net_profit})
    return rows


def generate_balance_sheet(company_key, as_of_date, branch_id=None):
    rows = []
    for row in get_trial_balance(company_key, end_date=as_of_date, branch_id=branch_id):
        account_type = str(row["account_type"]).title()
        if account_type not in {"Asset", "Liability", "Equity"}:
            continue
        amount = round(row["debit_total"] - row["credit_total"], 2) if account_type == "Asset" else round(row["credit_total"] - row["debit_total"], 2)
        rows.append({"category": account_type, "account_id": row["account_id"], "account_code": row["account_code"], "account_name": row["account_name"], "amount": amount})
    profit_rows = generate_income_statement(company_key, None, as_of_date, branch_id=branch_id)
    net_profit = next((row["amount"] for row in profit_rows if row["account_name"] == "Net Profit"), 0.0)
    rows.append({"category": "Equity", "account_id": None, "account_code": "", "account_name": "Current Period Earnings", "amount": round(net_profit, 2)})
    return rows


def generate_cash_flow_statement(company_key, start_date, end_date, branch_id=None):
    journal_df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date, branch_id=branch_id)
    if journal_df.empty:
        return []
    cash_equivalent_accounts = {"Cash", "Bank", "Mobile Money"}
    cash_df = journal_df[journal_df["account_name"].isin(cash_equivalent_accounts)].copy()
    if cash_df.empty:
        return []
    rows = []
    totals = {"Operating Activities": 0.0, "Investing Activities": 0.0, "Financing Activities": 0.0}
    for _, row in cash_df.iterrows():
        description = str(row["description"] or "").lower()
        source_module = str(row.get("source_module") or "").lower()
        source_type = str(row.get("source_type") or "").lower()
        other_side = journal_df[
            (journal_df["entry_id"] == row["entry_id"]) & (journal_df["account_id"] != row["account_id"])
        ]
        counterpart_types = {str(value).title() for value in other_side["account_type"].tolist()}
        counterpart_names = {str(value) for value in other_side["account_name"].tolist()}
        non_cash_counterpart_names = {name for name in counterpart_names if name not in cash_equivalent_accounts}
        movement = round(float(row["debit"] or 0.0) - float(row["credit"] or 0.0), 2)
        if counterpart_names and counterpart_names <= cash_equivalent_accounts:
            section = "Internal Transfers"
        elif (
            {"Accounts Receivable", "Accounts Payable"} & counterpart_names
            or "payroll" in source_module
            or "payroll" in source_type
            or "salary expense" in {name.lower() for name in non_cash_counterpart_names}
            or "taxation" in source_module
            or "tax settlement" in source_type
            or any("tax" in name.lower() or "vat" in name.lower() or "nhil" in name.lower() or "getfund" in name.lower() for name in non_cash_counterpart_names)
        ):
            section = "Operating Activities"
        elif "Fixed Assets" in counterpart_names or "Accumulated Depreciation" in counterpart_names or "fixed assets" in source_module:
            section = "Investing Activities"
        elif (
            {"Owner Capital", "Owner Drawings", "Retained Earnings", "Loan Payable", "Loans Payable"} & counterpart_names
            or any("loan" in name.lower() for name in non_cash_counterpart_names)
            or counterpart_types & {"Equity"}
        ):
            section = "Financing Activities"
        elif counterpart_types & {"Income", "Expense"}:
            section = "Operating Activities"
        elif counterpart_types & {"Liability"}:
            section = "Financing Activities"
        elif "depreciation" in description:
            section = "Operating Activities"
        else:
            section = "Operating Activities"
        if section in totals:
            totals[section] += movement
        rows.append(
            {
                "section": section,
                "line_item": row["description"],
                "amount": movement,
                "date": row["date"],
                "reference": row["reference"],
            }
        )
    internal_transfer_total = round(sum(float(row["amount"] or 0.0) for row in rows if row["section"] == "Internal Transfers"), 2)
    if any(row["section"] == "Internal Transfers" for row in rows):
        rows.append(
            {
                "section": "Internal Transfers",
                "line_item": "Net Internal Cash/Bank/Mobile Money Transfers",
                "amount": internal_transfer_total,
                "date": None,
                "reference": None,
            }
        )
    rows.extend(
        [
            {"section": key, "line_item": f"Net Cash from {key}", "amount": round(value, 2), "date": None, "reference": None}
            for key, value in totals.items()
        ]
    )
    rows.append(
        {
            "section": "Net Change",
            "line_item": "Net Cash Change",
            "amount": round(sum(totals.values()), 2),
            "date": None,
            "reference": None,
        }
    )
    return rows


def _aging_bucket(days_outstanding):
    days = int(days_outstanding or 0)
    if days <= 0:
        return "Current"
    if days <= 30:
        return "1-30 Days"
    if days <= 60:
        return "31-60 Days"
    if days <= 90:
        return "61-90 Days"
    return "90+ Days"


def get_ar_aging_report(company_key, as_of_date=None):
    report_date = pd.Timestamp(as_of_date or datetime.now().date())
    conn = get_connection()
    try:
        customers = execute_portable_query(
            conn,
            "SELECT id, customer_id, name, phone, email FROM customers WHERE company_key = ? ORDER BY customers.name",
            (company_key,),
        ).fetchall()
        rows = []
        for customer in customers:
            customer_id = int(row_get(customer, "id"))
            gl_balance = get_customer_balance(company_key, customer_id, as_of_date=report_date.date(), conn=conn)
            customer_label = row_get(customer, "customer_id") or f"CUST-{customer_id:06d}"
            document_remaining_total = 0.0
            invoice_rows = execute_portable_query(
                conn,
                """
                SELECT
                    i.id,
                    i.invoice_number,
                    i.invoice_date,
                    COALESCE(NULLIF(i.due_date, ''), i.invoice_date) AS due_date,
                    ROUND(COALESCE(i.amount, 0) + COALESCE(i.output_vat, 0), 2) AS original_amount,
                    ROUND(
                        COALESCE((
                            SELECT SUM(pa.amount)
                            FROM payment_allocations pa
                            JOIN payments p ON p.id = pa.payment_id
                            WHERE pa.invoice_id = i.id
                              AND p.company_key = i.company_key
                              AND date(p.payment_date) <= date(?)
                              AND COALESCE(p.approval_status, p.status, 'Posted') = 'Posted'
                        ), 0)
                        +
                        COALESCE((
                            SELECT SUM(p.amount)
                            FROM payments p
                            WHERE p.invoice_id = i.id
                              AND p.company_key = i.company_key
                              AND date(p.payment_date) <= date(?)
                              AND COALESCE(p.approval_status, p.status, 'Posted') = 'Posted'
                              AND NOT EXISTS (
                                  SELECT 1
                                  FROM payment_allocations pa
                                  WHERE pa.payment_id = p.id
                                    AND pa.invoice_id = i.id
                              )
                        ), 0),
                        2
                    ) AS paid_amount
                FROM invoices i
                WHERE i.company_key = ?
                  AND i.customer_id = ?
                  AND date(i.invoice_date) <= date(?)
                  AND COALESCE(i.approval_status, i.status, 'Draft') = 'Posted'
                ORDER BY date(COALESCE(NULLIF(i.due_date, ''), i.invoice_date)), i.id
                """,
                (
                    _resolve_date(report_date.date()),
                    _resolve_date(report_date.date()),
                    company_key,
                    customer_id,
                    _resolve_date(report_date.date()),
                ),
            ).fetchall()
            for invoice in invoice_rows:
                original_amount = round(float(row_get(invoice, "original_amount", 0) or 0.0), 2)
                paid_amount = round(float(row_get(invoice, "paid_amount", 0) or 0.0), 2)
                remaining = round(original_amount - paid_amount, 2)
                if remaining <= 0.005:
                    continue
                due_date = pd.Timestamp(row_get(invoice, "due_date") or row_get(invoice, "invoice_date") or report_date)
                days_overdue = max(int((report_date - due_date).days), 0)
                document_remaining_total = round(document_remaining_total + remaining, 2)
                rows.append(
                    {
                        "customer_id": customer_label,
                        "customer_name": row_get(customer, "name"),
                        "document_type": "Invoice",
                        "document_number": row_get(invoice, "invoice_number") or f"INV-{int(row_get(invoice, 'id', 0))}",
                        "document_date": row_get(invoice, "invoice_date"),
                        "due_date": row_get(invoice, "due_date"),
                        "phone": row_get(customer, "phone"),
                        "email": row_get(customer, "email"),
                        "original_amount": original_amount,
                        "paid_amount": paid_amount,
                        "remaining_balance": remaining,
                        "days_overdue": days_overdue,
                        "days_outstanding": days_overdue,
                        "bucket": _aging_bucket(days_overdue),
                        "balance": remaining,
                    }
                )
            legacy_balance = round(gl_balance - document_remaining_total, 2)
            if abs(legacy_balance) >= 0.005:
                oldest_row = execute_portable_query(
                    conn,
                    f"""
                    SELECT MIN(date(je.date)) AS oldest_open_date
                    FROM journal_entries je
                    JOIN journal_lines jl ON jl.entry_id = je.id
                    JOIN chart_of_accounts c ON c.id = jl.account_id
                    WHERE je.company_key = ?
                      AND je.customer_id = ?
                      AND jl.debit > 0
                      AND lower({_coa_name_expression()}) LIKE lower(?)
                      AND date(je.date) <= date(?)
                      AND COALESCE(je.is_voided, 0) = 0
                      AND COALESCE(je.approval_status, 'Posted') = 'Posted'
                    """,
                    (company_key, customer_id, "accounts receivable%", _resolve_date(report_date.date())),
                ).fetchone()
                oldest_date = pd.Timestamp(row_get(oldest_row, "oldest_open_date")) if oldest_row and row_get(oldest_row, "oldest_open_date") else report_date
                days = max(int((report_date - oldest_date).days), 0)
                rows.append(
                    {
                        "customer_id": customer_label,
                        "customer_name": row_get(customer, "name"),
                        "document_type": "Legacy / Unallocated",
                        "document_number": "Unallocated AR Balance",
                        "document_date": oldest_date.date().isoformat() if hasattr(oldest_date, "date") else str(oldest_date),
                        "due_date": oldest_date.date().isoformat() if hasattr(oldest_date, "date") else str(oldest_date),
                        "phone": row_get(customer, "phone"),
                        "email": row_get(customer, "email"),
                        "original_amount": round(legacy_balance, 2),
                        "paid_amount": 0.0,
                        "remaining_balance": round(legacy_balance, 2),
                        "days_overdue": days if legacy_balance > 0 else 0,
                        "days_outstanding": days if legacy_balance > 0 else 0,
                        "bucket": _aging_bucket(days if legacy_balance > 0 else 0),
                        "balance": round(legacy_balance, 2),
                    }
                )
        return rows
    finally:
        conn.close()


def get_supplier_balance(company_key, supplier_id, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = f"""
            SELECT COALESCE(SUM(jl.credit - jl.debit), 0) AS balance
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND je.supplier_id = ?
              AND lower({_coa_name_expression()}) LIKE lower(?)
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """
        params = [company_key, int(supplier_id), "accounts payable%"]
        if as_of_date:
            query += f" AND {sql_date_on_or_before('je.date')}"
            params.append(_resolve_date(as_of_date))
        balance = fetch_scalar(conn, query, tuple(params), default=0.0)
        return round(float(balance or 0.0), 2)
    finally:
        if owns_connection and conn:
            conn.close()


def get_supplier_balances(company_key, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        rows = execute_portable_query(
            conn,
            """
            SELECT id, name, email, phone, address
            FROM suppliers
            WHERE company_key = ?
            ORDER BY suppliers.name
            """,
            (company_key,),
        ).fetchall()
        balance_map = _supplier_balance_map(company_key, as_of_date=as_of_date, conn=conn)
        return [
            {
                "id": int(row_get(row, "id")),
                "name": row_get(row, "name"),
                "email": row_get(row, "email"),
                "phone": row_get(row, "phone"),
                "address": row_get(row, "address"),
                "balance": balance_map.get(int(row_get(row, "id")), 0.0),
            }
            for row in rows
        ]
    finally:
        if owns_connection and conn:
            conn.close()


def get_ap_aging_report(company_key, as_of_date=None):
    report_date = pd.Timestamp(as_of_date or datetime.now().date())
    conn = get_connection()
    try:
        suppliers = conn.execute(
            """
            SELECT id, name, email, phone, address
            FROM suppliers
            WHERE company_key = ?
            ORDER BY name
            """,
            (company_key,),
        ).fetchall()
        rows = []
        for supplier in suppliers:
            supplier_id = int(supplier["id"])
            gl_balance = get_supplier_balance(company_key, supplier_id, as_of_date=report_date.date(), conn=conn)
            document_remaining_total = 0.0
            bill_rows = conn.execute(
                """
                SELECT
                    b.id,
                    b.bill_number,
                    b.bill_date,
                    COALESCE(NULLIF(b.due_date, ''), b.bill_date) AS due_date,
                    ROUND(COALESCE(b.amount, 0) + COALESCE(b.input_vat, 0), 2) AS original_amount,
                    ROUND(
                        COALESCE((
                            SELECT SUM(pa.amount)
                            FROM payment_allocations pa
                            JOIN payments p ON p.id = pa.payment_id
                            WHERE pa.bill_id = b.id
                              AND p.company_key = b.company_key
                              AND date(p.payment_date) <= date(?)
                              AND COALESCE(p.approval_status, p.status, 'Posted') = 'Posted'
                        ), 0)
                        +
                        COALESCE((
                            SELECT SUM(p.amount)
                            FROM payments p
                            WHERE p.bill_id = b.id
                              AND p.company_key = b.company_key
                              AND date(p.payment_date) <= date(?)
                              AND COALESCE(p.approval_status, p.status, 'Posted') = 'Posted'
                              AND NOT EXISTS (
                                  SELECT 1
                                  FROM payment_allocations pa
                                  WHERE pa.payment_id = p.id
                                    AND pa.bill_id = b.id
                              )
                        ), 0),
                        2
                    ) AS paid_amount
                FROM bills b
                WHERE b.company_key = ?
                  AND b.supplier_id = ?
                  AND date(b.bill_date) <= date(?)
                  AND COALESCE(b.approval_status, b.status, 'Draft') = 'Posted'
                ORDER BY date(COALESCE(NULLIF(b.due_date, ''), b.bill_date)), b.id
                """,
                (
                    _resolve_date(report_date.date()),
                    _resolve_date(report_date.date()),
                    company_key,
                    supplier_id,
                    _resolve_date(report_date.date()),
                ),
            ).fetchall()
            for bill in bill_rows:
                original_amount = round(float(bill["original_amount"] or 0.0), 2)
                paid_amount = round(float(bill["paid_amount"] or 0.0), 2)
                remaining = round(original_amount - paid_amount, 2)
                if remaining <= 0.005:
                    continue
                due_date = pd.Timestamp(bill["due_date"] or bill["bill_date"] or report_date)
                days_overdue = max(int((report_date - due_date).days), 0)
                document_remaining_total = round(document_remaining_total + remaining, 2)
                rows.append(
                    {
                        "supplier_id": supplier_id,
                        "supplier_name": supplier["name"],
                        "document_type": "Bill",
                        "document_number": bill["bill_number"] or f"BILL-{int(bill['id'])}",
                        "document_date": bill["bill_date"],
                        "due_date": bill["due_date"],
                        "email": supplier["email"],
                        "phone": supplier["phone"],
                        "address": supplier["address"],
                        "original_amount": original_amount,
                        "paid_amount": paid_amount,
                        "remaining_balance": remaining,
                        "days_overdue": days_overdue,
                        "days_outstanding": days_overdue,
                        "bucket": _aging_bucket(days_overdue),
                        "balance": remaining,
                    }
                )
            legacy_balance = round(gl_balance - document_remaining_total, 2)
            if abs(legacy_balance) >= 0.005:
                oldest_row = conn.execute(
                    f"""
                    SELECT MIN(date(je.date)) AS oldest_open_date
                    FROM journal_entries je
                    JOIN journal_lines jl ON jl.entry_id = je.id
                    JOIN chart_of_accounts c ON c.id = jl.account_id
                    WHERE je.company_key = ?
                      AND je.supplier_id = ?
                      AND jl.credit > 0
                      AND lower({_coa_name_expression()}) LIKE 'accounts payable%'
                      AND date(je.date) <= date(?)
                      AND COALESCE(je.is_voided, 0) = 0
                      AND COALESCE(je.approval_status, 'Posted') = 'Posted'
                    """,
                    (company_key, supplier_id, _resolve_date(report_date.date())),
                ).fetchone()
                oldest_date = pd.Timestamp(oldest_row["oldest_open_date"]) if oldest_row and oldest_row["oldest_open_date"] else report_date
                days = max(int((report_date - oldest_date).days), 0)
                rows.append(
                    {
                        "supplier_id": supplier_id,
                        "supplier_name": supplier["name"],
                        "document_type": "Legacy / Unallocated",
                        "document_number": "Unallocated AP Balance",
                        "document_date": oldest_date.date().isoformat() if hasattr(oldest_date, "date") else str(oldest_date),
                        "due_date": oldest_date.date().isoformat() if hasattr(oldest_date, "date") else str(oldest_date),
                        "email": supplier["email"],
                        "phone": supplier["phone"],
                        "address": supplier["address"],
                        "original_amount": round(legacy_balance, 2),
                        "paid_amount": 0.0,
                        "remaining_balance": round(legacy_balance, 2),
                        "days_overdue": days if legacy_balance > 0 else 0,
                        "days_outstanding": days if legacy_balance > 0 else 0,
                        "bucket": _aging_bucket(days if legacy_balance > 0 else 0),
                        "balance": round(legacy_balance, 2),
                    }
                )
        return rows
    finally:
        conn.close()


def close_fiscal_year(company_key, closing_date, created_by, branch_id=None, conn=None):
    closing_date = _resolve_date(closing_date)
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        income_statement = generate_income_statement(company_key, None, closing_date)
        net_profit = round(sum(row["amount"] for row in income_statement if row["account_name"] == "Net Profit"), 2)
        if abs(net_profit) < 0.005:
            return None
        income_rows = [row for row in get_trial_balance(company_key, end_date=closing_date) if str(row["account_type"]).title() == "Income" and abs(row["credit_total"] - row["debit_total"]) > 0.005]
        expense_rows = [row for row in get_trial_balance(company_key, end_date=closing_date) if str(row["account_type"]).title() == "Expense" and abs(row["debit_total"] - row["credit_total"]) > 0.005]
        lines = []
        for row in income_rows:
            amount = round(row["credit_total"] - row["debit_total"], 2)
            lines.append({"account_id": row["account_id"], "debit": amount, "credit": 0})
        for row in expense_rows:
            amount = round(row["debit_total"] - row["credit_total"], 2)
            lines.append({"account_id": row["account_id"], "debit": 0, "credit": amount})
        retained_earnings_id = get_account_id(conn, "Retained Earnings", "Equity")
        if net_profit >= 0:
            lines.append({"account_id": retained_earnings_id, "debit": 0, "credit": net_profit})
        else:
            lines.append({"account_id": retained_earnings_id, "debit": abs(net_profit), "credit": 0})
        entry_id = post_journal_entry(
            company_key=company_key,
            date=closing_date,
            description=f"Year-end closing entry {closing_date[:4]}",
            reference=f"YEC-{closing_date}",
            lines=lines,
            created_by=created_by,
            branch_id=branch_id,
            source_module="Year End Closing",
            source_table="journal_entries",
            conn=conn,
        )
        if owns_connection:
            conn.commit()
        return entry_id
    finally:
        if owns_connection and conn:
            conn.close()


def get_bank_reconciliation(company_key, start_date=None, end_date=None):
    conn = get_connection()
    try:
        journal_df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date, conn=conn)
        bank_df = journal_df[journal_df["account_name"].isin(["Bank", "Mobile Money"])].copy()
        if bank_df.empty:
            return {"matched": [], "unmatched_journal": [], "summary": {"journal_total": 0.0, "matched_total": 0.0, "unmatched_total": 0.0}}
        payment_rows = conn.execute(
            """
            SELECT id, payment_date, amount, method, reference, payment_type
            FROM payments
            WHERE company_key = ?
              AND method IN ('Bank', 'Mobile Money')
              AND COALESCE(approval_status, 'Posted') = 'Posted'
              {start_clause}
              {end_clause}
            ORDER BY date(payment_date), id
            """.format(
                start_clause="AND date(payment_date) >= date(?)" if start_date else "",
                end_clause="AND date(payment_date) <= date(?)" if end_date else "",
            ),
            tuple(
                [company_key]
                + ([_resolve_date(start_date)] if start_date else [])
                + ([_resolve_date(end_date)] if end_date else [])
            ),
        ).fetchall()
        matched = []
        unmatched = []
        used_payment_ids = set()
        for _, row in bank_df.iterrows():
            movement = round(float(row["debit"] or 0.0) - float(row["credit"] or 0.0), 2)
            match = next(
                (
                    payment
                    for payment in payment_rows
                    if int(payment["id"]) not in used_payment_ids
                    and round(float(payment["amount"] or 0.0), 2) == abs(movement)
                    and (not row["reference"] or not payment["reference"] or str(payment["reference"]) == str(row["reference"]))
                ),
                None,
            )
            journal_item = {
                "date": row["date"],
                "description": row["description"],
                "reference": row["reference"],
                "account": row["account_name"],
                "movement": movement,
            }
            if match:
                used_payment_ids.add(int(match["id"]))
                matched.append(
                    {
                        **journal_item,
                        "payment_id": int(match["id"]),
                        "payment_date": match["payment_date"],
                        "payment_reference": match["reference"],
                        "payment_type": match["payment_type"],
                    }
                )
            else:
                unmatched.append(journal_item)
        return {
            "matched": matched,
            "unmatched_journal": unmatched,
            "summary": {
                "journal_total": round(float(bank_df["debit"].sum() - bank_df["credit"].sum()), 2),
                "matched_total": round(sum(item["movement"] for item in matched), 2),
                "unmatched_total": round(sum(item["movement"] for item in unmatched), 2),
            },
        }
    finally:
        conn.close()


def _table_exists(conn, table_name):
    return bool(
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
            (str(table_name or "").strip(),),
        ).fetchone()
    )


def _account_balance_snapshot(company_key, account_names, as_of_date=None, branch_id=None, conn=None):
    rows = []
    for account_name in account_names:
        account_total = get_account_total(
            company_key,
            account_name,
            end_date=as_of_date,
            branch_id=branch_id,
            conn=conn,
        )
        debit_total = round(float(account_total.get("debit_total") or 0.0), 2)
        credit_total = round(float(account_total.get("credit_total") or 0.0), 2)
        balance = round(debit_total - credit_total, 2)
        rows.append(
            {
                "account_name": account_name,
                "debit_total": debit_total,
                "credit_total": credit_total,
                "balance": balance,
            }
        )
    return rows


def get_reporting_trust_diagnostics(company_key, start_date=None, end_date=None, branch_id=None, conn=None):
    """Validate report outputs against posted journal data and reconciliation rules."""
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        report_end_date = end_date or datetime.now().date()
        trial_balance = get_trial_balance(company_key, start_date=start_date, end_date=end_date, branch_id=branch_id)
        total_debits = round(sum(float(row.get("debit_total") or 0.0) for row in trial_balance), 2)
        total_credits = round(sum(float(row.get("credit_total") or 0.0) for row in trial_balance), 2)
        trial_balance_difference = round(total_debits - total_credits, 2)

        balance_sheet = generate_balance_sheet(company_key, report_end_date, branch_id=branch_id)
        assets = round(sum(float(row.get("amount") or 0.0) for row in balance_sheet if str(row.get("category")).title() == "Asset"), 2)
        liabilities = round(sum(float(row.get("amount") or 0.0) for row in balance_sheet if str(row.get("category")).title() == "Liability"), 2)
        equity = round(sum(float(row.get("amount") or 0.0) for row in balance_sheet if str(row.get("category")).title() == "Equity"), 2)
        balance_sheet_difference = round(assets - (liabilities + equity), 2)

        income_statement = generate_income_statement(company_key, start_date, report_end_date, branch_id=branch_id)
        income_accounts = [row for row in income_statement if str(row.get("category")).lower() in {"income", "revenue"}]
        expense_accounts = [row for row in income_statement if str(row.get("category")).lower() in {"expense", "operating expenses", "cost of sales"}]
        net_profit = round(
            sum(float(row.get("amount") or 0.0) for row in income_statement if str(row.get("account_name")) == "Net Profit"),
            2,
        )

        integrity = get_finance_integrity_diagnostics(company_key, as_of_date=end_date, branch_id=branch_id, conn=conn)
        bank_reconciliation = get_bank_reconciliation(company_key, start_date=start_date, end_date=end_date)
        period_control = get_period_control_diagnostics(company_key, as_of_date=report_end_date, conn=conn)
        ar_aging_total = round(sum(float(row.get("remaining_balance", row.get("balance", 0.0)) or 0.0) for row in get_ar_aging_report(company_key, as_of_date=report_end_date)), 2)
        ap_aging_total = round(sum(float(row.get("remaining_balance", row.get("balance", 0.0)) or 0.0) for row in get_ap_aging_report(company_key, as_of_date=report_end_date)), 2)
        ar_gl_balance = round(float(integrity["accounts_receivable"]["control_account_balance"] or 0.0), 2)
        ap_gl_balance = round(float(integrity["accounts_payable"]["control_account_balance"] or 0.0), 2)

        cash_account_names = ["Cash", "Bank", "Mobile Money"]
        cash_balances = _account_balance_snapshot(company_key, cash_account_names, as_of_date=report_end_date, branch_id=branch_id, conn=conn)
        for cash_row in cash_balances:
            cash_row["balance"] = round(float(cash_row["debit_total"] or 0.0) - float(cash_row["credit_total"] or 0.0), 2)
        cash_gl_total = round(sum(float(row["balance"] or 0.0) for row in cash_balances), 2)

        fixed_assets_register_total = None
        if _table_exists(conn, "fixed_assets"):
            try:
                fixed_assets_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(COALESCE(book_value, cost, 0)), 0) AS register_total
                    FROM fixed_assets
                    WHERE company_key = ?
                      AND lower(COALESCE(status, 'Active')) NOT IN ('deleted', 'voided', 'cancelled')
                    """,
                    (company_key,),
                ).fetchone()
                fixed_assets_register_total = round(float(fixed_assets_row["register_total"] or 0.0), 2) if fixed_assets_row else 0.0
            except Exception:
                fixed_assets_register_total = None
        fixed_assets_cost_gl = round(float(get_account_total(company_key, "Fixed Assets", end_date=report_end_date, branch_id=branch_id, balance_side="debit", conn=conn)), 2)
        accumulated_depreciation_gl = round(float(get_account_total(company_key, "Accumulated Depreciation", end_date=report_end_date, branch_id=branch_id, balance_side="credit", conn=conn)), 2)
        fixed_assets_net_gl = round(fixed_assets_cost_gl - accumulated_depreciation_gl, 2)

        payroll_liability_accounts = [
            "Payroll Payable",
            "SSNIT Payable",
            "PAYE Payable",
            "Other Payroll Deductions Payable",
        ]
        payroll_liabilities = _account_balance_snapshot(company_key, payroll_liability_accounts, as_of_date=report_end_date, branch_id=branch_id, conn=conn)
        for payroll_row in payroll_liabilities:
            payroll_row["balance"] = round(float(payroll_row["credit_total"] or 0.0) - float(payroll_row["debit_total"] or 0.0), 2)

        tax_liability_accounts = [
            "VAT Payable",
            "NHIL Payable",
            "GETFund Levy Payable",
        ]
        tax_liabilities = _account_balance_snapshot(company_key, tax_liability_accounts, as_of_date=report_end_date, branch_id=branch_id, conn=conn)
        for tax_row in tax_liabilities:
            tax_row["balance"] = round(float(tax_row["credit_total"] or 0.0) - float(tax_row["debit_total"] or 0.0), 2)

        warnings = []
        if abs(trial_balance_difference) >= 0.01:
            warnings.append(f"Trial Balance is out of balance by {trial_balance_difference:.2f}.")
        if abs(balance_sheet_difference) >= 0.01:
            warnings.append(f"Balance Sheet does not balance by {balance_sheet_difference:.2f}.")
        if abs(ar_aging_total - ar_gl_balance) >= 0.01:
            warnings.append(f"A/R aging differs from A/R control by {ar_aging_total - ar_gl_balance:.2f}.")
        if abs(ap_aging_total - ap_gl_balance) >= 0.01:
            warnings.append(f"A/P aging differs from A/P control by {ap_aging_total - ap_gl_balance:.2f}.")
        if fixed_assets_register_total is not None and abs(fixed_assets_register_total - fixed_assets_net_gl) >= 0.01:
            warnings.append(f"Fixed asset register differs from fixed asset GL by {fixed_assets_register_total - fixed_assets_net_gl:.2f}.")
        if not income_accounts and not expense_accounts:
            warnings.append("Profit & Loss has no revenue or expense journal activity for the selected range.")
        if integrity["unbalanced_journal_count"]:
            warnings.append(f"{integrity['unbalanced_journal_count']} posted journal(s) are unbalanced.")
        if integrity["orphaned_journal_reference_count"]:
            warnings.append(f"{integrity['orphaned_journal_reference_count']} posted journal source reference(s) are orphaned.")
        if bank_reconciliation["summary"]["unmatched_total"]:
            warnings.append("Cash/Bank reconciliation has unmatched posted journal movement.")
        warnings.extend(period_control.get("warnings") or [])

        return {
            "report_source": "journal_entries + journal_lines, Posted only, non-voided only",
            "trial_balance": {
                "total_debits": total_debits,
                "total_credits": total_credits,
                "difference": trial_balance_difference,
                "balanced": abs(trial_balance_difference) < 0.01,
                "account_count": len(trial_balance),
            },
            "balance_sheet": {
                "assets": assets,
                "liabilities": liabilities,
                "equity": equity,
                "difference": balance_sheet_difference,
                "balanced": abs(balance_sheet_difference) < 0.01,
            },
            "profit_and_loss": {
                "income_account_count": len(income_accounts),
                "expense_account_count": len(expense_accounts),
                "net_profit": net_profit,
                "journal_driven": True,
            },
            "reconciliation": {
                "accounts_receivable": integrity["accounts_receivable"],
                "accounts_payable": integrity["accounts_payable"],
                "inventory": integrity["inventory"],
                "cash_bank": bank_reconciliation["summary"],
                "unbalanced_journal_count": integrity["unbalanced_journal_count"],
                "orphaned_journal_reference_count": integrity["orphaned_journal_reference_count"],
            },
            "ar_aging": {
                "aging_total": ar_aging_total,
                "gl_control_balance": ar_gl_balance,
                "difference": round(ar_aging_total - ar_gl_balance, 2),
                "reconciled": abs(ar_aging_total - ar_gl_balance) < 0.01,
            },
            "ap_aging": {
                "aging_total": ap_aging_total,
                "gl_control_balance": ap_gl_balance,
                "difference": round(ap_aging_total - ap_gl_balance, 2),
                "reconciled": abs(ap_aging_total - ap_gl_balance) < 0.01,
            },
            "cash_book": {
                "account_balances": cash_balances,
                "combined_cash_equivalent_balance": cash_gl_total,
                "gl_cash_equivalent_balance": cash_gl_total,
                "reconciled": True,
            },
            "fixed_assets": {
                "register_book_value": fixed_assets_register_total,
                "gl_cost_balance": fixed_assets_cost_gl,
                "gl_accumulated_depreciation": accumulated_depreciation_gl,
                "gl_net_balance": fixed_assets_net_gl,
                "difference": None if fixed_assets_register_total is None else round(fixed_assets_register_total - fixed_assets_net_gl, 2),
                "reconciled": fixed_assets_register_total is None or abs(fixed_assets_register_total - fixed_assets_net_gl) < 0.01,
            },
            "payroll_liabilities": {
                "account_balances": payroll_liabilities,
                "total_balance": round(sum(float(row["balance"] or 0.0) for row in payroll_liabilities), 2),
            },
            "tax_liabilities": {
                "account_balances": tax_liabilities,
                "total_balance": round(sum(float(row["balance"] or 0.0) for row in tax_liabilities), 2),
            },
            "period_control": period_control,
            "warnings": warnings,
            "ok": not warnings,
        }
    finally:
        if owns_connection and conn:
            conn.close()


def _customer_balance_map(company_key, as_of_date=None, conn=None):
    date_filter = ""
    params = [company_key, "accounts receivable%"]
    if as_of_date:
        date_filter = f" AND {sql_date_on_or_before('je.date')}"
        params.append(_resolve_date(as_of_date))
    rows = execute_portable_query(
        conn,
        f"""
        SELECT je.customer_id AS customer_id,
               COALESCE(SUM(jl.debit - jl.credit), 0) AS balance
        FROM journal_entries je
        JOIN journal_lines jl ON jl.entry_id = je.id
        JOIN chart_of_accounts c ON c.id = jl.account_id
        WHERE je.company_key = ?
          AND je.customer_id IS NOT NULL
          AND lower({_coa_name_expression()}) LIKE lower(?)
          AND COALESCE(je.is_voided, 0) = 0
          AND COALESCE(je.approval_status, 'Posted') = 'Posted'
          {date_filter}
        GROUP BY je.customer_id
        """,
        tuple(params),
    ).fetchall()
    return {
        int(row_get(row, "customer_id")): round(float(row_get(row, "balance", 0) or 0.0), 2)
        for row in rows
        if row_get(row, "customer_id") not in (None, "")
    }


def _supplier_balance_map(company_key, as_of_date=None, conn=None):
    date_filter = ""
    params = [company_key, "accounts payable%"]
    if as_of_date:
        date_filter = f" AND {sql_date_on_or_before('je.date')}"
        params.append(_resolve_date(as_of_date))
    rows = execute_portable_query(
        conn,
        f"""
        SELECT je.supplier_id AS supplier_id,
               COALESCE(SUM(jl.credit - jl.debit), 0) AS balance
        FROM journal_entries je
        JOIN journal_lines jl ON jl.entry_id = je.id
        JOIN chart_of_accounts c ON c.id = jl.account_id
        WHERE je.company_key = ?
          AND je.supplier_id IS NOT NULL
          AND lower({_coa_name_expression()}) LIKE lower(?)
          AND COALESCE(je.is_voided, 0) = 0
          AND COALESCE(je.approval_status, 'Posted') = 'Posted'
          {date_filter}
        GROUP BY je.supplier_id
        """,
        tuple(params),
    ).fetchall()
    return {
        int(row_get(row, "supplier_id")): round(float(row_get(row, "balance", 0) or 0.0), 2)
        for row in rows
        if row_get(row, "supplier_id") not in (None, "")
    }


def get_customer_balance(company_key, customer_id, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = f"""
            SELECT COALESCE(SUM(jl.debit - jl.credit), 0) AS balance
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND je.customer_id = ?
              AND lower({_coa_name_expression()}) LIKE lower(?)
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """
        params = [company_key, int(customer_id), "accounts receivable%"]
        if as_of_date:
            query += f" AND {sql_date_on_or_before('je.date')}"
            params.append(_resolve_date(as_of_date))
        balance = fetch_scalar(conn, query, tuple(params), default=0.0)
        return round(float(balance or 0.0), 2)
    finally:
        if owns_connection and conn:
            conn.close()


def get_customer_balances(company_key, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        rows = execute_portable_query(
            conn,
            """
            SELECT id, customer_id, name, phone, email
            FROM customers
            WHERE company_key = ?
            ORDER BY customers.name
            """,
            (company_key,),
        ).fetchall()
        balance_map = _customer_balance_map(company_key, as_of_date=as_of_date, conn=conn)
        return [
            {
                "id": int(row_get(row, "id")),
                "customer_id": row_get(row, "customer_id") or f"CUST-{int(row_get(row, 'id')):06d}",
                "name": row_get(row, "name"),
                "phone": row_get(row, "phone"),
                "email": row_get(row, "email"),
                "balance": balance_map.get(int(row_get(row, "id")), 0.0),
            }
            for row in rows
        ]
    finally:
        if owns_connection and conn:
            conn.close()
