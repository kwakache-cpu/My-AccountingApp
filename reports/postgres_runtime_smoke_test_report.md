# PostgreSQL Runtime Smoke Test Report

Phase: 5B.15N

Controlled staging/local PostgreSQL runtime activation smoke test only. No commit, push, SQLite modification, SQLite backup deletion, or production deployment was performed.

## Summary

- Status: READY_FOR_STREAMLIT_SECRETS_CUTOVER
- Started at: 2026-07-01T01:58:37.760809+00:00
- Completed at: 2026-07-01T01:58:37.762414+00:00
- Configured backend: postgres
- Active backend: postgres
- Startup result: PASSED
- Startup stage: postgres_runtime_startup
- SQLite bootstrap blocked: True
- Read checks passed: 9
- Read checks failed: 0
- Streamlit secrets cutover can proceed: True

## Guards

- Blocked: False
- Message: Runtime smoke test guards passed for controlled staging/local PostgreSQL checks.
- DATABASE_URL: postgresql://user:***@example.test:5432/postgres
- PostgreSQL driver: psycopg2
- DB_BACKEND_is_postgres: True
- ERP_ENABLE_POSTGRES_RUNTIME_is_enabled: True
- ERP_ENVIRONMENT_is_staging: True
- DATABASE_URL_present: True
- postgres_driver_available: True

## Checks

| Category | Check | Count | Result | Detail |
|---|---|---:|---|---|
| startup | startup stays off SQLite bootstrap |  | PASSED | stage=postgres_runtime_startup; should_run_sqlite_startup=False |
| connection | PostgreSQL connection opens | 1 | PASSED |  |
| read_path | companies can be read | 8 | PASSED | SELECT COUNT(*) succeeded |
| read_path | users can be read | 3 | PASSED | SELECT COUNT(*) succeeded |
| read_path | chart_of_accounts can be read | 38 | PASSED | SELECT COUNT(*) succeeded |
| read_path | customers can be read | 2 | PASSED | SELECT COUNT(*) succeeded |
| read_path | inventory can be read | 3 | PASSED | SELECT COUNT(*) succeeded |
| read_path | journal_entries can be read | 28 | PASSED | SELECT COUNT(*) succeeded |
| dashboard | dashboard source counts work | 82 | PASSED |  |

## Blockers

- No blockers found.

## Rollback Instruction

- If any smoke check regresses, remove or unset `ERP_ENABLE_POSTGRES_RUNTIME`, set `DB_BACKEND=sqlite`, remove or restore `DATABASE_URL` to the prior configuration, redeploy the previous known-good app, and verify SQLite company/user/customer/inventory/chart/journal counts.
