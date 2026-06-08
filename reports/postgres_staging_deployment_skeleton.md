# PostgreSQL Staging Deployment Skeleton

Phase: 5B.13H

This phase adds a staging deployment command skeleton only. It does not deploy schema, connect to Supabase, execute SQL, enable PostgreSQL runtime, migrate data, or modify SQLite behavior.

## Supported CLI Options

- `--dry-run`: Default mode. Validates required offline artifacts, prints redacted database URL diagnostics, and displays planned deployment phases.
- `--apply`: Validates guarded staging schema apply controls, then fails before SQL execution.
- `--confirm-schema-apply`: Required with `--apply` for future schema apply; still does not permit SQL execution in this phase.
- `--probe`: Runs the guarded PostgreSQL connection probe diagnostics only. The probe remains disabled unless `ERP_ENABLE_POSTGRES_PROBE=1` is set.
- `--probe-timeout`: Optional connection timeout for `--probe`; defaults to `5` seconds.

## Validation Behavior

The skeleton validates that these artifacts exist before a dry-run display:

- `reports\postgres_generated_schema.sql`
- `reports\postgres_generated_schema_summary.md`
- `reports\postgres_schema_validation_report.md`
- `reports\postgres_deployment_dry_run_plan.md`

Missing artifacts are reported with clear file paths. No SQL is parsed for execution and no database calls are made.

The schema execution adapter parses `reports/postgres_generated_schema.sql` for dry-run planning and guarded apply diagnostics only. It does not execute statements from this CLI.

## Phase Display

1. migration metadata
2. companies/branches/users
3. accounting masters
4. inventory
5. documents
6. journals
7. POS
8. payroll/assets
9. audit/system

## Safety Protections

- Default mode is dry-run.
- `--apply` validates guardrails but is blocked before SQL execution.
- `--confirm-schema-apply` is required for future apply but does not override the phase block.
- `--probe` never calls deployment, migration, or schema creation paths.
- Schema execution planning is dry-run only and does not open a database connection.
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
