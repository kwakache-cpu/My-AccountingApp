#!/usr/bin/env python3
"""
Read-only migration integrity audit for SQLite production databases.
Generates reports/migration_integrity_audit.md and reports/migration_integrity_summary.md
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "eka_enterprise_v3.db"
REPORTS_DIR = REPO_ROOT / "reports"

BRANCH_SCOPED_ROLES = ("Branch_Bookkeeper", "Cashier", "Staff", "Branch Manager")
KNOWN_ROLES = (
    "Dev",
    "Master Admin",
    "System Admin",
    "Gatekeeper",
    "Owner / CEO",
    "Sub-Admin",
    "Branch Manager",
    "Branch_Bookkeeper",
    "Cashier",
    "Sales Officer",
    "Inventory Officer",
    "Staff",
    "Bookkeeper",
    "Accountant",
    "Auditor / Read Only",
    "Demo",
)
VALID_BRANCH_TYPES = ("retail", "warehouse", "main", "subsidiary_main", "office", "other")


class AuditFinding:
    def __init__(self, name, count=0, risk="LOW", sql="", note="", sample=None, is_blocker=False):
        self.name = name
        self.count = int(count or 0)
        self.risk = risk
        self.sql = sql
        self.note = note
        self.sample = sample or []
        self.is_blocker = is_blocker


def _connect_readonly(db_path: Path):
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _safe_count(conn, sql, params=(), missing_table=None):
    if missing_table and not _table_exists(conn, missing_table):
        return None
    try:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] if row else 0)
    except sqlite3.Error as exc:
        return f"ERROR: {exc}"


def _safe_rows(conn, sql, params=(), limit=5, missing_table=None):
    if missing_table and not _table_exists(conn, missing_table):
        return []
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows[:limit]]
    except sqlite3.Error:
        return []


INFO_ONLY_FINDINGS = frozenset(
    {
        "total_companies",
        "total_branches",
        "active_branches",
        "inactive_branches",
        "total_users",
        "users_by_role",
        "journal_entries",
        "journal_lines",
        "total_pos_sales",
        "suspended_sales_count",
        "total_inventory_items",
        "expired_stock_count",
        "inactive_users",
    }
)


def _score_area(findings):
    if any(isinstance(f.count, str) for f in findings):
        return "RED"
    blocker_hits = [
        f for f in findings if f.is_blocker and isinstance(f.count, int) and f.count > 0
    ]
    if blocker_hits:
        return "RED"
    warning_hits = [
        f
        for f in findings
        if not f.is_blocker
        and f.name not in INFO_ONLY_FINDINGS
        and isinstance(f.count, int)
        and f.count > 0
        and f.risk in {"MEDIUM", "LOW"}
    ]
    if warning_hits:
        return "YELLOW"
    return "GREEN"


def run_audit(db_path: Path):
    audited_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    conn = _connect_readonly(db_path)
    sections = {}
    row_counts = {}
    all_findings = []

    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for table in tables:
            count = _safe_count(conn, f"SELECT COUNT(*) FROM {table}")
            if isinstance(count, int):
                row_counts[table] = count

        # --- 1. Companies ---
        company_findings = []
        total_companies = _safe_count(conn, "SELECT COUNT(*) FROM companies", missing_table="companies")
        company_findings.append(AuditFinding("total_companies", total_companies or 0, sql="SELECT COUNT(*) FROM companies"))
        missing_names = _safe_count(
            conn,
            "SELECT COUNT(*) FROM companies WHERE TRIM(COALESCE(name, '')) = ''",
            missing_table="companies",
        )
        company_findings.append(
            AuditFinding(
                "missing_names",
                missing_names or 0,
                risk="HIGH",
                is_blocker=True,
                sql="SELECT key FROM companies WHERE TRIM(COALESCE(name, '')) = ''",
            )
        )
        duplicate_keys = _safe_count(
            conn,
            "SELECT COUNT(*) FROM (SELECT key FROM companies GROUP BY key HAVING COUNT(*) > 1)",
            missing_table="companies",
        )
        company_findings.append(AuditFinding("duplicate_keys", duplicate_keys or 0, risk="HIGH", is_blocker=True))
        sections["Companies"] = company_findings
        all_findings.extend(company_findings)

        # --- 2. Branches ---
        branch_findings = []
        branch_cols = _columns(conn, "branches")
        total_branches = _safe_count(conn, "SELECT COUNT(*) FROM branches", missing_table="branches")
        branch_findings.append(AuditFinding("total_branches", total_branches or 0))
        if "is_active" in branch_cols:
            active_branches = _safe_count(
                conn,
                "SELECT COUNT(*) FROM branches WHERE COALESCE(is_active, 1) = 1",
                missing_table="branches",
            )
            inactive_branches = _safe_count(
                conn,
                "SELECT COUNT(*) FROM branches WHERE COALESCE(is_active, 0) = 0",
                missing_table="branches",
            )
            branch_findings.append(AuditFinding("active_branches", active_branches or 0))
            branch_findings.append(AuditFinding("inactive_branches", inactive_branches or 0))
        if "branch_code" in branch_cols:
            missing_branch_code = _safe_count(
                conn,
                "SELECT COUNT(*) FROM branches WHERE branch_code IS NULL OR TRIM(branch_code) = ''",
                missing_table="branches",
            )
            branch_findings.append(
                AuditFinding(
                    "missing_branch_code",
                    missing_branch_code or 0,
                    risk="MEDIUM",
                    sql="SELECT branch_id, branch_name FROM branches WHERE branch_code IS NULL OR TRIM(branch_code) = ''",
                )
            )
            duplicate_branch_code = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM (
                    SELECT company_key, LOWER(TRIM(branch_code))
                    FROM branches
                    WHERE branch_code IS NOT NULL AND TRIM(branch_code) != ''
                    GROUP BY company_key, LOWER(TRIM(branch_code))
                    HAVING COUNT(*) > 1
                )
                """,
                missing_table="branches",
            )
            branch_findings.append(
                AuditFinding(
                    "duplicate_branch_code",
                    duplicate_branch_code or 0,
                    risk="HIGH",
                    is_blocker=True,
                )
            )
        duplicate_access_key = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT branch_access_key FROM branches
                WHERE branch_access_key IS NOT NULL AND TRIM(branch_access_key) != ''
                GROUP BY branch_access_key HAVING COUNT(*) > 1
            )
            """,
            missing_table="branches",
        )
        branch_findings.append(
            AuditFinding(
                "duplicate_branch_access_key",
                duplicate_access_key or 0,
                risk="HIGH",
                is_blocker=True,
            )
        )
        if "branch_type" in branch_cols and _table_exists(conn, "branch_type_catalog"):
            invalid_branch_types = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM branches b
                LEFT JOIN branch_type_catalog c ON c.branch_type_key = LOWER(TRIM(b.branch_type))
                WHERE c.branch_type_key IS NULL
                """,
                missing_table="branches",
            )
        else:
            placeholders = ", ".join("?" for _ in VALID_BRANCH_TYPES)
            invalid_branch_types = _safe_count(
                conn,
                f"""
                SELECT COUNT(*) FROM branches
                WHERE LOWER(TRIM(COALESCE(branch_type, ''))) NOT IN ({placeholders})
                  AND TRIM(COALESCE(branch_type, '')) != ''
                """,
                VALID_BRANCH_TYPES,
                missing_table="branches",
            )
        branch_findings.append(AuditFinding("invalid_branch_types", invalid_branch_types or 0, risk="MEDIUM"))
        if "manager_user_id" in branch_cols:
            missing_managers = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM branches
                WHERE manager_user_id IS NULL OR TRIM(manager_user_id) = ''
                """,
                missing_table="branches",
            )
            branch_findings.append(AuditFinding("missing_manager_user_id", missing_managers or 0, risk="LOW"))
        license_overages = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT c.key
                FROM companies c
                JOIN branches b ON b.company_key = c.key AND COALESCE(b.is_active, 1) = 1
                GROUP BY c.key, COALESCE(c.max_branches, 1)
                HAVING COUNT(b.branch_id) > COALESCE(c.max_branches, 1)
            )
            """,
            missing_table="companies",
        )
        branch_findings.append(
            AuditFinding(
                "companies_over_active_branch_limit",
                license_overages or 0,
                risk="HIGH",
                is_blocker=True,
            )
        )
        sections["Branches"] = branch_findings
        all_findings.extend(branch_findings)

        # --- 3. Users ---
        user_findings = []
        total_users = _safe_count(conn, "SELECT COUNT(*) FROM users", missing_table="users")
        user_findings.append(AuditFinding("total_users", total_users or 0))
        role_rows = _safe_rows(
            conn,
            "SELECT role, COUNT(*) AS cnt FROM users GROUP BY role ORDER BY cnt DESC",
            missing_table="users",
            limit=50,
        )
        user_findings.append(AuditFinding("users_by_role", len(role_rows), note=str(role_rows)))
        duplicate_login = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT login_key FROM users GROUP BY login_key HAVING COUNT(*) > 1
            )
            """,
            missing_table="users",
        )
        user_findings.append(
            AuditFinding("duplicate_login_key", duplicate_login or 0, risk="HIGH", is_blocker=True)
        )
        missing_company = _safe_count(
            conn,
            "SELECT COUNT(*) FROM users WHERE company_key IS NULL OR TRIM(company_key) = ''",
            missing_table="users",
        )
        user_findings.append(
            AuditFinding("users_without_company_key", missing_company or 0, risk="HIGH", is_blocker=True)
        )
        placeholders = ", ".join("?" for _ in BRANCH_SCOPED_ROLES)
        branch_scoped_no_branch = _safe_count(
            conn,
            f"""
            SELECT COUNT(*) FROM users
            WHERE role IN ({placeholders})
              AND (branch_id IS NULL OR TRIM(branch_id) = '')
            """,
            BRANCH_SCOPED_ROLES,
            missing_table="users",
        )
        user_findings.append(
            AuditFinding(
                "branch_scoped_users_without_branch_id",
                branch_scoped_no_branch or 0,
                risk="HIGH",
                is_blocker=True,
            )
        )
        known_placeholders = ", ".join("?" for _ in KNOWN_ROLES)
        invalid_roles = _safe_count(
            conn,
            f"SELECT COUNT(*) FROM users WHERE role NOT IN ({known_placeholders})",
            KNOWN_ROLES,
            missing_table="users",
        )
        user_findings.append(AuditFinding("invalid_roles", invalid_roles or 0, risk="MEDIUM"))
        inactive_users = _safe_count(
            conn,
            "SELECT COUNT(*) FROM users WHERE LOWER(COALESCE(status, 'Active')) != 'active'",
            missing_table="users",
        )
        user_findings.append(AuditFinding("inactive_users", inactive_users or 0, risk="LOW"))
        sections["Users"] = user_findings
        all_findings.extend(user_findings)

        # --- 4. Journals ---
        journal_findings = []
        journal_count = _safe_count(conn, "SELECT COUNT(*) FROM journal_entries", missing_table="journal_entries")
        line_count = _safe_count(conn, "SELECT COUNT(*) FROM journal_lines", missing_table="journal_lines")
        journal_findings.append(AuditFinding("journal_entries", journal_count or 0))
        journal_findings.append(AuditFinding("journal_lines", line_count or 0))
        unbalanced = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT je.id
                FROM journal_entries je
                JOIN journal_lines jl ON jl.entry_id = je.id
                WHERE COALESCE(je.is_voided, 0) = 0
                GROUP BY je.id
                HAVING ABS(SUM(jl.debit) - SUM(jl.credit)) > 0.01
            )
            """,
            missing_table="journal_entries",
        )
        journal_findings.append(
            AuditFinding("unbalanced_journals", unbalanced or 0, risk="HIGH", is_blocker=True)
        )
        journals_without_lines = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM journal_entries je
            LEFT JOIN journal_lines jl ON jl.entry_id = je.id
            WHERE jl.id IS NULL
            """,
            missing_table="journal_entries",
        )
        journal_findings.append(
            AuditFinding("journals_without_lines", journals_without_lines or 0, risk="HIGH", is_blocker=True)
        )
        orphaned_lines = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM journal_lines jl
            LEFT JOIN journal_entries je ON je.id = jl.entry_id
            WHERE je.id IS NULL
            """,
            missing_table="journal_lines",
        )
        journal_findings.append(
            AuditFinding("orphaned_journal_lines", orphaned_lines or 0, risk="HIGH", is_blocker=True)
        )
        duplicate_source = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT company_key, source_table, source_id, source_type, COUNT(*) AS cnt
                FROM journal_entries
                WHERE COALESCE(is_voided, 0) = 0
                  AND source_table IS NOT NULL AND TRIM(source_table) != ''
                  AND source_id IS NOT NULL
                GROUP BY company_key, source_table, source_id, source_type
                HAVING COUNT(*) > 1
            )
            """,
            missing_table="journal_entries",
        )
        journal_findings.append(
            AuditFinding(
                "duplicate_source_postings",
                duplicate_source or 0,
                risk="MEDIUM",
                note="POS may intentionally have Sale + COGS pairs; review source_type.",
            )
        )
        if _table_exists(conn, "vouchers") and "reference_no" in _columns(conn, "vouchers"):
            duplicate_vouchers = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM (
                    SELECT company_key, reference_no FROM vouchers
                    WHERE reference_no IS NOT NULL AND TRIM(reference_no) != ''
                    GROUP BY company_key, reference_no HAVING COUNT(*) > 1
                )
                """,
                missing_table="vouchers",
            )
            journal_findings.append(AuditFinding("duplicate_voucher_reference_no", duplicate_vouchers or 0, risk="MEDIUM"))
        sections["Journals"] = journal_findings
        all_findings.extend(journal_findings)

        # --- 5. POS ---
        pos_findings = []
        total_sales = _safe_count(conn, "SELECT COUNT(*) FROM pos_sales", missing_table="pos_sales")
        pos_findings.append(AuditFinding("total_pos_sales", total_sales or 0))
        duplicate_receipts = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT company_key, receipt_number FROM pos_sales
                GROUP BY company_key, receipt_number HAVING COUNT(*) > 1
            )
            """,
            missing_table="pos_sales",
        )
        pos_findings.append(
            AuditFinding("duplicate_receipt_numbers", duplicate_receipts or 0, risk="HIGH", is_blocker=True)
        )
        sales_without_lines = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM pos_sales ps
            LEFT JOIN pos_sale_lines psl ON psl.pos_sale_id = ps.id
            WHERE psl.id IS NULL
            """,
            missing_table="pos_sales",
        )
        pos_findings.append(AuditFinding("sales_without_lines", sales_without_lines or 0, risk="MEDIUM"))
        orphaned_pos_lines = _safe_count(
            conn,
            """
            SELECT COUNT(*) FROM pos_sale_lines psl
            LEFT JOIN pos_sales ps ON ps.id = psl.pos_sale_id
            WHERE ps.id IS NULL
            """,
            missing_table="pos_sale_lines",
        )
        pos_findings.append(
            AuditFinding("orphaned_pos_sale_lines", orphaned_pos_lines or 0, risk="HIGH", is_blocker=True)
        )
        if "branch_id" in _columns(conn, "pos_sales"):
            sales_no_branch = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM pos_sales
                WHERE branch_id IS NULL OR TRIM(branch_id) = ''
                """,
                missing_table="pos_sales",
            )
            pos_findings.append(AuditFinding("sales_without_branch_id", sales_no_branch or 0, risk="MEDIUM"))
        if _table_exists(conn, "pos_sales") and _table_exists(conn, "journal_entries"):
            sales_missing_journal = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM pos_sales ps
                LEFT JOIN journal_entries je
                  ON je.company_key = ps.company_key
                 AND je.source_table = 'pos_sales'
                 AND je.source_id = ps.id
                 AND COALESCE(je.is_voided, 0) = 0
                WHERE je.id IS NULL
                """,
                missing_table="pos_sales",
            )
            pos_findings.append(
                AuditFinding(
                    "sales_without_journal_entry",
                    sales_missing_journal or 0,
                    risk="MEDIUM",
                    note="Expected when sales exist but revenue journal not posted.",
                )
            )
        suspended_count = _safe_count(
            conn,
            "SELECT COUNT(*) FROM pos_suspended_sales",
            missing_table="pos_suspended_sales",
        )
        pos_findings.append(AuditFinding("suspended_sales_count", suspended_count or 0, risk="LOW"))
        sections["POS"] = pos_findings
        all_findings.extend(pos_findings)

        # --- 6. Inventory ---
        inventory_findings = []
        total_items = _safe_count(conn, "SELECT COUNT(*) FROM inventory", missing_table="inventory")
        inventory_findings.append(AuditFinding("total_inventory_items", total_items or 0))
        negative_stock = _safe_count(
            conn,
            "SELECT COUNT(*) FROM inventory WHERE COALESCE(qty, 0) < 0",
            missing_table="inventory",
        )
        inventory_findings.append(
            AuditFinding("negative_stock", negative_stock or 0, risk="HIGH", is_blocker=True)
        )
        if "barcode" in _columns(conn, "inventory"):
            duplicate_barcode = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM (
                    SELECT company_key, barcode FROM inventory
                    WHERE barcode IS NOT NULL AND TRIM(barcode) != ''
                    GROUP BY company_key, barcode HAVING COUNT(*) > 1
                )
                """,
                missing_table="inventory",
            )
            inventory_findings.append(AuditFinding("duplicate_barcode", duplicate_barcode or 0, risk="MEDIUM"))
        if "item_code" in _columns(conn, "inventory"):
            duplicate_item_code = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM (
                    SELECT company_key, item_code FROM inventory
                    WHERE item_code IS NOT NULL AND TRIM(item_code) != ''
                    GROUP BY company_key, item_code HAVING COUNT(*) > 1
                )
                """,
                missing_table="inventory",
            )
            inventory_findings.append(AuditFinding("duplicate_item_code", duplicate_item_code or 0, risk="MEDIUM"))
        if "expiry_date" in _columns(conn, "inventory"):
            expired_stock = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM inventory
                WHERE expiry_date IS NOT NULL AND TRIM(expiry_date) != ''
                  AND date(expiry_date) < date('now')
                """,
                missing_table="inventory",
            )
            invalid_expiry = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM inventory
                WHERE expiry_date IS NOT NULL AND TRIM(expiry_date) != ''
                  AND expiry_date NOT GLOB '____-__-__'
                """,
                missing_table="inventory",
            )
            inventory_findings.append(AuditFinding("expired_stock_count", expired_stock or 0, risk="LOW"))
            inventory_findings.append(AuditFinding("invalid_expiry_dates", invalid_expiry or 0, risk="MEDIUM"))
        if _table_exists(conn, "stock_movements"):
            orphaned_movements = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM stock_movements sm
                LEFT JOIN inventory i ON i.id = sm.inventory_item_id
                WHERE i.id IS NULL
                """,
                missing_table="stock_movements",
            )
            inventory_findings.append(
                AuditFinding("orphaned_stock_movements", orphaned_movements or 0, risk="HIGH", is_blocker=True)
            )
            if "branch_id" in _columns(conn, "stock_movements"):
                movements_no_branch = _safe_count(
                    conn,
                    """
                    SELECT COUNT(*) FROM stock_movements
                    WHERE branch_id IS NULL OR TRIM(branch_id) = ''
                    """,
                    missing_table="stock_movements",
                )
                inventory_findings.append(
                    AuditFinding("stock_movements_without_branch_id", movements_no_branch or 0, risk="MEDIUM")
                )
        sections["Inventory"] = inventory_findings
        all_findings.extend(inventory_findings)

        # --- 7. AR/AP ---
        arap_findings = []
        if _table_exists(conn, "invoices") and _table_exists(conn, "customers"):
            invoices_no_customer = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM invoices i
                LEFT JOIN customers c ON c.id = i.customer_id
                WHERE i.customer_id IS NOT NULL AND c.id IS NULL
                """,
            )
            arap_findings.append(AuditFinding("invoices_without_customers", invoices_no_customer or 0, risk="MEDIUM"))
        if _table_exists(conn, "bills") and _table_exists(conn, "suppliers"):
            bills_no_supplier = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM bills b
                LEFT JOIN suppliers s ON s.id = b.supplier_id
                WHERE b.supplier_id IS NOT NULL AND s.id IS NULL
                """,
            )
            arap_findings.append(AuditFinding("bills_without_suppliers", bills_no_supplier or 0, risk="MEDIUM"))
        if _table_exists(conn, "payments"):
            payments_no_source = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM payments
                WHERE (invoice_id IS NULL AND bill_id IS NULL)
                  AND (reference IS NULL OR TRIM(reference) = '')
                """,
                missing_table="payments",
            )
            arap_findings.append(AuditFinding("payments_without_source_reference", payments_no_source or 0, risk="LOW"))
        if _table_exists(conn, "customers") and "current_balance" in _columns(conn, "customers"):
            customer_balance_flags = _safe_count(
                conn,
                "SELECT COUNT(*) FROM customers WHERE ABS(COALESCE(current_balance, 0)) > 1000000000",
                missing_table="customers",
            )
            arap_findings.append(AuditFinding("customer_balance_red_flags", customer_balance_flags or 0, risk="MEDIUM"))
        sections["AR/AP"] = arap_findings
        all_findings.extend(arap_findings)

        # --- 8. Branch Governance ---
        gov_findings = []
        if _table_exists(conn, "branch_module_grants") and _table_exists(conn, "branches"):
            missing_grants = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM branches b
                LEFT JOIN branch_module_grants g
                  ON g.company_key = b.company_key AND g.branch_id = b.branch_id
                GROUP BY b.branch_id
                HAVING COUNT(g.id) = 0
                """,
            )
            # above returns one row per branch missing grants; recount properly
            missing_grants = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM (
                    SELECT b.branch_id
                    FROM branches b
                    LEFT JOIN branch_module_grants g
                      ON g.company_key = b.company_key AND g.branch_id = b.branch_id
                    GROUP BY b.branch_id
                    HAVING COUNT(g.id) = 0
                )
                """,
            )
            gov_findings.append(AuditFinding("branches_missing_module_grants", missing_grants or 0, risk="MEDIUM"))
            duplicate_grants = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM (
                    SELECT company_key, branch_id, module_key, COUNT(*) AS cnt
                    FROM branch_module_grants
                    GROUP BY company_key, branch_id, module_key
                    HAVING COUNT(*) > 1
                )
                """,
            )
            gov_findings.append(AuditFinding("duplicate_module_grants", duplicate_grants or 0, risk="MEDIUM"))
        if _table_exists(conn, "branches") and _table_exists(conn, "users"):
            managers_not_found = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM branches b
                LEFT JOIN users u ON u.company_key = b.company_key AND u.user_id = b.manager_user_id
                WHERE b.manager_user_id IS NOT NULL AND TRIM(b.manager_user_id) != ''
                  AND u.id IS NULL
                """,
            )
            gov_findings.append(AuditFinding("branch_managers_not_found_in_users", managers_not_found or 0, risk="MEDIUM"))
            managers_wrong_branch = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM branches b
                JOIN users u ON u.company_key = b.company_key AND u.user_id = b.manager_user_id
                WHERE u.branch_id IS NOT NULL AND TRIM(u.branch_id) != ''
                  AND u.branch_id != b.branch_id
                """,
            )
            gov_findings.append(
                AuditFinding("branch_managers_assigned_to_wrong_branch", managers_wrong_branch or 0, risk="MEDIUM")
            )
            invalid_branch_users = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM users u
                LEFT JOIN branches b ON b.company_key = u.company_key AND b.branch_id = u.branch_id
                WHERE u.branch_id IS NOT NULL AND TRIM(u.branch_id) != ''
                  AND b.branch_id IS NULL
                """,
            )
            gov_findings.append(
                AuditFinding("branch_scoped_users_invalid_branch", invalid_branch_users or 0, risk="HIGH", is_blocker=True)
            )
            inactive_branch_active_users = _safe_count(
                conn,
                """
                SELECT COUNT(*) FROM users u
                JOIN branches b ON b.company_key = u.company_key AND b.branch_id = u.branch_id
                WHERE COALESCE(b.is_active, 1) = 0
                  AND LOWER(COALESCE(u.status, 'Active')) = 'active'
                """,
            )
            gov_findings.append(
                AuditFinding("inactive_branches_with_active_users", inactive_branch_active_users or 0, risk="MEDIUM")
            )
        sections["Branch Governance"] = gov_findings
        all_findings.extend(gov_findings)

    finally:
        conn.close()

    area_scores = {}
    for area, findings in sections.items():
        area_scores[area] = _score_area(findings)

    overall = "GREEN"
    if any(score == "RED" for score in area_scores.values()):
        overall = "RED"
    elif any(score == "YELLOW" for score in area_scores.values()):
        overall = "YELLOW"

    blockers = [f for f in all_findings if f.is_blocker and isinstance(f.count, int) and f.count > 0]
    warnings = [
        f
        for f in all_findings
        if not f.is_blocker
        and f.name not in INFO_ONLY_FINDINGS
        and isinstance(f.count, int)
        and f.count > 0
        and f.risk in {"MEDIUM", "LOW"}
    ]

    if overall == "RED":
        go_status = "NO-GO"
    elif overall == "YELLOW":
        go_status = "GO WITH WARNINGS"
    else:
        go_status = "GO"

    return {
        "audited_at": audited_at,
        "db_path": str(db_path),
        "db_size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "sections": sections,
        "area_scores": area_scores,
        "overall_score": overall,
        "go_status": go_status,
        "blockers": blockers,
        "warnings": warnings,
        "row_counts": row_counts,
        "tables_present": list(row_counts.keys()),
    }


def _render_summary(result):
    lines = [
        "# Migration Integrity Summary",
        "",
        f"**Audited at:** {result['audited_at']}",
        f"**Database:** `{result['db_path']}`",
        f"**Database size:** {result['db_size_bytes']:,} bytes",
        "",
        "## Executive Summary",
        "",
        f"This read-only audit scanned the active SQLite database for migration blockers and data-quality warnings "
        f"across companies, branches, users, journals, POS, inventory, AR/AP, and branch governance.",
        "",
        f"**Overall readiness score:** **{result['overall_score']}**",
        f"**Recommendation:** **{result['go_status']}**",
        "",
        "## Area Scores",
        "",
        "| Area | Score |",
        "|------|-------|",
    ]
    for area, score in result["area_scores"].items():
        lines.append(f"| {area} | {score} |")
    lines.extend(["", "## Top Blockers", ""])
    if result["blockers"]:
        for item in result["blockers"][:15]:
            lines.append(f"- **{item.name}:** {item.count}")
    else:
        lines.append("- None detected.")
    lines.extend(["", "## Top Warnings", ""])
    if result["warnings"]:
        for item in sorted(result["warnings"], key=lambda x: (-x.count, x.name))[:15]:
            lines.append(f"- **{item.name}:** {item.count} ({item.risk})")
    else:
        lines.append("- None detected.")
    lines.extend(["", "## Row Count Snapshot", ""])
    for table, count in sorted(result["row_counts"].items()):
        lines.append(f"- `{table}`: {count:,}")
    lines.extend(
        [
            "",
            "## Go / No-Go",
            "",
            f"**Decision:** {result['go_status']}",
            "",
        ]
    )
    if result["blockers"]:
        lines.append("**Exact blockers:**")
        for item in result["blockers"]:
            lines.append(f"- {item.name}: {item.count}")
    else:
        lines.append("No migration blockers detected in this audit pass.")
    lines.append("")
    return "\n".join(lines)


def _render_full(result):
    lines = [
        "# Migration Integrity Audit (Detailed)",
        "",
        f"**Audited at:** {result['audited_at']}",
        f"**Database:** `{result['db_path']}`",
        f"**Overall score:** {result['overall_score']}",
        f"**Go/No-Go:** {result['go_status']}",
        "",
        "All checks are SELECT-only. No data or schema modifications were performed.",
        "",
    ]
    for area, findings in result["sections"].items():
        score = result["area_scores"].get(area, "GREEN")
        lines.extend([f"## {area}", "", f"**Area score:** {score}", ""])
        lines.append("| Check | Count | Risk | Remediation |")
        lines.append("|-------|------:|------|-------------|")
        for finding in findings:
            remediation = "No action required."
            if finding.is_blocker and finding.count:
                remediation = "Resolve before PostgreSQL migration cutover."
            elif finding.count and finding.risk == "MEDIUM":
                remediation = "Review and clean up before migration; may not block cutover."
            elif finding.count and finding.risk == "LOW":
                remediation = "Informational; monitor during migration dry-run."
            if finding.name == "duplicate_source_postings" and finding.count:
                remediation = "Review rows; POS may legitimately have Sale + COGS journal pairs."
            if finding.name == "sales_without_journal_entry" and finding.count:
                remediation = "Verify whether revenue posting is expected for all sales."
            lines.append(
                f"| {finding.name} | {finding.count} | {finding.risk} | {remediation} |"
            )
            if finding.sql:
                lines.extend(["", f"SQL (`{finding.name}`):", "", "```sql", finding.sql.strip(), "```", ""])
            if finding.note:
                lines.extend(["", f"Note: {finding.note}", ""])
        lines.append("")
    lines.extend(["## Tables Present", ""])
    for table in result["tables_present"]:
        lines.append(f"- `{table}` ({result['row_counts'].get(table, 0):,} rows)")
    lines.append("")
    return "\n".join(lines)


def main():
    db_path = Path(os.environ.get("EKA_AUDIT_DB_PATH", DEFAULT_DB_PATH))
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    result = run_audit(db_path)
    summary_path = REPORTS_DIR / "migration_integrity_summary.md"
    audit_path = REPORTS_DIR / "migration_integrity_audit.md"
    summary_path.write_text(_render_summary(result), encoding="utf-8")
    audit_path.write_text(_render_full(result), encoding="utf-8")
    print(f"Wrote {summary_path}")
    print(f"Wrote {audit_path}")
    print(f"Overall score: {result['overall_score']}")
    print(f"Go/No-Go: {result['go_status']}")
    print(f"Blockers: {len(result['blockers'])}")
    print(f"Warnings: {len(result['warnings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
