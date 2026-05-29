import importlib

from test_support import ERPIsolatedTestCase


class BranchSessionTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_branch_scoped_user_cannot_access_company_wide_context(self):
        branch_user = {"role": "Branch_Bookkeeper", "branch_id": "BR-001"}
        self.assertTrue(self.modules.is_branch_scoped_user(branch_user))
        self.assertFalse(self.modules.can_access_branch(branch_user, None))
        self.assertEqual(self.modules.resolve_effective_branch_id(branch_user), "BR-001")

    def test_dashboard_kpi_snapshot_filters_pos_sales_by_branch(self):
        branch_id = f"{self.company_key}-kumasi"
        self.conn.execute(
            """
            INSERT INTO pos_sales (
                company_key, branch_id, sale_reference, receipt_number,
                sale_date, grand_total, payment_method, cashier
            )
            VALUES (?, ?, 'BR-SALE-1', 'RCP-1', date('now'), ?, 'Cash', 'Cashier A')
            """,
            (self.company_key, branch_id, 500.0),
        )
        self.conn.execute(
            """
            INSERT INTO pos_sales (
                company_key, branch_id, sale_reference, receipt_number,
                sale_date, grand_total, payment_method, cashier
            )
            VALUES (?, ?, 'OTHER-SALE-1', 'RCP-2', date('now'), ?, 'Cash', 'Cashier B')
            """,
            (self.company_key, "OTHER-BRANCH", 9000.0),
        )
        self.commit()
        self.modules.ensure_pos_sales_schema(self.conn)
        branch_snapshot = self.modules._fetch_dashboard_kpi_snapshot(self.conn, self.company_key, branch_id=branch_id)
        company_snapshot = self.modules._fetch_dashboard_kpi_snapshot(self.conn, self.company_key, branch_id=None)
        self.assertEqual(branch_snapshot["today_sales"], 500.0)
        self.assertGreaterEqual(company_snapshot["today_sales"], 9500.0)
