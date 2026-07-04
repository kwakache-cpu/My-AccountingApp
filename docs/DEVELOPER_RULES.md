# Developer Rules

Practical engineering rules for EKA Enterprise Platform.  
**Every contributor and AI editor must follow these.**

Entry point: `AGENTS.md`  
Protected workflows: `REGRESSION_LOCKDOWN.md`

---

## Before You Write Code

1. Read `AGENTS.md`
2. Read this document
3. Run the regression checklist in `scripts/regression_lockdown_checklist.md`
4. Identify which workflow(s) your change affects (`WORKFLOW_LIBRARY.md`)

---

## Absolute Prohibitions

| Rule | Rationale |
|------|-----------|
| **No DDL in UI** | `ALTER TABLE`, `CREATE TABLE`, `ADD COLUMN` during page render caused production `DuplicateColumn` crashes |
| **No diagnostics on client pages** | LV/admin panels belong on Dev/System surfaces only |
| **No schema mutations inside rendering** | Migrations run at startup, not on `show_*()` |
| **No broad rewrites** | High regression risk; surgical fixes only |
| **No accounting logic changes without tests** | Financial integrity is non-negotiable |
| **No secret exposure** | Use `security_utils`; never log keys or tokens |
| **No removal of working functionality** | Deprecate with migration path if needed |

---

## Database Rules

- **Dual backend:** SQLite and PostgreSQL must both work
- **Portable SQL:** Use `execute_portable_query` / `execute_portable_write`
- **Schema integrity:** Idempotent helpers (e.g. `ensure_users_user_id_schema_integrity`) at startup only
- **Cutover safety:** Do not weaken PostgreSQL activation guards or runtime evidence checks
- **Never** run DDL in: `show_company_setup`, `show_dashboard`, `show_pos`, `show_inventory`, `show_financial_reports`, `login_ui`

---

## UI / Streamlit Rules

- Prefer stable built-in widgets over fragile custom components on hot paths (login, registration, Gatekeeper)
- Lazy-load heavy admin panels (migration cleanup, deep audits)
- Defer expensive snapshots on dashboard first render (AR/AP on demand)
- Financial Reports: lazy report selection, shared connection, lazy CSV — do not revert to eager tabs
- User errors: `build_user_safe_error()` for clients; never raw `psycopg2` or `UNIQUE constraint` text

---

## Module Protection Zones

Changes in these areas require extra care and full regression run:

| Zone | Primary file | Protect |
|------|--------------|---------|
| **Accounting** | `accounting_engine.py` | Posting, periods, reversals |
| **Startup** | `database.py` | Backend selection, migrations, cutover |
| **POS** | `modules.py` (`show_pos`, `_persist_pos_sale`) | Sale identity, posting linkage |
| **Financial Reports** | `financials.py` | Lazy loading, ledger snapshot |
| **Permissions** | `modules.py` | Role matrices, `require_permission` |
| **Registration** | `modules.py` (`show_onboarding_payment`) | Trial + Paystack flow |
| **System Config** | `modules.py` (`show_company_setup`) | No DDL, company profile |

---

## Performance Rules

- **Measure before optimizing** — use existing LV profiler hooks where present
- Do not add eager heavy queries to client first render
- Do not run cloud backup download, Firebase verification, or full health audit on normal client navigation
- Respect budgets in `AGENTS.md`

---

## Testing Rules

- Run before reporting completion:

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_regress*.py" -v
python -m unittest discover -s tests -p "test_urgent*.py" -v
python -m unittest discover -s tests -p "test_lv00*.py" -v
python tests/run_regression_tests.py
git diff --check
```

- Add tests to `tests/test_regression_lockdown.py` when protecting a new workflow
- Update `reports/regression_lockdown_manifest.md` and this document when lockdown scope changes

---

## Git & Delivery Rules

- Review `git diff` before reporting completion
- Do not commit/push/PR unless explicitly requested
- Do not modify unrelated files (e.g. auto-updated smoke reports from test runs)
- Document architectural choices in `DECISION_LOG.md`

---

## Error Handling Rules

- Log internally with `sanitize_error_message()`
- Display to users with `build_user_safe_error(role=...)`
- Client roles: generic message only
- Admin roles: generic + sanitized details — never raw secrets

---

## Admin vs Client Surfaces

| Surface | Diagnostics allowed? |
|---------|------------------------|
| Client dashboard | No |
| POS | No |
| Inventory | No |
| Financial Reports | No |
| System Configuration (client) | No |
| Dev Gatekeeper | Yes (admin) |
| System Health | Yes (admin) |
| System Administration | Yes (admin) |

Approved helpers: `render_runtime_admin_diagnostics_suite` with surface gating.

---

## Code Review Self-Checklist

Before marking work complete:

- [ ] No DDL in any `show_*` or `login_ui` path
- [ ] No new admin diagnostics on client pages
- [ ] Accounting/posting logic unchanged (or explicitly tested)
- [ ] SQLite and PostgreSQL paths considered
- [ ] Regression suite passes
- [ ] `git diff --check` clean
- [ ] Decision logged if architectural

---

## Related Documents

- `AGENTS.md` — AI editor entry point
- `REGRESSION_LOCKDOWN.md` — protected workflows
- `EKA_ARCHITECTURE_MANUAL.md` — system structure
- `scripts/regression_lockdown_checklist.md` — command checklist

---

*Developer Rules — mandatory engineering discipline for EKA.*
