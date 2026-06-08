# SQLite/PostgreSQL Schema Mismatch Review

Phase: 5B.15B

Review only. No data migration, PostgreSQL write, PostgreSQL runtime enablement, SQLite behavior change, or production deployment was attempted.

## Summary

- Total mismatches: 47
- Safe/expected mismatches: 0
- Manual review count: 0
- Blocker count: 47

## Mismatch Categories

- SAFE_TYPE_WIDENING: 0
- EXPECTED_POSTGRES_IDENTITY: 0
- EXPECTED_TIMESTAMP_MAPPING: 0
- BOOLEAN_CANDIDATE: 0
- MONEY_NUMERIC_MAPPING: 0
- NEEDS_MANUAL_REVIEW: 0
- BLOCKER: 47

## Detailed Review

| Table | Column | SQLite | PostgreSQL | Classification | Risk | Recommended handling |
|---|---|---|---|---|---|---|
| `cashier_closings` | `cashier` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `cashier_closings` | `closed_at` | TIMESTAMP; default=CURRENT_TIMESTAMP; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `cashier_closings` | `closed_by` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `cashier_closings` | `closing_date` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `cashier_closings` | `counted_cash` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `cashier_closings` | `difference` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `cashier_closings` | `expected_cash` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `cashier_closings` | `notes` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `item_id` | INTEGER; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `item_name` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `original_sale_reference` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `pos_sale_line_id` | INTEGER; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `posted_entry_id` | INTEGER; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `qty_returned` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `reason` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `refund_amount` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `refund_method` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `return_reference` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `returned_at` | TIMESTAMP; default=CURRENT_TIMESTAMP; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `returned_by` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `status` | TEXT; default='Posted'; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_returns` | `unit_price` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `amount_tendered` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `cashier` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `change_due` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `cogs_posted_entry_id` | INTEGER; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `created_at` | TIMESTAMP; default=CURRENT_TIMESTAMP; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `customer_id` | INTEGER; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `discount_total` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `grand_total` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `last_journal_sync_at` | TIMESTAMP; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `payment_method` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `posted_entry_id` | INTEGER; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `receipt_number` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `sale_date` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `sale_datetime` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `sale_reference` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `subtotal` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_sales` | `tax_total` | REAL; default=0; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_suspended_sales` | `cancelled_at` | TIMESTAMP; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_suspended_sales` | `cart_json` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_suspended_sales` | `cashier` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_suspended_sales` | `created_at` | TIMESTAMP; default=CURRENT_TIMESTAMP; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_suspended_sales` | `note` | TEXT; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_suspended_sales` | `resumed_at` | TIMESTAMP; default=none; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_suspended_sales` | `status` | TEXT; default='suspended'; NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |
| `pos_suspended_sales` | `suspend_reference` | TEXT; default=none; NOT NULL | missing; default=missing; missing | BLOCKER | High | Reconcile the generated PostgreSQL schema before row-copy dry run; otherwise this SQLite column has no target. |

## Recommendation

- Data migration must not proceed to dry-run row mapping until all BLOCKER items above are reconciled in the PostgreSQL schema plan.
- Do not execute real row copy, PostgreSQL writes, runtime activation, or production deployment in this phase.
