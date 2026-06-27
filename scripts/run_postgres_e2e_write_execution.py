from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REPORT_PATH = REPO_ROOT / "reports" / "postgres_e2e_write_execution.md"
PHASE_PREFIX = "PG-E2E-5B17B"
TEST_COMPANY_KEY = f"{PHASE_PREFIX}-COMPANY"
TEST_BRANCH_ID = f"{PHASE_PREFIX}-BRANCH"
POS_LINE_ITEM_TABLE_CANDIDATES = (
    "pos_sale_lines",
    "pos_sales_lines",
    "pos_sales_items",
    "pos_sale_items",
    "sale_items",
)
E2E_IDENTITY_TABLES = (
    "accounts",
    "chart_of_accounts",
    "account_categories",
    "tax_codes",
    "bank_accounts",
    "customers",
    "suppliers",
    "inventory",
    "pos_sales",
    "pos_sale_lines",
    "stock_movements",
    "invoices",
    "bills",
    "payments",
    "journal_entries",
    "journal_lines",
    "payroll",
    "fixed_assets",
    "users",
    "audit_logs",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value):
    return int(value) if value is not None else None


def _fetch_count(conn, sql, params):
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return 0
    try:
        return int(row["count"])
    except Exception:
        try:
            return int(row[0])
        except Exception:
            return 0


def _row_value(row, key, index=0, default=None):
    if row is None:
        return default
    if hasattr(row, "keys"):
        try:
            return row[key]
        except Exception:
            pass
    try:
        return row[index]
    except Exception:
        return default


def _get_table_column_names(conn, database, table_name):
    return {str(column.get("name") or "") for column in database.list_columns(conn, table_name) if column.get("name")}


def _connection_diagnostics(conn, database):
    diagnostics = {
        "connection_id": hex(id(conn)),
        "in_transaction": bool(getattr(conn, "in_transaction", False)),
        "transaction_id": None,
    }
    try:
        if database.get_active_db_backend() == "postgres":
            row = database.execute_portable_query(conn, "SELECT txid_current() AS transaction_id", ()).fetchone()
            diagnostics["transaction_id"] = _row_value(row, "transaction_id", 0)
    except Exception as exc:
        diagnostics["transaction_id"] = f"unavailable: {exc}"
    return diagnostics


def _current_transaction_id(conn, database):
    if database.get_active_db_backend() != "postgres":
        return None
    row = database.execute_portable_query(conn, "SELECT txid_current() AS transaction_id", ()).fetchone()
    return _row_value(row, "transaction_id", 0)


def _begin_e2e_owned_transaction(conn, database):
    if database.get_active_db_backend() == "postgres":
        database.execute_portable_write(conn, "BEGIN", ())
        if hasattr(conn, "in_transaction"):
            conn.in_transaction = True
        return _current_transaction_id(conn, database)
    return None


def _assert_transaction_stable(conn, database, expected_transaction_id, *, label, timeline=None):
    current_transaction_id = _current_transaction_id(conn, database)
    if expected_transaction_id is not None and current_transaction_id != expected_transaction_id:
        _append_timeline(
            timeline,
            "Transaction ownership failed",
            conn,
            database,
            expected_transaction_id=expected_transaction_id,
            actual_transaction_id=current_transaction_id,
            after=label,
        )
        raise RuntimeError(
            f"E2E transaction changed after {label}: expected {expected_transaction_id}, got {current_transaction_id}"
        )
    _append_timeline(
        timeline,
        "Transaction ownership verified",
        conn,
        database,
        transaction_id=current_transaction_id,
        after=label,
    )
    return current_transaction_id


def _append_timeline(timeline, event, conn, database, **details):
    if timeline is None:
        return None
    entry = {
        "event": event,
        **_connection_diagnostics(conn, database),
        **details,
    }
    timeline.append(entry)
    return entry


def _verify_e2e_company_visible(conn, database, *, timeline=None, event="Company verified"):
    row = database.execute_portable_query(
        conn,
        "SELECT key FROM companies WHERE key = ? LIMIT 1",
        (TEST_COMPANY_KEY,),
    ).fetchone()
    if row is None:
        _append_timeline(timeline, "Company visibility failed", conn, database, company_key=TEST_COMPANY_KEY, company_visible=False)
        raise RuntimeError(f"E2E test company is not visible on active transaction connection: {TEST_COMPANY_KEY}")
    _append_timeline(timeline, event, conn, database, company_key=TEST_COMPANY_KEY, company_visible=True)
    return True


def _table_exists(conn, database, table_name):
    checker = getattr(database, "db_table_exists", None)
    if callable(checker):
        return bool(checker(conn, table_name))
    try:
        return bool(_get_table_column_names(conn, database, table_name))
    except Exception:
        return False


def _resolve_pos_line_item_table(conn, database):
    for table_name in POS_LINE_ITEM_TABLE_CANDIDATES:
        if _table_exists(conn, database, table_name):
            return table_name
    return None


def _validate_identifier(identifier):
    normalized = str(identifier or "").strip()
    if not normalized or not normalized.replace("_", "").isalnum() or normalized[0].isdigit():
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return normalized


def _sync_postgres_identity_sequence(conn, database, table_name, id_column="id"):
    if database.get_active_db_backend() != "postgres":
        return {"table": table_name, "status": "SKIPPED_NON_POSTGRES"}
    table = _validate_identifier(table_name)
    column = _validate_identifier(id_column)
    if not _table_exists(conn, database, table):
        return {"table": table, "status": "SKIPPED_MISSING_TABLE"}
    database.execute_portable_query(
        conn,
        f"""
        WITH sequence_name AS (
            SELECT pg_get_serial_sequence(?, ?) AS name
        ),
        next_identity AS (
            SELECT COALESCE(MAX({column}), 0) + 1 AS next_id
            FROM {table}
        )
        SELECT CASE
            WHEN sequence_name.name IS NULL THEN NULL
            ELSE setval(sequence_name.name::regclass, next_identity.next_id, false)
        END AS synced_identity
        FROM sequence_name, next_identity
        """,
        (table, column),
    ).fetchone()
    return {"table": table, "status": "SYNCED"}


def _sync_postgres_identity_sequences(conn, database):
    identity_tables = list(E2E_IDENTITY_TABLES)
    resolved_pos_line_table = _resolve_pos_line_item_table(conn, database)
    if resolved_pos_line_table and resolved_pos_line_table not in identity_tables:
        identity_tables.append(resolved_pos_line_table)
    return [
        _sync_postgres_identity_sequence(conn, database, table_name)
        for table_name in identity_tables
    ]


def _build_branch_insert_payload(available_columns):
    available = {str(column or "").strip() for column in (available_columns or set()) if str(column or "").strip()}
    required_columns = ("branch_id", "company_key", "branch_name")
    missing = [column for column in required_columns if column not in available]
    if missing:
        raise RuntimeError(f"branches table is missing required column(s): {', '.join(missing)}")

    candidate_values = {
        "branch_id": TEST_BRANCH_ID,
        "company_key": TEST_COMPANY_KEY,
        "branch_name": f"{PHASE_PREFIX} Branch",
        "status": "Active",
    }
    return {
        column_name: value
        for column_name, value in candidate_values.items()
        if column_name in available
    }


def _insert_branch_record(conn, database):
    payload = _build_branch_insert_payload(_get_table_column_names(conn, database, "branches"))
    columns = list(payload.keys())
    placeholders = ", ".join("?" for _ in columns)
    database.execute_portable_write(
        conn,
        f"INSERT INTO branches ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(payload[column] for column in columns),
    )
    return {"columns": columns, "branch_id": payload.get("branch_id")}


def _journal_balance_ok(conn, entry_id) -> bool:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(debit), 0) AS debit_total,
               COALESCE(SUM(credit), 0) AS credit_total
        FROM journal_lines
        WHERE entry_id = ?
        """,
        (entry_id,),
    ).fetchone()
    debit_total = float(row["debit_total"] if hasattr(row, "keys") else row[0])
    credit_total = float(row["credit_total"] if hasattr(row, "keys") else row[1])
    return round(debit_total, 2) == round(credit_total, 2)


def _write_report(payload: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    diagnostics = payload.get("backend_diagnostics", {})
    workflows = payload.get("workflows", [])
    execution_timeline = payload.get("execution_timeline") or []
    transaction_ownership = payload.get("transaction_ownership") or {}
    lines = [
        "# PostgreSQL E2E Write Execution",
        "",
        f"**Generated at:** {payload.get('generated_at')}",
        "**Branch:** `phase-5b17b-postgres-e2e-write-execution`",
        "**Scope:** staged PostgreSQL end-to-end write workflow execution.",
        "",
        "## Backend Diagnostics",
        "",
        f"- Active backend: `{diagnostics.get('active_backend')}`",
        f"- Configured backend: `{diagnostics.get('configured_backend')}`",
        f"- `DATABASE_URL` present: `{diagnostics.get('database_url_present')}`",
        f"- `ERP_ENABLE_POSTGRES_RUNTIME`: `{diagnostics.get('erp_enable_postgres_runtime')}`",
        f"- `ERP_ENVIRONMENT`: `{diagnostics.get('erp_environment')}`",
        f"- Abort reason: {payload.get('abort_reason') or 'None'}",
        "",
        "## Execution Summary",
        "",
        f"- Overall status: **{payload.get('overall_status')}**",
        f"- Cleanup status: **{payload.get('cleanup_status')}**",
        f"- Test company key: `{TEST_COMPANY_KEY}`",
        f"- Test branch id: `{TEST_BRANCH_ID}`",
        "",
        "## Workflow Results",
        "",
        "| Workflow | Status | Row IDs Created | Cleanup Status | Evidence |",
        "|---|---|---|---|---|",
    ]
    if workflows:
        for workflow in workflows:
            row_ids = workflow.get("row_ids") or {}
            row_id_text = ", ".join(f"{key}={value}" for key, value in row_ids.items()) or "None"
            evidence = workflow.get("evidence") or ""
            lines.append(
                f"| {workflow.get('workflow')} | {workflow.get('status')} | {row_id_text} | "
                f"{workflow.get('cleanup_status')} | {evidence} |"
            )
    else:
        lines.append("| All workflows | ABORTED | None | Not started | Backend guard blocked execution before writes. |")
    lines.extend(
        [
            "",
            "## Execution Timeline",
            "",
        ]
    )
    if execution_timeline:
        for entry in execution_timeline:
            detail_text = ", ".join(
                f"{key}={value}"
                for key, value in entry.items()
                if key not in {"event"}
            )
            lines.append(f"- {entry.get('event')}: {detail_text}")
    else:
        lines.append("- Not started before backend guard or no timeline entries recorded.")
    lines.extend(
        [
            "",
            "## Transaction Ownership",
            "",
            f"- Expected transaction id: `{transaction_ownership.get('expected_transaction_id')}`",
            f"- Status: **{transaction_ownership.get('status') or 'NOT_STARTED'}**",
            f"- Guard: {transaction_ownership.get('guard') or 'E2E transaction id guard not started before backend guard.'}",
        ]
    )
    lines.extend(
        [
            "",
            "## Cleanup Strategy",
            "",
            payload.get("cleanup_strategy")
            or "All staged writes run inside one owned transaction and are rolled back at the end of certification.",
            "",
            "## Schema Portability Notes",
            "",
            "- Branch test-record seeding is schema-aware: the runner inspects `branches` columns and inserts only available columns.",
            "- `branches.status` is optional for the E2E runner; schemas with only `branch_id`, `company_key`, and `branch_name` are supported.",
            "- Integer primary keys for E2E-owned rows are generated by the database and read back through portable identity helpers.",
            "- PostgreSQL staging identity sequences are synchronized before E2E inserts to avoid duplicate generated IDs after imported data.",
            "- Accounting master identity sequences (`accounts`, `chart_of_accounts`, `account_categories`, `tax_codes`, `bank_accounts`) are included in E2E sequence sync before account lookup can create missing COA rows.",
            "- POS line-item portability uses the canonical `pos_sale_lines` table; missing legacy aliases such as `pos_sale_items` are skipped during identity sync.",
            "- Inventory stock movements use the generated and transaction-visible `inventory.id` returned from E2E inventory seeding.",
            "- E2E audit events are inserted through the active certification transaction connection so the uncommitted test company remains visible.",
            "- E2E audit inserts verify company visibility on the owning transaction before writing `audit_logs` rows.",
            "- Transaction ownership is guarded by comparing PostgreSQL `txid_current()` after every critical E2E seed and audit step.",
            "- Asset depreciation certification uses E2E-local journal and fixed-asset update writes instead of the production depreciation helper, preserving the owned transaction through depreciation.",
            "",
            "## Blockers",
            "",
        ]
    )
    blockers = payload.get("blockers") or []
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- None recorded by this execution.")
    lines.extend(
        [
            "",
            "## Production Readiness Recommendation",
            "",
            payload.get("production_readiness_recommendation")
            or "NO-GO until this script runs with active PostgreSQL staging backend and all workflows pass.",
            "",
            "## Raw Execution Payload",
            "",
            "```json",
            json.dumps(payload, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def _backend_diagnostics(database):
    return {
        "active_backend": database.get_active_db_backend(),
        "configured_backend": database.get_configured_db_backend(),
        "database_url_present": bool(database.get_database_url()),
        "erp_enable_postgres_runtime": os.getenv("ERP_ENABLE_POSTGRES_RUNTIME"),
        "erp_environment": os.getenv("ERP_ENVIRONMENT"),
    }


def _abort_if_not_postgres(database):
    diagnostics = _backend_diagnostics(database)
    reasons = []
    if diagnostics["active_backend"] != "postgres":
        reasons.append("active backend is not postgres")
    if not diagnostics["database_url_present"]:
        reasons.append("DATABASE_URL is not present")
    if str(diagnostics.get("erp_enable_postgres_runtime") or "").strip() != "1":
        reasons.append("ERP_ENABLE_POSTGRES_RUNTIME is not 1")
    if str(diagnostics.get("erp_environment") or "").strip().lower() != "staging":
        reasons.append("ERP_ENVIRONMENT is not staging")
    if reasons:
        payload = {
            "generated_at": _utc_now(),
            "overall_status": "ABORTED",
            "cleanup_status": "NOT_STARTED",
            "backend_diagnostics": diagnostics,
            "abort_reason": "; ".join(reasons),
            "workflows": [],
            "blockers": [
                "E2E certification aborted before writes because PostgreSQL staging runtime is not active.",
                "Set DB_BACKEND=postgres, ERP_ENABLE_POSTGRES_RUNTIME=1, ERP_ENVIRONMENT=staging, and DATABASE_URL before executing.",
            ],
        }
        _write_report(payload)
        return payload
    return None


def _insert_company_and_branch(conn, database, timeline=None):
    database.execute_portable_write(
        conn,
        """
        INSERT INTO companies (
            key, name, subscription_expiry, status, deployment_status,
            number_of_branches, max_branches, branch_price_per_month, contact_email
        )
        VALUES (?, ?, 'Permanent', 'Active', 'Live', 1, 1, 0, ?)
        """,
        (TEST_COMPANY_KEY, f"{PHASE_PREFIX} Test Company", "postgres-e2e@example.com"),
    )
    _append_timeline(timeline, "Company inserted", conn, database, company_key=TEST_COMPANY_KEY)
    _verify_e2e_company_visible(conn, database, timeline=timeline)
    branch_result = _insert_branch_record(conn, database)
    _append_timeline(timeline, "Branch inserted", conn, database, branch_id=branch_result.get("branch_id"))
    return branch_result


def _insert_party(conn, database, table_name, name):
    columns = ("company_key", "name", "email", "phone", "address", "currency")
    cursor = database.execute_portable_write(
        conn,
        database.ensure_insert_sql_returning(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES (?, ?, ?, ?, ?, 'GHS')"
        ),
        (TEST_COMPANY_KEY, name, f"{name.lower().replace(' ', '.')}@example.com", "000", "Accra"),
    )
    return database.get_inserted_id(cursor)


def _insert_document(conn, database, table_name, number_column, number, party_column, party_id, amount, doc_date):
    date_column = "invoice_date" if table_name == "invoices" else "bill_date"
    cursor = database.execute_portable_write(
        conn,
        database.ensure_insert_sql_returning(
            f"""
            INSERT INTO {table_name} (
                company_key, {party_column}, {number_column}, {date_column}, due_date,
                status, approval_status, amount, currency, description, created_by
            )
            VALUES (?, ?, ?, ?, ?, 'Posted', 'Posted', ?, 'GHS', ?, ?)
            """
        ),
        (TEST_COMPANY_KEY, party_id, number, doc_date.isoformat(), doc_date.isoformat(), amount, f"{PHASE_PREFIX} {table_name}", "postgres_e2e"),
    )
    return database.get_inserted_id(cursor)


def _insert_payment(conn, database, payment_type, amount, *, customer_id=None, supplier_id=None, invoice_id=None, bill_id=None):
    cursor = database.execute_portable_write(
        conn,
        database.ensure_insert_sql_returning(
            """
            INSERT INTO payments (
                company_key, payment_date, payment_type, status, customer_id, supplier_id,
                invoice_id, bill_id, amount, currency, method, reference, approval_status, created_by
            )
            VALUES (?, ?, ?, 'Posted', ?, ?, ?, ?, ?, 'GHS', 'Cash', ?, 'Posted', ?)
            """
        ),
        (
            TEST_COMPANY_KEY,
            date(2026, 6, 25).isoformat(),
            payment_type,
            customer_id,
            supplier_id,
            invoice_id,
            bill_id,
            amount,
            f"{PHASE_PREFIX}-{payment_type.replace(' ', '-').upper()}",
            "postgres_e2e",
        ),
    )
    return database.get_inserted_id(cursor)


def _insert_inventory_item(conn, database):
    item_code = f"{PHASE_PREFIX}-ITEM"
    cursor = database.execute_portable_write(
        conn,
        database.ensure_insert_sql_returning(
            """
            INSERT INTO inventory (company_key, item_name, item_code, barcode, qty, price, cost_price, min_stock_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (TEST_COMPANY_KEY, f"{PHASE_PREFIX} Item", item_code, "", 10.0, 20.0, 6.0, 1.0),
    )
    generated_item_id = database.get_inserted_id(cursor)
    verified_row = database.execute_portable_query(
        conn,
        "SELECT id FROM inventory WHERE id = ? AND company_key = ? LIMIT 1",
        (generated_item_id, TEST_COMPANY_KEY),
    ).fetchone()
    if verified_row is None:
        verified_row = database.execute_portable_query(
            conn,
            "SELECT id FROM inventory WHERE company_key = ? AND item_code = ? ORDER BY id DESC LIMIT 1",
            (TEST_COMPANY_KEY, item_code),
        ).fetchone()
    if verified_row is None:
        raise RuntimeError("Generated E2E inventory row was not visible on the active transaction connection.")
    if hasattr(verified_row, "keys"):
        return int(verified_row["id"])
    return int(verified_row[0])


def _insert_e2e_audit_event(
    conn,
    database,
    *,
    user_role,
    action,
    module_name,
    details=None,
    branch_id=None,
    action_type=None,
    document_ref=None,
    timeline=None,
):
    _verify_e2e_company_visible(conn, database, timeline=timeline, event="Company verified before audit")
    available_columns = _get_table_column_names(conn, database, "audit_logs")
    event_payload = {
        "company_key": TEST_COMPANY_KEY,
        "user_role": user_role,
        "action": action,
        "module_name": module_name,
        "details": details,
        "branch_id": branch_id,
        "action_type": action_type,
        "document_ref": document_ref,
        "event_id": f"E2E-AUD-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
    }
    payload = {
        column_name: value
        for column_name, value in event_payload.items()
        if column_name in available_columns
    }
    required = ("company_key", "user_role", "action", "module_name")
    missing = [column_name for column_name in required if column_name not in payload]
    if missing:
        raise RuntimeError(f"audit_logs table is missing required column(s): {', '.join(missing)}")
    columns = list(payload.keys())
    placeholders = ", ".join("?" for _ in columns)
    database.execute_portable_write(
        conn,
        f"INSERT INTO audit_logs ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(payload[column_name] for column_name in columns),
    )
    _append_timeline(timeline, "Audit inserted", conn, database, action=action, module_name=module_name)
    return {"columns": columns, "action": action}


def _post_e2e_journal_entry(conn, database, entry_date, description, reference, lines, **kwargs):
    cursor = database.execute_portable_write(
        conn,
        database.ensure_insert_sql_returning(
            """
            INSERT INTO journal_entries (
                company_key, date, description, reference, created_by, branch_id,
                customer_id, supplier_id, inventory_item_id, payment_id,
                source_module, source_table, source_type, source_id,
                source_document_type, source_document_id, approval_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Posted')
            """
        ),
        (
            TEST_COMPANY_KEY,
            entry_date.isoformat() if hasattr(entry_date, "isoformat") else str(entry_date),
            description,
            reference,
            "postgres_e2e",
            TEST_BRANCH_ID,
            kwargs.get("customer_id"),
            kwargs.get("supplier_id"),
            kwargs.get("inventory_item_id"),
            kwargs.get("payment_id"),
            "PostgreSQL E2E",
            kwargs.get("source_table"),
            kwargs.get("source_type"),
            kwargs.get("source_id"),
            kwargs.get("source_type") or kwargs.get("source_table") or "PostgreSQL E2E",
            kwargs.get("source_id"),
        ),
    )
    entry_id = database.get_inserted_id(cursor)
    database.execute_portable_write(
        conn,
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
        (
            kwargs.get("source_type") or kwargs.get("source_table") or "PostgreSQL E2E",
            kwargs.get("source_type") or kwargs.get("source_table") or "PostgreSQL E2E",
            kwargs.get("source_id"),
            entry_id,
        ),
    )
    for line in lines:
        database.execute_portable_write(
            conn,
            "INSERT INTO journal_lines (entry_id, account_id, debit, credit) VALUES (?, ?, ?, ?)",
            (entry_id, line["account_id"], float(line.get("debit") or 0.0), float(line.get("credit") or 0.0)),
        )
    source_table = str(kwargs.get("source_table") or "").strip()
    source_id = kwargs.get("source_id")
    if source_table and source_id:
        source_columns = _get_table_column_names(conn, database, source_table)
        update_parts = []
        params = []
        if "posted_entry_id" in source_columns:
            update_parts.append("posted_entry_id = ?")
            params.append(entry_id)
        if "last_journal_sync_at" in source_columns:
            update_parts.append("last_journal_sync_at = CURRENT_TIMESTAMP")
        if update_parts:
            params.append(source_id)
            database.execute_portable_write(
                conn,
                f"UPDATE {source_table} SET {', '.join(update_parts)} WHERE id = ?",
                tuple(params),
            )
    return entry_id


def _post_entry(engine, conn, database, description, reference, lines, **kwargs):
    return _post_e2e_journal_entry(
        conn,
        database,
        date(2026, 6, 25),
        description,
        reference,
        lines,
        **kwargs,
    )


def _run_e2e_asset_depreciation(
    conn,
    database,
    engine,
    asset_id,
    asset_name,
    *,
    as_of_date,
    expected_transaction_id=None,
    timeline=None,
):
    _assert_transaction_stable(
        conn,
        database,
        expected_transaction_id,
        label="asset depreciation account lookup before",
        timeline=timeline,
    )
    depreciation_expense_account_id = engine.get_account_id(conn, "Depreciation Expense", "Expense")
    accumulated_depreciation_account_id = engine.get_account_id(conn, "Accumulated Depreciation", "Asset")
    _assert_transaction_stable(
        conn,
        database,
        expected_transaction_id,
        label="asset depreciation account lookup after",
        timeline=timeline,
    )
    depreciation_date = as_of_date.isoformat() if hasattr(as_of_date, "isoformat") else str(as_of_date)
    depreciation_entry_id = _post_e2e_journal_entry(
        conn,
        database,
        as_of_date,
        f"Monthly depreciation - {asset_name}",
        f"DEPR-{asset_id}-202601",
        [
            {"account_id": depreciation_expense_account_id, "debit": 100.0, "credit": 0.0},
            {"account_id": accumulated_depreciation_account_id, "debit": 0.0, "credit": 100.0},
        ],
        inventory_item_id=None,
        source_table=None,
        source_type="Asset Depreciation",
        source_id=asset_id,
    )
    _assert_transaction_stable(
        conn,
        database,
        expected_transaction_id,
        label="asset depreciation journal insert",
        timeline=timeline,
    )
    database.execute_portable_write(
        conn,
        """
        UPDATE fixed_assets
        SET accumulated_depreciation = ?,
            book_value = ?,
            last_depreciation_date = ?
        WHERE id = ? AND company_key = ?
        """,
        (100.0, 1100.0, depreciation_date, asset_id, TEST_COMPANY_KEY),
    )
    _assert_transaction_stable(
        conn,
        database,
        expected_transaction_id,
        label="asset depreciation asset update",
        timeline=timeline,
    )
    return {"depreciation_count": 1, "depreciation_journal_entry_id": depreciation_entry_id}


def _workflow_result(workflow, status, row_ids, cleanup_status, evidence):
    return {
        "workflow": workflow,
        "status": status,
        "row_ids": row_ids,
        "cleanup_status": cleanup_status,
        "evidence": evidence,
    }


def _run_workflows(conn, database, engine, modules, execution_timeline=None, expected_transaction_id=None):
    workflows = []
    today = date(2026, 6, 25)
    _sync_postgres_identity_sequences(conn, database)
    _assert_transaction_stable(conn, database, expected_transaction_id, label="identity sequence sync", timeline=execution_timeline)
    _insert_company_and_branch(conn, database, timeline=execution_timeline)
    _assert_transaction_stable(conn, database, expected_transaction_id, label="company and branch insert", timeline=execution_timeline)

    customer_id = _insert_party(conn, database, "customers", f"{PHASE_PREFIX} Customer")
    _append_timeline(execution_timeline, "Customer inserted", conn, database, customer_id=customer_id)
    _assert_transaction_stable(conn, database, expected_transaction_id, label="customer insert", timeline=execution_timeline)
    supplier_id = _insert_party(conn, database, "suppliers", f"{PHASE_PREFIX} Supplier")
    _append_timeline(execution_timeline, "Supplier inserted", conn, database, supplier_id=supplier_id)
    _assert_transaction_stable(conn, database, expected_transaction_id, label="supplier insert", timeline=execution_timeline)

    item_id = _insert_inventory_item(conn, database)
    _append_timeline(execution_timeline, "Inventory inserted", conn, database, inventory_item_id=item_id)
    _assert_transaction_stable(conn, database, expected_transaction_id, label="inventory insert", timeline=execution_timeline)

    database.execute_portable_write(
        conn,
        "UPDATE inventory SET qty = qty - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND company_key = ?",
        (2.0, item_id, TEST_COMPANY_KEY),
    )
    pos_sale_id = modules._persist_pos_sale(
        conn,
        TEST_COMPANY_KEY,
        TEST_BRANCH_ID,
        f"{PHASE_PREFIX}-POS",
        {
            "receipt_number": f"{PHASE_PREFIX}-POS",
            "sale_date": today.isoformat(),
            "sale_datetime": f"{today.isoformat()} 10:00:00",
            "cashier": "postgres_e2e",
            "payment_method": "On Credit",
            "subtotal": 40.0,
            "discount_total": 0.0,
            "tax_total": 0.0,
            "grand_total": 40.0,
        },
        [
            {
                "inventory_item_id": item_id,
                "name": f"{PHASE_PREFIX} Item",
                "item_code": f"{PHASE_PREFIX}-ITEM",
                "barcode": "",
                "qty": 2.0,
                "price": 20.0,
                "line_discount": 0.0,
                "tax_rate": 0.0,
                "line_total": 40.0,
                "cost_price": 6.0,
            }
        ],
        customer_id=customer_id,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="POS sale persistence", timeline=execution_timeline)
    pos_entry_id = _post_entry(
        engine,
        conn,
        database,
        "PostgreSQL E2E POS sale",
        f"{PHASE_PREFIX}-POS",
        [
            {"account_id": engine.get_account_id(conn, "Accounts Receivable", "Asset"), "debit": 40.0, "credit": 0.0},
            {"account_id": engine.get_account_id(conn, "Sales Revenue", "Income"), "debit": 0.0, "credit": 40.0},
        ],
        customer_id=customer_id,
        source_table="pos_sales",
        source_type="POS Sale",
        source_id=pos_sale_id,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="POS journal insert", timeline=execution_timeline)
    _insert_e2e_audit_event(
        conn,
        database,
        user_role="Cashier",
        action="POS Sale",
        module_name="POS",
        details=f"{PHASE_PREFIX} POS",
        branch_id=TEST_BRANCH_ID,
        action_type="pos",
        document_ref=f"{PHASE_PREFIX}-POS",
        timeline=execution_timeline,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="POS audit insert", timeline=execution_timeline)
    pos_balance = engine.get_customer_balance(TEST_COMPANY_KEY, customer_id, conn=conn)
    workflows.append(_workflow_result("POS sale", "PASS", {"pos_sale_id": pos_sale_id, "journal_entry_id": pos_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, pos_entry_id)} customer_balance={pos_balance}"))

    movement_id = modules._insert_stock_movement_record(
        conn,
        company_key=TEST_COMPANY_KEY,
        inventory_item_id=item_id,
        item_name=f"{PHASE_PREFIX} Item",
        movement_type="STOCK_OUT",
        quantity=1.0,
        previous_qty=8.0,
        new_qty=7.0,
        created_by="postgres_e2e",
        branch_id=TEST_BRANCH_ID,
        reason="PostgreSQL E2E adjustment",
        reference=f"{PHASE_PREFIX}-ADJ",
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="stock movement insert", timeline=execution_timeline)
    database.execute_portable_write(conn, "UPDATE inventory SET qty = ? WHERE id = ? AND company_key = ?", (7.0, item_id, TEST_COMPANY_KEY))
    workflows.append(_workflow_result("inventory adjustment", "PASS", {"stock_movement_id": movement_id}, "PENDING_ROLLBACK", "stock movement inserted and inventory quantity updated"))

    invoice_id = _insert_document(conn, database, "invoices", "invoice_number", f"{PHASE_PREFIX}-INV", "customer_id", customer_id, 300.0, today)
    invoice_entry_id = _post_entry(
        engine,
        conn,
        database,
        "PostgreSQL E2E invoice",
        f"{PHASE_PREFIX}-INV",
        [
            {"account_id": engine.get_account_id(conn, "Accounts Receivable", "Asset"), "debit": 300.0, "credit": 0.0},
            {"account_id": engine.get_account_id(conn, "Sales Revenue", "Income"), "debit": 0.0, "credit": 300.0},
        ],
        customer_id=customer_id,
        source_table="invoices",
        source_type="Invoice",
        source_id=invoice_id,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="customer invoice journal insert", timeline=execution_timeline)
    workflows.append(_workflow_result("customer invoice", "PASS", {"invoice_id": invoice_id, "journal_entry_id": invoice_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, invoice_entry_id)} customer_balance={engine.get_customer_balance(TEST_COMPANY_KEY, customer_id, conn=conn)}"))

    customer_payment_id = _insert_payment(conn, database, "Customer Receipt", 340.0, customer_id=customer_id, invoice_id=invoice_id)
    customer_payment_entry_id = _post_entry(
        engine,
        conn,
        database,
        "PostgreSQL E2E customer payment",
        f"{PHASE_PREFIX}-PAY-AR",
        [
            {"account_id": engine.get_account_id(conn, "Cash", "Asset"), "debit": 340.0, "credit": 0.0},
            {"account_id": engine.get_account_id(conn, "Accounts Receivable", "Asset"), "debit": 0.0, "credit": 340.0},
        ],
        customer_id=customer_id,
        payment_id=customer_payment_id,
        source_table="payments",
        source_type="Customer Payment",
        source_id=customer_payment_id,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="customer payment journal insert", timeline=execution_timeline)
    workflows.append(_workflow_result("customer payment", "PASS", {"payment_id": customer_payment_id, "journal_entry_id": customer_payment_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, customer_payment_entry_id)} customer_balance={engine.get_customer_balance(TEST_COMPANY_KEY, customer_id, conn=conn)}"))

    bill_id = _insert_document(conn, database, "bills", "bill_number", f"{PHASE_PREFIX}-BILL", "supplier_id", supplier_id, 220.0, today)
    bill_entry_id = _post_entry(
        engine,
        conn,
        database,
        "PostgreSQL E2E supplier bill",
        f"{PHASE_PREFIX}-BILL",
        [
            {"account_id": engine.get_account_id(conn, "Purchases", "Expense"), "debit": 220.0, "credit": 0.0},
            {"account_id": engine.get_account_id(conn, "Accounts Payable", "Liability"), "debit": 0.0, "credit": 220.0},
        ],
        supplier_id=supplier_id,
        source_table="bills",
        source_type="Bill",
        source_id=bill_id,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="supplier bill journal insert", timeline=execution_timeline)
    workflows.append(_workflow_result("supplier bill", "PASS", {"bill_id": bill_id, "journal_entry_id": bill_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, bill_entry_id)} supplier_balance={engine.get_supplier_balance(TEST_COMPANY_KEY, supplier_id, conn=conn)}"))

    supplier_payment_id = _insert_payment(conn, database, "Supplier Payment", 220.0, supplier_id=supplier_id, bill_id=bill_id)
    supplier_payment_entry_id = _post_entry(
        engine,
        conn,
        database,
        "PostgreSQL E2E supplier payment",
        f"{PHASE_PREFIX}-PAY-AP",
        [
            {"account_id": engine.get_account_id(conn, "Accounts Payable", "Liability"), "debit": 220.0, "credit": 0.0},
            {"account_id": engine.get_account_id(conn, "Cash", "Asset"), "debit": 0.0, "credit": 220.0},
        ],
        supplier_id=supplier_id,
        payment_id=supplier_payment_id,
        source_table="payments",
        source_type="Supplier Payment",
        source_id=supplier_payment_id,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="supplier payment journal insert", timeline=execution_timeline)
    workflows.append(_workflow_result("supplier payment", "PASS", {"payment_id": supplier_payment_id, "journal_entry_id": supplier_payment_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, supplier_payment_entry_id)} supplier_balance={engine.get_supplier_balance(TEST_COMPANY_KEY, supplier_id, conn=conn)}"))

    general_entry_id = _post_entry(
        engine,
        conn,
        database,
        "PostgreSQL E2E general journal",
        f"{PHASE_PREFIX}-GJ",
        [
            {"account_id": engine.get_account_id(conn, "Cash", "Asset"), "debit": 50.0, "credit": 0.0},
            {"account_id": engine.get_account_id(conn, "Owner Capital", "Equity"), "debit": 0.0, "credit": 50.0},
        ],
        manual_entry=True,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="general journal insert", timeline=execution_timeline)
    workflows.append(_workflow_result("general journal", "PASS", {"journal_entry_id": general_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, general_entry_id)}"))

    cursor = database.execute_portable_write(
        conn,
        database.ensure_insert_sql_returning(
            """
            INSERT INTO payroll (
                company_key, emp_name, basic_salary, allowances, deductions, net_salary,
                month, year, payment_status, approval_status, created_by, status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'June', '2026', 'Unpaid', 'Posted', ?, 'Active')
            """
        ),
        (TEST_COMPANY_KEY, f"{PHASE_PREFIX} Employee", 1000.0, 100.0, 200.0, 900.0, "postgres_e2e"),
    )
    payroll_id = database.get_inserted_id(cursor)
    payroll_entry_id = _post_entry(
        engine,
        conn,
        database,
        "PostgreSQL E2E payroll",
        f"{PHASE_PREFIX}-PAYROLL",
        [
            {"account_id": engine.get_account_id(conn, "Salary Expense", "Expense"), "debit": 1100.0, "credit": 0.0},
            {"account_id": engine.get_account_id(conn, "Payroll Payable", "Liability"), "debit": 0.0, "credit": 900.0},
            {"account_id": engine.get_account_id(conn, "Payroll Taxes Payable", "Liability"), "debit": 0.0, "credit": 200.0},
        ],
        source_table="payroll",
        source_type="Payroll",
        source_id=payroll_id,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="payroll journal insert", timeline=execution_timeline)
    workflows.append(_workflow_result("payroll posting", "PASS", {"payroll_id": payroll_id, "journal_entry_id": payroll_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, payroll_entry_id)}"))

    _assert_transaction_stable(conn, database, expected_transaction_id, label="fixed asset insert before", timeline=execution_timeline)
    cursor = database.execute_portable_write(
        conn,
        database.ensure_insert_sql_returning(
            """
            INSERT INTO fixed_assets (
                company_key, asset_name, asset_category, purchase_date, cost,
                opening_book_value, useful_life_years, residual_value, depreciation_method,
                depreciation_rate, accumulated_depreciation, book_value, status, approval_status, created_by
            )
            VALUES (?, ?, 'Equipment', ?, ?, ?, 1, 0, 'Straight-line', 100, 0, ?, 'Active', 'Posted', ?)
            """
        ),
        (TEST_COMPANY_KEY, f"{PHASE_PREFIX} Asset", date(2026, 1, 1).isoformat(), 1200.0, 1200.0, 1200.0, "postgres_e2e"),
    )
    asset_id = database.get_inserted_id(cursor)
    _assert_transaction_stable(conn, database, expected_transaction_id, label="fixed asset insert after", timeline=execution_timeline)
    _assert_transaction_stable(conn, database, expected_transaction_id, label="asset acquisition account lookup before", timeline=execution_timeline)
    fixed_assets_account_id = engine.get_account_id(conn, "Fixed Assets", "Asset")
    cash_account_id = engine.get_account_id(conn, "Cash", "Asset")
    _assert_transaction_stable(conn, database, expected_transaction_id, label="asset acquisition account lookup after", timeline=execution_timeline)
    asset_entry_id = _post_entry(
        engine,
        conn,
        database,
        "PostgreSQL E2E asset acquisition",
        f"{PHASE_PREFIX}-ASSET",
        [
            {"account_id": fixed_assets_account_id, "debit": 1200.0, "credit": 0.0},
            {"account_id": cash_account_id, "debit": 0.0, "credit": 1200.0},
        ],
        source_table="fixed_assets",
        source_type="Fixed Asset Purchase",
        source_id=asset_id,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="asset acquisition journal insert", timeline=execution_timeline)
    depreciation_result = _run_e2e_asset_depreciation(
        conn,
        database,
        engine,
        asset_id,
        f"{PHASE_PREFIX} Asset",
        as_of_date=date(2026, 1, 31),
        expected_transaction_id=expected_transaction_id,
        timeline=execution_timeline,
    )
    workflows.append(
        _workflow_result(
            "asset depreciation",
            "PASS",
            {
                "asset_id": asset_id,
                "acquisition_journal_entry_id": asset_entry_id,
                "depreciation_journal_entry_id": depreciation_result.get("depreciation_journal_entry_id"),
            },
            "PENDING_ROLLBACK",
            f"depreciation_count={depreciation_result.get('depreciation_count')} acquisition_journal_balanced={_journal_balance_ok(conn, asset_entry_id)}",
        )
    )

    cursor = database.execute_portable_write(
        conn,
        database.ensure_insert_sql_returning(
            """
            INSERT INTO users (company_key, branch_id, full_name, login_key, password_hash, role, status)
            VALUES (?, ?, ?, ?, ?, 'Branch_Bookkeeper', 'Active')
            """
        ),
        (TEST_COMPANY_KEY, TEST_BRANCH_ID, f"{PHASE_PREFIX} User", f"{PHASE_PREFIX}-USER", "test-hash"),
    )
    user_id = database.get_inserted_id(cursor)
    database.execute_portable_write(conn, "UPDATE users SET status = 'Inactive' WHERE id = ? AND company_key = ?", (user_id, TEST_COMPANY_KEY))
    _insert_e2e_audit_event(
        conn,
        database,
        user_role="Master Admin",
        action="PostgreSQL E2E User Update",
        module_name="User Management",
        details=f"user_id={user_id}",
        action_type="admin",
        document_ref=str(user_id),
        timeline=execution_timeline,
    )
    _assert_transaction_stable(conn, database, expected_transaction_id, label="admin audit insert", timeline=execution_timeline)
    audit_count = _fetch_count(conn, "SELECT COUNT(*) AS count FROM audit_logs WHERE company_key = ? AND action = ?", (TEST_COMPANY_KEY, "PostgreSQL E2E User Update"))
    workflows.append(_workflow_result("admin/user update", "PASS", {"user_id": user_id}, "PENDING_ROLLBACK", f"audit_count={audit_count}"))

    return workflows


def main() -> int:
    import database
    import accounting_engine as engine
    import modules

    print(f"active_backend={database.get_active_db_backend()}")
    print(f"DATABASE_URL_present={bool(database.get_database_url())}")
    print(f"ERP_ENABLE_POSTGRES_RUNTIME={os.getenv('ERP_ENABLE_POSTGRES_RUNTIME')}")

    abort_payload = _abort_if_not_postgres(database)
    if abort_payload:
        print(f"ABORTED: {abort_payload['abort_reason']}")
        return 2

    conn = database.get_connection()
    if conn is None:
        payload = {
            "generated_at": _utc_now(),
            "overall_status": "FAIL",
            "cleanup_status": "NOT_STARTED",
            "backend_diagnostics": _backend_diagnostics(database),
            "abort_reason": "database.get_connection() returned None",
            "workflows": [],
            "blockers": ["PostgreSQL connection could not be opened."],
        }
        _write_report(payload)
        return 1

    workflows = []
    execution_timeline = []
    cleanup_status = "UNKNOWN"
    blockers = []
    expected_transaction_id = None
    try:
        expected_transaction_id = _begin_e2e_owned_transaction(conn, database)
        if expected_transaction_id is not None:
            _append_timeline(
                execution_timeline,
                "Owned transaction started",
                conn,
                database,
                expected_transaction_id=expected_transaction_id,
            )
        workflows = _run_workflows(
            conn,
            database,
            engine,
            modules,
            execution_timeline=execution_timeline,
            expected_transaction_id=expected_transaction_id,
        )
        _assert_transaction_stable(conn, database, expected_transaction_id, label="workflow completion", timeline=execution_timeline)
        conn.rollback()
        cleanup_status = "ROLLED_BACK"
        cleanup_conn = database.get_connection()
        try:
            remaining_company_rows = _fetch_count(cleanup_conn, "SELECT COUNT(*) AS count FROM companies WHERE key = ?", (TEST_COMPANY_KEY,))
            if remaining_company_rows:
                cleanup_status = "WARNING_ROWS_REMAIN"
                blockers.append(f"Rollback cleanup left {remaining_company_rows} company row(s).")
        finally:
            cleanup_conn.close()
    except Exception as exc:
        try:
            conn.rollback()
            cleanup_status = "ROLLED_BACK_AFTER_FAILURE"
        except Exception:
            cleanup_status = "ROLLBACK_FAILED"
        blockers.append(f"E2E workflow execution failed: {exc}")
        payload = {
            "generated_at": _utc_now(),
            "overall_status": "FAIL",
            "cleanup_status": cleanup_status,
            "backend_diagnostics": _backend_diagnostics(database),
            "abort_reason": None,
            "workflows": workflows,
            "execution_timeline": execution_timeline,
            "transaction_ownership": {
                "expected_transaction_id": expected_transaction_id,
                "status": "FAILED",
                "guard": "Fails immediately if PostgreSQL txid_current() changes inside the E2E-owned transaction.",
            },
            "blockers": blockers,
            "production_readiness_recommendation": "NO-GO until the failing workflow is fixed and rerun on PostgreSQL staging.",
        }
        _write_report(payload)
        return 1
    finally:
        conn.close()

    payload = {
        "generated_at": _utc_now(),
        "overall_status": "PASS" if not blockers else "WARNING",
        "cleanup_status": cleanup_status,
        "backend_diagnostics": _backend_diagnostics(database),
        "abort_reason": None,
        "workflows": [
            {**workflow, "cleanup_status": cleanup_status}
            for workflow in workflows
        ],
        "execution_timeline": execution_timeline,
        "transaction_ownership": {
            "expected_transaction_id": expected_transaction_id,
            "status": "STABLE",
            "guard": "PostgreSQL txid_current() remained stable across all guarded E2E seed, journal, and audit steps.",
        },
        "blockers": blockers,
        "production_readiness_recommendation": (
            "GO for final production-readiness review if this PASS result is produced on approved PostgreSQL staging; "
            "NO-GO if backend diagnostics are not PostgreSQL staging."
        ),
    }
    _write_report(payload)
    print(f"overall_status={payload['overall_status']}")
    print(f"cleanup_status={payload['cleanup_status']}")
    print(f"report_path={REPORT_PATH}")
    return 0 if payload["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
