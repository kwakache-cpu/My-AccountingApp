# PostgreSQL Write Path Inventory

**Audited at:** 2026-06-01 12:31:48 UTC

Critical write paths that must use transactions + identity retrieval on Postgres.

## POS finalization

- `modules.py:5282`
- `modules.py:5292`
- `modules.py:799`
- `scripts/run_postgres_schema_compatibility_audit.py:59`

## Invoice posting

- `accounting_engine.py:937`
- `modules.py:12873`
- `modules.py:4342`

## Bill posting

- `modules.py:6038`
- `modules.py:8444`

## Payments

- `migration_cleanup.py:377`
- `modules.py:13315`
- `modules.py:13330`

## Inventory movements

- `modules.py:4416`

## Stock adjustments

- `modules.py:4411`
- `modules.py:758`

## Payroll posting

- `modules.py:14260`
- `modules.py:14283`

## Depreciation

- `modules.py:105`
- `modules.py:4052`

## Year-end close

- `modules.py:3204`
- `modules.py:88`

## Branch creation

- `database.py:5269`
- `database.py:5365`

## User creation

- `database.py:5613`
- `database.py:5675`

## Postgres Requirements per Path

- Use `execute_db_write_transaction()` or equivalent single-connection transactions.
- Replace `lastrowid` with `fetch_inserted_row_id()` after `insert_returning_id_sql()`.
- Avoid `PRAGMA` / `sqlite_master` in write paths.
- POS/inventory: preserve row-level locking strategy (Postgres `SELECT FOR UPDATE` where needed).
