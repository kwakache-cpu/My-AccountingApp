# PostgreSQL Auth And Subscription Runtime Portability

Phase: 5B.15P

Controlled portability fix only. No commit, push, SQLite data modification, SQLite backup deletion, or production deployment was performed.

## Root Cause

After guarded PostgreSQL runtime startup was enabled, login and subscription-plan reads still hit SQLite-specific paths. The immediate failing path was `database.py` `get_subscription_plan_settings()`, which opened `_open_sqlite_connection()` when no connection was injected. Related subscription metadata helpers also defaulted to `_open_sqlite_connection()`, and the login/access-key UI path used raw `?` placeholders directly against the active connection.

## Functions Fixed

- `database.py`
  - `get_subscription_plan_settings()`
  - `get_subscription_plan_setting()`
  - `get_company_subscription_snapshot()`
  - `get_subscription_billing_summary()`
  - `get_subscription_billing_diagnostics()`
  - Added `_row_to_dict()` for tuple-style PostgreSQL cursor rows.

- `app.py`
  - Added `authenticate_access_key_read_path()` for read-only company access-key, branch access-key, and staff login lookup.
  - Routed login/access-key and recovery read SELECTs through `execute_portable_query()`.
  - Kept existing business logic and session behavior unchanged.

## Portability Rules

- Default subscription reads now use `get_connection()` instead of `_open_sqlite_connection()`.
- SQLite billing schema ensure remains SQLite-only and is skipped under PostgreSQL runtime.
- Read SELECTs use `execute_portable_query()` so `?` placeholders become `%s` under PostgreSQL runtime.
- SQLite behavior remains unchanged for injected SQLite connections.
- PostgreSQL runtime must not open SQLite for subscription-plan reads.

## Tests Added

- `tests/test_postgres_auth_subscription_runtime_portability.py`
  - `get_subscription_plan_settings()` works with an injected PostgreSQL-like connection.
  - `get_subscription_plan_setting()` converts placeholders to `%s`.
  - default PostgreSQL subscription-plan reads do not call `_open_sqlite_connection()`.
  - injected SQLite subscription-plan reads still work.
  - login/access-key read path uses portable PostgreSQL placeholders and does not open SQLite.

Focused compatibility tests also covered existing company subscription DML and auth read placeholder behavior.

## Validation Results

- Focused auth/subscription portability tests: PASSED
- `python -m py_compile app.py database.py modules.py financials.py accounting_engine.py`: PASSED
- `python tests/run_regression_tests.py`: PASSED
- `git diff --check`: PASSED

## Runtime Cutover Retry

Runtime cutover can be retried for staging after final validation passes with:

- `DB_BACKEND=postgres`
- `ERP_ENABLE_POSTGRES_RUNTIME=1`
- `ERP_ENVIRONMENT=staging`
- `DATABASE_URL=<staging PostgreSQL connection string>`

Production deployment remains blocked until explicit approval and final deployment validation.
