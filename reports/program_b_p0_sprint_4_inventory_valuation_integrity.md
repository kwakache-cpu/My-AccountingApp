# Program B P0 Sprint 4 — Inventory Valuation and General Ledger Integrity

**Branch:** `program-b-p0-sprint-4-inventory-valuation-integrity`  
**Date:** 2026-08-04  
**Depends on:** Program B P0 Sprint 3 (`apply_inventory_quantity_change` movement integrity)

---

## Verified costing behavior

| Finding | Evidence |
|---------|----------|
| Authoritative cost field | `inventory.cost_price` |
| Method key | `last_unit_cost_field` |
| What it is | Mutable last unit cost overwritten on receive when `unit_cost > 0` |
| What it is not | FIFO, LIFO, weighted average, moving average, or standard cost |
| Dead fallback | `average_cost` is referenced in invoice stock effects but **no column is created** in schema |

Centralized resolvers:

- `parse_inventory_cost_value()`
- `resolve_inventory_unit_cost()`
- `INVENTORY_COSTING_METHOD` metadata in `accounting_engine.py`

**Future costing-policy sprint recommended** before changing method. Do not silently switch to weighted average.

---

## Valuation authority

Operational subledger value:

```
SUM(quantity_on_hand × resolved unit cost)
```

where resolved unit cost prefers `cost_price`.

GL Inventory balance:

```
get_account_total(..., "Inventory", balance_side="debit")
```

These are independent. Bills can debit Inventory GL without qty; receives can change qty without journals.

---

## Reconciliation method

`reconcile_inventory_subledger_to_gl()` returns:

- `subledger_value`
- `gl_inventory_balance`
- `difference`
- `status`: `MATCHED` | `REVIEW` | `CRITICAL`
- missing-cost / negative-stock / unvalued-movement counts
- item-level detail

**Never** auto-posts correcting journals.  
**Never** auto-modifies item costs.

UI: **Inventory Valuation** page (Inventory nav), gated to accounting/admin roles + `view_reports`.

Cache keys include `company_key`, `branch_id`, `as_of_date`, `active_backend`.

---

## Safeguards added

1. Safe numeric/string/null cost parsing — no crash on blanks or currency strings.
2. Missing cost flagged for review; established zero-cost COGS skip preserved.
3. Invoice/POS paths resolve cost through `resolve_inventory_unit_cost`.
4. Quantity-only movements with missing cost marked `unvalued=true`.
5. **Transfer** movements are quantity-only — no artificial COGS / Opening Equity P&L.
6. Negative stock detected in valuation snapshot.
7. Sprint 3 movement integrity helper preserved.

---

## Risks deliberately deferred (P1)

- Bill vs receive value auto-link / auto-receive
- True weighted-average or FIFO costing policy
- Historical as-of quantity layers (valuation uses live inventory balances)
- Dedicated damage/write-off expense accounts (still often hit COGS historically)
- Dual-leg inter-branch transfer clearing
- Automatic correcting journals

---

## Live UAT requirements

1. Accountant opens **Inventory Valuation** with stock and opening GL — expect MATCHED when funded equally.
2. Post Inventory Purchase bill without receive — expect REVIEW/CRITICAL drift.
3. Receive stock with unit cost — confirm cost_price updates and valuation changes.
4. POS sale — confirm COGS uses cost_price; missing cost does not crash.
5. Record Transfer reason — confirm no profit/loss journal.
6. Cashier cannot open Inventory Valuation.
7. Empty company shows helpful empty state.

---

## Tests

`tests/test_program_b_p0_inventory_valuation_integrity.py`
