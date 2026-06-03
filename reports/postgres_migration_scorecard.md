# PostgreSQL Migration Scorecard (Phase 5B.11)

**Audited at:** 2026-06-02 12:04:36 UTC

| Dimension | Grade | Notes |
|-----------|-------|-------|
| Startup guardrail | **YELLOW** | Phase 5B.13B blocks enabled PostgreSQL runtime before SQLite-only schema/recovery paths; schema deployment still not implemented |
| Schema deployment plan | **YELLOW** | Phase 5B.13C design plan exists in `reports/postgres_schema_deployment_plan.md`; deployer has not been implemented |
| Schema introspection abstraction | **YELLOW** | Phase 5B.13D adds backend-aware table/column/index/FK helpers and converts low-risk diagnostics/readiness callers; schema deployment paths remain SQLite-native |
| DDL generator | **YELLOW** | Phase 5B.13E adds offline `postgres_schema_generator.py` plus generated SQL/summary artifacts; no schema deployment or Supabase connection |
| Schema validator | **YELLOW** | Phase 5B.13F adds offline `postgres_schema_validator.py` and validation report; score 90/100 with 51/51 tables, 67 indexes, 47 FKs, and no forbidden SQLite syntax in generated SQL |
| Staging deployment skeleton | **YELLOW** | Phase 5B.13H adds `postgres_staging_deployer.py` with dry-run artifact checks, redacted DATABASE_URL diagnostics, and blocked `--apply`; execution is not implemented |
| Post-deployment validation framework | **YELLOW** | Phase 5B.13I adds offline `postgres_postdeploy_validator.py` and a validation plan covering schema/table/column/index/FK/seed/migration/runtime readiness checks; no DB access or execution |
| Deployment executor design | **YELLOW** | Phase 5B.14A adds `reports/postgres_deployment_executor_design.md` covering executor architecture, phase execution, transactions, rollback, migration history, validation checkpoints, logging, and safety protections; implementation has not started |
| Identity portability | **GREEN** | Production paths use get_inserted_id / ensure_insert_sql_returning; zero raw lastrowid in app modules |
| Placeholder portability | **RED** | ~600+ literal ? placeholders; 5B.12H routes company/subscription trial/metadata DML through `execute_portable_write()`, but modules/accounting_engine still dominate |
| Schema introspection portability | **YELLOW** | Shared helper layer exists, but many schema/self-heal and module callers still use SQLite-native PRAGMA/sqlite_master |
| Transaction portability | **YELLOW** | db_begin/commit OK; BEGIN IMMEDIATE SQLite-only in lock wrapper |
| Accounting portability | **YELLOW** | Journal identity GREEN; SQL dialect and strftime filters RED/YELLOW |
| POS portability | **YELLOW** | Sale identity converted; placeholders + inventory PRAGMA remain |
| Inventory portability | **YELLOW** | Stock movement identity OK; schema probes SQLite-specific |
| Branch governance portability | **YELLOW** | Business logic present; introspection/SQL not Postgres-ready |
| Auth portability | **YELLOW** | Straightforward queries but ? placeholders and schema ensure blocker |
| Reporting portability | **RED** | accounting_engine heavy ? + strftime in SQL |
| Data readiness | **GREEN** | FK orphans 0 on SQLite snapshot; cleanup phases documented |
| Overall staging readiness | **RED** | NO-GO for ERP_ENABLE_POSTGRES_RUNTIME=1; startup fails safe and schema deployment remains unimplemented |

## Phase 5B.10 identity work (reflected)

- `post_journal_entry` — converted (5B.10G)
- POS, payments, bills, invoices, payroll, fixed assets, stock movements — `get_inserted_id` pattern
- Remaining `lastrowid` — tests, `database.py` helper implementation, audit scripts only

## Overall recommendation

**NO-GO** for Postgres runtime switch. Continue on SQLite. Phase 5B.13B added a safe startup gate, Phase 5B.13C adds the schema deployment plan, Phase 5B.13D adds backend-aware introspection helpers, Phase 5B.13E adds offline DDL generation, Phase 5B.13F adds offline schema validation, Phase 5B.13H adds a staging deployment CLI skeleton, Phase 5B.13I adds a post-deployment validation framework, and Phase 5B.14A adds the deployment executor design, but PostgreSQL schema execution is not implemented and broad placeholder/DDL portability remains the next engineering priority.
