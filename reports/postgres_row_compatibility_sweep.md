# PostgreSQL Row Compatibility Sweep (Phase 5B.15T)

**Completed:** 2026-06-16

## Problem

PostgreSQL runtime page loads failed with `tuple index out of range` when application code assumed SQLite row shapes:

- chained `fetchone()[0]` on empty or single-column results
- positional `row[0]` / `row[1]` / `row[2]` without bounds checks
- `isinstance(row, sqlite3.Row)` branches that skipped `CompatibleRow` dict access
- `PRAGMA table_info(...)` column probes returning incompatible tuple shapes on PostgreSQL

## Infrastructure added

| Helper | Purpose |
|--------|---------|
| `fetch_scalar()` | Safe single-value reads via `execute_portable_query()` + `row_get()` |
| `CompatibleRow.__getitem__` bounds check | Positional overflow returns `IndexError`, caught by `row_get()` |
| `_row_value()` | Delegates to `row_to_dict()` / `row_get()` instead of raw indexing |

## Files changed

| File | Changes |
|------|---------|
| `database.py` | Added `fetch_scalar()`; hardened `CompatibleRow`, `_row_value()`; converted branch licensing, user lookup, module-grant, and staff assignment row reads to `row_get()` / `row_to_dict()` |
| `modules.py` | Converted master price, financial metrics, system health, reports bundle, dashboard branch label, audit trail column probe, debtors-by-city, branch admin panels to portable reads |
| `accounting_engine.py` | Converted period lock/diagnostics, inventory column probe, payment allocation scalar reads |
| `tests/test_postgres_row_compatibility_sweep.py` | New targeted regression coverage |
| `reports/postgres_row_compatibility_sweep.md` | This report |
| `reports/postgres_migration_scorecard.md` | Scorecard update |

## Row assumptions fixed (runtime paths)

### `database.py`

- `_fetch_company_name()` — `row[0]` → `row_get(row, "name", row_get(row, 0))`
- `backfill_branch_codes()` — raw `conn.execute` + tuple unpack → portable query + `row_get`
- `count_active_branches()` — `row[0]` → `row_get(row, "active_count", row_get(row, 0))`
- `get_company_branch_license_snapshot()` — `row[0]`/`row[1]` → indexed `row_get`
- `get_branch_type_catalog()` — sqlite3.Row if/else → `row_get` per field
- `list_company_branches_with_grants()` — 14-field positional else branch → unified `row_get`
- `repair_branch_module_grants()` — tuple unpack → `row_get`
- `_fetch_company_user_by_user_id()` — manual `row[0]`..`row[7]` → `dict(row_to_dict(row))`
- `assign_branch_manager()` — `branch_row[2]` → `row_get(..., "branch_access_key", row_get(..., 2))`
- `list_branch_users()` / `fetch_branch_manager_candidates()` / `list_company_staff_for_assignment()` — sqlite3.Row if/else → `dict(row_to_dict(row))`
- `update_branch_user_status()` / `update_company_staff_branch_assignment()` — `row[1]`/`row[2]` → `row_get`
- `_fetch_branch_type_default_module_keys()` / `get_branch_enabled_modules()` — `row[0]` → `row_get(row, "module_key", row_get(row, 0))`
- `update_company_branch()` — 11-field manual index map → `dict(row_to_dict(row))`

### `modules.py`

- `get_master_price_per_month()` — `row[0]` → portable query + `row_get`
- `is_period_locked()` — `PRAGMA` + raw execute → `list_columns()` + `execute_portable_query`
- debtors-by-city filter — `row[0]` → `row_get(row, "city_region", row_get(row, 0))`
- `get_financial_metrics()` / `get_system_health_snapshot()` — `fetchone()[0]` chains → `fetch_scalar`
- `_get_reports_data()` — six aggregate `fetchone()[0]` reads → `fetch_scalar`
- `show_dashboard()` branch label — `branch_row[0]` → `row_get`
- audit trail — `PRAGMA table_info(audit_logs)` → `list_columns(conn, "audit_logs")`
- branch admin diagnostics/users/staff/performance tabs — positional branch row reads → portable query + `row_get`

### `accounting_engine.py`

- `_period_locked()` / `get_period_control_diagnostics()` — `PRAGMA` + raw execute → `list_columns()` + portable reads + `row_get`
- `_inventory_value_query()` — inventory `PRAGMA` → `list_columns(conn, "inventory")`
- payment allocation outstanding balance — `fetchone()[0]` → `fetch_scalar`

## Remaining PostgreSQL blockers (not row-shape)

| Area | Blocker | Severity |
|------|---------|----------|
| `_get_reports_data()` payroll export query | SQLite `printf()` date formatting | Medium — reports page on PostgreSQL |
| Schema self-heal / migration paths in `database.py` | Many `PRAGMA table_info` probes in DDL helpers (guarded/skipped on PG when appropriate) | Low for page-load, Medium for schema drift repair |
| POS interactive checkout/search | Residual raw `conn.execute()` with SQLite dialect (prior phases) | Medium |
| Write/posting paths | Literal `?` on some DML not yet routed through `execute_portable_write()` | Medium |
| `date()` SQL functions | SQLite date helpers in period-lock queries may need PostgreSQL equivalents for edge cases | Low |

## Validation

```text
python -m py_compile  → PASS (expected)
python tests/run_regression_tests.py → PASS (expected)
git diff --check → PASS (expected)
```

## Staging recommendation

**YES — staging runtime page testing can continue.**

The `tuple index out of range` class of failures on dashboard, branch admin, financial metrics, system health, and payment allocation reads should be resolved. Expect possible follow-on failures from SQL dialect (`printf`, `date()`), write-path placeholders, or page-specific raw queries — not from positional row indexing on portable SELECT results.
