# Phase 5B.10C — Payments Identity Conversion

**Status:** Completed (identity retrieval only)  
**No commit / no push / no migration**

## Task 2 — Payment flow summary (before change)

### `allocate_payment` — `accounting_engine.py`

| Item | Detail |
|------|--------|
| **Table** | `payment_allocations` |
| **lastrowid** | Return allocation row id |
| **Downstream** | Callers use returned id; links `payment_id` to invoice/bill |
| **Journal** | None in this function |
| **Transaction** | Owns `conn` when `conn=None`; commit/rollback in function |
| **Rollback** | `conn.rollback()` on exception when owns connection |

### `show_banking` — `modules.py` (~13330)

| Item | Detail |
|------|--------|
| **Table** | `payments` |
| **lastrowid** | `payment_id` for `BANK-{id}` fallback reference, `post_journal_entry` (`payment_id`, `source_id`), audit |
| **Downstream** | All banking payment types (customer, supplier, owner, loan, transfer) |
| **Journal** | `post_journal_entry` per payment type (unchanged) |
| **Transaction** | UI `conn`; `rollback` on balance failure |
| **Rollback** | Explicit before return on insufficient balance |

### Financials payment pages — `financials.py`

| Function | Table | Prior identity | Journal |
|----------|-------|----------------|---------|
| `show_invoice_manager` (Payments tab) | `payments` | `SELECT last_insert_rowid()` | Optional `post_journal_entry` when Posted |
| `show_receive_payment_page` | `payments` | `SELECT last_insert_rowid()` | Same |
| `show_supplier_payment_page` | `payments` | `SELECT last_insert_rowid()` | Same |

## Conversions applied

All sites now use `ensure_insert_sql_returning()` + `get_inserted_id()` (SQLite unchanged; Postgres gets `RETURNING id`).

No changes to amounts, allocations validation, journal lines, balances, branch_id, or audit payloads.

## Identity sites removed

| # | File | Function | Table |
|---|------|----------|-------|
| 1 | `accounting_engine.py` | `allocate_payment` | `payment_allocations` |
| 2 | `modules.py` | `show_banking` | `payments` |
| 3 | `financials.py` | `show_invoice_manager` | `payments` |
| 4 | `financials.py` | `show_receive_payment_page` | `payments` |
| 5 | `financials.py` | `show_supplier_payment_page` | `payments` |

**Not touched:** `post_journal_entry`, POS, payroll, fixed assets, bills/invoices numbering, stock movements.
