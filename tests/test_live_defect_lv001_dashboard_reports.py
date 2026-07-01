import importlib

import pandas as pd

from test_support import ERPIsolatedTestCase, build_lines


class LiveDefectLv001DashboardReportsTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.financials = importlib.import_module("financials")

    def test_trial_balance_uses_cumulative_end_date_not_period_start(self):
        cash_id = self.account_id("Cash", "Asset")
        revenue_id = self.account_id("Sales Revenue", "Income")
        self.post_entry(
            build_lines(
                {"account_id": cash_id, "debit": 300.0, "credit": 0.0},
                {"account_id": revenue_id, "debit": 0.0, "credit": 300.0},
            ),
            description="LV-001 cumulative TB",
            reference="LV001-TB-001",
        )
        period_start = self.today.replace(day=1)
        trial_balance = self.financials.get_trial_balance(
            self.company_key,
            start_date=period_start,
            end_date=self.today,
        )
        self.assertFalse(trial_balance.empty)
        self.assertGreaterEqual(len(trial_balance), 2)

    def test_income_statement_uses_selected_period(self):
        cash_id = self.account_id("Cash", "Asset")
        revenue_id = self.account_id("Sales Revenue", "Income")
        self.post_entry(
            build_lines(
                {"account_id": cash_id, "debit": 180.0, "credit": 0.0},
                {"account_id": revenue_id, "debit": 0.0, "credit": 180.0},
            ),
            description="LV-001 period IS",
            reference="LV001-IS-001",
        )
        income_statement = self.financials.get_income_statement(
            self.company_key,
            start_date=self.today.replace(day=1),
            end_date=self.today,
        )
        self.assertFalse(income_statement.empty)
        net_profit_rows = income_statement.loc[income_statement["Account"] == "Net Profit", "Amount (GHS)"]
        self.assertFalse(net_profit_rows.empty)

    def test_dashboard_journal_fallback_populates_sales_charts_without_pos(self):
        cash_id = self.account_id("Cash", "Asset")
        revenue_id = self.account_id("Sales Revenue", "Income")
        self.post_entry(
            build_lines(
                {"account_id": cash_id, "debit": 95.0, "credit": 0.0},
                {"account_id": revenue_id, "debit": 0.0, "credit": 95.0},
            ),
            description="LV-001 journal fallback sale",
            reference="LV001-CHART-001",
        )
        sales = self.modules._fetch_dashboard_sales_analytics(self.conn, self.company_key)
        self.assertTrue(sales.get("daily_sales"))
        daily_df = pd.DataFrame(sales["daily_sales"]).set_index("sale_day")[["sales_total"]]
        normalized = self.modules._normalize_dashboard_chart_dataframe(daily_df)
        self.assertTrue(self.modules._dashboard_chart_has_data(normalized))

    def test_live_validation_lv001_diagnostics_include_required_evidence(self):
        cash_id = self.account_id("Cash", "Asset")
        revenue_id = self.account_id("Sales Revenue", "Income")
        self.post_entry(
            build_lines(
                {"account_id": cash_id, "debit": 50.0, "credit": 0.0},
                {"account_id": revenue_id, "debit": 0.0, "credit": 50.0},
            ),
            description="LV-001 diagnostics",
            reference="LV001-DIAG-001",
        )
        diagnostics = self.modules.get_live_validation_lv001_diagnostics(
            self.company_key,
            start_date=self.today.replace(day=1),
            end_date=self.today,
        )
        for marker in [
            "company_key",
            "backend_active",
            "selected_start_date",
            "selected_end_date",
            "journal_entries_all_rows",
            "journal_lines_all_rows",
            "dashboard_query_ms",
            "financial_report_query_ms",
            "chart_daily_sales_empty",
            "report_trial_balance_empty",
        ]:
            self.assertIn(marker, diagnostics, f"LV-001 diagnostics missing marker: {marker}")
        self.assertEqual(diagnostics["company_key"], self.company_key)
        self.assertFalse(diagnostics["report_trial_balance_empty"])

    def test_financial_report_runtime_diagnostics_include_unfiltered_row_counts(self):
        diagnostics = self.financials._financial_report_runtime_diagnostics(
            self.company_key,
            start_date=self.today,
            end_date=self.today,
        )
        self.assertIn("journal_entries_all_rows", diagnostics)
        self.assertIn("pos_sales_rows", diagnostics)
        self.assertIn("inventory_rows", diagnostics)
