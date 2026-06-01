# PostgreSQL FK Readiness

**Audited at:** 2026-06-01 12:31:48 UTC

Read-only orphan checks: child FK column populated but no matching parent row.

## Orphan Summary

| Child | Parent | Column | Orphans | Risk |
|-------|--------|--------|--------:|------|
| `audit_logs` | `companies` | `company_key` | 0 | LOW |
| `bank_accounts` | `branches` | `branch_id` | 0 | LOW |
| `bank_accounts` | `companies` | `company_key` | 0 | LOW |
| `bill_lines` | `bills` | `bill_id` | 0 | LOW |
| `bills` | `suppliers` | `supplier_id` | 0 | LOW |
| `branch_module_grants` | `branches` | `branch_id` | 0 | LOW |
| `branch_module_grants` | `companies` | `company_key` | 0 | LOW |
| `branch_type_module_defaults` | `branch_type_catalog` | `branch_type_key` | 0 | LOW |
| `branches` | `companies` | `company_key` | 0 | LOW |
| `cashier_closings` | `companies` | `company_key` | 0 | LOW |
| `chart_of_accounts` | `companies` | `company_key` | 0 | LOW |
| `company_subscriptions` | `companies` | `company_key` | 0 | LOW |
| `counterparties` | `companies` | `company_key` | 0 | LOW |
| `customer_transactions` | `branches` | `branch_id` | 0 | LOW |
| `customer_transactions` | `customers` | `customer_id` | 0 | LOW |
| `customer_transactions` | `companies` | `company_key` | 0 | LOW |
| `fixed_assets` | `companies` | `company_key` | 0 | LOW |
| `inventory` | `companies` | `company_key` | 0 | LOW |
| `inventory_import_batches` | `companies` | `company_key` | 0 | LOW |
| `invoice_lines` | `inventory` | `inventory_item_id` | 0 | LOW |
| `invoice_lines` | `invoices` | `invoice_id` | 0 | LOW |
| `invoices` | `customers` | `customer_id` | 0 | LOW |
| `journal_lines` | `chart_of_accounts` | `account_id` | 0 | LOW |
| `journal_lines` | `journal_entries` | `entry_id` | 0 | LOW |
| `payment_allocations` | `branches` | `branch_id` | 0 | LOW |
| `payment_allocations` | `bills` | `bill_id` | 0 | LOW |
| `payment_allocations` | `invoices` | `invoice_id` | 0 | LOW |
| `payment_allocations` | `payments` | `payment_id` | 0 | LOW |
| `payment_allocations` | `companies` | `company_key` | 0 | LOW |
| `payroll` | `companies` | `company_key` | 0 | LOW |
| `pending_approvals` | `companies` | `company_key` | 0 | LOW |
| `pos_returns` | `companies` | `company_key` | 0 | LOW |
| `pos_sale_lines` | `companies` | `company_key` | 0 | LOW |
| `pos_sale_lines` | `pos_sales` | `pos_sale_id` | 0 | LOW |
| `pos_sales` | `companies` | `company_key` | 0 | LOW |
| `pos_suspended_sales` | `companies` | `company_key` | 0 | LOW |
| `purchase_orders` | `companies` | `company_key` | 0 | LOW |
| `recurring_transactions` | `branches` | `branch_id` | 0 | LOW |
| `recurring_transactions` | `companies` | `company_key` | 0 | LOW |
| `sales_invoices` | `companies` | `company_key` | 0 | LOW |
| `stock_movements` | `branches` | `branch_id` | 0 | LOW |
| `stock_movements` | `companies` | `company_key` | 0 | LOW |
| `stock_movements` | `inventory` | `inventory_item_id` | 0 | LOW |
| `supplier_transactions` | `suppliers` | `supplier_id` | 0 | LOW |
| `supplier_transactions` | `companies` | `company_key` | 0 | LOW |
| `users` | `companies` | `company_key` | 0 | LOW |
| `vouchers` | `companies` | `company_key` | 0 | LOW |

## Missing FK Indexes (heuristic)

- `audit_logs.company_key → companies`
- `bank_accounts.branch_id → branches`
- `bank_accounts.company_key → companies`
- `bills.supplier_id → suppliers`
- `branch_module_grants.branch_id → branches`
- `branch_module_grants.company_key → companies`
- `branch_type_module_defaults.branch_type_key → branch_type_catalog`
- `branches.company_key → companies`
- `cashier_closings.company_key → companies`
- `chart_of_accounts.company_key → companies`
- `counterparties.company_key → companies`
- `customer_transactions.branch_id → branches`
- `customer_transactions.customer_id → customers`
- `customer_transactions.company_key → companies`
- `fixed_assets.company_key → companies`
- `inventory.company_key → companies`
- `inventory_import_batches.company_key → companies`
- `invoices.customer_id → customers`
- `journal_lines.account_id → chart_of_accounts`
- `journal_lines.entry_id → journal_entries`
- `payment_allocations.branch_id → branches`
- `payment_allocations.bill_id → bills`
- `payment_allocations.invoice_id → invoices`
- `payment_allocations.payment_id → payments`
- `payment_allocations.company_key → companies`
- `payroll.company_key → companies`
- `pending_approvals.company_key → companies`
- `pos_returns.company_key → companies`
- `pos_sale_lines.company_key → companies`
- `pos_sale_lines.pos_sale_id → pos_sales`
- `pos_sales.company_key → companies`
- `pos_suspended_sales.company_key → companies`
- `purchase_orders.company_key → companies`
- `recurring_transactions.branch_id → branches`
- `recurring_transactions.company_key → companies`
- `sales_invoices.company_key → companies`
- `stock_movements.branch_id → branches`
- `stock_movements.company_key → companies`
- `stock_movements.inventory_item_id → inventory`
- `supplier_transactions.supplier_id → suppliers`
- `supplier_transactions.company_key → companies`
- `users.company_key → companies`
- `vouchers.company_key → companies`

## Circular / Ordering Notes

- `companies` ← `branches`, `users`, most transactional tables.
- `journal_entries` ↔ `journal_lines` (lines depend on entries).
- `pos_sales` → `pos_sale_lines`; payments may reference invoices/bills/customers.
- Enable `FOREIGN KEY` enforcement in Postgres; load order: parents before children.
