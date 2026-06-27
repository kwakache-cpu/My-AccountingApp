import importlib
from pathlib import Path

from test_support import ERPIsolatedTestCase


class BackupRestoreReadinessTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_backup_restore_diagnostics_expose_required_evidence_without_secrets(self):
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

    def test_backup_restore_report_marks_required_manual_actions(self):
        report = Path(__file__).resolve().parent.parent / "reports" / "erp_backup_restore_rehearsal.md"
        text = report.read_text(encoding="utf-8")
        for marker in (
            "SUPABASE ACTION REQUIRED",
            "STREAMLIT SECRET REQUIRED",
            "FIREBASE ACTION REQUIRED",
            "DATABASE ACTION REQUIRED",
            "Rollback plan",
            "Restore Rehearsal",
        ):
            self.assertIn(marker, text)

    def test_backup_permission_aliases_remain_role_based(self):
        self.assertTrue(self.modules.user_has_permission("Master Admin", "backup_export"))
        self.assertTrue(self.modules.user_has_permission("System Admin", "restore_diagnostics"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "backup_export"))
        self.assertFalse(self.modules.user_has_permission("Staff", "restore_diagnostics"))
