import importlib
import os
from pathlib import Path
from unittest import mock

from test_support import ERPIsolatedTestCase


class FinalGoLiveContractTests(ERPIsolatedTestCase):
    """Certification contracts for Phase 5B.18D go-live blocker burndown."""

    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.repo_root = Path(__file__).resolve().parent.parent

    def _read_report(self, relative_path):
        return (self.repo_root / relative_path).read_text(encoding="utf-8")

    def test_final_go_live_reports_exist_with_required_markers(self):
        required_reports = {
            "reports/final_go_live_blockers.md": [
                "Current go-live readiness %",
                "Critical",
                "High",
                "Medium",
                "Low",
                "Blocks Production",
                "Manual Actions Required",
            ],
            "reports/deployment_secrets_checklist.md": [
                "Streamlit Secrets Template",
                "Firebase Checklist",
                "Supabase",
                "Database Backend Switching",
                "Pre-Deploy Validation",
            ],
            "reports/backup_restore_rehearsal_steps.md": [
                "Safety Guards",
                "Firebase Cloud Backup Rehearsal",
                "Cloud Restore Rehearsal",
                "Supabase",
                "Row-count reconciliation",
                "Rollback Plan",
            ],
            "reports/live_uat_checklist.md": [
                "Owner",
                "System Admin",
                "Accountant",
                "Cashier",
                "Inventory Officer",
                "HR / Payroll Officer",
                "Auditor",
                "Branch Manager",
                "Bookkeeper",
                "Staff",
                "Sign-Off",
            ],
            "reports/final_release_decision.md": [
                "NO-GO",
                "CONDITIONAL GO",
                "Day-One Deployment Checklist",
                "Post-Deployment Verification",
                "Rollback Checklist",
                "Performance Review Findings",
            ],
        }
        for relative_path, markers in required_reports.items():
            text = self._read_report(relative_path)
            for marker in markers:
                self.assertIn(marker, text, f"{relative_path} missing marker: {marker}")

    def test_all_ten_production_roles_have_permission_definitions(self):
        production_roles = [
            "Owner / CEO",
            "System Admin",
            "Accountant",
            "Cashier",
            "Inventory Officer",
            "HR / Payroll Officer",
            "Auditor / Read Only",
            "Branch Manager",
            "Bookkeeper",
            "Staff",
        ]
        for role in production_roles:
            self.assertIn(role, self.modules.ENTERPRISE_ROLE_PERMISSIONS, role)

    def test_critical_role_restrictions_remain_enforced(self):
        self.assertFalse(self.modules.user_has_permission("System Admin", "post_accounting_document"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "view_reports"))
        self.assertFalse(self.modules.user_has_permission("Staff", "post_accounting_document"))
        self.assertFalse(self.modules.user_has_permission("Auditor / Read Only", "post_accounting_document"))
        self.assertFalse(self.modules.user_has_permission("Inventory Officer", "post_accounting_document"))
        self.assertFalse(self.modules.user_has_permission("Branch Manager", "void_or_reverse_document"))
        self.assertFalse(self.modules.user_has_permission("Bookkeeper", "void_or_reverse_document"))
        self.assertFalse(self.modules.user_has_permission("Owner / CEO", "export_backup"))
        self.assertTrue(self.modules.user_has_permission("System Admin", "export_backup"))

    def test_backup_restore_diagnostics_remain_safe_and_complete(self):
        recovery = self.database.get_recovery_source_diagnostics()
        persistence = self.database.get_persistence_diagnostics()
        startup = self.database.get_startup_backend_diagnostics()

        for key in ("credentials_loaded", "credentials_source", "bucket_name", "object_name", "database_url"):
            self.assertIn(key, recovery)
        self.assertIn("latest_backup_upload_status", persistence)
        self.assertIn("latest_local_backup_status", persistence)
        self.assertIn("canonical_db_path", persistence)
        self.assertIn("active_backend", startup)
        self.assertNotIn("password", str(recovery).lower())
        self.assertNotIn("service_account_info", recovery)

    def test_postgres_runtime_blocks_sqlite_cloud_restore(self):
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": "postgresql://user:pass@example.supabase.co:6543/postgres",
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "staging",
            },
            clear=False,
        ):
            result = self.database.restore_latest_cloud_backup_to_local()
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("stage"), "postgres_runtime_recovery_blocked")

    def test_deployment_readiness_diagnostics_expose_required_fields(self):
        diagnostics = self.modules.get_deployment_readiness_diagnostics()
        for key in (
            "database_backend",
            "company_count",
            "cloud_vault_status",
            "runtime_db_valid",
            "last_local_backup",
            "last_cloud_backup",
            "schema_self_heal_status",
            "journal_integrity_status",
            "trial_balance_balanced",
            "recommended_action",
        ):
            self.assertIn(key, diagnostics)

    def test_restore_guard_mechanism_exists(self):
        self.assertTrue(hasattr(self.database, "restore_runtime_database_from_local_file"))
        self.assertTrue(hasattr(self.database, "restore_latest_cloud_backup_to_local"))
        self.assertTrue(hasattr(self.database, "run_persistence_self_test"))
        self.assertTrue(hasattr(self.database, "get_local_backup_diagnostics"))
        self.assertTrue(hasattr(self.database, "get_cloud_backup_diagnostics"))

    def test_performance_diagnostics_remain_available(self):
        sqlite_diag = self.database.get_sqlite_concurrency_diagnostics()
        postgres_diag = self.database.get_postgres_readiness_diagnostics(self.conn)
        for key in (
            "connection_opened",
            "connection_closed",
            "write_transactions_started",
            "write_transactions_committed",
            "active_write_operations",
        ):
            self.assertIn(key, sqlite_diag)
        self.assertIn("readiness_score", postgres_diag)

    def test_branch_scoped_roles_remain_branch_locked(self):
        branch_roles = {"Cashier", "Staff", "Branch Manager", "Branch_Bookkeeper"}
        for role in branch_roles:
            self.assertIn(role, self.modules.BRANCH_SCOPED_ROLES)

    def test_go_live_blocker_report_lists_remaining_critical_blockers(self):
        text = self._read_report("reports/final_go_live_blockers.md")
        for blocker in (
            "Live Firebase backup/restore",
            "Role-by-role browser UAT",
            "Production-size performance",
        ):
            self.assertIn(blocker, text)
