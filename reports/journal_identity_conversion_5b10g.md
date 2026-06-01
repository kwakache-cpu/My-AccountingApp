# Phase 5B.10G — Journal Posting Identity Conversion

**Status:** Completed (identity retrieval only)  
**Target:** `post_journal_entry` in `accounting_engine.py`  
**No commit / no push / no migration**

## Task 1 — Current flow (before change)

### Entry point

`post_journal_entry(company_key, date, description, reference, lines, created_by, …, conn=None)`

When `conn is None`, the function wraps itself in `execute_write_transaction` (POS/payroll/depreciation operation names) and re-invokes with a transaction connection.

### Preconditions (unchanged)

1. `lines` required; each line validated (account_id, debit/credit rules, active/posting accounts).
2. `_period_locked` — blocks locked accounting periods.
3. `_assert_source_document_postable` — source document must be postable.
4. `_assert_no_duplicate_source_posting` — controlled tables (`invoices`, `bills`, `payments`, `pos_sales`, etc.) cannot double-post same `source_id` (with branch/type rules for POS).

### Balance validation

`total_debit` must equal `total_credit` (rounded to 2 dp) or `ValueError` is raised **before** any INSERT.

### `journal_entries` INSERT

Single header row with company, date, description, **reference**, branch_id, party FKs, source traceability fields, approval_status.

### Identity (converted in 5B.10G)

- **Before:** `entry_id = int(cursor.lastrowid)`
- **After:** `entry_id = get_inserted_id(cursor)` with `ensure_insert_sql_returning` on header INSERT only

### Post-insert steps (unchanged)

1. `UPDATE journal_entries` — sets `document_number` from reference, document_type, source_document_* , posted_at/by.
2. `INSERT journal_lines` — one row per normalized line, FK `entry_id`.
3. `_sync_source_document_posting` when source_table + source_id present.
4. `_mirror_legacy_transactions` / `_legacy_voucher_insert` when enabled.
5. `conn.commit()` if caller did not pass `conn`; else caller commits.

### Rollback

On any exception after INSERT starts: if `owns_connection`, `conn.rollback()`; connection closed in `finally` when owned.

Callers passing `conn` expect atomic document + journal in one transaction.

### Reference / voucher

- `reference` stored on header as provided (not derived from lastrowid).
- `document_number` COALESCE from reference on UPDATE — numbering logic unchanged.

## Conversion scope

| Changed | Not changed |
|---------|-------------|
| `journal_entries` INSERT wrapped with `ensure_insert_sql_returning` | `journal_lines` INSERT SQL |
| `get_inserted_id(cursor)` for `entry_id` | Balance, duplicate checks, mirrors, commits |

## Expected inventory outcome

- **Zero** raw `lastrowid` in production app paths (`modules.py`, `accounting_engine.py`, `financials.py`).
- Remaining hits: tests, audit scripts, `database.py` helper docs, report strings.
