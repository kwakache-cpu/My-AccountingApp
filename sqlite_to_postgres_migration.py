"""Read-only SQLite to PostgreSQL migration planning and schema review.

This module estimates migration shape and classifies schema differences only.
It does not copy rows, write to SQLite, write to PostgreSQL, enable PostgreSQL
runtime, or deploy schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import math
import re
import sqlite3
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SQLITE_DB_PATH = REPO_ROOT / "data" / "eka_enterprise_v3.db"
DEFAULT_SQLITE_SCHEMA_REPORT = REPO_ROOT / "reports" / "postgres_schema_compatibility.md"
DEFAULT_POSTGRES_SCHEMA_PATH = REPO_ROOT / "reports" / "postgres_generated_schema.sql"
DEFAULT_MIGRATION_PLAN_REPORT = REPO_ROOT / "reports" / "sqlite_postgres_migration_plan.md"
DEFAULT_MISMATCH_REVIEW_REPORT = REPO_ROOT / "reports" / "sqlite_postgres_schema_mismatch_review.md"
DEFAULT_BATCH_SIZE = 1_000
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MigrationStatus(str, Enum):
    PLANNED = "PLANNED"
    BLOCKED = "BLOCKED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"


class MismatchClassification(str, Enum):
    SAFE_TYPE_WIDENING = "SAFE_TYPE_WIDENING"
    EXPECTED_POSTGRES_IDENTITY = "EXPECTED_POSTGRES_IDENTITY"
    EXPECTED_TIMESTAMP_MAPPING = "EXPECTED_TIMESTAMP_MAPPING"
    BOOLEAN_CANDIDATE = "BOOLEAN_CANDIDATE"
    MONEY_NUMERIC_MAPPING = "MONEY_NUMERIC_MAPPING"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"
    BLOCKER = "BLOCKER"


@dataclass(frozen=True)
class ColumnDefinition:
    table: str
    column: str
    data_type: str
    default: str = ""
    nullable: bool = True
    primary_key: bool = False
    identity: bool = False
    raw_definition: str = ""


@dataclass(frozen=True)
class ForeignKeyPlan:
    table: str
    column: str
    references_table: str
    references_column: str


@dataclass
class MigrationBatch:
    table_name: str
    batch_number: int
    offset: int
    limit: int
    estimated_rows: int


@dataclass
class MigrationTablePlan:
    table_name: str
    sqlite_columns: list[str]
    postgres_columns: list[str]
    row_count_estimate: int | None
    batch_size: int
    batch_count: int
    dependencies: list[str] = field(default_factory=list)
    missing_in_postgres: list[str] = field(default_factory=list)
    missing_in_sqlite: list[str] = field(default_factory=list)
    migration_order: int = 0


@dataclass(frozen=True)
class SchemaMismatchReview:
    table: str
    column: str
    sqlite_type: str
    sqlite_default: str
    sqlite_nullable: str
    postgres_type: str
    postgres_default: str
    postgres_nullable: str
    classification: MismatchClassification
    migration_risk: str
    recommended_handling: str


@dataclass
class MigrationResult:
    status: MigrationStatus
    sqlite_table_count: int
    postgres_table_count: int
    table_plans: list[MigrationTablePlan]
    batches: list[MigrationBatch]
    fk_dependency_order: list[str]
    estimated_total_rows: int | None
    schema_mismatches: list[SchemaMismatchReview] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def quote_identifier(identifier: str) -> str:
    if not SAFE_IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Unsafe SQL identifier for migration planning: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def open_sqlite_readonly(sqlite_db_path: Path = DEFAULT_SQLITE_DB_PATH) -> sqlite3.Connection:
    uri = f"file:{sqlite_db_path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _split_sql_items(sql_fragment: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_single_quote = False
    in_double_quote = False
    index = 0
    while index < len(sql_fragment):
        char = sql_fragment[index]
        next_char = sql_fragment[index + 1] if index + 1 < len(sql_fragment) else ""
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif not in_single_quote and not in_double_quote:
            if char == "(":
                depth += 1
            elif char == ")" and depth > 0:
                depth -= 1
            elif char == "," and depth == 0:
                item = "".join(current).strip()
                if item:
                    items.append(item)
                current = []
                index += 1
                continue
        current.append(char)
        if char == "'" and next_char == "'" and in_single_quote:
            current.append(next_char)
            index += 1
        index += 1
    trailing = "".join(current).strip()
    if trailing:
        items.append(trailing)
    return items


def _extract_sqlite_sections(report_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for match in re.finditer(r"^### `([^`]+)`\s*(.*?)(?=^### `|\Z)", report_text, flags=re.MULTILINE | re.DOTALL):
        sql_match = re.search(r"```sql\s*(.*?)\s*```", match.group(2), flags=re.DOTALL)
        if sql_match:
            sections[match.group(1)] = sql_match.group(1).strip().rstrip(";")
    return sections


def _extract_postgres_blocks(schema_sql: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    pattern = re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b(.*?);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(schema_sql):
        blocks[match.group(1)] = match.group(0)
    return blocks


def _column_items_from_create(sql: str) -> list[str]:
    open_index = sql.find("(")
    close_index = sql.rfind(")")
    if open_index < 0 or close_index <= open_index:
        return []
    return _split_sql_items(sql[open_index + 1 : close_index])


def _extract_default(definition: str) -> str:
    match = re.search(
        r"\bDEFAULT\s+(.+?)(?=\s+(?:NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|REFERENCES|CHECK|CONSTRAINT)\b|$)",
        definition,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return " ".join(match.group(1).strip().split()) if match else ""


def _extract_type(definition_tail: str) -> str:
    stop = re.search(
        r"\b(?:DEFAULT|NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|REFERENCES|CHECK|CONSTRAINT|COLLATE)\b",
        definition_tail,
        flags=re.IGNORECASE,
    )
    type_text = definition_tail[: stop.start()] if stop else definition_tail
    return " ".join(type_text.strip().split())


def parse_columns_from_create_sql(table_name: str, create_sql: str) -> dict[str, ColumnDefinition]:
    columns: dict[str, ColumnDefinition] = {}
    for item in _column_items_from_create(create_sql):
        if re.match(r"^(?:CONSTRAINT|FOREIGN\s+KEY|PRIMARY\s+KEY|UNIQUE|CHECK)\b", item, flags=re.IGNORECASE):
            continue
        match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s+(.+)", item, flags=re.DOTALL)
        if not match:
            continue
        column = match.group(1)
        tail = " ".join(match.group(2).split())
        columns[column] = ColumnDefinition(
            table=table_name,
            column=column,
            data_type=_extract_type(tail),
            default=_extract_default(tail),
            nullable=not bool(re.search(r"\bNOT\s+NULL\b", tail, flags=re.IGNORECASE)) and not bool(
                re.search(r"\bPRIMARY\s+KEY\b", tail, flags=re.IGNORECASE)
            ),
            primary_key=bool(re.search(r"\bPRIMARY\s+KEY\b", tail, flags=re.IGNORECASE)),
            identity=bool(re.search(r"\bIDENTITY\b|\bAUTOINCREMENT\b", tail, flags=re.IGNORECASE)),
            raw_definition=item,
        )
    return columns


def parse_sqlite_schema_columns(report_text: str) -> dict[str, dict[str, ColumnDefinition]]:
    return {
        table: parse_columns_from_create_sql(table, create_sql)
        for table, create_sql in _extract_sqlite_sections(report_text).items()
    }


def parse_postgres_schema_columns(schema_sql: str) -> dict[str, dict[str, ColumnDefinition]]:
    return {
        table: parse_columns_from_create_sql(table, create_sql)
        for table, create_sql in _extract_postgres_blocks(schema_sql).items()
    }


def discover_sqlite_tables_from_report(report_text: str) -> list[str]:
    return sorted(parse_sqlite_schema_columns(report_text))


def discover_postgres_tables(schema_sql: str) -> list[str]:
    return sorted(_extract_postgres_blocks(schema_sql))


def discover_sqlite_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE ? ORDER BY name",
        ("sqlite_%",),
    ).fetchall()
    return [str(row["name"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows]


def estimate_sqlite_row_counts(connection: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in tables:
        row = connection.execute(f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)}").fetchone()
        value = row["row_count"] if isinstance(row, sqlite3.Row) else row[0]
        counts[table_name] = int(value or 0)
    return counts


def discover_sqlite_columns(connection: sqlite3.Connection, table_name: str) -> dict[str, ColumnDefinition]:
    columns: dict[str, ColumnDefinition] = {}
    rows = connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})").fetchall()
    for row in rows:
        column = str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
        data_type = str((row["type"] if isinstance(row, sqlite3.Row) else row[2]) or "")
        not_null = bool(row["notnull"] if isinstance(row, sqlite3.Row) else row[3])
        default = row["dflt_value"] if isinstance(row, sqlite3.Row) else row[4]
        primary_key = bool(row["pk"] if isinstance(row, sqlite3.Row) else row[5])
        columns[column] = ColumnDefinition(
            table=table_name,
            column=column,
            data_type=data_type,
            default=str(default or ""),
            nullable=not not_null and not primary_key,
            primary_key=primary_key,
            identity=False,
            raw_definition=f"{column} {data_type}".strip(),
        )
    return columns


def discover_foreign_keys_from_schema(schema_sql: str) -> list[ForeignKeyPlan]:
    foreign_keys: list[ForeignKeyPlan] = []
    for table_name, block in _extract_postgres_blocks(schema_sql).items():
        for match in re.finditer(
            r"FOREIGN\s+KEY\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s+REFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
            block,
            flags=re.IGNORECASE,
        ):
            foreign_keys.append(ForeignKeyPlan(table_name, match.group(1), match.group(2), match.group(3)))
    return sorted(foreign_keys, key=lambda item: (item.table, item.column, item.references_table, item.references_column))


def order_tables_by_foreign_keys(tables: list[str], foreign_keys: list[ForeignKeyPlan]) -> list[str]:
    table_set = set(tables)
    dependencies: dict[str, set[str]] = {table: set() for table in tables}
    for foreign_key in foreign_keys:
        if foreign_key.table in table_set and foreign_key.references_table in table_set and foreign_key.table != foreign_key.references_table:
            dependencies[foreign_key.table].add(foreign_key.references_table)
    remaining = set(tables)
    ordered: list[str] = []
    while remaining:
        ready = sorted(table for table in remaining if not (dependencies[table] & remaining))
        if not ready:
            ready = sorted(remaining)
        for table_name in ready:
            ordered.append(table_name)
            remaining.remove(table_name)
    return ordered


def estimate_batch_size(row_count: int | None, default_batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    if row_count is None or row_count <= 0:
        return default_batch_size
    return min(default_batch_size, max(100, row_count))


def build_batches(table_name: str, row_count: int | None, batch_size: int) -> list[MigrationBatch]:
    if row_count is None or row_count <= 0:
        return []
    return [
        MigrationBatch(
            table_name=table_name,
            batch_number=batch_number,
            offset=(batch_number - 1) * batch_size,
            limit=batch_size,
            estimated_rows=min(batch_size, row_count - ((batch_number - 1) * batch_size)),
        )
        for batch_number in range(1, math.ceil(row_count / batch_size) + 1)
    ]


def _normalized_type(column: ColumnDefinition) -> str:
    text = column.data_type.upper()
    text = re.sub(r"\s+", " ", text).strip()
    if "GENERATED BY DEFAULT AS IDENTITY" in text:
        return "BIGINT IDENTITY"
    return text


def _nullability(column: ColumnDefinition) -> str:
    return "NULL" if column.nullable else "NOT NULL"


def _default_text(column: ColumnDefinition) -> str:
    return column.default or "none"


def _is_money_column(column_name: str) -> bool:
    return bool(
        re.search(
            r"(amount|balance|cost|price|salary|tax|rate|total|paid|payment|debit|credit|income|expense|discount)",
            column_name,
            flags=re.IGNORECASE,
        )
    )


def _is_boolean_candidate(column_name: str) -> bool:
    return column_name in {
        "is_active",
        "is_locked",
        "is_voided",
        "is_cleared",
        "is_enabled",
        "posting_allowed",
        "control_account",
        "allow_manual_posting",
        "opening_posted",
    }


def classify_mismatch(sqlite_column: ColumnDefinition, postgres_column: ColumnDefinition) -> tuple[MismatchClassification, str, str]:
    sqlite_type = _normalized_type(sqlite_column)
    postgres_type = _normalized_type(postgres_column)
    column_name = sqlite_column.column
    if sqlite_column.identity or postgres_column.identity:
        return (
            MismatchClassification.EXPECTED_POSTGRES_IDENTITY,
            "Low",
            "Allow explicit identity values during future row-copy dry run, then verify sequence state after load.",
        )
    if sqlite_type in {"DATETIME", "TIMESTAMP"} and postgres_type == "TIMESTAMPTZ":
        return (
            MismatchClassification.EXPECTED_TIMESTAMP_MAPPING,
            "Low",
            "Map SQLite timestamp text values into TIMESTAMPTZ during future dry-run row mapping and validate timezone assumptions.",
        )
    if sqlite_type == "REAL" and postgres_type.startswith("NUMERIC"):
        classification = MismatchClassification.MONEY_NUMERIC_MAPPING if _is_money_column(column_name) else MismatchClassification.SAFE_TYPE_WIDENING
        return (
            classification,
            "Low" if classification is MismatchClassification.MONEY_NUMERIC_MAPPING else "Medium",
            "Convert numeric values using Decimal-compatible handling and verify scale/rounding in dry-run row mapping.",
        )
    if _is_boolean_candidate(column_name) and sqlite_type == "INTEGER" and postgres_type in {"INTEGER", "BOOLEAN"}:
        return (
            MismatchClassification.BOOLEAN_CANDIDATE,
            "Medium",
            "Keep numeric for this schema revision unless all callers are audited for boolean semantics.",
        )
    if sqlite_type == "INTEGER" and postgres_type in {"BIGINT", "BIGINT PRIMARY KEY", "BIGINT IDENTITY"}:
        return (
            MismatchClassification.SAFE_TYPE_WIDENING,
            "Low",
            "Treat as integer widening; verify FK/PK pairs remain type-compatible before row-copy dry run.",
        )
    if sqlite_type == "TEXT" and postgres_type in {"TIMESTAMPTZ", "DATE"}:
        return (
            MismatchClassification.EXPECTED_TIMESTAMP_MAPPING,
            "Medium",
            "Review data values for parseability before converting text dates/timestamps in dry-run row mapping.",
        )
    return (
        MismatchClassification.NEEDS_MANUAL_REVIEW,
        "Medium",
        "Review manually before enabling row-copy dry run.",
    )


def build_type_mapping_reviews(
    sqlite_columns_by_table: dict[str, dict[str, ColumnDefinition]],
    postgres_columns_by_table: dict[str, dict[str, ColumnDefinition]],
) -> list[SchemaMismatchReview]:
    reviews: list[SchemaMismatchReview] = []
    for table_name in sorted(set(sqlite_columns_by_table) & set(postgres_columns_by_table)):
        sqlite_columns = sqlite_columns_by_table[table_name]
        postgres_columns = postgres_columns_by_table[table_name]
        for column_name in sorted(set(sqlite_columns) & set(postgres_columns)):
            sqlite_column = sqlite_columns[column_name]
            postgres_column = postgres_columns[column_name]
            if (
                _normalized_type(sqlite_column) == _normalized_type(postgres_column)
                and _default_text(sqlite_column) == _default_text(postgres_column)
                and _nullability(sqlite_column) == _nullability(postgres_column)
            ):
                continue
            classification, risk, handling = classify_mismatch(sqlite_column, postgres_column)
            reviews.append(
                SchemaMismatchReview(
                    table=table_name,
                    column=column_name,
                    sqlite_type=sqlite_column.data_type or "unknown",
                    sqlite_default=_default_text(sqlite_column),
                    sqlite_nullable=_nullability(sqlite_column),
                    postgres_type=postgres_column.data_type or "unknown",
                    postgres_default=_default_text(postgres_column),
                    postgres_nullable=_nullability(postgres_column),
                    classification=classification,
                    migration_risk=risk,
                    recommended_handling=handling,
                )
            )
    return reviews


def build_schema_mismatch_reviews(
    sqlite_columns_by_table: dict[str, dict[str, ColumnDefinition]],
    postgres_columns_by_table: dict[str, dict[str, ColumnDefinition]],
) -> list[SchemaMismatchReview]:
    reviews: list[SchemaMismatchReview] = []
    for table_name in sorted(set(sqlite_columns_by_table) | set(postgres_columns_by_table)):
        sqlite_columns = sqlite_columns_by_table.get(table_name, {})
        postgres_columns = postgres_columns_by_table.get(table_name, {})
        for column_name in sorted(set(sqlite_columns) - set(postgres_columns)):
            sqlite_column = sqlite_columns[column_name]
            reviews.append(
                SchemaMismatchReview(
                    table=table_name,
                    column=column_name,
                    sqlite_type=sqlite_column.data_type or "unknown",
                    sqlite_default=_default_text(sqlite_column),
                    sqlite_nullable=_nullability(sqlite_column),
                    postgres_type="missing",
                    postgres_default="missing",
                    postgres_nullable="missing",
                    classification=MismatchClassification.BLOCKER,
                    migration_risk="High",
                    recommended_handling=(
                        "Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target."
                    ),
                )
            )
        for column_name in sorted(set(postgres_columns) - set(sqlite_columns)):
            postgres_column = postgres_columns[column_name]
            reviews.append(
                SchemaMismatchReview(
                    table=table_name,
                    column=column_name,
                    sqlite_type="missing",
                    sqlite_default="missing",
                    sqlite_nullable="missing",
                    postgres_type=postgres_column.data_type or "unknown",
                    postgres_default=_default_text(postgres_column),
                    postgres_nullable=_nullability(postgres_column),
                    classification=MismatchClassification.NEEDS_MANUAL_REVIEW,
                    migration_risk="Medium",
                    recommended_handling=(
                        "Confirm whether this PostgreSQL-only column should be populated by defaults, transforms, or a later migration."
                    ),
                )
            )
    return reviews


def build_migration_plan(
    *,
    sqlite_db_path: Path | None = DEFAULT_SQLITE_DB_PATH,
    sqlite_schema_report_path: Path = DEFAULT_SQLITE_SCHEMA_REPORT,
    postgres_schema_path: Path = DEFAULT_POSTGRES_SCHEMA_PATH,
    default_batch_size: int = DEFAULT_BATCH_SIZE,
) -> MigrationResult:
    sqlite_report = _read_text(sqlite_schema_report_path)
    postgres_schema = _read_text(postgres_schema_path)
    sqlite_columns = parse_sqlite_schema_columns(sqlite_report)
    postgres_columns = parse_postgres_schema_columns(postgres_schema)
    sqlite_tables = sorted(sqlite_columns)
    postgres_tables = sorted(postgres_columns)
    foreign_keys = discover_foreign_keys_from_schema(postgres_schema)
    order = order_tables_by_foreign_keys(sorted(set(sqlite_tables) & set(postgres_tables)), foreign_keys)
    row_counts: dict[str, int] = {}
    blockers: list[str] = []
    if sqlite_db_path is not None and sqlite_db_path.exists():
        connection = open_sqlite_readonly(sqlite_db_path)
        try:
            live_tables = discover_sqlite_tables(connection)
            live_columns = {table: discover_sqlite_columns(connection, table) for table in live_tables}
            if live_columns:
                sqlite_columns = live_columns
                sqlite_tables = sorted(sqlite_columns)
                order = order_tables_by_foreign_keys(sorted(set(sqlite_tables) & set(postgres_tables)), foreign_keys)
            row_counts = estimate_sqlite_row_counts(connection, order)
        finally:
            connection.close()
    else:
        blockers.append("SQLite database file unavailable; row-count estimates are unknown.")

    reviews = build_schema_mismatch_reviews(sqlite_columns, postgres_columns)
    table_plans: list[MigrationTablePlan] = []
    batches: list[MigrationBatch] = []
    for index, table_name in enumerate(order, start=1):
        row_count = row_counts.get(table_name)
        batch_size = estimate_batch_size(row_count, default_batch_size)
        table_batches = build_batches(table_name, row_count, batch_size)
        batches.extend(table_batches)
        dependencies = sorted(
            foreign_key.references_table for foreign_key in foreign_keys if foreign_key.table == table_name
        )
        table_plans.append(
            MigrationTablePlan(
                table_name=table_name,
                sqlite_columns=sorted(sqlite_columns.get(table_name, {})),
                postgres_columns=sorted(postgres_columns.get(table_name, {})),
                row_count_estimate=row_count,
                batch_size=batch_size,
                batch_count=len(table_batches),
                dependencies=dependencies,
                migration_order=index,
            )
        )
    if any(review.classification is MismatchClassification.BLOCKER for review in reviews):
        blockers.append("Blocking schema mismatch found; row-copy dry run must not proceed.")
    if any(review.classification is MismatchClassification.NEEDS_MANUAL_REVIEW for review in reviews):
        blockers.append("Manual schema mismatch review is required before row-copy dry run.")
    return MigrationResult(
        status=MigrationStatus.PLANNED,
        sqlite_table_count=len(sqlite_tables),
        postgres_table_count=len(postgres_tables),
        table_plans=table_plans,
        batches=batches,
        fk_dependency_order=order,
        estimated_total_rows=sum(row_counts.values()) if row_counts else None,
        schema_mismatches=reviews,
        blockers=blockers,
    )


def render_migration_plan(result: MigrationResult) -> str:
    lines = [
        "# SQLite to PostgreSQL Migration Plan",
        "",
        "Phase: 5B.15B",
        "",
        "Planning framework only. No real data migration, PostgreSQL writes, SQLite writes, runtime enablement, or production deployment was attempted.",
        "",
        "## Summary",
        "",
        f"- Status: {result.status.value}",
        f"- SQLite tables discovered: {result.sqlite_table_count}",
        f"- PostgreSQL tables discovered: {result.postgres_table_count}",
        f"- FK-safe migration tables planned: {len(result.fk_dependency_order)}",
        f"- Estimated total rows: {result.estimated_total_rows if result.estimated_total_rows is not None else 'unknown'}",
        f"- Estimated batches: {len(result.batches)}",
        f"- Schema mismatches reviewed: {len(result.schema_mismatches)}",
        "",
        "## Migration Order",
        "",
    ]
    lines.extend(f"{index}. `{table}`" for index, table in enumerate(result.fk_dependency_order, start=1))
    lines.extend(["", "## Remaining Blockers", ""])
    if result.blockers:
        lines.extend(f"- {blocker}" for blocker in result.blockers)
    else:
        lines.append("- No blocking schema mismatch categories were found; dry-run row mapping may be planned next.")
    lines.extend(
        [
            "- Real row-copy execution is not implemented.",
            "- PostgreSQL runtime remains disabled.",
            "- Production deployment remains blocked.",
            "",
        ]
    )
    return "\n".join(lines)


def render_mismatch_review(result: MigrationResult) -> str:
    counts = {classification: 0 for classification in MismatchClassification}
    for review in result.schema_mismatches:
        counts[review.classification] += 1
    safe_expected = sum(
        counts[classification]
        for classification in (
            MismatchClassification.SAFE_TYPE_WIDENING,
            MismatchClassification.EXPECTED_POSTGRES_IDENTITY,
            MismatchClassification.EXPECTED_TIMESTAMP_MAPPING,
            MismatchClassification.BOOLEAN_CANDIDATE,
            MismatchClassification.MONEY_NUMERIC_MAPPING,
        )
    )
    manual_review = counts[MismatchClassification.NEEDS_MANUAL_REVIEW]
    blockers = counts[MismatchClassification.BLOCKER]
    lines = [
        "# SQLite/PostgreSQL Schema Mismatch Review",
        "",
        "Phase: 5B.15B",
        "",
        "Review only. No data migration, PostgreSQL write, PostgreSQL runtime enablement, SQLite behavior change, or production deployment was attempted.",
        "",
        "## Summary",
        "",
        f"- Total mismatches: {len(result.schema_mismatches)}",
        f"- Safe/expected mismatches: {safe_expected}",
        f"- Manual review count: {manual_review}",
        f"- Blocker count: {blockers}",
        "",
        "## Mismatch Categories",
        "",
    ]
    for classification in MismatchClassification:
        lines.append(f"- {classification.value}: {counts[classification]}")
    lines.extend(["", "## Detailed Review", ""])
    lines.append("| Table | Column | SQLite | PostgreSQL | Classification | Risk | Recommended handling |")
    lines.append("|---|---|---|---|---|---|---|")
    for review in result.schema_mismatches:
        sqlite_detail = f"{review.sqlite_type}; default={review.sqlite_default}; {review.sqlite_nullable}"
        postgres_detail = f"{review.postgres_type}; default={review.postgres_default}; {review.postgres_nullable}"
        lines.append(
            f"| `{review.table}` | `{review.column}` | {sqlite_detail} | {postgres_detail} | {review.classification.value} | {review.migration_risk} | {review.recommended_handling} |"
        )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "- Data migration must not proceed to dry-run row mapping until all BLOCKER items above are reconciled in the PostgreSQL schema plan.",
            "- Do not execute real row copy, PostgreSQL writes, runtime activation, or production deployment in this phase.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_migration_plan_report(output_path: Path = DEFAULT_MIGRATION_PLAN_REPORT, **plan_kwargs: Any) -> MigrationResult:
    result = build_migration_plan(**plan_kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_migration_plan(result), encoding="utf-8")
    return result


def generate_mismatch_review_report(output_path: Path = DEFAULT_MISMATCH_REVIEW_REPORT, **plan_kwargs: Any) -> MigrationResult:
    result = build_migration_plan(**plan_kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_mismatch_review(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    plan = generate_migration_plan_report()
    generate_mismatch_review_report()
    print(
        "Generated SQLite/PostgreSQL migration review: "
        f"tables={plan.sqlite_table_count}/{plan.postgres_table_count} "
        f"mismatches={len(plan.schema_mismatches)} "
        f"batches={len(plan.batches)}"
    )
