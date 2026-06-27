import importlib
import json
from datetime import date

from test_support import ERPIsolatedTestCase, build_lines, datetime_suffix


class ControlledCorrectionsTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database.ensure_pos_sales_schema(self.conn)
        self.conn.execute(
            "INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name) VALUES (?, ?, ?)",
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.commit()

    def _create_pos_sale_with_journal(self, *, sale_date="2026-04-24", cashier="Cashier A"):
        reference = f"CORR-POS-{datetime_suffix('POS')}"
        sale_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            reference,
            {
                "receipt_number": reference,
                "sale_date": sale_date,
                "sale_datetime": f"{sale_date} 09:15:00",
                "cashier": cashier,
                "payment_method": "Cash",
                "subtotal": 50.0,
                "discount_total": 0.0,
                "tax_total": 0.0,
                "grand_total": 50.0,
            },
            [
                {
                    "inventory_item_id": None,
                    "name": "Correction Item",
                    "item_code": "CORR",
                    "barcode": "",
                    "qty": 1.0,
                    "price": 50.0,
                    "line_discount": 0.0,
                    "tax_rate": 0.0,
                    "line_total": 50.0,
                    "cost_price": 0.0,
                }
            ],
        )
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 50.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 50.0},
            ),
            description="Controlled correction POS sale",
            reference=reference,
            source_table="pos_sales",
            source_id=sale_id,
            source_type="POS Sale",
            posting_date=date.fromisoformat(sale_date),
        )
        self.conn.execute("UPDATE pos_sales SET posted_entry_id = ? WHERE id = ?", (entry_id, sale_id))
        self.commit()
        return sale_id, entry_id, reference

    def test_unauthorized_users_cannot_edit_historical_sales(self):
        sale_id, _entry_id, _reference = self._create_pos_sale_with_journal()
        with self.assertRaises(PermissionError):
            self.modules.controlled_correct_pos_sale_metadata(
                self.conn,
                company_key=self.company_key,
                sale_id=sale_id,
                actor_role="Cashier",
                reason="Wrong transaction date",
                new_sale_date="2026-04-23",
                branch_id="MAIN",
            )

    def test_controlled_pos_correction_requires_reason_and_audits_old_new_values(self):
        sale_id, entry_id, reference = self._create_pos_sale_with_journal()
        with self.assertRaisesRegex(ValueError, "reason is required"):
            self.modules.controlled_correct_pos_sale_metadata(
                self.conn,
                company_key=self.company_key,
                sale_id=sale_id,
                actor_role="Accountant",
                new_sale_date="2026-04-23",
                branch_id="MAIN",
            )

        result = self.modules.controlled_correct_pos_sale_metadata(
            self.conn,
            company_key=self.company_key,
            sale_id=sale_id,
            actor_role="Accountant",
            actor_name="Amina Accountant",
            reason="Cashier posted sale under yesterday instead of today",
            new_sale_date="2026-04-25",
            new_cashier="Cashier B",
            branch_id="MAIN",
        )
        self.commit()

        sale_row = self.conn.execute("SELECT sale_date, sale_datetime, cashier FROM pos_sales WHERE id = ?", (sale_id,)).fetchone()
        journal_row = self.conn.execute("SELECT date FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
        audit_row = self.conn.execute(
            """
            SELECT before_after_summary, details, action_type, document_ref
            FROM audit_logs
            WHERE company_key = ? AND action = 'Controlled POS Sale Correction'
            ORDER BY id DESC LIMIT 1
            """,
            (self.company_key,),
        ).fetchone()
        line_totals = self.conn.execute(
            "SELECT ROUND(SUM(debit), 2) AS debit_total, ROUND(SUM(credit), 2) AS credit_total FROM journal_lines WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()

        self.assertEqual(result["changed_fields"]["sale_date"]["old"], "2026-04-24")
        self.assertEqual(sale_row["sale_date"], "2026-04-25")
        self.assertEqual(sale_row["sale_datetime"], "2026-04-25 09:15:00")
        self.assertEqual(sale_row["cashier"], "Cashier B")
        self.assertEqual(journal_row["date"], "2026-04-25")
        self.assertEqual(float(line_totals["debit_total"]), float(line_totals["credit_total"]))
        self.assertEqual(audit_row["action_type"], "correction")
        self.assertEqual(audit_row["document_ref"], reference)
        payload = json.loads(audit_row["before_after_summary"])
        self.assertEqual(payload["changed_fields"]["cashier"]["old"], "Cashier A")
        self.assertEqual(payload["changed_fields"]["cashier"]["new"], "Cashier B")
        self.assertIn("reason", payload)

    def test_voucher_date_permissions_and_locked_period_controls_are_respected(self):
        with self.assertRaises(PermissionError):
            self.post_entry(
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 10.0, "credit": 0.0},
                    {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 10.0},
                ),
                description="Unauthorized backdated journal",
                reference="UNAUTH-BACKDATE",
                user_role="Cashier",
                posting_date=date(2026, 1, 15),
            )

        self.create_period("2026-01", date(2026, 1, 1), date(2026, 1, 31), status="Locked", is_locked=1)
        with self.assertRaisesRegex(ValueError, "period.*locked"):
            self.post_entry(
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 10.0, "credit": 0.0},
                    {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 10.0},
                ),
                description="Locked period journal",
                reference="LOCKED-BACKDATE",
                user_role="Accountant",
                posting_date=date(2026, 1, 15),
            )
