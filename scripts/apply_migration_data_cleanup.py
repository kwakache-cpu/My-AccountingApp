#!/usr/bin/env python3
"""
Guarded migration data cleanup apply (Phase 5B.4).

Default: refuses to run without --plan and without --dry-run or --apply.
Only the safe payment reference fix may be applied, and only with --apply and --confirm.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "eka_enterprise_v3.db"
DEFAULT_PLAN_PATH = REPO_ROOT / "reports" / "migration_cleanup_plan.json"
CONFIRM_TEXT = "I_UNDERSTAND_THIS_WILL_MODIFY_THE_SQLITE_DATABASE"

try:
    from db_upgrade_safety import create_timestamped_backup

    BACKUP_HELPER_AVAILABLE = True
except ImportError:
    BACKUP_HELPER_AVAILABLE = False


def _load_plan(plan_path: Path) -> dict[str, Any]:
    if not plan_path.exists():
        raise FileNotFoundError(f"Cleanup plan not found: {plan_path}")
    return json.loads(plan_path.read_text(encoding="utf-8"))


def _payment_row(conn: sqlite3.Connection, payment_id: int, company_key: str) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT id, company_key, invoice_id, bill_id, customer_id, supplier_id, reference, payment_type, amount
        FROM payments
        WHERE id = ? AND company_key = ?
        """,
        (payment_id, company_key),
    ).fetchone()


def _payment_still_needs_fix(row: sqlite3.Row) -> bool:
    invoice_ok = row["invoice_id"] is None
    bill_ok = row["bill_id"] is None
    reference_empty = row["reference"] is None or str(row["reference"]).strip() == ""
    return invoice_ok and bill_ok and reference_empty


def _select_apply_candidates(plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = plan.get("payments_without_reference") or []
    return [
        c
        for c in candidates
        if c.get("auto_fix_safe") is True and c.get("manual_required") is False
    ]


def _build_update_sql(candidate: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    payment_id = int(candidate["id"])
    company_key = str(candidate["company_key"])
    proposed = candidate.get("proposed_values") or {}
    customer_id = proposed.get("customer_id")
    reference = str(proposed.get("reference") or "").strip()
    if customer_id is None or not reference:
        raise ValueError(f"Candidate payment {payment_id} missing proposed customer_id/reference.")
    sql = (
        "UPDATE payments SET customer_id = ?, reference = ? "
        "WHERE id = ? AND company_key = ? AND invoice_id IS NULL AND bill_id IS NULL "
        "AND (reference IS NULL OR TRIM(reference) = '')"
    )
    params = (customer_id, reference, payment_id, company_key)
    return sql, params


def _print_payment_state(label: str, row: sqlite3.Row | None) -> None:
    if row is None:
        print(f"{label}: <row not found>")
        return
    print(
        f"{label}: id={row['id']} company_key={row['company_key']} "
        f"customer_id={row['customer_id']} reference={row['reference']!r} "
        f"invoice_id={row['invoice_id']} bill_id={row['bill_id']} "
        f"type={row['payment_type']} amount={row['amount']}"
    )


def run_dry_run(db_path: Path, plan: dict[str, Any]) -> int:
    candidates = _select_apply_candidates(plan)
    if not candidates:
        print("No auto-fix-safe payment candidates in plan.")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        print(f"Database: {db_path}")
        print(f"Mode: DRY-RUN (no changes)")
        print(f"Apply-eligible payment fixes: {len(candidates)}")
        print()
        for candidate in candidates:
            payment_id = int(candidate["id"])
            company_key = str(candidate["company_key"])
            row = _payment_row(conn, payment_id, company_key)
            print(f"--- Payment #{payment_id} ({company_key}) ---")
            _print_payment_state("BEFORE (current DB)", row)
            if row is None:
                print("SKIP: row not found.")
                continue
            if not _payment_still_needs_fix(row):
                print("SKIP: row no longer matches expected bad state.")
                continue
            try:
                sql, params = _build_update_sql(candidate)
            except ValueError as exc:
                print(f"SKIP: {exc}")
                continue
            print("PROPOSED SQL:")
            print(sql)
            print("PARAMS:", params)
            proposed = candidate.get("proposed_values") or {}
            print(
                f"AFTER (expected): customer_id={proposed.get('customer_id')} "
                f"reference={proposed.get('reference')!r}"
            )
            print()
    finally:
        conn.close()
    return 0


def run_apply(db_path: Path, plan: dict[str, Any]) -> int:
    if not BACKUP_HELPER_AVAILABLE:
        print(
            "ERROR: db_upgrade_safety.create_timestamped_backup is unavailable; refusing apply.",
            file=sys.stderr,
        )
        return 2

    candidates = _select_apply_candidates(plan)
    if not candidates:
        print("No auto-fix-safe payment candidates to apply.")
        return 0
    if len(candidates) > 1:
        print(
            f"ERROR: expected at most one safe payment fix, found {len(candidates)}.",
            file=sys.stderr,
        )
        return 2

    candidate = candidates[0]
    payment_id = int(candidate["id"])
    company_key = str(candidate["company_key"])

    try:
        backup_path = create_timestamped_backup(str(db_path), reason="migration_cleanup")
    except Exception as exc:
        print(f"ERROR: backup failed: {exc}", file=sys.stderr)
        return 2
    if not backup_path:
        print("ERROR: backup helper returned no path; refusing apply.", file=sys.stderr)
        return 2

    print(f"Backup created: {backup_path}")
    print(f"Database: {db_path}")
    print("Mode: APPLY")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        before = _payment_row(conn, payment_id, company_key)
        print("--- BEFORE ---")
        _print_payment_state("payment", before)
        if before is None:
            print("ABORT: payment row not found.")
            return 1
        if not _payment_still_needs_fix(before):
            print("ABORT: payment row no longer matches expected bad state.")
            return 1

        sql, params = _build_update_sql(candidate)
        print("Executing:", sql)
        print("Params:", params)
        conn.execute("BEGIN")
        cursor = conn.execute(sql, params)
        if cursor.rowcount != 1:
            conn.execute("ROLLBACK")
            print(f"ABORT: UPDATE affected {cursor.rowcount} rows (expected 1).")
            return 1
        after = _payment_row(conn, payment_id, company_key)
        conn.execute("COMMIT")
        print("--- AFTER ---")
        _print_payment_state("payment", after)
        print("Apply completed successfully (1 transaction committed).")
    except Exception as exc:
        conn.execute("ROLLBACK")
        print(f"ERROR: apply failed, rolled back: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Guarded migration cleanup apply (dry-run by default requirement)."
    )
    parser.add_argument(
        "--plan",
        default=str(DEFAULT_PLAN_PATH),
        help="Path to migration_cleanup_plan.json (required).",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="Path to SQLite database.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed SQL and row state without modifying data.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply safe payment reference fixes (requires --confirm).",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Required exact text when using --apply: {CONFIRM_TEXT}",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not args.apply:
        print(
            "ERROR: specify --dry-run or --apply. Default mode does not modify data.",
            file=sys.stderr,
        )
        return 2

    if args.apply and args.dry_run:
        print("ERROR: --dry-run and --apply are mutually exclusive.", file=sys.stderr)
        return 2

    if args.apply:
        if args.confirm != CONFIRM_TEXT:
            print(
                f"ERROR: --apply requires --confirm {CONFIRM_TEXT!r}",
                file=sys.stderr,
            )
            return 2

    plan_path = Path(args.plan)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 1

    try:
        plan = _load_plan(plan_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not load plan: {exc}", file=sys.stderr)
        return 1

    print(f"Loaded plan: {plan_path}")
    if args.dry_run:
        return run_dry_run(db_path, plan)
    return run_apply(db_path, plan)


if __name__ == "__main__":
    raise SystemExit(main())
