from unittest import mock

from test_support import ERPIsolatedTestCase


class _DescribedCursor:
    def __init__(self, rows=None, row=None, columns=(), exc=None):
        self._rows = rows or []
        self._row = row
        self.description = [(column,) for column in columns] if columns else None
        self._exc = exc

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        if self._row is not None:
            return self._row
        return self._rows[0] if self._rows else None

    def execute(self, *args, **kwargs):
        if self._exc:
            raise self._exc


class _PostgresCursor:
    description = None

    def __init__(self, parent):
        self._parent = parent
        self._rows = []
        self._row = None

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        if self._row is not None:
            return self._row
        return self._rows[0] if self._rows else None

    def execute(self, statement, params=()):
        self._parent.statements.append((statement, params))
        effect = None
        if self._parent.execute_side_effect:
            effect = self._parent.execute_side_effect.pop(0)
        if isinstance(effect, Exception):
            raise effect
        if isinstance(effect, tuple) and len(effect) == 2:
            rows, columns = effect
            if isinstance(rows, tuple) and len(columns) == 1:
                self._row = rows
                self.description = [(columns[0],)]
            else:
                self._rows = list(rows)
                self.description = [(column,) for column in columns]
            return
        if isinstance(effect, dict):
            self._rows = list(effect.get("rows") or [])
            self._row = effect.get("row")
            columns = effect.get("columns") or ()
            self.description = [(column,) for column in columns] if columns else None
            return
        self._row = (1,)
        self.description = [("value",)]


class _PostgresRawConn:
    def __init__(self, execute_side_effect=None):
        self.execute_side_effect = list(execute_side_effect or [])
        self.rollback_count = 0
        self.statements = []

    def cursor(self):
        return _PostgresCursor(self)

    def rollback(self):
        self.rollback_count += 1


class PostgresRuntimeTraceAndReportFixesTests(ERPIsolatedTestCase):
    def test_resolve_source_document_mismatches_skips_sqlite_master_on_postgres(self):
        import accounting_engine

        fake = _PostgresRawConn(
            execute_side_effect=[
                RuntimeError("should not query sqlite_master"),
            ]
        )
        managed = self.database.PostgresManagedConnection(fake)
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            accounting_engine, "db_table_exists", return_value=False
        ):
            mismatches = accounting_engine._resolve_source_document_mismatches(managed, "COMPANY-1")

        self.assertEqual(mismatches, [])
        self.assertTrue(all("sqlite_master" not in str(statement) for statement, _ in fake.statements))

    def test_missing_optional_source_document_table_does_not_crash_financial_reports(self):
        import accounting_engine

        fake = _PostgresRawConn()
        managed = self.database.PostgresManagedConnection(fake)
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            accounting_engine, "get_customer_balances", return_value=[]
        ), mock.patch.object(
            accounting_engine, "get_supplier_balances", return_value=[]
        ), mock.patch.object(
            accounting_engine, "get_account_total", return_value=0.0
        ), mock.patch.object(
            accounting_engine, "list_tables", return_value=["journal_entries"]
        ), mock.patch.object(
            accounting_engine, "db_table_exists", return_value=False
        ), mock.patch.object(
            accounting_engine, "get_chart_of_accounts_diagnostics", return_value={}
        ):
            diagnostics = accounting_engine.get_finance_integrity_diagnostics("COMPANY-1", conn=managed)

        self.assertIn("source_document_mismatches", diagnostics)
        self.assertEqual(diagnostics["source_document_mismatches"], [])
        self.assertTrue(all("sqlite_master" not in str(statement) for statement, _ in fake.statements))

    def test_postgres_managed_connection_rolls_back_after_query_exception(self):
        raw = _PostgresRawConn(execute_side_effect=[RuntimeError("first query failed"), ((42,), ("value",))])
        managed = self.database.PostgresManagedConnection(raw)
        with self.assertRaises(RuntimeError):
            managed.execute("SELECT bad FROM missing_table WHERE id = ?", (1,))
        self.assertEqual(raw.rollback_count, 1)
        result = managed.execute("SELECT 1 AS value", ()).fetchone()
        self.assertEqual(result["value"], 42)

    def test_dashboard_failed_select_does_not_poison_subsequent_reads(self):
        import modules

        raw = _PostgresRawConn(
            execute_side_effect=[
                ((0.0,), ("total",)),
                ([], ("qty", "min_stock_level")),
                RuntimeError("pos_sales unavailable"),
                ((150.0,), ("sales_total",)),
                ((0.0,), ("balance",)),
            ]
        )
        managed = self.database.PostgresManagedConnection(raw)
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            modules, "db_table_exists", return_value=True
        ), mock.patch.object(
            modules, "list_columns", return_value=[{"name": "qty"}, {"name": "min_stock_level"}, {"name": "cost_price"}]
        ), mock.patch.object(
            modules, "get_month_sales_total", return_value=0.0
        ), mock.patch.object(
            modules, "get_customer_balances", return_value=[]
        ), mock.patch.object(
            modules, "get_supplier_balances", return_value=[]
        ), mock.patch.object(
            modules, "generate_income_statement", return_value=[]
        ):
            snapshot = modules._fetch_dashboard_kpi_snapshot(managed, "COMPANY-1")

        self.assertEqual(raw.rollback_count, 1)
        self.assertEqual(snapshot["today_sales"], 150.0)
        self.assertTrue(any("journal_entries" in str(statement) for statement, _ in raw.statements))

    def test_resolve_source_document_mismatches_sqlite_behavior_unchanged(self):
        import accounting_engine

        self.conn.execute(
            "INSERT INTO invoices (company_key, approval_status, posted_entry_id, invoice_date) VALUES (?, 'Posted', NULL, '2026-01-01')",
            (self.company_key,),
        )
        self.conn.commit()
        mismatches = accounting_engine._resolve_source_document_mismatches(self.conn, self.company_key)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["table"], "invoices")
        self.assertEqual(mismatches[0]["issue"], "posted source document is missing GL impact")

    def test_sql_group_concat_uses_string_agg_on_postgres(self):
        expr = self.database.sql_group_concat("id", backend="postgres")
        self.assertIn("string_agg", expr)
        self.assertNotIn("GROUP_CONCAT", expr)

    def test_sql_group_concat_uses_group_concat_on_sqlite(self):
        expr = self.database.sql_group_concat("id", backend="sqlite")
        self.assertIn("GROUP_CONCAT", expr)

    def test_portable_date_predicates_use_cast(self):
        self.assertIn("CAST(sale_date AS date)", self.database.sql_date_equals("sale_date"))
        self.assertIn("CAST(sale_date AS date)", self.database.sql_date_on_or_after("sale_date"))
