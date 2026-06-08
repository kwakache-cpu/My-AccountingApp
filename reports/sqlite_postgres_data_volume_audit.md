# SQLite to PostgreSQL Data Volume Audit

Phase: 5B.15C

Read-only sizing audit only. No rows were copied or exported, no PostgreSQL connection was opened, no PostgreSQL write was attempted, SQLite data was not modified, and PostgreSQL runtime was not enabled.

## Database File

- DB file path: `D:\Emma\My AccountingApp\data\eka_enterprise_v3.db`
- DB file size: 0.64 MB (671744 bytes)
- SQLite page count: 164
- SQLite page size: 4096 bytes
- SQLite freelist count: 0
- Total row count: 527
- Migration volume classification: **SMALL**

## Transfer Estimates

- Estimated CSV export size: 0.74 MB
- Estimated JSON export size: 1.02 MB
- Estimated compressed export size: 0.33 MB
- Estimated PostgreSQL upload size: 0.92 MB
- Minimum data needed: 1.00 MB
- Recommended data bundle: 2.00 MB
- Safe data bundle with 2x margin: 2.00 MB

## Largest Tables By Rows

| Table | Rows | Estimated data size | Estimated CSV | Estimated JSON |
|---|---:|---:|---:|---:|
| `system_logs` | 114 | 0.14 MB | 0.16 MB | 0.22 MB |
| `audit_logs` | 97 | 0.12 MB | 0.14 MB | 0.19 MB |
| `branch_type_module_defaults` | 69 | 0.08 MB | 0.10 MB | 0.13 MB |
| `journal_lines` | 61 | 0.07 MB | 0.09 MB | 0.12 MB |
| `chart_of_accounts` | 38 | 0.05 MB | 0.05 MB | 0.07 MB |
| `branch_module_grants` | 34 | 0.04 MB | 0.05 MB | 0.07 MB |
| `journal_entries` | 28 | 0.03 MB | 0.04 MB | 0.05 MB |
| `pos_sale_lines` | 13 | 0.02 MB | 0.02 MB | 0.03 MB |
| `companies` | 8 | 0.01 MB | 0.01 MB | 0.02 MB |
| `company_subscriptions` | 8 | 0.01 MB | 0.01 MB | 0.02 MB |

## Largest Estimated Tables By Data Size

| Table | Rows | Estimated data size | Estimated CSV | Estimated JSON |
|---|---:|---:|---:|---:|
| `system_logs` | 114 | 0.14 MB | 0.16 MB | 0.22 MB |
| `audit_logs` | 97 | 0.12 MB | 0.14 MB | 0.19 MB |
| `branch_type_module_defaults` | 69 | 0.08 MB | 0.10 MB | 0.13 MB |
| `journal_lines` | 61 | 0.07 MB | 0.09 MB | 0.12 MB |
| `chart_of_accounts` | 38 | 0.05 MB | 0.05 MB | 0.07 MB |
| `branch_module_grants` | 34 | 0.04 MB | 0.05 MB | 0.07 MB |
| `journal_entries` | 28 | 0.03 MB | 0.04 MB | 0.05 MB |
| `pos_sale_lines` | 13 | 0.02 MB | 0.02 MB | 0.03 MB |
| `companies` | 8 | 0.01 MB | 0.01 MB | 0.02 MB |
| `company_subscriptions` | 8 | 0.01 MB | 0.01 MB | 0.02 MB |

## Row Count Per Table

| Table | Rows | Estimated data size |
|---|---:|---:|
| `accounting_periods` | 0 | 0.00 MB |
| `accounts_payable` | 0 | 0.00 MB |
| `audit_logs` | 97 | 0.12 MB |
| `bank_accounts` | 0 | 0.00 MB |
| `bill_lines` | 0 | 0.00 MB |
| `bills` | 0 | 0.00 MB |
| `branch_module_grants` | 34 | 0.04 MB |
| `branch_type_catalog` | 6 | 0.01 MB |
| `branch_type_module_defaults` | 69 | 0.08 MB |
| `branches` | 2 | 0.00 MB |
| `cashier_closings` | 0 | 0.00 MB |
| `chart_of_accounts` | 38 | 0.05 MB |
| `companies` | 8 | 0.01 MB |
| `company_subscriptions` | 8 | 0.01 MB |
| `counterparties` | 0 | 0.00 MB |
| `customer_transactions` | 1 | 0.00 MB |
| `customers` | 2 | 0.00 MB |
| `database_identity` | 1 | 0.00 MB |
| `fixed_assets` | 0 | 0.00 MB |
| `inventory` | 3 | 0.00 MB |
| `inventory_import_batches` | 0 | 0.00 MB |
| `invoice_lines` | 0 | 0.00 MB |
| `invoices` | 1 | 0.00 MB |
| `journal_entries` | 28 | 0.03 MB |
| `journal_lines` | 61 | 0.07 MB |
| `license_payment_transactions` | 2 | 0.00 MB |
| `maintenance_settings` | 1 | 0.00 MB |
| `migration_history` | 2 | 0.00 MB |
| `migration_logs` | 2 | 0.00 MB |
| `payment_allocations` | 0 | 0.00 MB |
| `payments` | 8 | 0.01 MB |
| `payroll` | 1 | 0.00 MB |
| `payroll_records` | 1 | 0.00 MB |
| `pending_approvals` | 0 | 0.00 MB |
| `pos_returns` | 0 | 0.00 MB |
| `pos_sale_lines` | 13 | 0.02 MB |
| `pos_sales` | 8 | 0.01 MB |
| `pos_suspended_sales` | 3 | 0.00 MB |
| `purchase_orders` | 0 | 0.00 MB |
| `recurring_transactions` | 0 | 0.00 MB |
| `sales_invoices` | 0 | 0.00 MB |
| `schema_version` | 2 | 0.00 MB |
| `stock_movements` | 0 | 0.00 MB |
| `subscription_plan_settings` | 3 | 0.00 MB |
| `supplier_transactions` | 0 | 0.00 MB |
| `suppliers` | 4 | 0.00 MB |
| `system_logs` | 114 | 0.14 MB |
| `system_settings` | 1 | 0.00 MB |
| `transactions` | 0 | 0.00 MB |
| `users` | 3 | 0.00 MB |
| `vouchers` | 0 | 0.00 MB |

## Estimation Notes

- The audit used only `SELECT COUNT(*)`, `PRAGMA page_count`, `PRAGMA page_size`, and `PRAGMA freelist_count` against a read-only SQLite connection.
- Table byte estimates are proportional allocations from active SQLite pages by row count; they are planning estimates, not row exports.
- CSV/JSON estimates include serialization overhead; compressed estimate assumes roughly 55% compression from CSV.
- PostgreSQL upload estimate includes protocol/index/transaction overhead for planning the internet data bundle.
