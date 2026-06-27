# Final Release Decision

**Phase:** 5B.18D  
**Generated at:** 2026-06-27  
**Decision authority:** Business owner + Finance owner + Technical owner

---

## Release Decision Summary

| Decision | Status |
|---|---|
| Unrestricted enterprise production | **NO-GO** |
| Controlled production pilot | **CONDITIONAL GO** |
| SQLite pilot on Streamlit Cloud | **CONDITIONAL GO** (after checklist sign-off) |
| PostgreSQL production cutover | **NO-GO** (until Supabase backup SOP + staging rehearsal) |

---

## Go-Live Readiness Score

| Dimension | Readiness % | Trend |
|---|---|---|
| Technical / code certification | **92%** | Stable |
| Accounting integrity | **91%** | Stable |
| PostgreSQL portability | **96%** | Stable |
| Backup & restore | **82%** | Improved docs; live rehearsal open |
| Deployment & secrets | **89%** | Checklist added |
| Role UAT | **85%** | Checklist ready; execution open |
| Performance | **76%** | Unchanged; load tests open |
| Operational readiness | **80%** | Checklists added |
| **Overall go-live readiness** | **88%** | +2% from 5B.18A |

---

## Performance Review Findings (Document Only — No Rewrites)

| Surface | Risk Level | Finding | Production Impact |
|---|---|---|---|
| Dashboard | Medium | Metrics aggregation not load-tested at production scale | Slow initial load with large transaction history |
| POS | Low-Medium | Transaction wrapper and schema indexes exist; concurrency not profiled | Multiple simultaneous cashiers may contend on SQLite |
| Financial Reports | Medium | Journal-led correctness certified; large GL/TB timing unknown | Reports may exceed 5s target on large datasets |
| General Journal | Low | Balance controls and posting guards certified | No obvious production risk |
| Inventory | Low-Medium | POS decrement and purchase increase tested; bulk import not volume-tested | Import/adjustment at scale needs UAT |
| Receivables | Low | AR aging helpers exist; large customer count timing unknown | Aging report latency |
| Payables | Low | AP aging helpers exist; same as AR | Aging report latency |
| Audit Trail | Medium | High-volume filter/export not timed | Slow audit queries under heavy logging |
| N+1 queries | Medium | Some UI pages use repeated lookups | Incremental latency on list pages |
| SQLite concurrency | Medium | Warning documented in deployment diagnostics | Not suitable for high-concurrency enterprise without Postgres |
| PostgreSQL queries | Medium | Timing hooks exist; no production sample captured | Unknown slow queries until pilot profiling |
| Connection/transaction leaks | Low | Diagnostics expose counters; no leak in tests | Low risk |

**Performance targets** (from `erp_performance_certification.md`):
- Dashboard: < 3s (pilot dataset)
- POS checkout: < 2s
- POS finalization: < 2s
- TB/GL: < 5s
- AR/AP aging: < 5s
- Audit trail filter: < 5s

---

## Day-One Deployment Checklist

### T-24 Hours

- [ ] Confirm Streamlit Cloud secrets configured per `deployment_secrets_checklist.md`
- [ ] Verify Firebase credentials load (`credentials_loaded=true`)
- [ ] Confirm `ERP_PRODUCTION_MODE=1`
- [ ] Assign rollback owner and approve rollback window
- [ ] Assign customer support owner
- [ ] Notify pilot users of go-live window

### T-1 Hour

- [ ] Run pre-go-live backup (Firebase + local)
- [ ] Record backup timestamp and object path
- [ ] Verify trial balance balanced for pilot company
- [ ] Confirm all admin users can log in
- [ ] Disable or restrict Dev credentials

### Go-Live (T-0)

- [ ] Deploy or confirm latest app version on Streamlit Cloud
- [ ] Verify app starts without startup exception
- [ ] Owner login → dashboard loads
- [ ] System Admin login → config modules only
- [ ] Cashier login → POS only (branch-scoped)
- [ ] Execute one test POS sale (void if test)
- [ ] Confirm cloud backup triggers after write
- [ ] Confirm audit trail records deployment access

### T+1 Hour

- [ ] Monitor System Health diagnostics
- [ ] Confirm no unbalanced journals
- [ ] Confirm persistence self-test passes
- [ ] Check for startup errors in Streamlit logs

---

## Post-Deployment Verification Checklist

### Within 24 Hours

- [ ] All 10 roles can log in (per `live_uat_checklist.md`)
- [ ] POS sale → inventory → journal → audit chain verified
- [ ] Customer invoice → payment → AR reduction verified
- [ ] Supplier bill → payment → AP reduction verified
- [ ] Trial Balance, Balance Sheet, Income Statement reconcile
- [ ] Cloud backup uploaded after business writes
- [ ] No permission escalation observed
- [ ] Branch isolation confirmed for branch-scoped roles

### Within 1 Week

- [ ] Complete full role-by-role UAT sign-off
- [ ] Capture performance timings against targets
- [ ] Finance validates VAT/NHIL report formats
- [ ] Banking/cash drawer close procedure certified
- [ ] Inventory adjustment/import scenarios tested
- [ ] Fixed asset depreciation cycle tested
- [ ] External monitoring configured and tested
- [ ] Incident response runbook reviewed with team

### Ongoing

- [ ] Weekly backup verification (local + cloud company count match)
- [ ] Monthly restore rehearsal to staging
- [ ] Quarterly permission audit
- [ ] Review `final_go_live_blockers.md` for new risks

---

## Rollback Checklist

### Trigger Conditions

- Unbalanced trial balance after deployment
- Data corruption or missing companies after restore
- Critical permission escalation discovered
- Startup failure that cannot be resolved within rollback window
- Accounting integrity failure confirmed by finance

### Rollback Steps

1. [ ] **Announce freeze** — stop all user writes immediately
2. [ ] **Identify last known good backup** — Firebase object timestamp or Supabase snapshot
3. [ ] **Export current broken state** — for forensic analysis (do not overwrite good backup)
4. [ ] **Restore to staging first**
   - SQLite: cloud restore or local file restore to isolated environment
   - Postgres: Supabase restore to staging project
5. [ ] **Validate staging restore**
   - Row counts for all critical tables
   - Trial balance balances
   - Sample financial reports reconcile
   - Admin users can log in
6. [ ] **Switch production runtime**
   - Update Streamlit secrets if Postgres
   - Or replace runtime SQLite file
7. [ ] **Verify production**
   - Smoke test: login, dashboard, POS, one report
   - Confirm audit trail shows rollback event
8. [ ] **Document rollback**
   - Operator, timestamp, source backup id, target, validation results
   - Root cause analysis assigned
9. [ ] **Notify stakeholders** — business owner, finance, users

### Rollback Safety (Pre-Certified)

- Pre-restore safety copy created automatically
- Restore guard prevents unsafe cloud overwrite post-restore
- Upload guard prevents data loss from stale cloud backup
- Migration pre-backup exists but auto-rollback on migration failure is intentionally disabled

---

## Conditions for Upgrading to Full GO

| Condition | Required For |
|---|---|
| Live Firebase backup/restore rehearsal with sign-off | Unrestricted go-live |
| Supabase backup SOP rehearsed (if Postgres backend) | Postgres production |
| All 10 roles browser UAT signed off | Unrestricted go-live |
| Performance timings within pilot targets | High-volume tenants |
| Finance VAT/NHIL/payroll statutory sign-off | Tax compliance go-live |
| External monitoring configured | 24/7 SLA |
| Rollback owner assigned and runbook tested | All production |

---

## Sign-Off Block

| Stakeholder | Decision | Signature | Date |
|---|---|---|---|
| Business owner | [ ] Approve pilot / [ ] Reject | | |
| Finance owner | [ ] Approve pilot / [ ] Reject | | |
| Technical owner | [ ] Approve pilot / [ ] Reject | | |

**Approved deployment mode:** [ ] SQLite pilot [ ] PostgreSQL staging [ ] Other: _________

**Approved rollback window:** From _________ To _________  
**Rollback owner:** _______________________

---

## Related Reports

- `final_go_live_blockers.md` — Risk register
- `deployment_secrets_checklist.md` — Secrets and backend switching
- `backup_restore_rehearsal_steps.md` — Backup/restore runbook
- `live_uat_checklist.md` — Role-based UAT
- `erp_production_readiness_certification.md` — Prior certification (5B.18A)
- `erp_performance_certification.md` — Performance targets (5B.18B)
- `erp_remaining_blockers.md` — Prior blockers (superseded by final_go_live_blockers.md)
