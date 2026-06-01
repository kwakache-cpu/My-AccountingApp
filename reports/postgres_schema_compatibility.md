# PostgreSQL Schema Compatibility

**Audited at:** 2026-06-01 20:07:48 UTC  
**Phase 5B.11:** Application identity on INSERT is **GREEN**; schema DDL remains **SQLite-native** (42 tables with AUTOINCREMENT). Postgres requires generated DDL + ETL before runtime cutover.

**Database:** `D:\Emma\My AccountingApp\data\eka_enterprise_v3.db`  
**Tables:** 51

## Summary

- Total tables: **51**
- Total rows (sum): **526**
- Tables with AUTOINCREMENT: **42**
- Tables with triggers: **0**

## Table Inventory

| Table | Rows | Primary Key | FKs | Indexes | Triggers | SQLite-only |
|-------|-----:|-------------|----:|--------:|---------:|-------------|
| `accounting_periods` | 0 | id | 0 | 1 | 0 | AUTOINCREMENT on PK |
| `accounts_payable` | 0 | id | 0 | 0 | 0 | — |
| `audit_logs` | 96 | id | 1 | 2 | 0 | AUTOINCREMENT on PK |
| `bank_accounts` | 0 | id | 2 | 1 | 0 | AUTOINCREMENT on PK |
| `bill_lines` | 0 | id | 1 | 1 | 0 | AUTOINCREMENT on PK |
| `bills` | 0 | id | 1 | 2 | 0 | AUTOINCREMENT on PK |
| `branch_module_grants` | 34 | id | 2 | 1 | 0 | AUTOINCREMENT on PK |
| `branch_type_catalog` | 6 | branch_type_key | 0 | 0 | 0 | — |
| `branch_type_module_defaults` | 69 | id | 1 | 1 | 0 | AUTOINCREMENT on PK |
| `branches` | 2 | branch_id | 1 | 2 | 0 | — |
| `cashier_closings` | 0 | id | 1 | 2 | 0 | AUTOINCREMENT on PK |
| `chart_of_accounts` | 38 | id | 1 | 5 | 0 | AUTOINCREMENT on PK |
| `companies` | 8 | key | 0 | 0 | 0 | — |
| `company_subscriptions` | 8 | id | 1 | 2 | 0 | AUTOINCREMENT on PK |
| `counterparties` | 0 | id | 1 | 1 | 0 | AUTOINCREMENT on PK |
| `customer_transactions` | 1 | id | 3 | 2 | 0 | AUTOINCREMENT on PK |
| `customers` | 2 | id | 0 | 2 | 0 | AUTOINCREMENT on PK |
| `database_identity` | 1 | instance_id | 0 | 0 | 0 | — |
| `fixed_assets` | 0 | id | 1 | 0 | 0 | AUTOINCREMENT on PK |
| `inventory` | 3 | id | 1 | 3 | 0 | AUTOINCREMENT on PK |
| `inventory_import_batches` | 0 | id | 1 | 2 | 0 | AUTOINCREMENT on PK |
| `invoice_lines` | 0 | id | 2 | 2 | 0 | AUTOINCREMENT on PK |
| `invoices` | 1 | id | 1 | 2 | 0 | AUTOINCREMENT on PK |
| `journal_entries` | 28 | id | 0 | 5 | 0 | AUTOINCREMENT on PK |
| `journal_lines` | 61 | id | 2 | 2 | 0 | AUTOINCREMENT on PK |
| `license_payment_transactions` | 2 | id | 0 | 3 | 0 | AUTOINCREMENT on PK |
| `maintenance_settings` | 1 | id | 0 | 0 | 0 | — |
| `migration_history` | 2 | migration_id | 0 | 0 | 0 | — |
| `migration_logs` | 2 | id | 0 | 0 | 0 | AUTOINCREMENT on PK |
| `payment_allocations` | 0 | id | 5 | 3 | 0 | AUTOINCREMENT on PK |
| `payments` | 8 | id | 0 | 1 | 0 | AUTOINCREMENT on PK |
| `payroll` | 1 | id | 1 | 0 | 0 | AUTOINCREMENT on PK |
| `payroll_records` | 1 | id | 0 | 0 | 0 | AUTOINCREMENT on PK |
| `pending_approvals` | 0 | id | 1 | 0 | 0 | AUTOINCREMENT on PK |
| `pos_returns` | 0 | id | 1 | 2 | 0 | AUTOINCREMENT on PK |
| `pos_sale_lines` | 13 | id | 2 | 2 | 0 | AUTOINCREMENT on PK |
| `pos_sales` | 8 | id | 1 | 2 | 0 | AUTOINCREMENT on PK |
| `pos_suspended_sales` | 3 | id | 1 | 2 | 0 | AUTOINCREMENT on PK |
| `purchase_orders` | 0 | id | 1 | 0 | 0 | AUTOINCREMENT on PK |
| `recurring_transactions` | 0 | id | 2 | 2 | 0 | AUTOINCREMENT on PK |
| `sales_invoices` | 0 | id | 1 | 0 | 0 | AUTOINCREMENT on PK |
| `schema_version` | 2 | version | 0 | 0 | 0 | — |
| `stock_movements` | 0 | id | 3 | 2 | 0 | AUTOINCREMENT on PK |
| `subscription_plan_settings` | 3 | id | 0 | 1 | 0 | AUTOINCREMENT on PK |
| `supplier_transactions` | 0 | id | 2 | 2 | 0 | AUTOINCREMENT on PK |
| `suppliers` | 4 | id | 0 | 0 | 0 | AUTOINCREMENT on PK |
| `system_logs` | 114 | id | 0 | 0 | 0 | AUTOINCREMENT on PK |
| `system_settings` | 1 | id | 0 | 0 | 0 | — |
| `transactions` | 0 | id | 0 | 0 | 0 | AUTOINCREMENT on PK |
| `users` | 3 | id | 1 | 3 | 0 | AUTOINCREMENT on PK |
| `vouchers` | 0 | id | 1 | 1 | 0 | AUTOINCREMENT on PK |

## Per-Table Detail

### `accounting_periods`

- **Row count:** 0
- **Primary key:** id

**Indexes:** `idx_accounting_periods_company_status`

```sql
CREATE TABLE accounting_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            period_label TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_locked INTEGER DEFAULT 0,
            locked_at TIMESTAMP,
            locked_by TEXT, status TEXT DEFAULT 'Open', closed_at TIMESTAMP, closed_by TEXT, reopened_at TIMESTAMP, reopened_by TEXT,
            UNIQUE(company_key, period_label)
        )
```

### `accounts_payable`

- **Row count:** 0
- **Primary key:** id

```sql
CREATE TABLE accounts_payable (id INTEGER PRIMARY KEY, vendor TEXT, amount REAL, status TEXT, due_date TEXT)
```

### `audit_logs`

- **Row count:** 96
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

**Indexes:** `idx_audit_logs_action_type`, `idx_audit_logs_company_timestamp`

```sql
CREATE TABLE audit_logs 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                      company_key TEXT, 
                      user_role TEXT, 
                      action TEXT, 
                      module_name TEXT, details TEXT, ip_address TEXT, branch_id TEXT, action_type TEXT, document_ref TEXT, before_after_summary TEXT, event_id TEXT,
                      FOREIGN KEY (company_key) REFERENCES companies(key))
```

### `bank_accounts`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `branch_id` → `branches.branch_id` (on_delete=SET NULL)
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_bank_accounts_company`

```sql
CREATE TABLE bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT,
            account_name TEXT NOT NULL,
            account_number TEXT,
            bank_name TEXT,
            account_type TEXT DEFAULT 'Bank',
            currency TEXT DEFAULT 'GHS',
            balance REAL DEFAULT 0,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
```

### `bill_lines`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `bill_id` → `bills.id` (on_delete=CASCADE)

**Indexes:** `idx_bill_lines_bill_id`

```sql
CREATE TABLE bill_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            quantity REAL DEFAULT 1,
            unit_price REAL DEFAULT 0,
            line_total REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE
        )
```

### `bills`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `supplier_id` → `suppliers.id` (on_delete=NO ACTION)

**Indexes:** `idx_bills_company_status`, `idx_bills_company_bill_number`

```sql
CREATE TABLE bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            supplier_id INTEGER,
            bill_number TEXT,
            bill_date TEXT NOT NULL,
            due_date TEXT,
            status TEXT DEFAULT 'Draft',
            amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            description TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, input_vat REAL DEFAULT 0, output_vat REAL DEFAULT 0, approval_status TEXT DEFAULT 'Draft', posted_entry_id INTEGER, void_entry_id INTEGER, last_journal_sync_at TIMESTAMP, submitted_at TIMESTAMP, approved_at TIMESTAMP, approved_by TEXT, cancelled_at TIMESTAMP, cancelled_by TEXT, purchase_classification TEXT DEFAULT 'Inventory Purchase', payment_method TEXT, expense_account_name TEXT, asset_name TEXT, asset_category TEXT,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
```

### `branch_module_grants`

- **Row count:** 34
- **Primary key:** id

**Foreign keys:**
- `branch_id` → `branches.branch_id` (on_delete=CASCADE)
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_branch_module_grants_company_branch`

```sql
CREATE TABLE branch_module_grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT NOT NULL,
            module_key TEXT NOT NULL,
            is_enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_key, branch_id, module_key),
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches (branch_id) ON DELETE CASCADE
        )
```

### `branch_type_catalog`

- **Row count:** 6
- **Primary key:** branch_type_key

```sql
CREATE TABLE branch_type_catalog (
            branch_type_key TEXT PRIMARY KEY,
            branch_type_name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
```

### `branch_type_module_defaults`

- **Row count:** 69
- **Primary key:** id

**Foreign keys:**
- `branch_type_key` → `branch_type_catalog.branch_type_key` (on_delete=NO ACTION)

**Indexes:** `idx_branch_type_module_defaults_type`

```sql
CREATE TABLE branch_type_module_defaults (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_type_key TEXT NOT NULL,
            module_key TEXT NOT NULL,
            is_enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(branch_type_key, module_key),
            FOREIGN KEY (branch_type_key) REFERENCES branch_type_catalog (branch_type_key)
        )
```

### `branches`

- **Row count:** 2
- **Primary key:** branch_id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_branches_access_key`, `idx_branches_company`

```sql
CREATE TABLE branches (
                branch_id TEXT PRIMARY KEY,
                company_key TEXT NOT NULL,
                branch_name TEXT NOT NULL,
                location TEXT,
                branch_type TEXT,
                branch_access_key TEXT UNIQUE,
                contact_number TEXT,
                branch_manager TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1, manager_user_id TEXT, deployment_status TEXT DEFAULT 'active', branch_tier TEXT DEFAULT 'standard', branch_code TEXT,
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
```

### `cashier_closings`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_cashier_closings_company_date`, `idx_cashier_closings_unique_drawer`

```sql
CREATE TABLE cashier_closings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT DEFAULT '',
            cashier TEXT NOT NULL,
            closing_date TEXT NOT NULL,
            expected_cash REAL DEFAULT 0,
            counted_cash REAL DEFAULT 0,
            difference REAL DEFAULT 0,
            notes TEXT,
            closed_by TEXT,
            closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
```

### `chart_of_accounts`

- **Row count:** 38
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

**Indexes:** `idx_chart_of_accounts_account_code_unique`, `idx_chart_of_accounts_control_account`, `idx_chart_of_accounts_active`, `idx_chart_of_accounts_parent_id`, `idx_chart_of_accounts_type`

```sql
CREATE TABLE chart_of_accounts 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      account_code TEXT,
                      account_name TEXT,
                      account_type TEXT,
                      balance REAL DEFAULT 0.0,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP, name TEXT, type TEXT, parent_id INTEGER, category TEXT, code TEXT, posting_allowed INTEGER DEFAULT 1, control_account INTEGER DEFAULT 0, allow_manual_posting INTEGER DEFAULT 1, is_active INTEGER DEFAULT 1,
                      FOREIGN KEY (company_key) REFERENCES companies(key))
```

### `companies`

- **Row count:** 8
- **Primary key:** key

```sql
CREATE TABLE companies 
                     (key TEXT PRIMARY KEY, 
                      name TEXT, 
                      tin TEXT, 
                      sub_admin_key TEXT, 
                      staff_key TEXT, 
                      recovery_answer TEXT,
                      admin_email TEXT,
                      status TEXT DEFAULT 'Active',
                      subscription_end_date DATETIME,
                      deployment_status TEXT DEFAULT 'Live',
                      expiry_date DATETIME,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, contact_email TEXT, barcode_input_source TEXT DEFAULT 'Keyboard Entry', number_of_branches INTEGER DEFAULT 1, max_branches INTEGER DEFAULT 1, branch_price_per_month REAL DEFAULT 0.0, subscription_expiry TEXT, phone_number TEXT, physical_address TEXT, industry TEXT, currency TEXT DEFAULT 'GHS', logo_url TEXT)
```

### `company_subscriptions`

- **Row count:** 8
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

**Indexes:** `idx_company_subscriptions_status_end_date`, `idx_company_subscriptions_company_key`

```sql
CREATE TABLE company_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT UNIQUE,
            plan_name TEXT,
            status TEXT DEFAULT 'trial',
            start_date TEXT,
            end_date TEXT,
            last_payment_reference TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key)
        )
```

### `counterparties`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_counterparties_company_type`

```sql
CREATE TABLE counterparties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                party_name TEXT NOT NULL,
                party_type TEXT NOT NULL,
                city_region TEXT,
                last_transaction TEXT,
                balance REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_key, party_name, party_type),
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
```

### `customer_transactions`

- **Row count:** 1
- **Primary key:** id

**Foreign keys:**
- `branch_id` → `branches.branch_id` (on_delete=SET NULL)
- `customer_id` → `customers.id` (on_delete=CASCADE)
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_customer_transactions_company_date`, `idx_customer_transactions_customer_date`

```sql
CREATE TABLE customer_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            customer_id INTEGER NOT NULL,
            branch_id TEXT,
            transaction_type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            reference TEXT,
            transaction_date TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
```

### `customers`

- **Row count:** 2
- **Primary key:** id

**Indexes:** `idx_customers_company_name`, `idx_customers_company_customer_id`

```sql
CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            currency TEXT DEFAULT 'GHS',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, customer_id TEXT, current_balance REAL DEFAULT 0,
            UNIQUE(company_key, name)
        )
```

### `database_identity`

- **Row count:** 1
- **Primary key:** instance_id

```sql
CREATE TABLE database_identity (
            instance_id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        , schema_version INTEGER DEFAULT 0, last_startup_at TIMESTAMP, backend_label TEXT DEFAULT 'SQLite', environment_label TEXT)
```

### `fixed_assets`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

```sql
CREATE TABLE fixed_assets 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      company_key TEXT, 
                      asset_name TEXT, 
                      purchase_cost REAL, 
                      dep_rate REAL, 
                      accum_dep REAL DEFAULT 0.0, 
                      book_value REAL, 
                      purchase_date TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP, asset_category TEXT, cost REAL DEFAULT 0, depreciation_rate REAL DEFAULT 0, accumulated_depreciation REAL DEFAULT 0, location TEXT, status TEXT DEFAULT 'Active', opening_book_value REAL DEFAULT 0, useful_life_years REAL DEFAULT 0, residual_value REAL DEFAULT 0, depreciation_method TEXT DEFAULT 'Straight-line', last_depreciation_date TEXT, supplier_id INTEGER, custodian TEXT, description TEXT, notes TEXT, acquisition_type TEXT DEFAULT 'Opening Balance Asset', acquisition_source TEXT, payment_method TEXT, owner_contributor_name TEXT, owner_name TEXT, approval_status TEXT DEFAULT 'Posted', approved_at TIMESTAMP, approved_by TEXT, posted_entry_id INTEGER, acquisition_journal_entry_id INTEGER, last_journal_sync_at TIMESTAMP, created_by TEXT,
                      FOREIGN KEY (company_key) REFERENCES companies(key))
```

### `inventory`

- **Row count:** 3
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

**Indexes:** `idx_inv_barcode`, `idx_inv_name`, `idx_inv_comp`

```sql
CREATE TABLE inventory 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      company_key TEXT, 
                      item_name TEXT, 
                      unit TEXT, 
                      qty REAL DEFAULT 0.0, 
                      price REAL DEFAULT 0.0, 
                      cost_price REAL DEFAULT 0.0, 
                      warehouse TEXT DEFAULT 'Main',
                      barcode TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, item_code TEXT, category TEXT, description TEXT, min_stock_level REAL DEFAULT 10, tax_rate REAL DEFAULT 0, warehouse_location TEXT, is_active INTEGER DEFAULT 1, opening_balance REAL DEFAULT 0, inventory_account_id INTEGER, cogs_account_id INTEGER, brand TEXT, supplier_name TEXT, expiry_date TEXT, batch_number TEXT, vat_category TEXT,
                      FOREIGN KEY (company_key) REFERENCES companies(key))
```

### `inventory_import_batches`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_inventory_import_batches_company`, `idx_inventory_import_batches_reference`

```sql
CREATE TABLE inventory_import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_reference TEXT UNIQUE,
            company_key TEXT NOT NULL,
            branch_id TEXT,
            imported_item_count INTEGER DEFAULT 0,
            created_count INTEGER DEFAULT 0,
            updated_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            total_opening_value REAL DEFAULT 0,
            imported_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            opening_posted INTEGER DEFAULT 0,
            opening_posted_entry_id INTEGER,
            opening_posted_at TIMESTAMP,
            opening_posted_by TEXT,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
```

### `invoice_lines`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `inventory_item_id` → `inventory.id` (on_delete=SET NULL)
- `invoice_id` → `invoices.id` (on_delete=CASCADE)

**Indexes:** `idx_invoice_lines_inventory_item_id`, `idx_invoice_lines_invoice_id`

```sql
CREATE TABLE invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            inventory_item_id INTEGER,
            item_name TEXT NOT NULL,
            quantity REAL DEFAULT 1,
            unit_price REAL DEFAULT 0,
            line_total REAL DEFAULT 0,
            cost_price REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory(id) ON DELETE SET NULL
        )
```

### `invoices`

- **Row count:** 1
- **Primary key:** id

**Foreign keys:**
- `customer_id` → `customers.id` (on_delete=NO ACTION)

**Indexes:** `idx_invoices_company_status`, `idx_invoices_company_invoice_number`

```sql
CREATE TABLE invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            customer_id INTEGER,
            invoice_number TEXT,
            invoice_date TEXT NOT NULL,
            due_date TEXT,
            status TEXT DEFAULT 'Draft',
            amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            description TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, input_vat REAL DEFAULT 0, output_vat REAL DEFAULT 0, approval_status TEXT DEFAULT 'Draft', posted_entry_id INTEGER, void_entry_id INTEGER, last_journal_sync_at TIMESTAMP, submitted_at TIMESTAMP, approved_at TIMESTAMP, approved_by TEXT, cancelled_at TIMESTAMP, cancelled_by TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
```

### `journal_entries`

- **Row count:** 28
- **Primary key:** id

**Indexes:** `idx_journal_entries_supplier`, `idx_journal_entries_customer`, `idx_journal_entries_source`, `idx_journal_entries_reporting`, `idx_journal_entries_company_date`

```sql
CREATE TABLE journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            reference TEXT,
            created_by TEXT,
            branch_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        , customer_id INTEGER, supplier_id INTEGER, inventory_item_id INTEGER, payment_id INTEGER, source_module TEXT, source_table TEXT, source_id INTEGER, source_type TEXT, reversed_entry_id INTEGER, is_voided INTEGER DEFAULT 0, voided_at TIMESTAMP, voided_by TEXT, approval_status TEXT DEFAULT 'Posted', document_number TEXT, document_type TEXT, posted_at TIMESTAMP, posted_by TEXT, source_document_type TEXT, source_document_id INTEGER)
```

### `journal_lines`

- **Row count:** 61
- **Primary key:** id

**Foreign keys:**
- `account_id` → `chart_of_accounts.id` (on_delete=NO ACTION)
- `entry_id` → `journal_entries.id` (on_delete=CASCADE)

**Indexes:** `idx_journal_lines_entry_account`, `idx_journal_lines_entry`

```sql
CREATE TABLE journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            FOREIGN KEY (entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
            FOREIGN KEY (account_id) REFERENCES chart_of_accounts(id)
        )
```

### `license_payment_transactions`

- **Row count:** 2
- **Primary key:** id

**Indexes:** `idx_license_payment_transactions_plan_status`, `idx_license_payment_transactions_verified_at`, `idx_license_payment_transactions_company_status`

```sql
CREATE TABLE license_payment_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT UNIQUE,
            company_key TEXT,
            company_name TEXT,
            payer_email TEXT,
            payment_context TEXT DEFAULT 'license_activation',
            expected_amount INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            status TEXT DEFAULT 'initialized',
            authorization_url TEXT,
            callback_url TEXT,
            metadata_json TEXT,
            gateway_status_summary TEXT,
            paid_at TIMESTAMP,
            verified_at TIMESTAMP,
            activated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        , plan_name TEXT, configured_amount REAL DEFAULT 0, configured_duration_months INTEGER DEFAULT 0, configured_duration_days INTEGER DEFAULT 0)
```

### `maintenance_settings`

- **Row count:** 1
- **Primary key:** id

```sql
CREATE TABLE maintenance_settings 
                     (id INTEGER PRIMARY KEY, 
                      maintenance_date TEXT,
                      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, start_time TEXT, end_time TEXT, is_active INTEGER DEFAULT 0, message TEXT)
```

### `migration_history`

- **Row count:** 2
- **Primary key:** migration_id

```sql
CREATE TABLE migration_history (
            migration_id TEXT PRIMARY KEY,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
```

### `migration_logs`

- **Row count:** 2
- **Primary key:** id

```sql
CREATE TABLE migration_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER,
            description TEXT,
            status TEXT NOT NULL,
            backup_path TEXT,
            company_count_before INTEGER DEFAULT 0,
            company_count_after INTEGER DEFAULT 0,
            row_counts_before TEXT,
            row_counts_after TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
```

### `payment_allocations`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `branch_id` → `branches.branch_id` (on_delete=SET NULL)
- `bill_id` → `bills.id` (on_delete=CASCADE)
- `invoice_id` → `invoices.id` (on_delete=CASCADE)
- `payment_id` → `payments.id` (on_delete=CASCADE)
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_payment_allocations_bill`, `idx_payment_allocations_invoice`, `idx_payment_allocations_payment`

```sql
CREATE TABLE payment_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            payment_id INTEGER NOT NULL,
            invoice_id INTEGER,
            bill_id INTEGER,
            amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            branch_id TEXT,
            created_by TEXT,
            allocated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (payment_id) REFERENCES payments(id) ON DELETE CASCADE,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
```

### `payments`

- **Row count:** 8
- **Primary key:** id

**Indexes:** `idx_payments_company_status`

```sql
CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            payment_date TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            customer_id INTEGER,
            supplier_id INTEGER,
            invoice_id INTEGER,
            bill_id INTEGER,
            amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'GHS',
            method TEXT,
            reference TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        , bank_account_id INTEGER, approval_status TEXT DEFAULT 'Draft', posted_entry_id INTEGER, void_entry_id INTEGER, last_journal_sync_at TIMESTAMP, status TEXT DEFAULT 'Draft', submitted_at TIMESTAMP, approved_at TIMESTAMP, approved_by TEXT, cancelled_at TIMESTAMP, cancelled_by TEXT)
```

### `payroll`

- **Row count:** 1
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

```sql
CREATE TABLE payroll 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      company_key TEXT, 
                      emp_name TEXT, 
                      basic_salary REAL, 
                      ssnit_t1 REAL, 
                      ssnit_t2 REAL, 
                      ssnit_t3 REAL DEFAULT 0.0,
                      taxable_income REAL, 
                      paye REAL, 
                      net_salary REAL, 
                      month TEXT, 
                      year TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP, emp_id TEXT, bank_name TEXT, account_number TEXT, allowances REAL DEFAULT 0, payment_status TEXT DEFAULT 'Unpaid', deductions REAL DEFAULT 0, status TEXT DEFAULT 'Active', payment_method TEXT, approval_status TEXT DEFAULT 'Posted', approved_at TIMESTAMP, approved_by TEXT, posted_entry_id INTEGER, last_journal_sync_at TIMESTAMP, created_by TEXT,
                      FOREIGN KEY (company_key) REFERENCES companies(key))
```

### `payroll_records`

- **Row count:** 1
- **Primary key:** id

```sql
CREATE TABLE payroll_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            payroll_id INTEGER,
            period_start TEXT,
            period_end TEXT,
            employee_name TEXT NOT NULL,
            gross_pay REAL DEFAULT 0,
            deductions REAL DEFAULT 0,
            net_pay REAL DEFAULT 0,
            status TEXT DEFAULT 'Draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
```

### `pending_approvals`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

```sql
CREATE TABLE pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT,
                payment_reference TEXT UNIQUE,
                amount REAL,
                payment_method TEXT,
                plan_requested TEXT,
                status TEXT DEFAULT 'Pending',
                admin_notes TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_key) REFERENCES companies (key)
            )
```

### `pos_returns`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_pos_returns_sale_line`, `idx_pos_returns_reference_line`

```sql
CREATE TABLE pos_returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT DEFAULT '',
            original_sale_reference TEXT NOT NULL,
            return_reference TEXT NOT NULL,
            pos_sale_line_id INTEGER,
            item_id INTEGER,
            item_name TEXT NOT NULL,
            qty_returned REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            refund_amount REAL DEFAULT 0,
            reason TEXT,
            refund_method TEXT,
            returned_by TEXT,
            returned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_entry_id INTEGER,
            status TEXT DEFAULT 'Posted',
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
```

### `pos_sale_lines`

- **Row count:** 13
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=CASCADE)
- `pos_sale_id` → `pos_sales.id` (on_delete=CASCADE)

**Indexes:** `idx_pos_sale_lines_item`, `idx_pos_sale_lines_sale`

```sql
CREATE TABLE pos_sale_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pos_sale_id INTEGER NOT NULL,
            company_key TEXT NOT NULL,
            inventory_item_id INTEGER,
            item_name TEXT NOT NULL,
            item_code TEXT,
            barcode TEXT,
            qty_sold REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            line_discount REAL DEFAULT 0,
            tax_rate REAL DEFAULT 0,
            line_total REAL DEFAULT 0,
            cost_price REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pos_sale_id) REFERENCES pos_sales (id) ON DELETE CASCADE,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
```

### `pos_sales`

- **Row count:** 8
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_pos_sales_cashier_date`, `idx_pos_sales_reference`

```sql
CREATE TABLE pos_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT DEFAULT '',
            sale_reference TEXT NOT NULL,
            receipt_number TEXT NOT NULL,
            sale_date TEXT NOT NULL,
            sale_datetime TEXT,
            cashier TEXT,
            payment_method TEXT,
            customer_id INTEGER,
            subtotal REAL DEFAULT 0,
            discount_total REAL DEFAULT 0,
            tax_total REAL DEFAULT 0,
            grand_total REAL DEFAULT 0,
            amount_tendered REAL DEFAULT 0,
            change_due REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, posted_entry_id INTEGER, cogs_posted_entry_id INTEGER, last_journal_sync_at TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
```

### `pos_suspended_sales`

- **Row count:** 3
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_pos_suspended_sales_status`, `idx_pos_suspended_sales_reference`

```sql
CREATE TABLE pos_suspended_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT DEFAULT '',
            suspend_reference TEXT NOT NULL,
            cashier TEXT,
            cart_json TEXT NOT NULL,
            note TEXT,
            status TEXT DEFAULT 'suspended',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resumed_at TIMESTAMP,
            cancelled_at TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
        )
```

### `purchase_orders`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

```sql
CREATE TABLE purchase_orders 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      po_no TEXT,
                      supplier_name TEXT,
                      order_date TEXT,
                      total_amount REAL,
                      status TEXT DEFAULT 'Pending',
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP, item TEXT, quantity INTEGER, cost REAL,
                      FOREIGN KEY (company_key) REFERENCES companies(key))
```

### `recurring_transactions`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `branch_id` → `branches.branch_id` (on_delete=SET NULL)
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_recurring_transactions_next_run`, `idx_recurring_transactions_company`

```sql
CREATE TABLE recurring_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT,
            description TEXT NOT NULL,
            frequency TEXT NOT NULL,
            amount REAL DEFAULT 0,
            next_run_date TEXT NOT NULL,
            last_run_at TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            source_module TEXT,
            source_table TEXT,
            source_id INTEGER,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            recurrence_payload TEXT,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
```

### `sales_invoices`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

```sql
CREATE TABLE sales_invoices 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      company_key TEXT,
                      invoice_no TEXT,
                      customer_name TEXT,
                      customer_email TEXT,
                      invoice_date TEXT,
                      due_date TEXT,
                      total_amount REAL,
                      status TEXT DEFAULT 'Pending',
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))
```

### `schema_version`

- **Row count:** 2
- **Primary key:** version

```sql
CREATE TABLE schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
```

### `stock_movements`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `branch_id` → `branches.branch_id` (on_delete=SET NULL)
- `company_key` → `companies.key` (on_delete=CASCADE)
- `inventory_item_id` → `inventory.id` (on_delete=CASCADE)

**Indexes:** `idx_stock_movements_item`, `idx_stock_movements_company_created`

```sql
CREATE TABLE stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            branch_id TEXT,
            inventory_item_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            movement_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            reason TEXT,
            previous_qty REAL DEFAULT 0,
            new_qty REAL DEFAULT 0,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, posted_entry_id INTEGER, void_entry_id INTEGER, last_journal_sync_at TIMESTAMP, status TEXT DEFAULT 'Draft', approval_status TEXT DEFAULT 'Draft', submitted_at TIMESTAMP, approved_at TIMESTAMP, approved_by TEXT, cancelled_at TIMESTAMP, cancelled_by TEXT, reference TEXT, notes TEXT,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory(id) ON DELETE CASCADE,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(branch_id) ON DELETE SET NULL
        )
```

### `subscription_plan_settings`

- **Row count:** 3
- **Primary key:** id

**Indexes:** `idx_subscription_plan_settings_plan_name`

```sql
CREATE TABLE subscription_plan_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_name TEXT UNIQUE,
            configured_amount REAL,
            currency TEXT DEFAULT 'GHS',
            duration_months INTEGER DEFAULT 0,
            duration_days INTEGER DEFAULT 0,
            features_json TEXT,
            updated_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
```

### `supplier_transactions`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `supplier_id` → `suppliers.id` (on_delete=CASCADE)
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_supplier_transactions_company_date`, `idx_supplier_transactions_supplier_date`

```sql
CREATE TABLE supplier_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            supplier_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            reference TEXT,
            transaction_date TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_key) REFERENCES companies(key) ON DELETE CASCADE,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE
        )
```

### `suppliers`

- **Row count:** 4
- **Primary key:** id

```sql
CREATE TABLE suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            currency TEXT DEFAULT 'GHS',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, category TEXT,
            UNIQUE(company_key, name)
        )
```

### `system_logs`

- **Row count:** 114
- **Primary key:** id

```sql
CREATE TABLE system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level TEXT,
            module_name TEXT,
            message TEXT
        )
```

### `system_settings`

- **Row count:** 1
- **Primary key:** id

```sql
CREATE TABLE system_settings (
                id INTEGER PRIMARY KEY,
                master_price_per_month REAL DEFAULT 500,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            , base_currency TEXT DEFAULT 'GHS', display_currency TEXT DEFAULT 'GHS', exchange_rate REAL DEFAULT 1.0, journal_source_of_truth INTEGER DEFAULT 1, legacy_mirror_mode TEXT DEFAULT 'mirror', enforce_document_approval INTEGER DEFAULT 0, inventory_cost_method TEXT DEFAULT 'weighted_average', bank_reconciliation_mode TEXT DEFAULT 'journal_plus_payment')
```

### `transactions`

- **Row count:** 0
- **Primary key:** id

```sql
CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            account TEXT NOT NULL,
            description TEXT,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            reference TEXT,
            created_by TEXT,
            branch_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
```

### `users`

- **Row count:** 3
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=CASCADE)

**Indexes:** `idx_users_user_id_runtime`, `idx_users_user_id`, `idx_users_login_key`

```sql
CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                full_name TEXT NOT NULL,
                login_key TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                status TEXT DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, password_hash TEXT, branch_id TEXT, user_id TEXT, security_question TEXT, security_answer TEXT, current_session_id TEXT, last_login_device TEXT,
                FOREIGN KEY (company_key) REFERENCES companies (key) ON DELETE CASCADE
            )
```

### `vouchers`

- **Row count:** 0
- **Primary key:** id

**Foreign keys:**
- `company_key` → `companies.key` (on_delete=NO ACTION)

**Indexes:** `idx_vouch_date`

```sql
CREATE TABLE vouchers 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      company_key TEXT, 
                      date TEXT, 
                      v_type TEXT, 
                      ledger TEXT, 
                      debit REAL DEFAULT 0.0, 
                      credit REAL DEFAULT 0.0, 
                      payment_method TEXT, 
                      narration TEXT, 
                      ref_no TEXT,
                      created_at DATETIME DEFAULT CURRENT_TIMESTAMP, balance_after REAL DEFAULT 0, reference_no TEXT, is_cleared INTEGER DEFAULT 1, created_by TEXT, status TEXT DEFAULT 'Active', branch_id TEXT, approval_status TEXT DEFAULT 'Draft', is_voided INTEGER DEFAULT 0, voided_at TIMESTAMP, voided_by TEXT, submitted_at TIMESTAMP, approved_at TIMESTAMP, approved_by TEXT, posted_entry_id INTEGER, last_journal_sync_at TIMESTAMP,
                      FOREIGN KEY (company_key) REFERENCES companies(key))
```


---

# SQLite-Specific Features (Code Scan)

**Audited at:** 2026-06-01 20:07:48 UTC

Repository-wide scan of `*.py` (excluding `__pycache__`, `.test-tmp`).

## PRAGMA (1442 occurrences)

- `.venv/Lib/site-packages/cachecontrol/controller.py:236: # Check the max-age pragma in the cache control header`
- `.venv/Lib/site-packages/cachetools/_cachedmethod.py:44: raise NotImplementedError()  # pragma: no cover`
- `.venv/Lib/site-packages/cachetools/_cachedmethod.py:47: raise NotImplementedError()  # pragma: no cover`
- `.venv/Lib/site-packages/cffi/cparser.py:433: elif decl.__class__.__name__ == 'Pragma':`
- `.venv/Lib/site-packages/cffi/cparser.py:434: # skip pragma, only in pycparser 2.15`
- `.venv/Lib/site-packages/cffi/cparser.py:437: "#pragma in cdef() are entirely ignored. "`
- `.venv/Lib/site-packages/cffi/cparser.py:440: "of CFFI if #pragma support gets added. Note that "`
- `.venv/Lib/site-packages/cffi/cparser.py:441: "'#pragma pack' needs to be replaced with the "`
- `.venv/Lib/site-packages/cffi/recompiler.py:418: prnt('#  pragma GCC visibility push(default)  /* for -fvisibility= */')`
- `.venv/Lib/site-packages/cffi/recompiler.py:464: prnt('#  pragma GCC visibility pop')`
- `.venv/Lib/site-packages/charset_normalizer/legacy.py:38: raise TypeError(  # pragma: nocover`
- `.venv/Lib/site-packages/dateutil/parser/_parser.py:432: if label not in [None, 'Y']:  # pragma: no cover`
- `.venv/Lib/site-packages/dateutil/parser/_parser.py:437: if label not in [None, 'Y']:  # pragma: no cover`
- `.venv/Lib/site-packages/google/api_core/_python_package_support.py:147: ):  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/_python_version_support.py:148: def _get_pypi_package_name(module_name):  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/_python_version_support.py:162: if module_name in module_to_distributions:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/_python_version_support.py:165: except Exception as e:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/bidi.py:274: if hasattr(call, "_wrapped"):  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/bidi.py:706: if self._thread.is_alive():  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/bidi_async.py:190: if hasattr(call, "_wrapped"):  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/client_info.py:35: except ImportError:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/exceptions.py:35: )  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/exceptions.py:43: except ImportError:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/exceptions.py:46: except ImportError:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/exceptions.py:58: if grpc is not None:  # pragma: no branch`
- `.venv/Lib/site-packages/google/api_core/exceptions.py:603: if not rpc_status:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/general_helpers.py:16: from functools import wraps  # noqa: F401 pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/grpc_helpers_async.py:107: async for response in self._call:  # pragma: no branch`
- `.venv/Lib/site-packages/google/api_core/operations_v1/abstract_operations_base_client.py:73: ):  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/operations_v1/operations_rest_client_async.py:32: except ImportError as e:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/operations_v1/transports/base.py:111: )  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/operations_v1/transports/base.py:119: host += ":443"  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/operations_v1/transports/rest_asyncio.py:25: except ImportError as e:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/api_core/rest_streaming_async.py:23: except ImportError as e:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/auth/__init__.py:35: class Python37DeprecationWarning(DeprecationWarning):  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/auth/__init__.py:51: if sys.version_info.major == 3 and sys.version_info.minor == 8:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/auth/__init__.py:53: elif sys.version_info.major == 3 and sys.version_info.minor == 9:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/auth/_default.py:32: if TYPE_CHECKING:  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/auth/_default.py:117: def _warn_about_generic_load_method(method_name):  # pragma: NO COVER`
- `.venv/Lib/site-packages/google/auth/_helpers.py:358: return sys.version_info > (3, 0)  # pragma: NO COVER`
- _… and 1402 more_

## AUTOINCREMENT (209 occurrences)

- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:32: table. SQLAlchemy considers ``IDENTITY`` within its default "autoincrement"`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:34: :paramref:`_schema.Column.autoincrement`.  This means that by default,`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:61: specify ``False`` for the :paramref:`_schema.Column.autoincrement` flag,`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:68: Column("id", Integer, primary_key=True, autoincrement=False),`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:74: ``True`` for the :paramref:`_schema.Column.autoincrement` flag on the desired`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:76: :paramref:`_schema.Column.autoincrement``
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:83: Column("id", Integer, primary_key=True, autoincrement=False),`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:84: Column("x", Integer, autoincrement=True),`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:118: ``autoincrement=True`` to enable the IDENTITY keyword, SQLAlchemy does not`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:135: the table by ensuring that ``autoincrement=False`` is set.`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:202: autoincrement=True,`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:208: restriction that ``autoincrement`` only applies to ``Integer`` is established`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:240: autoincrement=True,`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:2598: or column.autoincrement is True`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:2633: or column.autoincrement is True`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:3063: # This is actually used for autoincrement, where itentity is used that`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:3083: InsertmanyvaluesSentinelOpts.AUTOINCREMENT`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:3809: "autoincrement": is_identity is not None,`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/base.py:192: Column("id", Integer(), primary_key=True, autoincrement=True),`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/base.py:193: Column("other_id", Integer(), primary_key=True, autoincrement=False),`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/base.py:294: :paramref:`_schema.Column.autoincrement` argument of :class:`_schema.Column`.`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/base.py:302: Column("gid", Integer, primary_key=True, autoincrement=False),`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/reflection.py:326: col_kw["autoincrement"] = True`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/reflection.py:328: col_kw["autoincrement"] = False`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/base.py:61: Older version of Oracle Database had no "autoincrement" feature: SQLAlchemy`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/base.py:64: autoincrement*.  This is divergent with the majority of documentation examples`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/base.py:65: which assume the usage of an autoincrement-capable database.  To specify`
- `.venv/Lib/site-packages/sqlalchemy/dialects/postgresql/base.py:4171: autoincrement = False`
- `.venv/Lib/site-packages/sqlalchemy/dialects/postgresql/base.py:4176: autoincrement = True`
- `.venv/Lib/site-packages/sqlalchemy/dialects/postgresql/base.py:4195: "autoincrement": autoincrement or identity is not None,`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:51: Background on SQLite's autoincrement is at: https://sqlite.org/autoinc.html`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:59: * SQLite also has an explicit "AUTOINCREMENT" keyword, that is **not**`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:60: equivalent to the implicit autoincrement feature; this keyword is not`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:65: Using the AUTOINCREMENT Keyword`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:68: To specifically render the AUTOINCREMENT keyword on the primary key column`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:79: Allowing autoincrement behavior SQLAlchemy types other than Integer/INTEGER`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:86: of "integer" affinity.  However, **the SQLite autoincrement feature, whether`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:91: TABLE`` statement in order for the autoincrement behavior to be available.`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:970: the ``AUTOINCREMENT`` column parameter is used.   In order to return`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:1728: column.autoincrement is True`
- _… and 169 more_

## lastrowid (118 occurrences)

- `.venv/Lib/site-packages/sqlalchemy/connectors/asyncio.py:83: lastrowid: int`
- `.venv/Lib/site-packages/sqlalchemy/connectors/asyncio.py:185: def lastrowid(self) -> int:`
- `.venv/Lib/site-packages/sqlalchemy/connectors/asyncio.py:186: return self._cursor.lastrowid`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:297: ``SELECT scope_identity() AS lastrowid`` subsequent to an INSERT`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:300: the statement ``SELECT @@identity AS lastrowid```
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:1941: "SELECT scope_identity() AS lastrowid",`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mssql/base.py:1947: self.cursor, "SELECT @@identity AS lastrowid", (), self`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/base.py:551: place of the traditional approach of using ``cursor.lastrowid``, however`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/base.py:552: ``cursor.lastrowid`` is currently still preferred for simple single-statement`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/mariadbconnector.py:111: self._lastrowid = self.cursor.lastrowid`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/pyodbc.py:86: lastrowid = cursor.fetchone()[0]  # type: ignore[index]`
- `.venv/Lib/site-packages/sqlalchemy/dialects/mysql/pyodbc.py:88: return lastrowid  # type: ignore[no-any-return]`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/aiosqlite.py:132: "lastrowid",`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/aiosqlite.py:168: self.lastrowid = self.rowcount = -1`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/aiosqlite.py:174: self.lastrowid = _cursor.lastrowid`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/aiosqlite.py:193: self.lastrowid = _cursor.lastrowid`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:339: place of the traditional approach of using ``cursor.lastrowid``, however`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:340: ``cursor.lastrowid`` is currently still preferred for simple single-statement`
- `.venv/Lib/site-packages/sqlalchemy/engine/cursor.py:2177: def lastrowid(self) -> int:`
- `.venv/Lib/site-packages/sqlalchemy/engine/cursor.py:2178: """Return the 'lastrowid' accessor on the DBAPI cursor.`
- `.venv/Lib/site-packages/sqlalchemy/engine/default.py:1691: Used to fire off sequences, default phrases, and "select lastrowid"`
- `.venv/Lib/site-packages/sqlalchemy/engine/default.py:1812: """return self.cursor.lastrowid, or equivalent, after an INSERT.`
- `.venv/Lib/site-packages/sqlalchemy/engine/default.py:1824: of the lastrowid concept.  In these cases, it is called directly after`
- `.venv/Lib/site-packages/sqlalchemy/engine/default.py:1828: return self.cursor.lastrowid`
- `.venv/Lib/site-packages/sqlalchemy/engine/default.py:2046: lastrowid = self.get_lastrowid()`
- `.venv/Lib/site-packages/sqlalchemy/engine/default.py:2047: return [getter(lastrowid, self.compiled_parameters[0])]`
- `.venv/Lib/site-packages/sqlalchemy/engine/interfaces.py:196: lastrowid: int`
- `.venv/Lib/site-packages/sqlalchemy/engine/interfaces.py:1016: """for backends that support both a lastrowid and a RETURNING insert`
- `.venv/Lib/site-packages/sqlalchemy/engine/interfaces.py:1019: cursor.lastrowid tends to be more performant on most backends.`
- `.venv/Lib/site-packages/sqlalchemy/orm/persistence.py:1044: # so we have to post-fetch / use lastrowid anyway.`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:1301: """if True, and this in insert, use cursor.lastrowid to populate`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:2268: # apply type post processors to the lastrowid`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:2276: # #7998; honor a non-None user-passed parameter over lastrowid.`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:2277: # previously in the 1.4 series we weren't fetching lastrowid`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:2281: def _autoinc_getter(lastrowid, parameters):`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:2282: param_value = parameters.get(autoinc_key, lastrowid)`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:2286: # cursor.lastrowid for INSERT..ON CONFLICT so it`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:2290: # use lastrowid`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:2291: return lastrowid`
- `.venv/Lib/site-packages/sqlalchemy/sql/compiler.py:2301: def get(lastrowid, parameters):`
- _… and 78 more_

## sqlite_master (55 occurrences)

- `.venv/Lib/site-packages/pandas/io/sql.py:2849: sqlite_master`
- `.venv/Lib/site-packages/pandas/tests/io/test_sql.py:514: c = conn.execute("SELECT name FROM sqlite_master WHERE type='view'")`
- `.venv/Lib/site-packages/pandas/tests/io/test_sql.py:539: c = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")`
- `.venv/Lib/site-packages/pandas/tests/io/test_sql.py:3129: "SELECT * FROM sqlite_master WHERE type = 'index' "`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:982: "system" tables that are present in schemas such as ``sqlite_master``.`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:2301: "sqlite_master", "table", schema, sqlite_include_internal`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:2348: "sqlite_master", "view", schema, sqlite_include_internal`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:2357: master = f"{qschema}.sqlite_master"`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:2366: " (SELECT * FROM sqlite_master UNION ALL "`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:2374: "SELECT sql FROM sqlite_master WHERE name = ? "`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:2997: "sqlite_master",`
- `accounting_engine.py:494: "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",`
- `accounting_engine.py:664: "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",`
- `accounting_engine.py:727: "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",`
- `accounting_engine.py:806: "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",`
- `accounting_engine.py:1086: conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'transactions'").fetchone()`
- `accounting_engine.py:2695: "SELECT name FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",`
- `database.py:42: "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",`
- `database.py:391: rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()`
- `database.py:648: "sqlite_master_usage": "sqlite_master",`
- `database.py:704: for row in diagnostics_conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()`
- `database.py:763: for row in diagnostics_conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall():`
- `database.py:1349: conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)).fetchone()`
- `database.py:4039: SELECT name FROM sqlite_master`
- `database.py:4236: "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",`
- `database.py:4254: for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()`
- `database.py:4330: for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()`
- `database.py:4741: "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",`
- `database.py:6348: "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",`
- `database.py:6384: "SELECT name FROM sqlite_master WHERE type='table' AND name = 'journal_entries'"`
- `database.py:6406: for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()`
- `db_upgrade_safety.py:55: "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",`
- `erp_migrations.py:6: "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",`
- `inspect_candidate_dbs.py:21: cur.execute("SELECT name FROM sqlite_master WHERE type='table'")`
- `modules.py:2738: "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",`
- `rebuild_db.py:10: "SELECT name FROM sqlite_master WHERE type='table' AND name=?",`
- `scripts/run_migration_integrity_audit.py:60: "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",`
- `scripts/run_migration_integrity_audit.py:144: "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"`
- `scripts/run_postgres_5b11_audit.py:26: "sqlite_master": re.compile(r"\bsqlite_master\b"),`
- `scripts/run_postgres_5b11_audit.py:47: "sqlite_master": "information_schema.tables, pg_catalog",`
- _… and 15 more_

## INSERT OR IGNORE (33 occurrences)

- `database.py:645: "insert_or_ignore": "INSERT OR IGNORE",`
- `database.py:1336: return f"INSERT OR IGNORE INTO {table_name} ({column_sql}) VALUES ({placeholders})"`
- `database.py:4609: "INSERT OR IGNORE INTO schema_version (version, description) VALUES (?, ?)",`
- `database.py:4769: INSERT OR IGNORE INTO branch_type_catalog (`
- `database.py:4792: INSERT OR IGNORE INTO branch_type_module_defaults (`
- `database.py:4849: INSERT OR IGNORE INTO branch_module_grants (`
- `database.py:5440: INSERT OR IGNORE INTO users (`
- `database.py:6604: "INSERT OR IGNORE INTO system_settings (id, master_price_per_month, base_currency, display_currency, exchange_rate) VALU`
- `database.py:7109: "INSERT OR IGNORE INTO system_settings (id, master_price_per_month, base_currency, display_currency, exchange_rate) VALU`
- `database.py:8188: cursor.execute("INSERT OR IGNORE INTO maintenance_settings (id, is_active) VALUES (1, 0)")`
- `database.py:8361: "INSERT OR IGNORE INTO system_settings (id, master_price_per_month) VALUES (1, 500)"`
- `erp_migrations.py:26: conn.execute("INSERT OR IGNORE INTO system_settings (id) VALUES (1)")`
- `erp_migrations.py:62: "INSERT OR IGNORE INTO migration_history (migration_id, description) VALUES (?, ?)",`
- `financials.py:572: conn.execute("INSERT OR IGNORE INTO customers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')", (`
- `financials.py:589: conn.execute("INSERT OR IGNORE INTO suppliers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')", (`
- `financials.py:912: "INSERT OR IGNORE INTO customers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')",`
- `financials.py:951: "INSERT OR IGNORE INTO suppliers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')",`
- `fix_db.py:227: INSERT OR IGNORE INTO maintenance_settings (`
- `FORCE_RESET_DB.py:124: INSERT OR IGNORE INTO maintenance_settings (`
- `rebuild_db.py:174: INSERT OR IGNORE INTO maintenance_settings (`
- `scripts/run_postgres_5b11_audit.py:28: "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.I),`
- `scripts/run_postgres_5b11_audit.py:49: "INSERT OR IGNORE": "INSERT ... ON CONFLICT DO NOTHING (db_insert_ignore_sql)",`
- `scripts/run_postgres_5b11_audit.py:184: if feat in {"INSERT OR IGNORE", "INSERT OR REPLACE", "REPLACE INTO"}:`
- `scripts/run_postgres_5b11_audit.py:266: needs.append("Migration SQL uses literal `?` and `INSERT OR IGNORE` — must route through helpers for Postgres")`
- `scripts/run_postgres_5b11_audit.py:376: "| **Migrations** (`erp_migrations.py`) | **Yes** | **Hard blocker** | `sqlite_master`, `PRAGMA`, `INSERT OR IGNORE`, li`
- `scripts/run_postgres_5b11_audit.py:401: "- `INSERT OR IGNORE` in `financials.py` / `erp_migrations.py` (not using `db_insert_ignore_sql()`).",`
- `scripts/run_postgres_schema_compatibility_audit.py:33: "INSERT OR IGNORE": re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.I),`
- `scripts/run_postgres_schema_compatibility_audit.py:307: if len(sqlite_features.get("INSERT OR IGNORE", [])) > 5:`
- `scripts/run_postgres_schema_compatibility_audit.py:308: medium.append("INSERT OR IGNORE — partially covered by db_insert_ignore_sql(); audit all call sites")`
- `tests/test_database_backend_foundation.py:86: self.assertIn("INSERT OR IGNORE", sqlite_sql)`
- `tests/test_journal_entry_identity.py:133: INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name)`
- `tests/test_pos_return_identity.py:18: INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name)`
- `tests/test_pos_sale_identity.py:14: INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name)`

## ROWID (19 occurrences)

- `.venv/Lib/site-packages/psycopg2/__init__.py:65: BINARY, NUMBER, STRING, DATETIME, ROWID,`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/__init__.py:31: from .base import ROWID`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/__init__.py:72: "ROWID",`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/base.py:968: from .types import ROWID  # noqa`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/base.py:1053: "ROWID": ROWID,`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/base.py:1210: return "ROWID"`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/cx_oracle.py:751: class _OracleRowid(oracle.ROWID):`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/cx_oracle.py:753: return dbapi.ROWID`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/cx_oracle.py:1078: oracle.ROWID: _OracleRowid,`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/types.py:304: class ROWID(sqltypes.TypeEngine):`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/types.py:305: """Oracle Database ROWID type.`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/types.py:307: When used in a cast() or similar, generates ROWID.`
- `.venv/Lib/site-packages/sqlalchemy/dialects/oracle/types.py:311: __visit_name__ = "ROWID"`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:945: * ``WITHOUT ROWID``::`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:1880: table_options.append("WITHOUT ROWID")`
- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:2423: r"(?:\s*,?\s*(?:WITHOUT\s+ROWID|STRICT))*$"`
- `scripts/run_postgres_schema_compatibility_audit.py:41: "ROWID": re.compile(r"\bROWID\b", re.I),`
- `scripts/run_postgres_schema_compatibility_audit.py:179: if "WITHOUT ROWID" in info.create_sql.upper():`
- `scripts/run_postgres_schema_compatibility_audit.py:180: info.sqlite_only.append("WITHOUT ROWID")`

## WAL (13 occurrences)

- `.venv/Lib/site-packages/PIL/WalImageFile.py:5: # WAL file handling`
- `.venv/Lib/site-packages/PIL/WalImageFile.py:23: To open a WAL file, use the :py:func:`PIL.WalImageFile.open()` function instead.`
- `.venv/Lib/site-packages/PIL/WalImageFile.py:35: format = "WAL"`
- `.venv/Lib/site-packages/PIL/WalImageFile.py:67: Load texture from a Quake2 WAL texture file.`
- `.venv/Lib/site-packages/PIL/WalImageFile.py:72: :param filename: WAL file name, or an opened file handle.`
- `database.py:1609: "journal_mode": "WAL",`
- `database.py:2316: source_conn.execute("PRAGMA journal_mode = WAL;")`
- `database.py:4084: conn.execute("PRAGMA journal_mode = WAL;")`
- `database.py:4106: conn.execute("PRAGMA journal_mode = WAL;")`
- `scripts/run_postgres_5b11_audit.py:40: "WAL": re.compile(r"\bWAL\b"),`
- `scripts/run_postgres_5b11_audit.py:61: "WAL": "N/A (Postgres MVCC)",`
- `scripts/run_postgres_5b11_audit.py:192: if feat in {"WAL", "busy_timeout"}:`
- `scripts/run_postgres_schema_compatibility_audit.py:39: "WAL": re.compile(r"\bWAL\b"),`

## busy_timeout (10 occurrences)

- `app.py:2499: "backup_overlaps={overlaps} busy_timeout={timeout}ms longest_write={longest}s ({operation})".format(`
- `database.py:2314: source_conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")`
- `database.py:2318: snapshot_conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")`
- `database.py:4083: conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")`
- `database.py:4105: conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")`
- `migration_cleanup.py:90: conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")`
- `scripts/run_postgres_5b11_audit.py:41: "busy_timeout": re.compile(r"\bbusy_timeout\b", re.I),`
- `scripts/run_postgres_5b11_audit.py:62: "busy_timeout": "lock_timeout / statement_timeout",`
- `scripts/run_postgres_5b11_audit.py:192: if feat in {"WAL", "busy_timeout"}:`
- `scripts/run_postgres_schema_compatibility_audit.py:37: "busy_timeout": re.compile(r"\bbusy_timeout\b", re.I),`

## BEGIN IMMEDIATE (9 occurrences)

- `database.py:1508: self.conn.execute("BEGIN IMMEDIATE" if self.immediate else "BEGIN")`
- `scripts/run_postgres_5b11_audit.py:39: "BEGIN IMMEDIATE": re.compile(r"\bBEGIN\s+IMMEDIATE\b", re.I),`
- `scripts/run_postgres_5b11_audit.py:60: "BEGIN IMMEDIATE": "BEGIN (default READ COMMITTED)",`
- `scripts/run_postgres_5b11_audit.py:180: if feat in {"PRAGMA", "sqlite_master", "AUTOINCREMENT", "BEGIN IMMEDIATE"} and rel in PROD_APP:`
- `scripts/run_postgres_5b11_audit.py:427: ("Transaction portability", "YELLOW", `db_begin`/`commit` OK; `BEGIN IMMEDIATE` SQLite-only in lock wrapper"),`
- `scripts/run_postgres_schema_compatibility_audit.py:36: "BEGIN IMMEDIATE": re.compile(r"\bBEGIN\s+IMMEDIATE\b", re.I),`
- `tests/test_sqlite_concurrency.py:121: holder.execute("BEGIN IMMEDIATE")`
- `tests/test_sqlite_concurrency.py:138: raw_conn.execute("BEGIN IMMEDIATE")`
- `tests/test_sqlite_concurrency.py:183: writer.execute("BEGIN IMMEDIATE")`

## GLOB (9 occurrences)

- `scripts/plan_migration_data_cleanup.py:250: # Match Phase 5B.2 audit selection (includes GLOB false positives).`
- `scripts/plan_migration_data_cleanup.py:256: AND expiry_date NOT GLOB ?`
- `scripts/run_migration_integrity_audit.py:594: AND expiry_date NOT GLOB '????-??-??'`
- `scripts/run_postgres_5b11_audit.py:35: "GLOB": re.compile(r"\bGLOB\b"),`
- `scripts/run_postgres_5b11_audit.py:56: "GLOB": "~ regex or SIMILAR TO",`
- `scripts/run_postgres_5b11_audit.py:190: if feat == "GLOB":`
- `scripts/run_postgres_schema_compatibility_audit.py:40: "GLOB": re.compile(r"\bGLOB\b"),`
- `scripts/run_postgres_schema_compatibility_audit.py:309: if len(sqlite_features.get("GLOB", [])) > 3:`
- `scripts/run_postgres_schema_compatibility_audit.py:310: low.append("GLOB patterns — use Postgres ~ or SIMILAR TO / regex")`

## journal_mode (5 occurrences)

- `database.py:1609: "journal_mode": "WAL",`
- `database.py:2316: source_conn.execute("PRAGMA journal_mode = WAL;")`
- `database.py:4084: conn.execute("PRAGMA journal_mode = WAL;")`
- `database.py:4106: conn.execute("PRAGMA journal_mode = WAL;")`
- `scripts/run_postgres_schema_compatibility_audit.py:38: "journal_mode": re.compile(r"\bjournal_mode\b", re.I),`

## INSERT OR REPLACE (5 occurrences)

- `scripts/run_postgres_5b11_audit.py:29: "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.I),`
- `scripts/run_postgres_5b11_audit.py:50: "INSERT OR REPLACE": "INSERT ... ON CONFLICT DO UPDATE",`
- `scripts/run_postgres_5b11_audit.py:184: if feat in {"INSERT OR IGNORE", "INSERT OR REPLACE", "REPLACE INTO"}:`
- `scripts/run_postgres_schema_compatibility_audit.py:32: "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.I),`
- `seed_data.py:21: INSERT OR REPLACE INTO companies (`

## sqlite_sequence (4 occurrences)

- `.venv/Lib/site-packages/sqlalchemy/dialects/sqlite/base.py:969: such an object is the ``sqlite_sequence`` table that's generated when`
- `scripts/run_postgres_5b11_audit.py:42: "sqlite_sequence": re.compile(r"\bsqlite_sequence\b"),`
- `scripts/run_postgres_5b11_audit.py:63: "sqlite_sequence": "pg_get_serial_sequence()",`
- `scripts/run_postgres_schema_compatibility_audit.py:42: "sqlite_sequence": re.compile(r"\bsqlite_sequence\b"),`


---

# Query Compatibility Scan

**Audited at:** 2026-06-01 20:07:48 UTC

Scoped files: `database.py`, `modules.py`, `financials.py`, `app.py`, `accounting_engine.py`.

## Placeholder & Dialect Notes

- `database.db_param_placeholder()` returns `?` (SQLite) or `%s` (Postgres) when backend routing is active.
- `insert_returning_id_sql`, `fetch_inserted_row_id`, `db_insert_ignore_sql` exist in `database.py` (Phase 5B.1).
- Most application SQL still uses literal `?` — full migration requires systematic placeholder pass.

## `database.py`

### datetime_now_utc (20)
- `database.py:1479: "started_at": datetime.utcnow().isoformat(timespec="seconds"),`
- `database.py:1891: timestamp = timestamp or datetime.utcnow()`
- `database.py:1896: timestamp = timestamp or datetime.utcnow()`
- `database.py:1904: timestamp = timestamp or datetime.utcnow()`
- `database.py:2196: "timestamp": datetime.utcnow().isoformat(timespec="seconds"),`
- `database.py:2209: "timestamp": datetime.utcnow().isoformat(timespec="seconds"),`
- `database.py:2338: local_history_path = _build_local_history_backup_path(datetime.utcnow())`
- `database.py:2394: backup_timestamp = datetime.utcnow()`
- `database.py:2765: timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")`
- `database.py:3034: "restored_at": datetime.utcnow().isoformat(timespec="seconds"),`
- `database.py:3110: "created_at": datetime.utcnow().isoformat(timespec="seconds"),`
- `database.py:3399: derived_start_date = subscription_start_date or datetime.now().date().isoformat()`
- `database.py:3406: if parsed_end is not None and parsed_end.date() < datetime.now().date():`
- `database.py:3715: start_value = str(start_date or datetime.now().date().isoformat())`
- `database.py:3756: today = datetime.now().date()`
- `database.py:3813: today = _parse_datetime_like(as_of) or datetime.now()`
- `database.py:3909: today = datetime.now().date()`
- `database.py:4204: (f"{os.path.basename(DB_PATH)}::{int(datetime.now().timestamp())}",),`
- `database.py:5699: user_id_seed = f"{normalized_company_key}|{normalized_full_name}|{resolved_login_key}|{datetime.now().isoformat()}|{rand`
- `database.py:8889: event_id = f"AUD-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"`

### insert_or_ignore (11)
- `database.py:645: "insert_or_ignore": "INSERT OR IGNORE",`
- `database.py:1336: return f"INSERT OR IGNORE INTO {table_name} ({column_sql}) VALUES ({placeholders})"`
- `database.py:4609: "INSERT OR IGNORE INTO schema_version (version, description) VALUES (?, ?)",`
- `database.py:4769: INSERT OR IGNORE INTO branch_type_catalog (`
- `database.py:4792: INSERT OR IGNORE INTO branch_type_module_defaults (`
- `database.py:4849: INSERT OR IGNORE INTO branch_module_grants (`
- `database.py:5440: INSERT OR IGNORE INTO users (`
- `database.py:6604: "INSERT OR IGNORE INTO system_settings (id, master_price_per_month, base_currency, display_currency, exchange_rate) VALU`
- `database.py:7109: "INSERT OR IGNORE INTO system_settings (id, master_price_per_month, base_currency, display_currency, exchange_rate) VALU`
- `database.py:8188: cursor.execute("INSERT OR IGNORE INTO maintenance_settings (id, is_active) VALUES (1, 0)")`
- `database.py:8361: "INSERT OR IGNORE INTO system_settings (id, master_price_per_month) VALUES (1, 500)"`

### returning_clause (5)
- `database.py:1244: PostgreSQL callers should append RETURNING and read the returned row.`
- `database.py:1255: return f"{base_sql} RETURNING {returning_col}"`
- `database.py:1282: SQLite: cursor.lastrowid. PostgreSQL: first column from RETURNING clause (call fetchone via fetch_inserted_row_id).`
- `database.py:1295: Append RETURNING for PostgreSQL when the INSERT statement does not already include it.`
- `database.py:1305: return f"{normalized} RETURNING {returning_col}"`

### sqlite_placeholder_question (4)
- `database.py:1349: conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)).fetchone()`
- `database.py:5051: if not conn.execute("SELECT 1 FROM branches WHERE branch_id = ? LIMIT 1", (candidate,)).fetchone():`
- `database.py:5055: if not conn.execute("SELECT 1 FROM branches WHERE branch_id = ? LIMIT 1", (candidate,)).fetchone():`
- `database.py:8973: return conn.execute("SELECT * FROM companies WHERE key = ?", (company_key,)).fetchone()`

### on_conflict (3)
- `database.py:1335: return f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders}) ON CONFLICT{conflict_sql} DO NOTHING"`
- `database.py:3631: ON CONFLICT(plan_name) DO UPDATE SET`
- `database.py:3723: ON CONFLICT(company_key) DO UPDATE SET`

### integer_boolean (1)
- `database.py:5306: is_active=1,`

## `modules.py`

### datetime_now_utc (89)
- `modules.py:1301: new_expiry = datetime.now() + relativedelta(months=+int(duration_months))`
- `modules.py:1339: datetime.now().isoformat(timespec="seconds"),`
- `modules.py:1616: datetime.now().isoformat(timespec="seconds"),`
- `modules.py:1670: return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"`
- `modules.py:1842: subscription_expiry=datetime.now().date().isoformat(),`
- `modules.py:1848: subscription_start_date=datetime.now().date().isoformat(),`
- `modules.py:1849: subscription_end_date=datetime.now().date().isoformat(),`
- `modules.py:1872: activated_at = datetime.now().isoformat(timespec="seconds")`
- `modules.py:1900: datetime.now().isoformat(timespec="seconds"),`
- `modules.py:2118: paid_at = data.get("paid_at") or datetime.now().isoformat(timespec="seconds")`
- `modules.py:2119: verified_at = datetime.now().isoformat(timespec="seconds")`
- `modules.py:2570: now_ts = datetime.utcnow().timestamp()`
- `modules.py:2746: since_date = (datetime.now() - timedelta(days=30)).date().isoformat()`
- `modules.py:2818: seed = f"{company_key}|{staff_name.strip()}|{login_key.strip()}|{datetime.now().isoformat()}|{random.randint(1000,9999)}`
- `modules.py:2937: value = entry_date or datetime.now().date()`
- `modules.py:3901: value=datetime.now().date(),`
- `modules.py:3964: reference = f"JRN-{datetime.now().strftime('%Y%m%d%H%M%S')}"`
- `modules.py:4062: depreciation_date = pd.to_datetime(as_of_date or datetime.now().date()).date()`
- `modules.py:4481: tx_date = transaction_date.isoformat() if hasattr(transaction_date, "isoformat") else (transaction_date or datetime.now(`
- `modules.py:4625: (datetime.now().isoformat(timespec="seconds"), level, module_name, message),`
- `modules.py:4794: "sale_date": datetime.now().date().isoformat(),`
- `modules.py:4795: "sale_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),`
- `modules.py:5013: return f"SUS-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"`
- `modules.py:5025: "sale_date": str(st.session_state.get(f"pos_sale_date_{company_key}") or datetime.now().date()),`
- `modules.py:5448: return f"RET-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"`
- _… 64 more_

### sqlite_placeholder_question (6)
- `modules.py:4351: conn.execute("DELETE FROM invoice_lines WHERE invoice_id = ?", (int(invoice_id),))`
- `modules.py:8571: suppliers = conn.execute("SELECT id, name FROM suppliers WHERE company_key = ? ORDER BY name", (company_key,)).fetchall(`
- `modules.py:8965: row = conn.execute("SELECT contact_email, name FROM companies WHERE key = ? LIMIT 1", (company_key,)).fetchone()`
- `modules.py:10839: company = conn.execute("SELECT * FROM companies WHERE key = ?", (company_key,)).fetchone()`
- `modules.py:11114: company_row = conn.execute("SELECT name, barcode_input_source FROM companies WHERE key = ?", (company_key,)).fetchone()`
- `modules.py:13105: suppliers = conn.execute("SELECT id, name FROM suppliers WHERE company_key = ? ORDER BY name", (company_key,)).fetchall(`

### on_conflict (2)
- `modules.py:1757: ON CONFLICT(reference) DO UPDATE SET`
- `modules.py:3273: ON CONFLICT(company_key, period_label) DO UPDATE SET`

### integer_boolean (1)
- `modules.py:16898: is_active=1 if is_active else 0,`

## `financials.py`

### datetime_now_utc (14)
- `financials.py:246: start_date = st.date_input("Start Date", value=datetime.now().date().replace(day=1), key=f"{prefix}_start")`
- `financials.py:248: end_date = st.date_input("End Date", value=datetime.now().date(), key=f"{prefix}_end")`
- `financials.py:498: period_date = st.date_input("Accounting Period", value=datetime.now().date().replace(day=1), key=f"period_date_{company_`
- `financials.py:514: tx_date = st.date_input("Transaction Date", value=datetime.now().date(), key=f"manual_tx_date_{company_key}")`
- `financials.py:613: invoice_date = st.date_input("Invoice Date", value=datetime.now().date(), key=f"invoice_date_{company_key}")`
- `financials.py:643: (company_key, customer_id, f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}", invoice_date.isoformat(), invoice_date.isof`
- `financials.py:720: bill_date = st.date_input("Bill Date", value=datetime.now().date(), key=f"bill_date_{company_key}")`
- `financials.py:749: f"BILL-{datetime.now().strftime('%Y%m%d%H%M%S')}",`
- `financials.py:817: payment_date = st.date_input("Payment Date", value=datetime.now().date())`
- `financials.py:990: invoice_date = st.date_input("Invoice Date", value=datetime.now().date(), key=f"invoice_date_{company_key}")`
- `financials.py:1032: f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",`
- `financials.py:1139: payment_date = st.date_input("Payment Date", value=datetime.now().date(), key=f"receive_payment_date_{company_key}")`
- `financials.py:1252: payment_date = st.date_input("Payment Date", value=datetime.now().date(), key=f"supplier_payment_date_{company_key}")`
- `financials.py:1873: closing_date = st.date_input("Closing Date", value=datetime.now().date(), key=f"year_end_close_{company_key}")`

### sqlite_placeholder_question (6)
- `financials.py:179: row = conn.execute(f"SELECT id FROM {table_name} WHERE company_key = ? AND name = ?", (company_key, name)).fetchone()`
- `financials.py:601: customers = [row[0] for row in conn.execute("SELECT name FROM customers WHERE company_key = ? ORDER BY name", (company_k`
- `financials.py:709: suppliers = [row[0] for row in conn.execute("SELECT name FROM suppliers WHERE company_key = ? ORDER BY name", (company_k`
- `financials.py:977: customers = [row[0] for row in conn.execute("SELECT name FROM customers WHERE company_key = ? ORDER BY name", (company_k`
- `financials.py:1131: customers = [row[0] for row in conn.execute("SELECT name FROM customers WHERE company_key = ? ORDER BY name", (company_k`
- `financials.py:1244: suppliers = [row[0] for row in conn.execute("SELECT name FROM suppliers WHERE company_key = ? ORDER BY name", (company_k`

### insert_or_ignore (4)
- `financials.py:572: conn.execute("INSERT OR IGNORE INTO customers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')", (`
- `financials.py:589: conn.execute("INSERT OR IGNORE INTO suppliers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')", (`
- `financials.py:912: "INSERT OR IGNORE INTO customers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')",`
- `financials.py:951: "INSERT OR IGNORE INTO suppliers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')",`

## `app.py`

### datetime_now_utc (12)
- `app.py:358: st.session_state.last_activity = datetime.now()`
- `app.py:542: last_activity = st.session_state.get('last_activity', datetime.now())`
- `app.py:543: if datetime.now() - last_activity > timedelta(minutes=SESSION_TIMEOUT):`
- `app.py:553: st.session_state.last_activity = datetime.now()`
- `app.py:576: st.session_state.last_activity = datetime.now()`
- `app.py:901: new_expiry = datetime.now() + relativedelta(months=+months)`
- `app.py:922: st.session_state.start_time = datetime.now()`
- `app.py:953: 'Date': [f"{(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')}" for i in range(90)],`
- `app.py:1287: current_month = datetime.now().strftime('%Y-%m')`
- `app.py:1435: month_sales = get_month_sales_total(company_key, year_month=datetime.now().strftime('%Y-%m'), conn=conn)`
- `app.py:2723: end_date=datetime.now().date(),`
- `app.py:3469: default_expiry = datetime.now().date()`

### sqlite_placeholder_question (3)
- `app.py:620: conn.execute(f"DELETE FROM {table_name} WHERE company_key = ?", (company_key,))`
- `app.py:623: conn.execute("DELETE FROM companies WHERE key = ?", (company_key,))`
- `app.py:2069: branches = conn.execute("SELECT branch_id, branch_name FROM branches WHERE company_key = ? ORDER BY branch_name", (user[`

### on_conflict (1)
- `app.py:3084: ON CONFLICT(id) DO UPDATE SET`

### integer_boolean (1)
- `app.py:3277: "UPDATE maintenance_settings SET maintenance_date=?, is_active=0, message=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",`

## `accounting_engine.py`

### datetime_now_utc (14)
- `accounting_engine.py:241: current_period = _period_label_for_date(as_of_date or datetime.now().date())`
- `accounting_engine.py:1459: reversal_date = _resolve_date(reversal_date or datetime.now().date())`
- `accounting_engine.py:1466: reference = f"REV-{entry_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"`
- `accounting_engine.py:1520: reversal_date=voided_at or datetime.now().date(),`
- `accounting_engine.py:1525: voided_timestamp = _resolve_date(voided_at or datetime.now().date())`
- `accounting_engine.py:1713: today = _resolve_date(run_date or datetime.now().date())`
- `accounting_engine.py:1736: entry_date = _resolve_date(run_date or row["next_run_date"] or datetime.now().date())`
- `accounting_engine.py:1742: reference=f"REC-{row['id']}-{datetime.now().strftime('%Y%m%d%H%M%S')}",`
- `accounting_engine.py:1755: (datetime.now().isoformat(), next_run.isoformat(), row["id"]),`
- `accounting_engine.py:1897: period_value = str(year_month or datetime.now().strftime("%Y-%m")).strip()`
- `accounting_engine.py:1964: current_month = datetime.now().strftime("%Y-%m")`
- `accounting_engine.py:2243: report_date = pd.Timestamp(as_of_date or datetime.now().date())`
- `accounting_engine.py:2433: report_date = pd.Timestamp(as_of_date or datetime.now().date())`
- `accounting_engine.py:2730: report_end_date = end_date or datetime.now().date()`

### sqlite_placeholder_question (7)
- `accounting_engine.py:1449: original = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()`
- `accounting_engine.py:1461: for row in conn.execute("SELECT account_id, debit, credit FROM journal_lines WHERE entry_id = ?", (entry_id,)):`
- `accounting_engine.py:1511: original = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()`
- `accounting_engine.py:1555: payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()`
- `accounting_engine.py:1560: invoice = conn.execute("SELECT amount FROM invoices WHERE id = ?", (invoice_id,)).fetchone()`
- `accounting_engine.py:1567: bill = conn.execute("SELECT amount FROM bills WHERE id = ?", (bill_id,)).fetchone()`
- `accounting_engine.py:1648: row = conn.execute("SELECT * FROM bank_accounts WHERE id = ?", (account_id,)).fetchone()`

### integer_boolean (3)
- `accounting_engine.py:1527: "UPDATE journal_entries SET is_voided = 1, voided_at = ?, voided_by = ?, approval_status = 'Voided' WHERE id = ?",`
- `accounting_engine.py:1714: query = "SELECT * FROM recurring_transactions WHERE is_active = 1 AND date(next_run_date) <= date(?)"`
- `accounting_engine.py:1717: query = "SELECT * FROM recurring_transactions WHERE is_active = 1 AND company_key = ? AND date(next_run_date) <= date(?)`
