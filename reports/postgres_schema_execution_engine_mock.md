# PostgreSQL Schema Execution Engine, Mock-First

Phase: 5B.14K

This phase adds an internal schema execution engine for injected mock connections only. It does not expose real execution through CLI, discover database connections, read `DATABASE_URL`, import PostgreSQL drivers, connect to Supabase, migrate data, enable PostgreSQL runtime, or change SQLite behavior.

## Execution Entry Point

`execute_schema_plan_with_connection(plan, connection, *, allow_execution=False)` is the only new engine entry point.

- With `allow_execution=False`, it returns a blocked `SchemaExecutionResult` and does not call `connection.execute`.
- With `allow_execution=True`, it executes statements only against the injected mock connection.
- Non-mock connections are blocked.
- No connection is created or discovered by the executor.

## Transaction Behavior

- Statements are sent to the injected mock connection in plan order.
- `commit()` is called only after every statement succeeds.
- `rollback()` is called when any statement raises.
- The result records executed statement count, rollback status, and error details.

## Audit Behavior

The engine emits audit events for statement execution:

- `BLOCKED` when execution is not explicitly allowed or the connection is not an injected mock.
- `RUNNING` before each statement is sent to the mock connection.
- `COMPLETED` after each successful statement.
- `FAILED` for the statement that raises.
- `ROLLED_BACK` after a successful rollback.

Dry-run and CLI apply paths remain separate from this engine.

## CLI Status

`postgres_staging_deployer.py --apply` remains blocked. It does not call `execute_schema_plan_with_connection`.

## Prohibited Actions

This phase must not:

- Execute SQL against a real database.
- Create or discover a database connection.
- Read `DATABASE_URL` from the execution engine.
- Import psycopg, psycopg2, SQLAlchemy, or Supabase SDKs.
- Enable PostgreSQL runtime.
- Migrate data.
- Modify SQLite behavior.

## Remaining Work

A future phase must define approved staging connection ownership, externalized audit persistence, transaction boundaries, migration history writes, post-apply validation, operator approval, and production exclusion before any real schema execution can be considered.
