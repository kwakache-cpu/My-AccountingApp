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


class PostgresRowCompatibilitySweepTests(ERPIsolatedTestCase):
    def test_row_get_avoids_tuple_index_out_of_range_on_single_column_rows(self):
        row = self.database.execute_portable_query(
            self.conn,
            "SELECT 42 AS only_value",
        ).fetchone()
        self.assertEqual(self.database.row_get(row, "only_value", self.database.row_get(row, 0)), 42)
        self.assertIsNone(self.database.row_get(row, 1, None))
        self.assertIsNone(self.database.row_get(row, "missing_key", None))

    def test_compatible_row_bounds_checking_matches_row_get(self):
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            row = self.database.execute_portable_query(
                _DescribedPostgresConn(row=("GHS",), columns=("display_currency",)),
                "SELECT display_currency FROM system_settings WHERE id = ?",
                (1,),
            ).fetchone()
        self.assertEqual(row["display_currency"], "GHS")
        self.assertEqual(row[0], "GHS")
        with self.assertRaises(IndexError):
            _ = row[1]
        self.assertIsNone(self.database.row_get(row, 1, None))

    def test_fetch_scalar_reads_postgres_compatible_cursor_results(self):
        fake = _DescribedPostgresConn(row=(7,), columns=("count",))
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            value = self.database.fetch_scalar(fake, "SELECT COUNT(*) AS count FROM companies", default=0)
        self.assertEqual(value, 7)
        self.assertIn("SELECT COUNT(*) AS count", fake.statements[0])

    def test_get_master_price_per_month_tolerates_postgres_row_shape(self):
        import modules

        fake = _DescribedPostgresConn(row=(650.0,), columns=("master_price_per_month",))
        with mock.patch.object(modules, "get_connection", return_value=fake), mock.patch.object(
            self.database, "get_active_db_backend", return_value="postgres"
        ):
            price = modules.get_master_price_per_month()
        self.assertEqual(price, 650.0)
        self.assertIn("master_price_per_month", fake.statements[0])

    def test_get_financial_metrics_avoids_fetchone_index_chaining(self):
        import modules

        fake = _DescribedPostgresConn()
        responses = [
            ((12500.0,), ("revenue",)),
            ((4200.0,), ("payables",)),
            ((3,), ("invoice_count",)),
            ((2,), ("bill_count",)),
        ]

        def _sequential_execute(statement, params=()):
            fake.statements.append(statement)
            fake.params.append(params)
            row, columns = responses.pop(0)
            return _DescribedCursor(row=row, columns=columns)

        fake.execute = _sequential_execute
        with mock.patch.object(modules, "get_connection", return_value=fake), mock.patch.object(
            self.database, "get_active_db_backend", return_value="postgres"
        ):
            metrics, _chart = modules.get_financial_metrics()

        self.assertEqual(metrics["revenue"], 12500.0)
        self.assertEqual(metrics["payables"], 4200.0)
        self.assertTrue(metrics["has_data"])

    def test_branch_license_snapshot_reads_two_column_postgres_rows(self):
        fake = _DescribedPostgresConn(row=(5, 8), columns=("coalesce", "coalesce"))
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            self.database, "ensure_branch_licensing_schema_integrity", return_value=None
        ), mock.patch.object(
            self.database, "count_active_branches", return_value=2
        ):
            snapshot = self.database.get_company_branch_license_snapshot(fake, "COMPANY-1", ensure_schema=False)

        self.assertEqual(snapshot["max_branches"], 5)
        self.assertEqual(snapshot["number_of_branches"], 8)

    def test_list_branch_users_returns_named_mappings_from_compatible_rows(self):
        branch_result = self.database.create_company_branch(
            self.conn,
            self.company_key,
            branch_name="Cashier Branch",
            branch_type_key="retail",
            branch_access_key="cashier-branch-key",
            is_active=1,
        )
        self.assertTrue(branch_result["ok"], branch_result.get("reason"))
        branch_id = branch_result["branch_id"]
        create_result = self.database.create_branch_scoped_user(
            self.conn,
            self.company_key,
            branch_id,
            full_name="Cashier One",
            role="Cashier",
            login_key=f"{self.company_key}-login-1",
        )
        self.assertTrue(create_result["ok"], create_result.get("reason"))
        self.commit()
        users = self.database.list_branch_users(self.conn, self.company_key, branch_id)
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["full_name"], "Cashier One")
        self.assertEqual(users[0]["role"], "Cashier")

    def test_row_to_dict_supports_tuple_unpacking_with_columns(self):
        mapping = self.database.row_to_dict(
            ("Acme", "accra-main", "branch-1"),
            columns=("branch_name", "branch_code", "branch_id"),
        )
        self.assertEqual(mapping["branch_name"], "Acme")
        self.assertEqual(mapping[0], "Acme")
        self.assertEqual(mapping[2], "branch-1")

    def test_rows_to_dicts_preserves_missing_keys_as_safe_defaults(self):
        rows = self.database.rows_to_dicts(
            [("Only",)],
            columns=("branch_name", "branch_code"),
        )
        self.assertEqual(rows[0]["branch_name"], "Only")
        self.assertIsNone(rows[0]["branch_code"])
        self.assertIsNone(self.database.row_get(rows[0], "branch_code", None))
