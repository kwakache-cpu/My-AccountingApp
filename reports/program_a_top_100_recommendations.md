# Program A — Top 100 Recommendations

**Date:** 2026-07-07  
**Context:** Core Platform Certification — ranked by business impact and urgency  
**Legend:** P0 Critical · P1 High · P2 Medium · P3 Future

---

| # | Recommendation | Pri | Business Value | Risk if Ignored | Complexity | Dependencies |
|---|----------------|-----|----------------|-----------------|------------|--------------|
| 1 | Pass `user_role` on POS `post_journal_entry` (close P0-5) | P0 | Segregation of duties; auditor trust | Cashier posts unauthorized GL | Low | `accounting_engine`, `modules.show_pos` |
| 2 | Execute browser UAT for all 10 operational roles | P0 | Human certification; find UX blockers | Unknown production failures | Low | Checklists in `reports/live_uat_checklist.md` |
| 3 | PostgreSQL write-path E2E certification (bill, POS, payment, payroll) | P0 | Production cutover safety | Data corruption on migrate | Medium | Staging Supabase, CI harness |
| 4 | Live backup restore rehearsal with documented RTO | P0 | Disaster recovery confidence | Total data loss | Medium | Firebase, ops SOP |
| 5 | Finance sign-off on VAT/NHIL/GETFund outputs | P0 | GRA compliance | Tax penalties | Low | Finance owner, taxation page |
| 6 | Finance sign-off on PAYE/SSNIT payroll outputs | P0 | Statutory payroll compliance | Employee/tax authority issues | Low | Finance owner, payroll module |
| 7 | Purchase-to-pay: optional receive-on-post for inventory bills (P1-1) | P1 | Eliminates #1 user confusion | Inventory/GL drift | High | Inventory, bills, no posting rewrite |
| 8 | Unified POS `stock_movements` writes (P1-2) | P1 | Single movement audit trail | Shrinkage invisible | Medium | POS, inventory |
| 9 | Valued inventory receive prompts GL posting (P1-3) | P1 | Bookkeeper trust | Inventory GL ≠ subledger | Medium | Receive, accounting engine |
| 10 | Invoice → Receive Payment shortcut (P1-4) | P1 | Faster collections | AR drag, user workarounds | Low | AR, payments UI |
| 11 | Persist `customer_id`/`supplier_id` on legacy tabbed payment form | P1 | Subledger accuracy | Reconciliation failures | Low | `financials.py` |
| 12 | Run payment subledger backfill with operator review | P1 | Clean AR/AP aging | Historical ambiguity | Low | Sprint 1 backfill helper |
| 13 | Dashboard AR/AP drill-down to customer/supplier (P1-5) | P1 | Owner decision speed | Blind to debtors | Medium | Dashboard, AR/AP |
| 14 | Dedicated `view_chart_of_accounts` permission (P1-8) | P1 | Structure confidentiality | Competitor staff sees COA | Low | Permissions |
| 15 | Post-registration welcome / first-login path (P1-10) | P1 | Time-to-first-value | Abandoned trials | Medium | Onboarding |
| 16 | Subscription expiry UX consistency (P1-11) | P1 | Renewal revenue | Unexpected lockout | Low | Subscription UI |
| 17 | Rename client AI "Gatekeeper Admin" → "Business Assistant" (P1-9) | P1 | Role clarity | Users fear wrong product | Low | `app.py` labels |
| 18 | Extend bill≠receive help text to legacy AP + tabbed purchase UI | P1 | Consistent training | Same confusion on alt paths | Low | Sprint 3 pattern |
| 19 | Payroll PAYE band calculation unit tests (P1-6) | P1 | Compliance confidence | Wrong tax withheld | Medium | Payroll, Ghana bands |
| 20 | Depreciation source linkage certification (P1-7) | P1 | Fixed asset audit | Weak trace | Medium | Assets, tests |
| 21 | Standardize `log_audit_action` on all write paths (P1-12) | P1 | Forensic completeness | Audit gaps | Medium | All modules |
| 22 | Bank reconciliation: statement import + match workflow | P1 | Month-end cash cert | Undetected cash errors | High | Banking, new UI |
| 23 | Resolve taxation journal vs statutory math delta | P1 | Filing confidence | Wrong return filed | Medium | Taxation, finance |
| 24 | Tax settlement workflow end-to-end test | P1 | Compliance | Settlement posts wrong | Medium | Sprint 2 tests |
| 25 | Paystack webhook test harness (P2-9) | P2 | Subscription reliability | Paid but inactive | Medium | Subscription |
| 26 | Notification engine design — low stock, overdue AR (P2-1) | P2 | Proactive ops | Stockouts, cash crunch | High | Platform |
| 27 | In-app notification center UI (P3-9) | P3 | User engagement | Alert fatigue elsewhere | High | Notification engine |
| 28 | Consolidate duplicate invoice/bill UI paths (P2-6) | P2 | Training cost | Duplicate entries | High | financials + modules |
| 29 | Guided month-end close checklist | P1 | Close discipline | Open period errors | Medium | Period close |
| 30 | Period close browser UAT execution | P1 | Lock verification | Backdated chaos | Low | UAT |
| 31 | Customer statement of account report | P1 | Collections | Manual Excel | Medium | AR reports |
| 32 | Supplier statement / remittance advice | P1 | AP professionalism | Disputes | Medium | AP reports |
| 33 | POS concurrent checkout load test on SQLite | P1 | Multi-cashier retail | Checkout failures | Medium | Performance |
| 34 | POS concurrent checkout certification on PostgreSQL | P1 | Scale path | Same on Postgres | Medium | P0 #3 |
| 35 | Financial Reports PostgreSQL benchmark in CI (P2-5) | P2 | Scale confidence | Slow TB at volume | Medium | CI, Postgres |
| 36 | Dashboard load test at 50k+ journal lines | P2 | Owner experience | Slow dashboard | Medium | Performance |
| 37 | Audit trail export performance at volume | P2 | Auditor wait time | Compliance delay | Medium | Audit |
| 38 | Mobile Money POS path isolated test | P1 | Ghana payment mix | Silent MM bugs | Low | POS tests |
| 39 | Inventory bulk import volume test | P2 | Wholesaler onboarding | Import timeout | Low | Inventory |
| 40 | Branch transfer stock movement certification | P2 | Multi-branch ops | Inter-branch drift | Medium | Inventory |
| 41 | COA account usage hints (P2-7) | P2 | Self-service accounting | Wrong account picks | Low | COA UI |
| 42 | Guided adjusting entry templates (P2-4) | P2 | Safer manual journals | Mis-postings | Medium | Journal |
| 43 | Asset disposal workflow (P2-8) | P2 | Asset lifecycle | Ghost assets on books | Medium | Assets |
| 44 | Maintenance notice on current dashboard (P2-2) | P2 | Ops communication | Users unaware of downtime | Low | Dashboard |
| 45 | Banking transaction wizards per type (P2-3) | P2 | Reduce errors | Wrong transaction type | Medium | Banking |
| 46 | Plain-language tax summary on taxation page (P2-10) | P2 | Non-accountant owners | Tax confusion | Low | Taxation |
| 47 | Plain-language executive cash summary on dashboard | P2 | Owner decisions | Data without insight | Medium | Phase 2 BI |
| 48 | Margin signal on dashboard (COGS vs revenue) | P2 | Profitability visibility | False confidence | Medium | BI, COGS |
| 49 | Top debtors / creditors widget with click-through | P2 | Working capital | Missed collections | Medium | Dashboard |
| 50 | Expiry batch trace report (pharmacy/frozen) | P2 | Vertical readiness | Regulatory risk | Medium | Inventory |
| 51 | Low stock email/SMS alert (post notification engine) | P2 | Stock continuity | Stockouts | High | P2 #26 |
| 52 | Overdue AR email alert | P2 | Cash collection | Bad debt | High | P2 #26 |
| 53 | Subscription expiry proactive alert | P2 | Renewal revenue | Churn | Medium | Subscription |
| 54 | Employee master linked to payroll (P3-4) | P3 | HR integrity | Duplicate employee data | High | HR module |
| 55 | Role template picker in System Configuration (P3-10) | P3 | Faster setup | Wrong permissions | Medium | Setup |
| 56 | Self-service staff password reset | P2 | Admin burden | Lockout support tickets | Medium | Auth |
| 57 | Credit limit on customer master | P2 | AR risk control | Over-trading | Medium | Customers, POS |
| 58 | POS held cart / recall | P2 | Retail UX | Lost sales | Medium | POS |
| 59 | POS return workflow visibility for Cashier | P2 | Returns handling | Manual workarounds | Low | POS permissions |
| 60 | Invoice credit note document type | P2 | Sales corrections | Ad-hoc journals | High | Sales, accounting |
| 61 | Supplier credit note / debit note | P2 | Purchase corrections | Ad-hoc journals | High | AP |
| 62 | Purchase order entity (no full module — lightweight) | P2 | Wholesaler workflow | Informal ordering | High | P2P design |
| 63 | Three-way match bill/PO/receive | P3 | Enterprise AP | Overpayment | Very High | PO, bills, receive |
| 64 | NHIS / pharmacy regulatory fields | P3 | Pharmacy vertical | Cannot serve pharmacies | High | Industry pack |
| 65 | Recipe/BOM for restaurant/manufacturing (P3-7) | P3 | Vertical fit | Wrong COGS | Very High | Phase 5 |
| 66 | Project/job costing (P3-6) | P3 | Construction/services | No job profitability | Very High | Phase 5 |
| 67 | Multi-currency full workflow (P3-5) | P3 | Importers/exporters | FX errors | Very High | Accounting |
| 68 | GRA e-VAT / e-invoicing integration | P3 | Future compliance | Regulatory change risk | Very High | External API |
| 69 | Bank feed API integration (Ghana banks) | P3 | Recon automation | Manual recon forever | Very High | Banking partners |
| 70 | Native mobile POS app | P3 | Field/tablet sales | Web-only limitation | Very High | Mobile team |
| 71 | Offline POS with sync | P3 | Unreliable internet | Sales stop | Very High | POS architecture |
| 72 | Workflow orchestration engine (P3-2) | P3 | Explicit state machines | Implicit flow bugs | Very High | Architecture |
| 73 | Industry Packs layer (P3-1) | P3 | Vertical acceleration | Premature complexity | Very High | Phase 1 exit |
| 74 | Fix Gatekeeper tab3 manual deployment label (P2-11) | P2 | Dev UX | Confusion | Low | Dev UI |
| 75 | Branch-scoped audit trail filter tests (P2-12) | P2 | Multi-branch audit | Wrong branch data | Low | Audit tests |
| 76 | Analytics page test suite + KPI definitions | P2 | BI trust | Misleading analytics | Medium | Analytics |
| 77 | Resolve 11 migration cleanup warning rows | P1 | Data hygiene | Orphan references | Medium | Migration cleanup |
| 78 | Document POS posting permission decision in DECISION_LOG | P0 | Governance | Repeated debate | Low | P0 #1 outcome |
| 79 | Compensating control: daily TB review SOP for pilots | P0 | Pilot safety | Undetected errors | Low | Operations |
| 80 | Pilot operator training deck (bill≠receive, roles) | P0 | Adoption | User error | Low | Training |
| 81 | Weekly pilot health check script (TB, backup, subledger) | P1 | Ongoing assurance | Silent drift | Low | Ops |
| 82 | Supabase backup SOP completion | P0 | Postgres GO | No DR | Medium | Cloud ops |
| 83 | Staging environment parity with production | P1 | Safe releases | Prod-only bugs | Medium | DevOps |
| 84 | Secrets rotation procedure documented | P1 | Security | Key leakage | Low | Security |
| 85 | Disable Dev credentials in production pilot | P0 | Security | Full platform access | Low | Deployment |
| 86 | Limit Demo role in production tenant | P1 | Data integrity | Demo data in live | Low | Roles |
| 87 | Inventory valuation vs GL reconciliation report | P1 | Month-end | Misstated inventory | Medium | Reports |
| 88 | COGS reconciliation report (POS + invoice) | P2 | Margin accuracy | Wrong profitability | Medium | Reports |
| 89 | Sales tax rounding policy documented and tested | P1 | Tax accuracy | Penny drift | Low | Tax engine |
| 90 | Withholding tax on supplier payments (Ghana WHT) | P2 | Ghana compliance | WHT exposure | High | AP, tax |
| 91 | Petty cash imprest workflow | P2 | Retail/office ops | Cash leakage | Medium | Banking |
| 92 | Daily cash count worksheet | P2 | Retail control | Undetected theft | Low | Banking/POS |
| 93 | Serial number tracking on inventory | P3 | Electronics | Warranty disputes | High | Inventory |
| 94 | Promotional pricing engine (P3-8) | P3 | Retail pack | Manual discounts | High | POS |
| 95 | Customer loyalty / store credit | P3 | Retail retention | Competitor feature | High | POS, AR |
| 96 | Inter-branch pricing rules | P3 | Multi-branch retail | Pricing chaos | High | Branches |
| 97 | Consolidated multi-branch financial reports | P2 | Group owners | Per-branch only | High | Branches, reports |
| 98 | API layer for third-party integrations | P3 | Ecosystem | Isolation | Very High | Architecture |
| 99 | AI-assisted transaction categorization (with audit) | P3 | Speed | Black-box posting | High | AI, accounting |
| 100 | Phase 1 exit criteria formal sign-off document | P0 | Product gate | Premature Phase 2 | Low | All P0 items |

---

## Priority Summary

| Priority | Count | Theme |
|----------|-------|-------|
| **P0** | 18 | Permissions, UAT, Postgres, backup, finance sign-off, pilot ops |
| **P1** | 42 | P2P link, movements, payments, payroll tests, recon, UX shortcuts |
| **P2** | 28 | Notifications design, consolidation, performance, templates |
| **P3** | 12 | Industry packs, mobile, APIs, advanced verticals |

---

## Recommended Next 30 Days (Certification Remediation)

1. Items **#1, #2, #5, #6, #78, #79, #80, #85, #100** — minimum bar to upgrade pilot confidence  
2. Items **#3, #4, #82** — minimum bar for PostgreSQL path  
3. Items **#7, #8, #10** — highest business-value P1 after P0  

---

*Program A Top 100 Recommendations — ranked for Core Platform certification remediation.*
