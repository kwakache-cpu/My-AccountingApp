from __future__ import annotations

from datetime import datetime
import sqlite3

import pandas as pd

from database import get_connection


LEGACY_TABLES = {"vouchers", "transactions"}


def _resolve_date(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _normal_balance(account_type):
    normalized = str(account_type or "").strip().title()
    return "debit" if normalized in ("Asset", "Expense") else "credit"


def _period_locked(conn, company_key, entry_date):
    if not company_key or not entry_date:
        return False
    row = conn.execute(
        """
        SELECT 1
        FROM accounting_periods
        WHERE company_key = ?
          AND is_locked = 1
          AND date(?) BETWEEN date(start_date) AND date(end_date)
        LIMIT 1
        """,
        (company_key, _resolve_date(entry_date)),
    ).fetchone()
    return bool(row)


def _coa_name_expression():
    return "COALESCE(NULLIF(name, ''), NULLIF(account_name, ''), '')"


def _coa_type_expression():
    return "COALESCE(NULLIF(type, ''), NULLIF(account_type, ''), NULLIF(category, ''), 'Asset')"


def get_or_create_account(conn, account_name, account_type, parent_id=None, account_code=None):
    account_name = str(account_name or "").strip()
    account_type = str(account_type or "").strip().title()
    account_code = str(account_code or "").strip()
    if not account_name or not account_type:
        raise ValueError("Account name and type are required.")

    row = conn.execute(
        f"""
        SELECT id
        FROM chart_of_accounts
        WHERE lower({_coa_name_expression()}) = lower(?)
        LIMIT 1
        """,
        (account_name,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE chart_of_accounts
            SET name = COALESCE(NULLIF(name, ''), ?),
                account_name = COALESCE(NULLIF(account_name, ''), ?),
                type = COALESCE(NULLIF(type, ''), ?),
                account_type = COALESCE(NULLIF(account_type, ''), ?),
                category = COALESCE(NULLIF(category, ''), ?),
                code = COALESCE(NULLIF(code, ''), NULLIF(?, ''), code),
                account_code = COALESCE(NULLIF(account_code, ''), NULLIF(?, ''), account_code),
                parent_id = COALESCE(parent_id, ?)
            WHERE id = ?
            """,
            (account_name, account_name, account_type, account_type, account_type, account_code, account_code, parent_id, int(row["id"])),
        )
        return int(row["id"])

    cursor = conn.execute(
        """
        INSERT INTO chart_of_accounts (name, type, parent_id, code, category, account_code, account_name, account_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_name, account_type, parent_id, account_code or None, account_type, account_code or None, account_name, account_type),
    )
    return int(cursor.lastrowid)


def get_account_id(conn, account_name, account_type=None):
    row = conn.execute(
        f"""
        SELECT id, {_coa_type_expression()} AS account_type
        FROM chart_of_accounts
        WHERE lower({_coa_name_expression()}) = lower(?)
        LIMIT 1
        """,
        (str(account_name or "").strip(),),
    ).fetchone()
    if row:
        return int(row["id"])
    if account_type is None:
        raise ValueError(f"Account '{account_name}' does not exist.")
    return get_or_create_account(conn, account_name, account_type)


def _mirror_legacy_transactions(conn, company_key, entry_date, description, reference, created_by, branch_id, normalized_lines):
    try:
        conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'transactions'").fetchone()
        for line in normalized_lines:
            conn.execute(
                """
                INSERT INTO transactions (company_key, transaction_date, account, description, debit, credit, reference, created_by, branch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_key,
                    entry_date,
                    line["account_name"],
                    f"{description} [legacy mirror]",
                    line["debit"],
                    line["credit"],
                    reference,
                    created_by,
                    branch_id,
                ),
            )
    except sqlite3.Error:
        return


def _legacy_voucher_insert(
    conn,
    company_key,
    branch_id,
    entry_date,
    description,
    reference,
    created_by,
    normalized_lines,
    source_module=None,
):
    try:
        revenue = sum(line["credit"] for line in normalized_lines if line["account_type"] == "Income")
        if revenue <= 0:
            return
        conn.execute(
            """
            INSERT INTO vouchers (company_key, branch_id, date, v_type, ledger, credit, reference_no, narration, status, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?)
            """,
            (
                company_key,
                branch_id,
                entry_date,
                "Journal",
                source_module or "Legacy Mirror",
                revenue,
                reference,
                f"{description} [legacy mirror]",
                created_by,
            ),
        )
    except sqlite3.Error:
        return


def post_journal_entry(
    company_key,
    date,
    description,
    reference,
    lines,
    created_by,
    branch_id=None,
    customer_id=None,
    supplier_id=None,
    inventory_item_id=None,
    payment_id=None,
    source_module=None,
    source_table=None,
    source_id=None,
    conn=None,
):
    if not lines:
        raise ValueError("Journal entry lines are required.")

    entry_date = _resolve_date(date)
    owns_connection = conn is None
    conn = conn or get_connection()
    if conn is None:
        raise RuntimeError("Database connection unavailable.")
    if _period_locked(conn, company_key, entry_date):
        raise ValueError(f"The accounting period for {entry_date[:7]} is locked.")

    normalized_lines = []
    total_debit = 0.0
    total_credit = 0.0
    for line in lines:
        account_id = int(line.get("account_id") or 0)
        debit = round(float(line.get("debit") or 0.0), 2)
        credit = round(float(line.get("credit") or 0.0), 2)
        if account_id <= 0:
            raise ValueError("Every journal line requires a valid account_id.")
        if debit < 0 or credit < 0:
            raise ValueError("Debit and credit amounts cannot be negative.")
        if debit == 0 and credit == 0:
            continue
        if debit > 0 and credit > 0:
            raise ValueError("A journal line cannot contain both debit and credit values.")
        account_row = conn.execute(
            f"""
            SELECT id,
                   {_coa_name_expression()} AS account_name,
                   {_coa_type_expression()} AS account_type
            FROM chart_of_accounts
            WHERE id = ?
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()
        if not account_row:
            raise ValueError(f"Account ID {account_id} does not exist.")
        normalized_lines.append(
            {
                "account_id": account_id,
                "account_name": str(account_row["account_name"]),
                "account_type": str(account_row["account_type"]),
                "debit": debit,
                "credit": credit,
            }
        )
        total_debit += debit
        total_credit += credit

    total_debit = round(total_debit, 2)
    total_credit = round(total_credit, 2)
    if not normalized_lines:
        raise ValueError("Journal entry must include at least one non-zero line.")
    if total_debit != total_credit:
        raise ValueError(f"Unbalanced journal entry: debit={total_debit:.2f}, credit={total_credit:.2f}")

    try:
        cursor = conn.execute(
            """
            INSERT INTO journal_entries (
                company_key, date, description, reference, created_by, branch_id,
                customer_id, supplier_id, inventory_item_id, payment_id,
                source_module, source_table, source_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_key,
                entry_date,
                description,
                reference,
                created_by,
                branch_id,
                customer_id,
                supplier_id,
                inventory_item_id,
                payment_id,
                source_module,
                source_table,
                source_id,
            ),
        )
        entry_id = int(cursor.lastrowid)
        for line in normalized_lines:
            conn.execute(
                """
                INSERT INTO journal_lines (entry_id, account_id, debit, credit)
                VALUES (?, ?, ?, ?)
                """,
                (entry_id, line["account_id"], line["debit"], line["credit"]),
            )
        _mirror_legacy_transactions(conn, company_key, entry_date, description, reference, created_by, branch_id, normalized_lines)
        if source_module:
            _legacy_voucher_insert(conn, company_key, branch_id, entry_date, description, reference, created_by, normalized_lines, source_module=source_module)
        if owns_connection:
            conn.commit()
        return entry_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def _journal_base_query():
    return f"""
        SELECT
            je.id AS entry_id,
            je.date,
            je.description,
            je.reference,
            je.created_by,
            je.branch_id,
            je.customer_id,
            je.supplier_id,
            je.inventory_item_id,
            je.payment_id,
            je.source_module,
            je.source_table,
            je.source_id,
            c.id AS account_id,
            COALESCE(NULLIF(c.code, ''), NULLIF(c.account_code, ''), '') AS account_code,
            {_coa_name_expression()} AS account_name,
            {_coa_type_expression()} AS account_type,
            jl.debit,
            jl.credit
        FROM journal_entries je
        JOIN journal_lines jl ON jl.entry_id = je.id
        JOIN chart_of_accounts c ON c.id = jl.account_id
        WHERE je.company_key = ?
    """


def _journal_dataframe(company_key, start_date=None, end_date=None, branch_id=None, account_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = _journal_base_query()
        params = [company_key]
        if start_date:
            query += " AND date(je.date) >= date(?)"
            params.append(_resolve_date(start_date))
        if end_date:
            query += " AND date(je.date) <= date(?)"
            params.append(_resolve_date(end_date))
        if branch_id:
            query += " AND je.branch_id = ?"
            params.append(branch_id)
        if account_id:
            query += " AND c.id = ?"
            params.append(int(account_id))
        query += " ORDER BY date(je.date), je.id, jl.id"
        return pd.read_sql_query(query, conn, params=params)
    finally:
        if owns_connection and conn:
            conn.close()


def get_trial_balance(company_key, start_date=None, end_date=None):
    df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date)
    if df.empty:
        return []
    grouped = (
        df.groupby(["account_id", "account_code", "account_name", "account_type"], as_index=False)[["debit", "credit"]]
        .sum()
        .sort_values(["account_code", "account_name"], na_position="last")
    )
    rows = []
    for _, row in grouped.iterrows():
        debit_total = round(float(row["debit"] or 0.0), 2)
        credit_total = round(float(row["credit"] or 0.0), 2)
        balance = round(
            debit_total - credit_total if _normal_balance(row["account_type"]) == "debit" else credit_total - debit_total,
            2,
        )
        rows.append(
            {
                "account_id": int(row["account_id"]),
                "account_code": row["account_code"],
                "account_name": row["account_name"],
                "account_type": row["account_type"],
                "debit_total": debit_total,
                "credit_total": credit_total,
                "balance": balance,
            }
        )
    return rows


def get_general_ledger(company_key, account_id, start_date, end_date):
    df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date, account_id=account_id)
    if df.empty:
        return []
    running_balance = 0.0
    rows = []
    normal = _normal_balance(df["account_type"].iloc[0])
    for _, row in df.iterrows():
        debit = round(float(row["debit"] or 0.0), 2)
        credit = round(float(row["credit"] or 0.0), 2)
        movement = debit - credit if normal == "debit" else credit - debit
        running_balance = round(running_balance + movement, 2)
        rows.append(
            {
                "date": row["date"],
                "description": row["description"],
                "reference": row["reference"],
                "debit": debit,
                "credit": credit,
                "running_balance": running_balance,
            }
        )
    return rows


def generate_income_statement(company_key, start_date, end_date):
    rows = []
    total_income = 0.0
    total_expenses = 0.0
    for row in get_trial_balance(company_key, start_date=start_date, end_date=end_date):
        account_type = str(row["account_type"]).title()
        if account_type == "Income":
            amount = round(row["credit_total"] - row["debit_total"], 2)
            total_income += amount
            rows.append({"category": "Income", "account_id": row["account_id"], "account_code": row["account_code"], "account_name": row["account_name"], "amount": amount})
        elif account_type == "Expense":
            amount = round(row["debit_total"] - row["credit_total"], 2)
            total_expenses += amount
            rows.append({"category": "Expense", "account_id": row["account_id"], "account_code": row["account_code"], "account_name": row["account_name"], "amount": amount})
    rows.append({"category": "Profit", "account_id": None, "account_code": "", "account_name": "Net Profit", "amount": round(total_income - total_expenses, 2)})
    return rows


def generate_balance_sheet(company_key, as_of_date):
    rows = []
    for row in get_trial_balance(company_key, end_date=as_of_date):
        account_type = str(row["account_type"]).title()
        if account_type not in {"Asset", "Liability", "Equity"}:
            continue
        amount = round(row["debit_total"] - row["credit_total"], 2) if account_type == "Asset" else round(row["credit_total"] - row["debit_total"], 2)
        rows.append({"category": account_type, "account_id": row["account_id"], "account_code": row["account_code"], "account_name": row["account_name"], "amount": amount})
    profit_rows = generate_income_statement(company_key, None, as_of_date)
    net_profit = next((row["amount"] for row in profit_rows if row["account_name"] == "Net Profit"), 0.0)
    rows.append({"category": "Equity", "account_id": None, "account_code": "", "account_name": "Current Period Earnings", "amount": round(net_profit, 2)})
    return rows


def generate_cash_flow_statement(company_key, start_date, end_date):
    journal_df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date)
    if journal_df.empty:
        return []
    cash_df = journal_df[journal_df["account_name"].isin(["Cash", "Bank", "Mobile Money"])].copy()
    if cash_df.empty:
        return []
    operating = round(float((cash_df["debit"] - cash_df["credit"]).sum()), 2)
    income_statement = generate_income_statement(company_key, start_date, end_date)
    depreciation = round(
        sum(row["amount"] for row in income_statement if "depreciation" in str(row["account_name"]).lower()),
        2,
    )
    return [
        {"section": "Operating Activities", "line_item": "Net Cash Movement in Cash Accounts", "amount": operating},
        {"section": "Operating Activities", "line_item": "Depreciation Add-Back", "amount": depreciation},
        {"section": "Net Change", "line_item": "Net Cash Change", "amount": round(operating + depreciation, 2)},
    ]


def get_customer_balance(company_key, customer_id, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(jl.debit - jl.credit), 0) AS balance
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND je.customer_id = ?
              AND lower({_coa_name_expression()}) LIKE 'accounts receivable%'
              { "AND date(je.date) <= date(?)" if as_of_date else "" }
            """,
            (company_key, int(customer_id), _resolve_date(as_of_date)) if as_of_date else (company_key, int(customer_id)),
        ).fetchone()
        return round(float(row["balance"] or 0.0), 2) if row else 0.0
    finally:
        if owns_connection and conn:
            conn.close()


def get_customer_balances(company_key, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, customer_id, name, phone, email
            FROM customers
            WHERE company_key = ?
            ORDER BY name
            """,
            (company_key,),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "customer_id": row["customer_id"] or f"CUST-{int(row['id']):06d}",
                "name": row["name"],
                "phone": row["phone"],
                "email": row["email"],
                "balance": get_customer_balance(company_key, int(row["id"]), conn=conn),
            }
            for row in rows
        ]
    finally:
        if owns_connection and conn:
            conn.close()
