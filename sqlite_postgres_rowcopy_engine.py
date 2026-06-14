"""Mock-first SQLite to PostgreSQL row-copy engine structure.

The engine is intentionally connection-injected. It never discovers or creates
a PostgreSQL connection, never reads runtime configuration, and never enables
PostgreSQL application runtime. Execution is blocked by default and can only
write through an explicitly supplied postgres_conn, which is currently intended
for tests with mock connections only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from sqlite_postgres_rowcopy_dryrun import RowCopyDryRunResult, TableRowCopyDryRun
from sqlite_to_postgres_migration import quote_identifier


class RowCopyStatus(str, Enum):
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class RowCopyBatch:
    table_name: str
    columns: tuple[str, ...]
    batch_number: int
    offset: int
    limit: int
    estimated_rows: int
    migration_order: int


@dataclass
class RowCopyTableResult:
    table_name: str
    status: RowCopyStatus
    batches_planned: int = 0
    batches_executed: int = 0
    rows_planned: int = 0
    rows_copied: int = 0
    error_message: str = ""


@dataclass
class RowCopyRunResult:
    status: RowCopyStatus
    batches_planned: int
    batches_executed: int = 0
    rows_planned: int = 0
    rows_copied: int = 0
    table_results: list[RowCopyTableResult] = field(default_factory=list)
    error_message: str = ""
    committed: bool = False
    rolled_back: bool = False


def build_row_copy_batches_from_dryrun(dryrun: RowCopyDryRunResult) -> list[RowCopyBatch]:
    """Build FK-ordered row-copy batches from a successful dry-run plan."""
    batches: list[RowCopyBatch] = []
    for table in sorted(dryrun.table_results, key=lambda item: item.migration_order):
        if table.rows_evaluated <= 0:
            continue
        for batch_number in range(1, table.batch_count + 1):
            offset = (batch_number - 1) * table.batch_size
            batches.append(
                RowCopyBatch(
                    table_name=table.table_name,
                    columns=tuple(table.mapped_columns),
                    batch_number=batch_number,
                    offset=offset,
                    limit=table.batch_size,
                    estimated_rows=max(0, min(table.batch_size, table.rows_evaluated - offset)),
                    migration_order=table.migration_order,
                )
            )
    return batches


def _table_results_from_batches(batches: Iterable[RowCopyBatch], status: RowCopyStatus) -> list[RowCopyTableResult]:
    grouped: dict[str, RowCopyTableResult] = {}
    for batch in batches:
        result = grouped.setdefault(
            batch.table_name,
            RowCopyTableResult(table_name=batch.table_name, status=status),
        )
        result.batches_planned += 1
        result.rows_planned += batch.estimated_rows
    return list(grouped.values())


def _cursor(postgres_conn: Any) -> Any:
    cursor_factory = getattr(postgres_conn, "cursor", None)
    if not callable(cursor_factory):
        raise TypeError("Injected postgres_conn must provide cursor().")
    return cursor_factory()


def _close_cursor(cursor: Any) -> None:
    close = getattr(cursor, "close", None)
    if callable(close):
        close()


def _select_batch_rows(sqlite_conn: Any, batch: RowCopyBatch) -> list[Any]:
    if not batch.columns:
        return []
    query = (
        f"SELECT {', '.join(quote_identifier(column) for column in batch.columns)} "
        f"FROM {quote_identifier(batch.table_name)} "
        f"LIMIT ? OFFSET ?"
    )
    return list(sqlite_conn.execute(query, (batch.limit, batch.offset)).fetchall())


def _row_values(row: Any, columns: tuple[str, ...]) -> tuple[Any, ...]:
    if hasattr(row, "keys"):
        return tuple(row[column] for column in columns)
    return tuple(row[index] for index, _column in enumerate(columns))


def _insert_sql(batch: RowCopyBatch) -> str:
    column_list = ", ".join(quote_identifier(column) for column in batch.columns)
    placeholders = ", ".join(["%s"] * len(batch.columns))
    return f"INSERT INTO {quote_identifier(batch.table_name)} ({column_list}) VALUES ({placeholders})"


def execute_row_copy_batches_with_connection(
    batches: list[RowCopyBatch],
    sqlite_conn: Any,
    postgres_conn: Any,
    *,
    allow_execution: bool = False,
) -> RowCopyRunResult:
    """Execute row-copy batches against an injected connection only.

    This path is mock-first: callers must pass a postgres_conn. No connection
    discovery or runtime configuration is performed here.
    """
    rows_planned = sum(batch.estimated_rows for batch in batches)
    if not allow_execution:
        return RowCopyRunResult(
            status=RowCopyStatus.BLOCKED,
            batches_planned=len(batches),
            rows_planned=rows_planned,
            table_results=_table_results_from_batches(batches, RowCopyStatus.BLOCKED),
            error_message="Row-copy execution is blocked unless allow_execution=True and an injected mock connection is supplied.",
        )

    table_results_by_name: dict[str, RowCopyTableResult] = {
        result.table_name: result for result in _table_results_from_batches(batches, RowCopyStatus.COMPLETED)
    }
    cursor = None
    batches_executed = 0
    rows_copied = 0
    try:
        cursor = _cursor(postgres_conn)
        for batch in sorted(batches, key=lambda item: (item.migration_order, item.batch_number)):
            rows = _select_batch_rows(sqlite_conn, batch)
            insert_sql = _insert_sql(batch)
            table_result = table_results_by_name[batch.table_name]
            for row in rows:
                cursor.execute(insert_sql, _row_values(row, batch.columns))
                rows_copied += 1
                table_result.rows_copied += 1
            batches_executed += 1
            table_result.batches_executed += 1

        commit = getattr(postgres_conn, "commit", None)
        if callable(commit):
            commit()
        return RowCopyRunResult(
            status=RowCopyStatus.COMPLETED,
            batches_planned=len(batches),
            batches_executed=batches_executed,
            rows_planned=rows_planned,
            rows_copied=rows_copied,
            table_results=list(table_results_by_name.values()),
            committed=True,
        )
    except Exception as exc:
        rollback = getattr(postgres_conn, "rollback", None)
        rolled_back = False
        if callable(rollback):
            rollback()
            rolled_back = True
        for result in table_results_by_name.values():
            if result.batches_executed < result.batches_planned:
                result.status = RowCopyStatus.ROLLED_BACK if rolled_back else RowCopyStatus.FAILED
                result.error_message = f"{type(exc).__name__}: {exc}"
        return RowCopyRunResult(
            status=RowCopyStatus.ROLLED_BACK if rolled_back else RowCopyStatus.FAILED,
            batches_planned=len(batches),
            batches_executed=batches_executed,
            rows_planned=rows_planned,
            rows_copied=rows_copied,
            table_results=list(table_results_by_name.values()),
            error_message=f"{type(exc).__name__}: {exc}",
            rolled_back=rolled_back,
        )
    finally:
        if cursor is not None:
            _close_cursor(cursor)
