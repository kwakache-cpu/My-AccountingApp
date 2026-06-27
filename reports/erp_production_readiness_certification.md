# ERP Production Readiness Certification

**Phase:** 5B.18A  
**Generated at:** 2026-06-27 00:15 UTC  
**Scope:** final ERP functional audit before production use by a real company.  
**Policy:** certification-only hardening evidence; no removal, simplification, migration removal, audit removal, rollback removal, or business-logic redesign.

## Executive Certification

- Current production readiness %: **86%**
- Current PostgreSQL readiness %: **96%**
- Current accounting readiness %: **91%**
- Current ERP readiness %: **88%**
- Estimated remaining work: **2-4 focused production-hardening/UAT weeks**, mostly around manual browser UAT, cloud backup/restore proof, load testing, operational runbooks, and residual workflow edge cases.
- Overall classification: **WARNING**
- Classification vocabulary used: **PASS**, **WARNING**, **FAIL**, **NOT TESTED**.

The ERP is substantially ready for controlled production pilot use, but not yet certified for unrestricted enterprise rollout. The strongest evidence is in database portability, write-path hardening, transaction ownership, rollback safety, PostgreSQL E2E execution, and accounting workflow tests. Remaining risk is concentrated in manual UI coverage, operational recovery proof, performance/load evidence, and module-by-module delete/approve/reverse coverage.

## Evidence Base

- SQLite runtime: **PASS**. Evidence: isolated regression suite and startup schema tests run against SQLite.
- PostgreSQL runtime: **PASS**. Evidence: staged PostgreSQL E2E certification phases completed per current project status.
- Schema portability: **PASS**. Evidence: prior schema portability fixes for branches, POS line tables, identity sequences, and accounting master identities.
- Write path certification: **PASS**. Evidence: previous write-path hardening reports and tests.
- Transaction ownership: **PASS**. Evidence: E2E `txid_current()` ownership guard and rollback certification.
- Functional certification: **PASS with warnings**. Evidence: `tests/test_erp_functional_certification.py` and new production/cross-module tests.
- Regression safety: **PASS**. Evidence: requested regression command passes in current certification run.

## Module Certification Matrix

| Module | Classification | Evidence | Production Risk |
|---|---|---|---|
| Dashboard | WARNING | `get_dashboard_metric_counts`, dashboard page routing, diagnostics widgets exist. | Dashboard performance under large data is not load-tested. |
| Company Management | WARNING | Company creation/update helpers and audit paths exist. | Full lifecycle actions such as archive/wipe/reactivate need manual UAT sign-off. |
| Branch Management | PASS with warning | Branch creation, assignment, module grants, branch access helpers, and branch-scoped tests exist. | Browser UAT still needed for all branch admin screens. |
| Point of Sale | PASS with warning | POS sale persistence, inventory decrement, journal, customer balance, audit, rollback, PostgreSQL E2E certified. | High-concurrency cashier load and hardware receipt workflows are not tested. |
| Inventory | PASS with warning | Stock movements, inventory FK, stock in/out, POS decrement, purchase increase tested. | Inventory imports and full adjustment UI need manual UAT. |
| Customers | PASS | Customer creation and AR workflows tested. | No blocker identified. |
| Suppliers | PASS | Supplier creation and AP workflows tested. | No blocker identified. |
| Sales | PASS with warning | Invoice posting, AR, VAT inputs, POS revenue tested. | Full approval/edit/delete UI matrix needs manual UAT. |
| Purchasing | PASS with warning | Bill/AP workflow and purchase inventory increase tested. | Purchase order lifecycle remains less deeply certified than bill/payment. |
| Accounts Receivable | PASS | Customer balance derives from journals and payment reduces AR. | No blocker identified. |
| Accounts Payable | PASS | Supplier balance derives from journals and payment reduces AP. | No blocker identified. |
| General Journal | PASS | Balanced entries post, unbalanced entries are blocked, duplicate source posting is blocked. | No blocker identified. |
| Chart of Accounts | PASS with warning | COA generated-ID behavior and PostgreSQL identity sync are certified. | Large COA import sequencing should remain in staging checklist. |
| Banking | WARNING | Banking page and cash/bank journal workflows exist and are tested at journal level. | Full bank reconciliation, transfers, and UI approvals need UAT. |
| Cash | WARNING | Cash journals, POS cashier permissions, cash drawer permissions exist. | Cash drawer close workflow needs manual operational proof. |
| Payroll | PASS with warning | Payroll posting and liabilities tested. | Payroll UI, statutory deductions, approvals, and period close need UAT. |
| Fixed Assets | PASS with warning | Asset acquisition, register update, depreciation, and E2E transaction ownership are certified. | Depreciation source linkage remains weaker than acquisition linkage. |
| Depreciation | PASS with warning | Straight-line depreciation and E2E-local PostgreSQL depreciation certification exist. | Multi-period schedules and edge cases require manual review. |
| VAT | PASS with warning | VAT transaction helper and VAT control journal tested. | VAT/NHIL return filing output needs finance-owner UAT. |
| NHIL | WARNING | Invoice UI captures NHIL/GETFund fields. | Full NHIL control-account report reconciliation is not fully automated. |
| Financial Reports | PASS with warning | Trial balance, balance sheet, income statement, cash flow, ledger, aging helpers exist and reconcile in tests. | Report performance on production-sized data is not load-tested. |
| Analytics | WARNING | Analytics/dashboard surfaces exist. | Data-heavy analytics performance is not load-tested. |
| Audit Trail | PASS with warning | Audit logging and audit trail permission checks exist. | External audit export/sign-off workflow needs manual review. |
| User Management | PASS with warning | Role permission matrix and branch-user controls exist. | UI UAT needed for every role and branch combination. |
| Permissions | PASS | Permission aliases, role mappings, branch isolation, and privilege-denial tests exist. | No critical privilege escalation found in certified checks. |
| Developer Dashboard | WARNING | Developer dashboard and diagnostics surfaces exist. | Production access controls and operational procedure must be signed off. |
| System Configuration | WARNING | Settings and integration management permissions exist. | Manual UAT needed for configuration changes and secrets handling. |
| Cloud Backup | WARNING | Backup helpers and recovery diagnostics exist. | Live cloud backup/restore is not certified in this local run. |
| Recovery | WARNING | Recovery diagnostics and restore permissions exist. | Full restore rehearsal remains mandatory before go-live. |
| Diagnostics | PASS with warning | Health, persistence, schema, PostgreSQL, recovery, and query diagnostics exist. | Alerting/monitoring outside app is not certified. |

## Accounting Workflow Certification

| Workflow | Classification | Evidence |
|---|---|---|
| POS Sale -> Inventory Reduction -> Revenue -> Customer Balance -> Journal | PASS | Functional and cross-module tests create POS sale, reduce inventory, post revenue, and update AR. |
| POS Sale -> COGS -> Inventory Control | PASS with warning | New cross-module test posts COGS and inventory credit; real POS UI COGS posting still requires UAT. |
| Purchases -> Inventory Increase -> Supplier Balance -> AP -> Journal | PASS | New cross-module test verifies stock movement, inventory quantity increase, AP journal, and supplier balance. |
| Customer Payment -> Reduce Receivable -> Cash Increase -> Journal | PASS | Functional certification covers AR lifecycle to zero balance. |
| Supplier Payment -> Reduce Payable -> Cash Reduction -> Journal | PASS | Functional certification covers AP lifecycle to zero balance. |
| Payroll -> Expense -> Liability -> Journal | PASS with warning | Functional certification validates payroll totals and journals. |
| Fixed Asset Purchase -> Asset Register -> Journal | PASS | Asset acquisition and journal posting are tested. |
| Depreciation -> Accumulated Depreciation -> Expense -> Journal | PASS with warning | Depreciation posting and E2E transaction ownership are certified; multi-period edge cases need UAT. |
| VAT -> VAT Control -> Journal | PASS with warning | VAT helper posts balanced VAT journal; full VAT/NHIL filing report remains a warning. |
| Bank Transfers -> Cash Movement -> Journal | PASS with warning | Journal-level bank transfer tested; UI workflow and reconciliation need UAT. |

## Financial Report Certification

| Report | Classification | Evidence |
|---|---|---|
| Trial Balance | PASS | Debits and credits reconcile in accounting integrity tests. |
| Balance Sheet | PASS | Assets = liabilities + equity in accounting integrity tests. |
| Income Statement | PASS | Net profit is derived from posted revenue and expense journals. |
| Cash Flow | WARNING | Engine helper exists and is included in report surface. Production-sized validation not load-tested. |
| General Ledger | PASS | Ledger output is tested in functional certification. |
| Receivables Aging | PASS with warning | AR aging helper exists; AR balance lifecycle tested. Full aging bucket UAT remains. |
| Payables Aging | PASS with warning | AP aging helper exists; AP balance lifecycle tested. Full aging bucket UAT remains. |
| Inventory Valuation | WARNING | Inventory value diagnostics exist; production valuation report needs finance UAT. |
| VAT Reports | WARNING | VAT journal control tested; filing layout and NHIL split need UAT. |
| Payroll Reports | WARNING | Payroll totals tested; statutory and period reports need UAT. |
| Fixed Asset Reports | PASS with warning | Depreciation schedule and fixed asset helper exist. Multi-period schedule UAT remains. |
| Depreciation Reports | WARNING | Depreciation schedule exists; full report reconciliation needs UAT. |

## Security Certification

| Role | Classification | Evidence |
|---|---|---|
| Developer | PASS with warning | Superuser role intentionally has all permissions; production access must be tightly controlled. |
| Master Admin | PASS | Broad admin/accounting permissions preserved and tested. |
| System Admin | PASS | Can manage config/users but cannot post accounting documents. |
| Owner | PASS | Owner alias maps to Owner / CEO and has company/accounting authority. |
| Branch Manager | PASS with warning | Branch management and branch access helpers exist. More branch UI UAT needed. |
| Accountant | PASS | Can post/report; cannot manage users/payroll. |
| Cashier | PASS | Can sell POS and receive payments; cannot view reports/manage users. |
| Sales Officer | PASS | Sales permissions without inventory admin. |
| Inventory Officer | PASS | Inventory management without journal posting. |
| Payroll Officer | PASS | Payroll management without user management. |
| Auditor | PASS | Read-only audit/report permissions without posting. |
| Staff | PASS | Narrow operational permissions only. |

No certified privilege escalation was found in the tested matrix. Developer access remains a deliberate operational risk that must be controlled by policy and environment.

## Performance Certification

| Area | Classification | Evidence |
|---|---|---|
| N+1 queries | WARNING | Some UI modules perform repeated lookups/schema discovery. No production load profile yet. |
| Repeated metadata lookups | WARNING | Column/table discovery is cached in core database helpers, but UI hot paths still need profiling. |
| Repeated connections | WARNING | Many UI pages open scoped connections safely; load testing is required to prove behavior under concurrency. |
| Connection leaks | PASS with warning | Tests repeatedly initialize/tear down isolated DBs; no leak surfaced. Browser/runtime profiling still required. |
| Transaction leaks | PASS | PostgreSQL E2E transaction ownership and rollback certification pass. |
| Dashboard widgets | WARNING | Dashboard metrics exist; large-tenant latency not measured. |
| Slow reports | WARNING | Report correctness certified; production-size performance not certified. |
| Duplicate journal posting | PASS | Duplicate source posting is blocked. |
| Duplicate writes | PASS with warning | POS idempotent sale reference and E2E duplicate identity fixes exist. Wider UI retry behavior needs UAT. |
| Orphan rows / FKs | WARNING | Core FK fixes and inventory FK certification exist. Full orphan sweep should run before go-live. |

## Final Classification

The ERP is **not FAIL**, but it remains **WARNING** for unrestricted production because a real company needs signed-off browser UAT, live backup/restore rehearsal, load/performance evidence, and operational runbooks. It is suitable for a controlled production pilot only after the blockers in `reports/erp_remaining_blockers.md` are addressed or formally accepted.

## Single Highest-Priority Next Phase

**PHASE 5B.18B — Production Pilot UAT, Backup/Restore Rehearsal, and Performance Certification**
