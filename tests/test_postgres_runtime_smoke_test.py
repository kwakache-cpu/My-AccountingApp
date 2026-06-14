import os
from types import SimpleNamespace
from unittest import TestCase, mock

import postgres_runtime_smoke_test as smoke


class FakeCursor:
    def __init__(self, queries):
        self.queries = queries
        self.last_query = ""

    def execute(self, query):
        self.last_query = query
        self.queries.append(query)

    def fetchone(self):
        normalized = " ".join(self.last_query.lower().split())
        if normalized == "select 1":
            return (1,)
        if "from \"companies\"" in normalized:
            return (8,)
        if "from \"users\"" in normalized:
            return (3,)
        if "from \"chart_of_accounts\"" in normalized:
            return (38,)
        if "from \"customers\"" in normalized:
            return (2,)
        if "from \"inventory\"" in normalized:
            return (3,)
        if "from \"journal_entries\"" in normalized:
            return (28,)
        if "select (select count(*) from companies)" in normalized:
            return (82,)
        return (1,)

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.queries = []
        self.closed = False

    def cursor(self):
        return FakeCursor(self.queries)

    def close(self):
        self.closed = True


class PostgresRuntimeSmokeTestTests(TestCase):
    def _env(self):
        return {
            "DB_BACKEND": "postgres",
            "ERP_ENABLE_POSTGRES_RUNTIME": "1",
            "ERP_ENVIRONMENT": "staging",
            "DATABASE_URL": "postgresql://user:secret@example.test:5432/postgres",
        }

    def _database_module(self):
        return SimpleNamespace(
            get_configured_db_backend=lambda: "postgres",
            get_startup_backend_diagnostics=lambda: {
                "active_backend": "postgres",
                "should_run_sqlite_startup": False,
            },
            startup_database=lambda: {
                "stage": "postgres_runtime_cutover_guard",
                "bootstrap_needed": False,
                "recovery_attempted": False,
            },
        )

    def test_guard_requires_staging_runtime_configuration(self):
        guard = smoke.validate_runtime_smoke_guard(environ={}, database_url="")
        self.assertTrue(guard.blocked)
        self.assertFalse(guard.guard_results["DB_BACKEND_is_postgres"])
        self.assertFalse(guard.guard_results["ERP_ENABLE_POSTGRES_RUNTIME_is_enabled"])
        self.assertFalse(guard.guard_results["ERP_ENVIRONMENT_is_staging"])
        self.assertFalse(guard.guard_results["DATABASE_URL_present"])

    def test_smoke_test_runs_select_only_checks_against_injected_connection(self):
        connection = FakeConnection()
        connector = mock.Mock(return_value=connection)
        result = smoke.execute_runtime_smoke_test(
            environ=self._env(),
            database_url=self._env()["DATABASE_URL"],
            connector=connector,
            database_module=self._database_module(),
        )
        self.assertEqual(result.status, smoke.RuntimeSmokeStatus.READY_FOR_STREAMLIT_SECRETS_CUTOVER)
        self.assertEqual(result.active_backend, "postgres")
        self.assertTrue(result.sqlite_bootstrap_blocked)
        self.assertEqual(result.checks_failed, 0)
        self.assertTrue(connection.closed)
        self.assertTrue(connection.queries)
        for query in connection.queries:
            self.assertTrue(query.lstrip().upper().startswith("SELECT"))
            self.assertNotRegex(query.upper(), r"\b(INSERT|UPDATE|DELETE)\b")
        rendered = smoke.render_runtime_smoke_report(result)
        self.assertNotIn("user:secret", rendered)
        self.assertNotIn(self._env()["DATABASE_URL"], rendered)

    def test_smoke_test_blocks_when_startup_would_run_sqlite_bootstrap(self):
        connection = FakeConnection()
        database_module = SimpleNamespace(
            get_configured_db_backend=lambda: "postgres",
            get_startup_backend_diagnostics=lambda: {
                "active_backend": "postgres",
                "should_run_sqlite_startup": True,
            },
            startup_database=lambda: {
                "stage": "unexpected_sqlite_startup",
                "bootstrap_needed": True,
                "recovery_attempted": False,
            },
        )
        result = smoke.execute_runtime_smoke_test(
            environ=self._env(),
            database_url=self._env()["DATABASE_URL"],
            connector=mock.Mock(return_value=connection),
            database_module=database_module,
        )
        self.assertEqual(result.status, smoke.RuntimeSmokeStatus.BLOCKED)
        self.assertFalse(result.sqlite_bootstrap_blocked)
        self.assertTrue(any("SQLite schema bootstrap" in blocker for blocker in result.blockers))


if __name__ == "__main__":
    import unittest

    unittest.main()
