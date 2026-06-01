# Migration Integrity Audit (Detailed)

**Audited at:** 2026-06-01 19:46:22 UTC
**Database:** `D:\Emma\My AccountingApp\data\eka_enterprise_v3.db`
**Overall score:** YELLOW
**Go/No-Go:** GO WITH WARNINGS

All checks are SELECT-only. No data or schema modifications were performed.

## Companies

**Area score:** GREEN

| Check | Count | Risk | Remediation |
|-------|------:|------|-------------|
| total_companies | 8 | LOW | Informational; monitor during migration dry-run. |

SQL (`total_companies`):

```sql
SELECT COUNT(*) FROM companies
```

| missing_names | 0 | HIGH | No action required. |

SQL (`missing_names`):

```sql
SELECT key FROM companies WHERE TRIM(COALESCE(name, '')) = ''
```

| duplicate_keys | 0 | HIGH | No action required. |

## Branches

**Area score:** YELLOW

| Check | Count | Risk | Remediation |
|-------|------:|------|-------------|
| total_branches | 2 | LOW | Informational; monitor during migration dry-run. |
| active_branches | 2 | LOW | Informational; monitor during migration dry-run. |
| inactive_branches | 0 | LOW | No action required. |
| missing_branch_code | 0 | MEDIUM | No action required. |

SQL (`missing_branch_code`):

```sql
SELECT branch_id, branch_name FROM branches WHERE branch_code IS NULL OR TRIM(branch_code) = ''
```

| duplicate_branch_code | 0 | HIGH | No action required. |
| duplicate_branch_access_key | 0 | HIGH | No action required. |
| invalid_branch_types | 0 | MEDIUM | No action required. |
| missing_manager_user_id | 2 | LOW | Informational; monitor during migration dry-run. |
| companies_over_active_branch_limit | 0 | HIGH | No action required. |

## Users

**Area score:** GREEN

| Check | Count | Risk | Remediation |
|-------|------:|------|-------------|
| total_users | 3 | LOW | Informational; monitor during migration dry-run. |
| users_by_role | 3 | LOW | Informational; monitor during migration dry-run. |

Note: [{'role': 'Staff', 'cnt': 1}, {'role': 'Dev', 'cnt': 1}, {'role': 'Branch Manager', 'cnt': 1}]

| duplicate_login_key | 0 | HIGH | No action required. |
| users_without_company_key | 0 | HIGH | No action required. |
| branch_scoped_users_without_branch_id | 0 | HIGH | No action required. |
| invalid_roles | 0 | MEDIUM | No action required. |
| inactive_users | 0 | LOW | No action required. |

## Journals

**Area score:** GREEN

| Check | Count | Risk | Remediation |
|-------|------:|------|-------------|
| journal_entries | 28 | LOW | Informational; monitor during migration dry-run. |
| journal_lines | 61 | LOW | Informational; monitor during migration dry-run. |
| unbalanced_journals | 0 | HIGH | No action required. |
| journals_without_lines | 0 | HIGH | No action required. |
| orphaned_journal_lines | 0 | HIGH | No action required. |
| duplicate_source_postings | 0 | MEDIUM | No action required. |

Note: POS may intentionally have Sale + COGS pairs; review source_type.

| duplicate_voucher_reference_no | 0 | MEDIUM | No action required. |

## POS

**Area score:** YELLOW

| Check | Count | Risk | Remediation |
|-------|------:|------|-------------|
| total_pos_sales | 8 | LOW | Informational; monitor during migration dry-run. |
| duplicate_receipt_numbers | 0 | HIGH | No action required. |
| sales_without_lines | 0 | MEDIUM | No action required. |
| orphaned_pos_sale_lines | 0 | HIGH | No action required. |
| sales_without_branch_id | 8 | MEDIUM | Review and clean up before migration; may not block cutover. |
| sales_without_journal_entry | 0 | MEDIUM | No action required. |

Note: Expected when sales exist but revenue journal not posted.

| suspended_sales_count | 3 | LOW | Informational; monitor during migration dry-run. |

## Inventory

**Area score:** GREEN

| Check | Count | Risk | Remediation |
|-------|------:|------|-------------|
| total_inventory_items | 3 | LOW | Informational; monitor during migration dry-run. |
| negative_stock | 0 | HIGH | No action required. |
| duplicate_barcode | 0 | MEDIUM | No action required. |
| duplicate_item_code | 0 | MEDIUM | No action required. |
| expired_stock_count | 2 | LOW | Informational; monitor during migration dry-run. |
| invalid_expiry_dates | 0 | MEDIUM | No action required. |
| orphaned_stock_movements | 0 | HIGH | No action required. |
| stock_movements_without_branch_id | 0 | MEDIUM | No action required. |

## AR/AP

**Area score:** YELLOW

| Check | Count | Risk | Remediation |
|-------|------:|------|-------------|
| invoices_without_customers | 0 | MEDIUM | No action required. |
| bills_without_suppliers | 0 | MEDIUM | No action required. |
| payments_without_source_reference | 1 | LOW | Informational; monitor during migration dry-run. |
| customer_balance_red_flags | 0 | MEDIUM | No action required. |

## Branch Governance

**Area score:** GREEN

| Check | Count | Risk | Remediation |
|-------|------:|------|-------------|
| branches_missing_module_grants | 0 | MEDIUM | No action required. |
| duplicate_module_grants | 0 | MEDIUM | No action required. |
| branch_managers_not_found_in_users | 0 | MEDIUM | No action required. |
| branch_managers_assigned_to_wrong_branch | 0 | MEDIUM | No action required. |
| branch_scoped_users_invalid_branch | 0 | HIGH | No action required. |
| inactive_branches_with_active_users | 0 | MEDIUM | No action required. |

## Tables Present

- `accounting_periods` (0 rows)
- `accounts_payable` (0 rows)
- `audit_logs` (96 rows)
- `bank_accounts` (0 rows)
- `bill_lines` (0 rows)
- `bills` (0 rows)
- `branch_module_grants` (34 rows)
- `branch_type_catalog` (6 rows)
- `branch_type_module_defaults` (69 rows)
- `branches` (2 rows)
- `cashier_closings` (0 rows)
- `chart_of_accounts` (38 rows)
- `companies` (8 rows)
- `company_subscriptions` (8 rows)
- `counterparties` (0 rows)
- `customer_transactions` (1 rows)
- `customers` (2 rows)
- `database_identity` (1 rows)
- `fixed_assets` (0 rows)
- `inventory` (3 rows)
- `inventory_import_batches` (0 rows)
- `invoice_lines` (0 rows)
- `invoices` (1 rows)
- `journal_entries` (28 rows)
- `journal_lines` (61 rows)
- `license_payment_transactions` (2 rows)
- `maintenance_settings` (1 rows)
- `migration_history` (2 rows)
- `migration_logs` (2 rows)
- `payment_allocations` (0 rows)
- `payments` (8 rows)
- `payroll` (1 rows)
- `payroll_records` (1 rows)
- `pending_approvals` (0 rows)
- `pos_returns` (0 rows)
- `pos_sale_lines` (13 rows)
- `pos_sales` (8 rows)
- `pos_suspended_sales` (3 rows)
- `purchase_orders` (0 rows)
- `recurring_transactions` (0 rows)
- `sales_invoices` (0 rows)
- `schema_version` (2 rows)
- `stock_movements` (0 rows)
- `subscription_plan_settings` (3 rows)
- `supplier_transactions` (0 rows)
- `suppliers` (4 rows)
- `system_logs` (114 rows)
- `system_settings` (1 rows)
- `transactions` (0 rows)
- `users` (3 rows)
- `vouchers` (0 rows)
