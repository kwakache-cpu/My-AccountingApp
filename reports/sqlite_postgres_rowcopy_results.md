# SQLite to PostgreSQL Row-Copy Results

Phase: 5B.15H

Guarded staging row-copy report. PostgreSQL runtime was not enabled, production deployment was not attempted, application runtime was not changed, and SQLite was opened read-only.

## Summary

- Status: BLOCKED
- Started at: 2026-06-14T06:22:52.555436+00:00
- Completed at: 2026-06-14T06:22:52.556330+00:00
- Dry-run status: not evaluated
- Batches planned: 0
- Batches executed: 0
- Rows planned: 0
- Rows copied: 0
- Committed: False
- Rolled back: False

## Guards

- Blocked: True
- Message: Row-copy execution is blocked until staging environment, enable flag, DATABASE_URL, explicit CLI flags, and PostgreSQL driver guards pass.
- PostgreSQL driver: psycopg2
- ERP_ENABLE_POSTGRES_ROW_COPY: False
- ERP_ENVIRONMENT_is_staging: False
- DATABASE_URL_present: False
- DATABASE_URL_valid: False
- explicit_copy_rows_flag: True
- explicit_confirm_row_copy_flag: False
- postgres_driver_available: True

## Error

- Row-copy execution is blocked until staging environment, enable flag, DATABASE_URL, explicit CLI flags, and PostgreSQL driver guards pass.

## Table Results

- No table batches executed.

## Safety Notes

- Required command: `python postgres_staging_deployer.py --copy-rows --confirm-row-copy`.
- Required environment: `ERP_ENVIRONMENT=staging`, `ERP_ENABLE_POSTGRES_ROW_COPY=1`, and `DATABASE_URL`.
- One transaction is used for the full row-copy run.
- Commit occurs only after all batches succeed; rollback occurs on failure.
