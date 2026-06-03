import tempfile
import unittest
from pathlib import Path

from postgres_schema_validator import (
    REQUIRED_CORE_TABLES,
    find_forbidden_sqlite_syntax,
    generate_postgres_schema_validation_report,
    parse_generated_tables,
    validate_postgres_schema_artifacts,
)


def _write_fixture_files(temp_path: Path, schema_sql: str, table_names: list[str] | None = None) -> dict[str, Path]:
    table_names = table_names or ["companies", "branches"]
    compatibility_rows = "\n".join(
        f"| `{table_name}` | 0 | id | 0 | 0 | 0 | — |" for table_name in table_names
    )
    compatibility = f"""# PostgreSQL Schema Compatibility

**Tables:** {len(table_names)}

## Table Inventory
| Table | Rows | Primary Key | FKs | Indexes | Triggers | SQLite-only |
|-------|-----:|-------------|----:|--------:|---------:|-------------|
{compatibility_rows}
"""
    summary = """# Generated PostgreSQL Schema Summary

## Statistics

- Table count: 2
- Tables represented in SQL: 2
- Index count captured: 1
- FK count captured: 1
- Unsupported constructs: 1
- Manual review items: 1
"""
    paths = {
        "schema_sql_path": temp_path / "schema.sql",
        "schema_summary_path": temp_path / "summary.md",
        "compatibility_report_path": temp_path / "compatibility.md",
        "fk_readiness_report_path": temp_path / "fk.md",
        "deployment_plan_path": temp_path / "plan.md",
    }
    paths["schema_sql_path"].write_text(schema_sql, encoding="utf-8")
    paths["schema_summary_path"].write_text(summary, encoding="utf-8")
    paths["compatibility_report_path"].write_text(compatibility, encoding="utf-8")
    paths["fk_readiness_report_path"].write_text("# FK readiness\n", encoding="utf-8")
    paths["deployment_plan_path"].write_text("# Deployment plan\n", encoding="utf-8")
    return paths


class PostgresSchemaValidatorTests(unittest.TestCase):
    def test_validator_detects_generated_tables(self):
        schema_sql = """
CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS branches (
    branch_id TEXT PRIMARY KEY,
    company_key TEXT,
    FOREIGN KEY (company_key) REFERENCES companies(key)
);
-- INDEX idx_branches_company ON branches captured from inventory; definition requires manual review.
"""
        self.assertEqual(parse_generated_tables(schema_sql), ["branches", "companies"])
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_fixture_files(Path(temp_dir), schema_sql)
            result = validate_postgres_schema_artifacts(**paths)
        self.assertEqual(result.expected_table_count, 2)
        self.assertEqual(result.generated_table_count, 2)
        self.assertEqual(result.index_count, 1)
        self.assertEqual(result.foreign_key_count, 1)

    def test_validator_detects_forbidden_sqlite_syntax(self):
        schema_sql = "CREATE TABLE bad (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT); -- ?"
        forbidden = find_forbidden_sqlite_syntax(schema_sql)
        self.assertIn("AUTOINCREMENT", forbidden)
        self.assertIn("?", forbidden)

    def test_validator_detects_missing_required_tables(self):
        schema_sql = "CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY);"
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_fixture_files(Path(temp_dir), schema_sql, table_names=["companies"])
            result = validate_postgres_schema_artifacts(**paths)
        self.assertIn("branches", result.missing_required_tables)
        self.assertEqual(result.deployment_readiness, "RED")

    def test_validator_produces_report(self):
        schema_sql = "\n".join(
            f"CREATE TABLE IF NOT EXISTS {table_name} (id BIGINT PRIMARY KEY);"
            for table_name in sorted(REQUIRED_CORE_TABLES)
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _write_fixture_files(temp_path, schema_sql, table_names=sorted(REQUIRED_CORE_TABLES))
            report_path = temp_path / "validation.md"
            result = generate_postgres_schema_validation_report(output_path=report_path, **paths)
            report_exists = report_path.exists()
            report = report_path.read_text(encoding="utf-8")
        self.assertTrue(report_exists)
        self.assertIn("# PostgreSQL Schema Validation Report", report)
        self.assertIn("Deployment readiness", report)
        self.assertEqual(result.missing_required_tables, [])

    def test_validator_does_not_connect_to_database(self):
        source = Path("postgres_schema_validator.py").read_text(encoding="utf-8")
        forbidden_terms = ["sqlite3.connect", "psycopg", "DATABASE_URL", "conn.execute", "cursor.execute"]
        for term in forbidden_terms:
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
