# PostgreSQL Runtime Dry-Run Report

Phase: 5B.15L

Controlled PostgreSQL runtime dry-run validation only. PostgreSQL runtime was not permanently enabled, SQLite data was not modified, application data was not written, migrations were not run, and production was not deployed.

## Summary

- Status: READY_FOR_RUNTIME_CUTOVER
- Started at: 2026-06-14T12:20:07.627552+00:00
- Completed at: 2026-06-14T12:20:13.957047+00:00
- Checks performed: 13
- Checks passed: 13
- Checks failed: 0
- Startup validation result: PASSED
- Business-module validation result: PASSED
- Reporting validation result: PASSED
- Runtime cutover readiness: READY_FOR_RUNTIME_CUTOVER
- PostgreSQL runtime permanently enabled: False
- SQLite data modified: False
- Production deployed: False

## Guards

- Blocked: False
- Message: Runtime dry-run guards passed for read-only staging checks.
- DATABASE_URL: postgresql://postgres.buzfvrhynszolxejdzen:***@aws-1-eu-west-1.pooler.supabase.com:6543/postgres
- PostgreSQL driver: psycopg2
- ERP_ENVIRONMENT_is_staging: True
- ERP_ENABLE_POSTGRES_RUNTIME_DRYRUN_is_enabled: True
- DATABASE_URL_present: True
- postgres_driver_available: True

## Checks Performed

| Category | Check | Tables validated | Count returned | Result | Detail |
|---|---|---|---:|---|---|
| startup | database_identity metadata | `database_identity` | 1 | PASSED | SELECT COUNT(*) succeeded |
| startup | migration_history metadata | `migration_history` | 2 | PASSED | SELECT COUNT(*) succeeded |
| startup | companies startup source | `companies` | 8 | PASSED | SELECT COUNT(*) succeeded |
| startup | users startup source | `users` | 3 | PASSED | SELECT COUNT(*) succeeded |
| business | chart_of_accounts read path | `chart_of_accounts` | 38 | PASSED | SELECT COUNT(*) succeeded |
| business | customers read path | `customers` | 2 | PASSED | SELECT COUNT(*) succeeded |
| business | suppliers read path | `suppliers` | 4 | PASSED | SELECT COUNT(*) succeeded |
| business | inventory read path | `inventory` | 3 | PASSED | SELECT COUNT(*) succeeded |
| business | invoices read path | `invoices` | 1 | PASSED | SELECT COUNT(*) succeeded |
| business | payments read path | `payments` | 8 | PASSED | SELECT COUNT(*) succeeded |
| business | journal_entries read path | `journal_entries` | 28 | PASSED | SELECT COUNT(*) succeeded |
| reporting | financial reports data sources | `journal_entries,journal_lines,chart_of_accounts` | 61 | PASSED | read-only source query succeeded |
| reporting | dashboard metrics sources | `companies,users,customers,inventory,invoices,payments,journal_entries` | 53 | PASSED | read-only source query succeeded |

## Failures And Blockers

- No failures or blockers found.

## Final Readiness Status

- READY_FOR_RUNTIME_CUTOVER
- Runtime cutover can proceed after review and an explicit approved cutover action.
