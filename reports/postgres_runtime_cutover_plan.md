# PostgreSQL Runtime Cutover Plan

Phase: 5B.15K

Planning artifact only. PostgreSQL runtime was not enabled, SQLite was not modified, application data was not written, and production was not deployed.

## Cutover Readiness

- Status: READY_FOR_RUNTIME_CUTOVER_AFTER_REVIEW
- Schema deployed: Yes, staging schema deployment has completed.
- Postdeploy validation passed: Yes, Phase 5B.15E reported 754/754 read-only checks passed, 0 failures, 0 schema mismatches, and 0 blockers.
- Rows copied: Yes, 527 SQLite rows were copied to staging PostgreSQL.
- Post-copy reconciliation: Yes, Phase 5B.15I reported 51/51 tables matched, 527/527 total rows matched, 0 missing rows, and 0 extra rows.
- Runtime readiness validation: Yes, Phase 5B.15J reported READY_FOR_RUNTIME_CUTOVER with 51/51 runtime tables, 47/47 FK checks, and 6/6 runtime smoke checks passing.
- Runtime status now: PostgreSQL runtime remains disabled.
- Production status now: production deployment remains blocked.

## Required Secrets To Set Later

Set these only during the approved runtime cutover window:

- `DATABASE_URL`: staging or approved production PostgreSQL connection string for the target runtime environment.
- `DB_BACKEND=postgres`
- `ERP_ENABLE_POSTGRES_RUNTIME=1`

Rollback secret values:

- Remove or unset `ERP_ENABLE_POSTGRES_RUNTIME`.
- Set `DB_BACKEND=sqlite` or restore the prior SQLite backend setting.
- Remove or replace `DATABASE_URL` according to the prior deployment configuration.

## Cutover Stages

1. Pre-cutover backup
   - Create and verify a fresh SQLite database backup.
   - Record backup path, timestamp, checksum or file size, and operator.
   - Confirm the backup is restorable before changing runtime secrets.

2. Freeze writes
   - Put the application in a controlled maintenance window.
   - Stop user sessions and background jobs that can create writes.
   - Confirm no application instance is still writing to SQLite.

3. Final SQLite snapshot
   - Capture the final read-only SQLite snapshot after writes are frozen.
   - Preserve it as the rollback source of truth.
   - Do not modify SQLite during or after this snapshot.

4. Final row reconciliation
   - Re-run SQLite vs PostgreSQL row-count reconciliation.
   - Require 51/51 tables matched, total rows matched, 0 missing rows, and 0 extra rows.
   - Treat any mismatch as a NO-GO.

5. Set Streamlit secrets
   - Set `DATABASE_URL`.
   - Set `DB_BACKEND=postgres`.
   - Set `ERP_ENABLE_POSTGRES_RUNTIME=1`.
   - Verify no unrelated secrets changed.

6. Deploy
   - Deploy the approved app version only.
   - Confirm deployment uses the intended secrets.
   - Confirm SQLite runtime path is not selected.

7. Smoke test
   - Execute the smoke tests listed below before opening the app to users.
   - Record pass/fail evidence and timestamps.

8. Monitor
   - Monitor application logs, database connection errors, auth failures, dashboard errors, accounting report errors, and unexpected write activity.
   - Keep the write freeze in place until smoke tests pass and the rollback decision window starts.

9. Rollback decision window
   - Keep an explicit rollback window open after deploy.
   - If any NO-GO condition occurs, rollback immediately instead of debugging in production.
   - End the window only after smoke tests and early monitoring remain clean.

## Smoke Tests

- Login: a known valid user can authenticate successfully.
- Company list: expected companies load and company count matches the validated dataset.
- Dashboard load: dashboard opens without backend, query, or rendering errors.
- Chart of accounts: chart of accounts list loads and count is nonzero.
- Customers: customer list loads and count matches expected migrated data.
- Inventory: inventory list loads and count matches expected migrated data.
- Journal reports: journal entry/report views load and totals are readable.
- POS read-only check: POS sales and suspended-sale views load in read-only verification mode without creating new sales, returns, or inventory movements.

## NO-GO Conditions

- Row mismatch in final reconciliation.
- Failed login for a known valid user.
- Missing company or unexpected company count.
- Failed dashboard load.
- Failed accounting or journal report.
- Unexpected PostgreSQL writes during smoke testing.
- Any SQLite modification after final snapshot.
- Any unintended production deployment or app version mismatch.
- Missing, malformed, or incorrect `DATABASE_URL`, `DB_BACKEND`, or `ERP_ENABLE_POSTGRES_RUNTIME` secret.
- Any operator uncertainty about which database backend is active.

## Rollback Plan

1. Trigger rollback
   - Declare rollback if any NO-GO condition occurs inside the decision window.
   - Stop or restrict user access before changing secrets.

2. Revert secrets to SQLite
   - Remove or unset `ERP_ENABLE_POSTGRES_RUNTIME`.
   - Set `DB_BACKEND=sqlite` or restore the prior backend secret state.
   - Remove or replace `DATABASE_URL` according to the previous deployment configuration.

3. Redeploy previous app
   - Redeploy the last known-good app version.
   - Confirm the deployment selects SQLite runtime.
   - Confirm PostgreSQL runtime is not enabled.

4. Restore SQLite backup if needed
   - Use the verified pre-cutover backup only if SQLite data was changed or the runtime state is uncertain.
   - Validate the restored database before reopening access.

5. Verify rollback health
   - Verify company count.
   - Verify user count.
   - Verify customer count.
   - Verify inventory count.
   - Verify chart of accounts count.
   - Verify journal count.
   - Confirm login and dashboard load on SQLite.

6. Preserve evidence
   - Save cutover logs, rollback logs, smoke-test results, and final database count evidence.
   - Keep the PostgreSQL dataset unchanged for follow-up investigation.

## Review Decision

Runtime cutover can proceed after human review of this plan and an explicit approved cutover phase. This phase does not enable PostgreSQL runtime. The next phase must repeat final backup, write freeze, final SQLite snapshot, final row reconciliation, secret update, deploy, smoke test, monitoring, and rollback decision steps under operator control.
