# Generated PostgreSQL Schema Summary

Generated offline by `postgres_schema_generator.py`. No database connection or deployment was attempted.

## Statistics

- Table count: 51
- Tables represented in SQL: 51
- Index count captured: 67
- FK count captured: 47
- Unsupported constructs: 42
- Manual review items: 58

## Validation

- Every SQLite table represented: YES
- FK inventory captured: YES
- Index inventory captured: YES
- Deployment attempted: NO

## Unsupported Constructs

- accounting_periods: AUTOINCREMENT
- audit_logs: AUTOINCREMENT
- bank_accounts: AUTOINCREMENT
- bill_lines: AUTOINCREMENT
- bills: AUTOINCREMENT
- branch_module_grants: AUTOINCREMENT
- branch_type_module_defaults: AUTOINCREMENT
- cashier_closings: AUTOINCREMENT
- chart_of_accounts: AUTOINCREMENT
- company_subscriptions: AUTOINCREMENT
- counterparties: AUTOINCREMENT
- customer_transactions: AUTOINCREMENT
- customers: AUTOINCREMENT
- fixed_assets: AUTOINCREMENT
- inventory: AUTOINCREMENT
- inventory_import_batches: AUTOINCREMENT
- invoice_lines: AUTOINCREMENT
- invoices: AUTOINCREMENT
- journal_entries: AUTOINCREMENT
- journal_lines: AUTOINCREMENT
- license_payment_transactions: AUTOINCREMENT
- migration_logs: AUTOINCREMENT
- payment_allocations: AUTOINCREMENT
- payments: AUTOINCREMENT
- payroll: AUTOINCREMENT
- payroll_records: AUTOINCREMENT
- pending_approvals: AUTOINCREMENT
- pos_returns: AUTOINCREMENT
- pos_sale_lines: AUTOINCREMENT
- pos_sales: AUTOINCREMENT
- pos_suspended_sales: AUTOINCREMENT
- purchase_orders: AUTOINCREMENT
- recurring_transactions: AUTOINCREMENT
- sales_invoices: AUTOINCREMENT
- stock_movements: AUTOINCREMENT
- subscription_plan_settings: AUTOINCREMENT
- supplier_transactions: AUTOINCREMENT
- suppliers: AUTOINCREMENT
- system_logs: AUTOINCREMENT
- transactions: AUTOINCREMENT
- users: AUTOINCREMENT
- vouchers: AUTOINCREMENT

## Manual Review Items

- Boolean candidate: accounting_periods.is_locked
- Boolean candidate: branch_module_grants.is_enabled
- Boolean candidate: branch_type_catalog.is_active
- Boolean candidate: branch_type_module_defaults.is_enabled
- Boolean candidate: branches.is_active
- Boolean candidate: chart_of_accounts.allow_manual_posting
- Boolean candidate: chart_of_accounts.control_account
- Boolean candidate: chart_of_accounts.is_active
- Boolean candidate: chart_of_accounts.posting_allowed
- Boolean candidate: inventory.is_active
- Boolean candidate: inventory_import_batches.opening_posted
- Boolean candidate: journal_entries.is_voided
- Boolean candidate: maintenance_settings.is_active
- Boolean candidate: recurring_transactions.is_active
- Boolean candidate: vouchers.is_cleared
- Boolean candidate: vouchers.is_voided
- Date/timestamp type review: accounting_periods
- Date/timestamp type review: bills
- Date/timestamp type review: fixed_assets
- Date/timestamp type review: invoices
- Date/timestamp type review: journal_entries
- Date/timestamp type review: payments
- Date/timestamp type review: payroll
- Date/timestamp type review: stock_movements
- Date/timestamp type review: vouchers
- Index definitions require review: accounting_periods
- Index definitions require review: audit_logs
- Index definitions require review: bank_accounts
- Index definitions require review: bill_lines
- Index definitions require review: bills
- Index definitions require review: branch_module_grants
- Index definitions require review: branch_type_module_defaults
- Index definitions require review: branches
- Index definitions require review: cashier_closings
- Index definitions require review: chart_of_accounts
- Index definitions require review: company_subscriptions
- Index definitions require review: counterparties
- Index definitions require review: customer_transactions
- Index definitions require review: customers
- Index definitions require review: inventory
- Index definitions require review: inventory_import_batches
- Index definitions require review: invoice_lines
- Index definitions require review: invoices
- Index definitions require review: journal_entries
- Index definitions require review: journal_lines
- Index definitions require review: license_payment_transactions
- Index definitions require review: payment_allocations
- Index definitions require review: payments
- Index definitions require review: pos_returns
- Index definitions require review: pos_sale_lines
- Index definitions require review: pos_sales
- Index definitions require review: pos_suspended_sales
- Index definitions require review: recurring_transactions
- Index definitions require review: stock_movements
- Index definitions require review: subscription_plan_settings
- Index definitions require review: supplier_transactions
- Index definitions require review: users
- Index definitions require review: vouchers
