from unittest import mock

from test_support import ERPIsolatedTestCase


class LowRiskDmlPortableWriteConversionTests(ERPIsolatedTestCase):
    def test_log_audit_action_still_inserts_on_sqlite(self):
        before = self.conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        self.database.log_audit_action(
            self.conn,
            company_key=self.company_key,
            user_role="Admin",
            action="Low-risk portable write test",
            module_name="Tests",
            details="details",
            branch_id=None,
        )
        after = self.conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        self.assertEqual(int(after), int(before) + 1)

    def test_log_audit_action_uses_execute_portable_write(self):
        with mock.patch.object(
            self.database, "execute_portable_write", wraps=self.database.execute_portable_write
        ) as portable:
            self.database.log_audit_action(
                self.conn,
                company_key=self.company_key,
                user_role="Admin",
                action="Portable write spy",
                module_name="Tests",
            )
        self.assertTrue(any("INSERT INTO audit_logs" in str(call.args[1]) for call in portable.call_args_list))

    def test_execute_portable_write_converts_database_identity_update_on_postgres_mock(self):
        captured = {}

        class _FakeConn:
            def execute(self, statement, params=()):
                captured["statement"] = statement
                captured["params"] = params
                return object()

        self.database.execute_portable_write(
            _FakeConn(),
            "UPDATE database_identity SET environment_label = ? WHERE instance_id = ?",
            ("development", "inst"),
            backend="postgres",
        )
        self.assertIn("%s", captured["statement"])
        self.assertEqual(captured["params"], ("development", "inst"))

    def test_record_schema_version_converts_on_postgres_mock(self):
        captured = {}

        class _FakeConn:
            def execute(self, statement, params=()):
                captured["statement"] = statement
                captured["params"] = params
                return object()

        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            self.database._record_schema_version(_FakeConn(), 123, "desc")
        self.assertIn("%s", captured["statement"])
        self.assertEqual(captured["params"], (123, "desc"))

    def test_log_migration_event_converts_on_postgres_mock(self):
        captured = {}

        class _FakeConn:
            def execute(self, statement, params=()):
                captured["statement"] = statement
                captured["params"] = params
                return object()

        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            self.database._log_migration_event(
                _FakeConn(),
                version=1,
                description="d",
                status="success",
                backup_path="b",
                before_counts={"companies": 0},
                after_counts={"companies": 0},
                details="x",
            )
        self.assertIn("%s", captured["statement"])
        self.assertEqual(captured["params"][0:3], (1, "d", "success"))

