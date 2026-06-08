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
DEFAULT_DATA_VOLUME_AUDIT_REPORT = REPO_ROOT / "reports" / "sqlite_postgres_data_volume_audit.md"
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


@dataclass(frozen=True)
class TableVolumeEstimate:
    table_name: str
    row_count: int
    estimated_data_bytes: int
    estimated_csv_bytes: int
    estimated_json_bytes: int


@dataclass(frozen=True)
class DataVolumeAudit:
    db_path: Path
    db_file_size_bytes: int
    page_count: int
    page_size: int
    freelist_count: int
    total_row_count: int
    table_estimates: list[TableVolumeEstimate]
    estimated_csv_export_bytes: int
    estimated_json_export_bytes: int
    estimated_compressed_export_bytes: int
    estimated_postgres_upload_bytes: int
    minimum_data_bundle_bytes: int
    recommended_data_bundle_bytes: int
    safe_data_bundle_2x_bytes: int
    volume_classification: str


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


def read_sqlite_page_metrics(connection: sqlite3.Connection) -> tuple[int, int, int]:
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0] or 0)
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0] or 0)
    freelist_count = int(connection.execute("PRAGMA freelist_count").fetchone()[0] or 0)
    return page_count, page_size, freelist_count


def _bytes_to_mb(value: int) -> float:
    return value / (1024 * 1024)


def _ceil_mb_bytes(value: int, minimum_mb: int = 1) -> int:
    mb = max(minimum_mb, math.ceil(value / (1024 * 1024)))
    return mb * 1024 * 1024


def classify_data_volume(total_bytes: int) -> str:
    if total_bytes < 50 * 1024 * 1024:
        return "SMALL"
    if total_bytes < 1_024 * 1024 * 1024:
        return "MEDIUM"
    return "LARGE"


def build_data_volume_audit(sqlite_db_path: Path = DEFAULT_SQLITE_DB_PATH) -> DataVolumeAudit:
    db_path = sqlite_db_path.resolve()
    db_file_size_bytes = db_path.stat().st_size
    connection = open_sqlite_readonly(db_path)
    try:
        page_count, page_size, freelist_count = read_sqlite_page_metrics(connection)
        tables = discover_sqlite_tables(connection)
        row_counts = estimate_sqlite_row_counts(connection, tables)
    finally:
        connection.close()

    total_rows = sum(row_counts.values())
    active_db_bytes = max(0, (page_count - freelist_count) * page_size)
    # Without reading rows, distribute active DB bytes by row count. Empty tables
    # remain zero; metadata/index overhead stays represented in total estimates.
    table_estimates: list[TableVolumeEstimate] = []
    for table_name in tables:
        row_count = row_counts.get(table_name, 0)
        estimated_data_bytes = round((active_db_bytes * row_count / total_rows)) if total_rows else 0
        estimated_csv_bytes = round(estimated_data_bytes * 1.15)
        estimated_json_bytes = round(estimated_data_bytes * 1.6)
        table_estimates.append(
            TableVolumeEstimate(
                table_name=table_name,
                row_count=row_count,
                estimated_data_bytes=estimated_data_bytes,
                estimated_csv_bytes=estimated_csv_bytes,
                estimated_json_bytes=estimated_json_bytes,
            )
        )
    table_estimates.sort(key=lambda item: (-item.row_count, -item.estimated_data_bytes, item.table_name))

    estimated_csv_export_bytes = max(db_file_size_bytes, round(active_db_bytes * 1.15))
    estimated_json_export_bytes = max(db_file_size_bytes, round(active_db_bytes * 1.6))
    estimated_compressed_export_bytes = round(estimated_csv_export_bytes * 0.45)
    estimated_postgres_upload_bytes = round(estimated_csv_export_bytes * 1.25)
    minimum_data_bundle_bytes = _ceil_mb_bytes(max(estimated_compressed_export_bytes, estimated_postgres_upload_bytes), minimum_mb=1)
    recommended_data_bundle_bytes = _ceil_mb_bytes(round(minimum_data_bundle_bytes * 1.5), minimum_mb=1)
    safe_data_bundle_2x_bytes = _ceil_mb_bytes(minimum_data_bundle_bytes * 2, minimum_mb=2)

    return DataVolumeAudit(
        db_path=db_path,
        db_file_size_bytes=db_file_size_bytes,
        page_count=page_count,
        page_size=page_size,
        freelist_count=freelist_count,
        total_row_count=total_rows,
        table_estimates=table_estimates,
        estimated_csv_export_bytes=estimated_csv_export_bytes,
        estimated_json_export_bytes=estimated_json_export_bytes,
        estimated_compressed_export_bytes=estimated_compressed_export_bytes,
        estimated_postgres_upload_bytes=estimated_postgres_upload_bytes,
        minimum_data_bundle_bytes=minimum_data_bundle_bytes,
        recommended_data_bundle_bytes=recommended_data_bundle_bytes,
        safe_data_bundle_2x_bytes=safe_data_bundle_2x_bytes,
        volume_classification=classify_data_volume(estimated_postgres_upload_bytes),
    )


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


def _format_mb(value: int) -> str:
    return f"{_bytes_to_mb(value):.2f} MB"


def render_data_volume_audit(audit: DataVolumeAudit) -> str:
    largest_by_rows = sorted(audit.table_estimates, key=lambda item: (-item.row_count, item.table_name))[:10]
    largest_by_size = sorted(audit.table_estimates, key=lambda item: (-item.estimated_data_bytes, item.table_name))[:10]
    lines = [
        "# SQLite to PostgreSQL Data Volume Audit",
        "",
        "Phase: 5B.15C",
        "",
        "Read-only sizing audit only. No rows were copied or exported, no PostgreSQL connection was opened, no PostgreSQL write was attempted, SQLite data was not modified, and PostgreSQL runtime was not enabled.",
        "",
        "## Database File",
        "",
        f"- DB file path: `{audit.db_path}`",
        f"- DB file size: {_format_mb(audit.db_file_size_bytes)} ({audit.db_file_size_bytes} bytes)",
        f"- SQLite page count: {audit.page_count}",
        f"- SQLite page size: {audit.page_size} bytes",
        f"- SQLite freelist count: {audit.freelist_count}",
        f"- Total row count: {audit.total_row_count}",
        f"- Migration volume classification: **{audit.volume_classification}**",
        "",
        "## Transfer Estimates",
        "",
        f"- Estimated CSV export size: {_format_mb(audit.estimated_csv_export_bytes)}",
        f"- Estimated JSON export size: {_format_mb(audit.estimated_json_export_bytes)}",
        f"- Estimated compressed export size: {_format_mb(audit.estimated_compressed_export_bytes)}",
        f"- Estimated PostgreSQL upload size: {_format_mb(audit.estimated_postgres_upload_bytes)}",
        f"- Minimum data needed: {_format_mb(audit.minimum_data_bundle_bytes)}",
        f"- Recommended data bundle: {_format_mb(audit.recommended_data_bundle_bytes)}",
        f"- Safe data bundle with 2x margin: {_format_mb(audit.safe_data_bundle_2x_bytes)}",
        "",
        "## Largest Tables By Rows",
        "",
        "| Table | Rows | Estimated data size | Estimated CSV | Estimated JSON |",
        "|---|---:|---:|---:|---:|",
    ]
    for table in largest_by_rows:
        lines.append(
            f"| `{table.table_name}` | {table.row_count} | {_format_mb(table.estimated_data_bytes)} | {_format_mb(table.estimated_csv_bytes)} | {_format_mb(table.estimated_json_bytes)} |"
        )
    lines.extend(
        [
            "",
            "## Largest Estimated Tables By Data Size",
            "",
            "| Table | Rows | Estimated data size | Estimated CSV | Estimated JSON |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for table in largest_by_size:
        lines.append(
            f"| `{table.table_name}` | {table.row_count} | {_format_mb(table.estimated_data_bytes)} | {_format_mb(table.estimated_csv_bytes)} | {_format_mb(table.estimated_json_bytes)} |"
        )
    lines.extend(
        [
            "",
            "## Row Count Per Table",
            "",
            "| Table | Rows | Estimated data size |",
            "|---|---:|---:|",
        ]
    )
    for table in sorted(audit.table_estimates, key=lambda item: item.table_name):
        lines.append(f"| `{table.table_name}` | {table.row_count} | {_format_mb(table.estimated_data_bytes)} |")
    lines.extend(
        [
            "",
            "## Estimation Notes",
            "",
            "- The audit used only `SELECT COUNT(*)`, `PRAGMA page_count`, `PRAGMA page_size`, and `PRAGMA freelist_count` against a read-only SQLite connection.",
            "- Table byte estimates are proportional allocations from active SQLite pages by row count; they are planning estimates, not row exports.",
            "- CSV/JSON estimates include serialization overhead; compressed estimate assumes roughly 55% compression from CSV.",
            "- PostgreSQL upload estimate includes protocol/index/transaction overhead for planning the internet data bundle.",
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


def generate_data_volume_audit_report(
    output_path: Path = DEFAULT_DATA_VOLUME_AUDIT_REPORT,
    sqlite_db_path: Path = DEFAULT_SQLITE_DB_PATH,
) -> DataVolumeAudit:
    audit = build_data_volume_audit(sqlite_db_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_data_volume_audit(audit), encoding="utf-8")
    return audit


if __name__ == "__main__":
    plan = generate_migration_plan_report()
    generate_mismatch_review_report()
    audit = generate_data_volume_audit_report()
    print(
        "Generated SQLite/PostgreSQL migration review: "
        f"tables={plan.sqlite_table_count}/{plan.postgres_table_count} "
        f"mismatches={len(plan.schema_mismatches)} "
        f"batches={len(plan.batches)} "
        f"db_size_mb={_bytes_to_mb(audit.db_file_size_bytes):.2f}"
    )
