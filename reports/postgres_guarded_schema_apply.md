# PostgreSQL Guarded Schema Apply

Phase: 5B.14I

This phase adds a guarded staging schema apply framework. It can validate explicit apply controls and build a schema execution plan, but it still stops before SQL execution.

## Required Controls

`SchemaApplyGuard` requires all of these conditions:

- `ERP_ENABLE_POSTGRES_SCHEMA_APPLY=1`
- `ERP_ENVIRONMENT=staging`
- `DATABASE_URL` present
- Explicit `--apply`
- Explicit `--confirm-schema-apply`
- Schema file exists at `reports/postgres_generated_schema.sql`

## Diagnostics

`SchemaApplyDiagnostics` reports:

- `status`
- `blocked`
- `all_guards_passed`
- `guard_results`
- `statements_planned`
- `schema_path`
- `message`

The status remains `BLOCKED` in this phase, even when every guard passes. Passing guards only indicate readiness for a future implementation phase.

## CLI Behavior

Default behavior remains dry-run:

```powershell
python postgres_staging_deployer.py --dry-run
```

Guarded apply diagnostics:

```powershell
python postgres_staging_deployer.py --apply --confirm-schema-apply
```

The apply path may parse `reports/postgres_generated_schema.sql`, count planned statements, and print guard pass/fail results. It then returns non-zero before execution.

## Prohibited Actions

This phase does not:

- Execute SQL.
- Create schema.
- Run migrations.
- Migrate data.
- Enable PostgreSQL runtime.
- Modify SQLite behavior.
- Deploy to production.

## Remaining Work

A future phase must define the real staging connection owner, transaction boundary, migration-history writes, post-apply validation checkpoints, rollback policy, operator approval process, and production exclusion controls before any real schema execution can be considered.
