# PostgreSQL Staging Deployment Skeleton

Phase: 5B.13H

This command defaults to a staging deployment dry-run. Guarded schema apply is available only for staging when every explicit control passes. It does not connect to Supabase, enable PostgreSQL runtime, migrate data, seed data, deploy to production, or modify SQLite behavior.

## Supported CLI Options

- `--dry-run`: Default mode. Validates required offline artifacts, prints redacted database URL diagnostics, and displays planned deployment phases.
- `--apply`: Validates guarded staging schema apply controls and may execute schema statements only when all guards and the safe probe pass.
- `--confirm-schema-apply`: Required with `--apply` for guarded staging schema apply.
- `--probe`: Runs the guarded PostgreSQL connection probe diagnostics only. The probe remains disabled unless `ERP_ENABLE_POSTGRES_PROBE=1` is set.
- `--probe-timeout`: Optional connection timeout for `--probe`; defaults to `5` seconds.
- `--validate-postdeploy`: Runs guarded read-only staging post-deployment validation queries. Requires `ERP_ENVIRONMENT=staging`, `DATABASE_URL`, deployed schema objects, and a PostgreSQL driver.

## Validation Behavior

The skeleton validates that these artifacts exist before a dry-run display:

- `reports\postgres_generated_schema.sql`
- `reports\postgres_generated_schema_summary.md`
- `reports\postgres_schema_validation_report.md`
- `reports\postgres_deployment_dry_run_plan.md`

Missing artifacts are reported with clear file paths. No SQL is parsed for execution and no database calls are made.

The schema execution adapter parses `reports/postgres_generated_schema.sql` for dry-run planning. In apply mode it may execute schema statements only after staging guards, confirmation, and the safe connection probe pass.

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
- `--apply` validates guardrails and fails closed unless every required control passes.
- `--confirm-schema-apply` is required for guarded apply.
- `--probe` never calls deployment, migration, or schema creation paths.
- Schema execution never runs during dry-run and does not run automatically on startup.
- Database URL diagnostics redact passwords and do not print secrets.
- Dry-run mode does not use any PostgreSQL client, Supabase client, cursor, connection, or execute path.
- Probe mode is limited to the guarded connection probe framework and does not execute SQL.
- Post-deployment validation mode only executes SELECT metadata checks and writes `reports/postgres_postdeploy_validation_results.md`.
- SQLite runtime behavior is not imported, called, or modified.

## Current Limitations

- Data migration is not implemented.
- Seed data deployment is not implemented.
- Migration history writes are not implemented.
- Post-deployment validation execution is read-only and staging guarded.
- Production deployment is blocked by `ERP_ENVIRONMENT=staging`.
- Runtime cutover remains NO-GO.
