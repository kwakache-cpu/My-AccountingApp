# Program C — Round A Live Operator Acceptance (Onboarding & Administration)

**Branch:** `program-c-round-a-onboarding-and-administration`  
**Session date:** 2026-08-04  
**Runtime:** local Streamlit `http://localhost:8501/`  
**Operator role:** Unauthenticated visitor → trial company Owner path  
**Stop rule:** Stop on first failure; do not continue until that workflow passes.

---

## Round A scope (13 workflows)

1. Registration  
2. Paystack initialization  
3. Trial activation  
4. Secure login  
5. Secure logout  
6. Company Profile  
7. Branch setup  
8. User creation  
9. User editing  
10. Role assignment  
11. Password change  
12. Password recovery  
13. Company wipe (trial company)

---

## STOP decision

| Workflow | Status | Why stop |
|----------|--------|----------|
| 1 Registration | **PASS** | Company created |
| 2 Paystack initialization | **FAIL** | `PAYSTACK_PUBLIC_KEY` not configured |
| 3 Trial activation | **PASS** (observed with W1/W2) | Trial active until 2026-08-11 |
| 4–13 | **NOT EXECUTED** | Stopped after W2 per Round A rule |

**Code change this Round A live session:** none. Failure is environment/config (local secrets contain `PAYSTACK_SECRET_KEY` only; public key/callback absent). Fabricating a public key is not allowed.

### Follow-up remediation (2026-08-06, same branch — uncommitted)

| Item | Result |
|------|--------|
| Secrets forensics | Confirmed local `.streamlit/secrets.toml` has Paystack **secret only**; public/callback missing. Clean resolution: SECRET=`st.secrets root`, PUBLIC/CALLBACK=`missing`, CURRENCY=`default`. |
| Resolver hardening | Env → root secrets → nested `[paystack]`; empty treated as missing |
| Public System Status | Removed from login tabs; admin-only |
| Public admin repair | Removed; token + authenticated recovery route required |
| Live W2 retest | **Pending** after operator adds real public key + callback and restarts Streamlit |

---

## Workflow evidence records

### 1. Registration — PASS

| Field | Value |
|-------|-------|
| Role | Unauthenticated registrant |
| Expected | Trial company created with unique name |
| Actual | Company `UAT-PC-RA Frozen Foods Ltd` key `EKA-PAY-CMOM-6715` present in `data/eka_enterprise_v3.db` |
| Elapsed | ~15s form fill + submit (approximate wall clock) |
| Screenshot | `reports/evidence/program_c_r1/RA02_registration_form_filled.png` |
| Support code | (see Paystack message on same submit) |
| Audit evidence | DB row company key/name |
| Status | **PASS** |
| Severity | — |
| Launch blocker? | NO |

### 2. Paystack initialization — FAIL

| Field | Value |
|-------|-------|
| Role | Unauthenticated registrant (same submit) |
| Expected | Paystack checkout initializes, or clear actionable config error |
| Actual | Warning: “Paystack public key is not configured yet. Trial access remains active until 2026-08-11. Support Code: 9087A613E2D5” |
| Elapsed | Same submit as registration (~2s response after click) |
| Screenshot | `reports/evidence/program_c_r1/RA04_paystack_key_missing_support_code.png` |
| Support code | `9087A613E2D5` |
| Audit evidence | UI warning + secrets.toml inspection: `PAYSTACK_SECRET_KEY` present, `PAYSTACK_PUBLIC_KEY` missing |
| Status | **FAIL** |
| Severity | **High** (Critical for paid activation path) |
| Launch blocker? | **YES** for paid onboarding; **NO** for trial-only supervised pilot if Owner accepts unpaid trial |

### 3. Trial activation — PASS

| Field | Value |
|-------|-------|
| Role | Same |
| Expected | 7-day trial access active after registration |
| Actual | UI states trial active until **2026-08-11**; company persisted |
| Elapsed | Included in registration submit |
| Screenshot | `RA04_paystack_key_missing_support_code.png` |
| Support code | `9087A613E2D5` |
| Audit evidence | Company row + UI trial expiry |
| Status | **PASS** |
| Severity | — |
| Launch blocker? | NO |

### 4–13 — NOT EXECUTED

Stopped after Paystack FAIL. No fabricated results.

Landing page screenshot prior to registration: `RA01_landing_secure_login.png`.

**Observation (not Round A stop):** First page load once showed `StreamlitDuplicateElementKey` for `v3_final_access_key_field`. Subsequent loads did not reproduce before registration. Logged as Medium watch item `DEF-PC-RA-002`.

**Hotfix follow-up (same branch):** Root cause was cold-start process warmup `import app` re-running module-level `login_ui()` under a second module name. Fixed via `__main__` entrypoint guard + warmup preferring `__main__` nav metadata. Regression: `tests/test_hotfix_streamlit_duplicate_login_key.py`. Status: **Fixed** on branch (not committed unless requested).

---

## Round A totals

| Status | Count |
|--------|------:|
| PASS | 2 (Registration, Trial activation) |
| PARTIAL | 0 |
| FAIL | 1 (Paystack initialization) |
| NOT EXECUTED | 10 |

---

## Required fix before continuing Round A

Configure a real `PAYSTACK_PUBLIC_KEY` (and matching secret) in Streamlit secrets/env for the local/pilot runtime. Re-run **only** Paystack initialization until PASS, then resume workflows 4–13.
