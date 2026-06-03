from test_support import ERPIsolatedTestCase


class _MockCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _MockConnection:
    def __init__(self, rows=None):
        self.rows = list(rows or [(True,)])
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((str(sql), tuple(params or ())))
        return _MockCursor(self.rows)


class SchemaIntrospectionHelperTests(ERPIsolatedTestCase):
    def test_sqlite_table_column_and_index_helpers(self):
        self.assertTrue(self.database.db_table_exists(self.conn, "companies"))
        self.assertTrue(self.database.db_column_exists(self.conn, "companies", "key"))
        self.assertTrue(self.database.db_index_exists(self.conn, "idx_branches_company", table_name="branches"))
        self.assertIn("companies", self.database.list_tables(self.conn))
        self.assertTrue(any(column["name"] == "key" for column in self.database.list_columns(self.conn, "companies")))
        self.assertTrue(any(index["name"] == "idx_branches_company" for index in self.database.list_indexes(self.conn, "branches")))

    def test_postgres_table_exists_uses_information_schema_and_converts_placeholder(self):
        conn = _MockConnection(rows=[(True,)])
        self.assertTrue(self.database.db_table_exists(conn, "companies", backend="postgres"))
        sql, params = conn.calls[-1]
        self.assertIn("information_schema.tables", sql)
        self.assertIn("table_schema = current_schema()", sql)
        self.assertIn("table_name = %s", sql)
        self.assertEqual(params, ("companies",))

    def test_postgres_column_exists_uses_information_schema_and_converts_placeholders(self):
        conn = _MockConnection(rows=[(True,)])
        self.assertTrue(self.database.db_column_exists(conn, "companies", "key", backend="postgres"))
        sql, params = conn.calls[-1]
        self.assertIn("information_schema.columns", sql)
        self.assertIn("table_name = %s", sql)
        self.assertIn("column_name = %s", sql)
        self.assertEqual(params, ("companies", "key"))

    def test_postgres_index_helpers_use_pg_indexes(self):
        conn = _MockConnection(rows=[(True,)])
        self.assertTrue(
            self.database.db_index_exists(
                conn,
                "idx_branches_company",
                table_name="branches",
                backend="postgres",
            )
        )
        sql, params = conn.calls[-1]
        self.assertIn("pg_indexes", sql)
        self.assertIn("indexname = %s", sql)
        self.assertIn("tablename = %s", sql)
        self.assertEqual(params, ("idx_branches_company", "branches"))

    def test_postgres_list_helpers_use_catalog_sources(self):
        table_conn = _MockConnection(rows=[("companies",), ("branches",)])
        self.assertEqual(self.database.list_tables(table_conn, backend="postgres"), ["companies", "branches"])
        self.assertIn("information_schema.tables", table_conn.calls[-1][0])

        column_conn = _MockConnection(rows=[("key", 1, "text", "NO", None, True)])
        columns = self.database.list_columns(column_conn, "companies", backend="postgres")
        self.assertEqual(columns[0]["name"], "key")
        self.assertTrue(columns[0]["primary_key"])
        self.assertIn("information_schema.columns", column_conn.calls[-1][0])
        self.assertEqual(column_conn.calls[-1][1], ("companies",))

        index_conn = _MockConnection(rows=[("idx_companies_name", "companies", "CREATE UNIQUE INDEX idx_companies_name ON companies (name)")])
        indexes = self.database.list_indexes(index_conn, "companies", backend="postgres")
        self.assertEqual(indexes[0]["name"], "idx_companies_name")
        self.assertTrue(indexes[0]["unique"])
        self.assertIn("pg_indexes", index_conn.calls[-1][0])

    def test_postgres_foreign_key_exists_uses_information_schema(self):
        conn = _MockConnection(rows=[(True,)])
        self.assertTrue(
            self.database.db_foreign_key_exists(
                conn,
                "branches",
                column_name="company_key",
                foreign_table="companies",
                foreign_column="key",
                backend="postgres",
            )
        )
        sql, params = conn.calls[-1]
        self.assertIn("information_schema.table_constraints", sql)
        self.assertIn("FOREIGN KEY", sql)
        self.assertIn("tc.table_name = %s", sql)
        self.assertIn("kcu.column_name = %s", sql)
        self.assertEqual(params, ("branches", "company_key", "companies", "key"))
