import importlib
import inspect
import os
import re
from unittest import mock

from test_support import ERPIsolatedTestCase


class PostgresE2EWriteExecutionGuardTests(ERPIsolatedTestCase):
    def test_company_insert_is_verified_before_branch_insert(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        events = []
        timeline = []

        class _FakeResult:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class _FakeDatabase:
            def get_active_db_backend(self):
                return "sqlite"

            def execute_portable_write(self, conn, sql, params):
                if "INSERT INTO companies" in sql:
                    events.append("company_inserted")
                if "INSERT INTO branches" in sql:
                    events.append("branch_inserted")

            def execute_portable_query(self, conn, sql, params):
                if "FROM companies" in sql:
                    events.append("company_verified")
                    return _FakeResult({"key": runner.TEST_COMPANY_KEY})
                return _FakeResult(None)

            def list_columns(self, conn, table_name):
                return [
                    {"name": "branch_id"},
                    {"name": "company_key"},
                    {"name": "branch_name"},
                ]

        runner._insert_company_and_branch(object(), _FakeDatabase(), timeline=timeline)

        self.assertLess(events.index("company_inserted"), events.index("company_verified"))
        self.assertLess(events.index("company_verified"), events.index("branch_inserted"))
        self.assertIn("Company inserted", [entry["event"] for entry in timeline])
        self.assertIn("Company verified", [entry["event"] for entry in timeline])

    def test_transaction_guard_remains_stable_across_seed_and_audit_steps(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        timeline = []
        checks = []

        class _FakeResult:
            def fetchone(self):
                return {"transaction_id": 1449}

        class _FakeDatabase:
            def get_active_db_backend(self):
                return "postgres"

            def execute_portable_write(self, conn, sql, params):
                checks.append(sql)

            def execute_portable_query(self, conn, sql, params):
                checks.append(sql)
                return _FakeResult()

        db = _FakeDatabase()
        expected = runner._begin_e2e_owned_transaction(object(), db)
        for label in (
            "company insert",
            "branch insert",
            "customer insert",
            "supplier insert",
            "inventory insert",
            "audit insert",
        ):
            runner._assert_transaction_stable(object(), db, expected, label=label, timeline=timeline)

        self.assertEqual(expected, 1449)
        self.assertTrue(all(entry["event"] == "Transaction ownership verified" for entry in timeline))
        self.assertIn("SELECT txid_current()", " ".join(checks))

    def test_transaction_guard_fails_on_changed_postgres_transaction_id(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")

        class _FakeResult:
            def fetchone(self):
                return {"transaction_id": 1450}

        class _FakeDatabase:
            def get_active_db_backend(self):
                return "postgres"

            def execute_portable_query(self, conn, sql, params):
                return _FakeResult()

        with self.assertRaisesRegex(RuntimeError, "E2E transaction changed after audit insert"):
            runner._assert_transaction_stable(object(), _FakeDatabase(), 1449, label="audit insert", timeline=[])

    def test_e2e_journal_path_avoids_posting_engine_helper(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        source = inspect.getsource(runner._post_entry)
        self.assertIn("_post_e2e_journal_entry", source)
        self.assertNotIn("post_accounting_impact", source)

    def test_e2e_asset_depreciation_path_avoids_production_helper(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        source = inspect.getsource(runner._run_workflows)
        self.assertIn("_run_e2e_asset_depreciation", source)
        self.assertNotIn("run_straight_line_depreciation", source)

    def test_e2e_asset_depreciation_writes_preserve_transaction_id(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        writes = []
        timeline = []

        class _FakeCursor:
            pass

        class _FakeResult:
            def fetchone(self):
                return {"transaction_id": 1452}

        class _FakeDatabase:
            def get_active_db_backend(self):
                return "postgres"

            def execute_portable_query(self, conn, sql, params=()):
                return _FakeResult()

            def execute_portable_write(self, conn, sql, params=()):
                writes.append(" ".join(str(sql).split()))
                return _FakeCursor()

            def ensure_insert_sql_returning(self, sql):
                return f"{sql} RETURNING id"

            def get_inserted_id(self, cursor):
                return 901

            def list_columns(self, conn, table_name):
                return [{"name": "id"}]

        class _FakeEngine:
            def get_account_id(self, conn, account_name, account_type=None):
                return {
                    "Depreciation Expense": 801,
                    "Accumulated Depreciation": 802,
                }[account_name]

        result = runner._run_e2e_asset_depreciation(
            object(),
            _FakeDatabase(),
            _FakeEngine(),
            77,
            "PG-E2E Asset",
            as_of_date=__import__("datetime").date(2026, 1, 31),
            expected_transaction_id=1452,
            timeline=timeline,
        )

        self.assertEqual(result["depreciation_count"], 1)
        self.assertIn("INSERT INTO journal_entries", " ".join(writes))
        self.assertIn("INSERT INTO journal_lines", " ".join(writes))
        self.assertIn("UPDATE fixed_assets", " ".join(writes))
        self.assertTrue(
            all(
                entry.get("transaction_id") == 1452
                for entry in timeline
                if entry["event"] == "Transaction ownership verified"
            )
        )

    def test_inventory_seed_returns_generated_visible_inventory_id(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        captured = {}

        class _FakeCursor:
            pass

        class _FakeRow:
            def __init__(self, value):
                self.value = value

            def keys(self):
                return ["id"]

            def __getitem__(self, key):
                if key == "id":
                    return self.value
                raise KeyError(key)

        class _FakeResult:
            def fetchone(self):
                return _FakeRow(44)

        class _FakeDatabase:
            def ensure_insert_sql_returning(self, sql):
                captured["insert_sql"] = sql
                return f"{sql} RETURNING id"

            def execute_portable_write(self, conn, sql, params):
                captured["write_sql"] = sql
                captured["write_params"] = params
                return _FakeCursor()

            def get_inserted_id(self, cursor):
                return 44

            def execute_portable_query(self, conn, sql, params):
                captured["verify_sql"] = sql
                captured["verify_params"] = params
                return _FakeResult()

        item_id = runner._insert_inventory_item(object(), _FakeDatabase())

        self.assertEqual(item_id, 44)
        self.assertIn("INSERT INTO inventory", captured["write_sql"])
        self.assertEqual(captured["verify_params"], (44, runner.TEST_COMPANY_KEY))

    def test_stock_movement_call_uses_generated_inventory_item_id_variable(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        source = inspect.getsource(runner._run_workflows)
        self.assertIn("item_id = _insert_inventory_item(conn, database)", source)
        self.assertIn("inventory_item_id=item_id", source)
        self.assertNotIn("inventory_item_id=1", source)
        self.assertNotIn("inventory_item_id=4", source)

    def test_e2e_audit_event_uses_supplied_transaction_connection(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        tx_conn = object()
        captured = {}
        events = []
        timeline = []

        class _FakeResult:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class _FakeDatabase:
            def get_active_db_backend(self):
                return "sqlite"

            def execute_portable_query(self, conn, sql, params):
                events.append("company_verified")
                return _FakeResult({"key": runner.TEST_COMPANY_KEY})

            def list_columns(self, conn, table_name):
                self.seen_conn = conn
                return [
                    {"name": "company_key"},
                    {"name": "user_role"},
                    {"name": "action"},
                    {"name": "module_name"},
                    {"name": "details"},
                    {"name": "branch_id"},
                    {"name": "action_type"},
                    {"name": "document_ref"},
                ]

            def execute_portable_write(self, conn, sql, params):
                events.append("audit_inserted")
                captured["conn"] = conn
                captured["sql"] = sql
                captured["params"] = params

        result = runner._insert_e2e_audit_event(
            tx_conn,
            _FakeDatabase(),
            user_role="Cashier",
            action="POS Sale",
            module_name="POS",
            details="detail",
            branch_id=runner.TEST_BRANCH_ID,
            action_type="pos",
            document_ref="doc",
            timeline=timeline,
        )

        self.assertIs(captured["conn"], tx_conn)
        self.assertIn("INSERT INTO audit_logs", captured["sql"])
        self.assertEqual(result["action"], "POS Sale")
        self.assertLess(events.index("company_verified"), events.index("audit_inserted"))
        self.assertIn("Company verified before audit", [entry["event"] for entry in timeline])
        self.assertIn("Audit inserted", [entry["event"] for entry in timeline])

    def test_pos_line_item_table_resolution_prefers_canonical_pos_sale_lines(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")

        class _FakeDatabase:
            def db_table_exists(self, conn, table_name):
                return table_name in {"pos_sale_lines", "pos_sale_items"}

        table_name = runner._resolve_pos_line_item_table(object(), _FakeDatabase())
        self.assertEqual(table_name, "pos_sale_lines")

    def test_postgres_identity_sync_skips_missing_pos_line_item_tables(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")

        class _FakeDatabase:
            def get_active_db_backend(self):
                return "postgres"

            def db_table_exists(self, conn, table_name):
                return False

            def execute_portable_query(self, conn, sql, params):
                raise AssertionError("Missing PostgreSQL tables must be skipped before sequence SQL")

        result = runner._sync_postgres_identity_sequence(object(), _FakeDatabase(), "pos_sale_items")
        self.assertEqual(result["status"], "SKIPPED_MISSING_TABLE")

    def test_e2e_identity_table_inserts_do_not_include_explicit_id_column(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        source = inspect.getsource(runner)
        for table_name in runner.E2E_IDENTITY_TABLES:
            pattern = re.compile(rf"INSERT\s+INTO\s+{table_name}\s*\((?P<columns>[^)]*)\)", re.IGNORECASE)
            for match in pattern.finditer(source):
                columns = [column.strip().lower() for column in match.group("columns").split(",")]
                self.assertNotIn("id", columns, f"{table_name} insert should use generated identity")

    def test_accounting_master_identity_sequences_are_synced(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        for table_name in (
            "accounts",
            "chart_of_accounts",
            "account_categories",
            "tax_codes",
            "bank_accounts",
        ):
            self.assertIn(table_name, runner.E2E_IDENTITY_TABLES)

    def test_chart_of_accounts_insert_uses_generated_id_not_hardcoded_primary_key(self):
        engine = importlib.import_module("accounting_engine")
        source = inspect.getsource(engine.get_or_create_account)
        match = re.search(r"INSERT\s+INTO\s+chart_of_accounts\s*\((?P<columns>[^)]*)\)", source, re.IGNORECASE)
        self.assertIsNotNone(match)
        columns = [column.strip().lower() for column in match.group("columns").split(",")]
        self.assertNotIn("id", columns)
        self.assertIn("ensure_insert_sql_returning", source)
        self.assertIn("get_inserted_id", source)

    def test_customer_insert_uses_generated_id_not_hardcoded_primary_key(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        captured = {}

        class _FakeDatabase:
            def ensure_insert_sql_returning(self, sql):
                captured["base_sql"] = sql
                return f"{sql} RETURNING id"

            def execute_portable_write(self, conn, sql, params):
                captured["sql"] = sql
                captured["params"] = params
                return object()

            def get_inserted_id(self, cursor):
                captured["get_inserted_id_called"] = True
                return 42

        inserted_id = runner._insert_party(object(), _FakeDatabase(), "customers", "Generated Customer")

        normalized_sql = " ".join(captured["sql"].split()).lower()
        self.assertEqual(inserted_id, 42)
        self.assertTrue(captured.get("get_inserted_id_called"))
        self.assertIn("insert into customers (company_key, name, email, phone, address, currency)", normalized_sql)
        self.assertNotIn("insert into customers (id,", normalized_sql)
        self.assertNotIn("values (1", normalized_sql)

    def test_identity_sequence_sync_skips_when_not_postgres(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")

        class _FakeDatabase:
            def get_active_db_backend(self):
                return "sqlite"

            def execute_portable_query(self, conn, sql, params):
                raise AssertionError("SQLite identity sync must not execute PostgreSQL sequence SQL")

        result = runner._sync_postgres_identity_sequence(object(), _FakeDatabase(), "customers")
        self.assertEqual(result["status"], "SKIPPED_NON_POSTGRES")

    def test_branch_insert_payload_omits_status_when_column_absent(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        payload = runner._build_branch_insert_payload({"branch_id", "company_key", "branch_name"})
        self.assertEqual(
            payload,
            {
                "branch_id": runner.TEST_BRANCH_ID,
                "company_key": runner.TEST_COMPANY_KEY,
                "branch_name": f"{runner.PHASE_PREFIX} Branch",
            },
        )
        self.assertNotIn("status", payload)

    def test_branch_insert_payload_includes_status_when_column_exists(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        payload = runner._build_branch_insert_payload({"branch_id", "company_key", "branch_name", "status"})
        self.assertEqual(payload["status"], "Active")

    def test_e2e_runner_aborts_before_writes_when_backend_is_not_postgres(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        diagnostics = runner._backend_diagnostics(self.database)
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertFalse(diagnostics["database_url_present"])

        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "sqlite",
                "ERP_ENABLE_POSTGRES_RUNTIME": "",
                "ERP_ENVIRONMENT": "",
            },
            clear=False,
        ):
            payload = runner._abort_if_not_postgres(self.database)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["overall_status"], "ABORTED")
        self.assertEqual(payload["cleanup_status"], "NOT_STARTED")
        self.assertIn("active backend is not postgres", payload["abort_reason"])
        self.assertFalse(payload["workflows"])

    def test_e2e_report_contract_exists_after_guarded_abort(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        payload = runner._abort_if_not_postgres(self.database)
        self.assertIsNotNone(payload)
        report = runner.REPORT_PATH.read_text(encoding="utf-8")
        for required_text in (
            "PostgreSQL E2E Write Execution",
            "Backend Diagnostics",
            "Workflow Results",
            "Execution Timeline",
            "Transaction Ownership",
            "Cleanup Strategy",
            "Schema Portability Notes",
            "branches.status",
            "Integer primary keys for E2E-owned rows are generated by the database",
            "PostgreSQL staging identity sequences are synchronized",
            "Accounting master identity sequences",
            "`chart_of_accounts`",
            "canonical `pos_sale_lines` table",
            "transaction-visible `inventory.id`",
            "active certification transaction connection",
            "verify company visibility on the owning transaction",
            "PostgreSQL `txid_current()`",
            "Asset depreciation certification uses E2E-local journal",
            "Production Readiness Recommendation",
            "ABORTED",
        ):
            self.assertIn(required_text, report)
