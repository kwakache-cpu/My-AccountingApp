# Live UAT Checklist — Role-Based Production Certification

**Phase:** 5B.18D  
**Generated at:** 2026-06-27  
**Purpose:** Browser UAT scripts for every production role before unrestricted go-live.

**Classification:** WARNING until all roles signed off.

---

## UAT Readiness

| Metric | Value |
|---|---|
| Automated permission coverage | **90%** |
| Browser UAT completion | **0%** (pending execution) |
| Overall role UAT readiness | **85%** (checklist ready, execution open) |

---

## Global UAT Rules

- Execute in **pilot company** with realistic branch setup (retail + warehouse recommended)
- Record: role, tester, date, pass/fail, defect ID, screenshot if failed
- Verify **audit trail** entry for every write action
- Verify **branch isolation** for branch-scoped roles
- No role should access modules not listed under "Accessible"
- Blocked actions must show permission denial, not silent failure

---

## 1. Owner (`Owner / CEO`)

**Scope:** Company-wide, exempt from branch module grants.

### Accessible Modules
Dashboard, POS, all Transactions, Customers, Suppliers, Banking, all Ledgers/Reports, Inventory, Assets, Financial Reports, Analytics, Audit Trail, Payroll (view), Gatekeeper Admin, System Configuration, Manage Branches

### Blocked Modules / Actions
- Backup export / cloud restore (System Admin only)
- Payroll management (view only)
- Dev platform console

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| O-01 | Login as Owner | Dashboard loads, all company modules visible | [ ] |
| O-02 | Create sales invoice → post | AR journal, customer balance updated | [ ] |
| O-03 | Receive customer payment | Cash/AR journal, allocation correct | [ ] |
| O-04 | Create supplier bill → post | AP journal, supplier balance updated | [ ] |
| O-05 | Post general journal | Balanced entry posts; unbalanced blocked | [ ] |
| O-06 | Void/reverse document | Reversal journal, audit trail | [ ] |
| O-07 | Close/lock accounting period | Period status changes; locked period blocks posting | [ ] |
| O-08 | POS sale | Revenue, inventory, COGS journals | [ ] |
| O-09 | View Trial Balance, BS, IS | Reports reconcile to journals | [ ] |
| O-10 | Manage users — create Accountant | User created with correct role | [ ] |
| O-11 | Manage branches | Branch create/edit/module grants | [ ] |
| O-12 | Owner equity / loan / bank transfer | Journals post correctly | [ ] |
| O-13 | Attempt backup export | Denied or not visible (System Admin only) | [ ] |
| O-14 | Switch branch context | Data filters to selected branch where applicable | [ ] |

### Expected Corrections
Can void/reverse documents, reopen periods, correct POS metadata (with audit).

### Expected Restrictions
Cannot export/restore backups; cannot manage payroll runs.

---

## 2. System Admin

**Scope:** IT/configuration only. **Cannot post accounting.**

### Accessible Modules
Dashboard, System Audit Trail, System Configuration, Manage Branches, Gatekeeper Admin (AI)

### Blocked Modules
POS, Transactions, Contacts, Banking, Ledgers/Reports, Inventory, Assets, Financial Reports, Analytics, Payroll

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| SA-01 | Login as System Admin | Config modules only in sidebar | [ ] |
| SA-02 | Manage users — create Cashier | User created | [ ] |
| SA-03 | Manage branches | Branch config accessible | [ ] |
| SA-04 | Export backup | Backup export succeeds or diagnostics shown | [ ] |
| SA-05 | View system health | Diagnostics load, no secrets exposed | [ ] |
| SA-06 | Attempt POS sale | Page blocked or not in sidebar | [ ] |
| SA-07 | Attempt journal posting | Permission denied | [ ] |
| SA-08 | Attempt financial reports | Page blocked or not in sidebar | [ ] |
| SA-09 | View audit trail | Read-only audit access | [ ] |
| SA-10 | Restore cloud backup (staging) | Restore initiates or shows guard message | [ ] |

### Expected Restrictions
No accounting posting, voiding, or operational transactions.

---

## 3. Accountant

**Scope:** Company-wide accounting operations.

### Accessible Modules
Dashboard, Transactions, Customers, Suppliers, Banking, Ledgers/Reports, Inventory (view), Assets, Financial Reports, Analytics, Audit Trail, Gatekeeper Admin

### Blocked Modules
POS, Payroll, System Configuration, Manage Branches

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| A-01 | Login as Accountant | Accounting modules visible, no admin config | [ ] |
| A-02 | Post sales invoice | AR journal posted | [ ] |
| A-03 | Post supplier bill | AP journal posted | [ ] |
| A-04 | Post general journal | Entry posts with balance check | [ ] |
| A-05 | Void/reverse journal | Reversal created, audit logged | [ ] |
| A-06 | Close accounting period | Period close succeeds | [ ] |
| A-07 | View/manage chart of accounts | COA accessible | [ ] |
| A-08 | View financial reports | TB, GL, aging load correctly | [ ] |
| A-09 | Attempt POS sale | Blocked or not in sidebar | [ ] |
| A-10 | Attempt user management | Denied | [ ] |
| A-11 | Approve POS discount (>10%) | Discount approval works if invoked | [ ] |
| A-12 | View inventory | Read-only inventory access | [ ] |

### Expected Corrections
Full void/reverse and period control.

---

## 4. Cashier

**Scope:** Branch-scoped, retail operations.

### Accessible Modules
Dashboard, POS, Customers, Receive Payment

### Blocked Modules
Invoices/Bills, Suppliers, Banking, Ledgers/Reports, Inventory, Assets, Payroll, Admin

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| C-01 | Login as Cashier | POS-focused sidebar only | [ ] |
| C-02 | Complete POS sale | Receipt, inventory decrement, journal | [ ] |
| C-03 | Apply discount ≤10% | Discount applied | [ ] |
| C-04 | Apply discount >10% | Requires manager approval prompt | [ ] |
| C-05 | Receive customer payment | Payment recorded, AR reduced | [ ] |
| C-06 | Create customer | Customer created in branch | [ ] |
| C-07 | Close cash drawer | Drawer close recorded | [ ] |
| C-08 | View own cashier session | Session visible | [ ] |
| C-09 | Attempt financial reports | Blocked | [ ] |
| C-10 | Attempt journal posting | Denied | [ ] |
| C-11 | Attempt supplier bill | Blocked | [ ] |
| C-12 | Switch branch | Branch selector not available (locked) | [ ] |
| C-13 | View other branch data | Not visible (branch filter) | [ ] |

### Expected Restrictions
No posting, reports, banking, or admin. Branch locked.

---

## 5. Inventory Officer

**Scope:** Stock management, typically branch-scoped.

### Accessible Modules
Dashboard, Inventory Management, Suppliers

### Blocked Modules
POS, Transactions, Customers, Banking, Ledgers/Reports, Assets, Payroll, Admin

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| IO-01 | Login as Inventory Officer | Inventory + Suppliers only | [ ] |
| IO-02 | Create/edit inventory item | Item saved | [ ] |
| IO-03 | Stock adjustment | Movement recorded with audit | [ ] |
| IO-04 | Create supplier | Supplier created | [ ] |
| IO-05 | Attempt POS sale | Blocked | [ ] |
| IO-06 | Attempt journal posting | Denied | [ ] |
| IO-07 | Attempt customer invoice | Blocked | [ ] |
| IO-08 | View financial reports | Blocked | [ ] |

### Expected Restrictions
No accounting posting or sales documents.

---

## 6. HR / Payroll Officer

**Scope:** Payroll operations with posting authority.

### Accessible Modules
Dashboard, Payroll, Ledgers/Reports (journals), Audit Trail

### Blocked Modules
POS, Banking, Inventory, Assets, Customers, System Config, Manage Branches

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| HR-01 | Login as HR/Payroll Officer | Payroll + reports visible | [ ] |
| HR-02 | Create payroll run | Run created | [ ] |
| HR-03 | Post payroll | Expense/liability journals posted | [ ] |
| HR-04 | Void payroll entry | Reversal with audit | [ ] |
| HR-05 | View payroll reports | Reports load | [ ] |
| HR-06 | Attempt user management | Denied | [ ] |
| HR-07 | Attempt POS | Blocked | [ ] |
| HR-08 | Attempt banking | Blocked | [ ] |

---

## 7. Auditor (`Auditor / Read Only`)

**Scope:** Read-only financial and audit access.

### Accessible Modules
Dashboard, Ledgers/Reports, Audit Trail

### Blocked Modules
All write modules: POS, Transactions, Contacts, Banking, Inventory, Assets, Payroll, Admin

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| AU-01 | Login as Auditor | Reports + audit only | [ ] |
| AU-02 | View Trial Balance | Read-only, loads correctly | [ ] |
| AU-03 | View General Ledger | Read-only | [ ] |
| AU-04 | View AR/AP aging | Read-only | [ ] |
| AU-05 | Filter audit trail | Filters work, export if available | [ ] |
| AU-06 | View system health diagnostics | Accessible | [ ] |
| AU-07 | Attempt journal posting | Denied | [ ] |
| AU-08 | Attempt any create/edit/delete | Denied across all modules | [ ] |

### Expected Restrictions
Strictly read-only. No posting, voiding, or admin.

---

## 8. Branch Manager

**Scope:** Branch-scoped operations with user management.

### Accessible Modules
Dashboard, POS, Transactions, Customers, Suppliers, Banking, Ledgers/Reports, Inventory, Assets (view), Financial Reports, Analytics, Audit Trail, Manage Branches (branch-level)

### Blocked Modules
System Configuration, Payroll, COA management, Gatekeeper Admin (branch rule)

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| BM-01 | Login as Branch Manager | Branch operations visible | [ ] |
| BM-02 | POS sale in branch | Sale posts correctly | [ ] |
| BM-03 | Create branch user (Cashier) | User created for branch | [ ] |
| BM-04 | Post invoice in branch | AR journal in branch | [ ] |
| BM-05 | View branch reports | Reports scoped to branch | [ ] |
| BM-06 | Attempt void/reverse document | Denied | [ ] |
| BM-07 | Attempt period close | Denied | [ ] |
| BM-08 | Attempt company-wide user admin | Denied or limited | [ ] |
| BM-09 | Attempt POS sale correction | Denied (no `correct_pos_sales`) | [ ] |
| BM-10 | View other branch data | Not visible | [ ] |
| BM-11 | Approve POS discount >10% | Approval succeeds | [ ] |

### Expected Corrections
Can post but not void/reverse or close periods.

---

## 9. Bookkeeper

**Scope:** Company-wide bookkeeping without void/period admin.

### Accessible Modules
Dashboard, POS, Transactions, Customers, Suppliers, Banking, Ledgers/Reports, Inventory (view), Assets, Financial Reports, Analytics

### Blocked Modules
Audit Trail, System Configuration, Manage Branches, Payroll

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| B-01 | Login as Bookkeeper | Bookkeeping modules visible | [ ] |
| B-02 | Post sales invoice | AR journal posted | [ ] |
| B-03 | Post general journal | Entry posts | [ ] |
| B-04 | POS sale | Sale completes | [ ] |
| B-05 | View financial reports | Reports load | [ ] |
| B-06 | Attempt void/reverse | Denied | [ ] |
| B-07 | Attempt period close | Denied | [ ] |
| B-08 | Attempt audit trail | Blocked or not in sidebar | [ ] |
| B-09 | Attempt user management | Denied | [ ] |

### Expected Restrictions
Can post but not void, reverse, or manage periods/users.

---

## 10. Staff

**Scope:** Most restricted branch-scoped role.

### Accessible Modules
Dashboard, POS, Customers, Receive Payment

### Blocked Modules
Same as Cashier minus own session view

### UAT Script

| # | Action | Expected | Pass |
|---|---|---|---|
| S-01 | Login as Staff | Minimal sidebar | [ ] |
| S-02 | POS sale | Sale completes | [ ] |
| S-03 | Receive payment | Payment recorded | [ ] |
| S-04 | Create customer | Customer created | [ ] |
| S-05 | Attempt reports | Blocked | [ ] |
| S-06 | Attempt journal | Denied | [ ] |
| S-07 | Attempt backup/system health | Denied | [ ] |
| S-08 | Attempt admin modules | Blocked | [ ] |

### Expected Restrictions
Same operational scope as Cashier but without cashier session view or elevated permissions.

---

## Cross-Role Verification Matrix

| Role | Post GL | Void | Period | POS | Reports | Admin | Branch Lock |
|---|---|---|---|---|---|---|---|
| Owner | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | No |
| System Admin | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | No |
| Accountant | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | No |
| Cashier | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | Yes |
| Inventory Officer | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | Often |
| HR/Payroll | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ | Optional |
| Auditor | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | Optional |
| Branch Manager | ✓ | ✗ | ✗ | ✓ | ✓ | Branch | Yes |
| Bookkeeper | ✓ | ✗ | ✗ | ✓ | ✓ | ✗ | No |
| Staff | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | Yes |

---

## Module Workflow UAT (All Roles)

Execute with appropriate role for each workflow:

| Module | Key Workflows | Responsible Role | Pass |
|---|---|---|---|
| Dashboard | Load time, branch context | Owner, Branch Manager | [ ] |
| POS | Sale, return, discount, drawer close | Cashier, Branch Manager | [ ] |
| Sales Invoice | Create, post, payment | Accountant, Owner | [ ] |
| Supplier Bill | Create, post, payment | Accountant, Owner | [ ] |
| General Journal | Post, locked period block | Accountant, Owner | [ ] |
| Banking | Transfer, reconciliation | Owner, Branch Manager | [ ] |
| Inventory | Adjust, movement | Inventory Officer | [ ] |
| Payroll | Run, post | HR/Payroll | [ ] |
| Fixed Assets | Acquire, depreciate | Accountant, Owner | [ ] |
| VAT/NHIL | Report totals | Accountant + Finance sign-off | [ ] |
| Audit Trail | Filter, export | Auditor, Owner | [ ] |
| User Management | Create, disable, branch assign | System Admin, Owner | [ ] |
| Backup/Restore | Export, restore (staging) | System Admin | [ ] |

---

## Sign-Off

| Role | Tester | Date | Result | Notes |
|---|---|---|---|---|
| Owner | | | [ ] Pass / [ ] Fail | |
| System Admin | | | [ ] Pass / [ ] Fail | |
| Accountant | | | [ ] Pass / [ ] Fail | |
| Cashier | | | [ ] Pass / [ ] Fail | |
| Inventory Officer | | | [ ] Pass / [ ] Fail | |
| HR/Payroll | | | [ ] Pass / [ ] Fail | |
| Auditor | | | [ ] Pass / [ ] Fail | |
| Branch Manager | | | [ ] Pass / [ ] Fail | |
| Bookkeeper | | | [ ] Pass / [ ] Fail | |
| Staff | | | [ ] Pass / [ ] Fail | |

**Business owner sign-off:** _________________ Date: _________  
**Finance owner sign-off:** _________________ Date: _________  
**Technical owner sign-off:** _________________ Date: _________
