# SQLite to PostgreSQL Migration Plan

Phase: 5B.15F

Planning framework only. No real data migration, PostgreSQL writes, SQLite writes, runtime enablement, or production deployment was attempted.

## Summary

- Status: PLANNED
- SQLite tables discovered: 51
- PostgreSQL tables discovered: 51
- FK-safe migration tables planned: 51
- Estimated total rows: 527
- Estimated batches: 31
- Schema mismatches reviewed: 0
- Blocker count: 0
- Staging postdeploy validation: PASSED, 754/754 read-only checks passed.
- Reconciled POS/cashier/return/suspended-sale columns: 47/47 present in deployed PostgreSQL.
- Row-copy dry-run planner: READY_FOR_DRY_RUN_COPY.
- Dry-run row projection: 527 rows evaluated, 527 rows mappable, 0 rows unmappable.
- Column mapping issues: 0.

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

## Remaining Blockers

- No blocking schema mismatch categories or dry-run row projection failures were found; actual row-copy engine may be built next.
- Real row-copy execution remains unimplemented and unauthorized.
- PostgreSQL runtime remains disabled.
- Production deployment remains blocked.
