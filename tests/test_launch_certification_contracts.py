import importlib
from pathlib import Path

from test_support import ERPIsolatedTestCase


class LaunchCertificationContractsTests(ERPIsolatedTestCase):
    """Certification contracts for Phase 5B.18F production cutover and launch readiness."""

    def setUp(self):
        super().setUp()
        self.repo_root = Path(__file__).resolve().parent.parent
        self.modules = importlib.import_module("modules")

    def _read_report(self, relative_path):
        return (self.repo_root / relative_path).read_text(encoding="utf-8")

    def test_launch_certification_reports_exist(self):
        required_reports = [
            "reports/production_cutover_runbook.md",
            "reports/final_launch_approval_checklist.md",
            "reports/first_24_hour_monitoring_checklist.md",
            "reports/post_launch_support_checklist.md",
            "reports/final_security_review.md",
            "reports/final_accounting_signoff.md",
            "reports/final_customer_launch_checklist.md",
            "reports/phase_5b18f_launch_certification_summary.md",
        ]
        for relative_path in required_reports:
            text = self._read_report(relative_path)
            self.assertTrue(text.strip(), f"{relative_path} must not be empty")

    def test_manual_action_markers_present(self):
        required_reports = [
            "reports/production_cutover_runbook.md",
            "reports/final_launch_approval_checklist.md",
            "reports/first_24_hour_monitoring_checklist.md",
            "reports/post_launch_support_checklist.md",
            "reports/final_security_review.md",
            "reports/final_accounting_signoff.md",
            "reports/final_customer_launch_checklist.md",
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

    def test_launch_certification_summary_contains_readiness_and_blockers(self):
        text = self._read_report("reports/phase_5b18f_launch_certification_summary.md")
        self.assertIn("launch certification", text.lower())
        self.assertIn("90%", text)
        self.assertIn("Remaining Blockers", text)
        self.assertIn("Manual Actions Required", text)

    def test_blocker_classification_markers_present(self):
        text = self._read_report("reports/phase_5b18f_launch_certification_summary.md")
        for marker in [
            "BLOCKS LAUNCH",
            "DOES NOT BLOCK LAUNCH",
            "POST-LAUNCH IMPROVEMENT",
        ]:
            self.assertIn(marker, text, f"launch certification summary missing blocker marker: {marker}")

    def test_production_cutover_runbook_contains_cutover_flow(self):
        text = self._read_report("reports/production_cutover_runbook.md")
        for marker in [
            "App startup",
            "Dashboard loads",
            "Trial Balance",
            "rollback",
            "T-0",
            "DATABASE_URL",
            "ERP_ENVIRONMENT=production",
        ]:
            self.assertIn(marker, text, f"production_cutover_runbook.md missing marker: {marker}")

    def test_final_customer_launch_checklist_contains_launch_flow(self):
        text = self._read_report("reports/final_customer_launch_checklist.md")
        for marker in [
            "App startup",
            "Dashboard loads",
            "Trial Balance",
            "audit trail",
            "backup",
        ]:
            self.assertIn(marker, text, f"final_customer_launch_checklist.md missing marker: {marker}")

    def test_final_security_review_covers_production_secrets(self):
        text = self._read_report("reports/final_security_review.md")
        for marker in [
            "DATABASE_URL",
            "DB_BACKEND=postgres",
            "ERP_ENABLE_POSTGRES_RUNTIME=1",
            "ERP_ENVIRONMENT=production",
            "FIREBASE_SERVICE_ACCOUNT",
            "FIREBASE_DB_BACKUP_OBJECT",
            "FIREBASE_STORAGE_BUCKET",
        ]:
            self.assertIn(marker, text, f"final_security_review.md missing marker: {marker}")
