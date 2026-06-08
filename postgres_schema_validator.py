"""Offline validation for generated PostgreSQL schema artifacts.

This module reads generated SQL and markdown inventory artifacts only. It does
not connect to any database and does not execute schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA_SQL = REPO_ROOT / "reports" / "postgres_generated_schema.sql"
DEFAULT_SCHEMA_SUMMARY = REPO_ROOT / "reports" / "postgres_generated_schema_summary.md"
DEFAULT_COMPATIBILITY_REPORT = REPO_ROOT / "reports" / "postgres_schema_compatibility.md"
DEFAULT_FK_READINESS_REPORT = REPO_ROOT / "reports" / "postgres_fk_readiness.md"
DEFAULT_DEPLOYMENT_PLAN = REPO_ROOT / "reports" / "postgres_schema_deployment_plan.md"
DEFAULT_VALIDATION_REPORT = REPO_ROOT / "reports" / "postgres_schema_validation_report.md"

REQUIRED_CORE_TABLES = {
    "companies",
    "branches",
    "users",
    "chart_of_accounts",
    "customers",
    "suppliers",
    "inventory",
    "journal_entries",
    "journal_lines",
    "pos_sales",
    "pos_sale_lines",
    "audit_logs",
    "system_settings",
    "schema_version",
}

FORBIDDEN_SQLITE_SYNTAX = (
    "AUTOINCREMENT",
    "PRAGMA",
    "sqlite_master",
    "INSERT OR IGNORE",
    "?",
    "last_insert_rowid",
)


@dataclass
class SchemaValidationResult:
    expected_table_count: int
    generated_table_count: int
    tables_found: list[str]
    missing_required_tables: list[str]
    tables_missing_primary_key: list[str]
    index_count: int
    foreign_key_count: int
    unsupported_construct_count: int
    manual_review_count: int
    dependency_cycle_count: int
    dependency_ordering_applied: str
    forbidden_syntax_found: list[str]
    validation_score: int
    deployment_readiness: str
    recommended_next_phase: str
    notes: list[str] = field(default_factory=list)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_expected_table_count(compatibility_text: str) -> int:
    match = re.search(r"\*\*Tables:\*\*\s*(\d+)", compatibility_text)
    if match:
        return int(match.group(1))
    match = re.search(r"Total tables:\s*\*\*(\d+)\*\*", compatibility_text)
    if match:
        return int(match.group(1))
    return 0


def parse_inventory_tables(compatibility_text: str) -> list[str]:
    tables = re.findall(r"^\| `([^`]+)` \|", compatibility_text, flags=re.MULTILINE)
    return sorted(set(tables))


def parse_generated_tables(schema_sql: str) -> list[str]:
    tables = re.findall(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b",
        schema_sql,
        flags=re.IGNORECASE,
    )
    return sorted(set(tables))


def _extract_create_table_blocks(schema_sql: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    pattern = re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b(.*?);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(schema_sql):
        blocks[match.group(1)] = match.group(0)
    return blocks


def find_tables_missing_primary_key(schema_sql: str) -> list[str]:
    missing: list[str] = []
    for table_name, block in _extract_create_table_blocks(schema_sql).items():
        if not re.search(r"\bPRIMARY\s+KEY\b", block, flags=re.IGNORECASE):
            missing.append(table_name)
    return sorted(missing)


def count_indexes(schema_sql: str) -> int:
    create_indexes = re.findall(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", schema_sql, flags=re.IGNORECASE)
    captured_index_comments = re.findall(r"^-- INDEX\s+[A-Za-z_][A-Za-z0-9_]*\s+ON\s+", schema_sql, flags=re.MULTILINE)
    return len(create_indexes) + len(captured_index_comments)


def count_foreign_keys(schema_sql: str) -> int:
    return len(re.findall(r"\bFOREIGN\s+KEY\b", schema_sql, flags=re.IGNORECASE))


def parse_summary_count(summary_text: str, label: str) -> int:
    match = re.search(rf"- {re.escape(label)}:\s*(\d+)", summary_text)
    return int(match.group(1)) if match else 0


def find_forbidden_sqlite_syntax(schema_sql: str) -> list[str]:
    found: list[str] = []
    for syntax in FORBIDDEN_SQLITE_SYNTAX:
        if syntax == "?":
            if "?" in schema_sql:
                found.append("?")
            continue
        if re.search(re.escape(syntax), schema_sql, flags=re.IGNORECASE):
            found.append(syntax)
    return found


def _score_validation(
    expected_table_count: int,
    generated_table_count: int,
    missing_required_tables: list[str],
    tables_missing_primary_key: list[str],
    index_count: int,
    foreign_key_count: int,
    unsupported_construct_count: int,
    manual_review_count: int,
    forbidden_syntax_found: list[str],
) -> tuple[int, str]:
    score = 100
    if expected_table_count != generated_table_count:
        score -= 25
    score -= min(len(missing_required_tables) * 10, 30)
    score -= min(len(tables_missing_primary_key) * 5, 25)
    if index_count == 0:
        score -= 10
    if foreign_key_count == 0:
        score -= 10
    score -= min(len(forbidden_syntax_found) * 15, 45)
    if unsupported_construct_count > 0:
        score -= 5
    if manual_review_count > 0:
        score -= 5
    score = max(score, 0)

    if forbidden_syntax_found or missing_required_tables or expected_table_count != generated_table_count:
        readiness = "RED"
    elif tables_missing_primary_key or unsupported_construct_count > 0 or manual_review_count > 0:
        readiness = "YELLOW"
    else:
        readiness = "GREEN"
    return score, readiness


def validate_postgres_schema_artifacts(
    schema_sql_path: Path = DEFAULT_SCHEMA_SQL,
    schema_summary_path: Path = DEFAULT_SCHEMA_SUMMARY,
    compatibility_report_path: Path = DEFAULT_COMPATIBILITY_REPORT,
    fk_readiness_report_path: Path = DEFAULT_FK_READINESS_REPORT,
    deployment_plan_path: Path = DEFAULT_DEPLOYMENT_PLAN,
) -> SchemaValidationResult:
    schema_sql = _read_text(schema_sql_path)
    summary_text = _read_text(schema_summary_path)
    compatibility_text = _read_text(compatibility_report_path)

    # These inputs are read to ensure the validation is anchored to the full
    # Phase 5B.13F artifact set, even though count checks come from SQL/summary.
    notes: list[str] = []
    for path in (fk_readiness_report_path, deployment_plan_path):
        if path.exists():
            _read_text(path)
        else:
            notes.append(f"Input report missing: {path.name}")

    expected_table_count = parse_expected_table_count(compatibility_text)
    inventory_tables = set(parse_inventory_tables(compatibility_text))
    generated_tables = parse_generated_tables(schema_sql)
    generated_table_set = set(generated_tables)
    missing_inventory_tables = sorted(inventory_tables - generated_table_set)
    missing_required_tables = sorted(REQUIRED_CORE_TABLES - generated_table_set)
    tables_missing_primary_key = find_tables_missing_primary_key(schema_sql)
    index_count = count_indexes(schema_sql)
    foreign_key_count = count_foreign_keys(schema_sql)
    unsupported_construct_count = parse_summary_count(summary_text, "Unsupported constructs")
    manual_review_count = parse_summary_count(summary_text, "Manual review items")
    dependency_cycle_count = parse_summary_count(summary_text, "Dependency cycles")
    ordering_match = re.search(r"- Dependency ordering applied:\s*(.+)", summary_text)
    dependency_ordering_applied = ordering_match.group(1).strip() if ordering_match else "UNKNOWN"
    forbidden_syntax_found = find_forbidden_sqlite_syntax(schema_sql)

    if missing_inventory_tables:
        notes.append("Missing inventory tables: " + ", ".join(missing_inventory_tables))

    validation_score, readiness = _score_validation(
        expected_table_count=expected_table_count,
        generated_table_count=len(generated_tables),
        missing_required_tables=missing_required_tables,
        tables_missing_primary_key=tables_missing_primary_key,
        index_count=index_count,
        foreign_key_count=foreign_key_count,
        unsupported_construct_count=unsupported_construct_count,
        manual_review_count=manual_review_count,
        forbidden_syntax_found=forbidden_syntax_found,
    )

    return SchemaValidationResult(
        expected_table_count=expected_table_count,
        generated_table_count=len(generated_tables),
        tables_found=generated_tables,
        missing_required_tables=missing_required_tables,
        tables_missing_primary_key=tables_missing_primary_key,
        index_count=index_count,
        foreign_key_count=foreign_key_count,
        unsupported_construct_count=unsupported_construct_count,
        manual_review_count=manual_review_count,
        dependency_cycle_count=dependency_cycle_count,
        dependency_ordering_applied=dependency_ordering_applied,
        forbidden_syntax_found=forbidden_syntax_found,
        validation_score=validation_score,
        deployment_readiness=readiness,
        recommended_next_phase=(
            "Phase 5B.13G - review generated DDL gaps, replace index placeholders with real "
            "PostgreSQL index definitions, and prepare a staging-only schema deployer design."
        ),
        notes=notes,
    )


def render_validation_report(result: SchemaValidationResult) -> str:
    missing_required = result.missing_required_tables or ["None"]
    missing_pk = result.tables_missing_primary_key or ["None"]
    forbidden = result.forbidden_syntax_found or ["None"]
    notes = result.notes or ["All inventory tables are represented in the generated SQL."]
    lines = [
        "# PostgreSQL Schema Validation Report",
        "",
        "Phase: 5B.13F",
        "",
        "Validated offline from generated SQL and markdown reports. No database connection, schema deployment, Supabase call, or data migration was attempted.",
        "",
        "## Validation Score",
        "",
        f"- Score: {result.validation_score}/100",
        f"- Deployment readiness: **{result.deployment_readiness}**",
        f"- Recommended next phase: {result.recommended_next_phase}",
        "",
        "## Coverage",
        "",
        f"- Expected SQLite table count: {result.expected_table_count}",
        f"- Generated PostgreSQL table count: {result.generated_table_count}",
        f"- Index count: {result.index_count}",
        f"- FK count: {result.foreign_key_count}",
        f"- Unsupported construct count: {result.unsupported_construct_count}",
        f"- Manual review count: {result.manual_review_count}",
        f"- Dependency cycle count: {result.dependency_cycle_count}",
        f"- Dependency ordering applied: {result.dependency_ordering_applied}",
        "",
        "## Missing Required Tables",
        "",
    ]
    lines.extend(f"- {item}" for item in missing_required)
    lines.extend(["", "## Tables Missing Primary Key", ""])
    lines.extend(f"- {item}" for item in missing_pk)
    lines.extend(["", "## Forbidden SQLite Syntax Found", ""])
    lines.extend(f"- {item}" for item in forbidden)
    lines.extend(["", "## Tables Found", ""])
    lines.extend(f"- {table}" for table in result.tables_found)
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in notes)
    lines.append("")
    return "\n".join(lines)


def generate_postgres_schema_validation_report(
    output_path: Path = DEFAULT_VALIDATION_REPORT,
    **validation_paths: Path,
) -> SchemaValidationResult:
    result = validate_postgres_schema_artifacts(**validation_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_validation_report(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    validation = generate_postgres_schema_validation_report()
    print(
        "Validated PostgreSQL schema draft: "
        f"score={validation.validation_score}/100 readiness={validation.deployment_readiness} "
        f"tables={validation.generated_table_count}/{validation.expected_table_count} "
        f"forbidden={len(validation.forbidden_syntax_found)}"
    )
