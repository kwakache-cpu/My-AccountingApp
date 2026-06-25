#!/usr/bin/env python3
"""
Read-only migration data cleanup planner (Phase 5B.3).

Default mode prints proposed SQL fixes without executing them.
--apply is reserved for a future guarded implementation and is NOT active yet.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "eka_enterprise_v3.db"
REPORTS_DIR = REPO_ROOT / "reports"
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATE_GLOB = "????-??-??"


@dataclass
class CleanupItem:
    warning_type: str
    table_name: str
    row_id: Any
    company_key: str
    branch_id: str | None
    label: str
    current_value: str
    recommended_fix: str
    proposed_sql: str
    risk_level: str
    auto_fix_safe: bool
    manual_decision_needed: bool
    notes: str = ""
    current_values: dict[str, Any] = field(default_factory=dict)
    proposed_values: dict[str, Any] = field(default_factory=dict)


@dataclass
class CleanupPlan:
    db_path: str
    generated_at: str
    items: list[CleanupItem] = field(default_factory=list)

    @property
    def manual_count(self) -> int:
        return sum(1 for i in self.items if i.manual_decision_needed)

    @property
    def auto_safe_count(self) -> int:
        return sum(1 for i in self.items if i.auto_fix_safe and not i.manual_decision_needed)

    @property
    def no_action_count(self) -> int:
        return sum(
            1
            for i in self.items
            if not i.manual_decision_needed and not i.auto_fix_safe and not i.proposed_sql.strip()
        )


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _iso_date_value(raw: str | None) -> tuple[bool, str | None, str]:
    text = str(raw or "").strip()
    if not text:
        return True, None, "empty"
    if ISO_DATE_RE.match(text):
        try:
            datetime.strptime(text, "%Y-%m-%d")
            return True, text, "already_iso"
        except ValueError:
            pass
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return False, parsed.strftime("%Y-%m-%d"), "parsed"
        except ValueError:
            continue
    return False, None, "unparseable"


def _active_branches(conn, company_key: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT branch_id, branch_name, branch_code, COALESCE(is_active, 1) AS is_active
        FROM branches
        WHERE company_key = ? AND COALESCE(is_active, 1) = 1
        ORDER BY branch_name
        """,
        (company_key,),
    ).fetchall()


def _company_users(conn, company_key: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, user_id, full_name, role, branch_id, login_key, status
        FROM users
        WHERE company_key = ?
        ORDER BY full_name
        """,
        (company_key,),
    ).fetchall()


def _match_user_by_manager_text(users: list[sqlite3.Row], manager_text: str) -> sqlite3.Row | None:
    needle = str(manager_text or "").strip().lower()
    if not needle:
        return None
    for user in users:
        full_name = str(user["full_name"] or "").strip().lower()
        user_id = str(user["user_id"] or "").strip().lower()
        login_key = str(user["login_key"] or "").strip().lower()
        if needle in {full_name, user_id, login_key}:
            return user
        if full_name.startswith(needle) or needle.startswith(full_name):
            if full_name and len(needle) >= 3:
                return user
    return None


def _infer_pos_branch(conn, sale: sqlite3.Row) -> tuple[str | None, str]:
    company_key = sale["company_key"]
    branches = _active_branches(conn, company_key)
    if not branches:
        return None, "No active branches for company."

    if len(branches) == 1:
        branch = branches[0]
        return branch["branch_id"], f"Single active branch: {branch['branch_name']} ({branch['branch_id']})."

    cashier = str(sale["cashier"] or "").strip()
    if cashier:
        users = _company_users(conn, company_key)
        for user in users:
            names = {
                str(user["full_name"] or "").strip().lower(),
                str(user["login_key"] or "").strip().lower(),
                str(user["user_id"] or "").strip().lower(),
            }
            if cashier.lower() in names and user["branch_id"]:
                return str(user["branch_id"]), f"Cashier '{cashier}' maps to user branch {user['branch_id']}."
        for user in users:
            if cashier.lower() in str(user["full_name"] or "").lower() and user["branch_id"]:
                return str(user["branch_id"]), f"Cashier partial match to user {user['full_name']}."

    journal = conn.execute(
        """
        SELECT branch_id FROM journal_entries
        WHERE company_key = ? AND source_table = 'pos_sales' AND source_id = ?
          AND branch_id IS NOT NULL AND TRIM(branch_id) != ''
        LIMIT 1
        """,
        (company_key, sale["id"]),
    ).fetchone()
    if journal and journal["branch_id"]:
        return str(journal["branch_id"]), "Inferred from linked journal entry branch_id."

    branch_names = ", ".join(f"{b['branch_name']} ({b['branch_id']})" for b in branches)
    return None, f"Multiple active branches ({len(branches)}): {branch_names}. Cashier '{cashier or 'unknown'}' is not branch-scoped."


def plan_pos_sales_cleanup(conn) -> list[CleanupItem]:
    items: list[CleanupItem] = []
    rows = conn.execute(
        """
        SELECT ps.id, ps.company_key, ps.branch_id, ps.receipt_number, ps.sale_date,
               ps.cashier, ps.grand_total, c.name AS company_name
        FROM pos_sales ps
        LEFT JOIN companies c ON c.key = ps.company_key
        WHERE ps.branch_id IS NULL OR TRIM(ps.branch_id) = ''
        ORDER BY ps.id
        """
    ).fetchall()

    for row in rows:
        inferred_branch, reason = _infer_pos_branch(conn, row)
        label = f"{row['company_name'] or row['company_key']} / receipt {row['receipt_number']}"
        current = f"branch_id='{row['branch_id'] or ''}'"
        row_current = {
            "branch_id": row["branch_id"] or "",
            "receipt_number": row["receipt_number"],
            "cashier": row["cashier"],
            "sale_date": row["sale_date"],
        }
        if inferred_branch:
            fix = f"Set branch_id to '{inferred_branch}'"
            sql = (
                f"UPDATE pos_sales SET branch_id = '{inferred_branch}' "
                f"WHERE id = {row['id']} AND company_key = '{row['company_key']}';"
            )
            items.append(
                CleanupItem(
                    warning_type="sales_without_branch_id",
                    table_name="pos_sales",
                    row_id=row["id"],
                    company_key=row["company_key"],
                    branch_id=inferred_branch,
                    label=label,
                    current_value=current,
                    recommended_fix=fix,
                    proposed_sql=sql,
                    risk_level="MEDIUM",
                    auto_fix_safe=True,
                    manual_decision_needed=False,
                    notes=reason,
                    current_values=row_current,
                    proposed_values={"branch_id": inferred_branch},
                )
            )
        else:
            items.append(
                CleanupItem(
                    warning_type="sales_without_branch_id",
                    table_name="pos_sales",
                    row_id=row["id"],
                    company_key=row["company_key"],
                    branch_id=None,
                    label=label,
                    current_value=current,
                    recommended_fix="Assign branch_id manually after confirming sale location.",
                    proposed_sql="-- manual review required; no auto SQL proposed",
                    risk_level="MEDIUM",
                    auto_fix_safe=False,
                    manual_decision_needed=True,
                    notes=reason,
                    current_values=row_current,
                    proposed_values={},
                )
            )
    return items


def plan_expiry_cleanup(conn) -> list[CleanupItem]:
    items: list[CleanupItem] = []
    # Match Phase 5B.2 audit selection (includes GLOB false positives).
    rows = conn.execute(
        """
        SELECT id, company_key, item_name, item_code, expiry_date
        FROM inventory
        WHERE expiry_date IS NOT NULL AND TRIM(expiry_date) != ''
          AND expiry_date NOT GLOB ?
        ORDER BY id
        """,
        (ISO_DATE_GLOB,),
    ).fetchall()

    for row in rows:
        valid, iso_value, status = _iso_date_value(row["expiry_date"])
        label = f"{row['item_name']} ({row['item_code'] or 'no code'})"
        current = f"expiry_date='{row['expiry_date']}'"
        row_current = {"expiry_date": row["expiry_date"], "item_code": row["item_code"]}
        if valid and status == "already_iso":
            items.append(
                CleanupItem(
                    warning_type="invalid_expiry_dates",
                    table_name="inventory",
                    row_id=row["id"],
                    company_key=row["company_key"],
                    branch_id=None,
                    label=label,
                    current_value=current,
                    recommended_fix="No change — date is already valid ISO YYYY-MM-DD.",
                    proposed_sql="",
                    risk_level="LOW",
                    auto_fix_safe=False,
                    manual_decision_needed=False,
                    notes="No action — valid ISO date.",
                    current_values=row_current,
                    proposed_values={"expiry_date": row["expiry_date"]},
                )
            )
            continue
        if valid and iso_value and status == "parsed":
            sql = (
                f"UPDATE inventory SET expiry_date = '{iso_value}' "
                f"WHERE id = {row['id']} AND company_key = '{row['company_key']}';"
            )
            items.append(
                CleanupItem(
                    warning_type="invalid_expiry_dates",
                    table_name="inventory",
                    row_id=row["id"],
                    company_key=row["company_key"],
                    branch_id=None,
                    label=label,
                    current_value=current,
                    recommended_fix=f"Normalize to ISO '{iso_value}'",
                    proposed_sql=sql,
                    risk_level="MEDIUM",
                    auto_fix_safe=True,
                    manual_decision_needed=False,
                    notes=f"Parsed from non-ISO input using {status}.",
                    current_values=row_current,
                    proposed_values={"expiry_date": iso_value},
                )
            )
            continue
        items.append(
            CleanupItem(
                warning_type="invalid_expiry_dates",
                table_name="inventory",
                row_id=row["id"],
                company_key=row["company_key"],
                branch_id=None,
                label=label,
                current_value=current,
                recommended_fix="Clear expiry_date or enter correct ISO date manually.",
                proposed_sql=(
                    f"-- Option A: UPDATE inventory SET expiry_date = NULL "
                    f"WHERE id = {row['id']} AND company_key = '{row['company_key']}';\n"
                    f"-- Option B: UPDATE inventory SET expiry_date = 'YYYY-MM-DD' "
                    f"WHERE id = {row['id']} AND company_key = '{row['company_key']}';"
                ),
                risk_level="MEDIUM",
                auto_fix_safe=False,
                manual_decision_needed=True,
                notes="Could not parse expiry date safely.",
                current_values=row_current,
                proposed_values={},
            )
        )
    return items


def plan_manager_cleanup(conn) -> list[CleanupItem]:
    items: list[CleanupItem] = []
    rows = conn.execute(
        """
        SELECT branch_id, company_key, branch_name, branch_manager, manager_user_id
        FROM branches
        WHERE manager_user_id IS NULL OR TRIM(manager_user_id) = ''
        ORDER BY branch_id
        """
    ).fetchall()

    for row in rows:
        users = _company_users(conn, row["company_key"])
        matched = _match_user_by_manager_text(users, row["branch_manager"])
        label = f"{row['branch_name']} ({row['branch_id']})"
        current = f"branch_manager='{row['branch_manager'] or ''}', manager_user_id=NULL"
        row_current = {
            "branch_manager": row["branch_manager"] or "",
            "manager_user_id": row["manager_user_id"],
        }

        if matched and matched["user_id"]:
            manager_user_id = str(matched["user_id"])
            sql = (
                f"UPDATE branches SET manager_user_id = '{manager_user_id}', "
                f"branch_manager = '{matched['full_name']}' "
                f"WHERE branch_id = '{row['branch_id']}' AND company_key = '{row['company_key']}';"
            )
            items.append(
                CleanupItem(
                    warning_type="missing_manager_user_id",
                    table_name="branches",
                    row_id=row["branch_id"],
                    company_key=row["company_key"],
                    branch_id=row["branch_id"],
                    label=label,
                    current_value=current,
                    recommended_fix=f"Link manager_user_id to user '{matched['full_name']}' ({manager_user_id})",
                    proposed_sql=sql,
                    risk_level="LOW",
                    auto_fix_safe=True,
                    manual_decision_needed=False,
                    notes=f"Matched branch_manager text to user full_name/user_id.",
                    current_values=row_current,
                    proposed_values={
                        "manager_user_id": manager_user_id,
                        "branch_manager": str(matched["full_name"] or ""),
                    },
                )
            )
        elif matched and not matched["user_id"]:
            items.append(
                CleanupItem(
                    warning_type="missing_manager_user_id",
                    table_name="branches",
                    row_id=row["branch_id"],
                    company_key=row["company_key"],
                    branch_id=row["branch_id"],
                    label=label,
                    current_value=current,
                    recommended_fix=(
                        f"User '{matched['full_name']}' matches branch_manager text but has NULL user_id. "
                        "Assign user_id first, then set branches.manager_user_id."
                    ),
                    proposed_sql="-- manual: assign users.user_id for matched user before branch manager link",
                    risk_level="LOW",
                    auto_fix_safe=False,
                    manual_decision_needed=True,
                    notes="Matched by name only; manager_user_id column requires users.user_id.",
                    current_values=row_current,
                    proposed_values={"manager_user_id": None},
                )
            )
        else:
            branch_staff = [
                u for u in users if str(u["branch_id"] or "") == row["branch_id"]
            ]
            hint = ""
            if branch_staff:
                names = ", ".join(f"{u['full_name']} ({u['role']})" for u in branch_staff)
                hint = f" Branch staff: {names}."
            items.append(
                CleanupItem(
                    warning_type="missing_manager_user_id",
                    table_name="branches",
                    row_id=row["branch_id"],
                    company_key=row["company_key"],
                    branch_id=row["branch_id"],
                    label=label,
                    current_value=current,
                    recommended_fix="Assign branch manager manually in Branch Management UI.",
                    proposed_sql="-- manual review required",
                    risk_level="LOW",
                    auto_fix_safe=False,
                    manual_decision_needed=True,
                    notes=f"No user match for branch_manager '{row['branch_manager']}'.{hint}",
                    current_values=row_current,
                    proposed_values={},
                )
            )
    return items


def plan_payment_cleanup(conn) -> list[CleanupItem]:
    items: list[CleanupItem] = []
    rows = conn.execute(
        """
        SELECT p.id, p.company_key, p.payment_date, p.payment_type, p.amount, p.method,
               p.reference, p.customer_id, p.supplier_id, p.invoice_id, p.bill_id,
               p.posted_entry_id, c.name AS company_name
        FROM payments p
        LEFT JOIN companies c ON c.key = p.company_key
        WHERE (p.invoice_id IS NULL AND p.bill_id IS NULL)
          AND (p.reference IS NULL OR TRIM(p.reference) = '')
        ORDER BY p.id
        """
    ).fetchall()

    for row in rows:
        label = (
            f"{row['company_name'] or row['company_key']} / "
            f"{row['payment_type']} GHS {row['amount']:.2f} on {row['payment_date']}"
        )
        current = (
            f"invoice_id=NULL, bill_id=NULL, customer_id={row['customer_id']}, "
            f"supplier_id={row['supplier_id']}, reference=''"
        )
        row_current = {
            "invoice_id": row["invoice_id"],
            "bill_id": row["bill_id"],
            "customer_id": row["customer_id"],
            "supplier_id": row["supplier_id"],
            "reference": row["reference"] or "",
            "payment_type": row["payment_type"],
            "amount": row["amount"],
        }
        proposed_values: dict[str, Any] = {}
        notes_parts: list[str] = []
        proposed_customer = row["customer_id"]
        proposed_supplier = row["supplier_id"]
        proposed_reference = str(row["reference"] or "").strip()
        proposed_invoice = row["invoice_id"]
        proposed_bill = row["bill_id"]

        if row["posted_entry_id"]:
            journal = conn.execute(
                "SELECT description FROM journal_entries WHERE id = ?",
                (row["posted_entry_id"],),
            ).fetchone()
            if journal and journal["description"]:
                notes_parts.append(f"Journal #{row['posted_entry_id']}: {journal['description']}")
                if not proposed_reference:
                    proposed_reference = str(journal["description"]).strip()

        if not proposed_customer and row["payment_type"] == "Customer Receipt":
            if row["posted_entry_id"] and proposed_reference:
                token = proposed_reference.split("-")[-1].strip()
                customer = conn.execute(
                    """
                    SELECT id, name FROM customers
                    WHERE company_key = ?
                      AND (LOWER(name) = LOWER(?) OR LOWER(name) LIKE '%' || LOWER(?) || '%')
                    LIMIT 1
                    """,
                    (row["company_key"], token, token),
                ).fetchone()
                if customer:
                    proposed_customer = customer["id"]
                    notes_parts.append(f"Matched customer '{customer['name']}' (id={customer['id']}) from journal text.")

        if proposed_invoice or proposed_bill:
            fix = "Link to existing invoice/bill reference."
            sql_parts = []
            if proposed_invoice:
                sql_parts.append(f"invoice_id = {proposed_invoice}")
            if proposed_bill:
                sql_parts.append(f"bill_id = {proposed_bill}")
            if proposed_reference:
                sql_parts.append(f"reference = '{proposed_reference.replace(chr(39), chr(39)+chr(39))}'")
            sql = (
                f"UPDATE payments SET {', '.join(sql_parts)} "
                f"WHERE id = {row['id']} AND company_key = '{row['company_key']}';"
            )
            auto_safe = True
            manual = False
        elif proposed_customer and proposed_reference:
            safe_ref = proposed_reference.replace("'", "''")
            sql = (
                f"UPDATE payments SET customer_id = {proposed_customer}, reference = '{safe_ref}' "
                f"WHERE id = {row['id']} AND company_key = '{row['company_key']}';"
            )
            fix = f"Set customer_id={proposed_customer} and reference from journal description."
            auto_safe = True
            manual = False
        elif row["payment_type"] in {"Loan Received", "Loan Repayment", "Owner Capital / Owner Investment"}:
            sql = "-- informational: non-AR/AP payment type may legitimately lack invoice/bill link"
            fix = "Review payment type — may not require invoice/bill; add descriptive reference only."
            auto_safe = False
            manual = True
            notes_parts.append("Non-invoice payment type.")
        else:
            sql = "-- manual review: add reference and/or link customer_id, invoice_id, or bill_id"
            fix = "Manual review — add reference and link to customer/supplier/invoice/bill if applicable."
            auto_safe = False
            manual = True

        if auto_safe and not manual:
            proposed_values = {
                "customer_id": proposed_customer,
                "reference": proposed_reference,
            }
        items.append(
            CleanupItem(
                warning_type="payments_without_source_reference",
                table_name="payments",
                row_id=row["id"],
                company_key=row["company_key"],
                branch_id=None,
                label=label,
                current_value=current,
                recommended_fix=fix,
                proposed_sql=sql,
                risk_level="LOW" if manual else "MEDIUM",
                auto_fix_safe=auto_safe,
                manual_decision_needed=manual,
                notes=" ".join(notes_parts),
                current_values=row_current,
                proposed_values=proposed_values,
            )
        )
    return items


def build_cleanup_plan(db_path: Path) -> CleanupPlan:
    override = str(os.environ.get("EKA_MIGRATION_REPORT_TIMESTAMP", "") or "").strip()
    generated_at = override or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    conn = _connect_readonly(db_path)
    try:
        items: list[CleanupItem] = []
        items.extend(plan_pos_sales_cleanup(conn))
        items.extend(plan_expiry_cleanup(conn))
        items.extend(plan_manager_cleanup(conn))
        items.extend(plan_payment_cleanup(conn))
    finally:
        conn.close()
    return CleanupPlan(db_path=str(db_path), generated_at=generated_at, items=items)


WARNING_JSON_KEYS = {
    "sales_without_branch_id": "pos_missing_branch_id",
    "missing_manager_user_id": "missing_manager_user_id",
    "payments_without_source_reference": "payments_without_reference",
    "invalid_expiry_dates": "invalid_expiry_dates",
}


def item_to_candidate(item: CleanupItem) -> dict[str, Any]:
    return {
        "id": item.row_id,
        "table": item.table_name,
        "company_key": item.company_key,
        "branch_id": item.branch_id,
        "label": item.label,
        "current_values": item.current_values,
        "proposed_values": item.proposed_values,
        "risk": item.risk_level,
        "auto_fix_safe": item.auto_fix_safe,
        "manual_required": item.manual_decision_needed,
        "reason": item.notes or item.recommended_fix,
        "proposed_sql": item.proposed_sql,
    }


def export_cleanup_plan_json(plan: CleanupPlan) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": plan.generated_at,
        "database_path": plan.db_path,
        "pos_missing_branch_id": [],
        "missing_manager_user_id": [],
        "payments_without_reference": [],
        "invalid_expiry_dates": [],
    }
    for item in plan.items:
        key = WARNING_JSON_KEYS.get(item.warning_type)
        if not key:
            continue
        payload[key].append(item_to_candidate(item))
    return payload


def write_cleanup_plan_json(plan: CleanupPlan, path: Path) -> None:
    path.write_text(
        json.dumps(export_cleanup_plan_json(plan), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def render_markdown(plan: CleanupPlan) -> str:
    lines = [
        "# Migration Data Cleanup Plan",
        "",
        f"**Generated at:** {plan.generated_at}",
        f"**Database:** `{plan.db_path}`",
        "**Mode:** read-only analysis (no data modified)",
        "",
        "## Summary",
        "",
        f"- **Total warning rows analyzed:** {len(plan.items)}",
        f"- **Safe to auto-fix later:** {plan.auto_safe_count}",
        f"- **Manual decision required:** {plan.manual_count}",
        f"- **No action needed:** {plan.no_action_count}",
        "",
        "## Cleanup Readiness",
        "",
    ]
    if plan.manual_count == 0 and plan.auto_safe_count > 0:
        lines.append("After applying safe auto-fixes, migration readiness should improve to **GO**.")
    elif plan.manual_count > 0:
        lines.append(
            "Migration remains **GO WITH WARNINGS** until manual items are resolved or accepted as exceptions."
        )
    else:
        lines.append("No cleanup actions required; audit warnings were false positives or informational.")

    warning_order = [
        "sales_without_branch_id",
        "invalid_expiry_dates",
        "missing_manager_user_id",
        "payments_without_source_reference",
    ]
    titles = {
        "sales_without_branch_id": "A. POS Sales Missing branch_id",
        "invalid_expiry_dates": "B. Invalid Expiry Dates",
        "missing_manager_user_id": "C. Missing manager_user_id",
        "payments_without_source_reference": "D. Payments Without Source Reference",
    }

    for warning_type in warning_order:
        group = [i for i in plan.items if i.warning_type == warning_type]
        if not group:
            continue
        lines.extend(["", f"## {titles[warning_type]}", ""])
        for item in group:
            lines.extend(
                [
                    f"### Row `{item.table_name}`.{item.row_id} — {item.label}",
                    "",
                    f"| Field | Value |",
                    f"|-------|-------|",
                    f"| company_key | `{item.company_key}` |",
                    f"| branch_id | `{item.branch_id or '—'}` |",
                    f"| current bad value | {item.current_value} |",
                    f"| recommended fix | {item.recommended_fix} |",
                    f"| risk level | **{item.risk_level}** |",
                    f"| auto-fix safe | **{'Yes' if item.auto_fix_safe else 'No'}** |",
                    f"| manual decision needed | **{'Yes' if item.manual_decision_needed else 'No'}** |",
                    "",
                ]
            )
            if item.notes:
                lines.extend([f"**Notes:** {item.notes}", ""])
            if item.proposed_sql:
                lines.extend(["**Proposed SQL (dry-run only):**", "", "```sql", item.proposed_sql, "```", ""])
            else:
                lines.append("**Proposed SQL:** none (no change recommended)")
                lines.append("")

    lines.extend(
        [
            "## Execution Policy",
            "",
            "- Run `python scripts/plan_migration_data_cleanup.py` to refresh the plan and JSON export.",
            "- Run `python scripts/apply_migration_data_cleanup.py --dry-run --plan reports/migration_cleanup_plan.json` to preview guarded apply.",
            "- Apply changes only with `scripts/apply_migration_data_cleanup.py --apply --confirm ...` (payment reference fix only).",
            "",
        ]
    )
    return "\n".join(lines)


def print_console_summary(plan: CleanupPlan) -> None:
    print(f"Database: {plan.db_path}")
    print(f"Rows analyzed: {len(plan.items)}")
    print(f"Safe auto-fix later: {plan.auto_safe_count}")
    print(f"Manual review: {plan.manual_count}")
    print(f"No action: {plan.no_action_count}")
    print()
    for item in plan.items:
        status = "MANUAL" if item.manual_decision_needed else ("AUTO" if item.auto_fix_safe else "NONE")
        print(f"[{status}] {item.warning_type} {item.table_name}#{item.row_id} — {item.recommended_fix}")
        if item.proposed_sql:
            print(item.proposed_sql)
            print()


def update_integrity_summary(plan: CleanupPlan, summary_path: Path) -> None:
    if not summary_path.exists():
        return
    text = summary_path.read_text(encoding="utf-8")
    marker = "## Go / No-Go"
    section = (
        "## Cleanup Readiness (Phase 5B.3)\n\n"
        f"**Plan generated:** {plan.generated_at}\n\n"
        f"- Warning rows analyzed: **{len(plan.items)}**\n"
        f"- Safe to auto-fix later: **{plan.auto_safe_count}**\n"
        f"- Manual decision required: **{plan.manual_count}**\n"
        f"- No action needed (false positive / already valid): **{plan.no_action_count}**\n\n"
        "Detailed row-level plan: `reports/migration_cleanup_plan.md`\n\n"
    )
    if plan.manual_count > 0:
        section += "**Migration status after cleanup planning:** remains **GO WITH WARNINGS** until manual items are resolved.\n\n"
    else:
        section += "**Migration status after cleanup planning:** safe auto-fixes available; may reach **GO** after apply phase.\n\n"

    if marker in text:
        if "## Cleanup Readiness (Phase 5B.3)" in text:
            start = text.index("## Cleanup Readiness (Phase 5B.3)")
            end = text.index(marker, start)
            text = text[:start] + section + text[end:]
        else:
            text = text.replace(marker, section + marker)
        summary_path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migration data cleanup planner (read-only by default).")
    parser.add_argument(
        "--db",
        default=os.environ.get("EKA_AUDIT_DB_PATH", str(DEFAULT_DB_PATH)),
        help="Path to SQLite database (read-only URI connection).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reserved for future guarded apply mode (NOT implemented in Phase 5B.3).",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip writing reports/migration_cleanup_plan.md",
    )
    parser.add_argument(
        "--skip-summary-update",
        action="store_true",
        help="Do not append cleanup readiness to migration_integrity_summary.md",
    )
    args = parser.parse_args(argv)

    if args.apply:
        print(
            "ERROR: This planner is read-only. Use scripts/apply_migration_data_cleanup.py for guarded apply.",
            file=sys.stderr,
        )
        return 2

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    plan = build_cleanup_plan(db_path)
    print_console_summary(plan)

    if not args.no_report:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "migration_cleanup_plan.md"
        report_path.write_text(render_markdown(plan), encoding="utf-8")
        json_path = REPORTS_DIR / "migration_cleanup_plan.json"
        write_cleanup_plan_json(plan, json_path)
        print(f"Wrote {report_path}")
        print(f"Wrote {json_path}")

    if not args.skip_summary_update:
        update_integrity_summary(plan, REPORTS_DIR / "migration_integrity_summary.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
