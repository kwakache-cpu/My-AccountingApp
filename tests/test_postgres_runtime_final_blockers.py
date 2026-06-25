from types import SimpleNamespace
from unittest import mock

from test_support import ERPIsolatedTestCase


class _DescribedCursor:
    def __init__(self, rows=None, row=None, columns=()):
        self._rows = rows or []
        self._row = row
        self.description = [(column,) for column in columns]

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        if self._row is not None:
            return self._row
        return self._rows[0] if self._rows else None


class _DescribedPostgresConn:
    def __init__(self, rows=None, row=None, columns=()):
        self.rows = rows or []
        self.row = row
        self.columns = tuple(columns)
        self.statements = []
        self.params = []

    def execute(self, statement, params=()):
        self.statements.append(statement)
        self.params.append(params)
        return _DescribedCursor(rows=self.rows, row=self.row, columns=self.columns)

    def close(self):
        return None


class PostgresRuntimeFinalBlockersTests(ERPIsolatedTestCase):
    def test_prepare_postgres_sql_escapes_literal_percent_in_like_patterns(self):
        prepared = self.database.prepare_postgres_executable_sql(
            """
            SELECT 1
            FROM chart_of_accounts
            WHERE lower(name) LIKE 'sales%'
              AND company_key = ?
            """,
            backend="postgres",
        )
        self.assertIn("LIKE 'sales%%'", prepared)
        self.assertIn("company_key = %s", prepared)
        self.assertNotIn("company_key = ?", prepared)

    def test_get_customer_balance_uses_parameterized_like_and_postgres_placeholders(self):
        import accounting_engine

        fake = _DescribedPostgresConn(row=(125.5,), columns=("balance",))
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            balance = accounting_engine.get_customer_balance("COMPANY-1", 7, conn=fake)

        self.assertEqual(balance, 125.5)
        self.assertIn("LIKE lower(%s)", fake.statements[0])
        self.assertEqual(fake.params[0][2], "accounts receivable%")
        self.assertNotIn("?", fake.statements[0])

    def test_get_customer_balances_drives_pos_customer_load_without_percent_format_error(self):
        import accounting_engine

        fake = _DescribedPostgresConn(
            rows=[(1, "CUST-001", "Acme Ltd", "024", "a@example.com")],
            columns=("id", "customer_id", "name", "phone", "email"),
        )
        balance_responses = [(25.0,)]

        def _sequential_execute(statement, params=()):
            fake.statements.append(statement)
            fake.params.append(params)
            if "FROM customers" in statement:
                return _DescribedCursor(rows=fake.rows, columns=fake.columns)
            if "GROUP BY je.customer_id" in statement:
                return _DescribedCursor(rows=[(1, 25.0)], columns=("customer_id", "balance"))
            row = balance_responses.pop(0)
            return _DescribedCursor(row=row, columns=("balance",))

        fake.execute = _sequential_execute
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            rows = accounting_engine.get_customer_balances("COMPANY-1", conn=fake)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Acme Ltd")
        self.assertEqual(rows[0]["balance"], 25.0)
        self.assertTrue(all("?" not in statement for statement in fake.statements))

    def test_get_month_sales_total_uses_portable_month_predicate(self):
        import accounting_engine

        fake = _DescribedPostgresConn(row=(500.0,), columns=("sales_total",))
        with mock.patch.object(accounting_engine, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            self.database, "get_active_db_backend", return_value="postgres"
        ):
            total = accounting_engine.get_month_sales_total("COMPANY-1", year_month="2026-06", conn=fake)

        self.assertEqual(total, 500.0)
        self.assertIn("to_char(CAST(je.date AS date), 'YYYY-MM') = %s", fake.statements[0])
        self.assertIn("LIKE lower(%s)", fake.statements[0])
        self.assertEqual(fake.params[0][1], "2026-06")
        self.assertEqual(fake.params[0][2], "sales%")

    def test_pos_inventory_search_uses_portable_query_with_like_parameters(self):
        import modules

        fake = _DescribedPostgresConn(
            rows=[(1, "Widget", "W-1", "General", "BrandA", 5, 10.0, 6.0, "123", 1, 0.0, None)],
            columns=(
                "id",
                "item_name",
                "item_code",
                "category",
                "brand",
                "qty",
                "price",
                "cost_price",
                "barcode",
                "min_stock_level",
                "tax_rate",
                "expiry_date",
            ),
        )
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            rows = modules._search_inventory_for_pos(fake, "COMPANY-1", "wid")

        self.assertEqual(len(rows), 1)
        self.assertIn("LIKE LOWER(%s)", fake.statements[0])
        self.assertTrue(any("%wid%" in str(param) for param in fake.params[0]))

    def test_get_finance_integrity_diagnostics_reads_customer_balances_portably(self):
        import accounting_engine

        fake = _DescribedPostgresConn(row=(0.0,), columns=("inventory_value",))
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            accounting_engine, "get_customer_balances", return_value=[]
        ), mock.patch.object(
            accounting_engine, "get_supplier_balances", return_value=[]
        ), mock.patch.object(
            accounting_engine, "get_account_total", return_value=0.0
        ), mock.patch.object(
            accounting_engine, "list_tables", return_value=[]
        ), mock.patch.object(
            accounting_engine, "_resolve_source_document_mismatches", return_value=[]
        ), mock.patch.object(
            accounting_engine, "get_chart_of_accounts_diagnostics", return_value={}
        ):
            diagnostics = accounting_engine.get_finance_integrity_diagnostics("COMPANY-1", conn=fake)

        self.assertTrue(diagnostics["accounts_receivable"]["reconciled"])
        self.assertTrue(diagnostics["inventory"]["reconciled"])
        self.assertTrue(any("inventory" in statement.lower() for statement in fake.statements))
