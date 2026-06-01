# PostgreSQL Write Path Inventory

**Audited at:** 2026-06-01 20:07:48 UTC  
**Phase 5B.11 note:** Critical INSERT identity retrieval is **converted** on paths below (`ensure_insert_sql_returning` + `get_inserted_id`). Remaining cutover risk is **SQL placeholders (`?`)** and **SQLite introspection**, not `lastrowid`.

Critical write paths that must use transactions + dialect-portable SQL on Postgres.

## POS finalization

- `modules.py:5290`
- `modules.py:5301`
- `modules.py:801`
- `scripts/run_postgres_schema_compatibility_audit.py:59`

## Invoice posting

- `accounting_engine.py:939`
- `modules.py:12892`
- `modules.py:4350`

## Bill posting

- `modules.py:6050`
- `modules.py:8459`

## Payments

- `migration_cleanup.py:377`
- `modules.py:13340`

## Inventory movements

- `modules.py:4424`

## Stock adjustments

- `modules.py:4419`
- `modules.py:758`

## Payroll posting

- `modules.py:14287`

## Depreciation

- `modules.py:105`
- `modules.py:4056`

## Year-end close

- `modules.py:3208`
- `modules.py:88`

## Branch creation

- `database.py:5298`
- `database.py:5394`

## User creation

- `database.py:5642`
- `database.py:5704`

## Postgres Requirements per Path

- Use `execute_db_write_transaction()` or equivalent single-connection transactions.
- **Identity (done on listed paths):** `ensure_insert_sql_returning()` + `get_inserted_id()` (Postgres uses `RETURNING id`).
- **Still required:** Route SQL parameters through `db_placeholders()` / `%s` on Postgres.
- Avoid `PRAGMA` / `sqlite_master` in write paths (use `db_table_exists` / `db_column_exists`).
- POS/inventory: preserve row-level locking strategy (Postgres `SELECT FOR UPDATE` where needed).
