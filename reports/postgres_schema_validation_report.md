# PostgreSQL Schema Validation Report

Phase: 5B.13F

Validated offline from generated SQL and markdown reports. No database connection, schema deployment, Supabase call, or data migration was attempted.

## Validation Score

- Score: 90/100
- Deployment readiness: **YELLOW**
- Recommended next phase: Phase 5B.13G - review generated DDL gaps, replace index placeholders with real PostgreSQL index definitions, and prepare a staging-only schema deployer design.

## Coverage

- Expected SQLite table count: 51
- Generated PostgreSQL table count: 51
- Index count: 67
- FK count: 47
- Unsupported construct count: 42
- Manual review count: 58
- Dependency cycle count: 0
- Dependency ordering applied: YES

## Missing Required Tables

- None

## Tables Missing Primary Key

- None

## Forbidden SQLite Syntax Found

- None

## Tables Found

- accounting_periods
- accounts_payable
- audit_logs
- bank_accounts
- bill_lines
- bills
- branch_module_grants
- branch_type_catalog
- branch_type_module_defaults
- branches
- cashier_closings
- chart_of_accounts
- companies
- company_subscriptions
- counterparties
- customer_transactions
- customers
- database_identity
- fixed_assets
- inventory
- inventory_import_batches
- invoice_lines
- invoices
- journal_entries
- journal_lines
- license_payment_transactions
- maintenance_settings
- migration_history
- migration_logs
- payment_allocations
- payments
- payroll
- payroll_records
- pending_approvals
- pos_returns
- pos_sale_lines
- pos_sales
- pos_suspended_sales
- purchase_orders
- recurring_transactions
- sales_invoices
- schema_version
- stock_movements
- subscription_plan_settings
- supplier_transactions
- suppliers
- system_logs
- system_settings
- transactions
- users
- vouchers

## Notes

- All inventory tables are represented in the generated SQL.
