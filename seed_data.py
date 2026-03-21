import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "database.db"
COMPANY_KEY = "EKA-TEST-2026-0001"


def main():
    print(f"Seeding database at: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    subscription_expiry = (datetime.now() + timedelta(days=365)).date().isoformat()

    cursor.execute(
        """
        INSERT OR REPLACE INTO companies (
            key,
            name,
            subscription_expiry,
            status,
            deployment_status,
            plan_type,
            contact_email,
            phone_number,
            industry,
            currency
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            COMPANY_KEY,
            "E.K.A. Solutions",
            subscription_expiry,
            "Active",
            "Live",
            "Enterprise",
            "info@ekasolutions.example",
            "+233200000001",
            "Technology",
            "GHS",
        ),
    )

    cursor.execute("DELETE FROM pending_approvals WHERE company_key = ?", (COMPANY_KEY,))
    revenue_rows = [
        ("EKA-APR-001", 1500.0, "Bank Transfer", "Enterprise", "Approved"),
        ("EKA-APR-002", 2500.0, "Mobile Money", "Premium", "Approved"),
        ("EKA-APR-003", 1200.0, "Card", "Basic", "Approved"),
    ]
    cursor.executemany(
        """
        INSERT INTO pending_approvals (
            company_key,
            payment_reference,
            amount,
            payment_method,
            plan_requested,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [(COMPANY_KEY, ref, amount, method, plan, status) for ref, amount, method, plan, status in revenue_rows],
    )

    cursor.execute("DELETE FROM inventory WHERE company_key = ?", (COMPANY_KEY,))
    inventory_rows = [
        ("Cloud ERP License Pack", "LIC-001", "Software", 25, "pcs", 600.0, 950.0, "Main", "ERP001"),
        ("POS Receipt Printer", "POS-002", "Hardware", 12, "pcs", 180.0, 320.0, "Main", "POS002"),
        ("Barcode Scanner", "BAR-003", "Hardware", 18, "pcs", 95.0, 170.0, "Main", "BAR003"),
        ("Payroll Setup Bundle", "PAY-004", "Service", 9, "pkg", 400.0, 750.0, "Services", "PAY004"),
        ("Support Retainer", "SUP-005", "Service", 6, "pkg", 850.0, 1400.0, "Services", "SUP005"),
    ]
    cursor.executemany(
        """
        INSERT INTO inventory (
            company_key,
            item_name,
            item_code,
            category,
            qty,
            unit,
            cost_price,
            price,
            warehouse,
            warehouse_location,
            barcode
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                COMPANY_KEY,
                item_name,
                item_code,
                category,
                qty,
                unit,
                cost_price,
                price,
                warehouse,
                warehouse,
                barcode,
            )
            for item_name, item_code, category, qty, unit, cost_price, price, warehouse, barcode in inventory_rows
        ],
    )

    conn.commit()
    conn.close()

    print("Seed data inserted successfully.")
    print(f"Company key: {COMPANY_KEY}")


if __name__ == "__main__":
    main()
