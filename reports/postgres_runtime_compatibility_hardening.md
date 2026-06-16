# PostgreSQL Runtime Compatibility Hardening

Phase: 5B.15Q

Controlled runtime compatibility hardening only. No commit, push, SQLite data modification, SQLite backup deletion, data migration, or production deployment was performed.

## Goal

PostgreSQL runtime now starts and login works, but common UI paths were still vulnerable to SQLite row-shape assumptions. The known failure was `_render_currency_sidebar_controls()` reading `settings_row["display_currency"]` from a PostgreSQL tuple row. This phase adds central row compatibility helpers and hardens common app-shell reads so PostgreSQL runtime can be retried without repeated tuple/dict crashes.

## Findings

| Area | Finding | Classification | Disposition |
|---|---|---|---|
| Row shape | Runtime code mixes `row["column"]`, `row[0]`, `dict(row)`, and tuple assumptions. PostgreSQL cursors may return tuples unless wrapped. | fixed now | Added `CompatibleRow`, `row_get()`, `row_to_dict()`, and `rows_to_dicts()` in `database.py`. |
| Portable SELECTs | `execute_portable_query()` converted placeholders but returned raw cursor rows. | fixed now | It now wraps described cursor results so rows support both key and positional access. |
| PostgreSQL adapter | Direct `PostgresManagedConnection.execute()` returned raw psycopg cursor rows. | fixed now | It now returns compatible rows for described result sets while leaving non-result writes untouched. |
| Sidebar currency | `_render_currency_sidebar_controls()` indexed `settings_row["display_currency"]` and used a raw SQLite-style update. | fixed now | Uses `execute_portable_query()`, `row_get()`, and `execute_portable_write()`. |
| Login/recovery | Password-recovery reads used portable SELECTs but still indexed rows by key directly. | fixed now | Recovery question and reset lookup now use `row_get()`; reset update uses `execute_portable_write()`. |
| User/session context | Session-lock and restored-admin checks used direct row/index reads. | fixed now | Session lock and restored-company admin checks use portable SELECTs and compatible row access. |
| Company/branch context | Branch selector and branch caption used raw placeholder queries and tuple assumptions. | fixed now | Branch reads use `execute_portable_query()` and `row_get()`. |
| Dashboard/cards | Dashboard low-stock table and metric reads could receive PostgreSQL-compatible rows. | fixed now | Dashboard metrics remain portable; low-stock rows are normalized before DataFrame creation. |
| System status | Maintenance status and journal-dominance company selector used direct cursor or row-key assumptions. | fixed now | These reads now use portable SELECTs and row helpers. |
| Admin portfolio | `pd.read_sql()` on the managed PostgreSQL connection wrapper is risky. | fixed now | Replaced with `execute_portable_query()` plus `rows_to_dicts()` before DataFrame creation. |
| Startup/schema/recovery | SQLite schema bootstrap, `PRAGMA`, `sqlite_master`, local health, and backup restore remain SQLite-native. | intentionally SQLite-only recovery/admin | Existing PostgreSQL startup guard and recovery blocks keep these out of PostgreSQL runtime. |
| `modules.py` currency/context reads | `get_display_currency()`, `get_exchange_rate()`, supplier-name loading, branch list reads, and accounting AI context summaries used direct cursor rows or `dict(row)`. | fixed now | Converted to `execute_portable_query()`, `row_get()`, `row_to_dict()`, and `rows_to_dicts()` where safe. |
| `financials.py` page-load reads | Customer/supplier/invoice/bill/payment page-load tables and customer/supplier selectbox reads used `pd.read_sql_query()` or direct row indexing. | fixed now | Added `_portable_read_dataframe()` and converted common page-load SELECTs plus party ID lookups to portable helpers. |
| `accounting_engine.py` report settings/chart reads | System setting and chart-of-accounts diagnostics used SQLite row shape or `dict(row)`. | fixed now | Converted to `list_columns()`, `execute_portable_query()`, `row_get()`, and `rows_to_dicts()` for read-only report surfaces. |
| `modules.py` write-heavy feature pages | POS, inventory, audit, branch governance, suppliers, and dashboard modules still include SQLite-native introspection and many raw placeholders. | needs page-level PostgreSQL test | Deferred for staged module-by-module hardening where writes or schema probes are involved. |
| `financials.py` write workflows | Customer/supplier creation, invoice/bill/payment posting, and related accounting writes still contain raw placeholders and SQLite `INSERT OR IGNORE`. | deferred write-path blocker | Page-load reads were hardened; write-heavy workflows need separate guarded PostgreSQL write validation. |
| `accounting_engine.py` journals/posting | Posting and integrity code still includes `PRAGMA`, `sqlite_master`, raw placeholders, and SQL-dialect assumptions. | needs page-level PostgreSQL test | Read-only chart/settings surfaces were hardened; journal posting and integrity workflows remain deferred blockers. |

## Functions Changed

- `database.py`
  - Added `CompatibleRow`.
  - Added `row_get(row, key, default=None, columns=None)`.
  - Added `row_to_dict(row, columns=None)`.
  - Added `rows_to_dicts(rows, columns=None)`.
  - Added `PortableCursorResult`.
  - Updated `execute_portable_query()` to wrap described cursor results.
  - Updated `PostgresManagedConnection.execute()` to return key/index compatible rows for result sets.
  - Routed the existing subscription `_row_to_dict()` helper through the central compatibility helper.

- `app.py`
  - Hardened `_render_currency_sidebar_controls()`.
  - Hardened password recovery and reset lookup row access.
  - Hardened `check_maintenance_status()`.
  - Hardened dashboard low-stock row normalization.
  - Hardened session-lock and restored-admin company context reads.
  - Hardened branch selector and branch caption reads.
  - Hardened system-health company selector.
  - Replaced admin portfolio `pd.read_sql()` with portable query row normalization.

- `modules.py`
  - Hardened `get_display_currency()` and `get_exchange_rate()`.
  - Hardened `get_company_branches()` and supplier-name loading.
  - Hardened accounting AI context summaries by normalizing rows through shared helpers.

- `financials.py`
  - Added `_portable_read_dataframe()`.
  - Hardened common customer, supplier, invoice, bill, payment, journal, and fixed-asset depreciation read tables.
  - Hardened customer/supplier party ID read lookups with `row_get()`.

- `accounting_engine.py`
  - Hardened chart-of-accounts diagnostics row normalization.
  - Hardened system-setting reads using backend-aware column introspection and row access.

## Tests Added

- `tests/test_postgres_auth_subscription_runtime_portability.py`
  - Row helpers support dict, SQLite row, tuple with columns, namedtuple, and object attribute rows.
  - `execute_portable_query()` returns rows that support both `row["column"]` and `row[0]` under PostgreSQL-style cursor metadata.
  - Sidebar currency controls tolerate PostgreSQL tuple rows.
  - Module currency helpers tolerate PostgreSQL tuple rows.
  - Financial page-load DataFrame helper normalizes PostgreSQL tuple rows.
  - Dashboard metric reads work with described PostgreSQL rows.
  - Company context repair checks use the PostgreSQL connection without opening SQLite.
  - Existing login/access-key, subscription, system diagnostics, recovery blocking, and SQLite behavior tests remain covered.

## Validation Results

- Focused hardening tests: PASSED
- `python -m py_compile app.py database.py modules.py financials.py accounting_engine.py`: PASSED
- `python tests/run_regression_tests.py`: PASSED
- `git diff --check`: PASSED

## Runtime Retry Status

PostgreSQL runtime can be retried in staging after full validation passes with:

- `DB_BACKEND=postgres`
- `ERP_ENABLE_POSTGRES_RUNTIME=1`
- `ERP_ENVIRONMENT=staging`
- `DATABASE_URL=<staging PostgreSQL connection string>`

Production deployment remains blocked until explicit production approval and final deployment validation.
