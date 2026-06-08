# PostgreSQL Schema Execution Adapter

Phase: 5B.14H

This phase adds a guarded schema execution adapter for future staging deployment. It does not enable PostgreSQL runtime, migrate data, modify SQLite behavior, connect to Supabase, or expose CLI schema execution.

## Safety Model

- `postgres_schema_executor.py` reads `reports/postgres_generated_schema.sql` as an offline artifact.
- SQL is split into executable statements for planning.
- CLI `--dry-run` may display the schema execution plan.
- CLI `--apply` remains blocked by `PostgreSQL deployment execution is not implemented yet.`
- The executor does not read `DATABASE_URL`, create connections, import PostgreSQL drivers, or import the Supabase SDK.
- Mock execution is available only through an explicitly injected mock connection for unit tests.

## Models

`SchemaExecutionPlan` records:

- `source_path`
- `statements`
- `dry_run`
- `execution_allowed`
- `rollback_modeled`
- `message`

`SchemaExecutionResult` records:

- `ok`
- `dry_run`
- `execution_allowed`
- `statements_planned`
- `statements_executed`
- `rollback_attempted`
- `rollback_succeeded`
- `error_message`
- `executed_statements`

## SQL Splitting

The splitter ignores line comments and block comments, preserves quoted semicolons, and returns semicolon-terminated executable statements. Commented index placeholders in `reports/postgres_generated_schema.sql` remain non-executable.

## Rollback Modeling

Mock execution calls `rollback()` when an injected mock connection raises during statement execution. This models the future rollback contract without opening a real database connection.

## Prohibited Actions

This phase must not:

- Run schema execution from CLI.
- Deploy schema to staging or production.
- Execute SQL through a real connection.
- Read `DATABASE_URL`.
- Connect to Supabase.
- Run migrations.
- Migrate data.
- Enable PostgreSQL runtime.
- Change SQLite runtime behavior.

## Current Status

The adapter is suitable for dry-run planning and unit-test-only mock execution. Real staging schema execution remains blocked until a future explicit implementation phase adds connection ownership, transaction policy, migration history writes, validation checkpoints, and operational approval.
