# Urgent Phase 1 Frontend Hardening — Root Cause & Retest

## Live errors observed

| Surface | Browser error | Streamlit chunk |
|---------|---------------|-----------------|
| Register New Company → Create Trial Company | `TypeError: error loading dynamically imported module: /static/js/Checkbox....` | Checkbox widget bundle |
| Gatekeeper / System Overview cards | `TypeError: error loading dynamically imported module: /static/js/embed....` | Custom-component iframe embedder |

## Root cause (verified)

**Primary — app-side fragile widgets on hot rerender paths**

1. **Registration / login footer** — `login_ui()` always rendered `st.toggle('Try Demo Mode')` on every rerun, including after the onboarding form submit in tab 3. `st.toggle` depends on the Checkbox frontend chunk. A failed chunk load surfaces as a client-side `TypeError` and can appear to break the registration action even when the backend trial/Paystack path succeeded.

2. **Gatekeeper System Overview** — `render_runtime_admin_diagnostics_suite()` eagerly executed `_render_migration_cleanup_review()` inside an expander on every Dev dashboard load. That panel renders nested `st.tabs`, multiple `st.dataframe` views, and several `st.checkbox` confirmations. Heavy admin widgets on first paint increase exposure to Checkbox/embed chunk failures and slow the overview cards.

3. **Manual Deployment tab** — used `st.checkbox` for Paystack bypass and company lifecycle confirmations on an admin surface that must open reliably.

**Secondary — stale Streamlit frontend cache (possible amplifier)**

After deploys or Streamlit runtime upgrades, browsers can retain old `/static/js/*` chunks while the server serves a new manifest. Symptoms match both Checkbox and `embed` chunk mismatches. App-side hardening reduces dependence on those chunks; cache clearing remains a valid retest step.

## Fixes applied (code)

- Replaced login `st.toggle` with button-based demo mode entry (`Try Demo Mode` / `Back to Secure Login`).
- Replaced onboarding Paystack `st.link_button` with a markdown checkout link (same URL, no extra widget chunk).
- Lazy-load migration cleanup diagnostics behind an explicit **Load migration cleanup review** button.
- Replaced migration cleanup and Manual Deployment checkbox confirmations with typed confirmation phrases.
- Preserved Paystack initialization/verification logic and Phase 1 Financial Reports lazy-loading.

## System Configuration `DuplicateColumn`

Still fixed: `show_company_setup()` performs no DDL on render; `database.ensure_users_user_id_schema_integrity()` is idempotent and runs in startup integrity checks only.

## Live retest steps

1. **Hard refresh** the app tab (`Ctrl+Shift+R` / `Cmd+Shift+R`).
2. Open an **incognito/private** window and repeat registration + Gatekeeper flows.
3. **Restart Streamlit** (stop process, start again) so the server serves a consistent static manifest.
4. If errors persist only in one browser profile, **clear site cache** for the app origin.
5. Re-test:
   - Register New Company → Create Trial Company & Proceed to Payment
   - Dev Gatekeeper → System Overview metrics (no embed errors on cards)
   - Manual Deployment tab opens without frontend import errors
   - System Configuration opens without PostgreSQL `DuplicateColumn`

## Phase 1 speed preservation

- Financial Reports still uses lazy `st.radio` report selection, shared ledger snapshot connection, and lazy CSV export.
- Client dashboard still defers AR/AP aging behind an on-demand load button.
- No diagnostics reintroduced on client pages.
