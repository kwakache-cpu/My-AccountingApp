import os
from collections import namedtuple
from types import SimpleNamespace
from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase


class _FakeCursor:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        if self._row is not None:
            return self._row
        return self._rows[0] if self._rows else None


class _DescribedCursor(_FakeCursor):
    def __init__(self, rows=None, row=None, columns=()):
        super().__init__(rows=rows, row=row)
        self.description = [(column,) for column in columns]


class _FakePostgresConn:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.statements = []
        self.params = []
        self.closed = False

    def execute(self, statement, params=()):
        self.statements.append(statement)
        self.params.append(params)
        return _FakeCursor(rows=self.rows, row=self.row)

    def close(self):
        self.closed = True


class _DescribedPostgresConn(_FakePostgresConn):
    def __init__(self, rows=None, row=None, columns=()):
        super().__init__(rows=rows, row=row)
        self.columns = tuple(columns)

    def execute(self, statement, params=()):
        self.statements.append(statement)
        self.params.append(params)
        return _DescribedCursor(rows=self.rows, row=self.row, columns=self.columns)


class _SequentialPostgresConn(_FakePostgresConn):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)

    def execute(self, statement, params=()):
        self.statements.append(statement)
        self.params.append(params)
        row, columns = self.responses.pop(0)
        return _DescribedCursor(row=row, columns=columns)


class _AttrDict(dict):
    def __getattr__(self, name):
        return self.get(name)

    def __setattr__(self, name, value):
        self[name] = value


class PostgresAuthSubscriptionRuntimePortabilityTests(ERPIsolatedTestCase):
    def test_row_helpers_support_common_runtime_row_shapes(self):
        sqlite_row = self.conn.execute(
            "SELECT 'SQLite Co' AS name, 'GHS' AS display_currency"
        ).fetchone()
        tuple_row = ("Tuple Co", "USD")
        described_columns = [SimpleNamespace(name="name"), SimpleNamespace(name="display_currency")]
        NamedRow = namedtuple("NamedRow", ["name", "display_currency"])
        named_row = NamedRow("Named Co", "EUR")
        object_row = SimpleNamespace(name="Object Co", display_currency="GBP")

        self.assertEqual(self.database.row_get({"name": "Dict Co"}, "name"), "Dict Co")
        self.assertEqual(self.database.row_get(sqlite_row, "display_currency"), "GHS")
        self.assertEqual(
            self.database.row_get(tuple_row, "display_currency", columns=("name", "display_currency")),
            "USD",
        )
        self.assertEqual(self.database.row_get(named_row, "display_currency"), "EUR")
        self.assertEqual(self.database.row_get(object_row, "display_currency"), "GBP")
        self.assertEqual(self.database.row_to_dict(tuple_row, columns=("name", "display_currency"))[0], "Tuple Co")
        self.assertEqual(
            self.database.rows_to_dicts([tuple_row], columns=("name", "display_currency"))[0]["name"],
            "Tuple Co",
        )
        self.assertEqual(
            self.database.row_to_dict(tuple_row, columns=described_columns)["display_currency"],
            "USD",
        )

    def test_execute_portable_query_returns_key_and_index_compatible_postgres_rows(self):
        fake = _DescribedPostgresConn(row=("GHS", 1.0), columns=("display_currency", "exchange_rate"))
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            row = self.database.execute_portable_query(
                fake,
                "SELECT display_currency, exchange_rate FROM system_settings WHERE id = ?",
                (1,),
            ).fetchone()

        self.assertEqual(row["display_currency"], "GHS")
        self.assertEqual(row[0], "GHS")
        self.assertIn("WHERE id = %s", fake.statements[0])
        self.assertNotIn("?", fake.statements[0])

    def test_sidebar_currency_controls_tolerate_postgres_tuple_rows(self):
        import app

        fake_conn = _DescribedPostgresConn(
            row=("GHS", "USD", 10.0),
            columns=("base_currency", "display_currency", "exchange_rate"),
        )
        fake_sidebar = SimpleNamespace(
            selectbox=mock.Mock(return_value="USD"),
            caption=mock.Mock(),
        )
        fake_st = SimpleNamespace(sidebar=fake_sidebar, session_state=_AttrDict(), rerun=mock.Mock())

        with mock.patch.object(app, "st", fake_st), mock.patch.object(
            app, "get_connection", return_value=fake_conn
        ), mock.patch.object(
            app, "_get_bog_display_rate", return_value=10.0
        ), mock.patch.object(
            self.database, "get_active_db_backend", return_value="postgres"
        ), mock.patch.object(
            self.database, "_open_sqlite_connection", side_effect=AssertionError("sqlite should not open")
        ):
            app._render_currency_sidebar_controls("currency_test")

        self.assertEqual(fake_st.session_state.display_currency, "USD")
        self.assertEqual(fake_st.session_state.exchange_rate, 10.0)
        self.assertTrue(fake_conn.closed)
        self.assertIn("SELECT COALESCE", fake_conn.statements[0])

    def test_module_currency_helpers_tolerate_postgres_tuple_rows(self):
        import modules

        display_conn = _DescribedPostgresConn(row=("USD",), columns=("currency",))
        rate_conn = _DescribedPostgresConn(
            row=("USD", 11.65),
            columns=("display_currency", "exchange_rate"),
        )
        fake_session = _AttrDict()
        with mock.patch.object(modules, "st", SimpleNamespace(session_state=fake_session)), mock.patch.object(
            modules, "get_connection", side_effect=[display_conn, rate_conn]
        ), mock.patch.object(
            self.database, "get_active_db_backend", return_value="postgres"
        ), mock.patch.object(
            self.database, "_open_sqlite_connection", side_effect=AssertionError("sqlite should not open")
        ):
            self.assertEqual(modules.get_display_currency(), "USD")
            self.assertEqual(modules.get_exchange_rate(), 11.65)

        self.assertTrue(display_conn.closed)
        self.assertTrue(rate_conn.closed)
        self.assertIn("SELECT COALESCE", display_conn.statements[0])
        self.assertIn("SELECT COALESCE", rate_conn.statements[0])

    def test_financials_portable_dataframe_reads_postgres_rows(self):
        import financials

        fake = _DescribedPostgresConn(
            rows=[("Customer One", "GHS"), ("Customer Two", "USD")],
            columns=("name", "currency"),
        )
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            df = financials._portable_read_dataframe(
                fake,
                "SELECT name, currency FROM customers WHERE company_key = ? ORDER BY name",
                ("COMPANY-1",),
            )

        self.assertEqual(list(df["name"]), ["Customer One", "Customer Two"])
        self.assertIn("company_key = %s", fake.statements[0])
        self.assertNotIn("?", fake.statements[0])

    def test_get_subscription_plan_settings_works_with_injected_postgres_like_connection(self):
        fake = _FakePostgresConn(
            rows=[
                (
                    "Basic",
                    100.0,
                    "GHS",
                    1,
                    0,
                    '{"modules": ["accounting"]}',
                    "tester",
                    "2026-06-16T00:00:00",
                )
            ]
        )
        with mock.patch.object(self.database, "is_sqlite_backend", return_value=False):
            settings = self.database.get_subscription_plan_settings(conn=fake)
        self.assertEqual(settings["Basic"]["configured_amount"], 100.0)
        self.assertFalse(fake.closed)
        self.assertTrue(any("FROM subscription_plan_settings" in sql for sql in fake.statements))

    def test_get_subscription_plan_setting_converts_placeholder_for_postgres(self):
        fake = _FakePostgresConn(
            row=(
                "Growth",
                250.0,
                "GHS",
                1,
                0,
                None,
                "tester",
                "2026-06-16T00:00:00",
            )
        )
        with mock.patch.object(self.database, "is_sqlite_backend", return_value=False), mock.patch.object(
            self.database, "get_active_db_backend", return_value="postgres"
        ):
            setting = self.database.get_subscription_plan_setting("Growth", conn=fake)
        self.assertEqual(setting["plan_name"], "Growth")
        self.assertIn("WHERE plan_name = %s", fake.statements[-1])
        self.assertNotIn("?", fake.statements[-1])
        self.assertEqual(fake.params[-1], ("Growth",))

    def test_subscription_plan_default_postgres_runtime_does_not_open_sqlite(self):
        fake = _FakePostgresConn(rows=[])
        with mock.patch.object(self.database, "get_connection", return_value=fake), mock.patch.object(
            self.database, "is_sqlite_backend", return_value=False
        ), mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            self.database, "_open_sqlite_connection", side_effect=AssertionError("sqlite should not open")
        ):
            settings = self.database.get_subscription_plan_settings()
        self.assertEqual(settings, {})
        self.assertTrue(fake.closed)

    def test_sqlite_subscription_plan_read_still_works_with_injected_sqlite_connection(self):
        self.database.upsert_subscription_plan_setting(
            self.conn,
            plan_name="SQLite Plan",
            configured_amount=42.0,
            currency="GHS",
            duration_months=1,
            updated_by="sqlite-test",
        )
        self.conn.commit()
        settings = self.database.get_subscription_plan_settings(conn=self.conn)
        self.assertEqual(settings["SQLite Plan"]["configured_amount"], 42.0)

    def test_auth_access_key_path_uses_portable_postgres_placeholders_without_sqlite(self):
        import app

        fake = _FakePostgresConn(row=("COMPANY-1", "Company One", "Active"))
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            self.database, "_open_sqlite_connection", side_effect=AssertionError("sqlite should not open")
        ):
            result = app.authenticate_access_key_read_path(fake, "COMPANY-1")
        self.assertTrue(result["matched"])
        self.assertEqual(result["user"]["role"], "Master Admin")
        self.assertTrue(fake.statements)
        self.assertIn("WHERE key = %s", fake.statements[0])
        self.assertNotIn("?", fake.statements[0])
        self.assertEqual(fake.params[0], ("COMPANY-1",))

    def test_dashboard_metric_counts_use_portable_postgres_placeholders_without_sqlite(self):
        import app

        fake = _DescribedPostgresConn(row=(10,), columns=("metric_value",))
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"), mock.patch.object(
            self.database, "_open_sqlite_connection", side_effect=AssertionError("sqlite should not open")
        ):
            counts = app.get_dashboard_metric_counts(fake, "COMPANY-1")

        self.assertEqual(counts["inventory_value"], 10)
        self.assertEqual(counts["employee_count"], 10)
        self.assertEqual(counts["fixed_asset_value"], 10)
        self.assertEqual(len(fake.statements), 3)
        self.assertTrue(all("company_key = %s" in statement for statement in fake.statements))
        self.assertTrue(all("?" not in statement for statement in fake.statements))
        self.assertTrue(all(params == ("COMPANY-1",) for params in fake.params))

    def test_company_context_repair_check_uses_postgres_connection_without_sqlite(self):
        import app

        fake = _SequentialPostgresConn(
            [
                ((1,), ("company_count",)),
                ((0,), ("admin_user_count",)),
            ]
        )
        with mock.patch.object(app, "get_connection", return_value=fake), mock.patch.object(
            self.database, "get_active_db_backend", return_value="postgres"
        ), mock.patch.object(
            self.database, "_open_sqlite_connection", side_effect=AssertionError("sqlite should not open")
        ):
            self.assertTrue(app._has_restored_data_without_admin_users())

        self.assertTrue(fake.closed)
        self.assertEqual(len(fake.statements), 2)

    def test_postgres_runtime_system_diagnostics_do_not_open_sqlite(self):
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres"
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "staging",
            },
            clear=False,
        ), mock.patch.object(
            self.database,
            "get_postgres_readiness_diagnostics",
            return_value={"active_backend": "postgres", "switch_blocked": False},
        ), mock.patch.object(
            self.database,
            "get_startup_backend_diagnostics",
            return_value={
                "schema_deployment_status": "PASSED",
                "row_reconciliation_status": "PASSED",
                "runtime_readiness_status": "PASSED",
                "runtime_dryrun_status": "PASSED",
            },
        ), mock.patch.object(
            self.database,
            "get_database_health_snapshot",
            side_effect=AssertionError("sqlite health should not run"),
        ), mock.patch.object(
            self.database,
            "get_sqlite_concurrency_diagnostics",
            side_effect=AssertionError("sqlite diagnostics should not run"),
        ), mock.patch.object(
            self.database,
            "_open_sqlite_connection",
            side_effect=AssertionError("sqlite should not open"),
        ):
            diagnostics = self.database.get_db_diagnostics()

        self.assertEqual(diagnostics["active_backend"], "postgres")
        self.assertIsNone(diagnostics["db_path"])
        self.assertIsNone(diagnostics["sqlite_concurrency"])
        self.assertEqual(diagnostics["schema_deployment_status"], "PASSED")
        self.assertNotIn("super-secret", str(diagnostics))

    def test_recovery_restore_paths_are_blocked_under_postgres_runtime(self):
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres"
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "staging",
            },
            clear=False,
        ), mock.patch.object(
            self.database,
            "get_database_health_snapshot",
            side_effect=AssertionError("sqlite health should not run"),
        ), mock.patch.object(
            self.database,
            "_open_sqlite_connection",
            side_effect=AssertionError("sqlite should not open"),
        ):
            restore = self.database.restore_latest_cloud_backup_to_local()
            recovery = self.database.attempt_production_database_recovery()

        self.assertFalse(restore["ok"])
        self.assertFalse(recovery["ok"])
        self.assertEqual(restore["stage"], "postgres_runtime_recovery_blocked")
        self.assertEqual(recovery["stage"], "postgres_runtime_recovery_blocked")
        self.assertFalse(restore["replacement_performed"])
        self.assertFalse(recovery["replacement_performed"])


if __name__ == "__main__":
    import unittest

    unittest.main()
