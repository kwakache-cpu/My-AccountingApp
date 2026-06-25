# PostgreSQL Display Correctness and Performance Sweep (Phase 5B.15W)

**Completed:** 2026-06-16

## Display issues fixed

### Audit Trail (primary)

**Root cause:** `show_audit_trail()` built `pd.DataFrame(data, columns=[...])` from PostgreSQL `CompatibleRow` dict rows while supplying Title Case column labels. Pandas looked for keys like `"Timestamp"` instead of SQL keys like `"timestamp"`, producing widespread `None` values.

**Fix:**
- Route audit reads through `execute_timed_portable_query()` + `rows_to_dicts()`
- Build display frames with `dataframe_from_portable_rows()` and explicit SQL-key → UI-label mapping
- Cache `audit_logs` column metadata via `get_cached_table_column_names()`

### System Status logs

**Root cause:** Same dict-row / forced-column-label mismatch on `system_logs` reads.

**Fix:** Portable query + `dataframe_from_portable_rows()` with label map.

### Dev forensic trail (`app.py`)

**Fix:** Same portable dataframe helper for the limited Dev audit preview table.

## Performance improvements

| Area | Before | After |
|------|--------|-------|
| Customer balances | 1 + N journal queries (one per customer) | 2 queries (customer list + grouped balance map) |
| Supplier balances | 1 + N journal queries | 2 queries (supplier list + grouped balance map) |
| Audit Trail metadata | `list_columns()` on every page load | 5-minute PostgreSQL cache via `get_cached_table_column_names()` |
| Dashboard inventory probes | `list_columns()` per section | Cached column-name lookup |
| Observability | None | `record_postgres_query_timing()` + recent timings panel on System Status (PostgreSQL only) |
| Dashboard bundle | Uncached section timing | Section timings recorded under PostgreSQL (`dashboard.kpis`, `dashboard.sales`, `dashboard.inventory`) |

Existing `@st.cache_data(ttl=120)` dashboard analytics bundle retained.

## Slow paths identified

1. **Customer/supplier balance N+1** — fixed with grouped journal queries
2. **Repeated schema introspection** — partially mitigated with PostgreSQL column-name cache
3. **Dashboard KPI path** — still runs multiple independent reads (inventory, month sales, optional POS, receivables/payables, cash/bank); section timings now visible for prioritization
4. **Financial Reports integrity diagnostics** — unchanged; still multi-query but no display regression found

## Remaining blockers / follow-up

- Other legacy `pd.DataFrame(rows, columns=[...])` call sites outside this sweep may still mis-render under PostgreSQL dict rows
- Write/posting paths and deeper report exports not performance-tuned in this phase
- PostgreSQL query timing panel is diagnostic only (System Status); no automatic slow-query alerting yet

## Tests added

`tests/test_postgres_display_performance_sweep.py`:

1. `rows_to_dicts` preserves cursor.description column names
2. Audit Trail dataframe preserves real values (including Amount/Source derivation)
3. Audit helper does not produce all-None rows
4. Customer balances use batch query (2 executes, not N+1)
5. Timed portable query records timing without changing results
6. SQLite customer balance list behavior unchanged

## Validation

```text
python -m py_compile app.py database.py modules.py financials.py accounting_engine.py  → PASS
python tests/run_regression_tests.py                                                  → PASS (449/449)
git diff --check                                                                      → PASS
```

## Runtime staging status

**READY_TO_CONTINUE** PostgreSQL runtime page testing. Audit Trail and System Status display correctness fixes target the reported `None` values directly; dashboard/report load should be measurably faster when customer/supplier lists are large.

## Out of scope (unchanged)

- No commits, pushes, SQLite data changes, backup deletion, data migration, or accounting posts
- SQLite behavior preserved (batch balance queries use portable SQL compatible with both backends)
