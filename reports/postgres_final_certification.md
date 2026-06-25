# PostgreSQL Final Certification

**Generated at:** 2026-06-25 13:29 UTC  
**Branch:** `phase-5b16a-postgres-final-certification`  
**Scope:** write-path certification inventory, critical workflow tracing, and additive certification tests.  
**Policy:** no commits, pushes, merges, data cleanup, redesign, or business-logic removal.

## Certification Summary

The ERP has strong PostgreSQL foundations for schema, read runtime, row compatibility, identity retrieval, and reporting reads. Write-path certification is not fully green yet. Critical identity paths generally use `ensure_insert_sql_returning()` and `get_inserted_id()`, but several write workflows still execute raw `conn.execute()` / `cursor.execute()` DML with SQLite-style placeholders and SQLite-specific transaction or schema assumptions.

**Overall write-path certification status:** **PostgreSQL warning**

Production PostgreSQL cutover should remain blocked until the warning/unsafe write paths below are either converted to portable helpers or proven safe through staged PostgreSQL write tests.

## Classification Key

| Classification | Meaning |
|---|---|
| PostgreSQL safe | Uses portable identity helpers, portable write helpers, backend-aware transaction helpers, or has strong staged PostgreSQL evidence. |
| PostgreSQL warning | Works in SQLite and appears structurally connected, but still uses raw write SQL, raw placeholders, UI-only transaction assumptions, or lacks staged PostgreSQL write evidence. |
| PostgreSQL unsafe | Uses SQLite-only transaction, DDL, introspection, conflict, or identity behavior that is expected to fail or misbehave on PostgreSQL unless guarded. |

## Write Path Inventory

### Safe Patterns Found

| Pattern | Classification | Evidence |
|---|---|---|
| `ensure_insert_sql_returning()` + `get_inserted_id()` on identity inserts | PostgreSQL safe | Used by POS sale, stock movement, invoice, bill, payment, payroll, fixed asset, journal entry, and other critical inserts. |
| `execute_portable_write()` | PostgreSQL safe | Central helper in `database.py`; used in selected branch/user/audit/migration cleanup paths. |
| `execute_db_write_transaction()` | PostgreSQL safe | Backend-aware transaction wrapper; SQLite uses the lock-safe path and PostgreSQL uses standard commit/rollback handling. |
| `log_audit_action()` portable insert path | PostgreSQL safe | Uses `execute_portable_write()` for audit inserts and portable column detection. |
| PostgreSQL runtime startup guard | PostgreSQL safe | Existing reports show SQLite bootstrap blocked under PostgreSQL runtime. |

### Warning Patterns Found

| Pattern | Classification | Evidence / Risk |
|---|---|---|
| Raw `conn.execute()` DML in `modules.py` | PostgreSQL warning | POS checkout, POS returns, invoice lines, invoice/bill/payment flows, payroll records, fixed asset updates, company/staff settings, and banking contain raw INSERT/UPDATE/DELETE calls. |
| Raw `conn.execute()` DML in `accounting_engine.py` | PostgreSQL warning | Journal writer uses portable identity for `journal_entries`, but raw UPDATE and `journal_lines` INSERT calls still rely on connection placeholder conversion. |
| Raw `INSERT OR IGNORE` in customer/supplier paths | PostgreSQL warning | Customer/supplier quick-add paths in `financials.py` and seed/setup paths require PostgreSQL conflict handling validation. |
| POS checkout inventory decrement | PostgreSQL warning | Direct `UPDATE inventory SET qty = qty - ?` is functionally connected but not routed through `execute_portable_write()` and does not record outbound `stock_movements`. |
| Payroll records insert | PostgreSQL warning | Payroll main identity insert is portable; `payroll_records` insert remains raw DML. |
| Fixed asset depreciation run | PostgreSQL warning | Posts journal and updates asset book value, but journal linkage is by reference rather than `source_table='fixed_assets'` / `source_id`. |
| Staff/company setup writes | PostgreSQL warning | Permission gates and audit logging exist, but raw DML remains in user/company update paths. |
| Direct `execute_write_transaction()` callers | PostgreSQL warning | `post_journal_entry()` without an existing connection and branch admin helpers can still reach the SQLite transaction wrapper; hot UI paths often pass an existing connection, but the latent API path needs hardening. |

### Unsafe or SQLite-Specific Patterns Found

| Pattern | Classification | Evidence / Risk |
|---|---|---|
| SQLite DDL/self-heal paths (`PRAGMA`, `AUTOINCREMENT`, `sqlite_master`) | PostgreSQL unsafe unless guarded | Still present in schema/bootstrap helpers; intended to be skipped under PostgreSQL runtime. |
| `BEGIN IMMEDIATE` transaction mode | PostgreSQL unsafe unless routed through `execute_db_write_transaction()` | Present in `SQLiteWriteTransaction`; direct `execute_write_transaction()` calls remain unsafe for PostgreSQL-managed connections. |
| `last_insert_rowid` | PostgreSQL unsafe | No active production use found in critical app modules; helper/reporting references only. |
| Direct `cursor.lastrowid` | PostgreSQL unsafe outside helper | Remaining direct usage appears in tests or helper implementation. Critical production identity paths use `get_inserted_id()`. |
| `INSERT OR IGNORE` | PostgreSQL unsafe unless translated | Must use backend-aware conflict SQL (`db_insert_ignore_sql()` or equivalent) before PostgreSQL write cutover. |

## Critical Workflow Certification

### POS Sale

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | `show_pos()` collects cart, payment method, credit customer, discounts, branch, cashier, and receipt fields. |
| Database write | `process_pos_sale()` validates stock, directly updates `inventory.qty`, calls `_persist_pos_sale()` to insert `pos_sales` and `pos_sale_lines`. |
| Journal creation | Revenue journal uses `post_journal_entry(source_table='pos_sales', source_type='POS Sale')`; COGS journal uses `source_type='POS COGS'`. |
| Balance updates | On-credit sales pass `customer_id` and record customer ledger impact; cash/card sales hit Cash/Bank/Mobile Money instead. |
| Audit logging | Logs POS sale and discount approvals through `log_audit_action()` / `log_system_event()`. |
| Certification result | Identity path is portable, but checkout inventory writes and line inserts are raw DML; POS branch cleanup warnings remain. |

### Inventory Adjustment

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | Inventory movement helpers normalize movement type, quantity, branch, reference, and reason. |
| Database write | `_insert_stock_movement_record()` uses `ensure_insert_sql_returning()` and `get_inserted_id()` for `stock_movements`; other inventory adjustments/imports still contain per-row raw writes. |
| Journal creation | Inventory purchase/import and invoice/POS stock effects can create journal impact through posting helpers; not every adjustment path posts GL impact automatically. |
| Balance updates | Inventory quantity/book value updates feed stock, COGS, and inventory account balances when journal impact is posted. |
| Audit logging | Inventory import and movement flows log system/audit events in selected paths. |
| Certification result | Stock movement identity is safe; complete inventory adjustment write certification remains warning due to raw DML and mixed GL behavior. |

### Customer Invoice

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | Sales/invoice forms collect customer, amount, tax fields, invoice items, status, posting state, date, and description. |
| Database write | Invoice insert uses `ensure_insert_sql_returning()` and `get_inserted_id()`; invoice line save deletes/reinserts lines via raw DML. |
| Journal creation | Posted invoices call `build_sales_tax_journal_lines()` and `post_journal_entry(source_table='invoices')`; inventory item invoices can add COGS lines. |
| Balance updates | AR balance derives from journal lines when invoice is unpaid/pending; paid invoices debit Cash. |
| Audit logging | Sales/invoice records log audit events after commit in UI flows. |
| Certification result | Identity and accounting chain are connected; invoice line and stock effect writes still need PostgreSQL write validation. |

### Customer Payment

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | Payment pages collect customer, amount, method, reference, date, and posting state. |
| Database write | Payment insert uses `ensure_insert_sql_returning()` and `get_inserted_id()` in primary paths. |
| Journal creation | Posted customer receipts debit Cash/Bank/Mobile Money and credit Accounts Receivable through `post_journal_entry(source_table='payments')`. |
| Balance updates | Customer balance falls through AR control-account journal lines. Existing posting tests verify AR reduces to zero. |
| Audit logging | Customer receipt posting logs audit and system events. |
| Certification result | Functional chain is strong, but PostgreSQL write certification remains warning until payment inserts/allocation/audit writes are staged against PostgreSQL. |

### Supplier Bill

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | Bill forms collect supplier, amount, VAT, purchase classification, payment method, date, status, posting state, and description. |
| Database write | Bill insert uses `ensure_insert_sql_returning()` and `get_inserted_id()`; line/detail writes still need certification. |
| Journal creation | Posted bills call `build_purchase_journal_lines()` and `post_journal_entry(source_table='bills')`. |
| Balance updates | Supplier/AP balance derives from Accounts Payable journal lines when not immediately paid. |
| Audit logging | Bill workflows log audit/user events in UI paths. |
| Certification result | Workflow is connected and has AP balance tests, but raw write paths remain warning for PostgreSQL. |

### Supplier Payment

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | Supplier payment pages collect supplier, amount, method, reference, date, and posting state. |
| Database write | Payment insert uses portable identity helpers in primary paths. |
| Journal creation | Posted supplier payments debit Accounts Payable and credit Cash/Bank/Mobile Money through `post_journal_entry(source_table='payments')`. |
| Balance updates | Supplier balance falls through AP control-account journal lines. Existing posting tests verify AP reduces to zero. |
| Audit logging | Supplier payment posting logs audit events. |
| Certification result | Functional chain is strong, but payment write/allocation/audit paths still need PostgreSQL staging certification. |

### Journal Entry

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | Manual journal and document workflows provide date, reference, source document, branch, party, and balanced lines. |
| Database write | `post_journal_entry()` uses `execute_write_transaction()` when it owns the connection, `ensure_insert_sql_returning()` for `journal_entries`, and `get_inserted_id()`. The owned-connection transaction wrapper remains a PostgreSQL warning until moved to `execute_db_write_transaction()`. |
| Journal creation | Inserts `journal_entries`, then `journal_lines`, then syncs controlled source documents. |
| Balance updates | All reporting, AR/AP, cash, inventory, payroll, asset, and tax balances derive from journal lines. |
| Audit logging | `post_accounting_impact()` logs posting-engine events and blocked/permission-denied posting attempts. UI workflows add domain audit logs. |
| Certification result | Identity and source sync are strong; raw `journal_lines` insert, metadata UPDATE, and the owned-connection `execute_write_transaction()` path still need PostgreSQL write execution certification. |

### Payroll Posting

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | Payroll page collects employee, salary, allowances, deductions, PAYE, SSNIT, month/year, payment status, and method. |
| Database write | Payroll row uses `ensure_insert_sql_returning()` and `get_inserted_id()`; `payroll_records` insert is raw DML. |
| Journal creation | `_build_payroll_journal_lines()` creates Salary Expense and payroll/tax liability/cash lines; posted through `post_journal_entry(source_table='payroll')`. |
| Balance updates | Payroll expense, cash, and payroll liability accounts update through journal lines. |
| Audit logging | Payroll UI logs `Payroll Entry Added`. |
| Certification result | Additive tests now verify payroll source-document journal linkage; full UI/write certification remains warning. |

### Depreciation Posting

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | Fixed asset page triggers straight-line depreciation for active depreciable assets. |
| Database write | `run_straight_line_depreciation()` updates `fixed_assets.accumulated_depreciation`, `book_value`, and `last_depreciation_date`. |
| Journal creation | Depreciation posts Dr Depreciation Expense / Cr Accumulated Depreciation through `create_journal_entry()`. |
| Balance updates | Fixed asset net book value and accumulated depreciation update through both asset table and journal lines. |
| Audit logging | Depreciation run logs through journal/accounting paths, but source-document audit linkage is weaker than other workflows. |
| Certification result | Warning: depreciation journal is reference-traceable but does not currently certify `source_table='fixed_assets'` / `source_id` linkage. |

### User/Role Changes

**Classification:** PostgreSQL warning

| Stage | Trace |
|---|---|
| Input | System Configuration, branch deployment, staff management, branch user, and manager flows collect user/branch/role/status fields with permission checks. |
| Database write | Some branch/user helpers use `execute_portable_write()`; company setup and staff creation still include raw INSERT/UPDATE DML. |
| Journal creation | Not applicable. User/role changes should not create accounting journals. |
| Balance updates | Not applicable. |
| Audit logging | Staff creation, client settings, branch manager, and permission-denied flows log audit/security events. |
| Certification result | Permission/audit posture is strong, but PostgreSQL user/role write certification remains warning due to raw DML in UI paths. |

## Certification Tests Added

Added `tests/test_postgres_final_certification.py` with coverage for:

- Critical write paths using portable identity helpers.
- Journal writer transaction/source-sync contract.
- Payroll source-document posting linkage.
- Fixed asset source-document posting linkage.
- Depreciation posting remaining a warning until fixed-asset source linkage is certified.
- Certification report contract and required workflow headings/classifications.

## Final Certification Decision

**Decision:** **NOT YET PRODUCTION CERTIFIED**

The application is ready for final staged PostgreSQL write certification, but not for production PostgreSQL cutover. The next work should be targeted hardening and staged write-path tests, not feature work or redesign.

## Required Before Production Approval

1. Convert or certify raw DML in POS checkout, invoice/bill/payment flows, payroll records, fixed asset depreciation, and staff/company setup paths.
2. Replace `INSERT OR IGNORE` paths with backend-aware conflict handling.
3. Replace direct owned-connection `execute_write_transaction()` use in PostgreSQL-capable write paths with `execute_db_write_transaction()`.
4. Confirm `journal_lines` inserts and source-document sync execute correctly on real PostgreSQL.
5. Add or run staged PostgreSQL write tests for every critical workflow listed above.
6. Resolve or formally accept migration cleanup warnings before final cutover.
