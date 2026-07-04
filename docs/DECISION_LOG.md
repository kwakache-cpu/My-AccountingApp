# Decision Log

Architectural and product decisions for EKA Enterprise Platform.  
**Append new decisions here.** Do not delete historical entries.

Format for new entries:

```
## Decision NNN — Title
**Date:** YYYY-MM-DD
**Status:** Accepted | Superseded | Proposed
**Context:** ...
**Decision:** ...
**Consequences:** ...
```

---

## Decision 001 — Platform Before Industry Packs

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** EKA serves multiple industries but the core platform must be stable before vertical specialization.

**Decision:** Industry Packs (Retail, Manufacturing, Services, Construction, etc.) are deferred to **Phase 5**. Phases 1–4 focus on core platform excellence, intelligence, workflow polish, and enterprise scale.

**Consequences:**
- No industry-specific forks of accounting logic
- Core regression lockdown takes priority over vertical features
- Industry features layer on configuration/templates, not separate codebases

---

## Decision 002 — Workflow Over Modules

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** ERPs often grow as disconnected menus. Users think in business flows.

**Decision:** Product and engineering prioritize **workflows** (Order to Cash, Purchase to Pay, etc.) over adding isolated modules. Every feature must map to a workflow improvement.

**Consequences:**
- `WORKFLOW_LIBRARY.md` is the canonical flow reference
- Feature proposals must state which workflow they improve
- Module boundaries remain for code organization, not product marketing

---

## Decision 003 — Performance as a Product Feature

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** Slow ERPs lose user trust. Performance work was historically reactive and unmeasured.

**Decision:** Performance is a first-class product requirement with explicit budgets (see `AGENTS.md`). Optimize only after measurement. Phase 1 Financial Reports uses lazy loading, shared connections, and deferred CSV export.

**Consequences:**
- LV forensic audits before broad optimization
- Dashboard defers AR/AP on first render
- No speculative rewrites of broad modules for speed

---

## Decision 004 — Client Simplicity Over Feature Count

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** Feature sprawl increases support burden and regression risk.

**Decision:** **Golden Rule:** complexity inside the ERP, simplicity for the user. Never trade client simplicity for feature count. Admin/diagnostic complexity stays on admin surfaces.

**Consequences:**
- No diagnostics on client pages
- No DDL during UI rendering
- Fragile widgets replaced with stable patterns on hot paths (login, registration, Gatekeeper)

---

## Decision 005 — Commercial Intelligence

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** Owners need decision support, not just record-keeping.

**Decision:** EKA evolves toward **commercial intelligence** — margin, cash, receivable/payable health, inventory signals — embedded in workflows (Phase 2), not as raw admin dumps.

**Consequences:**
- Dashboard KPIs and on-demand AR/AP are foundation
- Intelligence must respect performance budgets
- Client-visible insights use plain language

---

## Decision 006 — Business Memory

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** Businesses require auditability for tax, dispute, and governance reasons.

**Decision:** EKA preserves **business memory** through audit logs, forensic trails, and **controlled corrections** instead of silent deletes or unlogged edits.

**Consequences:**
- POS corrections require reason, permission, and audit
- Void/reversal paths are controlled and tested
- Destructive admin actions require typed confirmation

---

## Decision 007 — Dual Database Backend (SQLite + PostgreSQL)

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** Local development, safe fallback, and production PostgreSQL (Supabase) must coexist.

**Decision:** EKA maintains **first-class SQLite and PostgreSQL support**. PostgreSQL runtime requires explicit enablement and cutover safety. SQLite remains the safe fallback when runtime is disabled.

**Consequences:**
- Portable query/write helpers mandatory
- Startup backend diagnostics gate activation
- Tests must cover both paths where applicable

---

## Decision 008 — No DDL During UI Rendering

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** Running `ALTER TABLE` inside `show_company_setup()` caused PostgreSQL `DuplicateColumn` production crashes.

**Decision:** **All schema changes** run through startup/migration integrity paths (`database.py`). UI render functions never execute DDL.

**Consequences:**
- `show_company_setup` and all client `show_*` pages are DDL-free
- Idempotent schema helpers (e.g. `ensure_users_user_id_schema_integrity`) at startup only
- Regression lockdown tests scan for violations

---

## Decision 009 — Regression Lockdown as Permanent Gate

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** Repeated urgent fixes risked undoing Phase 1 speed improvements and working workflows.

**Decision:** Establish permanent **regression lockdown** with canonical tests (`tests/test_regression_lockdown.py`), manifest, and agent checklist. Full suite (706+ tests) runs before reporting completion.

**Consequences:**
- `docs/REGRESSION_LOCKDOWN.md` is governance authority
- New workflows must add lockdown tests
- AI editors read `AGENTS.md` before code changes

---

## Decision 010 — Admin Diagnostics Surface Gating

**Date:** 2026-07-04  
**Status:** Accepted

**Context:** LV performance and migration diagnostics leaked cognitive load and frontend fragility when rendered on client paths.

**Decision:** Runtime admin diagnostics (`render_runtime_admin_diagnostics_suite`, migration cleanup review) render only on approved surfaces: `dev_gatekeeper`, `system_health`, `system_administration`. Migration cleanup loads lazily on admin surfaces.

**Consequences:**
- Client dashboard, POS, inventory, financial reports remain diagnostic-free
- Dev/System roles retain full observability on admin pages
- Frontend hardening favors stable widgets on hot paths

---

## Template for Future Decisions

```markdown
## Decision NNN — Title
**Date:** YYYY-MM-DD
**Status:** Proposed
**Context:** What problem or choice prompted this?
**Decision:** What was decided?
**Consequences:** What must engineers/builders do differently?
**Alternatives considered:** Optional — what was rejected and why?
```

---

*Decision Log — append-only architectural record for EKA Enterprise Platform.*
