import importlib

from test_support import ERPIsolatedTestCase


class BranchLicensingEnforcementTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database = importlib.import_module("database")

    def _set_branch_license(self, max_branches=1, number_of_branches=1):
        self.conn.execute(
            """
            UPDATE companies
            SET max_branches = ?, number_of_branches = ?
            WHERE key = ?
            """,
            (int(max_branches), int(number_of_branches), self.company_key),
        )
        self.commit()

    def test_branch_type_catalog_available_for_dropdown(self):
        catalog = self.database.get_branch_type_catalog(self.conn)
        keys = {row["branch_type_key"] for row in catalog}
        self.assertGreaterEqual(len(catalog), 6)
        self.assertIn("retail", keys)
        self.assertIn("warehouse", keys)

    def test_branch_creation_creates_module_grants(self):
        result = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Accra Retail",
            branch_type_key="retail",
        )
        self.commit()
        self.assertTrue(result["ok"])
        grant_count = self.conn.execute(
            """
            SELECT COUNT(*) FROM branch_module_grants
            WHERE company_key = ? AND branch_id = ?
            """,
            (self.company_key, result["branch_id"]),
        ).fetchone()[0]
        self.assertEqual(int(grant_count), 10)

    def test_active_branch_limit_blocks_excess_branch(self):
        self._set_branch_license(max_branches=1, number_of_branches=1)
        first = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Branch One",
            branch_type_key="retail",
            is_active=1,
        )
        self.commit()
        self.assertTrue(first["ok"])

        second = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Branch Two",
            branch_type_key="warehouse",
            is_active=1,
        )
        self.assertFalse(second["ok"])
        self.assertIn("limit", str(second.get("reason") or "").lower())

    def test_inactive_branches_do_not_count_against_limit(self):
        self._set_branch_license(max_branches=1, number_of_branches=1)
        inactive = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Inactive Hub",
            branch_type_key="warehouse",
            is_active=0,
        )
        self.commit()
        self.assertTrue(inactive["ok"])

        active = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Active Store",
            branch_type_key="retail",
            is_active=1,
        )
        self.commit()
        self.assertTrue(active["ok"])

        blocked = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Second Active",
            branch_type_key="office",
            is_active=1,
        )
        self.assertFalse(blocked["ok"])

        snapshot = self.database.get_company_branch_license_snapshot(self.conn, self.company_key)
        self.assertEqual(snapshot["active_branch_count"], 1)
        self.assertEqual(snapshot["max_branches"], 1)

    def test_repair_branch_module_grants_is_idempotent(self):
        branch_id = f"{self.company_key}-repair-me"
        self.conn.execute(
            """
            INSERT INTO branches (
                branch_id, company_key, branch_name, branch_type, branch_access_key, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (branch_id, self.company_key, "Repair Me", "retail", f"{branch_id}-KEY", 1),
        )
        self.commit()

        first = self.database.repair_branch_module_grants(self.conn, self.company_key)
        self.assertTrue(first["ok"])
        self.assertEqual(first["branches_processed"], 1)
        self.assertGreaterEqual(first["grants_inserted"], 1)

        second = self.database.repair_branch_module_grants(self.conn, self.company_key)
        self.assertTrue(second["ok"])
        self.assertEqual(second["grants_inserted"], 0)

        grant_count = self.conn.execute(
            """
            SELECT COUNT(*) FROM branch_module_grants
            WHERE company_key = ? AND branch_id = ?
            """,
            (self.company_key, branch_id),
        ).fetchone()[0]
        self.assertEqual(int(grant_count), 10)
