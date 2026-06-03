# PostgreSQL Validation Query Framework

Phase: 5B.14D

Framework-only artifact. This phase defines future PostgreSQL post-deployment validation query definitions as strings. No SQL execution, database connection, Supabase connection, schema deployment, PostgreSQL runtime enablement, data migration, or SQLite behavior change is included.

## Module

Created: `postgres_validation_queries.py`

The module defines:

- `ValidationSeverity`
- `ValidationExpectation`
- `ValidationQuery`
- `ValidationQuerySet`
- `build_postgres_validation_query_set()`

The module contains PostgreSQL-oriented SQL text only. It has no cursor, connection, driver, execution, or environment configuration path.

## Query Categories

| Category | Purpose | PostgreSQL source |
|---|---|---|
| `schema_exists` | Confirm the staging schema is visible. | `information_schema.schemata` |
| `table_exists` | Confirm expected base tables exist. | `information_schema.tables` |
| `column_exists` | Confirm expected columns and metadata exist. | `information_schema.columns` |
| `index_exists` | Confirm expected indexes exist. | `pg_indexes` |
| `fk_exists` | Confirm expected foreign keys exist. | `information_schema.table_constraints`, `key_column_usage`, `constraint_column_usage` |
| `seed_rows_exist` | Confirm required seed rows are present. | Future seeded tables |
| `migration_history_exists` | Confirm deployment run and phase event history exists. | `postgres_deployment_runs`, `postgres_migration_history` |
| `runtime_smoke_test` | Confirm core runtime tables are queryable after staging validation. | Core ERP tables |

## Expected Result Model

Each `ValidationQuery` includes:

- Query ID.
- Category.
- Human-readable name.
- SQL text string.
- Expected result description.
- Severity.
- Run timing.
- Parameter names.

The framework does not evaluate results. A future executor should compare query output against `ValidationExpectation.expected_result` and record outcomes in migration history.

## Severity Levels

- `INFO`: Informational evidence. Should not block execution.
- `WARNING`: Needs review but may not block staging continuation.
- `ERROR`: Blocks the current validation stage until resolved.
- `CRITICAL`: Blocks deployment, runtime activation, or cutover.

Current category severities:

- `schema_exists`: `CRITICAL`
- `table_exists`: `CRITICAL`
- `column_exists`: `ERROR`
- `index_exists`: `ERROR`
- `fk_exists`: `CRITICAL`
- `seed_rows_exist`: `ERROR`
- `migration_history_exists`: `CRITICAL`
- `runtime_smoke_test`: `CRITICAL`

## When Queries Run

Recommended timing:

1. Before post-deployment object checks: `schema_exists`.
2. After each schema deployment phase: `table_exists`.
3. After table checks: `column_exists`.
4. After index creation: `index_exists`.
5. After FK creation or constraint validation: `fk_exists`.
6. After seed deployment: `seed_rows_exist`.
7. After every deployment phase status update: `migration_history_exists`.
8. After schema and seed validation, before runtime gate relaxation: `runtime_smoke_test`.

## Failure Handling

Future executor behavior should be:

- `CRITICAL`: stop the deployment stage immediately, record failure in migration history, and do not enable runtime.
- `ERROR`: stop the current validation stage, allow rollback or manual correction, and require a new validation run.
- `WARNING`: record finding and require explicit reviewer acceptance before continuation.
- `INFO`: record evidence only.

Validation failures must not mutate production SQLite data. Raw credentials must never be logged.

## Remaining Blockers

- Query execution is not implemented.
- Result comparison is not implemented.
- Validation result persistence is not implemented.
- PostgreSQL migration history tables are not deployed.
- Seed manifests are not implemented.
- Runtime cutover remains NO-GO.
