from datetime import datetime
import importlib.util
import logging
import os
import sqlite3
import sys
import time

import pandas as pd
import streamlit as st
from security_utils import build_user_safe_error, sanitize_error_message

from database import (
    dataframe_from_portable_rows,
    db_insert_ignore_sql,
    db_table_exists,
    ensure_insert_sql_returning,
    execute_portable_query,
    execute_portable_write,
    fetch_scalar,
    get_active_db_backend,
    get_connection,
    get_inserted_id,
    is_postgres_backend,
    row_get,
    rows_to_dicts,
    sql_date_on_or_after,
    sql_date_on_or_before,
)
from accounting_engine import (
    close_fiscal_year,
    generate_cash_flow_statement as engine_generate_cash_flow_statement,
    get_account_id,
    get_ap_aging_report,
    get_ar_aging_report,
    get_bank_reconciliation,
    get_finance_integrity_diagnostics,
    post_accounting_impact as post_journal_entry,
)
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCUMENT_WORKFLOW_STATUSES = ["Draft", "Submitted", "Approved", "Posted", "Cancelled", "Voided"]


def _load_local_modules_module():
    try:
        import modules as loaded_modules

        logger.info(
            "Financials imported modules via standard registry lookup: module=%s file=%s",
            getattr(loaded_modules, "__name__", "modules"),
            getattr(loaded_modules, "__file__", "unknown"),
        )
        return loaded_modules
    except KeyError as exc:
        modules_path = os.path.join(BASE_DIR, "modules.py")
        logger.warning(
            "Financials encountered missing 'modules' registry entry; loading local modules.py explicitly: path=%s error=%s",
            modules_path,
            exc,
        )
        spec = importlib.util.spec_from_file_location("modules", modules_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not build import spec for local modules.py at {modules_path}") from exc
        loaded_modules = importlib.util.module_from_spec(spec)
        sys.modules["modules"] = loaded_modules
        spec.loader.exec_module(loaded_modules)
        logger.info(
            "Financials recovered modules import from local file: module=%s file=%s",
            getattr(loaded_modules, "__name__", "modules"),
            getattr(loaded_modules, "__file__", modules_path),
        )
        return loaded_modules


eka_modules = _load_local_modules_module()
convert_amount_from_base = eka_modules.convert_amount_from_base
format_currency = eka_modules.format_currency
format_currency_dataframe = eka_modules.format_currency_dataframe
get_currency_symbol = eka_modules.get_currency_symbol
get_display_currency = eka_modules.get_display_currency
get_exchange_rate = eka_modules.get_exchange_rate
post_transaction = eka_modules.post_transaction
require_permission = eka_modules.require_permission
set_period_lock = eka_modules.set_period_lock
set_period_status = eka_modules.set_period_status
show_journal_entries = eka_modules.show_journal_entries
user_has_permission = eka_modules.user_has_permission
log_audit_action = eka_modules.log_audit_action
log_system_event = eka_modules.log_system_event
render_invoice_line_editor = eka_modules.render_invoice_line_editor
save_invoice_lines = eka_modules.save_invoice_lines
apply_invoice_stock_effects = eka_modules.apply_invoice_stock_effects
PURCHASE_CLASSIFICATION_OPTIONS = eka_modules.PURCHASE_CLASSIFICATION_OPTIONS
FIXED_ASSET_PURCHASE_CATEGORIES = eka_modules.FIXED_ASSET_PURCHASE_CATEGORIES
build_purchase_journal_lines = eka_modules.build_purchase_journal_lines
get_purchase_expense_account_options = eka_modules.get_purchase_expense_account_options
build_sales_tax_journal_lines = eka_modules.build_sales_tax_journal_lines
_tax_amount = eka_modules._tax_amount


def _resolve_date(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _payment_method_account_name(payment_method):
    normalized_method = str(payment_method or "").strip()
    if normalized_method == "Bank":
        return "Bank"
    if normalized_method == "Mobile Money":
        return "Mobile Money"
    return "Cash"


def _journal_df(company_key, branch_id=None, start_date=None, end_date=None, account_name=None):
    conn = get_connection()
    try:
        query = """
            SELECT
                je.id AS entry_id,
                je.date,
                je.description,
                je.reference,
                je.created_by,
                COALESCE(c.code, c.account_code, '') AS account_code,
                COALESCE(c.name, c.account_name) AS account_name,
                COALESCE(c.type, c.category, c.account_type) AS account_type,
                jl.debit,
                jl.credit
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """
        params = [company_key]
        if branch_id:
            query += " AND je.branch_id = ?"
            params.append(branch_id)
        if start_date:
            query += f" AND {sql_date_on_or_after('je.date')}"
            params.append(_resolve_date(start_date))
        if end_date:
            query += f" AND {sql_date_on_or_before('je.date')}"
            params.append(_resolve_date(end_date))
        if account_name:
            query += " AND lower(COALESCE(c.name, c.account_name)) LIKE ?"
            params.append(f"%{str(account_name).lower()}%")
        query += " ORDER BY CAST(je.date AS date), je.id, COALESCE(c.name, c.account_name)"
        try:
            df = _portable_read_dataframe(conn, query, tuple(params))
        except (pd.errors.DatabaseError, AttributeError, sqlite3.DatabaseError):
            return pd.DataFrame()
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    finally:
        conn.close()


def _normal_balance(account_type):
    normalized = str(account_type or "").strip().title()
    return "debit" if normalized in ("Asset", "Expense") else "credit"


def _chart_lookup():
    conn = get_connection()
    try:
        try:
            rows = execute_portable_query(
                conn,
                """
                SELECT COALESCE(code, account_code, '') AS account_code,
                       COALESCE(name, account_name) AS account_name,
                       COALESCE(type, category, account_type) AS account_type
                FROM chart_of_accounts
                ORDER BY COALESCE(name, account_name)
                """,
            ).fetchall()
        except sqlite3.Error:
            return []
        return {
            str(row_get(row, "account_name", "")): {
                "account_type": str(row_get(row, "account_type", "")),
                "account_code": str(row_get(row, "account_code", "") or ""),
            }
            for row in rows
            if row_get(row, "account_name")
        }
    finally:
        conn.close()


def _party_id(conn, table_name, company_key, name):
    row = execute_portable_query(
        conn,
        f"SELECT id FROM {table_name} WHERE company_key = ? AND name = ?",
        (company_key, name),
    ).fetchone()
    if row:
        return int(row_get(row, "id", row_get(row, 0)))
    cursor = conn.execute(
        ensure_insert_sql_returning(
            f"INSERT INTO {table_name} (company_key, name, currency) VALUES (?, ?, 'GHS')"
        ),
        (company_key, name),
    )
    return get_inserted_id(cursor)


def _csv_button(label, dataframe, key):
    st.download_button(
        f"📥 Export {label} CSV",
        data=dataframe.to_csv(index=False).encode("utf-8") if not dataframe.empty else b"",
        file_name=f"{label.lower().replace(' ', '_')}.csv",
        mime="text/csv",
        key=key,
    )


def _money_label():
    return f"({get_currency_symbol()})"


def _account_label(account_code, account_name):
    code = str(account_code or "").strip()
    name = str(account_name or "").strip()
    return f"{code} - {name}" if code else name


def _portable_read_dataframe(conn, query, params=()):
    rows = execute_portable_query(conn, query, params or ()).fetchall()
    return pd.DataFrame(rows_to_dicts(rows))


def _convert_money_frame_legacy(dataframe):
    if dataframe.empty:
        return dataframe
    df = dataframe.copy()
    money_columns = [
        column_name
        for column_name in df.columns
        if any(token in str(column_name) for token in ("(GHS)", "Amount", "Debit", "Credit", "Balance", "Movement"))
    ]
    for column_name in money_columns:
        df[column_name] = pd.to_numeric(df[column_name], errors="coerce").fillna(0.0).map(convert_amount_from_base)
    renamed_columns = {}
    for column_name in df.columns:
        if "(GHS)" in str(column_name):
            renamed_columns[column_name] = str(column_name).replace("(GHS)", _money_label())
    return format_currency_dataframe(df.rename(columns=renamed_columns))


def _format_account_headers(dataframe):
    if dataframe.empty:
        return dataframe
    df = dataframe.copy()
    if "Account" in df.columns:
        code_column = "Account Code" if "Account Code" in df.columns else None
        if code_column:
            df["Account"] = df.apply(
                lambda row: _account_label(row.get(code_column), row.get("Account")),
                axis=1,
            )
    return df


def _filter_controls(prefix):
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.now().date().replace(day=1), key=f"{prefix}_start")
    with col2:
        end_date = st.date_input("End Date", value=datetime.now().date(), key=f"{prefix}_end")
    with col3:
        account_name = st.text_input("Account Filter", key=f"{prefix}_account")
    return start_date, end_date, account_name.strip()


def get_general_journal(company_key, start_date=None, end_date=None, account_name=None, branch_id=None):
    try:
        df = _journal_df(company_key, branch_id=branch_id, start_date=start_date, end_date=end_date, account_name=account_name)
    except (pd.errors.DatabaseError, AttributeError, sqlite3.DatabaseError):
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame(columns=["Date", "Entry ID", "Description", "Reference", "Created By", "Account Code", "Account", "Type", "Debit (GHS)", "Credit (GHS)"])
    df = df.rename(
        columns={
            "date": "Date",
            "entry_id": "Entry ID",
            "description": "Description",
            "reference": "Reference",
            "created_by": "Created By",
            "account_code": "Account Code",
            "account_name": "Account",
            "account_type": "Type",
            "debit": "Debit (GHS)",
            "credit": "Credit (GHS)",
        }
    )
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df


def get_sales_journal(company_key, start_date=None, end_date=None, account_name=None, branch_id=None):
    df = get_general_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)
    if df.empty:
        return df
    return df[
        df["Description"].str.contains("sale|invoice|customer", case=False, na=False)
        | df["Account"].isin(["Sales", "Sales Revenue", "Accounts Receivable", "Cash"])
    ].reset_index(drop=True)


def get_purchases_journal(company_key, start_date=None, end_date=None, account_name=None, branch_id=None):
    df = get_general_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)
    if df.empty:
        return df
    return df[
        df["Description"].str.contains("purchase|bill|supplier", case=False, na=False)
        | df["Account"].isin(["Inventory", "Purchases", "Accounts Payable", "Cash"])
    ].reset_index(drop=True)


def get_cash_book(company_key, start_date=None, end_date=None, account_name=None, branch_id=None):
    df = get_general_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)
    columns = [
        "Date",
        "Description",
        "Reference",
        "Account Code",
        "Account",
        "Debit (GHS)",
        "Credit (GHS)",
        "Movement (GHS)",
        "Account Running Balance (GHS)",
        "Cash Balance (GHS)",
        "Bank Balance (GHS)",
        "Mobile Money Balance (GHS)",
        "Combined Cash Equivalents Balance (GHS)",
        "Running Balance (GHS)",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    cash_df = df[df["Account"].isin(["Cash", "Bank", "Mobile Money"])].copy()
    if cash_df.empty:
        return pd.DataFrame(columns=columns)
    cash_df["Movement (GHS)"] = cash_df["Debit (GHS)"] - cash_df["Credit (GHS)"]
    cash_df["Account Running Balance (GHS)"] = cash_df.groupby("Account", sort=False)["Movement (GHS)"].cumsum()
    account_balances = (
        cash_df.pivot_table(
            index=cash_df.index,
            columns="Account",
            values="Movement (GHS)",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reindex(columns=["Cash", "Bank", "Mobile Money"], fill_value=0.0)
        .cumsum()
    )
    cash_df["Cash Balance (GHS)"] = account_balances["Cash"].values
    cash_df["Bank Balance (GHS)"] = account_balances["Bank"].values
    cash_df["Mobile Money Balance (GHS)"] = account_balances["Mobile Money"].values
    cash_df["Combined Cash Equivalents Balance (GHS)"] = (
        cash_df["Cash Balance (GHS)"] + cash_df["Bank Balance (GHS)"] + cash_df["Mobile Money Balance (GHS)"]
    )
    cash_df["Running Balance (GHS)"] = cash_df["Combined Cash Equivalents Balance (GHS)"]
    return cash_df[columns]


def get_general_ledger(company_key, start_date=None, end_date=None, account_name=None, branch_id=None):
    df = get_general_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)
    if df.empty:
        return pd.DataFrame(columns=["Date", "Account Code", "Account", "Description", "Reference", "Debit (GHS)", "Credit (GHS)", "Running Balance (GHS)"])
    frames = []
    for (_account_code, account), group in df.groupby(["Account Code", "Account"], sort=True):
        running = (group["Debit (GHS)"] - group["Credit (GHS)"]) if _normal_balance(group["Type"].iloc[0]) == "debit" else (group["Credit (GHS)"] - group["Debit (GHS)"])
        ledger_group = group.copy()
        ledger_group["Running Balance (GHS)"] = running.cumsum()
        frames.append(ledger_group[["Date", "Account Code", "Account", "Description", "Reference", "Debit (GHS)", "Credit (GHS)", "Running Balance (GHS)"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["Date", "Account Code", "Account", "Description", "Reference", "Debit (GHS)", "Credit (GHS)", "Running Balance (GHS)"])


def _get_trial_balance_legacy(company_key, start_date=None, end_date=None, account_name=None):
    df = _journal_df(company_key, start_date, end_date, account_name)
    if df.empty:
        return pd.DataFrame(columns=["Account Code", "Account", "Type", "Debit (GHS)", "Credit (GHS)", "Balance (GHS)", "Balanced"])
    grouped = df.groupby(["account_code", "account_name", "account_type"], as_index=False)[["debit", "credit"]].sum()
    grouped["Balance (GHS)"] = grouped.apply(
        lambda row: (row["debit"] - row["credit"]) if _normal_balance(row["account_type"]) == "debit" else (row["credit"] - row["debit"]),
        axis=1,
    )
    grouped = grouped[(grouped["debit"].abs() > 0.0001) | (grouped["credit"].abs() > 0.0001)].copy()
    balanced = abs(float(grouped["debit"].sum()) - float(grouped["credit"].sum())) < 0.01
    grouped["Balanced"] = "Yes" if balanced else "No"
    grouped = grouped.rename(
        columns={
            "account_code": "Account Code",
            "account_name": "Account",
            "account_type": "Type",
            "debit": "Debit (GHS)",
            "credit": "Credit (GHS)",
        }
    ).reset_index(drop=True)
    return grouped.sort_values(["Account Code", "Account"], na_position="last").reset_index(drop=True)


def _get_income_statement_legacy(company_key, start_date=None, end_date=None, account_name=None):
    tb = get_trial_balance(company_key, start_date, end_date, account_name)
    rows = []
    gross_revenue = 0.0
    sales_returns = 0.0
    cost_of_sales = 0.0
    operating_expenses = 0.0
    for _, row in tb.iterrows():
        account_type = str(row["Type"]).title()
        account = str(row["Account"] or "").strip()
        normalized_account = account.lower()
        if account_type == "Income":
            amount = float(row["Credit (GHS)"] - row["Debit (GHS)"])
            gross_revenue += amount
            rows.append({"Category": "Revenue", "Account Code": row["Account Code"], "Account": account, "Amount (GHS)": amount})
        elif account_type == "Expense":
            amount = float(row["Debit (GHS)"] - row["Credit (GHS)"])
            if normalized_account == "sales returns and refunds":
                sales_returns += amount
                rows.append({"Category": "Sales Deductions", "Account Code": row["Account Code"], "Account": "Less: Sales Returns and Refunds", "Amount (GHS)": -amount})
            elif normalized_account == "cost of goods sold":
                cost_of_sales += amount
                rows.append({"Category": "Cost of Sales", "Account Code": row["Account Code"], "Account": account, "Amount (GHS)": amount})
            else:
                operating_expenses += amount
                rows.append({"Category": "Operating Expenses", "Account Code": row["Account Code"], "Account": account, "Amount (GHS)": amount})
    net_sales = gross_revenue - sales_returns
    gross_profit = net_sales - cost_of_sales
    rows.append({"Category": "Revenue", "Account Code": "", "Account": "Net Sales", "Amount (GHS)": net_sales})
    rows.append({"Category": "Profit for the Period", "Account Code": "", "Account": "Gross Profit", "Amount (GHS)": gross_profit})
    rows.append({"Category": "Profit for the Period", "Account Code": "", "Account": "Net Profit", "Amount (GHS)": gross_profit - operating_expenses})
    return pd.DataFrame(rows)


def _get_balance_sheet_legacy(company_key, start_date=None, end_date=None, account_name=None):
    tb = get_trial_balance(company_key, start_date, end_date, account_name)
    rows = []
    for _, row in tb.iterrows():
        account_type = str(row["Type"]).title()
        if account_type not in ("Asset", "Liability", "Equity"):
            continue
        amount = float(row["Debit (GHS)"] - row["Credit (GHS)"]) if account_type == "Asset" else float(row["Credit (GHS)"] - row["Debit (GHS)"])
        category_map = {"Asset": "Assets", "Liability": "Liabilities", "Equity": "Equity"}
        rows.append({"Category": category_map.get(account_type, account_type), "Account Code": row["Account Code"], "Account": row["Account"], "Amount (GHS)": amount})
    return pd.DataFrame(rows)


def _get_cash_flow_statement_legacy(company_key, start_date=None, end_date=None, account_name=None):
    rows = engine_generate_cash_flow_statement(company_key, start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["Section", "Line Item", "Amount (GHS)"])
    return pd.DataFrame(
        [
            {
                "Section": row.get("section"),
                "Line Item": row.get("line_item"),
                "Amount (GHS)": row.get("amount", 0.0),
            }
            for row in rows
        ]
    )


def _get_changes_in_equity_legacy(company_key, start_date=None, end_date=None, account_name=None):
    bs_df = get_balance_sheet(company_key, start_date, end_date, account_name)
    income_df = get_income_statement(company_key, start_date, end_date, account_name)
    opening_equity = float(bs_df.loc[bs_df["Account"] == "Opening Balance Equity", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    owner_capital = float(bs_df.loc[bs_df["Account"] == "Owner Capital", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    retained_earnings = float(bs_df.loc[bs_df["Account"] == "Retained Earnings", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    net_profit = float(income_df.loc[income_df["Account"] == "Net Profit", "Amount (GHS)"].sum()) if not income_df.empty else 0.0
    return pd.DataFrame(
        [
            {"Account Code": "", "Line Item": "Opening Balance Equity", "Amount (GHS)": opening_equity},
            {"Account Code": "", "Line Item": "Owner Capital", "Amount (GHS)": owner_capital},
            {"Account Code": "", "Line Item": "Retained Earnings", "Amount (GHS)": retained_earnings},
            {"Account Code": "", "Line Item": "Profit for the Period", "Amount (GHS)": net_profit},
            {"Account Code": "", "Line Item": "Closing Equity", "Amount (GHS)": opening_equity + owner_capital + retained_earnings + net_profit},
        ]
    )


def get_depreciation_schedule(company_key):
    conn = get_connection()
    try:
        df = _portable_read_dataframe(
            conn,
            """
            SELECT
                asset_name AS "Asset Name",
                asset_category AS "Category",
                purchase_date AS "Purchase Date",
                cost AS "Cost (GHS)",
                useful_life_years AS "Useful Life (Years)",
                residual_value AS "Residual Value (GHS)",
                depreciation_method AS "Method",
                depreciation_rate AS "Rate (%)",
                accumulated_depreciation AS "Accumulated Depreciation (GHS)",
                book_value AS "Book Value (GHS)",
                last_depreciation_date AS "Last Depreciation Date",
                status AS "Status"
            FROM fixed_assets
            WHERE company_key = ?
            ORDER BY asset_name
            """,
            (company_key,),
        )
        return df
    finally:
        conn.close()


def _show_manual_record_transaction_legacy(company_key, role):
    st.header("🧾 Record Transaction")
    accounts = _chart_lookup()
    account_map = accounts if isinstance(accounts, dict) else {}
    with st.expander("Period Lock Controls", expanded=False):
        period_date = st.date_input("Accounting Period", value=datetime.now().date().replace(day=1), key=f"period_date_{company_key}")
        if st.button("Close Period", key=f"close_period_{company_key}"):
            if require_permission(role, "close_period", action_label="close accounting periods", company_key=company_key):
                set_period_status(company_key, period_date, "Closed", changed_by=role)
                st.success(f"Closed {period_date.strftime('%Y-%m')}")
        col1, col2 = st.columns(2)
        if col1.button("🔒 Lock Period", key=f"lock_period_{company_key}"):
            if require_permission(role, "lock_period", action_label="lock accounting periods", company_key=company_key):
                set_period_lock(company_key, period_date, True, locked_by=role)
                st.success(f"Locked {period_date.strftime('%Y-%m')}")
        if col2.button("🔓 Unlock Period", key=f"unlock_period_{company_key}"):
            if require_permission(role, "reopen_period", action_label="unlock accounting periods", company_key=company_key):
                set_period_lock(company_key, period_date, False, locked_by=role)
                st.success(f"Unlocked {period_date.strftime('%Y-%m')}")

    with st.form(f"manual_tx_form_{company_key}"):
        tx_date = st.date_input("Transaction Date", value=datetime.now().date(), key=f"manual_tx_date_{company_key}")
        description = st.text_input("Description", key=f"manual_tx_desc_{company_key}")
        reference = st.text_input("Reference", key=f"manual_tx_ref_{company_key}")
        lines = []
        account_names = [""] + list(account_map.keys())
        for idx in range(4):
            c1, c2, c3 = st.columns([3, 1, 1])
            account = c1.selectbox(f"Account {idx + 1}", account_names, key=f"manual_account_{company_key}_{idx}")
            debit = c2.number_input(f"Debit {idx + 1}", min_value=0.0, step=0.01, key=f"manual_debit_{company_key}_{idx}")
            credit = c3.number_input(f"Credit {idx + 1}", min_value=0.0, step=0.01, key=f"manual_credit_{company_key}_{idx}")
            if account and (debit > 0 or credit > 0):
                account_meta = account_map.get(account, {"account_type": "Expense", "account_code": ""})
                lines.append({"account_name": account, "account_type": account_meta.get("account_type", "Expense"), "debit": debit, "credit": credit})
        if st.form_submit_button("Post Transaction"):
            try:
                conn = get_connection()
                journal_lines = [
                    {
                        "account_id": get_account_id(conn, line["account_name"], line["account_type"]),
                        "debit": line["debit"],
                        "credit": line["credit"],
                    }
                    for line in lines
                ]
                if not journal_lines:
                    raise ValueError("Add at least one valid account line.")
                post_journal_entry(
                    company_key=company_key,
                    date=tx_date,
                    description=description or "Manual journal entry",
                    reference=reference,
                    lines=journal_lines,
                    created_by=role,
                    branch_id=st.session_state.get("active_branch_id"),
                    source_module="Manual Journal",
                    source_table="journal_entries",
                    manual_entry=True,
                    conn=conn,
                )
                conn.commit()
                conn.close()
                st.success("Transaction posted successfully.")
                st.rerun()
            except Exception as exc:
                st.error(build_user_safe_error(exc, role))


def show_invoice_manager(company_key, role):
    st.header("🧾 Invoice Manager")
    tabs = st.tabs(["Customers", "Suppliers", "Invoices", "Bills", "Payments"])

    with tabs[0]:
        with st.form(f"customer_form_{company_key}"):
            name = st.text_input("Customer Name")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            if st.form_submit_button("Save Customer") and name:
                conn = get_connection()
                execute_portable_write(
                    conn,
                    db_insert_ignore_sql(
                        "customers",
                        ("company_key", "name", "email", "phone", "currency"),
                    ),
                    (company_key, name, email, phone, "GHS"),
                )
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = _portable_read_dataframe(
            conn,
            "SELECT name, email, phone, currency, created_at FROM customers WHERE company_key = ? ORDER BY name",
            (company_key,),
        )
        conn.close()
        st.dataframe(format_currency_dataframe(df), use_container_width=True)
        _csv_button("Customers", df, f"customers_csv_{company_key}")

    with tabs[1]:
        with st.form(f"supplier_form_{company_key}"):
            name = st.text_input("Supplier Name")
            email = st.text_input("Email", key=f"supplier_email_{company_key}")
            phone = st.text_input("Phone", key=f"supplier_phone_{company_key}")
            if st.form_submit_button("Save Supplier") and name:
                conn = get_connection()
                execute_portable_write(
                    conn,
                    db_insert_ignore_sql(
                        "suppliers",
                        ("company_key", "name", "email", "phone", "currency"),
                    ),
                    (company_key, name, email, phone, "GHS"),
                )
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = _portable_read_dataframe(
            conn,
            "SELECT name, email, phone, currency, created_at FROM suppliers WHERE company_key = ? ORDER BY name",
            (company_key,),
        )
        conn.close()
        st.dataframe(format_currency_dataframe(df), use_container_width=True)
        _csv_button("Suppliers", df, f"suppliers_csv_{company_key}")

    with tabs[2]:
        conn = get_connection()
        customers = [
            str(row_get(row, "name", row_get(row, 0)) or "")
            for row in execute_portable_query(
                conn,
                "SELECT name FROM customers WHERE company_key = ? ORDER BY name",
                (company_key,),
            ).fetchall()
        ]
        conn.close()
        invoice_items = []
        invoice_items_total = 0.0
        with st.form(f"invoice_form_{company_key}"):
            customer_name = st.selectbox("Customer", [""] + customers)
            amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01)
            output_vat_rate = st.number_input("Output VAT Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0, key=f"invoice_vat_rate_{company_key}")
            output_nhil_rate = st.number_input("Output NHIL Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0, key=f"invoice_nhil_rate_{company_key}")
            output_getfund_rate = st.number_input("Output GETFund Levy Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0, key=f"invoice_getfund_rate_{company_key}")
            status = st.selectbox("Status", ["Draft", "Pending", "Paid"])
            posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=0, key=f"invoice_posting_state_{company_key}")
            invoice_date = st.date_input("Invoice Date", value=datetime.now().date(), key=f"invoice_date_{company_key}")
            description = st.text_input("Description", key=f"invoice_description_{company_key}")
            editor_conn = get_connection()
            try:
                invoice_items, invoice_items_total = render_invoice_line_editor(
                    company_key,
                    f"financials_invoice_lines_{company_key}",
                    editor_conn,
                )
            finally:
                if editor_conn:
                    editor_conn.close()
            if st.form_submit_button("Save Invoice") and customer_name and amount > 0:
                conn = get_connection()
                if invoice_items and abs(invoice_items_total - float(amount or 0.0)) >= 0.01:
                    conn.close()
                    st.warning("Invoice amount must match the total of the invoice items before posting.")
                    return
                customer_id = _party_id(conn, "customers", company_key, customer_name)
                output_vat = _tax_amount(amount, output_vat_rate)
                output_nhil = _tax_amount(amount, output_nhil_rate)
                output_getfund = _tax_amount(amount, output_getfund_rate)
                try:
                    cursor = conn.execute(
                        ensure_insert_sql_returning(
                            """
                            INSERT INTO invoices (company_key, customer_id, invoice_number, invoice_date, due_date, status, approval_status, amount, output_vat, currency, description, created_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                            """
                        ),
                        (company_key, customer_id, f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}", invoice_date.isoformat(), invoice_date.isoformat(), status, posting_state, amount, output_vat, description, role),
                    )
                except sqlite3.IntegrityError as e:
                    conn.close()
                    st.error(build_user_safe_error(e, role))
                    st.stop()

                invoice_id = get_inserted_id(cursor)
                if invoice_items:
                    save_invoice_lines(conn, invoice_id, invoice_items)
                if posting_state == "Posted":
                    stock_effects = apply_invoice_stock_effects(
                        conn,
                        company_key=company_key,
                        invoice_reference=f"INV-{invoice_id}",
                        invoice_items=invoice_items,
                        role=role,
                        branch_id=st.session_state.get("active_branch_id"),
                    )
                    cogs_total = round(float(stock_effects.get("cogs_total") or 0.0), 2)
                    journal_lines, _ = build_sales_tax_journal_lines(
                        conn,
                        company_key,
                        receipt_account_name="Cash" if status == "Paid" else "Accounts Receivable",
                        receipt_account_type="Asset",
                        amount=amount,
                        output_vat=output_vat,
                        nhil=output_nhil,
                        getfund=output_getfund,
                    )
                    if cogs_total > 0:
                        journal_lines.extend(
                            [
                                {"account_id": get_account_id(conn, "Cost of Goods Sold", "Expense"), "debit": cogs_total, "credit": 0},
                                {"account_id": get_account_id(conn, "Inventory", "Asset"), "debit": 0, "credit": cogs_total},
                            ]
                        )
                    post_journal_entry(
                        company_key=company_key,
                        date=invoice_date,
                        description="Sales invoice",
                        reference=f"INV-{invoice_id}",
                        lines=journal_lines,
                        created_by=role,
                        branch_id=st.session_state.get("active_branch_id"),
                        customer_id=customer_id,
                        source_module="Invoices",
                        source_table="invoices",
                        source_type="Invoice",
                        source_id=invoice_id,
                        approval_status="Posted",
                        conn=conn,
                    )
                elif posting_state != "Cancelled":
                    st.warning("Invoice saved without accounting impact. Change Posting State to Posted when it is approved for the ledger.")
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = _portable_read_dataframe(
            conn,
            "SELECT invoice_number, invoice_date, due_date, status, approval_status, amount, currency, description FROM invoices WHERE company_key = ? ORDER BY invoice_date DESC",
            (company_key,),
        )
        conn.close()
        st.dataframe(format_currency_dataframe(df), use_container_width=True)
        _csv_button("Invoices", df, f"invoices_csv_{company_key}")

    with tabs[3]:
        conn = get_connection()
        suppliers = [
            str(row_get(row, "name", row_get(row, 0)) or "")
            for row in execute_portable_query(
                conn,
                "SELECT name FROM suppliers WHERE company_key = ? ORDER BY name",
                (company_key,),
            ).fetchall()
        ]
        expense_account_options = get_purchase_expense_account_options(company_key, conn=conn)
        conn.close()
        with st.form(f"bill_form_{company_key}"):
            supplier_name = st.selectbox("Supplier", [""] + suppliers)
            purchase_classification = st.selectbox("Purchase Classification", PURCHASE_CLASSIFICATION_OPTIONS, key=f"bill_classification_{company_key}")
            amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01, key=f"bill_amount_{company_key}")
            input_vat_rate = st.number_input("Input VAT Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0, key=f"bill_vat_rate_{company_key}")
            status = st.selectbox("Status", ["Draft", "Pending", "Received"], key=f"bill_status_{company_key}")
            payment_method = st.selectbox("Payment Method", ["Cash", "Bank", "Mobile Money"], key=f"bill_method_{company_key}", disabled=status != "Received")
            posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=1, key=f"bill_posting_state_{company_key}")
            bill_date = st.date_input("Bill Date", value=datetime.now().date(), key=f"bill_date_{company_key}")
            expense_account_name = None
            asset_name = ""
            asset_category = ""
            if purchase_classification == "Expense Purchase":
                expense_account_name = st.selectbox("Expense Account", expense_account_options, key=f"bill_expense_account_{company_key}")
            elif purchase_classification == "Fixed Asset Purchase":
                asset_name = st.text_input("Asset Name", key=f"bill_asset_name_{company_key}")
                asset_category = st.selectbox("Asset Category", FIXED_ASSET_PURCHASE_CATEGORIES, key=f"bill_asset_category_{company_key}")
            description = st.text_input("Description", key=f"bill_description_{company_key}")
            if st.form_submit_button("Save Bill") and supplier_name and amount > 0:
                conn = get_connection()
                supplier_id = _party_id(conn, "suppliers", company_key, supplier_name)
                input_vat = round(amount * (input_vat_rate or 0.0) / 100.0, 2)
                try:
                    cursor = conn.execute(
                        ensure_insert_sql_returning(
                            """
                            INSERT INTO bills (
                                company_key, supplier_id, bill_number, bill_date, due_date, status, approval_status,
                                amount, input_vat, purchase_classification, payment_method, expense_account_name, asset_name,
                                asset_category, currency, description, created_by
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                            """
                        ),
                        (
                            company_key,
                            supplier_id,
                            f"BILL-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            bill_date.isoformat(),
                            bill_date.isoformat(),
                            status,
                            posting_state,
                            amount,
                            input_vat,
                            purchase_classification,
                            payment_method if status == "Received" else None,
                            expense_account_name if purchase_classification == "Expense Purchase" else None,
                            asset_name.strip() or None,
                            asset_category or None,
                            description,
                            role,
                        ),
                    )
                except sqlite3.IntegrityError as e:
                    conn.close()
                    st.error(build_user_safe_error(e, role))
                    st.stop()

                bill_id = get_inserted_id(cursor)
                if posting_state == "Posted":
                    journal_lines, _ = build_purchase_journal_lines(
                        conn,
                        company_key,
                        classification=purchase_classification,
                        amount=amount,
                        input_vat=input_vat,
                        status=status,
                        payment_method=payment_method,
                        expense_account_name=expense_account_name,
                    )
                    post_journal_entry(
                        company_key=company_key,
                        date=bill_date,
                        description="Purchase bill",
                        reference=f"BILL-{bill_id}",
                        lines=journal_lines,
                        created_by=role,
                        branch_id=st.session_state.get("active_branch_id"),
                        supplier_id=supplier_id,
                        source_module="Bills",
                        source_table="bills",
                        source_type="Bill",
                        source_id=bill_id,
                        approval_status="Posted",
                        user_role=role,
                        conn=conn,
                    )
                elif posting_state != "Cancelled":
                    st.warning("Bill saved without accounting impact. Change Posting State to Posted when it is approved for the ledger.")
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = _portable_read_dataframe(
            conn,
            "SELECT bill_number, bill_date, due_date, status, approval_status, amount, currency, description FROM bills WHERE company_key = ? ORDER BY bill_date DESC",
            (company_key,),
        )
        conn.close()
        st.dataframe(format_currency_dataframe(df), use_container_width=True)
        _csv_button("Bills", df, f"bills_csv_{company_key}")

    with tabs[4]:
        with st.form(f"payments_form_{company_key}"):
            payment_type = st.selectbox("Payment Type", ["Customer Receipt", "Supplier Payment"])
            amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01, key=f"payment_amount_{company_key}")
            payment_method = st.selectbox("Method", ["Cash", "Bank", "Mobile Money"])
            posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=3, key=f"payment_posting_state_{company_key}")
            payment_ref = st.text_input("Reference")
            payment_date = st.date_input("Payment Date", value=datetime.now().date())
            if st.form_submit_button("Save Payment") and amount > 0:
                conn = get_connection()
                payment_cursor = conn.execute(
                    ensure_insert_sql_returning(
                        "INSERT INTO payments (company_key, payment_date, payment_type, status, amount, currency, method, reference, approval_status, created_by) VALUES (?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)"
                    ),
                    (company_key, payment_date.isoformat(), payment_type, posting_state, amount, payment_method, payment_ref, posting_state, role),
                )
                payment_id = get_inserted_id(payment_cursor)
                if posting_state == "Posted":
                    if not require_permission(
                        role,
                        "post_accounting_document",
                        action_label="post accounting documents",
                        company_key=company_key,
                        conn=conn,
                        branch_id=st.session_state.get("active_branch_id"),
                    ):
                        conn.rollback()
                        conn.close()
                        return
                    payment_account = _payment_method_account_name(payment_method)
                    lines = (
                        [
                            {"account_id": get_account_id(conn, payment_account, "Asset"), "debit": amount, "credit": 0},
                            {"account_id": get_account_id(conn, "Accounts Receivable", "Asset"), "debit": 0, "credit": amount},
                        ]
                        if payment_type == "Customer Receipt"
                        else [
                            {"account_id": get_account_id(conn, "Accounts Payable", "Liability"), "debit": amount, "credit": 0},
                            {"account_id": get_account_id(conn, payment_account, "Asset"), "debit": 0, "credit": amount},
                        ]
                    )
                    post_journal_entry(
                        company_key=company_key,
                        date=payment_date,
                        description="Payment entry",
                        reference=payment_ref,
                        lines=lines,
                        created_by=role,
                        branch_id=st.session_state.get("active_branch_id"),
                        payment_id=payment_id,
                        source_module="Payments",
                        source_table="payments",
                        source_id=payment_id,
                        approval_status="Posted",
                        user_role=role,
                        conn=conn,
                    )
                    log_audit_action(
                        conn,
                        company_key,
                        role,
                        f"Payment Posted: {payment_type}",
                        "Payments",
                        details=f"type={payment_type}; amount={amount:.2f}; method={payment_method}; reference={payment_ref or ''}",
                        branch_id=st.session_state.get("active_branch_id"),
                        action_type="post",
                        document_ref=str(payment_id),
                    )
                    log_system_event(
                        "INFO",
                        "Payments",
                        "Posted payment type={payment_type} amount={amount:.2f} method={method} user={user} payment_id={payment_id}".format(
                            payment_type=payment_type,
                            amount=float(amount or 0.0),
                            method=payment_method,
                            user=role,
                            payment_id=payment_id,
                        ),
                    )
                else:
                    st.warning("Payment saved without accounting impact. Move Posting State to Posted when it is approved.")
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = _portable_read_dataframe(
            conn,
            "SELECT payment_date, payment_type, status, approval_status, amount, currency, method, reference, created_by FROM payments WHERE company_key = ? ORDER BY payment_date DESC",
            (company_key,),
        )
        conn.close()
        st.dataframe(format_currency_dataframe(df), use_container_width=True)
        _csv_button("Payments", df, f"payments_csv_{company_key}")


def show_customers_page(company_key, role):
    st.header("🧾 Customers")
    with st.form(f"customer_form_{company_key}"):
        name = st.text_input("Customer Name")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        if st.form_submit_button("Save Customer") and name:
            if not require_permission(role, "create_customer", action_label="create customers", company_key=company_key):
                return
            conn = get_connection()
            execute_portable_write(
                conn,
                db_insert_ignore_sql(
                    "customers",
                    ("company_key", "name", "email", "phone", "currency"),
                ),
                (company_key, name, email, phone, "GHS"),
            )
            conn.commit()
            conn.close()
            st.rerun()

    conn = get_connection()
    df = _portable_read_dataframe(
        conn,
        "SELECT name, email, phone, currency, created_at FROM customers WHERE company_key = ? ORDER BY name",
        (company_key,),
    )
    conn.close()
    st.dataframe(format_currency_dataframe(df), use_container_width=True)
    _csv_button("Customers", df, f"customers_csv_{company_key}")


def show_suppliers_page(company_key, role):
    st.header("🏷️ Suppliers")
    supplier_contact_form_reset_key = f"supplier_contact_form_reset_{company_key}"
    with st.form(f"supplier_form_{company_key}"):
        name = st.text_input(
            "Supplier Name",
            key=eka_modules._form_widget_key(f"supplier_contact_name_{company_key}", supplier_contact_form_reset_key),
        )
        email = st.text_input(
            "Email",
            key=eka_modules._form_widget_key(f"supplier_contact_email_{company_key}", supplier_contact_form_reset_key),
        )
        phone = st.text_input(
            "Phone",
            key=eka_modules._form_widget_key(f"supplier_contact_phone_{company_key}", supplier_contact_form_reset_key),
        )
        if st.form_submit_button("Save Supplier") and name:
            if not require_permission(role, "create_supplier", action_label="create suppliers", company_key=company_key):
                return
            conn = get_connection()
            execute_portable_write(
                conn,
                db_insert_ignore_sql(
                    "suppliers",
                    ("company_key", "name", "email", "phone", "currency"),
                ),
                (company_key, name.strip(), email, phone, "GHS"),
            )
            conn.commit()
            conn.close()
            eka_modules._increment_form_reset(supplier_contact_form_reset_key)
            st.success("Supplier saved.")
            st.rerun()

    conn = get_connection()
    df = _portable_read_dataframe(
        conn,
        "SELECT name, email, phone, currency, created_at FROM suppliers WHERE company_key = ? ORDER BY name",
        (company_key,),
    )
    conn.close()
    st.dataframe(format_currency_dataframe(df), use_container_width=True)
    _csv_button("Suppliers", df, f"suppliers_csv_{company_key}")


def show_create_invoice_page(company_key, role):
    eka_modules.render_ui_standard_styles()
    eka_modules.page_header("📄 Create Invoice")
    if not require_permission(role, "create_invoice", action_label="create invoices", company_key=company_key):
        return
    conn = get_connection()
    customers = [
        str(row_get(row, "name", row_get(row, 0)) or "")
        for row in execute_portable_query(
            conn,
            "SELECT name FROM customers WHERE company_key = ? ORDER BY name",
            (company_key,),
        ).fetchall()
    ]
    conn.close()
    invoice_items = []
    invoice_items_total = 0.0
    with eka_modules.card_container():
        with st.form(f"invoice_form_{company_key}"):
            customer_name = st.selectbox("Customer", [""] + customers)
            amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01)
            output_vat_rate = st.number_input("Output VAT Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0, key=f"invoice_vat_rate_{company_key}")
            output_nhil_rate = st.number_input("Output NHIL Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0, key=f"create_invoice_nhil_rate_{company_key}")
            output_getfund_rate = st.number_input("Output GETFund Levy Rate (%)", min_value=0.0, max_value=100.0, step=0.5, value=0.0, key=f"create_invoice_getfund_rate_{company_key}")
            status = st.selectbox("Status", ["Draft", "Pending", "Paid"])
            posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=0)
            invoice_date = st.date_input("Invoice Date", value=datetime.now().date(), key=f"invoice_date_{company_key}")
            description = st.text_input("Description", key=f"invoice_description_{company_key}")
            editor_conn = get_connection()
            try:
                invoice_items, invoice_items_total = render_invoice_line_editor(
                    company_key,
                    f"create_invoice_lines_{company_key}",
                    editor_conn,
                )
            finally:
                if editor_conn:
                    editor_conn.close()
            submitted = st.form_submit_button("Save Invoice")
        
        if submitted and customer_name and amount > 0:
            conn = get_connection()
            if not require_permission(role, "create_invoice", action_label="create invoices", company_key=company_key, conn=conn):
                conn.close()
                return
            if invoice_items and abs(invoice_items_total - float(amount or 0.0)) >= 0.01:
                conn.close()
                st.warning("Invoice amount must match the total of the invoice items before posting.")
                return
            row = execute_portable_query(
                conn,
                "SELECT id FROM customers WHERE company_key = ? AND name = ? LIMIT 1",
                (company_key, customer_name),
            ).fetchone()
            customer_id = int(row_get(row, "id", row_get(row, 0))) if row else None
            output_vat = _tax_amount(amount, output_vat_rate)
            output_nhil = _tax_amount(amount, output_nhil_rate)
            output_getfund = _tax_amount(amount, output_getfund_rate)
            try:
                cursor = conn.execute(
                    ensure_insert_sql_returning(
                        """
                        INSERT INTO invoices (company_key, customer_id, invoice_number, invoice_date, due_date, status, approval_status, amount, output_vat, currency, description, created_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                        """
                    ),
                    (
                        company_key,
                        customer_id,
                        f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        invoice_date.isoformat(),
                        invoice_date.isoformat(),
                        status,
                        posting_state,
                        amount,
                        output_vat,
                        description,
                        role,
                    ),
                )
            except sqlite3.IntegrityError as e:
                conn.close()
                st.error(build_user_safe_error(e, role))
                st.stop()

            invoice_id = get_inserted_id(cursor)
            if invoice_items:
                save_invoice_lines(conn, invoice_id, invoice_items)
            if posting_state == "Posted":
                if not require_permission(
                    role,
                    "post_accounting_document",
                    action_label="post accounting documents",
                    company_key=company_key,
                    conn=conn,
                ):
                    conn.rollback()
                    conn.close()
                    return
                stock_effects = apply_invoice_stock_effects(
                    conn,
                    company_key=company_key,
                    invoice_reference=f"INV-{invoice_id}",
                    invoice_items=invoice_items,
                    role=role,
                    branch_id=st.session_state.get("active_branch_id"),
                )
                cogs_total = round(float(stock_effects.get("cogs_total") or 0.0), 2)
                journal_lines, _ = build_sales_tax_journal_lines(
                    conn,
                    company_key,
                    receipt_account_name="Cash" if status == "Paid" else "Accounts Receivable",
                    receipt_account_type="Asset",
                    amount=amount,
                    output_vat=output_vat,
                    nhil=output_nhil,
                    getfund=output_getfund,
                )
                if cogs_total > 0:
                    journal_lines.extend(
                        [
                            {"account_id": get_account_id(conn, "Cost of Goods Sold", "Expense"), "debit": cogs_total, "credit": 0},
                            {"account_id": get_account_id(conn, "Inventory", "Asset"), "debit": 0, "credit": cogs_total},
                        ]
                    )
                post_journal_entry(
                    company_key=company_key,
                    date=invoice_date,
                    description="Sales invoice",
                    reference=f"INV-{invoice_id}",
                    lines=journal_lines,
                    created_by=role,
                    branch_id=st.session_state.get("active_branch_id"),
                    customer_id=customer_id,
                    source_module="Invoices",
                    source_table="invoices",
                    source_type="Invoice",
                    source_id=invoice_id,
                    approval_status="Posted",
                    conn=conn,
                )
            elif posting_state != "Cancelled":
                st.warning("Invoice saved without accounting impact. Change Posting State to Posted when it is approved for the ledger.")
            conn.commit()
            conn.close()
            st.rerun()

    conn = get_connection()
    df = _portable_read_dataframe(
        conn,
        "SELECT invoice_number, invoice_date, due_date, status, approval_status, amount, currency, description FROM invoices WHERE company_key = ? ORDER BY invoice_date DESC",
        (company_key,),
    )
    conn.close()
    st.dataframe(format_currency_dataframe(df), use_container_width=True)
    _csv_button("Invoices", df, f"invoices_csv_{company_key}")


def show_receive_payment_page(company_key, role):
    st.header("💳 Receive Payment")
    if not require_permission(
        role,
        "receive_customer_payment",
        action_label="receive customer payments",
        company_key=company_key,
    ):
        return
    conn = get_connection()
    customers = [
        str(row_get(row, "name", row_get(row, 0)) or "")
        for row in execute_portable_query(
            conn,
            "SELECT name FROM customers WHERE company_key = ? ORDER BY name",
            (company_key,),
        ).fetchall()
    ]
    conn.close()
    with st.form(f"receive_payment_form_{company_key}"):
        customer_name = st.selectbox("Customer", [""] + customers)
        amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01, key=f"receive_payment_amount_{company_key}")
        payment_method = st.selectbox("Method", ["Cash", "Bank", "Mobile Money"], key=f"receive_payment_method_{company_key}")
        posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=3, key=f"receive_payment_posting_state_{company_key}")
        payment_ref = st.text_input("Reference", key=f"receive_payment_ref_{company_key}")
        payment_date = st.date_input("Payment Date", value=datetime.now().date(), key=f"receive_payment_date_{company_key}")
        if st.form_submit_button("Save Receipt") and amount > 0 and customer_name:
            conn = get_connection()
            if not require_permission(
                role,
                "receive_customer_payment",
                action_label="receive customer payments",
                company_key=company_key,
                conn=conn,
            ):
                conn.close()
                return
            row = execute_portable_query(
                conn,
                "SELECT id FROM customers WHERE company_key = ? AND name = ? LIMIT 1",
                (company_key, customer_name),
            ).fetchone()
            customer_id = int(row_get(row, "id", row_get(row, 0))) if row else None
            payment_cursor = conn.execute(
                ensure_insert_sql_returning(
                    "INSERT INTO payments (company_key, payment_date, payment_type, status, amount, currency, method, reference, approval_status, created_by) VALUES (?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)"
                ),
                (company_key, payment_date.isoformat(), "Customer Receipt", posting_state, amount, payment_method, payment_ref, posting_state, role),
            )
            payment_id = get_inserted_id(payment_cursor)
            if posting_state == "Posted":
                if not require_permission(
                    role,
                    "post_accounting_document",
                    action_label="post accounting documents",
                    company_key=company_key,
                    conn=conn,
                ):
                    conn.rollback()
                    conn.close()
                    return
                lines = [
                    {"account_id": get_account_id(conn, _payment_method_account_name(payment_method), "Asset"), "debit": amount, "credit": 0},
                    {"account_id": get_account_id(conn, "Accounts Receivable", "Asset"), "debit": 0, "credit": amount},
                ]
                post_journal_entry(
                    company_key=company_key,
                    date=payment_date,
                    description=f"Customer receipt - {customer_name}",
                    reference=payment_ref,
                    lines=lines,
                    created_by=role,
                    branch_id=st.session_state.get("active_branch_id"),
                    payment_id=payment_id,
                    source_module="Payments",
                    source_table="payments",
                    source_type="Customer Receipt",
                    source_id=payment_id,
                    customer_id=customer_id,
                    approval_status="Posted",
                    user_role=role,
                    conn=conn,
                )
                log_audit_action(
                    conn,
                    company_key,
                    role,
                    "Customer Receipt Posted",
                    "Payments",
                    details=f"type=Customer Receipt; amount={amount:.2f}; method={payment_method}; user={role}; reference={payment_ref or ''}",
                    branch_id=st.session_state.get("active_branch_id"),
                    action_type="post",
                    document_ref=str(payment_id),
                )
                log_system_event(
                    "INFO",
                    "Payments",
                    "Posted customer receipt amount={amount:.2f} method={method} user={user} payment_id={payment_id}".format(
                        amount=float(amount or 0.0),
                        method=payment_method,
                        user=role,
                        payment_id=payment_id,
                    ),
                )
            else:
                st.warning("Receipt saved without accounting impact. Move Posting State to Posted when it is approved.")
            conn.commit()
            conn.close()
            st.rerun()

    conn = get_connection()
    df = _portable_read_dataframe(
        conn,
        "SELECT payment_date, payment_type, status, approval_status, amount, currency, method, reference, created_by FROM payments WHERE company_key = ? AND payment_type = 'Customer Receipt' ORDER BY payment_date DESC",
        (company_key,),
    )
    conn.close()
    st.dataframe(format_currency_dataframe(df), use_container_width=True)
    _csv_button("Customer Payments", df, f"customer_payments_csv_{company_key}")


def show_supplier_payment_page(company_key, role):
    st.header("💸 Supplier Payment")
    if not require_permission(
        role,
        "make_supplier_payment",
        action_label="make supplier payments",
        company_key=company_key,
    ):
        return
    conn = get_connection()
    suppliers = [
        str(row_get(row, "name", row_get(row, 0)) or "")
        for row in execute_portable_query(
            conn,
            "SELECT name FROM suppliers WHERE company_key = ? ORDER BY name",
            (company_key,),
        ).fetchall()
    ]
    conn.close()
    with st.form(f"supplier_payment_form_{company_key}"):
        supplier_name = st.selectbox("Supplier", [""] + suppliers)
        amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01, key=f"supplier_payment_amount_{company_key}")
        payment_method = st.selectbox("Method", ["Cash", "Bank", "Mobile Money"], key=f"supplier_payment_method_{company_key}")
        posting_state = st.selectbox("Posting State", DOCUMENT_WORKFLOW_STATUSES, index=3, key=f"supplier_payment_posting_state_{company_key}")
        payment_ref = st.text_input("Reference", key=f"supplier_payment_ref_{company_key}")
        payment_date = st.date_input("Payment Date", value=datetime.now().date(), key=f"supplier_payment_date_{company_key}")
        if st.form_submit_button("Save Payment") and amount > 0 and supplier_name:
            conn = get_connection()
            if not require_permission(
                role,
                "make_supplier_payment",
                action_label="make supplier payments",
                company_key=company_key,
                conn=conn,
            ):
                conn.close()
                return
            row = execute_portable_query(
                conn,
                "SELECT id FROM suppliers WHERE company_key = ? AND name = ? LIMIT 1",
                (company_key, supplier_name),
            ).fetchone()
            supplier_id = int(row_get(row, "id", row_get(row, 0))) if row else None
            payment_cursor = conn.execute(
                ensure_insert_sql_returning(
                    "INSERT INTO payments (company_key, payment_date, payment_type, status, amount, currency, method, reference, approval_status, created_by) VALUES (?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)"
                ),
                (company_key, payment_date.isoformat(), "Supplier Payment", posting_state, amount, payment_method, payment_ref, posting_state, role),
            )
            payment_id = get_inserted_id(payment_cursor)
            if posting_state == "Posted":
                if not require_permission(
                    role,
                    "post_accounting_document",
                    action_label="post accounting documents",
                    company_key=company_key,
                    conn=conn,
                ):
                    conn.rollback()
                    conn.close()
                    return
                lines = [
                    {"account_id": get_account_id(conn, "Accounts Payable", "Liability"), "debit": amount, "credit": 0},
                    {"account_id": get_account_id(conn, _payment_method_account_name(payment_method), "Asset"), "debit": 0, "credit": amount},
                ]
                post_journal_entry(
                    company_key=company_key,
                    date=payment_date,
                    description=f"Supplier payment - {supplier_name}",
                    reference=payment_ref,
                    lines=lines,
                    created_by=role,
                    branch_id=st.session_state.get("active_branch_id"),
                    payment_id=payment_id,
                    source_module="Payments",
                    source_table="payments",
                    source_type="Supplier Payment",
                    source_id=payment_id,
                    supplier_id=supplier_id,
                    approval_status="Posted",
                    user_role=role,
                    conn=conn,
                )
                log_audit_action(
                    conn,
                    company_key,
                    role,
                    "Supplier Payment Posted",
                    "Payments",
                    details=f"type=Supplier Payment; amount={amount:.2f}; method={payment_method}; user={role}; reference={payment_ref or ''}",
                    branch_id=st.session_state.get("active_branch_id"),
                    action_type="post",
                    document_ref=str(payment_id),
                )
                log_system_event(
                    "INFO",
                    "Payments",
                    "Posted supplier payment amount={amount:.2f} method={method} user={user} payment_id={payment_id}".format(
                        amount=float(amount or 0.0),
                        method=payment_method,
                        user=role,
                        payment_id=payment_id,
                    ),
                )
            else:
                st.warning("Supplier payment saved without accounting impact. Move Posting State to Posted when it is approved.")
            conn.commit()
            conn.close()
            st.rerun()

    conn = get_connection()
    df = _portable_read_dataframe(
        conn,
        "SELECT payment_date, payment_type, status, approval_status, amount, currency, method, reference, created_by FROM payments WHERE company_key = ? AND payment_type = 'Supplier Payment' ORDER BY payment_date DESC",
        (company_key,),
    )
    conn.close()
    st.dataframe(format_currency_dataframe(df), use_container_width=True)
    _csv_button("Supplier Payments", df, f"supplier_payments_csv_{company_key}")


def _show_legacy_ledger_viewer(company_key, role):
    st.header("📚 Ledger Viewer")
    branch_id = st.session_state.get("active_branch_id")
    start_date, end_date, account_name = _filter_controls(f"ledger_{company_key}")
    tabs = st.tabs(["General Journal", "Sales Journal", "Purchases Journal", "Cash Book", "General Ledger"])
    report_defs = [
        ("General Journal", get_general_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)),
        ("Sales Journal", get_sales_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)),
        ("Purchases Journal", get_purchases_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)),
        ("Cash Book", get_cash_book(company_key, start_date, end_date, account_name, branch_id=branch_id)),
        ("General Ledger", get_general_ledger(company_key, start_date, end_date, account_name, branch_id=branch_id)),
    ]
    for tab, (label, df) in zip(tabs, report_defs):
        with tab:
            st.dataframe(format_currency_dataframe(df), use_container_width=True)
            _csv_button(label, df, f"{label}_{company_key}")


def show_ledger_viewer(company_key, role):
    st.header("📚 Ledger Viewer")
    if not require_permission(role, "view_reports", action_label="view reports", company_key=company_key):
        return
    branch_id = st.session_state.get("active_branch_id")
    start_date, end_date, account_name = _filter_controls(f"ledger_override_{company_key}")
    tabs = st.tabs(["General Journal", "Sales Journal", "Purchases Journal", "Cash Book", "General Ledger"])
    report_defs = [
        ("General Journal", get_general_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)),
        ("Sales Journal", get_sales_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)),
        ("Purchases Journal", get_purchases_journal(company_key, start_date, end_date, account_name, branch_id=branch_id)),
        ("Cash Book", get_cash_book(company_key, start_date, end_date, account_name, branch_id=branch_id)),
        ("General Ledger", get_general_ledger(company_key, start_date, end_date, account_name, branch_id=branch_id)),
    ]
    for tab, (label, df) in zip(tabs, report_defs):
        with tab:
            display_df = _convert_money_frame(df)
            st.dataframe(format_currency_dataframe(display_df), use_container_width=True)
            _csv_button(label, display_df, f"{label}_override_{company_key}")


def show_record_transaction(company_key, role):
    if not require_permission(role, "post_accounting_document", action_label="post accounting documents", company_key=company_key):
        return
    show_journal_entries(company_key, role)


def _show_legacy_financial_reports_v1(company_key, role=None):
    st.header("📊 Financial Reports")
    start_date, end_date, account_name = _filter_controls(f"financial_override_{company_key}")
    trial_balance_df = get_trial_balance(company_key, start_date, end_date, account_name)
    income_statement_df = get_income_statement(company_key, start_date, end_date, account_name)
    balance_sheet_df = get_balance_sheet(company_key, start_date, end_date, account_name)
    cash_flow_df = get_cash_flow_statement(company_key, start_date, end_date, account_name)
    equity_df = get_changes_in_equity(company_key, start_date, end_date, account_name)

    total_debits = float(trial_balance_df["Debit (GHS)"].sum()) if not trial_balance_df.empty else 0.0
    total_credits = float(trial_balance_df["Credit (GHS)"].sum()) if not trial_balance_df.empty else 0.0
    total_assets = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Asset", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    total_liabilities = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Liability", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    total_equity = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Equity", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    net_profit = float(income_statement_df.loc[income_statement_df["Account"] == "Net Profit", "Amount (GHS)"].sum()) if not income_statement_df.empty else 0.0
    balanced = abs(total_debits - total_credits) < 0.01

    col1, col2, col3 = st.columns(3)
    col1.metric("Trial Balance", "Balanced" if balanced else "Out of Balance")
    col2.metric("Net Profit", format_currency(net_profit))
    col3.metric("Balance Sheet", "Balanced" if abs(total_assets - (total_liabilities + total_equity)) < 0.01 else "Needs Review")
    st.caption(f"Debit/Credit Validation: {'Balanced' if balanced else 'Needs review'}")

    tabs = st.tabs(["Trial Balance", "Income Statement", "Balance Sheet", "Cash Flow Statement", "Changes in Equity"])
    report_defs = [
        ("Trial Balance", trial_balance_df),
        ("Income Statement", income_statement_df),
        ("Balance Sheet", balance_sheet_df),
        ("Cash Flow Statement", cash_flow_df),
        ("Statement of Changes in Equity", equity_df),
    ]
    for tab, (label, df) in zip(tabs, report_defs):
        with tab:
            display_df = _convert_money_frame(df)
            st.dataframe(format_currency_dataframe(display_df), use_container_width=True)
            _csv_button(label, display_df, f"{label}_override_{company_key}")


def _show_legacy_financial_reports_v2(company_key, role=None):
    st.header("📊 Financial Reports")
    start_date, end_date, account_name = _filter_controls(f"financial_{company_key}")
    trial_balance_df = get_trial_balance(company_key, start_date, end_date, account_name)
    income_statement_df = get_income_statement(company_key, start_date, end_date, account_name)
    balance_sheet_df = get_balance_sheet(company_key, start_date, end_date, account_name)
    cash_flow_df = get_cash_flow_statement(company_key, start_date, end_date, account_name)
    equity_df = get_changes_in_equity(company_key, start_date, end_date, account_name)

    total_debits = float(trial_balance_df["Debit (GHS)"].sum()) if not trial_balance_df.empty else 0.0
    total_credits = float(trial_balance_df["Credit (GHS)"].sum()) if not trial_balance_df.empty else 0.0
    total_assets = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Asset", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    total_liabilities = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Liability", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    total_equity = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Equity", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    net_profit = float(income_statement_df.loc[income_statement_df["Account"] == "Net Profit", "Amount (GHS)"].sum()) if not income_statement_df.empty else 0.0

    col1, col2, col3 = st.columns(3)
    col1.metric("Trial Balance", "Balanced" if abs(total_debits - total_credits) < 0.01 else "Out of Balance")
    col2.metric("Net Profit", f"{get_display_currency()} {net_profit:,.2f}")
    col3.metric("Balance Sheet", "Balanced" if abs(total_assets - (total_liabilities + total_equity)) < 0.01 else "Needs Review")

    tabs = st.tabs(["Trial Balance", "Income Statement", "Balance Sheet", "Cash Flow Statement", "Changes in Equity"])
    report_defs = [
        ("Trial Balance", trial_balance_df),
        ("Income Statement", income_statement_df),
        ("Balance Sheet", balance_sheet_df),
        ("Cash Flow Statement", cash_flow_df),
        ("Statement of Changes in Equity", equity_df),
    ]
    for tab, (label, df) in zip(tabs, report_defs):
        with tab:
            st.dataframe(format_currency_dataframe(df), use_container_width=True)
            _csv_button(label, df, f"{label}_{company_key}")


def _show_legacy_financial_reports_v3(company_key, role=None):
    st.header("📊 Financial Reports")
    start_date, end_date, account_name = _filter_controls(f"financial_final_{company_key}")
    trial_balance_df = get_trial_balance(company_key, start_date, end_date, account_name)
    income_statement_df = get_income_statement(company_key, start_date, end_date, account_name)
    balance_sheet_df = get_balance_sheet(company_key, start_date, end_date, account_name)
    cash_flow_df = get_cash_flow_statement(company_key, start_date, end_date, account_name)
    equity_df = get_changes_in_equity(company_key, start_date, end_date, account_name)
    depreciation_df = get_depreciation_schedule(company_key)

    total_debits = float(trial_balance_df["Debit (GHS)"].sum()) if not trial_balance_df.empty else 0.0
    total_credits = float(trial_balance_df["Credit (GHS)"].sum()) if not trial_balance_df.empty else 0.0
    total_assets = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Asset", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    total_liabilities = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Liability", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    total_equity = float(balance_sheet_df.loc[balance_sheet_df["Category"] == "Equity", "Amount (GHS)"].sum()) if not balance_sheet_df.empty else 0.0
    net_profit = float(income_statement_df.loc[income_statement_df["Account"] == "Net Profit", "Amount (GHS)"].sum()) if not income_statement_df.empty else 0.0
    balanced = abs(total_debits - total_credits) < 0.01

    col1, col2, col3 = st.columns(3)
    col1.metric("Trial Balance", "Balanced" if balanced else "Out of Balance")
    col2.metric("Net Profit", format_currency(net_profit))
    col3.metric("Balance Sheet", "Balanced" if abs(total_assets - (total_liabilities + total_equity)) < 0.01 else "Needs Review")
    st.caption(f"Debit/Credit Validation: {'Balanced' if balanced else 'Needs review'}")

    tabs = st.tabs(
        [
            "Trial Balance",
            "Income Statement",
            "Balance Sheet",
            "Cash Flow Statement",
            "Changes in Equity",
            "Depreciation Schedule",
        ]
    )
    report_defs = [
        ("Trial Balance", trial_balance_df),
        ("Income Statement", income_statement_df),
        ("Balance Sheet", balance_sheet_df),
        ("Cash Flow Statement", cash_flow_df),
        ("Statement of Changes in Equity", equity_df),
        ("Depreciation Schedule", depreciation_df),
    ]
    for tab, (label, df) in zip(tabs, report_defs):
        with tab:
            display_df = _format_account_headers(_convert_money_frame(df))
            st.dataframe(format_currency_dataframe(display_df), use_container_width=True)
            _csv_button(label, display_df, f"{label}_final_{company_key}")


def _show_legacy_reports_wrapper(company_key, role=None):
    """Financial reports sidebar entry point."""
    show_financial_reports(company_key, role)


def _safe_rate():
    try:
        rate = float(st.session_state.get("exchange_rate", 1.0) or 1.0)
        return rate if rate > 0 else 1.0
    except Exception:
        return 1.0


def _report_convert(value):
    try:
        return float(value or 0.0) / _safe_rate()
    except Exception:
        return 0.0


def _safe_number(series, default=0.0):
    try:
        if series is None:
            return float(default)
        if hasattr(series, "sum"):
            return float(series.sum())
        return float(series)
    except Exception:
        return float(default)


def _safe_dataframe(dataframe, columns):
    if isinstance(dataframe, pd.DataFrame):
        return dataframe.copy()
    return pd.DataFrame(columns=columns)


def _account_bucket(account_code, account_name, account_type):
    code = str(account_code or "").strip()
    name = str(account_name or "").strip().lower()
    normalized_type = str(account_type or "").strip().title()
    if normalized_type == "Asset":
        if code.startswith("15") or "fixed asset" in name or "property" in name or "equipment" in name:
            return "Non-Current Assets"
        return "Current Assets"
    if normalized_type == "Liability":
        if "loan" in name and not code.startswith("20"):
            return "Non-Current Liabilities"
        return "Current Liabilities"
    if normalized_type == "Equity":
        return "Equity"
    if normalized_type == "Income":
        return "Revenue"
    if normalized_type == "Expense":
        if name == "sales returns and refunds":
            return "Sales Deductions"
        if name == "cost of goods sold":
            return "Cost of Sales"
        if "depreciation" in name:
            return "Operating Expenses"
        return "Operating Expenses"
    return normalized_type or "Unclassified"


def _ifrs_account_display(dataframe):
    df = _safe_dataframe(dataframe, [])
    if df.empty:
        return df
    if "Account" in df.columns and "Account Code" in df.columns:
        df["Account"] = df.apply(
            lambda row: _account_label(row.get("Account Code"), row.get("Account")),
            axis=1,
        )
    return df


def _display_table_with_rate(df_original):
    df_display = _safe_dataframe(df_original, [])
    if df_display.empty:
        st.table(df_display)
        return df_display
    active_rate = get_exchange_rate()
    safe_rate = active_rate if active_rate and active_rate > 0 else 1.0
    if "Amount" in df_display.columns:
        df_display["Amount"] = pd.to_numeric(df_display["Amount"], errors="coerce").fillna(0.0).map(
            lambda x: f"{st.session_state.currency_symbol}{x / safe_rate:,.2f}"
        )
    if "Amount (GHS)" in df_display.columns:
        df_display["Amount (GHS)"] = pd.to_numeric(df_display["Amount (GHS)"], errors="coerce").fillna(0.0).map(
            lambda x: f"{st.session_state.currency_symbol}{x / safe_rate:,.2f}"
        )
    df_display = format_currency_dataframe(df_display)
    st.table(df_display)
    return df_display


def get_ledger_balances(company_key, start_date=None, end_date=None, account_name=None):
    conn = get_connection()
    try:
        query = """
            SELECT
                COALESCE(c.code, c.account_code, '') AS account_code,
                COALESCE(c.name, c.account_name, '') AS account_name,
                COALESCE(c.type, c.category, c.account_type, '') AS account_type,
                COALESCE(SUM(jl.debit), 0) AS total_debit,
                COALESCE(SUM(jl.credit), 0) AS total_credit
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.entry_id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
              AND COALESCE(je.is_voided, 0) = 0
              AND COALESCE(je.approval_status, 'Posted') = 'Posted'
        """
        params = [company_key]
        if start_date:
            query += f" AND {sql_date_on_or_after('je.date')}"
            params.append(_resolve_date(start_date))
        if end_date:
            query += f" AND {sql_date_on_or_before('je.date')}"
            params.append(_resolve_date(end_date))
        if account_name:
            query += " AND lower(COALESCE(c.name, c.account_name, '')) LIKE ?"
            params.append(f"%{str(account_name).lower()}%")
        query += """
            GROUP BY COALESCE(c.code, c.account_code, ''), COALESCE(c.name, c.account_name, ''), COALESCE(c.type, c.category, c.account_type, '')
            ORDER BY COALESCE(c.code, c.account_code, ''), COALESCE(c.name, c.account_name, '')
        """
        rows = execute_portable_query(conn, query, tuple(params)).fetchall()
        if not rows:
            return {}
        balances = {}
        for row in rows:
            debit = float(row_get(row, "total_debit", 0) or 0.0)
            credit = float(row_get(row, "total_credit", 0) or 0.0)
            account_type = str(row_get(row, "account_type", "") or "")
            balance = debit - credit if _normal_balance(account_type) == "debit" else credit - debit
            balances[str(row_get(row, "account_name", "") or "")] = {
                "account_code": str(row_get(row, "account_code", "") or ""),
                "account_type": account_type,
                "debit": debit,
                "credit": credit,
                "balance": balance,
            }
        return balances
    except Exception:
        return {}
    finally:
        conn.close()


def _financial_report_runtime_diagnostics(company_key, start_date=None, end_date=None, branch_id=None):
    diagnostics = {
        "company_key": company_key,
        "backend": get_active_db_backend(),
        "postgres_runtime": is_postgres_backend(),
        "start_date": _resolve_date(start_date) if start_date else None,
        "end_date": _resolve_date(end_date) if end_date else None,
        "branch_id": branch_id or "(all branches)",
    }
    conn = get_connection()
    try:
        table_specs = {
            "companies": ("SELECT COUNT(*) AS row_count FROM companies", []),
            "journal_entries_all": (
                """
                SELECT COUNT(*) AS row_count
                FROM journal_entries
                WHERE company_key = ?
                  AND COALESCE(is_voided, 0) = 0
                  AND COALESCE(approval_status, 'Posted') = 'Posted'
                """,
                [company_key],
            ),
            "journal_lines_all": (
                """
                SELECT COUNT(*) AS row_count
                FROM journal_lines jl
                JOIN journal_entries je ON je.id = jl.entry_id
                WHERE je.company_key = ?
                  AND COALESCE(je.is_voided, 0) = 0
                  AND COALESCE(je.approval_status, 'Posted') = 'Posted'
                """,
                [company_key],
            ),
            "pos_sales": (
                "SELECT COUNT(*) AS row_count FROM pos_sales WHERE company_key = ?",
                [company_key],
            ),
            "invoices": (
                "SELECT COUNT(*) AS row_count FROM invoices WHERE company_key = ?",
                [company_key],
            ),
            "bills": (
                "SELECT COUNT(*) AS row_count FROM bills WHERE company_key = ?",
                [company_key],
            ),
            "payments": (
                "SELECT COUNT(*) AS row_count FROM payments WHERE company_key = ?",
                [company_key],
            ),
            "inventory": (
                "SELECT COUNT(*) AS row_count FROM inventory WHERE company_key = ?",
                [company_key],
            ),
        }
        for table_name, (query, params) in table_specs.items():
            physical_table = table_name.replace("_all", "")
            if not db_table_exists(conn, physical_table):
                diagnostics[f"{table_name}_rows"] = 0
                continue
            diagnostics[f"{table_name}_rows"] = int(fetch_scalar(conn, query, tuple(params), default=0) or 0)

        for table_name in ("journal_entries", "journal_lines", "chart_of_accounts", "customers", "suppliers"):
            if not db_table_exists(conn, table_name):
                diagnostics[f"{table_name}_rows"] = 0
                continue
            if table_name == "journal_entries":
                query = """
                    SELECT COUNT(*) AS row_count
                    FROM journal_entries
                    WHERE company_key = ?
                      AND COALESCE(is_voided, 0) = 0
                      AND COALESCE(approval_status, 'Posted') = 'Posted'
                """
                params = [company_key]
                if branch_id:
                    query += " AND branch_id = ?"
                    params.append(branch_id)
                if start_date:
                    query += f" AND {sql_date_on_or_after('date')}"
                    params.append(_resolve_date(start_date))
                if end_date:
                    query += f" AND {sql_date_on_or_before('date')}"
                    params.append(_resolve_date(end_date))
            elif table_name == "journal_lines":
                query = """
                    SELECT COUNT(*) AS row_count
                    FROM journal_lines jl
                    JOIN journal_entries je ON je.id = jl.entry_id
                    WHERE je.company_key = ?
                      AND COALESCE(je.is_voided, 0) = 0
                      AND COALESCE(je.approval_status, 'Posted') = 'Posted'
                """
                params = [company_key]
                if branch_id:
                    query += " AND je.branch_id = ?"
                    params.append(branch_id)
                if start_date:
                    query += f" AND {sql_date_on_or_after('je.date')}"
                    params.append(_resolve_date(start_date))
                if end_date:
                    query += f" AND {sql_date_on_or_before('je.date')}"
                    params.append(_resolve_date(end_date))
            elif table_name == "chart_of_accounts":
                query = "SELECT COUNT(*) AS row_count FROM chart_of_accounts"
                params = []
            else:
                query = f"SELECT COUNT(*) AS row_count FROM {table_name} WHERE company_key = ?"
                params = [company_key]
            diagnostics[f"{table_name}_rows"] = int(
                fetch_scalar(conn, query, tuple(params), default=0) or 0
            )
    finally:
        conn.close()
    return diagnostics


def get_trial_balance(company_key, start_date=None, end_date=None, account_name=None):
    try:
        # Cumulative trial balance as of end_date; period movement belongs on income statement.
        balances = get_ledger_balances(company_key, start_date=None, end_date=end_date, account_name=account_name)
        if not balances:
            return pd.DataFrame(columns=["Account Code", "Account", "Type", "Debit (GHS)", "Credit (GHS)", "Balance (GHS)", "Balanced"])
        rows = []
        total_debits = 0.0
        total_credits = 0.0
        for account_name_key, payload in balances.items():
            debit = float(payload.get("debit", 0.0))
            credit = float(payload.get("credit", 0.0))
            total_debits += debit
            total_credits += credit
            rows.append(
                {
                    "Account Code": payload.get("account_code", ""),
                    "Account": account_name_key,
                    "Type": payload.get("account_type", ""),
                    "Debit (GHS)": debit,
                    "Credit (GHS)": credit,
                    "Balance (GHS)": float(payload.get("balance", 0.0)),
                }
            )
        balanced = abs(total_debits - total_credits) < 0.01
        df = pd.DataFrame(rows)
        df["Balanced"] = "Yes" if balanced else "No"
        return df.sort_values(["Account Code", "Account"], na_position="last").reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["Account Code", "Account", "Type", "Debit (GHS)", "Credit (GHS)", "Balance (GHS)", "Balanced"])


def get_income_statement(company_key, start_date=None, end_date=None, account_name=None):
    try:
        balances = get_ledger_balances(company_key, start_date=start_date, end_date=end_date, account_name=account_name)
        if not balances:
            return pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
        rows = []
        gross_revenue = 0.0
        sales_returns = 0.0
        cost_of_sales = 0.0
        operating_expenses = 0.0
        for account_name_key, payload in balances.items():
            account_type = str(payload.get("account_type", "")).title()
            account = str(account_name_key or "").strip()
            normalized_account = account.lower()
            if account_type == "Income":
                amount = float(payload.get("credit", 0.0) - payload.get("debit", 0.0))
                gross_revenue += amount
                rows.append(
                    {
                        "Category": "Revenue",
                        "Account Code": payload.get("account_code", ""),
                        "Account": account,
                        "Amount (GHS)": amount,
                    }
                )
            elif account_type == "Expense":
                amount = float(payload.get("debit", 0.0) - payload.get("credit", 0.0))
                category = _account_bucket(payload.get("account_code", ""), account, account_type)
                if normalized_account == "sales returns and refunds":
                    sales_returns += amount
                    amount = -amount
                    account = "Less: Sales Returns and Refunds"
                elif normalized_account == "cost of goods sold":
                    cost_of_sales += amount
                else:
                    operating_expenses += amount
                rows.append(
                    {
                        "Category": category,
                        "Account Code": payload.get("account_code", ""),
                        "Account": account,
                        "Amount (GHS)": amount,
                    }
                )
        net_sales = gross_revenue - sales_returns
        gross_profit = net_sales - cost_of_sales
        rows.append(
            {
                "Category": "Revenue",
                "Account Code": "",
                "Account": "Net Sales",
                "Amount (GHS)": net_sales,
            }
        )
        rows.append(
            {
                "Category": "Profit for the Period",
                "Account Code": "",
                "Account": "Gross Profit",
                "Amount (GHS)": gross_profit,
            }
        )
        rows.append(
            {
                "Category": "Profit for the Period",
                "Account Code": "",
                "Account": "Net Profit",
                "Amount (GHS)": gross_profit - operating_expenses,
            }
        )
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])


def get_balance_sheet(company_key, start_date=None, end_date=None, account_name=None):
    try:
        tb = get_trial_balance(company_key, start_date=None, end_date=end_date, account_name=account_name)
        if tb.empty:
            return pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
        rows = []
        for _, row in tb.iterrows():
            account_type = str(row.get("Type", "")).title()
            if account_type not in ("Asset", "Liability", "Equity"):
                continue
            amount = (
                float(row.get("Debit (GHS)", 0.0) - row.get("Credit (GHS)", 0.0))
                if account_type == "Asset"
                else float(row.get("Credit (GHS)", 0.0) - row.get("Debit (GHS)", 0.0))
            )
            rows.append(
                {
                    "Category": _account_bucket(row.get("Account Code", ""), row.get("Account", ""), account_type),
                    "Account Code": row.get("Account Code", ""),
                    "Account": row.get("Account", ""),
                    "Amount (GHS)": amount,
                }
            )
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])


def get_cash_flow_statement(company_key, start_date=None, end_date=None, account_name=None):
    try:
        income_df = get_income_statement(company_key, start_date, end_date, account_name)
        bs_df = get_balance_sheet(company_key, start_date, end_date, account_name)
        net_profit = _safe_number(income_df.loc[income_df["Account"] == "Net Profit", "Amount (GHS)"]) if not income_df.empty else 0.0
        depreciation = _safe_number(income_df.loc[income_df["Account"].astype(str).str.contains("Depreciation", case=False, na=False), "Amount (GHS)"]) if not income_df.empty else 0.0
        receivables = _safe_number(bs_df.loc[bs_df["Account"].astype(str).str.contains("Receivable", case=False, na=False), "Amount (GHS)"]) if not bs_df.empty else 0.0
        inventory = _safe_number(bs_df.loc[bs_df["Account"].astype(str).str.contains("Inventory", case=False, na=False), "Amount (GHS)"]) if not bs_df.empty else 0.0
        payables = _safe_number(bs_df.loc[bs_df["Account"].astype(str).str.contains("Payable", case=False, na=False), "Amount (GHS)"]) if not bs_df.empty else 0.0
        fixed_assets = _safe_number(bs_df.loc[bs_df["Category"] == "Non-Current Assets", "Amount (GHS)"]) if not bs_df.empty else 0.0
        capital = _safe_number(bs_df.loc[bs_df["Account"].astype(str).str.contains("Capital|Equity", case=False, na=False), "Amount (GHS)"]) if not bs_df.empty else 0.0
        operating = net_profit + depreciation - receivables - inventory + payables
        investing = -fixed_assets
        financing = capital
        return pd.DataFrame(
            [
                {"Section": "Operating Activities", "Line Item": "Profit for the Period", "Amount (GHS)": net_profit},
                {"Section": "Operating Activities", "Line Item": "Depreciation and Non-Cash Adjustments", "Amount (GHS)": depreciation},
                {"Section": "Operating Activities", "Line Item": "Working Capital Changes", "Amount (GHS)": -receivables - inventory + payables},
                {"Section": "Operating Activities", "Line Item": "Net Cash from Operating Activities", "Amount (GHS)": operating},
                {"Section": "Investing Activities", "Line Item": "Acquisition of Non-Current Assets", "Amount (GHS)": investing},
                {"Section": "Financing Activities", "Line Item": "Capital Contributions and Equity Movements", "Amount (GHS)": financing},
                {"Section": "Net Movement", "Line Item": "Net Increase or Decrease in Cash", "Amount (GHS)": operating + investing + financing},
            ]
        )
    except Exception:
        return pd.DataFrame(columns=["Section", "Line Item", "Amount (GHS)"])


def get_changes_in_equity(company_key, start_date=None, end_date=None, account_name=None):
    try:
        bs_df = get_balance_sheet(company_key, start_date, end_date, account_name)
        income_df = get_income_statement(company_key, start_date, end_date, account_name)
        opening_equity = _safe_number(bs_df.loc[bs_df["Account"].astype(str).str.contains("Opening Balance Equity", case=False, na=False), "Amount (GHS)"]) if not bs_df.empty else 0.0
        owner_capital = _safe_number(bs_df.loc[bs_df["Account"].astype(str).str.contains("Owner Capital|Capital", case=False, na=False), "Amount (GHS)"]) if not bs_df.empty else 0.0
        retained_earnings = _safe_number(bs_df.loc[bs_df["Account"].astype(str).str.contains("Retained Earnings", case=False, na=False), "Amount (GHS)"]) if not bs_df.empty else 0.0
        net_profit = _safe_number(income_df.loc[income_df["Account"] == "Net Profit", "Amount (GHS)"]) if not income_df.empty else 0.0
        return pd.DataFrame(
            [
                {"Account Code": "", "Line Item": "Opening Equity", "Amount (GHS)": opening_equity},
                {"Account Code": "", "Line Item": "Capital Contributions", "Amount (GHS)": owner_capital},
                {"Account Code": "", "Line Item": "Retained Earnings", "Amount (GHS)": retained_earnings},
                {"Account Code": "", "Line Item": "Profit for the Period", "Amount (GHS)": net_profit},
                {"Account Code": "", "Line Item": "Closing Equity", "Amount (GHS)": opening_equity + owner_capital + retained_earnings + net_profit},
            ]
        )
    except Exception:
        return pd.DataFrame(columns=["Account Code", "Line Item", "Amount (GHS)"])


def _convert_money_frame(dataframe):
    if dataframe.empty:
        return dataframe
    df = dataframe.copy()
    money_columns = [
        column_name
        for column_name in df.columns
        if any(token in str(column_name) for token in ("(GHS)", "Amount", "Debit", "Credit", "Balance", "Movement"))
    ]
    for column_name in money_columns:
        df[column_name] = pd.to_numeric(df[column_name], errors="coerce").fillna(0.0).map(_report_convert)
    renamed_columns = {}
    for column_name in df.columns:
        if "(GHS)" in str(column_name):
            renamed_columns[column_name] = str(column_name).replace("(GHS)", _money_label())
    return df.rename(columns=renamed_columns)


def _financial_report_cache_date(value):
    if value is None:
        return "none"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_trial_balance_report(company_key, start_key, end_key, account_key):
    start_date = None if start_key in (None, "none") else datetime.fromisoformat(start_key).date()
    end_date = None if end_key in (None, "none") else datetime.fromisoformat(end_key).date()
    account_name = None if account_key in (None, "none", "") else account_key
    return get_trial_balance(company_key, start_date=start_date, end_date=end_date, account_name=account_name)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_income_statement_report(company_key, start_key, end_key, account_key):
    start_date = None if start_key in (None, "none") else datetime.fromisoformat(start_key).date()
    end_date = None if end_key in (None, "none") else datetime.fromisoformat(end_key).date()
    account_name = None if account_key in (None, "none", "") else account_key
    return get_income_statement(company_key, start_date=start_date, end_date=end_date, account_name=account_name)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_balance_sheet_report(company_key, start_key, end_key, account_key):
    start_date = None if start_key in (None, "none") else datetime.fromisoformat(start_key).date()
    end_date = None if end_key in (None, "none") else datetime.fromisoformat(end_key).date()
    account_name = None if account_key in (None, "none", "") else account_key
    return get_balance_sheet(company_key, start_date=start_date, end_date=end_date, account_name=account_name)


def show_financial_reports(company_key, role=None):
    reports_started = time.perf_counter()
    eka_modules = importlib.import_module("modules")
    eka_modules.render_ui_standard_styles()
    eka_modules.page_header("📊 Financial Reports", "View financial statements, trial balance, and cash flow analysis")
    effective_role = role or st.session_state.get("user", {}).get("role", "System")
    if not require_permission(effective_role, "view_reports", action_label="view reports", company_key=company_key):
        return
    with st.expander("Year-End Closing", expanded=False):
        closing_date = st.date_input("Closing Date", value=datetime.now().date(), key=f"year_end_close_{company_key}")
        if st.button("Post Year-End Closing Entry", key=f"year_end_close_btn_{company_key}"):
            try:
                if not require_permission(
                    effective_role,
                    "close_period",
                    action_label="post year-end closing entries",
                    company_key=company_key,
                ):
                    return
                entry_id = close_fiscal_year(
                    company_key,
                    closing_date,
                    effective_role,
                    branch_id=st.session_state.get("active_branch_id"),
                )
                if entry_id:
                    st.success(f"Year-end closing entry posted as journal #{entry_id}.")
                else:
                    st.info("No net profit or loss balance was available to close.")
            except Exception as exc:
                st.error(build_user_safe_error(exc, effective_role))
    
    # Consolidator for Master Admins
    if effective_role == "Master Admin":
        if st.button("🔄 Generate Consolidated Group Reports", key=f"consolidator_{company_key}"):
            st.session_state.consolidated_view = True
            st.rerun()
        if st.session_state.get("consolidated_view"):
            if st.button("🔙 Back to Branch Reports", key=f"back_to_branch_{company_key}"):
                st.session_state.consolidated_view = False
                st.rerun()
    
    consolidated = st.session_state.get("consolidated_view", False) and effective_role == "Master Admin"
    
    try:
        start_date, end_date, account_name = _filter_controls(f"financial_ifrs_safe_{company_key}")
    except Exception:
        start_date, end_date, account_name = None, None, None

    if consolidated:
        try:
            trial_balance_df = get_trial_balance(company_key, start_date, end_date, account_name)  # Consolidated
        except Exception:
            trial_balance_df = pd.DataFrame(columns=["Account Code", "Account", "Type", "Debit (GHS)", "Credit (GHS)", "Balance (GHS)", "Balanced"])
        try:
            income_statement_df = get_consolidated_pnl(company_key, start_date, end_date)
        except Exception:
            income_statement_df = pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
        try:
            balance_sheet_df = get_consolidated_balance_sheet(company_key, start_date, end_date)
        except Exception:
            balance_sheet_df = pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
        # For consolidated, skip cash flow and equity for now
        cash_flow_df = pd.DataFrame(columns=["Section", "Line Item", "Amount (GHS)"])
        equity_df = pd.DataFrame(columns=["Account Code", "Line Item", "Amount (GHS)"])
    else:
        start_key = _financial_report_cache_date(start_date)
        end_key = _financial_report_cache_date(end_date)
        account_key = _financial_report_cache_date(account_name)
        try:
            trial_balance_df = _cached_trial_balance_report(company_key, start_key, end_key, account_key)
        except Exception:
            trial_balance_df = pd.DataFrame(columns=["Account Code", "Account", "Type", "Debit (GHS)", "Credit (GHS)", "Balance (GHS)", "Balanced"])
        try:
            income_statement_df = _cached_income_statement_report(company_key, start_key, end_key, account_key)
        except Exception:
            income_statement_df = pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
        try:
            balance_sheet_df = _cached_balance_sheet_report(company_key, start_key, end_key, account_key)
        except Exception:
            balance_sheet_df = pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
        try:
            cash_flow_df = get_cash_flow_statement(company_key, start_date, end_date, account_name)
        except Exception:
            cash_flow_df = pd.DataFrame(columns=["Section", "Line Item", "Amount (GHS)"])
        try:
            equity_df = get_changes_in_equity(company_key, start_date, end_date, account_name)
        except Exception:
            equity_df = pd.DataFrame(columns=["Account Code", "Line Item", "Amount (GHS)"])
    
    try:
        depreciation_df = get_depreciation_schedule(company_key)
    except Exception:
        depreciation_df = pd.DataFrame(columns=["Asset Name", "Category", "Purchase Date", "Cost (GHS)", "Useful Life (Years)", "Residual Value (GHS)", "Method", "Rate (%)", "Accumulated Depreciation (GHS)", "Book Value (GHS)", "Last Depreciation Date", "Status"])

    total_debits = _safe_number(trial_balance_df.get("Debit (GHS)"))
    total_credits = _safe_number(trial_balance_df.get("Credit (GHS)"))
    total_assets = _safe_number(balance_sheet_df.loc[balance_sheet_df["Category"].isin(["Current Assets", "Non-Current Assets"]), "Amount (GHS)"]) if not balance_sheet_df.empty else 0.0
    total_liabilities = _safe_number(balance_sheet_df.loc[balance_sheet_df["Category"].isin(["Current Liabilities", "Non-Current Liabilities"]), "Amount (GHS)"]) if not balance_sheet_df.empty else 0.0
    total_equity = _safe_number(balance_sheet_df.loc[balance_sheet_df["Category"] == "Equity", "Amount (GHS)"]) if not balance_sheet_df.empty else 0.0
    net_profit = _safe_number(income_statement_df.loc[income_statement_df["Account"] == "Net Profit", "Amount (GHS)"]) if not income_statement_df.empty else 0.0
    balanced = abs(total_debits - total_credits) < 0.01
    integrity = get_finance_integrity_diagnostics(
        company_key,
        as_of_date=end_date,
        branch_id=st.session_state.get("active_branch_id"),
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Trial Balance", "Balanced" if balanced else "Out of Balance")
    col2.metric("Profit for the Period", format_currency(_report_convert(net_profit)))
    col3.metric("Balance Sheet", "Balanced" if abs(total_assets - (total_liabilities + total_equity)) < 0.01 else "Needs Review")
    st.caption(f"Debit/Credit Validation: {'Balanced' if balanced else 'Needs review'}")
    with st.expander("Finance Integrity", expanded=False):
        i1, i2, i3 = st.columns(3)
        i1.metric(
            "A/R Reconciliation",
            "Matched" if integrity["accounts_receivable"]["reconciled"] else "Mismatch",
            format_currency(integrity["accounts_receivable"]["difference"]),
        )
        i2.metric(
            "A/P Reconciliation",
            "Matched" if integrity["accounts_payable"]["reconciled"] else "Mismatch",
            format_currency(integrity["accounts_payable"]["difference"]),
        )
        i3.metric(
            "Inventory Reconciliation",
            "Matched" if integrity["inventory"]["reconciled"] else "Mismatch",
            format_currency(integrity["inventory"]["difference"]),
        )
        j1, j2, j3 = st.columns(3)
        j1.metric("Unbalanced Journals", str(int(integrity["unbalanced_journal_count"])))
        j2.metric("Orphaned Journal Refs", str(int(integrity["orphaned_journal_reference_count"])))
        j3.metric("Missing GL Impact", str(int(integrity["source_documents_missing_gl_count"])))
        st.caption(
            "A/R subledger {ar_sub} vs control {ar_gl} | A/P subledger {ap_sub} vs control {ap_gl} | Inventory subledger {inv_sub} vs control {inv_gl}".format(
                ar_sub=format_currency(integrity["accounts_receivable"]["subledger_total"]),
                ar_gl=format_currency(integrity["accounts_receivable"]["control_account_balance"]),
                ap_sub=format_currency(integrity["accounts_payable"]["subledger_total"]),
                ap_gl=format_currency(integrity["accounts_payable"]["control_account_balance"]),
                inv_sub=format_currency(integrity["inventory"]["subledger_total"]),
                inv_gl=format_currency(integrity["inventory"]["control_account_balance"]),
            )
        )
        if integrity["orphaned_journal_references"]:
            st.markdown("Orphaned source-document journal references")
            st.dataframe(pd.DataFrame(integrity["orphaned_journal_references"]), use_container_width=True)
        if integrity["source_document_mismatches"]:
            st.markdown("Source documents with missing or unexpected GL impact")
            st.dataframe(pd.DataFrame(integrity["source_document_mismatches"]), use_container_width=True)
        account_warnings = integrity["chart_of_accounts"].get("warnings", [])
        if account_warnings:
            st.warning("Account structure warnings: " + "; ".join(account_warnings))
        else:
            st.success("Account structure warnings: none")

    tabs = st.tabs(
        [
            "Trial Balance",
            "Statement of Profit or Loss",
            "Statement of Financial Position",
            "Statement of Cash Flows",
            "Statement of Changes in Equity",
            "Depreciation Schedule",
        ]
    )
    report_defs = [
        ("Trial Balance", trial_balance_df),
        ("Statement of Profit or Loss", income_statement_df),
        ("Statement of Financial Position", balance_sheet_df),
        ("Statement of Cash Flows", cash_flow_df),
        ("Statement of Changes in Equity", equity_df),
        ("Depreciation Schedule", depreciation_df),
    ]
    reports_empty = all(_safe_dataframe(df, []).empty for _, df in report_defs)
    if eka_modules.can_view_runtime_admin_diagnostics(effective_role):
        eka_modules.render_backend_activation_diagnostics_panel(
            effective_role,
            expanded=reports_empty and get_active_db_backend() != "postgres",
        )
        with st.expander("LV-001 Live Validation Diagnostics (Admin Only)", expanded=reports_empty):
            lv001 = eka_modules.get_live_validation_lv001_diagnostics(
                company_key,
                branch_id=st.session_state.get("active_branch_id"),
                start_date=start_date,
                end_date=end_date,
            )
            st.dataframe(
                pd.DataFrame(
                    [{key: value for key, value in lv001.items() if key != "postgres_query_timings"}]
                ),
                use_container_width=True,
                hide_index=True,
            )
            if lv001.get("postgres_query_timings"):
                st.markdown("**PostgreSQL Read Timings (Recent)**")
                st.dataframe(pd.DataFrame(lv001["postgres_query_timings"]), use_container_width=True, hide_index=True)
    if reports_empty:
        st.warning(
            "No financial report rows were returned for the current filters. "
            "Trial Balance and Balance Sheet use cumulative balances through End Date; "
            "Income Statement uses Start Date through End Date. "
            "Open LV-001 diagnostics to confirm company scope, row counts, and query timing."
        )

    for tab, (label, df) in zip(tabs, report_defs):
        with tab:
            display_df = _ifrs_account_display(_convert_money_frame(_safe_dataframe(df, [])))
            _display_table_with_rate(display_df)
            _csv_button(label, display_df, f"{label}_ifrs_safe_{company_key}")
    eka_modules.record_lv002b_operation(
        "financial_reports.load",
        (time.perf_counter() - reports_started) * 1000.0,
        surface="financial_reports",
    )
    eka_modules.record_lv003_hot_path_call(
        "financials.show_financial_reports",
        (time.perf_counter() - reports_started) * 1000.0,
        required=True,
        recommendation="keep",
        surface="financial_reports",
    )


def show_reports(company_key, role=None):
    """Financial reports sidebar entry point."""
    show_financial_reports(company_key, role)


def get_consolidated_pnl(company_key, start_date=None, end_date=None):
    """Get consolidated Profit & Loss for all branches."""
    # For now, since branch_id is optional, get all transactions for company
    df = _journal_df(company_key, start_date=start_date, end_date=end_date)
    if df.empty:
        return pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
    
    income_df = df[df["account_type"].isin(["Income", "Expense"])].copy()
    if income_df.empty:
        return pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
    
    rows = []
    gross_revenue = 0.0
    sales_returns = 0.0
    cost_of_sales = 0.0
    operating_expenses = 0.0
    income_df["amount"] = income_df.apply(
        lambda row: (row["credit"] - row["debit"]) if row["account_type"] == "Income" else (row["debit"] - row["credit"]),
        axis=1,
    )
    grouped = income_df.groupby(["account_code", "account_name", "account_type"], as_index=False)["amount"].sum()
    for _, row in grouped.iterrows():
        account_type = str(row["account_type"] or "").title()
        account_name = str(row["account_name"] or "").strip()
        normalized_account = account_name.lower()
        amount = float(row["amount"] or 0.0)
        if account_type == "Income":
            gross_revenue += amount
            rows.append({"Category": "Revenue", "Account Code": row["account_code"], "Account": account_name, "Amount (GHS)": amount})
        elif normalized_account == "sales returns and refunds":
            sales_returns += amount
            rows.append({"Category": "Sales Deductions", "Account Code": row["account_code"], "Account": "Less: Sales Returns and Refunds", "Amount (GHS)": -amount})
        elif normalized_account == "cost of goods sold":
            cost_of_sales += amount
            rows.append({"Category": "Cost of Sales", "Account Code": row["account_code"], "Account": account_name, "Amount (GHS)": amount})
        else:
            operating_expenses += amount
            rows.append({"Category": "Operating Expenses", "Account Code": row["account_code"], "Account": account_name, "Amount (GHS)": amount})

    net_sales = gross_revenue - sales_returns
    gross_profit = net_sales - cost_of_sales
    rows.append({"Category": "Revenue", "Account Code": "", "Account": "Net Sales", "Amount (GHS)": net_sales})
    rows.append({"Category": "Profit for the Period", "Account Code": "", "Account": "Gross Profit", "Amount (GHS)": gross_profit})
    rows.append({"Category": "Profit for the Period", "Account Code": "", "Account": "Net Profit", "Amount (GHS)": gross_profit - operating_expenses})
    return pd.DataFrame(rows)


def get_consolidated_balance_sheet(company_key, start_date=None, end_date=None):
    """Get consolidated Balance Sheet for all branches."""
    df = _journal_df(company_key, start_date=start_date, end_date=end_date)
    if df.empty:
        return pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
    
    bs_df = df[df["account_type"].isin(["Asset", "Liability", "Equity"])].copy()
    if bs_df.empty:
        return pd.DataFrame(columns=["Category", "Account Code", "Account", "Amount (GHS)"])
    
    bs_df["amount"] = bs_df.apply(
        lambda row: (row["debit"] - row["credit"]) if row["account_type"] == "Asset" else (row["credit"] - row["debit"]),
        axis=1,
    )
    grouped = bs_df.groupby(["account_code", "account_name", "account_type"], as_index=False)["amount"].sum()
    category_map = {"Asset": "Assets", "Liability": "Liabilities", "Equity": "Equity"}
    grouped["Category"] = grouped["account_type"].map(category_map)
    grouped = grouped.rename(columns={"account_name": "Account", "account_code": "Account Code", "amount": "Amount (GHS)"})
    return grouped[["Category", "Account Code", "Account", "Amount (GHS)"]]
