import importlib
import json
import os
from unittest import mock

from test_support import ERPIsolatedTestCase, build_lines


class PostgresReportsAndCleanupReadinessTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.cleanup = importlib.import_module("migration_cleanup")
        self.financials = importlib.import_module("financials")

    def _write_summary(self, path, *, audited_at, go_status="GO WITH WARNINGS"):
        path.write_text(
            "\n".join(
                [
                    "# Migration Integrity Summary",
                    "",
                    "**Overall readiness score:** **YELLOW**",
                    f"**Recommendation:** **{go_status}**",
                    "",
                    f"**Audited at:** {audited_at}",
                    "",
                    "## Top Warnings",
                    "",
                    "- **sales_without_branch_id:** 8 (MEDIUM)",
                    "- **missing_manager_user_id:** 2 (LOW)",
                    "- **payments_without_source_reference:** 1 (LOW)",
                ]
            ),
            encoding="utf-8",
        )

    def _write_plan(self, path, *, generated_at):
        payload = {
            "generated_at": generated_at,
            "pos_missing_branch_id": [{"id": 1}],
            "missing_manager_user_id": [{"id": 1}, {"id": 2}],
            "payments_without_reference": [{"id": 1}],
            "invalid_expiry_dates": [],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_parse_timestamp_helpers(self):
        summary_text = "**Audited at:** 2026-06-01 19:46:22 UTC\n"
        plan = {"generated_at": "2026-06-01 19:46:22 UTC"}
        self.assertEqual(
            self.cleanup.parse_timestamp_from_summary_text(summary_text),
            "2026-06-01 19:46:22 UTC",
        )
        self.assertEqual(
            self.cleanup.parse_timestamp_from_plan(plan),
            "2026-06-01 19:46:22 UTC",
        )

    def test_build_readiness_marks_stale_when_timestamps_differ(self):
        summary_path = self.data_dir / "migration_integrity_summary.md"
        plan_path = self.data_dir / "migration_cleanup_plan.json"
        self._write_summary(summary_path, audited_at="2026-06-01 19:46:22 UTC")
        self._write_plan(plan_path, generated_at="2026-06-01 11:29:02 UTC")
        snapshot = self.cleanup.build_readiness_snapshot(summary_path, plan_path)
        self.assertTrue(snapshot.reports_stale)
        self.assertNotEqual(snapshot.audit_timestamp, snapshot.plan_timestamp)
        self.assertIn("timestamps differ", snapshot.refresh_hint.lower())

    def test_build_readiness_aligned_when_timestamps_match(self):
        summary_path = self.data_dir / "migration_integrity_summary.md"
        plan_path = self.data_dir / "migration_cleanup_plan.json"
        timestamp = "2026-06-01 19:46:22 UTC"
        self._write_summary(summary_path, audited_at=timestamp)
        self._write_plan(plan_path, generated_at=timestamp)
        snapshot = self.cleanup.build_readiness_snapshot(summary_path, plan_path)
        self.assertFalse(snapshot.reports_stale)
        self.assertEqual(snapshot.audit_timestamp, snapshot.plan_timestamp)
        self.assertEqual(snapshot.display_warning_total, 4)

    def test_go_status_preserves_full_text(self):
        summary_path = self.data_dir / "migration_integrity_summary.md"
        plan_path = self.data_dir / "migration_cleanup_plan.json"
        go_status = "GO WITH WARNINGS"
        self._write_summary(summary_path, audited_at="2026-06-01 19:46:22 UTC", go_status=go_status)
        self._write_plan(plan_path, generated_at="2026-06-01 19:46:22 UTC")
        snapshot = self.cleanup.build_readiness_snapshot(summary_path, plan_path)
        self.assertEqual(snapshot.go_status, go_status)

    def test_summarize_cleanup_classifications(self):
        plan = {
            "pos_missing_branch_id": [{"manual_required": True}],
            "missing_manager_user_id": [{"manual_required": False}],
            "payments_without_reference": [{"manual_required": True, "auto_fix_safe": False}],
            "invalid_expiry_dates": [],
        }
        rows = self.cleanup.summarize_cleanup_classifications(plan)
        by_key = {row["item_key"]: row for row in rows}
        self.assertEqual(by_key["pos_missing_branch_id"]["classification"], "manual_review")
        self.assertEqual(by_key["missing_manager_user_id"]["classification"], "warning")
        self.assertEqual(by_key["payments_without_reference"]["classification"], "manual_review")
        self.assertEqual(by_key["pos_missing_branch_id"]["count"], 1)

    def test_regenerate_uses_shared_timestamp_env(self):
        with mock.patch.object(self.cleanup, "run_readonly_audit_subprocess") as audit_mock, mock.patch.object(
            self.cleanup, "run_readonly_plan_subprocess"
        ) as plan_mock:
            audit_mock.return_value = {"ok": True, "stdout": "", "stderr": ""}
            plan_mock.return_value = {"ok": True, "stdout": "", "stderr": ""}
            result = self.cleanup.regenerate_migration_integrity_reports()
        self.assertTrue(result["ok"])
        timestamp = result["report_timestamp"]
        self.assertTrue(timestamp.endswith("UTC"))
        audit_env = audit_mock.call_args.kwargs["env"]
        plan_env = plan_mock.call_args.kwargs["env"]
        self.assertEqual(
            audit_env[self.cleanup.MIGRATION_REPORT_TIMESTAMP_ENV],
            plan_env[self.cleanup.MIGRATION_REPORT_TIMESTAMP_ENV],
        )
        self.assertEqual(audit_env[self.cleanup.MIGRATION_REPORT_TIMESTAMP_ENV], timestamp)

    def test_migration_report_timestamp_env_override_in_scripts(self):
        from pathlib import Path

        audit_script = importlib.import_module("scripts.run_migration_integrity_audit")
        plan_script = importlib.import_module("scripts.plan_migration_data_cleanup")
        with mock.patch.dict(os.environ, {"EKA_MIGRATION_REPORT_TIMESTAMP": "2026-06-16 09:30:00 UTC"}):
            self.assertEqual(audit_script._migration_report_timestamp(), "2026-06-16 09:30:00 UTC")
            plan = plan_script.build_cleanup_plan(Path(self.database.DB_PATH))
        self.assertEqual(plan.generated_at, "2026-06-16 09:30:00 UTC")

    def test_get_ledger_balances_returns_posted_rows(self):
        cash_id = self.account_id("Cash", "Asset")
        revenue_id = self.account_id("Sales Revenue", "Income")
        self.post_entry(
            build_lines(
                {"account_id": cash_id, "debit": 250.0, "credit": 0.0},
                {"account_id": revenue_id, "debit": 0.0, "credit": 250.0},
            ),
            description="Report readiness revenue",
            reference="RPT-READY-001",
        )
        balances = self.financials.get_ledger_balances(self.company_key)
        self.assertIn("Sales Revenue", balances)
        self.assertAlmostEqual(balances["Sales Revenue"]["credit"], 250.0)
        trial_balance = self.financials.get_trial_balance(self.company_key)
        self.assertFalse(trial_balance.empty)
        self.assertGreaterEqual(len(trial_balance), 2)

    def test_financial_report_runtime_diagnostics_include_scope(self):
        diagnostics = self.financials._financial_report_runtime_diagnostics(
            self.company_key,
            start_date=self.today,
            end_date=self.today,
        )
        self.assertEqual(diagnostics["company_key"], self.company_key)
        self.assertIn("backend", diagnostics)
        self.assertIn("journal_entries_rows", diagnostics)
        self.assertIn("journal_lines_rows", diagnostics)
        self.assertEqual(diagnostics["start_date"], self.today.isoformat())
        self.assertEqual(diagnostics["end_date"], self.today.isoformat())
