import hashlib
from unittest import mock

from test_support import ERPIsolatedTestCase


class BranchUserDmlPortabilityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database.ensure_branch_licensing_schema_integrity(self.conn)
        # allow creating more than the default 1 active branch in tests
        self.conn.execute(
            "UPDATE companies SET max_branches = 10, number_of_branches = 10 WHERE key = ?",
            (self.company_key,),
        )
        self.conn.commit()

    def test_create_company_branch_sqlite_unchanged(self):
        result = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Operations",
            branch_type_key="retail",
            ensure_schema=False,
        )
        self.assertTrue(result["ok"])
        row = self.conn.execute(
            "SELECT branch_id, branch_access_key FROM branches WHERE company_key = ? AND branch_id = ?",
            (self.company_key, result["branch_id"]),
        ).fetchone()
        self.assertIsNotNone(row)

    def test_create_company_branch_uses_execute_portable_write(self):
        with mock.patch.object(
            self.database, "execute_portable_write", wraps=self.database.execute_portable_write
        ) as portable:
            result = self.database.create_company_branch(
                self.conn,
                self.company_key,
                branch_name="Sales",
                branch_type_key="retail",
                ensure_schema=False,
            )
        self.assertTrue(result["ok"])
        self.assertTrue(any("INSERT INTO branches" in str(call.args[1]) for call in portable.call_args_list))

    def test_update_company_branch_uses_execute_portable_write(self):
        created = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Warehouse",
            branch_type_key="retail",
            ensure_schema=False,
        )
        self.assertTrue(created["ok"])
        with mock.patch.object(
            self.database, "execute_portable_write", wraps=self.database.execute_portable_write
        ) as portable:
            result = self.database.update_company_branch(
                self.conn,
                self.company_key,
                created["branch_id"],
                branch_name="Warehouse Updated",
            )
        self.assertTrue(result["ok"])
        self.assertTrue(any("UPDATE branches" in str(call.args[1]) for call in portable.call_args_list))

    def test_assign_branch_manager_uses_execute_portable_write(self):
        created = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="HR",
            branch_type_key="retail",
            ensure_schema=False,
        )
        self.assertTrue(created["ok"])
        login_key = f"{self.company_key}-mgr-hr"
        user_id = hashlib.sha256(login_key.encode("utf-8")).hexdigest()
        self.conn.execute(
            """
            INSERT INTO users (company_key, branch_id, full_name, user_id, login_key, role, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, created["branch_id"], "Manager", user_id, login_key, "Cashier", "Active"),
        )
        self.conn.commit()
        with mock.patch.object(
            self.database, "execute_portable_write", wraps=self.database.execute_portable_write
        ) as portable:
            result = self.database.assign_branch_manager(
                self.conn,
                self.company_key,
                created["branch_id"],
                user_id,
            )
        self.assertTrue(result["ok"])
        sqls = [str(call.args[1]) for call in portable.call_args_list]
        self.assertTrue(any("UPDATE users" in sql for sql in sqls))
        self.assertTrue(any("UPDATE branches" in sql for sql in sqls))

    def test_create_branch_scoped_user_uses_execute_portable_write(self):
        created = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Retail",
            branch_type_key="retail",
            ensure_schema=False,
        )
        self.assertTrue(created["ok"])
        with mock.patch.object(
            self.database, "execute_portable_write", wraps=self.database.execute_portable_write
        ) as portable:
            result = self.database.create_branch_scoped_user(
                self.conn,
                self.company_key,
                created["branch_id"],
                full_name="Cashier One",
                role="Cashier",
            )
        self.assertTrue(result["ok"])
        self.assertTrue(any("INSERT INTO users" in str(call.args[1]) for call in portable.call_args_list))

    def test_update_branch_user_status_uses_execute_portable_write(self):
        created = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Ops",
            branch_type_key="retail",
            ensure_schema=False,
        )
        self.assertTrue(created["ok"])
        user = self.database.create_branch_scoped_user(
            self.conn,
            self.company_key,
            created["branch_id"],
            full_name="Staff One",
            role="Cashier",
        )
        self.assertTrue(user["ok"])
        row = self.conn.execute(
            "SELECT id FROM users WHERE company_key = ? AND user_id = ?",
            (self.company_key, user["user_id"]),
        ).fetchone()
        self.assertIsNotNone(row)
        user_pk = int(row[0])
        with mock.patch.object(
            self.database, "execute_portable_write", wraps=self.database.execute_portable_write
        ) as portable:
            result = self.database.update_branch_user_status(
                self.conn,
                self.company_key,
                created["branch_id"],
                user_pk,
                "Inactive",
            )
        self.assertTrue(result["ok"])
        self.assertTrue(any("UPDATE users SET status" in str(call.args[1]) for call in portable.call_args_list))

    def test_update_company_staff_branch_assignment_uses_execute_portable_write(self):
        branch_a = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="A",
            branch_type_key="retail",
            ensure_schema=False,
        )
        branch_b = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="B",
            branch_type_key="retail",
            ensure_schema=False,
        )
        self.assertTrue(branch_a["ok"] and branch_b["ok"])
        user = self.database.create_branch_scoped_user(
            self.conn,
            self.company_key,
            branch_a["branch_id"],
            full_name="Transfer User",
            role="Cashier",
        )
        self.assertTrue(user["ok"])
        pk_row = self.conn.execute(
            "SELECT id FROM users WHERE company_key = ? AND user_id = ?",
            (self.company_key, user["user_id"]),
        ).fetchone()
        user_pk = int(pk_row[0])
        with mock.patch.object(
            self.database, "execute_portable_write", wraps=self.database.execute_portable_write
        ) as portable:
            result = self.database.update_company_staff_branch_assignment(
                self.conn,
                self.company_key,
                user_pk,
                branch_b["branch_id"],
                actor_role="System Admin",
            )
        self.assertTrue(result["ok"])
        self.assertTrue(any("UPDATE users" in str(call.args[1]) for call in portable.call_args_list))

    def test_postgres_placeholder_conversion_for_dml_sql(self):
        sql = "UPDATE users SET branch_id = ? WHERE id = ? AND company_key = ?"
        converted = self.database.convert_placeholders_for_backend(sql, backend="postgres")
        self.assertIn("%s", converted)
        self.assertNotIn("?", converted)

