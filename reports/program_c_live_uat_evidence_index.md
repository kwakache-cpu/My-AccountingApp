# Program C — Live UAT Evidence Index (Round 1)

**Date:** 2026-08-04  
**Branch:** `program-c-live-business-acceptance-round-1`  

---

## Evidence policy

| Class | Storage | Acceptable for live PASS? |
|-------|---------|---------------------------|
| LIVE_UI | Screenshots under `reports/evidence/program_c_r1/` (create when captured) + timing notes in checklist | Yes |
| AUTO_CERT | Test module::method + run log excerpt | No — PARTIAL platform only |
| CODE_TRACE | File/function citation | No |
| KNOWN_GAP | Prior report citation | Defect only |

**Screenshot folder status:** Not created this session (no captures). Operators should add `reports/evidence/program_c_r1/` when live UAT runs.

---

## A. Live UI evidence (Round 1 session)

| Evidence ID | Workflow | File / note | Status |
|-------------|----------|-------------|--------|
| LIVE-000 | — | No live runtime session in agent Round 1 | **Missing** |

---

## B. Automated / certification evidence mapped to workflows

| Evidence ID | Workflow IDs | Source | What it proves | Limits |
|-------------|--------------|--------|----------------|--------|
| AUTO-001 | W17, W18, W21 | `tests/test_erp_functional_certification.py::test_pos_credit_sale_updates_inventory_journal_customer_balance_and_audit` | POS credit: inventory, journals, customer, audit | Not browser UX/timing |
| AUTO-002 | W10, W20 | `test_customer_invoice_and_payment_certify_ar_lifecycle` | AR invoice + receipt journals/subledger | Not live receipt UI |
| AUTO-003 | W11, W15, W16 | `test_supplier_bill_and_payment_certify_ap_lifecycle` | AP bill + payment | Bill≠stock still true |
| AUTO-004 | W29, W30–W32 | `test_general_journal_certifies_balancing_and_ledger_updates` + `test_financial_reports_certify_trial_balance_income_balance_sheet_and_ledger` | Journal balance + TB/IS/BS | Warm timing not measured |
| AUTO-005 | W25 | `test_payroll_posting_creates_journal_and_reconciles_totals` | Payroll JE totals | Statutory sign-off open |
| AUTO-006 | W26, W27 | `test_fixed_asset_creation_depreciation_journal_and_book_value` | Asset + depreciation | Disposal missing |
| AUTO-007 | W04, W08, W34 | `test_security_role_branch_and_admin_audit_certification` + `tests/test_regression_lockdown.py` | Permissions / lockdown | Not full menu click matrix |
| AUTO-008 | W21 | `tests/test_program_b_p0_inventory_movement_integrity.py` (23 tests) | Qty⇔movement integrity | Live movement UI review open |
| AUTO-009 | W22 | `tests/test_program_b_p0_inventory_valuation_integrity.py` (18 tests) | Valuation vs GL detection | Live page unused |
| AUTO-010 | W01–W03 | Subscription/Paystack/onboarding unit suites (regression pack) | Init/config paths | Live Paystack depends on secrets |
| AUTO-011 | W37 | Hotfix-004 company lifecycle tests (if present in suite) | Wipe safety patterns | Only on UAT keys |

---

## C. Code-trace evidence (Program B)

| Evidence ID | Topic | Citation |
|-------------|-------|----------|
| CODE-001 | Movement integrity helper | `modules.apply_inventory_quantity_change` |
| CODE-002 | Valuation snapshot / reconcile | `accounting_engine.build_inventory_valuation_snapshot`, `reconcile_inventory_subledger_to_gl` |
| CODE-003 | Transfer quantity-only | Sprint 4 safeguard in Adjust Stock UI |
| CODE-004 | Inventory Valuation page | `modules.show_inventory_valuation` + app nav |

Report: `reports/program_b_p0_sprint_4_inventory_valuation_integrity.md`

---

## D. Known-gap citations

| Evidence ID | Defect | Source report |
|-------------|--------|---------------|
| GAP-001 | Bill≠receive | `program_a_go_no_go_assessment.md`, Program B Sprint 2 |
| GAP-002 | Browser UAT 0% | `reports/live_uat_checklist.md` |
| GAP-003 | Backup restore | Program A readiness |
| GAP-004 | Tax sign-off | Top 100 #5 |
| GAP-005 | Frozen multi-UOM | Program A scorecard verticals |

---

## E. Validation runs for Program C documentation sprint

| Run | Command | Expected record |
|-----|---------|-----------------|
| V1 | `python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py` | **PASS** exit 0 (2026-08-04 Program C session) |
| V2 | `python -m unittest discover -s tests -p "test_regression_lockdown.py" -v` | **PASS** 26 tests OK |
| V3 | `python tests/run_regression_tests.py` | **PASS** 875 tests OK (~1157s), EXIT:0 |
| V4 | `git diff --check` | **PASS** exit 0 |
| V5 | `git status --short` / `git diff --stat` | Docs-only Program C package |

---

## F. Accounting proof matrix (operator)

Copy per transaction during live UAT:

| Check | Y/N | Evidence ref |
|-------|-----|--------------|
| Source document | | |
| Expected journal exists | | |
| Journal balanced | | |
| Correct accounts | | |
| Subledger updated | | |
| Qty updated | | |
| Stock movement | | |
| Valuation impact | | |
| TB reflects | | |
| Statements reflect | | |
| Audit trail | | |

---

## G. How to attach screenshots (next operator)

1. Create `reports/evidence/program_c_r1/`.  
2. Name files `Wxx_role_yyyyMMdd_HHmm.png`.  
3. Link filename in checklist row “Screenshot/evidence reference”.  
4. Never commit secrets, access keys, or live customer PII beyond UAT-marked data.
