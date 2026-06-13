# SQLite to PostgreSQL Row-Copy Dry-Run Planner

Phase: 5B.15F

Read-only row projection only. No INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, COPY, PostgreSQL write transaction, data migration, PostgreSQL runtime enablement, production deployment, or SQLite behavior change was attempted.

## Summary

- Status: READY_FOR_DRY_RUN_COPY
- Tables evaluated: 51
- Rows evaluated: 527
- Rows mappable: 527
- Rows unmappable: 0
- Column mapping issues: 0 (0 blocking, 0 informational)
- FK-order migration tables planned: 51
- Estimated migration batches: 31

## Read-Only Guarantees

- SQLite was opened with `mode=ro`.
- PostgreSQL schema was parsed from `reports/postgres_generated_schema.sql`; no PostgreSQL connection was opened.
- Rows were projected in memory only; no INSERT statements or write transactions were built or executed.

## FK-Order Migration Plan

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

## Table Projection Summary

| Order | Table | Rows | Mappable | Unmappable | Mapped columns | Required | Nullable | Defaulted | Batches |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `accounting_periods` | 0 | 0 | 0 | 13 | 4 | 8 | 3 | 0 |
| 2 | `accounts_payable` | 0 | 0 | 0 | 5 | 1 | 4 | 0 | 0 |
| 3 | `branch_type_catalog` | 6 | 6 | 0 | 5 | 2 | 3 | 2 | 1 |
| 4 | `companies` | 8 | 8 | 0 | 24 | 1 | 23 | 9 | 1 |
| 5 | `customers` | 2 | 2 | 0 | 10 | 2 | 7 | 4 | 1 |
| 6 | `database_identity` | 1 | 1 | 0 | 7 | 1 | 6 | 4 | 1 |
| 7 | `journal_entries` | 28 | 28 | 0 | 27 | 2 | 24 | 4 | 1 |
| 8 | `license_payment_transactions` | 2 | 2 | 0 | 22 | 0 | 21 | 10 | 1 |
| 9 | `maintenance_settings` | 1 | 1 | 0 | 7 | 1 | 6 | 2 | 1 |
| 10 | `migration_history` | 2 | 2 | 0 | 3 | 1 | 2 | 1 | 1 |
| 11 | `migration_logs` | 2 | 2 | 0 | 11 | 1 | 9 | 4 | 1 |
| 12 | `payments` | 8 | 8 | 0 | 25 | 3 | 21 | 6 | 1 |
| 13 | `payroll_records` | 1 | 1 | 0 | 11 | 2 | 8 | 6 | 1 |
| 14 | `schema_version` | 2 | 2 | 0 | 3 | 2 | 1 | 1 | 1 |
| 15 | `subscription_plan_settings` | 3 | 3 | 0 | 10 | 0 | 9 | 6 | 1 |
| 16 | `suppliers` | 4 | 4 | 0 | 9 | 2 | 6 | 3 | 1 |
| 17 | `system_logs` | 114 | 114 | 0 | 5 | 0 | 4 | 1 | 1 |
| 18 | `system_settings` | 1 | 1 | 0 | 11 | 1 | 10 | 10 | 1 |
| 19 | `transactions` | 0 | 0 | 0 | 11 | 3 | 7 | 4 | 0 |
| 20 | `audit_logs` | 97 | 97 | 0 | 13 | 0 | 12 | 2 | 1 |
| 21 | `bills` | 0 | 0 | 0 | 28 | 2 | 25 | 9 | 0 |
| 22 | `branch_type_module_defaults` | 69 | 69 | 0 | 5 | 2 | 2 | 3 | 1 |
| 23 | `branches` | 2 | 2 | 0 | 14 | 3 | 11 | 4 | 1 |
| 24 | `cashier_closings` | 0 | 0 | 0 | 11 | 3 | 7 | 6 | 0 |
| 25 | `chart_of_accounts` | 38 | 38 | 0 | 16 | 0 | 15 | 7 | 1 |
| 26 | `company_subscriptions` | 8 | 8 | 0 | 9 | 0 | 8 | 4 | 1 |
| 27 | `counterparties` | 0 | 0 | 0 | 9 | 3 | 5 | 4 | 0 |
| 28 | `fixed_assets` | 0 | 0 | 0 | 36 | 0 | 35 | 13 | 0 |
| 29 | `inventory` | 3 | 3 | 0 | 26 | 0 | 25 | 11 | 1 |
| 30 | `inventory_import_batches` | 0 | 0 | 0 | 16 | 1 | 14 | 9 | 0 |
| 31 | `invoices` | 1 | 1 | 0 | 23 | 2 | 20 | 8 | 1 |
| 32 | `payroll` | 1 | 1 | 0 | 27 | 0 | 26 | 8 | 1 |
| 33 | `pending_approvals` | 0 | 0 | 0 | 9 | 0 | 8 | 3 | 0 |
| 34 | `pos_returns` | 0 | 0 | 0 | 17 | 4 | 12 | 7 | 0 |
| 35 | `pos_sales` | 8 | 8 | 0 | 20 | 4 | 15 | 9 | 1 |
| 36 | `pos_suspended_sales` | 3 | 3 | 0 | 11 | 3 | 7 | 4 | 1 |
| 37 | `purchase_orders` | 0 | 0 | 0 | 11 | 0 | 10 | 3 | 0 |
| 38 | `sales_invoices` | 0 | 0 | 0 | 10 | 0 | 9 | 3 | 0 |
| 39 | `supplier_transactions` | 0 | 0 | 0 | 10 | 5 | 4 | 2 | 0 |
| 40 | `users` | 3 | 3 | 0 | 14 | 4 | 9 | 3 | 1 |
| 41 | `vouchers` | 0 | 0 | 0 | 26 | 0 | 25 | 9 | 0 |
| 42 | `bank_accounts` | 0 | 0 | 0 | 11 | 2 | 8 | 5 | 0 |
| 43 | `bill_lines` | 0 | 0 | 0 | 7 | 2 | 4 | 5 | 0 |
| 44 | `branch_module_grants` | 34 | 34 | 0 | 6 | 3 | 2 | 3 | 1 |
| 45 | `customer_transactions` | 1 | 1 | 0 | 11 | 5 | 5 | 2 | 1 |
| 46 | `invoice_lines` | 0 | 0 | 0 | 9 | 2 | 6 | 6 | 0 |
| 47 | `journal_lines` | 61 | 61 | 0 | 5 | 2 | 2 | 3 | 1 |
| 48 | `payment_allocations` | 0 | 0 | 0 | 10 | 2 | 7 | 4 | 0 |
| 49 | `pos_sale_lines` | 13 | 13 | 0 | 14 | 3 | 10 | 8 | 1 |
| 50 | `recurring_transactions` | 0 | 0 | 0 | 15 | 4 | 10 | 4 | 0 |
| 51 | `stock_movements` | 0 | 0 | 0 | 24 | 5 | 18 | 6 | 0 |

## Table Column Mapping Details

### `accounting_periods`

- Source row count: 0
- Source columns: `closed_at`, `closed_by`, `company_key`, `end_date`, `id`, `is_locked`, `locked_at`, `locked_by`, `period_label`, `reopened_at`, `reopened_by`, `start_date`, `status`
- Destination columns: `closed_at`, `closed_by`, `company_key`, `end_date`, `id`, `is_locked`, `locked_at`, `locked_by`, `period_label`, `reopened_at`, `reopened_by`, `start_date`, `status`
- Mapped columns: `closed_at`, `closed_by`, `company_key`, `end_date`, `id`, `is_locked`, `locked_at`, `locked_by`, `period_label`, `reopened_at`, `reopened_by`, `start_date`, `status`
- Required fields: `company_key`, `end_date`, `period_label`, `start_date`
- Nullable fields: `closed_at`, `closed_by`, `is_locked`, `locked_at`, `locked_by`, `reopened_at`, `reopened_by`, `status`
- Defaulted fields: `id`, `is_locked`, `status`

### `accounts_payable`

- Source row count: 0
- Source columns: `amount`, `due_date`, `id`, `status`, `vendor`
- Destination columns: `amount`, `due_date`, `id`, `status`, `vendor`
- Mapped columns: `amount`, `due_date`, `id`, `status`, `vendor`
- Required fields: `id`
- Nullable fields: `amount`, `due_date`, `status`, `vendor`
- Defaulted fields: none

### `branch_type_catalog`

- Source row count: 6
- Source columns: `branch_type_key`, `branch_type_name`, `created_at`, `description`, `is_active`
- Destination columns: `branch_type_key`, `branch_type_name`, `created_at`, `description`, `is_active`
- Mapped columns: `branch_type_key`, `branch_type_name`, `created_at`, `description`, `is_active`
- Required fields: `branch_type_key`, `branch_type_name`
- Nullable fields: `created_at`, `description`, `is_active`
- Defaulted fields: `created_at`, `is_active`

### `companies`

- Source row count: 8
- Source columns: `admin_email`, `barcode_input_source`, `branch_price_per_month`, `contact_email`, `created_at`, `currency`, `deployment_status`, `expiry_date`, `industry`, `key`, `logo_url`, `max_branches`, `name`, `number_of_branches`, `phone_number`, `physical_address`, `recovery_answer`, `staff_key`, `status`, `sub_admin_key`, `subscription_end_date`, `subscription_expiry`, `tin`, `updated_at`
- Destination columns: `admin_email`, `barcode_input_source`, `branch_price_per_month`, `contact_email`, `created_at`, `currency`, `deployment_status`, `expiry_date`, `industry`, `key`, `logo_url`, `max_branches`, `name`, `number_of_branches`, `phone_number`, `physical_address`, `recovery_answer`, `staff_key`, `status`, `sub_admin_key`, `subscription_end_date`, `subscription_expiry`, `tin`, `updated_at`
- Mapped columns: `admin_email`, `barcode_input_source`, `branch_price_per_month`, `contact_email`, `created_at`, `currency`, `deployment_status`, `expiry_date`, `industry`, `key`, `logo_url`, `max_branches`, `name`, `number_of_branches`, `phone_number`, `physical_address`, `recovery_answer`, `staff_key`, `status`, `sub_admin_key`, `subscription_end_date`, `subscription_expiry`, `tin`, `updated_at`
- Required fields: `key`
- Nullable fields: `admin_email`, `barcode_input_source`, `branch_price_per_month`, `contact_email`, `created_at`, `currency`, `deployment_status`, `expiry_date`, `industry`, `logo_url`, `max_branches`, `name`, `number_of_branches`, `phone_number`, `physical_address`, `recovery_answer`, `staff_key`, `status`, `sub_admin_key`, `subscription_end_date`, `subscription_expiry`, `tin`, `updated_at`
- Defaulted fields: `barcode_input_source`, `branch_price_per_month`, `created_at`, `currency`, `deployment_status`, `max_branches`, `number_of_branches`, `status`, `updated_at`

### `customers`

- Source row count: 2
- Source columns: `address`, `company_key`, `created_at`, `currency`, `current_balance`, `customer_id`, `email`, `id`, `name`, `phone`
- Destination columns: `address`, `company_key`, `created_at`, `currency`, `current_balance`, `customer_id`, `email`, `id`, `name`, `phone`
- Mapped columns: `address`, `company_key`, `created_at`, `currency`, `current_balance`, `customer_id`, `email`, `id`, `name`, `phone`
- Required fields: `company_key`, `name`
- Nullable fields: `address`, `created_at`, `currency`, `current_balance`, `customer_id`, `email`, `phone`
- Defaulted fields: `created_at`, `currency`, `current_balance`, `id`

### `database_identity`

- Source row count: 1
- Source columns: `backend_label`, `created_at`, `environment_label`, `instance_id`, `last_startup_at`, `last_verified_at`, `schema_version`
- Destination columns: `backend_label`, `created_at`, `environment_label`, `instance_id`, `last_startup_at`, `last_verified_at`, `schema_version`
- Mapped columns: `backend_label`, `created_at`, `environment_label`, `instance_id`, `last_startup_at`, `last_verified_at`, `schema_version`
- Required fields: `instance_id`
- Nullable fields: `backend_label`, `created_at`, `environment_label`, `last_startup_at`, `last_verified_at`, `schema_version`
- Defaulted fields: `backend_label`, `created_at`, `last_verified_at`, `schema_version`

### `journal_entries`

- Source row count: 28
- Source columns: `approval_status`, `branch_id`, `company_key`, `created_at`, `created_by`, `customer_id`, `date`, `description`, `document_number`, `document_type`, `id`, `inventory_item_id`, `is_voided`, `payment_id`, `posted_at`, `posted_by`, `reference`, `reversed_entry_id`, `source_document_id`, `source_document_type`, `source_id`, `source_module`, `source_table`, `source_type`, `supplier_id`, `voided_at`, `voided_by`
- Destination columns: `approval_status`, `branch_id`, `company_key`, `created_at`, `created_by`, `customer_id`, `date`, `description`, `document_number`, `document_type`, `id`, `inventory_item_id`, `is_voided`, `payment_id`, `posted_at`, `posted_by`, `reference`, `reversed_entry_id`, `source_document_id`, `source_document_type`, `source_id`, `source_module`, `source_table`, `source_type`, `supplier_id`, `voided_at`, `voided_by`
- Mapped columns: `approval_status`, `branch_id`, `company_key`, `created_at`, `created_by`, `customer_id`, `date`, `description`, `document_number`, `document_type`, `id`, `inventory_item_id`, `is_voided`, `payment_id`, `posted_at`, `posted_by`, `reference`, `reversed_entry_id`, `source_document_id`, `source_document_type`, `source_id`, `source_module`, `source_table`, `source_type`, `supplier_id`, `voided_at`, `voided_by`
- Required fields: `date`, `description`
- Nullable fields: `approval_status`, `branch_id`, `company_key`, `created_at`, `created_by`, `customer_id`, `document_number`, `document_type`, `inventory_item_id`, `is_voided`, `payment_id`, `posted_at`, `posted_by`, `reference`, `reversed_entry_id`, `source_document_id`, `source_document_type`, `source_id`, `source_module`, `source_table`, `source_type`, `supplier_id`, `voided_at`, `voided_by`
- Defaulted fields: `approval_status`, `created_at`, `id`, `is_voided`

### `license_payment_transactions`

- Source row count: 2
- Source columns: `activated_at`, `authorization_url`, `callback_url`, `company_key`, `company_name`, `configured_amount`, `configured_duration_days`, `configured_duration_months`, `created_at`, `currency`, `expected_amount`, `gateway_status_summary`, `id`, `metadata_json`, `paid_at`, `payer_email`, `payment_context`, `plan_name`, `reference`, `status`, `updated_at`, `verified_at`
- Destination columns: `activated_at`, `authorization_url`, `callback_url`, `company_key`, `company_name`, `configured_amount`, `configured_duration_days`, `configured_duration_months`, `created_at`, `currency`, `expected_amount`, `gateway_status_summary`, `id`, `metadata_json`, `paid_at`, `payer_email`, `payment_context`, `plan_name`, `reference`, `status`, `updated_at`, `verified_at`
- Mapped columns: `activated_at`, `authorization_url`, `callback_url`, `company_key`, `company_name`, `configured_amount`, `configured_duration_days`, `configured_duration_months`, `created_at`, `currency`, `expected_amount`, `gateway_status_summary`, `id`, `metadata_json`, `paid_at`, `payer_email`, `payment_context`, `plan_name`, `reference`, `status`, `updated_at`, `verified_at`
- Required fields: none
- Nullable fields: `activated_at`, `authorization_url`, `callback_url`, `company_key`, `company_name`, `configured_amount`, `configured_duration_days`, `configured_duration_months`, `created_at`, `currency`, `expected_amount`, `gateway_status_summary`, `metadata_json`, `paid_at`, `payer_email`, `payment_context`, `plan_name`, `reference`, `status`, `updated_at`, `verified_at`
- Defaulted fields: `configured_amount`, `configured_duration_days`, `configured_duration_months`, `created_at`, `currency`, `expected_amount`, `id`, `payment_context`, `status`, `updated_at`

### `maintenance_settings`

- Source row count: 1
- Source columns: `end_time`, `id`, `is_active`, `maintenance_date`, `message`, `start_time`, `updated_at`
- Destination columns: `end_time`, `id`, `is_active`, `maintenance_date`, `message`, `start_time`, `updated_at`
- Mapped columns: `end_time`, `id`, `is_active`, `maintenance_date`, `message`, `start_time`, `updated_at`
- Required fields: `id`
- Nullable fields: `end_time`, `is_active`, `maintenance_date`, `message`, `start_time`, `updated_at`
- Defaulted fields: `is_active`, `updated_at`

### `migration_history`

- Source row count: 2
- Source columns: `applied_at`, `description`, `migration_id`
- Destination columns: `applied_at`, `description`, `migration_id`
- Mapped columns: `applied_at`, `description`, `migration_id`
- Required fields: `migration_id`
- Nullable fields: `applied_at`, `description`
- Defaulted fields: `applied_at`

### `migration_logs`

- Source row count: 2
- Source columns: `backup_path`, `company_count_after`, `company_count_before`, `created_at`, `description`, `details`, `id`, `row_counts_after`, `row_counts_before`, `status`, `version`
- Destination columns: `backup_path`, `company_count_after`, `company_count_before`, `created_at`, `description`, `details`, `id`, `row_counts_after`, `row_counts_before`, `status`, `version`
- Mapped columns: `backup_path`, `company_count_after`, `company_count_before`, `created_at`, `description`, `details`, `id`, `row_counts_after`, `row_counts_before`, `status`, `version`
- Required fields: `status`
- Nullable fields: `backup_path`, `company_count_after`, `company_count_before`, `created_at`, `description`, `details`, `row_counts_after`, `row_counts_before`, `version`
- Defaulted fields: `company_count_after`, `company_count_before`, `created_at`, `id`

### `payments`

- Source row count: 8
- Source columns: `amount`, `approval_status`, `approved_at`, `approved_by`, `bank_account_id`, `bill_id`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `currency`, `customer_id`, `id`, `invoice_id`, `last_journal_sync_at`, `method`, `payment_date`, `payment_type`, `posted_entry_id`, `reference`, `status`, `submitted_at`, `supplier_id`, `void_entry_id`
- Destination columns: `amount`, `approval_status`, `approved_at`, `approved_by`, `bank_account_id`, `bill_id`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `currency`, `customer_id`, `id`, `invoice_id`, `last_journal_sync_at`, `method`, `payment_date`, `payment_type`, `posted_entry_id`, `reference`, `status`, `submitted_at`, `supplier_id`, `void_entry_id`
- Mapped columns: `amount`, `approval_status`, `approved_at`, `approved_by`, `bank_account_id`, `bill_id`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `currency`, `customer_id`, `id`, `invoice_id`, `last_journal_sync_at`, `method`, `payment_date`, `payment_type`, `posted_entry_id`, `reference`, `status`, `submitted_at`, `supplier_id`, `void_entry_id`
- Required fields: `company_key`, `payment_date`, `payment_type`
- Nullable fields: `amount`, `approval_status`, `approved_at`, `approved_by`, `bank_account_id`, `bill_id`, `cancelled_at`, `cancelled_by`, `created_at`, `created_by`, `currency`, `customer_id`, `invoice_id`, `last_journal_sync_at`, `method`, `posted_entry_id`, `reference`, `status`, `submitted_at`, `supplier_id`, `void_entry_id`
- Defaulted fields: `amount`, `approval_status`, `created_at`, `currency`, `id`, `status`

### `payroll_records`

- Source row count: 1
- Source columns: `company_key`, `created_at`, `deductions`, `employee_name`, `gross_pay`, `id`, `net_pay`, `payroll_id`, `period_end`, `period_start`, `status`
- Destination columns: `company_key`, `created_at`, `deductions`, `employee_name`, `gross_pay`, `id`, `net_pay`, `payroll_id`, `period_end`, `period_start`, `status`
- Mapped columns: `company_key`, `created_at`, `deductions`, `employee_name`, `gross_pay`, `id`, `net_pay`, `payroll_id`, `period_end`, `period_start`, `status`
- Required fields: `company_key`, `employee_name`
- Nullable fields: `created_at`, `deductions`, `gross_pay`, `net_pay`, `payroll_id`, `period_end`, `period_start`, `status`
- Defaulted fields: `created_at`, `deductions`, `gross_pay`, `id`, `net_pay`, `status`

### `schema_version`

- Source row count: 2
- Source columns: `applied_at`, `description`, `version`
- Destination columns: `applied_at`, `description`, `version`
- Mapped columns: `applied_at`, `description`, `version`
- Required fields: `description`, `version`
- Nullable fields: `applied_at`
- Defaulted fields: `applied_at`

### `subscription_plan_settings`

- Source row count: 3
- Source columns: `configured_amount`, `created_at`, `currency`, `duration_days`, `duration_months`, `features_json`, `id`, `plan_name`, `updated_at`, `updated_by`
- Destination columns: `configured_amount`, `created_at`, `currency`, `duration_days`, `duration_months`, `features_json`, `id`, `plan_name`, `updated_at`, `updated_by`
- Mapped columns: `configured_amount`, `created_at`, `currency`, `duration_days`, `duration_months`, `features_json`, `id`, `plan_name`, `updated_at`, `updated_by`
- Required fields: none
- Nullable fields: `configured_amount`, `created_at`, `currency`, `duration_days`, `duration_months`, `features_json`, `plan_name`, `updated_at`, `updated_by`
- Defaulted fields: `created_at`, `currency`, `duration_days`, `duration_months`, `id`, `updated_at`

### `suppliers`

- Source row count: 4
- Source columns: `address`, `category`, `company_key`, `created_at`, `currency`, `email`, `id`, `name`, `phone`
- Destination columns: `address`, `category`, `company_key`, `created_at`, `currency`, `email`, `id`, `name`, `phone`
- Mapped columns: `address`, `category`, `company_key`, `created_at`, `currency`, `email`, `id`, `name`, `phone`
- Required fields: `company_key`, `name`
- Nullable fields: `address`, `category`, `created_at`, `currency`, `email`, `phone`
- Defaulted fields: `created_at`, `currency`, `id`

### `system_logs`

- Source row count: 114
- Source columns: `id`, `level`, `message`, `module_name`, `timestamp`
- Destination columns: `id`, `level`, `message`, `module_name`, `timestamp`
- Mapped columns: `id`, `level`, `message`, `module_name`, `timestamp`
- Required fields: none
- Nullable fields: `level`, `message`, `module_name`, `timestamp`
- Defaulted fields: `id`

### `system_settings`

- Source row count: 1
- Source columns: `bank_reconciliation_mode`, `base_currency`, `display_currency`, `enforce_document_approval`, `exchange_rate`, `id`, `inventory_cost_method`, `journal_source_of_truth`, `legacy_mirror_mode`, `master_price_per_month`, `updated_at`
- Destination columns: `bank_reconciliation_mode`, `base_currency`, `display_currency`, `enforce_document_approval`, `exchange_rate`, `id`, `inventory_cost_method`, `journal_source_of_truth`, `legacy_mirror_mode`, `master_price_per_month`, `updated_at`
- Mapped columns: `bank_reconciliation_mode`, `base_currency`, `display_currency`, `enforce_document_approval`, `exchange_rate`, `id`, `inventory_cost_method`, `journal_source_of_truth`, `legacy_mirror_mode`, `master_price_per_month`, `updated_at`
- Required fields: `id`
- Nullable fields: `bank_reconciliation_mode`, `base_currency`, `display_currency`, `enforce_document_approval`, `exchange_rate`, `inventory_cost_method`, `journal_source_of_truth`, `legacy_mirror_mode`, `master_price_per_month`, `updated_at`
- Defaulted fields: `bank_reconciliation_mode`, `base_currency`, `display_currency`, `enforce_document_approval`, `exchange_rate`, `inventory_cost_method`, `journal_source_of_truth`, `legacy_mirror_mode`, `master_price_per_month`, `updated_at`

### `transactions`

- Source row count: 0
- Source columns: `account`, `branch_id`, `company_key`, `created_at`, `created_by`, `credit`, `debit`, `description`, `id`, `reference`, `transaction_date`
- Destination columns: `account`, `branch_id`, `company_key`, `created_at`, `created_by`, `credit`, `debit`, `description`, `id`, `reference`, `transaction_date`
- Mapped columns: `account`, `branch_id`, `company_key`, `created_at`, `created_by`, `credit`, `debit`, `description`, `id`, `reference`, `transaction_date`
- Required fields: `account`, `company_key`, `transaction_date`
- Nullable fields: `branch_id`, `created_at`, `created_by`, `credit`, `debit`, `description`, `reference`
- Defaulted fields: `created_at`, `credit`, `debit`, `id`

### `audit_logs`

- Source row count: 97
- Source columns: `action`, `action_type`, `before_after_summary`, `branch_id`, `company_key`, `details`, `document_ref`, `event_id`, `id`, `ip_address`, `module_name`, `timestamp`, `user_role`
- Destination columns: `action`, `action_type`, `before_after_summary`, `branch_id`, `company_key`, `details`, `document_ref`, `event_id`, `id`, `ip_address`, `module_name`, `timestamp`, `user_role`
- Mapped columns: `action`, `action_type`, `before_after_summary`, `branch_id`, `company_key`, `details`, `document_ref`, `event_id`, `id`, `ip_address`, `module_name`, `timestamp`, `user_role`
- Required fields: none
- Nullable fields: `action`, `action_type`, `before_after_summary`, `branch_id`, `company_key`, `details`, `document_ref`, `event_id`, `ip_address`, `module_name`, `timestamp`, `user_role`
- Defaulted fields: `id`, `timestamp`

### `bills`

- Source row count: 0
- Source columns: `amount`, `approval_status`, `approved_at`, `approved_by`, `asset_category`, `asset_name`, `bill_date`, `bill_number`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `currency`, `description`, `due_date`, `expense_account_name`, `id`, `input_vat`, `last_journal_sync_at`, `output_vat`, `payment_method`, `posted_entry_id`, `purchase_classification`, `status`, `submitted_at`, `supplier_id`, `void_entry_id`
- Destination columns: `amount`, `approval_status`, `approved_at`, `approved_by`, `asset_category`, `asset_name`, `bill_date`, `bill_number`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `currency`, `description`, `due_date`, `expense_account_name`, `id`, `input_vat`, `last_journal_sync_at`, `output_vat`, `payment_method`, `posted_entry_id`, `purchase_classification`, `status`, `submitted_at`, `supplier_id`, `void_entry_id`
- Mapped columns: `amount`, `approval_status`, `approved_at`, `approved_by`, `asset_category`, `asset_name`, `bill_date`, `bill_number`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `currency`, `description`, `due_date`, `expense_account_name`, `id`, `input_vat`, `last_journal_sync_at`, `output_vat`, `payment_method`, `posted_entry_id`, `purchase_classification`, `status`, `submitted_at`, `supplier_id`, `void_entry_id`
- Required fields: `bill_date`, `company_key`
- Nullable fields: `amount`, `approval_status`, `approved_at`, `approved_by`, `asset_category`, `asset_name`, `bill_number`, `cancelled_at`, `cancelled_by`, `created_at`, `created_by`, `currency`, `description`, `due_date`, `expense_account_name`, `input_vat`, `last_journal_sync_at`, `output_vat`, `payment_method`, `posted_entry_id`, `purchase_classification`, `status`, `submitted_at`, `supplier_id`, `void_entry_id`
- Defaulted fields: `amount`, `approval_status`, `created_at`, `currency`, `id`, `input_vat`, `output_vat`, `purchase_classification`, `status`

### `branch_type_module_defaults`

- Source row count: 69
- Source columns: `branch_type_key`, `created_at`, `id`, `is_enabled`, `module_key`
- Destination columns: `branch_type_key`, `created_at`, `id`, `is_enabled`, `module_key`
- Mapped columns: `branch_type_key`, `created_at`, `id`, `is_enabled`, `module_key`
- Required fields: `branch_type_key`, `module_key`
- Nullable fields: `created_at`, `is_enabled`
- Defaulted fields: `created_at`, `id`, `is_enabled`

### `branches`

- Source row count: 2
- Source columns: `branch_access_key`, `branch_code`, `branch_id`, `branch_manager`, `branch_name`, `branch_tier`, `branch_type`, `company_key`, `contact_number`, `created_at`, `deployment_status`, `is_active`, `location`, `manager_user_id`
- Destination columns: `branch_access_key`, `branch_code`, `branch_id`, `branch_manager`, `branch_name`, `branch_tier`, `branch_type`, `company_key`, `contact_number`, `created_at`, `deployment_status`, `is_active`, `location`, `manager_user_id`
- Mapped columns: `branch_access_key`, `branch_code`, `branch_id`, `branch_manager`, `branch_name`, `branch_tier`, `branch_type`, `company_key`, `contact_number`, `created_at`, `deployment_status`, `is_active`, `location`, `manager_user_id`
- Required fields: `branch_id`, `branch_name`, `company_key`
- Nullable fields: `branch_access_key`, `branch_code`, `branch_manager`, `branch_tier`, `branch_type`, `contact_number`, `created_at`, `deployment_status`, `is_active`, `location`, `manager_user_id`
- Defaulted fields: `branch_tier`, `created_at`, `deployment_status`, `is_active`

### `cashier_closings`

- Source row count: 0
- Source columns: `branch_id`, `cashier`, `closed_at`, `closed_by`, `closing_date`, `company_key`, `counted_cash`, `difference`, `expected_cash`, `id`, `notes`
- Destination columns: `branch_id`, `cashier`, `closed_at`, `closed_by`, `closing_date`, `company_key`, `counted_cash`, `difference`, `expected_cash`, `id`, `notes`
- Mapped columns: `branch_id`, `cashier`, `closed_at`, `closed_by`, `closing_date`, `company_key`, `counted_cash`, `difference`, `expected_cash`, `id`, `notes`
- Required fields: `cashier`, `closing_date`, `company_key`
- Nullable fields: `branch_id`, `closed_at`, `closed_by`, `counted_cash`, `difference`, `expected_cash`, `notes`
- Defaulted fields: `branch_id`, `closed_at`, `counted_cash`, `difference`, `expected_cash`, `id`

### `chart_of_accounts`

- Source row count: 38
- Source columns: `account_code`, `account_name`, `account_type`, `allow_manual_posting`, `balance`, `category`, `code`, `company_key`, `control_account`, `created_at`, `id`, `is_active`, `name`, `parent_id`, `posting_allowed`, `type`
- Destination columns: `account_code`, `account_name`, `account_type`, `allow_manual_posting`, `balance`, `category`, `code`, `company_key`, `control_account`, `created_at`, `id`, `is_active`, `name`, `parent_id`, `posting_allowed`, `type`
- Mapped columns: `account_code`, `account_name`, `account_type`, `allow_manual_posting`, `balance`, `category`, `code`, `company_key`, `control_account`, `created_at`, `id`, `is_active`, `name`, `parent_id`, `posting_allowed`, `type`
- Required fields: none
- Nullable fields: `account_code`, `account_name`, `account_type`, `allow_manual_posting`, `balance`, `category`, `code`, `company_key`, `control_account`, `created_at`, `is_active`, `name`, `parent_id`, `posting_allowed`, `type`
- Defaulted fields: `allow_manual_posting`, `balance`, `control_account`, `created_at`, `id`, `is_active`, `posting_allowed`

### `company_subscriptions`

- Source row count: 8
- Source columns: `company_key`, `created_at`, `end_date`, `id`, `last_payment_reference`, `plan_name`, `start_date`, `status`, `updated_at`
- Destination columns: `company_key`, `created_at`, `end_date`, `id`, `last_payment_reference`, `plan_name`, `start_date`, `status`, `updated_at`
- Mapped columns: `company_key`, `created_at`, `end_date`, `id`, `last_payment_reference`, `plan_name`, `start_date`, `status`, `updated_at`
- Required fields: none
- Nullable fields: `company_key`, `created_at`, `end_date`, `last_payment_reference`, `plan_name`, `start_date`, `status`, `updated_at`
- Defaulted fields: `created_at`, `id`, `status`, `updated_at`

### `counterparties`

- Source row count: 0
- Source columns: `balance`, `city_region`, `company_key`, `created_at`, `id`, `last_transaction`, `party_name`, `party_type`, `updated_at`
- Destination columns: `balance`, `city_region`, `company_key`, `created_at`, `id`, `last_transaction`, `party_name`, `party_type`, `updated_at`
- Mapped columns: `balance`, `city_region`, `company_key`, `created_at`, `id`, `last_transaction`, `party_name`, `party_type`, `updated_at`
- Required fields: `company_key`, `party_name`, `party_type`
- Nullable fields: `balance`, `city_region`, `created_at`, `last_transaction`, `updated_at`
- Defaulted fields: `balance`, `created_at`, `id`, `updated_at`

### `fixed_assets`

- Source row count: 0
- Source columns: `accum_dep`, `accumulated_depreciation`, `acquisition_journal_entry_id`, `acquisition_source`, `acquisition_type`, `approval_status`, `approved_at`, `approved_by`, `asset_category`, `asset_name`, `book_value`, `company_key`, `cost`, `created_at`, `created_by`, `custodian`, `dep_rate`, `depreciation_method`, `depreciation_rate`, `description`, `id`, `last_depreciation_date`, `last_journal_sync_at`, `location`, `notes`, `opening_book_value`, `owner_contributor_name`, `owner_name`, `payment_method`, `posted_entry_id`, `purchase_cost`, `purchase_date`, `residual_value`, `status`, `supplier_id`, `useful_life_years`
- Destination columns: `accum_dep`, `accumulated_depreciation`, `acquisition_journal_entry_id`, `acquisition_source`, `acquisition_type`, `approval_status`, `approved_at`, `approved_by`, `asset_category`, `asset_name`, `book_value`, `company_key`, `cost`, `created_at`, `created_by`, `custodian`, `dep_rate`, `depreciation_method`, `depreciation_rate`, `description`, `id`, `last_depreciation_date`, `last_journal_sync_at`, `location`, `notes`, `opening_book_value`, `owner_contributor_name`, `owner_name`, `payment_method`, `posted_entry_id`, `purchase_cost`, `purchase_date`, `residual_value`, `status`, `supplier_id`, `useful_life_years`
- Mapped columns: `accum_dep`, `accumulated_depreciation`, `acquisition_journal_entry_id`, `acquisition_source`, `acquisition_type`, `approval_status`, `approved_at`, `approved_by`, `asset_category`, `asset_name`, `book_value`, `company_key`, `cost`, `created_at`, `created_by`, `custodian`, `dep_rate`, `depreciation_method`, `depreciation_rate`, `description`, `id`, `last_depreciation_date`, `last_journal_sync_at`, `location`, `notes`, `opening_book_value`, `owner_contributor_name`, `owner_name`, `payment_method`, `posted_entry_id`, `purchase_cost`, `purchase_date`, `residual_value`, `status`, `supplier_id`, `useful_life_years`
- Required fields: none
- Nullable fields: `accum_dep`, `accumulated_depreciation`, `acquisition_journal_entry_id`, `acquisition_source`, `acquisition_type`, `approval_status`, `approved_at`, `approved_by`, `asset_category`, `asset_name`, `book_value`, `company_key`, `cost`, `created_at`, `created_by`, `custodian`, `dep_rate`, `depreciation_method`, `depreciation_rate`, `description`, `last_depreciation_date`, `last_journal_sync_at`, `location`, `notes`, `opening_book_value`, `owner_contributor_name`, `owner_name`, `payment_method`, `posted_entry_id`, `purchase_cost`, `purchase_date`, `residual_value`, `status`, `supplier_id`, `useful_life_years`
- Defaulted fields: `accum_dep`, `accumulated_depreciation`, `acquisition_type`, `approval_status`, `cost`, `created_at`, `depreciation_method`, `depreciation_rate`, `id`, `opening_book_value`, `residual_value`, `status`, `useful_life_years`

### `inventory`

- Source row count: 3
- Source columns: `barcode`, `batch_number`, `brand`, `category`, `cogs_account_id`, `company_key`, `cost_price`, `created_at`, `description`, `expiry_date`, `id`, `inventory_account_id`, `is_active`, `item_code`, `item_name`, `min_stock_level`, `opening_balance`, `price`, `qty`, `supplier_name`, `tax_rate`, `unit`, `updated_at`, `vat_category`, `warehouse`, `warehouse_location`
- Destination columns: `barcode`, `batch_number`, `brand`, `category`, `cogs_account_id`, `company_key`, `cost_price`, `created_at`, `description`, `expiry_date`, `id`, `inventory_account_id`, `is_active`, `item_code`, `item_name`, `min_stock_level`, `opening_balance`, `price`, `qty`, `supplier_name`, `tax_rate`, `unit`, `updated_at`, `vat_category`, `warehouse`, `warehouse_location`
- Mapped columns: `barcode`, `batch_number`, `brand`, `category`, `cogs_account_id`, `company_key`, `cost_price`, `created_at`, `description`, `expiry_date`, `id`, `inventory_account_id`, `is_active`, `item_code`, `item_name`, `min_stock_level`, `opening_balance`, `price`, `qty`, `supplier_name`, `tax_rate`, `unit`, `updated_at`, `vat_category`, `warehouse`, `warehouse_location`
- Required fields: none
- Nullable fields: `barcode`, `batch_number`, `brand`, `category`, `cogs_account_id`, `company_key`, `cost_price`, `created_at`, `description`, `expiry_date`, `inventory_account_id`, `is_active`, `item_code`, `item_name`, `min_stock_level`, `opening_balance`, `price`, `qty`, `supplier_name`, `tax_rate`, `unit`, `updated_at`, `vat_category`, `warehouse`, `warehouse_location`
- Defaulted fields: `cost_price`, `created_at`, `id`, `is_active`, `min_stock_level`, `opening_balance`, `price`, `qty`, `tax_rate`, `updated_at`, `warehouse`

### `inventory_import_batches`

- Source row count: 0
- Source columns: `branch_id`, `company_key`, `created_at`, `created_count`, `error_count`, `id`, `import_reference`, `imported_by`, `imported_item_count`, `opening_posted`, `opening_posted_at`, `opening_posted_by`, `opening_posted_entry_id`, `skipped_count`, `total_opening_value`, `updated_count`
- Destination columns: `branch_id`, `company_key`, `created_at`, `created_count`, `error_count`, `id`, `import_reference`, `imported_by`, `imported_item_count`, `opening_posted`, `opening_posted_at`, `opening_posted_by`, `opening_posted_entry_id`, `skipped_count`, `total_opening_value`, `updated_count`
- Mapped columns: `branch_id`, `company_key`, `created_at`, `created_count`, `error_count`, `id`, `import_reference`, `imported_by`, `imported_item_count`, `opening_posted`, `opening_posted_at`, `opening_posted_by`, `opening_posted_entry_id`, `skipped_count`, `total_opening_value`, `updated_count`
- Required fields: `company_key`
- Nullable fields: `branch_id`, `created_at`, `created_count`, `error_count`, `import_reference`, `imported_by`, `imported_item_count`, `opening_posted`, `opening_posted_at`, `opening_posted_by`, `opening_posted_entry_id`, `skipped_count`, `total_opening_value`, `updated_count`
- Defaulted fields: `created_at`, `created_count`, `error_count`, `id`, `imported_item_count`, `opening_posted`, `skipped_count`, `total_opening_value`, `updated_count`

### `invoices`

- Source row count: 1
- Source columns: `amount`, `approval_status`, `approved_at`, `approved_by`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `currency`, `customer_id`, `description`, `due_date`, `id`, `input_vat`, `invoice_date`, `invoice_number`, `last_journal_sync_at`, `output_vat`, `posted_entry_id`, `status`, `submitted_at`, `void_entry_id`
- Destination columns: `amount`, `approval_status`, `approved_at`, `approved_by`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `currency`, `customer_id`, `description`, `due_date`, `id`, `input_vat`, `invoice_date`, `invoice_number`, `last_journal_sync_at`, `output_vat`, `posted_entry_id`, `status`, `submitted_at`, `void_entry_id`
- Mapped columns: `amount`, `approval_status`, `approved_at`, `approved_by`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `currency`, `customer_id`, `description`, `due_date`, `id`, `input_vat`, `invoice_date`, `invoice_number`, `last_journal_sync_at`, `output_vat`, `posted_entry_id`, `status`, `submitted_at`, `void_entry_id`
- Required fields: `company_key`, `invoice_date`
- Nullable fields: `amount`, `approval_status`, `approved_at`, `approved_by`, `cancelled_at`, `cancelled_by`, `created_at`, `created_by`, `currency`, `customer_id`, `description`, `due_date`, `input_vat`, `invoice_number`, `last_journal_sync_at`, `output_vat`, `posted_entry_id`, `status`, `submitted_at`, `void_entry_id`
- Defaulted fields: `amount`, `approval_status`, `created_at`, `currency`, `id`, `input_vat`, `output_vat`, `status`

### `payroll`

- Source row count: 1
- Source columns: `account_number`, `allowances`, `approval_status`, `approved_at`, `approved_by`, `bank_name`, `basic_salary`, `company_key`, `created_at`, `created_by`, `deductions`, `emp_id`, `emp_name`, `id`, `last_journal_sync_at`, `month`, `net_salary`, `paye`, `payment_method`, `payment_status`, `posted_entry_id`, `ssnit_t1`, `ssnit_t2`, `ssnit_t3`, `status`, `taxable_income`, `year`
- Destination columns: `account_number`, `allowances`, `approval_status`, `approved_at`, `approved_by`, `bank_name`, `basic_salary`, `company_key`, `created_at`, `created_by`, `deductions`, `emp_id`, `emp_name`, `id`, `last_journal_sync_at`, `month`, `net_salary`, `paye`, `payment_method`, `payment_status`, `posted_entry_id`, `ssnit_t1`, `ssnit_t2`, `ssnit_t3`, `status`, `taxable_income`, `year`
- Mapped columns: `account_number`, `allowances`, `approval_status`, `approved_at`, `approved_by`, `bank_name`, `basic_salary`, `company_key`, `created_at`, `created_by`, `deductions`, `emp_id`, `emp_name`, `id`, `last_journal_sync_at`, `month`, `net_salary`, `paye`, `payment_method`, `payment_status`, `posted_entry_id`, `ssnit_t1`, `ssnit_t2`, `ssnit_t3`, `status`, `taxable_income`, `year`
- Required fields: none
- Nullable fields: `account_number`, `allowances`, `approval_status`, `approved_at`, `approved_by`, `bank_name`, `basic_salary`, `company_key`, `created_at`, `created_by`, `deductions`, `emp_id`, `emp_name`, `last_journal_sync_at`, `month`, `net_salary`, `paye`, `payment_method`, `payment_status`, `posted_entry_id`, `ssnit_t1`, `ssnit_t2`, `ssnit_t3`, `status`, `taxable_income`, `year`
- Defaulted fields: `allowances`, `approval_status`, `created_at`, `deductions`, `id`, `payment_status`, `ssnit_t3`, `status`

### `pending_approvals`

- Source row count: 0
- Source columns: `admin_notes`, `amount`, `company_key`, `id`, `payment_method`, `payment_reference`, `plan_requested`, `status`, `timestamp`
- Destination columns: `admin_notes`, `amount`, `company_key`, `id`, `payment_method`, `payment_reference`, `plan_requested`, `status`, `timestamp`
- Mapped columns: `admin_notes`, `amount`, `company_key`, `id`, `payment_method`, `payment_reference`, `plan_requested`, `status`, `timestamp`
- Required fields: none
- Nullable fields: `admin_notes`, `amount`, `company_key`, `payment_method`, `payment_reference`, `plan_requested`, `status`, `timestamp`
- Defaulted fields: `id`, `status`, `timestamp`

### `pos_returns`

- Source row count: 0
- Source columns: `branch_id`, `company_key`, `id`, `item_id`, `item_name`, `original_sale_reference`, `pos_sale_line_id`, `posted_entry_id`, `qty_returned`, `reason`, `refund_amount`, `refund_method`, `return_reference`, `returned_at`, `returned_by`, `status`, `unit_price`
- Destination columns: `branch_id`, `company_key`, `id`, `item_id`, `item_name`, `original_sale_reference`, `pos_sale_line_id`, `posted_entry_id`, `qty_returned`, `reason`, `refund_amount`, `refund_method`, `return_reference`, `returned_at`, `returned_by`, `status`, `unit_price`
- Mapped columns: `branch_id`, `company_key`, `id`, `item_id`, `item_name`, `original_sale_reference`, `pos_sale_line_id`, `posted_entry_id`, `qty_returned`, `reason`, `refund_amount`, `refund_method`, `return_reference`, `returned_at`, `returned_by`, `status`, `unit_price`
- Required fields: `company_key`, `item_name`, `original_sale_reference`, `return_reference`
- Nullable fields: `branch_id`, `item_id`, `pos_sale_line_id`, `posted_entry_id`, `qty_returned`, `reason`, `refund_amount`, `refund_method`, `returned_at`, `returned_by`, `status`, `unit_price`
- Defaulted fields: `branch_id`, `id`, `qty_returned`, `refund_amount`, `returned_at`, `status`, `unit_price`

### `pos_sales`

- Source row count: 8
- Source columns: `amount_tendered`, `branch_id`, `cashier`, `change_due`, `cogs_posted_entry_id`, `company_key`, `created_at`, `customer_id`, `discount_total`, `grand_total`, `id`, `last_journal_sync_at`, `payment_method`, `posted_entry_id`, `receipt_number`, `sale_date`, `sale_datetime`, `sale_reference`, `subtotal`, `tax_total`
- Destination columns: `amount_tendered`, `branch_id`, `cashier`, `change_due`, `cogs_posted_entry_id`, `company_key`, `created_at`, `customer_id`, `discount_total`, `grand_total`, `id`, `last_journal_sync_at`, `payment_method`, `posted_entry_id`, `receipt_number`, `sale_date`, `sale_datetime`, `sale_reference`, `subtotal`, `tax_total`
- Mapped columns: `amount_tendered`, `branch_id`, `cashier`, `change_due`, `cogs_posted_entry_id`, `company_key`, `created_at`, `customer_id`, `discount_total`, `grand_total`, `id`, `last_journal_sync_at`, `payment_method`, `posted_entry_id`, `receipt_number`, `sale_date`, `sale_datetime`, `sale_reference`, `subtotal`, `tax_total`
- Required fields: `company_key`, `receipt_number`, `sale_date`, `sale_reference`
- Nullable fields: `amount_tendered`, `branch_id`, `cashier`, `change_due`, `cogs_posted_entry_id`, `created_at`, `customer_id`, `discount_total`, `grand_total`, `last_journal_sync_at`, `payment_method`, `posted_entry_id`, `sale_datetime`, `subtotal`, `tax_total`
- Defaulted fields: `amount_tendered`, `branch_id`, `change_due`, `created_at`, `discount_total`, `grand_total`, `id`, `subtotal`, `tax_total`

### `pos_suspended_sales`

- Source row count: 3
- Source columns: `branch_id`, `cancelled_at`, `cart_json`, `cashier`, `company_key`, `created_at`, `id`, `note`, `resumed_at`, `status`, `suspend_reference`
- Destination columns: `branch_id`, `cancelled_at`, `cart_json`, `cashier`, `company_key`, `created_at`, `id`, `note`, `resumed_at`, `status`, `suspend_reference`
- Mapped columns: `branch_id`, `cancelled_at`, `cart_json`, `cashier`, `company_key`, `created_at`, `id`, `note`, `resumed_at`, `status`, `suspend_reference`
- Required fields: `cart_json`, `company_key`, `suspend_reference`
- Nullable fields: `branch_id`, `cancelled_at`, `cashier`, `created_at`, `note`, `resumed_at`, `status`
- Defaulted fields: `branch_id`, `created_at`, `id`, `status`

### `purchase_orders`

- Source row count: 0
- Source columns: `company_key`, `cost`, `created_at`, `id`, `item`, `order_date`, `po_no`, `quantity`, `status`, `supplier_name`, `total_amount`
- Destination columns: `company_key`, `cost`, `created_at`, `id`, `item`, `order_date`, `po_no`, `quantity`, `status`, `supplier_name`, `total_amount`
- Mapped columns: `company_key`, `cost`, `created_at`, `id`, `item`, `order_date`, `po_no`, `quantity`, `status`, `supplier_name`, `total_amount`
- Required fields: none
- Nullable fields: `company_key`, `cost`, `created_at`, `item`, `order_date`, `po_no`, `quantity`, `status`, `supplier_name`, `total_amount`
- Defaulted fields: `created_at`, `id`, `status`

### `sales_invoices`

- Source row count: 0
- Source columns: `company_key`, `created_at`, `customer_email`, `customer_name`, `due_date`, `id`, `invoice_date`, `invoice_no`, `status`, `total_amount`
- Destination columns: `company_key`, `created_at`, `customer_email`, `customer_name`, `due_date`, `id`, `invoice_date`, `invoice_no`, `status`, `total_amount`
- Mapped columns: `company_key`, `created_at`, `customer_email`, `customer_name`, `due_date`, `id`, `invoice_date`, `invoice_no`, `status`, `total_amount`
- Required fields: none
- Nullable fields: `company_key`, `created_at`, `customer_email`, `customer_name`, `due_date`, `invoice_date`, `invoice_no`, `status`, `total_amount`
- Defaulted fields: `created_at`, `id`, `status`

### `supplier_transactions`

- Source row count: 0
- Source columns: `amount`, `company_key`, `created_at`, `created_by`, `description`, `id`, `reference`, `supplier_id`, `transaction_date`, `transaction_type`
- Destination columns: `amount`, `company_key`, `created_at`, `created_by`, `description`, `id`, `reference`, `supplier_id`, `transaction_date`, `transaction_type`
- Mapped columns: `amount`, `company_key`, `created_at`, `created_by`, `description`, `id`, `reference`, `supplier_id`, `transaction_date`, `transaction_type`
- Required fields: `amount`, `company_key`, `supplier_id`, `transaction_date`, `transaction_type`
- Nullable fields: `created_at`, `created_by`, `description`, `reference`
- Defaulted fields: `created_at`, `id`

### `users`

- Source row count: 3
- Source columns: `branch_id`, `company_key`, `created_at`, `current_session_id`, `full_name`, `id`, `last_login_device`, `login_key`, `password_hash`, `role`, `security_answer`, `security_question`, `status`, `user_id`
- Destination columns: `branch_id`, `company_key`, `created_at`, `current_session_id`, `full_name`, `id`, `last_login_device`, `login_key`, `password_hash`, `role`, `security_answer`, `security_question`, `status`, `user_id`
- Mapped columns: `branch_id`, `company_key`, `created_at`, `current_session_id`, `full_name`, `id`, `last_login_device`, `login_key`, `password_hash`, `role`, `security_answer`, `security_question`, `status`, `user_id`
- Required fields: `company_key`, `full_name`, `login_key`, `role`
- Nullable fields: `branch_id`, `created_at`, `current_session_id`, `last_login_device`, `password_hash`, `security_answer`, `security_question`, `status`, `user_id`
- Defaulted fields: `created_at`, `id`, `status`

### `vouchers`

- Source row count: 0
- Source columns: `approval_status`, `approved_at`, `approved_by`, `balance_after`, `branch_id`, `company_key`, `created_at`, `created_by`, `credit`, `date`, `debit`, `id`, `is_cleared`, `is_voided`, `last_journal_sync_at`, `ledger`, `narration`, `payment_method`, `posted_entry_id`, `ref_no`, `reference_no`, `status`, `submitted_at`, `v_type`, `voided_at`, `voided_by`
- Destination columns: `approval_status`, `approved_at`, `approved_by`, `balance_after`, `branch_id`, `company_key`, `created_at`, `created_by`, `credit`, `date`, `debit`, `id`, `is_cleared`, `is_voided`, `last_journal_sync_at`, `ledger`, `narration`, `payment_method`, `posted_entry_id`, `ref_no`, `reference_no`, `status`, `submitted_at`, `v_type`, `voided_at`, `voided_by`
- Mapped columns: `approval_status`, `approved_at`, `approved_by`, `balance_after`, `branch_id`, `company_key`, `created_at`, `created_by`, `credit`, `date`, `debit`, `id`, `is_cleared`, `is_voided`, `last_journal_sync_at`, `ledger`, `narration`, `payment_method`, `posted_entry_id`, `ref_no`, `reference_no`, `status`, `submitted_at`, `v_type`, `voided_at`, `voided_by`
- Required fields: none
- Nullable fields: `approval_status`, `approved_at`, `approved_by`, `balance_after`, `branch_id`, `company_key`, `created_at`, `created_by`, `credit`, `date`, `debit`, `is_cleared`, `is_voided`, `last_journal_sync_at`, `ledger`, `narration`, `payment_method`, `posted_entry_id`, `ref_no`, `reference_no`, `status`, `submitted_at`, `v_type`, `voided_at`, `voided_by`
- Defaulted fields: `approval_status`, `balance_after`, `created_at`, `credit`, `debit`, `id`, `is_cleared`, `is_voided`, `status`

### `bank_accounts`

- Source row count: 0
- Source columns: `account_name`, `account_number`, `account_type`, `balance`, `bank_name`, `branch_id`, `company_key`, `created_at`, `created_by`, `currency`, `id`
- Destination columns: `account_name`, `account_number`, `account_type`, `balance`, `bank_name`, `branch_id`, `company_key`, `created_at`, `created_by`, `currency`, `id`
- Mapped columns: `account_name`, `account_number`, `account_type`, `balance`, `bank_name`, `branch_id`, `company_key`, `created_at`, `created_by`, `currency`, `id`
- Required fields: `account_name`, `company_key`
- Nullable fields: `account_number`, `account_type`, `balance`, `bank_name`, `branch_id`, `created_at`, `created_by`, `currency`
- Defaulted fields: `account_type`, `balance`, `created_at`, `currency`, `id`

### `bill_lines`

- Source row count: 0
- Source columns: `bill_id`, `created_at`, `id`, `item_name`, `line_total`, `quantity`, `unit_price`
- Destination columns: `bill_id`, `created_at`, `id`, `item_name`, `line_total`, `quantity`, `unit_price`
- Mapped columns: `bill_id`, `created_at`, `id`, `item_name`, `line_total`, `quantity`, `unit_price`
- Required fields: `bill_id`, `item_name`
- Nullable fields: `created_at`, `line_total`, `quantity`, `unit_price`
- Defaulted fields: `created_at`, `id`, `line_total`, `quantity`, `unit_price`

### `branch_module_grants`

- Source row count: 34
- Source columns: `branch_id`, `company_key`, `created_at`, `id`, `is_enabled`, `module_key`
- Destination columns: `branch_id`, `company_key`, `created_at`, `id`, `is_enabled`, `module_key`
- Mapped columns: `branch_id`, `company_key`, `created_at`, `id`, `is_enabled`, `module_key`
- Required fields: `branch_id`, `company_key`, `module_key`
- Nullable fields: `created_at`, `is_enabled`
- Defaulted fields: `created_at`, `id`, `is_enabled`

### `customer_transactions`

- Source row count: 1
- Source columns: `amount`, `branch_id`, `company_key`, `created_at`, `created_by`, `customer_id`, `description`, `id`, `reference`, `transaction_date`, `transaction_type`
- Destination columns: `amount`, `branch_id`, `company_key`, `created_at`, `created_by`, `customer_id`, `description`, `id`, `reference`, `transaction_date`, `transaction_type`
- Mapped columns: `amount`, `branch_id`, `company_key`, `created_at`, `created_by`, `customer_id`, `description`, `id`, `reference`, `transaction_date`, `transaction_type`
- Required fields: `amount`, `company_key`, `customer_id`, `transaction_date`, `transaction_type`
- Nullable fields: `branch_id`, `created_at`, `created_by`, `description`, `reference`
- Defaulted fields: `created_at`, `id`

### `invoice_lines`

- Source row count: 0
- Source columns: `cost_price`, `created_at`, `id`, `inventory_item_id`, `invoice_id`, `item_name`, `line_total`, `quantity`, `unit_price`
- Destination columns: `cost_price`, `created_at`, `id`, `inventory_item_id`, `invoice_id`, `item_name`, `line_total`, `quantity`, `unit_price`
- Mapped columns: `cost_price`, `created_at`, `id`, `inventory_item_id`, `invoice_id`, `item_name`, `line_total`, `quantity`, `unit_price`
- Required fields: `invoice_id`, `item_name`
- Nullable fields: `cost_price`, `created_at`, `inventory_item_id`, `line_total`, `quantity`, `unit_price`
- Defaulted fields: `cost_price`, `created_at`, `id`, `line_total`, `quantity`, `unit_price`

### `journal_lines`

- Source row count: 61
- Source columns: `account_id`, `credit`, `debit`, `entry_id`, `id`
- Destination columns: `account_id`, `credit`, `debit`, `entry_id`, `id`
- Mapped columns: `account_id`, `credit`, `debit`, `entry_id`, `id`
- Required fields: `account_id`, `entry_id`
- Nullable fields: `credit`, `debit`
- Defaulted fields: `credit`, `debit`, `id`

### `payment_allocations`

- Source row count: 0
- Source columns: `allocated_at`, `amount`, `bill_id`, `branch_id`, `company_key`, `created_by`, `currency`, `id`, `invoice_id`, `payment_id`
- Destination columns: `allocated_at`, `amount`, `bill_id`, `branch_id`, `company_key`, `created_by`, `currency`, `id`, `invoice_id`, `payment_id`
- Mapped columns: `allocated_at`, `amount`, `bill_id`, `branch_id`, `company_key`, `created_by`, `currency`, `id`, `invoice_id`, `payment_id`
- Required fields: `company_key`, `payment_id`
- Nullable fields: `allocated_at`, `amount`, `bill_id`, `branch_id`, `created_by`, `currency`, `invoice_id`
- Defaulted fields: `allocated_at`, `amount`, `currency`, `id`

### `pos_sale_lines`

- Source row count: 13
- Source columns: `barcode`, `company_key`, `cost_price`, `created_at`, `id`, `inventory_item_id`, `item_code`, `item_name`, `line_discount`, `line_total`, `pos_sale_id`, `qty_sold`, `tax_rate`, `unit_price`
- Destination columns: `barcode`, `company_key`, `cost_price`, `created_at`, `id`, `inventory_item_id`, `item_code`, `item_name`, `line_discount`, `line_total`, `pos_sale_id`, `qty_sold`, `tax_rate`, `unit_price`
- Mapped columns: `barcode`, `company_key`, `cost_price`, `created_at`, `id`, `inventory_item_id`, `item_code`, `item_name`, `line_discount`, `line_total`, `pos_sale_id`, `qty_sold`, `tax_rate`, `unit_price`
- Required fields: `company_key`, `item_name`, `pos_sale_id`
- Nullable fields: `barcode`, `cost_price`, `created_at`, `inventory_item_id`, `item_code`, `line_discount`, `line_total`, `qty_sold`, `tax_rate`, `unit_price`
- Defaulted fields: `cost_price`, `created_at`, `id`, `line_discount`, `line_total`, `qty_sold`, `tax_rate`, `unit_price`

### `recurring_transactions`

- Source row count: 0
- Source columns: `amount`, `branch_id`, `company_key`, `created_at`, `created_by`, `description`, `frequency`, `id`, `is_active`, `last_run_at`, `next_run_date`, `recurrence_payload`, `source_id`, `source_module`, `source_table`
- Destination columns: `amount`, `branch_id`, `company_key`, `created_at`, `created_by`, `description`, `frequency`, `id`, `is_active`, `last_run_at`, `next_run_date`, `recurrence_payload`, `source_id`, `source_module`, `source_table`
- Mapped columns: `amount`, `branch_id`, `company_key`, `created_at`, `created_by`, `description`, `frequency`, `id`, `is_active`, `last_run_at`, `next_run_date`, `recurrence_payload`, `source_id`, `source_module`, `source_table`
- Required fields: `company_key`, `description`, `frequency`, `next_run_date`
- Nullable fields: `amount`, `branch_id`, `created_at`, `created_by`, `is_active`, `last_run_at`, `recurrence_payload`, `source_id`, `source_module`, `source_table`
- Defaulted fields: `amount`, `created_at`, `id`, `is_active`

### `stock_movements`

- Source row count: 0
- Source columns: `approval_status`, `approved_at`, `approved_by`, `branch_id`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `id`, `inventory_item_id`, `item_name`, `last_journal_sync_at`, `movement_type`, `new_qty`, `notes`, `posted_entry_id`, `previous_qty`, `quantity`, `reason`, `reference`, `status`, `submitted_at`, `void_entry_id`
- Destination columns: `approval_status`, `approved_at`, `approved_by`, `branch_id`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `id`, `inventory_item_id`, `item_name`, `last_journal_sync_at`, `movement_type`, `new_qty`, `notes`, `posted_entry_id`, `previous_qty`, `quantity`, `reason`, `reference`, `status`, `submitted_at`, `void_entry_id`
- Mapped columns: `approval_status`, `approved_at`, `approved_by`, `branch_id`, `cancelled_at`, `cancelled_by`, `company_key`, `created_at`, `created_by`, `id`, `inventory_item_id`, `item_name`, `last_journal_sync_at`, `movement_type`, `new_qty`, `notes`, `posted_entry_id`, `previous_qty`, `quantity`, `reason`, `reference`, `status`, `submitted_at`, `void_entry_id`
- Required fields: `company_key`, `inventory_item_id`, `item_name`, `movement_type`, `quantity`
- Nullable fields: `approval_status`, `approved_at`, `approved_by`, `branch_id`, `cancelled_at`, `cancelled_by`, `created_at`, `created_by`, `last_journal_sync_at`, `new_qty`, `notes`, `posted_entry_id`, `previous_qty`, `reason`, `reference`, `status`, `submitted_at`, `void_entry_id`
- Defaulted fields: `approval_status`, `created_at`, `id`, `new_qty`, `previous_qty`, `status`


## Column Mapping Issues

- No column mapping issues found.

## Row Projection Failures

- No sampled row projection failures found.

## Final Status

- READY_FOR_DRY_RUN_COPY: every evaluated SQLite row can be projected into the generated PostgreSQL destination schema.
- Actual row-copy engine may be built next, but real data migration and PostgreSQL writes remain blocked until explicitly authorized.
