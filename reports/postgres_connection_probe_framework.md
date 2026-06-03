# PostgreSQL Connection Probe Framework

Phase: 5B.14F

This phase adds a strictly controlled PostgreSQL endpoint reachability probe. It is not schema deployment, migration, data movement, runtime activation, or a SQLite behavior change.

## Safety Model

- Default behavior is blocked. No probe is allowed unless `ERP_ENABLE_POSTGRES_PROBE=1` is present.
- The probe is isolated in `postgres_connection_probe.py` and is only invoked directly or through `postgres_staging_deployer.py --probe`.
- The staging deployer `--probe` path exits before deployment dry-run, artifact validation, migration, schema creation, or apply behavior.
- When a probe is enabled and all prerequisites are present, the permitted operation is connection establishment followed immediately by disconnect.
- Diagnostics redact credentials and report only endpoint/configuration readiness signals.

## Enablement Flag

`ERP_ENABLE_POSTGRES_PROBE=1` is required before any connection attempt is allowed.

Any other value, including an unset variable, returns `ProbeStatus.PROBE_DISABLED` with `probe_attempted=False`.

## Diagnostics

`ProbeResult` records:

- `status`
- `diagnostics`
- `timestamp`
- `driver_detected`
- `database_url_present`
- `probe_attempted`
- `probe_succeeded`
- `error_message`

Supported statuses:

- `BLOCKED`
- `NOT_CONFIGURED`
- `DRIVER_MISSING`
- `READY_FOR_PROBE`
- `PROBE_DISABLED`
- `PROBE_SUCCEEDED`
- `PROBE_FAILED`

## Limitations

- The framework verifies only connection establishment capability.
- It does not validate schema, tables, indexes, constraints, seed data, migrations, or application SQL compatibility.
- It does not enable `ERP_ENABLE_POSTGRES_RUNTIME`.
- It does not make PostgreSQL safe for staging cutover.
- Driver behavior and network policy are still environment dependent.

## Prohibited Actions

The probe must never:

- Execute SQL.
- Deploy schema.
- Run migrations.
- Migrate data.
- Create, alter, or drop database objects.
- Enable PostgreSQL runtime behavior.
- Change SQLite runtime behavior.
- Invoke deployment apply paths.

## CLI Integration

Run diagnostics with:

```powershell
python postgres_staging_deployer.py --probe
```

Without `ERP_ENABLE_POSTGRES_PROBE=1`, the command reports `PROBE_DISABLED` and does not attempt a connection.
