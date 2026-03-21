import os
import sqlite3
from datetime import datetime

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
    "businesses and use the current dashboard figures when asked about financial health."
)
USER_ROLES = ["Master Admin", "Client"]


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
    return f"GH₵ {value:,.2f}"


def get_real_financial_metrics():
    conn = get_connection()
    try:
        revenue = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM sales_invoices WHERE status = 'Paid'"
        ).fetchone()[0] or 0.0
        payables = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM accounts_payable WHERE status = 'Unpaid'"
        ).fetchone()[0] or 0.0
        has_data = (
            (conn.execute("SELECT COUNT(*) FROM sales_invoices").fetchone()[0] or 0)
            + (conn.execute("SELECT COUNT(*) FROM accounts_payable").fetchone()[0] or 0)
        ) > 0
    finally:
        conn.close()

    metrics = {
        "revenue": float(revenue),
        "payables": float(payables),
        "net_health": float(revenue) - float(payables),
        "has_data": has_data,
    }
    chart_df = pd.DataFrame(
        {"Amount": [metrics["revenue"], metrics["payables"]]},
        index=["Income", "Expenses"],
    )
    return metrics, chart_df


def get_demo_financial_metrics():
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


def get_ai_client():
    return Groq(api_key=st.secrets["GROQ_API_KEY"])


def ask_gatekeeper_ai(menu_name, chat_history, metrics, demo_on):
    context = (
        f"Dashboard snapshot: Revenue {format_money(metrics['revenue'])}, "
        f"Payables {format_money(metrics['payables'])}, "
        f"Net Health {format_money(metrics['net_health'])}. "
        f"Demo mode is {'ON' if demo_on else 'OFF'}."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Current page: {menu_name}. {context}"},
    ]
    messages.extend(chat_history[-8:])

    try:
        client = get_ai_client()
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
            border: 1px solid #e6edf5;
            border-radius: 16px;
            padding: 15px;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
        }
        .sidebar-chat-shell {
            position: sticky;
            bottom: 0;
            padding-top: 0.75rem;
            border-top: 1px solid #e5e7eb;
            background: linear-gradient(180deg, rgba(255,255,255,0.96), #ffffff);
        }
        .logout-wrap button {
            background: #b91c1c !important;
            color: white !important;
            border: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def ensure_session_state():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'current_user' not in st.session_state:
        st.session_state.current_user = {"name": "", "role": "Client"}


def render_login_gate():
    st.markdown("## Gatekeeper Login")
    st.caption("Sign in to access the finance command center.")

    with st.form("gatekeeper_login_form"):
        username = st.text_input("Username")
        role = st.selectbox("Role", USER_ROLES)
        submitted = st.form_submit_button("Login")

        if submitted:
            display_name = username.strip() or role
            st.session_state.logged_in = True
            st.session_state.current_user = {"name": display_name, "role": role}
            st.rerun()


def render_sidebar(current_page):
    user = st.session_state.current_user
    st.sidebar.title("Gatekeeper")
    st.sidebar.markdown(
        f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:14px;margin-bottom:12px;">
            <div style="font-size:12px;color:#64748b;">Current User</div>
            <div style="font-size:18px;font-weight:700;color:#0f172a;">{user['name']}</div>
            <div style="font-size:13px;color:#334155;">Role: {user['role']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    demo_on = st.sidebar.toggle("Enterprise Demo Mode")

    if user["role"] == "Master Admin":
        if st.sidebar.button("Reset Clean Database", width="stretch"):
            reset_to_clean_state()
            st.success("Database reset complete.")
            st.rerun()

    page = st.sidebar.radio(
        "Module Navigation",
        ["Dashboard", "Sales Invoices", "Accounts Payable", "Chart of Accounts", "Vouchers"],
        index=["Dashboard", "Sales Invoices", "Accounts Payable", "Chart of Accounts", "Vouchers"].index(current_page)
        if current_page in ["Dashboard", "Sales Invoices", "Accounts Payable", "Chart of Accounts", "Vouchers"]
        else 0,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown('<div class="logout-wrap">', unsafe_allow_html=True)
    logout = st.sidebar.button("Secure Logout", width="stretch")
    st.sidebar.markdown("</div>", unsafe_allow_html=True)
    if logout:
        st.session_state.clear()
        st.rerun()

    return demo_on, page


def render_financial_dashboard(metrics, chart_df):
    revenue_delta = "Healthy" if metrics["revenue"] >= metrics["payables"] else "Watch"
    payables_delta = "Controlled" if metrics["payables"] <= metrics["revenue"] else "High"
    health_delta = "Good" if metrics["net_health"] >= 0 else "Needs Attention"

    st.header("Financial Health Command Center")
    with st.container():
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Revenue", format_money(metrics["revenue"]), revenue_delta)
        col2.metric("Outstanding Payables", format_money(metrics["payables"]), payables_delta, delta_color="inverse")
        col3.metric("Net Health", format_money(metrics["net_health"]), health_delta)
        if not metrics["has_data"]:
            st.caption("Add your first invoice to see health metrics.")

    st.bar_chart(chart_df)


def render_sidebar_chat(menu_name, demo_on, metrics):
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Ask about your financial health, chart of accounts, payables, or invoices.",
            }
        ]

    st.sidebar.markdown('<div class="sidebar-chat-shell">', unsafe_allow_html=True)
    st.sidebar.markdown("### Gatekeeper AI")
    st.sidebar.caption(f"Current view: {menu_name}")

    for message in st.session_state.messages[-6:]:
        with st.sidebar:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    question = st.sidebar.chat_input("Ask Gatekeeper AI...")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        answer = ask_gatekeeper_ai(menu_name, st.session_state.messages, metrics, demo_on)
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()

    st.sidebar.markdown("</div>", unsafe_allow_html=True)


def main():
    st.set_page_config(page_title="Gatekeeper Finance", layout="wide", initial_sidebar_state="expanded")
    inject_css()
    ensure_session_state()
    init_db()
    if not st.session_state.logged_in:
        render_login_gate()
        return

    demo_on, page = render_sidebar("Dashboard")

    if demo_on:
        metrics, chart_df = get_demo_financial_metrics()
    else:
        metrics, chart_df = get_real_financial_metrics()

    if page == "Dashboard":
        render_financial_dashboard(metrics, chart_df)
    else:
        conn = None if demo_on else get_connection()
        try:
            if page == "Sales Invoices":
                show_sales_invoices_page(conn, demo_on)
            elif page == "Accounts Payable":
                show_accounts_payable_page(conn, demo_on)
            elif page == "Chart of Accounts":
                show_chart_of_accounts_page(conn, demo_on)
            elif page == "Vouchers":
                show_vouchers_page(conn, demo_on)
        finally:
            if conn:
                conn.close()

    render_sidebar_chat(page, demo_on, metrics)


if __name__ == "__main__":
    main()
