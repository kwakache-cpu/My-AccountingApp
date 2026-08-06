# Program C — Live UAT Defect Register (Round 1)

**Branch:** `program-c-live-business-acceptance-round-1`  
**Date:** 2026-08-04  
**Rule:** Every failure needs a row. Do not fix during audit unless it blocks all further testing.

---

## Severity / launch blocking guide

| Severity | Launch blocking default |
|----------|-------------------------|
| Critical | YES |
| High | YES unless explicitly waived by Owner + Accountant |
| Medium | NO |
| Low | NO |

---

## Defects logged this Round 1 session

### New live-discovered defects

| Defect ID | Workflow | Role | Severity | Status |
|-----------|----------|------|----------|--------|
| DEF-PC-RA-001 | Paystack initialization | Registrant | High | **Remediated on branch** — local secrets lacked public key/callback; resolver hardened |
| DEF-PC-RA-002 | Secure Login landing | Unauthenticated | Medium | **Fixed** on branch — cold-start `import app` double `login_ui()` |
| DEF-PC-RA-003 | Public System Status | Unauthenticated | High | **Fixed** on branch — removed from login tabs; admin-only |
| DEF-PC-RA-004 | Public admin recovery | Unauthenticated | Critical | **Fixed** on branch — token + authenticated recovery route required |

### DEF-PC-RA-001 — Paystack public key not configured (Round A stop)

| Field | Value |
|-------|-------|
| Workflow | Paystack initialization (Round A #2) |
| Role | Unauthenticated registrant |
| Severity | High (Critical for paid activation) |
| Reproduction | Register company → Create Trial Company & Proceed to Payment on local Streamlit |
| Expected | Paystack checkout starts, or clear fix instructions with configured keys |
| Actual | “Paystack public key is not configured yet. Trial access remains active until 2026-08-11. Support Code: 9087A613E2D5” |
| Evidence | `reports/evidence/program_c_r1/RA04_paystack_key_missing_support_code.png`; company `EKA-PAY-CMOM-6715` |
| Forensic finding (2026-08-06) | Local `.streamlit/secrets.toml` contains **only** `PAYSTACK_SECRET_KEY` among Paystack keys. `PAYSTACK_PUBLIC_KEY` and `PAYSTACK_CALLBACK_URL` are **absent** from the file Streamlit loads for this workspace. Env vars for those keys were also missing. Runtime correctly reported missing. |
| Re-verify (2026-08-06 clean) | After clearing env, resolution from local secrets.toml: SECRET=`st.secrets root` / present; PUBLIC=`missing`; CALLBACK=`missing`; CURRENCY=`default`/`GHS`. Claim that public key/callback were already in Streamlit secrets does **not** match this workspace secrets file (root keys: DB_NAME, FIREBASE_*, MASTER_KEY, OPENAI_API_KEY, PAYSTACK_SECRET_KEY only; no nested `[paystack]`). |
| Code remediation | Hardened `_read_secret_or_env` / `get_paystack_runtime_config` precedence: env → root `st.secrets` → nested `[paystack]` → default(currency only). Added admin-only source diagnostic (no values). |
| Ops action still required | Add non-empty `PAYSTACK_PUBLIC_KEY` and `PAYSTACK_CALLBACK_URL` (root or `[paystack]`) then restart Streamlit and retest W2. |
| Accounting risk | None (no money moved) |
| Data risk | Low — trial company created |
| Workaround | Use trial until 2026-08-11; configure public key + callback |
| Recommended priority | P0 for paid onboarding |
| Owner | Ops / Deployer + Engineering (resolver) |
| Status | **Remediated on branch** (resolver); **live retest pending** after secrets are actually present |
| Launch blocking | YES for paid go-live until live W2 PASS |

### DEF-PC-RA-002 — Intermittent duplicate Streamlit login key

| Field | Value |
|-------|-------|
| Workflow | Secure Login landing |
| Role | Unauthenticated |
| Severity | Medium |
| Reproduction | First cold load of `/` once showed DuplicateElementKey for `v3_final_access_key_field` |
| Expected | Clean login form |
| Actual | Exception banner on one load; not reproduced on later loads before registration |
| Evidence | First-session browser snapshot text (error string); later screenshots clean |
| Accounting risk | None |
| Data risk | None |
| Root cause | Cold-start `run_process_startup_warmup()` did `import app` while Streamlit ran the script as `__main__`, re-executing module-level `login_ui()` and registering `v3_final_access_key_field` twice. Warm cache skipped the import → intermittent. |
| Fix | `app.py`: guard Streamlit entrypoint with `if __name__ == "__main__":`. `modules.py`: warmup prefers `sys.modules["__main__"]` for nav metadata. Tests: `tests/test_hotfix_streamlit_duplicate_login_key.py`. |
| Workaround | Refresh page (pre-fix) |
| Recommended priority | P2 (resolved on this branch) |
| Owner | Engineering |
| Status | **Fixed** on `program-c-round-a-onboarding-and-administration` (not committed unless requested) |
| Launch blocking | NO |

### DEF-PC-RA-003 — Public System Status exposure

| Field | Value |
|-------|-------|
| Workflow | Unauthenticated login landing |
| Role | Unauthenticated / ordinary client |
| Severity | High |
| Reproduction | Open `/` → **System Status** tab shows API Gateway, Database Engine, Payment Server, uptime, incidents |
| Expected | No infrastructure diagnostics before authentication |
| Actual | Public fourth tab rendered `show_system_status()` without auth |
| Path | `login_ui()` → `st.tabs(..., "System Status")` → `with t4: show_system_status()` |
| Fix | Removed public tab; `show_system_status()` now requires auth + Dev/Master Admin/System Admin; available under Gatekeeper System Health |
| Status | **Fixed** on branch |
| Launch blocking | YES until verified on live restart |

### DEF-PC-RA-004 — Public administrative recovery exposure

| Field | Value |
|-------|-------|
| Workflow | System Recovery tab (unauthenticated) |
| Role | Unauthenticated |
| Severity | Critical |
| Reproduction | When active companies exist with zero admin-capable `users` rows, System Recovery showed “Administrative Access Repair Needed” and allowed creating System Admin for listed companies |
| Expected | Anonymous users cannot create admins or see company recovery internals |
| Actual | `_has_restored_data_without_admin_users()` auto-triggered `_show_admin_recovery_panel()` on public recovery tab |
| Path | `login_ui()` → System Recovery (`t2`) → `_show_admin_recovery_panel()` |
| Fix | Removed from public login UI. Repair requires authenticated Dev/Master Admin/System Admin + `?admin_recovery=1` route + `EKA_ADMIN_RECOVERY_TOKEN` unlock + verified recovery condition. Audited unlock/create. |
| Status | **Fixed** on branch |
| Launch blocking | YES until verified on live restart |

---

## Inherited / reconfirm-required defects (from Program A/B certification)

These are **not** invented as new Round 1 FAIL results. They remain **Open** until live reconfirm or remediation sprint.

### DEF-PC-R1-001 — Bill does not receive inventory

| Field | Value |
|-------|-------|
| Workflow | W15 Supplier bill / W14 Stock receive |
| Role | Accountant / Inventory Officer |
| Severity | High |
| Reproduction | Post supplier bill classified Inventory Purchase; check item qty |
| Expected | Clear operator understanding; optional controlled receive link |
| Actual (certified) | Bill posts Inventory GL / AP; qty unchanged until separate receive |
| Evidence | Program A Sprint 3 clarity + Program B Sprint 2 drift monitor |
| Accounting risk | Inventory GL ≠ physical subledger |
| Data risk | Overstated GL inventory if receive never done |
| Workaround | Enter bill number on Receive Reference; weekly drift monitor |
| Recommended priority | P1 |
| Owner | Product / Accounting |
| Status | Open — awaiting live reconfirm |
| Launch blocking | YES for unsupervised go-live; **NO** for supervised pilot with signed limitations |

### DEF-PC-R1-002 — Costing is last `cost_price`, not average/FIFO

| Field | Value |
|-------|-------|
| Workflow | W14 / W17 / W22 |
| Role | Accountant |
| Severity | High |
| Reproduction | Receive at new unit cost; review valuation and later COGS |
| Expected | Documented costing policy matching books |
| Actual | Last unit cost overwrite; qty×cost_price valuation |
| Evidence | Program B Sprint 4 report |
| Accounting risk | Margin distortion after cost changes |
| Data risk | Historical cost layers absent |
| Workaround | Train staff; freeze cost edits; review Inventory Valuation weekly |
| Recommended priority | P1 (costing-policy sprint) |
| Owner | Finance + Product |
| Status | Open — documented behavior |
| Launch blocking | NO if disclosed; YES if customer requires FIFO/average without disclosure |

### DEF-PC-R1-003 — Live browser UAT still 0% executed

| Field | Value |
|-------|-------|
| Workflow | All W01–W37 |
| Role | All |
| Severity | Critical (process) |
| Reproduction | Request production/pilot runtime UAT evidence |
| Expected | Completed role-based live checklist with screenshots/timings |
| Actual | Round 1 agent session: checklists created; **no LIVE_UI evidence** |
| Evidence | This register + prior `reports/live_uat_checklist.md` (0% browser) |
| Accounting risk | Unknown operator-facing failures |
| Data risk | Unknown |
| Workaround | Schedule supervised 4-hour UAT before pilot |
| Recommended priority | P0 |
| Owner | Pilot Owner + QA |
| Status | Open |
| Launch blocking | **YES** for unrestricted production; blocks unconditional GO |

### DEF-PC-R1-004 — Live backup restore rehearsal open

| Field | Value |
|-------|-------|
| Workflow | W36 Backup/recovery |
| Role | System Admin |
| Severity | Critical |
| Reproduction | Attempt documented restore with RTO measurement |
| Expected | Proven restore |
| Actual | Path exists; live restore rehearsal open (Program A) |
| Evidence | Program A go/no-go; backup readiness notes |
| Accounting risk | Irrecoverable books after incident |
| Data risk | Total loss |
| Workaround | External DB dumps until rehearsal done |
| Recommended priority | P0 |
| Owner | Ops |
| Status | Open |
| Launch blocking | YES for production; waive only for tiny SQLite pilot with daily copies |

### DEF-PC-R1-005 — VAT/NHIL finance sign-off open

| Field | Value |
|-------|-------|
| Workflow | W28 |
| Role | Accountant |
| Severity | High |
| Reproduction | Compare tax page vs expected Ghana statutory math |
| Expected | Finance-signed outputs |
| Actual | Scaffolding present; formal sign-off open |
| Evidence | Program A recommendations #5 |
| Accounting risk | Wrong filing |
| Data risk | Compliance |
| Workaround | External spreadsheet cross-check during pilot |
| Recommended priority | P0/P1 |
| Owner | Finance |
| Status | Open |
| Launch blocking | YES if filing from EKA without sign-off |

### DEF-PC-R1-006 — Flexible carton/piece/kg unit engine absent

| Field | Value |
|-------|-------|
| Workflow | W12–W18 (frozen foods) |
| Role | Inventory / Cashier |
| Severity | Medium |
| Reproduction | Buy carton, sell piece/kg |
| Expected | Unit conversion |
| Actual | Not built; Program C forbids building it this sprint |
| Evidence | Program A frozen-foods “Needs Work” |
| Accounting risk | Wrong qty/COGS if operators improvise |
| Data risk | Stock errors |
| Workaround | One sellable UOM per SKU; separate SKUs for pack sizes |
| Recommended priority | P2/P3 |
| Owner | Product |
| Status | Open — deferred by design |
| Launch blocking | NO if SKU workaround used; YES for true multi-UOM frozen ops |

### DEF-PC-R1-007 — Transfer historically risked fake P&L (mitigated in code)

| Field | Value |
|-------|-------|
| Workflow | W21 Transfer reason |
| Role | Inventory Officer |
| Severity | Medium (mitigated) |
| Reproduction | Record Transfer stock movement |
| Expected | Qty relocation without company-wide profit |
| Actual (Sprint 4) | Quantity-only transfer; no artificial COGS/equity journal |
| Evidence | Program B Sprint 4 safeguards + tests |
| Accounting risk | Residual: no dual-branch clearing yet |
| Data risk | Branch qty confusion |
| Workaround | Avoid Transfer reason for inter-branch until dual-leg exists; use notes |
| Recommended priority | P1 dual-leg transfer |
| Owner | Product |
| Status | Partially mitigated — live reconfirm required |
| Launch blocking | NO for single-branch pilot |

---

## Blocker stop rule

If a Critical defect prevents continuing the sequence (e.g., cannot login, cannot post balanced journals, data corruption), **stop UAT**, log the defect, and report before any code change.

**This session:** No runtime blocker encountered because live UI session did not start. Process blocker **DEF-PC-R1-003** prevents Round 1 live acceptance closure.
