# PostgreSQL Schema Execution Audit Framework

Phase: 5B.14J

This phase adds structured audit logging for future PostgreSQL schema apply attempts. It does not execute SQL, connect to Supabase, deploy schema, enable PostgreSQL runtime, migrate data, or change SQLite behavior.

## Data Models

`SchemaExecutionAuditEvent` records:

- `deployment_id`
- `phase_id`
- `statement_index`
- `statement_preview`
- `status`
- `started_at`
- `completed_at`
- `duration_ms`
- `error_message`
- `rollback_required`

`SchemaExecutionAuditLog` groups audit events under a deployment and phase.

`SchemaExecutionAuditStatus` values:

- `PLANNED`
- `BLOCKED`
- `SUCCEEDED`
- `FAILED`

Only `PLANNED` and `BLOCKED` are produced by current CLI paths because execution is still disabled.

## Dry-Run Behavior

Dry-run builds a schema execution plan from `reports/postgres_generated_schema.sql` and creates one `PLANNED` audit event per parsed statement. No statement is executed.

## Apply Behavior

`--apply` remains blocked. The deployer validates schema apply guards and creates a single `BLOCKED` audit event showing the blocked attempt. No rollback is required because execution never starts.

## Statement Previews

Statement previews are normalized to one line, truncated, and scrubbed for password-like literals such as `password`, `secret`, `token`, and `key` assignments. Previews are for operator diagnostics only and are not a substitute for reviewed SQL artifacts.

## Prohibited Actions

This framework must not:

- Execute SQL.
- Open PostgreSQL connections.
- Connect to Supabase.
- Deploy schema.
- Run migrations.
- Migrate data.
- Enable PostgreSQL runtime.
- Modify SQLite behavior.

## Remaining Work

A future execution phase must persist audit logs to an approved destination, define transaction and rollback policy, attach post-apply validation results, and include operator approval before real staging schema execution is allowed.
