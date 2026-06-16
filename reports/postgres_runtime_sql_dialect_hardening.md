# PostgreSQL Runtime SQL Dialect Hardening

Phase: 5B.15R

Controlled runtime SQL dialect hardening only. No commit, push, SQLite data modification, SQLite backup deletion, data migration, or production deployment was performed.

## Goal

PostgreSQL runtime boots and login works, but common page-load paths still failed on SQLite-specific SQL: raw `?` placeholders bypassing portable helpers, and runtime self-heal DDL using `AUTOINCREMENT` / `PRAGMA` / `sqlite_master`. This phase blocks SQLite-only runtime DDL under PostgreSQL and converts high-priority read/page-load paths to backend-aware helpers.

## SQL Dialect Findings

| Area | Finding | Classification | Disposition |
|---|---|---|---|
| Dashboard low stock (`app.py`) | `_show_local_dashboard()` used `pd.read_sql_query()` with raw `?` placeholders | fixed now | Replaced with `execute_portable_query()` + `rows_to_dicts()` |
| Dashboard low stock (`modules.py`) | Branch-aware dashboard used `PRAGMA table_info(inventory)` and `pd.read_sql_query()` | fixed now | Uses `list_columns()` and `_portable_read_dataframe()` |
| POS page load | `ensure_pos_sales_schema()` / `ensure_cashier_closings_schema()` executed SQLite `CREATE TABLE ... AUTOINCREMENT` and `PRAGMA` under PostgreSQL runtime | fixed now | Added `should_skip_sqlite_runtime_ddl()` guard in runtime self-heal helpers |
| Inventory page load | `ensure_inventory_schema_integrity()` attempted SQLite DDL; metrics/overview used `pd.read_sql_query()` | fixed now | DDL blocked on PostgreSQL; reads use `_portable_read_dataframe()` |
| POS initial reads | Company/branch/inventory bootstrap queries used raw `conn.execute()` with `?` | fixed now | Converted to `execute_portable_query()` + `row_get()` / `rows_to_dicts()` |
| System logging | `log_system_event()` always ran SQLite `CREATE TABLE ... AUTOINCREMENT` | fixed now | Skips SQLite DDL on PostgreSQL; insert uses `execute_portable_write()` |
| Chart of accounts reads | Journal and COA pages used raw `conn.execute()` / tuple row assumptions | fixed now | Converted to portable SELECT helpers and row normalization |
| Journal report reads | Journal entries page and `_journal_dataframe()` used `pd.read_sql_query()` | fixed now | Uses portable SELECT helpers and DataFrame normalization |
| Financial chart lookup | `_chart_lookup()` used raw SQLite cursor reads | fixed now | Uses `execute_portable_query()` + `row_get()` |
| Inventory average-cost probe | `_inventory_has_average_cost()` used `PRAGMA table_info(inventory)` | fixed now | Uses backend-aware `list_columns()` |
| AI assistant table probe | `_table_exists()` used `sqlite_master` | fixed now | Uses `db_table_exists()` |
| Accounting source introspection | `_source_document_columns()` used `PRAGMA table_info()` | fixed now | Uses `list_columns()` |
| POS search/lookup hot paths | `_lookup_inventory_for_pos()` and related search SQL still use raw `conn.execute()` with `?` | deferred write/interaction blocker | Page load is hardened; interactive POS search/checkout writes need staged PostgreSQL validation |
| Financial write workflows | Customer/supplier `INSERT OR IGNORE`, invoice/bill/payment posting still SQLite-native | deferred write-path blocker | Page-load reads already portable; writes remain staged |
| Accounting posting/integrity | Remaining `PRAGMA`, `sqlite_master`, `date()` filters, and write placeholders in posting engine | deferred write-path blocker | Read/report surfaces hardened; posting workflows remain staged |
| Startup/schema deployment | SQLite bootstrap, recovery, and full schema deployment remain SQLite-native by design | intentionally SQLite-only recovery/admin | Existing PostgreSQL startup guard unchanged |

## Functions Changed

- `database.py`
  - Added `should_skip_sqlite_runtime_ddl()`.
  - Guarded `ensure_branch_licensing_schema_integrity()`, `ensure_inventory_schema_integrity()`, `ensure_stock_movements_schema_integrity()`, `ensure_cashier_closings_schema()`, and `ensure_pos_sales_schema()` from SQLite-only runtime DDL under PostgreSQL.

- `app.py`
  - Hardened `_show_local_dashboard()` low-stock query to use portable SELECT helpers.

- `modules.py`
  - Added `_portable_read_dataframe()`.
  - Hardened `_table_exists()`, `_inventory_has_average_cost()`, and `log_system_event()`.
  - Hardened POS page-load reads, inventory metrics/overview reads, journal report reads, chart-of-accounts reads, and branch-aware dashboard low-stock reads.

- `financials.py`
  - Hardened `_chart_lookup()` for portable SELECT execution and row access.

- `accounting_engine.py`
  - Hardened `_source_document_columns()` and `_journal_dataframe()` for backend-aware introspection and read paths.

## Tests Added

- `tests/test_postgres_runtime_sql_dialect_hardening.py`
  - Dashboard low-stock query converts placeholders under PostgreSQL.
  - POS/inventory runtime self-heal skips SQLite `AUTOINCREMENT` DDL under PostgreSQL.
  - `log_system_event()` skips SQLite `CREATE TABLE` under PostgreSQL.
  - Inventory metrics portable read converts placeholders under PostgreSQL.
  - SQLite runtime self-heal and system-log creation remain unchanged.

## Validation Results

- Focused dialect hardening tests: PASSED (6/6)
- `python -m py_compile app.py database.py modules.py financials.py accounting_engine.py`: PASSED
- `python tests/run_regression_tests.py`: PASSED (416/416)
- `git diff --check`: PASSED

## Runtime Retry Status

PostgreSQL runtime page testing can resume in staging after validation passes for:

- Dashboard and inventory cards
- POS page load
- Invoices/customers/suppliers page-load reads
- Chart of accounts and journal report reads
- Sidebar/settings reads already hardened in Phase 5B.15Q

Remaining deferred blockers for later phases:

- POS interactive search/checkout writes
- Financial and accounting write/posting workflows
- Residual raw placeholders in non-page-load module paths

Production deployment remains blocked until explicit production approval and final deployment validation.
