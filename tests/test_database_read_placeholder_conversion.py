from unittest import mock

from test_support import ERPIsolatedTestCase


class DatabaseReadPlaceholderConversionTests(ERPIsolatedTestCase):
    def _seed_branch(self, branch_id="test-branch", branch_type="retail"):
        self.database.ensure_branch_licensing_schema_integrity(self.conn)
        self.conn.execute(
            """
            INSERT INTO branches (
                branch_id, company_key, branch_name, branch_code, branch_type,
                branch_access_key, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(branch_id) DO NOTHING
            """,
            (
                branch_id,
                self.company_key,
                "Test Branch",
                "test-branch",
                branch_type,
                f"{branch_id}-ACCESS",
            ),
        )
        self.conn.commit()
        return branch_id

    def test_fetch_company_name_sqlite_unchanged(self):
        self.assertEqual(
            self.database._fetch_company_name(self.conn, self.company_key),
            "Test Company",
        )

    def test_count_active_branches_with_exclude(self):
        branch_id = self._seed_branch()
        self.assertEqual(self.database.count_active_branches(self.conn, self.company_key), 1)
        self.assertEqual(
            self.database.count_active_branches(
                self.conn, self.company_key, exclude_branch_id=branch_id
            ),
            0,
        )

    def test_get_branch_enabled_modules_after_grant_seed(self):
        branch_id = self._seed_branch()
        self.database.ensure_branch_module_grants_for_branch(
            self.conn,
            self.company_key,
            branch_id,
            branch_type_key="retail",
            ensure_schema=False,
        )
        modules = self.database.get_branch_enabled_modules(
            self.conn, self.company_key, branch_id
        )
        self.assertIsInstance(modules, set)
        self.assertTrue(len(modules) > 0)

    def test_fetch_branch_type_default_module_keys(self):
        keys = self.database._fetch_branch_type_default_module_keys(self.conn, "retail")
        self.assertIsInstance(keys, set)
        self.assertTrue(len(keys) > 0)

    def test_get_company_branch_license_snapshot(self):
        snapshot = self.database.get_company_branch_license_snapshot(
            self.conn, self.company_key, ensure_schema=False
        )
        self.assertEqual(snapshot["company_key"], self.company_key)
        self.assertGreaterEqual(snapshot["max_branches"], 1)

    def test_get_audit_operations_summary_portable(self):
        self.database.log_audit_action(
            self.conn,
            company_key=self.company_key,
            user_role="Admin",
            action="Test audit read placeholder",
            module_name="Tests",
        )
        with mock.patch.object(
            self.database, "execute_portable_query", wraps=self.database.execute_portable_query
        ) as portable:
            summary = self.database.get_audit_operations_summary(
                conn=self.conn, company_key=self.company_key, limit=5
            )
        self.assertTrue(summary["ok"])
        self.assertTrue(portable.called)
        self.assertTrue(any("audit_logs" in str(call[0][1]) for call in portable.call_args_list))

    def test_get_company_data_returns_row(self):
        row = self.database.get_company_data(self.company_key)
        self.assertIsNotNone(row)
        key = row["key"] if hasattr(row, "keys") else row[0]
        self.assertEqual(key, self.company_key)

    def test_repair_branch_module_grants_uses_portable_select(self):
        self._seed_branch()
        with mock.patch.object(
            self.database, "execute_portable_query", wraps=self.database.execute_portable_query
        ) as portable:
            result = self.database.repair_branch_module_grants(
                self.conn, self.company_key, ensure_schema=False
            )
        self.assertTrue(result["ok"])
        select_calls = [
            call for call in portable.call_args_list if "SELECT branch_id, branch_type" in str(call[0][1])
        ]
        self.assertTrue(select_calls)

    def test_allocate_unique_branch_id_portable_on_postgres_mock(self):
        captured = []

        class _FakeCursor:
            def fetchone(self):
                return None

        class _FakeConn:
            def execute(self, statement, params=()):
                captured.append((statement, params))
                return _FakeCursor()

        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            branch_id = self.database._allocate_unique_branch_id(_FakeConn(), "new-branch")
        self.assertEqual(branch_id, "new-branch")
        self.assertIn("%s", captured[0][0])

    def test_db_placeholders_in_list_sqlite_and_postgres(self):
        roles = ("Admin", "Owner", "Branch Manager")
        sqlite_in = self.database.db_placeholders(len(roles), backend="sqlite")
        postgres_in = self.database.db_placeholders(len(roles), backend="postgres")
        self.assertEqual(sqlite_in, "?, ?, ?")
        self.assertEqual(postgres_in, "%s, %s, %s")
        sqlite_sql = f"SELECT 1 WHERE role NOT IN ({sqlite_in})"
        self.assertIn("?, ?, ?", sqlite_sql)

    def test_branch_licensing_table_exists_delegates_to_db_table_exists(self):
        with mock.patch.object(self.database, "db_table_exists", return_value=True) as exists:
            self.assertTrue(self.database._branch_licensing_table_exists(self.conn, "branches"))
        exists.assert_called_once_with(self.conn, "branches")
