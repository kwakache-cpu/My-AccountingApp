import sqlite3
from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase


class _FakePostgresConn:
    def __init__(self):
        self.statements = []
        self.params = []

    def execute(self, statement, params=()):
        self.statements.append(statement)
        self.params.append(params)
        return self

    def cursor(self):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def commit(self):
        return None

    def close(self):
        return None


class _DescribedCursor:
    def __init__(self, rows=None, columns=()):
        self._rows = rows or []
        self.description = [(column,) for column in columns]

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _DescribedPostgresConn:
    def __init__(self, rows=None, columns=()):
        self.rows = rows or []
        self.columns = tuple(columns)
        self.statements = []
        self.params = []

    def execute(self, statement, params=()):
        self.statements.append(statement)
        self.params.append(params)
        return _DescribedCursor(rows=self.rows, columns=self.columns)

    def close(self):
        return None


class _NonClosingConn:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def close(self):
        return None


class PostgresRuntimeSqlDialectHardeningTests(ERPIsolatedTestCase):
    def test_dashboard_low_stock_query_uses_portable_postgres_placeholders(self):
        import app

        fake = _DescribedPostgresConn(
            rows=[("Widget", 2, "pcs")],
            columns=("Item", "Quantity", "Unit"),
        )
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            rows = app.execute_portable_query(
                fake,
                """
                SELECT item_name AS Item, qty AS Quantity, unit AS Unit
                FROM inventory
                WHERE company_key = ? AND qty <= 10
                ORDER BY qty ASC
                LIMIT 10
                """,
                ("COMPANY-1",),
            ).fetchall()

        self.assertEqual(len(rows), 1)
        self.assertIn("company_key = %s", fake.statements[0])
        self.assertNotIn("?", fake.statements[0])
        self.assertEqual(fake.params[0], ("COMPANY-1",))

    def test_pos_page_load_skips_sqlite_autoincrement_ddl_under_postgres(self):
        fake = _FakePostgresConn()
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            self.database.ensure_pos_sales_schema(fake)
            self.database.ensure_cashier_closings_schema(fake)
            self.database.ensure_inventory_schema_integrity(fake)

        self.assertEqual(fake.statements, [])
        combined = " ".join(fake.statements)
        self.assertNotIn("AUTOINCREMENT", combined)
        self.assertNotIn("PRAGMA", combined)

    def test_log_system_event_skips_sqlite_create_table_under_postgres(self):
        import modules

        fake = _FakePostgresConn()
        with mock.patch.object(modules, "get_connection", return_value=fake), mock.patch.object(
            modules, "is_postgres_backend", return_value=True
        ), mock.patch.object(modules, "db_table_exists", return_value=True), mock.patch.object(
            modules, "execute_portable_write", wraps=modules.execute_portable_write
        ) as portable_write:
            modules.log_system_event("INFO", "POS", "test event")

        self.assertFalse(any("AUTOINCREMENT" in statement for statement in fake.statements))
        self.assertFalse(any("CREATE TABLE" in statement for statement in fake.statements))
        portable_write.assert_called_once()
        insert_sql = portable_write.call_args[0][1]
        self.assertIn("INSERT INTO system_logs", insert_sql)

    def test_inventory_metrics_read_uses_portable_postgres_placeholders(self):
        import modules

        fake = _DescribedPostgresConn(
            rows=[(10.0, 5.0, None, 100.0)],
            columns=("quantity", "min_stock_level", "expiry_date", "total_value"),
        )
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            df = modules._portable_read_dataframe(
                fake,
                """
                SELECT qty as quantity, min_stock_level, expiry_date, (qty * cost_price) as total_value
                FROM inventory
                WHERE company_key = ?
                """,
                ("COMPANY-1",),
            )

        self.assertEqual(len(df), 1)
        self.assertIn("company_key = %s", fake.statements[0])
        self.assertNotIn("?", fake.statements[0])

    def test_sqlite_runtime_schema_self_heal_still_runs(self):
        with self.conn:
            self.database.ensure_pos_sales_schema(self.conn)
            self.database.ensure_cashier_closings_schema(self.conn)
        table_names = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        self.assertIn("pos_sales", table_names)
        self.assertIn("cashier_closings", table_names)

    def test_sqlite_log_system_event_still_creates_system_logs_table(self):
        import modules

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        wrapped_conn = _NonClosingConn(conn)
        with mock.patch.object(modules, "get_connection", return_value=wrapped_conn), mock.patch.object(
            modules, "is_postgres_backend", return_value=False
        ):
            modules.log_system_event("INFO", "Test", "sqlite path")
        row = conn.execute(
            "SELECT level, module_name, message FROM system_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "INFO")
        self.assertEqual(row[1], "Test")


if __name__ == "__main__":
    import unittest

    unittest.main()
