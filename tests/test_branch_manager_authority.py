import hashlib
import importlib

from test_support import ERPIsolatedTestCase


class BranchManagerAuthorityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")

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
        self.commit()
        return user_id, login_key

    def _insert_branch(self, branch_id, branch_access_key, **kwargs):
        self.conn.execute(
            """
            INSERT INTO branches (
                branch_id, company_key, branch_name, branch_type, branch_access_key, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                branch_id,
                self.company_key,
                kwargs.get("branch_name", branch_id),
                kwargs.get("branch_type", "retail"),
                branch_access_key,
                kwargs.get("is_active", 1),
            ),
        )
        self.commit()

    def test_branch_manager_has_manage_branch_users_not_manage_branches(self):
        self.assertTrue(self.modules.user_has_permission("Branch Manager", "manage_branch_users"))
        self.assertTrue(self.modules.user_has_permission("Branch Manager", "view_branch_configuration"))
        self.assertFalse(self.modules.user_has_permission("Branch Manager", "manage_branches"))
        self.assertFalse(self.modules.user_has_permission("Branch Manager", "manual_license_override"))
        self.assertFalse(self.modules.user_has_permission("Branch Manager", "manage_company_branches"))

    def test_branch_manager_cannot_create_privileged_roles(self):
        branch_id = f"{self.company_key}-ops"
        self._insert_branch(branch_id, f"{branch_id}-ACCESS")
        for blocked_role in ("Dev", "Master Admin", "System Admin"):
            result = self.database.create_branch_scoped_user(
                self.conn,
                self.company_key,
                branch_id,
                full_name="Blocked User",
                role=blocked_role,
                allowed_roles=self.database.BRANCH_MANAGER_CREATABLE_ROLES,
            )
            self.assertFalse(result["ok"], msg=blocked_role)

    def test_branch_manager_can_create_user_in_own_branch_only_via_api(self):
        branch_a = f"{self.company_key}-branch-a"
        branch_b = f"{self.company_key}-branch-b"
        self._insert_branch(branch_a, f"{branch_a}-KEY")
        self._insert_branch(branch_b, f"{branch_b}-KEY")

        result = self.database.create_branch_scoped_user(
            self.conn,
            self.company_key,
            branch_a,
            full_name="Cashier A",
            role="Cashier",
            allowed_roles=self.database.BRANCH_MANAGER_CREATABLE_ROLES,
        )
        self.commit()
        self.assertTrue(result["ok"])
        row = self.conn.execute(
            "SELECT branch_id, role FROM users WHERE login_key = ?",
            (result["login_key"],),
        ).fetchone()
        self.assertEqual(row[0], branch_a)
        self.assertEqual(row[1], "Cashier")

        wrong_branch_user = self.conn.execute(
            "SELECT COUNT(*) FROM users WHERE company_key = ? AND branch_id = ?",
            (self.company_key, branch_b),
        ).fetchone()[0]
        self.assertEqual(int(wrong_branch_user), 0)

    def test_master_admin_can_assign_manager_user_id(self):
        branch_id = f"{self.company_key}-managed"
        access_key = f"{branch_id}-ACCESS"
        self._insert_branch(branch_id, access_key)
        manager_user_id, _login = self._insert_user(
            full_name="Ops Lead",
            role="Staff",
            branch_id=None,
        )

        result = self.database.assign_branch_manager(
            self.conn,
            self.company_key,
            branch_id,
            manager_user_id,
            promote_to_branch_manager=True,
        )
        self.commit()
        self.assertTrue(result["ok"])

        branch_row = self.conn.execute(
            "SELECT manager_user_id, branch_access_key FROM branches WHERE branch_id = ?",
            (branch_id,),
        ).fetchone()
        self.assertEqual(branch_row[0], manager_user_id)
        self.assertEqual(branch_row[1], access_key)

        user_row = self.conn.execute(
            "SELECT role, branch_id FROM users WHERE user_id = ?",
            (manager_user_id,),
        ).fetchone()
        self.assertEqual(user_row[0], "Branch Manager")
        self.assertEqual(user_row[1], branch_id)

    def test_branch_manager_session_helpers_lock_branch_context(self):
        branch_user = {"role": "Branch Manager", "branch_id": "BR-100", "key": self.company_key}
        self.assertTrue(self.modules.is_branch_scoped_user(branch_user))
        self.assertEqual(self.modules.resolve_effective_branch_id(branch_user), "BR-100")
        self.assertTrue(self.modules.can_access_branch(branch_user, "BR-100"))
        self.assertFalse(self.modules.can_access_branch(branch_user, "BR-200"))
        self.assertFalse(self.modules.can_access_branch(branch_user, None))

    def test_create_branch_user_does_not_mutate_branch_access_key(self):
        branch_id = f"{self.company_key}-secure-key"
        access_key = f"{branch_id}-ORIGINAL-KEY"
        self._insert_branch(branch_id, access_key)

        result = self.database.create_branch_scoped_user(
            self.conn,
            self.company_key,
            branch_id,
            full_name="New Cashier",
            role="Cashier",
        )
        self.commit()
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("branch_access_key_unchanged"))

        stored_key = self.conn.execute(
            "SELECT branch_access_key FROM branches WHERE branch_id = ?",
            (branch_id,),
        ).fetchone()[0]
        self.assertEqual(stored_key, access_key)
        self.assertNotEqual(result["login_key"], access_key)
