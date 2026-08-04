# Program C — Live Business Acceptance Round 1

**Branch:** `program-c-live-business-acceptance-round-1`  
**Date opened:** 2026-08-04  
**Sprint type:** Live workflow validation (documentation + evidence)  
**Baseline:** Program A overall product **6.8/10**; Program B P0 inventory movement + valuation integrity merged  

---

## Strict rules (this sprint)

- No features, refactors, schema changes, or accounting-rule changes.
- Do not mark **PASS** without evidence.
- Do not hide failed workflows.
- Prefer stopping on launch blockers over silent workarounds.

---

## Test business profile (controlled UAT company)

| Field | Value |
|-------|-------|
| Suggested company name | `UAT PC R1 Frozen Foods Ltd` |
| Suggested company key pattern | `UAT-PC-R1-*` (must be wipeable) |
| Vertical | Ghana retail / frozen foods SME |
| Branch | One main branch (`MAIN`) |
| Roles | Owner/CEO, Accountant, Cashier, Inventory Officer, Auditor/Read Only, System Admin or Dev |
| Tender types | Cash, Bank, Mobile Money |
| Parties | At least 2 customers, 2 suppliers |
| Stock model | Carton purchase / piece or kg sale **only where currently supported** |
| Tax | VAT/NHIL where applicable |
| Data marking | All UAT entities named with prefix `UAT-PC-R1` for later wipe |

**Wipe rule:** Use approved company wipe / Hotfix-004 lifecycle path only on clearly marked UAT companies. Never wipe production.

---

## Evidence classes

| Code | Meaning | May support PASS? |
|------|---------|-------------------|
| `LIVE_UI` | Browser/operator session against running app with screenshots/timings | Yes |
| `AUTO_CERT` | Automated functional/regression test with journal/qty assertions | Supports **PARTIAL** only for live acceptance |
| `CODE_TRACE` | Static verification from Program B sprints / code review | Supports documentation, not PASS |
| `KNOWN_GAP` | Documented in Program A/B; not re-proven this round | Defect register only until live reconfirm |

**Round 1 agent session finding:** No approved live runtime URL was available and no interactive browser UAT session was executed. Automated regression was green. Therefore **zero workflows are marked PASS for live business acceptance**.

---

## Companion files

| File | Purpose |
|------|---------|
| `reports/program_c_live_uat_defect_register.md` | Defect log |
| `reports/program_c_live_uat_scorecard.md` | Scores + GO decision |
| `reports/program_c_live_uat_evidence_index.md` | Evidence map |

---

## Acceptance criteria fields (every workflow)

For each workflow below, the live operator must capture:

- Role used  
- Start time / End time / Elapsed  
- Steps taken  
- Expected vs Actual  
- Accounting impact  
- Inventory impact  
- Audit trail evidence  
- Screenshot/evidence reference  
- Status: `PASS` | `PARTIAL` | `FAIL` | `NOT EXECUTED`  
- Severity (if not PASS): Critical / High / Medium / Low  
- Launch blocking: YES / NO  

---

## Round 1 workflow checklist (37)

### Legend for Round 1 status column

Statuses below reflect **this agent session**. Operators must overwrite with live results.

| ID | Workflow | Role (primary) | Expected result (summary) | Accounting proof required | Inventory proof required | Round 1 status | Severity if fail | Launch blocking if fail | Evidence class |
|----|----------|----------------|---------------------------|---------------------------|--------------------------|----------------|------------------|-------------------------|----------------|
| W01 | Company registration | Owner | Trial company created; unique name enforced | Company + subscription rows | N/A | **NOT EXECUTED** | Critical | YES | — |
| W02 | Paystack initialization | Owner | Checkout init succeeds or clear config error | Payment attempt logged safely | N/A | **NOT EXECUTED** | Critical | YES | AUTO_CERT available in suite; live unpaid |
| W03 | Trial/subscription activation | Owner | License active for trial path | Subscription status active | N/A | **NOT EXECUTED** | Critical | YES | — |
| W04 | Secure login/logout | All | Auth resolves company/branch/user; logout clears session | N/A | N/A | **NOT EXECUTED** | Critical | YES | AUTO_CERT lockdown login tests |
| W05 | Company Profile | Owner/Admin | Profile loads; **no DDL on render** | Company settings persist | N/A | **NOT EXECUTED** | High | YES | CODE_TRACE / lockdown |
| W06 | Branch setup | Owner/Admin | MAIN branch usable | Branch row exists | Movements carry branch_id | **NOT EXECUTED** | High | YES | — |
| W07 | User creation | Owner/Admin | Staff users created | Audit of user create | N/A | **NOT EXECUTED** | High | YES | — |
| W08 | Role assignment | Owner/Admin | Roles map to permission matrix | N/A | N/A | **NOT EXECUTED** | High | YES | AUTO_CERT permission tests |
| W09 | Chart of Accounts | Accountant | Core accounts present; posting rules hold | COA queryable | N/A | **NOT EXECUTED** | High | YES | AUTO_CERT |
| W10 | Customer creation | Accountant/Cashier | Customer master usable on credit sale | Customer row | N/A | **NOT EXECUTED** | Medium | NO | AUTO_CERT AR lifecycle |
| W11 | Supplier creation | Accountant/Inv | Supplier usable on bills | Supplier row | N/A | **NOT EXECUTED** | Medium | NO | AUTO_CERT AP lifecycle |
| W12 | Item/inventory creation | Inv Officer | Item with cost_price + sell price | Optional opening JE | Item qty | **NOT EXECUTED** | High | YES | — |
| W13 | Opening stock | Inv/Accountant | Opening qty + valued movement/JE where designed | Opening JE if value>0 | OPENING_BALANCE movement | **NOT EXECUTED** | High | YES | CODE_TRACE Sprint 3 |
| W14 | Stock receive | Inv Officer | Qty↑; cost may overwrite cost_price; **no silent bill link** | No receive journal unless separate | STOCK_IN movement | **NOT EXECUTED** | High | YES | AUTO_CERT / Sprint 3–4 |
| W15 | Supplier bill | Accountant | AP + GL; **does not receive stock** | Bill JE; AP↑ | Qty unchanged | **NOT EXECUTED** | Critical | YES | AUTO_CERT + drift notice |
| W16 | Supplier payment | Accountant | AP↓; cash/bank/MoMo credit | Payment JE | N/A | **NOT EXECUTED** | High | YES | AUTO_CERT |
| W17 | POS cash sale | Cashier | Sale + stock↓ + COGS if cost>0 | Revenue + COGS JEs | POS_SALE movement | **NOT EXECUTED** | Critical | YES | AUTO_CERT POS |
| W18 | POS credit sale | Cashier | AR↑ + stock↓ | Revenue/AR + COGS | POS_SALE movement | **NOT EXECUTED** | Critical | YES | AUTO_CERT credit sale |
| W19 | POS return/correction | Cashier/Manager | Restock + reverse value path | Return JEs | POS_RETURN movement | **NOT EXECUTED** | High | YES | AUTO_CERT / Sprint 3 |
| W20 | Customer receipt | Accountant | AR↓; tender account↑ | Receipt JE | N/A | **NOT EXECUTED** | High | YES | AUTO_CERT |
| W21 | Inventory movement review | Accountant/Inv | Movement history complete | N/A | One movement per qty change | **NOT EXECUTED** | High | YES | Sprint 3 tests |
| W22 | Inventory valuation review | Accountant | Subledger vs Inventory GL status | MATCHED/REVIEW/CRITICAL | qty×cost_price | **NOT EXECUTED** | High | YES | Sprint 4 tests |
| W23 | Cash book | Accountant | Cash movements visible | Cash account activity | N/A | **NOT EXECUTED** | Medium | NO | — |
| W24 | Banking/cash movement | Accountant | Transfer/loan/equity journals | Balanced JEs | N/A | **NOT EXECUTED** | Medium | NO | AUTO_CERT banking patterns |
| W25 | Payroll processing | HR/Accountant | Payroll post + statutory lines | Payroll JE linked | N/A | **NOT EXECUTED** | High | YES | AUTO_CERT payroll |
| W26 | Asset acquisition | Accountant | Asset + GL | Acquisition JE | N/A | **NOT EXECUTED** | Medium | NO | AUTO_CERT assets |
| W27 | Depreciation | Accountant | Book value↓; expense posted | Depreciation JE | N/A | **NOT EXECUTED** | Medium | NO | AUTO_CERT |
| W28 | VAT/NHIL reporting | Accountant | Tax page readable; math reviewable | Tax balances | N/A | **NOT EXECUTED** | High | YES | KNOWN_GAP finance sign-off |
| W29 | General Journal | Accountant | Balanced post; unbalanced blocked | JE + lines | N/A | **NOT EXECUTED** | Critical | YES | AUTO_CERT |
| W30 | Trial Balance | Accountant | Loads; debits=credits | TB from journals | N/A | **NOT EXECUTED** | Critical | YES | AUTO_CERT |
| W31 | Income Statement | Accountant | Reflects posted activity | P&L accounts | COGS if sales | **NOT EXECUTED** | High | YES | AUTO_CERT |
| W32 | Balance Sheet | Accountant | Assets=liab+equity identity | BS accounts | Inventory GL line | **NOT EXECUTED** | Critical | YES | AUTO_CERT |
| W33 | Cash Flow | Accountant | Loads without crash | Operating/invest/finance | N/A | **NOT EXECUTED** | Medium | NO | AUTO_CERT reports |
| W34 | Audit Trail | Auditor/Owner | Write actions logged | Audit rows | N/A | **NOT EXECUTED** | High | YES | AUTO_CERT |
| W35 | Dashboard | Owner | First render usable; no LV diagnostics | KPI read models | Inventory value metric | **NOT EXECUTED** | Medium | NO | Lockdown dashboard |
| W36 | Backup/recovery | System Admin | Backup path exists; restore rehearsal | N/A | N/A | **NOT EXECUTED** | Critical | YES | KNOWN_GAP live restore |
| W37 | Company wipe (UAT only) | Dev/Admin | UAT company removable safely | Company gone | Inventory gone | **NOT EXECUTED** | High | NO* | Hotfix-004 tests (*YES if wipe hits wrong company) |

---

## Round 1 totals (this session)

| Status | Count |
|--------|------:|
| PASS | **0** |
| PARTIAL | **0** (none promoted without live UI) |
| FAIL | **0** (no new live failures recorded) |
| NOT EXECUTED | **37** |

**Automated platform health (supporting, not live PASS):** regression suite executed in this Program C validation pass — see evidence index.

---

## Accounting proof checklist (per financial transaction)

Operator must verify **all** of:

1. Source document exists  
2. Exactly one expected posted journal (or documented multi-entry pattern)  
3. Journal balanced  
4. Correct debit/credit accounts  
5. Customer/supplier subledger updated when applicable  
6. Inventory qty updated when applicable  
7. Stock movement exists when qty changed (Sprint 3 contract)  
8. Valuation impact sensible when cost known (Sprint 4)  
9. Trial Balance reflects entry  
10. Financial statements reflect entry  
11. Audit trail records action  

Do **not** accept UI success toasts alone.

---

## Performance targets (live capture required)

| Surface | Target | Round 1 measured? |
|---------|--------|-------------------|
| Cold login | < 3s | **No** |
| Warm login | < 3s | **No** |
| Dashboard first load | < 3s warm preferred | **No** |
| Dashboard rerun | < 3s | **No** |
| POS open | < 1s practical | **No** |
| Barcode lookup | < 1s | **No** |
| Sale finalization | < 2s | **No** |
| Supplier bill save | < 2s | **No** |
| Customer receipt save | < 2s | **No** |
| Inventory valuation | < 5s warm | **No** |
| Trial Balance warm | < 5s | **No** |
| Income Statement warm | < 5s | **No** |
| Balance Sheet warm | < 5s | **No** |
| Company Profile | < 3s | **No** |
| System Health fast view | < 3s | **No** |

---

## Role acceptance matrix (to execute live)

| Role | Menus correct | Unauthorized hidden | Direct route denied | Allowed tasks work | Sensitive blocked | Diagnostics admin-only |
|------|---------------|---------------------|---------------------|--------------------|-------------------|------------------------|
| Owner / CEO | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED |
| Accountant | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED |
| Cashier | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED |
| Inventory Officer | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED |
| Auditor / Read Only | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED |
| System Admin / Dev | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED |

Automated permission denials exist in regression lockdown / permission tests — cited in evidence index as **PARTIAL platform evidence only**.

---

## Ghana SME practicality (evaluation prompts)

Record live observations for:

1. Mobile Money as tender  
2. Cash and bank handling clarity  
3. VAT/NHIL terminology  
4. Ghana cedi (GHS) presentation  
5. Small retail workflow clarity  
6. Carton vs piece/kg limitations (**do not build flexible-unit engine**)  
7. Partial-unit selling limitations  
8. Receipt usefulness  
9. Supplier/customer payment clarity  
10. Ease of use for a non-accountant  

Rank verified gaps in the scorecard. Round 1 agent session: **not observed live** — inherited Program A frozen-foods “Needs Work” stands.

---

## Operator script (recommended sequence)

1. Register `UAT PC R1 Frozen Foods Ltd`  
2. Complete Paystack/trial path available in environment  
3. Create users for six roles  
4. Seed COA defaults; create customers/suppliers  
5. Create 5 SKUs with cost + price; opening stock  
6. Post inventory bill **without** receive; confirm qty unchanged  
7. Receive stock with supplier bill number in reference  
8. Open Inventory Valuation; note status  
9. POS cash + credit + return  
10. Customer receipt; supplier payment (Cash + MoMo if available)  
11. Payroll mini-run; asset + depreciation  
12. Tax page review  
13. TB / P&L / BS / Cash flow  
14. Audit trail spot-check  
15. Dashboard timings  
16. Backup status note  
17. Wipe UAT company  

---

## Decision pointer

See `reports/program_c_live_uat_scorecard.md` for readiness scores and **GO / CONDITIONAL GO / NO-GO**.

**This session’s decision:** Live Round 1 acceptance is **incomplete**. Platform remains **CONDITIONAL GO** for supervised 5-person pilot pending executed browser UAT — unchanged honesty from Program A, with Program B inventory controls improving the pilot conditions.
