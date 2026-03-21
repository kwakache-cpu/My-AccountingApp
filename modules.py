import os
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta


def _demo_notice():
    st.info("Enterprise Demo Mode is active. These values are temporary and are not written to the database.")


def show_sales_invoices_page(conn, demo_on):
    st.header("Sales Invoices")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [
                {"Customer": "Accra Retail Ltd", "Amount": 12500.0, "Status": "Paid", "Date": datetime.now().date().isoformat()},
            ]
        )
        st.dataframe(demo_df, width="stretch")
        return

    with st.form("sales_invoice_form"):
        customer_name = st.text_input("Customer Name")
        amount = st.number_input("Amount (₵)", min_value=0.0, value=0.0)
        status = st.selectbox("Status", ["Paid", "Pending", "Draft"])
        invoice_date = st.date_input("Date", value=datetime.now().date())
        submitted = st.form_submit_button("Save Invoice")

        if submitted and customer_name and amount > 0:
            conn.execute(
                "INSERT INTO sales_invoices (customer_name, amount, status, date) VALUES (?, ?, ?, ?)",
                (customer_name, amount, status, invoice_date.isoformat()),
            )
            conn.commit()
            st.success("Invoice saved.")
            st.rerun()

    invoice_rows = conn.execute(
        "SELECT customer_name, amount, status, date FROM sales_invoices ORDER BY date DESC, id DESC"
    ).fetchall()
    if invoice_rows:
        st.dataframe(pd.DataFrame(invoice_rows, columns=["Customer Name", "Amount", "Status", "Date"]), width="stretch")
    else:
        st.caption("No invoices yet.")


def show_accounts_payable_page(conn, demo_on):
    st.header("Accounts Payable")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [
                {"Supplier": "Tema Supplier Co.", "Amount": 4200.0, "Status": "Unpaid", "Date": datetime.now().date().isoformat()},
            ]
        )
        st.dataframe(demo_df, width="stretch")
        return

    with st.form("accounts_payable_form"):
        supplier_name = st.text_input("Supplier Name")
        amount = st.number_input("Amount (₵)", min_value=0.0, value=0.0)
        status = st.selectbox("Status", ["Unpaid", "Paid"])
        payable_date = st.date_input("Date", value=datetime.now().date())
        submitted = st.form_submit_button("Save Payable")

        if submitted and supplier_name and amount > 0:
            conn.execute(
                "INSERT INTO accounts_payable (supplier_name, amount, status, date) VALUES (?, ?, ?, ?)",
                (supplier_name, amount, status, payable_date.isoformat()),
            )
            conn.commit()
            st.success("Payable saved.")
            st.rerun()

    payable_rows = conn.execute(
        "SELECT supplier_name, amount, status, date FROM accounts_payable ORDER BY date DESC, id DESC"
    ).fetchall()
    if payable_rows:
        st.dataframe(pd.DataFrame(payable_rows, columns=["Supplier Name", "Amount", "Status", "Date"]), width="stretch")
    else:
        st.caption("No payables yet.")


def show_chart_of_accounts_page(conn, demo_on):
    st.header("Chart of Accounts")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [
                {"Account Name": "Sales Revenue", "Account Type": "Income", "Balance": 12500.0},
                {"Account Name": "Accounts Payable", "Account Type": "Liability", "Balance": 4200.0},
            ]
        )
        st.dataframe(demo_df, width="stretch")
        return

    with st.form("chart_of_accounts_form"):
        account_name = st.text_input("Account Name")
        account_type = st.selectbox("Account Type", ["Asset", "Liability", "Equity", "Income", "Expense"])
        balance = st.number_input("Opening Balance (₵)", value=0.0)
        submitted = st.form_submit_button("Add Account")

        if submitted and account_name:
            conn.execute(
                "INSERT INTO chart_of_accounts (account_name, account_type, balance) VALUES (?, ?, ?)",
                (account_name, account_type, balance),
            )
            conn.commit()
            st.success("Account created.")
            st.rerun()

    account_rows = conn.execute(
        "SELECT account_name, account_type, balance FROM chart_of_accounts ORDER BY account_name"
    ).fetchall()
    if account_rows:
        st.dataframe(pd.DataFrame(account_rows, columns=["Account Name", "Account Type", "Balance"]), width="stretch")
    else:
        st.caption("No chart of accounts records yet.")


def show_vouchers_page(conn, demo_on):
    st.header("Vouchers")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [
                {"Narration": "Demo revenue booking", "Amount": 12500.0, "Reference": "DEMO-001", "Date": datetime.now().date().isoformat()},
            ]
        )
        st.dataframe(demo_df, width="stretch")
        return

    with st.form("voucher_form"):
        narration = st.text_area("Narration")
        amount = st.number_input("Amount (₵)", min_value=0.0, value=0.0)
        ref_no = st.text_input("Reference Number")
        voucher_date = st.date_input("Date", value=datetime.now().date())
        submitted = st.form_submit_button("Post Voucher")

        if submitted and narration and amount > 0:
            conn.execute(
                "INSERT INTO vouchers (narration, amount, ref_no, date) VALUES (?, ?, ?, ?)",
                (narration, amount, ref_no, voucher_date.isoformat()),
            )
            conn.commit()
            st.success("Voucher posted.")
            st.rerun()

    voucher_rows = conn.execute(
        "SELECT narration, amount, ref_no, date FROM vouchers ORDER BY date DESC, id DESC"
    ).fetchall()
    if voucher_rows:
        st.dataframe(pd.DataFrame(voucher_rows, columns=["Narration", "Amount", "Reference", "Date"]), width="stretch")
    else:
        st.caption("No vouchers yet.")
