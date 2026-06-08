"""Read-only SQLite to PostgreSQL migration planning framework.

This module estimates migration shape and order only. It does not copy rows,
write to SQLite, write to PostgreSQL, enable PostgreSQL runtime, or deploy
schema.
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
DEFAULT_OUTPUT_REPORT = REPO_ROOT / "reports" / "sqlite_postgres_migration_plan.md"
DEFAULT_BATCH_SIZE = 1_000
SQLITE_SYSTEM_TABLE_PREFIX = "sqlite_"
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MigrationStatus(str, Enum):
    PLANNED = "PLANNED"
    BLOCKED = "BLOCKED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"


@dataclass(frozen=True)
class ColumnPlan:
    name: str
    source_type: str = ""
    target_type: str = ""


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


@dataclass
class MigrationResult:
    status: MigrationStatus
    sqlite_table_count: int
    postgres_table_count: int
    table_plans: list[MigrationTablePlan]
    batches: list[MigrationBatch]
    fk_dependency_order: list[str]
    estimated_total_rows: int | None
    schema_mismatches: list[str] = field(default_factory=list)
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


def discover_sqlite_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE ?
        ORDER BY name
        """,
        (f"{SQLITE_SYSTEM_TABLE_PREFIX}%",),
    ).fetchall()
    return [str(row["name"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows]


def discover_sqlite_columns(connection: sqlite3.Connection, table_name: str) -> list[ColumnPlan]:
    rows = connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})").fetchall()
    columns: list[ColumnPlan] = []
    for row in rows:
        name = row["name"] if isinstance(row, sqlite3.Row) else row[1]
        source_type = row["type"] if isinstance(row, sqlite3.Row) else row[2]
        columns.append(ColumnPlan(name=str(name), source_type=str(source_type or "")))
    return columns


def discover_sqlite_foreign_keys(connection: sqlite3.Connection, table_name: str) -> list[ForeignKeyPlan]:
    rows = connection.execute(f"PRAGMA foreign_key_list({quote_identifier(table_name)})").fetchall()
    foreign_keys: list[ForeignKeyPlan] = []
    for row in rows:
        column = row["from"] if isinstance(row, sqlite3.Row) else row[3]
        references_table = row["table"] if isinstance(row, sqlite3.Row) else row[2]
        references_column = row["to"] if isinstance(row, sqlite3.Row) else row[4]
        foreign_keys.append(
            ForeignKeyPlan(
                table=table_name,
                column=str(column),
                references_table=str(references_table),
                references_column=str(references_column),
            )
        )
    return sorted(foreign_keys, key=lambda item: (item.table, item.column, item.references_table, item.references_column))


def estimate_sqlite_row_counts(connection: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in tables:
        row = connection.execute(f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)}").fetchone()
        value = row["row_count"] if isinstance(row, sqlite3.Row) else row[0]
        counts[table_name] = int(value or 0)
    return counts


def _extract_create_table_blocks(schema_sql: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    pattern = re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b(.*?);",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(schema_sql):
        blocks[match.group(1)] = match.group(0)
    return blocks


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


def discover_postgres_tables(schema_sql: str) -> list[str]:
    return sorted(_extract_create_table_blocks(schema_sql))


def discover_postgres_columns(schema_sql: str) -> dict[str, list[ColumnPlan]]:
    columns_by_table: dict[str, list[ColumnPlan]] = {}
    for table_name, block in _extract_create_table_blocks(schema_sql).items():
        open_index = block.find("(")
        close_index = block.rfind(")")
        if open_index < 0 or close_index <= open_index:
            columns_by_table[table_name] = []
            continue
        body = block[open_index + 1 : close_index]
        columns: list[ColumnPlan] = []
        for item in _split_sql_items(body):
            if re.match(r"^(?:CONSTRAINT|FOREIGN\s+KEY|PRIMARY\s+KEY|UNIQUE|CHECK)\b", item, flags=re.IGNORECASE):
                continue
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s+(.+)", item, flags=re.DOTALL)
            if match:
                columns.append(ColumnPlan(name=match.group(1), target_type=" ".join(match.group(2).split())))
        columns_by_table[table_name] = sorted(columns, key=lambda item: item.name)
    return columns_by_table


def discover_postgres_foreign_keys(schema_sql: str) -> list[ForeignKeyPlan]:
    foreign_keys: list[ForeignKeyPlan] = []
    for table_name, block in _extract_create_table_blocks(schema_sql).items():
        for match in re.finditer(
            r"FOREIGN\s+KEY\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s+REFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
            block,
            flags=re.IGNORECASE,
        ):
            foreign_keys.append(
                ForeignKeyPlan(
                    table=table_name,
                    column=match.group(1),
                    references_table=match.group(2),
                    references_column=match.group(3),
                )
            )
    return sorted(foreign_keys, key=lambda item: (item.table, item.column, item.references_table, item.references_column))


def discover_sqlite_tables_from_report(report_text: str) -> list[str]:
    return sorted(set(re.findall(r"^### `([^`]+)`", report_text, flags=re.MULTILINE)))


def discover_sqlite_columns_from_report(report_text: str) -> dict[str, list[ColumnPlan]]:
    columns_by_table: dict[str, list[ColumnPlan]] = {}
    for table_match in re.finditer(r"^### `([^`]+)`\s*(.*?)(?=^### `|\Z)", report_text, flags=re.MULTILINE | re.DOTALL):
        table_name = table_match.group(1)
        section = table_match.group(2)
        sql_match = re.search(r"```sql\s*(.*?)\s*```", section, flags=re.DOTALL)
        if not sql_match:
            columns_by_table[table_name] = []
            continue
        block = sql_match.group(1)
        open_index = block.find("(")
        close_index = block.rfind(")")
        if open_index < 0 or close_index <= open_index:
            columns_by_table[table_name] = []
            continue
        columns: list[ColumnPlan] = []
        for item in _split_sql_items(block[open_index + 1 : close_index]):
            if re.match(r"^(?:CONSTRAINT|FOREIGN\s+KEY|PRIMARY\s+KEY|UNIQUE|CHECK)\b", item, flags=re.IGNORECASE):
                continue
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s+(.+)", item, flags=re.DOTALL)
            if match:
                columns.append(ColumnPlan(name=match.group(1), source_type=" ".join(match.group(2).split())))
        columns_by_table[table_name] = sorted(columns, key=lambda item: item.name)
    return columns_by_table


def discover_sqlite_foreign_keys_from_report(report_text: str) -> list[ForeignKeyPlan]:
    foreign_keys: list[ForeignKeyPlan] = []
    for table_match in re.finditer(r"^### `([^`]+)`\s*(.*?)(?=^### `|\Z)", report_text, flags=re.MULTILINE | re.DOTALL):
        table_name = table_match.group(1)
        section = table_match.group(2)
        for column, references_table, references_column, _on_delete in re.findall(
            r"- `([^`]+)` \u2192 `([^`.]+)\.([^`]+)` \(on_delete=([^)]+)\)",
            section,
        ):
            foreign_keys.append(
                ForeignKeyPlan(
                    table=table_name,
                    column=column,
                    references_table=references_table,
                    references_column=references_column,
                )
            )
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
            # Preserve deterministic output; cyclic FK handling must be reviewed before real migration.
            ready = sorted(remaining)
        for table_name in ready:
            ordered.append(table_name)
            remaining.remove(table_name)
    return ordered


def estimate_batch_size(row_count: int | None, default_batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    if row_count is None:
        return default_batch_size
    if row_count <= 0:
        return default_batch_size
    return min(default_batch_size, max(100, row_count))


def build_batches(table_name: str, row_count: int | None, batch_size: int) -> list[MigrationBatch]:
    if row_count is None:
        return [MigrationBatch(table_name=table_name, batch_number=1, offset=0, limit=batch_size, estimated_rows=0)]
    if row_count <= 0:
        return []
    batch_count = math.ceil(row_count / batch_size)
    batches: list[MigrationBatch] = []
    for batch_number in range(1, batch_count + 1):
        offset = (batch_number - 1) * batch_size
        estimated_rows = min(batch_size, row_count - offset)
        batches.append(
            MigrationBatch(
                table_name=table_name,
                batch_number=batch_number,
                offset=offset,
                limit=batch_size,
                estimated_rows=estimated_rows,
            )
        )
    return batches


def build_migration_plan(
    *,
    sqlite_connection: sqlite3.Connection | None = None,
    sqlite_db_path: Path | None = DEFAULT_SQLITE_DB_PATH,
    sqlite_schema_report_path: Path | None = DEFAULT_SQLITE_SCHEMA_REPORT,
    postgres_schema_path: Path = DEFAULT_POSTGRES_SCHEMA_PATH,
    default_batch_size: int = DEFAULT_BATCH_SIZE,
) -> MigrationResult:
    postgres_schema = _read_text(postgres_schema_path)
    postgres_tables = discover_postgres_tables(postgres_schema)
    postgres_columns = discover_postgres_columns(postgres_schema)
    postgres_foreign_keys = discover_postgres_foreign_keys(postgres_schema)

    connection = sqlite_connection
    should_close = False
    blockers: list[str] = []
    if connection is None:
        if sqlite_db_path is not None and sqlite_db_path.exists():
            connection = open_sqlite_readonly(sqlite_db_path)
            should_close = True
        else:
            blockers.append("SQLite database file is unavailable; row counts and live SQLite schema discovery were not estimated.")

    sqlite_tables: list[str] = []
    sqlite_columns: dict[str, list[ColumnPlan]] = {}
    sqlite_foreign_keys: list[ForeignKeyPlan] = []
    row_counts: dict[str, int] = {}
    try:
        if connection is not None:
            sqlite_tables = discover_sqlite_tables(connection)
            sqlite_columns = {table: discover_sqlite_columns(connection, table) for table in sqlite_tables}
            sqlite_foreign_keys = [foreign_key for table in sqlite_tables for foreign_key in discover_sqlite_foreign_keys(connection, table)]
            row_counts = estimate_sqlite_row_counts(connection, sqlite_tables)
    finally:
        if should_close and connection is not None:
            connection.close()

    if not sqlite_tables:
        if sqlite_schema_report_path is not None and sqlite_schema_report_path.exists():
            sqlite_report = _read_text(sqlite_schema_report_path)
            sqlite_tables = discover_sqlite_tables_from_report(sqlite_report)
            sqlite_columns = discover_sqlite_columns_from_report(sqlite_report)
            sqlite_foreign_keys = discover_sqlite_foreign_keys_from_report(sqlite_report)
            blockers.append("SQLite row counts were not estimated from a live database; schema inventory report was used for planning.")
        else:
            sqlite_tables = postgres_tables
            sqlite_columns = {table: [] for table in sqlite_tables}
            blockers.append("SQLite schema inventory report is unavailable; PostgreSQL schema was used as a planning fallback.")
        row_counts = {}

    common_tables = sorted(set(sqlite_tables) & set(postgres_tables))
    order_source_fks = sqlite_foreign_keys if sqlite_foreign_keys else postgres_foreign_keys
    migration_order = [table for table in order_tables_by_foreign_keys(common_tables, order_source_fks) if table in common_tables]
    order_index = {table: index for index, table in enumerate(migration_order, start=1)}

    table_plans: list[MigrationTablePlan] = []
    batches: list[MigrationBatch] = []
    schema_mismatches: list[str] = []
    for table_name in migration_order:
        sqlite_column_names = sorted(column.name for column in sqlite_columns.get(table_name, []))
        postgres_column_names = sorted(column.name for column in postgres_columns.get(table_name, []))
        missing_in_postgres = sorted(set(sqlite_column_names) - set(postgres_column_names))
        missing_in_sqlite = sorted(set(postgres_column_names) - set(sqlite_column_names)) if sqlite_column_names else []
        for column_name in missing_in_postgres:
            schema_mismatches.append(f"{table_name}.{column_name} missing in PostgreSQL schema")
        for column_name in missing_in_sqlite:
            schema_mismatches.append(f"{table_name}.{column_name} missing in SQLite schema")
        row_count = row_counts.get(table_name)
        batch_size = estimate_batch_size(row_count, default_batch_size)
        table_batches = build_batches(table_name, row_count, batch_size)
        batches.extend(table_batches)
        dependencies = sorted(
            foreign_key.references_table
            for foreign_key in order_source_fks
            if foreign_key.table == table_name and foreign_key.references_table in common_tables
        )
        table_plans.append(
            MigrationTablePlan(
                table_name=table_name,
                sqlite_columns=sqlite_column_names,
                postgres_columns=postgres_column_names,
                row_count_estimate=row_count,
                batch_size=batch_size,
                batch_count=len(table_batches) if row_count is not None else 0,
                dependencies=dependencies,
                missing_in_postgres=missing_in_postgres,
                missing_in_sqlite=missing_in_sqlite,
                migration_order=order_index[table_name],
            )
        )

    missing_postgres_tables = sorted(set(sqlite_tables) - set(postgres_tables))
    missing_sqlite_tables = sorted(set(postgres_tables) - set(sqlite_tables)) if connection is not None else []
    schema_mismatches.extend(f"{table} table missing in PostgreSQL schema" for table in missing_postgres_tables)
    schema_mismatches.extend(f"{table} table missing in SQLite schema" for table in missing_sqlite_tables)
    if schema_mismatches:
        blockers.append("Schema differences require review before real data migration.")

    estimated_total_rows = sum(row_counts.get(table, 0) for table in common_tables) if row_counts else None
    return MigrationResult(
        status=MigrationStatus.PLANNED,
        sqlite_table_count=len(sqlite_tables),
        postgres_table_count=len(postgres_tables),
        table_plans=table_plans,
        batches=batches,
        fk_dependency_order=migration_order,
        estimated_total_rows=estimated_total_rows,
        schema_mismatches=schema_mismatches,
        blockers=blockers,
    )


def render_migration_plan(result: MigrationResult) -> str:
    lines = [
        "# SQLite to PostgreSQL Migration Plan",
        "",
        "Phase: 5B.15A",
        "",
        "Planning framework only. No real data migration, PostgreSQL writes, SQLite writes, INSERT, UPDATE, DELETE, runtime enablement, or production deployment was attempted.",
        "",
        "## Summary",
        "",
        f"- Status: {result.status.value}",
        f"- SQLite tables discovered: {result.sqlite_table_count}",
        f"- PostgreSQL tables discovered: {result.postgres_table_count}",
        f"- FK-safe migration tables planned: {len(result.fk_dependency_order)}",
        f"- Estimated total rows: {result.estimated_total_rows if result.estimated_total_rows is not None else 'unknown'}",
        f"- Estimated batches: {len(result.batches)}",
        f"- Schema mismatches: {len(result.schema_mismatches)}",
        "",
        "## Migration Order",
        "",
    ]
    lines.extend(f"{index}. `{table}`" for index, table in enumerate(result.fk_dependency_order, start=1))
    if not result.fk_dependency_order:
        lines.append("- None.")

    lines.extend(["", "## Table Plans", ""])
    for plan in result.table_plans:
        row_count = plan.row_count_estimate if plan.row_count_estimate is not None else "unknown"
        dependencies = ", ".join(f"`{dependency}`" for dependency in plan.dependencies) if plan.dependencies else "none"
        lines.append(
            f"- `{plan.table_name}`: order={plan.migration_order}, rows={row_count}, batch_size={plan.batch_size}, batches={plan.batch_count}, dependencies={dependencies}"
        )

    lines.extend(["", "## Schema Mismatches", ""])
    if result.schema_mismatches:
        lines.extend(f"- {item}" for item in result.schema_mismatches[:200])
    else:
        lines.append("- None detected.")

    lines.extend(["", "## Batch Estimates", ""])
    if result.batches:
        for batch in result.batches[:200]:
            lines.append(
                f"- `{batch.table_name}` batch {batch.batch_number}: offset={batch.offset}, limit={batch.limit}, estimated_rows={batch.estimated_rows}"
            )
        if len(result.batches) > 200:
            lines.append(f"- {len(result.batches) - 200} additional batch estimates omitted from report preview.")
    else:
        lines.append("- No positive row-count batches estimated.")

    lines.extend(["", "## Remaining Blockers", ""])
    if result.blockers:
        lines.extend(f"- {item}" for item in result.blockers)
    else:
        lines.append("- Real migration execution is not implemented.")
    lines.extend(
        [
            "- PostgreSQL runtime remains disabled.",
            "- Production deployment remains blocked.",
            "- Row copy, INSERT, UPDATE, DELETE, and reconciliation execution remain future phases.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_migration_plan_report(
    output_path: Path = DEFAULT_OUTPUT_REPORT,
    **plan_kwargs: Any,
) -> MigrationResult:
    result = build_migration_plan(**plan_kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_migration_plan(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    generated = generate_migration_plan_report()
    print(
        "Generated SQLite to PostgreSQL migration plan: "
        f"sqlite_tables={generated.sqlite_table_count} "
        f"postgres_tables={generated.postgres_table_count} "
        f"planned_tables={len(generated.fk_dependency_order)} "
        f"estimated_batches={len(generated.batches)}"
    )
