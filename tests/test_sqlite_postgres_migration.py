import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlite_to_postgres_migration import (
    MigrationStatus,
    build_batches,
    build_migration_plan,
    discover_postgres_foreign_keys,
    discover_postgres_tables,
    discover_sqlite_tables,
    estimate_batch_size,
    generate_migration_plan_report,
    order_tables_by_foreign_keys,
    quote_identifier,
)


POSTGRES_SCHEMA = """
BEGIN;
CREATE TABLE IF NOT EXISTS companies (
    key TEXT PRIMARY KEY,
    name TEXT
);
CREATE TABLE IF NOT EXISTS branches (
    branch_id TEXT PRIMARY KEY,
    company_key TEXT,
    FOREIGN KEY (company_key) REFERENCES companies(key)
);
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    branch_id TEXT,
    FOREIGN KEY (branch_id) REFERENCES branches(branch_id)
);
COMMIT;
"""


class SQLiteToPostgresMigrationTests(unittest.TestCase):
    def _sqlite_connection(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE TABLE companies (key TEXT PRIMARY KEY, name TEXT)")
        connection.execute(
            """
            CREATE TABLE branches (
                branch_id TEXT PRIMARY KEY,
                company_key TEXT,
                FOREIGN KEY (company_key) REFERENCES companies(key)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                branch_id TEXT,
                FOREIGN KEY (branch_id) REFERENCES branches(branch_id)
            )
            """
        )
        connection.executemany("INSERT INTO companies (key, name) VALUES (?, ?)", [("c1", "Company 1"), ("c2", "Company 2")])
        connection.executemany("INSERT INTO branches (branch_id, company_key) VALUES (?, ?)", [("b1", "c1"), ("b2", "c2")])
        connection.executemany("INSERT INTO users (id, branch_id) VALUES (?, ?)", [(1, "b1"), (2, "b1"), (3, "b2")])
        return connection

    def test_discovers_sqlite_and_postgres_tables(self):
        connection = self._sqlite_connection()
        try:
            self.assertEqual(discover_sqlite_tables(connection), ["branches", "companies", "users"])
        finally:
            connection.close()
        self.assertEqual(discover_postgres_tables(POSTGRES_SCHEMA), ["branches", "companies", "users"])

    def test_fk_dependency_order_parent_before_child(self):
        foreign_keys = discover_postgres_foreign_keys(POSTGRES_SCHEMA)
        ordered = order_tables_by_foreign_keys(["users", "branches", "companies"], foreign_keys)
        self.assertEqual(ordered, ["companies", "branches", "users"])

    def test_build_migration_plan_estimates_rows_batches_and_schema(self):
        connection = self._sqlite_connection()
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "postgres.sql"
            schema_path.write_text(POSTGRES_SCHEMA, encoding="utf-8")
            result = build_migration_plan(
                sqlite_connection=connection,
                sqlite_schema_report_path=None,
                postgres_schema_path=schema_path,
                default_batch_size=2,
            )
        connection.close()
        self.assertEqual(result.status, MigrationStatus.PLANNED)
        self.assertEqual(result.sqlite_table_count, 3)
        self.assertEqual(result.postgres_table_count, 3)
        self.assertEqual(result.fk_dependency_order, ["companies", "branches", "users"])
        self.assertEqual(result.estimated_total_rows, 7)
        table_plans = {plan.table_name: plan for plan in result.table_plans}
        self.assertEqual(table_plans["users"].row_count_estimate, 3)
        self.assertEqual(table_plans["users"].batch_count, 2)
        self.assertEqual(len(result.batches), 4)

    def test_batch_estimation(self):
        self.assertEqual(estimate_batch_size(0, 1000), 1000)
        self.assertEqual(estimate_batch_size(50, 1000), 100)
        self.assertEqual(estimate_batch_size(1500, 1000), 1000)
        batches = build_batches("users", 3, 2)
        self.assertEqual([(batch.offset, batch.limit, batch.estimated_rows) for batch in batches], [(0, 2, 2), (2, 2, 1)])

    def test_identifier_safety_blocks_injection(self):
        self.assertEqual(quote_identifier("companies"), '"companies"')
        with self.assertRaises(ValueError):
            quote_identifier("companies; DROP TABLE users")

    def test_generate_report_without_live_sqlite_uses_schema_inventory_fallback(self):
        report_text = """
### `companies`

```sql
CREATE TABLE companies (key TEXT PRIMARY KEY, name TEXT)
```

### `branches`

**Foreign keys:**
- `company_key` \u2192 `companies.key` (on_delete=NO ACTION)

```sql
CREATE TABLE branches (
    branch_id TEXT PRIMARY KEY,
    company_key TEXT,
    FOREIGN KEY (company_key) REFERENCES companies(key)
)
```
"""
        postgres_schema = """
CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS branches (
    branch_id TEXT PRIMARY KEY,
    company_key TEXT,
    FOREIGN KEY (company_key) REFERENCES companies(key)
);
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sqlite_report_path = temp_path / "compat.md"
            postgres_schema_path = temp_path / "schema.sql"
            output_path = temp_path / "migration_plan.md"
            sqlite_report_path.write_text(report_text, encoding="utf-8")
            postgres_schema_path.write_text(postgres_schema, encoding="utf-8")
            result = generate_migration_plan_report(
                output_path=output_path,
                sqlite_db_path=temp_path / "missing.db",
                sqlite_schema_report_path=sqlite_report_path,
                postgres_schema_path=postgres_schema_path,
            )
            report = output_path.read_text(encoding="utf-8")
        self.assertEqual(result.sqlite_table_count, 2)
        self.assertIsNone(result.estimated_total_rows)
        self.assertIn("SQLite row counts were not estimated", report)
        self.assertIn("No real data migration", report)

    def test_no_write_sql_keywords_in_framework_source(self):
        source = Path("sqlite_to_postgres_migration.py").read_text(encoding="utf-8")
        forbidden_snippets = [
            "INSERT INTO",
            "UPDATE ",
            "DELETE FROM",
            ".commit(",
            "psycopg",
            "create_engine",
            "ERP_ENABLE_POSTGRES_RUNTIME",
        ]
        for snippet in forbidden_snippets:
            self.assertNotIn(snippet, source)


if __name__ == "__main__":
    unittest.main()
