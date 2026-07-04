"""
Permanent regression shield for completed ERP workflows.

Each class maps to a protected workflow documented in
reports/regression_lockdown_manifest.md
"""
import importlib
import inspect
import os
from unittest import TestCase, mock

from security_utils import build_user_safe_error, sanitize_error_message
from test_support import ERPIsolatedTestCase, load_isolated_modules


def _function_source(module, function_name):
    return inspect.getsource(getattr(module, function_name))


def _extract_function_block(source_text, function_name):
    block = source_text.split(f"def {function_name}(", 1)[1].split("\ndef ", 1)[0]
    return block


class RegressionLockdownLoginLogoutTests(TestCase):
    """Workflow 1: Login and secure logout."""

    def setUp(self):
        self.app = importlib.import_module("app")
        self.database = importlib.import_module("database")

    def test_authenticate_access_key_returns_active_company_master_admin(self):
        conn = mock.MagicMock()
        company_row = {"key": "CO-001", "name": "Acme Ltd", "status": "Active"}
        with mock.patch.object(self.app, "execute_portable_query") as query_mock:
            query_mock.return_value.fetchone.return_value = company_row
            result = self.app.authenticate_access_key_read_path(conn, "CO-001")
        self.assertTrue(result["matched"])
        self.assertTrue(result["active"])
        self.assertEqual(result["user"]["role"], "Master Admin")

    def test_clear_session_removes_auth_keys_and_closes_postgres_connection(self):
        state = {
            "auth": True,
            "user": {"role": "Staff"},
            "company_id": "CO-001",
            "canonical_startup_result": {"ok": True},
            "lv002b_operation_events": [],
        }
        st_stub = mock.MagicMock()
        st_stub.session_state = state
        with mock.patch.object(self.app, "st", st_stub):
            with mock.patch.object(
                self.database,
                "close_session_postgres_connection",
            ) as close_mock:
                self.app._clear_session()
        self.assertNotIn("auth", state)
        self.assertNotIn("user", state)
        self.assertNotIn("company_id", state)
        self.assertNotIn("canonical_startup_result", state)
        self.assertTrue(state.get("_clear_streamlit_caches"))
        close_mock.assert_called_once()


class RegressionLockdownStartupTests(TestCase):
    """Workflows 2–3: PostgreSQL runtime startup and SQLite fallback."""

    def setUp(self):
        self._original_env = {
            key: os.environ.get(key)
            for key in (
                "DB_BACKEND",
                "DATABASE_URL",
                "ERP_ENABLE_POSTGRES_RUNTIME",
                "ERP_ENVIRONMENT",
                "EKA_DATA_DIR",
                "ERP_PRODUCTION_MODE",
                "ERP_SAFE_STARTUP_MODE",
            )
        }

    def tearDown(self):
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _load_database(self):
        data_dir = os.path.join(os.getcwd(), ".test-tmp", "regression_lockdown_startup")
        os.makedirs(data_dir, exist_ok=True)
        database, _engine = load_isolated_modules(data_dir)
        return database

    def test_postgres_runtime_startup_selected_when_enabled(self):
        database = self._load_database()
        secret_url = "postgresql://user:secret@example.supabase.co:6543/postgres"
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "staging",
            },
            clear=False,
        ), mock.patch.object(database, "test_postgres_connection", return_value={"ok": True}), mock.patch.object(
            database, "get_connection"
        ) as get_connection, mock.patch.object(database, "_ensure_local_db_file"), mock.patch.object(
            database, "_open_sqlite_connection"
        ):
            conn = mock.MagicMock()
            conn.execute.return_value.fetchone.return_value = {"company_count": 0}
            get_connection.return_value = conn
            result = database.startup_database()
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "postgres_runtime_startup")

    def test_sqlite_fallback_when_postgres_runtime_disabled(self):
        database = self._load_database()
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": "postgresql://user:secret@example.supabase.co:6543/postgres",
                "ERP_ENABLE_POSTGRES_RUNTIME": "0",
            },
            clear=False,
        ):
            diagnostics = database.get_startup_backend_diagnostics()
        self.assertEqual(diagnostics["configured_backend"], "postgres")
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertTrue(diagnostics["should_run_sqlite_startup"])


class RegressionLockdownRegistrationTests(TestCase):
    """Workflows 4 and 6: Company registration duplicate protection and trial flow."""

    def setUp(self):
        self.modules = importlib.import_module("modules")

    def test_onboarding_blocks_duplicate_company_name_case_insensitive(self):
        class _SubmitStub:
            session_state = {}

            def header(self, *args, **kwargs):
                pass

            def info(self, *args, **kwargs):
                pass

            def form(self, *args, **kwargs):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def columns(self, spec):
                count = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
                return [self] * count

            def text_input(self, label, *args, **kwargs):
                if "Company" in str(label):
                    return "Existing Co"
                if "Email" in str(label):
                    return "admin@existing.test"
                return ""

            def selectbox(self, *args, **kwargs):
                options = args[1] if len(args) > 1 else kwargs.get("options", [])
                return options[0] if options else ""

            def form_submit_button(self, *args, **kwargs):
                return True

            def caption(self, *args, **kwargs):
                pass

            def warning(self, *args, **kwargs):
                self.last_warning = args[0] if args else kwargs.get("body")

            def error(self, *args, **kwargs):
                pass

        stub = _SubmitStub()
        conn = mock.MagicMock()
        conn.execute.return_value.fetchone.return_value = {"key": "EXISTING-CO"}
        plan = {
            "amount": 100.0,
            "currency": "GHS",
            "configured": True,
            "duration_months": 1,
            "duration_days": 0,
        }
        with mock.patch.object(self.modules, "st", stub):
            with mock.patch.object(self.modules, "get_connection", return_value=conn):
                with mock.patch.object(self.modules, "get_subscription_plans", return_value={"Starter": plan}):
                    with mock.patch.object(self.modules, "get_subscription_plan", return_value=plan):
                        with mock.patch.object(
                            self.modules,
                            "ensure_company_trial_subscription",
                        ) as trial_mock:
                            with mock.patch.object(
                                self.modules,
                                "_render_onboarding_payment_verification",
                            ):
                                self.modules.show_onboarding_payment()
        trial_mock.assert_not_called()
        self.assertIn("already exists", str(getattr(stub, "last_warning", "")).lower())

    def test_trial_subscription_creation_is_idempotent(self):
        database = importlib.import_module("database")
        data_dir = os.path.join(os.getcwd(), ".test-tmp", "regression_lockdown_trial")
        os.makedirs(data_dir, exist_ok=True)
        database, _engine = load_isolated_modules(data_dir)
        database.startup_database()
        conn = database._open_sqlite_connection(path=database.DB_PATH)
        try:
            first = database.ensure_company_trial_subscription(
                conn,
                company_key="TRIAL-001",
                company_name="Trial Co",
                contact_email="trial@example.com",
                trial_days=7,
            )
            conn.commit()
            second = database.ensure_company_trial_subscription(
                conn,
                company_key="TRIAL-001",
                company_name="Trial Co",
                contact_email="trial@example.com",
                trial_days=7,
            )
        finally:
            conn.close()
        self.assertTrue(first.get("created") or first.get("end_date"))
        self.assertEqual(first.get("end_date"), second.get("end_date"))


class RegressionLockdownPaystackTests(TestCase):
    """Workflow 5: Paystack configuration resolution."""

    def setUp(self):
        self.modules = importlib.import_module("modules")
        self._original_env = {
            key: os.environ.get(key)
            for key in (
                "PAYSTACK_SECRET_KEY",
                "PAYSTACK_PUBLIC_KEY",
                "PAYSTACK_CALLBACK_URL",
                "PAYSTACK_CURRENCY",
            )
        }

    def tearDown(self):
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_paystack_runtime_config_resolves_from_environment(self):
        os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_lockdown"
        os.environ["PAYSTACK_PUBLIC_KEY"] = "pk_test_lockdown"
        os.environ["PAYSTACK_CALLBACK_URL"] = "https://example.com/callback"
        os.environ["PAYSTACK_CURRENCY"] = "ghs"
        config = self.modules.get_paystack_runtime_config()
        diagnostics = self.modules.get_paystack_diagnostics()
        self.assertTrue(config["secret_key_present"])
        self.assertTrue(config["public_key_present"])
        self.assertTrue(config["callback_url_configured"])
        self.assertEqual(config["currency"], "GHS")
        self.assertEqual(diagnostics["currency"], "GHS")
        self.assertTrue(diagnostics["secret_key_present"])


class RegressionLockdownDashboardTests(TestCase):
    """Workflow 7: Dashboard first render."""

    def test_dashboard_defers_heavy_receivable_payable_snapshot(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        dashboard_block = _extract_function_block(content, "show_dashboard")
        bundle_block = _extract_function_block(content, "_cached_dashboard_analytics_bundle")
        self.assertNotIn("_fetch_dashboard_receivable_payable_health", bundle_block)
        self.assertIn("receivable_payable_key", dashboard_block)
        self.assertIn("loads on demand", dashboard_block.lower())

    def test_dashboard_does_not_render_admin_diagnostics(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        dashboard_block = _extract_function_block(content, "show_dashboard")
        for marker in (
            "render_runtime_admin_diagnostics_suite",
            "render_lv002_postgres_performance_panel",
            "render_lv003_hot_path_panel",
            "LV-001 Live Validation Diagnostics",
        ):
            self.assertNotIn(marker, dashboard_block)


class RegressionLockdownPosTests(ERPIsolatedTestCase):
    """Workflows 8–9: POS sale and controlled correction."""

    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database.ensure_pos_sales_schema(self.conn)
        self.conn.execute(
            "INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name) VALUES (?, ?, ?)",
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.commit()

    def test_pos_sale_persists_with_valid_identity(self):
        sale_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            "LOCKDOWN-POS-001",
            {
                "receipt_number": "LOCKDOWN-POS-001",
                "sale_date": "2026-04-24",
                "sale_datetime": "2026-04-24 10:00:00",
                "cashier": "Cashier Lockdown",
                "payment_method": "Cash",
                "subtotal": 25.0,
                "discount_total": 0.0,
                "tax_total": 0.0,
                "grand_total": 25.0,
            },
            [
                {
                    "inventory_item_id": None,
                    "name": "Lockdown Item",
                    "item_code": "LD-1",
                    "barcode": "",
                    "qty": 1.0,
                    "price": 25.0,
                    "line_discount": 0.0,
                    "tax_rate": 0.0,
                    "line_total": 25.0,
                    "cost_price": 0.0,
                }
            ],
        )
        self.assertGreater(int(sale_id), 0)
        row = self.conn.execute(
            "SELECT grand_total, receipt_number FROM pos_sales WHERE id = ?",
            (sale_id,),
        ).fetchone()
        self.assertEqual(float(row["grand_total"]), 25.0)

    def test_controlled_pos_correction_requires_reason_and_permission(self):
        sale_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            "LOCKDOWN-CORR-001",
            {
                "receipt_number": "LOCKDOWN-CORR-001",
                "sale_date": "2026-04-24",
                "sale_datetime": "2026-04-24 11:00:00",
                "cashier": "Cashier A",
                "payment_method": "Cash",
                "subtotal": 40.0,
                "discount_total": 0.0,
                "tax_total": 0.0,
                "grand_total": 40.0,
            },
            [],
        )
        with self.assertRaises(PermissionError):
            self.modules.controlled_correct_pos_sale_metadata(
                self.conn,
                company_key=self.company_key,
                sale_id=sale_id,
                actor_role="Cashier",
                reason="",
                new_sale_date="2026-04-23",
                branch_id="MAIN",
            )


class RegressionLockdownFinancialReportsTests(TestCase):
    """Workflow 10: Financial Reports lazy loading."""

    def test_financial_reports_lazy_loading_contract(self):
        financials = importlib.import_module("financials")
        source = inspect.getsource(financials.show_financial_reports)
        self.assertIn("st.radio", source)
        self.assertIn("_cached_financial_report_by_type", source)
        self.assertIn("_lazy_csv_button", source)
        self.assertNotIn("render_runtime_admin_diagnostics_suite", source)


class RegressionLockdownSystemConfigTests(TestCase):
    """Workflows 11 and 15: System Configuration / no UI DDL."""

    def test_show_company_setup_has_no_ddl(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        setup_block = _extract_function_block(content, "show_company_setup")
        for forbidden in ("ALTER TABLE", "ADD COLUMN", "CREATE INDEX", "CREATE TABLE"):
            self.assertNotIn(forbidden, setup_block)

    def test_users_user_id_schema_integrity_is_idempotent(self):
        database = importlib.import_module("database")
        conn = mock.MagicMock()
        with mock.patch.object(database, "db_table_exists", return_value=True):
            with mock.patch.object(database, "_get_existing_columns", return_value={"user_id", "login_key"}):
                with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                    first = database.ensure_users_user_id_schema_integrity(conn)
                    second = database.ensure_users_user_id_schema_integrity(conn)
        self.assertTrue(first["user_id_column_present"])
        self.assertFalse(first["user_id_column_added"])
        self.assertTrue(second["user_id_column_present"])
        conn.execute.assert_not_called()


class RegressionLockdownStaffRoleTests(ERPIsolatedTestCase):
    """Workflow 12: Staff/user/role setup."""

    def test_staff_role_cannot_manage_users(self):
        modules = importlib.import_module("modules")
        self.assertFalse(modules.user_has_permission("Staff", "manage_users"))
        self.assertFalse(modules.user_has_permission("Cashier", "manage_users"))

    def test_master_admin_can_manage_users(self):
        modules = importlib.import_module("modules")
        self.assertTrue(modules.user_has_permission("Master Admin", "manage_users"))

    def test_staff_assignment_lists_company_users(self):
        branch_id = "BR-LOCKDOWN"
        self.conn.execute(
            "INSERT INTO branches (branch_id, company_key, branch_name) VALUES (?, ?, ?)",
            (branch_id, self.company_key, "Lockdown Branch"),
        )
        self.conn.execute(
            """
            INSERT INTO users (company_key, branch_id, login_key, password_hash, full_name, role, status, user_id)
            VALUES (?, ?, ?, ?, ?, ?, 'Active', ?)
            """,
            (self.company_key, branch_id, "staff-key-1", "hash", "Lockdown Staff", "Staff", "USR-LOCK-1"),
        )
        self.commit()
        staff_rows = self.database.list_company_staff_for_assignment(self.conn, self.company_key)
        names = {row["full_name"] for row in staff_rows}
        self.assertIn("Lockdown Staff", names)


class RegressionLockdownMigrationVisibilityTests(TestCase):
    """Workflow 13: Migration Cleanup hidden from client pages."""

    def setUp(self):
        self.modules = importlib.import_module("modules")

    def test_migration_cleanup_hidden_from_client_surfaces(self):
        for role in ("Demo", "Staff", "Cashier", "Accountant", "Owner", "Bookkeeper"):
            self.assertFalse(
                self.modules.can_render_migration_cleanup_diagnostics(role, "dashboard")
            )
            self.assertFalse(
                self.modules.can_render_migration_cleanup_diagnostics(role, "system_configuration")
            )

    def test_migration_cleanup_lazy_on_admin_surfaces(self):
        source = inspect.getsource(self.modules.render_runtime_admin_diagnostics_suite)
        self.assertIn("_render_migration_cleanup_diagnostics_lazy", source)


class RegressionLockdownAdminDiagnosticsTests(TestCase):
    """Workflow 14: Dev/System diagnostics visible only to admin roles."""

    def setUp(self):
        self.modules = importlib.import_module("modules")

    def test_admin_diagnostics_roles(self):
        for role in ("Dev", "Master Admin", "System Admin"):
            self.assertTrue(self.modules.can_view_runtime_admin_diagnostics(role))
        for role in ("Staff", "Cashier", "Accountant", "Owner / CEO", "Bookkeeper"):
            self.assertFalse(self.modules.can_view_runtime_admin_diagnostics(role))

    def test_admin_diagnostics_blocked_on_client_surfaces(self):
        self.assertFalse(self.modules.can_render_admin_diagnostics_surface("dashboard"))
        self.assertFalse(self.modules.can_render_admin_diagnostics_surface("financial_reports"))


class RegressionLockdownUserSafeErrorsTests(TestCase):
    """Workflow 16: No raw DuplicateColumn / UNIQUE constraint errors shown to users."""

    def test_duplicate_column_hidden_from_client_roles(self):
        raw = 'psycopg2.errors.DuplicateColumn: column "user_id" already exists'
        for role in ("Staff", "Accountant", "Owner / CEO", "Cashier", "Bookkeeper"):
            message = build_user_safe_error(raw, role)
            self.assertNotIn("DuplicateColumn", message)
            self.assertNotIn("user_id", message)

    def test_unique_constraint_hidden_from_client_roles(self):
        raw = 'UNIQUE constraint failed: companies.key'
        message = build_user_safe_error(raw, "Staff")
        self.assertNotIn("UNIQUE constraint", message)

    def test_admin_roles_may_receive_sanitized_details(self):
        raw = 'psycopg2.errors.DuplicateColumn: column "user_id" already exists'
        message = build_user_safe_error(raw, "Dev")
        self.assertIn("Details:", message)
        self.assertIn("DuplicateColumn", message)
        client_message = build_user_safe_error(raw, "Staff")
        self.assertNotIn("DuplicateColumn", client_message)


class RegressionLockdownClientNavigationTests(TestCase):
    """Workflows 17–18: No LV diagnostics or deep audit on client workflow pages."""

    _CLIENT_WORKFLOW_FUNCTIONS = (
        "show_dashboard",
        "show_pos",
        "show_inventory",
        "show_financial_reports",
    )

    _FORBIDDEN_CLIENT_MARKERS = (
        "render_runtime_admin_diagnostics_suite",
        "render_lv002_postgres_performance_panel",
        "render_lv003_hot_path_panel",
        "render_lv006_startup_pipeline_panel",
        "render_lv007_warmup_panel",
        "get_live_validation_lv001_diagnostics",
        "build_operations_console_full_audit",
        "_init_modules_firebase_app",
        "restore_latest_cloud_backup_to_local",
    )

    def test_client_workflow_pages_exclude_admin_and_deep_audit_calls(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        financials_path = os.path.join(os.getcwd(), "financials.py")
        with open(modules_path, encoding="utf-8") as handle:
            modules_content = handle.read()
        with open(financials_path, encoding="utf-8") as handle:
            financials_content = handle.read()

        for function_name in ("show_dashboard", "show_pos", "show_inventory"):
            block = _extract_function_block(modules_content, function_name)
            for marker in self._FORBIDDEN_CLIENT_MARKERS:
                self.assertNotIn(marker, block, msg=f"{function_name} must not call {marker}")

        reports_block = _extract_function_block(financials_content, "show_financial_reports")
        for marker in self._FORBIDDEN_CLIENT_MARKERS:
            self.assertNotIn(marker, reports_block, msg=f"show_financial_reports must not call {marker}")

    def test_process_warmup_skips_heavy_client_navigation_paths(self):
        modules = importlib.import_module("modules")
        skipped = set(modules._WARMUP_SKIP_ITEMS)
        for item in (
            "cloud_backup_download",
            "firebase_verification",
            "subscription_billing",
            "full_health_audit",
            "financial_reports",
        ):
            self.assertIn(item, skipped)
