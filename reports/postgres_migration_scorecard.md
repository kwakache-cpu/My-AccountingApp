# PostgreSQL Migration Scorecard (Phase 5B.11–5B.12D)

**Audited at:** 2026-06-01 22:31:34 UTC
**5B.12D:** Branch/user write preflight SELECTs portable; DML statements still SQLite `?`.

| Dimension | Grade | Notes |
|-----------|-------|-------|
| Identity portability | **GREEN** | Production paths use get_inserted_id / ensure_insert_sql_returning; zero raw lastrowid in app modules |
| Placeholder portability | **RED** | ~1035 scoped literal `?`; `database.py` pre-write SELECTs routed (~38 execute_portable_query); modules untouched |
| Schema introspection portability | **RED** | PRAGMA / sqlite_master dominate outside small db_* helpers |
| Transaction portability | **YELLOW** | db_begin/commit OK; BEGIN IMMEDIATE SQLite-only in lock wrapper |
| Accounting portability | **YELLOW** | Journal identity GREEN; SQL dialect and strftime filters RED/YELLOW |
| POS portability | **YELLOW** | Sale identity converted; placeholders + inventory PRAGMA remain |
| Inventory portability | **YELLOW** | Stock movement identity OK; schema probes SQLite-specific |
| Branch governance portability | **YELLOW** | Business logic present; introspection/SQL not Postgres-ready |
| Auth portability | **YELLOW** | User/branch pre-write checks portable in `database.py`; session login in `app.py`/`modules.py` still blocked |
| Reporting portability | **RED** | accounting_engine heavy ? + strftime in SQL |
| Data readiness | **GREEN** | FK orphans 0 on SQLite snapshot; cleanup phases documented |
| Overall staging readiness | **RED** | NO-GO for ERP_ENABLE_POSTGRES_RUNTIME=1 until placeholders + DDL |

## Phase 5B.12 placeholder foundation

- 5B.12A–C: helpers + branch/read/auth listing paths (where merged on branch)
- 5B.12D: write **preflight** SELECTs (uniqueness, existence, manager lookup) — no DML conversion yet
- Tests: `tests/test_database_write_preflight_placeholder_conversion.py`

## Phase 5B.10 identity work (reflected)

- `post_journal_entry` — converted (5B.10G)
- POS, payments, bills, invoices, payroll, fixed assets, stock movements — `get_inserted_id` pattern
- Remaining `lastrowid` — tests, `database.py` helper implementation, audit scripts only

## Overall recommendation

**NO-GO** for Postgres runtime switch. Continue on SQLite. Next engineering priority: **placeholder + DDL portability**, not identity.
