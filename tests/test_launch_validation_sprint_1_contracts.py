import importlib
from pathlib import Path

from test_support import ERPIsolatedTestCase


class LaunchValidationSprint1ContractsTests(ERPIsolatedTestCase):
    """Certification contracts for Launch Validation Sprint 1 live browser UAT artifacts."""

    SPRINT_1_REPORTS = [
        "reports/launch_blocker_tracker.md",
        "reports/live_browser_uat_sprint_1.md",
        "reports/role_based_live_uat_matrix.md",
        "reports/live_defect_intake_template.md",
    ]

    TRACKER_AND_DEFECT_MARKERS = [
        "Critical",
        "High",
        "Medium",
        "Low",
        "Open",
        "Fixed",
        "Verified",
        "Owner",
        "Evidence",
        "Screenshot",
        "Module",
        "Role",
        "Launch blocking decision",
    ]

    def setUp(self):
        super().setUp()
        self.repo_root = Path(__file__).resolve().parent.parent
        self.modules = importlib.import_module("modules")

    def _read_report(self, relative_path):
        return (self.repo_root / relative_path).read_text(encoding="utf-8")

    def test_launch_validation_sprint_1_reports_exist(self):
        for relative_path in self.SPRINT_1_REPORTS:
            text = self._read_report(relative_path)
            self.assertTrue(text.strip(), f"{relative_path} must not be empty")

    def test_launch_blocker_tracker_is_authoritative_register(self):
        text = self._read_report("reports/launch_blocker_tracker.md")
        self.assertIn("Authoritative", text)
        self.assertIn("Launch Blocker Register", text)
        self.assertIn("Live Defect Register", text)
        self.assertIn("BLOCKS LAUNCH", text)
        self.assertIn("91%", text)

    def test_tracker_and_defect_template_include_required_fields(self):
        combined = "\n".join(self._read_report(path) for path in [
            "reports/launch_blocker_tracker.md",
            "reports/live_defect_intake_template.md",
        ])
        for marker in self.TRACKER_AND_DEFECT_MARKERS:
            self.assertIn(marker, combined, f"tracker/defect docs missing marker: {marker}")

    def test_live_browser_uat_sprint_1_contains_critical_path_tests(self):
        text = self._read_report("reports/live_browser_uat_sprint_1.md")
        for marker in [
            "App startup",
            "Dashboard loads",
            "Trial Balance",
            "audit trail",
            "Launch blocking decision",
            "Critical",
            "High",
            "Medium",
            "Low",
            "Module",
            "Role",
            "Owner",
            "Evidence",
            "Screenshot",
        ]:
            self.assertIn(marker, text, f"live_browser_uat_sprint_1.md missing marker: {marker}")

    def test_role_based_live_uat_matrix_covers_all_roles(self):
        text = self._read_report("reports/role_based_live_uat_matrix.md")
        for role in [
            "Owner / CEO",
            "System Admin",
            "Accountant",
            "Cashier",
            "Inventory Officer",
            "HR / Payroll Officer",
            "Auditor",
            "Branch Manager",
            "Bookkeeper",
            "Staff",
        ]:
            self.assertIn(role, text, f"role_based_live_uat_matrix.md missing role: {role}")
        for marker in [
            "Module",
            "Role",
            "Owner",
            "Status",
            "Evidence",
            "Screenshot",
            "Launch blocking decision",
            "Open",
            "Fixed",
            "Verified",
        ]:
            self.assertIn(marker, text, f"role_based_live_uat_matrix.md missing marker: {marker}")

    def test_live_defect_intake_template_contains_workflow_fields(self):
        text = self._read_report("reports/live_defect_intake_template.md")
        for marker in self.TRACKER_AND_DEFECT_MARKERS:
            self.assertIn(marker, text, f"live_defect_intake_template.md missing marker: {marker}")
        self.assertIn("Steps to reproduce", text)
        self.assertIn("BLOCKS LAUNCH", text)

    def test_sprint_1_documents_cross_reference_each_other(self):
        for relative_path in [
            "reports/live_browser_uat_sprint_1.md",
            "reports/role_based_live_uat_matrix.md",
            "reports/live_defect_intake_template.md",
        ]:
            text = self._read_report(relative_path)
            self.assertIn("launch_blocker_tracker.md", text, f"{relative_path} must reference launch_blocker_tracker.md")
