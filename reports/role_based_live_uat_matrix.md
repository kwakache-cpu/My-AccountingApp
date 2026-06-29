# Role-Based Live UAT Matrix — Sprint 1

**Sprint:** Launch Validation Sprint 1  
**Generated at:** 2026-06-28  
**Purpose:** Matrix for tracking live browser UAT completion by production role and module.

**Reference:** Detailed scripts in `reports/live_uat_checklist.md`. Sprint 1 focuses on critical-path validation per role.

---

## Matrix Summary

| Metric | Value |
|---|---|
| Total production roles | **10** |
| Roles with Sprint 1 sign-off | **0 / 10** |
| Automated permission coverage | **90%** |
| Live browser validation | **Pending** |

---

## Status Key

| Status | Meaning |
|---|---|
| **Open** | Live UAT not started for this role/module |
| **Fixed** | Defect fixed; pending live re-test |
| **Verified** | Live browser test passed |

---

## Role × Module Matrix

| Role | Module | Critical Tests | Owner | Status | Evidence | Screenshot | Launch blocking decision |
|---|---|---|---|---|---|---|---|
| Owner / CEO | Dashboard | Login, Dashboard loads, navigation | | Open | | | |
| Owner / CEO | POS | POS sale, void if test | | Open | | | |
| Owner / CEO | Receivables | Invoice, payment | | Open | | | |
| Owner / CEO | Payables | Bill, payment | | Open | | | |
| Owner / CEO | General Ledger | Journal post, Trial Balance | | Open | | | |
| Owner / CEO | Financial Reports | TB, BS, IS | | Open | | | |
| Owner / CEO | Audit Trail | Write actions logged | | Open | | | |
| System Admin | System Configuration | Config access only | | Open | | | |
| System Admin | Permissions | Accounting modules blocked | | Open | | | |
| System Admin | Backup / Restore | Backup path visible; restore guarded | | Open | | | |
| Accountant | General Ledger | Balanced/unbalanced journal | | Open | | | |
| Accountant | Receivables | Invoice, payment, AR aging | | Open | | | |
| Accountant | Payables | Bill, payment, AP aging | | Open | | | |
| Accountant | Financial Reports | TB, GL detail | | Open | | | |
| Cashier | POS | Sale, checkout, branch scope | | Open | | | |
| Cashier | Permissions | Non-POS modules blocked | | Open | | | |
| Inventory Officer | Inventory | Stock view, adjustment | | Open | | | |
| Inventory Officer | POS | Inventory decrement on sale | | Open | | | |
| HR / Payroll Officer | Payroll | Payroll view/run if in scope | | Open | | | |
| HR / Payroll Officer | Permissions | Non-payroll write blocked | | Open | | | |
| Auditor | Financial Reports | Read-only TB, BS, IS | | Open | | | |
| Auditor | Audit Trail | Read-only audit access | | Open | | | |
| Auditor | Permissions | All write actions blocked | | Open | | | |
| Branch Manager | Branch | Branch-scoped data | | Open | | | |
| Branch Manager | POS | Branch POS access | | Open | | | |
| Branch Manager | Reports | Branch-level reports | | Open | | | |
| Bookkeeper | General Ledger | Journal entry, posting | | Open | | | |
| Bookkeeper | Receivables | Invoice, payment | | Open | | | |
| Bookkeeper | Payables | Bill, payment | | Open | | | |
| Staff | Permissions | Limited module access | | Open | | | |
| Staff | Assigned modules | Role-scoped workflows only | | Open | | | |

---

## Role Sign-Off Summary

| # | Role | Sprint 1 Complete | Defects | Owner | Status | Launch blocking decision |
|---|---|---|---|---|---|---|
| 1 | Owner / CEO | [ ] | | | Open | |
| 2 | System Admin | [ ] | | | Open | |
| 3 | Accountant | [ ] | | | Open | |
| 4 | Cashier | [ ] | | | Open | |
| 5 | Inventory Officer | [ ] | | | Open | |
| 6 | HR / Payroll Officer | [ ] | | | Open | |
| 7 | Auditor / Read Only | [ ] | | | Open | |
| 8 | Branch Manager | [ ] | | | Open | |
| 9 | Bookkeeper | [ ] | | | Open | |
| 10 | Staff | [ ] | | | Open | |

---

## Severity Escalation by Role

If any role encounters a defect during live testing, classify and record:

| Severity | Action |
|---|---|
| **Critical** | Stop role sign-off; log in tracker; **BLOCKS LAUNCH** until Verified |
| **High** | Log defect; complete remaining tests; **Launch blocking decision** required |
| **Medium** | Log defect; continue if workaround exists |
| **Low** | Log defect; continue testing |

---

## Related Reports

- `reports/live_browser_uat_sprint_1.md`
- `reports/launch_blocker_tracker.md`
- `reports/live_defect_intake_template.md`
- `reports/live_uat_checklist.md`
