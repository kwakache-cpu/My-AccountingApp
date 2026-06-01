import os
from unittest import mock

from test_support import ERPIsolatedTestCase


class DatabaseBackendFoundationTests(ERPIsolatedTestCase):
    def test_backend_detection_defaults_to_sqlite(self):
        with mock.patch.dict(os.environ, {"DB_BACKEND": ""}, clear=False):
            self.assertEqual(self.database.get_db_backend(), "sqlite")
            self.assertEqual(self.database.get_configured_db_backend(), "sqlite")
            self.assertEqual(self.database.get_active_db_backend(), "sqlite")
            self.assertTrue(self.database.is_sqlite())
            self.assertTrue(self.database.is_sqlite_backend())
            self.assertFalse(self.database.is_postgres())
            self.assertFalse(self.database.is_postgres_backend())

    def test_postgres_config_detected_without_secret_exposure(self):
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(os.environ, {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url}, clear=False):
            diagnostics = self.database.get_db_diagnostics()
        self.assertEqual(diagnostics["configured_backend"], "postgres")
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertTrue(diagnostics["database_url_configured"])
        self.assertNotIn("super-secret", diagnostics["database_url_label"])
        self.assertIn("***", diagnostics["database_url_label"])

    def test_postgres_disabled_unless_runtime_flag_and_database_url(self):
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(
            os.environ,
            {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url, "ERP_ENABLE_POSTGRES_RUNTIME": "0"},
            clear=False,
        ):
            validation = self.database.validate_postgres_runtime_enabled()
            self.assertFalse(validation["ok"])
            self.assertEqual(self.database.get_active_db_backend(), "sqlite")
            self.assertTrue(validation["postgres_blocked"])
            self.assertIn("ERP_ENABLE_POSTGRES_RUNTIME is not enabled.", validation["reasons"])

    def test_postgres_requires_database_url(self):
        with mock.patch.dict(
            os.environ,
            {"DB_BACKEND": "postgres", "DATABASE_URL": "", "ERP_ENABLE_POSTGRES_RUNTIME": "1"},
            clear=False,
        ):
            validation = self.database.validate_postgres_runtime_enabled()
            self.assertFalse(validation["ok"])
            self.assertEqual(self.database.get_active_db_backend(), "sqlite")
            self.assertIn("DATABASE_URL is not configured.", validation["reasons"])

    def test_sql_placeholder_helpers_are_backend_aware(self):
        self.assertEqual(self.database.db_placeholder(backend="sqlite"), "?")
        self.assertEqual(self.database.db_param_placeholder(1, backend="sqlite"), "?")
        self.assertEqual(self.database.db_placeholders(3, backend="sqlite"), "?, ?, ?")
        self.assertEqual(self.database.db_placeholder(backend="postgres"), "%s")
        self.assertEqual(self.database.db_param_placeholder(2, backend="postgres"), "%s")
        self.assertEqual(self.database.db_placeholders(3, backend="postgres"), "%s, %s, %s")

    def test_insert_returning_id_sql_patterns(self):
        sqlite_sql = self.database.insert_returning_id_sql(
            "journal_entries",
            ["company_key", "description"],
            backend="sqlite",
        )
        postgres_sql = self.database.insert_returning_id_sql(
            "journal_entries",
            ["company_key", "description"],
            backend="postgres",
        )
        self.assertEqual(
            sqlite_sql,
            "INSERT INTO journal_entries (company_key, description) VALUES (?, ?)",
        )
        self.assertEqual(
            postgres_sql,
            "INSERT INTO journal_entries (company_key, description) VALUES (%s, %s) RETURNING id",
        )

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

    def test_postgres_foundation_diagnostics_never_expose_full_database_url(self):
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(os.environ, {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url}, clear=False):
            diagnostics = self.database.get_postgres_foundation_diagnostics()
        self.assertNotIn("super-secret", str(diagnostics))
        self.assertIn("***", diagnostics["database_url_label"])

    def test_test_postgres_connection_handles_missing_driver_safely(self):
        with mock.patch.object(
            self.database,
            "_get_postgres_driver_info",
            return_value={
                "available": False,
                "driver": None,
                "message": "Install psycopg2-binary (recommended) or psycopg to enable PostgreSQL connections.",
            },
        ):
            result = self.database.test_postgres_connection(
                database_url="postgresql://user:secret@example.supabase.co:6543/postgres"
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["backend"], "postgres")
        self.assertIn("psycopg2-binary", result["message"])
        self.assertNotIn("secret", str(result))

    def test_execute_db_write_transaction_uses_sqlite_path_by_default(self):
        calls = []

        def _callback(conn):
            calls.append(type(conn).__name__)
            conn.execute("SELECT 1")
            return {"ok": True}

        result = self.database.execute_db_write_transaction(_callback, operation_name="foundation_sqlite_write")
        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 1)

    def test_migration_export_plan_is_report_only(self):
        plan = self.database.get_data_migration_export_plan(conn=self.conn)
        self.assertEqual(plan["mode"], "report_only")
        self.assertIn("companies", plan["export_order"])
        self.assertTrue(any(row["table"] == "companies" for row in plan["tables"]))

    def test_existing_sqlite_startup_still_works(self):
        result = self.database.startup_database()
        self.assertTrue(result["ok"])
        self.assertEqual(result["startup_mode"], "local_production_ready")
