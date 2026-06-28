# Final Finance and Accounting Sign-Off — Phase 5B.18F

**Phase:** 5B.18F  
**Generated at:** 2026-06-28  
**Purpose:** Finance owner sign-off checklist for accounting integrity, statutory reporting readiness, and controlled production launch approval.

## Sign-Off Scope

This checklist certifies finance and accounting readiness for a **controlled first-customer production launch**.
Unrestricted enterprise rollout requires additional statutory and volume testing sign-off.

- Accounting integrity baseline: **certified** (automated regression and prior phase reports)
- Statutory report sign-off: **required for tax-compliant go-live**; pilot waiver may apply for limited scope
- Source of truth: `reports/final_go_live_blockers.md`, `reports/final_release_decision.md`

---

## Manual Action Preconditions

- **STREAMLIT SECRET REQUIRED** — finance team confirms production runtime uses approved configuration
- **FIREBASE ACTION REQUIRED** — finance team confirms backup/restore path supports accounting data recovery
- **DATABASE ACTION REQUIRED** — finance team confirms active backend matches approved cutover plan
- **SUPABASE ACTION REQUIRED** — if Postgres backend is active, finance team confirms Supabase backup SOP supports GL recovery

---

## Core Accounting Integrity

| Control | Status | Notes |
|---|---|---|
| Trial Balance balances for pilot company | [ ] |  |
| Journal entries balance (debits = credits) | [ ] |  |
| Posted journals immutable without reversal workflow | [ ] |  |
| AR customer balances reconcile to open invoices and payments | [ ] |  |
| AP supplier balances reconcile to open bills and payments | [ ] |  |
| Inventory valuation aligns with configured costing method | [ ] |  |
| Accounting period controls enforced | [ ] |  |
| Audit trail records financial transactions | [ ] |  |

---

## Financial Report Validation

Confirm key reports for pilot company:

- [ ] Trial Balance
- [ ] Balance Sheet
- [ ] Income Statement
- [ ] General Ledger detail
- [ ] AR Aging (if receivables in pilot scope)
- [ ] AP Aging (if payables in pilot scope)

Performance note: large-dataset report timing is a **POST-LAUNCH IMPROVEMENT** unless pilot volume exceeds documented targets.

---

## Statutory and Tax Reporting

| Report / Control | Status | Blocks Launch? |
|---|---|---|
| VAT report format validated against expected filing | [ ] | **BLOCKS LAUNCH** for statutory tax go-live |
| NHIL / GETFund report format validated | [ ] | **BLOCKS LAUNCH** for statutory tax go-live |
| Payroll statutory outputs validated (if payroll in pilot scope) | [ ] | **BLOCKS LAUNCH** if payroll active |
| Finance owner pilot waiver documented (if limited non-tax pilot) | [ ] | Allows **DOES NOT BLOCK LAUNCH** pilot |

---

## End-to-End Workflow Sign-Off

- [ ] POS sale → inventory decrement → journal posting → audit trail (if POS in scope)
- [ ] Customer invoice → payment → AR reduction
- [ ] Supplier bill → payment → AP reduction
- [ ] Manual journal entry → Trial Balance update
- [ ] Void/reversal workflow preserves audit integrity (if tested)

---

## Rollback Accounting Validation

Finance owner confirms understanding of rollback validation steps:

- [ ] Trial Balance must balance after restore
- [ ] Row counts for critical tables reconciled post-restore
- [ ] Sample financial reports reconciled post-restore
- [ ] Rollback owner and finance owner jointly approve any production restore

Reference: `reports/production_rollback_checklist.md`

---

## Known Accounting Findings (From Prior Phases)

| Finding | Classification | Launch Impact |
|---|---|---|
| Fixed asset multi-period depreciation edge cases | POST-LAUNCH IMPROVEMENT | DOES NOT BLOCK LAUNCH for pilot with finance review |
| Banking/cash reconciliation UI not operationally certified | Operational gap | DOES NOT BLOCK LAUNCH for controlled pilot |
| Inventory bulk import at volume untested | Volume testing gap | DOES NOT BLOCK LAUNCH for controlled pilot |
| Production-size TB/GL timing unknown | Performance gap | DOES NOT BLOCK LAUNCH for small pilot dataset |

---

## Finance Sign-Off Record

| Stakeholder | Role | Accounting Sign-Off | Signature | Date |
|---|---|---|---|---|
|  | Finance Owner | [ ] Approve pilot [ ] Reject |  |  |
|  | Business Owner | [ ] Acknowledge |  |  |
|  | Technical Owner | [ ] Acknowledge |  |  |

**Pilot waiver for statutory reports (if applicable):** _______________________  
**Approved pilot scope (modules):** _______________________

---

## Related Reports

- `reports/final_release_decision.md`
- `reports/final_go_live_blockers.md`
- `reports/final_launch_approval_checklist.md`
- `reports/final_customer_launch_checklist.md`
- `reports/phase_5b18f_launch_certification_summary.md`
