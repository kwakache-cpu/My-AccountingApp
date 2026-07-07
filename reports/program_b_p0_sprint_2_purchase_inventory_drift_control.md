# Program B P0 Sprint 2 — Purchase / Inventory Drift Control

**Date:** 2026-07-07  
**Scope:** Visibility, status computation, and drift monitoring — **no auto-receive, no auto-GL from receive, no posting amount changes**

---

## Certification Risk Addressed

| Risk | Control added |
|------|----------------|
| Bill debits Inventory GL without qty change | Drift monitor + status on Create Bill |
| Receive updates qty without bill link | Reference linking + warnings on Receive Stock |
| Silent mismatch undiscoverable | Unmatched bills/receipts lists |
| Operators confuse payment vs stock receipt | Prior Sprint 3 text retained; drift status added |

---

## Drift Risks Found (Audit)

| Path | GL / Accounting | Physical Stock | Link |
|------|-----------------|----------------|------|
| **Create Bill** (Inventory Purchase, Posted) | Debits Inventory GL via `build_purchase_journal_lines` | **No qty change** | None to `stock_movements` |
| **Inventory Receive** (`_receive_inventory_stock`) | **No journal** | Updates `inventory.qty` + `stock_movements` | Optional via `reference` = `bill_number` |
| **Legacy AP bill** | Same as Create Bill | No qty | Not in scope this sprint |

**Linking rule (computed, not enforced):** `stock_movements.reference` (Receive Stock) matches `bills.bill_number` (Inventory Purchase, Posted).

---

## Controls Added

### Status computation (`compute_purchase_inventory_status`)

| Field | Meaning |
|-------|---------|
| Bill Posted to GL | `approval_status == Posted` |
| Inventory GL Posted | Posted + Inventory Purchase classification |
| Stock Received | Matching Receive Stock movement for bill number |
| Quantity Updated | Same as Stock Received (this sprint) |

### UI surfaces

| Surface | Addition |
|---------|----------|
| **Create Bill** | Drift Monitor expander; inventory-classification warning; post-success drift alert |
| **Inventory → Receive Stock** | Bill link notice; drift monitor; reference preview warnings |

### Reports / lists (in-product)

- **Bills posted to Inventory GL but not received** — `_fetch_posted_inventory_bills_missing_stock`
- **Stock received without linked bill** — `_fetch_stock_receipts_missing_bill_link`

### Explicitly NOT added (per sprint rules)

- Auto stock movement from bill post
- Auto journal from stock receive
- Full purchasing module / PO workflow

---

## Files Changed

| File | Change |
|------|--------|
| `modules.py` | Drift helpers, monitor UI, Create Bill + Receive Stock warnings |
| `tests/test_program_b_p0_purchase_inventory_drift_control.py` | Regression suite |
| `reports/program_a_top_100_recommendations.md` | Drift control noted |
| `reports/program_a_go_no_go_assessment.md` | Pilot conditions updated |
| `reports/program_b_p0_sprint_2_purchase_inventory_drift_control.md` | This report |

---

## Tests Run

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_program_b_p0_purchase_inventory_drift_control.py" -v
python -m unittest discover -s tests -p "test_regression_lockdown.py" -v
python tests/run_regression_tests.py
git diff --check
```

---

## Remaining P1 Purchase-to-Pay Work

| ID | Item |
|----|------|
| P1-1 | Optional receive-on-post for inventory-classified bills |
| P1-3 | Valued inventory receive prompts GL posting |
| P1-18 | Extend bill≠receive help to legacy AP + tabbed purchase UI |
| P1-87 | Inventory valuation vs GL reconciliation report |
| P3-63 | Three-way match bill/PO/receive |

---

*Program B P0 Sprint 2 — no commit in this pass.*
