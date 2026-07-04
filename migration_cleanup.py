"""
Migration cleanup helpers (Phase 5B.5).

Read-only planners live in scripts/; this module provides DB operations and
report loading for the admin review UI. No Streamlit dependency.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = REPO_ROOT / "reports"
DEFAULT_PLAN_PATH = REPORTS_DIR / "migration_cleanup_plan.json"
DEFAULT_SUMMARY_PATH = REPORTS_DIR / "migration_integrity_summary.md"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "run_migration_integrity_audit.py"
PLAN_SCRIPT = REPO_ROOT / "scripts" / "plan_migration_data_cleanup.py"

MIGRATION_CLEANUP_ROLES = frozenset({"Dev", "Master Admin", "System Admin"})
CONFIRM_PAYMENT_APPLY_TEXT = "I confirm this payment reference fix"


READONLY_BUSY_TIMEOUT_MS = 5000

PLAN_WARNING_KEYS = (
    "pos_missing_branch_id",
    "missing_manager_user_id",
    "payments_without_reference",
    "invalid_expiry_dates",
)

SUMMARY_TO_PLAN_WARNING_KEYS = {
    "sales_without_branch_id": "pos_missing_branch_id",
    "missing_manager_user_id": "missing_manager_user_id",
    "payments_without_source_reference": "payments_without_reference",
    "invalid_expiry_dates": "invalid_expiry_dates",
}

CLEANUP_ITEM_CLASSIFICATION = {
    "pos_missing_branch_id": {
        "title": "POS sales missing branch_id",
        "classification": "manual_review",
        "summary_key": "sales_without_branch_id",
        "notes": "Assign branch manually when multiple active branches exist.",
    },
    "missing_manager_user_id": {
        "title": "Branches missing manager_user_id",
        "classification": "warning",
        "summary_key": "missing_manager_user_id",
        "notes": "Link an eligible manager user; does not block PostgreSQL runtime reads.",
    },
    "payments_without_reference": {
        "title": "Payments without source reference",
        "classification": "manual_review",
        "summary_key": "payments_without_source_reference",
        "notes": "Use guarded payment reference apply only after operator confirmation.",
    },
    "invalid_expiry_dates": {
        "title": "Invalid inventory expiry dates",
        "classification": "warning",
        "summary_key": "invalid_expiry_dates",
        "notes": "Review inventory expiry values; informational for migration readiness.",
    },
}

MIGRATION_REPORT_TIMESTAMP_ENV = "EKA_MIGRATION_REPORT_TIMESTAMP"


@dataclass
class ReadinessSnapshot:
    overall_score: str = "UNKNOWN"
    go_status: str = "UNKNOWN"
    warning_counts: dict[str, int] | None = None
    plan_item_counts: dict[str, int] = field(default_factory=dict)
    plan_warning_total: int = 0
    summary_warning_total: int = 0
    display_warning_total: int = 0
    reports_stale: bool = False
    refresh_hint: str = ""
    summary_path: str = ""
    audit_path: str = ""
    plan_path: str = ""
    audit_timestamp: str = ""
    plan_timestamp: str = ""
    report_timestamp: str = ""
    cleanup_classifications: list[dict[str, Any]] = field(default_factory=list)


def can_access_migration_cleanup(role: str | None) -> bool:
    return str(role or "").strip() in MIGRATION_CLEANUP_ROLES


def _company_scope_clause(role: str, company_key: str | None, column: str = "company_key") -> tuple[str, list[Any]]:
    if str(role or "").strip() == "Dev" or not company_key:
        return "", []
    return f" AND {column} = ?", [company_key]


def _portable_query(conn, sql: str, params: tuple[Any, ...] | list[Any] = ()):
    from database import execute_portable_query

    return execute_portable_query(conn, sql, tuple(params or ()))


def _portable_write(conn, sql: str, params: tuple[Any, ...] | list[Any] = ()):
    from database import execute_portable_write

    return execute_portable_write(conn, sql, tuple(params or ()))


def _row_dict(row) -> dict[str, Any]:
    from database import row_to_dict

    return dict(row_to_dict(row))


def _begin_transaction(conn) -> None:
    conn.execute("BEGIN")


def _commit_transaction(conn) -> None:
    if hasattr(conn, "commit"):
        conn.commit()
    else:
        conn.execute("COMMIT")


def _rollback_transaction(conn) -> None:
    if hasattr(conn, "rollback"):
        conn.rollback()
    else:
        conn.execute("ROLLBACK")


def get_runtime_db_path() -> Path:
    from database import DB_PATH

    return Path(DB_PATH)


def is_database_locked_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database is busy" in message


@contextmanager
def readonly_connection(
    db_path: Path | None = None,
    *,
    busy_timeout_ms: int = READONLY_BUSY_TIMEOUT_MS,
) -> Iterator[Any]:
    from database import get_connection, is_postgres_backend

    if is_postgres_backend():
        conn = get_connection()
        if conn is None:
            raise RuntimeError("Could not open PostgreSQL connection for migration cleanup review.")
        try:
            yield conn
        finally:
            conn.close()
        return

    path = db_path or get_runtime_db_path()
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=busy_timeout_ms / 1000.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
        yield conn
    finally:
        conn.close()


def count_plan_warning_items(plan: dict[str, Any] | None) -> dict[str, int]:
    plan = plan or {}
    counts = {key: len(plan.get(key) or []) for key in PLAN_WARNING_KEYS}
    return counts


def parse_timestamp_from_summary_text(text: str) -> str:
    match = re.search(r"\*\*Audited at:\*\*\s*([^\n]+)", text or "")
    return match.group(1).strip() if match else ""


def parse_timestamp_from_plan(plan: dict[str, Any] | None) -> str:
    return str((plan or {}).get("generated_at") or "").strip()


def summarize_cleanup_classifications(plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    plan = plan or {}
    rows: list[dict[str, Any]] = []
    for plan_key in PLAN_WARNING_KEYS:
        items = plan.get(plan_key) or []
        if not items:
            continue
        meta = CLEANUP_ITEM_CLASSIFICATION.get(plan_key, {})
        manual_count = sum(1 for item in items if item.get("manual_required"))
        auto_safe_count = sum(1 for item in items if item.get("auto_fix_safe"))
        rows.append(
            {
                "item_key": plan_key,
                "title": meta.get("title", plan_key),
                "classification": meta.get("classification", "warning"),
                "count": len(items),
                "manual_required_count": manual_count,
                "auto_fix_safe_count": auto_safe_count,
                "notes": meta.get("notes", ""),
            }
        )
    return rows


def build_readiness_snapshot(
    summary_path: Path | None = None,
    plan_path: Path | None = None,
) -> ReadinessSnapshot:
    summary_path = summary_path or DEFAULT_SUMMARY_PATH
    plan_path = plan_path or DEFAULT_PLAN_PATH
    snapshot = parse_readiness_from_summary(summary_path)
    snapshot.plan_path = str(plan_path)
    plan = load_cleanup_plan_json(plan_path) if plan_path.exists() else {}
    snapshot.plan_item_counts = count_plan_warning_items(plan)
    snapshot.plan_warning_total = sum(snapshot.plan_item_counts.values())
    snapshot.summary_warning_total = sum((snapshot.warning_counts or {}).values())
    snapshot.cleanup_classifications = summarize_cleanup_classifications(plan)
    if summary_path.exists():
        snapshot.audit_timestamp = parse_timestamp_from_summary_text(summary_path.read_text(encoding="utf-8"))
    snapshot.plan_timestamp = parse_timestamp_from_plan(plan)
    if snapshot.audit_timestamp and snapshot.plan_timestamp:
        snapshot.report_timestamp = snapshot.audit_timestamp
        snapshot.reports_stale = snapshot.audit_timestamp != snapshot.plan_timestamp
    elif not summary_path.exists() or not plan_path.exists():
        snapshot.reports_stale = True

    if plan_path.exists():
        snapshot.display_warning_total = snapshot.plan_warning_total
    elif snapshot.summary_warning_total:
        snapshot.display_warning_total = snapshot.summary_warning_total
    else:
        snapshot.display_warning_total = 0

    if snapshot.display_warning_total > 0 and snapshot.overall_score.upper() == "GREEN":
        snapshot.overall_score = "YELLOW"
    if snapshot.display_warning_total > 0 and snapshot.go_status.upper() == "GO":
        snapshot.go_status = "GO WITH WARNINGS"

    if not summary_path.exists() or not plan_path.exists():
        snapshot.refresh_hint = "Run audit to refresh reports."
    elif snapshot.reports_stale:
        snapshot.refresh_hint = (
            "Audit summary and cleanup plan timestamps differ; re-run audit to regenerate both with one timestamp."
        )
    elif (
        snapshot.go_status.upper().startswith("GO WITH")
        and snapshot.display_warning_total == 0
        and snapshot.summary_warning_total > 0
    ):
        snapshot.reports_stale = True
        snapshot.refresh_hint = "Warning totals may be stale — use Re-run Migration Integrity Audit."
    elif snapshot.go_status.upper().startswith("GO WITH") and snapshot.display_warning_total == 0:
        snapshot.refresh_hint = (
            "Go/No-Go is from the last audit file; cleanup items may already be resolved."
        )
    elif snapshot.display_warning_total > 0:
        snapshot.refresh_hint = (
            "Cleanup items remain. Resolve manual-review items or accept warnings before PostgreSQL cutover."
        )
    return snapshot


def load_cleanup_plan_json(plan_path: Path | None = None) -> dict[str, Any]:
    path = plan_path or DEFAULT_PLAN_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_readiness_from_summary(summary_path: Path | None = None) -> ReadinessSnapshot:
    path = summary_path or DEFAULT_SUMMARY_PATH
    snapshot = ReadinessSnapshot(
        summary_path=str(path),
        audit_path=str(REPORTS_DIR / "migration_integrity_audit.md"),
        plan_path=str(DEFAULT_PLAN_PATH),
    )
    if not path.exists():
        return snapshot
    text = path.read_text(encoding="utf-8")
    score_match = re.search(r"\*\*Overall readiness score:\*\*\s*\*\*([A-Z]+)\*\*", text)
    go_match = re.search(r"\*\*Recommendation:\*\*\s*\*\*([^*]+)\*\*", text)
    if score_match:
        snapshot.overall_score = score_match.group(1).strip()
    if go_match:
        snapshot.go_status = go_match.group(1).strip()
    warnings: dict[str, int] = {}
    in_top_warnings = False
    for line in text.splitlines():
        if line.strip() == "## Top Warnings":
            in_top_warnings = True
            continue
        if in_top_warnings and line.startswith("## "):
            break
        if not in_top_warnings:
            continue
        match = re.match(r"-\s+\*\*([^*]+):\*\*\s*(\d+)", line.strip())
        if match and match.group(1) in {
            "sales_without_branch_id",
            "missing_manager_user_id",
            "payments_without_source_reference",
            "invalid_expiry_dates",
        }:
            warnings[match.group(1)] = int(match.group(2))
    snapshot.warning_counts = warnings
    return snapshot


def list_pos_sales_missing_branch(
    conn: Any,
    *,
    role: str,
    company_key: str | None = None,
) -> list[dict[str, Any]]:
    scope_sql, scope_params = _company_scope_clause(role, company_key, "ps.company_key")
    rows = _portable_query(
        conn,
        f"""
        SELECT ps.id, ps.company_key, ps.receipt_number, ps.sale_date, ps.sale_datetime,
               ps.cashier, ps.grand_total, ps.branch_id, c.name AS company_name
        FROM pos_sales ps
        LEFT JOIN companies c ON c.key = ps.company_key
        WHERE (ps.branch_id IS NULL OR TRIM(ps.branch_id) = '')
        {scope_sql}
        ORDER BY ps.company_key, ps.id
        """,
        scope_params,
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        item = _row_dict(row)
        item["suggested_branch_id"] = _infer_single_active_branch(conn, item["company_key"])
        results.append(item)
    return results


def _infer_single_active_branch(conn: Any, company_key: str) -> str | None:
    from database import row_get

    branches = _portable_query(
        conn,
        """
        SELECT branch_id FROM branches
        WHERE company_key = ? AND COALESCE(is_active, 1) = 1
        ORDER BY branch_name
        """,
        (company_key,),
    ).fetchall()
    if len(branches) == 1:
        return str(row_get(branches[0], "branch_id", row_get(branches[0], 0)))
    return None


def _table_has_column(conn: Any, table_name: str, column_name: str) -> bool:
    from database import get_cached_table_column_names

    columns = get_cached_table_column_names(conn, table_name)
    return column_name in columns


def assign_pos_sale_branch_id(
    conn: Any,
    *,
    company_key: str,
    sale_id: int,
    branch_id: str,
    actor_role: str,
    confirmed: bool,
) -> dict[str, Any]:
    if not confirmed:
        return {"ok": False, "reason": "Confirmation required."}
    normalized_branch = str(branch_id or "").strip()
    if not normalized_branch:
        return {"ok": False, "reason": "Target branch is required."}
    branch_row = _portable_query(
        conn,
        """
        SELECT branch_id FROM branches
        WHERE company_key = ? AND branch_id = ? AND COALESCE(is_active, 1) = 1
        """,
        (company_key, normalized_branch),
    ).fetchone()
    if not branch_row:
        return {"ok": False, "reason": "Branch not found or inactive for this company."}
    sale_row = _portable_query(
        conn,
        """
        SELECT id, branch_id, receipt_number, sale_date, sale_datetime, cashier, grand_total
        FROM pos_sales
        WHERE id = ? AND company_key = ?
        """,
        (sale_id, company_key),
    ).fetchone()
    if not sale_row:
        return {"ok": False, "reason": "POS sale not found."}
    sale = _row_dict(sale_row)
    before_branch = sale.get("branch_id")
    if before_branch is not None and str(before_branch).strip():
        return {"ok": False, "reason": "POS sale already has a branch_id assigned."}
    receipt_number = sale.get("receipt_number")
    from database import log_audit_action

    try:
        _begin_transaction(conn)
        cursor = _portable_write(
            conn,
            """
            UPDATE pos_sales SET branch_id = ?
            WHERE id = ? AND company_key = ?
              AND (branch_id IS NULL OR TRIM(branch_id) = '')
            """,
            (normalized_branch, sale_id, company_key),
        )
        if cursor.rowcount != 1:
            _rollback_transaction(conn)
            return {"ok": False, "reason": "POS sale update did not affect exactly one row."}
        if _table_has_column(conn, "pos_sale_lines", "branch_id"):
            _portable_write(
                conn,
                """
                UPDATE pos_sale_lines SET branch_id = ?
                WHERE pos_sale_id = ? AND company_key = ?
                """,
                (normalized_branch, sale_id, company_key),
            )
        log_audit_action(
            conn,
            company_key,
            actor_role,
            "Migration cleanup: POS branch assigned",
            "Migration Cleanup",
            details=f"pos_sale_id={sale_id} receipt={receipt_number} branch_id={normalized_branch}",
            branch_id=normalized_branch,
            action_type="data_cleanup",
            document_ref=str(receipt_number),
            before_after_summary=f"branch_id: '' -> {normalized_branch}",
        )
        _commit_transaction(conn)
        return {
            "ok": True,
            "sale_id": sale_id,
            "branch_id": normalized_branch,
            "before": {
                "branch_id": before_branch or "",
                "receipt_number": receipt_number,
                "sale_date": sale.get("sale_datetime") or sale.get("sale_date"),
                "cashier": sale.get("cashier"),
                "grand_total": sale.get("grand_total"),
            },
            "after": {
                "branch_id": normalized_branch,
                "receipt_number": receipt_number,
                "sale_date": sale.get("sale_datetime") or sale.get("sale_date"),
                "cashier": sale.get("cashier"),
                "grand_total": sale.get("grand_total"),
            },
        }
    except Exception as exc:
        _rollback_transaction(conn)
        return {"ok": False, "reason": str(exc)}


def list_branches_missing_manager(
    conn: Any,
    *,
    role: str,
    company_key: str | None = None,
) -> list[dict[str, Any]]:
    scope_sql, scope_params = _company_scope_clause(role, company_key, "b.company_key")
    rows = _portable_query(
        conn,
        f"""
        SELECT b.branch_id, b.company_key, b.branch_name, b.branch_code,
               b.branch_manager, b.manager_user_id, c.name AS company_name
        FROM branches b
        LEFT JOIN companies c ON c.key = b.company_key
        WHERE (b.manager_user_id IS NULL OR TRIM(b.manager_user_id) = '')
        {scope_sql}
        ORDER BY b.company_key, b.branch_name
        """,
        scope_params,
    ).fetchall()
    return [_row_dict(row) for row in rows]


def assign_branch_manager_user_id(
    conn: Any,
    *,
    company_key: str,
    branch_id: str,
    manager_user_id: str,
    actor_role: str,
    confirmed: bool,
) -> dict[str, Any]:
    if not confirmed:
        return {"ok": False, "reason": "Confirmation required."}
    normalized_company_key = str(company_key or "").strip()
    normalized_branch_id = str(branch_id or "").strip()
    normalized_manager_user_id = str(manager_user_id or "").strip()
    if not normalized_company_key or not normalized_branch_id or not normalized_manager_user_id:
        return {"ok": False, "reason": "Company, branch, and manager user are required."}

    branch_row = _portable_query(
        conn,
        """
        SELECT branch_id, branch_name, branch_manager, manager_user_id
        FROM branches
        WHERE company_key = ? AND branch_id = ?
        """,
        (normalized_company_key, normalized_branch_id),
    ).fetchone()
    if not branch_row:
        return {"ok": False, "reason": "Branch not found for this company."}
    branch = _row_dict(branch_row)
    before_manager_user_id = branch.get("manager_user_id")
    if before_manager_user_id is not None and str(before_manager_user_id).strip():
        return {"ok": False, "reason": "Branch already has a manager_user_id assigned."}

    user_row = _portable_query(
        conn,
        """
        SELECT user_id, full_name, role, status, branch_id
        FROM users
        WHERE company_key = ? AND user_id = ?
        """,
        (normalized_company_key, normalized_manager_user_id),
    ).fetchone()
    if not user_row:
        return {"ok": False, "reason": "Active manager user not found in this company."}
    user = _row_dict(user_row)
    if str(user.get("status") or "Active").strip() != "Active":
        return {"ok": False, "reason": "Selected manager user is not active."}

    from database import PRIVILEGED_COMPANY_USER_ROLES, log_audit_action

    if str(user.get("role") or "").strip() in PRIVILEGED_COMPANY_USER_ROLES:
        return {"ok": False, "reason": "Privileged company roles cannot be assigned as branch managers."}
    existing_user_branch = str(user.get("branch_id") or "").strip()
    if existing_user_branch and existing_user_branch != normalized_branch_id:
        return {"ok": False, "reason": "Manager must be unassigned or already assigned to this branch."}

    manager_name = str(user.get("full_name") or "Branch Manager").strip() or "Branch Manager"
    try:
        _begin_transaction(conn)
        cursor = _portable_write(
            conn,
            """
            UPDATE branches
            SET manager_user_id = ?, branch_manager = ?
            WHERE company_key = ? AND branch_id = ?
              AND (manager_user_id IS NULL OR TRIM(manager_user_id) = '')
            """,
            (
                normalized_manager_user_id,
                manager_name,
                normalized_company_key,
                normalized_branch_id,
            ),
        )
        if cursor.rowcount != 1:
            _rollback_transaction(conn)
            return {"ok": False, "reason": "Branch manager update did not affect exactly one row."}
        log_audit_action(
            conn,
            normalized_company_key,
            actor_role,
            "Migration cleanup: branch manager_user_id assigned",
            "Migration Cleanup",
            details=f"branch_id={normalized_branch_id} manager_user_id={normalized_manager_user_id}",
            branch_id=normalized_branch_id,
            action_type="data_cleanup",
            document_ref=normalized_branch_id,
            before_after_summary=(
                f"manager_user_id: {before_manager_user_id!r} -> {normalized_manager_user_id!r}; "
                f"branch_manager: {branch.get('branch_manager')!r} -> {manager_name!r}"
            ),
        )
        _commit_transaction(conn)
        return {
            "ok": True,
            "company_key": normalized_company_key,
            "branch_id": normalized_branch_id,
            "manager_user_id": normalized_manager_user_id,
            "before": {
                "branch_manager": branch.get("branch_manager") or "",
                "manager_user_id": before_manager_user_id,
                "user_role": user.get("role"),
                "user_branch_id": user.get("branch_id"),
            },
            "after": {
                "branch_manager": manager_name,
                "manager_user_id": normalized_manager_user_id,
                "user_role": user.get("role"),
                "user_branch_id": user.get("branch_id"),
            },
        }
    except Exception as exc:
        _rollback_transaction(conn)
        return {"ok": False, "reason": str(exc)}


def list_payment_reference_candidates(
    conn: Any,
    plan: dict[str, Any] | None = None,
    *,
    role: str,
    company_key: str | None = None,
) -> list[dict[str, Any]]:
    plan = plan or load_cleanup_plan_json()
    candidates = plan.get("payments_without_reference") or []
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        if not candidate.get("auto_fix_safe") or candidate.get("manual_required"):
            continue
        payment_company = str(candidate.get("company_key") or "")
        if role != "Dev" and company_key and payment_company != company_key:
            continue
        payment_id = int(candidate["id"])
        row = _portable_query(
            conn,
            """
            SELECT p.id, p.company_key, p.payment_type, p.amount, p.customer_id, p.reference,
                   p.invoice_id, p.bill_id, p.supplier_id, p.posted_entry_id, c.name AS company_name
            FROM payments p
            LEFT JOIN companies c ON c.key = p.company_key
            WHERE p.id = ? AND p.company_key = ?
            """,
            (payment_id, payment_company),
        ).fetchone()
        if not row:
            continue
        item = _row_dict(row)
        item["proposed_values"] = candidate.get("proposed_values") or {}
        item["current_values"] = {
            "customer_id": item.get("customer_id"),
            "supplier_id": item.get("supplier_id"),
            "invoice_id": item.get("invoice_id"),
            "bill_id": item.get("bill_id"),
            "reference": item.get("reference") or "",
            "posted_entry_id": item.get("posted_entry_id"),
        }
        item["still_needs_fix"] = payment_still_needs_reference_fix(item)
        results.append(item)
    return results


def payment_still_needs_reference_fix(payment_row: dict[str, Any]) -> bool:
    invoice_ok = payment_row.get("invoice_id") is None
    bill_ok = payment_row.get("bill_id") is None
    reference_empty = payment_row.get("reference") is None or str(payment_row.get("reference") or "").strip() == ""
    return invoice_ok and bill_ok and reference_empty


def apply_payment_reference_fix(
    conn: Any,
    *,
    company_key: str,
    payment_id: int,
    customer_id: int,
    reference: str,
    actor_role: str,
    confirmed: bool,
    confirmation_text: str,
    create_backup: bool = True,
) -> dict[str, Any]:
    if str(confirmation_text or "").strip() != CONFIRM_PAYMENT_APPLY_TEXT:
        return {"ok": False, "reason": f"Confirmation text must match exactly: {CONFIRM_PAYMENT_APPLY_TEXT}"}
    if not confirmed:
        return {"ok": False, "reason": f"Confirmation text must match exactly: {CONFIRM_PAYMENT_APPLY_TEXT}"}
    safe_reference = str(reference or "").strip()
    if not safe_reference:
        return {"ok": False, "reason": "Reference is required."}
    if customer_id is None:
        return {"ok": False, "reason": "customer_id is required."}

    row = _portable_query(
        conn,
        """
        SELECT id, company_key, customer_id, reference, invoice_id, bill_id, payment_type, amount
        FROM payments WHERE id = ? AND company_key = ?
        """,
        (payment_id, company_key),
    ).fetchone()
    if not row:
        return {"ok": False, "reason": "Payment not found."}
    payment = _row_dict(row)
    if not payment_still_needs_reference_fix(payment):
        return {"ok": False, "reason": "Payment no longer matches expected bad state."}

    backup_path = None
    if create_backup:
        try:
            from db_upgrade_safety import create_timestamped_backup

            from database import DB_PATH

            backup_path = create_timestamped_backup(str(DB_PATH), reason="migration_cleanup_ui")
        except Exception as exc:
            return {"ok": False, "reason": f"Backup failed; apply refused: {exc}"}
        if not backup_path:
            return {"ok": False, "reason": "Backup helper unavailable; apply refused."}

    from database import log_audit_action

    before_customer = payment.get("customer_id")
    before_reference = payment.get("reference")
    try:
        _begin_transaction(conn)
        cursor = _portable_write(
            conn,
            """
            UPDATE payments
            SET customer_id = ?, reference = ?
            WHERE id = ? AND company_key = ?
              AND invoice_id IS NULL AND bill_id IS NULL
              AND (reference IS NULL OR TRIM(reference) = '')
            """,
            (customer_id, safe_reference, payment_id, company_key),
        )
        if cursor.rowcount != 1:
            _rollback_transaction(conn)
            return {"ok": False, "reason": "Payment update did not affect exactly one row."}
        log_audit_action(
            conn,
            company_key,
            actor_role,
            "Migration cleanup: payment reference linked",
            "Migration Cleanup",
            details=f"payment_id={payment_id} customer_id={customer_id} reference={safe_reference}",
            action_type="data_cleanup",
            document_ref=str(payment_id),
            before_after_summary=(
                f"customer_id: {before_customer} -> {customer_id}; "
                f"reference: {before_reference!r} -> {safe_reference!r}"
            ),
        )
        _commit_transaction(conn)
        return {
            "ok": True,
            "payment_id": payment_id,
            "backup_path": backup_path,
            "customer_id": customer_id,
            "reference": safe_reference,
            "before": {
                "customer_id": before_customer,
                "reference": before_reference or "",
                "invoice_id": payment.get("invoice_id"),
                "bill_id": payment.get("bill_id"),
                "payment_type": payment.get("payment_type"),
                "amount": payment.get("amount"),
            },
            "after": {
                "customer_id": customer_id,
                "reference": safe_reference,
                "invoice_id": payment.get("invoice_id"),
                "bill_id": payment.get("bill_id"),
                "payment_type": payment.get("payment_type"),
                "amount": payment.get("amount"),
            },
        }
    except Exception as exc:
        _rollback_transaction(conn)
        return {"ok": False, "reason": str(exc)}


def run_readonly_audit_subprocess(db_path: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    if not AUDIT_SCRIPT.exists():
        return {"ok": False, "reason": f"Audit script not found: {AUDIT_SCRIPT}"}
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    if db_path:
        run_env["EKA_AUDIT_DB_PATH"] = str(db_path)
    result = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=run_env,
        timeout=120,
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def run_readonly_plan_subprocess(db_path: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    if not PLAN_SCRIPT.exists():
        return {"ok": False, "reason": f"Plan script not found: {PLAN_SCRIPT}"}
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    if db_path:
        run_env["EKA_AUDIT_DB_PATH"] = str(db_path)
    result = subprocess.run(
        [sys.executable, str(PLAN_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=run_env,
        timeout=120,
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def regenerate_migration_integrity_reports(db_path: Path | None = None) -> dict[str, Any]:
    """Run audit + cleanup plan with one shared UTC timestamp embedded in both reports."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    env = {MIGRATION_REPORT_TIMESTAMP_ENV: timestamp}
    audit_result = run_readonly_audit_subprocess(db_path=db_path, env=env)
    plan_result = run_readonly_plan_subprocess(db_path=db_path, env=env)
    snapshot = build_readiness_snapshot()
    return {
        "ok": bool(audit_result.get("ok") and plan_result.get("ok")),
        "report_timestamp": timestamp,
        "audit_result": audit_result,
        "plan_result": plan_result,
        "reports_aligned": bool(snapshot.audit_timestamp and snapshot.audit_timestamp == snapshot.plan_timestamp),
        "readiness": snapshot,
    }
