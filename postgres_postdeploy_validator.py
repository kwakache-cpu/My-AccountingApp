"""PostgreSQL post-deployment validation framework.

The default plan-generation path reads existing report artifacts only. The
Phase 5B.14O execution path is guarded for staging and runs read-only metadata
SELECT checks only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from importlib import import_module
import os
from pathlib import Path
import re
from typing import Any, Callable

from postgres_connection_adapter import redact_database_url
from postgres_connection_probe import DEFAULT_DRIVER_PREFERENCE, detect_postgres_driver
from postgres_validation_queries import ValidationQuery, ValidationSeverity, build_postgres_validation_query_set


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA_SQL = REPO_ROOT / "reports" / "postgres_generated_schema.sql"
DEFAULT_SCHEMA_VALIDATION_REPORT = REPO_ROOT / "reports" / "postgres_schema_validation_report.md"
DEFAULT_DEPLOYMENT_DRY_RUN_PLAN = REPO_ROOT / "reports" / "postgres_deployment_dry_run_plan.md"
DEFAULT_OUTPUT_REPORT = REPO_ROOT / "reports" / "postgres_postdeploy_validation_plan.md"
DEFAULT_RESULTS_REPORT = REPO_ROOT / "reports" / "postgres_postdeploy_validation_results.md"

VALIDATION_CATEGORIES = (
    "Schema validation",
    "Table validation",
    "Column validation",
    "Index validation",
    "FK validation",
    "Seed data validation",
    "Migration history validation",
    "Runtime readiness validation",
)

EXPECTED_MIGRATION_TABLES = ("migration_history", "schema_version", "database_identity")
EXPECTED_SEED_TABLES = (
    "branch_type_catalog",
    "branch_type_module_defaults",
    "subscription_plan_settings",
    "system_settings",
    "companies",
    "branches",
    "users",
)
REQUIRED_SYSTEM_TABLES = ("companies", "branches", "users", "system_settings", "schema_version", "database_identity", "migration_history")
FORBIDDEN_VALIDATION_SQL_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "CREATE",
    "ALTER",
    "DROP",
    "TRUNCATE",
    "MERGE",
    "UPSERT",
    "COPY",
    "GRANT",
    "REVOKE",
)


@dataclass(frozen=True)
class ValidationCategory:
    name: str
    objective: str
    evidence_sources: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedForeignKey:
    table: str
    column: str
    references_table: str
    references_column: str


@dataclass(frozen=True)
class ExpectedColumn:
    table: str
    column: str


@dataclass(frozen=True)
class ExpectedExecutableIndex:
    table: str
    index: str


@dataclass(frozen=True)
class ValidationChecklistStage:
    stage: str
    name: str
    checks: tuple[str, ...]


@dataclass
class ExpectedInventory:
    tables: list[str]
    indexes: list[str]
    foreign_keys: list[ExpectedForeignKey]
    migration_tables: list[str]
    seed_tables: list[str]


@dataclass
class PostDeployValidationPlan:
    categories: list[ValidationCategory]
    inventory: ExpectedInventory
    checklist_stages: list[ValidationChecklistStage]
    source_schema_score: str = ""
    source_deployment_readiness: str = ""
    notes: list[str] = field(default_factory=list)


class PostDeployValidationStatus(str, Enum):
    BLOCKED = "BLOCKED"
    READY = "READY"
    PASSED = "PASSED"
    FAILED = "FAILED"


class PostDeployValidationCheckStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    BLOCKED = "BLOCKED"


@dataclass
class PostDeployValidationGuard:
    status: PostDeployValidationStatus
    blocked: bool
    guard_results: dict[str, bool]
    message: str
    redacted_database_url: str = ""
    driver_name: str = ""


@dataclass(frozen=True)
class PostDeployValidationCheck:
    query_id: str
    category: str
    name: str
    sql: str
    parameters: dict[str, Any] = field(default_factory=dict)
    minimum_rows: int = 1
    severity: ValidationSeverity = ValidationSeverity.ERROR


@dataclass
class PostDeployValidationCheckResult:
    check: PostDeployValidationCheck
    status: PostDeployValidationCheckStatus
    row_count: int = 0
    error_message: str = ""


@dataclass
class PostDeployValidationExecutionResult:
    status: PostDeployValidationStatus
    guard: PostDeployValidationGuard
    checks_planned: int
    checks_executed: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    results: tuple[PostDeployValidationCheckResult, ...] = ()
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str = ""
    error_message: str = ""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_generated_tables(schema_sql: str) -> list[str]:
    tables = re.findall(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b",
        schema_sql,
        flags=re.IGNORECASE,
    )
    return sorted(set(tables))


def parse_captured_indexes(schema_sql: str) -> list[str]:
    created = re.findall(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b", schema_sql, flags=re.IGNORECASE)
    captured = re.findall(r"^-- INDEX\s+([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+", schema_sql, flags=re.MULTILINE)
    return sorted(set(created + captured))


def parse_executable_indexes(schema_sql: str) -> list[ExpectedExecutableIndex]:
    indexes: list[ExpectedExecutableIndex] = []
    pattern = re.compile(
        r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(schema_sql):
        indexes.append(ExpectedExecutableIndex(table=match.group(2), index=match.group(1)))
    return sorted(indexes, key=lambda item: (item.table, item.index))


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


def parse_expected_columns(schema_sql: str) -> list[ExpectedColumn]:
    columns: list[ExpectedColumn] = []
    for table, block in _extract_create_table_blocks(schema_sql).items():
        open_index = block.find("(")
        close_index = block.rfind(")")
        if open_index < 0 or close_index <= open_index:
            continue
        body = block[open_index + 1 : close_index]
        for item in _split_sql_items(body):
            if re.match(r"^(?:CONSTRAINT|FOREIGN\s+KEY|PRIMARY\s+KEY|UNIQUE|CHECK)\b", item, flags=re.IGNORECASE):
                continue
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s+", item)
            if match:
                columns.append(ExpectedColumn(table=table, column=match.group(1)))
    return sorted(columns, key=lambda item: (item.table, item.column))


def parse_expected_foreign_keys(schema_sql: str) -> list[ExpectedForeignKey]:
    foreign_keys: list[ExpectedForeignKey] = []
    for table, block in _extract_create_table_blocks(schema_sql).items():
        for match in re.finditer(
            r"FOREIGN\s+KEY\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s+REFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
            block,
            flags=re.IGNORECASE,
        ):
            foreign_keys.append(
                ExpectedForeignKey(
                    table=table,
                    column=match.group(1),
                    references_table=match.group(2),
                    references_column=match.group(3),
                )
            )
    return sorted(foreign_keys, key=lambda fk: (fk.table, fk.column, fk.references_table, fk.references_column))


def is_select_only_sql(sql: str) -> bool:
    stripped = sql.strip().rstrip(";")
    if not re.match(r"^(?:WITH\b.*?\bSELECT\b|SELECT\b)", stripped, flags=re.IGNORECASE | re.DOTALL):
        return False
    scrubbed = re.sub(r"'(?:''|[^'])*'", "''", stripped)
    return not any(re.search(rf"\b{keyword}\b", scrubbed, flags=re.IGNORECASE) for keyword in FORBIDDEN_VALIDATION_SQL_KEYWORDS)


def validate_select_only_checks(checks: tuple[PostDeployValidationCheck, ...]) -> None:
    unsafe = [check.query_id for check in checks if not is_select_only_sql(check.sql)]
    if unsafe:
        raise ValueError("Post-deployment validation contains non-SELECT checks: " + ", ".join(unsafe))


def _query_template(category: str) -> ValidationQuery:
    query_set = build_postgres_validation_query_set()
    return query_set.queries_by_category[category][0]


def _check_id(prefix: str, *parts: str) -> str:
    raw = "_".join((prefix, *parts))
    return re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_").lower()


def build_postdeploy_validation_checks(schema_sql: str) -> tuple[PostDeployValidationCheck, ...]:
    plan = build_postdeploy_validation_plan(schema_sql)
    checks: list[PostDeployValidationCheck] = []

    schema_query = _query_template("schema_exists")
    checks.append(
        PostDeployValidationCheck(
            query_id=schema_query.query_id,
            category=schema_query.category,
            name=schema_query.name,
            sql=schema_query.sql,
            severity=schema_query.expectation.severity,
        )
    )

    table_query = _query_template("table_exists")
    for table in plan.inventory.tables:
        checks.append(
            PostDeployValidationCheck(
                query_id=_check_id("table_exists", table),
                category="table_exists",
                name=f"Expected table exists: {table}",
                sql=table_query.sql,
                parameters={"table_name": table},
                severity=table_query.expectation.severity,
            )
        )

    column_query = _query_template("column_exists")
    for column in parse_expected_columns(schema_sql):
        checks.append(
            PostDeployValidationCheck(
                query_id=_check_id("column_exists", column.table, column.column),
                category="column_exists",
                name=f"Expected column exists: {column.table}.{column.column}",
                sql=column_query.sql,
                parameters={"table_name": column.table, "column_name": column.column},
                severity=column_query.expectation.severity,
            )
        )

    index_query = _query_template("index_exists")
    for index in parse_executable_indexes(schema_sql):
        checks.append(
            PostDeployValidationCheck(
                query_id=_check_id("index_exists", index.table, index.index),
                category="index_exists",
                name=f"Expected executable index exists: {index.index}",
                sql=index_query.sql,
                parameters={"table_name": index.table, "index_name": index.index},
                severity=index_query.expectation.severity,
            )
        )

    fk_query = _query_template("fk_exists")
    for foreign_key in plan.inventory.foreign_keys:
        checks.append(
            PostDeployValidationCheck(
                query_id=_check_id("fk_exists", foreign_key.table, foreign_key.column, foreign_key.references_table),
                category="fk_exists",
                name=f"Expected FK exists: {foreign_key.table}.{foreign_key.column} -> {foreign_key.references_table}.{foreign_key.references_column}",
                sql=fk_query.sql,
                parameters={
                    "table_name": foreign_key.table,
                    "column_name": foreign_key.column,
                    "foreign_table_name": foreign_key.references_table,
                    "foreign_column_name": foreign_key.references_column,
                },
                severity=fk_query.expectation.severity,
            )
        )

    for table in plan.inventory.migration_tables:
        checks.append(
            PostDeployValidationCheck(
                query_id=_check_id("migration_table_exists", table),
                category="migration_history_exists",
                name=f"Expected migration/system table exists: {table}",
                sql=table_query.sql,
                parameters={"table_name": table},
                severity=ValidationSeverity.CRITICAL,
            )
        )

    for table in REQUIRED_SYSTEM_TABLES:
        if table in plan.inventory.tables:
            checks.append(
                PostDeployValidationCheck(
                    query_id=_check_id("required_system_table_exists", table),
                    category="table_exists",
                    name=f"Required system table exists: {table}",
                    sql=table_query.sql,
                    parameters={"table_name": table},
                    severity=ValidationSeverity.CRITICAL,
                )
            )

    planned = tuple(checks)
    validate_select_only_checks(planned)
    return planned


def validate_postdeploy_execution_guard(
    *,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    schema_sql_path: Path = DEFAULT_SCHEMA_SQL,
    driver_preference: tuple[str, ...] = DEFAULT_DRIVER_PREFERENCE,
) -> PostDeployValidationGuard:
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
    return PostDeployValidationGuard(
        status=PostDeployValidationStatus.BLOCKED if blocked else PostDeployValidationStatus.READY,
        blocked=blocked,
        guard_results=guard_results,
        message=(
            "Post-deployment validation is blocked until staging environment, DATABASE_URL, schema artifact, and PostgreSQL driver guards pass."
            if blocked
            else "Post-deployment validation guards passed for read-only staging checks."
        ),
        redacted_database_url=redact_database_url(value),
        driver_name=driver_name,
    )


def open_postdeploy_validation_connection(database_url: str, driver_name: str, connect_timeout_seconds: int = 5):
    driver = import_module(driver_name)
    return driver.connect(database_url, connect_timeout=max(1, int(connect_timeout_seconds)))


ConnectionFactory = Callable[[str, str, int], Any]


def _execute_validation_check(connection: Any, check: PostDeployValidationCheck) -> int:
    execute = getattr(connection, "execute", None)
    if callable(execute):
        cursor = execute(check.sql, check.parameters)
        fetchall = getattr(cursor, "fetchall", None)
        return len(fetchall()) if callable(fetchall) else 0
    cursor_factory = getattr(connection, "cursor", None)
    if not callable(cursor_factory):
        raise RuntimeError("Validation connection does not expose execute() or cursor().")
    cursor = cursor_factory()
    try:
        cursor.execute(check.sql, check.parameters)
        fetchall = getattr(cursor, "fetchall", None)
        return len(fetchall()) if callable(fetchall) else 0
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


def execute_postdeploy_validation(
    *,
    schema_sql_path: Path = DEFAULT_SCHEMA_SQL,
    output_path: Path = DEFAULT_RESULTS_REPORT,
    environ: dict[str, str] | None = None,
    database_url: str | None = None,
    connector: ConnectionFactory | None = None,
    connect_timeout_seconds: int = 5,
) -> PostDeployValidationExecutionResult:
    started_at = datetime.now(UTC).isoformat()
    env = os.environ if environ is None else environ
    value = env.get("DATABASE_URL", "") if database_url is None else database_url
    guard = validate_postdeploy_execution_guard(
        environ=dict(env),
        database_url=value,
        schema_sql_path=schema_sql_path,
    )
    checks: tuple[PostDeployValidationCheck, ...] = ()
    if schema_sql_path.exists():
        checks = build_postdeploy_validation_checks(_read_text(schema_sql_path))

    if guard.blocked:
        result = PostDeployValidationExecutionResult(
            status=PostDeployValidationStatus.BLOCKED,
            guard=guard,
            checks_planned=len(checks),
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
            error_message=guard.message,
        )
        write_postdeploy_validation_results(result, output_path)
        return result

    connect = connector or open_postdeploy_validation_connection
    connection = connect(value, guard.driver_name, connect_timeout_seconds)
    check_results: list[PostDeployValidationCheckResult] = []
    try:
        for check in checks:
            try:
                row_count = _execute_validation_check(connection, check)
                status = (
                    PostDeployValidationCheckStatus.PASSED
                    if row_count >= check.minimum_rows
                    else PostDeployValidationCheckStatus.FAILED
                )
                check_results.append(PostDeployValidationCheckResult(check=check, status=status, row_count=row_count))
            except Exception as exc:  # pragma: no cover - exact driver exceptions vary.
                check_results.append(
                    PostDeployValidationCheckResult(
                        check=check,
                        status=PostDeployValidationCheckStatus.ERROR,
                        error_message=f"{type(exc).__name__}: {exc}",
                    )
                )
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    failed = sum(1 for item in check_results if item.status is not PostDeployValidationCheckStatus.PASSED)
    result = PostDeployValidationExecutionResult(
        status=PostDeployValidationStatus.PASSED if failed == 0 else PostDeployValidationStatus.FAILED,
        guard=guard,
        checks_planned=len(checks),
        checks_executed=len(check_results),
        checks_passed=sum(1 for item in check_results if item.status is PostDeployValidationCheckStatus.PASSED),
        checks_failed=failed,
        results=tuple(check_results),
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
        error_message="" if failed == 0 else "One or more read-only post-deployment validation checks failed.",
    )
    write_postdeploy_validation_results(result, output_path)
    return result


def render_postdeploy_validation_results(result: PostDeployValidationExecutionResult) -> str:
    lines = [
        "# PostgreSQL Post-Deployment Validation Results",
        "",
        "Phase: 5B.14O",
        "",
        "Read-only staging validation only. No INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, data migration, runtime enablement, production deployment, Supabase API call, or SQLite behavior change was attempted.",
        "",
        "## Summary",
        "",
        f"- Status: {result.status.value}",
        f"- Started at: {result.started_at}",
        f"- Completed at: {result.completed_at}",
        f"- Checks planned: {result.checks_planned}",
        f"- Checks executed: {result.checks_executed}",
        f"- Checks passed: {result.checks_passed}",
        f"- Checks failed: {result.checks_failed}",
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
    lines.extend(f"- {name}: {passed}" for name, passed in result.guard.guard_results.items())
    lines.extend(["", "## Check Results", ""])
    if result.results:
        for item in result.results:
            lines.append(
                f"- {item.status.value}: {item.check.query_id} ({item.check.category}) rows={item.row_count}"
                + (f" error={item.error_message}" if item.error_message else "")
            )
    else:
        lines.append("- No checks executed.")
    lines.extend(
        [
            "",
            "## Remaining Blockers",
            "",
            "- PostgreSQL runtime remains disabled.",
            "- Data migration remains blocked.",
            "- Production deployment remains blocked.",
            "- Application SQL portability work remains required before runtime cutover.",
            "",
        ]
    )
    return "\n".join(lines)


def write_postdeploy_validation_results(
    result: PostDeployValidationExecutionResult,
    output_path: Path = DEFAULT_RESULTS_REPORT,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_postdeploy_validation_results(result), encoding="utf-8")


def build_validation_categories() -> list[ValidationCategory]:
    return [
        ValidationCategory("Schema validation", "Confirm schema artifact was applied in the intended staging scope.", ("schema deploy log", "table count query output")),
        ValidationCategory("Table validation", "Confirm every expected table exists after deployment.", ("generated schema inventory", "information_schema.tables snapshot")),
        ValidationCategory("Column validation", "Confirm required columns, primary keys, and nullable/default metadata match the generated artifact.", ("generated schema SQL", "information_schema.columns snapshot")),
        ValidationCategory("Index validation", "Confirm all expected PostgreSQL indexes exist after explicit index definitions are added.", ("generated index inventory", "pg_indexes snapshot")),
        ValidationCategory("FK validation", "Confirm foreign key constraints exist and reference expected parent tables/columns.", ("generated FK inventory", "information_schema constraints snapshot")),
        ValidationCategory("Seed data validation", "Confirm required seed tables contain expected baseline rows.", ("seed manifest", "staging row-count snapshot")),
        ValidationCategory("Migration history validation", "Confirm deployment phases are recorded in PostgreSQL migration metadata.", ("migration history table", "deployment log")),
        ValidationCategory("Runtime readiness validation", "Confirm startup gate remains safe until deployment and validation are complete.", ("startup diagnostics", "configuration review")),
    ]


def build_checklist_stages() -> list[ValidationChecklistStage]:
    return [
        ValidationChecklistStage(
            stage="Stage 1",
            name="Schema deployment validation",
            checks=(
                "Confirm all expected tables exist in the staging schema.",
                "Confirm primary keys exist for every generated table.",
                "Confirm expected foreign keys are present or intentionally deferred.",
                "Confirm expected indexes are present after index placeholders are replaced.",
                "Confirm generated schema validation report still has no forbidden SQLite syntax.",
            ),
        ),
        ValidationChecklistStage(
            stage="Stage 2",
            name="Seed deployment validation",
            checks=(
                "Confirm seed tables exist before seed writes are attempted.",
                "Confirm branch type catalog rows are present.",
                "Confirm subscription plan settings rows are present.",
                "Confirm system settings and baseline company/branch/user seed strategy is approved.",
            ),
        ),
        ValidationChecklistStage(
            stage="Stage 3",
            name="Runtime activation validation",
            checks=(
                "Confirm DATABASE_URL is configured only in staging and remains redacted in logs.",
                "Confirm ERP_ENABLE_POSTGRES_RUNTIME remains disabled until schema and seed checks pass.",
                "Confirm startup gate diagnostics show PostgreSQL readiness criteria are satisfied before any relaxation.",
                "Confirm application SQL portability blockers are reviewed before runtime activation.",
            ),
        ),
        ValidationChecklistStage(
            stage="Stage 4",
            name="Cutover validation",
            checks=(
                "Confirm data migration validation has passed.",
                "Confirm accounting, POS, inventory, payroll, and reporting smoke tests pass on staging PostgreSQL.",
                "Confirm rollback plan and production SQLite preservation plan are approved.",
                "Confirm final cutover decision remains NO-GO until deployment, migration, and runtime tests all pass.",
            ),
        ),
    ]


def _parse_schema_validation_summary(report_text: str) -> tuple[str, str]:
    score_match = re.search(r"- Score:\s*([0-9]+/100)", report_text)
    readiness_match = re.search(r"- Deployment readiness:\s*\*\*([A-Z]+)\*\*", report_text)
    return (
        score_match.group(1) if score_match else "unknown",
        readiness_match.group(1) if readiness_match else "unknown",
    )


def build_expected_inventory(schema_sql: str) -> ExpectedInventory:
    tables = parse_generated_tables(schema_sql)
    table_set = set(tables)
    return ExpectedInventory(
        tables=tables,
        indexes=parse_captured_indexes(schema_sql),
        foreign_keys=parse_expected_foreign_keys(schema_sql),
        migration_tables=[table for table in EXPECTED_MIGRATION_TABLES if table in table_set],
        seed_tables=[table for table in EXPECTED_SEED_TABLES if table in table_set],
    )


def build_postdeploy_validation_plan(
    schema_sql: str,
    schema_validation_report: str = "",
    deployment_dry_run_plan: str = "",
) -> PostDeployValidationPlan:
    score, readiness = _parse_schema_validation_summary(schema_validation_report)
    notes: list[str] = []
    if "Deployment readiness: **YELLOW**" in deployment_dry_run_plan:
        notes.append("Deployment dry-run readiness is YELLOW; this framework remains planning-only.")
    return PostDeployValidationPlan(
        categories=build_validation_categories(),
        inventory=build_expected_inventory(schema_sql),
        checklist_stages=build_checklist_stages(),
        source_schema_score=score,
        source_deployment_readiness=readiness,
        notes=notes,
    )


def render_postdeploy_validation_plan(plan: PostDeployValidationPlan) -> str:
    lines = [
        "# PostgreSQL Post-Deployment Validation Plan",
        "",
        "Phase: 5B.13I",
        "",
        "Offline framework definition only. No database connection, SQL execution, schema deployment, PostgreSQL runtime enablement, or data migration was attempted.",
        "",
        "## Source Artifact Summary",
        "",
        f"- Source schema validation score: {plan.source_schema_score}",
        f"- Source deployment readiness: {plan.source_deployment_readiness}",
        f"- Expected tables: {len(plan.inventory.tables)}",
        f"- Expected indexes: {len(plan.inventory.indexes)}",
        f"- Expected FKs: {len(plan.inventory.foreign_keys)}",
        f"- Expected migration tables: {len(plan.inventory.migration_tables)}",
        f"- Expected seed tables: {len(plan.inventory.seed_tables)}",
        "",
        "## Validation Categories",
        "",
    ]
    for category in plan.categories:
        lines.extend(
            [
                f"### {category.name}",
                "",
                f"- Objective: {category.objective}",
                "- Evidence sources: " + ", ".join(category.evidence_sources),
                "",
            ]
        )

    lines.extend(["## Expected Tables", ""])
    lines.extend(f"- {table}" for table in plan.inventory.tables)

    lines.extend(["", "## Expected Indexes", ""])
    lines.extend(f"- {index}" for index in plan.inventory.indexes)
    if not plan.inventory.indexes:
        lines.append("- None captured.")

    lines.extend(["", "## Expected FKs", ""])
    lines.extend(
        f"- {fk.table}.{fk.column} -> {fk.references_table}.{fk.references_column}"
        for fk in plan.inventory.foreign_keys
    )
    if not plan.inventory.foreign_keys:
        lines.append("- None captured.")

    lines.extend(["", "## Expected Migration Tables", ""])
    lines.extend(f"- {table}" for table in plan.inventory.migration_tables)

    lines.extend(["", "## Expected Seed Tables", ""])
    lines.extend(f"- {table}" for table in plan.inventory.seed_tables)

    lines.extend(["", "## Validation Checklists", ""])
    for stage in plan.checklist_stages:
        lines.extend([f"### {stage.stage}: {stage.name}", ""])
        lines.extend(f"- {check}" for check in stage.checks)
        lines.append("")

    lines.extend(["## Notes", ""])
    if plan.notes:
        lines.extend(f"- {note}" for note in plan.notes)
    else:
        lines.append("- Framework generated from offline artifacts.")

    lines.extend(
        [
            "",
            "## Current Limitations",
            "",
            "- Plan generation does not query staging PostgreSQL.",
            "- Validation execution is available separately through the guarded Phase 5B.14O read-only path.",
            "- Seed manifests and migration-history write behavior still need implementation.",
            "- Runtime cutover remains NO-GO.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_postdeploy_validation_plan(
    schema_sql_path: Path = DEFAULT_SCHEMA_SQL,
    schema_validation_report_path: Path = DEFAULT_SCHEMA_VALIDATION_REPORT,
    deployment_dry_run_plan_path: Path = DEFAULT_DEPLOYMENT_DRY_RUN_PLAN,
    output_path: Path = DEFAULT_OUTPUT_REPORT,
) -> PostDeployValidationPlan:
    schema_sql = _read_text(schema_sql_path)
    schema_validation_report = _read_text(schema_validation_report_path)
    deployment_dry_run_plan = _read_text(deployment_dry_run_plan_path)
    plan = build_postdeploy_validation_plan(schema_sql, schema_validation_report, deployment_dry_run_plan)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_postdeploy_validation_plan(plan), encoding="utf-8")
    return plan


if __name__ == "__main__":
    generated = generate_postdeploy_validation_plan()
    print(
        "Generated PostgreSQL post-deployment validation framework: "
        f"categories={len(generated.categories)} "
        f"tables={len(generated.inventory.tables)} "
        f"indexes={len(generated.inventory.indexes)} "
        f"foreign_keys={len(generated.inventory.foreign_keys)}"
    )
