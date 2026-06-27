import importlib

from test_support import ERPIsolatedTestCase, datetime_suffix


class POSSalesmanDateFilterTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database.ensure_pos_sales_schema(self.conn)
        self.conn.execute(
            "INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name) VALUES (?, ?, ?)",
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name) VALUES (?, ?, ?)",
            ("EAST", self.company_key, "East Branch"),
        )
        self.commit()

    def _sale(self, *, sale_date, cashier, branch_id="MAIN", amount=25.0):
        reference = f"FILTER-POS-{datetime_suffix('POS')}"
        return self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            branch_id,
            reference,
            {
                "receipt_number": reference,
                "sale_date": sale_date,
                "sale_datetime": f"{sale_date} 10:00:00",
                "cashier": cashier,
                "payment_method": "Cash",
                "subtotal": amount,
                "discount_total": 0.0,
                "tax_total": 0.0,
                "grand_total": amount,
            },
            [
                {
                    "inventory_item_id": None,
                    "name": "Filter Item",
                    "item_code": "FLT",
                    "barcode": "",
                    "qty": 1.0,
                    "price": amount,
                    "line_discount": 0.0,
                    "tax_rate": 0.0,
                    "line_total": amount,
                    "cost_price": 0.0,
                }
            ],
        )

    def test_pos_sales_filter_by_date_cashier_and_branch(self):
        sale_a = self._sale(sale_date="2026-04-20", cashier="Amina")
        self._sale(sale_date="2026-04-21", cashier="Kojo")
        self._sale(sale_date="2026-04-21", cashier="Amina", branch_id="EAST")
        self.commit()

        date_rows = self.modules.fetch_pos_sales_for_correction(
            self.conn,
            self.company_key,
            start_date="2026-04-20",
            end_date="2026-04-20",
        )
        cashier_rows = self.modules.fetch_pos_sales_for_correction(
            self.conn,
            self.company_key,
            cashier="Amina",
        )
        branch_rows = self.modules.fetch_pos_sales_for_correction(
            self.conn,
            self.company_key,
            cashier="Amina",
            branch_id="MAIN",
        )

        self.assertEqual([row["id"] for row in date_rows], [sale_a])
        self.assertEqual({row["cashier"] for row in cashier_rows}, {"Amina"})
        self.assertEqual({row["branch_id"] for row in branch_rows}, {"MAIN"})

    def test_cashier_correction_updates_filters_without_touching_cashier_closings(self):
        sale_id = self._sale(sale_date="2026-04-22", cashier="Wrong Cashier")
        self.conn.execute(
            """
            INSERT INTO cashier_closings (
                company_key, branch_id, cashier, closing_date, expected_cash, counted_cash, difference, closed_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "MAIN", "Wrong Cashier", "2026-04-22", 25.0, 25.0, 0.0, "Branch Manager"),
        )
        self.commit()

        self.modules.controlled_correct_pos_sale_metadata(
            self.conn,
            company_key=self.company_key,
            sale_id=sale_id,
            actor_role="Accountant",
            reason="Sale assigned to wrong cashier during pilot UAT",
            new_cashier="Correct Cashier",
            branch_id="MAIN",
        )
        self.commit()

        old_rows = self.modules.fetch_pos_sales_for_correction(self.conn, self.company_key, cashier="Wrong Cashier")
        new_rows = self.modules.fetch_pos_sales_for_correction(self.conn, self.company_key, cashier="Correct Cashier")
        closing_count = int(
            self.conn.execute(
                "SELECT COUNT(*) AS c FROM cashier_closings WHERE company_key = ? AND cashier = ?",
                (self.company_key, "Wrong Cashier"),
            ).fetchone()["c"]
        )

        self.assertEqual(old_rows, [])
        self.assertEqual([row["id"] for row in new_rows], [sale_id])
        self.assertEqual(closing_count, 1)
