# PostgreSQL Migration Scorecard (Phase 5B.11–5B.12C)

**Audited at:** 2026-06-01 21:44:36 UTC
**5B.12C:** Auth/user branch listing reads portable in `database.py`; login-key guards unchanged.

| Dimension | Grade | Notes |
|-----------|-------|-------|
| Identity portability | **GREEN** | Production paths use get_inserted_id / ensure_insert_sql_returning; zero raw lastrowid in app modules |
| Placeholder portability | **RED** | ~1035 scoped literal `?`; `database.py` read paths largely routed; `modules.py` / `accounting_engine.py` untouched |
| Schema introspection portability | **RED** | PRAGMA / sqlite_master dominate outside small db_* helpers |
| Transaction portability | **YELLOW** | db_begin/commit OK; BEGIN IMMEDIATE SQLite-only in lock wrapper |
| Accounting portability | **YELLOW** | Journal identity GREEN; SQL dialect and strftime filters RED/YELLOW |
| POS portability | **YELLOW** | Sale identity converted; placeholders + inventory PRAGMA remain |
| Inventory portability | **YELLOW** | Stock movement identity OK; schema probes SQLite-specific |
| Branch governance portability | **YELLOW** | Business logic present; introspection/SQL not Postgres-ready |
| Auth portability | **YELLOW** | User/branch listing reads portable in `database.py`; login-key probes + `app.py` session SQL remain SQLite-specific |
| Reporting portability | **RED** | accounting_engine heavy ? + strftime in SQL |
| Data readiness | **GREEN** | FK orphans 0 on SQLite snapshot; cleanup phases documented |
| Overall staging readiness | **RED** | NO-GO for ERP_ENABLE_POSTGRES_RUNTIME=1 until placeholders + DDL |

## Phase 5B.12 placeholder foundation

- 5B.12A: core helpers + branch/license reads
- 5B.12B: branch catalog, audit summary, company profile reads
- 5B.12C: auth/user listing and lookup reads (`tests/test_database_auth_read_placeholder_conversion.py`)
- Login-key uniqueness probes deliberately left on raw `conn.execute` for byte-identical SQLite guards

## Phase 5B.10 identity work (reflected)

- `post_journal_entry` — converted (5B.10G)
- POS, payments, bills, invoices, payroll, fixed assets, stock movements — `get_inserted_id` pattern
- Remaining `lastrowid` — tests, `database.py` helper implementation, audit scripts only

## Overall recommendation

**NO-GO** for Postgres runtime switch. Continue on SQLite. Next engineering priority: **placeholder + DDL portability**, not identity.
