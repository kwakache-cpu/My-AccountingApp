# Program A P0 Sprint 3 — Bill vs Inventory Receive Clarity

**Date:** 2026-07-06  
**Scope:** User-facing workflow clarity on Create Bill — **no accounting posting changes, no inventory rewrites**

---

## Audit Finding Addressed

| Gap | Resolution |
|-----|------------|
| Users assume Create Bill receives stock | Persistent help text + inventory-classification warning on Create Bill page |
| Payment status "Received" confused with stock receipt | Caption clarifies payment settled ≠ stock received |
| Bill/inventory separation undocumented in-product | Next-step guidance to Inventory → Receive Stock |
| No regression tests for bill vs receive boundary | `tests/test_program_a_p0_bill_inventory_receive_clarity.py` |

---

## Discovery Summary

### Pages & routes

| Surface | Location | Entry |
|---------|----------|-------|
| **Create Bill** | `modules.show_create_bill_page` | Sidebar → Finance → Create Bill; `app.py` route `Create Bill` |
| **Inventory Receive Stock** | `modules.show_inventory` (Stock In/Out tab) | Sidebar → Inventory → Receive Stock form |
| **Legacy AP quick bill** | `modules.show_accounts_payable_page` | Separate legacy path (not changed this sprint) |
| **Tabbed purchases** | `financials.show_invoice_manager(doc_type=Purchase)` | Alternate bill UI (not changed this sprint) |

### Bill posting logic

| Step | Function | Effect |
|------|----------|--------|
| Insert bill | `show_create_bill_page` → `bills` + `bill_lines` | Supplier liability record |
| Build journal | `build_purchase_journal_lines` | Debit Inventory / Expense / Fixed Assets; credit AP or payment account |
| Post | `post_journal_entry` | GL + supplier subledger when Posted |

### Current behavior (confirmed)

| Question | Answer |
|----------|--------|
| Posts to Accounts Payable? | **Yes** — when Payment Status is Pending and bill is Posted |
| Posts to Inventory (GL)? | **Yes** — when Purchase Classification is Inventory Purchase |
| Posts to Expense? | **Yes** — when classification is Expense Purchase |
| Creates `stock_movements` row? | **No** — Create Bill path does not call `_receive_inventory_stock` or `_insert_stock_movement_record` |
| Updates `inventory.qty`? | **No** — physical stock unchanged by bill alone |
| Separate receive path? | **Yes** — Inventory → Stock In/Out → Receive Stock (`_receive_inventory_stock`) |

### Existing tests (prior coverage)

| Test file | Coverage |
|-----------|----------|
| `tests/test_posting_workflow.py` | Posted bill → AP journal |
| `tests/test_erp_functional_certification.py` | Supplier bill + payment AP lifecycle |
| `tests/test_inventory_movements.py` | Receive stock → movement + qty |
| `tests/test_erp_cross_module_workflows.py` | Manual stock movement + bill journal are separate steps |

---

## User-Facing Clarification Added

On **Create Bill** (`show_create_bill_page`):

1. **Always visible (info + caption):**
   - "Creating a bill records supplier liability/accounting. It does not receive stock unless inventory receiving is completed."
   - "Use Inventory → Receive Stock / Purchases to update quantities."

2. **When Purchase Classification = Inventory Purchase (in-form captions):**
   - "Inventory quantity will not increase from this bill alone."
   - Repeat of next-step guidance to Receive Stock.

3. **Payment Status caption:**
   - "Received means payment is settled — not that stock was received."

Constants live in `modules.py`: `CREATE_BILL_ACCOUNTING_NOTICE`, `CREATE_BILL_INVENTORY_QTY_NOTICE`, `CREATE_BILL_INVENTORY_NEXT_STEP`, `CREATE_BILL_PAYMENT_STATUS_NOTICE`.

---

## Files Changed

| File | Change |
|------|--------|
| `modules.py` | Workflow notice constants, `_render_create_bill_workflow_guidance()`, Create Bill UI captions |
| `tests/test_program_a_p0_bill_inventory_receive_clarity.py` | New sprint regression suite |
| `reports/program_a_priority_roadmap.md` | P0-6 marked complete |
| `reports/program_a_p0_sprint_3_bill_inventory_receive_clarity.md` | This report |

**Not changed:** `accounting_engine.py`, `build_purchase_journal_lines` logic, inventory receive implementation, database schema.

---

## Tests Run

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_program_a_p0_bill_inventory_receive_clarity.py" -v
python -m unittest discover -s tests -p "test_regression_lockdown.py" -v
python tests/run_regression_tests.py
git diff --check
```

---

## Remaining P1 Purchase-to-Pay Work

| ID | Item | Notes |
|----|------|-------|
| P1-1 | Optional receive-on-post for inventory-classified bills | Link bill lines to inventory SKUs; prompt receive or auto-movement when explicitly chosen |
| P1-2 | Unified stock movement ledger for POS | POS sale decrements should write `stock_movements` |
| P1-3 | Valued inventory receive prompts GL posting | Align physical receive with inventory GL when unit cost supplied |
| P2-6 | Consolidate duplicate invoice/bill UI paths | `financials.show_invoice_manager` vs dedicated Create Bill page |

No stock movements were invented in this sprint — bill and receive remain intentionally separate workflows.

---

*Program A P0 Sprint 3 — bill vs inventory receive clarity. No commit in this pass.*
