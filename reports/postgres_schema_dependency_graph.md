# PostgreSQL Schema Dependency Graph

Phase: 5B.14N

This graph is derived from `reports/postgres_generated_schema.sql`. It is an offline analysis artifact only; no SQL was executed.

## Summary

- Table nodes: **51**
- Foreign-key edges: **47**
- Executable index nodes: **0**
- Commented index placeholders: **67**
- `ALTER TABLE` statements: **0**
- Seed statements: **0**

## Dependency-Safe Table Order

| Order | Table | Current statement | References |
|---:|---|---:|---|
| 1 | `accounting_periods` | 2 | - |
| 2 | `accounts_payable` | 3 | - |
| 3 | `branch_type_catalog` | 4 | - |
| 4 | `companies` | 5 | - |
| 5 | `customers` | 6 | - |
| 6 | `database_identity` | 7 | - |
| 7 | `journal_entries` | 8 | - |
| 8 | `license_payment_transactions` | 9 | - |
| 9 | `maintenance_settings` | 10 | - |
| 10 | `migration_history` | 11 | - |
| 11 | `migration_logs` | 12 | - |
| 12 | `payments` | 13 | - |
| 13 | `payroll_records` | 14 | - |
| 14 | `schema_version` | 15 | - |
| 15 | `subscription_plan_settings` | 16 | - |
| 16 | `suppliers` | 17 | - |
| 17 | `system_logs` | 18 | - |
| 18 | `system_settings` | 19 | - |
| 19 | `transactions` | 20 | - |
| 20 | `audit_logs` | 21 | `companies` |
| 21 | `bills` | 22 | `suppliers` |
| 22 | `branch_type_module_defaults` | 23 | `branch_type_catalog` |
| 23 | `branches` | 24 | `companies` |
| 24 | `cashier_closings` | 25 | `companies` |
| 25 | `chart_of_accounts` | 26 | `companies` |
| 26 | `company_subscriptions` | 27 | `companies` |
| 27 | `counterparties` | 28 | `companies` |
| 28 | `fixed_assets` | 29 | `companies` |
| 29 | `inventory` | 30 | `companies` |
| 30 | `inventory_import_batches` | 31 | `companies` |
| 31 | `invoices` | 32 | `customers` |
| 32 | `payroll` | 33 | `companies` |
| 33 | `pending_approvals` | 34 | `companies` |
| 34 | `pos_returns` | 35 | `companies` |
| 35 | `pos_sales` | 36 | `companies` |
| 36 | `pos_suspended_sales` | 37 | `companies` |
| 37 | `purchase_orders` | 38 | `companies` |
| 38 | `sales_invoices` | 39 | `companies` |
| 39 | `supplier_transactions` | 40 | `companies`, `suppliers` |
| 40 | `users` | 41 | `companies` |
| 41 | `vouchers` | 42 | `companies` |
| 42 | `bank_accounts` | 43 | `branches`, `companies` |
| 43 | `bill_lines` | 44 | `bills` |
| 44 | `branch_module_grants` | 45 | `branches`, `companies` |
| 45 | `customer_transactions` | 46 | `branches`, `companies`, `customers` |
| 46 | `invoice_lines` | 47 | `inventory`, `invoices` |
| 47 | `journal_lines` | 48 | `chart_of_accounts`, `journal_entries` |
| 48 | `payment_allocations` | 49 | `bills`, `branches`, `companies`, `invoices`, `payments` |
| 49 | `pos_sale_lines` | 50 | `companies`, `pos_sales` |
| 50 | `recurring_transactions` | 51 | `branches`, `companies` |
| 51 | `stock_movements` | 52 | `branches`, `companies`, `inventory` |

## Foreign-Key Edges

```text
audit_logs -> companies
bank_accounts -> branches
bank_accounts -> companies
bill_lines -> bills
bills -> suppliers
branch_module_grants -> branches
branch_module_grants -> companies
branch_type_module_defaults -> branch_type_catalog
branches -> companies
cashier_closings -> companies
chart_of_accounts -> companies
company_subscriptions -> companies
counterparties -> companies
customer_transactions -> branches
customer_transactions -> companies
customer_transactions -> customers
fixed_assets -> companies
inventory -> companies
inventory_import_batches -> companies
invoice_lines -> inventory
invoice_lines -> invoices
invoices -> customers
journal_lines -> chart_of_accounts
journal_lines -> journal_entries
payment_allocations -> bills
payment_allocations -> branches
payment_allocations -> companies
payment_allocations -> invoices
payment_allocations -> payments
payroll -> companies
pending_approvals -> companies
pos_returns -> companies
pos_sale_lines -> companies
pos_sale_lines -> pos_sales
pos_sales -> companies
pos_suspended_sales -> companies
purchase_orders -> companies
recurring_transactions -> branches
recurring_transactions -> companies
sales_invoices -> companies
stock_movements -> branches
stock_movements -> companies
stock_movements -> inventory
supplier_transactions -> companies
supplier_transactions -> suppliers
users -> companies
vouchers -> companies
```

## Forward References In Current Statement Order

No foreign-key edge points to a table that appears later in the regenerated SQL.

```text
None.
```

## Mermaid Graph

```mermaid
graph TD
  audit_logs --> companies
  bank_accounts --> branches
  bank_accounts --> companies
  bill_lines --> bills
  bills --> suppliers
  branch_module_grants --> branches
  branch_module_grants --> companies
  branch_type_module_defaults --> branch_type_catalog
  branches --> companies
  cashier_closings --> companies
  chart_of_accounts --> companies
  company_subscriptions --> companies
  counterparties --> companies
  customer_transactions --> branches
  customer_transactions --> companies
  customer_transactions --> customers
  fixed_assets --> companies
  inventory --> companies
  inventory_import_batches --> companies
  invoice_lines --> inventory
  invoice_lines --> invoices
  invoices --> customers
  journal_lines --> chart_of_accounts
  journal_lines --> journal_entries
  payment_allocations --> bills
  payment_allocations --> branches
  payment_allocations --> companies
  payment_allocations --> invoices
  payment_allocations --> payments
  payroll --> companies
  pending_approvals --> companies
  pos_returns --> companies
  pos_sale_lines --> companies
  pos_sale_lines --> pos_sales
  pos_sales --> companies
  pos_suspended_sales --> companies
  purchase_orders --> companies
  recurring_transactions --> branches
  recurring_transactions --> companies
  sales_invoices --> companies
  stock_movements --> branches
  stock_movements --> companies
  stock_movements --> inventory
  supplier_transactions --> companies
  supplier_transactions --> suppliers
  users --> companies
  vouchers --> companies
```

## Ordering Recommendation

The generated schema now emits table DDL in dependency-safe order. Keep future executable indexes after all table creation statements. If future cycles appear, split cyclic foreign keys into post-table `ALTER TABLE ... ADD CONSTRAINT` statements.
