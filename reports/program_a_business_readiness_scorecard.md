# Program A — Business Readiness Scorecard

**Date:** 2026-07-07  
**Certification posture:** CERTIFIED WITH CONDITIONS  
**Evidence basis:** Workflow trace matrix, functional certification, P0 sprints, regression lockdown, release decision, UAT checklists

---

## Section 1 — Business Lifecycle Matrix

Can a company run the full lifecycle **without leaving the ERP**?

| Stage | Rating | Rationale |
|-------|--------|-----------|
| **Company Registration** | **PASS** | Trial registration, duplicate name block, Paystack verify → activation tested. Webhook harness thin. |
| **Company Setup** | **PARTIAL** | System Configuration works; no DDL on render (certified). No guided first-setup wizard; branch/currency/tax defaults require knowledgeable admin. |
| **Chart of Accounts** | **PARTIAL** | COA exists; core accounts auto-ensured. View ungated via `view_reports`. No usage hints; manual opening balances error-prone. |
| **Inventory** | **PARTIAL** | Item master, barcode, expiry, receive, adjust, import exist. Sprint B P0-3 unified stock movements. Sprint B P0-4 adds valuation vs GL reconciliation (detection). Costing is last `cost_price`, not policy-grade average/FIFO. |
| **Customers** | **PASS** | Master CRUD, balances, POS/invoice linkage, AR aging helpers. |
| **Suppliers** | **PASS** | Master CRUD, balances, bill linkage, AP aging helpers. |
| **Sales** | **PARTIAL** | POS + invoice paths strong. Credit sales, returns, corrections certified. Invoice→payment shortcut missing; duplicate invoice UIs. |
| **Purchases** | **PARTIAL** | Bill creates AP/GL. **Does not receive stock.** Users must complete separate inventory receive — now documented (Sprint 3) but not linked. |
| **Payments** | **PARTIAL** | Customer receipt and supplier payment pages fixed (Sprint 1). Legacy tabbed payment form gaps remain. Banking granular permissions good. |
| **Banking** | **PARTIAL** | Cash book, transfers, loans, equity movements certified at journal level. Bank reconciliation is read-only display; no matching workflow. |
| **Payroll** | **PARTIAL** | Run, post, payslip, SSNIT/PAYE journal lines exist. No PAYE band unit tests; no employee master HR link; finance statutory sign-off open. |
| **Assets** | **PARTIAL** | Acquisition and depreciation post. Source linkage certification gap. No disposal workflow. |
| **VAT** | **PARTIAL** | Taxation page with permission gates (Sprint 2). Journal-backed balances + statutory math; reconciliation shown not resolved. GRA filing format not certified. |
| **Month End** | **PARTIAL** | Period lock/close permissions exist. No guided close checklist in-product. UAT for period close 0% executed. |
| **Financial Reports** | **PASS** | TB, P&L, BS, GL, cash flow, equity changes — lazy-loaded, regression-certified. Large-dataset Postgres timing unproven. |
| **Backup** | **PARTIAL** | Cloud backup paths exist; live restore rehearsal open (82% readiness). Operator SOP required. |
| **Audit** | **PARTIAL** | Audit log, controlled corrections, system events. Coverage uneven across write paths. High-volume export not performance-tested. |

**Lifecycle summary:** 3 PASS · 15 PARTIAL · 0 FAIL  
**Interpretation:** A disciplined operator **can** run inside EKA, but will hit friction, training needs, and reconciliation traps at purchases, inventory, month-end, and statutory tax.

---

## Section 9 — Certification Scorecard (Detail)

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Accounting** | 7.5/10 | Strong journal engine, TB integrity, source linkage. Gaps: bill/inventory GL vs physical, depreciation linkage, statutory reconciliation. |
| **Inventory** | 6.5/10 | Functional item master and receive. Sprint B P0-3 movement integrity; Sprint B P0-4 valuation/GL detection. Purchase-to-pay still not auto-linked; costing method not yet policy-grade. |
| **POS** | 7.5/10 | Fast path, barcode, stock checks, receipts. Sprint B P0-1 permission gate; Sprint B P0-3 stock_movements on sale. |
| **Payroll** | 6.5/10 | Ghana components present. Calculation tests thin; HR employee master shallow; statutory sign-off open. |
| **Assets** | 6.0/10 | Register, acquisition, depreciation work. Disposal missing; dashboard impact minimal; certification gaps on source linkage. |
| **Reporting** | 8.0/10 | Best-in-class for core financials at this stage. BI/actionable insights weak; large-scale performance unproven. |
| **Permissions** | 6.5/10 | Rich role matrix, branch scoping, regression-tested denials. POS bypass, COA view leak, some role confusion (Bookkeeper vs Branch Manager). |
| **Performance** | 6.5/10 | Phase 1 budgets met on warm paths. Dashboard, GL/TB, audit at scale unprofiled; SQLite concurrency risk. |
| **Security** | 7.5/10 | Sanitized errors, no client diagnostics, least-privilege intent. Segregation of duties gap on POS posting. |
| **Usability** | 5.5/10 | Streamlit functional but dense. Duplicate paths, terminology drift, no onboarding guide, menu sprawl. |
| **Reliability** | 7.0/10 | Regression lockdown, startup safety, controlled corrections. Backup rehearsal and Postgres write paths open. |
| **Cloud** | 6.0/10 | Firebase backup, Paystack, Streamlit deploy paths. Postgres production NO-GO; webhook gap. |
| **AI readiness** | 4.0/10 | Assistive AI exists; not workflow-integrated; naming confusion with Dev Gatekeeper; not certification-tested. |
| **Overall Architecture** | 7.5/10 | Layered, portable, governance-heavy. Monolithic modules.py; no workflow orchestration service yet. |
| **Overall Product** | **6.8/10** | Strong foundation; not yet "exceptional core" per constitution Phase 1 exit criteria. |

---

## Workflow Certification Summary

| Certification | Count | Examples |
|---------------|-------|----------|
| **READY** | 6 | Financial reports, general journal, user/roles, onboarding/Paystack, dashboard (read), banking movements (journal) |
| **PARTIAL** | 14 | Order to Cash (payment shortcut), Purchase to Pay, inventory, payroll, assets, VAT, bank recon, period close, POS (permissions) |
| **NOT READY** | 2 | Notifications/alerts, analytics page |

---

## Ghana SME Vertical Readiness (Summary)

| Vertical | Rating |
|----------|--------|
| Retail shop | Mostly Ready |
| Provision store | Mostly Ready |
| Frozen foods | Needs Work |
| Pharmacy | Needs Work |
| Wholesaler | Mostly Ready |
| Electronics shop | Mostly Ready |
| Feed mill | Needs Work |
| Small manufacturer | Needs Work |
| Restaurant | Needs Work |
| Pig farm | Needs Work |

*Detail in `program_a_core_platform_certification.md` Section 4.*

---

## Accounting Certification Summary

**Rating: Needs Work → approaching Enterprise Ready for core GL; not Enterprise Ready for statutory/compliance layer**

| Area | Status |
|------|--------|
| Posting integrity | Strong |
| Trial Balance | Certified |
| Journal | Certified |
| Financial Statements | Certified |
| Cash Book | Strong |
| VAT/NHIL/GETFund | Needs Work |
| Receipts / Supplier Payments | Partial (Sprint 1 improved) |
| Corrections | Strong (controlled) |
| Period Locks | Partial (UAT open) |
| Audit Trail | Partial (coverage uneven) |

---

*Program A Business Readiness Scorecard — companion to core platform certification.*
