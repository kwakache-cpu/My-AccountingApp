# PostgreSQL Runtime Readiness Report

Phase: 5B.15J

Read-only PostgreSQL runtime readiness validation only. No PostgreSQL runtime enablement, SQLite modification, application data writes, migration activity, or production deployment was attempted.

## Summary

- Status: READY_FOR_RUNTIME_CUTOVER
- Started at: 2026-06-14T07:39:04.620396+00:00
- Completed at: 2026-06-14T07:39:43.225693+00:00
- Tables checked: 51
- Tables passed: 51
- Indexes checked: 0
- Indexes passed: 0
- FK checks: 47
- FK checks passed: 47
- Smoke checks: 6
- Smoke checks passed: 6
- Runtime remains disabled: True

## Guards

- Blocked: False
- Message: Runtime readiness guards passed for read-only staging checks.
- DATABASE_URL: postgresql://postgres.buzfvrhynszolxejdzen:***@aws-1-eu-west-1.pooler.supabase.com:6543/postgres
- PostgreSQL driver: psycopg2
- ERP_ENVIRONMENT_is_staging: True
- DATABASE_URL_present: True
- schema_artifact_present: True
- postgres_driver_available: True

## Runtime Smoke Checks

| Check | Table | Row count | Result |
|---|---|---:|---|
| company_count | `companies` | 8 | PASSED |
| user_count | `users` | 3 | PASSED |
| customer_count | `customers` | 2 | PASSED |
| inventory_count | `inventory` | 3 | PASSED |
| chart_of_accounts_count | `chart_of_accounts` | 38 | PASSED |
| journal_count | `journal_entries` | 28 | PASSED |

## Runtime Table Groups

| Category | Table | Result |
|---|---|---|
| startup_metadata_tables | `schema_version` | PASSED |
| startup_metadata_tables | `database_identity` | PASSED |
| startup_metadata_tables | `migration_history` | PASSED |
| authentication_tables | `users` | PASSED |
| company_configuration_tables | `companies` | PASSED |
| company_configuration_tables | `branches` | PASSED |
| company_configuration_tables | `system_settings` | PASSED |
| company_configuration_tables | `company_subscriptions` | PASSED |
| company_configuration_tables | `subscription_plan_settings` | PASSED |
| company_configuration_tables | `branch_type_catalog` | PASSED |
| company_configuration_tables | `branch_type_module_defaults` | PASSED |
| company_configuration_tables | `branch_module_grants` | PASSED |
| chart_of_accounts_tables | `chart_of_accounts` | PASSED |
| pos_tables | `cashier_closings` | PASSED |
| pos_tables | `pos_returns` | PASSED |
| pos_tables | `pos_sale_lines` | PASSED |
| pos_tables | `pos_sales` | PASSED |
| pos_tables | `pos_suspended_sales` | PASSED |
| accounting_tables | `accounting_periods` | PASSED |
| accounting_tables | `accounts_payable` | PASSED |
| accounting_tables | `bank_accounts` | PASSED |
| accounting_tables | `bill_lines` | PASSED |
| accounting_tables | `bills` | PASSED |
| accounting_tables | `chart_of_accounts` | PASSED |
| accounting_tables | `customer_transactions` | PASSED |
| accounting_tables | `invoice_lines` | PASSED |
| accounting_tables | `invoices` | PASSED |
| accounting_tables | `journal_entries` | PASSED |
| accounting_tables | `journal_lines` | PASSED |
| accounting_tables | `payment_allocations` | PASSED |
| accounting_tables | `payments` | PASSED |
| accounting_tables | `supplier_transactions` | PASSED |
| accounting_tables | `transactions` | PASSED |
| accounting_tables | `vouchers` | PASSED |
| audit_history_tables | `audit_logs` | PASSED |
| audit_history_tables | `system_logs` | PASSED |
| audit_history_tables | `migration_logs` | PASSED |
| audit_history_tables | `migration_history` | PASSED |
| audit_history_tables | `schema_version` | PASSED |
| audit_history_tables | `database_identity` | PASSED |

## Required Runtime Tables

| Table | Result |
|---|---|
| `accounting_periods` | PASSED |
| `accounts_payable` | PASSED |
| `audit_logs` | PASSED |
| `bank_accounts` | PASSED |
| `bill_lines` | PASSED |
| `bills` | PASSED |
| `branch_module_grants` | PASSED |
| `branch_type_catalog` | PASSED |
| `branch_type_module_defaults` | PASSED |
| `branches` | PASSED |
| `cashier_closings` | PASSED |
| `chart_of_accounts` | PASSED |
| `companies` | PASSED |
| `company_subscriptions` | PASSED |
| `counterparties` | PASSED |
| `customer_transactions` | PASSED |
| `customers` | PASSED |
| `database_identity` | PASSED |
| `fixed_assets` | PASSED |
| `inventory` | PASSED |
| `inventory_import_batches` | PASSED |
| `invoice_lines` | PASSED |
| `invoices` | PASSED |
| `journal_entries` | PASSED |
| `journal_lines` | PASSED |
| `license_payment_transactions` | PASSED |
| `maintenance_settings` | PASSED |
| `migration_history` | PASSED |
| `migration_logs` | PASSED |
| `payment_allocations` | PASSED |
| `payments` | PASSED |
| `payroll` | PASSED |
| `payroll_records` | PASSED |
| `pending_approvals` | PASSED |
| `pos_returns` | PASSED |
| `pos_sale_lines` | PASSED |
| `pos_sales` | PASSED |
| `pos_suspended_sales` | PASSED |
| `purchase_orders` | PASSED |
| `recurring_transactions` | PASSED |
| `sales_invoices` | PASSED |
| `schema_version` | PASSED |
| `stock_movements` | PASSED |
| `subscription_plan_settings` | PASSED |
| `supplier_transactions` | PASSED |
| `suppliers` | PASSED |
| `system_logs` | PASSED |
| `system_settings` | PASSED |
| `transactions` | PASSED |
| `users` | PASSED |
| `vouchers` | PASSED |

## Required Runtime Indexes

- No executable runtime indexes are present in the current generated schema artifact; captured index comments remain manual-review artifacts.

## Required Runtime Foreign Keys

| Foreign key | Result |
|---|---|
| `audit_logs.company_key->companies.key` | PASSED |
| `bank_accounts.branch_id->branches.branch_id` | PASSED |
| `bank_accounts.company_key->companies.key` | PASSED |
| `bill_lines.bill_id->bills.id` | PASSED |
| `bills.supplier_id->suppliers.id` | PASSED |
| `branch_module_grants.branch_id->branches.branch_id` | PASSED |
| `branch_module_grants.company_key->companies.key` | PASSED |
| `branch_type_module_defaults.branch_type_key->branch_type_catalog.branch_type_key` | PASSED |
| `branches.company_key->companies.key` | PASSED |
| `cashier_closings.company_key->companies.key` | PASSED |
| `chart_of_accounts.company_key->companies.key` | PASSED |
| `company_subscriptions.company_key->companies.key` | PASSED |
| `counterparties.company_key->companies.key` | PASSED |
| `customer_transactions.branch_id->branches.branch_id` | PASSED |
| `customer_transactions.company_key->companies.key` | PASSED |
| `customer_transactions.customer_id->customers.id` | PASSED |
| `fixed_assets.company_key->companies.key` | PASSED |
| `inventory.company_key->companies.key` | PASSED |
| `inventory_import_batches.company_key->companies.key` | PASSED |
| `invoice_lines.inventory_item_id->inventory.id` | PASSED |
| `invoice_lines.invoice_id->invoices.id` | PASSED |
| `invoices.customer_id->customers.id` | PASSED |
| `journal_lines.account_id->chart_of_accounts.id` | PASSED |
| `journal_lines.entry_id->journal_entries.id` | PASSED |
| `payment_allocations.bill_id->bills.id` | PASSED |
| `payment_allocations.branch_id->branches.branch_id` | PASSED |
| `payment_allocations.company_key->companies.key` | PASSED |
| `payment_allocations.invoice_id->invoices.id` | PASSED |
| `payment_allocations.payment_id->payments.id` | PASSED |
| `payroll.company_key->companies.key` | PASSED |
| `pending_approvals.company_key->companies.key` | PASSED |
| `pos_returns.company_key->companies.key` | PASSED |
| `pos_sale_lines.company_key->companies.key` | PASSED |
| `pos_sale_lines.pos_sale_id->pos_sales.id` | PASSED |
| `pos_sales.company_key->companies.key` | PASSED |
| `pos_suspended_sales.company_key->companies.key` | PASSED |
| `purchase_orders.company_key->companies.key` | PASSED |
| `recurring_transactions.branch_id->branches.branch_id` | PASSED |
| `recurring_transactions.company_key->companies.key` | PASSED |
| `sales_invoices.company_key->companies.key` | PASSED |
| `stock_movements.branch_id->branches.branch_id` | PASSED |
| `stock_movements.company_key->companies.key` | PASSED |
| `stock_movements.inventory_item_id->inventory.id` | PASSED |
| `supplier_transactions.company_key->companies.key` | PASSED |
| `supplier_transactions.supplier_id->suppliers.id` | PASSED |
| `users.company_key->companies.key` | PASSED |
| `vouchers.company_key->companies.key` | PASSED |

## Final Status

- READY_FOR_RUNTIME_CUTOVER
- PostgreSQL runtime remains disabled until explicit cutover approval.
