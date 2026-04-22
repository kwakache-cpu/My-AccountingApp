from __future__ import annotations

from datetime import datetime
import json
import logging
import sqlite3

import pandas as pd

from database import get_connection


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
CONTROL_ACCOUNT_NAMES = {"Accounts Receivable", "Accounts Payable", "Inventory"}
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


def normalize_document_status(value, default="Draft"):
    normalized = str(value or "").strip().title()
    return normalized if normalized in VALID_DOCUMENT_CONTROL_STATUSES else str(default)


def _is_posting_status(value):
    return normalize_document_status(value, default="Draft") == "Posted"


def _source_document_columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _sync_source_document_posting(conn, source_table, source_id, entry_id, posting_user=None):
    if not source_table or not source_id:
        return
    normalized_source_table = str(source_table).strip().lower()
    if normalized_source_table not in {"invoices", "bills", "payments", "stock_movements", "vouchers"}:
        return
    source_columns = _source_document_columns(conn, normalized_source_table)
    update_parts = []
    params = []
    if "posted_entry_id" in source_columns:
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
    row = conn.execute(
        """
        SELECT 1
        FROM accounting_periods
        WHERE company_key = ?
          AND is_locked = 1
          AND date(?) BETWEEN date(start_date) AND date(end_date)
        LIMIT 1
        """,
        (company_key, _resolve_date(entry_date)),
    ).fetchone()
    return bool(row)


def _system_setting_value(conn, column_name, default=None):
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(system_settings)").fetchall()}
        if column_name not in columns:
            return default
        row = conn.execute(f"SELECT {column_name} AS value FROM system_settings WHERE id = 1").fetchone()
        return row["value"] if row and "value" in row.keys() else default
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


def _document_approval_enforced(conn):
    return bool(int(_system_setting_value(conn, "enforce_document_approval", 0) or 0))


def _assert_source_document_postable(conn, source_table, source_id):
    if not source_table or not source_id or not _document_approval_enforced(conn):
        return
    allowed_tables = {"invoices", "bills", "payments", "vouchers", "stock_movements"}
    normalized_table = str(source_table).strip().lower()
    if normalized_table not in allowed_tables:
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
    if status not in {"Approved", "Posted", "Active"}:
        raise ValueError(
            f"{normalized_table[:-1].title() if normalized_table.endswith('s') else normalized_table.title()} "
            f"{source_id} cannot post to the journal while approval_status is '{status or 'Draft'}'."
        )


def _coa_name_expression():
    return "COALESCE(NULLIF(name, ''), NULLIF(account_name, ''), '')"


def _coa_type_expression():
    return "COALESCE(NULLIF(type, ''), NULLIF(account_type, ''), NULLIF(category, ''), 'Asset')"


def _coa_code_expression():
    return "COALESCE(NULLIF(account_code, ''), NULLIF(code, ''), '')"


def _inventory_value_query(conn, company_key, branch_id=None):
    inventory_columns = {row[1] for row in conn.execute("PRAGMA table_info(inventory)").fetchall()}
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
    return "Draft"


def _chart_account_structure(conn):
    return [dict(row) for row in conn.execute(
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
    ).fetchall()]


def get_chart_of_accounts_diagnostics(conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        rows = _chart_account_structure(conn)
        duplicate_codes = []
        invalid_types = []
        header_posting_allowed = []
        control_accounts_manual = []
        seen_codes = {}
        parent_ids = {int(row["parent_id"]) for row in rows if row.get("parent_id") not in (None, "")}
        for row in rows:
            account_name = str(row.get("account_name") or "").strip()
            account_code = str(row.get("account_code") or "").strip()
            account_type = str(row.get("account_type") or "").strip().title()
            posting_allowed = bool(int(row.get("posting_allowed") or 0))
            control_account = bool(int(row.get("control_account") or 0))
            allow_manual_posting = bool(int(row.get("allow_manual_posting") or 0))
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
        return {
            "total_accounts": len(rows),
            "duplicate_account_codes": duplicate_codes,
            "invalid_account_types": invalid_types,
            "header_accounts_allowing_posting": header_posting_allowed,
            "control_accounts_allowing_manual_posting": control_accounts_manual,
            "warnings": warnings,
        }
    finally:
        if owns_connection and conn:
            conn.close()


def _resolve_source_document_mismatches(conn, company_key, branch_id=None):
    mismatches = []
    allowed_tables = ("invoices", "bills", "payments", "stock_movements", "vouchers")
    for table_name in allowed_tables:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        if not table_exists:
            continue
        columns = _source_document_columns(conn, table_name)
        if "id" not in columns:
            continue
        query = f"SELECT * FROM {table_name} WHERE company_key = ?"
        params = [company_key]
        if branch_id and "branch_id" in columns:
            query += " AND branch_id = ?"
            params.append(branch_id)
        rows = conn.execute(query, tuple(params)).fetchall()
        for row in rows:
            status = _safe_doc_status(row, columns)
            row_id = int(row["id"])
            posted_entry_id = int(row["posted_entry_id"]) if "posted_entry_id" in columns and row["posted_entry_id"] not in (None, "") else None
            journal_ref = conn.execute(
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
        inventory_row = conn.execute(inventory_query, inventory_params).fetchone()
        inventory_subledger_total = round(float(inventory_row["inventory_value"] or 0.0), 2) if inventory_row else 0.0
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
        unbalanced_journal_rows = conn.execute(
            """
            SELECT je.id
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            WHERE je.company_key = ?
              AND COALESCE(je.is_voided, 0) = 0
              {branch_clause}
            GROUP BY je.id
            HAVING ABS(COALESCE(SUM(jl.debit), 0) - COALESCE(SUM(jl.credit), 0)) >= 0.01
            """.format(branch_clause="AND je.branch_id = ?" if branch_id else ""),
            tuple([company_key] + ([branch_id] if branch_id else [])),
        ).fetchall()
        orphaned_journal_refs = []
        source_rows = conn.execute(
            """
            SELECT id, source_table, source_id, reference
            FROM journal_entries
            WHERE company_key = ?
              AND source_table IS NOT NULL
              AND TRIM(COALESCE(source_table, '')) != ''
              AND source_id IS NOT NULL
              AND COALESCE(is_voided, 0) = 0
              {branch_clause}
            """.format(branch_clause="AND branch_id = ?" if branch_id else ""),
            tuple([company_key] + ([branch_id] if branch_id else [])),
        ).fetchall()
        for row in source_rows:
            source_table = str(row["source_table"] or "").strip().lower()
            source_id = int(row["source_id"])
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (source_table,),
            ).fetchone()
            if not exists:
                orphaned_journal_refs.append(
                    {"entry_id": int(row["id"]), "source_table": source_table, "source_id": source_id, "reason": "source table missing"}
                )
                continue
            source_match = conn.execute(
                f"SELECT id FROM {source_table} WHERE id = ? LIMIT 1",
                (source_id,),
            ).fetchone()
            if not source_match:
                orphaned_journal_refs.append(
                    {"entry_id": int(row["id"]), "source_table": source_table, "source_id": source_id, "reason": "source document missing"}
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

    row = conn.execute(
        f"""
        SELECT id
        FROM chart_of_accounts
        WHERE lower({_coa_name_expression()}) = lower(?)
        LIMIT 1
        """,
        (account_name,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE chart_of_accounts
            SET name = COALESCE(NULLIF(name, ''), ?),
                account_name = COALESCE(NULLIF(account_name, ''), ?),
                type = COALESCE(NULLIF(type, ''), ?),
                account_type = COALESCE(NULLIF(account_type, ''), ?),
                category = COALESCE(NULLIF(category, ''), ?),
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
        """
        INSERT INTO chart_of_accounts (
            name, type, parent_id, code, category, account_code, account_name, account_type,
            posting_allowed, control_account, allow_manual_posting, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
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
    return int(cursor.lastrowid)


def get_account_id(conn, account_name, account_type=None):
    row = conn.execute(
        f"""
        SELECT id, {_coa_type_expression()} AS account_type
        FROM chart_of_accounts
        WHERE lower({_coa_name_expression()}) = lower(?)
        LIMIT 1
        """,
        (str(account_name or "").strip(),),
    ).fetchone()
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
    conn = conn or get_connection()
    if conn is None:
        raise RuntimeError("Database connection unavailable.")
    if _period_locked(conn, company_key, entry_date):
        raise ValueError(f"The accounting period for {entry_date[:7]} is locked.")
    _assert_source_document_postable(conn, source_table, source_id)

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
            """
            INSERT INTO journal_entries (
                company_key, date, description, reference, created_by, branch_id,
                customer_id, supplier_id, inventory_item_id, payment_id,
                source_module, source_table, source_type, source_id,
                source_document_type, source_document_id, approval_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
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
        entry_id = int(cursor.lastrowid)
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
            )
        _mirror_legacy_transactions(conn, company_key, entry_date, description, reference, created_by, branch_id, normalized_lines)
        if source_module:
            _legacy_voucher_insert(conn, company_key, branch_id, entry_date, description, reference, created_by, normalized_lines, source_module=source_module)
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
            outstanding = float(invoice["amount"] or 0.0) - float(conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payment_allocations WHERE invoice_id = ?", (invoice_id,)).fetchone()[0] or 0.0)
            if amount > outstanding:
                raise ValueError(f"Allocation amount exceeds outstanding invoice balance ({outstanding:.2f}).")
        if bill_id:
            bill = conn.execute("SELECT amount FROM bills WHERE id = ?", (bill_id,)).fetchone()
            if not bill:
                raise ValueError(f"Bill {bill_id} does not exist.")
            outstanding = float(bill["amount"] or 0.0) - float(conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payment_allocations WHERE bill_id = ?", (bill_id,)).fetchone()[0] or 0.0)
            if amount > outstanding:
                raise ValueError(f"Allocation amount exceeds outstanding bill balance ({outstanding:.2f}).")

        cursor = conn.execute(
            "INSERT INTO payment_allocations (company_key, payment_id, invoice_id, bill_id, amount, currency, branch_id, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payment["company_key"],
                payment_id,
                invoice_id,
                bill_id,
                amount,
                payment["currency"],
                branch_id or payment["branch_id"],
                created_by or payment["created_by"],
            ),
        )
        if owns_connection:
            conn.commit()
        return int(cursor.lastrowid)
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
            "INSERT INTO bank_accounts (company_key, branch_id, account_name, account_number, bank_name, account_type, currency, balance, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_key, branch_id, account_name, account_number, bank_name, account_type, currency, opening_balance, created_by),
        )
        if owns_connection:
            conn.commit()
        return int(cursor.lastrowid)
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
            "INSERT INTO recurring_transactions (company_key, branch_id, description, frequency, amount, next_run_date, is_active, source_module, source_table, source_id, created_by, recurrence_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_key, branch_id, description, frequency, amount, _resolve_date(next_run_date), 1 if active else 0, source_module, source_table, source_id, created_by, payload),
        )
        if owns_connection:
            conn.commit()
        return int(cursor.lastrowid)
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
            query += " AND date(je.date) >= date(?)"
            params.append(_resolve_date(start_date))
        if end_date:
            query += " AND date(je.date) <= date(?)"
            params.append(_resolve_date(end_date))
        if branch_id:
            query += " AND je.branch_id = ?"
            params.append(branch_id)
        if account_id:
            query += " AND c.id = ?"
            params.append(int(account_id))
        query += " ORDER BY date(je.date), je.id, jl.id"
        return pd.read_sql_query(query, conn, params=params)
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
            query += " AND date(je.date) >= date(?)"
            params.append(_resolve_date(start_date))
        if end_date:
            query += " AND date(je.date) <= date(?)"
            params.append(_resolve_date(end_date))
        if branch_id:
            query += " AND je.branch_id = ?"
            params.append(branch_id)
        row = conn.execute(query, tuple(params)).fetchone()
        debit_total = round(float(row["debit_total"] or 0.0), 2) if row else 0.0
        credit_total = round(float(row["credit_total"] or 0.0), 2) if row else 0.0
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
    start_date = f"{period_value}-01"
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = """
            SELECT COALESCE(SUM(jl.credit), 0) AS sales_total
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND strftime('%Y-%m', je.date) = ?
              AND lower(COALESCE(NULLIF(c.name, ''), NULLIF(c.account_name, ''), '')) LIKE 'sales%'
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """
        params = [company_key, period_value]
        if branch_id:
            query += " AND je.branch_id = ?"
            params.append(branch_id)
        row = conn.execute(query, tuple(params)).fetchone()
        return round(float(row["sales_total"] or 0.0), 2) if row else 0.0
    finally:
        if owns_connection and conn:
            conn.close()


def get_recent_accounting_activity(company_key, branch_id=None, limit=10, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = """
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
            ORDER BY date(je.date) DESC, je.id DESC
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
        return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
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
    total_income = 0.0
    total_expenses = 0.0
    for row in get_trial_balance(company_key, start_date=start_date, end_date=end_date, branch_id=branch_id):
        account_type = str(row["account_type"]).title()
        if account_type == "Income":
            amount = round(row["credit_total"] - row["debit_total"], 2)
            total_income += amount
            rows.append({"category": "Income", "account_id": row["account_id"], "account_code": row["account_code"], "account_name": row["account_name"], "amount": amount})
        elif account_type == "Expense":
            amount = round(row["debit_total"] - row["credit_total"], 2)
            total_expenses += amount
            rows.append({"category": "Expense", "account_id": row["account_id"], "account_code": row["account_code"], "account_name": row["account_name"], "amount": amount})
    rows.append({"category": "Profit", "account_id": None, "account_code": "", "account_name": "Net Profit", "amount": round(total_income - total_expenses, 2)})
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
    cash_df = journal_df[journal_df["account_name"].isin(["Cash", "Bank", "Mobile Money"])].copy()
    if cash_df.empty:
        return []
    rows = []
    totals = {"Operating Activities": 0.0, "Investing Activities": 0.0, "Financing Activities": 0.0}
    for _, row in cash_df.iterrows():
        description = str(row["description"] or "").lower()
        other_side = journal_df[
            (journal_df["entry_id"] == row["entry_id"]) & (journal_df["account_id"] != row["account_id"])
        ]
        counterpart_types = {str(value).title() for value in other_side["account_type"].tolist()}
        counterpart_names = {str(value) for value in other_side["account_name"].tolist()}
        movement = round(float(row["debit"] or 0.0) - float(row["credit"] or 0.0), 2)
        if counterpart_types & {"Income", "Expense"} or "Accounts Receivable" in counterpart_names or "Accounts Payable" in counterpart_names:
            section = "Operating Activities"
        elif "Fixed Assets" in counterpart_names or "Inventory" in counterpart_names or "Accumulated Depreciation" in counterpart_names:
            section = "Investing Activities"
        elif counterpart_types & {"Equity", "Liability"} or "Owner Capital" in counterpart_names or "Retained Earnings" in counterpart_names:
            section = "Financing Activities"
        elif "depreciation" in description:
            section = "Operating Activities"
        else:
            section = "Operating Activities"
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
    if days_outstanding <= 30:
        return "0-30 Days"
    if days_outstanding <= 60:
        return "31-60 Days"
    if days_outstanding <= 90:
        return "61-90 Days"
    return "91+ Days"


def get_ar_aging_report(company_key, as_of_date=None):
    report_date = pd.Timestamp(as_of_date or datetime.now().date())
    conn = get_connection()
    try:
        customers = conn.execute(
            "SELECT id, customer_id, name, phone, email FROM customers WHERE company_key = ? ORDER BY name",
            (company_key,),
        ).fetchall()
        rows = []
        for customer in customers:
            balance = get_customer_balance(company_key, int(customer["id"]), as_of_date=report_date.date(), conn=conn)
            if abs(balance) < 0.005:
                continue
            oldest_row = conn.execute(
                f"""
                SELECT MIN(date(je.date)) AS oldest_open_date
                FROM journal_entries je
                JOIN journal_lines jl ON jl.entry_id = je.id
                JOIN chart_of_accounts c ON c.id = jl.account_id
                WHERE je.company_key = ?
                  AND je.customer_id = ?
                  AND jl.debit > 0
                  AND lower({_coa_name_expression()}) LIKE 'accounts receivable%'
                  AND date(je.date) <= date(?)
                """,
                (company_key, int(customer["id"]), _resolve_date(report_date.date())),
            ).fetchone()
            oldest_date = pd.Timestamp(oldest_row["oldest_open_date"]) if oldest_row and oldest_row["oldest_open_date"] else pd.Timestamp(report_date)
            if oldest_row is None or oldest_row["oldest_open_date"] is None:
                tx_rows = conn.execute(
                    """
                    SELECT transaction_date
                    FROM customer_transactions
                    WHERE company_key = ? AND customer_id = ? AND transaction_type = 'Debit'
                    ORDER BY date(transaction_date) ASC, id ASC
                    """,
                    (company_key, int(customer["id"])),
                ).fetchall()
                if tx_rows:
                    oldest_date = min(pd.Timestamp(row["transaction_date"]) for row in tx_rows if row["transaction_date"])
            days = int((report_date - oldest_date).days) if oldest_date is not None else 0
            rows.append(
                {
                    "customer_id": customer["customer_id"] or f"CUST-{int(customer['id']):06d}",
                    "customer_name": customer["name"],
                    "phone": customer["phone"],
                    "email": customer["email"],
                    "days_outstanding": days,
                    "bucket": _aging_bucket(days),
                    "balance": round(balance, 2),
                }
            )
        return rows
    finally:
        conn.close()


def get_supplier_balance(company_key, supplier_id, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(jl.credit - jl.debit), 0) AS balance
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND je.supplier_id = ?
              AND lower({_coa_name_expression()}) LIKE 'accounts payable%'
              {"AND date(je.date) <= date(?)" if as_of_date else ""}
            """,
            (company_key, int(supplier_id), _resolve_date(as_of_date)) if as_of_date else (company_key, int(supplier_id)),
        ).fetchone()
        return round(float(row["balance"] or 0.0), 2) if row else 0.0
    finally:
        if owns_connection and conn:
            conn.close()


def get_supplier_balances(company_key, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, name, email, phone, address
            FROM suppliers
            WHERE company_key = ?
            ORDER BY name
            """,
            (company_key,),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "email": row["email"],
                "phone": row["phone"],
                "address": row["address"],
                "balance": get_supplier_balance(company_key, int(row["id"]), as_of_date=as_of_date, conn=conn),
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
            balance = get_supplier_balance(company_key, supplier_id, as_of_date=report_date.date(), conn=conn)
            if abs(balance) < 0.005:
                continue
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
                """,
                (company_key, supplier_id, _resolve_date(report_date.date())),
            ).fetchone()
            oldest_date = pd.Timestamp(oldest_row["oldest_open_date"]) if oldest_row and oldest_row["oldest_open_date"] else report_date
            days = int((report_date - oldest_date).days)
            rows.append(
                {
                    "supplier_id": supplier_id,
                    "supplier_name": supplier["name"],
                    "email": supplier["email"],
                    "phone": supplier["phone"],
                    "address": supplier["address"],
                    "days_outstanding": days,
                    "bucket": _aging_bucket(days),
                    "balance": round(balance, 2),
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


def get_customer_balance(company_key, customer_id, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(jl.debit - jl.credit), 0) AS balance
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND je.customer_id = ?
              AND lower({_coa_name_expression()}) LIKE 'accounts receivable%'
              { "AND date(je.date) <= date(?)" if as_of_date else "" }
            """,
            (company_key, int(customer_id), _resolve_date(as_of_date)) if as_of_date else (company_key, int(customer_id)),
        ).fetchone()
        return round(float(row["balance"] or 0.0), 2) if row else 0.0
    finally:
        if owns_connection and conn:
            conn.close()


def get_customer_balances(company_key, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, customer_id, name, phone, email
            FROM customers
            WHERE company_key = ?
            ORDER BY name
            """,
            (company_key,),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "customer_id": row["customer_id"] or f"CUST-{int(row['id']):06d}",
                "name": row["name"],
                "phone": row["phone"],
                "email": row["email"],
                "balance": get_customer_balance(company_key, int(row["id"]), as_of_date=as_of_date, conn=conn),
            }
            for row in rows
        ]
    finally:
        if owns_connection and conn:
            conn.close()
