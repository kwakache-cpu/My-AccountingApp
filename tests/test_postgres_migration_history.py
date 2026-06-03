from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from postgres_deployment_executor import run_deployment_apply, run_deployment_dry_run
from postgres_migration_history import (
    MigrationEvent,
    MigrationHistory,
    MigrationStatus,
    build_phase_history,
    create_dry_run_history,
    is_valid_status_transition,
    transition_event,
)


class PostgresMigrationHistoryTests(unittest.TestCase):
    def test_history_creation(self):
        created_at = datetime(2026, 6, 3, tzinfo=timezone.utc)
        history = create_dry_run_history(
            [("Phase 1", "Migration history and system metadata")],
            deployment_id="dry-run-test",
            created_at=created_at,
        )
        self.assertIsInstance(history, MigrationHistory)
        self.assertEqual(history.deployment_id, "dry-run-test")
        self.assertEqual(history.created_at, created_at)
        self.assertEqual(len(history.events), 1)
        self.assertEqual(history.events[0].status, MigrationStatus.PENDING)

    def test_phase_event_generation(self):
        event = build_phase_history(
            "Phase 2",
            "Companies, branches, and users",
            deployment_id="deploy-1",
            rollback_point="before Phase 2",
            metadata={"execution_mode": "dry-run"},
        )
        self.assertIsInstance(event, MigrationEvent)
        self.assertEqual(event.migration_id, "deploy-1:2")
        self.assertEqual(event.phase_id, "Phase 2")
        self.assertEqual(event.status, MigrationStatus.PENDING)
        self.assertEqual(event.rollback_point, "before Phase 2")
        self.assertEqual(event.metadata["execution_mode"], "dry-run")

    def test_status_transitions(self):
        started_at = datetime(2026, 6, 3, tzinfo=timezone.utc)
        event = build_phase_history("Phase 1", "Metadata", deployment_id="deploy-2", created_at=started_at)
        self.assertTrue(is_valid_status_transition(MigrationStatus.PENDING, MigrationStatus.RUNNING))
        running = transition_event(event, MigrationStatus.RUNNING)
        completed = transition_event(running, MigrationStatus.COMPLETED, completed_at=started_at + timedelta(seconds=3))
        self.assertEqual(completed.status, MigrationStatus.COMPLETED)
        self.assertEqual(completed.duration_seconds, 3)
        self.assertFalse(is_valid_status_transition(MigrationStatus.COMPLETED, MigrationStatus.RUNNING))
        with self.assertRaises(ValueError):
            transition_event(completed, MigrationStatus.RUNNING)

    def test_executor_dry_run_history_generation(self):
        result = run_deployment_dry_run()
        self.assertIsNotNone(result.migration_history)
        self.assertEqual(len(result.migration_history.events), 9)
        self.assertTrue(all(event.status == MigrationStatus.PENDING for event in result.migration_history.events))
        self.assertFalse(result.execution_allowed)

    def test_executor_apply_history_is_blocked(self):
        result = run_deployment_apply()
        self.assertIsNotNone(result.migration_history)
        self.assertEqual(len(result.migration_history.events), 9)
        self.assertTrue(all(event.status == MigrationStatus.BLOCKED for event in result.migration_history.events))
        self.assertTrue(result.blocked)

    def test_no_db_access_or_sql_execution(self):
        for filename in ("postgres_migration_history.py", "postgres_deployment_executor.py"):
            source = Path(filename).read_text(encoding="utf-8")
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
