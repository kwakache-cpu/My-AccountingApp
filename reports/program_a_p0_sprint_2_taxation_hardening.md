# Program A P0 Sprint 2 — Taxation Hardening

**Date:** 2026-07-06  
**Branch:** `program-a-p0-sprint-2-taxation-hardening`  
**Scope:** Permission gates, regression tests, client-surface hygiene — **no accounting logic changes**

---

## Audit Finding Addressed

| Gap | Resolution |
|-----|------------|
| Taxation page mapped to generic `view_reports` | Dedicated `view_taxation` permission + page map update |
| No settlement-specific gate | `manage_taxation` required for tax settlement posting (plus existing `post_accounting_document`) |
| Zero taxation test coverage | `tests/test_program_a_p0_taxation_hardening.py` |
| Legacy/journal diagnostic on client page | Removed `compare_legacy_and_journal_totals()` call from `show_taxation` |

---

## Discovery Summary

### Pages & routes

| Surface | Location | Entry |
|---------|----------|-------|
| **Taxation (VAT/NHIL)** | `modules.show_taxation` | Sidebar → Finance → Taxation; `app.py` route `Taxation (VAT/NHIL)` |
| Sales tax posting helpers | `build_sales_tax_journal_lines`, `_tax_amount` | Used by invoice/sales flows in `financials.py` / `modules.py` |
| Tax control accounts | `ensure_tax_control_accounts`, `TAX_CONTROL_ACCOUNT_SPECS` | VAT Payable/Receivable, NHIL Payable, GETFund Levy Payable |
| Tax balances | `_tax_account_journal_totals`, `_tax_control_balance` | Journal-backed balances on taxation page |

### Tables (read/write via taxation page)

- `chart_of_accounts` — tax control accounts (ensure on page load)
- `journal_entries` / `journal_lines` — posted VAT/NHIL/GETFund and settlements
- `invoices` / sales flows — source of output tax via `build_sales_tax_journal_lines` (unchanged)

### Prior permission state

- `PAGE_PERMISSION_MAP["Taxation (VAT/NHIL)"]` = `view_reports` (any role with general report access could open taxation)
- `show_taxation` had **no** `require_permission` gate at page entry
- Settlement used only `post_accounting_document`

---

## Permission Changes

### New keys

| Permission | Purpose |
|------------|---------|
| `view_taxation` | Open Taxation (VAT/NHIL) page and read tax report |
| `manage_taxation` | Post tax settlement entries from taxation page |

### Role grants

| Role | view_taxation | manage_taxation |
|------|---------------|-----------------|
| Dev | ✓ (all) | ✓ |
| Master Admin | ✓ | ✓ |
| Owner / CEO | ✓ | ✓ |
| Accountant | ✓ | ✓ |
| Bookkeeper | ✓ | ✓ |
| Branch_Bookkeeper | ✓ | ✓ |
| Branch Manager | ✓ | ✓ |
| Sub-Admin | ✓ | ✓ |
| Auditor / Read Only | ✓ | — |
| HR / Payroll Officer | — | — |
| Cashier / Staff / Sales / Inventory Officer | — | — |

### Enforcement layers

1. **Sidebar** — `_render_sidebar_navigation` / `user_can_access_page` hides Taxation when `view_taxation` missing
2. **Direct route** — `app._render_primary_page` blocks page before dispatch; safe denial message
3. **Page handler** — `show_taxation` calls `require_permission(..., "view_taxation")`
4. **Settlement** — requires `manage_taxation` and `post_accounting_document`

---

## Files Changed

| File | Change |
|------|--------|
| `modules.py` | Permissions, role matrix, `PAGE_PERMISSION_MAP`, `show_taxation` gates, remove client diagnostic call |
| `app.py` | `PAGE_PERMISSION_MAP` → `view_taxation` |
| `tests/test_program_a_p0_taxation_hardening.py` | New regression suite |
| `reports/program_a_priority_roadmap.md` | P0-3 / P0-4 sprint status |
| `reports/program_a_p0_sprint_2_taxation_hardening.md` | This document |

**Not changed:** `build_sales_tax_journal_lines`, posting rates, tax account specs, database schema.

---

## Tests Added

`tests/test_program_a_p0_taxation_hardening.py`:

- Permission keys registered; page map uses `view_taxation`
- Authorized roles (Accountant, Bookkeeper, Auditor, Owner) can access taxation route
- Unauthorized roles (Cashier, Staff, Sales Officer, Inventory Officer) denied
- HR/Payroll keeps `view_reports` but not taxation
- Auditor view-only (no `manage_taxation`)
- Sidebar visibility follows `user_can_access_page`
- `show_taxation` requires `view_taxation`; no client diagnostics
- Posted VAT journal lines appear in `_tax_control_balance`
- Tax SQL avoids sqlite-specific functions; uses portable aggregates
- Regression lockdown manifest compatibility check

---

## Validation Commands

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_program_a_p0_taxation_hardening.py" -v
python -m unittest discover -s tests -p "test_regression_lockdown.py" -v
python tests/run_regression_tests.py
git diff --check
```
