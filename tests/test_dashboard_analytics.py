import importlib

import pandas as pd

from test_support import ERPIsolatedTestCase


class DashboardAnalyticsTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_normalize_stock_movement_type_alias(self):
        self.assertEqual(self.modules._normalize_stock_movement_type("In"), "STOCK_IN")

    def test_dashboard_kpi_snapshot_returns_expected_keys(self):
        self.conn.execute(
            """
            INSERT INTO inventory (company_key, item_name, qty, cost_price, min_stock_level, price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "Dash Item", 2.0, 5.0, 10.0, 12.0),
        )
        self.commit()
        snapshot = self.modules._fetch_dashboard_kpi_snapshot(self.conn, self.company_key)
        for key in (
            "today_sales",
            "month_sales",
            "gross_profit",
            "inventory_value",
            "low_stock_count",
            "receivables_total",
            "payables_total",
            "cash_bank_balance",
        ):
            self.assertIn(key, snapshot)

    def test_dashboard_chart_has_data_detects_empty_and_zero_series(self):
        self.assertFalse(self.modules._dashboard_chart_has_data(pd.DataFrame()))
        self.assertFalse(
            self.modules._dashboard_chart_has_data(
                pd.DataFrame({"sales_total": [0.0, 0.0]}, index=["A", "B"])
            )
        )
        self.assertTrue(
            self.modules._dashboard_chart_has_data(
                pd.DataFrame({"sales_total": [1.0]}, index=["A"])
            )
        )

    def test_filter_inventory_overview_ok_only(self):
        overview = self.modules._prepare_inventory_overview_dataframe(
            __import__("pandas").DataFrame(
                [
                    {"item_name": "A", "quantity": 1, "min_stock_level": 5, "expiry_date": None},
                    {"item_name": "B", "quantity": 20, "min_stock_level": 5, "expiry_date": None},
                ]
            )
        )
        filtered = self.modules._filter_inventory_overview_dataframe(overview, "LOW STOCK")
        self.assertEqual(len(filtered), 1)
