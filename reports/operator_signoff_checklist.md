# Operator Sign-Off Checklist — Phase 5B.18E

**Phase:** 5B.18E  
**Generated at:** 2026-06-27  
**Purpose:** Capture operator and stakeholder approvals for release candidate deployment.

## Sign-Off Scope

The operator sign-off checklist covers deployment readiness, production secrets, rollback planning, and first-customer onboarding readiness.

- **STREAMLIT SECRET REQUIRED** — production secrets validated
- **FIREBASE ACTION REQUIRED** — Firebase backup/restore credentials and object path verified
- **DATABASE ACTION REQUIRED** — backend selection and `DATABASE_URL` validated
- **SUPABASE ACTION REQUIRED** — Postgres backup/restore SOP and staging rehearsal documented when Postgres runtime is enabled

---

## Operator Readiness

| Task | Status |
|---|---|
| Release candidate checklist reviewed | [ ] |
| Live app smoke test checklist reviewed | [ ] |
| Production rollback checklist reviewed | [ ] |
| First customer onboarding checklist reviewed | [ ] |
| Firebase backup and restore path validated | [ ] |
| Runtime backend diagnostics verified | [ ] |
| Log and audit trail access confirmed | [ ] |
| Rollback plan and owner assigned | [ ] |
| External monitoring or alerting ownership assigned | [ ] |

---

## Stakeholder Approvals

### Technical Owner
- [ ] Confirm app build and runtime diagnostics
- [ ] Confirm `ERP_PRODUCTION_MODE=1` and runtime security controls
- [ ] Confirm no code changes are required for release candidate status
- [ ] Confirm rollback runbook accessible

### Business Owner
- [ ] Confirm business process readiness for pilot or controlled rollout
- [ ] Confirm finance and statutory sign-off requirements captured
- [ ] Confirm customer communication plan agreed
- [ ] Approve go-live window and rollback window

### Finance Owner
- [ ] Confirm Trial Balance, VAT, NHIL, and payroll reporting readiness
- [ ] Confirm accounting integrity controls are effective
- [ ] Approve pilot financial risk and monitoring plan

### Operator
- [ ] Confirm operational checklist is complete
- [ ] Confirm first customer onboarding plan is ready
- [ ] Confirm post-deploy verification ownership assigned
- [ ] Approve release candidate deployment

---

## Sign-Off Record

| Name | Role | Approval | Signature | Date |
|---|---|---|---|---|
|  | Technical Owner | [ ] |  |  |
|  | Business Owner | [ ] |  |  |
|  | Finance Owner | [ ] |  |  |
|  | Operator | [ ] |  |  |

---

## Notes

This sign-off is a release candidate certification, not a final unrestricted go-live approval. It is intended to ensure that the deployment is ready for pilot and controlled rollout while preserving rollback and compliance controls.
