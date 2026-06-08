# SQLite to PostgreSQL Migration Plan

Phase: 5B.15A

Planning framework only. No real data migration, PostgreSQL writes, SQLite writes, INSERT, UPDATE, DELETE, runtime enablement, or production deployment was attempted.

## Summary

- Status: PLANNED
- SQLite tables discovered: 51
- PostgreSQL tables discovered: 51
- FK-safe migration tables planned: 51
- Estimated total rows: 527
- Estimated batches: 31
- Schema mismatches: 47

## Migration Order

1. `accounting_periods`
2. `accounts_payable`
3. `branch_type_catalog`
4. `companies`
5. `customers`
6. `database_identity`
7. `journal_entries`
8. `license_payment_transactions`
9. `maintenance_settings`
10. `migration_history`
11. `migration_logs`
12. `payments`
13. `payroll_records`
14. `schema_version`
15. `subscription_plan_settings`
16. `suppliers`
17. `system_logs`
18. `system_settings`
19. `transactions`
20. `audit_logs`
21. `bills`
22. `branch_type_module_defaults`
23. `branches`
24. `cashier_closings`
25. `chart_of_accounts`
26. `company_subscriptions`
27. `counterparties`
28. `fixed_assets`
29. `inventory`
30. `inventory_import_batches`
31. `invoices`
32. `payroll`
33. `pending_approvals`
34. `pos_returns`
35. `pos_sales`
36. `pos_suspended_sales`
37. `purchase_orders`
38. `sales_invoices`
39. `supplier_transactions`
40. `users`
41. `vouchers`
42. `bank_accounts`
43. `bill_lines`
44. `branch_module_grants`
45. `customer_transactions`
46. `invoice_lines`
47. `journal_lines`
48. `payment_allocations`
49. `pos_sale_lines`
50. `recurring_transactions`
51. `stock_movements`

## Table Plans

- `accounting_periods`: order=1, rows=0, batch_size=1000, batches=0, dependencies=none
- `accounts_payable`: order=2, rows=0, batch_size=1000, batches=0, dependencies=none
- `branch_type_catalog`: order=3, rows=6, batch_size=100, batches=1, dependencies=none
- `companies`: order=4, rows=8, batch_size=100, batches=1, dependencies=none
- `customers`: order=5, rows=2, batch_size=100, batches=1, dependencies=none
- `database_identity`: order=6, rows=1, batch_size=100, batches=1, dependencies=none
- `journal_entries`: order=7, rows=28, batch_size=100, batches=1, dependencies=none
- `license_payment_transactions`: order=8, rows=2, batch_size=100, batches=1, dependencies=none
- `maintenance_settings`: order=9, rows=1, batch_size=100, batches=1, dependencies=none
- `migration_history`: order=10, rows=2, batch_size=100, batches=1, dependencies=none
- `migration_logs`: order=11, rows=2, batch_size=100, batches=1, dependencies=none
- `payments`: order=12, rows=8, batch_size=100, batches=1, dependencies=none
- `payroll_records`: order=13, rows=1, batch_size=100, batches=1, dependencies=none
- `schema_version`: order=14, rows=2, batch_size=100, batches=1, dependencies=none
- `subscription_plan_settings`: order=15, rows=3, batch_size=100, batches=1, dependencies=none
- `suppliers`: order=16, rows=4, batch_size=100, batches=1, dependencies=none
- `system_logs`: order=17, rows=114, batch_size=114, batches=1, dependencies=none
- `system_settings`: order=18, rows=1, batch_size=100, batches=1, dependencies=none
- `transactions`: order=19, rows=0, batch_size=1000, batches=0, dependencies=none
- `audit_logs`: order=20, rows=97, batch_size=100, batches=1, dependencies=`companies`
- `bills`: order=21, rows=0, batch_size=1000, batches=0, dependencies=`suppliers`
- `branch_type_module_defaults`: order=22, rows=69, batch_size=100, batches=1, dependencies=`branch_type_catalog`
- `branches`: order=23, rows=2, batch_size=100, batches=1, dependencies=`companies`
- `cashier_closings`: order=24, rows=0, batch_size=1000, batches=0, dependencies=`companies`
- `chart_of_accounts`: order=25, rows=38, batch_size=100, batches=1, dependencies=`companies`
- `company_subscriptions`: order=26, rows=8, batch_size=100, batches=1, dependencies=`companies`
- `counterparties`: order=27, rows=0, batch_size=1000, batches=0, dependencies=`companies`
- `fixed_assets`: order=28, rows=0, batch_size=1000, batches=0, dependencies=`companies`
- `inventory`: order=29, rows=3, batch_size=100, batches=1, dependencies=`companies`
- `inventory_import_batches`: order=30, rows=0, batch_size=1000, batches=0, dependencies=`companies`
- `invoices`: order=31, rows=1, batch_size=100, batches=1, dependencies=`customers`
- `payroll`: order=32, rows=1, batch_size=100, batches=1, dependencies=`companies`
- `pending_approvals`: order=33, rows=0, batch_size=1000, batches=0, dependencies=`companies`
- `pos_returns`: order=34, rows=0, batch_size=1000, batches=0, dependencies=`companies`
- `pos_sales`: order=35, rows=8, batch_size=100, batches=1, dependencies=`companies`
- `pos_suspended_sales`: order=36, rows=3, batch_size=100, batches=1, dependencies=`companies`
- `purchase_orders`: order=37, rows=0, batch_size=1000, batches=0, dependencies=`companies`
- `sales_invoices`: order=38, rows=0, batch_size=1000, batches=0, dependencies=`companies`
- `supplier_transactions`: order=39, rows=0, batch_size=1000, batches=0, dependencies=`companies`, `suppliers`
- `users`: order=40, rows=3, batch_size=100, batches=1, dependencies=`companies`
- `vouchers`: order=41, rows=0, batch_size=1000, batches=0, dependencies=`companies`
- `bank_accounts`: order=42, rows=0, batch_size=1000, batches=0, dependencies=`branches`, `companies`
- `bill_lines`: order=43, rows=0, batch_size=1000, batches=0, dependencies=`bills`
- `branch_module_grants`: order=44, rows=34, batch_size=100, batches=1, dependencies=`branches`, `companies`
- `customer_transactions`: order=45, rows=1, batch_size=100, batches=1, dependencies=`branches`, `companies`, `customers`
- `invoice_lines`: order=46, rows=0, batch_size=1000, batches=0, dependencies=`inventory`, `invoices`
- `journal_lines`: order=47, rows=61, batch_size=100, batches=1, dependencies=`chart_of_accounts`, `journal_entries`
- `payment_allocations`: order=48, rows=0, batch_size=1000, batches=0, dependencies=`bills`, `branches`, `companies`, `invoices`, `payments`
- `pos_sale_lines`: order=49, rows=13, batch_size=100, batches=1, dependencies=`companies`, `pos_sales`
- `recurring_transactions`: order=50, rows=0, batch_size=1000, batches=0, dependencies=`branches`, `companies`
- `stock_movements`: order=51, rows=0, batch_size=1000, batches=0, dependencies=`branches`, `companies`, `inventory`

## Schema Mismatches

- cashier_closings.cashier missing in PostgreSQL schema
- cashier_closings.closed_at missing in PostgreSQL schema
- cashier_closings.closed_by missing in PostgreSQL schema
- cashier_closings.closing_date missing in PostgreSQL schema
- cashier_closings.counted_cash missing in PostgreSQL schema
- cashier_closings.difference missing in PostgreSQL schema
- cashier_closings.expected_cash missing in PostgreSQL schema
- cashier_closings.notes missing in PostgreSQL schema
- pos_returns.item_id missing in PostgreSQL schema
- pos_returns.item_name missing in PostgreSQL schema
- pos_returns.original_sale_reference missing in PostgreSQL schema
- pos_returns.pos_sale_line_id missing in PostgreSQL schema
- pos_returns.posted_entry_id missing in PostgreSQL schema
- pos_returns.qty_returned missing in PostgreSQL schema
- pos_returns.reason missing in PostgreSQL schema
- pos_returns.refund_amount missing in PostgreSQL schema
- pos_returns.refund_method missing in PostgreSQL schema
- pos_returns.return_reference missing in PostgreSQL schema
- pos_returns.returned_at missing in PostgreSQL schema
- pos_returns.returned_by missing in PostgreSQL schema
- pos_returns.status missing in PostgreSQL schema
- pos_returns.unit_price missing in PostgreSQL schema
- pos_sales.amount_tendered missing in PostgreSQL schema
- pos_sales.cashier missing in PostgreSQL schema
- pos_sales.change_due missing in PostgreSQL schema
- pos_sales.cogs_posted_entry_id missing in PostgreSQL schema
- pos_sales.created_at missing in PostgreSQL schema
- pos_sales.customer_id missing in PostgreSQL schema
- pos_sales.discount_total missing in PostgreSQL schema
- pos_sales.grand_total missing in PostgreSQL schema
- pos_sales.last_journal_sync_at missing in PostgreSQL schema
- pos_sales.payment_method missing in PostgreSQL schema
- pos_sales.posted_entry_id missing in PostgreSQL schema
- pos_sales.receipt_number missing in PostgreSQL schema
- pos_sales.sale_date missing in PostgreSQL schema
- pos_sales.sale_datetime missing in PostgreSQL schema
- pos_sales.sale_reference missing in PostgreSQL schema
- pos_sales.subtotal missing in PostgreSQL schema
- pos_sales.tax_total missing in PostgreSQL schema
- pos_suspended_sales.cancelled_at missing in PostgreSQL schema
- pos_suspended_sales.cart_json missing in PostgreSQL schema
- pos_suspended_sales.cashier missing in PostgreSQL schema
- pos_suspended_sales.created_at missing in PostgreSQL schema
- pos_suspended_sales.note missing in PostgreSQL schema
- pos_suspended_sales.resumed_at missing in PostgreSQL schema
- pos_suspended_sales.status missing in PostgreSQL schema
- pos_suspended_sales.suspend_reference missing in PostgreSQL schema

## Batch Estimates

- `branch_type_catalog` batch 1: offset=0, limit=100, estimated_rows=6
- `companies` batch 1: offset=0, limit=100, estimated_rows=8
- `customers` batch 1: offset=0, limit=100, estimated_rows=2
- `database_identity` batch 1: offset=0, limit=100, estimated_rows=1
- `journal_entries` batch 1: offset=0, limit=100, estimated_rows=28
- `license_payment_transactions` batch 1: offset=0, limit=100, estimated_rows=2
- `maintenance_settings` batch 1: offset=0, limit=100, estimated_rows=1
- `migration_history` batch 1: offset=0, limit=100, estimated_rows=2
- `migration_logs` batch 1: offset=0, limit=100, estimated_rows=2
- `payments` batch 1: offset=0, limit=100, estimated_rows=8
- `payroll_records` batch 1: offset=0, limit=100, estimated_rows=1
- `schema_version` batch 1: offset=0, limit=100, estimated_rows=2
- `subscription_plan_settings` batch 1: offset=0, limit=100, estimated_rows=3
- `suppliers` batch 1: offset=0, limit=100, estimated_rows=4
- `system_logs` batch 1: offset=0, limit=114, estimated_rows=114
- `system_settings` batch 1: offset=0, limit=100, estimated_rows=1
- `audit_logs` batch 1: offset=0, limit=100, estimated_rows=97
- `branch_type_module_defaults` batch 1: offset=0, limit=100, estimated_rows=69
- `branches` batch 1: offset=0, limit=100, estimated_rows=2
- `chart_of_accounts` batch 1: offset=0, limit=100, estimated_rows=38
- `company_subscriptions` batch 1: offset=0, limit=100, estimated_rows=8
- `inventory` batch 1: offset=0, limit=100, estimated_rows=3
- `invoices` batch 1: offset=0, limit=100, estimated_rows=1
- `payroll` batch 1: offset=0, limit=100, estimated_rows=1
- `pos_sales` batch 1: offset=0, limit=100, estimated_rows=8
- `pos_suspended_sales` batch 1: offset=0, limit=100, estimated_rows=3
- `users` batch 1: offset=0, limit=100, estimated_rows=3
- `branch_module_grants` batch 1: offset=0, limit=100, estimated_rows=34
- `customer_transactions` batch 1: offset=0, limit=100, estimated_rows=1
- `journal_lines` batch 1: offset=0, limit=100, estimated_rows=61
- `pos_sale_lines` batch 1: offset=0, limit=100, estimated_rows=13

## Remaining Blockers

- Schema differences require review before real data migration.
- PostgreSQL runtime remains disabled.
- Production deployment remains blocked.
- Row copy, INSERT, UPDATE, DELETE, and reconciliation execution remain future phases.
