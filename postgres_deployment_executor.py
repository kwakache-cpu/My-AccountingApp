"""Non-executing PostgreSQL deployment executor skeleton.

The executor models future deployment phases, dry-run output, and migration
history events only. It does not connect to any database and does not execute
SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from postgres_deployment_planner import PHASE_DEFINITIONS
from postgres_migration_history import (
    MigrationHistory,
    create_dry_run_history,
)


REPO_ROOT = Path(__file__).resolve().parent
APPLY_NOT_IMPLEMENTED_MESSAGE = "PostgreSQL deployment execution is not implemented yet."


@dataclass(frozen=True)
class DeploymentStep:
    step_id: str
    description: str
    status: str = "planned"
    execution_allowed: bool = False


@dataclass(frozen=True)
class DeploymentPhase:
    phase_id: str
    name: str
    tables: tuple[str, ...]
    steps: tuple[DeploymentStep, ...]
    execution_allowed: bool = False


@dataclass(frozen=True)
class DeploymentResult:
    ok: bool
    mode: str
    execution_allowed: bool
    blocked: bool
    message: str
    phases: tuple[DeploymentPhase, ...] = field(default_factory=tuple)
    planned_step_count: int = 0
    migration_history: MigrationHistory | None = None


def _phase_number(phase_id: str) -> str:
    return phase_id.replace("Phase ", "").strip()


def _build_phase_steps(phase: str, name: str, tables: list[str]) -> tuple[DeploymentStep, ...]:
    phase_number = _phase_number(phase)
    return (
        DeploymentStep(f"{phase_number}.1", f"Validate prerequisites for {name}"),
        DeploymentStep(f"{phase_number}.2", f"Plan creation of {len(tables)} table artifact(s)"),
        DeploymentStep(f"{phase_number}.3", "Plan indexes, constraints, and validation checkpoint"),
        DeploymentStep(f"{phase_number}.4", "Record future migration-history checkpoint"),
    )


def build_deployment_phases() -> tuple[DeploymentPhase, ...]:
    phases: list[DeploymentPhase] = []
    for phase_id, name, tables in PHASE_DEFINITIONS:
        phases.append(
            DeploymentPhase(
                phase_id=phase_id,
                name=name,
                tables=tuple(tables),
                steps=_build_phase_steps(phase_id, name, tables),
                execution_allowed=False,
            )
        )
    return tuple(phases)


def _build_history(phases: tuple[DeploymentPhase, ...], *, blocked: bool) -> MigrationHistory:
    phase_pairs = tuple((phase.phase_id, phase.name) for phase in phases)
    return create_dry_run_history(phase_pairs, blocked=blocked)


def validate_execution_allowed(apply: bool = False) -> DeploymentResult:
    phases = build_deployment_phases()
    planned_step_count = sum(len(phase.steps) for phase in phases)
    if apply:
        return DeploymentResult(
            ok=False,
            mode="apply",
            execution_allowed=False,
            blocked=True,
            message=APPLY_NOT_IMPLEMENTED_MESSAGE,
            phases=phases,
            planned_step_count=planned_step_count,
            migration_history=_build_history(phases, blocked=True),
        )
    return DeploymentResult(
        ok=True,
        mode="dry-run",
        execution_allowed=False,
        blocked=True,
        message="Dry-run only: deployment phases are planned but execution is blocked.",
        phases=phases,
        planned_step_count=planned_step_count,
        migration_history=_build_history(phases, blocked=False),
    )


def run_deployment_dry_run() -> DeploymentResult:
    return validate_execution_allowed(apply=False)


def run_deployment_apply() -> DeploymentResult:
    return validate_execution_allowed(apply=True)


def format_phase_summary(result: DeploymentResult) -> str:
    lines = ["Planned PostgreSQL deployment phases (executor dry-run, display only):"]
    for phase in result.phases:
        lines.append(f"{_phase_number(phase.phase_id)}. {phase.name}")
        for step in phase.steps:
            lines.append(f"   - {step.step_id}: {step.description} [{step.status}; execution_allowed={step.execution_allowed}]")
    if result.migration_history is not None:
        lines.append(f"Migration history deployment_id: {result.migration_history.deployment_id}")
        lines.append(f"Migration history events: {len(result.migration_history.events)}")
    lines.append(f"Execution allowed: {result.execution_allowed}")
    lines.append(result.message)
    return "\n".join(lines)
