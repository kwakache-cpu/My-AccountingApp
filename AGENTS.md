# AGENTS.md — EKA Enterprise Platform

**Read this document before making any code change.**

This file is the entry point for AI editors, contractors, and maintainers working on EKA Enterprise Platform (E.K.A Enterprise ERP).

---

## Mission

Build one of the smartest ERPs in the world **without** becoming one of the most complicated.

---

## Identity

**EKA is a Business Operating Platform.**

It is **not** simply:

- Accounting software
- POS software
- Inventory software

EKA connects commercial operations, financial truth, inventory movement, people, and decisions into one coherent platform.

---

## Golden Rule

**Complexity belongs inside the ERP.**  
**Simplicity belongs to the user.**

Users should experience clarity. The platform absorbs rules, validations, posting logic, permissions, and edge cases internally.

---

## Platform Strategy

1. **Platform first.** Industry Packs later.
2. **Workflow over modules.** Features must improve end-to-end business flows, not add isolated screens.
3. **Measure before optimizing.** No speculative performance rewrites.
4. **Protect what works.** Regression lockdown is mandatory.

---

## Required Reading (before code changes)

| Order | Document | Purpose |
|-------|----------|---------|
| 1 | `AGENTS.md` (this file) | Mission, rules, budgets |
| 2 | `docs/DEVELOPER_RULES.md` | Engineering constraints |
| 3 | `docs/REGRESSION_LOCKDOWN.md` | Protected workflows and test gates |
| 4 | `docs/EKA_CONSTITUTION.md` | Product identity and philosophy |
| 5 | `scripts/regression_lockdown_checklist.md` | Commands to run before/after edits |

When changing architecture or product direction, also read `docs/DECISION_LOG.md` and append a new decision if warranted.

---

## Core Non-Negotiables

- **No DDL during UI rendering.** Schema changes belong in startup/migration paths only.
- **No diagnostics on client pages.** Admin/Dev diagnostics stay on approved admin surfaces.
- **Preserve PostgreSQL + SQLite support.** Both backends remain first-class.
- **Preserve accounting integrity.** Do not change posting logic without explicit approval and tests.
- **Preserve audit trail.** Corrections are controlled; history is not silently erased.
- **Preserve startup/cutover safety.** Database activation and backend cutover guards stay intact.
- **Preserve regression lockdown.** Run the regression checklist; do not weaken protected workflows.
- **Measure before optimizing.** Profile and benchmark before broad performance changes.
- **Never rewrite broad modules without justification.** Prefer surgical fixes.
- **Never remove working functionality.** Deprecate with migration path if needed.
- **Never expose secrets.** Use `security_utils` sanitization for user-visible errors.
- **Every feature must improve a workflow.**
- **Every feature must save time, prevent mistakes, improve decisions, or increase security.**

---

## Performance Budgets

These are product-level targets for normal client usage (not admin diagnostics):

| Surface | Budget |
|---------|--------|
| Login | < 2s |
| Dashboard (first render) | < 3s |
| POS scan response | < 300ms |
| Invoice save | < 1s |
| Financial Reports (warm, selected report) | < 2s |

If a change risks these budgets, measure first and document in `docs/DECISION_LOG.md`.

---

## What AI Editors Must Do

### Before editing

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_regress*.py" -v
python -m unittest discover -s tests -p "test_urgent*.py" -v
python -m unittest discover -s tests -p "test_lv00*.py" -v
python tests/run_regression_tests.py
git diff --check
```

### After editing

1. Confirm all commands above pass.
2. Confirm no DDL added to UI render paths.
3. Confirm no admin diagnostics reintroduced on client surfaces.
4. Review `git diff` before reporting completion.
5. Update `docs/REGRESSION_LOCKDOWN.md` and `reports/regression_lockdown_manifest.md` if a new protected workflow is added.

### Do not

- Add features during bug-fix or hardening tasks unless explicitly requested.
- Commit, push, or open PRs unless explicitly requested.
- Modify accounting/posting logic casually.
- Trade client simplicity for feature count.

---

## Key Code Areas (orientation)

| Area | Primary modules |
|------|-----------------|
| UI shell & auth | `app.py` |
| Business modules & workflows | `modules.py` |
| Database & startup | `database.py` |
| Accounting engine | `accounting_engine.py` |
| Financial reports | `financials.py` |
| Enterprise/admin services | `enterprise_services.py` |
| Regression tests | `tests/test_regression_lockdown.py`, `tests/run_regression_tests.py` |

---

## Governance Document Index

| Document | Location |
|----------|----------|
| Constitution | `docs/EKA_CONSTITUTION.md` |
| Architecture | `docs/EKA_ARCHITECTURE_MANUAL.md` |
| Principles | `docs/PROJECT_PRINCIPLES.md` |
| Roadmap | `docs/PRODUCT_ROADMAP.md` |
| Workflows | `docs/WORKFLOW_LIBRARY.md` |
| Developer rules | `docs/DEVELOPER_RULES.md` |
| Regression lockdown | `docs/REGRESSION_LOCKDOWN.md` |
| Decision log | `docs/DECISION_LOG.md` |

---

*EKA Enterprise Platform — governance entry point. Last updated: 2026-07-04.*
