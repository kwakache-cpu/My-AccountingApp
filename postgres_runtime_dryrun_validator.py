"""Guarded PostgreSQL runtime dry-run validation.

This module validates core PostgreSQL runtime read paths before final cutover.
It only connects to PostgreSQL and executes SELECT queries. It does not enable
runtime permanently, deploy production, run migrations, write application data,
or modify SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from importlib import import_module
import os
from pathlib import Path
import re
from typing import Any

from postgres_connection_adapter import redact_database_url
from postgres_connection_probe import DEFAULT_DRIVER_PREFERENCE, detect_postgres_driver


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_REPORT = REPO_ROOT / "reports" / "postgres_runtime_dryrun_report.md"
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

STARTUP_TABLES = ("database_identity", "migration_history", "companies", "users")
BUSINESS_TABLES = (
    "chart_of_accounts",
    "customers",
    "suppliers",
    "inventory",
    "invoices",
    "payments",
    "journal_entries",
)


class RuntimeDryRunStatus(str, Enum):
    READY_FOR_RUNTIME_CUTOVER = "READY_FOR_RUNTIME_CUTOVER"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RuntimeDryRunGuard:
    blocked: bool
    guard_results: dict[str, bool]
    message: str
    redacted_database_url: str = ""
    driver_name: str = ""


@dataclass(frozen=True)
class RuntimeDryRunCheck:
    category: str
    name: str
    table_name: str
    status: str
    row_count: int | None = None
    detail: str = ""
    error_message: str = ""


@dataclass
class RuntimeDryRunResult:
    status: RuntimeDryRunStatus
    guard: RuntimeDryRunGuard
    started_at: str
    completed_at: str
    checks: list[RuntimeDryRunCheck] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    @property
    def checks_passed(self) -> int:
        return sum(1 for check in self.checks if check.status == "PASSED")

    @property
    def checks_failed(self) -> int:
        return sum(1 for check in self.checks if check.status != "PASSED")

    def category_status(self, category: str) -> str:
        checks = [check for check in self.checks if check.category == category]
        if not checks:
            return "BLOCKED"
        return "PASSED" if all(check.status == "PASSED" for check in checks) else "FAILED"


def quote_identifier(identifier: str) -> str:
    if not SAFE_IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return f'"{identifier}"'


def validate_runtime_dryrun_guard(
    *,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    driver_preference: tuple[str, ...] = DEFAULT_DRIVER_PREFERENCE,
) -> RuntimeDryRunGuard:
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "") if database_url is None else database_url
    driver_name, driver_detected = detect_postgres_driver(driver_preference)
    guard_results = {
        "ERP_ENVIRONMENT_is_staging": env.get("ERP_ENVIRONMENT") == "staging",
        "ERP_ENABLE_POSTGRES_RUNTIME_DRYRUN_is_enabled": env.get("ERP_ENABLE_POSTGRES_RUNTIME_DRYRUN") == "1",
        "DATABASE_URL_present": bool(value),
        "postgres_driver_available": driver_detected,
    }
    blocked = not all(guard_results.values())
    return RuntimeDryRunGuard(
        blocked=blocked,
        guard_results=guard_results,
        message=(
            "Runtime dry-run validation is blocked until staging environment, dry-run enablement, DATABASE_URL, and PostgreSQL driver guards pass."
            if blocked
            else "Runtime dry-run guards passed for read-only staging checks."
        ),
        redacted_database_url=redact_database_url(value),
        driver_name=driver_name,
    )


def open_runtime_dryrun_connection(database_url: str, driver_name: str, connect_timeout_seconds: int = 5):
    driver = import_module(driver_name)
    return driver.connect(database_url, connect_timeout=connect_timeout_seconds)


def _fetchone(connection: Any, sql: str, params: dict[str, Any] | tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
        return cursor.fetchone()
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


def _fetchone_count(connection: Any, sql: str, params: dict[str, Any] | tuple[Any, ...] = ()) -> int:
    row = _fetchone(connection, sql, params)
    return int((row[0] if row else 0) or 0)


def _table_exists(connection: Any, table_name: str) -> bool:
    return _fetchone_count(
        connection,
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_type = 'BASE TABLE'
          AND table_name = %(table_name)s
        """,
        {"table_name": table_name},
    ) == 1


def _table_count(connection: Any, table_name: str) -> int:
    return _fetchone_count(connection, f"SELECT COUNT(*) FROM {quote_identifier(table_name)}")


def _count_check(connection: Any, *, category: str, name: str, table_name: str, minimum_count: int = 0) -> RuntimeDryRunCheck:
    try:
        if not _table_exists(connection, table_name):
            return RuntimeDryRunCheck(category, name, table_name, "FAILED", None, error_message="table is missing")
        count = _table_count(connection, table_name)
        if count < minimum_count:
            return RuntimeDryRunCheck(
                category,
                name,
                table_name,
                "FAILED",
                count,
                error_message=f"row count {count} is below required minimum {minimum_count}",
            )
        return RuntimeDryRunCheck(category, name, table_name, "PASSED", count, "SELECT COUNT(*) succeeded")
    except Exception as exc:  # pragma: no cover - defensive report path
        return RuntimeDryRunCheck(category, name, table_name, "FAILED", None, error_message=str(exc))


def _query_check(
    connection: Any,
    *,
    category: str,
    name: str,
    table_name: str,
    sql: str,
    minimum_count: int = 0,
) -> RuntimeDryRunCheck:
    try:
        count = _fetchone_count(connection, sql)
        if count < minimum_count:
            return RuntimeDryRunCheck(
                category,
                name,
                table_name,
                "FAILED",
                count,
                error_message=f"result count {count} is below required minimum {minimum_count}",
            )
        return RuntimeDryRunCheck(category, name, table_name, "PASSED", count, "read-only source query succeeded")
    except Exception as exc:
        return RuntimeDryRunCheck(category, name, table_name, "FAILED", None, error_message=str(exc))


def _startup_checks(connection: Any) -> list[RuntimeDryRunCheck]:
    return [
        _count_check(connection, category="startup", name="database_identity metadata", table_name="database_identity", minimum_count=1),
        _count_check(connection, category="startup", name="migration_history metadata", table_name="migration_history", minimum_count=1),
        _count_check(connection, category="startup", name="companies startup source", table_name="companies", minimum_count=1),
        _count_check(connection, category="startup", name="users startup source", table_name="users", minimum_count=1),
    ]


def _business_checks(connection: Any) -> list[RuntimeDryRunCheck]:
    return [
        _count_check(connection, category="business", name=f"{table_name} read path", table_name=table_name, minimum_count=1)
        for table_name in BUSINESS_TABLES
    ]


def _reporting_checks(connection: Any) -> list[RuntimeDryRunCheck]:
    return [
        _query_check(
            connection,
            category="reporting",
            name="financial reports data sources",
            table_name="journal_entries,journal_lines,chart_of_accounts",
            sql="""
            SELECT COUNT(*)
            FROM journal_entries AS je
            LEFT JOIN journal_lines AS jl ON jl.entry_id = je.id
            LEFT JOIN chart_of_accounts AS coa ON coa.id = jl.account_id
            """,
            minimum_count=1,
        ),
        _query_check(
            connection,
            category="reporting",
            name="dashboard metrics sources",
            table_name="companies,users,customers,inventory,invoices,payments,journal_entries",
            sql="""
            SELECT
                (SELECT COUNT(*) FROM companies)
              + (SELECT COUNT(*) FROM users)
              + (SELECT COUNT(*) FROM customers)
              + (SELECT COUNT(*) FROM inventory)
              + (SELECT COUNT(*) FROM invoices)
              + (SELECT COUNT(*) FROM payments)
              + (SELECT COUNT(*) FROM journal_entries)
            """,
            minimum_count=1,
        ),
    ]


def execute_runtime_dryrun_validation(
    *,
    output_path: Path = DEFAULT_OUTPUT_REPORT,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    connector: Any | None = None,
    connect_timeout_seconds: int = 5,
) -> RuntimeDryRunResult:
    started_at = datetime.now(UTC).isoformat()
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "") if database_url is None else database_url
    guard = validate_runtime_dryrun_guard(environ=dict(env), database_url=value)
    if guard.blocked:
        result = RuntimeDryRunResult(
            status=RuntimeDryRunStatus.BLOCKED,
            guard=guard,
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
            blockers=[guard.message],
        )
        write_runtime_dryrun_report(result, output_path)
        return result

    connect = connector or open_runtime_dryrun_connection
    connection = connect(value, guard.driver_name, connect_timeout_seconds)
    try:
        checks = []
        checks.extend(_startup_checks(connection))
        checks.extend(_business_checks(connection))
        checks.extend(_reporting_checks(connection))
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    blockers = []
    for category in ("startup", "business", "reporting"):
        failed = sum(1 for check in checks if check.category == category and check.status != "PASSED")
        if failed:
            blockers.append(f"{category} validation failed: {failed} check(s).")

    result = RuntimeDryRunResult(
        status=RuntimeDryRunStatus.BLOCKED if blockers else RuntimeDryRunStatus.READY_FOR_RUNTIME_CUTOVER,
        guard=guard,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        checks=checks,
        blockers=blockers,
    )
    write_runtime_dryrun_report(result, output_path)
    return result


def render_runtime_dryrun_report(result: RuntimeDryRunResult) -> str:
    startup = result.category_status("startup")
    business = result.category_status("business")
    reporting = result.category_status("reporting")
    lines = [
        "# PostgreSQL Runtime Dry-Run Report",
        "",
        "Phase: 5B.15L",
        "",
        "Controlled PostgreSQL runtime dry-run validation only. PostgreSQL runtime was not permanently enabled, SQLite data was not modified, application data was not written, migrations were not run, and production was not deployed.",
        "",
        "## Summary",
        "",
        f"- Status: {result.status.value}",
        f"- Started at: {result.started_at}",
        f"- Completed at: {result.completed_at}",
        f"- Checks performed: {len(result.checks)}",
        f"- Checks passed: {result.checks_passed}",
        f"- Checks failed: {result.checks_failed}",
        f"- Startup validation result: {startup}",
        f"- Business-module validation result: {business}",
        f"- Reporting validation result: {reporting}",
        f"- Runtime cutover readiness: {result.status.value}",
        "- PostgreSQL runtime permanently enabled: False",
        "- SQLite data modified: False",
        "- Production deployed: False",
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

    lines.extend(["", "## Checks Performed", "", "| Category | Check | Tables validated | Count returned | Result | Detail |", "|---|---|---|---:|---|---|"])
    for check in result.checks:
        count = "" if check.row_count is None else str(check.row_count)
        detail = check.error_message or check.detail
        lines.append(f"| {check.category} | {check.name} | `{check.table_name}` | {count} | {check.status} | {detail} |")

    lines.extend(["", "## Failures And Blockers", ""])
    if result.blockers:
        lines.extend(f"- {blocker}" for blocker in result.blockers)
    else:
        lines.append("- No failures or blockers found.")

    lines.extend(["", "## Final Readiness Status", ""])
    if result.status == RuntimeDryRunStatus.READY_FOR_RUNTIME_CUTOVER:
        lines.append("- READY_FOR_RUNTIME_CUTOVER")
        lines.append("- Runtime cutover can proceed after review and an explicit approved cutover action.")
    else:
        lines.append("- BLOCKED")
        lines.append("- Runtime cutover must not proceed until blockers are resolved and dry-run validation is rerun.")
    lines.append("")
    return "\n".join(lines)


def write_runtime_dryrun_report(result: RuntimeDryRunResult, output_path: Path = DEFAULT_OUTPUT_REPORT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_runtime_dryrun_report(result), encoding="utf-8")


if __name__ == "__main__":
    validation = execute_runtime_dryrun_validation()
    print(
        "PostgreSQL runtime dry-run validation: "
        f"status={validation.status.value} "
        f"checks={validation.checks_passed}/{len(validation.checks)} "
        f"startup={validation.category_status('startup')} "
        f"business={validation.category_status('business')} "
        f"reporting={validation.category_status('reporting')}"
    )
