# EKA Constitution

The enduring charter for EKA Enterprise Platform.  
This document defines **what EKA is**, **who it serves**, and **how it must evolve**.

For engineering constraints, see `DEVELOPER_RULES.md`.  
For protected workflows, see `REGRESSION_LOCKDOWN.md`.

---

## Mission

Build one of the smartest ERPs in the world without becoming one of the most complicated.

EKA exists to give growing businesses enterprise-grade operational control with everyday usability.

---

## Vision

EKA becomes the **Business Operating Platform** that African and global SMEs trust to run sales, inventory, finance, people, and decisions from one place — with intelligence built in, not bolted on.

---

## Product Identity

EKA is a **Business Operating Platform**.

It integrates:

- Point of sale and commercial capture
- Inventory and supply movement
- Accounting and financial reporting
- People, roles, and branch governance
- Subscription, licensing, and platform administration

EKA is **not** a collection of disconnected tools. It is one platform with one source of financial truth.

---

## Golden Rule

**Complexity belongs inside the ERP.**  
**Simplicity belongs to the user.**

If a user must understand database schema, posting mechanics, or internal diagnostics to complete daily work, the product has failed that moment.

---

## Core Philosophy

1. **The ERP thinks so the user doesn't have to.**
2. **Workflow over modules.** Build flows, not feature islands.
3. **One source of truth.** Sales, inventory, and ledger must reconcile.
4. **Everything must explain itself.** Labels, warnings, and outcomes must be plain language.
5. **Performance is a feature.** Speed builds trust.
6. **Security by default.** Least privilege, sanitized errors, no secret leakage.
7. **Business memory.** Audit trails and controlled corrections preserve history.
8. **Commercial intelligence.** The platform should help owners decide, not just record.

---

## Product Principles

| Principle | Meaning |
|-----------|---------|
| Platform first | Perfect the core before Industry Packs |
| Workflow first | Ship improvements to real business journeys |
| Measure before optimizing | No speculative rewrites |
| Never trade simplicity for feature count | Fewer, better flows beat menu sprawl |
| Protect working behavior | Regression lockdown is part of the constitution |
| Admin complexity stays admin-side | Diagnostics never belong on client pages |

---

## Target Users

### Primary

- **Owners / CEOs** — visibility, control, decision support
- **Master Admins / Sub-Admins** — company setup, branches, staff, configuration
- **Bookkeepers / Accountants** — posting, periods, reports, reconciliation
- **Cashiers / Sales staff** — fast POS, minimal friction
- **Operations managers** — inventory, purchasing, supplier/customer coordination

### Platform operators

- **Dev / System Admin / Gatekeeper** — licensing, deployment, diagnostics, cutover

Each role sees only what their workflow requires.

---

## Platform First

Industry-specific packs (retail templates, manufacturing BOMs, construction job costing, etc.) are **intentionally deferred** until the Core Platform is exceptional.

The core must first excel at:

- Reliable posting and reporting
- Fast daily operations (POS, invoicing, inventory)
- Secure multi-branch governance
- PostgreSQL and SQLite portability
- Subscription and onboarding flows

Industry Packs extend the platform; they do not replace core discipline.

---

## Workflow First

Modules are implementation boundaries. **Workflows are the product.**

Priority workflows include Order to Cash, Purchase to Pay, Inventory Lifecycle, Payroll, Assets, and Year-End Closing. See `WORKFLOW_LIBRARY.md`.

---

## Business Intelligence

EKA must evolve from recording transactions to surfacing:

- Margin and cash signals
- Receivable/payable health
- Inventory velocity and risk
- Subscription and revenue visibility (platform level)

Intelligence must be actionable inside workflows, not buried in admin-only panels.

---

## Security Principles

- Role-based permissions on every sensitive action
- Controlled corrections instead of silent deletes
- User-safe error messages (`security_utils`)
- No schema DDL during page render
- No raw database errors on client surfaces
- Secrets resolved from environment/secrets stores, never logged or displayed

---

## Future Direction

Phased evolution (see `PRODUCT_ROADMAP.md`):

1. Perfect Core Platform
2. Business Intelligence
3. Workflow Excellence
4. Enterprise Scale
5. Industry Packs

Architectural choices that affect this direction must be recorded in `DECISION_LOG.md`.

---

*EKA Constitution — foundational product charter.*
