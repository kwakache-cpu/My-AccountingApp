# Program B P0 Sprint 1 — POS Posting Permission Hardening

**Date:** 2026-07-07  
**Scope:** Permission propagation and POS-scoped posting gates — **no POS rewrite, no amount/inventory changes**

---

## Certification Finding Addressed

| Gap | Resolution |
|-----|------------|
| POS `post_journal_entry` omitted `user_role` | Both POS Sale and POS COGS posts in `_pos_checkout_write` now pass `user_role=role` |
| Accounting engine skipped role check when `user_role` resolved to `None` | `user_role` explicitly passed; POS-scoped permission via `sell_pos` / `process_pos_return` |
| Cashier could post GL without `post_accounting_document` | **Fixed:** Cashier must have `sell_pos` for `source_module="POS"`; cannot post manual journals |

---

## Discovery — POS Posting Paths

| Path | Location | `user_role` before | After |
|------|----------|-------------------|-------|
| **POS Sale journal** | `show_pos` → `_pos_checkout_write` → `post_journal_entry` | Missing | `user_role=role` |
| **POS COGS journal** | Same checkout write path | Missing | `user_role=role` |
| **POS Return journal** | `_process_pos_return` → `post_journal_entry` | Already present | Unchanged |

No other `source_table="pos_sales"` posting paths found in `modules.py`.

---

## Exact Permission Gap

1. `modules.post_journal_entry` is an alias for `accounting_engine.post_accounting_impact`.
2. `_assert_posting_role_allowed(user_role)` **returns immediately when `user_role is None`** — no check.
3. `_resolve_effective_posting_role(None, created_by)` returns `None` when `created_by` (e.g. `Cashier`) lacks `post_accounting_document`.
4. Result: **effective role `None` → check skipped → Cashier posts journals without any permission validation.**

---

## Exact Fix

### `modules.py` — `_pos_checkout_write`

Added `user_role=role` to:

- POS Sale `post_journal_entry` (`source_type="POS Sale"`)
- POS COGS `post_journal_entry` (`source_type="POS COGS"`)

### `accounting_engine.py` — scoped posting permission

Extended `_assert_posting_role_allowed(user_role, source_module=None)`:

| `source_module` | Required permission (alternative to `post_accounting_document`) |
|-----------------|------------------------------------------------------------------|
| `POS` | `sell_pos` |
| `POS Return` | `process_pos_return` |

`post_accounting_impact` forwards `source_module` to the assertion.

**Segregation preserved:** Cashier/Staff/Sales Officer can post **only** POS-scoped documents, not manual journals or bills.

---

## Files Changed

| File | Change |
|------|--------|
| `accounting_engine.py` | POS-scoped permission in `_assert_posting_role_allowed`; forward `source_module` |
| `modules.py` | `user_role=role` on POS Sale + COGS posts |
| `tests/test_program_b_p0_pos_posting_permission.py` | New sprint regression suite |
| `reports/program_a_top_100_recommendations.md` | Item #1 marked complete |
| `reports/program_b_p0_sprint_1_pos_posting_permission.md` | This report |

**Not changed:** POS UI, cart logic, inventory decrement SQL, journal line amounts, COGS calculation.

---

## Tests Run

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_program_b_p0_pos_posting_permission.py" -v
python -m unittest discover -s tests -p "test_regression_lockdown.py" -v
python tests/run_regression_tests.py
git diff --check
```

---

## Remaining Notes

- Non-POS paths that omit `user_role` still rely on `_resolve_effective_posting_role` fallback — out of scope for this sprint.
- `process_pos_return` already passed `user_role`; now benefits from `POS Return` scoped permission explicitly.

---

*Program B P0 Sprint 1 — no commit in this pass.*
