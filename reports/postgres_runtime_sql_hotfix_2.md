# PostgreSQL Runtime SQL Hotfix 2

Phase: 5B.15S

Controlled hotfix only. No commit, push, SQLite data modification, backup deletion, data migration, or transactional posting was performed.

## Problem

After Phase 5B.15R, PostgreSQL runtime still failed on two page-load paths:

1. **Dashboard** — `syntax error at end of input ... FROM inventory WHERE company_key = ? ^`
2. **POS** — `syntax error at or near "ORDER" LINE 5: ORDER BY name ^`

## Root Cause

`PostgresManagedConnection.execute()` passes SQL directly to psycopg and does **not** convert SQLite `?` placeholders. Phase 5B.15R hardened several paths, but two high-traffic bundles still used raw `conn.execute()`:

- Executive dashboard analytics (`_fetch_dashboard_kpi_snapshot` and related dashboard bundle readers) for inventory KPI SQL ending in `company_key = ?`
- POS page load via `get_customer_balances()` with a five-line query ending in `ORDER BY name`

The POS error line number matched the customer lookup query exactly. PostgreSQL also treats bare `name` as ambiguous in `ORDER BY`; qualifying as `customers.name` avoids parser confusion.

## Exact Queries Fixed

| Location | Before | After |
|---|---|---|
| `modules._fetch_dashboard_kpi_snapshot()` | `conn.execute("... FROM inventory WHERE company_key = ?...")` | `_portable_fetchone()` / `_portable_fetchall()` via `execute_portable_query()` |
| `modules._fetch_dashboard_kpi_snapshot()` low-stock count | `conn.execute("SELECT qty, min_stock_level FROM inventory WHERE company_key = ?...")` | `_portable_fetchall()` |
| `modules._fetch_dashboard_kpi_snapshot()` cash/bank balance | raw `conn.execute(...)` | `_portable_fetchone()` |
| `modules._fetch_dashboard_sales_analytics()` | six raw POS analytics `conn.execute(...)` calls | `_portable_fetchall()` |
| `modules._fetch_dashboard_inventory_insights()` | raw inventory/POS/stock-movement `conn.execute(...)` calls | `_portable_fetchall()` |
| `modules._dashboard_branch_ledger_balance()` | raw `conn.execute(...)` | `_portable_fetchone()` |
| `modules._dashboard_stock_movement_branch_sql()` | `PRAGMA table_info(stock_movements)` | `list_columns()` |
| `accounting_engine.get_customer_balances()` | `conn.execute(... ORDER BY name)` | `execute_portable_query(... ORDER BY customers.name)` |
| `accounting_engine.get_supplier_balances()` | `conn.execute(... ORDER BY name)` | `execute_portable_query(... ORDER BY suppliers.name)` |
| `accounting_engine.get_ar_aging_report()` customer seed query | `conn.execute(... ORDER BY name)` | `execute_portable_query(... ORDER BY customers.name)` |

## Helper Additions

- `modules._portable_fetchone()`
- `modules._portable_fetchall()`

## Tests Added

- `tests/test_postgres_runtime_sql_hotfix_2.py`
  - Dashboard inventory KPI query emits `%s`, not raw `?`
  - POS `get_customer_balances()` emits valid PostgreSQL SQL with `ORDER BY customers.name`
  - SQLite customer balance ordering unchanged
  - SQLite dashboard inventory KPI still reads inventory totals

## Validation Results

- Focused hotfix tests: PASSED (4/4)
- `python -m py_compile app.py database.py modules.py financials.py accounting_engine.py`: PASSED
- `python tests/run_regression_tests.py`: PASSED (420/420)
- `git diff --check`: PASSED

## Runtime Retry Status

PostgreSQL runtime page testing can resume in staging for:

- Executive dashboard KPI/inventory cards
- POS page load customer lookup

Remaining deferred blockers:

- POS interactive inventory search helpers (`_lookup_inventory_for_pos`, `_search_inventory_for_pos`) still use raw `conn.execute()`
- Other module write/interaction paths outside this hotfix scope

Production deployment remains blocked until explicit production approval and final deployment validation.
