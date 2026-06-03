"""Strictly guarded PostgreSQL connection probe.

This module is separate from runtime database selection. It can only attempt a
PostgreSQL connect/disconnect cycle when ERP_ENABLE_POSTGRES_PROBE=1 is set.
It never executes SQL, deploys schema, runs migrations, or changes SQLite
runtime behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from importlib import import_module
from importlib.util import find_spec
import os
from typing import Any, Callable

from postgres_connection_adapter import parse_database_url_safely, redact_database_url


PROBE_ENABLE_ENV_VAR = "ERP_ENABLE_POSTGRES_PROBE"
DEFAULT_PROBE_TIMEOUT_SECONDS = 5.0
DEFAULT_DRIVER_PREFERENCE = ("psycopg", "psycopg2")
PROHIBITED_ACTIONS = (
    "schema deployment",
    "migration execution",
    "data migration",
    "SQL execution",
    "PostgreSQL runtime activation",
    "SQLite runtime behavior changes",
)


class ProbeStatus(str, Enum):
    BLOCKED = "BLOCKED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    DRIVER_MISSING = "DRIVER_MISSING"
    READY_FOR_PROBE = "READY_FOR_PROBE"
    PROBE_DISABLED = "PROBE_DISABLED"
    PROBE_SUCCEEDED = "PROBE_SUCCEEDED"
    PROBE_FAILED = "PROBE_FAILED"


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    diagnostics: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    driver_detected: bool = False
    database_url_present: bool = False
    probe_attempted: bool = False
    probe_succeeded: bool = False
    error_message: str = ""


Connector = Callable[[str, str, float], Any]


def is_probe_enabled() -> bool:
    return os.environ.get(PROBE_ENABLE_ENV_VAR) == "1"


def detect_postgres_driver(driver_preference: tuple[str, ...] = DEFAULT_DRIVER_PREFERENCE) -> tuple[str, bool]:
    for driver_name in driver_preference:
        if find_spec(driver_name) is not None:
            return driver_name, True
    return "", False


def build_probe_diagnostics(
    database_url: str | None = None,
    driver_preference: tuple[str, ...] = DEFAULT_DRIVER_PREFERENCE,
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    value = os.environ.get("DATABASE_URL", "") if database_url is None else database_url
    driver_name, driver_detected = detect_postgres_driver(driver_preference)
    parsed = parse_database_url_safely(value)
    enabled = is_probe_enabled()

    return {
        "probe_enabled": enabled,
        "enablement_flag": PROBE_ENABLE_ENV_VAR,
        "database_url_present": bool(value),
        "database_url_valid": bool(parsed["valid"]),
        "database_url_redacted": redact_database_url(value),
        "database_host": parsed["hostname"],
        "database_name": parsed["database"],
        "driver_name": driver_name,
        "driver_detected": driver_detected,
        "timeout_seconds": timeout_seconds,
        "ready_for_probe": enabled and bool(value) and bool(parsed["valid"]) and driver_detected,
        "safe_behavior": "connect/disconnect only when explicitly enabled",
        "prohibited_actions": PROHIBITED_ACTIONS,
    }


def _default_connector(database_url: str, driver_name: str, timeout_seconds: float):
    driver = import_module(driver_name)
    return driver.connect(database_url, connect_timeout=timeout_seconds)


def _connect_and_close(database_url: str, driver_name: str, timeout_seconds: float, connector: Connector) -> None:
    connection = connector(database_url, driver_name, timeout_seconds)
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def _blocked_result(status: ProbeStatus, diagnostics: dict[str, Any], message: str) -> ProbeResult:
    return ProbeResult(
        status=status,
        diagnostics=diagnostics,
        driver_detected=bool(diagnostics["driver_detected"]),
        database_url_present=bool(diagnostics["database_url_present"]),
        probe_attempted=False,
        probe_succeeded=False,
        error_message=message,
    )


def run_safe_connection_probe(
    database_url: str | None = None,
    driver_preference: tuple[str, ...] = DEFAULT_DRIVER_PREFERENCE,
    connector: Connector | None = None,
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> ProbeResult:
    diagnostics = build_probe_diagnostics(database_url, driver_preference, timeout_seconds)
    value = os.environ.get("DATABASE_URL", "") if database_url is None else database_url

    if not diagnostics["probe_enabled"]:
        return _blocked_result(
            ProbeStatus.PROBE_DISABLED,
            diagnostics,
            f"{PROBE_ENABLE_ENV_VAR}=1 is required before any PostgreSQL probe is allowed.",
        )

    if not value:
        return _blocked_result(ProbeStatus.NOT_CONFIGURED, diagnostics, "DATABASE_URL is not configured.")

    if not diagnostics["database_url_valid"]:
        return _blocked_result(ProbeStatus.NOT_CONFIGURED, diagnostics, "DATABASE_URL is not a valid PostgreSQL URL.")

    if not diagnostics["driver_detected"]:
        return _blocked_result(ProbeStatus.DRIVER_MISSING, diagnostics, "No PostgreSQL driver is available.")

    if timeout_seconds <= 0:
        return _blocked_result(ProbeStatus.BLOCKED, diagnostics, "Probe timeout must be greater than zero seconds.")

    connect = connector or _default_connector
    try:
        _connect_and_close(value, str(diagnostics["driver_name"]), timeout_seconds, connect)
    except TimeoutError as exc:
        return ProbeResult(
            status=ProbeStatus.PROBE_FAILED,
            diagnostics=diagnostics,
            driver_detected=True,
            database_url_present=True,
            probe_attempted=True,
            probe_succeeded=False,
            error_message=f"Connection probe timed out after {timeout_seconds:g} seconds: {exc}",
        )
    except Exception as exc:  # pragma: no cover - exact driver exceptions vary.
        return ProbeResult(
            status=ProbeStatus.PROBE_FAILED,
            diagnostics=diagnostics,
            driver_detected=True,
            database_url_present=True,
            probe_attempted=True,
            probe_succeeded=False,
            error_message=f"Connection probe failed during connect/disconnect: {type(exc).__name__}: {exc}",
        )

    return ProbeResult(
        status=ProbeStatus.PROBE_SUCCEEDED,
        diagnostics=diagnostics,
        driver_detected=True,
        database_url_present=True,
        probe_attempted=True,
        probe_succeeded=True,
        error_message="",
    )
