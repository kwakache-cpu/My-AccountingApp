# SQLite/PostgreSQL Schema Reconciliation Plan

Phase: 5B.15D

Planning only. No data migration, SQLite modification, PostgreSQL write, schema regeneration, runtime enablement, commit, or push was performed.

## Summary

- Original blocker columns reviewed: 47
- ADD_COLUMN: 47
- IGNORE: 0
- COMPUTED: 0
- MERGED: 0
- Columns required for POS: 47
- Columns required for accounting: 18
- Columns required for audit trail: 24
- Columns required for reporting: 47
- PostgreSQL columns that must be added or confirmed present: 47
- Columns that may safely be ignored: 0
- Columns requiring manual review before row-copy dry run: 0

## Current Artifact Status

The 47 blockers from Phase 5B.15B were live SQLite columns that the previous parser reported as missing from generated PostgreSQL DDL. After quote-safe parsing of `DEFAULT ''` column definitions, the current `reports/postgres_generated_schema.sql` contains all 47 columns.

Reconciliation decision: keep these columns in PostgreSQL. They preserve POS receipts, refunds, suspended carts, cashier closeout evidence, accounting posting references, audit timestamps, and reporting dimensions. Do not ignore, merge, or compute them during migration planning.

## Category Summary

| Category | Count | Recommendation |
|---|---:|---|
| ADD_COLUMN | 47 | Required target schema fields; current generated schema should retain them. |
| IGNORE | 0 | No blocker column is safe to drop from migration scope. |
| COMPUTED | 0 | Even mathematically derivable values are historical/audit values and should be preserved as stored columns. |
| MERGED | 0 | No blocker column has a complete equivalent target column to merge into. |

## Detailed Reconciliation

| Table | Column | SQLite type | Intended business purpose | PostgreSQL action | Required for | Recommendation |
|---|---|---|---|---|---|---|
| `cashier_closings` | `cashier` | TEXT NOT NULL | Identifies the cashier responsible for a drawer closeout. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT NOT NULL`; needed for cashier accountability and closeout reporting. |
| `cashier_closings` | `closed_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | Timestamp when a drawer closeout was completed. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP`; preserve historical closeout timing. |
| `cashier_closings` | `closed_by` | TEXT | User/operator who finalized the closeout. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT`; required for audit attribution. |
| `cashier_closings` | `closing_date` | TEXT NOT NULL | Business date for cashier closeout. | ADD_COLUMN | POS, accounting, reporting | Keep as `TEXT NOT NULL` for now; date normalization can be reviewed later. |
| `cashier_closings` | `counted_cash` | REAL DEFAULT 0 | Actual cash counted during closeout. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; required for reconciliation. |
| `cashier_closings` | `difference` | REAL DEFAULT 0 | Stored cash variance between expected and counted cash. | ADD_COLUMN | POS, accounting, audit trail, reporting | Preserve stored value as `NUMERIC(18,2) DEFAULT 0`; do not compute only, because historical overrides matter. |
| `cashier_closings` | `expected_cash` | REAL DEFAULT 0 | Expected cash from POS activity. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; required to validate drawer differences. |
| `cashier_closings` | `notes` | TEXT | Closeout notes and exception context. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT`; user-entered evidence should be migrated. |
| `pos_returns` | `item_id` | INTEGER | Inventory item identifier for returned item. | ADD_COLUMN | POS, accounting, reporting | Keep as `INTEGER`; later FK/type alignment can follow inventory identity decision. |
| `pos_returns` | `item_name` | TEXT NOT NULL | Item description captured on return. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT NOT NULL`; preserves historical item label even if inventory changes. |
| `pos_returns` | `original_sale_reference` | TEXT NOT NULL | Original POS sale being reversed. | ADD_COLUMN | POS, accounting, audit trail, reporting | Keep as `TEXT NOT NULL`; required for traceability to original sale. |
| `pos_returns` | `pos_sale_line_id` | INTEGER | Original POS sale line being returned. | ADD_COLUMN | POS, accounting, audit trail, reporting | Keep as `INTEGER`; supports line-level return traceability. |
| `pos_returns` | `posted_entry_id` | INTEGER | Accounting journal entry generated for the return. | ADD_COLUMN | accounting, audit trail, reporting | Keep as `INTEGER`; required to link return to accounting posting. |
| `pos_returns` | `qty_returned` | REAL DEFAULT 0 | Quantity returned. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; quantity precision can be revisited later. |
| `pos_returns` | `reason` | TEXT | Return reason entered by user. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT`; preserves return rationale. |
| `pos_returns` | `refund_amount` | REAL DEFAULT 0 | Refund amount issued. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; required for cash/customer refund reconciliation. |
| `pos_returns` | `refund_method` | TEXT | Refund payment method. | ADD_COLUMN | POS, accounting, reporting | Keep as `TEXT`; supports payment-method reporting. |
| `pos_returns` | `return_reference` | TEXT NOT NULL | Unique return reference. | ADD_COLUMN | POS, accounting, audit trail, reporting | Keep as `TEXT NOT NULL`; required for idempotent return identity. |
| `pos_returns` | `returned_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | Return timestamp. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP`; preserve return timing. |
| `pos_returns` | `returned_by` | TEXT | User/cashier processing return. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT`; required for accountability. |
| `pos_returns` | `status` | TEXT DEFAULT 'Posted' | Posting/workflow status for return. | ADD_COLUMN | POS, accounting, reporting | Keep as `TEXT DEFAULT 'Posted'`; required to distinguish posted/pending returns. |
| `pos_returns` | `unit_price` | REAL DEFAULT 0 | Unit price at return time. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; preserves historical price basis. |
| `pos_sales` | `amount_tendered` | REAL DEFAULT 0 | Customer tendered amount. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; required for payment reconciliation. |
| `pos_sales` | `cashier` | TEXT | Cashier who processed sale. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT`; required for cashier reports. |
| `pos_sales` | `change_due` | REAL DEFAULT 0 | Change due to customer. | ADD_COLUMN | POS, accounting, reporting | Preserve as `NUMERIC(18,2) DEFAULT 0`; do not compute only, because stored tendering record is audit evidence. |
| `pos_sales` | `cogs_posted_entry_id` | INTEGER | COGS journal entry generated for sale. | ADD_COLUMN | accounting, audit trail, reporting | Keep as `INTEGER`; required for accounting traceability. |
| `pos_sales` | `created_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | System creation timestamp for sale record. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP`; preserve source creation time. |
| `pos_sales` | `customer_id` | INTEGER | Optional customer linked to POS sale. | ADD_COLUMN | POS, accounting, reporting | Keep as `INTEGER`; supports customer sales analysis. |
| `pos_sales` | `discount_total` | REAL DEFAULT 0 | Total discount applied to sale. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; needed for revenue analysis. |
| `pos_sales` | `grand_total` | REAL DEFAULT 0 | Final sale total. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; core sale amount. |
| `pos_sales` | `last_journal_sync_at` | TIMESTAMP | Last accounting sync timestamp. | ADD_COLUMN | accounting, audit trail, reporting | Keep as `TIMESTAMPTZ`; required to audit posting synchronization. |
| `pos_sales` | `payment_method` | TEXT | Payment method used for sale. | ADD_COLUMN | POS, accounting, reporting | Keep as `TEXT`; required for tender reports. |
| `pos_sales` | `posted_entry_id` | INTEGER | Revenue journal entry generated for sale. | ADD_COLUMN | accounting, audit trail, reporting | Keep as `INTEGER`; required for accounting traceability. |
| `pos_sales` | `receipt_number` | TEXT NOT NULL | Customer-facing receipt number. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT NOT NULL`; required for receipt lookup. |
| `pos_sales` | `sale_date` | TEXT NOT NULL | Business sale date. | ADD_COLUMN | POS, accounting, reporting | Keep as `TEXT NOT NULL` for now; date normalization can be planned later. |
| `pos_sales` | `sale_datetime` | TEXT | Sale date/time as captured by POS workflow. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT`; later conversion to timestamp requires data audit. |
| `pos_sales` | `sale_reference` | TEXT NOT NULL | Stable sale reference. | ADD_COLUMN | POS, accounting, audit trail, reporting | Keep as `TEXT NOT NULL`; required for idempotency and returns. |
| `pos_sales` | `subtotal` | REAL DEFAULT 0 | Sale subtotal before tax/discount. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; needed for sales breakdown. |
| `pos_sales` | `tax_total` | REAL DEFAULT 0 | Tax total on sale. | ADD_COLUMN | POS, accounting, reporting | Keep as `NUMERIC(18,2) DEFAULT 0`; needed for tax reporting. |
| `pos_suspended_sales` | `cancelled_at` | TIMESTAMP | Timestamp when suspended sale was cancelled. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TIMESTAMPTZ`; preserves suspended-cart lifecycle. |
| `pos_suspended_sales` | `cart_json` | TEXT NOT NULL | Serialized suspended cart contents. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT NOT NULL`; JSONB conversion requires caller audit. |
| `pos_suspended_sales` | `cashier` | TEXT | Cashier who suspended/resumed cart. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT`; supports accountability. |
| `pos_suspended_sales` | `created_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | Suspended cart creation timestamp. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP`. |
| `pos_suspended_sales` | `note` | TEXT | User note for suspended cart. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT`; preserve operator context. |
| `pos_suspended_sales` | `resumed_at` | TIMESTAMP | Timestamp when cart was resumed. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TIMESTAMPTZ`; preserves lifecycle evidence. |
| `pos_suspended_sales` | `status` | TEXT DEFAULT 'suspended' | Suspended sale state. | ADD_COLUMN | POS, reporting | Keep as `TEXT DEFAULT 'suspended'`; required for queue/status reporting. |
| `pos_suspended_sales` | `suspend_reference` | TEXT NOT NULL | Stable suspended-sale reference. | ADD_COLUMN | POS, audit trail, reporting | Keep as `TEXT NOT NULL`; required for lookup/resume flow. |

## Required-By Views

### POS

All 47 columns are required for POS workflows: cashier closeout, sale receipts, returns/refunds, suspended carts, payment methods, tender/change tracking, and item-level return context.

### Accounting

Accounting-required columns: `cashier_closings.closing_date`, `cashier_closings.expected_cash`, `cashier_closings.counted_cash`, `cashier_closings.difference`, `pos_returns.original_sale_reference`, `pos_returns.pos_sale_line_id`, `pos_returns.posted_entry_id`, `pos_returns.qty_returned`, `pos_returns.refund_amount`, `pos_returns.return_reference`, `pos_returns.status`, `pos_returns.unit_price`, `pos_sales.amount_tendered`, `pos_sales.change_due`, `pos_sales.cogs_posted_entry_id`, `pos_sales.posted_entry_id`, `pos_sales.grand_total`, `pos_sales.payment_method`.

### Audit Trail

Audit-required columns include cashier/operator fields, references, timestamps, status fields, closeout notes, suspended cart lifecycle timestamps, and accounting posting IDs. None should be ignored.

### Reporting

All 47 columns are reporting-relevant because they support POS sales summaries, refunds, tender reports, drawer variance reports, cashier accountability, and suspended cart monitoring.

## Final Recommendation

- Add or retain all 47 columns in the PostgreSQL schema.
- Ignore 0 columns.
- Compute 0 columns during migration; preserve historical stored values.
- Merge 0 columns into existing targets.
- Manual review count: 0 for action selection, but staging must validate that the deployed PostgreSQL schema matches the current generated artifact.

The row-copy dry run can begin only after the reconciled PostgreSQL schema is applied to staging and post-deployment validation confirms these 47 columns exist. The current generated schema artifact already includes them, but this phase did not regenerate schema or write to PostgreSQL.
