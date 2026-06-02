# PostgreSQL Schema Engine Audit Part 1

Scope: `database.py` only. Runtime code was not changed.

## Inventory

| Occurrence | Category | PostgreSQL Risk | Line(s) and Function(s) |
|---|---|---|---|
| `PRAGMA` | SQLite connection/schema pragma | HIGH | 398 `_get_existing_columns`; 644 `<module>`; 709 `get_postgres_readiness_diagnostics`; 769 `get_data_migration_export_plan`; 1498 `db_column_exists`; 2445 `_create_runtime_snapshot_file`; 2446 `_create_runtime_snapshot_file`; 2447 `_create_runtime_snapshot_file`; 2449 `_create_runtime_snapshot_file`; 3604 `_ensure_subscription_billing_schema`; 3642 `_ensure_subscription_billing_schema`; 3690 `_ensure_subscription_billing_schema`; 4222 `_ensure_local_db_file`; 4223 `_ensure_local_db_file`; 4224 `_ensure_local_db_file`; 4243 `_open_sqlite_connection`; 4244 `_open_sqlite_connection`; 4245 `_open_sqlite_connection`; 4246 `_open_sqlite_connection`; 4264 `ensure_schema`; 4328 `_ensure_database_identity_table`; 4400 `is_database_valid`; 4890 `_branch_licensing_column_exists`; 6535 `ensure_schema_integrity`; 6541 `ensure_schema_integrity`; 6569 `ensure_schema_integrity`; 6608 `ensure_schema_integrity`; 6628 `ensure_schema_integrity`; 6776 `ensure_schema_integrity`; 6823 `ensure_schema_integrity`; 6913 `ensure_schema_integrity`; 6977 `ensure_schema_integrity`; 7265 `ensure_schema_integrity`; 7281 `ensure_schema_integrity`; 7335 `ensure_inventory_schema_integrity`; 7390 `ensure_inventory_schema_integrity`; 7445 `ensure_stock_movements_schema_integrity`; 7497 `ensure_cashier_closings_schema`; 7531 `ensure_pos_sales_schema`; 7563 `ensure_pos_sales_schema`; 7618 `ensure_pos_sales_schema`; 7669 `ensure_pos_sales_schema`; 7716 `ensure_pos_sales_schema`; 7764 `_ensure_app_compatibility_tables`; 7781 `_ensure_app_compatibility_tables`; 7804 `_ensure_app_compatibility_tables`; 7825 `_ensure_app_compatibility_tables`; 7979 `_deploy_full_schema`; 8033 `_deploy_full_schema`; 8079 `_deploy_full_schema`; 8132 `_deploy_full_schema`; 8194 `_deploy_full_schema`; 8256 `_deploy_full_schema`; 8308 `_deploy_full_schema`; 8333 `_deploy_full_schema`; 8357 `_deploy_full_schema`; 8387 `_deploy_full_schema`; 8425 `_deploy_full_schema`; 8476 `_deploy_full_schema`; 8515 `_deploy_full_schema`; 9070 `log_audit_action`; 9114 `get_audit_operations_summary` |
| `sqlite_master` | SQLite catalog introspection | CRITICAL | 43 `collect_row_counts`; 392 `_get_existing_tables`; 649 `<module>`; 649 `<module>`; 682 `<module>`; 705 `get_postgres_readiness_diagnostics`; 764 `get_data_migration_export_plan`; 1478 `db_table_exists`; 4178 `get_subscription_billing_diagnostics`; 4378 `_table_exists`; 4396 `is_database_valid`; 4472 `get_database_production_readiness_report`; 6530 `ensure_schema_integrity`; 6566 `ensure_schema_integrity`; 6588 `ensure_schema_integrity` |
| `sqlite_sequence` | SQLite sequence metadata | CRITICAL | None |
| `AUTOINCREMENT` | SQLite identity DDL | HIGH | 645 `<module>`; 3591 `_ensure_subscription_billing_schema`; 3629 `_ensure_subscription_billing_schema`; 3665 `_ensure_subscription_billing_schema`; 4298 `_ensure_migration_metadata_tables`; 5035 `ensure_branch_licensing_schema_integrity`; 5048 `ensure_branch_licensing_schema_integrity`; 6494 `ensure_schema_integrity`; 6505 `ensure_schema_integrity`; 6616 `ensure_schema_integrity`; 6793 `ensure_schema_integrity`; 6858 `ensure_schema_integrity`; 6875 `ensure_schema_integrity`; 6899 `ensure_schema_integrity`; 6942 `ensure_schema_integrity`; 6964 `ensure_schema_integrity`; 6995 `ensure_schema_integrity`; 7015 `ensure_schema_integrity`; 7045 `ensure_schema_integrity`; 7080 `ensure_schema_integrity`; 7099 `ensure_schema_integrity`; 7114 `ensure_schema_integrity`; 7134 `ensure_schema_integrity`; 7165 `ensure_schema_integrity`; 7189 `ensure_schema_integrity`; 7214 `ensure_schema_integrity`; 7231 `ensure_schema_integrity`; 7251 `ensure_schema_integrity`; 7310 `ensure_inventory_schema_integrity`; 7370 `ensure_inventory_schema_integrity`; 7428 `ensure_stock_movements_schema_integrity`; 7482 `ensure_cashier_closings_schema`; 7539 `ensure_pos_sales_schema`; 7599 `ensure_pos_sales_schema`; 7648 `ensure_pos_sales_schema`; 7701 `ensure_pos_sales_schema`; 7750 `_ensure_app_compatibility_tables`; 7796 `_ensure_app_compatibility_tables`; 7817 `_ensure_app_compatibility_tables`; 7994 `_deploy_full_schema`; 8062 `_deploy_full_schema`; 8104 `_deploy_full_schema`; 8165 `_deploy_full_schema`; 8222 `_deploy_full_schema`; 8293 `_deploy_full_schema`; 8325 `_deploy_full_schema`; 8375 `_deploy_full_schema`; 8402 `_deploy_full_schema`; 8458 `_deploy_full_schema`; 8502 `_deploy_full_schema` |
| `INSERT OR IGNORE` | SQLite conflict handling | HIGH | 646 `<module>`; 1463 `db_insert_ignore_sql`; 4753 `_record_schema_version`; 4909 `seed_branch_type_catalog`; 4932 `seed_branch_type_module_defaults`; 4992 `ensure_branch_module_grants_for_branch`; 5596 `create_company_branch`; 6786 `ensure_schema_integrity`; 7291 `ensure_schema_integrity`; 8370 `_deploy_full_schema`; 8543 `_deploy_full_schema` |
| `CREATE TABLE` | Schema DDL create table | MEDIUM | 3590 `_ensure_subscription_billing_schema`; 3628 `_ensure_subscription_billing_schema`; 3664 `_ensure_subscription_billing_schema`; 4288 `_ensure_migration_metadata_tables`; 4297 `_ensure_migration_metadata_tables`; 4317 `_ensure_database_identity_table`; 5023 `ensure_branch_licensing_schema_integrity`; 5034 `ensure_branch_licensing_schema_integrity`; 5047 `ensure_branch_licensing_schema_integrity`; 6493 `ensure_schema_integrity`; 6504 `ensure_schema_integrity`; 6615 `ensure_schema_integrity`; 6766 `ensure_schema_integrity`; 6792 `ensure_schema_integrity`; 6857 `ensure_schema_integrity`; 6874 `ensure_schema_integrity`; 6898 `ensure_schema_integrity`; 6941 `ensure_schema_integrity`; 6963 `ensure_schema_integrity`; 6994 `ensure_schema_integrity`; 7014 `ensure_schema_integrity`; 7044 `ensure_schema_integrity`; 7079 `ensure_schema_integrity`; 7098 `ensure_schema_integrity`; 7113 `ensure_schema_integrity`; 7133 `ensure_schema_integrity`; 7164 `ensure_schema_integrity`; 7188 `ensure_schema_integrity`; 7213 `ensure_schema_integrity`; 7230 `ensure_schema_integrity`; 7250 `ensure_schema_integrity`; 7271 `ensure_schema_integrity`; 7309 `ensure_inventory_schema_integrity`; 7369 `ensure_inventory_schema_integrity`; 7427 `ensure_stock_movements_schema_integrity`; 7481 `ensure_cashier_closings_schema`; 7538 `ensure_pos_sales_schema`; 7598 `ensure_pos_sales_schema`; 7647 `ensure_pos_sales_schema`; 7700 `ensure_pos_sales_schema`; 7749 `_ensure_app_compatibility_tables`; 7795 `_ensure_app_compatibility_tables`; 7816 `_ensure_app_compatibility_tables`; 7955 `_deploy_full_schema`; 7993 `_deploy_full_schema`; 8019 `_deploy_full_schema`; 8061 `_deploy_full_schema`; 8103 `_deploy_full_schema`; 8164 `_deploy_full_schema`; 8221 `_deploy_full_schema`; 8292 `_deploy_full_schema`; 8324 `_deploy_full_schema`; 8347 `_deploy_full_schema`; 8374 `_deploy_full_schema`; 8401 `_deploy_full_schema`; 8457 `_deploy_full_schema`; 8501 `_deploy_full_schema`; 8536 `_deploy_full_schema` |
| `ALTER TABLE` | Schema DDL alter table | HIGH | 529 `get_fixed_assets_schema_diagnostics`; 574 `get_fixed_assets_schema_diagnostics`; 3618 `_ensure_subscription_billing_schema`; 3657 `_ensure_subscription_billing_schema`; 3716 `_ensure_subscription_billing_schema`; 4267 `ensure_schema`; 4336 `_ensure_database_identity_table`; 4897 `_ensure_branch_licensing_column`; 6539 `ensure_schema_integrity`; 6562 `ensure_schema_integrity`; 6572 `ensure_schema_integrity`; 6611 `ensure_schema_integrity`; 6645 `ensure_schema_integrity`; 6780 `ensure_schema_integrity`; 6782 `ensure_schema_integrity`; 6784 `ensure_schema_integrity`; 6853 `ensure_schema_integrity`; 6928 `ensure_schema_integrity`; 6991 `ensure_schema_integrity`; 7268 `ensure_schema_integrity`; 7285 `ensure_schema_integrity`; 7287 `ensure_schema_integrity`; 7289 `ensure_schema_integrity`; 7364 `ensure_inventory_schema_integrity`; 7411 `ensure_inventory_schema_integrity`; 7463 `ensure_stock_movements_schema_integrity`; 7513 `ensure_cashier_closings_schema`; 7534 `ensure_pos_sales_schema`; 7588 `ensure_pos_sales_schema`; 7637 `ensure_pos_sales_schema`; 7691 `ensure_pos_sales_schema`; 7732 `ensure_pos_sales_schema`; 7777 `_ensure_app_compatibility_tables`; 7791 `_ensure_app_compatibility_tables`; 7813 `_ensure_app_compatibility_tables`; 7834 `_ensure_app_compatibility_tables`; 7988 `_deploy_full_schema`; 8052 `_deploy_full_schema`; 8096 `_deploy_full_schema`; 8153 `_deploy_full_schema`; 8216 `_deploy_full_schema`; 8261 `_deploy_full_schema`; 8321 `_deploy_full_schema`; 8343 `_deploy_full_schema`; 8369 `_deploy_full_schema`; 8398 `_deploy_full_schema`; 8447 `_deploy_full_schema`; 8495 `_deploy_full_schema`; 8529 `_deploy_full_schema` |
| `BEGIN IMMEDIATE` | SQLite transaction locking | HIGH | 1639 `SQLiteWriteTransaction.__enter__` |
| `WAL` | SQLite journal mode | MEDIUM | 1740 `get_sqlite_concurrency_diagnostics`; 2447 `_create_runtime_snapshot_file`; 4223 `_ensure_local_db_file`; 4245 `_open_sqlite_connection` |
| `busy_timeout` | SQLite lock timeout setting | MEDIUM | 1737 `get_sqlite_concurrency_diagnostics`; 2445 `_create_runtime_snapshot_file`; 2449 `_create_runtime_snapshot_file`; 4222 `_ensure_local_db_file`; 4244 `_open_sqlite_connection` |
| `journal_mode` | SQLite journal mode setting | MEDIUM | 1740 `get_sqlite_concurrency_diagnostics`; 2447 `_create_runtime_snapshot_file`; 4223 `_ensure_local_db_file`; 4245 `_open_sqlite_connection` |
| `synchronous` | SQLite durability setting | MEDIUM | 1741 `get_sqlite_concurrency_diagnostics`; 4224 `_ensure_local_db_file`; 4246 `_open_sqlite_connection` |
| `foreign_keys` | SQLite FK pragma | MEDIUM | 2446 `_create_runtime_snapshot_file`; 4243 `_open_sqlite_connection` |
| `sqlite3.Row` | SQLite row adapter | MEDIUM | 4239 `_open_sqlite_connection`; 5105 `_fetch_company_name`; 5131 `backfill_branch_codes`; 5231 `count_active_branches`; 5305 `get_branch_type_catalog`; 5363 `list_company_branches_with_grants`; 5426 `repair_branch_module_grants`; 5499 `create_company_branch`; 5687 `_fetch_company_user_by_user_id`; 5768 `assign_branch_manager`; 5788 `list_branch_users`; 5935 `update_branch_user_status`; 5936 `update_branch_user_status`; 5982 `fetch_branch_manager_candidates`; 6023 `_fetch_branch_type_default_module_keys`; 6041 `get_branch_enabled_modules`; 6137 `update_company_branch`; 6301 `list_company_staff_for_assignment`; 6359 `update_company_staff_branch_assignment` |
| `row_factory` | SQLite row factory configuration | MEDIUM | 4239 `_open_sqlite_connection` |

## Count By Category

| Category | Count |
|---|---:|
| Schema DDL alter table | 49 |
| Schema DDL create table | 58 |
| SQLite catalog introspection | 15 |
| SQLite conflict handling | 11 |
| SQLite connection/schema pragma | 62 |
| SQLite durability setting | 3 |
| SQLite FK pragma | 2 |
| SQLite identity DDL | 50 |
| SQLite journal mode | 4 |
| SQLite journal mode setting | 4 |
| SQLite lock timeout setting | 5 |
| SQLite row adapter/configuration | 20 |
| SQLite sequence metadata | 0 |
| SQLite transaction locking | 1 |

## Highest-Risk Schema/Bootstrap Functions

| Function | Max Risk | Why It Is High Risk |
|---|---|---|
| `ensure_schema_integrity` | CRITICAL | Concentrates SQLite catalog checks, PRAGMA table introspection, many `CREATE TABLE`, `ALTER TABLE`, `AUTOINCREMENT`, and seed `INSERT OR IGNORE` paths. |
| `_deploy_full_schema` | HIGH | Full bootstrap DDL uses SQLite identity syntax, PRAGMA table introspection, ALTER backfills, and SQLite conflict inserts. |
| `_ensure_subscription_billing_schema` | HIGH | Creates and mutates subscription/payment tables with SQLite DDL and identity columns. |
| `_open_sqlite_connection` | HIGH | Centralizes `sqlite3.Row`, `row_factory`, and SQLite-only PRAGMA runtime settings. |
| `_ensure_local_db_file` | HIGH | Bootstraps a local SQLite database file and sets WAL/synchronous/busy timeout PRAGMAs. |
| `_create_runtime_snapshot_file` | HIGH | Opens raw SQLite connections and applies PRAGMAs before backup snapshot operations. |
| `get_postgres_readiness_diagnostics` | CRITICAL | Reads `sqlite_master` and PRAGMA table metadata while reporting PostgreSQL readiness. |
| `get_data_migration_export_plan` | CRITICAL | Builds export planning from `sqlite_master` and PRAGMA table metadata. |
| `is_database_valid` | CRITICAL | Uses `sqlite_master` and PRAGMA table metadata as production readiness gates. |
| `get_database_production_readiness_report` | CRITICAL | Uses SQLite catalog state for production readiness reporting. |

## Top 20 PostgreSQL Cutover Blockers Inside database.py

| Rank | Blocker | Risk |
|---:|---|---|
| 1 | `ensure_schema_integrity` is a SQLite schema engine with catalog reads, PRAGMA column introspection, additive ALTERs, identity columns, and seed inserts. | CRITICAL |
| 2 | `_deploy_full_schema` is a second full schema deployment path that duplicates many SQLite DDL assumptions. | HIGH |
| 3 | `sqlite_master` remains the table-existence source in multiple readiness and bootstrap paths. | CRITICAL |
| 4 | `AUTOINCREMENT` appears throughout table definitions and must become PostgreSQL identity/sequence behavior. | HIGH |
| 5 | `ALTER TABLE ... ADD COLUMN` is embedded in many startup self-heal flows and needs PostgreSQL-compatible migration ownership. | HIGH |
| 6 | `PRAGMA table_info` is the dominant column introspection mechanism and must move to PostgreSQL catalog queries. | HIGH |
| 7 | `_open_sqlite_connection` sets SQLite-only runtime PRAGMAs and row adapters. | HIGH |
| 8 | `_ensure_local_db_file` creates/configures local SQLite files, which does not map to PostgreSQL provisioning. | HIGH |
| 9 | `BEGIN IMMEDIATE` encodes SQLite write-lock behavior that does not translate directly to PostgreSQL transactions. | HIGH |
| 10 | `INSERT OR IGNORE` seed paths need explicit PostgreSQL `ON CONFLICT DO NOTHING` conflict targets. | HIGH |
| 11 | `_ensure_subscription_billing_schema` owns payment/subscription DDL outside a migration system. | HIGH |
| 12 | `ensure_branch_licensing_schema_integrity` owns branch licensing DDL and seed data inside runtime code. | HIGH |
| 13 | `ensure_inventory_schema_integrity`, `ensure_stock_movements_schema_integrity`, `ensure_cashier_closings_schema`, and `ensure_pos_sales_schema` create operational tables at runtime. | HIGH |
| 14 | `_ensure_app_compatibility_tables` creates compatibility tables and mutates columns at runtime. | HIGH |
| 15 | `sqlite3.Row` checks are spread through branch/user helper contracts. | MEDIUM |
| 16 | `row_factory` makes callers depend on SQLite row shape. | MEDIUM |
| 17 | `WAL`, `journal_mode`, `synchronous`, and `busy_timeout` are SQLite operational tuning, not PostgreSQL runtime configuration. | MEDIUM |
| 18 | `foreign_keys` PRAGMA must be removed from PostgreSQL paths because FK enforcement is not toggled per connection the same way. | MEDIUM |
| 19 | `get_postgres_readiness_diagnostics` mixes readiness reporting with live SQLite metadata inspection. | CRITICAL |
| 20 | `get_data_migration_export_plan` assumes SQLite table and column discovery semantics. | CRITICAL |

## Recommended Phase 5B.13A-2 Scope

1. Split schema/bootstrap ownership into PostgreSQL-aware DDL/migration paths and stop relying on runtime SQLite self-heal logic for PostgreSQL.
2. Replace `sqlite_master` and PRAGMA table/column introspection with PostgreSQL catalog or `information_schema` queries.
3. Translate `AUTOINCREMENT` to PostgreSQL identity/sequence behavior and document sequence reset ownership.
4. Convert `INSERT OR IGNORE` to explicit `ON CONFLICT DO NOTHING` with verified unique constraints.
5. Replace `BEGIN IMMEDIATE` and SQLite lock retry assumptions with PostgreSQL transaction/isolation semantics.
6. Decouple `sqlite3.Row` and `row_factory` expectations from callers before switching drivers.

## Validation

- Passed: `python -m py_compile database.py`
