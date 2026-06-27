from pathlib import Path

from test_support import ERPIsolatedTestCase


class PerformanceCertificationContractTests(ERPIsolatedTestCase):
    def test_performance_diagnostics_are_available(self):
        sqlite_diag = self.database.get_sqlite_concurrency_diagnostics()
        postgres_diag = self.database.get_postgres_readiness_diagnostics(self.conn)
        timings = self.database.get_postgres_query_timings(limit=5)

        for key in (
            "connection_opened",
            "connection_closed",
            "write_transactions_started",
            "write_transactions_committed",
            "write_transactions_rolled_back",
            "active_write_operations",
            "longest_write_seconds",
        ):
            self.assertIn(key, sqlite_diag)
        self.assertIn("readiness_score", postgres_diag)
        self.assertIsInstance(timings, list)

    def test_performance_report_contract_includes_required_surfaces(self):
        report = Path(__file__).resolve().parent.parent / "reports" / "erp_performance_certification.md"
        text = report.read_text(encoding="utf-8")
        for required in (
            "Dashboard load time",
            "POS load time",
            "Financial Reports load time",
            "Audit Trail load time",
            "AR/AP aging speed",
            "N+1",
            "connection leaks",
            "transaction leaks",
            "slow PostgreSQL queries",
            "Current performance readiness %",
        ):
            self.assertIn(required, text)

    def test_timed_query_helper_preserves_query_results(self):
        row = self.database.execute_timed_portable_query(
            self.conn,
            "SELECT COUNT(*) AS company_count FROM companies WHERE key = ?",
            (self.company_key,),
            label="performance_contract_company_count",
        ).fetchone()
        self.assertEqual(int(row["company_count"]), 1)
