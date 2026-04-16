from __future__ import annotations

from datetime import datetime
import json
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


VALID_ACCOUNT_TYPES = {"Asset", "Liability", "Equity", "Income", "Expense"}


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
    source_type=None,
    source_id=None,
    approval_status="Posted",
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
        account_type = str(account_row["account_type"]).strip().title()
        if account_type not in VALID_ACCOUNT_TYPES:
            raise ValueError(f"Account ID {account_id} has invalid type '{account_type}'.")
        normalized_lines.append(
            {
                "account_id": account_id,
                "account_name": str(account_row["account_name"]),
                "account_type": account_type,
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
                source_module, source_table, source_type, source_id,
                approval_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                source_type,
                source_id,
                approval_status,
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


def reverse_journal_entry(entry_id, created_by=None, reversal_date=None, reason=None, branch_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        original = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
        if not original:
            raise ValueError(f"Journal entry {entry_id} not found.")
        if original["is_voided"]:
            raise ValueError(f"Journal entry {entry_id} is already voided.")
        if str(original["source_type"] or "").lower() == "reversal":
            raise ValueError("Cannot reverse a reversal entry.")
        if original["reversed_entry_id"]:
            raise ValueError(f"Journal entry {entry_id} has already been reversed.")

        reversal_date = _resolve_date(reversal_date or datetime.now().date())
        reversal_lines = []
        for row in conn.execute("SELECT account_id, debit, credit FROM journal_lines WHERE entry_id = ?", (entry_id,)):
            reversal_lines.append({"account_id": int(row["account_id"]), "debit": float(row["credit"] or 0.0), "credit": float(row["debit"] or 0.0)})
        if not reversal_lines:
            raise ValueError(f"Journal entry {entry_id} contains no lines to reverse.")

        reference = f"REV-{entry_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        description = f"Reversal of journal entry {entry_id}"
        if reason:
            description = f"{description}: {reason}"

        reversal_id = post_journal_entry(
            company_key=original["company_key"],
            date=reversal_date,
            description=description,
            reference=reference,
            lines=reversal_lines,
            created_by=created_by or original["created_by"],
            branch_id=branch_id or original["branch_id"],
            source_module="Journal Reversal",
            source_table="journal_entries",
            source_type="Reversal",
            source_id=entry_id,
            approval_status="Posted",
            conn=conn,
        )
        conn.execute(
            "UPDATE journal_entries SET reversed_entry_id = ? WHERE id = ?",
            (reversal_id, entry_id),
        )
        if owns_connection:
            conn.commit()
        return reversal_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def void_journal_entry(entry_id, voided_by=None, voided_at=None, reason=None, branch_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        original = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
        if not original:
            raise ValueError(f"Journal entry {entry_id} not found.")
        if original["is_voided"]:
            raise ValueError(f"Journal entry {entry_id} is already voided.")

        reversal_id = reverse_journal_entry(
            entry_id,
            created_by=voided_by or original["created_by"],
            reversal_date=voided_at or datetime.now().date(),
            reason=reason or "Voided by user",
            branch_id=branch_id or original["branch_id"],
            conn=conn,
        )
        voided_timestamp = _resolve_date(voided_at or datetime.now().date())
        conn.execute(
            "UPDATE journal_entries SET is_voided = 1, voided_at = ?, voided_by = ?, approval_status = 'Voided' WHERE id = ?",
            (voided_timestamp, voided_by or original["created_by"], entry_id),
        )
        if owns_connection:
            conn.commit()
        return reversal_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def allocate_payment(payment_id, invoice_id=None, bill_id=None, amount=None, created_by=None, branch_id=None, conn=None):
    if amount is None or amount <= 0:
        raise ValueError("Allocation amount must be a positive number.")
    if not invoice_id and not bill_id:
        raise ValueError("Either invoice_id or bill_id must be provided for payment allocation.")
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not payment:
            raise ValueError(f"Payment {payment_id} does not exist.")

        if invoice_id:
            invoice = conn.execute("SELECT amount FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            if not invoice:
                raise ValueError(f"Invoice {invoice_id} does not exist.")
            outstanding = float(invoice["amount"] or 0.0) - float(conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payment_allocations WHERE invoice_id = ?", (invoice_id,)).fetchone()[0] or 0.0)
            if amount > outstanding:
                raise ValueError(f"Allocation amount exceeds outstanding invoice balance ({outstanding:.2f}).")
        if bill_id:
            bill = conn.execute("SELECT amount FROM bills WHERE id = ?", (bill_id,)).fetchone()
            if not bill:
                raise ValueError(f"Bill {bill_id} does not exist.")
            outstanding = float(bill["amount"] or 0.0) - float(conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payment_allocations WHERE bill_id = ?", (bill_id,)).fetchone()[0] or 0.0)
            if amount > outstanding:
                raise ValueError(f"Allocation amount exceeds outstanding bill balance ({outstanding:.2f}).")

        cursor = conn.execute(
            "INSERT INTO payment_allocations (company_key, payment_id, invoice_id, bill_id, amount, currency, branch_id, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payment["company_key"],
                payment_id,
                invoice_id,
                bill_id,
                amount,
                payment["currency"],
                branch_id or payment["branch_id"],
                created_by or payment["created_by"],
            ),
        )
        if owns_connection:
            conn.commit()
        return int(cursor.lastrowid)
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def get_payment_allocations(payment_id=None, invoice_id=None, bill_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = "SELECT * FROM payment_allocations WHERE 1=1"
        params = []
        if payment_id:
            query += " AND payment_id = ?"
            params.append(payment_id)
        if invoice_id:
            query += " AND invoice_id = ?"
            params.append(invoice_id)
        if bill_id:
            query += " AND bill_id = ?"
            params.append(bill_id)
        return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    finally:
        if owns_connection and conn:
            conn.close()


def create_bank_account(company_key, account_name, bank_name=None, account_number=None, currency="GHS", account_type="Bank", branch_id=None, opening_balance=0.0, created_by=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO bank_accounts (company_key, branch_id, account_name, account_number, bank_name, account_type, currency, balance, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_key, branch_id, account_name, account_number, bank_name, account_type, currency, opening_balance, created_by),
        )
        if owns_connection:
            conn.commit()
        return int(cursor.lastrowid)
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def get_bank_account(account_id, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute("SELECT * FROM bank_accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None
    finally:
        if owns_connection and conn:
            conn.close()


def get_bank_accounts(company_key, branch_id=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        query = "SELECT * FROM bank_accounts WHERE company_key = ?"
        params = [company_key]
        if branch_id:
            query += " AND branch_id = ?"
            params.append(branch_id)
        return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    finally:
        if owns_connection and conn:
            conn.close()


def _next_recurrence_date(current_date, frequency):
    if frequency == "Daily":
        return current_date + pd.Timedelta(days=1)
    if frequency == "Weekly":
        return current_date + pd.Timedelta(weeks=1)
    if frequency == "Monthly":
        return current_date + pd.DateOffset(months=1)
    if frequency == "Quarterly":
        return current_date + pd.DateOffset(months=3)
    if frequency == "Yearly":
        return current_date + pd.DateOffset(years=1)
    raise ValueError(f"Unsupported recurrence frequency: {frequency}")


def schedule_recurring_transaction(company_key, description, frequency, amount, next_run_date, lines, created_by, branch_id=None, source_module=None, source_table=None, source_id=None, active=True, conn=None):
    if frequency not in {"Daily", "Weekly", "Monthly", "Quarterly", "Yearly"}:
        raise ValueError("Frequency must be one of Daily, Weekly, Monthly, Quarterly, Yearly.")
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        payload = json.dumps(lines)
        cursor = conn.execute(
            "INSERT INTO recurring_transactions (company_key, branch_id, description, frequency, amount, next_run_date, is_active, source_module, source_table, source_id, created_by, recurrence_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_key, branch_id, description, frequency, amount, _resolve_date(next_run_date), 1 if active else 0, source_module, source_table, source_id, created_by, payload),
        )
        if owns_connection:
            conn.commit()
        return int(cursor.lastrowid)
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection and conn:
            conn.close()


def get_due_recurring_transactions(company_key=None, run_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        today = _resolve_date(run_date or datetime.now().date())
        query = "SELECT * FROM recurring_transactions WHERE is_active = 1 AND date(next_run_date) <= date(?)"
        params = [today]
        if company_key:
            query = "SELECT * FROM recurring_transactions WHERE is_active = 1 AND company_key = ? AND date(next_run_date) <= date(?)"
            params = [company_key, today]
        return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    finally:
        if owns_connection and conn:
            conn.close()


def run_recurring_transactions(company_key=None, run_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        due = get_due_recurring_transactions(company_key=company_key, run_date=run_date, conn=conn)
        count = 0
        for row in due:
            payload = row.get("recurrence_payload")
            if not payload:
                continue
            lines = json.loads(payload)
            entry_date = _resolve_date(run_date or row["next_run_date"] or datetime.now().date())
            try:
                post_journal_entry(
                    company_key=row["company_key"],
                    date=entry_date,
                    description=f"Recurring: {row['description']}",
                    reference=f"REC-{row['id']}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    lines=lines,
                    created_by=row["created_by"],
                    branch_id=row["branch_id"],
                    source_module=row["source_module"],
                    source_table=row["source_table"],
                    source_type="Recurring",
                    source_id=row["source_id"],
                    conn=conn,
                )
                next_run = _next_recurrence_date(pd.Timestamp(entry_date), row["frequency"]).date()
                conn.execute(
                    "UPDATE recurring_transactions SET last_run_at = ?, next_run_date = ? WHERE id = ?",
                    (datetime.now().isoformat(), next_run.isoformat(), row["id"]),
                )
                count += 1
            except Exception:
                continue
        if owns_connection:
            conn.commit()
        return count
    finally:
        if owns_connection and conn:
            conn.close()


def post_vat_transaction(company_key, date, description, net_amount, vat_amount, vat_type, created_by, branch_id=None, source_module=None, source_table=None, source_id=None, conn=None):
    if vat_type not in {"InputVAT", "OutputVAT"}:
        raise ValueError("vat_type must be 'InputVAT' or 'OutputVAT'.")
    if vat_amount < 0:
        raise ValueError("VAT amount cannot be negative.")
    total_amount = net_amount + vat_amount
    vat_account = "VAT Payable" if vat_type == "OutputVAT" else "VAT Receivable"
    revenue_account = "Sales Revenue" if vat_type == "OutputVAT" else "Inventory"
    lines = [
        {"account_id": get_account_id(conn, revenue_account, "Income" if vat_type == "OutputVAT" else "Asset"), "debit": net_amount if vat_type == "InputVAT" else 0, "credit": net_amount if vat_type == "OutputVAT" else 0},
        {"account_id": get_account_id(conn, vat_account, "Liability" if vat_type == "OutputVAT" else "Asset"), "debit": vat_amount if vat_type == "InputVAT" else 0, "credit": vat_amount if vat_type == "OutputVAT" else 0},
        {"account_id": get_account_id(conn, "Cash" if vat_type == "OutputVAT" else "Accounts Payable", "Asset" if vat_type == "OutputVAT" else "Liability"), "debit": total_amount if vat_type == "OutputVAT" else 0, "credit": total_amount if vat_type == "InputVAT" else 0},
    ]
    return post_journal_entry(
        company_key=company_key,
        date=date,
        description=description,
        reference=f"VAT-{source_id}" if source_id else None,
        lines=lines,
        created_by=created_by,
        branch_id=branch_id,
        source_module=source_module,
        source_table=source_table,
        source_type="VAT",
        source_id=source_id,
        conn=conn,
    )


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
            je.source_type,
            je.source_id,
            je.reversed_entry_id,
            je.is_voided,
            je.voided_at,
            je.voided_by,
            je.approval_status,
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


def get_trial_balance(company_key, start_date=None, end_date=None, branch_id=None):
    df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date, branch_id=branch_id)
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


def generate_income_statement(company_key, start_date, end_date, branch_id=None):
    rows = []
    total_income = 0.0
    total_expenses = 0.0
    for row in get_trial_balance(company_key, start_date=start_date, end_date=end_date, branch_id=branch_id):
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


def generate_balance_sheet(company_key, as_of_date, branch_id=None):
    rows = []
    for row in get_trial_balance(company_key, end_date=as_of_date, branch_id=branch_id):
        account_type = str(row["account_type"]).title()
        if account_type not in {"Asset", "Liability", "Equity"}:
            continue
        amount = round(row["debit_total"] - row["credit_total"], 2) if account_type == "Asset" else round(row["credit_total"] - row["debit_total"], 2)
        rows.append({"category": account_type, "account_id": row["account_id"], "account_code": row["account_code"], "account_name": row["account_name"], "amount": amount})
    profit_rows = generate_income_statement(company_key, None, as_of_date, branch_id=branch_id)
    net_profit = next((row["amount"] for row in profit_rows if row["account_name"] == "Net Profit"), 0.0)
    rows.append({"category": "Equity", "account_id": None, "account_code": "", "account_name": "Current Period Earnings", "amount": round(net_profit, 2)})
    return rows


def generate_cash_flow_statement(company_key, start_date, end_date, branch_id=None):
    journal_df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date, branch_id=branch_id)
    if journal_df.empty:
        return []
    cash_df = journal_df[journal_df["account_name"].isin(["Cash", "Bank", "Mobile Money"])].copy()
    if cash_df.empty:
        return []
    rows = []
    totals = {"Operating Activities": 0.0, "Investing Activities": 0.0, "Financing Activities": 0.0}
    for _, row in cash_df.iterrows():
        description = str(row["description"] or "").lower()
        other_side = journal_df[
            (journal_df["entry_id"] == row["entry_id"]) & (journal_df["account_id"] != row["account_id"])
        ]
        counterpart_types = {str(value).title() for value in other_side["account_type"].tolist()}
        counterpart_names = {str(value) for value in other_side["account_name"].tolist()}
        movement = round(float(row["debit"] or 0.0) - float(row["credit"] or 0.0), 2)
        if counterpart_types & {"Income", "Expense"} or "Accounts Receivable" in counterpart_names or "Accounts Payable" in counterpart_names:
            section = "Operating Activities"
        elif "Fixed Assets" in counterpart_names or "Inventory" in counterpart_names or "Accumulated Depreciation" in counterpart_names:
            section = "Investing Activities"
        elif counterpart_types & {"Equity", "Liability"} or "Owner Capital" in counterpart_names or "Retained Earnings" in counterpart_names:
            section = "Financing Activities"
        elif "depreciation" in description:
            section = "Operating Activities"
        else:
            section = "Operating Activities"
        totals[section] += movement
        rows.append(
            {
                "section": section,
                "line_item": row["description"],
                "amount": movement,
                "date": row["date"],
                "reference": row["reference"],
            }
        )
    rows.extend(
        [
            {"section": key, "line_item": f"Net Cash from {key}", "amount": round(value, 2), "date": None, "reference": None}
            for key, value in totals.items()
        ]
    )
    rows.append(
        {
            "section": "Net Change",
            "line_item": "Net Cash Change",
            "amount": round(sum(totals.values()), 2),
            "date": None,
            "reference": None,
        }
    )
    return rows


def _aging_bucket(days_outstanding):
    if days_outstanding <= 30:
        return "0-30 Days"
    if days_outstanding <= 60:
        return "31-60 Days"
    if days_outstanding <= 90:
        return "61-90 Days"
    return "91+ Days"


def get_ar_aging_report(company_key, as_of_date=None):
    report_date = pd.Timestamp(as_of_date or datetime.now().date())
    conn = get_connection()
    try:
        customers = conn.execute(
            "SELECT id, customer_id, name, phone, email FROM customers WHERE company_key = ? ORDER BY name",
            (company_key,),
        ).fetchall()
        rows = []
        for customer in customers:
            balance = get_customer_balance(company_key, int(customer["id"]), as_of_date=report_date.date(), conn=conn)
            if abs(balance) < 0.005:
                continue
            tx_rows = conn.execute(
                """
                SELECT transaction_date, amount, description
                FROM customer_transactions
                WHERE company_key = ? AND customer_id = ? AND transaction_type = 'Debit'
                ORDER BY date(transaction_date) ASC, id ASC
                """,
                (company_key, int(customer["id"])),
            ).fetchall()
            oldest_date = pd.Timestamp(report_date)
            if tx_rows:
                oldest_date = min(pd.Timestamp(row["transaction_date"]) for row in tx_rows if row["transaction_date"])
            days = int((report_date - oldest_date).days) if oldest_date is not None else 0
            rows.append(
                {
                    "customer_id": customer["customer_id"] or f"CUST-{int(customer['id']):06d}",
                    "customer_name": customer["name"],
                    "phone": customer["phone"],
                    "email": customer["email"],
                    "days_outstanding": days,
                    "bucket": _aging_bucket(days),
                    "balance": round(balance, 2),
                }
            )
        return rows
    finally:
        conn.close()


def get_supplier_balance(company_key, supplier_id, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(jl.credit - jl.debit), 0) AS balance
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND je.supplier_id = ?
              AND lower({_coa_name_expression()}) LIKE 'accounts payable%'
              {"AND date(je.date) <= date(?)" if as_of_date else ""}
            """,
            (company_key, int(supplier_id), _resolve_date(as_of_date)) if as_of_date else (company_key, int(supplier_id)),
        ).fetchone()
        return round(float(row["balance"] or 0.0), 2) if row else 0.0
    finally:
        if owns_connection and conn:
            conn.close()


def get_supplier_balances(company_key, as_of_date=None, conn=None):
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, name, email, phone, address
            FROM suppliers
            WHERE company_key = ?
            ORDER BY name
            """,
            (company_key,),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "email": row["email"],
                "phone": row["phone"],
                "address": row["address"],
                "balance": get_supplier_balance(company_key, int(row["id"]), as_of_date=as_of_date, conn=conn),
            }
            for row in rows
        ]
    finally:
        if owns_connection and conn:
            conn.close()


def get_ap_aging_report(company_key, as_of_date=None):
    report_date = pd.Timestamp(as_of_date or datetime.now().date())
    conn = get_connection()
    try:
        suppliers = conn.execute(
            """
            SELECT id, name, email, phone, address
            FROM suppliers
            WHERE company_key = ?
            ORDER BY name
            """,
            (company_key,),
        ).fetchall()
        rows = []
        for supplier in suppliers:
            supplier_id = int(supplier["id"])
            balance = get_supplier_balance(company_key, supplier_id, as_of_date=report_date.date(), conn=conn)
            if abs(balance) < 0.005:
                continue
            oldest_row = conn.execute(
                f"""
                SELECT MIN(date(je.date)) AS oldest_open_date
                FROM journal_entries je
                JOIN journal_lines jl ON jl.entry_id = je.id
                JOIN chart_of_accounts c ON c.id = jl.account_id
                WHERE je.company_key = ?
                  AND je.supplier_id = ?
                  AND jl.credit > 0
                  AND lower({_coa_name_expression()}) LIKE 'accounts payable%'
                  AND date(je.date) <= date(?)
                """,
                (company_key, supplier_id, _resolve_date(report_date.date())),
            ).fetchone()
            oldest_date = pd.Timestamp(oldest_row["oldest_open_date"]) if oldest_row and oldest_row["oldest_open_date"] else report_date
            days = int((report_date - oldest_date).days)
            rows.append(
                {
                    "supplier_id": supplier_id,
                    "supplier_name": supplier["name"],
                    "email": supplier["email"],
                    "phone": supplier["phone"],
                    "address": supplier["address"],
                    "days_outstanding": days,
                    "bucket": _aging_bucket(days),
                    "balance": round(balance, 2),
                }
            )
        return rows
    finally:
        conn.close()


def close_fiscal_year(company_key, closing_date, created_by, branch_id=None, conn=None):
    closing_date = _resolve_date(closing_date)
    owns_connection = conn is None
    conn = conn or get_connection()
    try:
        income_statement = generate_income_statement(company_key, None, closing_date)
        net_profit = round(sum(row["amount"] for row in income_statement if row["account_name"] == "Net Profit"), 2)
        if abs(net_profit) < 0.005:
            return None
        income_rows = [row for row in get_trial_balance(company_key, end_date=closing_date) if str(row["account_type"]).title() == "Income" and abs(row["credit_total"] - row["debit_total"]) > 0.005]
        expense_rows = [row for row in get_trial_balance(company_key, end_date=closing_date) if str(row["account_type"]).title() == "Expense" and abs(row["debit_total"] - row["credit_total"]) > 0.005]
        lines = []
        for row in income_rows:
            amount = round(row["credit_total"] - row["debit_total"], 2)
            lines.append({"account_id": row["account_id"], "debit": amount, "credit": 0})
        for row in expense_rows:
            amount = round(row["debit_total"] - row["credit_total"], 2)
            lines.append({"account_id": row["account_id"], "debit": 0, "credit": amount})
        retained_earnings_id = get_account_id(conn, "Retained Earnings", "Equity")
        if net_profit >= 0:
            lines.append({"account_id": retained_earnings_id, "debit": 0, "credit": net_profit})
        else:
            lines.append({"account_id": retained_earnings_id, "debit": abs(net_profit), "credit": 0})
        entry_id = post_journal_entry(
            company_key=company_key,
            date=closing_date,
            description=f"Year-end closing entry {closing_date[:4]}",
            reference=f"YEC-{closing_date}",
            lines=lines,
            created_by=created_by,
            branch_id=branch_id,
            source_module="Year End Closing",
            source_table="journal_entries",
            conn=conn,
        )
        if owns_connection:
            conn.commit()
        return entry_id
    finally:
        if owns_connection and conn:
            conn.close()


def get_bank_reconciliation(company_key, start_date=None, end_date=None):
    conn = get_connection()
    try:
        journal_df = _journal_dataframe(company_key, start_date=start_date, end_date=end_date, conn=conn)
        bank_df = journal_df[journal_df["account_name"].isin(["Bank", "Mobile Money"])].copy()
        if bank_df.empty:
            return {"matched": [], "unmatched_journal": [], "summary": {"journal_total": 0.0, "matched_total": 0.0, "unmatched_total": 0.0}}
        payment_rows = conn.execute(
            """
            SELECT id, payment_date, amount, method, reference, payment_type
            FROM payments
            WHERE company_key = ?
              AND method IN ('Bank', 'Mobile Money')
              {start_clause}
              {end_clause}
            ORDER BY date(payment_date), id
            """.format(
                start_clause="AND date(payment_date) >= date(?)" if start_date else "",
                end_clause="AND date(payment_date) <= date(?)" if end_date else "",
            ),
            tuple(
                [company_key]
                + ([_resolve_date(start_date)] if start_date else [])
                + ([_resolve_date(end_date)] if end_date else [])
            ),
        ).fetchall()
        matched = []
        unmatched = []
        used_payment_ids = set()
        for _, row in bank_df.iterrows():
            movement = round(float(row["debit"] or 0.0) - float(row["credit"] or 0.0), 2)
            match = next(
                (
                    payment
                    for payment in payment_rows
                    if int(payment["id"]) not in used_payment_ids
                    and round(float(payment["amount"] or 0.0), 2) == abs(movement)
                    and (not row["reference"] or not payment["reference"] or str(payment["reference"]) == str(row["reference"]))
                ),
                None,
            )
            journal_item = {
                "date": row["date"],
                "description": row["description"],
                "reference": row["reference"],
                "account": row["account_name"],
                "movement": movement,
            }
            if match:
                used_payment_ids.add(int(match["id"]))
                matched.append(
                    {
                        **journal_item,
                        "payment_id": int(match["id"]),
                        "payment_date": match["payment_date"],
                        "payment_reference": match["reference"],
                        "payment_type": match["payment_type"],
                    }
                )
            else:
                unmatched.append(journal_item)
        return {
            "matched": matched,
            "unmatched_journal": unmatched,
            "summary": {
                "journal_total": round(float(bank_df["debit"].sum() - bank_df["credit"].sum()), 2),
                "matched_total": round(sum(item["movement"] for item in matched), 2),
                "unmatched_total": round(sum(item["movement"] for item in unmatched), 2),
            },
        }
    finally:
        conn.close()


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
