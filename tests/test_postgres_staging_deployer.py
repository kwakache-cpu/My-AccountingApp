import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from postgres_staging_deployer import (
    APPLY_NOT_IMPLEMENTED_MESSAGE,
    main,
    redact_database_url,
    validate_database_url,
    validate_required_artifacts,
)


class PostgresStagingDeployerTests(unittest.TestCase):
    def test_dry_run_works(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict("os.environ", {}, clear=True):
            exit_code = main(["--dry-run"], output_stream=stdout, error_stream=stderr)
        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("PostgreSQL staging deployment skeleton dry-run.", output)
        self.assertIn("Planned PostgreSQL deployment phases", output)
        self.assertIn("No SQL executed. No database connection attempted.", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_apply_fails_immediately(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = main(["--apply"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 1)
        self.assertIn(APPLY_NOT_IMPLEMENTED_MESSAGE, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_missing_files_detected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.sql"
            result = validate_required_artifacts((missing,))
        self.assertFalse(result.ok)
        self.assertEqual(len(result.missing), 1)

    def test_database_url_redacted(self):
        url = "postgresql://user:super-secret@example.com:5432/appdb?sslmode=require"
        redacted = redact_database_url(url)
        self.assertIn("user:***@example.com:5432", redacted)
        self.assertNotIn("super-secret", redacted)
        diagnostics = validate_database_url(url)
        self.assertTrue(diagnostics.configured)
        self.assertNotIn("super-secret", diagnostics.redacted_url)

    def test_no_db_connection_attempted(self):
        source = Path("postgres_staging_deployer.py").read_text(encoding="utf-8")
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
