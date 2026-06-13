"""Read-only SQLite to PostgreSQL row-copy dry-run planner.

This module proves row mapping shape without copying rows. It reads the local
SQLite database in read-only mode and parses the generated PostgreSQL schema
artifact. It never opens a PostgreSQL connection, executes INSERT statements,
writes application data, enables PostgreSQL runtime, or modifies SQLite data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
import math
from typing import Any

from sqlite_to_postgres_migration import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_POSTGRES_SCHEMA_PATH,
    DEFAULT_SQLITE_DB_PATH,
    ColumnDefinition,
    build_batches,
    discover_foreign_keys_from_schema,
    discover_postgres_tables,
    discover_sqlite_columns,
    discover_sqlite_tables,
    estimate_batch_size,
    estimate_sqlite_row_counts,
    open_sqlite_readonly,
    order_tables_by_foreign_keys,
    parse_postgres_schema_columns,
    quote_identifier,
)


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_REPORT = REPO_ROOT / "reports" / "sqlite_postgres_rowcopy_dryrun.md"
ROW_FAILURE_SAMPLE_LIMIT = 10


class RowCopyDryRunStatus(str, Enum):
    READY_FOR_DRY_RUN_COPY = "READY_FOR_DRY_RUN_COPY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ColumnMappingIssue:
    table_name: str
    column_name: str
    severity: str
    issue: str


@dataclass(frozen=True)
class RowProjectionFailure:
    table_name: str
    row_number: int
    column_name: str
    reason: str


@dataclass
class TableRowCopyDryRun:
    table_name: str
    source_row_count: int
    rows_evaluated: int
    rows_mappable: int
    rows_unmappable: int
    source_columns: list[str]
    destination_columns: list[str]
    mapped_columns: list[str]
    nullable_fields: list[str]
    required_fields: list[str]
    defaulted_fields: list[str]
    column_mapping_issues: list[ColumnMappingIssue] = field(default_factory=list)
    row_failures: list[RowProjectionFailure] = field(default_factory=list)
    migration_order: int = 0
    dependencies: list[str] = field(default_factory=list)
    batch_size: int = DEFAULT_BATCH_SIZE
    batch_count: int = 0


@dataclass
class RowCopyDryRunResult:
    status: RowCopyDryRunStatus
    tables_evaluated: int
    rows_evaluated: int
    rows_mappable: int
    rows_unmappable: int
    estimated_batches: int
    fk_dependency_order: list[str]
    table_results: list[TableRowCopyDryRun]
    column_mapping_issues: list[ColumnMappingIssue]
    blockers: list[str]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _is_defaulted(column: ColumnDefinition) -> bool:
    return bool(column.default) or column.identity


def _is_required(column: ColumnDefinition) -> bool:
    return not column.nullable and not _is_defaulted(column)


def _normalized_type(column: ColumnDefinition) -> str:
    return " ".join((column.data_type or "").upper().split())


def _value_is_blank(value: Any) -> bool:
    return isinstance(value, str) and value.strip() == ""


def _can_project_value(column: ColumnDefinition, value: Any) -> tuple[bool, str]:
    if value is None:
        if _is_required(column):
            return False, "required destination column received NULL"
        return True, ""

    destination_type = _normalized_type(column)
    if _value_is_blank(value):
        if any(token in destination_type for token in ("TIMESTAMP", "TIMESTAMPTZ", "DATE", "NUMERIC", "REAL", "DOUBLE", "INTEGER", "BIGINT")):
            if column.nullable or _is_defaulted(column):
                return True, ""
            return False, "blank value cannot satisfy required typed destination column"
        return True, ""

    if "BOOLEAN" in destination_type:
        if isinstance(value, bool):
            return True, ""
        if isinstance(value, int) and value in (0, 1):
            return True, ""
        if str(value).strip().lower() in {"0", "1", "true", "false", "t", "f", "yes", "no"}:
            return True, ""
        return False, f"value {value!r} is not boolean-compatible"

    if "INTEGER" in destination_type or "BIGINT" in destination_type:
        try:
            int(value)
        except (TypeError, ValueError):
            return False, f"value {value!r} is not integer-compatible"
        return True, ""

    if any(token in destination_type for token in ("NUMERIC", "REAL", "DOUBLE", "DECIMAL")):
        try:
            Decimal(str(value))
        except (InvalidOperation, ValueError):
            return False, f"value {value!r} is not numeric-compatible"
        return True, ""

    if "BYTEA" in destination_type and not isinstance(value, (bytes, bytearray, memoryview)):
        return False, f"value {value!r} is not bytea-compatible"

    return True, ""


def _column_mapping_issues(
    table_name: str,
    sqlite_columns: dict[str, ColumnDefinition],
    postgres_columns: dict[str, ColumnDefinition],
) -> list[ColumnMappingIssue]:
    issues: list[ColumnMappingIssue] = []
    for column_name in sorted(set(sqlite_columns) - set(postgres_columns)):
        issues.append(
            ColumnMappingIssue(
                table_name=table_name,
                column_name=column_name,
                severity="BLOCKER",
                issue="SQLite source column has no PostgreSQL destination column.",
            )
        )
    for column_name in sorted(set(postgres_columns) - set(sqlite_columns)):
        postgres_column = postgres_columns[column_name]
        if postgres_column.nullable:
            severity = "INFO"
            issue = "PostgreSQL-only destination column is nullable and can be omitted from row-copy projection."
        elif _is_defaulted(postgres_column):
            severity = "INFO"
            issue = "PostgreSQL-only destination column has a default/identity and can be omitted from row-copy projection."
        else:
            severity = "BLOCKER"
            issue = "Required PostgreSQL destination column has no SQLite source column or default."
        issues.append(ColumnMappingIssue(table_name=table_name, column_name=column_name, severity=severity, issue=issue))
    return issues


def _project_table_rows(
    connection: Any,
    table_name: str,
    mapped_columns: list[str],
    postgres_columns: dict[str, ColumnDefinition],
    row_count: int,
) -> tuple[int, int, list[RowProjectionFailure]]:
    if row_count <= 0:
        return 0, 0, []

    rows_mappable = 0
    failures: list[RowProjectionFailure] = []
    query = f"SELECT {', '.join(quote_identifier(column) for column in mapped_columns)} FROM {quote_identifier(table_name)}"
    for row_number, row in enumerate(connection.execute(query), start=1):
        row_ok = True
        for column_name in mapped_columns:
            ok, reason = _can_project_value(postgres_columns[column_name], row[column_name])
            if not ok:
                row_ok = False
                if len(failures) < ROW_FAILURE_SAMPLE_LIMIT:
                    failures.append(RowProjectionFailure(table_name, row_number, column_name, reason))
        if row_ok:
            rows_mappable += 1
    return rows_mappable, row_count - rows_mappable, failures


def build_rowcopy_dryrun(
    *,
    sqlite_db_path: Path = DEFAULT_SQLITE_DB_PATH,
    postgres_schema_path: Path = DEFAULT_POSTGRES_SCHEMA_PATH,
    default_batch_size: int = DEFAULT_BATCH_SIZE,
) -> RowCopyDryRunResult:
    postgres_schema = _read_text(postgres_schema_path)
    postgres_columns_by_table = parse_postgres_schema_columns(postgres_schema)
    postgres_tables = discover_postgres_tables(postgres_schema)
    foreign_keys = discover_foreign_keys_from_schema(postgres_schema)

    blockers: list[str] = []
    table_results: list[TableRowCopyDryRun] = []
    all_column_issues: list[ColumnMappingIssue] = []

    connection = open_sqlite_readonly(sqlite_db_path)
    try:
        sqlite_tables = discover_sqlite_tables(connection)
        sqlite_columns_by_table = {table: discover_sqlite_columns(connection, table) for table in sqlite_tables}
        ordered_tables = order_tables_by_foreign_keys(sorted(set(sqlite_tables) & set(postgres_tables)), foreign_keys)
        row_counts = estimate_sqlite_row_counts(connection, ordered_tables)

        missing_postgres_tables = sorted(set(sqlite_tables) - set(postgres_tables))
        missing_sqlite_tables = sorted(set(postgres_tables) - set(sqlite_tables))
        for table_name in missing_postgres_tables:
            blockers.append(f"SQLite table `{table_name}` has no PostgreSQL destination table.")
        for table_name in missing_sqlite_tables:
            blockers.append(f"PostgreSQL table `{table_name}` has no SQLite source table.")

        for order_index, table_name in enumerate(ordered_tables, start=1):
            sqlite_columns = sqlite_columns_by_table[table_name]
            postgres_columns = postgres_columns_by_table[table_name]
            mapped_columns = sorted(set(sqlite_columns) & set(postgres_columns))
            row_count = row_counts.get(table_name, 0)
            column_issues = _column_mapping_issues(table_name, sqlite_columns, postgres_columns)
            all_column_issues.extend(column_issues)
            schema_blocked = any(issue.severity == "BLOCKER" for issue in column_issues)
            if schema_blocked:
                rows_mappable = 0
                rows_unmappable = row_count
                row_failures: list[RowProjectionFailure] = []
            else:
                rows_mappable, rows_unmappable, row_failures = _project_table_rows(
                    connection,
                    table_name,
                    mapped_columns,
                    postgres_columns,
                    row_count,
                )
            batch_size = estimate_batch_size(row_count, default_batch_size)
            dependencies = sorted(
                foreign_key.references_table for foreign_key in foreign_keys if foreign_key.table == table_name
            )
            table_results.append(
                TableRowCopyDryRun(
                    table_name=table_name,
                    source_row_count=row_count,
                    rows_evaluated=row_count,
                    rows_mappable=rows_mappable,
                    rows_unmappable=rows_unmappable,
                    source_columns=sorted(sqlite_columns),
                    destination_columns=sorted(postgres_columns),
                    mapped_columns=mapped_columns,
                    nullable_fields=sorted(column for column, definition in postgres_columns.items() if definition.nullable),
                    required_fields=sorted(column for column, definition in postgres_columns.items() if _is_required(definition)),
                    defaulted_fields=sorted(column for column, definition in postgres_columns.items() if _is_defaulted(definition)),
                    column_mapping_issues=column_issues,
                    row_failures=row_failures,
                    migration_order=order_index,
                    dependencies=dependencies,
                    batch_size=batch_size,
                    batch_count=len(build_batches(table_name, row_count, batch_size)),
                )
            )
    finally:
        connection.close()

    rows_evaluated = sum(table.rows_evaluated for table in table_results)
    rows_mappable = sum(table.rows_mappable for table in table_results)
    rows_unmappable = sum(table.rows_unmappable for table in table_results)
    estimated_batches = sum(table.batch_count for table in table_results)
    blocking_column_issues = [issue for issue in all_column_issues if issue.severity == "BLOCKER"]
    if blocking_column_issues:
        blockers.append(f"Blocking column mapping issues: {len(blocking_column_issues)}.")
    if rows_unmappable:
        blockers.append(f"Unmappable source rows: {rows_unmappable}.")
    status = RowCopyDryRunStatus.BLOCKED if blockers else RowCopyDryRunStatus.READY_FOR_DRY_RUN_COPY

    return RowCopyDryRunResult(
        status=status,
        tables_evaluated=len(table_results),
        rows_evaluated=rows_evaluated,
        rows_mappable=rows_mappable,
        rows_unmappable=rows_unmappable,
        estimated_batches=estimated_batches,
        fk_dependency_order=[table.table_name for table in sorted(table_results, key=lambda item: item.migration_order)],
        table_results=table_results,
        column_mapping_issues=all_column_issues,
        blockers=blockers,
    )


def render_rowcopy_dryrun(result: RowCopyDryRunResult) -> str:
    blocking_issues = [issue for issue in result.column_mapping_issues if issue.severity == "BLOCKER"]
    nonblocking_issues = [issue for issue in result.column_mapping_issues if issue.severity != "BLOCKER"]
    lines = [
        "# SQLite to PostgreSQL Row-Copy Dry-Run Planner",
        "",
        "Phase: 5B.15F",
        "",
        "Read-only row projection only. No INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, COPY, PostgreSQL write transaction, data migration, PostgreSQL runtime enablement, production deployment, or SQLite behavior change was attempted.",
        "",
        "## Summary",
        "",
        f"- Status: {result.status.value}",
        f"- Tables evaluated: {result.tables_evaluated}",
        f"- Rows evaluated: {result.rows_evaluated}",
        f"- Rows mappable: {result.rows_mappable}",
        f"- Rows unmappable: {result.rows_unmappable}",
        f"- Column mapping issues: {len(result.column_mapping_issues)} ({len(blocking_issues)} blocking, {len(nonblocking_issues)} informational)",
        f"- FK-order migration tables planned: {len(result.fk_dependency_order)}",
        f"- Estimated migration batches: {result.estimated_batches}",
        "",
        "## Read-Only Guarantees",
        "",
        "- SQLite was opened with `mode=ro`.",
        "- PostgreSQL schema was parsed from `reports/postgres_generated_schema.sql`; no PostgreSQL connection was opened.",
        "- Rows were projected in memory only; no INSERT statements or write transactions were built or executed.",
        "",
        "## FK-Order Migration Plan",
        "",
    ]
    lines.extend(f"{index}. `{table}`" for index, table in enumerate(result.fk_dependency_order, start=1))

    lines.extend(
        [
            "",
            "## Table Projection Summary",
            "",
            "| Order | Table | Rows | Mappable | Unmappable | Mapped columns | Required | Nullable | Defaulted | Batches |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for table in sorted(result.table_results, key=lambda item: item.migration_order):
        lines.append(
            f"| {table.migration_order} | `{table.table_name}` | {table.rows_evaluated} | {table.rows_mappable} | {table.rows_unmappable} | "
            f"{len(table.mapped_columns)} | {len(table.required_fields)} | {len(table.nullable_fields)} | {len(table.defaulted_fields)} | {table.batch_count} |"
        )

    lines.extend(["", "## Table Column Mapping Details", ""])
    for table in sorted(result.table_results, key=lambda item: item.migration_order):
        lines.extend(
            [
                f"### `{table.table_name}`",
                "",
                f"- Source row count: {table.source_row_count}",
                f"- Source columns: {', '.join(f'`{column}`' for column in table.source_columns) if table.source_columns else 'none'}",
                f"- Destination columns: {', '.join(f'`{column}`' for column in table.destination_columns) if table.destination_columns else 'none'}",
                f"- Mapped columns: {', '.join(f'`{column}`' for column in table.mapped_columns) if table.mapped_columns else 'none'}",
                f"- Required fields: {', '.join(f'`{column}`' for column in table.required_fields) if table.required_fields else 'none'}",
                f"- Nullable fields: {', '.join(f'`{column}`' for column in table.nullable_fields) if table.nullable_fields else 'none'}",
                f"- Defaulted fields: {', '.join(f'`{column}`' for column in table.defaulted_fields) if table.defaulted_fields else 'none'}",
                "",
            ]
        )

    lines.extend(["", "## Column Mapping Issues", ""])
    if result.column_mapping_issues:
        lines.append("| Table | Column | Severity | Issue |")
        lines.append("|---|---|---|---|")
        for issue in result.column_mapping_issues:
            lines.append(f"| `{issue.table_name}` | `{issue.column_name}` | {issue.severity} | {issue.issue} |")
    else:
        lines.append("- No column mapping issues found.")

    row_failures = [failure for table in result.table_results for failure in table.row_failures]
    lines.extend(["", "## Row Projection Failures", ""])
    if row_failures:
        lines.append("| Table | Row number | Column | Reason |")
        lines.append("|---|---:|---|---|")
        for failure in row_failures:
            lines.append(f"| `{failure.table_name}` | {failure.row_number} | `{failure.column_name}` | {failure.reason} |")
    else:
        lines.append("- No sampled row projection failures found.")

    lines.extend(["", "## Final Status", ""])
    if result.blockers:
        lines.extend(f"- {blocker}" for blocker in result.blockers)
        lines.append("- Actual row-copy engine must not be built until blockers are resolved.")
    else:
        lines.append("- READY_FOR_DRY_RUN_COPY: every evaluated SQLite row can be projected into the generated PostgreSQL destination schema.")
        lines.append("- Actual row-copy engine may be built next, but real data migration and PostgreSQL writes remain blocked until explicitly authorized.")
    lines.append("")
    return "\n".join(lines)


def generate_rowcopy_dryrun_report(output_path: Path = DEFAULT_OUTPUT_REPORT, **dryrun_kwargs: Any) -> RowCopyDryRunResult:
    result = build_rowcopy_dryrun(**dryrun_kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_rowcopy_dryrun(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    dryrun = generate_rowcopy_dryrun_report()
    print(
        "Generated SQLite/PostgreSQL row-copy dry-run: "
        f"status={dryrun.status.value} "
        f"tables={dryrun.tables_evaluated} "
        f"rows={dryrun.rows_evaluated} "
        f"unmappable={dryrun.rows_unmappable} "
        f"batches={dryrun.estimated_batches}"
    )
