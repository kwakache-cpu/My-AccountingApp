from unittest.mock import patch
from pathlib import Path
import unittest

from postgres_connection_adapter import (
    CONNECTION_NOT_IMPLEMENTED_MESSAGE,
    PostgresAdapterStatus,
    PostgresConnectionAdapter,
    PostgresConnectionConfig,
    build_connection_diagnostics,
    detect_postgres_driver,
    parse_database_url_safely,
    redact_database_url,
    validate_connection_allowed,
)


class PostgresConnectionAdapterTests(unittest.TestCase):
    def test_url_redaction_hides_password(self):
        url = "postgresql://user:secret-password@example.com:5432/accounting?sslmode=require"
        redacted = redact_database_url(url)
        self.assertIn("user:***@example.com:5432", redacted)
        self.assertNotIn("secret-password", redacted)
        self.assertNotIn(":secret-password@", redacted)

    def test_missing_url_blocks(self):
        diagnostics = build_connection_diagnostics(PostgresConnectionConfig(database_url=""))
        self.assertTrue(diagnostics.blocked)
        self.assertEqual(diagnostics.status, PostgresAdapterStatus.MISSING_DATABASE_URL)
        self.assertFalse(diagnostics.database_url_configured)
        self.assertIn("DATABASE_URL is not configured", diagnostics.message)

    def test_diagnostics_do_not_expose_secrets(self):
        url = "postgres://user:top-secret@db.example.test/appdb"
        diagnostics = build_connection_diagnostics(PostgresConnectionConfig(database_url=url))
        self.assertTrue(diagnostics.database_url_configured)
        self.assertNotIn("top-secret", diagnostics.database_url_redacted)
        self.assertNotIn("top-secret", diagnostics.message)
        self.assertTrue(diagnostics.blocked)

    def test_parse_database_url_safely(self):
        parsed = parse_database_url_safely("postgresql://user:pw@localhost:5432/appdb")
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["scheme"], "postgresql")
        self.assertEqual(parsed["hostname"], "localhost")
        self.assertEqual(parsed["database"], "appdb")
        self.assertNotIn("pw", str(parsed["redacted_url"]))

    def test_driver_detection_does_not_connect(self):
        with patch("postgres_connection_adapter.find_spec", return_value=object()) as find_spec:
            driver_name, available = detect_postgres_driver(("psycopg",))
        self.assertEqual(driver_name, "psycopg")
        self.assertTrue(available)
        find_spec.assert_called_once_with("psycopg")

    def test_connect_is_blocked(self):
        adapter = PostgresConnectionAdapter(PostgresConnectionConfig(database_url="postgresql://user:pw@localhost/app"))
        with self.assertRaises(NotImplementedError) as raised:
            adapter.connect()
        self.assertEqual(str(raised.exception), CONNECTION_NOT_IMPLEMENTED_MESSAGE)
        diagnostics = validate_connection_allowed(adapter.config)
        self.assertTrue(diagnostics.blocked)

    def test_source_scan_confirms_no_execution_or_connection_calls(self):
        source = Path("postgres_connection_adapter.py").read_text(encoding="utf-8")
        forbidden_terms = [
            "conn.execute",
            "cursor.execute",
            "psycopg.connect",
            "psycopg2.connect",
            "supabase",
            "create_client",
            "create_engine",
            ".execute(",
            ".cursor(",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
