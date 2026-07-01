import os
from types import SimpleNamespace
from unittest import TestCase, mock

from test_support import load_isolated_modules


class Lv001eBackendActivationTests(TestCase):
    def setUp(self):
        self._original_env = {
            key: os.environ.get(key)
            for key in (
                "DB_BACKEND",
                "DATABASE_URL",
                "ERP_ENABLE_POSTGRES_RUNTIME",
                "ERP_ENVIRONMENT",
                "ERP_POSTGRES_PRODUCTION_APPROVED",
                "EKA_DATA_DIR",
            )
        }

    def tearDown(self):
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _load_database(self):
        data_dir = os.path.join(os.getcwd(), ".test-tmp", "lv001e_backend_activation")
        os.makedirs(data_dir, exist_ok=True)
        database, _engine = load_isolated_modules(data_dir)
        return database

    def _mock_secrets(self, database, secrets_mapping):
        class FakeSecrets:
            def __init__(self, mapping):
                self._mapping = mapping

            def __contains__(self, key):
                return key in self._mapping

            def __getitem__(self, key):
                return self._mapping[key]

            def get(self, key, default=None):
                return self._mapping.get(key, default)

            def keys(self):
                return self._mapping.keys()

        fake_st = SimpleNamespace(secrets=FakeSecrets(secrets_mapping))
        return mock.patch.object(database, "st", fake_st)

    def test_os_env_enables_postgres_active_backend(self):
        database = self._load_database()
        secret_url = "postgresql://user:secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "staging",
            },
            clear=False,
        ):
            self.assertEqual(database.get_active_db_backend(), "postgres")
            diagnostics = database.get_backend_activation_diagnostics()
        self.assertTrue(diagnostics["postgres_runtime_enabled"])
        self.assertTrue(diagnostics["database_url_present"])
        self.assertEqual(diagnostics["active_backend"], "postgres")
        self.assertEqual(diagnostics["config_resolution_channel"], "os.environ")
        self.assertEqual(diagnostics["config_resolution_sources"]["DB_BACKEND"], "os.environ")

    def test_nested_streamlit_secret_enables_postgres_runtime(self):
        database = self._load_database()
        secret_url = "postgresql://user:secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in ("DB_BACKEND", "DATABASE_URL", "ERP_ENABLE_POSTGRES_RUNTIME", "ERP_ENVIRONMENT"):
                os.environ.pop(key, None)
            with self._mock_secrets(
                database,
                {
                    "database": {
                        "DB_BACKEND": "postgres",
                        "DATABASE_URL": secret_url,
                        "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                        "ERP_ENVIRONMENT": "staging",
                    }
                },
            ):
                self.assertEqual(database.get_configured_db_backend(), "postgres")
                self.assertTrue(database.is_postgres_runtime_enabled())
                self.assertEqual(database.get_active_db_backend(), "postgres")
                diagnostics = database.get_backend_activation_diagnostics()
        self.assertEqual(diagnostics["config_resolution_channel"], "st.secrets")
        self.assertEqual(diagnostics["config_resolution_sources"]["DATABASE_URL"], "st.secrets.database")

    def test_os_env_takes_priority_over_streamlit_secrets(self):
        database = self._load_database()
        secret_url = "postgresql://user:secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "staging",
            },
            clear=False,
        ), self._mock_secrets(
            database,
            {
                "DB_BACKEND": "sqlite",
                "ERP_ENABLE_POSTGRES_RUNTIME": "0",
            },
        ):
            self.assertEqual(database.get_active_db_backend(), "postgres")
            diagnostics = database.get_backend_activation_diagnostics()
        self.assertEqual(diagnostics["config_resolution_sources"]["DB_BACKEND"], "os.environ")
        self.assertEqual(diagnostics["config_resolution_sources"]["ERP_ENABLE_POSTGRES_RUNTIME"], "os.environ")

    def test_runtime_flag_off_keeps_sqlite_active_backend(self):
        database = self._load_database()
        secret_url = "postgresql://user:secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "0",
            },
            clear=False,
        ):
            diagnostics = database.get_backend_activation_diagnostics()
        self.assertEqual(diagnostics["configured_backend"], "postgres")
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertFalse(diagnostics["postgres_runtime_enabled"])
        self.assertIn("ERP_ENABLE_POSTGRES_RUNTIME", diagnostics["reason_postgres_not_activated"])

    def test_backend_activation_diagnostics_include_required_fields(self):
        database = self._load_database()
        with mock.patch.dict(os.environ, {"DB_BACKEND": "sqlite"}, clear=False):
            diagnostics = database.get_backend_activation_diagnostics()
        for marker in [
            "os_db_backend",
            "os_erp_enable_postgres_runtime",
            "os_erp_environment",
            "database_url_present",
            "configured_backend",
            "active_backend",
            "reason_postgres_not_activated",
            "cutover_guard_blocked",
            "reading_os_env",
            "reading_streamlit_secrets",
            "config_resolution_channel",
        ]:
            self.assertIn(marker, diagnostics, f"missing backend activation marker: {marker}")

    def test_cutover_guard_blocked_when_evidence_missing(self):
        database = self._load_database()
        secret_url = "postgresql://user:secret@example.supabase.co:6543/postgres?sslmode=require"
        missing_report = os.path.join(os.getcwd(), ".test-tmp", "lv001e_backend_activation", "missing_cutover_report.md")
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "staging",
            },
            clear=False,
        ), mock.patch.dict(
            database.POSTGRES_CUTOVER_REPORTS,
            {"schema_deployment": (missing_report, ("Status: PASSED",))},
            clear=True,
        ):
            diagnostics = database.get_backend_activation_diagnostics()
            message = database.get_postgres_activation_admin_message()
        self.assertTrue(diagnostics["cutover_guard_blocked"])
        self.assertFalse(diagnostics["runtime_cutover_guard_ok"])
        self.assertIsNotNone(message)
        self.assertIn("cutover guard blocked", message.lower())

    def test_admin_message_lists_missing_production_approval(self):
        database = self._load_database()
        secret_url = "postgresql://user:secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "production",
                "ERP_POSTGRES_PRODUCTION_APPROVED": "0",
            },
            clear=False,
        ):
            message = database.get_postgres_activation_admin_message()
        self.assertIsNotNone(message)
        self.assertIn("ERP_POSTGRES_PRODUCTION_APPROVED", message)
