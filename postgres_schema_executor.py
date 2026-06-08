"""Guarded PostgreSQL schema execution adapter.

This module prepares future staging schema execution, but the public deployment
CLI remains non-executing. Real connections are intentionally out of scope:
tests may inject a mock connection to exercise execution and rollback behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA_PATH = REPO_ROOT / "reports" / "postgres_generated_schema.sql"
EXECUTION_BLOCKED_MESSAGE = "Schema execution is blocked outside injected mock-connection tests."
SCHEMA_APPLY_BLOCKED_MESSAGE = "Schema apply is blocked before SQL execution."
SCHEMA_APPLY_ENABLE_ENV_VAR = "ERP_ENABLE_POSTGRES_SCHEMA_APPLY"
STAGING_ENVIRONMENT = "staging"
DEFAULT_AUDIT_PHASE_ID = "schema-apply"
MAX_STATEMENT_PREVIEW_CHARS = 160


class SchemaApplyStatus(str, Enum):
    BLOCKED = "BLOCKED"


class SchemaExecutionAuditStatus(str, Enum):
    PLANNED = "PLANNED"
    BLOCKED = "BLOCKED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SchemaApplyGuard:
    apply_flag: bool
    confirmation_flag: bool
    schema_apply_enabled: bool
    environment_is_staging: bool
    database_url_present: bool
    schema_file_exists: bool

    @property
    def all_required_conditions_passed(self) -> bool:
        return (
            self.apply_flag
            and self.confirmation_flag
            and self.schema_apply_enabled
            and self.environment_is_staging
            and self.database_url_present
            and self.schema_file_exists
        )


@dataclass(frozen=True)
class SchemaApplyDiagnostics:
    status: SchemaApplyStatus
    guard: SchemaApplyGuard
    guard_results: dict[str, bool]
    blocked: bool = True
    all_guards_passed: bool = False
    statements_planned: int = 0
    schema_path: str = ""
    message: str = SCHEMA_APPLY_BLOCKED_MESSAGE


@dataclass(frozen=True)
class SchemaExecutionPlan:
    source_path: Path
    statements: tuple[str, ...]
    dry_run: bool = True
    execution_allowed: bool = False
    rollback_modeled: bool = True
    message: str = "Dry-run only: schema statements parsed but not executed."


@dataclass(frozen=True)
class SchemaExecutionResult:
    ok: bool
    dry_run: bool
    execution_allowed: bool
    statements_planned: int
    statements_executed: int = 0
    rollback_attempted: bool = False
    rollback_succeeded: bool = False
    error_message: str = ""
    executed_statements: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SchemaExecutionAuditEvent:
    deployment_id: str
    phase_id: str
    statement_index: int
    statement_preview: str
    status: SchemaExecutionAuditStatus
    started_at: str
    completed_at: str
    duration_ms: int
    error_message: str = ""
    rollback_required: bool = False


@dataclass(frozen=True)
class SchemaExecutionAuditLog:
    deployment_id: str
    phase_id: str
    events: tuple[SchemaExecutionAuditEvent, ...] = field(default_factory=tuple)


def build_schema_apply_guard_diagnostics(
    *,
    apply_flag: bool,
    confirmation_flag: bool,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    environ: dict[str, str] | None = None,
    statements_planned: int = 0,
) -> SchemaApplyDiagnostics:
    env = os.environ if environ is None else environ
    guard = SchemaApplyGuard(
        apply_flag=apply_flag,
        confirmation_flag=confirmation_flag,
        schema_apply_enabled=env.get(SCHEMA_APPLY_ENABLE_ENV_VAR) == "1",
        environment_is_staging=env.get("ERP_ENVIRONMENT") == STAGING_ENVIRONMENT,
        database_url_present=bool(env.get("DATABASE_URL")),
        schema_file_exists=schema_path.exists(),
    )
    guard_results = {
        "explicit_apply_flag": guard.apply_flag,
        "explicit_confirm_schema_apply_flag": guard.confirmation_flag,
        SCHEMA_APPLY_ENABLE_ENV_VAR: guard.schema_apply_enabled,
        "ERP_ENVIRONMENT_is_staging": guard.environment_is_staging,
        "DATABASE_URL_present": guard.database_url_present,
        "schema_file_exists": guard.schema_file_exists,
    }
    status = SchemaApplyStatus.BLOCKED
    message = (
        "All schema apply guards passed, but SQL execution is still disabled in this phase."
        if guard.all_required_conditions_passed
        else SCHEMA_APPLY_BLOCKED_MESSAGE
    )
    return SchemaApplyDiagnostics(
        status=status,
        guard=guard,
        guard_results=guard_results,
        blocked=True,
        all_guards_passed=guard.all_required_conditions_passed,
        statements_planned=statements_planned,
        schema_path=str(schema_path),
        message=message,
    )


def validate_schema_apply_guard(
    *,
    apply_flag: bool,
    confirmation_flag: bool,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    environ: dict[str, str] | None = None,
    statements_planned: int = 0,
) -> SchemaApplyDiagnostics:
    return build_schema_apply_guard_diagnostics(
        apply_flag=apply_flag,
        confirmation_flag=confirmation_flag,
        schema_path=schema_path,
        environ=environ,
        statements_planned=statements_planned,
    )


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_deployment_id() -> str:
    return f"schema-apply-{uuid4().hex}"


def build_statement_preview(statement: str, max_chars: int = MAX_STATEMENT_PREVIEW_CHARS) -> str:
    preview = " ".join(statement.split())
    preview = re.sub(
        r"(?i)(password|secret|token|key)(\s*=\s*)'[^']*'",
        r"\1\2'***'",
        preview,
    )
    preview = re.sub(
        r"(?i)(password|secret|token|key)(\s*=\s*)\"[^\"]*\"",
        lambda match: f'{match.group(1)}{match.group(2)}"***"',
        preview,
    )
    if len(preview) <= max_chars:
        return preview
    return f"{preview[: max_chars - 3]}..."


def build_schema_execution_audit_log(
    plan: SchemaExecutionPlan,
    *,
    deployment_id: str | None = None,
    phase_id: str = DEFAULT_AUDIT_PHASE_ID,
) -> SchemaExecutionAuditLog:
    audit_deployment_id = deployment_id or build_deployment_id()
    events: list[SchemaExecutionAuditEvent] = []
    for index, statement in enumerate(plan.statements, start=1):
        timestamp = _utc_now_iso()
        events.append(
            SchemaExecutionAuditEvent(
                deployment_id=audit_deployment_id,
                phase_id=phase_id,
                statement_index=index,
                statement_preview=build_statement_preview(statement),
                status=SchemaExecutionAuditStatus.PLANNED,
                started_at=timestamp,
                completed_at=timestamp,
                duration_ms=0,
                error_message="",
                rollback_required=False,
            )
        )
    return SchemaExecutionAuditLog(
        deployment_id=audit_deployment_id,
        phase_id=phase_id,
        events=tuple(events),
    )


def build_blocked_schema_apply_audit_log(
    diagnostics: SchemaApplyDiagnostics,
    *,
    deployment_id: str | None = None,
    phase_id: str = DEFAULT_AUDIT_PHASE_ID,
) -> SchemaExecutionAuditLog:
    audit_deployment_id = deployment_id or build_deployment_id()
    timestamp = _utc_now_iso()
    event = SchemaExecutionAuditEvent(
        deployment_id=audit_deployment_id,
        phase_id=phase_id,
        statement_index=0,
        statement_preview="Schema apply blocked before SQL execution.",
        status=SchemaExecutionAuditStatus.BLOCKED,
        started_at=timestamp,
        completed_at=timestamp,
        duration_ms=0,
        error_message=diagnostics.message,
        rollback_required=False,
    )
    return SchemaExecutionAuditLog(
        deployment_id=audit_deployment_id,
        phase_id=phase_id,
        events=(event,),
    )


def read_schema_sql(schema_path: Path = DEFAULT_SCHEMA_PATH) -> str:
    return schema_path.read_text(encoding="utf-8")


def _starts_dollar_quote(sql: str, index: int) -> str:
    if sql[index] != "$":
        return ""
    end = sql.find("$", index + 1)
    if end == -1:
        return ""
    tag = sql[index : end + 1]
    inner = tag[1:-1]
    if inner and not (inner[0].isalpha() or inner[0] == "_"):
        return ""
    if any(not (char.isalnum() or char == "_") for char in inner):
        return ""
    return tag


def split_sql_statements(sql: str) -> tuple[str, ...]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    dollar_quote_tag = ""
    index = 0

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if in_line_comment:
            if char in "\r\n":
                in_line_comment = False
                current.append(char)
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue

        if dollar_quote_tag:
            current.append(char)
            if sql.startswith(dollar_quote_tag, index):
                current.extend(dollar_quote_tag[1:])
                index += len(dollar_quote_tag)
                dollar_quote_tag = ""
            else:
                index += 1
            continue

        if not in_single_quote and not in_double_quote:
            if char == "-" and next_char == "-":
                in_line_comment = True
                index += 2
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                index += 2
                continue
            if char == "$":
                tag = _starts_dollar_quote(sql, index)
                if tag:
                    dollar_quote_tag = tag
                    current.append(tag)
                    index += len(tag)
                    continue

        current.append(char)

        if char == "'" and not in_double_quote:
            if in_single_quote and next_char == "'":
                current.append(next_char)
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []

        index += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return tuple(statements)


def build_schema_execution_plan(schema_path: Path = DEFAULT_SCHEMA_PATH) -> SchemaExecutionPlan:
    sql = read_schema_sql(schema_path)
    statements = split_sql_statements(sql)
    return SchemaExecutionPlan(source_path=schema_path, statements=statements)


def _is_mock_connection(connection: Any) -> bool:
    return connection.__class__.__module__.startswith("unittest.mock")


def execute_schema_plan(
    plan: SchemaExecutionPlan,
    connection: Any | None = None,
    *,
    allow_mock_execution: bool = False,
) -> SchemaExecutionResult:
    if not allow_mock_execution or connection is None or not _is_mock_connection(connection):
        return SchemaExecutionResult(
            ok=False,
            dry_run=plan.dry_run,
            execution_allowed=False,
            statements_planned=len(plan.statements),
            error_message=EXECUTION_BLOCKED_MESSAGE,
        )

    executed: list[str] = []
    try:
        for statement in plan.statements:
            connection.execute(statement)
            executed.append(statement)
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()
    except Exception as exc:
        rollback_attempted = False
        rollback_succeeded = False
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback_attempted = True
            try:
                rollback()
                rollback_succeeded = True
            except Exception:
                rollback_succeeded = False
        return SchemaExecutionResult(
            ok=False,
            dry_run=False,
            execution_allowed=True,
            statements_planned=len(plan.statements),
            statements_executed=len(executed),
            rollback_attempted=rollback_attempted,
            rollback_succeeded=rollback_succeeded,
            error_message=f"Mock schema execution failed: {type(exc).__name__}: {exc}",
            executed_statements=tuple(executed),
        )

    return SchemaExecutionResult(
        ok=True,
        dry_run=False,
        execution_allowed=True,
        statements_planned=len(plan.statements),
        statements_executed=len(executed),
        executed_statements=tuple(executed),
    )


def format_schema_execution_plan(plan: SchemaExecutionPlan) -> str:
    lines = [
        "PostgreSQL schema execution adapter dry-run:",
        f"Source: {plan.source_path.relative_to(REPO_ROOT)}",
        f"Statements planned: {len(plan.statements)}",
        f"Execution allowed: {plan.execution_allowed}",
        f"Rollback modeled: {plan.rollback_modeled}",
        plan.message,
    ]
    return "\n".join(lines)
