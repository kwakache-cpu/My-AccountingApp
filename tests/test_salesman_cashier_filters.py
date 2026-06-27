import importlib
import json

from test_support import ERPIsolatedTestCase, datetime_suffix


class SalesmanCashierFilterTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database.ensure_pos_sales_schema(self.conn)
        self.conn.execute(
            "INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name) VALUES (?, ?, ?)",
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.commit()

    def _sale(self, cashier):
        reference = f"USER-FILTER-{datetime_suffix('POS')}"
        sale_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            reference,
            {
                "receipt_number": reference,
                "sale_date": "2026-04-24",
                "sale_datetime": "2026-04-24 12:00:00",
                "cashier": cashier,
                "payment_method": "Cash",
                "subtotal": 40.0,
                "discount_total": 0.0,
                "tax_total": 0.0,
                "grand_total": 40.0,
            },
            [
                {
                    "inventory_item_id": None,
                    "name": "User Filter Item",
                    "item_code": "USR",
                    "barcode": "",
                    "qty": 1.0,
                    "price": 40.0,
                    "line_discount": 0.0,
                    "tax_rate": 0.0,
                    "line_total": 40.0,
                    "cost_price": 0.0,
                }
            ],
        )
        self.commit()
        return sale_id, reference

    def test_responsible_user_filter_uses_cashier_attribution_without_new_free_edit_field(self):
        sale_id, _reference = self._sale("Sales Officer A")
        self._sale("Cashier B")

        rows = self.modules.fetch_pos_sales_for_correction(
            self.conn,
            self.company_key,
            responsible_user="Sales Officer A",
        )

        self.assertEqual([row["id"] for row in rows], [sale_id])
        self.assertEqual(rows[0]["cashier"], "Sales Officer A")

    def test_responsible_user_reassignment_is_audited_as_controlled_correction(self):
        sale_id, reference = self._sale("Wrong User")

        self.modules.controlled_correct_pos_sale_metadata(
            self.conn,
            company_key=self.company_key,
            sale_id=sale_id,
            actor_role="Accountant",
            reason="Sale assigned to the wrong responsible user",
            new_responsible_user="Correct User",
            branch_id="MAIN",
        )
        self.commit()

        sale_row = self.conn.execute("SELECT cashier FROM pos_sales WHERE id = ?", (sale_id,)).fetchone()
        audit_row = self.conn.execute(
            """
            SELECT before_after_summary, document_ref
            FROM audit_logs
            WHERE company_key = ? AND action = 'Controlled POS Sale Correction'
            ORDER BY id DESC LIMIT 1
            """,
            (self.company_key,),
        ).fetchone()
        payload = json.loads(audit_row["before_after_summary"])

        self.assertEqual(sale_row["cashier"], "Correct User")
        self.assertEqual(audit_row["document_ref"], reference)
        self.assertEqual(payload["responsible_user_field"], "cashier")
        self.assertEqual(payload["changed_fields"]["cashier"]["old"], "Wrong User")
        self.assertEqual(payload["changed_fields"]["cashier"]["new"], "Correct User")
