from datetime import datetime

import pandas as pd
import streamlit as st

from database import get_connection
from modules import convert_amount_from_base, format_currency, get_display_currency, post_transaction, set_period_lock


def _resolve_date(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _journal_df(company_key, start_date=None, end_date=None, account_name=None):
    conn = get_connection()
    try:
        query = """
            SELECT
                je.id AS entry_id,
                je.date,
                je.description,
                je.reference,
                je.created_by,
                COALESCE(c.name, c.account_name) AS account_name,
                COALESCE(c.type, c.category, c.account_type) AS account_type,
                jl.debit,
                jl.credit
            FROM journal_entries je
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE je.company_key = ?
        """
        params = [company_key]
        if start_date:
            query += " AND date(je.date) >= date(?)"
            params.append(_resolve_date(start_date))
        if end_date:
            query += " AND date(je.date) <= date(?)"
            params.append(_resolve_date(end_date))
        if account_name:
            query += " AND lower(COALESCE(c.name, c.account_name)) LIKE ?"
            params.append(f"%{str(account_name).lower()}%")
        query += " ORDER BY date(je.date), je.id, COALESCE(c.name, c.account_name)"
        df = pd.read_sql_query(query, conn, params=params)
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
        rows = conn.execute(
            """
            SELECT COALESCE(name, account_name) AS account_name,
                   COALESCE(type, category, account_type) AS account_type
            FROM chart_of_accounts
            ORDER BY COALESCE(name, account_name)
            """
        ).fetchall()
        return {str(row["account_name"]): str(row["account_type"]) for row in rows}
    finally:
        conn.close()


def _party_id(conn, table_name, company_key, name):
    row = conn.execute(f"SELECT id FROM {table_name} WHERE company_key = ? AND name = ?", (company_key, name)).fetchone()
    if row:
        return int(row["id"])
    cursor = conn.execute(
        f"INSERT INTO {table_name} (company_key, name, currency) VALUES (?, ?, 'GHS')",
        (company_key, name),
    )
    return int(cursor.lastrowid)


def _csv_button(label, dataframe, key):
    st.download_button(
        f"📥 Export {label} CSV",
        data=dataframe.to_csv(index=False).encode("utf-8") if not dataframe.empty else b"",
        file_name=f"{label.lower().replace(' ', '_')}.csv",
        mime="text/csv",
        key=key,
    )


def _money_label():
    return f"({get_display_currency()})"


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
        df[column_name] = pd.to_numeric(df[column_name], errors="coerce").fillna(0.0).map(convert_amount_from_base)
    renamed_columns = {}
    for column_name in df.columns:
        if "(GHS)" in str(column_name):
            renamed_columns[column_name] = str(column_name).replace("(GHS)", _money_label())
    return df.rename(columns=renamed_columns)


def _filter_controls(prefix):
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.now().date().replace(day=1), key=f"{prefix}_start")
    with col2:
        end_date = st.date_input("End Date", value=datetime.now().date(), key=f"{prefix}_end")
    with col3:
        account_name = st.text_input("Account Filter", key=f"{prefix}_account")
    return start_date, end_date, account_name.strip()


def get_general_journal(company_key, start_date=None, end_date=None, account_name=None):
    df = _journal_df(company_key, start_date, end_date, account_name)
    if df.empty:
        return pd.DataFrame(columns=["Date", "Entry ID", "Description", "Reference", "Created By", "Account", "Type", "Debit (GHS)", "Credit (GHS)"])
    df = df.rename(
        columns={
            "date": "Date",
            "entry_id": "Entry ID",
            "description": "Description",
            "reference": "Reference",
            "created_by": "Created By",
            "account_name": "Account",
            "account_type": "Type",
            "debit": "Debit (GHS)",
            "credit": "Credit (GHS)",
        }
    )
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df


def get_sales_journal(company_key, start_date=None, end_date=None, account_name=None):
    df = get_general_journal(company_key, start_date, end_date, account_name)
    if df.empty:
        return df
    return df[
        df["Description"].str.contains("sale|invoice|customer", case=False, na=False)
        | df["Account"].isin(["Sales", "Sales Revenue", "Accounts Receivable", "Cash"])
    ].reset_index(drop=True)


def get_purchases_journal(company_key, start_date=None, end_date=None, account_name=None):
    df = get_general_journal(company_key, start_date, end_date, account_name)
    if df.empty:
        return df
    return df[
        df["Description"].str.contains("purchase|bill|supplier", case=False, na=False)
        | df["Account"].isin(["Inventory", "Purchases", "Accounts Payable", "Cash"])
    ].reset_index(drop=True)


def get_cash_book(company_key, start_date=None, end_date=None, account_name=None):
    df = get_general_journal(company_key, start_date, end_date, account_name)
    if df.empty:
        return pd.DataFrame(columns=["Date", "Description", "Reference", "Account", "Debit (GHS)", "Credit (GHS)", "Movement (GHS)", "Running Balance (GHS)"])
    cash_df = df[df["Account"].isin(["Cash", "Bank", "Mobile Money"])].copy()
    if cash_df.empty:
        return pd.DataFrame(columns=["Date", "Description", "Reference", "Account", "Debit (GHS)", "Credit (GHS)", "Movement (GHS)", "Running Balance (GHS)"])
    cash_df["Movement (GHS)"] = cash_df["Debit (GHS)"] - cash_df["Credit (GHS)"]
    cash_df["Running Balance (GHS)"] = cash_df["Movement (GHS)"].cumsum()
    return cash_df[["Date", "Description", "Reference", "Account", "Debit (GHS)", "Credit (GHS)", "Movement (GHS)", "Running Balance (GHS)"]]


def get_general_ledger(company_key, start_date=None, end_date=None, account_name=None):
    df = get_general_journal(company_key, start_date, end_date, account_name)
    if df.empty:
        return pd.DataFrame(columns=["Date", "Account", "Description", "Reference", "Debit (GHS)", "Credit (GHS)", "Running Balance (GHS)"])
    frames = []
    for account, group in df.groupby("Account", sort=True):
        running = (group["Debit (GHS)"] - group["Credit (GHS)"]) if _normal_balance(group["Type"].iloc[0]) == "debit" else (group["Credit (GHS)"] - group["Debit (GHS)"])
        ledger_group = group.copy()
        ledger_group["Running Balance (GHS)"] = running.cumsum()
        frames.append(ledger_group[["Date", "Account", "Description", "Reference", "Debit (GHS)", "Credit (GHS)", "Running Balance (GHS)"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["Date", "Account", "Description", "Reference", "Debit (GHS)", "Credit (GHS)", "Running Balance (GHS)"])


def get_trial_balance(company_key, start_date=None, end_date=None, account_name=None):
    df = _journal_df(company_key, start_date, end_date, account_name)
    if df.empty:
        return pd.DataFrame(columns=["Account", "Type", "Debit (GHS)", "Credit (GHS)", "Balance (GHS)", "Balanced"])
    grouped = df.groupby(["account_name", "account_type"], as_index=False)[["debit", "credit"]].sum()
    grouped["Balance (GHS)"] = grouped.apply(
        lambda row: (row["debit"] - row["credit"]) if _normal_balance(row["account_type"]) == "debit" else (row["credit"] - row["debit"]),
        axis=1,
    )
    grouped = grouped[(grouped["debit"].abs() > 0.0001) | (grouped["credit"].abs() > 0.0001)].copy()
    balanced = abs(float(grouped["debit"].sum()) - float(grouped["credit"].sum())) < 0.01
    grouped["Balanced"] = "Yes" if balanced else "No"
    return grouped.rename(columns={"account_name": "Account", "account_type": "Type", "debit": "Debit (GHS)", "credit": "Credit (GHS)"}).reset_index(drop=True)


def get_income_statement(company_key, start_date=None, end_date=None, account_name=None):
    tb = get_trial_balance(company_key, start_date, end_date, account_name)
    rows = []
    income_total = 0.0
    expense_total = 0.0
    for _, row in tb.iterrows():
        account_type = str(row["Type"]).title()
        if account_type == "Income":
            amount = float(row["Credit (GHS)"] - row["Debit (GHS)"])
            income_total += amount
            rows.append({"Category": "Income", "Account": row["Account"], "Amount (GHS)": amount})
        elif account_type == "Expense":
            amount = float(row["Debit (GHS)"] - row["Credit (GHS)"])
            expense_total += amount
            rows.append({"Category": "Expense", "Account": row["Account"], "Amount (GHS)": amount})
    rows.append({"Category": "Summary", "Account": "Net Profit", "Amount (GHS)": income_total - expense_total})
    return pd.DataFrame(rows)


def get_balance_sheet(company_key, start_date=None, end_date=None, account_name=None):
    tb = get_trial_balance(company_key, start_date, end_date, account_name)
    rows = []
    for _, row in tb.iterrows():
        account_type = str(row["Type"]).title()
        if account_type not in ("Asset", "Liability", "Equity"):
            continue
        amount = float(row["Debit (GHS)"] - row["Credit (GHS)"]) if account_type == "Asset" else float(row["Credit (GHS)"] - row["Debit (GHS)"])
        rows.append({"Category": account_type, "Account": row["Account"], "Amount (GHS)": amount})
    return pd.DataFrame(rows)


def get_cash_flow_statement(company_key, start_date=None, end_date=None, account_name=None):
    income_df = get_income_statement(company_key, start_date, end_date, account_name)
    bs_df = get_balance_sheet(company_key, start_date, end_date, account_name)
    net_profit = float(income_df.loc[income_df["Account"] == "Net Profit", "Amount (GHS)"].sum()) if not income_df.empty else 0.0
    depreciation = float(income_df.loc[income_df["Account"] == "Depreciation Expense", "Amount (GHS)"].sum()) if not income_df.empty else 0.0
    receivables = float(bs_df.loc[bs_df["Account"] == "Accounts Receivable", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    inventory = float(bs_df.loc[bs_df["Account"] == "Inventory", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    payables = float(bs_df.loc[bs_df["Account"] == "Accounts Payable", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    fixed_assets = float(bs_df.loc[bs_df["Account"] == "Fixed Assets", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    capital = float(bs_df.loc[bs_df["Account"].isin(["Owner Capital", "Opening Balance Equity"]), "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    loans = float(bs_df.loc[bs_df["Account"] == "Loans Payable", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    operating = net_profit + depreciation - receivables - inventory + payables
    investing = -fixed_assets
    financing = capital + loans
    return pd.DataFrame(
        [
            {"Section": "Operating", "Line Item": "Net Profit", "Amount (GHS)": net_profit},
            {"Section": "Operating", "Line Item": "Depreciation", "Amount (GHS)": depreciation},
            {"Section": "Operating", "Line Item": "Working Capital Impact", "Amount (GHS)": -receivables - inventory + payables},
            {"Section": "Operating", "Line Item": "Net Cash from Operations", "Amount (GHS)": operating},
            {"Section": "Investing", "Line Item": "Net Fixed Asset Movement", "Amount (GHS)": investing},
            {"Section": "Financing", "Line Item": "Capital and Loan Movement", "Amount (GHS)": financing},
            {"Section": "Summary", "Line Item": "Net Cash Movement", "Amount (GHS)": operating + investing + financing},
        ]
    )


def get_changes_in_equity(company_key, start_date=None, end_date=None, account_name=None):
    bs_df = get_balance_sheet(company_key, start_date, end_date, account_name)
    income_df = get_income_statement(company_key, start_date, end_date, account_name)
    opening_equity = float(bs_df.loc[bs_df["Account"] == "Opening Balance Equity", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    owner_capital = float(bs_df.loc[bs_df["Account"] == "Owner Capital", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    retained_earnings = float(bs_df.loc[bs_df["Account"] == "Retained Earnings", "Amount (GHS)"].sum()) if not bs_df.empty else 0.0
    net_profit = float(income_df.loc[income_df["Account"] == "Net Profit", "Amount (GHS)"].sum()) if not income_df.empty else 0.0
    return pd.DataFrame(
        [
            {"Line Item": "Opening Balance Equity", "Amount (GHS)": opening_equity},
            {"Line Item": "Owner Capital", "Amount (GHS)": owner_capital},
            {"Line Item": "Retained Earnings", "Amount (GHS)": retained_earnings},
            {"Line Item": "Net Profit for Period", "Amount (GHS)": net_profit},
            {"Line Item": "Closing Equity", "Amount (GHS)": opening_equity + owner_capital + retained_earnings + net_profit},
        ]
    )


def get_depreciation_schedule(company_key):
    conn = get_connection()
    try:
        df = pd.read_sql_query(
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
            conn,
            params=(company_key,),
        )
        return df
    finally:
        conn.close()


def show_record_transaction(company_key, role):
    st.header("🧾 Record Transaction")
    accounts = _chart_lookup()
    with st.expander("Period Lock Controls", expanded=False):
        period_date = st.date_input("Accounting Period", value=datetime.now().date().replace(day=1), key=f"period_date_{company_key}")
        col1, col2 = st.columns(2)
        if col1.button("🔒 Lock Period", key=f"lock_period_{company_key}"):
            set_period_lock(company_key, period_date, True, locked_by=role)
            st.success(f"Locked {period_date.strftime('%Y-%m')}")
        if col2.button("🔓 Unlock Period", key=f"unlock_period_{company_key}"):
            set_period_lock(company_key, period_date, False, locked_by=role)
            st.success(f"Unlocked {period_date.strftime('%Y-%m')}")

    with st.form(f"manual_tx_form_{company_key}"):
        tx_date = st.date_input("Date", value=datetime.now().date(), key=f"manual_tx_date_{company_key}")
        description = st.text_input("Description", key=f"manual_tx_desc_{company_key}")
        reference = st.text_input("Reference", key=f"manual_tx_ref_{company_key}")
        lines = []
        account_names = [""] + list(accounts.keys())
        for idx in range(4):
            c1, c2, c3 = st.columns([3, 1, 1])
            account = c1.selectbox(f"Account {idx + 1}", account_names, key=f"manual_account_{company_key}_{idx}")
            debit = c2.number_input(f"Debit {idx + 1}", min_value=0.0, step=0.01, key=f"manual_debit_{company_key}_{idx}")
            credit = c3.number_input(f"Credit {idx + 1}", min_value=0.0, step=0.01, key=f"manual_credit_{company_key}_{idx}")
            if account and (debit > 0 or credit > 0):
                lines.append({"account_name": account, "category": accounts.get(account, "Expense"), "debit": debit, "credit": credit})
        if st.form_submit_button("Post Transaction"):
            try:
                post_transaction(description or "Manual journal entry", lines, company_key=company_key, reference=reference, created_by=role, entry_date=tx_date)
                st.success("Transaction posted successfully.")
                st.rerun()
            except Exception as exc:
                st.error(f"Transaction posting failed: {exc}")


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
                conn.execute("INSERT OR IGNORE INTO customers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')", (company_key, name, email, phone))
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = pd.read_sql_query("SELECT name, email, phone, currency, created_at FROM customers WHERE company_key = ? ORDER BY name", conn, params=(company_key,))
        conn.close()
        st.dataframe(df, use_container_width=True)
        _csv_button("Customers", df, f"customers_csv_{company_key}")

    with tabs[1]:
        with st.form(f"supplier_form_{company_key}"):
            name = st.text_input("Supplier Name")
            email = st.text_input("Email", key=f"supplier_email_{company_key}")
            phone = st.text_input("Phone", key=f"supplier_phone_{company_key}")
            if st.form_submit_button("Save Supplier") and name:
                conn = get_connection()
                conn.execute("INSERT OR IGNORE INTO suppliers (company_key, name, email, phone, currency) VALUES (?, ?, ?, ?, 'GHS')", (company_key, name, email, phone))
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = pd.read_sql_query("SELECT name, email, phone, currency, created_at FROM suppliers WHERE company_key = ? ORDER BY name", conn, params=(company_key,))
        conn.close()
        st.dataframe(df, use_container_width=True)
        _csv_button("Suppliers", df, f"suppliers_csv_{company_key}")

    with tabs[2]:
        conn = get_connection()
        customers = [row[0] for row in conn.execute("SELECT name FROM customers WHERE company_key = ? ORDER BY name", (company_key,)).fetchall()]
        conn.close()
        with st.form(f"invoice_form_{company_key}"):
            customer_name = st.selectbox("Customer", [""] + customers)
            amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01)
            status = st.selectbox("Status", ["Draft", "Pending", "Paid"])
            invoice_date = st.date_input("Invoice Date", value=datetime.now().date(), key=f"invoice_date_{company_key}")
            description = st.text_input("Description", key=f"invoice_description_{company_key}")
            if st.form_submit_button("Save Invoice") and customer_name and amount > 0:
                conn = get_connection()
                customer_id = _party_id(conn, "customers", company_key, customer_name)
                cursor = conn.execute(
                    """
                    INSERT INTO invoices (company_key, customer_id, invoice_number, invoice_date, due_date, status, amount, currency, description, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                    """,
                    (company_key, customer_id, f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}", invoice_date.isoformat(), invoice_date.isoformat(), status, amount, description, role),
                )
                if status != "Draft":
                    post_transaction(
                        "Sales invoice",
                        [
                            {"account_name": "Cash" if status == "Paid" else "Accounts Receivable", "category": "Asset", "debit": amount, "credit": 0},
                            {"account_name": "Sales Revenue", "category": "Income", "debit": 0, "credit": amount},
                        ],
                        company_key=company_key,
                        reference=f"INV-{cursor.lastrowid}",
                        created_by=role,
                        entry_date=invoice_date,
                        conn=conn,
                    )
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = pd.read_sql_query("SELECT invoice_number, invoice_date, due_date, status, amount, currency, description FROM invoices WHERE company_key = ? ORDER BY invoice_date DESC", conn, params=(company_key,))
        conn.close()
        st.dataframe(df, use_container_width=True)
        _csv_button("Invoices", df, f"invoices_csv_{company_key}")

    with tabs[3]:
        conn = get_connection()
        suppliers = [row[0] for row in conn.execute("SELECT name FROM suppliers WHERE company_key = ? ORDER BY name", (company_key,)).fetchall()]
        conn.close()
        with st.form(f"bill_form_{company_key}"):
            supplier_name = st.selectbox("Supplier", [""] + suppliers)
            amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01, key=f"bill_amount_{company_key}")
            status = st.selectbox("Status", ["Draft", "Pending", "Received"], key=f"bill_status_{company_key}")
            bill_date = st.date_input("Bill Date", value=datetime.now().date(), key=f"bill_date_{company_key}")
            description = st.text_input("Description", key=f"bill_description_{company_key}")
            if st.form_submit_button("Save Bill") and supplier_name and amount > 0:
                conn = get_connection()
                supplier_id = _party_id(conn, "suppliers", company_key, supplier_name)
                cursor = conn.execute(
                    """
                    INSERT INTO bills (company_key, supplier_id, bill_number, bill_date, due_date, status, amount, currency, description, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                    """,
                    (company_key, supplier_id, f"BILL-{datetime.now().strftime('%Y%m%d%H%M%S')}", bill_date.isoformat(), bill_date.isoformat(), status, amount, description, role),
                )
                if status != "Draft":
                    credit_account = "Cash" if status == "Received" else "Accounts Payable"
                    credit_type = "Asset" if credit_account == "Cash" else "Liability"
                    post_transaction(
                        "Purchase bill",
                        [
                            {"account_name": "Inventory", "category": "Asset", "debit": amount, "credit": 0},
                            {"account_name": credit_account, "category": credit_type, "debit": 0, "credit": amount},
                        ],
                        company_key=company_key,
                        reference=f"BILL-{cursor.lastrowid}",
                        created_by=role,
                        entry_date=bill_date,
                        conn=conn,
                    )
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = pd.read_sql_query("SELECT bill_number, bill_date, due_date, status, amount, currency, description FROM bills WHERE company_key = ? ORDER BY bill_date DESC", conn, params=(company_key,))
        conn.close()
        st.dataframe(df, use_container_width=True)
        _csv_button("Bills", df, f"bills_csv_{company_key}")

    with tabs[4]:
        with st.form(f"payments_form_{company_key}"):
            payment_type = st.selectbox("Payment Type", ["Customer Receipt", "Supplier Payment"])
            amount = st.number_input("Amount (GHS)", min_value=0.0, step=0.01, key=f"payment_amount_{company_key}")
            payment_method = st.selectbox("Method", ["Cash", "Bank", "Mobile Money"])
            payment_ref = st.text_input("Reference")
            payment_date = st.date_input("Payment Date", value=datetime.now().date())
            if st.form_submit_button("Save Payment") and amount > 0:
                conn = get_connection()
                conn.execute(
                    "INSERT INTO payments (company_key, payment_date, payment_type, amount, currency, method, reference, created_by) VALUES (?, ?, ?, ?, 'GHS', ?, ?, ?)",
                    (company_key, payment_date.isoformat(), payment_type, amount, payment_method, payment_ref, role),
                )
                lines = (
                    [
                        {"account_name": "Cash", "category": "Asset", "debit": amount, "credit": 0},
                        {"account_name": "Accounts Receivable", "category": "Asset", "debit": 0, "credit": amount},
                    ]
                    if payment_type == "Customer Receipt"
                    else [
                        {"account_name": "Accounts Payable", "category": "Liability", "debit": amount, "credit": 0},
                        {"account_name": "Cash", "category": "Asset", "debit": 0, "credit": amount},
                    ]
                )
                post_transaction("Payment entry", lines, company_key=company_key, reference=payment_ref, created_by=role, entry_date=payment_date, conn=conn)
                conn.commit()
                conn.close()
                st.rerun()
        conn = get_connection()
        df = pd.read_sql_query("SELECT payment_date, payment_type, amount, currency, method, reference, created_by FROM payments WHERE company_key = ? ORDER BY payment_date DESC", conn, params=(company_key,))
        conn.close()
        st.dataframe(df, use_container_width=True)
        _csv_button("Payments", df, f"payments_csv_{company_key}")


def show_ledger_viewer(company_key, role):
    st.header("📚 Ledger Viewer")
    start_date, end_date, account_name = _filter_controls(f"ledger_{company_key}")
    tabs = st.tabs(["General Journal", "Sales Journal", "Purchases Journal", "Cash Book", "General Ledger"])
    report_defs = [
        ("General Journal", get_general_journal(company_key, start_date, end_date, account_name)),
        ("Sales Journal", get_sales_journal(company_key, start_date, end_date, account_name)),
        ("Purchases Journal", get_purchases_journal(company_key, start_date, end_date, account_name)),
        ("Cash Book", get_cash_book(company_key, start_date, end_date, account_name)),
        ("General Ledger", get_general_ledger(company_key, start_date, end_date, account_name)),
    ]
    for tab, (label, df) in zip(tabs, report_defs):
        with tab:
            st.dataframe(df, use_container_width=True)
            _csv_button(label, df, f"{label}_{company_key}")


def show_ledger_viewer(company_key, role):
    st.header("📚 Ledger Viewer")
    start_date, end_date, account_name = _filter_controls(f"ledger_override_{company_key}")
    tabs = st.tabs(["General Journal", "Sales Journal", "Purchases Journal", "Cash Book", "General Ledger"])
    report_defs = [
        ("General Journal", get_general_journal(company_key, start_date, end_date, account_name)),
        ("Sales Journal", get_sales_journal(company_key, start_date, end_date, account_name)),
        ("Purchases Journal", get_purchases_journal(company_key, start_date, end_date, account_name)),
        ("Cash Book", get_cash_book(company_key, start_date, end_date, account_name)),
        ("General Ledger", get_general_ledger(company_key, start_date, end_date, account_name)),
    ]
    for tab, (label, df) in zip(tabs, report_defs):
        with tab:
            display_df = _convert_money_frame(df)
            st.dataframe(display_df, use_container_width=True)
            _csv_button(label, display_df, f"{label}_override_{company_key}")


def show_financial_reports(company_key, role=None):
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
            st.dataframe(display_df, use_container_width=True)
            _csv_button(label, display_df, f"{label}_override_{company_key}")


def show_financial_reports(company_key, role=None):
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
            st.dataframe(df, use_container_width=True)
            _csv_button(label, df, f"{label}_{company_key}")


def show_financial_reports(company_key, role=None):
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
            display_df = _convert_money_frame(df)
            st.dataframe(display_df, use_container_width=True)
            _csv_button(label, display_df, f"{label}_final_{company_key}")


def show_reports(company_key, role=None):
    """Financial reports sidebar entry point."""
    show_financial_reports(company_key, role)
