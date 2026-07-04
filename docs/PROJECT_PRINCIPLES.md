# Project Principles

Design and engineering principles for EKA Enterprise Platform.  
These guide **what we build** and **what we refuse to build**.

---

## Foundational Principles

### 1. The ERP thinks so the user doesn't have to

Defaults, validations, posting rules, and permissions should be enforced by the platform. Users focus on business actions; the system handles consequences.

### 2. Workflow over modules

Features are acceptable only when they improve a complete business journey (e.g. Order to Cash), not when they add an isolated screen.

### 3. One source of truth

Sales documents, inventory movements, and ledger balances must reconcile. If two numbers disagree, that is a product defect — not a user training issue.

### 4. Everything must explain itself

Labels, warnings, empty states, and errors must use plain language. Client users never see stack traces, DDL errors, or internal diagnostic jargon.

### 5. Performance is a feature

Slow software erodes trust. Measure against budgets in `AGENTS.md` before shipping changes.

### 6. Security by default

Least privilege, sanitized errors, no secrets in logs or UI, controlled corrections instead of silent deletes.

### 7. Business memory

Audit trails, forensic logs, and correction workflows preserve what happened and why. History is an asset.

### 8. Commercial intelligence

The platform should help owners answer: *Am I making money? Who owes me? What is running out? What needs attention today?*

---

## Product Design Principles

| Principle | Application |
|-----------|-------------|
| **Complexity inside, simplicity outside** | Admin/diagnostic complexity stays on admin surfaces |
| **Never trade simplicity for feature count** | Fewer excellent flows beat menu sprawl |
| **Platform first** | Core must be exceptional before Industry Packs |
| **Measure before optimizing** | Profile first; no speculative rewrites |
| **Protect working behavior** | Regression lockdown is not optional |
| **Every feature must earn its place** | Save time, prevent mistakes, improve decisions, or increase security |

---

## Engineering Principles

| Principle | Application |
|-----------|-------------|
| **No DDL in UI** | Schema changes in startup/migration only |
| **No diagnostics on client pages** | LV/admin panels on approved surfaces only |
| **Dual-backend respect** | SQLite and PostgreSQL remain first-class |
| **Surgical fixes** | No broad module rewrites without justification |
| **Accounting integrity is sacred** | Posting changes require tests and explicit intent |
| **Startup/cutover safety** | Never weaken database activation guards |

---

## UX Principles

- **Fast paths for daily roles** — Cashier POS, bookkeeper posting, owner dashboard
- **Dangerous actions require confirmation** — Typed phrases over fragile widgets where possible
- **Progressive disclosure** — Advanced options expand on demand; dashboard defers heavy snapshots
- **Consistent language** — Same terms for customer, invoice, receipt, branch across modules

---

## Anti-Patterns (avoid)

- Adding a module without a workflow owner
- Running migrations when a user opens a settings page
- Showing PostgreSQL errors to shop-floor staff
- Optimizing without measurement
- Removing working features to "simplify"
- Industry-specific forks of core posting logic

---

## Principle Hierarchy

When principles conflict, resolve in this order:

1. **Accounting integrity & audit trail**
2. **Security & data safety**
3. **Regression lockdown / working behavior**
4. **Client simplicity**
5. **Performance budgets**
6. **New capability**

Document conflicts in `DECISION_LOG.md`.

---

## Related Documents

- `EKA_CONSTITUTION.md` — mission and identity
- `DEVELOPER_RULES.md` — practical engineering rules
- `WORKFLOW_LIBRARY.md` — workflow definitions
- `AGENTS.md` — AI editor entry point

---

*Project Principles — how EKA product and engineering decisions are judged.*
