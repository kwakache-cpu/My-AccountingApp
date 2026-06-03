"""Offline PostgreSQL migration history framework.

This module defines data structures and dry-run helpers for future PostgreSQL
deployment history. It does not access any database and does not execute SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class MigrationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    BLOCKED = "BLOCKED"


TERMINAL_STATUSES = {
    MigrationStatus.COMPLETED,
    MigrationStatus.FAILED,
    MigrationStatus.ROLLED_BACK,
    MigrationStatus.BLOCKED,
}

ALLOWED_TRANSITIONS = {
    MigrationStatus.PENDING: {
        MigrationStatus.RUNNING,
        MigrationStatus.BLOCKED,
    },
    MigrationStatus.RUNNING: {
        MigrationStatus.COMPLETED,
        MigrationStatus.FAILED,
        MigrationStatus.ROLLED_BACK,
    },
    MigrationStatus.FAILED: {
        MigrationStatus.ROLLED_BACK,
        MigrationStatus.BLOCKED,
    },
    MigrationStatus.COMPLETED: set(),
    MigrationStatus.ROLLED_BACK: set(),
    MigrationStatus.BLOCKED: set(),
}


@dataclass(frozen=True)
class MigrationEvent:
    migration_id: str
    phase_id: str
    phase_name: str
    status: MigrationStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str = ""
    rollback_point: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MigrationHistory:
    deployment_id: str
    created_at: datetime
    events: tuple[MigrationEvent, ...] = field(default_factory=tuple)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_valid_status_transition(current: MigrationStatus, new_status: MigrationStatus) -> bool:
    return new_status in ALLOWED_TRANSITIONS[current]


def transition_event(
    event: MigrationEvent,
    new_status: MigrationStatus,
    *,
    completed_at: datetime | None = None,
    error_message: str = "",
    rollback_point: str = "",
    metadata: dict[str, str] | None = None,
) -> MigrationEvent:
    if not is_valid_status_transition(event.status, new_status):
        raise ValueError(f"Invalid migration status transition: {event.status.value} -> {new_status.value}")
    final_completed_at = completed_at if new_status in TERMINAL_STATUSES else None
    duration_seconds = None
    if final_completed_at is not None:
        duration_seconds = max((final_completed_at - event.started_at).total_seconds(), 0)
    merged_metadata = dict(event.metadata)
    if metadata:
        merged_metadata.update(metadata)
    return MigrationEvent(
        migration_id=event.migration_id,
        phase_id=event.phase_id,
        phase_name=event.phase_name,
        status=new_status,
        started_at=event.started_at,
        completed_at=final_completed_at,
        duration_seconds=duration_seconds,
        error_message=error_message or event.error_message,
        rollback_point=rollback_point or event.rollback_point,
        metadata=merged_metadata,
    )


def build_phase_history(
    phase_id: str,
    phase_name: str,
    *,
    deployment_id: str,
    status: MigrationStatus = MigrationStatus.PENDING,
    created_at: datetime | None = None,
    rollback_point: str = "",
    metadata: dict[str, str] | None = None,
) -> MigrationEvent:
    started_at = created_at or utc_now()
    phase_number = phase_id.replace("Phase ", "").strip()
    return MigrationEvent(
        migration_id=f"{deployment_id}:{phase_number}",
        phase_id=phase_id,
        phase_name=phase_name,
        status=status,
        started_at=started_at,
        rollback_point=rollback_point,
        metadata=metadata or {},
    )


def create_dry_run_history(
    phases: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    *,
    deployment_id: str | None = None,
    created_at: datetime | None = None,
    blocked: bool = False,
) -> MigrationHistory:
    final_deployment_id = deployment_id or f"dry-run-{uuid4().hex}"
    final_created_at = created_at or utc_now()
    status = MigrationStatus.BLOCKED if blocked else MigrationStatus.PENDING
    events = tuple(
        build_phase_history(
            phase_id,
            phase_name,
            deployment_id=final_deployment_id,
            status=status,
            created_at=final_created_at,
            rollback_point=f"before {phase_id}",
            metadata={
                "execution_mode": "dry-run",
                "execution_allowed": "false",
            },
        )
        for phase_id, phase_name in phases
    )
    return MigrationHistory(
        deployment_id=final_deployment_id,
        created_at=final_created_at,
        events=events,
    )
