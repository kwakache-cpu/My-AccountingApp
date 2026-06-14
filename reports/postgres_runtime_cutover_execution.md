# PostgreSQL Runtime Cutover Execution Checklist

Phase: 5B.15M

Controlled runtime cutover preparation only. No commit, push, SQLite data modification, SQLite backup deletion, or production deployment was performed.

## Cutover Readiness

- Status: READY_FOR_CONTROLLED_RUNTIME_CUTOVER_VALIDATION
- Schema deployed: CONFIRMED by postdeploy validation evidence.
- Postdeploy validation passed: CONFIRMED, 754/754 checks passed with 0 failures.
- Rows copied: CONFIRMED, 527 rows copied to staging PostgreSQL.
- Postcopy reconciliation passed: CONFIRMED, 51/51 tables matched, 527/527 rows matched, 0 missing rows, and 0 extra rows.
- Runtime readiness passed: CONFIRMED, 51/51 runtime tables, 47/47 FK checks, and 6/6 smoke checks passed.
- Runtime dry-run passed: CONFIRMED, startup, business-module, and reporting read paths passed 13/13 SELECT-only checks.
- Production deployment: NOT PERFORMED.
- SQLite data modification: NOT PERFORMED.
- SQLite backups deleted: NO.

## Code Change Summary

- Code changed: Yes.
- `database.py`: added final PostgreSQL runtime cutover guard diagnostics, staging/production-approval checks, report-backed schema/reconciliation/readiness evidence, redacted database URL reporting, and startup return diagnostics for the controlled cutover block.
- `tests/test_startup_backend_gate.py`: updated startup gate expectations and added final cutover guard coverage.
- Report changed: `reports/postgres_runtime_cutover_execution.md`.
- Scorecard changed: `reports/postgres_migration_scorecard.md`.

## Final Runtime Cutover Guard

The runtime cutover guard requires:

- `DB_BACKEND=postgres`
- `ERP_ENABLE_POSTGRES_RUNTIME=1`
- `DATABASE_URL` present
- `ERP_ENVIRONMENT=staging`, or `ERP_ENVIRONMENT=production` with `ERP_POSTGRES_PRODUCTION_APPROVED=1`
- PostgreSQL driver available
- schema deployment evidence present
- row reconciliation evidence present
- runtime readiness evidence present
- runtime dry-run evidence present

Current diagnostics expected from the guard:

- active backend: `postgres` when `DB_BACKEND=postgres`, `ERP_ENABLE_POSTGRES_RUNTIME=1`, and `DATABASE_URL` are present
- configured backend: `postgres`
- runtime enabled: `True`
- database URL: redacted
- schema deployment status: `PASSED`
- row reconciliation status: `PASSED`
- runtime readiness status: `PASSED`
- runtime dry-run status: `PASSED`

## SQLite Startup Protection

When PostgreSQL runtime is selected, startup remains fail-closed before SQLite schema, recovery, migration, or backup paths can run. The application skips `ensure_schema()` and `startup_database()` returns a controlled `postgres_runtime_cutover_guard` status with redacted diagnostics instead of invoking SQLite-only schema creation.

## Exact Streamlit Secrets To Set Later

For staging cutover validation:

- `DB_BACKEND=postgres`
- `ERP_ENABLE_POSTGRES_RUNTIME=1`
- `ERP_ENVIRONMENT=staging`
- `DATABASE_URL=<staging PostgreSQL connection string>`

For production cutover only after approval:

- `DB_BACKEND=postgres`
- `ERP_ENABLE_POSTGRES_RUNTIME=1`
- `ERP_ENVIRONMENT=production`
- `ERP_POSTGRES_PRODUCTION_APPROVED=1`
- `DATABASE_URL=<approved production PostgreSQL connection string>`

Do not set production secrets until validation passes and a production deployment has been explicitly approved.

## Execution Checklist

1. Confirm this report and the scorecard are reviewed by the operator.
2. Confirm SQLite backup exists and is restorable.
3. Confirm SQLite backups are not deleted.
4. Freeze writes before final cutover validation.
5. Capture final SQLite snapshot without modifying SQLite data.
6. Re-run final row reconciliation and require 51/51 tables matched.
7. Set the Streamlit secrets listed above for the approved target environment.
8. Start the app in the controlled environment.
9. Confirm startup diagnostics show configured backend `postgres`, active backend `postgres`, runtime enabled `True`, redacted `DATABASE_URL`, schema deployment `PASSED`, and row reconciliation `PASSED`.
10. Confirm SQLite schema creation and SQLite recovery paths did not run.
11. Run login, company list, dashboard, chart of accounts, customers, inventory, journal reports, and POS read-only smoke checks.
12. Monitor logs and database activity during the rollback decision window.
13. Proceed only if all validation and smoke tests pass.

## Rollback Steps

1. Stop or restrict user access.
2. Remove or unset `ERP_ENABLE_POSTGRES_RUNTIME`.
3. Set `DB_BACKEND=sqlite` or restore the prior backend setting.
4. Remove or replace `DATABASE_URL` according to the previous SQLite deployment configuration.
5. Remove `ERP_POSTGRES_PRODUCTION_APPROVED` if it was set.
6. Redeploy the previous known-good app version.
7. Restore the verified SQLite backup only if needed.
8. Verify company count, user count, customer count, inventory count, chart of accounts count, journal count, login, and dashboard load.
9. Preserve logs and PostgreSQL state for investigation.

## Validation Results

- `python -m py_compile app.py database.py modules.py financials.py accounting_engine.py`: PASSED
- Focused backend guard tests with `PYTHONPATH=tests`: PASSED
- `python tests/run_regression_tests.py`: PASSED
- `git diff --check`: PASSED

## Final Decision

Runtime cutover can proceed only after final validation passes, operator review is complete, and deployment approval is explicit. This phase prepares the cutover guard and checklist but does not deploy production.
