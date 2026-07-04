# EKA Architecture Manual

Technical orientation for EKA Enterprise Platform.  
This document describes **how the platform is structured** and **why**.

For day-to-day engineering rules, see `DEVELOPER_RULES.md`.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Streamlit UI Layer                       │
│  app.py  ·  modules.py (pages/workflows)  ·  financials.py │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Enterprise Services Layer                    │
│  enterprise_services.py — health, ops console, admin snapshots │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Accounting Engine                           │
│  accounting_engine.py — posting, periods, ledger integrity   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Database & Startup Layer                    │
│  database.py — SQLite/PostgreSQL, migrations, cutover safety   │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Platform

The Core Platform is the shared foundation all workflows depend on:

| Component | Responsibility |
|-----------|----------------|
| **Authentication & session** | Access keys, roles, branch context, secure logout |
| **Company & branch model** | Multi-tenant companies, branch deployment, licensing |
| **Startup pipeline** | Canonical DB init, backend selection, cutover guards |
| **Permissions** | Role gates on every sensitive operation |
| **Audit logging** | Actions, corrections, admin events |

**Rule:** Core Platform behavior is protected by regression lockdown. Changes require tests.

---

## Accounting Engine

**Module:** `accounting_engine.py`

Responsibilities:

- Chart of accounts resolution
- Journal entry posting with source linkage
- Period controls and lock behavior
- Trial balance, balance sheet, and report inputs
- Reversal/void discipline (controlled, auditable)

**Non-negotiable:** Posting logic changes require explicit approval, tests, and decision-log entry. Never casual refactors.

---

## Inventory & Item Engine

**Primary surfaces:** `modules.py` (inventory, POS, purchasing)

Responsibilities:

- Item master, barcode, expiry, branch stock
- Stock movements tied to commercial documents
- POS line capture and sale persistence
- Cost/COGS linkage to accounting where applicable

Inventory quantity and GL must remain reconcilable.

---

## Workflow Engine

EKA does not yet expose a separate workflow engine service. **Workflow behavior is implemented as coordinated UI + service functions** across `modules.py`, `accounting_engine.py`, and `database.py`.

Workflow patterns:

- Validate → persist source document → post accounting impact → audit
- Controlled correction instead of destructive edit
- Permission check at every write boundary

Future Workflow Excellence phase may introduce explicit workflow orchestration; until then, preserve existing flow integrity.

---

## Notification Engine

Current state: operational messages via Streamlit UI (success/warning/info), audit logs, and system health surfaces.

Future direction: structured notifications (email, SMS, in-app) tied to workflow events (low stock, overdue receivables, subscription expiry).

**Do not** block core workflows on notification infrastructure that is not yet implemented.

---

## Security Layer

| Layer | Implementation |
|-------|----------------|
| Authentication | Access keys, company/branch/user resolution |
| Authorization | `require_permission`, role matrices in `modules.py` |
| Error sanitization | `security_utils.py` — `build_user_safe_error`, `sanitize_error_message` |
| Admin diagnostics gating | `can_view_runtime_admin_diagnostics`, surface checks |
| Startup/cutover guards | PostgreSQL activation evidence, backend diagnostics |

Client pages must never render admin diagnostics or raw database exceptions.

---

## AI Layer

Optional OpenAI integration for assistant features. AI is **assistive**, not authoritative:

- AI must not post accounting entries without explicit user action
- AI health/diagnostics remain admin-side
- API keys via secrets/environment only

---

## Performance Layer

Performance strategies already in production:

| Area | Pattern |
|------|---------|
| Financial Reports | Lazy report selection, shared ledger snapshot, lazy CSV |
| Dashboard | Deferred AR/AP aging, cached analytics bundle |
| Startup | Process warmup once per deploy, session reuse |
| PostgreSQL | Session connection reuse (LV-008), query timing hooks |
| Admin surfaces | Lazy migration cleanup load, fast vs full health audit split |

**Measure before optimizing.** See performance budgets in `AGENTS.md`.

---

## Database Dual-Backend Model

EKA supports **SQLite** (local/dev/safe fallback) and **PostgreSQL** (production/Supabase).

| Concern | Location |
|---------|----------|
| Backend selection | `database.py` startup diagnostics |
| Portable SQL | `execute_portable_query`, `execute_portable_write` |
| Schema migrations | Startup pipeline, idempotent integrity helpers |
| Cutover safety | Runtime guards, missing-evidence checks |

Never remove either backend. Never run DDL during UI page render.

---

## Future Industry Packs

Industry Packs are **intentionally deferred** until the Core Platform is exceptional.

### Why defer?

1. **Industry features multiply edge cases** — a weak core becomes unmaintainable.
2. **Workflow quality matters more than vertical labels** — Order to Cash must be flawless before "Retail Pack" branding.
3. **Regression surface explodes** — each pack adds permutations on posting, inventory, and permissions.
4. **Platform credibility** — users trust EKA when daily operations are fast, correct, and simple.

### What Industry Packs will be

Configuration + workflow templates + report packs + optional fields layered **on top of** the core — not forks of accounting logic.

Examples (future):

- Retail: barcode-heavy POS defaults, promo workflows
- Manufacturing: BOM, WIP, production orders
- Services: project billing, milestone revenue
- Construction: job costing, retention

**Until Phase 5:** Do not implement Industry Packs at the expense of core regression stability.

---

## Key File Map

| File | Role |
|------|------|
| `app.py` | App shell, login, routing, Gatekeeper dashboard |
| `modules.py` | Business modules, POS, inventory, setup, admin helpers |
| `financials.py` | Financial reports UI and report caching |
| `accounting_engine.py` | Ledger posting and accounting rules |
| `database.py` | Connections, startup, migrations, portability |
| `enterprise_services.py` | Operations console, health snapshots |
| `migration_cleanup.py` | Admin-only migration data cleanup |
| `security_utils.py` | Safe error handling |

---

## Related Documents

- `PROJECT_PRINCIPLES.md` — product design principles
- `WORKFLOW_LIBRARY.md` — business workflow definitions
- `REGRESSION_LOCKDOWN.md` — protected behaviors
- `DECISION_LOG.md` — architectural decisions

---

*EKA Architecture Manual — platform structure and rationale.*
