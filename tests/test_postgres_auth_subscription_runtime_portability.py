from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase


class _FakeCursor:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        if self._row is not None:
            return self._row
        return self._rows[0] if self._rows else None


class _FakePostgresConn:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.statements = []
        self.params = []
        self.closed = False

    def execute(self, statement, params=()):
        self.statements.append(statement)
        self.params.append(params)
        return _FakeCursor(rows=self.rows, row=self.row)

    def close(self):
        self.closed = True


class PostgresAuthSubscriptionRuntimePortabilityTests(ERPIsolatedTestCase):
    def test_get_subscription_plan_settings_works_with_injected_postgres_like_connection(self):
        fake = _FakePostgresConn(
            rows=[
                (
                    "Basic",
                    100.0,
                    "GHS",
                    1,
                    0,
                    '{"modules": ["accounting"]}',
                    "tester",
                    "2026-06-16T00:00:00",
                )
            ]
        )
        with mock.patch.object(self.database, "is_sqlite_backend", return_value=False):
            settings = self.database.get_subscription_plan_settings(conn=fake)
        self.assertEqual(settings["Basic"]["configured_amount"], 100.0)
        self.assertFalse(fake.closed)
        self.assertTrue(any("FROM subscription_plan_settings" in sql for sql in fake.statements))

    def test_get_subscription_plan_setting_converts_placeholder_for_postgres(self):
        fake = _FakePostgresConn(
            row=(
                "Growth",
                250.0,
                "GHS",
                1,
                0,
                None,
                "tester",
                "2026-06-16T00:00:00",
            )
        )
        with mock.patch.object(self.database, "is_sqlite_backend", return_value=False), mock.patch.object(
            self.database, "get_active_db_backend", return_value="postgres"
        ):
            setting = self.database.get_subscription_plan_setting("Growth", conn=fake)
        self.assertEqual(setting["plan_name"], "Growth")
        self.assertIn("WHERE plan_name = %s", fake.statements[-1])
        self.assertNotIn("?", fake.statements[-1])
        self.assertEqual(fake.params[-1], ("Growth",))

    def test_subscription_plan_default_postgres_runtime_does_not_open_sqlite(self):
        fake = _FakePostgresConn(rows=[])
        with mock.patch.object(self.database, "get_connection", return_value=fake), mock.patch.object(
            self.database, "is_sqlite_backend", return_value=False
        ), mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            self.database, "_open_sqlite_connection", side_effect=AssertionError("sqlite should not open")
        ):
            settings = self.database.get_subscription_plan_settings()
        self.assertEqual(settings, {})
        self.assertTrue(fake.closed)

    def test_sqlite_subscription_plan_read_still_works_with_injected_sqlite_connection(self):
        self.database.upsert_subscription_plan_setting(
            self.conn,
            plan_name="SQLite Plan",
            configured_amount=42.0,
            currency="GHS",
            duration_months=1,
            updated_by="sqlite-test",
        )
        self.conn.commit()
        settings = self.database.get_subscription_plan_settings(conn=self.conn)
        self.assertEqual(settings["SQLite Plan"]["configured_amount"], 42.0)

    def test_auth_access_key_path_uses_portable_postgres_placeholders_without_sqlite(self):
        import app

        fake = _FakePostgresConn(row=("COMPANY-1", "Company One", "Active"))
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            self.database, "_open_sqlite_connection", side_effect=AssertionError("sqlite should not open")
        ):
            result = app.authenticate_access_key_read_path(fake, "COMPANY-1")
        self.assertTrue(result["matched"])
        self.assertEqual(result["user"]["role"], "Master Admin")
        self.assertTrue(fake.statements)
        self.assertIn("WHERE key = %s", fake.statements[0])
        self.assertNotIn("?", fake.statements[0])
        self.assertEqual(fake.params[0], ("COMPANY-1",))


if __name__ == "__main__":
    import unittest

    unittest.main()
