# Program A — Core Platform Certification Summary

**Date:** 2026-07-07  
**Assessor role:** Independent ERP implementation consultant  
**Scope:** Core Platform readiness for real Ghana SME businesses  
**Method:** Governance review, audit synthesis, workflow trace, test evidence, code-path verification — **no code changes**

---

## Final Certification

# CERTIFIED WITH CONDITIONS

EKA Enterprise ERP has a **genuine accounting core** with strong automated regression coverage (717+ tests) and working end-to-end flows for sales, purchases (accounting layer), payments, payroll posting, assets, and financial reporting. It is **not** ready for unrestricted enterprise production or blind self-service rollout.

**Conditions for deployment:**

1. Resolve **P0-5 POS posting permission model** (Cashier can post journals without `post_accounting_document`).
2. Execute **browser UAT** across all operational roles (currently 0% executed despite checklist readiness).
3. Complete **PostgreSQL write-path certification** and backup/restore live rehearsal before Postgres production cutover.
4. Train users on **bill ≠ stock receive** and inventory movement inconsistencies (POS vs invoice).
5. Obtain **finance/statutory sign-off** for VAT/NHIL/GETFund and PAYE/SSNIT outputs.
6. Assign rollback owner, support owner, and pilot scope (SQLite single-branch recommended first).

---

## Score at a Glance

| Dimension | Score /10 |
|-----------|-----------|
| Accounting | 7.5 |
| Inventory | 5.5 |
| POS | 7.0 |
| Payroll | 6.5 |
| Assets | 6.0 |
| Reporting | 8.0 |
| Permissions | 6.5 |
| Performance | 6.5 |
| Security | 7.5 |
| Usability | 5.5 |
| Reliability | 7.0 |
| Cloud | 6.0 |
| AI readiness | 4.0 |
| Overall Architecture | 7.5 |
| **Overall Product** | **6.8** |

---

## Top 10 Strengths

1. **Journal-led accounting engine** — source-document linkage, balanced posting, trial balance integrity certified.
2. **717+ automated regression tests** — rare depth for an SME ERP at this stage.
3. **Dual SQLite/PostgreSQL backend** — portable SQL, cutover guards, startup safety pipeline.
4. **Order-to-cash accounting chain** — POS, invoice, receipt, AR lifecycle functionally connected.
5. **Controlled corrections** — permission + reason + audit; history not silently erased.
6. **Financial Reports Phase 1** — lazy loading preserved; TB, P&L, BS, GL certified.
7. **Ghana tax scaffolding** — VAT, NHIL, GETFund control accounts and taxation page with permission gates.
8. **Paystack subscription flow** — trial, verify, activation tested for platform billing.
9. **Client surface hygiene** — no admin diagnostics on POS, dashboard, inventory, reports (regression-locked).
10. **Governance discipline** — constitution, workflow library, regression lockdown, decision log — unusually mature for product stage.

---

## Top 10 Weaknesses

1. **Purchase-to-pay inventory disconnect** — bill posts Inventory GL but not physical qty; separate receive step easy to miss.
2. **POS posting permission bypass** — operational staff can post GL without `post_accounting_document`.
3. **Inconsistent inventory movement ledger** — POS decrements qty only; invoice writes `stock_movements`; receive may not post GL.
4. **Zero executed browser UAT** — no human role certification despite extensive checklists.
5. **PostgreSQL production cutover blocked** — write paths and operational rehearsal incomplete.
6. **Duplicate UI paths** — bills/invoices in both `financials.py` tabbed UI and dedicated `modules.py` pages.
7. **No notification engine** — no proactive low-stock, overdue AR, subscription, or period-close alerts.
8. **Bank reconciliation is display-only** — no certified matching workflow or tests.
9. **Statutory tax/payroll sign-off pending** — journal vs statutory math can diverge; finance owner has not certified.
10. **First-time user onboarding gap** — no guided path from registration to first sale, first bill, first report.

---

## Top 10 Fastest Wins

1. **Pass `user_role` on POS `post_journal_entry`** — closes P0-5 with minimal diff.
2. **Invoice → Receive Payment shortcut** — reduces AR collection clicks (P1-4).
3. **Dashboard AR/AP drill-down links** — deferred balances should open detail (P1-5).
4. **Rename "Gatekeeper Admin" client AI** → "Business Assistant" — reduces Dev confusion (P1-9).
5. **Chart of Accounts dedicated `view_chart_of_accounts` permission** — quick security win (P1-8).
6. **Subscription expiry banner consistency** — align sidebar, banner, renewal block (P1-11).
7. **Post-registration welcome screen** — first-login checklist (P1-10).
8. **Consolidate bill help text** to legacy AP form and tabbed purchase UI — extend Sprint 3 clarity.
9. **Execute 2-hour pilot UAT** — Cashier + Bookkeeper smoke on SQLite (unblocks confidence).
10. **Document POS inventory behavior** on POS screen — "qty updates; movement history on invoice path."

---

## Top 10 Biggest Business Risks

1. **Physical vs GL inventory drift** — books show inventory asset; warehouse empty or opposite.
2. **Segregation of duties failure** — Cashier posts journals via POS without posting permission.
3. **PostgreSQL cutover without rehearsal** — data loss or partial migration under pressure.
4. **Statutory tax filing from uncertified outputs** — GRA penalties if journal ≠ statutory view used blindly.
5. **Payment subledger gaps on legacy paths** — customer/supplier balance reports miss allocations.
6. **SQLite concurrency under multi-cashier load** — lock contention, failed checkouts at peak.
7. **Period lock bypass confusion** — users backdate without understanding override rules.
8. **Backup restore never rehearsed** — discovery of broken restore during real incident.
9. **Paystack webhook gap** — subscription state desync if verify path missed.
10. **Menu sprawl without workflow glue** — users open wrong screen (tabbed vs dedicated) and duplicate entries.

---

## Go / No-Go (Summary)

| Deployment target | Decision |
|-------------------|----------|
| 5-person business (SQLite, single branch, supervised pilot) | **CONDITIONAL GO** |
| 20-person business (multi-role, multi-cashier) | **NO-GO** until P0-5 + UAT + concurrency plan |
| 100-person business (multi-branch, Postgres) | **NO-GO** until Phase 1 exit criteria + scale certification |

---

## Report Index

| Document | Contents |
|----------|----------|
| `program_a_core_platform_certification.md` | Full Sections 1–10 (lifecycle, workflows, roles, Ghana SMEs, accounting, UX, competitive, scorecard) |
| `program_a_business_readiness_scorecard.md` | Lifecycle PASS/PARTIAL/FAIL matrix and dimension scores |
| `program_a_top_100_recommendations.md` | Ranked P0–P3 improvements with value, risk, complexity, dependencies |
| `program_a_go_no_go_assessment.md` | Deployment scenarios, conditions, sign-off requirements |
| `program_a_certification_summary.md` | This executive summary |

---

*Program A Certification — documentation only. No production code modified.*
