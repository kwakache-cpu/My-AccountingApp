import inspect
import re
from datetime import date
from unittest import TestCase, mock

import pandas as pd

from test_support import ERPIsolatedTestCase


class Lv009FinancialReportsLazyLoadTests(TestCase):
    def setUp(self):
        self.financials = __import__("financials")

    def test_show_financial_reports_uses_lazy_report_fetch(self):
        source = inspect.getsource(self.financials.show_financial_reports)
        self.assertIn("_cached_financial_report_by_type", source)
        self.assertNotIn("_cached_financial_reports_bundle(", source)
        self.assertIn("st.radio", source)
        self.assertNotIn("st.tabs(", source.split("if consolidated:")[0])

    def test_show_financial_reports_uses_lazy_csv_button(self):
        source = inspect.getsource(self.financials.show_financial_reports)
        non_consolidated = source.split("else:")[-1]
        self.assertIn("_lazy_csv_button(", non_consolidated)
        self.assertIsNone(re.search(r"(?<!_lazy)_csv_button\(", non_consolidated))

    def test_report_by_type_cache_signature_includes_scope_and_report_type(self):
        signature = inspect.signature(self.financials._cached_financial_report_by_type)
        params = list(signature.parameters)
        for key in (
            "company_key",
            "start_key",
            "end_key",
            "account_key",
            "branch_key",
            "backend_key",
            "report_type_key",
        ):
            self.assertIn(key, params)

    def test_only_selected_report_type_is_built(self):
        ledger_snapshot = {
            "cumulative": {
                "Cash": {
                    "account_code": "1000",
                    "account_type": "Asset",
                    "debit": 100.0,
                    "credit": 0.0,
                    "balance": 100.0,
                }
            },
            "period": {
                "Sales": {
                    "account_code": "4000",
                    "account_type": "Income",
                    "debit": 0.0,
                    "credit": 50.0,
                    "balance": 50.0,
                }
            },
        }
        with mock.patch.object(
            self.financials,
            "_income_statement_from_balances",
            wraps=self.financials._income_statement_from_balances,
        ) as income_mock:
            with mock.patch.object(
                self.financials,
                "_cash_flow_from_reports",
                wraps=self.financials._cash_flow_from_reports,
            ) as cash_flow_mock:
                self.financials._build_financial_report_dataframe(
                    "trial_balance",
                    "demo-co",
                    ledger_snapshot=ledger_snapshot,
                )
                income_mock.assert_not_called()
                cash_flow_mock.assert_not_called()

                income_mock.reset_mock()
                cash_flow_mock.reset_mock()
                self.financials._build_financial_report_dataframe(
                    "income_statement",
                    "demo-co",
                    ledger_snapshot=ledger_snapshot,
                )
                income_mock.assert_called_once()
                cash_flow_mock.assert_not_called()


class Lv009LazyCsvTests(TestCase):
    def test_lazy_csv_does_not_encode_until_prepare_click(self):
        financials = __import__("financials")
        dataframe = mock.Mock()
        dataframe.empty = False
        dataframe.to_csv.return_value = "a,b\n1,2"

        class _SessionState(dict):
            def __getattr__(self, name):
                return self[name]

            def __setattr__(self, name, value):
                self[name] = value

        session_state = _SessionState()
        button_calls = []

        def _button(label, key=None):
            button_calls.append(key)
            return key == "_fr_csv_prepare_test_key"

        with mock.patch.object(financials.st, "session_state", session_state):
            with mock.patch.object(financials.st, "button", side_effect=_button):
                with mock.patch.object(financials.st, "download_button"):
                    financials._lazy_csv_button("Trial Balance", dataframe, "test_key")

        dataframe.to_csv.assert_called_once_with(index=False)
        self.assertIn(b"a,b", session_state["_fr_csv_blob_test_key"])


class Lv009SharedConnectionTests(TestCase):
    def setUp(self):
        self.financials = __import__("financials")

    def test_ledger_snapshot_uses_single_connection(self):
        connections = []

        class _Conn:
            def close(self):
                pass

        def _get_connection():
            conn = _Conn()
            connections.append(conn)
            return conn

        with mock.patch.object(self.financials, "get_connection", side_effect=_get_connection):
            with mock.patch.object(
                self.financials,
                "get_ledger_balances",
                side_effect=[{"Cash": {}}, {"Cash": {}}],
            ) as ledger_mock:
                snapshot = self.financials._fetch_ledger_balance_snapshot(
                    "demo-co",
                    start_date=date(2026, 1, 1),
                    end_date=date(2026, 3, 31),
                )
        self.assertEqual(len(connections), 1)
        self.assertEqual(ledger_mock.call_count, 2)
        self.assertTrue(all(call.kwargs.get("conn") is connections[0] for call in ledger_mock.call_args_list))
        self.assertIn("cumulative", snapshot)
        self.assertIn("period", snapshot)


class Lv009ReportTotalsUnchangedTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.financials = __import__("financials")

    def test_lazy_report_outputs_match_bundle_outputs(self):
        company_key = "ADMIN-PERFECTO-123"
        start_key = "none"
        end_key = date.today().isoformat()
        account_key = "none"
        branch_key = "none"
        backend_key = self.financials.get_active_db_backend()

        for cache_fn in (
            self.financials._cached_financial_reports_bundle,
            self.financials._cached_financial_report_by_type,
            self.financials._cached_ledger_balance_snapshot,
            self.financials._cached_financial_report_summary,
        ):
            cache_fn.clear()

        bundle = self.financials._cached_financial_reports_bundle(
            company_key,
            start_key,
            end_key,
            account_key,
            branch_key,
            backend_key,
        )

        for report_type_key, bundle_key in (
            ("trial_balance", "trial_balance"),
            ("income_statement", "income_statement"),
            ("balance_sheet", "balance_sheet"),
            ("cash_flow", "cash_flow"),
            ("equity", "equity"),
            ("depreciation", "depreciation"),
        ):
            payload = self.financials._cached_financial_report_by_type(
                company_key,
                start_key,
                end_key,
                account_key,
                branch_key,
                backend_key,
                report_type_key,
            )
            expected = bundle[bundle_key].fillna("").astype(str)
            actual = payload["dataframe"].fillna("").astype(str)
            pd.testing.assert_frame_equal(actual, expected)

        summary = self.financials._cached_financial_report_summary(
            company_key,
            start_key,
            end_key,
            account_key,
            branch_key,
            backend_key,
        )
        trial_balance_df = bundle["trial_balance"]
        income_statement_df = bundle["income_statement"]
        balance_sheet_df = bundle["balance_sheet"]
        self.assertAlmostEqual(
            summary["total_debits"],
            float(self.financials._safe_number(trial_balance_df.get("Debit (GHS)"))),
        )
        self.assertAlmostEqual(
            summary["net_profit"],
            float(
                self.financials._safe_number(
                    income_statement_df.loc[income_statement_df["Account"] == "Net Profit", "Amount (GHS)"]
                )
            ),
        )
        self.assertAlmostEqual(
            summary["total_assets"],
            float(
                self.financials._safe_number(
                    balance_sheet_df.loc[
                        balance_sheet_df["Category"].isin(["Current Assets", "Non-Current Assets"]),
                        "Amount (GHS)",
                    ]
                )
            ),
        )


class Lv009PortableBackendTests(TestCase):
    def test_get_ledger_balances_accepts_optional_connection(self):
        financials = __import__("financials")
        signature = inspect.signature(financials.get_ledger_balances)
        self.assertIn("conn", signature.parameters)

    def test_get_depreciation_schedule_accepts_optional_connection(self):
        financials = __import__("financials")
        signature = inspect.signature(financials.get_depreciation_schedule)
        self.assertIn("conn", signature.parameters)

    def test_financials_module_retains_sqlite_and_postgres_helpers(self):
        financials = __import__("financials")
        database = __import__("database")
        self.assertTrue(hasattr(financials, "execute_portable_query"))
        self.assertTrue(hasattr(database, "is_postgres_backend"))
        self.assertTrue(hasattr(database, "get_active_db_backend"))
