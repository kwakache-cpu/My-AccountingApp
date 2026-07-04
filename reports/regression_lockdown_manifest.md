# Regression Lockdown Manifest

Permanent shield for completed ERP workflows. **Before editing production code**, run the checklist in `scripts/regression_lockdown_checklist.md`.

Last validated: 2026-07-04 (local suite)

## Protected workflows

| # | Workflow | Primary test file(s) | Lockdown test class | Status |
|---|----------|-------------------|---------------------|--------|
| 1 | Login and secure logout | `test_regression_lockdown.py`, `test_postgres_auth_subscription_runtime_portability.py`, `test_lv008_performance_autopsy.py` | `RegressionLockdownLoginLogoutTests` | PASS |
| 2 | PostgreSQL runtime startup | `test_regression_lockdown.py`, `test_startup_backend_gate.py`, `test_lv004_streamlit_postgres_cutover_startup.py` | `RegressionLockdownStartupTests` | PASS |
| 3 | SQLite fallback startup | `test_regression_lockdown.py`, `test_startup_backend_gate.py` | `RegressionLockdownStartupTests` | PASS |
| 4 | Company registration duplicate protection | `test_regression_lockdown.py`, `test_urgent_phase1_hardening_and_frontend_errors.py` | `RegressionLockdownRegistrationTests` | PASS |
| 5 | Paystack configuration resolution | `test_regression_lockdown.py`, `test_subscription_billing.py` | `RegressionLockdownPaystackTests` | PASS |
| 6 | Subscription/trial company flow | `test_regression_lockdown.py`, `test_subscription_billing.py`, `test_company_subscription_dml_portability.py` | `RegressionLockdownRegistrationTests` | PASS |
| 7 | Dashboard first render | `test_regression_lockdown.py`, `test_lv007_performance_and_client_visibility.py`, `test_lv008_performance_autopsy.py` | `RegressionLockdownDashboardTests` | PASS |
| 8 | POS sale | `test_regression_lockdown.py`, `test_pos_sale_identity.py`, `test_erp_functional_certification.py` | `RegressionLockdownPosTests` | PASS |
| 9 | POS controlled correction | `test_regression_lockdown.py`, `test_controlled_corrections.py` | `RegressionLockdownPosTests` | PASS |
| 10 | Financial Reports lazy loading | `test_regression_lockdown.py`, `test_lv009_phase1_financial_reports_speed.py`, `test_urgent_phase1_hardening_and_frontend_errors.py` | `RegressionLockdownFinancialReportsTests` | PASS |
| 11 | System Configuration / Company Profile | `test_regression_lockdown.py`, `test_urgent_system_config_and_migration_visibility.py` | `RegressionLockdownSystemConfigTests` | PASS |
| 12 | Staff/user/role setup | `test_regression_lockdown.py`, `test_branch_module_governance.py`, `test_permission_security.py` | `RegressionLockdownStaffRoleTests` | PASS |
| 13 | Migration Cleanup hidden from client pages | `test_regression_lockdown.py`, `test_urgent_system_config_and_migration_visibility.py`, `test_migration_cleanup_ui.py` | `RegressionLockdownMigrationVisibilityTests` | PASS |
| 14 | Dev/System diagnostics admin-only | `test_regression_lockdown.py`, `test_lv007_performance_and_client_visibility.py`, `test_lv006_startup_pipeline_consolidation.py` | `RegressionLockdownAdminDiagnosticsTests` | PASS |
| 15 | No schema DDL during UI page render | `test_regression_lockdown.py`, `test_urgent_system_config_and_migration_visibility.py` | `RegressionLockdownSystemConfigTests` | PASS |
| 16 | No raw DuplicateColumn / UNIQUE errors to users | `test_regression_lockdown.py`, `test_permission_security.py` | `RegressionLockdownUserSafeErrorsTests` | PASS |
| 17 | No LV diagnostics on client workflow pages | `test_regression_lockdown.py`, `test_lv007_performance_and_client_visibility.py` | `RegressionLockdownClientNavigationTests` | PASS |
| 18 | No cloud/Firebase/deep audit on normal client navigation | `test_regression_lockdown.py`, `test_lv007_performance_and_client_visibility.py` | `RegressionLockdownClientNavigationTests` | PASS |

## Coverage gaps found (before lockdown)

| Gap | Resolution |
|-----|------------|
| No canonical test for `_clear_session()` auth cleanup + postgres close | Added `RegressionLockdownLoginLogoutTests.test_clear_session_removes_auth_keys_and_closes_postgres_connection` |
| Duplicate company name during onboarding not directly tested | Added `RegressionLockdownRegistrationTests.test_onboarding_blocks_duplicate_company_name_case_insensitive` |
| Paystack env resolution not isolated in lockdown suite | Added `RegressionLockdownPaystackTests.test_paystack_runtime_config_resolves_from_environment` |
| DuplicateColumn/UNIQUE redaction not explicitly locked for client roles | Added `RegressionLockdownUserSafeErrorsTests` |
| Client workflow pages vs deep audit/firebase not centrally scanned | Added `RegressionLockdownClientNavigationTests` |

## Existing coverage retained (not duplicated)

These areas already had strong tests; lockdown references them rather than rewriting:

- POS identity/idempotency: `test_pos_sale_identity.py`
- Controlled correction audit trail: `test_controlled_corrections.py`
- Paystack payment verification: `test_subscription_billing.py`
- Postgres startup cutover: `test_lv004_streamlit_postgres_cutover_startup.py`
- Phase 1 financial reports speed: `test_lv009_phase1_financial_reports_speed.py`
- Urgent system config DDL fix: `test_urgent_system_config_and_migration_visibility.py`

## Production code changed

**None.** This lockdown pass added tests and documentation only.

## Quick validation commands

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_regress*.py" -v
python -m unittest discover -s tests -p "test_urgent*.py" -v
python -m unittest discover -s tests -p "test_lv00*.py" -v
python tests/run_regression_tests.py
git diff --check
```

## Full regression suite

`python tests/run_regression_tests.py` — runs all `tests/test_*.py` (706 tests at time of lockdown).
