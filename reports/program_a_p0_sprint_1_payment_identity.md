# Program A P0 Sprint 1 — Payment Subledger Identity Hardening

**Date:** 2026-07-04  
**Scope:** P0-1, P0-2 (payment `customer_id` / `supplier_id` persistence)  
**Status:** Complete (not committed)

---

## Root Cause

Payment rows in the `payments` table already had `customer_id` and `supplier_id` columns in base DDL, but several write paths omitted them on INSERT:

| Path | File | Issue |
|------|------|-------|
| Customer Receipt page | `financials.py` `show_receive_payment_page` | INSERT omitted `customer_id`; journal entry had it |
| Supplier Payment page | `financials.py` `show_supplier_payment_page` | INSERT omitted `supplier_id`; journal entry had it |
| Legacy tabbed Payments form | `financials.py` tabbed AR/AP UI | No party picker — INSERT stores NULL (unchanged; not a regression) |
| Banking Customer/Supplier Payment | `modules.py` `show_banking` | Already correct |

Impact: AR/AP subledger reconciliation drift, weak payment traceability by stable party ID, migration cleanup and future 360° profiles unreliable when keyed only on journal linkage.

---

## Schema Changes

No new tables. Additive integrity only:

1. **`ensure_schema_integrity`** — added `customer_id` / `supplier_id` to `payments` critical column map (`database.py`).
2. **`ensure_payments_party_identity_schema_integrity(conn)`** — idempotent `ALTER TABLE ... ADD COLUMN` (SQLite) or `ADD COLUMN IF NOT EXISTS` (PostgreSQL). Wired into `_run_lightweight_integrity_checks()` at startup only.

No DDL in UI render paths.

---

## Write Paths Fixed

| Location | Change |
|----------|--------|
| `financials.show_receive_payment_page` | INSERT now includes `customer_id` (and explicit `supplier_id=NULL`) |
| `financials.show_supplier_payment_page` | INSERT now includes `supplier_id` (and explicit `customer_id=NULL`) |
| `financials` tabbed Payments form | INSERT includes explicit NULL party columns (no party UI — legacy limitation preserved) |
| `modules.show_banking` | No change — already persisted party IDs |

Preserved: `company_key`, `branch_id` (via journal), source document linkage, amount, date, method, reference, approval/posting behavior.

---

## Read Paths Hardened

1. **`resolve_payment_party_identity(conn, payment_row)`** (`database.py`) — prefers `payments.customer_id` / `payments.supplier_id`; falls back to journal, `posted_entry_id`, or invoice/bill FK when unambiguous.
2. **`_payments_list_sql()` / `_payments_list_params()`** (`financials.py`) — payment list queries (tabbed, customer receipt, supplier payment pages) now expose resolved party IDs and names via `COALESCE(payment, journal, invoice/bill)`.
3. **AR/AP aging** — unchanged; continues to use GL balances via `journal_entries.customer_id` / `supplier_id`. Legacy payments without payment-row IDs still appear via journal linkage and legacy/unallocated buckets.

---

## Backfill Behavior

**`backfill_payments_party_identity(conn, company_key=None, dry_run=False)`** (`database.py`):

- Targets `Customer Receipt` rows with NULL `customer_id` and `Supplier Payment` rows with NULL `supplier_id`.
- Collects candidate party IDs from: linked journal entries (`source_table='payments'`), `posted_entry_id`, and `invoice_id` / `bill_id` document FKs.
- **Updates** when exactly one distinct candidate ID is found.
- **Skips (ambiguous)** when multiple distinct IDs are found — counted in `customer_skipped_ambiguous` / `supplier_skipped_ambiguous`.
- **Unmatched** when no candidate — counted separately.
- Idempotent: re-run produces zero updates after first successful pass.
- Non-destructive: never deletes rows or overwrites non-NULL party IDs.
- **Not auto-run on every startup** — helper available for admin/ops and tests; schema ensure runs at startup.

---

## Tests

**File:** `tests/test_program_a_p0_payment_subledger_identity.py`

| Test | Proves |
|------|--------|
| `test_customer_payment_stores_customer_id` | Customer receipt INSERT persists `customer_id` |
| `test_supplier_payment_stores_supplier_id` | Supplier payment INSERT persists `supplier_id` |
| `test_resolve_prefers_payment_row_customer_id` | Read path prefers payment row over journal |
| `test_resolve_falls_back_to_journal_for_legacy_payment` | Legacy rows resolve via journal |
| `test_legacy_payment_without_payment_id_still_appears_in_ar_aging` | AR aging not empty for legacy rows |
| `test_backfill_populates_customer_id_from_journal` | Backfill idempotent success |
| `test_backfill_skips_ambiguous_customer_matches` | Ambiguous backfill skipped safely |
| `test_payments_party_identity_schema_integrity_is_idempotent` | Schema ensure idempotent |
| `test_postgres_schema_ensure_uses_if_not_exists` | PostgreSQL portable DDL |
| `test_financials_payment_pages_have_no_ddl` | No UI DDL |
| `test_startup_integrity_includes_payments_party_columns` | Columns present after startup |

---

## Validation Commands Run

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_program_a_p0_payment_subledger_identity.py" -v
python -m unittest discover -s tests -p "test_regression_lockdown.py" -v
python tests/run_regression_tests.py
git diff --check
git status
git diff --stat
```

*(Results recorded below after execution.)*

| Command | Result |
|---------|--------|
| `py_compile` (6 modules) | ✅ Pass |
| `test_program_a_p0_payment_subledger_identity.py` | ✅ 11/11 OK |
| `test_regression_lockdown.py` | ✅ 26/26 OK |
| `run_regression_tests.py` | ✅ 717/717 OK |
| `git diff --check` | ✅ Pass (no conflict markers) |

---

## Remaining Risks

| Risk | Mitigation |
|------|------------|
| Legacy tabbed Payments form has no party picker | Documented; backfill cannot infer party without journal/document linkage |
| Payments with conflicting journal customer/supplier IDs | Backfill skips; manual review via migration cleanup |
| Name-only legacy rows with no journal party ID | Unmatched in backfill; AR/AP aging still works via GL if journal posted correctly |
| Operational backfill not scheduled | Helper exists; ops can run during maintenance window |

---

## Files Changed

- `database.py` — schema ensure, resolve, backfill helpers; critical column map; startup wiring
- `financials.py` — write-path INSERT fixes; enriched payment list queries
- `tests/test_program_a_p0_payment_subledger_identity.py` — new
- `reports/program_a_priority_roadmap.md` — P0-1/P0-2 marked complete
- `reports/program_a_p0_sprint_1_payment_identity.md` — this document

**Not changed:** posting logic in `accounting_engine.py`, banking path in `modules.py`, regression lockdown rules.
