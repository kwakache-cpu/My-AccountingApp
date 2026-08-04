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
| — | — | — | — | **None** — live browser UAT not executed; no new live failures observed |

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
