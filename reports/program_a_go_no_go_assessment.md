# Program A — Go / No-Go Assessment

**Date:** 2026-07-07  
**Final certification:** CERTIFIED WITH CONDITIONS  
**Assessor:** Independent ERP implementation consultant

---

## Decision Framework

EKA is judged on **workflow continuity**, **accounting correctness**, **role appropriateness**, **operational risk**, and **Ghana SME practicality** — not feature count or test count alone.

---

## Section 10 — Deployment Scenarios

### Would you deploy EKA to a 5-person business?

**Answer: CONDITIONAL GO (supervised pilot)**

| Factor | Assessment |
|--------|------------|
| Team shape | Typically Owner + 1 bookkeeper + 1–2 cashiers + 1 stockkeeper |
| EKA fit | POS, basic inventory, invoices, bills, reports cover daily needs |
| Blockers | Bill≠receive training; POS permission model; no proactive alerts |
| Infrastructure | SQLite acceptable for single-location, low concurrency |
| Conditions | Owner signs known-limitations doc; 4-hour UAT; weekly TB check; rollback owner named |

**Why yes (with conditions):** Core accounting chains work; regression depth reduces surprise breakage; Ghana tax scaffolding exists; cost of alternatives (QuickBooks + separate POS) may exceed EKA for local operator.

**Why not unconditional:** Segregation of duties gap; inventory drift risk; no executed human UAT; support model undefined.

---

### Would you deploy EKA to a 20-person business?

**Answer: NO-GO (today)**

| Factor | Assessment |
|--------|------------|
| Team shape | Multiple cashiers, branch manager, dedicated accountant, inventory officer, HR/payroll |
| EKA fit | Role matrix exists but POS posting bypass breaks control expectations |
| Blockers | SQLite concurrency; no notification engine; duplicate UI paths increase training cost |
| Infrastructure | PostgreSQL required; production cutover **NO-GO** per release decision |
| Minimum bar | P0-5 resolved; browser UAT all roles; Postgres write certification; backup rehearsal |

**Why no:** At 20 people, **segregation of duties**, **concurrent POS**, and **multi-user inventory** are non-negotiable. EKA has not demonstrated these under load or human certification.

**Path to GO:** 90-day remediation on P0-5, P1-1 (bill/inventory link), P1-2 (POS movements), Postgres pilot, executed UAT.

---

### Would you deploy EKA to a 100-person business?

**Answer: NO-GO**

| Factor | Assessment |
|--------|------------|
| Team shape | Multi-branch, audit committee, IT admin, compliance officer |
| EKA fit | Branch scoping exists; scale certification absent |
| Blockers | Performance at scale unproven; audit export timing; no workflow orchestration; industry packs deferred |
| Infrastructure | Enterprise Postgres ops, monitoring, webhook reliability, DR tested |
| Minimum bar | Phase 1 exit criteria + Phase 4 scale work + finance statutory certification |

**Why no:** Constitution targets "exceptional core" before scale. EKA is Phase 1 **in progress**, not complete. A 100-person deployment needs proven Postgres performance, notification/escalation, payroll HR integration, and auditor-grade export — all partial or missing.

---

## Sign-Off Requirements (Before Any Production Use)

| Signatory | Must confirm |
|-----------|--------------|
| **Business owner** | Accepts known workflow traps (bill≠receive, POS inventory movement) |
| **Finance owner** | TB balances; VAT/NHIL/GETFund outputs reviewed against journals |
| **Technical owner** | Backup/restore tested; secrets configured; rollback plan |
| **Operations lead** | Role matrix matches job functions; Cashier POS posting risk acknowledged or mitigated |
| **Support owner** | Escalation path, hours, data recovery contact |

---

## Deployment Mode Matrix

| Mode | Decision | Prerequisites |
|------|----------|---------------|
| Unrestricted enterprise production | **NO-GO** | Phase 1 exit + UAT + Postgres write cert |
| Controlled SQLite pilot (≤5 users, 1 branch) | **CONDITIONAL GO** | Sign-offs above; P0-5 mitigated or accepted in writing |
| PostgreSQL production cutover | **NO-GO** | Supabase backup SOP; staging rehearsal; write-path certification |
| Streamlit Cloud demo/trial | **GO** | Demo role only; no real books |
| Dev/Gatekeeper internal | **GO** | Admin surfaces only |

---

## Conditions That Must Be Met for "CERTIFIED" (Upgrade from WITH CONDITIONS)

1. **P0-5 closed** — POS respects `post_accounting_document` or documented compensating control enforced.
2. **Browser UAT ≥ 80% executed** — all operational roles with signed results.
3. **PostgreSQL write certification PASS** — supplier bill, POS, payment, payroll on Postgres in CI or staging.
4. **Backup restore rehearsal PASS** — documented RTO/RPO for pilot.
5. **Finance statutory sign-off** — VAT/NHIL/GETFund and PAYE/SSNIT outputs approved for filing use.
6. **Purchase-to-pay functional link** — at minimum optional receive-on-post for inventory bills (P1-1).
7. **Performance smoke on pilot dataset** — dashboard <3s, POS <2s, TB <5s documented.

Until all seven: remain **CERTIFIED WITH CONDITIONS**.

---

## Risk Acceptance Statement (Pilot Template)

> We accept that EKA will not automatically increase inventory when a supplier bill is posted; stock must be received separately. We accept that POS sales update quantity without a unified stock movement row. We have assigned [name] as rollback owner and [name] as finance reconciler for weekly trial balance review.

---

*Program A Go/No-Go Assessment — honest deployment guidance, not marketing.*
