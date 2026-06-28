# Production Cutover Runbook — Phase 5B.18F

**Phase:** 5B.18F  
**Generated at:** 2026-06-28  
**Purpose:** Operator runbook for controlled production cutover and first live customer launch.

## Executive Summary

This runbook consolidates cutover steps from Phase 5B.18D release decision, Phase 5B.18E release candidate checklists, and final launch certification requirements.
It is intended for technical owners, operators, finance, and business stakeholders.

- Cutover goal: **controlled first-customer production launch**
- Approved deployment mode: **SQLite pilot on Streamlit Cloud** (conditional) or **PostgreSQL** (only after Supabase backup SOP sign-off)
- Preserve: SQLite, PostgreSQL, audit logging, permissions, rollback safety, accounting integrity
- Strict: no new features during cutover; execute checklists and record sign-off only

---

## Cutover Preconditions

- [ ] Review `reports/final_release_decision.md` and confirm **CONDITIONAL GO** for approved deployment mode
- [ ] Review `reports/final_go_live_blockers.md` and confirm no unresolved **BLOCKS LAUNCH** items for selected deployment mode
- [ ] Confirm `reports/final_launch_approval_checklist.md` is complete
- [ ] Confirm rollback owner assigned and `reports/production_rollback_checklist.md` reviewed
- [ ] Confirm `reports/first_24_hour_monitoring_checklist.md` owner assigned
- [ ] Confirm `reports/post_launch_support_checklist.md` support owner assigned

### Manual Action Preconditions

- **STREAMLIT SECRET REQUIRED** — production secrets configured and validated in Streamlit Cloud or approved host
- **FIREBASE ACTION REQUIRED** — Firebase service account, database URL, storage bucket, and backup object path verified
- **DATABASE ACTION REQUIRED** — confirm `DATABASE_URL`, `DB_BACKEND`, `ERP_ENABLE_POSTGRES_RUNTIME`, and `ERP_ENVIRONMENT` values match approved cutover plan
- **SUPABASE ACTION REQUIRED** — if Postgres backend is active, Supabase backup/restore SOP must be documented, rehearsed, and approved before cutover

---

## T-72 Hours — Cutover Planning

- [ ] Confirm approved deployment mode: [ ] SQLite pilot [ ] PostgreSQL production [ ] Other: _________
- [ ] Confirm go-live window and rollback window with business owner
- [ ] Assign cutover operator, rollback owner, monitoring owner, and support owner
- [ ] Notify pilot customer and internal stakeholders of cutover schedule
- [ ] Confirm `reports/deployment_secrets_checklist.md` completed for production runtime
- [ ] Confirm `reports/final_security_review.md` reviewed and signed
- [ ] Confirm `reports/final_accounting_signoff.md` reviewed by finance owner (or deferred with documented waiver for pilot-only scope)

---

## T-24 Hours — Pre-Cutover Validation

- [ ] Execute `reports/live_app_smoke_test_checklist.md` in staging or rehearsal environment
- [ ] Run pre-cutover backup (Firebase cloud + local if enabled)
- [ ] Record backup timestamp, object path, and company count
- [ ] Confirm Trial Balance balances for pilot company
- [ ] Confirm all required admin and operator users can log in
- [ ] Restrict or disable Developer credentials for production runtime
- [ ] Confirm `ERP_PRODUCTION_MODE=1` and `ERP_ENVIRONMENT=production` (or approved staging equivalent for rehearsal)
- [ ] Confirm `get_deployment_readiness_diagnostics()` reports healthy backend, company count, and backup status
- [ ] Confirm no plaintext secrets appear in diagnostics output

---

## T-1 Hour — Final Go/No-Go

- [ ] Technical owner confirms runtime diagnostics healthy
- [ ] Finance owner confirms accounting sign-off status (or pilot waiver documented)
- [ ] Business owner confirms customer communication sent
- [ ] Operator confirms rollback plan and owner on standby
- [ ] Monitoring owner confirms first-24-hour checklist ready
- [ ] Support owner confirms post-launch support roster assigned
- [ ] Record final go/no-go decision in `reports/final_launch_approval_checklist.md`

---

## T-0 — Production Cutover Steps

1. **Deploy or confirm runtime**
   - [ ] Deploy latest approved app version to Streamlit Cloud or production host
   - [ ] Confirm App startup without exception
   - [ ] Confirm Dashboard loads for Owner / CEO login

2. **Validate core runtime**
   - [ ] Confirm active backend matches approved cutover plan (`SQLite` or `postgres`)
   - [ ] Confirm cloud backup path exists and is writable
   - [ ] Confirm audit trail records deployment access

3. **Execute smoke write path**
   - [ ] Perform one controlled test transaction (void if test-only)
   - [ ] Confirm journal posting, inventory update (if applicable), and audit trail entry
   - [ ] Confirm cloud backup upload triggered after write activity

4. **Validate permissions**
   - [ ] System Admin access limited to configuration modules
   - [ ] Cashier access limited to POS (branch-scoped)
   - [ ] Accountant access limited to finance modules
   - [ ] Auditor / Read Only access limited to reports and audit trail

5. **Record cutover completion**
   - [ ] Operator records cutover timestamp, app version, backup object path, and validation results
   - [ ] Begin `reports/first_24_hour_monitoring_checklist.md`

---

## T+1 Hour — Immediate Post-Cutover Checks

- [ ] Monitor System Health diagnostics
- [ ] Confirm no unbalanced journals
- [ ] Confirm persistence self-test passes
- [ ] Review Streamlit runtime logs for startup errors
- [ ] Confirm support channel is active for pilot customer

---

## Rollback During Cutover

If cutover fails, follow `reports/production_rollback_checklist.md`:

- [ ] Announce write freeze immediately
- [ ] Preserve current broken state for forensic analysis
- [ ] Restore to staging first, validate Trial Balance and row counts
- [ ] Switch production runtime only after staging validation passes
- [ ] Document rollback owner, timestamp, source backup, and validation results

---

## Cutover Sign-Off

| Stakeholder | Role | Cutover Approved | Signature | Date |
|---|---|---|---|---|
|  | Technical Owner | [ ] |  |  |
|  | Business Owner | [ ] |  |  |
|  | Finance Owner | [ ] |  |  |
|  | Operator | [ ] |  |  |

---

## Related Reports

- `reports/final_release_decision.md`
- `reports/final_go_live_blockers.md`
- `reports/phase_5b18e_release_candidate_summary.md`
- `reports/live_app_smoke_test_checklist.md`
- `reports/production_rollback_checklist.md`
- `reports/final_launch_approval_checklist.md`
- `reports/first_24_hour_monitoring_checklist.md`
- `reports/post_launch_support_checklist.md`
- `reports/final_customer_launch_checklist.md`
- `reports/phase_5b18f_launch_certification_summary.md`
