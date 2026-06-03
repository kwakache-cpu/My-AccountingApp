import tempfile
import unittest
from pathlib import Path

from postgres_deployment_planner import (
    build_dry_run_plan,
    generate_postgres_deployment_dry_run_plan,
    parse_fk_dependencies,
    parse_generated_tables,
)


VALIDATION_REPORT = """# PostgreSQL Schema Validation Report

## Validation Score

- Score: 90/100
- Deployment readiness: **YELLOW**
"""


class PostgresDeploymentPlannerTests(unittest.TestCase):
    def test_planner_detects_generated_tables_and_phases(self):
        schema_sql = """
CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS branches (
    branch_id TEXT PRIMARY KEY,
    company_key TEXT,
    FOREIGN KEY (company_key) REFERENCES companies(key)
);
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    company_key TEXT,
    FOREIGN KEY (company_key) REFERENCES companies(key)
);
"""
        self.assertEqual(parse_generated_tables(schema_sql), ["branches", "companies", "users"])
        plan = build_dry_run_plan(schema_sql, VALIDATION_REPORT)
        phase_2 = next(phase for phase in plan.phases if phase.phase_id == "Phase 2")
        self.assertEqual(phase_2.tables, ["companies", "branches", "users"])
        self.assertEqual(plan.deployment_readiness, "RED")
        self.assertTrue(phase_2.missing_tables)

    def test_planner_extracts_fk_dependencies(self):
        schema_sql = """
CREATE TABLE IF NOT EXISTS invoices (id BIGINT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS invoice_lines (
    id BIGINT PRIMARY KEY,
    invoice_id INTEGER,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);
"""
        dependencies = parse_fk_dependencies(schema_sql)
        self.assertEqual(len(dependencies), 1)
        self.assertEqual(dependencies[0].table, "invoice_lines")
        self.assertEqual(dependencies[0].referenced_table, "invoices")

    def test_planner_detects_later_phase_dependency_risk(self):
        schema_sql = """
CREATE TABLE IF NOT EXISTS invoices (
    id BIGINT PRIMARY KEY,
    journal_entry_id INTEGER,
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id)
);
CREATE TABLE IF NOT EXISTS journal_entries (id BIGINT PRIMARY KEY);
"""
        plan = build_dry_run_plan(schema_sql, VALIDATION_REPORT)
        self.assertTrue(any("later Phase 6" in risk for risk in plan.dependency_risks))
        self.assertEqual(plan.deployment_readiness, "RED")

    def test_planner_generates_report_file(self):
        schema_sql = """
CREATE TABLE IF NOT EXISTS migration_history (migration_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS branches (branch_id TEXT PRIMARY KEY);
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            schema_path = temp_path / "schema.sql"
            validation_path = temp_path / "validation.md"
            deployment_plan_path = temp_path / "deployment.md"
            output_path = temp_path / "dry_run.md"
            schema_path.write_text(schema_sql, encoding="utf-8")
            validation_path.write_text(VALIDATION_REPORT, encoding="utf-8")
            deployment_plan_path.write_text("# Deployment plan\n", encoding="utf-8")
            plan = generate_postgres_deployment_dry_run_plan(
                schema_sql_path=schema_path,
                validation_report_path=validation_path,
                deployment_plan_path=deployment_plan_path,
                output_path=output_path,
            )
            report_exists = output_path.exists()
            report = output_path.read_text(encoding="utf-8")
        self.assertTrue(report_exists)
        self.assertIn("# PostgreSQL Deployment Dry-Run Plan", report)
        self.assertIn("## Rollback Planning", report)
        self.assertEqual(len(plan.phases), 9)

    def test_planner_does_not_connect_to_database(self):
        source = Path("postgres_deployment_planner.py").read_text(encoding="utf-8")
        forbidden_terms = ["sqlite3.connect", "psycopg", "DATABASE_URL", "conn.execute", "cursor.execute"]
        for term in forbidden_terms:
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
