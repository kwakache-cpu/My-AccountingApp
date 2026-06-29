# Live Browser UAT — Sprint 1 Checklist

**Sprint:** Launch Validation Sprint 1  
**Generated at:** 2026-06-28  
**Purpose:** Practical browser UAT checklist for live-app validation in production or approved pilot runtime.

**Prerequisite:** App deployed to live runtime with production secrets configured.  
**Defect logging:** Use `reports/live_defect_intake_template.md` and update `reports/launch_blocker_tracker.md`.

---

## Sprint 1 Objectives

- Move from development certification to **real live-app validation**
- Execute high-priority browser flows across all production roles
- Capture defects with Severity, Module, Role, Owner, Evidence, and Screenshot
- Record **Launch blocking decision** for each Critical or High finding

---

## UAT Environment

| Field | Value |
|---|---|
| Runtime URL | _______________________ |
| Deployment mode | [ ] SQLite pilot [ ] PostgreSQL [ ] Staging rehearsal |
| Pilot company | _______________________ |
| Test date | _______________________ |
| Lead tester | _______________________ |
| Owner | _______________________ |

---

## Global Live Test Rules

- Test in a **live browser** against deployed runtime — not local dev unless explicitly approved
- Record **Role**, **Module**, pass/fail, defect ID, **Evidence** (steps to reproduce), and **Screenshot** for failures
- Verify **audit trail** entry for every write action
- Verify permission denials are explicit — not silent failures
- Classify each defect: **Critical**, **High**, **Medium**, or **Low**
- Track defect status: **Open**, **Fixed**, or **Verified**
- Record **Launch blocking decision** for each defect

---

## Sprint 1 — Critical Path Live Tests

### 1. App Startup and Dashboard

| # | Module | Role | Test | Expected | Pass | Defect ID |
|---|---|---|---|---|---|---|
| S1-01 | Startup | Owner / CEO | App startup | App loads without exception | [ ] | |
| S1-02 | Dashboard | Owner / CEO | Dashboard loads | Metrics and navigation visible | [ ] | |
| S1-03 | Diagnostics | System Admin | System health visible | Backend, company count, backup status shown; no secrets exposed | [ ] | |
| S1-04 | Permissions | All roles | Login for each role | Each role reaches intended module set only | [ ] | |

### 2. Core Accounting Write Path

| # | Module | Role | Test | Expected | Pass | Defect ID |
|---|---|---|---|---|---|---|
| S1-05 | POS | Cashier | POS sale | Revenue, inventory, COGS journals; audit trail | [ ] | |
| S1-06 | Receivables | Accountant | Customer invoice → post | AR journal; customer balance updated | [ ] | |
| S1-07 | Receivables | Accountant | Customer payment | Cash/AR journal; allocation correct | [ ] | |
| S1-08 | Payables | Accountant | Supplier bill → post | AP journal; supplier balance updated | [ ] | |
| S1-09 | General Ledger | Accountant | Balanced journal entry | Posts successfully; audit trail | [ ] | |
| S1-10 | General Ledger | Accountant | Unbalanced journal entry | Blocked with clear error | [ ] | |

### 3. Financial Reports

| # | Module | Role | Test | Expected | Pass | Defect ID |
|---|---|---|---|---|---|---|
| S1-11 | Financial Reports | Owner / CEO | Trial Balance | Report loads and balances | [ ] | |
| S1-12 | Financial Reports | Accountant | Balance Sheet | Reconciles to Trial Balance | [ ] | |
| S1-13 | Financial Reports | Accountant | Income Statement | Reconciles to posted activity | [ ] | |
| S1-14 | Financial Reports | Auditor | Read-only report access | Reports visible; write actions blocked | [ ] | |

### 4. Permissions and Branch Isolation

| # | Module | Role | Test | Expected | Pass | Defect ID |
|---|---|---|---|---|---|---|
| S1-15 | Permissions | System Admin | Accounting modules blocked | Cannot post journals or transactions | [ ] | |
| S1-16 | Permissions | Cashier | Non-POS modules blocked | POS only; other modules denied | [ ] | |
| S1-17 | Permissions | Auditor | Write actions blocked | Reports and audit trail only | [ ] | |
| S1-18 | Branch | Branch Manager | Branch-scoped data | Data limited to assigned branch | [ ] | |

### 5. Backup and Audit

| # | Module | Role | Test | Expected | Pass | Defect ID |
|---|---|---|---|---|---|---|
| S1-19 | Backup | Operator | Post-write cloud backup | Backup timestamp updates after write | [ ] | |
| S1-20 | Audit Trail | Owner / CEO | Audit trail after writes | All Sprint 1 write actions logged | [ ] | |

---

## Defect Severity Guide (Sprint 1)

| Severity | Example | Launch blocking decision |
|---|---|---|
| **Critical** | Data corruption, unbalanced TB, permission escalation | **BLOCKS LAUNCH** |
| **High** | Core workflow broken for pilot role | **BLOCKS LAUNCH** unless waived |
| **Medium** | Workaround exists; limited pilot impact | Usually **DOES NOT BLOCK LAUNCH** |
| **Low** | Cosmetic or minor UX issue | **DOES NOT BLOCK LAUNCH** |

---

## Sprint 1 Sign-Off

| Role | Tester | Tests Complete | Defects Logged | Signature | Date |
|---|---|---|---|---|---|
| Owner / CEO | | [ ] | [ ] | | |
| System Admin | | [ ] | [ ] | | |
| Accountant | | [ ] | [ ] | | |
| Cashier | | [ ] | [ ] | | |
| Operator | | [ ] | [ ] | | |

**Sprint 1 result:** [ ] PASS [ ] PASS WITH DEFECTS [ ] FAIL  
**Launch blocking decision:** _______________________

---

## Related Reports

- `reports/launch_blocker_tracker.md`
- `reports/role_based_live_uat_matrix.md`
- `reports/live_defect_intake_template.md`
- `reports/live_uat_checklist.md`
