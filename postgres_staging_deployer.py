"""PostgreSQL staging deployment CLI.

This entrypoint defaults to dry-run diagnostics. Staging schema apply is only
available behind explicit environment and CLI guards; runtime activation and
data migration are not implemented here.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit, urlunsplit

from postgres_deployment_executor import (
    APPLY_NOT_IMPLEMENTED_MESSAGE,
    format_phase_summary,
    run_deployment_dry_run,
)
from postgres_connection_probe import DEFAULT_PROBE_TIMEOUT_SECONDS, ProbeStatus, run_safe_connection_probe
from postgres_schema_executor import (
    build_blocked_schema_apply_audit_log,
    build_schema_execution_plan,
    build_schema_execution_audit_log,
    execute_schema_plan_with_database_url,
    format_schema_execution_plan,
    validate_schema_apply_guard,
)


REPO_ROOT = Path(__file__).resolve().parent
REQUIRED_ARTIFACTS = (
    REPO_ROOT / "reports" / "postgres_generated_schema.sql",
    REPO_ROOT / "reports" / "postgres_generated_schema_summary.md",
    REPO_ROOT / "reports" / "postgres_schema_validation_report.md",
    REPO_ROOT / "reports" / "postgres_deployment_dry_run_plan.md",
)
SKELETON_REPORT = REPO_ROOT / "reports" / "postgres_staging_deployment_skeleton.md"

DISPLAY_PHASES = (
    ("1", "migration metadata"),
    ("2", "companies/branches/users"),
    ("3", "accounting masters"),
    ("4", "inventory"),
    ("5", "documents"),
    ("6", "journals"),
    ("7", "POS"),
    ("8", "payroll/assets"),
    ("9", "audit/system"),
)


@dataclass
class DatabaseUrlDiagnostics:
    configured: bool
    redacted_url: str
    message: str


@dataclass
class ArtifactValidationResult:
    ok: bool
    missing: list[Path]
    present: list[Path]


def redact_database_url(database_url: str | None) -> str:
    if not database_url:
        return ""
    try:
        parts = urlsplit(database_url)
    except ValueError:
        return "<invalid-url>"
    if not parts.netloc:
        return "<redacted>"
    host_part = parts.hostname or ""
    if parts.port:
        host_part = f"{host_part}:{parts.port}"
    if parts.username:
        netloc = f"{parts.username}:***@{host_part}"
    else:
        netloc = host_part
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def validate_database_url(database_url: str | None = None) -> DatabaseUrlDiagnostics:
    value = os.environ.get("DATABASE_URL") if database_url is None else database_url
    if not value:
        return DatabaseUrlDiagnostics(
            configured=False,
            redacted_url="",
            message="DATABASE_URL is not configured. No connection will be attempted.",
        )
    return DatabaseUrlDiagnostics(
        configured=True,
        redacted_url=redact_database_url(value),
        message="DATABASE_URL is configured. Value is redacted and no connection will be attempted.",
    )


def validate_required_artifacts(required_artifacts: tuple[Path, ...] = REQUIRED_ARTIFACTS) -> ArtifactValidationResult:
    missing = [path for path in required_artifacts if not path.exists()]
    present = [path for path in required_artifacts if path.exists()]
    return ArtifactValidationResult(ok=not missing, missing=missing, present=present)


def format_phase_display() -> str:
    result = run_deployment_dry_run()
    return format_phase_summary(result)


def render_skeleton_report() -> str:
    artifact_list = "\n".join(f"- `{path.relative_to(REPO_ROOT)}`" for path in REQUIRED_ARTIFACTS)
    phase_list = "\n".join(f"{number}. {name}" for number, name in DISPLAY_PHASES)
    return f"""# PostgreSQL Staging Deployment Skeleton

Phase: 5B.13H

This command defaults to a staging deployment dry-run. Guarded schema apply is available only for staging when every explicit control passes. It does not connect to Supabase, enable PostgreSQL runtime, migrate data, seed data, deploy to production, or modify SQLite behavior.

## Supported CLI Options

- `--dry-run`: Default mode. Validates required offline artifacts, prints redacted database URL diagnostics, and displays planned deployment phases.
- `--apply`: Validates guarded staging schema apply controls and may execute schema statements only when all guards and the safe probe pass.
- `--confirm-schema-apply`: Required with `--apply` for guarded staging schema apply.
- `--probe`: Runs the guarded PostgreSQL connection probe diagnostics only. The probe remains disabled unless `ERP_ENABLE_POSTGRES_PROBE=1` is set.
- `--probe-timeout`: Optional connection timeout for `--probe`; defaults to `{DEFAULT_PROBE_TIMEOUT_SECONDS:g}` seconds.

## Validation Behavior

The skeleton validates that these artifacts exist before a dry-run display:

{artifact_list}

Missing artifacts are reported with clear file paths. No SQL is parsed for execution and no database calls are made.

The schema execution adapter parses `reports/postgres_generated_schema.sql` for dry-run planning. In apply mode it may execute schema statements only after staging guards, confirmation, and the safe connection probe pass.

## Phase Display

{phase_list}

## Safety Protections

- Default mode is dry-run.
- `--apply` validates guardrails and fails closed unless every required control passes.
- `--confirm-schema-apply` is required for guarded apply.
- `--probe` never calls deployment, migration, or schema creation paths.
- Schema execution never runs during dry-run and does not run automatically on startup.
- Database URL diagnostics redact passwords and do not print secrets.
- Dry-run mode does not use any PostgreSQL client, Supabase client, cursor, connection, or execute path.
- Probe mode is limited to the guarded connection probe framework and does not execute SQL.
- SQLite runtime behavior is not imported, called, or modified.

## Current Limitations

- Data migration is not implemented.
- Seed data deployment is not implemented.
- Migration history writes are not implemented.
- Post-deployment validation queries are not implemented.
- Production deployment is blocked by `ERP_ENVIRONMENT=staging`.
- Runtime cutover remains NO-GO.
"""


def write_skeleton_report(output_path: Path = SKELETON_REPORT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_skeleton_report(), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PostgreSQL staging deployment skeleton.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate artifacts and display phases. This is the default.")
    mode.add_argument("--apply", action="store_true", help="Guarded staging schema apply. Requires explicit environment and confirmation guards.")
    mode.add_argument("--probe", action="store_true", help="Run guarded PostgreSQL connection probe diagnostics only.")
    parser.add_argument(
        "--confirm-schema-apply",
        action="store_true",
        help="Required future confirmation for schema apply. SQL execution remains blocked in this phase.",
    )
    parser.add_argument(
        "--probe-timeout",
        type=float,
        default=DEFAULT_PROBE_TIMEOUT_SECONDS,
        help=f"Connection timeout for --probe in seconds. Defaults to {DEFAULT_PROBE_TIMEOUT_SECONDS:g}.",
    )
    return parser


def run_probe(timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS, output_stream=sys.stdout, error_stream=sys.stderr) -> int:
    result = run_safe_connection_probe(timeout_seconds=timeout_seconds)
    diagnostics = result.diagnostics
    stream = error_stream if result.status is ProbeStatus.PROBE_FAILED else output_stream

    print("PostgreSQL safe connection probe diagnostics.", file=stream)
    print(f"Status: {result.status.value}", file=stream)
    print(f"Probe enabled: {diagnostics['probe_enabled']}", file=stream)
    print(f"DATABASE_URL present: {result.database_url_present}", file=stream)
    if diagnostics["database_url_redacted"]:
        print(f"DATABASE_URL: {diagnostics['database_url_redacted']}", file=stream)
    print(f"Driver detected: {result.driver_detected}", file=stream)
    if diagnostics["driver_name"]:
        print(f"Driver: {diagnostics['driver_name']}", file=stream)
    print(f"Timeout seconds: {diagnostics['timeout_seconds']:g}", file=stream)
    print(f"Probe attempted: {result.probe_attempted}", file=stream)
    print(f"Probe succeeded: {result.probe_succeeded}", file=stream)
    if result.error_message:
        print(f"Message: {result.error_message}", file=stream)
    print("No deployment, migration, schema creation, data migration, SQL execution, or runtime activation was run.", file=stream)
    return 1 if result.status is ProbeStatus.PROBE_FAILED else 0


def run_apply(confirm_schema_apply: bool = False, output_stream=sys.stdout, error_stream=sys.stderr) -> int:
    try:
        plan = build_schema_execution_plan()
        statements_planned = len(plan.statements)
    except FileNotFoundError:
        statements_planned = 0
    diagnostics = validate_schema_apply_guard(
        apply_flag=True,
        confirmation_flag=confirm_schema_apply,
        statements_planned=statements_planned,
    )

    print("PostgreSQL guarded schema apply diagnostics.", file=error_stream)
    print(f"Status: {diagnostics.status.value}", file=error_stream)
    print(f"Blocked: {diagnostics.blocked}", file=error_stream)
    print(f"All guards passed: {diagnostics.all_guards_passed}", file=error_stream)
    print(f"Statements planned: {diagnostics.statements_planned}", file=error_stream)
    print(f"Schema path: {diagnostics.schema_path}", file=error_stream)
    print("Guard results:", file=error_stream)
    for guard_name, passed in diagnostics.guard_results.items():
        print(f"- {guard_name}: {passed}", file=error_stream)

    if diagnostics.blocked:
        audit_log = build_blocked_schema_apply_audit_log(diagnostics)
        print("Audit log:", file=error_stream)
        print(f"- deployment_id: {audit_log.deployment_id}", file=error_stream)
        print(f"- events: {len(audit_log.events)}", file=error_stream)
        for event in audit_log.events:
            print(f"- event_status: {event.status.value}", file=error_stream)
            print(f"- rollback_required: {event.rollback_required}", file=error_stream)
        print(diagnostics.message, file=error_stream)
        print(APPLY_NOT_IMPLEMENTED_MESSAGE, file=error_stream)
        print("No SQL executed. No schema created. No migrations run.", file=error_stream)
        return 1

    probe_result = run_safe_connection_probe()
    print(f"Probe status: {probe_result.status.value}", file=error_stream)
    if probe_result.diagnostics.get("database_url_redacted"):
        print(f"DATABASE_URL: {probe_result.diagnostics['database_url_redacted']}", file=error_stream)
    if probe_result.status is not ProbeStatus.PROBE_SUCCEEDED:
        audit_log = build_blocked_schema_apply_audit_log(diagnostics)
        print("Audit log:", file=error_stream)
        print(f"- deployment_id: {audit_log.deployment_id}", file=error_stream)
        print(f"- events: {len(audit_log.events)}", file=error_stream)
        print(f"Schema apply blocked: {probe_result.error_message}", file=error_stream)
        print("No SQL executed. No schema created. No migrations run.", file=error_stream)
        return 1

    database_url = os.environ.get("DATABASE_URL", "")
    driver_name = str(probe_result.diagnostics.get("driver_name", ""))
    result = execute_schema_plan_with_database_url(
        plan,
        database_url=database_url,
        driver_name=driver_name,
    )
    print("Audit log:", file=error_stream)
    if result.audit_log is not None:
        print(f"- deployment_id: {result.audit_log.deployment_id}", file=error_stream)
        print(f"- events: {len(result.audit_log.events)}", file=error_stream)
    print(f"Statements executed: {result.statements_executed}/{result.statements_planned}", file=error_stream)
    print(f"Rollback attempted: {result.rollback_attempted}", file=error_stream)
    print(f"Rollback succeeded: {result.rollback_succeeded}", file=error_stream)
    if result.ok:
        print("Schema apply completed for staging. PostgreSQL runtime remains disabled.", file=error_stream)
        return 0
    print(f"Schema apply failed: {result.error_message}", file=error_stream)
    return 1


def run_dry_run(output_stream=sys.stdout, error_stream=sys.stderr) -> int:
    artifacts = validate_required_artifacts()
    if not artifacts.ok:
        print("Missing required PostgreSQL deployment artifacts:", file=error_stream)
        for path in artifacts.missing:
            print(f"- {path.relative_to(REPO_ROOT)}", file=error_stream)
        return 2

    diagnostics = validate_database_url()
    write_skeleton_report()
    print("PostgreSQL staging deployment skeleton dry-run.", file=output_stream)
    print(diagnostics.message, file=output_stream)
    if diagnostics.redacted_url:
        print(f"DATABASE_URL: {diagnostics.redacted_url}", file=output_stream)
    print("Required artifacts present:", file=output_stream)
    for path in artifacts.present:
        print(f"- {path.relative_to(REPO_ROOT)}", file=output_stream)
    print("", file=output_stream)
    print(format_phase_display(), file=output_stream)
    print("", file=output_stream)
    schema_plan = build_schema_execution_plan()
    audit_log = build_schema_execution_audit_log(schema_plan)
    print(format_schema_execution_plan(schema_plan), file=output_stream)
    print(f"Audit events planned: {len(audit_log.events)}", file=output_stream)
    print("", file=output_stream)
    print("No SQL executed. No database connection attempted.", file=output_stream)
    return 0


def main(argv: list[str] | None = None, output_stream=sys.stdout, error_stream=sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.apply:
        return run_apply(confirm_schema_apply=args.confirm_schema_apply, output_stream=output_stream, error_stream=error_stream)
    if args.probe:
        return run_probe(timeout_seconds=args.probe_timeout, output_stream=output_stream, error_stream=error_stream)
    return run_dry_run(output_stream=output_stream, error_stream=error_stream)


if __name__ == "__main__":
    raise SystemExit(main())
