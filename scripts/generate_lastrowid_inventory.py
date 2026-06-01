#!/usr/bin/env python3
"""Generate reports/lastrowid_portability_inventory.md (read-only scan)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "reports" / "lastrowid_portability_inventory.md"

HIGH_RISK_HINTS = (
    "post_journal",
    "post_accounting",
    "process_pos",
    "_persist_pos",
    "pos_sale",
    "finalize_pos",
    "save_invoice",
    "invoice_cursor",
    "bill_cursor",
    "payment_cursor",
    "payment_id",
    "payment_allocation",
    "allocate_payment",
    "stock_movement",
    "movement_cursor",
    "payroll",
    "depreciation",
    "post_transaction",
    "show_accounts_payable",
    "show_create_bill",
    "show_sales_purchase",
    "show_fixed_assets",
    "show_banking",
    "_process_pos_return",
)
MEDIUM_RISK_HINTS = (
    "financials",
    "recurring_transaction",
    "payment_allocation",
    "pos_return",
)
CONVERTED_MARKERS = (
    "get_inserted_id",
    "fetch_inserted_row_id",
)


def _current_function(lines: list[str], line_no: int) -> str:
    for idx in range(line_no - 1, -1, -1):
        match = re.match(r"^\s*def\s+([a-zA-Z0-9_]+)\s*\(", lines[idx])
        if match:
            return match.group(1)
    return "<module>"


def _infer_table(snippet: str, context: str) -> str:
    insert_match = re.search(r"INSERT\s+INTO\s+([a-zA-Z0-9_]+)", snippet, re.I)
    if insert_match:
        return insert_match.group(1)
    for hint in ("pos_sales", "journal_entries", "payments", "invoices", "bills", "inventory"):
        if hint in context.lower():
            return hint
    return "unknown"


def _risk_bucket(rel_path: str, func: str, snippet: str) -> str:
    blob = f"{rel_path} {func} {snippet}".lower()
    if any(h in blob for h in HIGH_RISK_HINTS):
        return "high"
    if any(h in blob for h in MEDIUM_RISK_HINTS):
        return "medium"
    return "low"


def _safe_to_convert_now(bucket: str, snippet: str) -> str:
    if "get_inserted_id" in snippet or "fetch_inserted_row_id" in snippet:
        return "done"
    if bucket == "high":
        return "no — dedicated transaction testing required"
    if bucket == "medium":
        return "later phase"
    return "yes — use ensure_insert_sql_returning + get_inserted_id"


SKIP_DIR_PARTS = {".test-tmp", "__pycache__", "node_modules", ".venv", "venv", ".git"}


def _is_helper_implementation(rel: str, func: str, line: str) -> bool:
    if rel == "database.py" and func in {"fetch_inserted_row_id", "get_inserted_id"}:
        return True
    if "getattr(cursor, \"lastrowid\"" in line or "getattr(cursor, 'lastrowid'" in line:
        return True
    if "cursor.lastrowid after execute" in line.lower():
        return True
    return False


def scan_repo() -> list[dict]:
    entries: list[dict] = []
    pattern = re.compile(r"\blastrowid\b")
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if any(part in path.parts for part in SKIP_DIR_PARTS):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("scripts/generate_lastrowid"):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_no, line in enumerate(lines, start=1):
            if not pattern.search(line):
                continue
            if _is_helper_implementation(rel, _current_function(lines, line_no), line):
                continue
            func = _current_function(lines, line_no)
            snippet = line.strip()
            table = _infer_table(snippet, "\n".join(lines[max(0, line_no - 15) : line_no]))
            bucket = _risk_bucket(rel, func, snippet)
            entries.append(
                {
                    "file": rel,
                    "function": func,
                    "line": line_no,
                    "snippet": snippet,
                    "table": table,
                    "risk": bucket,
                    "convert_now": _safe_to_convert_now(bucket, snippet),
                }
            )
    return entries


def render_report(entries: list[dict]) -> str:
    audited_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        by_bucket[entry["risk"]].append(entry)
    app_entries = [e for e in entries if not e["file"].startswith("tests/")]
    test_entries = [e for e in entries if e["file"].startswith("tests/")]
    remaining = [e for e in app_entries if e["convert_now"] != "done"]

    lines = [
        "# lastrowid Portability Inventory",
        "",
        f"**Generated at:** {audited_at}",
        f"**Total lastrowid references (app + tests, excl. .venv):** {len(entries)}",
        f"**Application code references:** {len(app_entries)}",
        f"**Test-only references:** {len(test_entries)}",
        f"**Remaining raw lastrowid (application):** {len(remaining)}",
        "",
        "## Recommended Helper Usage",
        "",
        "```python",
        "from database import ensure_insert_sql_returning, get_inserted_id",
        "",
        "cursor = conn.execute(",
        "    ensure_insert_sql_returning('INSERT INTO my_table (...) VALUES (...)'),",
        "    params,",
        ")",
        "row_id = get_inserted_id(cursor)",
        "```",
        "",
        "PostgreSQL requires `RETURNING id` (appended by `ensure_insert_sql_returning`).",
        "SQLite continues to use `cursor.lastrowid` via `get_inserted_id()`.",
        "",
    ]
    titles = {
        "low": "Low-risk — setup / admin / contacts",
        "medium": "Medium-risk — CRUD / financials helpers",
        "high": "High-risk — accounting / POS / payments / inventory",
    }
    for bucket in ("low", "medium", "high"):
        group = by_bucket.get(bucket, [])
        lines.extend([f"## {titles[bucket]}", "", f"**Count:** {len(group)}", ""])
        if not group:
            lines.append("_None._")
            lines.append("")
            continue
        lines.append("| File | Function | Line | Table | Convert now? | Snippet |")
        lines.append("|------|----------|-----:|-------|--------------|---------|")
        for e in sorted(group, key=lambda x: (x["file"], x["line"])):
            snip = e["snippet"].replace("|", "\\|")[:80]
            lines.append(
                f"| `{e['file']}` | `{e['function']}` | {e['line']} | `{e['table']}` | {e['convert_now']} | `{snip}` |"
            )
        lines.append("")
    lines.extend(
        [
            "## Phase 5B.7 Conversions (completed)",
            "",
            "| Function | File |",
            "|----------|------|",
            "| `_create_legacy_voucher_if_enabled` | `modules.py` |",
            "| `_get_or_create_party` | `modules.py` |",
            "| `_register_customer` | `modules.py` |",
            "| `_register_supplier` | `modules.py` |",
            "| `get_or_create_account` | `accounting_engine.py` |",
            "| `create_bank_account` | `accounting_engine.py` |",
            "",
            "## Phase 5B.8 Conversions (completed)",
            "",
            "| Function | File |",
            "|----------|------|",
            "| `_party_id` | `financials.py` |",
            "| `show_invoice_manager` (invoice + bill saves) | `financials.py` |",
            "| `show_create_invoice_page` | `financials.py` |",
            "| `schedule_recurring_transaction` | `accounting_engine.py` |",
            "",
            "## Phase 5B.9 — High-risk conversion plan",
            "",
            "See [high_risk_identity_conversion_plan.md](high_risk_identity_conversion_plan.md) for phased conversion order (5B.10A–5B.10G).",
            "",
            "## Phase 5B.10A Conversions (completed)",
            "",
            "| Function | File |",
            "|----------|------|",
            "| `_insert_stock_movement_record` | `modules.py` |",
            "",
            "## Phase 5B.10B Conversions (completed)",
            "",
            "| Function | File |",
            "|----------|------|",
            "| `show_accounts_payable_page` | `modules.py` |",
            "| `show_create_bill_page` | `modules.py` |",
            "| `show_sales_purchase` (Purchase / bill branch only) | `modules.py` |",
            "",
            "## Phase 5B.10C Conversions (completed)",
            "",
            "| Function | File |",
            "|----------|------|",
            "| `allocate_payment` | `accounting_engine.py` |",
            "| `show_banking` | `modules.py` |",
            "| `show_invoice_manager` (Payments tab) | `financials.py` |",
            "| `show_receive_payment_page` | `financials.py` |",
            "| `show_supplier_payment_page` | `financials.py` |",
            "",
            "Details: [payments_identity_conversion_5b10c.md](payments_identity_conversion_5b10c.md)",
            "",
            "## Phase 5B.10D Conversions (completed)",
            "",
            "| Function | File |",
            "|----------|------|",
            "| `show_payroll` | `modules.py` |",
            "| `show_fixed_assets` (acquisition insert) | `modules.py` |",
            "",
            "## Phase 5B.10E Conversions (completed)",
            "",
            "| Function | File |",
            "|----------|------|",
            "| `_process_pos_return` (`pos_returns` insert only) | `modules.py` |",
            "",
            "## Phase 5B.10F Conversions (completed)",
            "",
            "| Function | File |",
            "|----------|------|",
            "| `_persist_pos_sale` (`pos_sales` insert only) | `modules.py` |",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    entries = scan_repo()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(entries), encoding="utf-8")
    remaining = sum(1 for e in entries if e["convert_now"] != "done")
    print(f"Wrote {REPORT_PATH}")
    print(f"Total lastrowid: {len(entries)}")
    print(f"Remaining raw lastrowid: {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
