# Program A — Core Platform Certification

**Date:** 2026-07-07  
**Type:** Independent production-readiness assessment  
**Product:** EKA Enterprise ERP (Business Operating Platform)  
**Assessor lens:** Accountant · Cashier · Storekeeper · Owner · Auditor · Payroll · Admin · Ghana SME  
**Method:** Governance docs, workflow traces, functional certification, regression tests, sprint reports, code-path review — **no code changes**

---

## Executive Verdict

**CERTIFIED WITH CONDITIONS**

EKA is a **real ERP with a real accounting core** — not a prototype. It is **not** yet safe for unsupervised multi-site enterprise rollout. Suitable for a **controlled pilot** with trained operators who understand documented gaps.

---

## Section 1 — Business Lifecycle

See `program_a_business_readiness_scorecard.md` for the full PASS/PARTIAL/FAIL matrix.

**Headline:** Every stage is reachable inside EKA. None of the PARTIAL stages are show-stoppers for a supervised 5-person pilot; all become material at 20+ people without remediation.

**Critical friction points:**

1. **Purchases → Inventory** — two-step mental model (bill then receive).
2. **Month-end** — tools exist; guided close does not.
3. **VAT** — readable but not filing-certified.
4. **Backup** — exists; restore not rehearsed.

---

## Section 2 — Workflow Certification

### Order to Cash

| Field | Detail |
|-------|--------|
| **Purpose** | Sell goods/services, recognize revenue, collect cash, reconcile AR |
| **Implementation** | POS (`show_pos`), Create Invoice, Receive Payment, customer balances, dashboard defer |
| **Missing steps** | Invoice→payment shortcut; overdue proactive alerts; credit limit enforcement |
| **User pain** | Duplicate invoice UIs; credit customer selection in POS; returns workflow not obvious |
| **Business risks** | Legacy payment form may omit `customer_id`; AR aging vs counterparty drift on old rows |
| **Certification** | **PARTIAL** |

### Purchase to Pay

| Field | Detail |
|-------|--------|
| **Purpose** | Record supplier obligation, receive goods, pay supplier, reconcile AP |
| **Implementation** | Create Bill (`show_create_bill_page`), supplier payment, `build_purchase_journal_lines`, inventory receive (separate) |
| **Missing steps** | Bill-to-receive linkage; three-way match; purchase order concept |
| **User pain** | "I posted the bill — where is my stock?" (mitigated by Sprint 3 text, not function) |
| **Business risks** | GL Inventory asset vs empty warehouse; auditor finds physical count ≠ books |
| **Certification** | **PARTIAL** |

### Inventory

| Field | Detail |
|-------|--------|
| **Purpose** | Track qty, cost, expiry, movements, valuation |
| **Implementation** | Item master, receive, adjust, import, POS decrement, invoice stock effects |
| **Missing steps** | Unified `stock_movements` on all channels; valued receive → GL; branch transfer certification |
| **User pain** | Three decrement patterns; low-stock only visible on inventory page |
| **Business risks** | Shrinkage invisible on POS path; expiry sold if not enforced at checkout (partially enforced) |
| **Certification** | **PARTIAL** |

### Payroll

| Field | Detail |
|-------|--------|
| **Purpose** | Calculate Ghana payroll, post expenses/liabilities, pay employees |
| **Implementation** | `show_payroll`, SSNIT/PAYE/net salary journal lines, payslip display |
| **Missing steps** | Employee master HR link; PAYE band tests; bank file export; statutory filing format |
| **User pain** | Payroll officer may lack taxation view; correction path unclear |
| **Business risks** | Wrong PAYE if bands change without test coverage; finance sign-off not obtained |
| **Certification** | **PARTIAL** |

### Fixed Assets

| Field | Detail |
|-------|--------|
| **Purpose** | Register assets, depreciate, reconcile to GL |
| **Implementation** | Asset register, acquisition types, depreciation run, schedule report |
| **Missing steps** | Disposal; revaluation; full source linkage certification |
| **User pain** | Assets disconnected from dashboard; acquisition from bill not automatic |
| **Business risks** | Depreciation posted but weak document trace for audit |
| **Certification** | **PARTIAL** |

### Bank Reconciliation

| Field | Detail |
|-------|--------|
| **Purpose** | Match bank statement to ledger cash/bank |
| **Implementation** | `get_bank_reconciliation` display in banking expander — read-only |
| **Missing steps** | Statement import; match/unmatch; reconciliation report; period sign-off |
| **User pain** | Bookkeeper expects QuickBooks-style recon; gets a list |
| **Business risks** | Undetected cash errors; month-end cash cert impossible in-product |
| **Certification** | **NOT READY** |

### Cash Management

| Field | Detail |
|-------|--------|
| **Purpose** | Record cash/bank/mobile movements, transfers, loans |
| **Implementation** | Banking page, granular permissions, journal posting |
| **Missing steps** | Petty cash workflow; daily cash count; Mobile Money POS isolated test |
| **User pain** | Many transaction types on one page |
| **Business risks** | Low — journal path certified |
| **Certification** | **READY** (journal layer) / **PARTIAL** (operational cash ops) |

### VAT / NHIL / GETFund

| Field | Detail |
|-------|--------|
| **Purpose** | Track output/input tax, settle liabilities, support GRA compliance |
| **Implementation** | Control accounts, `show_taxation`, sales tax journal builders, Sprint 2 permissions |
| **Missing steps** | Filing format; settlement workflow certification; resolve journal vs statutory delta |
| **User pain** | Two numbers shown — which do I file? |
| **Business risks** | Incorrect tax return if user picks wrong column |
| **Certification** | **PARTIAL** |

### General Journal

| Field | Detail |
|-------|--------|
| **Purpose** | Manual adjusting entries with controls |
| **Implementation** | Journal entry UI, balance validation, period lock, posting permission |
| **Missing steps** | Templates for common adjustments |
| **User pain** | Account picker without usage hints |
| **Business risks** | Low — well tested |
| **Certification** | **READY** |

### Period Closing

| Field | Detail |
|-------|--------|
| **Purpose** | Lock periods, prevent casual backdating, produce final reports |
| **Implementation** | `close_period`/`lock_period` permissions, operational date controls |
| **Missing steps** | Guided close checklist; lock status dashboard widget |
| **User pain** | Owner may not know period is open until post fails |
| **Business risks** | Backdated entries if override granted too broadly |
| **Certification** | **PARTIAL** |

### Receivables

| Field | Detail |
|-------|--------|
| **Purpose** | Track who owes money, collect, age debt |
| **Implementation** | AR from invoices/POS credit, receipts, aging helpers, dashboard defer |
| **Missing steps** | Statement of account; collection workflow; dunning |
| **User pain** | Must navigate to receive payment manually |
| **Business risks** | Legacy payment rows without customer_id |
| **Certification** | **PARTIAL** |

### Payables

| Field | Detail |
|-------|--------|
| **Purpose** | Track what business owes, pay suppliers, age creditors |
| **Implementation** | Bills, supplier payments, AP aging |
| **Missing steps** | Payment run batch; supplier statement |
| **User pain** | Same as AR for navigation |
| **Business risks** | Legacy payment rows without supplier_id |
| **Certification** | **PARTIAL** |

### POS

| Field | Detail |
|-------|--------|
| **Purpose** | Fast checkout, stock check, receipt |
| **Implementation** | Barcode, cart, checkout, journal post, inventory decrement |
| **Missing steps** | `stock_movements`; posting permission enforcement; held carts |
| **User pain** | Gatekeeper naming elsewhere; scanner mode setup |
| **Business risks** | **P0-5** Cashier posts GL; concurrent SQLite locks |
| **Certification** | **PARTIAL** |

### User Administration

| Field | Detail |
|-------|--------|
| **Purpose** | Staff, roles, branches, access keys |
| **Implementation** | Staff management, permission matrix, branch module grants |
| **Missing steps** | Role template picker; self-service password reset |
| **User pain** | 15+ roles — which to pick? |
| **Business risks** | Over-permissioning Owner defaults |
| **Certification** | **READY** |

### Subscription

| Field | Detail |
|-------|--------|
| **Purpose** | Trial, Paystack pay, license activation |
| **Implementation** | Registration, verify, subscription status |
| **Missing steps** | Webhook test harness; expiry UX consistency |
| **User pain** | Renewal block vs sidebar message mismatch |
| **Business risks** | Paid but inactive if verify missed |
| **Certification** | **READY** (core path) / **PARTIAL** (edge cases) |

### Company Recovery

| Field | Detail |
|-------|--------|
| **Purpose** | Restore from backup after failure |
| **Implementation** | Cloud backup download, restore helpers, recovery mode |
| **Missing steps** | Live rehearsal; documented RTO |
| **User pain** | Admin-only; scary diagnostics nearby |
| **Business risks** | Untested restore = false confidence |
| **Certification** | **PARTIAL** |

### Cloud Backup

| Field | Detail |
|-------|--------|
| **Purpose** | Off-site data protection |
| **Implementation** | Firebase upload paths, backup metadata |
| **Missing steps** | Automated schedule visibility for client admin; restore drill |
| **User pain** | Unclear if last backup succeeded |
| **Business risks** | Data loss |
| **Certification** | **PARTIAL** |

---

## Section 3 — Role Review

| Role | Daily work? | Too much? | Too little? | Confusing? | Missing? |
|------|-------------|-----------|-------------|------------|----------|
| **Dev** | Yes (platform) | Full access appropriate | — | Gatekeeper vs client AI naming | — |
| **Master Admin** | Yes | Broad — intentional | — | Overlaps Owner | — |
| **Owner / CEO** | Yes | Can post, close, correct | — | Menu size | Executive KPI plain language |
| **Accountant** | Yes | Appropriate | — | Duplicate bill paths | Bank recon |
| **Bookkeeper** | Yes | Cannot void/close — good | Cannot manage taxation settlement | vs Branch Manager overlap | Period close visibility |
| **Cashier** | Mostly | **Posts GL via POS without posting permission** | No reports — good | Returns/corrections hidden | Hold/recall sale |
| **Sales Officer** | Partial | — | No POS? (has sell) | Role boundary vs Cashier | CRM pipeline |
| **Inventory Officer** | Yes | — | No accounting — good | Receive vs bill disconnect | Transfer certification |
| **HR / Payroll** | Yes | Posts payroll | No taxation view | — | Employee HR master |
| **Branch Manager** | Yes | Posts but cannot void | — | vs Bookkeeper | Branch P&L default |
| **Auditor / Read Only** | Yes | Read-only enforced | No manage taxation — good | COA via view_reports | Export pack |
| **Staff** | Limited | POS only — OK | — | — | — |
| **Demo** | N/A | — | By design | — | — |
| **Sub-Admin** | Yes | High | — | vs Master Admin | — |
| **System Admin** | Config only | Narrow — good | No accounting — intentional | — | — |

---

## Section 4 — Ghana SME Readiness

| Vertical | Rating | Why |
|----------|--------|-----|
| **Retail shop** | Mostly Ready | POS + inventory + VAT; single location SQLite OK |
| **Provision store** | Mostly Ready | Barcode, expiry, low stock; bill/receive training needed |
| **Frozen foods** | Needs Work | Expiry critical — enforced at POS but batch/trace weak |
| **Pharmacy** | Needs Work | Batch, regulatory trace, NHIS — not in core |
| **Wholesaler** | Mostly Ready | Bulk inventory, AP; multi-location needs Postgres |
| **Electronics shop** | Mostly Ready | Serial/warranty tracking absent but workable |
| **Feed mill** | Needs Work | Manufacturing/BOM deferred; inventory alone insufficient |
| **Small manufacturer** | Needs Work | No BOM, WIP, production orders (Phase 5) |
| **Restaurant** | Needs Work | Recipe/portion costing, table service — not core |
| **Pig farm** | Needs Work | Livestock/batch costing — industry pack territory |

**Ghana-specific positives:** GHS default, VAT/NHIL/GETFund, Paystack, Mobile Money payment method, SSNIT/PAYE payroll lines.

**Ghana-specific gaps:** GRA filing format, NHIS, mobile money reconciliation, withholding on suppliers, e-VAT integration.

---

## Section 5 — Accounting Certification

**Overall: Needs Work** (core GL approaching Enterprise Ready; compliance layer not)

| Area | Verdict | Notes |
|------|---------|-------|
| Posting integrity | Enterprise Ready | Balanced entries, source linkage, void discipline |
| Trial Balance | Enterprise Ready | Certified; reporting trust checks |
| Journal | Enterprise Ready | Manual + system entries |
| Financial Statements | Enterprise Ready | TB, IS, BS, CF, equity |
| Cash Book | Enterprise Ready | Banking journal integration |
| VAT | Needs Work | Dual calculation paths |
| Receipts | Needs Work | Sprint 1 fixed primary; legacy gaps |
| Supplier Payments | Needs Work | Same as receipts |
| Corrections | Enterprise Ready | Controlled, audited |
| Period Locks | Needs Work | Logic exists; UAT open |
| Audit Trail | Needs Work | Uneven `log_audit_action` coverage |

---

## Section 6 — User Experience

### Where users become confused

- Bill posted but stock unchanged
- "Received" on bill = payment, not goods
- Two places to create invoices/bills
- Taxation page shows two balance columns
- Gatekeeper vs Business Assistant naming
- Chart of Accounts visible to report viewers

### Unfinished screens

- Bank reconciliation (read-only)
- Analytics page (thin coverage)
- Accounts Payable legacy form
- Post-registration welcome (missing)

### Terminology improvements

| Current | Suggested |
|---------|-----------|
| Gatekeeper Admin (client) | Business Assistant |
| Payment Status: Received | Payment Settled |
| Posting State | Accounting Status |
| LV* internal names | Never user-visible (already mostly hidden) |

### Too many clicks

- Invoice → payment (no shortcut)
- Dashboard AR → customer detail
- Low stock → receive (partially addressed via action center)

### Missing

- In-app onboarding checklist
- Notification center
- Statement of account (customer/supplier)
- Guided month-end close

---

## Section 7 — Competitive Review

### Where EKA is already better

- **Unified platform ambition** — POS + inventory + GL in one product (vs QuickBooks + add-on)
- **Ghana-first tax scaffolding** — NHIL/GETFund native (vs generic international tools)
- **Regression depth** — 717+ tests unusual at SME tier
- **Controlled corrections** — audit-friendly vs silent edit culture in smaller tools
- **Dual-backend portability** — serious engineering for African deploy realities
- **Permission granularity** — finer than Manager.io / many Zoho tiers
- **No per-module pricing trap** — single platform (commercial model aside)

### Where EKA is behind

- **Purchase-to-pay completeness** — Odoo, SAP B1, Zoho have PO→GRN→bill match
- **Bank reconciliation** — QuickBooks, Xero, Sage mature
- **Payroll compliance packaging** — Tally, local Ghana payroll tools more filing-ready
- **UX polish** — Zoho, QuickBooks smoother onboarding
- **Mobile apps** — competitors have native mobile; EKA is Streamlit web
- **Ecosystem / integrations** — banks, GRA, NHIS APIs absent
- **Notifications** — all majors have alerts; EKA has none

### What should NEVER be copied

- QuickBooks **silent auto-categorization** without audit trail
- Odoo **module sprawl** without workflow ownership
- SAP B1 **implementation complexity** exposed to end users
- Tally **keyboard-era UX** transplanted to web without simplification
- Sage **perpetual duplicate entity models** (customer in 3 places)
- Manager.io **over-simplified GL** that breaks at VAT audit
- Zoho **feature gating** that splits inventory from accounting mid-workflow

### Ideas worth adapting

- **Zoho:** invoice payment allocation UX in one screen
- **Odoo:** optional receive-on-bill for inventory (not full Odoo complexity)
- **QuickBooks:** bank feed matching pattern (when API available)
- **Tally:** statutory report layouts familiar to Ghana accountants
- **Xero:** plain-language cash summary on dashboard
- **SAP B1:** approval workflow concept (future, lightweight)

---

## Section 8 — Top 100 Improvements

See `program_a_top_100_recommendations.md` for the full ranked list with P0–P3, business value, risk, complexity, and dependencies.

---

## Section 9 — Certification Scorecard

See `program_a_business_readiness_scorecard.md`.

---

## Section 10 — Go / No-Go

See `program_a_go_no_go_assessment.md`.

| Business size | Decision |
|---------------|----------|
| 5-person | CONDITIONAL GO |
| 20-person | NO-GO |
| 100-person | NO-GO |

---

## Certification Statement

As independent assessor, I certify that EKA Enterprise ERP **Core Platform**:

- **Meets** the bar for a **supervised pilot** with documented limitations.
- **Does not meet** the bar for unrestricted production, multi-site scale, or statutory filing without finance sign-off.

**Final grade: CERTIFIED WITH CONDITIONS**

---

*Program A Core Platform Certification — 2026-07-07*
