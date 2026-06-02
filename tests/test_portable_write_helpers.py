from unittest import mock

from test_support import ERPIsolatedTestCase


class PortableWriteHelperTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portable_write_test (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                a TEXT,
                b INTEGER
            )
            """
        )
        self.conn.commit()

    def test_sqlite_execute_portable_write_insert_update_delete(self):
        cursor = self.database.execute_portable_write(
            self.conn,
            "INSERT INTO portable_write_test (a, b) VALUES (?, ?)",
            ("hello", 1),
            backend="sqlite",
        )
        self.assertIsNotNone(cursor)
        row = self.conn.execute(
            "SELECT a, b FROM portable_write_test WHERE a = ?",
            ("hello",),
        ).fetchone()
        self.assertEqual(row[0], "hello")
        self.assertEqual(int(row[1]), 1)

        self.database.execute_portable_write(
            self.conn,
            "UPDATE portable_write_test SET b = ? WHERE a = ?",
            (2, "hello"),
            backend="sqlite",
        )
        row = self.conn.execute(
            "SELECT b FROM portable_write_test WHERE a = ?",
            ("hello",),
        ).fetchone()
        self.assertEqual(int(row[0]), 2)

        self.database.execute_portable_write(
            self.conn,
            "DELETE FROM portable_write_test WHERE a = ?",
            ("hello",),
            backend="sqlite",
        )
        row = self.conn.execute(
            "SELECT COUNT(*) FROM portable_write_test WHERE a = ?",
            ("hello",),
        ).fetchone()
        self.assertEqual(int(row[0]), 0)

    def test_sqlite_executemany_portable_write(self):
        self.database.executemany_portable_write(
            self.conn,
            "INSERT INTO portable_write_test (a, b) VALUES (?, ?)",
            [("a1", 1), ("a2", 2), ("a3", 3)],
            backend="sqlite",
        )
        row = self.conn.execute("SELECT COUNT(*) FROM portable_write_test").fetchone()
        self.assertEqual(int(row[0]), 3)

    def test_postgres_placeholder_conversion_on_execute(self):
        captured = {}

        class _FakeConn:
            def execute(self, statement, params=()):
                captured["statement"] = statement
                captured["params"] = params
                return object()

        self.database.execute_portable_write(
            _FakeConn(),
            "UPDATE t SET a = ? WHERE id = ?",
            ("x", 10),
            backend="postgres",
        )
        self.assertEqual(captured["statement"], "UPDATE t SET a = %s WHERE id = %s")
        self.assertEqual(captured["params"], ("x", 10))

    def test_postgres_placeholder_conversion_on_executemany(self):
        captured = {}

        class _FakeConn:
            def executemany(self, statement, seq_of_params):
                captured["statement"] = statement
                captured["params"] = list(seq_of_params)
                return object()

        self.database.executemany_portable_write(
            _FakeConn(),
            "INSERT INTO t (a, b) VALUES (?, ?)",
            [("x", 1), ("y", 2)],
            backend="postgres",
        )
        self.assertEqual(captured["statement"], "INSERT INTO t (a, b) VALUES (%s, %s)")
        self.assertEqual(captured["params"], [("x", 1), ("y", 2)])

    def test_transaction_neutrality_does_not_commit(self):
        self.conn.execute("BEGIN")
        self.assertTrue(bool(getattr(self.conn, "in_transaction", False)))
        self.database.execute_portable_write(
            self.conn,
            "INSERT INTO portable_write_test (a, b) VALUES (?, ?)",
            ("txn", 1),
            backend="sqlite",
        )
        self.assertTrue(bool(getattr(self.conn, "in_transaction", False)))
        self.conn.rollback()
        row = self.conn.execute(
            "SELECT COUNT(*) FROM portable_write_test WHERE a = ?",
            ("txn",),
        ).fetchone()
        self.assertEqual(int(row[0]), 0)

    def test_execute_portable_write_uses_conn_execute_sqlite(self):
        with mock.patch.object(self.conn, "execute", wraps=self.conn.execute) as spy:
            self.database.execute_portable_write(
                self.conn,
                "INSERT INTO portable_write_test (a, b) VALUES (?, ?)",
                ("spy", 1),
                backend="sqlite",
            )
        self.assertTrue(any("INSERT INTO portable_write_test" in str(call.args[0]) for call in spy.call_args_list))

