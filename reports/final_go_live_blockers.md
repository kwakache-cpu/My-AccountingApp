# Final Go-Live Blockers

**Phase:** 5B.18D  
**Generated at:** 2026-06-27  
**Purpose:** Consolidated production risk register and blocker burndown after backup/restore review, deployment readiness, role UAT mapping, and performance review.

## Executive Summary

| Metric | Value |
|---|---|
| Current go-live readiness % | **88%** |
| Controlled pilot readiness % | **91%** |
| Unrestricted enterprise rollout | **NO-GO** |
| Controlled pilot with sign-off | **GO (conditional)** |

The ERP is technically certified for SQLite and PostgreSQL runtimes, accounting integrity, rollback safety, and permission enforcement. Remaining blockers are **operational proof** — live backup/restore rehearsal, browser UAT by role, production-size performance timing, and finance/statutory sign-off.

---

## Risk Register (Severity-Ordered)

### Critical

| ID | Risk | Impact | Mitigation | Blocks Production? |
|---|---|---|---|---|
| C-01 | Live Firebase backup/restore not rehearsed against real credentials and bucket | Data loss or failed recovery during Streamlit Cloud redeploy | Run full backup → isolated restore → row-count and financial reconciliation; record sign-off in `backup_restore_rehearsal_steps.md` | **Yes** for unrestricted go-live |
| C-02 | Supabase/PostgreSQL in-app backup/restore does not exist | Postgres cutover leaves recovery entirely on platform operator | Document and rehearse Supabase pg_dump/PITR; keep SQLite Firebase path until Postgres backup SOP is signed off | **Yes** if Postgres is production backend without external backup proof |

### High

| ID | Risk | Impact | Mitigation | Blocks Production? |
|---|---|---|---|---|
| H-01 | Role-by-role browser UAT incomplete for all 10 production roles | Undetected UI permission leaks or broken workflows | Execute `live_uat_checklist.md` per role; record defects and sign-off | **Yes** for unrestricted go-live |
| H-02 | Production-size performance not measured | Slow dashboard, POS, reports under real data volumes | Profile pilot dataset against targets in `erp_performance_certification.md`; capture timings | **Yes** for high-volume tenants |
| H-03 | Finance owner has not signed VAT/NHIL statutory report formats | Incorrect tax filing outputs | Finance validates TB, VAT control, NHIL/GETFund reports against expected filings | **Yes** for statutory compliance go-live |
| H-04 | Admin cloud restore blocked when local DB is valid and populated | Operator cannot replace runtime DB via UI without `explicit_recovery_mode` | Document recovery procedure; use explicit recovery path or staging restore first | **Partial** — blocks naive restore, not go-live if runbook exists |
| H-05 | External monitoring and alerting not configured | Undetected outages | Configure uptime/error alerts; assign incident owner | **Yes** for 24/7 production SLA |

### Medium

| ID | Risk | Impact | Mitigation | Blocks Production? |
|---|---|---|---|---|
| M-01 | Fixed asset multi-period depreciation edge cases | Incorrect depreciation schedules | Asset lifecycle UAT: acquisition, multi-period, disposal | No (pilot OK with finance review) |
| M-02 | Banking/cash reconciliation UI not operationally certified | Cash drawer and bank reconciliation gaps | Manual UAT: drawer close, transfers, reconciliation | No for controlled pilot |
| M-03 | Inventory bulk import/adjustment at volume | Stock count errors under load | Production-like import/adjustment scenarios with audit | No for controlled pilot |
| M-04 | No `PRAGMA integrity_check` at restore time | Corrupted backup could pass structural readiness | Add optional integrity scan to restore validation (future hardening); manual check in rehearsal | No if manual validation done |
| M-05 | Local file restore API exists but no admin UI | Operators cannot restore from local `.db` without API/script | Document `restore_runtime_database_from_local_file()` in runbook | No |
| M-06 | SMTP hardcoded to Gmail in `app.py` | Email delivery may fail in production | Configure production SMTP or disable email features until configured | No for pilot without email |
| M-07 | No committed `.env.example` or `secrets.toml.example` | Deployment misconfiguration risk | Use `deployment_secrets_checklist.md` | No |

### Low

| ID | Risk | Impact | Mitigation | Blocks Production? |
|---|---|---|---|---|
| L-01 | Developer role retains full superuser permissions | Privileged access abuse | Restrict Dev credentials; emergency-use policy | No |
| L-02 | Company-count-only backup divergence detection | Subtle data drift undetected | Run full row-count reconciliation in restore rehearsal | No |
| L-03 | Historical certification reports show evolving state | Confusion about current status | Treat this report and `final_release_decision.md` as current | No |
| L-04 | SQLite concurrency warning for enterprise scale | Write contention under many concurrent cashiers | Pilot on SQLite; plan Postgres cutover for scale | No for small pilot |

---

## Blocker Burndown Status

| Task Area | Prior % | Current % | Status |
|---|---|---|---|
| Backup & restore certification | 77% | **82%** | Documentation improved; live rehearsal still open |
| Deployment readiness | 84% | **89%** | Checklist generated; secrets template documented |
| Role-based UAT | 79% | **85%** | Per-role checklist generated; browser execution open |
| Performance review | 76% | **76%** | Findings documented; load tests not run |
| Operational checklists | 70% | **92%** | Day-one, post-deploy, rollback checklists generated |

---

## Non-Blocker PASS Items (Retained)

- SQLite runtime: **PASS**
- PostgreSQL runtime: **PASS**
- Schema portability: **PASS**
- Accounting integrity and rollback: **PASS**
- Permission matrix enforcement (automated): **PASS**
- Regression suite: **PASS**
- Restore guard and upload guards: **PASS**
- Postgres runtime blocks unsafe SQLite cloud restore: **PASS**

---

## Remaining Blockers Summary

1. **Live cloud backup/restore rehearsal** (Critical)
2. **Supabase backup SOP** if Postgres is production backend (Critical)
3. **Browser UAT for all 10 roles** (High)
4. **Production-size performance timing** (High)
5. **Finance statutory report sign-off** (High)
6. **External monitoring configuration** (High)

---

## Manual Actions Required

See also: `backup_restore_rehearsal_steps.md`, `deployment_secrets_checklist.md`, `live_uat_checklist.md`, `final_release_decision.md`.

- [ ] Execute Firebase backup → staging restore → reconciliation
- [ ] Execute Supabase export/restore if Postgres backend
- [ ] Complete role-by-role browser UAT
- [ ] Capture performance timings against pilot targets
- [ ] Obtain finance and business owner sign-off
- [ ] Configure external monitoring
- [ ] Assign rollback owner and approve rollback window
