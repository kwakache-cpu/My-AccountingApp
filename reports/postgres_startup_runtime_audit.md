# PostgreSQL Startup Runtime Audit

Scope: startup/runtime backend selection paths only:

- `database.py`: `startup_database()`, `get_connection()`, backend selectors, runtime enablement checks, SQLite/PostgreSQL openers, lightweight integrity/startup call points.
- `app.py`: database startup and initialization calls in `main()`.

Updated after Phase 5B.13B: a backend-aware startup gate now blocks enabled PostgreSQL runtime before SQLite-only schema/recovery paths run. PostgreSQL schema deployment is still not implemented.

## Key Findings

| Area | Finding | Risk |
|---|---|---|
| Backend selection | `get_active_db_backend()` returns `postgres` only when configured backend is PostgreSQL, runtime flag is enabled, and `DATABASE_URL` exists. Otherwise it silently returns `sqlite`. | MEDIUM |
| Connection factory | `get_connection()` is backend-aware and can call `_open_postgres_connection()` when PostgreSQL is fully enabled. | LOW |
| App startup order | `app.py` now checks backend diagnostics before `ensure_schema()` and only runs `ensure_schema()` on the SQLite path. | MEDIUM |
| Canonical startup | `startup_database()` now blocks active PostgreSQL runtime before SQLite-file bootstrap/recovery logic. SQLite remains the normal path. | HIGH |
| Readiness reporting | `get_database_health_snapshot()` and `is_database_ready_for_production()` are SQLite database-file readiness checks, not backend-neutral health checks. | CRITICAL |
| PostgreSQL connection | `_open_postgres_connection()` can create a wrapped psycopg/psycopg2 connection and enforce `sslmode=require`; startup intentionally does not reach it until PostgreSQL schema deployment exists. | HIGH |
| Lightweight checks | `_run_lightweight_integrity_checks()` calls SQLite DDL/bootstrap helpers, including `ensure_schema_integrity()`, `_ensure_database_identity_table()`, `_ensure_app_compatibility_tables()`, and schema manifest diagnostics. | CRITICAL |

## 1. What Happens Today When DB_BACKEND=sqlite?

`get_configured_db_backend()` normalizes `DB_BACKEND=sqlite` to `sqlite`, and `get_active_db_backend()` returns `sqlite`.

In `app.py`, `main()` first calls `ensure_schema()`. That function opens `_open_sqlite_connection()`, runs `PRAGMA table_info(companies)`, may run `ALTER TABLE companies ...`, then calls `ensure_schema_integrity()`.

`main()` then calls `startup_database()`, which:

1. Calls `_ensure_local_db_file()`.
2. Uses SQLite file readiness through `is_database_valid()` and `get_database_health_snapshot()`.
3. May open `_open_sqlite_connection()` for preflight and run `_run_lightweight_integrity_checks()`.
4. Opens `_open_sqlite_connection()` for startup migrations and validation.
5. Returns a startup result such as `bootstrap_mode`, `fallback_complete`, `startup_complete`, or failure metadata.

Risk: LOW for the current SQLite runtime because this is the designed path.

## 2. What Happens Today When DB_BACKEND=postgres But Runtime Flag Is Off?

`get_configured_db_backend()` returns `postgres`, but `is_postgres_runtime_enabled()` returns false unless `ERP_ENABLE_POSTGRES_RUNTIME` is explicitly one of `1`, `true`, `yes`, or `on`.

Because the runtime flag is off, `get_active_db_backend()` returns `sqlite`. `validate_postgres_runtime_enabled()` would report `postgres_blocked=True` and include the reason `ERP_ENABLE_POSTGRES_RUNTIME is not enabled.`

Startup still follows the same SQLite path as `DB_BACKEND=sqlite`, including `app.py` `ensure_schema()` and `startup_database()` SQLite file validation.

Risk: MEDIUM. The fallback is intentional as a safety gate, but it can mask misconfiguration because `DB_BACKEND=postgres` does not make startup exercise PostgreSQL.

## 3. What Happens Today When DB_BACKEND=postgres, DATABASE_URL Is Set, And ERP_ENABLE_POSTGRES_RUNTIME=1?

Backend selection becomes PostgreSQL-aware:

- `get_active_db_backend()` returns `postgres`.
- `validate_postgres_runtime_enabled()` can return `ok=True` if a PostgreSQL driver is installed.
- Direct calls to `get_connection()` can use `_open_postgres_connection()`.

Application startup now fails safe:

1. `app.py` reads backend diagnostics before calling `ensure_schema()`.
2. When PostgreSQL runtime is active, `app.py` skips `ensure_schema()`.
3. `startup_database()` returns `stage=postgres_schema_not_implemented` before `_ensure_local_db_file()`, `_open_sqlite_connection()`, recovery, migrations, or schema bootstrap.
4. The user-facing message is: `PostgreSQL runtime is enabled, but PostgreSQL schema deployment is not implemented yet.`

Risk: HIGH. The immediate SQLite-startup hazard is guarded, but PostgreSQL runtime remains blocked because schema deployment and startup health checks are not implemented.

## 4. SQLite-Only Hard Blockers

| Startup Call | Why It Blocks PostgreSQL | Risk |
|---|---|---|
| `app.py` `ensure_schema()` before `startup_database()` | Guarded in Phase 5B.13B; still a blocker if bypassed outside the gate. | HIGH |
| `startup_database()` `_ensure_local_db_file()` | Guarded in Phase 5B.13B for active PostgreSQL runtime; still SQLite-only. | HIGH |
| `startup_database()` `is_database_valid(DB_PATH)` | Requires `DB_PATH` to exist and be a valid SQLite file; uses `sqlite_master` and PRAGMA metadata. | CRITICAL |
| `startup_database()` `get_database_health_snapshot(DB_PATH)` | Delegates to SQLite production readiness reporting and returns SQLite-specific health fields. | CRITICAL |
| `startup_database()` `_open_sqlite_connection()` | Used for preflight, migration, and final validation regardless of active backend. | CRITICAL |
| `_run_lightweight_integrity_checks()` | Calls SQLite schema metadata/DDL paths, including `ensure_schema_integrity()`. | CRITICAL |
| `_ensure_migration_metadata_tables()` | Creates SQLite-flavored tables, including `AUTOINCREMENT` in `migration_logs`. | HIGH |
| `_ensure_database_identity_table()` | Uses `PRAGMA table_info`, `ALTER TABLE`, and `?` placeholder writes. | HIGH |
| `_record_schema_version()` | Uses `INSERT OR IGNORE` and `?` placeholders. | HIGH |
| `_log_migration_event()` | Uses `?` placeholders; relies on portable write conversion, but its target table is created by SQLite DDL. | MEDIUM |
| `_open_sqlite_connection()` | Sets `sqlite3.Row`, `PRAGMA foreign_keys`, `busy_timeout`, `journal_mode=WAL`, and `synchronous=NORMAL`. | CRITICAL |
| PostgreSQL schema deployment | Not implemented; the startup gate blocks here by design. | CRITICAL |

## 5. Safe Or Already Backend-Aware Calls

| Call | Status | Risk |
|---|---|---|
| `get_configured_db_backend()` / `get_db_backend()` | Normalizes `DB_BACKEND` without opening a connection. | LOW |
| `is_postgres_runtime_enabled()` | Reads an explicit runtime flag from secrets/env. | LOW |
| `get_active_db_backend()` | Correctly gates PostgreSQL behind backend, runtime flag, and `DATABASE_URL`. | LOW |
| `validate_postgres_runtime_enabled()` | Checks configured backend, URL, runtime flag, and driver availability without connecting. | LOW |
| `_ensure_postgres_database_url()` | Adds `sslmode=require` when missing. | LOW |
| `_open_postgres_connection()` | Opens psycopg2/psycopg and wraps it in `PostgresManagedConnection`. | MEDIUM |
| `get_connection()` | Routes to PostgreSQL only when the active backend is PostgreSQL; otherwise falls back to SQLite. | MEDIUM |
| `execute_portable_query()` / `execute_portable_write()` | Convert `?` placeholders to `%s` for PostgreSQL where safe. | MEDIUM |
| `db_table_exists()` / `db_column_exists()` | Have PostgreSQL branches using `information_schema`; startup paths do not consistently use them. | MEDIUM |

## 6. What Would Fail First In A Real PostgreSQL Staging Run?

After Phase 5B.13B, the first failure is intentional: `startup_database()` returns `postgres_schema_not_implemented` before touching SQLite schema/recovery paths or opening a PostgreSQL connection.

If this guard were bypassed, the next blockers remain PostgreSQL schema absence, SQLite-specific schema engine calls, `?` placeholders, and post-startup app queries that are not yet dialect-routed.

## 7. Recommended Next Phase

1. Implement PostgreSQL schema deployment/migration ownership before allowing runtime startup to proceed.
2. Create PostgreSQL startup health checks that validate `DATABASE_URL`, driver availability, connectivity, required tables, migration version, and company count without touching `DB_PATH`.
3. Replace SQLite startup metadata helpers with backend-aware versions, especially migration metadata, database identity, schema version, and production readiness.
4. Route lightweight integrity checks through backend-aware table/column helpers, or keep SQLite self-heal checks strictly on SQLite paths.
5. Audit the first post-startup `get_connection()` call sites in `app.py` for SQLite placeholders and SQLite-specific SQL.

## Validation

- Passed: `python -m py_compile app.py database.py`
