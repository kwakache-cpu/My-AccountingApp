# Release Candidate Checklist — Phase 5B.18E

**Phase:** 5B.18E  
**Generated at:** 2026-06-27  
**Purpose:** Prepare the ERP for release candidate status by rehearsing live deployment readiness, finalizing operator and onboarding checklists, and validating production secrets without changing working code.

## Executive Summary

This checklist consolidates the final release candidate readiness work after Phase 5B.18D.
It is intended for technical owners, operators, finance, and business stakeholders.

- Release candidate goal: **production pilot or controlled rollout readiness**
- Scope: runtime startup, smoke test, rollback, operator sign-off, onboarding, secrets, diagnostics
- Preserve: SQLite, PostgreSQL, audit logging, permissions, rollback safety, accounting integrity
- Strict: no new features, only reports, tests, diagnostics, and verified go-live blockers

---

## Required Deliverables

- [ ] Reviewed `reports/final_release_decision.md` and `reports/final_go_live_blockers.md`
- [ ] Created `reports/live_app_smoke_test_checklist.md`
- [ ] Created `reports/production_rollback_checklist.md`
- [ ] Created `reports/operator_signoff_checklist.md`
- [ ] Created `reports/first_customer_onboarding_checklist.md`
- [ ] Created `reports/phase_5b18e_release_candidate_summary.md`

---

## Production Readiness Verification

### Deployment Secrets
- [ ] Confirm `reports/deployment_secrets_checklist.md` includes the required production secrets:
  - `DATABASE_URL`
  - `DB_BACKEND=postgres`
  - `ERP_ENABLE_POSTGRES_RUNTIME=1`
  - `ERP_ENVIRONMENT=production`
  - Firebase credentials
  - cloud backup object paths
- [ ] Confirm final secrets checklist includes manual markers:
  - **STREAMLIT SECRET REQUIRED**
  - **FIREBASE ACTION REQUIRED**
  - **DATABASE ACTION REQUIRED**
  - **SUPABASE ACTION REQUIRED**

### Runtime & Backend
- [ ] Startup verifies active backend diagnostics
- [ ] SQLite runtime remains certified for pilot if Postgres is not enabled
- [ ] PostgreSQL runtime only enabled with cutover evidence and backup SOP
- [ ] Runtime does not expose secrets in diagnostics
- [ ] Cloud restore guards remain effective for active backend

### Smoke Test and Rollback
- [ ] Live app smoke test checklist completed
- [ ] Production rollback checklist completed
- [ ] Operator sign-off checklist completed
- [ ] First-customer onboarding checklist completed
- [ ] Rollback owner assigned and rollback window approved

### Business and Operator Readiness
- [ ] Finance sign-off criteria captured
- [ ] Control owner sign-off criteria captured
- [ ] Onboarding steps for first customer documented and validated
- [ ] External monitoring and alerting ownership assigned

---

## Release Candidate Status

| Item | Status |
|---|---|
| Final go-live readiness reviewed | [ ] |
| Secrets checklist validated | [ ] |
| Smoke test checklist created | [ ] |
| Rollback checklist created | [ ] |
| Operator sign-off checklist created | [ ] |
| First customer onboarding checklist created | [ ] |
| Release candidate summary created | [ ] |

---

## Manual Actions Required

These actions are operational; they must be completed and recorded rather than automated.

- **STREAMLIT SECRET REQUIRED** — configure production secrets and verify `st.secrets` or environment variables
- **FIREBASE ACTION REQUIRED** — verify Firebase service account, DB URL, bucket, and backup object path
- **DATABASE ACTION REQUIRED** — verify backend selection, PostgreSQL cutover approval, and `DATABASE_URL`
- **SUPABASE ACTION REQUIRED** — document and rehearse Supabase/Postgres backup/restore SOP before Postgres production

---

## Related Reports

- `reports/final_release_decision.md`
- `reports/final_go_live_blockers.md`
- `reports/deployment_secrets_checklist.md`
- `reports/live_uat_checklist.md`
- `reports/backup_restore_rehearsal_steps.md`
