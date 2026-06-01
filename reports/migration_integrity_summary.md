# Migration Integrity Summary

**Audited at:** 2026-06-01 11:29:02 UTC
**Database:** `D:\Emma\My AccountingApp\data\eka_enterprise_v3.db`
**Database size:** 671,744 bytes

## Executive Summary

This read-only audit scanned the active SQLite database for migration blockers and data-quality warnings across companies, branches, users, journals, POS, inventory, AR/AP, and branch governance.

**Overall readiness score:** **YELLOW**
**Recommendation:** **GO WITH WARNINGS**

## Area Scores

| Area | Score |
|------|-------|
| Companies | GREEN |
| Branches | YELLOW |
| Users | GREEN |
| Journals | GREEN |
| POS | YELLOW |
| Inventory | GREEN |
| AR/AP | YELLOW |
| Branch Governance | GREEN |

## Top Blockers

- None detected.

## Top Warnings

- **sales_without_branch_id:** 8 (MEDIUM)
- **missing_manager_user_id:** 2 (LOW)
- **payments_without_source_reference:** 1 (LOW)

## Row Count Snapshot

- `accounting_periods`: 0
- `accounts_payable`: 0
- `audit_logs`: 93
- `bank_accounts`: 0
- `bill_lines`: 0
- `bills`: 0
- `branch_module_grants`: 34
- `branch_type_catalog`: 6
- `branch_type_module_defaults`: 69
- `branches`: 2
- `cashier_closings`: 0
- `chart_of_accounts`: 38
- `companies`: 8
- `company_subscriptions`: 8
- `counterparties`: 0
- `customer_transactions`: 1
- `customers`: 2
- `database_identity`: 1
- `fixed_assets`: 0
- `inventory`: 3
- `inventory_import_batches`: 0
- `invoice_lines`: 0
- `invoices`: 1
- `journal_entries`: 28
- `journal_lines`: 61
- `license_payment_transactions`: 2
- `maintenance_settings`: 1
- `migration_history`: 2
- `migration_logs`: 2
- `payment_allocations`: 0
- `payments`: 8
- `payroll`: 1
- `payroll_records`: 1
- `pending_approvals`: 0
- `pos_returns`: 0
- `pos_sale_lines`: 13
- `pos_sales`: 8
- `pos_suspended_sales`: 3
- `purchase_orders`: 0
- `recurring_transactions`: 0
- `sales_invoices`: 0
- `schema_version`: 2
- `stock_movements`: 0
- `subscription_plan_settings`: 3
- `supplier_transactions`: 0
- `suppliers`: 4
- `system_logs`: 114
- `system_settings`: 1
- `transactions`: 0
- `users`: 3
- `vouchers`: 0

## Cleanup Readiness (Phase 5B.3)

**Plan generated:** 2026-06-01 11:29:02 UTC

- Warning rows analyzed: **11**
- Safe to auto-fix later: **1**
- Manual decision required: **10**
- No action needed (false positive / already valid): **0**

Detailed row-level plan: `reports/migration_cleanup_plan.md`

**Migration status after cleanup planning:** remains **GO WITH WARNINGS** until manual items are resolved.

## Go / No-Go

**Decision:** GO WITH WARNINGS

No migration blockers detected in this audit pass.
