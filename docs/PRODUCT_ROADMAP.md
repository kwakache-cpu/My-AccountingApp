# Product Roadmap

Execution roadmap for EKA Enterprise Platform.  
This is a **sequence**, not a date commitment. Phases complete when quality gates pass — not when calendars flip.

For governance and principles, see `EKA_CONSTITUTION.md` and `PROJECT_PRINCIPLES.md`.

---

## Roadmap Summary

| Phase | Name | Focus |
|-------|------|-------|
| **1** | Perfect Core Platform | Reliable daily operations, dual-backend, regression-stable |
| **2** | Business Intelligence | Owner-facing signals inside workflows |
| **3** | Workflow Excellence | End-to-end flow polish and automation |
| **4** | Enterprise Scale | Multi-branch scale, performance, ops maturity |
| **5** | Industry Packs | Vertical templates on proven core |

---

## Phase 1 — Perfect Core Platform *(current)*

**Goal:** Make the core platform fast, correct, and trustworthy for daily business operations.

### Scope

- Login, logout, session safety
- PostgreSQL runtime + SQLite fallback
- Company registration, trial, Paystack subscription
- Dashboard first render (deferred heavy work)
- POS sale and controlled correction
- Financial Reports lazy loading
- System Configuration without UI DDL
- Staff/roles/permissions
- Migration cleanup admin-only
- Regression lockdown (706+ tests)

### Exit criteria

- All regression lockdown workflows pass
- Performance budgets met on representative datasets
- No client-page diagnostics
- Accounting reconciliation tests green
- Cutover/startup safety preserved

### Explicitly not Phase 1

- Industry Packs
- Broad UI redesigns
- Speculative performance rewrites

---

## Phase 2 — Business Intelligence

**Goal:** Help owners and managers decide faster inside the platform.

### Scope

- Executive KPI clarity on dashboard
- Receivable/payable intelligence (on-demand, fast)
- Margin and cash visibility
- Subscription/revenue signals (platform admin)
- Plain-language insights, not raw data dumps

### Principles

- Intelligence appears in workflow context
- No admin-only diagnostics on client pages
- Measure query cost before adding BI widgets

---

## Phase 3 — Workflow Excellence

**Goal:** End-to-end flows feel inevitable — minimal steps, minimal confusion.

### Scope

- Order to Cash polish
- Purchase to Pay polish
- Inventory lifecycle continuity
- Customer and supplier journey coherence
- Payroll and asset workflow refinement
- Year-end closing guided experience

### Principles

- Workflow over modules
- Every step must explain itself
- Controlled corrections remain the norm

---

## Phase 4 — Enterprise Scale

**Goal:** Support larger deployments without sacrificing simplicity for small businesses.

### Scope

- Multi-branch performance at scale
- PostgreSQL query optimization (measured)
- Backup/restore and ops maturity
- Deeper admin observability (admin surfaces only)
- Process warmup and caching discipline

### Principles

- Measure before optimizing
- Preserve SQLite for dev/safe fallback
- Never weaken cutover guards

---

## Phase 5 — Industry Packs

**Goal:** Vertical acceleration **on top of** an exceptional core.

### Scope (examples)

- Retail Pack — POS defaults, promotions, retail reports
- Manufacturing Pack — BOM, production, WIP
- Services Pack — projects, milestones, time billing
- Construction Pack — jobs, retention, progress billing

### Entry criteria (must all be true)

- Phase 1 exit criteria still met
- Core workflows benchmarked and stable
- Regression suite covers pack boundaries
- No fork of accounting engine per industry

### Why last

Industry Packs multiply edge cases. A weak core cannot carry vertical complexity. See `EKA_ARCHITECTURE_MANUAL.md`.

---

## Cross-Phase Rules (all phases)

- Read `AGENTS.md` before code changes
- Run regression checklist before merge
- Append architectural decisions to `DECISION_LOG.md`
- No DDL during UI rendering — ever
- No diagnostics on client pages

---

## Related Artifacts

| Artifact | Location |
|----------|----------|
| Regression manifest | `reports/regression_lockdown_manifest.md` |
| Performance audit | `reports/lv009_performance_forensic_audit.md` |
| Decision log | `docs/DECISION_LOG.md` |

---

*Product Roadmap — phased execution plan for EKA Enterprise Platform.*
