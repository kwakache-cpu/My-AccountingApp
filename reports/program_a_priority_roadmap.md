# Program A — Priority Roadmap

**Date:** 2026-07-04  
**Basis:** Core Platform Audit, Workflow Trace Matrix, Module Linkage Map  
**Classification:** P0 → P3 (do not implement in this audit pass)

---

## Priority Definitions

| Level | Meaning | Timing |
|-------|---------|--------|
| **P0** | Must fix before serious client rollout — data integrity, security, or blocking UX | Immediate |
| **P1** | Needed for strong SME product — workflow completeness, trust | Phase 1 completion |
| **P2** | Smart ERP enhancement — intelligence, polish, scale | Phase 2–3 |
| **P3** | Future / Industry-pack enabling — defer until core exceptional | Phase 4–5 |

---

## P0 — Must Fix Before Serious Client Rollout

| # | Item | Module(s) | Rationale | Evidence |
|---|------|-----------|-----------|----------|
| P0-1 | **Persist `customer_id` on customer payment INSERT** | AR, Banking, financials | Subledger reconciliation; payment reports; migration cleanup | Workflow trace 4; linkage map |
| P0-2 | **Persist `supplier_id` on supplier payment INSERT** | AP, Banking, financials | Same as P0-1 for payables | Workflow trace 6 |
| P0-3 | **Add taxation test suite** | Tax/VAT/NHIL | Zero test coverage on compliance module | Module audit §12 |
| P0-4 | **Add view permission gate on taxation page** | Tax | Ungated read of tax control data | Module audit §12 |
| P0-5 | **Resolve POS posting permission model** | POS, accounting_engine | Cashier posts without `post_accounting_document` when `user_role` omitted — document as intentional OR pass role | Workflow trace 1–2; permission audit |
| P0-6 | **Document bill vs inventory receive for users** | Purchases, Inventory | Users expect bill post to increase stock — causes silent inventory/GL drift | Workflow trace 5–7 |

---

## P1 — Needed for Strong SME Product

| # | Item | Module(s) | Rationale |
|---|------|-----------|-----------|
| P1-1 | **Purchase-to-Pay inventory link** — optional receive-on-post for inventory-classified bills | Bills, Inventory | Closes bill/inventory gap |
| P1-2 | **Unified stock movement ledger** — POS decrements write `stock_movements` | POS, Inventory | One movement audit trail |
| P1-3 | **Valued inventory receive prompts GL posting** when unit cost provided | Inventory | Receive without GL confuses bookkeepers |
| P1-4 | **Invoice → Receive Payment shortcut** | Sales, AR | Order-to-Cash UX |
| P1-5 | **Customer/supplier balance drill-down from dashboard** | Dashboard, AR/AP | Deferred AR/AP load should link to detail |
| P1-6 | **Payroll calculation unit tests** (SSNIT, PAYE bands) | Payroll | Compliance confidence |
| P1-7 | **Depreciation source linkage certification** | Assets | `test_postgres_final_certification` flags gap |
| P1-8 | **Chart of Accounts view permission** (`view_chart_of_accounts`) | COA | Ungated structure exposure |
| P1-9 | **Rename client AI page** ("Gatekeeper Admin" → "Business Assistant") | AI | Confusion with Dev Gatekeeper |
| P1-10 | **Post-registration welcome / first-login path** | Onboarding | Trial → first ERP session guidance |
| P1-11 | **Subscription expiry UX consistency** | Platform | Sidebar + banner + renewal block aligned |
| P1-12 | **Standardize audit logging** on all write paths | Audit | Uneven `log_audit_action` coverage |

---

## P2 — Smart ERP Enhancement

| # | Item | Module(s) | Rationale |
|---|------|-----------|-----------|
| P2-1 | **Notification engine design** — low stock, overdue AR, subscription expiry | Platform | No proactive alerts today |
| P2-2 | **Maintenance notice on current dashboard** | Dashboard | Only in legacy dashboard path |
| P2-3 | **Banking transaction wizards** per type | Banking | Reduce single-page complexity |
| P2-4 | **Guided adjusting entry templates** | Journal | Safer manual entries |
| P2-5 | **PostgreSQL financial reports benchmark in CI** | Financial Reports | Scale confidence |
| P2-6 | **Consolidate duplicate invoice/bill UI paths** | financials.py | Tabbed vs dedicated pages |
| P2-7 | **COA account usage hints** | Chart of Accounts | Self-explaining accounts |
| P2-8 | **Asset disposal workflow** | Assets | Lifecycle completeness |
| P2-9 | **Paystack webhook test harness** | Subscription | Completeness |
| P2-10 | **Plain-language tax summary on taxation page** | Tax | Non-accountant readability |
| P2-11 | **Fix Gatekeeper tab3** — wire Manual Deployment tab or remove label | Dev | UX bug |
| P2-12 | **Branch-scoped audit trail tests** | Audit | Filtering correctness |

---

## P3 — Future / Industry-Pack Enabling

| # | Item | Module(s) | Rationale |
|---|------|-----------|-----------|
| P3-1 | **Industry Packs layer** | Platform | Deferred per constitution until Phase 5 |
| P3-2 | **Workflow orchestration engine** | Platform | Explicit state machines for flows |
| P3-3 | **Email/SMS notification delivery** | Notifications | Requires engine first |
| P3-4 | **Employee master linked to payroll** | Payroll, HR | Beyond current register |
| P3-5 | **Multi-currency full workflow** | Accounting | Industry/global expansion |
| P3-6 | **Project/job costing** | Construction pack | Vertical feature |
| P3-7 | **BOM / manufacturing** | Manufacturing pack | Vertical feature |
| P3-8 | **Promo/pricing engine for retail pack** | POS | Vertical feature |
| P3-9 | **In-app notification center UI** | Platform | After notification engine |
| P3-10 | **Role template picker in System Configuration** | Setup | Broader admin self-service |

---

## Recommended Execution Order (First 90 Days)

### Sprint A — Data Integrity (P0)
1. P0-1, P0-2 — payment subledger IDs
2. P0-3, P0-4 — taxation tests + permission
3. P0-5 — POS posting permission decision
4. P0-6 — in-app help text for bill vs receive

### Sprint B — Workflow Completeness (P1 top)
5. P1-1 — bill/inventory link option
6. P1-2 — POS stock_movements
7. P1-4 — invoice payment shortcut
8. P1-7 — depreciation certification

### Sprint C — Trust & UX (P1 remainder)
9. P1-5, P1-9, P1-10, P1-11
10. P1-6, P1-8, P1-12

### Do Not Start Yet
- Industry packs (P3)
- Broad performance rewrites (measure first per AGENTS.md)
- Notification engine implementation until P2 design approved

---

## What NOT to Prioritize (Protected — Do Not Break)

These are **working and regression-locked** — improvements must not regress:

- Financial Reports lazy loading (Phase 1)
- Dashboard AR/AP deferral
- System Configuration no-DDL render
- PostgreSQL + SQLite dual backend
- Startup/cutover safety
- Migration cleanup admin-only visibility
- Client page diagnostic exclusion
- Controlled POS correction path
- Paystack trial + verify flow

---

## Priority Summary Counts

| Level | Count | Theme |
|-------|-------|-------|
| P0 | 6 | Subledger IDs, taxation tests/permissions, POS posting model, P2P documentation |
| P1 | 12 | Workflow links, movement ledger, UX, certification, permissions |
| P2 | 12 | Notifications, polish, benchmarks, consolidation |
| P3 | 10 | Industry packs, orchestration, vertical features |

---

## Alignment with Product Roadmap

| Roadmap Phase | Priority items |
|---------------|----------------|
| Phase 1 — Perfect Core Platform | **All P0 + P1** |
| Phase 2 — Business Intelligence | P2-1, P2-2, P1-5 |
| Phase 3 — Workflow Excellence | P1-1–P1-4, P2-3–P2-6 |
| Phase 4 — Enterprise Scale | P2-5, P2-12 |
| Phase 5 — Industry Packs | **All P3** |

---

*Program A Priority Roadmap — recommendations only; no code changes in this audit.*
