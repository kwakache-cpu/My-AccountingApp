import importlib

from test_support import ERPIsolatedTestCase, build_lines, datetime_suffix


class JournalEntryIdentityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.engine = importlib.import_module("accounting_engine")
        self.database = importlib.import_module("database")

    def test_post_journal_entry_returns_valid_entry_id(self):
        entry_id = self.engine.post_journal_entry(
            company_key=self.company_key,
            date=self.today,
            description="Identity journal",
            reference="JE-ID-001",
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 50.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 50.0},
            ),
            created_by="Bookkeeper",
            conn=self.conn,
        )
        self.commit()
        header = self.conn.execute(
            "SELECT description, reference FROM journal_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        self.assertEqual(header["description"], "Identity journal")
        self.assertEqual(header["reference"], "JE-ID-001")

    def test_journal_lines_use_returned_entry_id(self):
        cash_id = self.account_id("Cash", "Asset")
        equity_id = self.account_id("Owner Capital", "Equity")
        entry_id = self.engine.post_journal_entry(
            company_key=self.company_key,
            date=self.today,
            description="Line linkage",
            reference="JE-LINES-001",
            lines=build_lines(
                {"account_id": cash_id, "debit": 75.0, "credit": 0.0},
                {"account_id": equity_id, "debit": 0.0, "credit": 75.0},
            ),
            created_by="Bookkeeper",
            conn=self.conn,
        )
        self.commit()
        rows = self.conn.execute(
            "SELECT entry_id, account_id, debit, credit FROM journal_lines WHERE entry_id = ? ORDER BY debit DESC",
            (entry_id,),
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(int(row["entry_id"]) == entry_id for row in rows))
        self.assertEqual(float(rows[0]["debit"]), 75.0)
        self.assertEqual(float(rows[1]["credit"]), 75.0)

    def test_journal_remains_balanced(self):
        entry_id = self.engine.post_journal_entry(
            company_key=self.company_key,
            date=self.today,
            description="Balanced",
            reference="JE-BAL-001",
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 120.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 0.0, "credit": 120.0},
            ),
            created_by="Bookkeeper",
            conn=self.conn,
        )
        self.commit()
        totals = self.conn.execute(
            """
            SELECT ROUND(SUM(debit), 2) AS total_debit, ROUND(SUM(credit), 2) AS total_credit
            FROM journal_lines WHERE entry_id = ?
            """,
            (entry_id,),
        ).fetchone()
        self.assertEqual(float(totals["total_debit"]), float(totals["total_credit"]))

    def test_unbalanced_journal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unbalanced journal entry"):
            self.engine.post_journal_entry(
                company_key=self.company_key,
                date=self.today,
                description="Broken",
                reference="JE-UNBAL",
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 100.0, "credit": 0.0},
                    {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 90.0},
                ),
                created_by="Bookkeeper",
                conn=self.conn,
            )

    def test_duplicate_source_document_protection_still_works(self):
        invoice_id = self.create_invoice(status="Posted", amount=80.0)
        lines = build_lines(
            {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 80.0, "credit": 0.0},
            {"account_id": self.account_id("Sales Revenue", "Revenue"), "debit": 0.0, "credit": 80.0},
        )
        first_id = self.engine.post_journal_entry(
            company_key=self.company_key,
            date=self.today,
            description="Invoice post",
            reference="INV-JE-1",
            lines=lines,
            created_by="Bookkeeper",
            source_table="invoices",
            source_type="Invoice",
            source_id=invoice_id,
            conn=self.conn,
        )
        self.commit()
        self.assertGreater(first_id, 0)
        with self.assertRaisesRegex(ValueError, "already posted"):
            self.engine.post_journal_entry(
                company_key=self.company_key,
                date=self.today,
                description="Duplicate invoice post",
                reference="INV-JE-2",
                lines=lines,
                created_by="Bookkeeper",
                source_table="invoices",
                source_type="Invoice",
                source_id=invoice_id,
                conn=self.conn,
            )

    def test_branch_id_is_preserved(self):
        self.conn.execute(
            """
            INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name)
            VALUES (?, ?, ?)
            """,
            ("JE-BR", self.company_key, "Journal Branch"),
        )
        self.commit()
        entry_id = self.engine.post_journal_entry(
            company_key=self.company_key,
            date=self.today,
            description="Branch journal",
            reference="JE-BR-001",
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 10.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 10.0},
            ),
            created_by="Bookkeeper",
            branch_id="JE-BR",
            conn=self.conn,
        )
        self.commit()
        row = self.conn.execute(
            "SELECT branch_id, reference, document_number FROM journal_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        self.assertEqual(row["branch_id"], "JE-BR")
        self.assertEqual(row["reference"], "JE-BR-001")
        self.assertEqual(row["document_number"], "JE-BR-001")

    def test_rollback_prevents_orphan_journal_lines(self):
        reference = f"JE-ROLLBACK-{datetime_suffix('R')}"
        try:
            entry_id = self.engine.post_journal_entry(
                company_key=self.company_key,
                date=self.today,
                description="Rollback test",
                reference=reference,
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 15.0, "credit": 0.0},
                    {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 15.0},
                ),
                created_by="Bookkeeper",
                conn=self.conn,
            )
            line_count = self.conn.execute(
                "SELECT COUNT(*) AS c FROM journal_lines WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()["c"]
            self.assertEqual(int(line_count), 2)
            self.conn.rollback()
        except Exception:
            self.conn.rollback()
            raise
        header_count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM journal_entries WHERE reference = ?",
            (reference,),
        ).fetchone()["c"]
        self.assertEqual(int(header_count), 0)

    def test_journal_insert_sqlite_matches_lastrowid(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO journal_entries (
                    company_key, date, description, reference, created_by, approval_status
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                self.today.isoformat(),
                "SQLite header",
                "JE-SQLITE",
                "test",
                "Posted",
            ),
        )
        self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)

    def test_journal_insert_sql_postgres_returning(self):
        base = (
            "INSERT INTO journal_entries (company_key, date, description, reference) "
            "VALUES (?, ?, ?, ?)"
        )
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)
