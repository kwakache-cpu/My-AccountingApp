import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlite_to_postgres_migration import (
    MismatchClassification,
    build_data_volume_audit,
    build_migration_plan,
    build_schema_mismatch_reviews,
    generate_data_volume_audit_report,
    generate_mismatch_review_report,
    parse_columns_from_create_sql,
    quote_identifier,
)


class SQLitePostgresMigrationReviewTests(unittest.TestCase):
    def test_parse_columns_captures_type_default_and_nullability(self):
        columns = parse_columns_from_create_sql(
            "sample",
            """
            CREATE TABLE sample (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL DEFAULT 0,
                branch_id TEXT DEFAULT '',
                sale_reference TEXT NOT NULL,
                name TEXT NOT NULL
            )
            """,
        )
        self.assertEqual(columns["id"].data_type, "INTEGER")
        self.assertTrue(columns["id"].primary_key)
        self.assertFalse(columns["id"].nullable)
        self.assertEqual(columns["amount"].default, "0")
        self.assertEqual(columns["branch_id"].default, "''")
        self.assertIn("sale_reference", columns)
        self.assertFalse(columns["name"].nullable)

    def test_missing_postgres_column_is_blocker(self):
        sqlite_columns = {
            "pos_sales": parse_columns_from_create_sql(
                "pos_sales",
                "CREATE TABLE pos_sales (id INTEGER PRIMARY KEY, sale_reference TEXT NOT NULL)",
            )
        }
        postgres_columns = {
            "pos_sales": parse_columns_from_create_sql(
                "pos_sales",
                "CREATE TABLE IF NOT EXISTS pos_sales (id BIGINT PRIMARY KEY)",
            )
        }
        reviews = build_schema_mismatch_reviews(sqlite_columns, postgres_columns)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].column, "sale_reference")
        self.assertEqual(reviews[0].classification, MismatchClassification.BLOCKER)

    def test_identifier_safety_blocks_injection(self):
        self.assertEqual(quote_identifier("companies"), '"companies"')
        with self.assertRaises(ValueError):
            quote_identifier("companies; DROP TABLE users")

    def test_generate_mismatch_review_report(self):
        sqlite_report = """
### `companies`

```sql
CREATE TABLE companies (key TEXT PRIMARY KEY, name TEXT, live_only TEXT)
```
"""
        postgres_schema = "CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY, name TEXT);"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sqlite_db = temp_path / "sample.db"
            connection = sqlite3.connect(sqlite_db)
            connection.execute("CREATE TABLE companies (key TEXT PRIMARY KEY, name TEXT, live_only TEXT)")
            connection.close()
            sqlite_report_path = temp_path / "sqlite.md"
            postgres_schema_path = temp_path / "postgres.sql"
            output_path = temp_path / "review.md"
            sqlite_report_path.write_text(sqlite_report, encoding="utf-8")
            postgres_schema_path.write_text(postgres_schema, encoding="utf-8")
            result = build_migration_plan(
                sqlite_db_path=sqlite_db,
                sqlite_schema_report_path=sqlite_report_path,
                postgres_schema_path=postgres_schema_path,
            )
            generate_mismatch_review_report(
                output_path=output_path,
                sqlite_db_path=sqlite_db,
                sqlite_schema_report_path=sqlite_report_path,
                postgres_schema_path=postgres_schema_path,
            )
            report = output_path.read_text(encoding="utf-8")
        self.assertEqual(len(result.schema_mismatches), 1)
        self.assertIn("Blocker count: 1", report)
        self.assertIn("live_only", report)

    def test_data_volume_audit_uses_read_only_counts_and_pragmas(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sqlite_db = temp_path / "sample.db"
            connection = sqlite3.connect(sqlite_db)
            connection.execute("CREATE TABLE companies (key TEXT PRIMARY KEY, name TEXT)")
            connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, company_key TEXT)")
            connection.executemany("INSERT INTO companies (key, name) VALUES (?, ?)", [("c1", "One"), ("c2", "Two")])
            connection.executemany("INSERT INTO users (id, company_key) VALUES (?, ?)", [(1, "c1"), (2, "c1"), (3, "c2")])
            connection.commit()
            connection.close()
            output_path = temp_path / "volume.md"
            audit = build_data_volume_audit(sqlite_db)
            generated = generate_data_volume_audit_report(output_path=output_path, sqlite_db_path=sqlite_db)
            report = output_path.read_text(encoding="utf-8")
        self.assertEqual(audit.total_row_count, 5)
        self.assertEqual(generated.total_row_count, 5)
        self.assertGreater(audit.db_file_size_bytes, 0)
        self.assertIn("SQLite to PostgreSQL Data Volume Audit", report)
        self.assertIn("Recommended data bundle", report)


if __name__ == "__main__":
    unittest.main()
