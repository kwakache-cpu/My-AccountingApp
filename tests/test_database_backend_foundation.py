import os
from unittest import mock

from test_support import ERPIsolatedTestCase


class DatabaseBackendFoundationTests(ERPIsolatedTestCase):
    def test_backend_detection_defaults_to_sqlite(self):
        with mock.patch.dict(os.environ, {"DB_BACKEND": ""}, clear=False):
            self.assertEqual(self.database.get_db_backend(), "sqlite")
            self.assertEqual(self.database.get_active_db_backend(), "sqlite")
            self.assertTrue(self.database.is_sqlite())
            self.assertFalse(self.database.is_postgres())

    def test_postgres_config_detected_without_secret_exposure(self):
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(os.environ, {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url}, clear=False):
            diagnostics = self.database.get_db_diagnostics()
        self.assertEqual(diagnostics["configured_backend"], "postgres")
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertTrue(diagnostics["database_url_configured"])
        self.assertNotIn("super-secret", diagnostics["database_url_label"])
        self.assertIn("***", diagnostics["database_url_label"])

    def test_sql_placeholder_helpers_are_backend_aware(self):
        self.assertEqual(self.database.db_param_placeholder(1, backend="sqlite"), "?")
        self.assertEqual(self.database.db_placeholders(3, backend="sqlite"), "?, ?, ?")
        self.assertEqual(self.database.db_param_placeholder(2, backend="postgres"), "$2")
        self.assertEqual(self.database.db_placeholders(3, backend="postgres"), "$1, $2, $3")

    def test_insert_ignore_sql_helper_is_backend_aware(self):
        sqlite_sql = self.database.db_insert_ignore_sql("users", ["company_key", "login_key"], backend="sqlite")
        postgres_sql = self.database.db_insert_ignore_sql(
            "users",
            ["company_key", "login_key"],
            conflict_columns=["company_key", "login_key"],
            backend="postgres",
        )
        self.assertIn("INSERT OR IGNORE", sqlite_sql)
        self.assertIn("ON CONFLICT (company_key, login_key) DO NOTHING", postgres_sql)

    def test_table_and_column_existence_helpers_work_for_sqlite(self):
        self.assertTrue(self.database.db_table_exists(self.conn, "companies"))
        self.assertTrue(self.database.db_column_exists(self.conn, "companies", "key"))
        self.assertFalse(self.database.db_column_exists(self.conn, "companies", "not_a_real_column"))

    def test_postgres_readiness_diagnostics_report_sqlite_warning(self):
        diagnostics = self.database.get_postgres_readiness_diagnostics(conn=self.conn)
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertTrue(diagnostics["sqlite_concurrency_warning"])
        self.assertTrue(diagnostics["switch_blocked"])
        self.assertGreaterEqual(diagnostics["readiness_score"], 0)

    def test_migration_export_plan_is_report_only(self):
        plan = self.database.get_data_migration_export_plan(conn=self.conn)
        self.assertEqual(plan["mode"], "report_only")
        self.assertIn("companies", plan["export_order"])
        self.assertTrue(any(row["table"] == "companies" for row in plan["tables"]))

    def test_existing_sqlite_startup_still_works(self):
        result = self.database.startup_database()
        self.assertTrue(result["ok"])
        self.assertEqual(result["startup_mode"], "local_production_ready")
