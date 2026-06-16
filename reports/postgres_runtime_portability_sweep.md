# PostgreSQL Runtime Portability Sweep

Phase: 5B.15P

Controlled portability sweep only. No commit, push, SQLite data modification, SQLite backup deletion, or production deployment was performed.

## Goal

PostgreSQL runtime can start, but runtime read paths must not fall back to SQLite when `DB_BACKEND=postgres` and `ERP_ENABLE_POSTGRES_RUNTIME=1`. This sweep audited direct SQLite usage across `app.py`, `database.py`, `modules.py`, `financials.py`, `accounting_engine.py`, tests, and reports, then fixed the high-priority runtime blockers that affect login/auth, subscription reads, company lookup, dashboard read counts, and system diagnostics.

## SQLite Direct-Call Findings

| Area | Finding | Classification | Disposition |
|---|---|---|---|
| `database.py` auth/subscription | `get_subscription_plan_settings()` and related subscription helpers previously opened `_open_sqlite_connection()` by default. | subscription/licensing | Fixed in prior auth/subscription portability pass and verified in this sweep. Defaults now route through `get_connection()` and portable SELECT helpers. |
| `app.py` login/access-key | Company, branch, staff, recovery-question, password-reset, and session-lock reads used active connections with raw SQLite `?` placeholders. | login/auth, company selection, user lookup | Fixed in prior auth/subscription portability pass and verified in this sweep. Reads use `authenticate_access_key_read_path()` and `execute_portable_query()`. |
| `app.py` dashboard metrics | Inventory value, payroll employee count, fixed-asset value, and gatekeeper company count used direct `conn.execute()` calls with SQLite placeholders. | dashboard, system status | Fixed. Dashboard source counts now use `get_dashboard_metric_counts()` and `execute_portable_query()`. |
| `database.py` system diagnostics | `get_db_diagnostics()` unconditionally built SQLite file health and SQLite concurrency diagnostics. | system status/recovery | Fixed. When PostgreSQL is active it reports backend/cutover evidence diagnostics without opening SQLite health or concurrency probes. |
| `database.py` restore/recovery | Cloud restore and trusted recovery inspect or replace the local SQLite database. | system status/recovery | Intentionally SQLite-only and now blocked under active PostgreSQL runtime before SQLite health inspection or file replacement. |
| `database.py` startup/schema | SQLite bootstrap, schema integrity, migrations, `PRAGMA`, `sqlite_master`, `row_factory`, `sqlite3.connect`, and local database validation remain extensive. | startup | Intentionally SQLite-only. Startup remains skipped/blocked when PostgreSQL runtime guard passes. |
| `modules.py` dashboard/POS/inventory/audit | Several runtime module reads still use `PRAGMA` for column detection and raw `conn.execute(... ? ...)` for feature areas such as POS, suppliers, inventory, and audit. | POS, inventory, suppliers, dashboard, system status | Not changed in this narrow sweep unless part of requested high-priority blockers. These require staged module-by-module PostgreSQL portability. |
| `financials.py` customer/supplier UI | Customer/supplier reads and writes use raw SQLite placeholders and SQLite `INSERT OR IGNORE`. | customers, suppliers | Left unchanged. These are broader feature workflows and not part of the immediate login/subscription/dashboard blocker set. |
| `accounting_engine.py` journal/report paths | Accounting reads use `sqlite_master`, `PRAGMA`, raw placeholders, and SQLite-oriented checks. | chart of accounts, journals/reports | Left unchanged. Reporting portability remains a follow-up migration area. |
| tests | Test fixtures intentionally open SQLite isolated databases. | tests | Intentionally SQLite-only for regression coverage. New PostgreSQL runtime tests mock SQLite opening to enforce no fallback on guarded read paths. |

## Functions Fixed Or Verified

- `database.py`
  - `get_db_diagnostics()` no longer opens SQLite health or concurrency diagnostics when active backend is PostgreSQL.
  - `restore_latest_cloud_backup_to_local()` now blocks before SQLite restore work under PostgreSQL runtime.
  - `attempt_production_database_recovery()` now blocks before SQLite recovery work under PostgreSQL runtime.
  - Subscription-plan and subscription metadata reads remain routed through backend-aware connections and portable SELECT helpers.

- `app.py`
  - Added `get_dashboard_metric_counts()` for backend-aware dashboard source reads.
  - Routed dashboard inventory, payroll, fixed asset, and gatekeeper company count reads through `execute_portable_query()`.
  - Verified login/access-key reads continue to use `authenticate_access_key_read_path()` and portable placeholders.

## Runtime Guard Coverage

When PostgreSQL runtime is active, the covered login/auth, subscription, company lookup, dashboard read counts, and system diagnostics paths must not call `_open_sqlite_connection()`. Focused tests patch `_open_sqlite_connection()` to raise if these paths regress.

SQLite-only recovery and restore paths are explicitly blocked under active PostgreSQL runtime with `stage=postgres_runtime_recovery_blocked`; they do not inspect SQLite health or replace the SQLite file in that mode.

## Tests Added

- `tests/test_postgres_auth_subscription_runtime_portability.py`
  - PostgreSQL runtime dashboard metric reads do not open SQLite and convert placeholders to `%s`.
  - PostgreSQL runtime system diagnostics do not open SQLite health or concurrency diagnostics.
  - PostgreSQL runtime recovery/restore paths are blocked before SQLite access.
  - Existing coverage continues to verify login/access-key and subscription-plan reads avoid SQLite and keep SQLite behavior working with injected SQLite connections.

## Validation Results

- Focused portability tests: PASSED
- `python -m py_compile app.py database.py modules.py financials.py accounting_engine.py`: PASSED
- `python tests/run_regression_tests.py`: PASSED
- `git diff --check`: PASSED

## Runtime Retry Status

PostgreSQL runtime retry can proceed in staging after the full validation suite passes, using:

- `DB_BACKEND=postgres`
- `ERP_ENABLE_POSTGRES_RUNTIME=1`
- `ERP_ENVIRONMENT=staging`
- `DATABASE_URL=<staging PostgreSQL connection string>`

Production deployment remains blocked until explicit production approval and final deployment validation.
