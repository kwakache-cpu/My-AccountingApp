import importlib
import json
from datetime import date

from test_support import ERPIsolatedTestCase, datetime_suffix


class PeriodLockingControlsTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database.ensure_pos_sales_schema(self.conn)
        self.conn.execute(
            "INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name) VALUES (?, ?, ?)",
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.commit()

    def _sale(self):
        reference = f"LOCK-POS-{datetime_suffix('POS')}"
        sale_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            reference,
            {
                "receipt_number": reference,
                "sale_date": "2026-04-24",
                "sale_datetime": "2026-04-24 13:00:00",
                "cashier": "Cashier A",
                "payment_method": "Cash",
                "subtotal": 50.0,
                "discount_total": 0.0,
                "tax_total": 0.0,
                "grand_total": 50.0,
            },
            [
                {
                    "inventory_item_id": None,
                    "name": "Locked Period Item",
                    "item_code": "LCK",
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
        self.commit()
        return sale_id

    def test_locked_period_status_blocks_normal_pos_date_correction(self):
        sale_id = self._sale()
        self.create_period("2026-03", date(2026, 3, 1), date(2026, 3, 31), status="Locked", is_locked=1)
        self.modules.ENTERPRISE_ROLE_PERMISSIONS["Test Corrector"] = {"void_or_reverse_document"}

        status = self.modules.get_operational_date_control_status(
            self.company_key,
            "2026-03-15",
            actor_role="Test Corrector",
            conn=self.conn,
        )

        self.assertTrue(status["period_locked"])
        self.assertTrue(status["posting_blocked"])
        with self.assertRaises(PermissionError):
            self.modules.controlled_correct_pos_sale_metadata(
                self.conn,
                company_key=self.company_key,
                sale_id=sale_id,
                actor_role="Test Corrector",
                reason="Move sale into locked period without override",
                new_sale_date="2026-03-15",
                branch_id="MAIN",
            )

    def test_privileged_locked_period_override_requires_reason_and_is_audited(self):
        sale_id = self._sale()
        self.create_period("2026-03", date(2026, 3, 1), date(2026, 3, 31), status="Locked", is_locked=1)

        result = self.modules.controlled_correct_pos_sale_metadata(
            self.conn,
            company_key=self.company_key,
            sale_id=sale_id,
            actor_role="Master Admin",
            reason="Approved finance override for month-end correction",
            new_sale_date="2026-03-15",
            branch_id="MAIN",
        )
        self.commit()

        audit_row = self.conn.execute(
            """
            SELECT before_after_summary
            FROM audit_logs
            WHERE company_key = ? AND action = 'Controlled POS Sale Correction'
            ORDER BY id DESC LIMIT 1
            """,
            (self.company_key,),
        ).fetchone()
        payload = json.loads(audit_row["before_after_summary"])

        self.assertEqual(result["new_values"]["sale_date"], "2026-03-15")
        self.assertTrue(payload["locked_period_override"])
