import tempfile
import unittest
from pathlib import Path

from postgres_postdeploy_validator import (
    VALIDATION_CATEGORIES,
    build_postdeploy_validation_plan,
    generate_postdeploy_validation_plan,
    parse_captured_indexes,
    parse_expected_foreign_keys,
    parse_generated_tables,
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS migration_history (migration_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS schema_version (version BIGINT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS database_identity (instance_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS branch_type_catalog (branch_type_key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS branches (
    branch_id TEXT PRIMARY KEY,
    company_key TEXT,
    FOREIGN KEY (company_key) REFERENCES companies(key)
);
-- INDEX idx_branches_company ON branches captured from inventory; definition requires manual review.
"""


class PostdeployValidatorTests(unittest.TestCase):
    def test_validation_models_build(self):
        plan = build_postdeploy_validation_plan(
            SCHEMA_SQL,
            "- Score: 90/100\n- Deployment readiness: **YELLOW**",
            "Deployment readiness: **YELLOW**",
        )
        self.assertEqual(len(plan.categories), len(VALIDATION_CATEGORIES))
        self.assertEqual(len(plan.checklist_stages), 4)
        self.assertIn("Schema validation", [category.name for category in plan.categories])
        self.assertEqual(plan.source_schema_score, "90/100")
        self.assertEqual(plan.source_deployment_readiness, "YELLOW")

    def test_expected_inventory_parses_tables_indexes_and_fks(self):
        self.assertIn("branches", parse_generated_tables(SCHEMA_SQL))
        self.assertEqual(parse_captured_indexes(SCHEMA_SQL), ["idx_branches_company"])
        foreign_keys = parse_expected_foreign_keys(SCHEMA_SQL)
        self.assertEqual(len(foreign_keys), 1)
        self.assertEqual(foreign_keys[0].table, "branches")
        self.assertEqual(foreign_keys[0].references_table, "companies")

    def test_report_generation_works(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            schema_path = temp_path / "schema.sql"
            validation_path = temp_path / "validation.md"
            dry_run_path = temp_path / "dry_run.md"
            output_path = temp_path / "postdeploy.md"
            schema_path.write_text(SCHEMA_SQL, encoding="utf-8")
            validation_path.write_text("- Score: 90/100\n- Deployment readiness: **YELLOW**", encoding="utf-8")
            dry_run_path.write_text("Deployment readiness: **YELLOW**", encoding="utf-8")
            plan = generate_postdeploy_validation_plan(
                schema_sql_path=schema_path,
                schema_validation_report_path=validation_path,
                deployment_dry_run_plan_path=dry_run_path,
                output_path=output_path,
            )
            report_exists = output_path.exists()
            report = output_path.read_text(encoding="utf-8")
        self.assertTrue(report_exists)
        self.assertIn("# PostgreSQL Post-Deployment Validation Plan", report)
        self.assertIn("Stage 1: Schema deployment validation", report)
        self.assertGreaterEqual(len(plan.inventory.tables), 1)

    def test_no_db_access_or_sql_execution_paths(self):
        source = Path("postgres_postdeploy_validator.py").read_text(encoding="utf-8")
        forbidden_terms = [
            "sqlite3.connect",
            "psycopg",
            "conn.execute",
            "cursor.execute",
            "create_engine",
            "supabase.create_client",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
