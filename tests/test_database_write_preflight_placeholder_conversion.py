import hashlib
from unittest import mock

from test_support import ERPIsolatedTestCase


class DatabaseWritePreflightPlaceholderConversionTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database.ensure_branch_licensing_schema_integrity(self.conn)

    def _insert_branch(self, branch_id, branch_access_key=None, branch_name=None):
        branch_access_key = branch_access_key or f"{branch_id}-ACCESS"
        branch_name = branch_name or branch_id.replace("-", " ").title()
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
                branch_name,
                branch_id,
                "retail",
                branch_access_key,
            ),
        )
        self.conn.commit()
        return branch_id

    def _insert_user(self, *, full_name, role, branch_id=None, login_key=None, user_id=None):
        login_key = login_key or f"{self.company_key}-{role}-{full_name.replace(' ', '_')}"
        user_id = user_id or hashlib.sha256(login_key.encode("utf-8")).hexdigest()
        self.conn.execute(
            """
            INSERT INTO users (
                company_key, branch_id, full_name, user_id, login_key, role, status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'Active')
            """,
            (self.company_key, branch_id, full_name, user_id, login_key, role),
        )
        self.conn.commit()
        return user_id, login_key

    def test_create_branch_scoped_user_blocks_duplicate_login_key(self):
        branch_id = self._insert_branch("preflight-branch")
        existing_key = f"{self.company_key}-dup-login"
        self._insert_user(full_name="Existing", role="Clerk", branch_id=branch_id, login_key=existing_key)
        result = self.database.create_branch_scoped_user(
            self.conn,
            self.company_key,
            branch_id,
            full_name="New User",
            role="Cashier",
            login_key=existing_key,
        )
        self.assertFalse(result["ok"])
        self.assertIn("login key", result["reason"].lower())

    def test_create_company_branch_blocks_duplicate_access_key(self):
        self.conn.execute(
            "UPDATE companies SET max_branches = 5, number_of_branches = 5 WHERE key = ?",
            (self.company_key,),
        )
        self.conn.commit()
        taken_key = f"{self.company_key}-taken-access"
        self._insert_branch("branch-taken", branch_access_key=taken_key)
        result = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Another Branch",
            branch_type_key="retail",
            branch_access_key=taken_key,
            ensure_schema=False,
        )
        self.assertFalse(result["ok"])
        self.assertIn("access key", result["reason"].lower())

    def test_create_company_branch_blocks_duplicate_branch_name(self):
        self._insert_branch("branch-dup-name", branch_name="Same Name Shop")
        result = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Same Name Shop",
            branch_type_key="retail",
            ensure_schema=False,
        )
        self.assertFalse(result["ok"])
        self.assertIn("already exists", result["reason"])

    def test_update_company_branch_blocks_duplicate_access_key(self):
        branch_a = self._insert_branch("branch-a", branch_access_key="KEY-A")
        branch_b = self._insert_branch("branch-b", branch_access_key="KEY-B")
        result = self.database.update_company_branch(
            self.conn,
            self.company_key,
            branch_b,
            branch_access_key="KEY-A",
        )
        self.assertFalse(result["ok"])
        self.assertIn("access key", result["reason"].lower())
        self.assertNotEqual(branch_a, branch_b)

    def test_assign_branch_manager_requires_existing_user(self):
        branch_id = self._insert_branch("branch-mgr-check")
        result = self.database.assign_branch_manager(
            self.conn,
            self.company_key,
            branch_id,
            "nonexistent-user-id",
        )
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["reason"].lower())

    def test_assign_branch_manager_succeeds_for_valid_user(self):
        branch_id = self._insert_branch("branch-mgr-ok")
        user_id, _ = self._insert_user(full_name="Manager Pick", role="Clerk", branch_id=branch_id)
        result = self.database.assign_branch_manager(
            self.conn,
            self.company_key,
            branch_id,
            user_id,
        )
        self.assertTrue(result["ok"])

    def test_login_key_conflict_preflight_uses_portable_query(self):
        branch_id = self._insert_branch("branch-pg-preflight")
        existing_key = f"{self.company_key}-portable-dup"
        self._insert_user(full_name="Holder", role="Cashier", branch_id=branch_id, login_key=existing_key)
        with mock.patch.object(
            self.database, "execute_portable_query", wraps=self.database.execute_portable_query
        ) as portable:
            self.database.create_branch_scoped_user(
                self.conn,
                self.company_key,
                branch_id,
                full_name="Portable",
                role="Cashier",
                login_key=existing_key,
            )
        conflict_calls = [
            call
            for call in portable.call_args_list
            if call.args and "login_key = ?" in str(call.args[1])
        ]
        self.assertTrue(conflict_calls)

    def test_login_key_conflict_sql_converts_for_postgres(self):
        sql = "SELECT 1 FROM users WHERE login_key = ? LIMIT 1"
        converted = self.database.convert_placeholders_for_backend(sql, backend="postgres")
        self.assertIn("%s", converted)
        self.assertNotIn("login_key = ?", converted)

    def test_generate_unique_login_key_sqlite_unchanged(self):
        branch_id = self._insert_branch("branch-login-gen")
        key = self.database._generate_unique_branch_user_login_key(
            self.conn, self.company_key, branch_id, "Clerk"
        )
        self.assertTrue(key)
        self.assertIn(self.company_key, key)
