# PostgreSQL Real Schema Apply, Guarded

Phase: 5B.14L

This phase adds the first real PostgreSQL schema apply path for staging only. Default behavior remains dry-run. Runtime activation, data migration, seed data deployment, production deployment, and SQLite behavior changes remain blocked.

## Required Guards

Real schema apply requires all of these controls:

- `ERP_ENABLE_POSTGRES_SCHEMA_APPLY=1`
- `ERP_ENVIRONMENT=staging`
- `ERP_ENABLE_POSTGRES_PROBE=1`
- `DATABASE_URL` present
- CLI `--apply`
- CLI `--confirm-schema-apply`
- Successful safe connection probe

If any guard fails, no SQL is executed.

## Execution Behavior

When all guards pass:

- The deployer reads `reports/postgres_generated_schema.sql`.
- Statements are parsed with the schema executor splitter.
- The safe connection probe opens and closes a connection first.
- The apply path opens a PostgreSQL connection using `DATABASE_URL`.
- Statements execute in order.
- `commit()` is called only after all statements succeed.
- `rollback()` is called if any statement fails.
- The connection is closed in all cases.

## Safety Constraints

- `DATABASE_URL` is redacted in operator output.
- Audit events log statement previews only.
- PostgreSQL runtime is not enabled.
- No data migration runs.
- No seed data runs.
- No app startup path is changed.
- No SQLite runtime behavior is changed.
- Production is blocked because `ERP_ENVIRONMENT` must equal `staging`.

## Command

Real staging schema apply command:

```powershell
$env:ERP_ENABLE_POSTGRES_SCHEMA_APPLY="1"
$env:ERP_ENVIRONMENT="staging"
$env:ERP_ENABLE_POSTGRES_PROBE="1"
$env:DATABASE_URL="postgresql://..."
python postgres_staging_deployer.py --apply --confirm-schema-apply
```

## Remaining Blockers

- Migration history persistence is not implemented.
- Post-apply validation execution is not implemented.
- Data migration is not implemented.
- Seed data deployment is not implemented.
- Runtime cutover remains NO-GO.
- Production deployment remains prohibited.
