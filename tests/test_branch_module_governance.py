import hashlib
import importlib

from test_support import ERPIsolatedTestCase


class BranchModuleGovernanceTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")

    def _create_branch(self, branch_name, branch_type_key, access_key):
        result = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name=branch_name,
            branch_type_key=branch_type_key,
            branch_access_key=access_key,
            is_active=1,
        )
        self.commit()
        self.assertTrue(result["ok"], result.get("reason"))
        return result["branch_id"]

    def test_master_admin_can_manage_branch_users_and_bypass_gating(self):
        self.assertTrue(self.modules.can_manage_branch_users_role("Master Admin"))
        self.assertTrue(self.modules.user_has_permission("Master Admin", "manage_branches"))
        master_user = {"role": "Master Admin", "key": self.company_key}
        self.assertTrue(self.modules.branch_allows_page(master_user, "Point of Sale", company_key=self.company_key, conn=self.conn))
        self.assertTrue(
            self.modules.user_can_access_page(master_user, "branch_management", company_key=self.company_key, conn=self.conn)
        )

    def test_master_admin_can_edit_branch_and_reactivation_respects_limit(self):
        self.conn.execute(
            "UPDATE companies SET max_branches = 1, number_of_branches = 1 WHERE key = ?",
            (self.company_key,),
        )
        self.commit()
        branch_a = self._create_branch("alpha", "retail", "alpha-KEY")

        inactive = self.database.update_company_branch(
            self.conn,
            self.company_key,
            branch_a,
            is_active=0,
        )
        self.commit()
        self.assertTrue(inactive["ok"])

        create_b = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="beta",
            branch_type_key="warehouse",
            branch_access_key="beta-KEY",
            is_active=1,
        )
        self.commit()
        self.assertTrue(create_b["ok"])

        reactivate = self.database.update_company_branch(
            self.conn,
            self.company_key,
            branch_a,
            is_active=1,
        )
        self.assertFalse(reactivate["ok"])
        self.assertIn("limit", str(reactivate.get("reason") or "").lower())

    def test_staff_assignment_transfers_user_branch_id(self):
        branch_id = self._create_branch("staff branch", "retail", "staff-branch-KEY")
        user_pk = self.conn.execute(
            """
            INSERT INTO users (company_key, full_name, user_id, login_key, role, status)
            VALUES (?, 'Movable Staff', ?, ?, 'Staff', 'Active')
            """,
            (
                self.company_key,
                hashlib.sha256(b"movable").hexdigest(),
                f"{self.company_key}-movable-key",
            ),
        ).lastrowid
        self.commit()

        result = self.database.update_company_staff_branch_assignment(
            self.conn,
            self.company_key,
            user_pk,
            branch_id,
            role="Cashier",
            actor_role="Master Admin",
        )
        self.commit()
        self.assertTrue(result["ok"])
        row = self.conn.execute("SELECT branch_id, role FROM users WHERE id = ?", (user_pk,)).fetchone()
        self.assertEqual(row[0], branch_id)
        self.assertEqual(row[1], "Cashier")

    def test_branch_manager_cannot_transfer_cross_branch_users(self):
        result = self.database.update_company_staff_branch_assignment(
            self.conn,
            self.company_key,
            1,
            "some-branch",
            actor_role="Branch Manager",
        )
        self.assertFalse(result["ok"])

    def test_retail_allows_pos_warehouse_blocks_pos(self):
        self.conn.execute(
            "UPDATE companies SET max_branches = 5, number_of_branches = 5 WHERE key = ?",
            (self.company_key,),
        )
        self.commit()
        retail_id = self._create_branch("retail pos", "retail", "retail-pos-KEY")
        warehouse_id = self._create_branch("warehouse pos", "warehouse", "warehouse-pos-KEY")

        retail_modules = self.database.get_branch_enabled_modules(self.conn, self.company_key, retail_id)
        warehouse_modules = self.database.get_branch_enabled_modules(self.conn, self.company_key, warehouse_id)
        self.assertIn("Point of Sale", retail_modules)
        self.assertNotIn("Point of Sale", warehouse_modules)

        cashier = {"role": "Cashier", "key": self.company_key, "branch_id": retail_id}
        warehouse_cashier = {"role": "Cashier", "key": self.company_key, "branch_id": warehouse_id}
        self.assertTrue(
            self.modules.branch_allows_page(cashier, "Point of Sale", company_key=self.company_key, conn=self.conn)
        )
        self.assertFalse(
            self.modules.branch_allows_page(
                warehouse_cashier,
                "Point of Sale",
                company_key=self.company_key,
                conn=self.conn,
            )
        )

    def test_main_branch_allows_operating_modules(self):
        main_id = self._create_branch("main branch", "main", "main-branch-KEY")
        modules = self.database.get_branch_enabled_modules(self.conn, self.company_key, main_id)
        self.assertIn("Point of Sale", modules)
        self.assertIn("Inventory", modules)
        self.assertIn("Financial Reports", modules)

    def test_disabled_module_grant_hides_page(self):
        branch_id = self._create_branch("disabled pos", "retail", "disabled-pos-DKEY")
        self.conn.execute(
            """
            UPDATE branch_module_grants
            SET is_enabled = 0
            WHERE company_key = ? AND branch_id = ? AND module_key = 'Point of Sale'
            """,
            (self.company_key, branch_id),
        )
        self.commit()
        user = {"role": "Cashier", "key": self.company_key, "branch_id": branch_id}
        self.assertFalse(
            self.modules.user_can_access_page(user, "Point of Sale", company_key=self.company_key, conn=self.conn)
        )
        self.assertTrue(
            self.modules.user_can_access_page(user, "Dashboard", company_key=self.company_key, conn=self.conn)
        )

    def test_branch_type_change_refreshes_grants_without_duplicates(self):
        branch_id = self._create_branch("type change", "retail", "type-change-TKEY")
        before = self.conn.execute(
            "SELECT COUNT(*) FROM branch_module_grants WHERE company_key = ? AND branch_id = ?",
            (self.company_key, branch_id),
        ).fetchone()[0]

        result = self.database.update_company_branch(
            self.conn,
            self.company_key,
            branch_id,
            branch_type_key="warehouse",
        )
        self.commit()
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("branch_type_changed"))

        after = self.conn.execute(
            "SELECT COUNT(*) FROM branch_module_grants WHERE company_key = ? AND branch_id = ?",
            (self.company_key, branch_id),
        ).fetchone()[0]
        self.assertLessEqual(int(after), int(before) + 5)
        pos_rows = self.conn.execute(
            """
            SELECT is_enabled FROM branch_module_grants
            WHERE company_key = ? AND branch_id = ? AND module_key = 'Point of Sale'
            """,
            (self.company_key, branch_id),
        ).fetchall()
        if pos_rows:
            disabled_value = pos_rows[0][0] if not isinstance(pos_rows[0], dict) else pos_rows[0]["is_enabled"]
            self.assertEqual(int(disabled_value), 0)

    def test_master_admin_passes_branch_users_panel_gate(self):
        self.assertTrue(self.modules.can_manage_branch_users_role("Master Admin"))
        self.assertTrue(self.modules.is_company_branch_admin("Master Admin"))
        self.assertTrue(self.modules.can_access_branch_management("Master Admin"))

    def test_manager_select_options_include_current_manager(self):
        branch_id = self._create_branch("mgr select", "retail", "mgr-select-MKEY")
        access_key = "mgr-select-MKEY"
        manager_user_id, _login = self._insert_staff_user(
            full_name="Current Manager",
            role="Staff",
            branch_id=branch_id,
        )
        self.conn.execute(
            "UPDATE branches SET manager_user_id = ? WHERE branch_id = ?",
            (manager_user_id, branch_id),
        )
        self.commit()
        options = self.database.fetch_branch_manager_select_options(
            self.conn,
            self.company_key,
            branch_id,
            current_manager_user_id=manager_user_id,
        )
        option_ids = {row["user_id"] for row in options}
        self.assertIn(manager_user_id, option_ids)

    def test_staff_assignment_lists_eligible_non_privileged_users(self):
        self._insert_staff_user(full_name="Assignable One", role="Staff")
        self._insert_staff_user(full_name="Assignable Two", role="Cashier")
        staff_rows = self.database.list_company_staff_for_assignment(self.conn, self.company_key)
        self.assertGreaterEqual(len(staff_rows), 2)
        for row in staff_rows:
            self.assertNotIn(row["role"], self.database.PRIVILEGED_COMPANY_USER_ROLES)

    def test_branch_access_key_unchanged_after_user_and_staff_actions(self):
        branch_id = self._create_branch("key guard", "retail", "key-guard-GUARDKEY")
        access_key = "key-guard-GUARDKEY"
        before = self.conn.execute(
            "SELECT branch_access_key FROM branches WHERE branch_id = ?",
            (branch_id,),
        ).fetchone()[0]

        create_result = self.database.create_branch_scoped_user(
            self.conn,
            self.company_key,
            branch_id,
            full_name="Branch Staff",
            role="Staff",
        )
        self.commit()
        self.assertTrue(create_result["ok"])
        self.assertTrue(create_result.get("branch_access_key_unchanged"))

        user_pk = self.conn.execute(
            "SELECT id FROM users WHERE company_key = ? AND full_name = ?",
            (self.company_key, "Branch Staff"),
        ).fetchone()[0]
        transfer = self.database.update_company_staff_branch_assignment(
            self.conn,
            self.company_key,
            user_pk,
            branch_id,
            role="Cashier",
            actor_role="Master Admin",
        )
        self.commit()
        self.assertTrue(transfer["ok"])

        after = self.conn.execute(
            "SELECT branch_access_key FROM branches WHERE branch_id = ?",
            (branch_id,),
        ).fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(access_key, after)

    def test_run_branch_db_write_uses_single_transaction(self):
        calls = []

        def _callback(write_conn):
            calls.append("callback")
            write_conn.execute("SELECT 1")
            return {"ok": True}

        result = self.modules._run_branch_db_write("test_branch_write", _callback)
        self.assertTrue(result["ok"])
        self.assertEqual(calls, ["callback"])

    def test_staff_assignment_handles_null_user_id(self):
        self.conn.execute(
            """
            INSERT INTO users (company_key, full_name, user_id, login_key, role, status)
            VALUES (?, 'Legacy Staff', NULL, ?, 'Staff', 'Active')
            """,
            (self.company_key, f"{self.company_key}-legacy-login"),
        )
        self.commit()
        staff_rows = self.database.list_company_staff_for_assignment(self.conn, self.company_key)
        legacy = next((row for row in staff_rows if row["full_name"] == "Legacy Staff"), None)
        self.assertIsNotNone(legacy)
        self.assertEqual(legacy["user_id_display"], f"{self.company_key}-legacy-login")
        self.assertEqual(legacy["login_key_display"], f"{self.company_key}-legacy-login")

    def test_get_income_statement_does_not_accept_branch_id(self):
        import inspect

        financials = importlib.import_module("financials")
        signature = inspect.signature(financials.get_income_statement)
        self.assertNotIn("branch_id", signature.parameters)

    def test_new_branch_id_uses_company_name_and_branch_name(self):
        branch_id = self.database._derive_branch_id(self.conn, self.company_key, "Kumasi")
        self.assertEqual(branch_id, "test-company-kumasi")
        result = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Kumasi",
            branch_type_key="retail",
            branch_access_key="kumasi-access-key",
        )
        self.commit()
        self.assertTrue(result["ok"])
        self.assertEqual(result["branch_id"], "test-company-kumasi")
        self.assertEqual(result["branch_code"], "kumasi")

    def test_branch_code_backfill_uses_branch_name(self):
        legacy_branch_id = f"{self.company_key}-legacy-code"
        self.conn.execute(
            """
            INSERT INTO branches (
                branch_id, company_key, branch_name, branch_type, branch_access_key, is_active
            )
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (legacy_branch_id, self.company_key, "Legacy Kumasi", "retail", f"{legacy_branch_id}-KEY"),
        )
        self.commit()
        self.database.ensure_branch_licensing_schema_integrity(self.conn)
        self.commit()
        row = self.conn.execute(
            "SELECT branch_code, branch_id FROM branches WHERE branch_id = ?",
            (legacy_branch_id,),
        ).fetchone()
        self.assertEqual(row[0], "Legacy Kumasi")
        self.assertEqual(row[1], legacy_branch_id)

    def test_update_company_branch_can_edit_branch_code(self):
        branch_id = self._create_branch("Editable Branch", "retail", "editable-branch-KEY")
        result = self.database.update_company_branch(
            self.conn,
            self.company_key,
            branch_id,
            branch_code="accra-main",
        )
        self.commit()
        self.assertTrue(result["ok"])
        self.assertEqual(result["branch_code"], "accra-main")
        row = self.conn.execute(
            "SELECT branch_code, branch_id FROM branches WHERE branch_id = ?",
            (branch_id,),
        ).fetchone()
        self.assertEqual(row[0], "accra-main")
        self.assertEqual(row[1], branch_id)

    def test_existing_branch_id_is_not_renamed(self):
        legacy_branch_id = f"{self.company_key}-legacy-kumasi"
        self.conn.execute(
            """
            INSERT INTO branches (
                branch_id, company_key, branch_name, branch_type, branch_access_key, is_active
            )
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (legacy_branch_id, self.company_key, "Legacy Kumasi", "retail", f"{legacy_branch_id}-KEY"),
        )
        self.commit()
        row = self.conn.execute(
            "SELECT branch_id FROM branches WHERE branch_id = ?",
            (legacy_branch_id,),
        ).fetchone()
        self.assertEqual(row[0], legacy_branch_id)

    def test_branch_manager_display_prefers_full_name(self):
        branch = {
            "manager_user_name": "Kwame Nkrumah",
            "manager_user_id": "abc123",
            "branch_manager": "KIN",
        }
        self.assertEqual(self.modules._branch_manager_display_label(branch), "Kwame Nkrumah")
        self.assertEqual(
            self.modules._branch_manager_display_label(
                {"manager_user_name": "", "manager_user_id": "abc123", "branch_manager": "KIN"}
            ),
            "abc123",
        )
        self.assertEqual(
            self.modules._branch_manager_display_label(
                {"manager_user_name": "", "manager_user_id": "", "branch_manager": "KIN"}
            ),
            "KIN",
        )

    def _insert_staff_user(self, *, full_name, role, branch_id=None):
        login_key = f"{self.company_key}-{role}-{full_name.replace(' ', '_')}"
        user_id = hashlib.sha256(login_key.encode("utf-8")).hexdigest()
        self.conn.execute(
            """
            INSERT INTO users (
                company_key, branch_id, full_name, user_id, login_key, role, status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'Active')
            """,
            (self.company_key, branch_id, full_name, user_id, login_key, role),
        )
        self.commit()
        return user_id, login_key
