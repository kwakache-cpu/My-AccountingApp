import hashlib
from unittest import mock

from test_support import ERPIsolatedTestCase


class DatabaseAuthReadPlaceholderConversionTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database.ensure_branch_licensing_schema_integrity(self.conn)

    def _insert_branch(self, branch_id, branch_access_key=None):
        branch_access_key = branch_access_key or f"{branch_id}-ACCESS"
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
                branch_id.replace("-", " ").title(),
                branch_id,
                "retail",
                branch_access_key,
            ),
        )
        self.conn.commit()
        return branch_id

    def _insert_user(
        self,
        *,
        full_name,
        role,
        branch_id=None,
        login_key=None,
        user_id=None,
        status="Active",
    ):
        login_key = login_key or f"{self.company_key}-{role}-{full_name.replace(' ', '_')}"
        user_id = user_id or hashlib.sha256(login_key.encode("utf-8")).hexdigest()
        self.conn.execute(
            """
            INSERT INTO users (
                company_key, branch_id, full_name, user_id, login_key, role, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, branch_id, full_name, user_id, login_key, role, status),
        )
        self.conn.commit()
        return user_id, login_key

    def test_fetch_company_user_by_user_id(self):
        branch_id = self._insert_branch("branch-a")
        user_id, login_key = self._insert_user(
            full_name="Lookup User", role="Clerk", branch_id=branch_id
        )
        row = self.database._fetch_company_user_by_user_id(self.conn, self.company_key, user_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["login_key"], login_key)
        self.assertEqual(row["full_name"], "Lookup User")

    def test_list_branch_users(self):
        branch_id = self._insert_branch("branch-a")
        self._insert_user(full_name="Alice Clerk", role="Clerk", branch_id=branch_id)
        self._insert_user(full_name="Bob Clerk", role="Cashier", branch_id=branch_id)
        users = self.database.list_branch_users(self.conn, self.company_key, branch_id)
        self.assertEqual(len(users), 2)
        names = {user["full_name"] for user in users}
        self.assertEqual(names, {"Alice Clerk", "Bob Clerk"})

    def test_fetch_branch_manager_candidates_excludes_privileged_roles(self):
        branch_id = self._insert_branch("branch-mgr")
        clerk_id, _ = self._insert_user(full_name="Clerk One", role="Clerk", branch_id=branch_id)
        self._insert_user(full_name="Admin User", role="Master Admin", branch_id=None)
        candidates = self.database.fetch_branch_manager_candidates(
            self.conn, self.company_key, branch_id
        )
        user_ids = {row["user_id"] for row in candidates}
        self.assertIn(clerk_id, user_ids)
        self.assertFalse(any(row["role"] == "Master Admin" for row in candidates))

    def test_fetch_branch_manager_select_options_includes_current_manager(self):
        branch_id = self._insert_branch("branch-opt")
        manager_id, _ = self._insert_user(
            full_name="Current Manager", role="Branch Manager", branch_id=branch_id
        )
        options = self.database.fetch_branch_manager_select_options(
            self.conn,
            self.company_key,
            branch_id,
            current_manager_user_id=manager_id,
        )
        self.assertTrue(any(row["user_id"] == manager_id for row in options))

    def test_list_company_staff_for_assignment(self):
        branch_id = self._insert_branch("branch-staff")
        self._insert_user(full_name="Staff One", role="Clerk", branch_id=branch_id)
        self._insert_user(full_name="Hidden Admin", role="System Admin", branch_id=None)
        staff = self.database.list_company_staff_for_assignment(self.conn, self.company_key)
        names = {row["full_name"] for row in staff}
        self.assertIn("Staff One", names)
        self.assertNotIn("Hidden Admin", names)

    def test_list_branch_users_postgres_placeholder_mock(self):
        branch_id = self._insert_branch("branch-pg")
        self._insert_user(full_name="Portable User", role="Clerk", branch_id=branch_id)
        captured = {}

        class _FakeCursor:
            def fetchall(self):
                return []

        class _FakeConn:
            def execute(self, statement, params=()):
                captured["statement"] = statement
                captured["params"] = params
                return _FakeCursor()

        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            self.database.list_branch_users(_FakeConn(), self.company_key, branch_id)
        self.assertIn("%s", captured["statement"])
        self.assertNotIn("?", captured["statement"].replace("COALESCE", ""))

    def test_fetch_branch_manager_candidates_uses_db_placeholders_for_in_clause(self):
        branch_id = self._insert_branch("branch-in")
        privileged = tuple(self.database.PRIVILEGED_COMPANY_USER_ROLES)
        with mock.patch.object(
            self.database, "execute_portable_query", wraps=self.database.execute_portable_query
        ) as portable:
            self.database.fetch_branch_manager_candidates(self.conn, self.company_key, branch_id)
        sql = str(portable.call_args[0][1])
        expected_in = self.database.db_placeholders(len(privileged))
        self.assertIn(f"NOT IN ({expected_in})", sql)

    def test_login_key_uniqueness_probes_stay_on_raw_execute(self):
        """Login/access-key conflict SELECTs are not converted (write-path guards)."""
        branch_id = self._insert_branch("branch-login-guard")
        with mock.patch.object(self.conn, "execute", wraps=self.conn.execute) as execute_spy:
            self.database._generate_unique_branch_user_login_key(
                self.conn, self.company_key, branch_id, "Clerk"
            )
        sql_calls = [str(call.args[0]) for call in execute_spy.call_args_list if call.args]
        self.assertTrue(any("login_key = ?" in sql for sql in sql_calls))
        self.assertTrue(any("branch_access_key = ?" in sql for sql in sql_calls))
