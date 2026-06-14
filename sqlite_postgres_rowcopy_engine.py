"""Guarded SQLite to PostgreSQL row-copy engine structure.

The low-level engine remains connection-injected and blocked by default. The
real staging wrapper validates explicit row-copy guards before opening a
read-only SQLite connection and a PostgreSQL connection from DATABASE_URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from importlib import import_module
import os
from pathlib import Path
from typing import Any, Iterable

from postgres_connection_adapter import parse_database_url_safely, redact_database_url
from postgres_connection_probe import DEFAULT_DRIVER_PREFERENCE, detect_postgres_driver
from sqlite_postgres_rowcopy_dryrun import RowCopyDryRunResult, RowCopyDryRunStatus, TableRowCopyDryRun, build_rowcopy_dryrun
from sqlite_to_postgres_migration import DEFAULT_SQLITE_DB_PATH, open_sqlite_readonly, quote_identifier


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_ROW_COPY_RESULTS_REPORT = REPO_ROOT / "reports" / "sqlite_postgres_rowcopy_results.md"
ROW_COPY_ENABLE_ENV_VAR = "ERP_ENABLE_POSTGRES_ROW_COPY"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5


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


@dataclass(frozen=True)
class RowCopyGuard:
    status: RowCopyStatus
    blocked: bool
    guard_results: dict[str, bool]
    message: str
    redacted_database_url: str = ""
    driver_name: str = ""


@dataclass
class GuardedRowCopyResult:
    status: RowCopyStatus
    guard: RowCopyGuard
    run_result: RowCopyRunResult
    started_at: str
    completed_at: str
    dryrun_status: str = ""
    error_message: str = ""


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


def validate_row_copy_guard(
    *,
    copy_rows_flag: bool,
    confirmation_flag: bool,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    driver_preference: tuple[str, ...] = DEFAULT_DRIVER_PREFERENCE,
) -> RowCopyGuard:
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "") if database_url is None else database_url
    driver_name, driver_detected = detect_postgres_driver(driver_preference)
    parsed = parse_database_url_safely(value)
    guard_results = {
        ROW_COPY_ENABLE_ENV_VAR: env.get(ROW_COPY_ENABLE_ENV_VAR) == "1",
        "ERP_ENVIRONMENT_is_staging": env.get("ERP_ENVIRONMENT") == "staging",
        "DATABASE_URL_present": bool(value),
        "DATABASE_URL_valid": bool(parsed["valid"]),
        "explicit_copy_rows_flag": bool(copy_rows_flag),
        "explicit_confirm_row_copy_flag": bool(confirmation_flag),
        "postgres_driver_available": driver_detected,
    }
    blocked = not all(guard_results.values())
    return RowCopyGuard(
        status=RowCopyStatus.BLOCKED if blocked else RowCopyStatus.COMPLETED,
        blocked=blocked,
        guard_results=guard_results,
        message=(
            "Row-copy execution is blocked until staging environment, enable flag, DATABASE_URL, explicit CLI flags, and PostgreSQL driver guards pass."
            if blocked
            else "Row-copy guards passed for staging execution."
        ),
        redacted_database_url=redact_database_url(value),
        driver_name=driver_name,
    )


def open_postgres_row_copy_connection(database_url: str, driver_name: str, connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS):
    driver = import_module(driver_name)
    return driver.connect(database_url, connect_timeout=connect_timeout_seconds)


def _close_connection(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def _blocked_guarded_result(guard: RowCopyGuard, started_at: str, output_path: Path) -> GuardedRowCopyResult:
    run_result = RowCopyRunResult(status=RowCopyStatus.BLOCKED, batches_planned=0, error_message=guard.message)
    result = GuardedRowCopyResult(
        status=RowCopyStatus.BLOCKED,
        guard=guard,
        run_result=run_result,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        error_message=guard.message,
    )
    write_row_copy_results(result, output_path)
    return result


def execute_guarded_row_copy_to_staging(
    *,
    copy_rows_flag: bool,
    confirmation_flag: bool,
    sqlite_db_path: Path = DEFAULT_SQLITE_DB_PATH,
    output_path: Path = DEFAULT_ROW_COPY_RESULTS_REPORT,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    connector: Any | None = None,
    sqlite_connection_factory: Any = open_sqlite_readonly,
    dryrun_builder: Any = build_rowcopy_dryrun,
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
) -> GuardedRowCopyResult:
    started_at = datetime.now(UTC).isoformat()
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "") if database_url is None else database_url
    guard = validate_row_copy_guard(
        copy_rows_flag=copy_rows_flag,
        confirmation_flag=confirmation_flag,
        environ=dict(env),
        database_url=value,
    )
    if guard.blocked:
        return _blocked_guarded_result(guard, started_at, output_path)

    sqlite_conn = None
    postgres_conn = None
    dryrun_status = ""
    try:
        dryrun = dryrun_builder(sqlite_db_path=sqlite_db_path)
        dryrun_status = dryrun.status.value
        if dryrun.status is not RowCopyDryRunStatus.READY_FOR_DRY_RUN_COPY:
            message = "Row-copy dry-run is not READY_FOR_DRY_RUN_COPY; guarded row-copy remains blocked."
            run_result = RowCopyRunResult(status=RowCopyStatus.BLOCKED, batches_planned=0, error_message=message)
            result = GuardedRowCopyResult(
                status=RowCopyStatus.BLOCKED,
                guard=guard,
                run_result=run_result,
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
                dryrun_status=dryrun_status,
                error_message=message,
            )
            write_row_copy_results(result, output_path)
            return result

        batches = build_row_copy_batches_from_dryrun(dryrun)
        sqlite_conn = sqlite_connection_factory(sqlite_db_path)
        connect = connector or open_postgres_row_copy_connection
        postgres_conn = connect(value, guard.driver_name, connect_timeout_seconds)
        run_result = execute_row_copy_batches_with_connection(
            batches,
            sqlite_conn,
            postgres_conn,
            allow_execution=True,
        )
        result = GuardedRowCopyResult(
            status=run_result.status,
            guard=guard,
            run_result=run_result,
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
            dryrun_status=dryrun_status,
            error_message=run_result.error_message,
        )
        write_row_copy_results(result, output_path)
        return result
    except Exception as exc:
        if postgres_conn is not None:
            rollback = getattr(postgres_conn, "rollback", None)
            if callable(rollback):
                rollback()
        run_result = RowCopyRunResult(
            status=RowCopyStatus.ROLLED_BACK if postgres_conn is not None else RowCopyStatus.FAILED,
            batches_planned=0,
            error_message=f"{type(exc).__name__}: {exc}",
            rolled_back=postgres_conn is not None,
        )
        result = GuardedRowCopyResult(
            status=run_result.status,
            guard=guard,
            run_result=run_result,
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
            dryrun_status=dryrun_status,
            error_message=run_result.error_message,
        )
        write_row_copy_results(result, output_path)
        return result
    finally:
        if sqlite_conn is not None:
            _close_connection(sqlite_conn)
        if postgres_conn is not None:
            _close_connection(postgres_conn)


def render_row_copy_results(result: GuardedRowCopyResult) -> str:
    lines = [
        "# SQLite to PostgreSQL Row-Copy Results",
        "",
        "Phase: 5B.15H",
        "",
        "Guarded staging row-copy report. PostgreSQL runtime was not enabled, production deployment was not attempted, application runtime was not changed, and SQLite was opened read-only.",
        "",
        "## Summary",
        "",
        f"- Status: {result.status.value}",
        f"- Started at: {result.started_at}",
        f"- Completed at: {result.completed_at}",
        f"- Dry-run status: {result.dryrun_status or 'not evaluated'}",
        f"- Batches planned: {result.run_result.batches_planned}",
        f"- Batches executed: {result.run_result.batches_executed}",
        f"- Rows planned: {result.run_result.rows_planned}",
        f"- Rows copied: {result.run_result.rows_copied}",
        f"- Committed: {result.run_result.committed}",
        f"- Rolled back: {result.run_result.rolled_back}",
        "",
        "## Guards",
        "",
        f"- Blocked: {result.guard.blocked}",
        f"- Message: {result.guard.message}",
    ]
    if result.guard.redacted_database_url:
        lines.append(f"- DATABASE_URL: {result.guard.redacted_database_url}")
    if result.guard.driver_name:
        lines.append(f"- PostgreSQL driver: {result.guard.driver_name}")
    for guard_name, passed in result.guard.guard_results.items():
        lines.append(f"- {guard_name}: {passed}")
    if result.error_message:
        lines.extend(["", "## Error", "", f"- {result.error_message}"])
    lines.extend(
        [
            "",
            "## Table Results",
            "",
        ]
    )
    if result.run_result.table_results:
        lines.append("| Table | Status | Batches | Rows planned | Rows copied | Error |")
        lines.append("|---|---|---:|---:|---:|---|")
        for table in result.run_result.table_results:
            lines.append(
                f"| `{table.table_name}` | {table.status.value} | {table.batches_executed}/{table.batches_planned} | "
                f"{table.rows_planned} | {table.rows_copied} | {table.error_message or ''} |"
            )
    else:
        lines.append("- No table batches executed.")
    lines.extend(
        [
            "",
            "## Safety Notes",
            "",
            "- Required command: `python postgres_staging_deployer.py --copy-rows --confirm-row-copy`.",
            "- Required environment: `ERP_ENVIRONMENT=staging`, `ERP_ENABLE_POSTGRES_ROW_COPY=1`, and `DATABASE_URL`.",
            "- One transaction is used for the full row-copy run.",
            "- Commit occurs only after all batches succeed; rollback occurs on failure.",
            "",
        ]
    )
    return "\n".join(lines)


def write_row_copy_results(result: GuardedRowCopyResult, output_path: Path = DEFAULT_ROW_COPY_RESULTS_REPORT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_row_copy_results(result), encoding="utf-8")
