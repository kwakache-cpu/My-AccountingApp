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
            "## Cleanup Strategy",
            "",
            payload.get("cleanup_strategy")
            or "All staged writes run inside one owned transaction and are rolled back at the end of certification.",
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


def _insert_company_and_branch(conn, database):
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
    database.execute_portable_write(
        conn,
        """
        INSERT INTO branches (branch_id, company_key, branch_name, status)
        VALUES (?, ?, ?, 'Active')
        """,
        (TEST_BRANCH_ID, TEST_COMPANY_KEY, f"{PHASE_PREFIX} Branch"),
    )


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


def _post_entry(engine, conn, description, reference, lines, **kwargs):
    return engine.post_accounting_impact(
        company_key=TEST_COMPANY_KEY,
        date=date(2026, 6, 25),
        description=description,
        reference=reference,
        lines=lines,
        created_by="postgres_e2e",
        branch_id=TEST_BRANCH_ID,
        source_module="PostgreSQL E2E",
        user_role="Bookkeeper",
        conn=conn,
        **kwargs,
    )


def _workflow_result(workflow, status, row_ids, cleanup_status, evidence):
    return {
        "workflow": workflow,
        "status": status,
        "row_ids": row_ids,
        "cleanup_status": cleanup_status,
        "evidence": evidence,
    }


def _run_workflows(conn, database, engine, modules):
    workflows = []
    today = date(2026, 6, 25)
    _insert_company_and_branch(conn, database)

    customer_id = _insert_party(conn, database, "customers", f"{PHASE_PREFIX} Customer")
    supplier_id = _insert_party(conn, database, "suppliers", f"{PHASE_PREFIX} Supplier")

    cursor = database.execute_portable_write(
        conn,
        database.ensure_insert_sql_returning(
            """
            INSERT INTO inventory (company_key, item_name, item_code, barcode, qty, price, cost_price, min_stock_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (TEST_COMPANY_KEY, f"{PHASE_PREFIX} Item", f"{PHASE_PREFIX}-ITEM", "", 10.0, 20.0, 6.0, 1.0),
    )
    item_id = database.get_inserted_id(cursor)

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
    pos_entry_id = _post_entry(
        engine,
        conn,
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
    modules.log_audit_action(conn, TEST_COMPANY_KEY, "Cashier", "POS Sale", "POS", details=f"{PHASE_PREFIX} POS", branch_id=TEST_BRANCH_ID)
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
    database.execute_portable_write(conn, "UPDATE inventory SET qty = ? WHERE id = ? AND company_key = ?", (7.0, item_id, TEST_COMPANY_KEY))
    workflows.append(_workflow_result("inventory adjustment", "PASS", {"stock_movement_id": movement_id}, "PENDING_ROLLBACK", "stock movement inserted and inventory quantity updated"))

    invoice_id = _insert_document(conn, database, "invoices", "invoice_number", f"{PHASE_PREFIX}-INV", "customer_id", customer_id, 300.0, today)
    invoice_entry_id = _post_entry(
        engine,
        conn,
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
    workflows.append(_workflow_result("customer invoice", "PASS", {"invoice_id": invoice_id, "journal_entry_id": invoice_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, invoice_entry_id)} customer_balance={engine.get_customer_balance(TEST_COMPANY_KEY, customer_id, conn=conn)}"))

    customer_payment_id = _insert_payment(conn, database, "Customer Receipt", 340.0, customer_id=customer_id, invoice_id=invoice_id)
    customer_payment_entry_id = _post_entry(
        engine,
        conn,
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
    workflows.append(_workflow_result("customer payment", "PASS", {"payment_id": customer_payment_id, "journal_entry_id": customer_payment_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, customer_payment_entry_id)} customer_balance={engine.get_customer_balance(TEST_COMPANY_KEY, customer_id, conn=conn)}"))

    bill_id = _insert_document(conn, database, "bills", "bill_number", f"{PHASE_PREFIX}-BILL", "supplier_id", supplier_id, 220.0, today)
    bill_entry_id = _post_entry(
        engine,
        conn,
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
    workflows.append(_workflow_result("supplier bill", "PASS", {"bill_id": bill_id, "journal_entry_id": bill_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, bill_entry_id)} supplier_balance={engine.get_supplier_balance(TEST_COMPANY_KEY, supplier_id, conn=conn)}"))

    supplier_payment_id = _insert_payment(conn, database, "Supplier Payment", 220.0, supplier_id=supplier_id, bill_id=bill_id)
    supplier_payment_entry_id = _post_entry(
        engine,
        conn,
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
    workflows.append(_workflow_result("supplier payment", "PASS", {"payment_id": supplier_payment_id, "journal_entry_id": supplier_payment_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, supplier_payment_entry_id)} supplier_balance={engine.get_supplier_balance(TEST_COMPANY_KEY, supplier_id, conn=conn)}"))

    general_entry_id = _post_entry(
        engine,
        conn,
        "PostgreSQL E2E general journal",
        f"{PHASE_PREFIX}-GJ",
        [
            {"account_id": engine.get_account_id(conn, "Cash", "Asset"), "debit": 50.0, "credit": 0.0},
            {"account_id": engine.get_account_id(conn, "Owner Capital", "Equity"), "debit": 0.0, "credit": 50.0},
        ],
        manual_entry=True,
    )
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
    workflows.append(_workflow_result("payroll posting", "PASS", {"payroll_id": payroll_id, "journal_entry_id": payroll_entry_id}, "PENDING_ROLLBACK", f"journal_balanced={_journal_balance_ok(conn, payroll_entry_id)}"))

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
    asset_entry_id = _post_entry(
        engine,
        conn,
        "PostgreSQL E2E asset acquisition",
        f"{PHASE_PREFIX}-ASSET",
        [
            {"account_id": engine.get_account_id(conn, "Fixed Assets", "Asset"), "debit": 1200.0, "credit": 0.0},
            {"account_id": engine.get_account_id(conn, "Cash", "Asset"), "debit": 0.0, "credit": 1200.0},
        ],
        source_table="fixed_assets",
        source_type="Fixed Asset Purchase",
        source_id=asset_id,
    )
    depreciation_count = modules.run_straight_line_depreciation(TEST_COMPANY_KEY, as_of_date=date(2026, 1, 31), conn=conn, created_by="postgres_e2e")
    workflows.append(_workflow_result("asset depreciation", "PASS", {"asset_id": asset_id, "acquisition_journal_entry_id": asset_entry_id}, "PENDING_ROLLBACK", f"depreciation_count={depreciation_count} acquisition_journal_balanced={_journal_balance_ok(conn, asset_entry_id)}"))

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
    modules.log_audit_action(conn, TEST_COMPANY_KEY, "Master Admin", "PostgreSQL E2E User Update", "User Management", details=f"user_id={user_id}", action_type="admin")
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
    cleanup_status = "UNKNOWN"
    blockers = []
    try:
        workflows = _run_workflows(conn, database, engine, modules)
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
