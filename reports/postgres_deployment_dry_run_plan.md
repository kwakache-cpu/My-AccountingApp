# PostgreSQL Deployment Dry-Run Plan

Phase: 5B.13G

Generated offline from PostgreSQL schema artifacts. No SQL execution, PostgreSQL connection, Supabase call, runtime enablement, or data migration was attempted.

## Readiness

- Deployment readiness score: 85/100
- Deployment readiness: **YELLOW**
- Source schema validation score: 90/100
- Source schema validation readiness: YELLOW

## Deployment Order

### Phase 1: Migration history and system metadata

- migration_history
- schema_version
- database_identity
- system_settings

### Phase 2: Companies, branches, and users

- companies
- branch_type_catalog
- branches
- users
- branch_type_module_defaults
- branch_module_grants
- company_subscriptions
- subscription_plan_settings
- license_payment_transactions

Dependencies:
- branch_module_grants.company_key -> companies.key
- branch_module_grants.branch_id -> branches.branch_id
- branch_type_module_defaults.branch_type_key -> branch_type_catalog.branch_type_key
- branches.company_key -> companies.key
- company_subscriptions.company_key -> companies.key
- users.company_key -> companies.key

### Phase 3: Chart of accounts, customers, and suppliers

- chart_of_accounts
- customers
- suppliers
- counterparties
- bank_accounts
- customer_transactions
- supplier_transactions

Dependencies:
- bank_accounts.company_key -> companies.key
- bank_accounts.branch_id -> branches.branch_id
- chart_of_accounts.company_key -> companies.key
- counterparties.company_key -> companies.key
- customer_transactions.company_key -> companies.key
- customer_transactions.customer_id -> customers.id
- customer_transactions.branch_id -> branches.branch_id
- supplier_transactions.company_key -> companies.key
- supplier_transactions.supplier_id -> suppliers.id

### Phase 4: Inventory

- inventory
- inventory_import_batches
- stock_movements
- purchase_orders

Dependencies:
- inventory.company_key -> companies.key
- inventory_import_batches.company_key -> companies.key
- purchase_orders.company_key -> companies.key
- stock_movements.inventory_item_id -> inventory.id
- stock_movements.company_key -> companies.key
- stock_movements.branch_id -> branches.branch_id

### Phase 5: Invoices, bills, and payments

- invoices
- invoice_lines
- bills
- bill_lines
- payments
- payment_allocations
- sales_invoices
- accounts_payable
- vouchers
- transactions
- recurring_transactions
- pending_approvals

Dependencies:
- bill_lines.bill_id -> bills.id
- bills.supplier_id -> suppliers.id
- invoice_lines.invoice_id -> invoices.id
- invoice_lines.inventory_item_id -> inventory.id
- invoices.customer_id -> customers.id
- payment_allocations.company_key -> companies.key
- payment_allocations.payment_id -> payments.id
- payment_allocations.invoice_id -> invoices.id
- payment_allocations.bill_id -> bills.id
- payment_allocations.branch_id -> branches.branch_id
- pending_approvals.company_key -> companies.key
- recurring_transactions.company_key -> companies.key
- recurring_transactions.branch_id -> branches.branch_id
- sales_invoices.company_key -> companies.key
- vouchers.company_key -> companies.key

### Phase 6: Journal tables

- journal_entries
- journal_lines
- accounting_periods

Dependencies:
- journal_lines.entry_id -> journal_entries.id
- journal_lines.account_id -> chart_of_accounts.id

### Phase 7: POS

- pos_sales
- pos_sale_lines
- pos_returns
- pos_suspended_sales
- cashier_closings

Dependencies:
- cashier_closings.company_key -> companies.key
- pos_returns.company_key -> companies.key
- pos_sale_lines.pos_sale_id -> pos_sales.id
- pos_sale_lines.company_key -> companies.key
- pos_sales.company_key -> companies.key
- pos_suspended_sales.company_key -> companies.key

### Phase 8: Payroll and fixed assets

- payroll
- payroll_records
- fixed_assets

Dependencies:
- fixed_assets.company_key -> companies.key
- payroll.company_key -> companies.key

### Phase 9: Audit and system tables

- audit_logs
- system_logs
- migration_logs
- maintenance_settings

Dependencies:
- audit_logs.company_key -> companies.key

## FK Dependency Risks

- None detected for the proposed phase order.

## Unassigned Generated Tables

- None.

## Rollback Planning

- Use a staging-only database clone or disposable schema before any future execution.
- Wrap future deployer phases in explicit transactions where PostgreSQL permits it.
- Record every applied phase in a PostgreSQL migration history table before moving to the next phase.
- On failure, stop immediately and drop only the staging schema or objects created by the failed dry-run phase.
- Do not roll back or mutate production SQLite data as part of PostgreSQL deployment recovery.
- Capture generated SQL, validation report, deployment logs, and table-count validation output for audit review.

## Staging-Only Deployment Checklist

- Confirm PostgreSQL runtime remains disabled until schema validation and deployer review pass.
- Review all generated SQL manually, especially type conversions and timestamp/date columns.
- Replace captured index placeholders with explicit PostgreSQL CREATE INDEX statements.
- Review FK ordering risks and decide whether to add foreign keys after base table creation.
- Prepare migration history and seed-data strategy before any staging execution.
- Run the schema validator after any generated SQL change.
- Require a staging-only approval before any future schema deployment command exists.

## Remaining Blockers

- PostgreSQL schema deployment is not implemented.
- Generated SQL still requires manual review before it can be executed in staging.
- Captured index placeholders must be replaced with real PostgreSQL index definitions.
- Seed data, migration history writes, and validation queries still need a staging-only deployer design.
- Runtime cutover remains NO-GO until deployment, data migration, and application SQL portability are complete.
