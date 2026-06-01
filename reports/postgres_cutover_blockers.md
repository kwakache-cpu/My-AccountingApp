# PostgreSQL Runtime Cutover Blockers (Phase 5B.11)

**Audited at:** 2026-06-01 20:09:00 UTC

**Assumed env (not enabled in this audit):**
```
DB_BACKEND="postgres"
ERP_ENABLE_POSTGRES_RUNTIME="1"
DATABASE_URL="postgresql://..."
```

Analysis based on `get_connection()`, `ensure_schema()`, `get_postgres_readiness_diagnostics()`, and scoped code review.

## Subsystem Failure Matrix

| Subsystem | Would fail today? | Classification | Primary cause |
|-----------|-------------------|----------------|---------------|
| **Schema ensure** (`ensure_schema`, `_deploy_full_schema`) | **Yes** | **Hard blocker** | SQLite DDL (`AUTOINCREMENT`, `PRAGMA table_info`), no Postgres schema bootstrap |
| **Migrations** (`erp_migrations.py`) | **Yes** | **Hard blocker** | `sqlite_master`, `PRAGMA`, `INSERT OR IGNORE`, literal `?` |
| **Startup checks** (`get_postgres_readiness_diagnostics`) | **Partial** | **High risk** | Diagnostics use `sqlite_master`/`PRAGMA` even when probing readiness |
| **Dashboard** (`app.py` → modules) | **Yes** | **High risk** | Underlying queries use `?`, `PRAGMA`, `sqlite_master` in modules |
| **POS** (`finalize_pos_sale`, stock) | **Likely** | **High risk** | Identity OK via `get_inserted_id`; SQL placeholders and inventory `PRAGMA` not |
| **Accounting posting** | **Likely** | **Medium risk** | `post_journal_entry` identity portable; `strftime` period filters and `?` SQL remain |
| **Branch governance** | **Likely** | **High risk** | Grant repair uses SQLite introspection patterns in database.py |
| **Inventory** | **Likely** | **High risk** | `PRAGMA table_info(inventory)` in accounting_engine; movement SQL uses `?` |
| **Reporting** | **Likely** | **High risk** | `accounting_engine` trial balance / GL use `?` and `strftime('%Y-%m', je.date)` |
| **Auth/login** | **Partial** | **Medium risk** | User lookup SQL uses `?`; schema for `users` not ensured on Postgres |

## Hard Blockers (must fix before any staging cutover)

1. **No Postgres DDL path** — `_deploy_full_schema` / `ensure_schema_integrity` only emit SQLite syntax.
2. **~600+ literal `?` placeholders** across core modules — psycopg requires `%s`.
3. **Schema introspection** — widespread `PRAGMA` / `sqlite_master` outside `db_table_exists` / `db_column_exists` helpers.
4. **No migrated Postgres database** — data still in `eka_enterprise_v3.db`; cutover requires ETL (out of scope).

## High Risk (may connect but core flows break)

- `get_connection()` can open Postgres when validation passes, but callers assume SQLite row tuples and semantics.
- `get_postgres_readiness_diagnostics()` runs SQLite catalog queries — misleading or errors on Postgres conn.
- Financial dashboards and branch license snapshots depend on modules SQL not yet dialect-routed.

## Medium Risk

- `INSERT OR IGNORE` in `financials.py` / `erp_migrations.py` (not using `db_insert_ignore_sql()`).
- Accounting period reports using SQLite `strftime` in SQL.
- INTEGER 0/1 booleans — work on Postgres but differ from native BOOLEAN.

## Low Risk

- Identity retrieval on converted paths (POS, payments, journal, payroll, bills, invoices).
- FK orphan count is zero on current SQLite snapshot (data readiness good on SQLite).
- `test_postgres_connection()` — connectivity probe only, not app readiness.

## Expected first failures (ordered)

1. App startup → `ensure_schema()` → syntax error on `AUTOINCREMENT` / `PRAGMA`.
2. If schema skipped → first `execute('... ? ...')` → psycopg programming error.
3. If some queries work → `PRAGMA table_info` in accounting_engine inventory guard.
4. Reporting month filter → `strftime` function does not exist.
