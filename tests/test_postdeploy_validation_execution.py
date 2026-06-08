import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from postgres_postdeploy_validator import (
    PostDeployValidationStatus,
    build_postdeploy_validation_checks,
    execute_postdeploy_validation,
    is_select_only_sql,
    validate_postdeploy_execution_guard,
    validate_select_only_checks,
    PostDeployValidationCheck,
)
from postgres_staging_deployer import main


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS migration_history (migration_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS schema_version (version BIGINT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS database_identity (instance_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY, name TEXT);
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
CREATE INDEX IF NOT EXISTS idx_branches_company ON branches(company_key);
"""


class FetchingCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.closed = False

    def execute(self, sql, parameters=None):
        self.calls.append((sql, parameters or {}))

    def fetchall(self):
        return list(self.rows)

    def close(self):
        self.closed = True


class PostdeployValidationExecutionTests(unittest.TestCase):
    def _schema_file(self, temp_path: Path) -> Path:
        schema_path = temp_path / "schema.sql"
        schema_path.write_text(SCHEMA_SQL, encoding="utf-8")
        return schema_path

    def _env(self):
        return {
            "ERP_ENVIRONMENT": "staging",
            "DATABASE_URL": "postgresql://user:secret@example.test/app",
        }

    def test_validation_blocks_without_staging(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = self._schema_file(Path(temp_dir))
            guard = validate_postdeploy_execution_guard(
                environ={"ERP_ENVIRONMENT": "production", "DATABASE_URL": "postgresql://example/app"},
                schema_sql_path=schema_path,
                driver_preference=("missing_driver_for_test",),
            )
        self.assertEqual(guard.status, PostDeployValidationStatus.BLOCKED)
        self.assertFalse(guard.guard_results["ERP_ENVIRONMENT_is_staging"])

    def test_validation_blocks_without_database_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = self._schema_file(Path(temp_dir))
            guard = validate_postdeploy_execution_guard(
                environ={"ERP_ENVIRONMENT": "staging"},
                schema_sql_path=schema_path,
                driver_preference=("missing_driver_for_test",),
            )
        self.assertEqual(guard.status, PostDeployValidationStatus.BLOCKED)
        self.assertFalse(guard.guard_results["DATABASE_URL_present"])

    def test_validation_only_allows_select(self):
        self.assertTrue(is_select_only_sql("SELECT table_name FROM information_schema.tables"))
        self.assertFalse(is_select_only_sql("UPDATE companies SET name = 'x'"))
        self.assertFalse(is_select_only_sql("CREATE TABLE unsafe (id INTEGER)"))
        unsafe_check = PostDeployValidationCheck(
            query_id="unsafe",
            category="table_exists",
            name="Unsafe",
            sql="DELETE FROM companies",
        )
        with self.assertRaises(ValueError):
            validate_select_only_checks((unsafe_check,))

    def test_mocked_validation_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            schema_path = self._schema_file(temp_path)
            output_path = temp_path / "results.md"
            connection = Mock()
            connection.execute.return_value = Mock(fetchall=Mock(return_value=[("ok",)]))
            connector = Mock(return_value=connection)
            with patch("postgres_postdeploy_validator.detect_postgres_driver", return_value=("psycopg", True)):
                result = execute_postdeploy_validation(
                    schema_sql_path=schema_path,
                    output_path=output_path,
                    environ=self._env(),
                    connector=connector,
                )
        self.assertEqual(result.status, PostDeployValidationStatus.PASSED)
        self.assertGreater(result.checks_executed, 0)
        self.assertEqual(result.checks_failed, 0)
        connector.assert_called_once_with("postgresql://user:secret@example.test/app", "psycopg", 5)
        connection.close.assert_called_once_with()
        for call in connection.execute.call_args_list:
            self.assertTrue(is_select_only_sql(call.args[0]))
            self.assertNotIn("secret", str(call.args))

    def test_mocked_validation_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            schema_path = self._schema_file(temp_path)
            output_path = temp_path / "results.md"
            connection = Mock()
            connection.execute.return_value = Mock(fetchall=Mock(return_value=[]))
            connector = Mock(return_value=connection)
            with patch("postgres_postdeploy_validator.detect_postgres_driver", return_value=("psycopg", True)):
                result = execute_postdeploy_validation(
                    schema_sql_path=schema_path,
                    output_path=output_path,
                    environ=self._env(),
                    connector=connector,
                )
            output_exists = output_path.exists()
            output_text = output_path.read_text(encoding="utf-8")
        self.assertEqual(result.status, PostDeployValidationStatus.FAILED)
        self.assertGreater(result.checks_failed, 0)
        self.assertTrue(output_exists)
        self.assertNotIn("secret", output_text)

    def test_cli_option_routes_only_validation(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        execution_result = Mock(
            status=PostDeployValidationStatus.PASSED,
            guard=Mock(
                blocked=False,
                guard_results={
                    "ERP_ENVIRONMENT_is_staging": True,
                    "DATABASE_URL_present": True,
                    "schema_artifact_present": True,
                    "postgres_driver_available": True,
                },
                redacted_database_url="postgresql://user:***@example.test/app",
            ),
            checks_planned=3,
            checks_executed=3,
            checks_passed=3,
            checks_failed=0,
            error_message="",
        )
        with patch("postgres_staging_deployer.execute_schema_plan_with_database_url") as apply_execute:
            with patch("postgres_staging_deployer.run_safe_connection_probe") as probe:
                with patch("postgres_staging_deployer.execute_postdeploy_validation", return_value=execution_result) as validate:
                    exit_code = main(["--validate-postdeploy"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 0)
        validate.assert_called_once_with()
        apply_execute.assert_not_called()
        probe.assert_not_called()
        self.assertIn("PostgreSQL post-deployment validation execution.", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_checks_are_built_from_schema_artifact(self):
        checks = build_postdeploy_validation_checks(SCHEMA_SQL)
        categories = {check.category for check in checks}
        self.assertIn("table_exists", categories)
        self.assertIn("column_exists", categories)
        self.assertIn("index_exists", categories)
        self.assertIn("fk_exists", categories)
        self.assertTrue(all(is_select_only_sql(check.sql) for check in checks))


if __name__ == "__main__":
    unittest.main()
