import importlib
from pathlib import Path

from test_support import ERPIsolatedTestCase, datetime_suffix


class OperationalPolishControlsTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database.ensure_pos_sales_schema(self.conn)
        self.conn.execute(
            "INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name) VALUES (?, ?, ?)",
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.commit()

    def _sale(self, reference, sale_date="2026-04-24", cashier="Cashier A"):
        return self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            reference,
            {
                "receipt_number": reference,
                "sale_date": sale_date,
                "sale_datetime": f"{sale_date} 11:00:00",
                "cashier": cashier,
                "payment_method": "Cash",
                "subtotal": 30.0,
                "discount_total": 0.0,
                "tax_total": 0.0,
                "grand_total": 30.0,
            },
            [
                {
                    "inventory_item_id": None,
                    "name": "Polish Item",
                    "item_code": "POL",
                    "barcode": "",
                    "qty": 1.0,
                    "price": 30.0,
                    "line_discount": 0.0,
                    "tax_rate": 0.0,
                    "line_total": 30.0,
                    "cost_price": 0.0,
                }
            ],
        )

    def test_historical_pos_lookup_supports_reference_date_user_and_branch_filters(self):
        wanted_ref = f"POLISH-{datetime_suffix('POS')}"
        wanted_id = self._sale(wanted_ref, sale_date="2026-04-20", cashier="Amina")
        self._sale(f"OTHER-{datetime_suffix('POS')}", sale_date="2026-04-21", cashier="Kojo")
        self.commit()

        rows = self.modules.fetch_pos_sales_for_correction(
            self.conn,
            self.company_key,
            start_date="2026-04-01",
            end_date="2026-04-30",
            responsible_user="Amina",
            sale_reference=wanted_ref[-8:],
            branch_id="MAIN",
        )

        self.assertEqual([row["id"] for row in rows], [wanted_id])
        self.assertEqual(rows[0]["cashier"], "Amina")

    def test_controlled_correction_ui_copy_is_explicit_about_no_deletion(self):
        source = Path(__file__).resolve().parent.parent / "modules.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("Controlled Historical Sales Correction", text)
        self.assertIn("does not delete sales or edit sale totals/line items", text)
        self.assertIn("Use returns, reversal, or reposting workflows", text)
