# PostgreSQL Migration History Plan

Phase: 5B.14C

Framework-only plan. No SQL execution, Supabase connection, schema deployment, PostgreSQL runtime enablement, data migration, or SQLite behavior change is included.

## Event Lifecycle

1. Deployment run is created with a unique `deployment_id`.
2. Phase events are generated for all planned deployment phases.
3. Dry-run events remain `PENDING` unless the run is intentionally blocked.
4. Future apply events start as `PENDING`, transition to `RUNNING`, then finish as a terminal status.
5. Validation checkpoints attach summaries to event metadata.
6. Deployment run status is derived from the phase event statuses.

## Status Transitions

Allowed transitions:

- `PENDING` -> `RUNNING`
- `PENDING` -> `BLOCKED`
- `RUNNING` -> `COMPLETED`
- `RUNNING` -> `FAILED`
- `RUNNING` -> `ROLLED_BACK`
- `FAILED` -> `ROLLED_BACK`
- `FAILED` -> `BLOCKED`

Terminal statuses:

- `COMPLETED`
- `ROLLED_BACK`
- `BLOCKED`

`FAILED` is recoverable only through a later rollback or block decision. Dry-run should not transition into `RUNNING`.

## Dry-Run Event Generation

`postgres_migration_history.py` provides:

- `create_dry_run_history()`
- `build_phase_history()`

The executor dry-run now produces a `MigrationHistory` object containing one event per deployment phase. Current dry-run events use:

- `status=PENDING`
- `metadata.execution_mode=dry-run`
- `metadata.execution_allowed=false`
- `rollback_point=before <phase>`

Apply remains blocked and can produce blocked history events for reporting, but it does not execute anything.

## Rollback Model

Each event stores a rollback point. Future implementation should use rollback points to decide whether recovery is:

- Transaction rollback before commit.
- Phase reset after commit in a disposable staging schema.
- Full staging schema reset.
- Manual stop with no mutation of production SQLite data.

Rollback rules:

- Stop on first failed phase.
- Record rollback outcome as `ROLLED_BACK` only after rollback has actually occurred.
- Do not mark a failed event as completed after a retry; create a new deployment run.
- Keep rollback metadata redacted.

## Recovery Model

Recovery should use the history tables to answer:

- Which deployment run failed?
- Which phase failed?
- Was the phase committed, rolled back, or blocked?
- Which artifact version was used?
- Which validation checkpoint failed?
- Which rollback point applies?

Future retry policy:

- Create a new `deployment_id` for each retry.
- Link retries through metadata, not by overwriting old events.
- Preserve failure records for auditability.
- Require human approval before retrying any failed apply run.

## Retention Recommendations

- Keep all staging deployment run summaries for the life of the migration project.
- Keep failed and rolled-back event records indefinitely until cutover completion.
- Keep dry-run histories long enough to compare artifact drift across planning phases.
- Archive old successful staging histories after production cutover and audit sign-off.

## Audit Requirements

Every future apply event should include:

- Deployment ID.
- Phase ID and name.
- Status.
- Redacted target label.
- Artifact hash/version.
- Executor version.
- Validation checkpoint summary.
- Error summary, if any.
- Rollback point and rollback outcome.

Never store:

- Raw `DATABASE_URL`.
- Passwords or tokens.
- Supabase keys.
- Customer financial payloads.

## Current Limitations

- History tables are design-only and are not deployed.
- The executor does not write history to PostgreSQL.
- No SQL is executed.
- PostgreSQL deployment execution remains blocked.
- Runtime cutover remains NO-GO.
