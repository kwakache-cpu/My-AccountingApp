"""PostgreSQL post-deployment validation query definitions.

This module stores future validation query text and expectations only. It does
not connect to a database and does not execute SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


VALIDATION_CATEGORIES = (
    "schema_exists",
    "table_exists",
    "column_exists",
    "index_exists",
    "fk_exists",
    "seed_rows_exist",
    "migration_history_exists",
    "runtime_smoke_test",
)


class ValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ValidationExpectation:
    description: str
    expected_result: str
    severity: ValidationSeverity


@dataclass(frozen=True)
class ValidationQuery:
    query_id: str
    category: str
    name: str
    sql: str
    expectation: ValidationExpectation
    when_to_run: str
    parameters: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ValidationQuerySet:
    name: str
    queries_by_category: dict[str, tuple[ValidationQuery, ...]]

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(self.queries_by_category.keys())

    @property
    def queries(self) -> tuple[ValidationQuery, ...]:
        return tuple(query for queries in self.queries_by_category.values() for query in queries)


def _query(
    query_id: str,
    category: str,
    name: str,
    sql: str,
    expected_result: str,
    severity: ValidationSeverity,
    when_to_run: str,
    parameters: tuple[str, ...],
) -> ValidationQuery:
    return ValidationQuery(
        query_id=query_id,
        category=category,
        name=name,
        sql=sql.strip(),
        expectation=ValidationExpectation(
            description=name,
            expected_result=expected_result,
            severity=severity,
        ),
        when_to_run=when_to_run,
        parameters=parameters,
    )


def build_postgres_validation_query_set() -> ValidationQuerySet:
    queries_by_category = {
        "schema_exists": (
            _query(
                "schema_exists_current",
                "schema_exists",
                "Current schema is visible",
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name = current_schema()
                """,
                "One row for the current staging schema.",
                ValidationSeverity.CRITICAL,
                "Before any post-deployment object checks.",
                (),
            ),
        ),
        "table_exists": (
            _query(
                "table_exists_named",
                "table_exists",
                "Expected table exists",
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_type = 'BASE TABLE'
                  AND table_name = %(table_name)s
                """,
                "One row per expected table.",
                ValidationSeverity.CRITICAL,
                "After each schema deployment phase.",
                ("table_name",),
            ),
        ),
        "column_exists": (
            _query(
                "column_exists_named",
                "column_exists",
                "Expected column exists",
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %(table_name)s
                  AND column_name = %(column_name)s
                """,
                "One row per expected table column.",
                ValidationSeverity.ERROR,
                "After table existence checks for each phase.",
                ("table_name", "column_name"),
            ),
        ),
        "index_exists": (
            _query(
                "index_exists_named",
                "index_exists",
                "Expected index exists",
                """
                SELECT indexname, tablename, indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = %(table_name)s
                  AND indexname = %(index_name)s
                """,
                "One row per expected index.",
                ValidationSeverity.ERROR,
                "After indexes are created for a phase.",
                ("table_name", "index_name"),
            ),
        ),
        "fk_exists": (
            _query(
                "fk_exists_named",
                "fk_exists",
                "Expected foreign key exists",
                """
                SELECT tc.constraint_name, kcu.column_name, ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name
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
                "One row per expected foreign key.",
                ValidationSeverity.CRITICAL,
                "After foreign key constraints are created or validated.",
                ("table_name", "column_name", "foreign_table_name", "foreign_column_name"),
            ),
        ),
        "seed_rows_exist": (
            _query(
                "seed_rows_exist_named",
                "seed_rows_exist",
                "Expected seed rows exist",
                """
                SELECT COUNT(*) AS row_count
                FROM %(qualified_table_name)s
                """,
                "Row count is greater than or equal to the expected seed count.",
                ValidationSeverity.ERROR,
                "After seed deployment and before runtime activation.",
                ("qualified_table_name", "minimum_row_count"),
            ),
        ),
        "migration_history_exists": (
            _query(
                "migration_history_run_exists",
                "migration_history_exists",
                "Deployment run is recorded",
                """
                SELECT deployment_id, status, execution_mode, schema_version
                FROM postgres_deployment_runs
                WHERE deployment_id = %(deployment_id)s
                """,
                "One deployment run row for the current deployment.",
                ValidationSeverity.CRITICAL,
                "After migration-history tables are created and after each phase status update.",
                ("deployment_id",),
            ),
            _query(
                "migration_history_phase_events_exist",
                "migration_history_exists",
                "Deployment phase events are recorded",
                """
                SELECT deployment_id, phase_id, phase_name, status
                FROM postgres_migration_history
                WHERE deployment_id = %(deployment_id)s
                ORDER BY phase_id
                """,
                "One event row per planned deployment phase.",
                ValidationSeverity.CRITICAL,
                "After phase event generation in a future apply run.",
                ("deployment_id",),
            ),
        ),
        "runtime_smoke_test": (
            _query(
                "runtime_smoke_core_tables",
                "runtime_smoke_test",
                "Core runtime tables are queryable",
                """
                SELECT
                    (SELECT COUNT(*) FROM companies) AS company_count,
                    (SELECT COUNT(*) FROM branches) AS branch_count,
                    (SELECT COUNT(*) FROM users) AS user_count
                """,
                "Core tables return counts without errors.",
                ValidationSeverity.CRITICAL,
                "After schema and seed validation, before runtime gate relaxation.",
                (),
            ),
        ),
    }
    return ValidationQuerySet(
        name="postgres_postdeploy_validation_queries",
        queries_by_category={category: queries_by_category[category] for category in VALIDATION_CATEGORIES},
    )
