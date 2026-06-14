# Post-Copy Reconciliation Report

Phase: 5B.15I

Read-only post-copy reconciliation only. SQLite was not modified, PostgreSQL runtime was not enabled, application runtime was not changed, and production deployment was not attempted.

## Summary

- Status: READY_FOR_RUNTIME_VALIDATION
- Tables compared: 51
- Matched tables: 51
- Mismatched tables: 0
- SQLite total rows: 527
- PostgreSQL total rows: 527
- Missing rows: 0
- Extra rows: 0
- Runtime remains disabled: True

## Validation Areas

- Total rows: MATCH, 527 SQLite rows and 527 PostgreSQL rows.
- FK tables: MATCH, 32/32 FK-dependent tables matched.
- Audit/migration tables: MATCH, 6/6 tables matched.
- POS tables: MATCH, 5/5 tables matched.
- Accounting tables: MATCH, 12/12 tables matched.

## Category Coverage

- FK tables: `audit_logs`, `bank_accounts`, `bill_lines`, `bills`, `branch_module_grants`, `branch_type_module_defaults`, `branches`, `cashier_closings`, `chart_of_accounts`, `company_subscriptions`, `counterparties`, `customer_transactions`, `fixed_assets`, `inventory`, `inventory_import_batches`, `invoice_lines`, `invoices`, `journal_lines`, `payment_allocations`, `payroll`, `pending_approvals`, `pos_returns`, `pos_sale_lines`, `pos_sales`, `pos_suspended_sales`, `purchase_orders`, `recurring_transactions`, `sales_invoices`, `stock_movements`, `supplier_transactions`, `users`, `vouchers`
- Audit/migration tables: `audit_logs`, `system_logs`, `migration_logs`, `migration_history`, `schema_version`, `database_identity`
- POS tables: `cashier_closings`, `pos_returns`, `pos_sale_lines`, `pos_sales`, `pos_suspended_sales`
- Accounting tables: `accounting_periods`, `chart_of_accounts`, `journal_entries`, `journal_lines`, `transactions`, `payments`, `payment_allocations`, `invoices`, `invoice_lines`, `bills`, `bill_lines`, `vouchers`

## Table Comparison

| Table | SQLite rows | PostgreSQL rows | Result | Missing rows | Extra rows |
|---|---:|---:|---|---:|---:|
| `accounting_periods` | 0 | 0 | Match | 0 | 0 |
| `accounts_payable` | 0 | 0 | Match | 0 | 0 |
| `audit_logs` | 97 | 97 | Match | 0 | 0 |
| `bank_accounts` | 0 | 0 | Match | 0 | 0 |
| `bill_lines` | 0 | 0 | Match | 0 | 0 |
| `bills` | 0 | 0 | Match | 0 | 0 |
| `branch_module_grants` | 34 | 34 | Match | 0 | 0 |
| `branch_type_catalog` | 6 | 6 | Match | 0 | 0 |
| `branch_type_module_defaults` | 69 | 69 | Match | 0 | 0 |
| `branches` | 2 | 2 | Match | 0 | 0 |
| `cashier_closings` | 0 | 0 | Match | 0 | 0 |
| `chart_of_accounts` | 38 | 38 | Match | 0 | 0 |
| `companies` | 8 | 8 | Match | 0 | 0 |
| `company_subscriptions` | 8 | 8 | Match | 0 | 0 |
| `counterparties` | 0 | 0 | Match | 0 | 0 |
| `customer_transactions` | 1 | 1 | Match | 0 | 0 |
| `customers` | 2 | 2 | Match | 0 | 0 |
| `database_identity` | 1 | 1 | Match | 0 | 0 |
| `fixed_assets` | 0 | 0 | Match | 0 | 0 |
| `inventory` | 3 | 3 | Match | 0 | 0 |
| `inventory_import_batches` | 0 | 0 | Match | 0 | 0 |
| `invoice_lines` | 0 | 0 | Match | 0 | 0 |
| `invoices` | 1 | 1 | Match | 0 | 0 |
| `journal_entries` | 28 | 28 | Match | 0 | 0 |
| `journal_lines` | 61 | 61 | Match | 0 | 0 |
| `license_payment_transactions` | 2 | 2 | Match | 0 | 0 |
| `maintenance_settings` | 1 | 1 | Match | 0 | 0 |
| `migration_history` | 2 | 2 | Match | 0 | 0 |
| `migration_logs` | 2 | 2 | Match | 0 | 0 |
| `payment_allocations` | 0 | 0 | Match | 0 | 0 |
| `payments` | 8 | 8 | Match | 0 | 0 |
| `payroll` | 1 | 1 | Match | 0 | 0 |
| `payroll_records` | 1 | 1 | Match | 0 | 0 |
| `pending_approvals` | 0 | 0 | Match | 0 | 0 |
| `pos_returns` | 0 | 0 | Match | 0 | 0 |
| `pos_sale_lines` | 13 | 13 | Match | 0 | 0 |
| `pos_sales` | 8 | 8 | Match | 0 | 0 |
| `pos_suspended_sales` | 3 | 3 | Match | 0 | 0 |
| `purchase_orders` | 0 | 0 | Match | 0 | 0 |
| `recurring_transactions` | 0 | 0 | Match | 0 | 0 |
| `sales_invoices` | 0 | 0 | Match | 0 | 0 |
| `schema_version` | 2 | 2 | Match | 0 | 0 |
| `stock_movements` | 0 | 0 | Match | 0 | 0 |
| `subscription_plan_settings` | 3 | 3 | Match | 0 | 0 |
| `supplier_transactions` | 0 | 0 | Match | 0 | 0 |
| `suppliers` | 4 | 4 | Match | 0 | 0 |
| `system_logs` | 114 | 114 | Match | 0 | 0 |
| `system_settings` | 1 | 1 | Match | 0 | 0 |
| `transactions` | 0 | 0 | Match | 0 | 0 |
| `users` | 3 | 3 | Match | 0 | 0 |
| `vouchers` | 0 | 0 | Match | 0 | 0 |

## Final Status

- READY_FOR_RUNTIME_VALIDATION: post-copy row-count reconciliation passed for all tables and required validation areas.
- PostgreSQL runtime remains disabled.
- Production deployment remains blocked.
