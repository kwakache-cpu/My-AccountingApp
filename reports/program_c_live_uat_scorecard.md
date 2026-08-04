# Program C — Live UAT Scorecard (Round 1)

**Date:** 2026-08-04  
**Branch:** `program-c-live-business-acceptance-round-1`  
**Program A baseline overall product:** **6.8/10**  
**Rule:** Do not inflate. Live UI not executed this session → scores stay conservative.

---

## 1. Workflow outcome totals (Round 1 session)

| Status | Count | Notes |
|--------|------:|-------|
| PASS | 0 | No LIVE_UI PASS allowed without screenshots/timings |
| PARTIAL | 0 | Automated proof kept in evidence index; not promoted to PARTIAL live status |
| FAIL | 0 | No new live FAIL |
| NOT EXECUTED | 37 | Full checklist pending operator session |

---

## 2. Dimension scores (/10)

| Dimension | Program A (approx) | Round 1 score | Rationale |
|-----------|--------------------|---------------|-----------|
| Onboarding | 7.0 | **6.5** | Auto/Paystack paths certified in tests; live init not re-run |
| Accounting integrity | 7.5 | **7.5** | Journal engine strong; bill≠stock drift remains |
| Inventory integrity | 5.5→6.5 (B) | **7.0** | Sprint 3 movements + Sprint 4 valuation detection; live unused |
| POS | 7.0→7.5 (B) | **7.5** | Permission + movements hardened; live timings absent |
| Purchasing | 5.5 | **5.5** | Bill/receive still split; monitor only |
| Receivables | 7.0 | **7.0** | Lifecycle auto-certified; live shortcut gaps remain |
| Payables | 7.0 | **6.5** | AP works; inventory purchase confusion remains operational risk |
| Banking/cash | 6.5 | **6.5** | Journals exist; recon matching weak |
| Payroll | 6.5 | **6.5** | Posts in tests; statutory sign-off open |
| Assets | 6.0 | **6.0** | Acquisition/depr tests; disposal missing |
| Tax | 6.0 | **5.5** | No live finance sign-off |
| Reporting | 8.0 | **8.0** | Strong auto cert; live warm timings not measured |
| Permissions | 6.5 | **7.0** | Lockdown + POS role gate; live matrix not clicked |
| Performance | 6.5 | **6.0** | Targets defined; **zero live timings captured** |
| Usability | 5.5 | **5.5** | Streamlit density; frozen multi-UOM gap |
| Reliability | 7.0 | **7.0** | Regression green this session; backup rehearsal open |
| Ghana SME readiness | 6.0 | **6.0** | Retail mostly ready; frozen foods needs work |
| **Overall product readiness** | **6.8** | **6.9** | Slight lift from inventory integrity only; **not** a live-acceptance pass |

**Why only +0.1 overall:** Program B inventory controls are real code improvements, but Round 1 did not complete live business acceptance. Inflating beyond 7.0 would violate honesty rules.

---

## 3. Critical and High items (launch lens)

| ID | Summary | Launch blocking |
|----|---------|-----------------|
| DEF-PC-R1-003 | Live browser UAT not executed | YES (unconditional GO) |
| DEF-PC-R1-004 | Backup restore rehearsal open | YES (production) |
| DEF-PC-R1-001 | Bill ≠ receive stock | YES unsupervised / NO supervised with waiver |
| DEF-PC-R1-005 | VAT/NHIL sign-off open | YES if filing from EKA |
| DEF-PC-R1-002 | Costing method limitations | Disclosure-dependent |

---

## 4. Performance timings

| Metric | Target | Actual | Result |
|--------|--------|--------|--------|
| Cold login | < 3s | **Not measured** | Incomplete |
| Warm login | < 3s | **Not measured** | Incomplete |
| Dashboard first / rerun | < 3s | **Not measured** | Incomplete |
| POS open / lookup / sale | < 1s / < 2s | **Not measured** | Incomplete |
| Bill / receipt save | < 2s | **Not measured** | Incomplete |
| Valuation / TB / IS / BS | < 5s warm | **Not measured** | Incomplete |
| Company Profile | < 3s | **Not measured** | Incomplete |
| System Health fast | < 3s | **Not measured** | Incomplete |

---

## 5. Top 10 user-friction points (ranked)

1. Supplier bill does not receive stock (training + drift risk)  
2. Inventory valuation can disagree with Inventory GL without auto-fix  
3. Costing method not policy-grade (last cost overwrite)  
4. Frozen foods carton→piece/kg not supported  
5. Duplicate invoice/bill UI paths (training cost)  
6. Dense Streamlit navigation / menu sprawl  
7. Tax outputs need external finance confirmation  
8. Bank reconciliation is display-oriented, not match workflow  
9. No notification engine for low stock / overdue AR  
10. Live restore confidence missing for operators  

---

## 6. Top 10 strengths observed (platform evidence)

1. Balanced journal posting engine with tests  
2. Trial Balance / P&L / Balance Sheet certification path  
3. POS credit sale inventory + AR + audit automation  
4. Supplier bill/payment AP lifecycle automation  
5. Sprint 3: qty change ⇒ stock movement integrity  
6. Sprint 4: inventory vs GL reconciliation visibility  
7. Role permission matrix with regression lockdown  
8. Safe user-facing errors (no raw DB dumps to clients)  
9. Dual SQLite/PostgreSQL portability posture  
10. Controlled corrections / audit trail patterns  

---

## 7. Ghana SME usability findings

| Topic | Finding | Rank |
|-------|---------|------|
| Mobile Money | Supported as tender in product model; live UX not timed | P1 confirm live |
| Cash/Bank | Present; clarity depends on account naming | Medium |
| VAT/NHIL terms | Present on tax surfaces; sign-off open | High |
| GHS presentation | Currency helpers exist | Medium confirm |
| Retail clarity | Mostly ready (Program A) | — |
| Carton/piece/kg | **Gap** — do not build engine in Program C | High for frozen |
| Partial units | Limited — SKU workaround | Medium |
| Receipts | Exist; live usefulness unrated | Medium |
| Payment clarity | Improved pages; legacy duplicates remain | Medium |
| Non-accountant ease | Partial — needs pilot training | High |

---

## 8. GO / CONDITIONAL GO / NO-GO

### Decision for Round 1 closure

# CONDITIONAL GO (supervised 5-person pilot only)

**Not** unconditional production GO.  
**Not** 20+ person GO.

### Conditions (must remain)

1. Complete live browser UAT (this checklist) with screenshots before expanding users.  
2. Owner signs known-limitations: bill≠receive; last-cost valuation; no multi-UOM.  
3. Weekly Trial Balance + Inventory Valuation review by accountant.  
4. Daily/local backup until restore rehearsal signed.  
5. Do not file VAT/NHIL from EKA without finance sign-off.  
6. Use SQLite only for low-concurrency single branch; Postgres production cutover remains separate NO-GO until certified.

### Why not NO-GO for tiny pilot

Core accounting chains and inventory movement/valuation detection are stronger than Program A baseline; regression green. Tiny supervised pilot remains the honest path.

### Why not GO

Zero LIVE_UI workflow PASSes in Round 1; Critical process gap DEF-PC-R1-003.
