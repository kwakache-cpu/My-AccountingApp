# PostgreSQL DML Inventory (Phase 5B.12E)

**Audited at:** 2026-06-02  
**Scope:** `database.py` only  
**Method:** text scan of `INSERT`, `UPDATE`, `DELETE` statements (read-only audit; no runtime changes).

## Summary counts (rough)

- **INSERT INTO**: ~12 occurrences (plus multiple `INSERT OR IGNORE` / `ON CONFLICT ... DO UPDATE` blocks)
- **UPDATE**: ~32 occurrences (includes schema/bootstrap routines and data backfills)
- **DELETE FROM**: 0 direct occurrences in `database.py` (FK DDL contains `ON DELETE ...`)

These counts are indicative (string-based scan), not an AST SQL parser.

## Risk classification rubric

- **Low risk**: diagnostic/audit logging, schema-version bookkeeping, migration log append-only metadata
- **Medium risk**: branch/user/admin CRUD in `database.py` (business-adjacent but not accounting/POS posting)
- **High risk**: any accounting, inventory/posting, POS, payroll, large backfills, or schema/bootstrap routines (out of scope for 5B.12E portability work)

## Inventory by area

### Low risk

- **Migration bookkeeping**
  - `INSERT INTO migration_logs (...)` (write-only operational log)
  - `INSERT OR IGNORE INTO schema_version (...)` (version tracking)
- **Identity metadata**
  - `INSERT INTO database_identity (...)`, `UPDATE database_identity ...` (runtime metadata)
- **Audit logging**
  - `INSERT INTO audit_logs (...)` (append-only diagnostic record)

### Medium risk

- **Company / subscription admin**
  - `INSERT INTO companies (...)`
  - `INSERT INTO subscription_plan_settings (...) ON CONFLICT ... DO UPDATE`
  - `INSERT INTO company_subscriptions (...) ON CONFLICT ... DO UPDATE`
  - `UPDATE companies ...` subscription/expiry changes
  - `UPDATE company_subscriptions ...`
- **Branch governance**
  - `INSERT INTO branches (...)`
  - `UPDATE branches ...` (manager assignment / update flows)
  - `INSERT OR IGNORE INTO users (...)` (default bookkeeper user, branch provisioning)
  - `UPDATE branch_module_grants ...` (enable/disable grants)
- **User administration**
  - `INSERT INTO users (...)` (branch-scoped user creation)
  - `UPDATE users ...` (status updates, assignment transfers)

### High risk (out of scope to change behavior)

- **Schema/bootstrap / backfills embedded in runtime startup**
  - Chart-of-accounts bootstrap: multiple `UPDATE chart_of_accounts ...`, `INSERT INTO chart_of_accounts ...`
  - Backfills on legacy columns: `UPDATE inventory ...`, `UPDATE vouchers ...`, `UPDATE fixed_assets ...`
  - Any DDL/PRAGMA-driven repair blocks are excluded from portability conversions in this phase.

## Portability notes (Phase 5B.12E goal)

- Identity portability is already addressed via `ensure_insert_sql_returning()` + `get_inserted_id()`.
- The remaining DML portability blocker is placeholder syntax:
  - SQLite uses `?`
  - psycopg requires `%s`
- Phase 5B.12E adds **write execution helpers only** so future DML migrations can be routed without changing business logic:
  - `execute_portable_write()`
  - `executemany_portable_write()`

