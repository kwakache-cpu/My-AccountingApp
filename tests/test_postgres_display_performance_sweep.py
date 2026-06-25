from types import SimpleNamespace
from unittest import mock

from test_support import ERPIsolatedTestCase


class _DescribedCursor:
    description = None

    def __init__(self, rows=(), columns=()):
        self._rows = list(rows)
        self.description = [(column,) for column in columns]

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _TimingPostgresConn:
    def __init__(self, rows=(), columns=()):
        self._rows = rows
        self._columns = columns
        self.execute_count = 0

    def cursor(self):
        return self

    def execute(self, statement, params=()):
        self.execute_count += 1
        self.last_statement = statement
        self.last_params = params
        self.description = [(column,) for column in self._columns]
        return self

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def rollback(self):
        return None


class PostgresDisplayPerformanceSweepTests(ERPIsolatedTestCase):
    def test_rows_to_dicts_preserves_cursor_description_column_names(self):
        cursor = _DescribedCursor(
            rows=[("2026-06-16 10:00:00", "COMP-1", "Main", "Admin", "Login", "Auth", "read", "REF-1", "Signed in")],
            columns=(
                "timestamp",
                "company_key",
                "branch_id",
                "user_role",
                "action",
                "module_name",
                "action_type",
                "document_ref",
                "details",
            ),
        )
        wrapped = self.database.PortableCursorResult(cursor)
        rows = self.database.rows_to_dicts(wrapped.fetchall(), columns=self.database._normalize_row_columns(cursor.description))
        self.assertEqual(rows[0]["timestamp"], "2026-06-16 10:00:00")
        self.assertEqual(rows[0]["company_key"], "COMP-1")
        self.assertEqual(rows[0]["action"], "Login")
        self.assertEqual(rows[0]["details"], "Signed in")

    def test_dataframe_from_portable_rows_preserves_audit_trail_values(self):
        import modules

        rows = [
            {
                "timestamp": "2026-06-16 10:00:00",
                "company_key": "COMP-1",
                "branch_id": "BR-1",
                "user_role": "Master Admin",
                "action": "Updated settings",
                "module_name": "System Configuration",
                "action_type": "update",
                "document_ref": "CFG-001",
                "details": "amount=150.50",
            }
        ]
        df = modules._audit_trail_dataframe(rows)
        self.assertEqual(df.iloc[0]["Timestamp"], "2026-06-16 10:00:00")
        self.assertEqual(df.iloc[0]["Company"], "COMP-1")
        self.assertEqual(df.iloc[0]["User"], "Master Admin")
        self.assertEqual(df.iloc[0]["Reference"], "CFG-001")
        self.assertEqual(float(df.iloc[0]["Amount"]), 150.5)
        self.assertEqual(df.iloc[0]["Source"], "System Configuration")

    def test_audit_trail_helper_does_not_build_all_none_rows(self):
        import modules

        fake = _TimingPostgresConn(
            rows=[
                (
                    "2026-06-16 10:00:00",
                    "COMP-1",
                    "BR-1",
                    "Master Admin",
                    "Saved invoice",
                    "Invoices",
                    "create",
                    "INV-001",
                    "amount=250",
                )
            ],
            columns=(
                "timestamp",
                "company_key",
                "branch_id",
                "user_role",
                "action",
                "module_name",
                "action_type",
                "document_ref",
                "details",
            ),
        )
        managed = self.database.PostgresManagedConnection(fake)
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            modules, "get_cached_table_column_names", return_value={"action_type", "document_ref"}
        ):
            rows = modules._fetch_audit_trail_rows(managed, "COMP-1", role="Master Admin")
            df = modules._audit_trail_dataframe(rows)

        self.assertFalse(df.empty)
        self.assertNotEqual(df.iloc[0]["Company"], None)
        self.assertEqual(df.iloc[0]["Action"], "Saved invoice")

    def test_get_customer_balances_uses_batch_query_not_per_customer_n_plus_one(self):
        import accounting_engine

        class _BatchCursor:
            description = None

            def __init__(self, parent):
                self._parent = parent

            def fetchall(self):
                rows, columns = self._parent.responses.pop(0)
                self.description = [(column,) for column in columns]
                return list(rows)

            def fetchone(self):
                rows, columns = self.responses[0]
                self.description = [(column,) for column in columns]
                return rows[0] if rows else None

            def execute(self, statement, params=()):
                self._parent.execute_count += 1
                self._parent.statements.append(statement)
                if self._parent.responses:
                    rows, columns = self._parent.responses[0]
                    self.description = [(column,) for column in columns]
                return self

        class _BatchConn:
            def __init__(self):
                self.execute_count = 0
                self.statements = []
                self.responses = [
                    ([(1, "CUST-001", "Acme Ltd", "024", "a@example.com")], ("id", "customer_id", "name", "phone", "email")),
                    ([(1, 75.0)], ("customer_id", "balance")),
                ]

            def cursor(self):
                return _BatchCursor(self)

            def rollback(self):
                return None

        fake = _BatchConn()
        managed = self.database.PostgresManagedConnection(fake)
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            rows = accounting_engine.get_customer_balances("COMP-1", conn=managed)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["balance"], 75.0)
        self.assertEqual(fake.execute_count, 2)

    def test_execute_timed_portable_query_records_timing_without_changing_results(self):
        fake = _TimingPostgresConn(rows=[(42,)], columns=("value",))
        managed = self.database.PostgresManagedConnection(fake)
        self.database.clear_postgres_query_timings()
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            self.database, "is_postgres_backend", return_value=True
        ):
            row = self.database.execute_timed_portable_query(
                managed,
                "SELECT 42 AS value",
                label="test.timed_query",
            ).fetchone()
            timings = self.database.get_postgres_query_timings(limit=5)

        self.assertEqual(self.database.row_get(row, "value"), 42)
        self.assertEqual(len(timings), 1)
        self.assertEqual(timings[0]["label"], "test.timed_query")
        self.assertGreaterEqual(timings[0]["elapsed_ms"], 0)

    def test_sqlite_customer_balances_behavior_unchanged(self):
        import accounting_engine

        self.conn.execute(
            """
            INSERT INTO customers (company_key, customer_id, name, phone, email)
            VALUES (?, 'CUST-001', 'Acme Ltd', '024', 'a@example.com')
            """,
            (self.company_key,),
        )
        self.conn.commit()
        rows = accounting_engine.get_customer_balances(self.company_key, conn=self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Acme Ltd")
        self.assertEqual(rows[0]["balance"], 0.0)
