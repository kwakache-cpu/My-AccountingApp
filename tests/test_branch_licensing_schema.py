import importlib

from test_support import ERPIsolatedTestCase


class BranchLicensingSchemaTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database = importlib.import_module("database")

    def test_branch_type_catalog_seeds(self):
        count = self.conn.execute("SELECT COUNT(*) FROM branch_type_catalog").fetchone()[0]
        self.assertGreaterEqual(int(count), 6)
        keys = {
            row[0]
            for row in self.conn.execute(
                "SELECT branch_type_key FROM branch_type_catalog ORDER BY branch_type_key"
            ).fetchall()
        }
        self.assertEqual(
            keys,
            {"main", "office", "other", "retail", "subsidiary_main", "warehouse"},
        )

    def test_default_module_template_seeds(self):
        retail_modules = {
            row[0]
            for row in self.conn.execute(
                """
                SELECT module_key
                FROM branch_type_module_defaults
                WHERE branch_type_key = 'retail'
                """
            ).fetchall()
        }
        self.assertIn("Dashboard", retail_modules)
        self.assertIn("Point of Sale", retail_modules)
        self.assertIn("Inventory", retail_modules)
        self.assertEqual(len(retail_modules), 10)

        warehouse_modules = {
            row[0]
            for row in self.conn.execute(
                """
                SELECT module_key
                FROM branch_type_module_defaults
                WHERE branch_type_key = 'warehouse'
                """
            ).fetchall()
        }
        self.assertEqual(warehouse_modules, {"Dashboard", "Inventory", "Reports"})

        main_count = self.conn.execute(
            "SELECT COUNT(*) FROM branch_type_module_defaults WHERE branch_type_key = 'main'"
        ).fetchone()[0]
        subsidiary_count = self.conn.execute(
            "SELECT COUNT(*) FROM branch_type_module_defaults WHERE branch_type_key = 'subsidiary_main'"
        ).fetchone()[0]
        self.assertEqual(int(main_count), len(self.database.BRANCH_MAIN_OPERATING_MODULE_KEYS))
        self.assertEqual(int(subsidiary_count), len(self.database.BRANCH_MAIN_OPERATING_MODULE_KEYS))

        excluded = self.conn.execute(
            """
            SELECT COUNT(*) FROM branch_type_module_defaults
            WHERE branch_type_key IN ('main', 'subsidiary_main')
              AND module_key IN ('Gatekeeper Admin', 'System Configuration', 'branch_management')
            """
        ).fetchone()[0]
        self.assertEqual(int(excluded), 0)

    def test_branch_module_grants_created_idempotently(self):
        branch_id = f"{self.company_key}-retail-1"
        self.conn.execute(
            """
            INSERT INTO branches (
                branch_id, company_key, branch_name, branch_type, branch_access_key, is_active
            )
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (branch_id, self.company_key, "Retail One", "Retail", f"{branch_id}-KEY"),
        )
        self.commit()

        first = self.database.ensure_branch_module_grants_for_branch(
            self.conn,
            self.company_key,
            branch_id,
            branch_type_key="retail",
        )
        self.assertTrue(first["ok"])
        self.assertEqual(first["template_count"], 10)
        self.assertEqual(first["inserted"], 10)

        grant_count_after_first = self.conn.execute(
            """
            SELECT COUNT(*) FROM branch_module_grants
            WHERE company_key = ? AND branch_id = ?
            """,
            (self.company_key, branch_id),
        ).fetchone()[0]
        self.assertEqual(int(grant_count_after_first), 10)

        second = self.database.ensure_branch_module_grants_for_branch(
            self.conn,
            self.company_key,
            branch_id,
            branch_type_key="retail",
        )
        self.assertTrue(second["ok"])
        self.assertEqual(second["inserted"], 0)

        grant_count_after_second = self.conn.execute(
            """
            SELECT COUNT(*) FROM branch_module_grants
            WHERE company_key = ? AND branch_id = ?
            """,
            (self.company_key, branch_id),
        ).fetchone()[0]
        self.assertEqual(int(grant_count_after_second), 10)

    def test_existing_branch_receives_grants_from_legacy_branch_type(self):
        branch_id = f"{self.company_key}-warehouse-legacy"
        self.conn.execute(
            """
            INSERT INTO branches (
                branch_id, company_key, branch_name, branch_type, branch_access_key
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                branch_id,
                self.company_key,
                "Warehouse Legacy",
                "Warehouse",
                f"{branch_id}-KEY",
            ),
        )
        self.commit()

        result = self.database.ensure_branch_module_grants_for_branch(
            self.conn,
            self.company_key,
            branch_id,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["branch_type_key"], "warehouse")

        modules = {
            row[0]
            for row in self.conn.execute(
                """
                SELECT module_key FROM branch_module_grants
                WHERE company_key = ? AND branch_id = ?
                """,
                (self.company_key, branch_id),
            ).fetchall()
        }
        self.assertEqual(modules, {"Dashboard", "Inventory", "Reports"})

    def test_branches_additive_columns_exist(self):
        columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(branches)").fetchall()
        }
        for column_name in ("is_active", "manager_user_id", "deployment_status", "branch_tier"):
            self.assertIn(column_name, columns)
