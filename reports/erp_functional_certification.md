# ERP Functional Certification

**Generated at:** 2026-06-25 15:28 UTC  
**Branch:** `phase-5b17a-erp-functional-certification`  
**Scope:** accounting workflow certification after PostgreSQL migration hardening.  
**Policy:** additive certification only; no feature removal, redesign, commits, pushes, or merges.

## Executive Summary

The ERP core accounting workflows are functionally connected through source documents, journal entries, balances, reports, permissions, branch controls, and audit logging. This phase adds workflow-level certification tests that prove the major accounting chains work together in an isolated runtime database.

**Module readiness:** **88%**  
**Functional accounting readiness:** **86%**  
**Production readiness:** **80%**

Production deployment should remain blocked until staged PostgreSQL workflow execution, migration cleanup disposition, and operational cutover checks are complete.

## Module Readiness

| Module / Area | Readiness | Certification Result |
|---|---:|---|
| POS | 86% | PASS with warning: sale, inventory, journal, credit customer balance, and audit chain certified in tests; staged PostgreSQL checkout still required. |
| Inventory | 85% | PASS with warning: quantity movement and POS decrement effects certified; broader imports and adjustment UI still need staged runtime evidence. |
| Customers / AR | 92% | PASS: invoice posting increases AR/customer balance and receipt payment reduces balance to zero. |
| Suppliers / AP | 92% | PASS: bill posting increases AP/supplier balance and supplier payment reduces balance to zero. |
| General Journal | 94% | PASS: balanced journals post, unbalanced journals are blocked, ledger balances update. |
| Payroll | 84% | PASS with warning: payroll record, journal posting, and payroll total reconciliation certified; full UI staging remains required. |
| Fixed Assets | 82% | PASS with warning: asset creation, acquisition posting, depreciation journal, and book value update certified; source linkage for depreciation remains weaker than acquisition. |
| Financial Reports | 90% | PASS: trial balance, income statement, balance sheet, and general ledger outputs certified from posted journals. |
| Security / Branch / Audit | 90% | PASS: role restrictions, branch restrictions, and admin audit logging certified. |

## Workflow Certification

| Workflow | Status | Certified Evidence |
|---|---|---|
| POS Sale | PASS with warning | Inventory decreases, `pos_sales` record is created, journal entry posts, credit customer balance updates, audit log records action. Warning remains for real PostgreSQL staged checkout. |
| Customer Invoice / AR | PASS | Invoice is created, AR/revenue journal posts, customer balance increases, customer receipt payment reduces balance to zero. |
| Supplier Bill / AP | PASS | Bill is created, expense/AP journal posts, supplier balance increases, supplier payment reduces balance to zero. |
| General Journal | PASS | Balanced manual journal posts, unbalanced journal is rejected, cash ledger running balance updates. |
| Payroll | PASS with warning | Payroll row posts to salary expense and liabilities; payroll gross and net totals reconcile to journal impact. |
| Fixed Assets | PASS with warning | Fixed asset is created, acquisition journal posts, depreciation posts, accumulated depreciation increases, book value decreases. |
| Financial Reports | PASS | Trial balance debits equal credits; income statement includes revenue and expense; balance sheet equation holds; general ledger shows transactions. |
| Security | PASS | Cashier/reporting permissions are restricted, branch-scoped access is enforced, admin action is audit logged. |

## Accounting Integrity Issues

- No new accounting integrity failures were found in the certified workflow tests.
- Trial balance remains balanced from posted journal lines.
- AR and AP balances derive from journal postings and reduce correctly after matching payments.
- Fixed asset depreciation updates the asset register and creates journal impact, but depreciation journal source linkage should be strengthened in a later hardening phase.
- POS certification uses the backend-aware transaction wrapper and audit path, but real PostgreSQL checkout staging remains required before production approval.

## Remaining Production Blockers

- Staged PostgreSQL execution is still required for POS checkout, inventory adjustments, AR/AP workflows, payroll, fixed assets, reports, audit, and security/admin paths.
- Manual migration cleanup warnings from earlier reports still need resolution or formal acceptance before production cutover.
- Production cutover still requires backup/restore proof, rollback window approval, operator sign-off, and final smoke testing.
- Performance and concurrency behavior under real PostgreSQL load remains outside this isolated functional certification.

## Tests Added

Added `tests/test_erp_functional_certification.py` covering:

- POS sale inventory, sale record, journal, credit customer balance, and audit trail.
- Customer invoice and receipt AR lifecycle.
- Supplier bill and supplier payment AP lifecycle.
- General journal balanced/unbalanced behavior and ledger updates.
- Payroll posting and payroll total reconciliation.
- Fixed asset acquisition and depreciation posting/book value update.
- Trial balance, income statement, balance sheet, and general ledger report integrity.
- Security role restrictions, branch restrictions, and admin audit logging.
- Report contract for this certification report.

## Recommended Next Action

**Recommended next action:** run staged PostgreSQL end-to-end functional certification using the same workflow matrix, then resolve or formally disposition migration cleanup warnings before production cutover approval.
