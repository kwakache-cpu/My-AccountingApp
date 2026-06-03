from pathlib import Path
import unittest

from postgres_validation_queries import (
    VALIDATION_CATEGORIES,
    ValidationExpectation,
    ValidationQuery,
    ValidationQuerySet,
    ValidationSeverity,
    build_postgres_validation_query_set,
)


class PostgresValidationQueriesTests(unittest.TestCase):
    def test_query_set_builds(self):
        query_set = build_postgres_validation_query_set()
        self.assertIsInstance(query_set, ValidationQuerySet)
        self.assertEqual(query_set.name, "postgres_postdeploy_validation_queries")
        self.assertGreaterEqual(len(query_set.queries), len(VALIDATION_CATEGORIES))
        self.assertTrue(all(isinstance(query, ValidationQuery) for query in query_set.queries))
        self.assertTrue(all(isinstance(query.expectation, ValidationExpectation) for query in query_set.queries))

    def test_required_categories_exist(self):
        query_set = build_postgres_validation_query_set()
        self.assertEqual(set(query_set.categories), set(VALIDATION_CATEGORIES))
        for category in VALIDATION_CATEGORIES:
            self.assertIn(category, query_set.queries_by_category)
            self.assertGreater(len(query_set.queries_by_category[category]), 0)

    def test_no_execution_apis_used(self):
        source = Path("postgres_validation_queries.py").read_text(encoding="utf-8")
        forbidden_terms = [
            "conn.execute",
            "cursor.execute",
            "psycopg",
            "supabase",
            "sqlite3.connect",
            "create_engine",
            "DATABASE_URL",
            "connect(",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)

    def test_sql_strings_are_postgresql_oriented(self):
        query_set = build_postgres_validation_query_set()
        sql = "\n".join(query.sql for query in query_set.queries)
        self.assertIn("information_schema.tables", sql)
        self.assertIn("information_schema.columns", sql)
        self.assertIn("pg_indexes", sql)
        self.assertIn("information_schema.table_constraints", sql)
        self.assertIn("current_schema()", sql)
        self.assertNotIn("sqlite_master", sql)
        self.assertNotIn("PRAGMA", sql)
        self.assertNotIn("?", sql)

    def test_severity_model_works(self):
        self.assertEqual(ValidationSeverity.CRITICAL.value, "CRITICAL")
        query_set = build_postgres_validation_query_set()
        critical_categories = {
            query.category
            for query in query_set.queries
            if query.expectation.severity == ValidationSeverity.CRITICAL
        }
        self.assertIn("schema_exists", critical_categories)
        self.assertIn("fk_exists", critical_categories)
        self.assertIn("migration_history_exists", critical_categories)
        self.assertIn("runtime_smoke_test", critical_categories)

    def test_queries_have_expected_metadata(self):
        query_set = build_postgres_validation_query_set()
        for query in query_set.queries:
            self.assertTrue(query.query_id)
            self.assertTrue(query.name)
            self.assertTrue(query.sql)
            self.assertTrue(query.expectation.expected_result)
            self.assertTrue(query.when_to_run)


if __name__ == "__main__":
    unittest.main()
