# Regression Lockdown

Permanent regression shield for completed EKA Enterprise Platform work.  
Future fixes must **not break already-working modules**.

This document is the governance view. Operational test mapping lives in `reports/regression_lockdown_manifest.md`.  
Command checklist: `scripts/regression_lockdown_checklist.md`  
Canonical tests: `tests/test_regression_lockdown.py`

---

## Purpose

Regression lockdown ensures:

- Working workflows stay working
- Client pages stay clean (no diagnostics, no DDL)
- Accounting integrity survives future edits
- Performance improvements are not accidentally undone

**Before any production code edit**, run the checklist in `scripts/regression_lockdown_checklist.md`.

---

## Protected Workflows

### Authentication & Session

| Workflow | What must stay true | Lockdown / test reference |
|----------|---------------------|---------------------------|
| **Login** | Access key auth resolves company/branch/user; active status enforced | `RegressionLockdownLoginLogoutTests`, `test_postgres_auth_subscription_runtime_portability.py` |
| **Logout** | Session keys cleared; PostgreSQL session connection closed | `RegressionLockdownLoginLogoutTests`, `test_lv008_performance_autopsy.py` |

### Database Startup

| Workflow | What must stay true | Lockdown / test reference |
|----------|---------------------|---------------------------|
| **PostgreSQL startup** | Runtime startup path when enabled and evidence passes | `RegressionLockdownStartupTests`, `test_startup_backend_gate.py`, `test_lv004_streamlit_postgres_cutover_startup.py` |
| **SQLite startup / fallback** | Safe fallback when PG configured but runtime disabled | `RegressionLockdownStartupTests`, `test_startup_backend_gate.py` |
| **Startup pipeline** | Canonical startup, no duplicate heavy work per session | `test_lv006_startup_pipeline_consolidation.py` |

### Registration & Subscription

| Workflow | What must stay true | Lockdown / test reference |
|----------|---------------------|---------------------------|
| **Registration** | Trial company creation; duplicate name blocked | `RegressionLockdownRegistrationTests`, `test_urgent_phase1_hardening_and_frontend_errors.py` |
| **Paystack** | Config resolution from env/secrets; checkout initialization | `RegressionLockdownPaystackTests`, `test_subscription_billing.py` |
| **Subscription / trial** | Trial idempotency; payment verification activates license | `RegressionLockdownRegistrationTests`, `test_company_subscription_dml_portability.py` |

### Client Operations

| Workflow | What must stay true | Lockdown / test reference |
|----------|---------------------|---------------------------|
| **Dashboard** | First render fast; AR/AP deferred on demand; no admin diagnostics | `RegressionLockdownDashboardTests`, `test_lv007_performance_and_client_visibility.py`, `test_lv008_performance_autopsy.py` |
| **POS sale** | Valid sale identity; lines linked; references preserved | `RegressionLockdownPosTests`, `test_pos_sale_identity.py`, `test_erp_functional_certification.py` |
| **Controlled corrections** | Permission + reason required; audit old/new values | `RegressionLockdownPosTests`, `test_controlled_corrections.py` |
| **Financial Reports** | Lazy report selection; shared ledger snapshot; lazy CSV | `RegressionLockdownFinancialReportsTests`, `test_lv009_phase1_financial_reports_speed.py` |

### Configuration & Governance

| Workflow | What must stay true | Lockdown / test reference |
|----------|---------------------|---------------------------|
| **System Configuration** | Company profile renders; **no DDL** on render | `RegressionLockdownSystemConfigTests`, `test_urgent_system_config_and_migration_visibility.py` |
| **Roles / staff** | Permission matrix enforced; staff listing works | `RegressionLockdownStaffRoleTests`, `test_permission_security.py`, `test_branch_module_governance.py` |
| **Migration visibility** | Migration cleanup hidden from client roles/surfaces | `RegressionLockdownMigrationVisibilityTests`, `test_migration_cleanup_ui.py` |
| **Admin diagnostics** | LV panels admin-only; approved surfaces only | `RegressionLockdownAdminDiagnosticsTests`, `test_lv006_startup_pipeline_consolidation.py` |

### Safety & Client Experience

| Workflow | What must stay true | Lockdown / test reference |
|----------|---------------------|---------------------------|
| **No UI DDL** | No `ALTER TABLE` / `ADD COLUMN` in render paths | `RegressionLockdownSystemConfigTests` |
| **Safe user errors** | No raw DuplicateColumn/UNIQUE to client roles | `RegressionLockdownUserSafeErrorsTests`, `test_permission_security.py` |
| **No LV on client pages** | Dashboard, POS, inventory, reports exclude admin diagnostics | `RegressionLockdownClientNavigationTests`, `test_lv007_performance_and_client_visibility.py` |
| **No deep audit on client nav** | No cloud/Firebase/full audit on normal client pages | `RegressionLockdownClientNavigationTests`, warmup skip list in `modules.py` |

### Performance (Phase 1 preserved)

| Area | Must preserve |
|------|----------------|
| Financial Reports | Lazy `st.radio`, `_cached_financial_report_by_type`, `_lazy_csv_button` |
| Dashboard | Receivable/payable on-demand load |
| Warmup | Skips cloud backup, Firebase, subscription billing, full health audit |
| Process warmup | Once per deploy signature; session reuse |

---

## Validation Commands

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_regress*.py" -v
python -m unittest discover -s tests -p "test_urgent*.py" -v
python -m unittest discover -s tests -p "test_lv00*.py" -v
python tests/run_regression_tests.py
git diff --check
```

### Full suite

`python tests/run_regression_tests.py` — discovers all `tests/test_*.py`  
**706 tests** at time of lockdown documentation (2026-07-04).

---

## Adding a New Protected Workflow

1. Add test(s) to `tests/test_regression_lockdown.py`
2. Update `reports/regression_lockdown_manifest.md` (operational mapping)
3. Update this document (governance list)
4. Append decision to `DECISION_LOG.md` if scope is architectural

---

## What To Do When a Lockdown Test Fails

1. **Stop** — do not commit broad fixes
2. Identify smallest safe change
3. Fix without weakening adjacent protections
4. Re-run full checklist
5. Document in decision log if the fix changes architecture

---

## Related Artifacts

| Artifact | Path |
|----------|------|
| Test manifest (pass/fail mapping) | `reports/regression_lockdown_manifest.md` |
| Agent command checklist | `scripts/regression_lockdown_checklist.md` |
| Canonical lockdown tests | `tests/test_regression_lockdown.py` |
| Full regression runner | `tests/run_regression_tests.py` |
| Frontend hardening notes | `reports/urgent_phase1_frontend_hardening.md` |

---

## Governance Rules

- Do **not** remove lockdown tests to make CI pass
- Do **not** disable tests without explicit approval
- Do **not** change accounting/posting logic to fix unrelated failures
- Production code changes require failing tests proving a **current real bug**

---

*Regression Lockdown — permanent shield for completed EKA work.*
