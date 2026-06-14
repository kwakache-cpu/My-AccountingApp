"""Controlled PostgreSQL runtime activation smoke test.

The smoke test is staging/local only and performs no writes. It verifies that
runtime configuration selects PostgreSQL, SQLite bootstrap is not selected, a
PostgreSQL connection opens, and core read paths return counts.
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
DEFAULT_OUTPUT_REPORT = REPO_ROOT / "reports" / "postgres_runtime_smoke_test_report.md"
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FORBIDDEN_SQL = ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE", "MERGE", "COPY")
READ_TABLES = (
    "companies",
    "users",
    "chart_of_accounts",
    "customers",
    "inventory",
    "journal_entries",
)


class RuntimeSmokeStatus(str, Enum):
    READY_FOR_STREAMLIT_SECRETS_CUTOVER = "READY_FOR_STREAMLIT_SECRETS_CUTOVER"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RuntimeSmokeGuard:
    blocked: bool
    guard_results: dict[str, bool]
    message: str
    redacted_database_url: str = ""
    driver_name: str = ""


@dataclass(frozen=True)
class RuntimeSmokeCheck:
    category: str
    name: str
    status: str
    count: int | None = None
    detail: str = ""
    error_message: str = ""


@dataclass
class RuntimeSmokeResult:
    status: RuntimeSmokeStatus
    guard: RuntimeSmokeGuard
    started_at: str
    completed_at: str
    active_backend: str = ""
    configured_backend: str = ""
    startup_result: str = ""
    startup_stage: str = ""
    sqlite_bootstrap_blocked: bool = False
    checks: list[RuntimeSmokeCheck] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    @property
    def checks_passed(self) -> int:
        return sum(1 for check in self.checks if check.status == "PASSED")

    @property
    def checks_failed(self) -> int:
        return sum(1 for check in self.checks if check.status != "PASSED")


def quote_identifier(identifier: str) -> str:
    if not SAFE_IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return f'"{identifier}"'


def validate_select_only(sql: str) -> None:
    scrubbed = re.sub(r"'(?:''|[^'])*'", "''", sql)
    if not re.match(r"^\s*SELECT\b", scrubbed, flags=re.IGNORECASE):
        raise ValueError(f"Smoke test query is not SELECT-only: {sql}")
    for keyword in FORBIDDEN_SQL:
        if re.search(rf"\b{keyword}\b", scrubbed, flags=re.IGNORECASE):
            raise ValueError(f"Smoke test query contains forbidden keyword {keyword}: {sql}")


def validate_runtime_smoke_guard(
    *,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    driver_preference: tuple[str, ...] = DEFAULT_DRIVER_PREFERENCE,
) -> RuntimeSmokeGuard:
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "") if database_url is None else database_url
    driver_name, driver_detected = detect_postgres_driver(driver_preference)
    guard_results = {
        "DB_BACKEND_is_postgres": str(env.get("DB_BACKEND", "")).strip().lower() in {"postgres", "postgresql", "supabase"},
        "ERP_ENABLE_POSTGRES_RUNTIME_is_enabled": str(env.get("ERP_ENABLE_POSTGRES_RUNTIME", "")).strip().lower() in {"1", "true", "yes", "on"},
        "ERP_ENVIRONMENT_is_staging": env.get("ERP_ENVIRONMENT") == "staging",
        "DATABASE_URL_present": bool(value),
        "postgres_driver_available": driver_detected,
    }
    blocked = not all(guard_results.values())
    return RuntimeSmokeGuard(
        blocked=blocked,
        guard_results=guard_results,
        message=(
            "Runtime smoke test is blocked until PostgreSQL runtime, staging environment, DATABASE_URL, and driver guards pass."
            if blocked
            else "Runtime smoke test guards passed for controlled staging/local PostgreSQL checks."
        ),
        redacted_database_url=redact_database_url(value),
        driver_name=driver_name,
    )


def open_runtime_smoke_connection(database_url: str, driver_name: str, connect_timeout_seconds: int = 5):
    driver = import_module(driver_name)
    return driver.connect(database_url, connect_timeout=connect_timeout_seconds)


def _fetchone(connection: Any, sql: str) -> tuple[Any, ...] | None:
    validate_select_only(sql)
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        return cursor.fetchone()
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


def _count(connection: Any, sql: str) -> int:
    row = _fetchone(connection, sql)
    return int((row[0] if row else 0) or 0)


def _read_check(connection: Any, table_name: str) -> RuntimeSmokeCheck:
    try:
        count = _count(connection, f"SELECT COUNT(*) FROM {quote_identifier(table_name)}")
        status = "PASSED" if count > 0 else "FAILED"
        return RuntimeSmokeCheck("read_path", f"{table_name} can be read", status, count, "SELECT COUNT(*) succeeded")
    except Exception as exc:
        return RuntimeSmokeCheck("read_path", f"{table_name} can be read", "FAILED", None, error_message=str(exc))


def _connection_check(connection: Any) -> RuntimeSmokeCheck:
    try:
        value = _count(connection, "SELECT 1")
        return RuntimeSmokeCheck("connection", "PostgreSQL connection opens", "PASSED" if value == 1 else "FAILED", value)
    except Exception as exc:
        return RuntimeSmokeCheck("connection", "PostgreSQL connection opens", "FAILED", None, error_message=str(exc))


def _dashboard_check(connection: Any) -> RuntimeSmokeCheck:
    sql = """
    SELECT
        (SELECT COUNT(*) FROM companies)
      + (SELECT COUNT(*) FROM users)
      + (SELECT COUNT(*) FROM customers)
      + (SELECT COUNT(*) FROM inventory)
      + (SELECT COUNT(*) FROM chart_of_accounts)
      + (SELECT COUNT(*) FROM journal_entries)
    """
    try:
        count = _count(connection, sql)
        return RuntimeSmokeCheck("dashboard", "dashboard source counts work", "PASSED" if count > 0 else "FAILED", count)
    except Exception as exc:
        return RuntimeSmokeCheck("dashboard", "dashboard source counts work", "FAILED", None, error_message=str(exc))


def _startup_check(database_module: Any) -> tuple[str, str, bool, RuntimeSmokeCheck]:
    try:
        diagnostics = database_module.get_startup_backend_diagnostics()
        startup_status = database_module.startup_database()
        active_backend = str(diagnostics.get("active_backend") or "")
        stage = str(startup_status.get("stage") or startup_status.get("startup_mode") or "")
        sqlite_blocked = not bool(diagnostics.get("should_run_sqlite_startup"))
        passed = (
            active_backend == "postgres"
            and sqlite_blocked
            and startup_status.get("stage") == "postgres_runtime_startup"
            and not startup_status.get("bootstrap_needed")
            and not startup_status.get("recovery_attempted")
        )
        return (
            active_backend,
            stage,
            sqlite_blocked,
            RuntimeSmokeCheck(
                "startup",
                "startup stays off SQLite bootstrap",
                "PASSED" if passed else "FAILED",
                None,
                f"stage={stage}; should_run_sqlite_startup={diagnostics.get('should_run_sqlite_startup')}",
            ),
        )
    except Exception as exc:
        return "", "", False, RuntimeSmokeCheck("startup", "startup stays off SQLite bootstrap", "FAILED", None, error_message=str(exc))


def execute_runtime_smoke_test(
    *,
    output_path: Path = DEFAULT_OUTPUT_REPORT,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    connector: Any | None = None,
    database_module: Any | None = None,
    connect_timeout_seconds: int = 5,
) -> RuntimeSmokeResult:
    started_at = datetime.now(UTC).isoformat()
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "") if database_url is None else database_url
    guard = validate_runtime_smoke_guard(environ=dict(env), database_url=value)
    if guard.blocked:
        result = RuntimeSmokeResult(
            status=RuntimeSmokeStatus.BLOCKED,
            guard=guard,
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
            blockers=[guard.message],
        )
        write_runtime_smoke_report(result, output_path)
        return result

    if database_module is None:
        database_module = import_module("database")

    configured_backend = str(getattr(database_module, "get_configured_db_backend")())
    active_backend, startup_stage, sqlite_bootstrap_blocked, startup_check = _startup_check(database_module)
    checks = [startup_check]
    connect = connector or open_runtime_smoke_connection
    connection = connect(value, guard.driver_name, connect_timeout_seconds)
    try:
        checks.append(_connection_check(connection))
        checks.extend(_read_check(connection, table_name) for table_name in READ_TABLES)
        checks.append(_dashboard_check(connection))
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    blockers = []
    if configured_backend != "postgres":
        blockers.append("Configured backend is not postgres.")
    if active_backend != "postgres":
        blockers.append("Active backend is not postgres.")
    if not sqlite_bootstrap_blocked:
        blockers.append("SQLite schema bootstrap was not blocked.")
    failed = sum(1 for check in checks if check.status != "PASSED")
    if failed:
        blockers.append(f"Runtime smoke checks failed: {failed}.")

    result = RuntimeSmokeResult(
        status=RuntimeSmokeStatus.BLOCKED if blockers else RuntimeSmokeStatus.READY_FOR_STREAMLIT_SECRETS_CUTOVER,
        guard=guard,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        active_backend=active_backend,
        configured_backend=configured_backend,
        startup_result=startup_check.status,
        startup_stage=startup_stage,
        sqlite_bootstrap_blocked=sqlite_bootstrap_blocked,
        checks=checks,
        blockers=blockers,
    )
    write_runtime_smoke_report(result, output_path)
    return result


def render_runtime_smoke_report(result: RuntimeSmokeResult) -> str:
    lines = [
        "# PostgreSQL Runtime Smoke Test Report",
        "",
        "Phase: 5B.15N",
        "",
        "Controlled staging/local PostgreSQL runtime activation smoke test only. No commit, push, SQLite modification, SQLite backup deletion, or production deployment was performed.",
        "",
        "## Summary",
        "",
        f"- Status: {result.status.value}",
        f"- Started at: {result.started_at}",
        f"- Completed at: {result.completed_at}",
        f"- Configured backend: {result.configured_backend or 'unknown'}",
        f"- Active backend: {result.active_backend or 'unknown'}",
        f"- Startup result: {result.startup_result or 'BLOCKED'}",
        f"- Startup stage: {result.startup_stage or 'not-run'}",
        f"- SQLite bootstrap blocked: {result.sqlite_bootstrap_blocked}",
        f"- Read checks passed: {result.checks_passed}",
        f"- Read checks failed: {result.checks_failed}",
        f"- Streamlit secrets cutover can proceed: {result.status == RuntimeSmokeStatus.READY_FOR_STREAMLIT_SECRETS_CUTOVER}",
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

    lines.extend(["", "## Checks", "", "| Category | Check | Count | Result | Detail |", "|---|---|---:|---|---|"])
    for check in result.checks:
        count = "" if check.count is None else str(check.count)
        detail = check.error_message or check.detail
        lines.append(f"| {check.category} | {check.name} | {count} | {check.status} | {detail} |")

    lines.extend(["", "## Blockers", ""])
    if result.blockers:
        lines.extend(f"- {blocker}" for blocker in result.blockers)
    else:
        lines.append("- No blockers found.")

    lines.extend(["", "## Rollback Instruction", ""])
    lines.append("- If any smoke check regresses, remove or unset `ERP_ENABLE_POSTGRES_RUNTIME`, set `DB_BACKEND=sqlite`, remove or restore `DATABASE_URL` to the prior configuration, redeploy the previous known-good app, and verify SQLite company/user/customer/inventory/chart/journal counts.")
    lines.append("")
    return "\n".join(lines)


def write_runtime_smoke_report(result: RuntimeSmokeResult, output_path: Path = DEFAULT_OUTPUT_REPORT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_runtime_smoke_report(result), encoding="utf-8")


if __name__ == "__main__":
    smoke_result = execute_runtime_smoke_test()
    print(
        "PostgreSQL runtime smoke test: "
        f"status={smoke_result.status.value} "
        f"active_backend={smoke_result.active_backend or 'unknown'} "
        f"startup={smoke_result.startup_result or 'BLOCKED'} "
        f"checks={smoke_result.checks_passed}/{len(smoke_result.checks)}"
    )
