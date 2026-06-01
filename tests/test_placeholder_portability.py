import os
from unittest import mock

from test_support import ERPIsolatedTestCase


class PlaceholderPortabilityTests(ERPIsolatedTestCase):
    def test_db_placeholder_sqlite_and_postgres(self):
        self.assertEqual(self.database.db_placeholder(backend="sqlite"), "?")
        self.assertEqual(self.database.db_placeholder(backend="postgres"), "%s")
        self.assertEqual(self.database.db_param_placeholder(1, backend="sqlite"), "?")

    def test_db_placeholders_count(self):
        self.assertEqual(self.database.db_placeholders(0, backend="sqlite"), "")
        self.assertEqual(self.database.db_placeholders(3, backend="sqlite"), "?, ?, ?")
        self.assertEqual(self.database.db_placeholders(2, backend="postgres"), "%s, %s")

    def test_sql_for_backend_selects_dialect_sql(self):
        sqlite_sql = "SELECT 1 WHERE id = ?"
        postgres_sql = "SELECT 1 WHERE id = %s"
        self.assertEqual(
            self.database.sql_for_backend(sqlite_sql, postgres_sql, backend="sqlite"),
            sqlite_sql,
        )
        self.assertEqual(
            self.database.sql_for_backend(sqlite_sql, postgres_sql, backend="postgres"),
            postgres_sql,
        )
        self.assertEqual(
            self.database.sql_for_backend(sqlite_sql, None, backend="postgres"),
            sqlite_sql,
        )

    def test_convert_placeholders_simple_where_clause(self):
        sql = "SELECT * FROM branches WHERE company_key = ? AND branch_id = ?"
        self.assertEqual(
            self.database.convert_placeholders_for_backend(sql, backend="sqlite"),
            sql,
        )
        self.assertEqual(
            self.database.convert_placeholders_for_backend(sql, backend="postgres"),
            "SELECT * FROM branches WHERE company_key = %s AND branch_id = %s",
        )

    def test_convert_placeholders_preserves_quoted_question_marks(self):
        sql = "SELECT label FROM t WHERE note = 'What is your status?' AND id = ?"
        self.assertEqual(
            self.database.convert_placeholders_for_backend(sql, backend="postgres"),
            "SELECT label FROM t WHERE note = 'What is your status?' AND id = %s",
        )

    def test_convert_placeholders_refuses_unsafe_quoted_literal_by_default(self):
        with self.assertRaises(self.database.PlaceholderConversionError):
            self.database.convert_placeholders_for_backend(
                "SELECT * FROM t WHERE code = '?'",
                backend="postgres",
            )

    def test_convert_placeholders_allows_quoted_literal_when_not_strict(self):
        converted = self.database.convert_placeholders_for_backend(
            "SELECT * FROM t WHERE code = '?'",
            backend="postgres",
            strict_quoted_literals=False,
        )
        self.assertEqual(converted, "SELECT * FROM t WHERE code = '?'")

    def test_execute_portable_query_preserves_sqlite_behavior(self):
        self.conn.execute(
            """
            INSERT INTO branch_type_catalog (branch_type_key, branch_type_name, description, is_active)
            VALUES ('test_type', 'Test Type', 'Portable query test', 1)
            ON CONFLICT(branch_type_key) DO NOTHING
            """
        )
        self.conn.commit()
        row = self.database.execute_portable_query(
            self.conn,
            """
            SELECT branch_type_name
            FROM branch_type_catalog
            WHERE branch_type_key = ?
            """,
            ("test_type",),
            backend="sqlite",
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Test Type")

    def test_execute_portable_query_converts_on_postgres_backend(self):
        sql = "SELECT ? AS one"
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            captured = {}

            class _FakeCursor:
                def fetchone(self):
                    return (1,)

            class _FakeConn:
                def execute(self, statement, params=()):
                    captured["statement"] = statement
                    captured["params"] = params
                    return _FakeCursor()

            self.database.execute_portable_query(_FakeConn(), sql, (1,), backend="postgres")
        self.assertEqual(captured["statement"], "SELECT %s AS one")
        self.assertEqual(captured["params"], (1,))

    def test_list_company_branches_with_grants_uses_portable_query(self):
        with mock.patch.object(self.database, "execute_portable_query", wraps=self.database.execute_portable_query) as portable:
            branches = self.database.list_company_branches_with_grants(self.conn, self.company_key)
        self.assertIsInstance(branches, list)
        branch_list_sql = [
            str(call[0][1])
            for call in portable.call_args_list
            if "FROM branches b" in str(call[0][1])
        ]
        self.assertTrue(branch_list_sql)
        self.assertIn("company_key = ?", branch_list_sql[0])
