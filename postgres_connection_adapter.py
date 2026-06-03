"""Safe PostgreSQL connection adapter skeleton.

This module validates configuration and reports diagnostics only. It does not
open network connections or execute SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from importlib.util import find_spec
from urllib.parse import urlsplit, urlunsplit


CONNECTION_NOT_IMPLEMENTED_MESSAGE = "PostgreSQL connection execution is not implemented yet."


class PostgresAdapterStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    MISSING_DATABASE_URL = "MISSING_DATABASE_URL"
    DRIVER_AVAILABLE = "DRIVER_AVAILABLE"
    DRIVER_MISSING = "DRIVER_MISSING"
    INVALID_DATABASE_URL = "INVALID_DATABASE_URL"


@dataclass(frozen=True)
class PostgresConnectionConfig:
    database_url: str = ""
    allow_future_connection: bool = False
    driver_preference: tuple[str, ...] = ("psycopg", "psycopg2")


@dataclass(frozen=True)
class PostgresConnectionDiagnostics:
    status: PostgresAdapterStatus
    blocked: bool
    database_url_configured: bool
    database_url_redacted: str = ""
    driver_name: str = ""
    driver_available: bool = False
    message: str = ""
    reasons: tuple[str, ...] = field(default_factory=tuple)


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


def parse_database_url_safely(database_url: str | None) -> dict[str, str | bool]:
    if not database_url:
        return {
            "valid": False,
            "scheme": "",
            "hostname": "",
            "database": "",
            "redacted_url": "",
            "reason": "DATABASE_URL is missing.",
        }
    try:
        parts = urlsplit(database_url)
    except ValueError:
        return {
            "valid": False,
            "scheme": "",
            "hostname": "",
            "database": "",
            "redacted_url": "<invalid-url>",
            "reason": "DATABASE_URL could not be parsed.",
        }
    valid = parts.scheme in {"postgres", "postgresql"} and bool(parts.hostname)
    return {
        "valid": valid,
        "scheme": parts.scheme,
        "hostname": parts.hostname or "",
        "database": parts.path.lstrip("/"),
        "redacted_url": redact_database_url(database_url),
        "reason": "" if valid else "DATABASE_URL must use postgres/postgresql scheme and include a hostname.",
    }


def detect_postgres_driver(driver_preference: tuple[str, ...] = ("psycopg", "psycopg2")) -> tuple[str, bool]:
    for driver_name in driver_preference:
        if find_spec(driver_name) is not None:
            return driver_name, True
    return "", False


def build_connection_diagnostics(config: PostgresConnectionConfig) -> PostgresConnectionDiagnostics:
    parsed = parse_database_url_safely(config.database_url)
    driver_name, driver_available = detect_postgres_driver(config.driver_preference)
    reasons: list[str] = []

    if not config.database_url:
        reasons.append("DATABASE_URL is missing.")
        return PostgresConnectionDiagnostics(
            status=PostgresAdapterStatus.MISSING_DATABASE_URL,
            blocked=True,
            database_url_configured=False,
            database_url_redacted="",
            driver_name=driver_name,
            driver_available=driver_available,
            message="DATABASE_URL is not configured. PostgreSQL connection is blocked.",
            reasons=tuple(reasons),
        )

    if not parsed["valid"]:
        reasons.append(str(parsed["reason"]))
        return PostgresConnectionDiagnostics(
            status=PostgresAdapterStatus.INVALID_DATABASE_URL,
            blocked=True,
            database_url_configured=True,
            database_url_redacted=str(parsed["redacted_url"]),
            driver_name=driver_name,
            driver_available=driver_available,
            message="DATABASE_URL is invalid. PostgreSQL connection is blocked.",
            reasons=tuple(reasons),
        )

    if not driver_available:
        reasons.append("No PostgreSQL driver is available.")

    if not config.allow_future_connection:
        reasons.append(CONNECTION_NOT_IMPLEMENTED_MESSAGE)

    blocked = True
    status = PostgresAdapterStatus.DRIVER_AVAILABLE if driver_available else PostgresAdapterStatus.DRIVER_MISSING
    return PostgresConnectionDiagnostics(
        status=status if not config.allow_future_connection else PostgresAdapterStatus.BLOCKED,
        blocked=blocked,
        database_url_configured=True,
        database_url_redacted=str(parsed["redacted_url"]),
        driver_name=driver_name,
        driver_available=driver_available,
        message="PostgreSQL connection diagnostics only. No connection will be attempted.",
        reasons=tuple(reasons),
    )


def validate_connection_allowed(config: PostgresConnectionConfig) -> PostgresConnectionDiagnostics:
    diagnostics = build_connection_diagnostics(config)
    if diagnostics.blocked:
        return diagnostics
    return PostgresConnectionDiagnostics(
        status=PostgresAdapterStatus.BLOCKED,
        blocked=True,
        database_url_configured=diagnostics.database_url_configured,
        database_url_redacted=diagnostics.database_url_redacted,
        driver_name=diagnostics.driver_name,
        driver_available=diagnostics.driver_available,
        message=CONNECTION_NOT_IMPLEMENTED_MESSAGE,
        reasons=diagnostics.reasons + (CONNECTION_NOT_IMPLEMENTED_MESSAGE,),
    )


class PostgresConnectionAdapter:
    def __init__(self, config: PostgresConnectionConfig):
        self.config = config

    def diagnostics(self) -> PostgresConnectionDiagnostics:
        return build_connection_diagnostics(self.config)

    def connect(self):
        raise NotImplementedError(CONNECTION_NOT_IMPLEMENTED_MESSAGE)
