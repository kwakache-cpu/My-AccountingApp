"""Read-only PostgreSQL runtime readiness validation.

This validator checks the staged PostgreSQL schema and copied data before any
runtime cutover. It performs SELECT-only metadata and smoke-count checks. It
does not enable PostgreSQL runtime, modify SQLite, write application data, run
migrations, or deploy production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from importlib import import_module
import os
from pathlib import Path
from typing import Any

from postgres_connection_adapter import redact_database_url
from postgres_connection_probe import DEFAULT_DRIVER_PREFERENCE, detect_postgres_driver
from postgres_postdeploy_validator import (
    ExpectedExecutableIndex,
    ExpectedForeignKey,
    parse_executable_indexes,
    parse_expected_foreign_keys,
    parse_generated_tables,
)
from sqlite_to_postgres_migration import quote_identifier


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA_SQL = REPO_ROOT / "reports" / "postgres_generated_schema.sql"
DEFAULT_OUTPUT_REPORT = REPO_ROOT / "reports" / "postgres_runtime_readiness_report.md"

STARTUP_METADATA_TABLES = ("schema_version", "database_identity", "migration_history")
AUTHENTICATION_TABLES = ("users",)
COMPANY_CONFIGURATION_TABLES = (
    "companies",
    "branches",
    "system_settings",
    "company_subscriptions",
    "subscription_plan_settings",
    "branch_type_catalog",
    "branch_type_module_defaults",
    "branch_module_grants",
)
CHART_OF_ACCOUNTS_TABLES = ("chart_of_accounts",)
POS_TABLES = ("cashier_closings", "pos_returns", "pos_sale_lines", "pos_sales", "pos_suspended_sales")
ACCOUNTING_TABLES = (
    "accounting_periods",
    "accounts_payable",
    "bank_accounts",
    "bill_lines",
    "bills",
    "chart_of_accounts",
    "customer_transactions",
    "invoice_lines",
    "invoices",
    "journal_entries",
    "journal_lines",
    "payment_allocations",
    "payments",
    "supplier_transactions",
    "transactions",
    "vouchers",
)
AUDIT_HISTORY_TABLES = ("audit_logs", "system_logs", "migration_logs", "migration_history", "schema_version", "database_identity")
SMOKE_CHECK_TABLES = {
    "company_count": "companies",
    "user_count": "users",
    "customer_count": "customers",
    "inventory_count": "inventory",
    "chart_of_accounts_count": "chart_of_accounts",
    "journal_count": "journal_entries",
}


class RuntimeReadinessStatus(str, Enum):
    READY_FOR_RUNTIME_CUTOVER = "READY_FOR_RUNTIME_CUTOVER"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RuntimeReadinessGuard:
    blocked: bool
    guard_results: dict[str, bool]
    message: str
    redacted_database_url: str = ""
    driver_name: str = ""


@dataclass(frozen=True)
class ObjectCheck:
    category: str
    object_name: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    table_name: str
    row_count: int
    status: str


@dataclass
class RuntimeReadinessResult:
    status: RuntimeReadinessStatus
    guard: RuntimeReadinessGuard
    started_at: str
    completed_at: str
    tables_checked: int = 0
    tables_passed: int = 0
    indexes_checked: int = 0
    indexes_passed: int = 0
    foreign_keys_checked: int = 0
    foreign_keys_passed: int = 0
    table_checks: list[ObjectCheck] = field(default_factory=list)
    index_checks: list[ObjectCheck] = field(default_factory=list)
    foreign_key_checks: list[ObjectCheck] = field(default_factory=list)
    group_checks: list[ObjectCheck] = field(default_factory=list)
    smoke_checks: list[SmokeCheck] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_runtime_readiness_guard(
    *,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    schema_sql_path: Path = DEFAULT_SCHEMA_SQL,
    driver_preference: tuple[str, ...] = DEFAULT_DRIVER_PREFERENCE,
) -> RuntimeReadinessGuard:
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "") if database_url is None else database_url
    driver_name, driver_detected = detect_postgres_driver(driver_preference)
    guard_results = {
        "ERP_ENVIRONMENT_is_staging": env.get("ERP_ENVIRONMENT") == "staging",
        "DATABASE_URL_present": bool(value),
        "schema_artifact_present": schema_sql_path.exists(),
        "postgres_driver_available": driver_detected,
    }
    blocked = not all(guard_results.values())
    return RuntimeReadinessGuard(
        blocked=blocked,
        guard_results=guard_results,
        message=(
            "Runtime readiness validation is blocked until staging environment, DATABASE_URL, schema artifact, and PostgreSQL driver guards pass."
            if blocked
            else "Runtime readiness guards passed for read-only staging checks."
        ),
        redacted_database_url=redact_database_url(value),
        driver_name=driver_name,
    )


def open_runtime_readiness_connection(database_url: str, driver_name: str, connect_timeout_seconds: int = 5):
    driver = import_module(driver_name)
    return driver.connect(database_url, connect_timeout=connect_timeout_seconds)


def _fetchone_count(connection: Any, sql: str, params: dict[str, Any] | tuple[Any, ...] = ()) -> int:
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return int((row[0] if row else 0) or 0)
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


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


def _index_exists(connection: Any, index: ExpectedExecutableIndex) -> bool:
    return _fetchone_count(
        connection,
        """
        SELECT COUNT(*)
        FROM pg_indexes
        WHERE schemaname = current_schema()
          AND tablename = %(table_name)s
          AND indexname = %(index_name)s
        """,
        {"table_name": index.table, "index_name": index.index},
    ) == 1


def _foreign_key_exists(connection: Any, foreign_key: ExpectedForeignKey) -> bool:
    return _fetchone_count(
        connection,
        """
        SELECT COUNT(*)
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.table_schema = current_schema()
          AND tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name = %(table_name)s
          AND kcu.column_name = %(column_name)s
          AND ccu.table_name = %(foreign_table_name)s
          AND ccu.column_name = %(foreign_column_name)s
        """,
        {
            "table_name": foreign_key.table,
            "column_name": foreign_key.column,
            "foreign_table_name": foreign_key.references_table,
            "foreign_column_name": foreign_key.references_column,
        },
    ) >= 1


def _table_row_count(connection: Any, table_name: str) -> int:
    return _fetchone_count(connection, f"SELECT COUNT(*) FROM {quote_identifier(table_name)}")


def _group_checks(connection: Any, group_name: str, tables: tuple[str, ...]) -> list[ObjectCheck]:
    checks: list[ObjectCheck] = []
    for table_name in tables:
        exists = _table_exists(connection, table_name)
        checks.append(ObjectCheck(group_name, table_name, "PASSED" if exists else "FAILED"))
    return checks


def execute_runtime_readiness_validation(
    *,
    output_path: Path = DEFAULT_OUTPUT_REPORT,
    schema_sql_path: Path = DEFAULT_SCHEMA_SQL,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    connector: Any | None = None,
    connect_timeout_seconds: int = 5,
) -> RuntimeReadinessResult:
    started_at = datetime.now(UTC).isoformat()
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "") if database_url is None else database_url
    guard = validate_runtime_readiness_guard(environ=dict(env), database_url=value, schema_sql_path=schema_sql_path)
    if guard.blocked:
        result = RuntimeReadinessResult(
            status=RuntimeReadinessStatus.BLOCKED,
            guard=guard,
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
            blockers=[guard.message],
        )
        write_runtime_readiness_report(result, output_path)
        return result

    schema_sql = _read_text(schema_sql_path)
    expected_tables = parse_generated_tables(schema_sql)
    expected_indexes = parse_executable_indexes(schema_sql)
    expected_foreign_keys = parse_expected_foreign_keys(schema_sql)
    connect = connector or open_runtime_readiness_connection
    connection = connect(value, guard.driver_name, connect_timeout_seconds)
    try:
        table_checks = [
            ObjectCheck("runtime_table", table_name, "PASSED" if _table_exists(connection, table_name) else "FAILED")
            for table_name in expected_tables
        ]
        index_checks = [
            ObjectCheck("runtime_index", index.index, "PASSED" if _index_exists(connection, index) else "FAILED", f"table={index.table}")
            for index in expected_indexes
        ]
        foreign_key_checks = [
            ObjectCheck(
                "runtime_foreign_key",
                f"{fk.table}.{fk.column}->{fk.references_table}.{fk.references_column}",
                "PASSED" if _foreign_key_exists(connection, fk) else "FAILED",
            )
            for fk in expected_foreign_keys
        ]
        group_checks = []
        for group_name, tables in (
            ("startup_metadata_tables", STARTUP_METADATA_TABLES),
            ("authentication_tables", AUTHENTICATION_TABLES),
            ("company_configuration_tables", COMPANY_CONFIGURATION_TABLES),
            ("chart_of_accounts_tables", CHART_OF_ACCOUNTS_TABLES),
            ("pos_tables", POS_TABLES),
            ("accounting_tables", ACCOUNTING_TABLES),
            ("audit_history_tables", AUDIT_HISTORY_TABLES),
        ):
            group_checks.extend(_group_checks(connection, group_name, tables))
        smoke_checks = []
        for check_name, table_name in SMOKE_CHECK_TABLES.items():
            count = _table_row_count(connection, table_name)
            smoke_checks.append(SmokeCheck(check_name, table_name, count, "PASSED" if count > 0 else "FAILED"))
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    blockers: list[str] = []
    for label, checks in (
        ("table checks", table_checks),
        ("index checks", index_checks),
        ("foreign key checks", foreign_key_checks),
        ("runtime table group checks", group_checks),
    ):
        failed = sum(1 for check in checks if check.status != "PASSED")
        if failed:
            blockers.append(f"{label} failed: {failed}.")
    failed_smoke = sum(1 for check in smoke_checks if check.status != "PASSED")
    if failed_smoke:
        blockers.append(f"runtime smoke checks failed: {failed_smoke}.")

    result = RuntimeReadinessResult(
        status=RuntimeReadinessStatus.BLOCKED if blockers else RuntimeReadinessStatus.READY_FOR_RUNTIME_CUTOVER,
        guard=guard,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        tables_checked=len(table_checks),
        tables_passed=sum(1 for check in table_checks if check.status == "PASSED"),
        indexes_checked=len(index_checks),
        indexes_passed=sum(1 for check in index_checks if check.status == "PASSED"),
        foreign_keys_checked=len(foreign_key_checks),
        foreign_keys_passed=sum(1 for check in foreign_key_checks if check.status == "PASSED"),
        table_checks=table_checks,
        index_checks=index_checks,
        foreign_key_checks=foreign_key_checks,
        group_checks=group_checks,
        smoke_checks=smoke_checks,
        blockers=blockers,
    )
    write_runtime_readiness_report(result, output_path)
    return result


def render_runtime_readiness_report(result: RuntimeReadinessResult) -> str:
    lines = [
        "# PostgreSQL Runtime Readiness Report",
        "",
        "Phase: 5B.15J",
        "",
        "Read-only PostgreSQL runtime readiness validation only. No PostgreSQL runtime enablement, SQLite modification, application data writes, migration activity, or production deployment was attempted.",
        "",
        "## Summary",
        "",
        f"- Status: {result.status.value}",
        f"- Started at: {result.started_at}",
        f"- Completed at: {result.completed_at}",
        f"- Tables checked: {result.tables_checked}",
        f"- Tables passed: {result.tables_passed}",
        f"- Indexes checked: {result.indexes_checked}",
        f"- Indexes passed: {result.indexes_passed}",
        f"- FK checks: {result.foreign_keys_checked}",
        f"- FK checks passed: {result.foreign_keys_passed}",
        f"- Smoke checks: {len(result.smoke_checks)}",
        f"- Smoke checks passed: {sum(1 for check in result.smoke_checks if check.status == 'PASSED')}",
        "- Runtime remains disabled: True",
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

    lines.extend(["", "## Runtime Smoke Checks", "", "| Check | Table | Row count | Result |", "|---|---|---:|---|"])
    for check in result.smoke_checks:
        lines.append(f"| {check.name} | `{check.table_name}` | {check.row_count} | {check.status} |")

    lines.extend(["", "## Runtime Table Groups", "", "| Category | Table | Result |", "|---|---|---|"])
    for check in result.group_checks:
        lines.append(f"| {check.category} | `{check.object_name}` | {check.status} |")

    lines.extend(["", "## Required Runtime Tables", "", "| Table | Result |", "|---|---|"])
    for check in result.table_checks:
        lines.append(f"| `{check.object_name}` | {check.status} |")

    lines.extend(["", "## Required Runtime Indexes", ""])
    if result.index_checks:
        lines.append("| Index | Result | Detail |")
        lines.append("|---|---|---|")
        for check in result.index_checks:
            lines.append(f"| `{check.object_name}` | {check.status} | {check.detail} |")
    else:
        lines.append("- No executable runtime indexes are present in the current generated schema artifact; captured index comments remain manual-review artifacts.")

    lines.extend(["", "## Required Runtime Foreign Keys", "", "| Foreign key | Result |", "|---|---|"])
    for check in result.foreign_key_checks:
        lines.append(f"| `{check.object_name}` | {check.status} |")

    lines.extend(["", "## Final Status", ""])
    if result.blockers:
        lines.extend(f"- {blocker}" for blocker in result.blockers)
        lines.append("- BLOCKED")
    else:
        lines.append("- READY_FOR_RUNTIME_CUTOVER")
        lines.append("- PostgreSQL runtime remains disabled until explicit cutover approval.")
    lines.append("")
    return "\n".join(lines)


def write_runtime_readiness_report(result: RuntimeReadinessResult, output_path: Path = DEFAULT_OUTPUT_REPORT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_runtime_readiness_report(result), encoding="utf-8")


if __name__ == "__main__":
    validation = execute_runtime_readiness_validation()
    print(
        "PostgreSQL runtime readiness validation: "
        f"status={validation.status.value} "
        f"tables={validation.tables_passed}/{validation.tables_checked} "
        f"indexes={validation.indexes_passed}/{validation.indexes_checked} "
        f"fks={validation.foreign_keys_passed}/{validation.foreign_keys_checked} "
        f"smoke={sum(1 for item in validation.smoke_checks if item.status == 'PASSED')}/{len(validation.smoke_checks)}"
    )
