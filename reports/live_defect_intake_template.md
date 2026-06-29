# Live Defect Intake Template — Sprint 1

**Sprint:** Launch Validation Sprint 1  
**Generated at:** 2026-06-28  
**Purpose:** Standard template for logging live browser UAT defects and launch blocking decisions.

Copy completed entries to `reports/launch_blocker_tracker.md` Live Defect Register.

---

## Defect Record Template

| Field | Value |
|---|---|
| **Defect ID** | DEF-___ |
| **Severity** | [ ] Critical [ ] High [ ] Medium [ ] Low |
| **Status** | [ ] Open [ ] Fixed [ ] Verified |
| **Module** | _______________________ |
| **Role** | _______________________ |
| **Owner** | _______________________ |
| **Launch blocking decision** | [ ] BLOCKS LAUNCH [ ] DOES NOT BLOCK LAUNCH [ ] POST-LAUNCH IMPROVEMENT |
| **Reported by** | _______________________ |
| **Reported date** | _______________________ |
| **Runtime URL** | _______________________ |
| **App version / commit** | _______________________ |

---

## Defect Details

**Title:** _______________________

**Steps to reproduce:**
1. 
2. 
3. 

**Expected result:** _______________________

**Actual result:** _______________________

**Evidence:**
- Log excerpt, error message, or diagnostic output: _______________________
- Related test ID (from `live_browser_uat_sprint_1.md` or `role_based_live_uat_matrix.md`): _______________________

**Screenshot:**
- File name or link: _______________________
- [ ] Screenshot attached

---

## Triage

| Severity | Criteria | Default Launch blocking decision |
|---|---|---|
| **Critical** | Data loss, accounting integrity failure, security breach, unrecoverable error | **BLOCKS LAUNCH** |
| **High** | Core workflow broken; permission escalation; pilot-blocking | **BLOCKS LAUNCH** (waiver requires sign-off) |
| **Medium** | Degraded workflow; workaround available | **DOES NOT BLOCK LAUNCH** |
| **Low** | Cosmetic, minor UX, documentation | **DOES NOT BLOCK LAUNCH** |

**Triage owner:** _______________________  
**Triage date:** _______________________

---

## Resolution

| Field | Value |
|---|---|
| **Fix description** | _______________________ |
| **Fix owner** | _______________________ |
| **Fix date** | _______________________ |
| **Status after fix** | [ ] Fixed [ ] Verified |
| **Verification evidence** | _______________________ |
| **Verified by** | _______________________ |
| **Verified date** | _______________________ |

**Re-test Module / Role:** _______________________

---

## Example Defect Entry

| Field | Example Value |
|---|---|
| Defect ID | DEF-001 |
| Severity | High |
| Status | Open |
| Module | POS |
| Role | Cashier |
| Owner | Technical Owner |
| Launch blocking decision | BLOCKS LAUNCH |
| Title | POS checkout fails after item scan |
| Evidence | Streamlit error: "Transaction wrapper failed" in runtime logs |
| Screenshot | sprint1-def001-pos-checkout.png |

---

## Defect Log (Active Sprint 1)

| Defect ID | Severity | Module | Role | Owner | Status | Launch blocking decision | Evidence | Screenshot |
|---|---|---|---|---|---|---|---|---|
| | Critical / High / Medium / Low | | | | Open / Fixed / Verified | | | |
| | Critical / High / Medium / Low | | | | Open / Fixed / Verified | | | |
| | Critical / High / Medium / Low | | | | Open / Fixed / Verified | | | |

---

## Related Reports

- `reports/launch_blocker_tracker.md`
- `reports/live_browser_uat_sprint_1.md`
- `reports/role_based_live_uat_matrix.md`
