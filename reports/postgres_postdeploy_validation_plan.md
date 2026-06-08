# PostgreSQL Post-Deployment Validation Plan

Phase: 5B.13I

Offline framework definition only. No database connection, SQL execution, schema deployment, PostgreSQL runtime enablement, or data migration was attempted.

## Source Artifact Summary

- Source schema validation score: 90/100
- Source deployment readiness: YELLOW
- Expected tables: 51
- Expected indexes: 67
- Expected FKs: 47
- Expected migration tables: 3
- Expected seed tables: 7

## Validation Categories

### Schema validation

- Objective: Confirm schema artifact was applied in the intended staging scope.
- Evidence sources: schema deploy log, table count query output

### Table validation

- Objective: Confirm every expected table exists after deployment.
- Evidence sources: generated schema inventory, information_schema.tables snapshot

### Column validation

- Objective: Confirm required columns, primary keys, and nullable/default metadata match the generated artifact.
- Evidence sources: generated schema SQL, information_schema.columns snapshot

### Index validation

- Objective: Confirm all expected PostgreSQL indexes exist after explicit index definitions are added.
- Evidence sources: generated index inventory, pg_indexes snapshot

### FK validation

- Objective: Confirm foreign key constraints exist and reference expected parent tables/columns.
- Evidence sources: generated FK inventory, information_schema constraints snapshot

### Seed data validation

- Objective: Confirm required seed tables contain expected baseline rows.
- Evidence sources: seed manifest, staging row-count snapshot

### Migration history validation

- Objective: Confirm deployment phases are recorded in PostgreSQL migration metadata.
- Evidence sources: migration history table, deployment log

### Runtime readiness validation

- Objective: Confirm startup gate remains safe until deployment and validation are complete.
- Evidence sources: startup diagnostics, configuration review

## Expected Tables

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

## Expected Indexes

- idx_accounting_periods_company_status
- idx_audit_logs_action_type
- idx_audit_logs_company_timestamp
- idx_bank_accounts_company
- idx_bill_lines_bill_id
- idx_bills_company_bill_number
- idx_bills_company_status
- idx_branch_module_grants_company_branch
- idx_branch_type_module_defaults_type
- idx_branches_access_key
- idx_branches_company
- idx_cashier_closings_company_date
- idx_cashier_closings_unique_drawer
- idx_chart_of_accounts_account_code_unique
- idx_chart_of_accounts_active
- idx_chart_of_accounts_control_account
- idx_chart_of_accounts_parent_id
- idx_chart_of_accounts_type
- idx_company_subscriptions_company_key
- idx_company_subscriptions_status_end_date
- idx_counterparties_company_type
- idx_customer_transactions_company_date
- idx_customer_transactions_customer_date
- idx_customers_company_customer_id
- idx_customers_company_name
- idx_inv_barcode
- idx_inv_comp
- idx_inv_name
- idx_inventory_import_batches_company
- idx_inventory_import_batches_reference
- idx_invoice_lines_inventory_item_id
- idx_invoice_lines_invoice_id
- idx_invoices_company_invoice_number
- idx_invoices_company_status
- idx_journal_entries_company_date
- idx_journal_entries_customer
- idx_journal_entries_reporting
- idx_journal_entries_source
- idx_journal_entries_supplier
- idx_journal_lines_entry
- idx_journal_lines_entry_account
- idx_license_payment_transactions_company_status
- idx_license_payment_transactions_plan_status
- idx_license_payment_transactions_verified_at
- idx_payment_allocations_bill
- idx_payment_allocations_invoice
- idx_payment_allocations_payment
- idx_payments_company_status
- idx_pos_returns_reference_line
- idx_pos_returns_sale_line
- idx_pos_sale_lines_item
- idx_pos_sale_lines_sale
- idx_pos_sales_cashier_date
- idx_pos_sales_reference
- idx_pos_suspended_sales_reference
- idx_pos_suspended_sales_status
- idx_recurring_transactions_company
- idx_recurring_transactions_next_run
- idx_stock_movements_company_created
- idx_stock_movements_item
- idx_subscription_plan_settings_plan_name
- idx_supplier_transactions_company_date
- idx_supplier_transactions_supplier_date
- idx_users_login_key
- idx_users_user_id
- idx_users_user_id_runtime
- idx_vouch_date

## Expected FKs

- audit_logs.company_key -> companies.key
- bank_accounts.branch_id -> branches.branch_id
- bank_accounts.company_key -> companies.key
- bill_lines.bill_id -> bills.id
- bills.supplier_id -> suppliers.id
- branch_module_grants.branch_id -> branches.branch_id
- branch_module_grants.company_key -> companies.key
- branch_type_module_defaults.branch_type_key -> branch_type_catalog.branch_type_key
- branches.company_key -> companies.key
- cashier_closings.company_key -> companies.key
- chart_of_accounts.company_key -> companies.key
- company_subscriptions.company_key -> companies.key
- counterparties.company_key -> companies.key
- customer_transactions.branch_id -> branches.branch_id
- customer_transactions.company_key -> companies.key
- customer_transactions.customer_id -> customers.id
- fixed_assets.company_key -> companies.key
- inventory.company_key -> companies.key
- inventory_import_batches.company_key -> companies.key
- invoice_lines.inventory_item_id -> inventory.id
- invoice_lines.invoice_id -> invoices.id
- invoices.customer_id -> customers.id
- journal_lines.account_id -> chart_of_accounts.id
- journal_lines.entry_id -> journal_entries.id
- payment_allocations.bill_id -> bills.id
- payment_allocations.branch_id -> branches.branch_id
- payment_allocations.company_key -> companies.key
- payment_allocations.invoice_id -> invoices.id
- payment_allocations.payment_id -> payments.id
- payroll.company_key -> companies.key
- pending_approvals.company_key -> companies.key
- pos_returns.company_key -> companies.key
- pos_sale_lines.company_key -> companies.key
- pos_sale_lines.pos_sale_id -> pos_sales.id
- pos_sales.company_key -> companies.key
- pos_suspended_sales.company_key -> companies.key
- purchase_orders.company_key -> companies.key
- recurring_transactions.branch_id -> branches.branch_id
- recurring_transactions.company_key -> companies.key
- sales_invoices.company_key -> companies.key
- stock_movements.branch_id -> branches.branch_id
- stock_movements.company_key -> companies.key
- stock_movements.inventory_item_id -> inventory.id
- supplier_transactions.company_key -> companies.key
- supplier_transactions.supplier_id -> suppliers.id
- users.company_key -> companies.key
- vouchers.company_key -> companies.key

## Expected Migration Tables

- migration_history
- schema_version
- database_identity

## Expected Seed Tables

- branch_type_catalog
- branch_type_module_defaults
- subscription_plan_settings
- system_settings
- companies
- branches
- users

## Validation Checklists

### Stage 1: Schema deployment validation

- Confirm all expected tables exist in the staging schema.
- Confirm primary keys exist for every generated table.
- Confirm expected foreign keys are present or intentionally deferred.
- Confirm expected indexes are present after index placeholders are replaced.
- Confirm generated schema validation report still has no forbidden SQLite syntax.

### Stage 2: Seed deployment validation

- Confirm seed tables exist before seed writes are attempted.
- Confirm branch type catalog rows are present.
- Confirm subscription plan settings rows are present.
- Confirm system settings and baseline company/branch/user seed strategy is approved.

### Stage 3: Runtime activation validation

- Confirm DATABASE_URL is configured only in staging and remains redacted in logs.
- Confirm ERP_ENABLE_POSTGRES_RUNTIME remains disabled until schema and seed checks pass.
- Confirm startup gate diagnostics show PostgreSQL readiness criteria are satisfied before any relaxation.
- Confirm application SQL portability blockers are reviewed before runtime activation.

### Stage 4: Cutover validation

- Confirm data migration validation has passed.
- Confirm accounting, POS, inventory, payroll, and reporting smoke tests pass on staging PostgreSQL.
- Confirm rollback plan and production SQLite preservation plan are approved.
- Confirm final cutover decision remains NO-GO until deployment, migration, and runtime tests all pass.

## Notes

- Deployment dry-run readiness is YELLOW; this framework remains planning-only.

## Current Limitations

- Plan generation does not query staging PostgreSQL.
- Validation execution is available separately through the guarded Phase 5B.14O read-only path.
- Seed manifests and migration-history write behavior still need implementation.
- Runtime cutover remains NO-GO.
