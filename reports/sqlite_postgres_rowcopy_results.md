# SQLite to PostgreSQL Row-Copy Results

Phase: 5B.15H

Guarded staging row-copy report. PostgreSQL runtime was not enabled, production deployment was not attempted, application runtime was not changed, and SQLite was opened read-only.

## Summary

- Status: COMPLETED
- Started at: 2026-06-14T06:57:12.571360+00:00
- Completed at: 2026-06-14T06:59:06.543214+00:00
- Dry-run status: READY_FOR_DRY_RUN_COPY
- Batches planned: 31
- Batches executed: 31
- Rows planned: 527
- Rows copied: 527
- Committed: True
- Rolled back: False

## Guards

- Blocked: False
- Message: Row-copy guards passed for staging execution.
- DATABASE_URL: postgresql://postgres.buzfvrhynszolxejdzen:***@aws-1-eu-west-1.pooler.supabase.com:6543/postgres
- PostgreSQL driver: psycopg2
- ERP_ENABLE_POSTGRES_ROW_COPY: True
- ERP_ENVIRONMENT_is_staging: True
- DATABASE_URL_present: True
- DATABASE_URL_valid: True
- explicit_copy_rows_flag: True
- explicit_confirm_row_copy_flag: True
- postgres_driver_available: True

## Table Results

| Table | Status | Batches | Rows planned | Rows copied | Error |
|---|---|---:|---:|---:|---|
| `branch_type_catalog` | COMPLETED | 1/1 | 6 | 6 |  |
| `companies` | COMPLETED | 1/1 | 8 | 8 |  |
| `customers` | COMPLETED | 1/1 | 2 | 2 |  |
| `database_identity` | COMPLETED | 1/1 | 1 | 1 |  |
| `journal_entries` | COMPLETED | 1/1 | 28 | 28 |  |
| `license_payment_transactions` | COMPLETED | 1/1 | 2 | 2 |  |
| `maintenance_settings` | COMPLETED | 1/1 | 1 | 1 |  |
| `migration_history` | COMPLETED | 1/1 | 2 | 2 |  |
| `migration_logs` | COMPLETED | 1/1 | 2 | 2 |  |
| `payments` | COMPLETED | 1/1 | 8 | 8 |  |
| `payroll_records` | COMPLETED | 1/1 | 1 | 1 |  |
| `schema_version` | COMPLETED | 1/1 | 2 | 2 |  |
| `subscription_plan_settings` | COMPLETED | 1/1 | 3 | 3 |  |
| `suppliers` | COMPLETED | 1/1 | 4 | 4 |  |
| `system_logs` | COMPLETED | 1/1 | 114 | 114 |  |
| `system_settings` | COMPLETED | 1/1 | 1 | 1 |  |
| `audit_logs` | COMPLETED | 1/1 | 97 | 97 |  |
| `branch_type_module_defaults` | COMPLETED | 1/1 | 69 | 69 |  |
| `branches` | COMPLETED | 1/1 | 2 | 2 |  |
| `chart_of_accounts` | COMPLETED | 1/1 | 38 | 38 |  |
| `company_subscriptions` | COMPLETED | 1/1 | 8 | 8 |  |
| `inventory` | COMPLETED | 1/1 | 3 | 3 |  |
| `invoices` | COMPLETED | 1/1 | 1 | 1 |  |
| `payroll` | COMPLETED | 1/1 | 1 | 1 |  |
| `pos_sales` | COMPLETED | 1/1 | 8 | 8 |  |
| `pos_suspended_sales` | COMPLETED | 1/1 | 3 | 3 |  |
| `users` | COMPLETED | 1/1 | 3 | 3 |  |
| `branch_module_grants` | COMPLETED | 1/1 | 34 | 34 |  |
| `customer_transactions` | COMPLETED | 1/1 | 1 | 1 |  |
| `journal_lines` | COMPLETED | 1/1 | 61 | 61 |  |
| `pos_sale_lines` | COMPLETED | 1/1 | 13 | 13 |  |

## Safety Notes

- Required command: `python postgres_staging_deployer.py --copy-rows --confirm-row-copy`.
- Required environment: `ERP_ENVIRONMENT=staging`, `ERP_ENABLE_POSTGRES_ROW_COPY=1`, and `DATABASE_URL`.
- One transaction is used for the full row-copy run.
- Commit occurs only after all batches succeed; rollback occurs on failure.
