"""PostgreSQL staging deployment CLI skeleton.

This entrypoint is intentionally non-executing. It validates offline artifacts,
prints redacted diagnostics, and displays the planned deployment phases. Actual
PostgreSQL deployment is not implemented in this phase.
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
from postgres_connection_probe import ProbeStatus, run_safe_connection_probe


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

This phase adds a staging deployment command skeleton only. It does not deploy schema, connect to Supabase, execute SQL, enable PostgreSQL runtime, migrate data, or modify SQLite behavior.

## Supported CLI Options

- `--dry-run`: Default mode. Validates required offline artifacts, prints redacted database URL diagnostics, and displays planned deployment phases.
- `--apply`: Fails immediately with `{APPLY_NOT_IMPLEMENTED_MESSAGE}` and exits non-zero.
- `--probe`: Runs the guarded PostgreSQL connection probe diagnostics only. The probe remains disabled unless `ERP_ENABLE_POSTGRES_PROBE=1` is set.

## Validation Behavior

The skeleton validates that these artifacts exist before a dry-run display:

{artifact_list}

Missing artifacts are reported with clear file paths. No SQL is parsed for execution and no database calls are made.

## Phase Display

{phase_list}

## Safety Protections

- Default mode is dry-run.
- `--apply` is blocked unconditionally.
- `--probe` never calls deployment, migration, or schema creation paths.
- Database URL diagnostics redact passwords and do not print secrets.
- Dry-run mode does not use any PostgreSQL client, Supabase client, cursor, connection, or execute path.
- Probe mode is limited to the guarded connection probe framework and does not execute SQL.
- SQLite runtime behavior is not imported, called, or modified.

## Current Limitations

- Actual PostgreSQL deployment execution is not implemented.
- Migration history writes are not implemented.
- Seed data deployment is not implemented.
- Post-deployment validation queries are not implemented.
- Runtime cutover remains NO-GO.
"""


def write_skeleton_report(output_path: Path = SKELETON_REPORT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_skeleton_report(), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PostgreSQL staging deployment skeleton.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate artifacts and display phases. This is the default.")
    mode.add_argument("--apply", action="store_true", help="Blocked: deployment execution is not implemented.")
    mode.add_argument("--probe", action="store_true", help="Run guarded PostgreSQL connection probe diagnostics only.")
    return parser


def run_probe(output_stream=sys.stdout, error_stream=sys.stderr) -> int:
    result = run_safe_connection_probe()
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
    print(f"Probe attempted: {result.probe_attempted}", file=stream)
    print(f"Probe succeeded: {result.probe_succeeded}", file=stream)
    if result.error_message:
        print(f"Message: {result.error_message}", file=stream)
    print("No deployment, migration, schema creation, data migration, SQL execution, or runtime activation was run.", file=stream)
    return 1 if result.status is ProbeStatus.PROBE_FAILED else 0


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
    print("No SQL executed. No database connection attempted.", file=output_stream)
    return 0


def main(argv: list[str] | None = None, output_stream=sys.stdout, error_stream=sys.stderr) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.apply:
        print(APPLY_NOT_IMPLEMENTED_MESSAGE, file=error_stream)
        return 1
    if args.probe:
        return run_probe(output_stream=output_stream, error_stream=error_stream)
    return run_dry_run(output_stream=output_stream, error_stream=error_stream)


if __name__ == "__main__":
    raise SystemExit(main())
