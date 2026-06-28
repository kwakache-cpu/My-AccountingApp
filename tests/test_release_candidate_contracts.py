import importlib
from pathlib import Path

from test_support import ERPIsolatedTestCase


class ReleaseCandidateContractsTests(ERPIsolatedTestCase):
    """Certification contracts for Phase 5B.18E release candidate readiness."""

    def setUp(self):
        super().setUp()
        self.repo_root = Path(__file__).resolve().parent.parent
        self.modules = importlib.import_module("modules")

    def _read_report(self, relative_path):
        return (self.repo_root / relative_path).read_text(encoding="utf-8")

    def test_release_candidate_reports_exist(self):
        required_reports = [
            "reports/release_candidate_checklist.md",
            "reports/live_app_smoke_test_checklist.md",
            "reports/production_rollback_checklist.md",
            "reports/operator_signoff_checklist.md",
            "reports/first_customer_onboarding_checklist.md",
            "reports/phase_5b18e_release_candidate_summary.md",
        ]
        for relative_path in required_reports:
            text = self._read_report(relative_path)
            self.assertTrue(text.strip(), f"{relative_path} must not be empty")

    def test_deployment_secrets_checklist_covers_production_items(self):
        required_markers = [
            "DATABASE_URL",
            "DB_BACKEND",
            "ERP_ENABLE_POSTGRES_RUNTIME",
            "ERP_ENVIRONMENT",
            "FIREBASE_SERVICE_ACCOUNT",
            "FIREBASE_DB_BACKUP_OBJECT",
            "FIREBASE_STORAGE_BUCKET",
        ]
        text = self._read_report("reports/deployment_secrets_checklist.md")
        for marker in required_markers:
            self.assertIn(marker, text, f"deployment_secrets_checklist.md missing marker: {marker}")

    def test_manual_action_markers_present(self):
        required_reports = [
            "reports/release_candidate_checklist.md",
            "reports/live_app_smoke_test_checklist.md",
            "reports/production_rollback_checklist.md",
            "reports/operator_signoff_checklist.md",
            "reports/first_customer_onboarding_checklist.md",
        ]
        required_markers = [
            "STREAMLIT SECRET REQUIRED",
            "FIREBASE ACTION REQUIRED",
            "DATABASE ACTION REQUIRED",
            "SUPABASE ACTION REQUIRED",
        ]
        for relative_path in required_reports:
            text = self._read_report(relative_path)
            for marker in required_markers:
                self.assertIn(marker, text, f"{relative_path} missing manual action marker: {marker}")

    def test_release_candidate_summary_contains_readiness_and_blockers(self):
        text = self._read_report("reports/phase_5b18e_release_candidate_summary.md")
        self.assertIn("release candidate", text.lower())
        self.assertIn("88%", text)
        self.assertIn("Remaining Blockers", text)
        self.assertIn("Manual Actions Required", text)

    def test_live_app_smoke_test_checklist_contains_smoke_flow(self):
        text = self._read_report("reports/live_app_smoke_test_checklist.md")
        for marker in [
            "App startup",
            "Dashboard loads",
            "Trial Balance",
            "backup object path",
            "DATABASE_URL",
            "DB_BACKEND=postgres",
            "ERP_ENABLE_POSTGRES_RUNTIME=1",
            "ERP_ENVIRONMENT=production",
        ]:
            self.assertIn(marker, text, f"live_app_smoke_test_checklist.md missing marker: {marker}")
