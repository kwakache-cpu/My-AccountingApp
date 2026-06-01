#!/usr/bin/env python3
"""
Read-only PostgreSQL schema compatibility audit (Phase 5B.6).
Generates reports under reports/ — no DB writes, no backend switch.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "eka_enterprise_v3.db"

SCAN_FILES = (
    REPO_ROOT / "database.py",
    REPO_ROOT / "modules.py",
    REPO_ROOT / "financials.py",
    REPO_ROOT / "app.py",
    REPO_ROOT / "accounting_engine.py",
)

SQLITE_FEATURE_PATTERNS = {
    "AUTOINCREMENT": re.compile(r"\bAUTOINCREMENT\b", re.I),
    "lastrowid": re.compile(r"\blastrowid\b"),
    "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.I),
    "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.I),
    "PRAGMA": re.compile(r"\bPRAGMA\b", re.I),
    "sqlite_master": re.compile(r"\bsqlite_master\b"),
    "BEGIN IMMEDIATE": re.compile(r"\bBEGIN\s+IMMEDIATE\b", re.I),
    "busy_timeout": re.compile(r"\bbusy_timeout\b", re.I),
    "journal_mode": re.compile(r"\bjournal_mode\b", re.I),
    "WAL": re.compile(r"\bWAL\b"),
    "GLOB": re.compile(r"\bGLOB\b"),
    "ROWID": re.compile(r"\bROWID\b", re.I),
    "sqlite_sequence": re.compile(r"\bsqlite_sequence\b"),
}

QUERY_PATTERNS = {
    "sqlite_placeholder_question": re.compile(r'execute\s*\([^)]*\?'),
    "postgres_placeholder_percent": re.compile(r"execute\s*\([^)]*%s"),
    "insert_or_ignore": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.I),
    "insert_or_replace": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.I),
    "on_conflict": re.compile(r"\bON\s+CONFLICT\b", re.I),
    "returning_clause": re.compile(r"\bRETURNING\b", re.I),
    "datetime_now_utc": re.compile(r"datetime\.(utcnow|now)"),
    "integer_boolean": re.compile(r"(is_active|is_voided|is_locked)\s*=\s*[01]\b"),
    "date_glob": re.compile(r"\bGLOB\s+['\"]"),
}

WRITE_PATH_HINTS = {
    "POS finalization": [
        (r"def finalize_pos_sale", "modules.py"),
        (r"def _persist_pos_sale", "modules.py"),
        (r"INSERT INTO pos_sales", "modules.py"),
        (r"post_accounting_impact.*POS", "modules.py"),
    ],
    "Invoice posting": [
        (r"def save_invoice", "modules.py"),
        (r"post_accounting_impact", "accounting_engine.py"),
        (r"INSERT INTO invoices", "modules.py"),
    ],
    "Bill posting": [
        (r"INSERT INTO bills", "modules.py"),
        (r"def save_bill", "modules.py"),
    ],
    "Payments": [
        (r"INSERT INTO payments", "modules.py"),
        (r"payment_cursor\.lastrowid", "modules.py"),
        (r"apply_payment_reference_fix", "migration_cleanup.py"),
    ],
    "Inventory movements": [
        (r"INSERT INTO stock_movements", "modules.py"),
        (r"def record_stock_movement", "modules.py"),
    ],
    "Stock adjustments": [
        (r"UPDATE inventory SET qty", "modules.py"),
        (r"stock_movement", "modules.py"),
    ],
    "Payroll posting": [
        (r"INSERT INTO payroll", "modules.py"),
        (r"payroll_cursor\.lastrowid", "modules.py"),
    ],
    "Depreciation": [
        (r"depreciat", "modules.py"),
        (r"fixed_assets", "modules.py"),
    ],
    "Year-end close": [
        (r"close_period|set_period_status", "modules.py"),
        (r"accounting_periods", "modules.py"),
    ],
    "Branch creation": [
        (r"def create_company_branch", "database.py"),
        (r"INSERT INTO branches", "database.py"),
    ],
    "User creation": [
        (r"def create_branch_scoped_user", "database.py"),
        (r"INSERT INTO users", "database.py"),
    ],
}


@dataclass
class TableInfo:
    name: str
    row_count: int = 0
    create_sql: str = ""
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[dict] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    sqlite_only: list[str] = field(default_factory=list)


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _scan_file_patterns(path: Path, patterns: dict[str, re.Pattern]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = defaultdict(list)
    if not path.exists():
        return hits
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return hits
    rel = path.relative_to(REPO_ROOT).as_posix()
    for line_no, line in enumerate(lines, start=1):
        for name, pattern in patterns.items():
            if pattern.search(line):
                hits[name].append(f"{rel}:{line_no}: {line.strip()[:120]}")
    return hits


def _scan_repo_py(patterns: dict[str, re.Pattern]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = defaultdict(list)
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if "node_modules" in path.parts or ".test-tmp" in path.parts or "__pycache__" in path.parts:
            continue
        for name, items in _scan_file_patterns(path, patterns).items():
            merged[name].extend(items)
    return merged


def _inventory_schema(conn: sqlite3.Connection) -> list[TableInfo]:
    tables = [
        row[0]
        for row in conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]
    result: list[TableInfo] = []
    for name in tables:
        info = TableInfo(name=name)
        try:
            info.row_count = int(conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0])
        except sqlite3.Error:
            info.row_count = -1
        create_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,),
        ).fetchone()
        info.create_sql = (create_row[0] or "") if create_row else ""
        if "AUTOINCREMENT" in info.create_sql.upper():
            info.sqlite_only.append("AUTOINCREMENT on PK")
        if "WITHOUT ROWID" in info.create_sql.upper():
            info.sqlite_only.append("WITHOUT ROWID")
        pk_rows = conn.execute(f"PRAGMA table_info({name})").fetchall()
        info.primary_key = [row[1] for row in pk_rows if row[5]]
        for fk in conn.execute(f"PRAGMA foreign_key_list({name})").fetchall():
            info.foreign_keys.append(
                {
                    "from": fk[3],
                    "to_table": fk[2],
                    "to_column": fk[4],
                    "on_update": fk[5],
                    "on_delete": fk[6],
                }
            )
        for idx in conn.execute(f"PRAGMA index_list({name})").fetchall():
            idx_name = idx[1]
            if idx_name and not idx_name.startswith("sqlite_autoindex"):
                info.indexes.append(idx_name)
        for trg in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
            (name,),
        ).fetchall():
            info.triggers.append(trg[0] or trg["name"])
        result.append(info)
    return result


def _fk_orphan_checks(conn: sqlite3.Connection, tables: list[TableInfo]) -> list[dict]:
    checks = []
    for table in tables:
        for fk in table.foreign_keys:
            child_table = table.name
            child_col = fk["from"]
            parent_table = fk["to_table"]
            parent_col = fk["to_column"] or "id"
            try:
                orphan_count = conn.execute(
                    f"""
                    SELECT COUNT(*) FROM [{child_table}] c
                    LEFT JOIN [{parent_table}] p ON p.[{parent_col}] = c.[{child_col}]
                    WHERE c.[{child_col}] IS NOT NULL AND p.[{parent_col}] IS NULL
                    """
                ).fetchone()[0]
            except sqlite3.Error as exc:
                checks.append(
                    {
                        "child": child_table,
                        "parent": parent_table,
                        "column": child_col,
                        "orphans": f"ERROR: {exc}",
                        "risk": "MEDIUM",
                    }
                )
                continue
            risk = "HIGH" if int(orphan_count or 0) > 0 else "LOW"
            checks.append(
                {
                    "child": child_table,
                    "parent": parent_table,
                    "column": child_col,
                    "orphans": int(orphan_count or 0),
                    "risk": risk,
                }
            )
    return checks


def _find_write_paths() -> dict[str, list[str]]:
    paths: dict[str, list[str]] = {}
    for category, hints in WRITE_PATH_HINTS.items():
        found: list[str] = []
        for pattern, preferred in hints:
            rx = re.compile(pattern, re.I)
            scan_paths = list(SCAN_FILES) + [
                REPO_ROOT / "accounting_engine.py",
                REPO_ROOT / "migration_cleanup.py",
            ]
            for path in scan_paths:
                if not path.exists():
                    continue
                if preferred and preferred not in path.name:
                    continue
                for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        found.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{line_no}")
                        break
            if not found:
                for path in sorted(REPO_ROOT.rglob("*.py")):
                    if "__pycache__" in path.parts:
                        continue
                    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if rx.search(line):
                            found.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{line_no}")
                            break
                    if found:
                        break
        paths[category] = sorted(set(found))
    return paths


def _score_risks(
    tables: list[TableInfo],
    sqlite_features: dict[str, list[str]],
    query_hits: dict[str, list[str]],
    orphans: list[dict],
) -> dict[str, list[str]]:
    blockers: list[str] = []
    high: list[str] = []
    medium: list[str] = []
    low: list[str] = []

    q_count = sum(1 for v in sqlite_features.get("lastrowid", []) if "database.py" not in v or True)
    lastrowid_hits = len(sqlite_features.get("lastrowid", []))
    pragma_hits = len(sqlite_features.get("PRAGMA", []))
    sqlite_master_hits = len(sqlite_features.get("sqlite_master", []))
    autoinc_tables = sum(1 for t in tables if any("AUTOINCREMENT" in s for s in t.sqlite_only))

    if lastrowid_hits > 20:
        blockers.append(f"Widespread cursor.lastrowid usage ({lastrowid_hits} references) — requires RETURNING migration")
    if pragma_hits > 50:
        high.append(f"PRAGMA usage ({pragma_hits} refs) — schema introspection must use information_schema on Postgres")
    if sqlite_master_hits > 30:
        high.append(f"sqlite_master queries ({sqlite_master_hits} refs) — replace with information_schema / pg_catalog")
    orphan_high = [o for o in orphans if o.get("risk") == "HIGH" and isinstance(o.get("orphans"), int) and o["orphans"] > 0]
    if orphan_high:
        high.append(f"FK orphan rows detected on {len(orphan_high)} relationships before migration")
    if autoinc_tables > 0:
        medium.append(f"{autoinc_tables} tables use AUTOINCREMENT — map to SERIAL/IDENTITY in Postgres DDL")
    if len(sqlite_features.get("INSERT OR IGNORE", [])) > 5:
        medium.append("INSERT OR IGNORE — partially covered by db_insert_ignore_sql(); audit all call sites")
    if len(sqlite_features.get("GLOB", [])) > 3:
        low.append("GLOB patterns — use Postgres ~ or SIMILAR TO / regex")
    if len(query_hits.get("sqlite_placeholder_question", [])) > 100:
        blockers.append("Thousands of ? placeholders in hot paths — need %s routing via db_param_placeholder()")
    if not any("insert_returning_id_sql" in str(REPO_ROOT / "database.py") for _ in [0]):
        pass
    medium.append("Dual reporting (financials.py vs accounting_engine) — verify branch filters on Postgres")
    low.append("INTEGER booleans (0/1) — use db_boolean_value() or native BOOLEAN")

    return {
        "blockers": blockers,
        "high": high,
        "medium": medium,
        "low": low,
    }


def render_schema_report(tables: list[TableInfo], db_path: Path, audited_at: str) -> str:
    lines = [
        "# PostgreSQL Schema Compatibility",
        "",
        f"**Audited at:** {audited_at}",
        f"**Database:** `{db_path}`",
        f"**Tables:** {len(tables)}",
        "",
        "## Summary",
        "",
        f"- Total tables: **{len(tables)}**",
        f"- Total rows (sum): **{sum(max(t.row_count, 0) for t in tables):,}**",
        f"- Tables with AUTOINCREMENT: **{sum(1 for t in tables if any('AUTOINCREMENT' in s for s in t.sqlite_only))}**",
        f"- Tables with triggers: **{sum(1 for t in tables if t.triggers)}**",
        "",
        "## Table Inventory",
        "",
        "| Table | Rows | Primary Key | FKs | Indexes | Triggers | SQLite-only |",
        "|-------|-----:|-------------|----:|--------:|---------:|-------------|",
    ]
    for t in tables:
        pk = ", ".join(t.primary_key) or "—"
        fks = len(t.foreign_keys)
        idx = len(t.indexes)
        trg = len(t.triggers)
        so = "; ".join(t.sqlite_only) if t.sqlite_only else "—"
        lines.append(f"| `{t.name}` | {t.row_count:,} | {pk} | {fks} | {idx} | {trg} | {so} |")
    lines.extend(["", "## Per-Table Detail", ""])
    for t in tables:
        lines.extend([f"### `{t.name}`", "", f"- **Row count:** {t.row_count:,}", f"- **Primary key:** {', '.join(t.primary_key) or 'none'}", ""])
        if t.foreign_keys:
            lines.append("**Foreign keys:**")
            for fk in t.foreign_keys:
                lines.append(f"- `{fk['from']}` → `{fk['to_table']}.{fk['to_column']}` (on_delete={fk['on_delete']})")
            lines.append("")
        if t.indexes:
            lines.append(f"**Indexes:** {', '.join(f'`{i}`' for i in t.indexes)}")
            lines.append("")
        if t.triggers:
            lines.append(f"**Triggers:** {', '.join(t.triggers)}")
            lines.append("")
        if t.create_sql:
            lines.extend(["```sql", t.create_sql[:2000], "```", ""])
    return "\n".join(lines)


def render_sqlite_features_report(features: dict[str, list[str]], audited_at: str) -> str:
    lines = [
        "# SQLite-Specific Features (Code Scan)",
        "",
        f"**Audited at:** {audited_at}",
        "",
        "Repository-wide scan of `*.py` (excluding `__pycache__`, `.test-tmp`).",
        "",
    ]
    for name, items in sorted(features.items(), key=lambda x: -len(x[1])):
        lines.extend([f"## {name} ({len(items)} occurrences)", ""])
        if not items:
            lines.append("_None found._")
        else:
            for item in items[:40]:
                lines.append(f"- `{item}`")
            if len(items) > 40:
                lines.append(f"- _… and {len(items) - 40} more_")
        lines.append("")
    return "\n".join(lines)


def render_query_compat_report(file_hits: dict[str, dict[str, list[str]]], audited_at: str) -> str:
    lines = [
        "# Query Compatibility Scan",
        "",
        f"**Audited at:** {audited_at}",
        "",
        "Scoped files: `database.py`, `modules.py`, `financials.py`, `app.py`, `accounting_engine.py`.",
        "",
        "## Placeholder & Dialect Notes",
        "",
        "- `database.db_param_placeholder()` returns `?` (SQLite) or `%s` (Postgres) when backend routing is active.",
        "- `insert_returning_id_sql`, `fetch_inserted_row_id`, `db_insert_ignore_sql` exist in `database.py` (Phase 5B.1).",
        "- Most application SQL still uses literal `?` — full migration requires systematic placeholder pass.",
        "",
    ]
    for path_key, hits in file_hits.items():
        lines.extend([f"## `{path_key}`", ""])
        for name, items in sorted(hits.items(), key=lambda x: -len(x[1])):
            lines.append(f"### {name} ({len(items)})")
            for item in items[:25]:
                lines.append(f"- `{item}`")
            if len(items) > 25:
                lines.append(f"- _… {len(items) - 25} more_")
            lines.append("")
    return "\n".join(lines)


def render_fk_report(orphans: list[dict], tables: list[TableInfo], audited_at: str) -> str:
    lines = [
        "# PostgreSQL FK Readiness",
        "",
        f"**Audited at:** {audited_at}",
        "",
        "Read-only orphan checks: child FK column populated but no matching parent row.",
        "",
        "## Orphan Summary",
        "",
        "| Child | Parent | Column | Orphans | Risk |",
        "|-------|--------|--------|--------:|------|",
    ]
    for o in sorted(orphans, key=lambda x: (-(x["orphans"] if isinstance(x["orphans"], int) else 0), x["child"])):
        lines.append(
            f"| `{o['child']}` | `{o['parent']}` | `{o['column']}` | {o['orphans']} | {o['risk']} |"
        )
    missing_idx = []
    for t in tables:
        for fk in t.foreign_keys:
            col = fk["from"]
            if not any(col in idx for idx in t.indexes):
                missing_idx.append(f"{t.name}.{col} → {fk['to_table']}")
    lines.extend(["", "## Missing FK Indexes (heuristic)", ""])
    if missing_idx:
        for item in missing_idx[:50]:
            lines.append(f"- `{item}`")
    else:
        lines.append("- No obvious unindexed FK columns detected (named indexes may still cover columns).")
    lines.extend(
        [
            "",
            "## Circular / Ordering Notes",
            "",
            "- `companies` ← `branches`, `users`, most transactional tables.",
            "- `journal_entries` ↔ `journal_lines` (lines depend on entries).",
            "- `pos_sales` → `pos_sale_lines`; payments may reference invoices/bills/customers.",
            "- Enable `FOREIGN KEY` enforcement in Postgres; load order: parents before children.",
            "",
        ]
    )
    return "\n".join(lines)


def render_write_paths_report(paths: dict[str, list[str]], audited_at: str) -> str:
    lines = [
        "# PostgreSQL Write Path Inventory",
        "",
        f"**Audited at:** {audited_at}",
        "",
        "Critical write paths that must use transactions + identity retrieval on Postgres.",
        "",
    ]
    for category, locs in paths.items():
        lines.extend([f"## {category}", ""])
        if locs:
            for loc in locs:
                lines.append(f"- `{loc}`")
        else:
            lines.append("- _No direct match — review manually._")
        lines.append("")
    lines.extend(
        [
            "## Postgres Requirements per Path",
            "",
            "- Use `execute_db_write_transaction()` or equivalent single-connection transactions.",
            "- Replace `lastrowid` with `fetch_inserted_row_id()` after `insert_returning_id_sql()`.",
            "- Avoid `PRAGMA` / `sqlite_master` in write paths.",
            "- POS/inventory: preserve row-level locking strategy (Postgres `SELECT FOR UPDATE` where needed).",
            "",
        ]
    )
    return "\n".join(lines)


def render_readiness_report(
    scores: dict[str, list[str]],
    tables: list[TableInfo],
    audited_at: str,
) -> tuple[str, str]:
    overall = "RED" if scores["blockers"] else ("YELLOW" if scores["high"] or scores["medium"] else "GREEN")
    rec = "NO-GO" if overall == "RED" else ("GO WITH CONDITIONS" if overall == "YELLOW" else "GO")
    lines = [
        "# PostgreSQL Migration Readiness",
        "",
        f"**Audited at:** {audited_at}",
        f"**Overall grade:** **{overall}**",
        f"**Recommendation:** **{rec}**",
        "",
        f"- Tables inventoried: {len(tables)}",
        "",
        "## Blockers",
        "",
    ]
    for item in scores["blockers"] or ["None identified by automated scan."]:
        lines.append(f"- {item}")
    lines.extend(["", "## High Risk", ""])
    for item in scores["high"] or ["None."]:
        lines.append(f"- {item}")
    lines.extend(["", "## Medium Risk", ""])
    for item in scores["medium"] or ["None."]:
        lines.append(f"- {item}")
    lines.extend(["", "## Low Risk", ""])
    for item in scores["low"] or ["None."]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Migration Recommendation",
            "",
            "1. Complete Phase 5B data cleanup on SQLite (POS branch_id, managers, payment reference).",
            "2. Finish placeholder + `lastrowid` migration on critical write paths using existing `database.py` helpers.",
            "3. Generate Postgres DDL from SQLite schema (AUTOINCREMENT → GENERATED BY DEFAULT AS IDENTITY).",
            "4. Run read-only FK orphan remediation on SQLite before cutover.",
            "5. Enable `DB_BACKEND=postgres`, `DATABASE_URL`, `ERP_ENABLE_POSTGRES_RUNTIME=1` only in staging first.",
            "6. Do **not** switch production `DB_BACKEND` until regression + concurrency tests pass on Postgres.",
            "",
            "**Do not migrate data in this phase.**",
            "",
        ]
    )
    return "\n".join(lines), overall


def main() -> int:
    db_path = Path(os.environ.get("EKA_AUDIT_DB_PATH", DEFAULT_DB_PATH))
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1
    audited_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    conn = _connect_readonly(db_path)
    try:
        tables = _inventory_schema(conn)
        orphans = _fk_orphan_checks(conn, tables)
    finally:
        conn.close()

    sqlite_features = _scan_repo_py(SQLITE_FEATURE_PATTERNS)
    file_hits = {
        p.relative_to(REPO_ROOT).as_posix(): _scan_file_patterns(p, QUERY_PATTERNS) for p in SCAN_FILES if p.exists()
    }
    write_paths = _find_write_paths()
    scores = _score_risks(tables, sqlite_features, {k: v for fh in file_hits.values() for k, v in fh.items()}, orphans)

    q_total = 0
    for p in SCAN_FILES:
        if p.exists():
            q_total += p.read_text(encoding="utf-8", errors="replace").count("?")
    if q_total > 500:
        if not any("placeholder" in b for b in scores["blockers"]):
            scores["blockers"].append(f"~{q_total} `?` characters in core modules — requires db_param_placeholder() rollout")

    schema_md = render_schema_report(tables, db_path, audited_at)
    features_section = render_sqlite_features_report(sqlite_features, audited_at)
    query_section = render_query_compat_report(file_hits, audited_at)
    fk_md = render_fk_report(orphans, tables, audited_at)
    write_md = render_write_paths_report(write_paths, audited_at)
    readiness_md, overall = render_readiness_report(scores, tables, audited_at)

    # Merge features into schema report appendix
    schema_path = REPORTS_DIR / "postgres_schema_compatibility.md"
    schema_path.write_text(
        schema_md + "\n\n---\n\n" + features_section + "\n\n---\n\n" + query_section,
        encoding="utf-8",
    )
    (REPORTS_DIR / "postgres_fk_readiness.md").write_text(fk_md, encoding="utf-8")
    (REPORTS_DIR / "postgres_write_paths.md").write_text(write_md, encoding="utf-8")
    (REPORTS_DIR / "postgres_migration_readiness.md").write_text(readiness_md, encoding="utf-8")

    print(f"Wrote {schema_path}")
    print(f"Wrote {REPORTS_DIR / 'postgres_fk_readiness.md'}")
    print(f"Wrote {REPORTS_DIR / 'postgres_write_paths.md'}")
    print(f"Wrote {REPORTS_DIR / 'postgres_migration_readiness.md'}")
    print(f"Overall grade: {overall}")
    print(f"Blockers: {len(scores['blockers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
