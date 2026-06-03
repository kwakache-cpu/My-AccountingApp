# PostgreSQL Staging Deployment Skeleton

Phase: 5B.13H

This phase adds a staging deployment command skeleton only. It does not deploy schema, connect to Supabase, execute SQL, enable PostgreSQL runtime, migrate data, or modify SQLite behavior.

## Supported CLI Options

- `--dry-run`: Default mode. Validates required offline artifacts, prints redacted database URL diagnostics, and displays planned deployment phases.
- `--apply`: Fails immediately with `PostgreSQL deployment execution is not implemented yet.` and exits non-zero.

## Validation Behavior

The skeleton validates that these artifacts exist before a dry-run display:

- `reports\postgres_generated_schema.sql`
- `reports\postgres_generated_schema_summary.md`
- `reports\postgres_schema_validation_report.md`
- `reports\postgres_deployment_dry_run_plan.md`

Missing artifacts are reported with clear file paths. No SQL is parsed for execution and no database calls are made.

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
- `--apply` is blocked unconditionally.
- Database URL diagnostics redact passwords and do not print secrets.
- No PostgreSQL client, Supabase client, cursor, connection, or execute path is used.
- SQLite runtime behavior is not imported, called, or modified.

## Current Limitations

- Actual PostgreSQL deployment execution is not implemented.
- Migration history writes are not implemented.
- Seed data deployment is not implemented.
- Post-deployment validation queries are not implemented.
- Runtime cutover remains NO-GO.
