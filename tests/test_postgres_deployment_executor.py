import io
import unittest
from pathlib import Path

from postgres_deployment_executor import (
    APPLY_NOT_IMPLEMENTED_MESSAGE,
    DeploymentPhase,
    DeploymentResult,
    DeploymentStep,
    build_deployment_phases,
    format_phase_summary,
    run_deployment_apply,
    run_deployment_dry_run,
    validate_execution_allowed,
)
from postgres_staging_deployer import main as staging_main


class PostgresDeploymentExecutorTests(unittest.TestCase):
    def test_phases_build(self):
        phases = build_deployment_phases()
        self.assertEqual(len(phases), 9)
        self.assertIsInstance(phases[0], DeploymentPhase)
        self.assertIsInstance(phases[0].steps[0], DeploymentStep)
        self.assertEqual(phases[0].phase_id, "Phase 1")
        self.assertFalse(phases[0].execution_allowed)
        self.assertTrue(all(not step.execution_allowed for phase in phases for step in phase.steps))

    def test_dry_run_returns_blocked_non_executing_result(self):
        result = run_deployment_dry_run()
        self.assertIsInstance(result, DeploymentResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.mode, "dry-run")
        self.assertTrue(result.blocked)
        self.assertFalse(result.execution_allowed)
        self.assertGreater(result.planned_step_count, 0)
        self.assertIn("Dry-run only", result.message)

    def test_apply_is_blocked(self):
        result = run_deployment_apply()
        self.assertFalse(result.ok)
        self.assertEqual(result.mode, "apply")
        self.assertTrue(result.blocked)
        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.message, APPLY_NOT_IMPLEMENTED_MESSAGE)
        self.assertEqual(validate_execution_allowed(apply=True).message, APPLY_NOT_IMPLEMENTED_MESSAGE)

    def test_staging_deployer_uses_executor_dry_run(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = staging_main(["--dry-run"], output_stream=stdout, error_stream=stderr)
        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("executor dry-run", output)
        self.assertIn("Execution allowed: False", output)
        self.assertIn("Dry-run only", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_phase_summary_is_display_only(self):
        summary = format_phase_summary(run_deployment_dry_run())
        self.assertIn("display only", summary)
        self.assertIn("execution_allowed=False", summary)

    def test_safety_scan_passes(self):
        source = Path("postgres_deployment_executor.py").read_text(encoding="utf-8")
        forbidden_terms = [
            "conn.execute",
            "cursor.execute",
            "psycopg",
            "supabase",
            "sqlite3.connect",
            "create_engine",
            "connect(",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
