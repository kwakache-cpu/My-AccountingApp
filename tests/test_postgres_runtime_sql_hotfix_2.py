import sqlite3
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


class PostgresRuntimeSqlHotfix2Tests(ERPIsolatedTestCase):
    def test_dashboard_inventory_kpi_query_uses_postgres_placeholders(self):
        import modules

        fake = _DescribedPostgresConn(row=(1250.0,), columns=("total",))
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            modules, "list_columns", return_value=[]
        ), mock.patch.object(
            modules, "get_month_sales_total", return_value=0.0
        ), mock.patch.object(
            modules, "get_customer_balances", return_value=[]
        ), mock.patch.object(
            modules, "get_supplier_balances", return_value=[]
        ), mock.patch.object(
            modules, "generate_income_statement", return_value=[]
        ), mock.patch.object(
            modules, "ensure_pos_sales_schema", return_value=None
        ):
            snapshot = modules._fetch_dashboard_kpi_snapshot(fake, "COMPANY-1")

        self.assertEqual(snapshot["inventory_value"], 1250.0)
        inventory_sql = fake.statements[0]
        self.assertIn("FROM inventory WHERE company_key = %s", inventory_sql.replace("\n", " "))
        self.assertNotIn("?", inventory_sql)

    def test_pos_customer_balances_query_is_valid_postgres_sql(self):
        import accounting_engine

        fake = _DescribedPostgresConn(
            rows=[(1, "CUST-001", "Acme Ltd", "024", "a@example.com")],
            columns=("id", "customer_id", "name", "phone", "email"),
        )
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            accounting_engine, "get_customer_balance", return_value=0.0
        ):
            rows = accounting_engine.get_customer_balances("COMPANY-1", conn=fake)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Acme Ltd")
        customer_sql = fake.statements[0]
        self.assertIn("WHERE company_key = %s", customer_sql)
        self.assertIn("ORDER BY customers.name", customer_sql)
        self.assertNotIn("ORDER BY name", customer_sql.replace("customers.name", ""))
        self.assertNotIn("?", customer_sql)

    def test_sqlite_customer_balances_still_order_by_name(self):
        import accounting_engine

        self.conn.execute(
            "INSERT INTO customers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')",
            ("COMPANY-1", "Zulu Corp", "z@example.com", "111"),
        )
        self.conn.execute(
            "INSERT INTO customers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')",
            ("COMPANY-1", "Alpha Corp", "a@example.com", "222"),
        )
        self.conn.commit()
        with mock.patch.object(accounting_engine, "get_customer_balance", return_value=0.0):
            rows = accounting_engine.get_customer_balances("COMPANY-1", conn=self.conn)
        self.assertEqual([row["name"] for row in rows], ["Alpha Corp", "Zulu Corp"])

    def test_sqlite_dashboard_inventory_kpi_still_reads_inventory(self):
        import modules

        self.conn.execute(
            "INSERT INTO companies (key, name, status) VALUES (?, ?, 'Active')",
            ("COMPANY-1", "Test Co"),
        )
        self.conn.execute(
            """
            INSERT INTO inventory (company_key, item_name, qty, cost_price, min_stock_level)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("COMPANY-1", "Widget", 5, 10.0, 10),
        )
        self.conn.commit()
        with mock.patch.object(modules, "get_month_sales_total", return_value=0.0), mock.patch.object(
            modules, "get_customer_balances", return_value=[]
        ), mock.patch.object(
            modules, "get_supplier_balances", return_value=[]
        ), mock.patch.object(
            modules, "generate_income_statement", return_value=[]
        ), mock.patch.object(
            modules, "ensure_pos_sales_schema", return_value=None
        ):
            snapshot = modules._fetch_dashboard_kpi_snapshot(self.conn, "COMPANY-1")
        self.assertEqual(snapshot["inventory_value"], 50.0)
        self.assertEqual(snapshot["low_stock_count"], 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
