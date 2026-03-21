import os
import sqlite3
from datetime import date, datetime

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta
from groq import Groq

from modules import (
    show_accounts_payable_page,
    show_chart_of_accounts_page,
    show_sales_invoices_page,
    show_vouchers_page,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
SYSTEM_PROMPT = (
    "You are the Gatekeeper Accounting Expert. Explain accounting terms simply for Ghanaian "
    "businesses. Use live financial health figures when they are provided."
)


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sales_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT,
                amount REAL,
                status TEXT,
                date TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts_payable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_name TEXT,
                amount REAL,
                status TEXT,
                date TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_of_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT,
                account_type TEXT,
                balance REAL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                narration TEXT,
                amount REAL,
                ref_no TEXT,
                date TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def reset_to_clean_state():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()


def format_money(value):
    return f"₵ {value:,.2f}"


def get_demo_financial_snapshot():
    metrics = {
        "revenue": 12500.0,
        "payables": 4200.0,
        "net_health": 8300.0,
        "has_data": True,
    }
    chart_df = pd.DataFrame(
        {"Amount": [metrics["revenue"], metrics["payables"]]},
        index=["Income", "Expenses"],
    )
    return metrics, chart_df


def get_financial_metrics():
    conn = get_connection()
    try:
        revenue = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM sales_invoices WHERE status = 'Paid'"
        ).fetchone()[0] or 0.0
        payables = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM accounts_payable WHERE status = 'Unpaid'"
        ).fetchone()[0] or 0.0
        invoice_count = conn.execute("SELECT COUNT(*) FROM sales_invoices").fetchone()[0] or 0
        payable_count = conn.execute("SELECT COUNT(*) FROM accounts_payable").fetchone()[0] or 0
    finally:
        conn.close()

    metrics = {
        "revenue": float(revenue),
        "payables": float(payables),
        "net_health": float(revenue) - float(payables),
        "has_data": (invoice_count + payable_count) > 0,
    }
    chart_df = pd.DataFrame(
        {"Amount": [metrics["revenue"], metrics["payables"]]},
        index=["Income", "Expenses"],
    )
    return metrics, chart_df


def get_groq_client():
    return Groq(api_key=st.secrets["GROQ_API_KEY"])


def ask_gatekeeper_ai(menu_selection, chat_history, metrics, demo_on):
    metric_context = (
        f"Revenue: {format_money(metrics['revenue'])}, "
        f"Payables: {format_money(metrics['payables'])}, "
        f"Net Health: {format_money(metrics['net_health'])}."
    )
    mode_context = "Demo mode is ON. These are simulated figures." if demo_on else "Demo mode is OFF. These are real database figures."
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Current page: {menu_selection}."},
        {"role": "system", "content": f"{mode_context} {metric_context}"},
    ]
    messages.extend(chat_history[-8:])

    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as error:
        return f"Gatekeeper AI is unavailable right now: {error}"


def inject_css():
    st.markdown(
        """
        <style>
        .main .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border-radius: 16px;
            padding: 15px;
            border: 1px solid #e5e7eb;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
        }
        [data-testid="stMetricLabel"] {
            font-weight: 700;
        }
        .sidebar-chat-shell {
            position: sticky;
            bottom: 0;
            background: linear-gradient(180deg, rgba(255,255,255,0.92), #ffffff);
            padding-top: 0.75rem;
            border-top: 1px solid #e5e7eb;
            margin-top: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_chat(menu_selection, demo_on, metrics):
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Ask about your financial health, payables, or chart of accounts.",
            }
        ]

    st.sidebar.markdown('<div class="sidebar-chat-shell">', unsafe_allow_html=True)
    st.sidebar.markdown("### Gatekeeper AI")
    st.sidebar.caption(f"Current view: {menu_selection}")

    for message in st.session_state.messages[-6:]:
        with st.sidebar:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    user_question = st.sidebar.chat_input("Ask Gatekeeper AI...")
    if user_question:
        st.session_state.messages.append({"role": "user", "content": user_question})
        ai_response = ask_gatekeeper_ai(menu_selection, st.session_state.messages, metrics, demo_on)
        st.session_state.messages.append({"role": "assistant", "content": ai_response})
        st.rerun()

    st.sidebar.markdown("</div>", unsafe_allow_html=True)


def show_dashboard(demo_on):
    if demo_on:
        metrics, chart_df = get_demo_financial_snapshot()
    else:
        metrics, chart_df = get_financial_metrics()

    revenue_delta = "Good" if metrics["revenue"] >= metrics["payables"] else "Needs Attention"
    payables_delta = "Needs Attention" if metrics["payables"] > metrics["revenue"] else "Good"
    health_delta = "Good" if metrics["net_health"] >= 0 else "Needs Attention"

    st.header("Financial Health Command Center")
    with st.container():
        col1, col2, col3 = st.columns([1, 1, 1])
        col1.metric("Total Revenue", format_money(metrics["revenue"]), revenue_delta)
        col2.metric("Outstanding Payables", format_money(metrics["payables"]), payables_delta, delta_color="inverse")
        col3.metric("Net Financial Health", format_money(metrics["net_health"]), health_delta)
        if not metrics["has_data"] and not demo_on:
            st.caption("Add your first invoice to see health metrics.")

    st.bar_chart(chart_df)
    return metrics


def main():
    st.set_page_config(page_title="Gatekeeper Finance", layout="wide", initial_sidebar_state="expanded")
    inject_css()

    if "clean_bootstrap_done" not in st.session_state:
        init_db()
        st.session_state.clean_bootstrap_done = True

    st.sidebar.title("Gatekeeper")
    demo_on = st.sidebar.toggle("Enterprise Demo Mode")

    if st.sidebar.button("Reset To Clean State", width="stretch"):
        reset_to_clean_state()
        st.success("Database reset to clean state.")
        st.rerun()

    menu_selection = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "Sales Invoices", "Accounts Payable", "Chart of Accounts", "Vouchers"],
    )

    if menu_selection == "Dashboard":
        metrics = show_dashboard(demo_on)
    else:
        metrics = get_demo_financial_snapshot()[0] if demo_on else get_financial_metrics()[0]
        conn = None if demo_on else get_connection()
        try:
            if menu_selection == "Sales Invoices":
                show_sales_invoices_page(conn, demo_on)
            elif menu_selection == "Accounts Payable":
                show_accounts_payable_page(conn, demo_on)
            elif menu_selection == "Chart of Accounts":
                show_chart_of_accounts_page(conn, demo_on)
            elif menu_selection == "Vouchers":
                show_vouchers_page(conn, demo_on)
        finally:
            if conn:
                conn.close()

    render_sidebar_chat(menu_selection, demo_on, metrics)


if __name__ == "__main__":
    main()
