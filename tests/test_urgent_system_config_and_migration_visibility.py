import inspect
import os
from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase


class UrgentCompanySetupDdlTests(TestCase):
    def test_show_company_setup_does_not_run_alter_table_during_render(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        setup_block = content.split("def show_company_setup(", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("ALTER TABLE", setup_block)
        self.assertNotIn("ADD COLUMN", setup_block)
        self.assertNotIn("CREATE INDEX", setup_block)
        self.assertNotIn("CREATE TABLE", setup_block)
        self.assertNotIn("_render_migration_cleanup_review", setup_block)

    def test_users_user_id_migration_is_idempotent(self):
        database = __import__("database")
        conn = mock.MagicMock()
        with mock.patch.object(database, "db_table_exists", return_value=True):
            with mock.patch.object(database, "_get_existing_columns", return_value={"user_id", "login_key"}):
                with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                    first = database.ensure_users_user_id_schema_integrity(conn)
                    second = database.ensure_users_user_id_schema_integrity(conn)
        self.assertTrue(first["user_id_column_present"])
        self.assertFalse(first["user_id_column_added"])
        self.assertTrue(second["user_id_column_present"])
        conn.execute.assert_not_called()

    def test_users_user_id_migration_adds_column_once_on_postgres(self):
        database = __import__("database")
        conn = mock.MagicMock()
        columns = {"login_key"}

        def _columns(_conn, _table):
            return set(columns)

        def _add_column(*args, **kwargs):
            columns.add("user_id")

        with mock.patch.object(database, "db_table_exists", return_value=True):
            with mock.patch.object(database, "_get_existing_columns", side_effect=_columns):
                with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                    with mock.patch.object(database, "execute_portable_write", side_effect=_add_column) as write_mock:
                        result = database.ensure_users_user_id_schema_integrity(conn)
        self.assertTrue(result["user_id_column_added"])
        alter_calls = [
            call
            for call in write_mock.call_args_list
            if "ADD COLUMN" in str(call.args[1] if len(call.args) > 1 else "")
        ]
        self.assertEqual(len(alter_calls), 1)
        database.ensure_users_user_id_schema_integrity(conn)
        self.assertEqual(
            len(
                [
                    call
                    for call in write_mock.call_args_list
                    if "ADD COLUMN" in str(call.args[1] if len(call.args) > 1 else "")
                ]
            ),
            1,
        )

    def test_duplicate_users_user_id_column_does_not_crash_postgres_path(self):
        database = __import__("database")
        conn = mock.MagicMock()
        with mock.patch.object(database, "db_table_exists", return_value=True):
            with mock.patch.object(database, "_get_existing_columns", return_value={"user_id"}):
                with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                    with mock.patch.object(database, "execute_portable_write") as write_mock:
                        write_mock.side_effect = [
                            None,
                            None,
                        ]
                        database.ensure_users_user_id_schema_integrity(conn)
                        database.ensure_users_user_id_schema_integrity(conn)
        alter_calls = [
            call
            for call in write_mock.call_args_list
            if "ADD COLUMN" in str(call.args[1] if len(call.args) > 1 else "")
        ]
        self.assertEqual(len(alter_calls), 0)


class UrgentMigrationCleanupVisibilityTests(TestCase):
    def setUp(self):
        self.modules = __import__("modules")
        self.cleanup = __import__("migration_cleanup")

    def test_migration_cleanup_hidden_from_client_roles(self):
        for role in ("Demo", "Staff", "Cashier", "Accountant", "Owner", "Bookkeeper", "Sub-Admin"):
            self.assertFalse(self.modules.can_render_migration_cleanup_diagnostics(role, "dashboard"))
            self.assertFalse(self.modules.can_render_migration_cleanup_diagnostics(role, "system_configuration"))

    def test_migration_cleanup_visible_on_admin_diagnostic_surfaces(self):
        for role in ("Dev", "Master Admin", "System Admin"):
            self.assertTrue(self.modules.can_render_migration_cleanup_diagnostics(role, "dev_gatekeeper"))
            self.assertTrue(self.modules.can_render_migration_cleanup_diagnostics(role, "system_health"))
            self.assertTrue(self.modules.can_render_migration_cleanup_diagnostics(role, "system_administration"))

    def test_migration_cleanup_not_on_financial_reports_surface(self):
        self.assertFalse(self.modules.can_render_migration_cleanup_diagnostics("Dev", "financial_reports"))
        self.assertFalse(self.modules.can_render_migration_cleanup_diagnostics("Master Admin", "dashboard"))

    def test_admin_diagnostics_suite_includes_migration_cleanup_gate(self):
        source = inspect.getsource(self.modules.render_runtime_admin_diagnostics_suite)
        self.assertIn("can_render_migration_cleanup_diagnostics", source)
        self.assertIn("_render_migration_cleanup_diagnostics_lazy", source)

    def test_cleanup_role_gate_includes_system_admin(self):
        self.assertTrue(self.cleanup.can_access_migration_cleanup("System Admin"))
        self.assertFalse(self.cleanup.can_access_migration_cleanup("Staff"))


class UrgentCompanySetupFunctionalTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = __import__("modules")
        self.database = __import__("database")

    def test_users_user_id_schema_integrity_on_sqlite(self):
        result = self.database.ensure_users_user_id_schema_integrity(self.conn)
        self.assertTrue(result["user_id_column_present"])
        columns = self.database._get_existing_columns(self.conn, "users")
        self.assertIn("user_id", columns)
        repeat = self.database.ensure_users_user_id_schema_integrity(self.conn)
        self.assertFalse(repeat["user_id_column_added"])

    def test_role_user_setup_source_references_user_id_without_ui_ddl(self):
        setup_block = inspect.getsource(self.modules.show_company_setup)
        self.assertIn("user_id", setup_block)
        self.assertNotIn("ALTER TABLE", setup_block)
