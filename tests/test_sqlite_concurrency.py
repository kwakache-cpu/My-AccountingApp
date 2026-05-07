import sqlite3
import threading
import time
import unittest

from test_support import ERPIsolatedTestCase, build_lines


class SQLiteConcurrencyTests(ERPIsolatedTestCase):
    def _new_conn(self):
        return self.database._open_sqlite_connection(path=self.database.DB_PATH)

    def test_simultaneous_invoice_posting_remains_atomic(self):
        customer_id = self.create_customer("Concurrent Customer")
        invoice_ids = [
            self.create_invoice(customer_id=customer_id, status="Posted", amount=100.0 + index)
            for index in range(4)
        ]
        ar_id = self.account_id("Accounts Receivable", "Asset")
        revenue_id = self.account_id("Sales Revenue", "Income")
        barrier = threading.Barrier(len(invoice_ids))
        errors = []
        entry_ids = []
        lock = threading.Lock()

        def worker(index, invoice_id):
            try:
                barrier.wait(timeout=5)
                amount = 100.0 + index
                entry_id = self.engine.post_journal_entry(
                    company_key=self.company_key,
                    date=self.today,
                    description=f"Concurrent invoice {index}",
                    reference=f"CONC-INV-{index}",
                    lines=build_lines(
                        {"account_id": ar_id, "debit": amount, "credit": 0.0},
                        {"account_id": revenue_id, "debit": 0.0, "credit": amount},
                    ),
                    created_by="Bookkeeper",
                    source_table="invoices",
                    source_id=invoice_id,
                    source_type="Invoice",
                    customer_id=customer_id,
                )
                with lock:
                    entry_ids.append(entry_id)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(index, invoice_id)) for index, invoice_id in enumerate(invoice_ids)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(errors, [])
        self.assertEqual(len(entry_ids), len(invoice_ids))
        row = self.conn.execute(
            "SELECT COUNT(*) AS entries FROM journal_entries WHERE reference LIKE 'CONC-INV-%'"
        ).fetchone()
        self.assertEqual(row["entries"], len(invoice_ids))
        orphan_count = self.conn.execute(
            """
            SELECT COUNT(*) AS orphan_count
            FROM journal_lines jl
            LEFT JOIN journal_entries je ON je.id = jl.entry_id
            WHERE je.id IS NULL
            """
        ).fetchone()["orphan_count"]
        self.assertEqual(orphan_count, 0)

    def test_duplicate_concurrent_invoice_posting_allows_only_one_entry(self):
        customer_id = self.create_customer("Duplicate Concurrent Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, status="Posted", amount=77.0)
        ar_id = self.account_id("Accounts Receivable", "Asset")
        revenue_id = self.account_id("Sales Revenue", "Income")
        barrier = threading.Barrier(2)
        successes = []
        errors = []
        lock = threading.Lock()

        def worker(index):
            try:
                barrier.wait(timeout=5)
                entry_id = self.engine.post_journal_entry(
                    company_key=self.company_key,
                    date=self.today,
                    description=f"Duplicate concurrent invoice {index}",
                    reference=f"DUP-CONC-{index}",
                    lines=build_lines(
                        {"account_id": ar_id, "debit": 77.0, "credit": 0.0},
                        {"account_id": revenue_id, "debit": 0.0, "credit": 77.0},
                    ),
                    created_by="Bookkeeper",
                    source_table="invoices",
                    source_id=invoice_id,
                    source_type="Invoice",
                    customer_id=customer_id,
                )
                with lock:
                    successes.append(entry_id)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("already posted", str(errors[0]))
        row = self.conn.execute("SELECT posted_entry_id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        self.assertEqual(int(row["posted_entry_id"]), int(successes[0]))

    def test_retry_after_sqlite_write_lock(self):
        holder = self._new_conn()
        holder.execute("BEGIN IMMEDIATE")
        holder.execute(
            "INSERT INTO system_logs (timestamp, level, module_name, message) VALUES (CURRENT_TIMESTAMP, 'INFO', 'ConcurrencyTest', 'holder')"
        )
        result = {}

        def release_lock():
            time.sleep(0.25)
            holder.rollback()
            holder.close()

        releaser = threading.Thread(target=release_lock)
        releaser.start()

        def raw_write_attempt():
            raw_conn = sqlite3.connect(self.database.DB_PATH, timeout=0, check_same_thread=False)
            try:
                raw_conn.execute("BEGIN IMMEDIATE")
                raw_conn.execute(
                    "INSERT INTO system_logs (timestamp, level, module_name, message) VALUES (CURRENT_TIMESTAMP, 'INFO', 'ConcurrencyTest', 'retried')"
                )
                raw_conn.commit()
                return True
            finally:
                raw_conn.close()

        result["ok"] = self.database.with_retry_on_lock(
            raw_write_attempt,
            operation_name="retry_after_lock",
            attempts=10,
            base_delay=0.05,
        )
        releaser.join(timeout=5)

        self.assertTrue(result["ok"])
        row = self.conn.execute(
            "SELECT COUNT(*) AS row_count FROM system_logs WHERE module_name = 'ConcurrencyTest' AND message = 'retried'"
        ).fetchone()
        self.assertEqual(row["row_count"], 1)
        diagnostics = self.database.get_sqlite_concurrency_diagnostics()
        self.assertGreaterEqual(int(diagnostics.get("lock_retries") or 0), 1)

    def test_write_transaction_rolls_back_on_failure(self):
        before = self.conn.execute(
            "SELECT COUNT(*) AS row_count FROM system_logs WHERE module_name = 'RollbackTest'"
        ).fetchone()["row_count"]

        def failing_write(conn):
            conn.execute(
                "INSERT INTO system_logs (timestamp, level, module_name, message) VALUES (CURRENT_TIMESTAMP, 'INFO', 'RollbackTest', 'should rollback')"
            )
            raise RuntimeError("forced rollback")

        with self.assertRaisesRegex(RuntimeError, "forced rollback"):
            self.database.execute_write_transaction(failing_write, operation_name="rollback_test")
        after = self.conn.execute(
            "SELECT COUNT(*) AS row_count FROM system_logs WHERE module_name = 'RollbackTest'"
        ).fetchone()["row_count"]
        self.assertEqual(before, after)

    def test_backup_snapshot_during_uncommitted_write_is_valid(self):
        writer = self._new_conn()
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            "INSERT INTO system_logs (timestamp, level, module_name, message) VALUES (CURRENT_TIMESTAMP, 'INFO', 'BackupOverlapTest', 'uncommitted')"
        )
        snapshot_result = {}
        errors = []

        def run_backup():
            try:
                snapshot_result.update(self.database.backup_runtime_database_to_cloud(force=True, trigger_tables=["journal_entries"]))
            except Exception as exc:
                errors.append(exc)

        backup_thread = threading.Thread(target=run_backup)
        backup_thread.start()
        time.sleep(0.25)
        writer.rollback()
        writer.close()
        backup_thread.join(timeout=20)

        self.assertEqual(errors, [])
        self.assertIn("local_ok", snapshot_result)
        self.assertTrue(snapshot_result.get("latest_local_path"))
        backup_path = snapshot_result.get("latest_local_path")
        backup_conn = sqlite3.connect(backup_path)
        try:
            self.assertEqual(backup_conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            backup_conn.close()


if __name__ == "__main__":
    unittest.main()
