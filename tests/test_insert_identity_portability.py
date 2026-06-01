import importlib

from test_support import ERPIsolatedTestCase


class InsertIdentityPortabilityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database = importlib.import_module("database")
        self.modules = importlib.import_module("modules")

    def test_get_inserted_id_returns_sqlite_lastrowid(self):
        cursor = self.conn.execute(
            "INSERT INTO customers (company_key, name, phone, email, customer_id, current_balance, currency) "
            "VALUES (?, 'Identity Test', '', '', 'CUST-ID-001', 0, 'GHS')",
            (self.company_key,),
        )
        self.commit()
        self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)
        self.assertEqual(self.database.fetch_inserted_row_id(cursor, backend="sqlite"), cursor.lastrowid)

    def test_ensure_insert_sql_returning_appends_for_postgres_only(self):
        base = "INSERT INTO suppliers (company_key, name) VALUES (?, ?)"
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)

    def test_register_supplier_uses_portable_identity(self):
        supplier_id = self.modules._register_supplier(
            self.conn,
            self.company_key,
            "Portable Supplier",
            "000",
            "supplier@example.com",
            "Accra",
            "General",
        )
        self.commit()
        self.assertIsNotNone(supplier_id)
        row = self.conn.execute(
            "SELECT name FROM suppliers WHERE id = ? AND company_key = ?",
            (supplier_id, self.company_key),
        ).fetchone()
        self.assertEqual(row["name"], "Portable Supplier")

    def test_register_customer_uses_portable_identity(self):
        customer_id = self.modules._register_customer(
            self.conn,
            self.company_key,
            "Portable Customer",
            phone="111",
            email="cust@example.com",
        )
        self.commit()
        self.assertIsNotNone(customer_id)
        row = self.conn.execute(
            "SELECT customer_id, name FROM customers WHERE id = ?",
            (customer_id,),
        ).fetchone()
        self.assertEqual(row["name"], "Portable Customer")
        self.assertTrue(str(row["customer_id"] or "").startswith("CUST-"))

    def test_get_or_create_account_inserts_chart_row(self):
        engine = importlib.import_module("accounting_engine")
        account_id = engine.get_or_create_account(self.conn, "Portable Test Account", "Expense")
        self.commit()
        self.assertIsNotNone(account_id)
        row = self.conn.execute(
            "SELECT account_name FROM chart_of_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        self.assertEqual(row["account_name"], "Portable Test Account")
