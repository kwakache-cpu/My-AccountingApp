# PostgreSQL Runtime Startup Enablement

Phase: 5B.15O

Controlled startup-path enablement only. No commit, push, SQLite data modification, SQLite backup deletion, or production deployment was performed.

## Root Cause

The final runtime cutover evidence guard was already passing, but `startup_database()` still treated any active PostgreSQL backend as a fail-closed condition. With `DB_BACKEND=postgres`, `ERP_ENABLE_POSTGRES_RUNTIME=1`, `DATABASE_URL` present, and `ERP_ENVIRONMENT=staging`, startup returned `stage=postgres_runtime_cutover_guard` even when schema deployment, row reconciliation, runtime readiness, and runtime dry-run evidence had all passed.

## Code Changed

- `database.py`
  - Allows `startup_database()` to return `ok=True` with `stage=postgres_runtime_startup` only when the final cutover guard passes.
  - Continues to block SQLite schema/bootstrap/recovery/migration paths under PostgreSQL runtime.
  - Keeps the fail-closed `postgres_runtime_cutover_guard` path when evidence is missing or the environment is not staging or production-approved.
  - Returns redacted diagnostics for configured backend, active backend, runtime flag, `DATABASE_URL`, environment approval, schema deployment, row reconciliation, runtime readiness, and runtime dry-run status.

- `app.py`
  - Treats skipped SQLite schema startup as an allowed PostgreSQL runtime route when the cutover guard passes.
  - Retains error logging for blocked PostgreSQL runtime configurations.

- `postgres_runtime_smoke_test.py`
  - Updated the smoke validator to require `stage=postgres_runtime_startup`.

## Tests Added Or Updated

- `tests/test_startup_backend_gate.py`
  - PostgreSQL runtime is allowed when all guards and evidence pass.
  - PostgreSQL runtime is blocked when evidence is missing.
  - SQLite startup remains unchanged.
  - Database URL secrets remain redacted.

- `tests/test_postgres_runtime_smoke_test.py`
  - Smoke test expectation updated to the enabled `postgres_runtime_startup` stage.

## Runtime Verification

- Controlled smoke test result: READY_FOR_STREAMLIT_SECRETS_CUTOVER
- Active backend: postgres
- Startup stage: postgres_runtime_startup
- SQLite bootstrap blocked: True
- Read checks: 9/9 passed
- Blockers: 0

## Exact Streamlit Secrets To Retry

For staging:

- `DB_BACKEND=postgres`
- `ERP_ENABLE_POSTGRES_RUNTIME=1`
- `ERP_ENVIRONMENT=staging`
- `DATABASE_URL=<staging PostgreSQL connection string>`

For production only after explicit approval:

- `DB_BACKEND=postgres`
- `ERP_ENABLE_POSTGRES_RUNTIME=1`
- `ERP_ENVIRONMENT=production`
- `ERP_POSTGRES_PRODUCTION_APPROVED=1`
- `DATABASE_URL=<approved production PostgreSQL connection string>`

## Rollback Instruction

If startup or smoke validation regresses:

1. Remove or unset `ERP_ENABLE_POSTGRES_RUNTIME`.
2. Set `DB_BACKEND=sqlite` or restore the previous backend setting.
3. Remove or restore `DATABASE_URL` to the previous configuration.
4. Remove `ERP_POSTGRES_PRODUCTION_APPROVED` if it was set.
5. Redeploy the previous known-good app version.
6. Verify SQLite company, user, customer, inventory, chart of accounts, and journal counts.

## Validation Results

- Focused startup and smoke tests: PASSED
- `python -m py_compile app.py database.py modules.py financials.py accounting_engine.py`: PASSED
- `python tests/run_regression_tests.py`: PASSED
- `git diff --check`: PASSED

## Final Status

PostgreSQL runtime startup is enabled for guarded staging or approved production configurations after all required validation reports pass. SQLite startup remains unchanged by default, and SQLite schema/bootstrap/recovery/migration paths remain blocked while PostgreSQL runtime is active.
