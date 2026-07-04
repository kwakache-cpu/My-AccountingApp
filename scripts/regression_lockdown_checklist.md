# Regression Lockdown Checklist — For Future Agents

**Read this before editing ERP production code.**

## Rules

- Do **not** add features, optimize performance, or rewrite broad modules.
- Do **not** change accounting/posting logic unless a failing lockdown test proves a real bug.
- Preserve SQLite + PostgreSQL support and startup/cutover safety.
- Keep diagnostics off client pages.

## Before editing — run in order

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py enterprise_services.py
python -m unittest discover -s tests -p "test_regress*.py" -v
python -m unittest discover -s tests -p "test_urgent*.py" -v
python -m unittest discover -s tests -p "test_lv00*.py" -v
python tests/run_regression_tests.py
git diff --check
```

## After editing — confirm

1. All commands above pass.
2. No new DDL in UI render paths (`show_company_setup`, client pages).
3. No admin diagnostics reintroduced on client surfaces.
4. Update `reports/regression_lockdown_manifest.md` if you add a new protected workflow or test file.

## Protected workflows (18)

See full mapping: `reports/regression_lockdown_manifest.md`

1. Login and secure logout
2. PostgreSQL runtime startup
3. SQLite fallback startup
4. Company registration duplicate protection
5. Paystack configuration resolution
6. Subscription/trial company flow
7. Dashboard first render
8. POS sale
9. POS controlled correction
10. Financial Reports lazy loading
11. System Configuration / Company Profile
12. Staff/user/role setup
13. Migration Cleanup hidden from client pages
14. Dev/System diagnostics admin-only
15. No schema DDL during UI page render
16. No raw DuplicateColumn / UNIQUE errors to users
17. No LV diagnostics on client workflow pages
18. No cloud/Firebase/deep audit on normal client navigation

## Canonical lockdown test file

`tests/test_regression_lockdown.py`

If a workflow fails, fix the smallest safe change and re-run the checklist.
