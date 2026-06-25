# PostgreSQL Reports and Migration Cleanup Readiness (Phase 5B.15X)

**Audited at:** 2026-06-16 12:00:00 UTC

## Summary

Phase 5B.15X hardens migration cleanup review determinism and restores Financial Reports under PostgreSQL runtime.

| Area | Status | Notes |
|------|--------|-------|
| Migration cleanup timestamps | **GREEN** | Audit summary and cleanup plan share `EKA_MIGRATION_REPORT_TIMESTAMP` via `regenerate_migration_integrity_reports()` |
| Go/No-Go display | **GREEN** | Full recommendation text rendered with markdown instead of truncated `st.metric` |
| Cleanup classification | **GREEN** | Items mapped to blocker / warning / manual_review with counts from cleanup plan JSON |
| Destructive cleanup guard | **GREEN** | No auto-apply; POS branch, manager link, and payment reference fixes still require explicit confirmation |
| Financial Reports reads | **GREEN** | `get_ledger_balances()` and `_journal_df()` use portable date predicates and `execute_portable_query()` |
| Empty report diagnostics | **GREEN** | When all report tabs are empty, UI shows company, date range, backend, and table row counts |

## Migration cleanup item classification

| Plan key | Summary key | Count (staging) | Classification |
|----------|-------------|-----------------|----------------|
| `pos_missing_branch_id` | `sales_without_branch_id` | 8 | manual_review |
| `missing_manager_user_id` | `missing_manager_user_id` | 2 | warning |
| `payments_without_reference` | `payments_without_source_reference` | 1 | manual_review |

These counts remain until operators resolve them manually in System Configuration → Migration Cleanup Review. Re-run **Migration Integrity Audit** after fixes to refresh aligned timestamps and counts.

## Financial Reports PostgreSQL fixes

- Replaced SQLite `date(je.date)` filters with `sql_date_on_or_after()` / `sql_date_on_or_before()`.
- Replaced raw `conn.execute()` ledger aggregation with `execute_portable_query()` and `row_get()`.
- Added `_financial_report_runtime_diagnostics()` for empty-report troubleshooting.

## Display sweep

High-traffic `pd.DataFrame(rows, columns=[...])` call sites in company list, license renewal, sales invoices, and accounts payable bills now use `dataframe_from_portable_rows()`.

## Validation

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py
python tests/run_regression_tests.py
git diff --check
```

## Manual checks

- Financial Reports shows trial balance / P&L data or diagnostics panel when empty.
- Migration Cleanup Review audit and plan timestamps match after re-run.
- Go/No-Go shows full text (e.g. **GO WITH WARNINGS**).
- Dashboard, POS, and Audit Trail remain functional.
