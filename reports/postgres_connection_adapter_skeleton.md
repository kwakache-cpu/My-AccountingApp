# PostgreSQL Connection Adapter Skeleton

Phase: 5B.14E

Skeleton only. This phase defines a safe PostgreSQL connection adapter interface for future deployment execution. No Supabase connection, SQL execution, schema deployment, PostgreSQL runtime enablement, data migration, or SQLite runtime behavior change is included.

## Module

Created: `postgres_connection_adapter.py`

## Data Models

- `PostgresConnectionConfig`: captures `database_url`, future connection flag, and driver preference.
- `PostgresConnectionDiagnostics`: reports redacted URL state, driver discovery, blocking status, and reasons.
- `PostgresAdapterStatus`: enum for `READY`, `BLOCKED`, `MISSING_DATABASE_URL`, `DRIVER_AVAILABLE`, `DRIVER_MISSING`, and `INVALID_DATABASE_URL`.

## Helpers

- `redact_database_url()`: hides passwords and returns only a safe display label.
- `parse_database_url_safely()`: parses URL structure without connecting.
- `detect_postgres_driver()`: checks driver availability using import metadata/spec discovery only.
- `build_connection_diagnostics()`: returns a blocked diagnostic summary.
- `validate_connection_allowed()`: preserves the block until a future execution phase explicitly implements connection support.

## Adapter Class

`PostgresConnectionAdapter` exposes:

- `diagnostics()`: returns safe diagnostics without connecting.
- `connect()`: raises `NotImplementedError("PostgreSQL connection execution is not implemented yet.")`.

## Safety Guarantees

- Missing `DATABASE_URL` returns blocked diagnostics.
- `DATABASE_URL` output is always redacted.
- Passwords are never printed.
- Driver detection does not open a connection.
- Connection attempts remain blocked.
- No PostgreSQL driver connect call is present.
- No Supabase SDK is used.
- No SQL execution path is present.
- SQLite runtime behavior is not changed.

## Current Limitations

- The adapter cannot connect to PostgreSQL.
- The deployment executor cannot use a live database connection.
- Validation queries remain string definitions only.
- Migration history writes remain framework-only.
- Runtime cutover remains NO-GO.
