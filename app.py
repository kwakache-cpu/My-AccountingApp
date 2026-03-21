import os
from datetime import datetime

import streamlit as st
from dateutil.relativedelta import relativedelta
from groq import Groq

from modules import (
    DB_NAME,
    get_connection,
    get_system_health_snapshot,
    init_db,
    log_system_event,
    show_company_registration_module,
    show_license_renewal_module,
    show_system_health_module,
    show_vault_dashboard_module,
)


APP_TITLE = "EKA ERP | GATEKEEPER"
SYSTEM_PROMPT = (
    "You are the Gatekeeper ERP Assistant for EKA Vault Management. Help Master Admin and "
    "client users understand the vault dashboard, company onboarding, license renewal, and "
    "system health in simple business language."
)


def get_ai_client():
    return Groq(api_key=st.secrets["GROQ_API_KEY"])


def ensure_session_state():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user" not in st.session_state:
        st.session_state.user = {"name": "", "role": "Client"}
    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = [
            {
                "role": "assistant",
                "content": "Welcome to EKA ERP | GATEKEEPER. Ask about vault health, onboarding, or license renewal.",
            }
        ]


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
        .gatekeeper-hero {
            background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
            color: white;
            border-radius: 18px;
            padding: 1.2rem 1.4rem;
            margin-bottom: 1rem;
            box-shadow: 0 20px 40px rgba(15, 23, 42, 0.18);
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #dbe7f3;
            border-radius: 16px;
            padding: 15px;
            box-shadow: 0 10px 26px rgba(15, 23, 42, 0.08);
        }
        .sidebar-user-card {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 14px;
            margin-bottom: 12px;
        }
        .sidebar-chat-shell {
            position: sticky;
            bottom: 0;
            background: linear-gradient(180deg, rgba(255,255,255,0.96), #ffffff);
            border-top: 1px solid #e2e8f0;
            padding-top: 0.75rem;
            margin-top: 1rem;
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


def render_brand_header():
    st.markdown(
        f"""
        <div class="gatekeeper-hero">
            <div style="font-size:12px; letter-spacing:0.08em; opacity:0.85;">VAULT MANAGEMENT SYSTEM</div>
            <div style="font-size:28px; font-weight:800; margin-top:4px;">{APP_TITLE}</div>
            <div style="opacity:0.9; margin-top:6px;">
                Enterprise onboarding, licensing, vault visibility, and platform health in one command center.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_login_gate():
    render_brand_header()
    st.subheader("Gatekeeper Login")
    st.caption(f"Secure access to `{DB_NAME}`")

    with st.form("gatekeeper_login_form"):
        username = st.text_input("Username")
        role = st.selectbox("Role", ["Master Admin", "Client"])
        submitted = st.form_submit_button("Login")
        if submitted:
            display_name = username.strip() or role
            st.session_state.logged_in = True
            st.session_state.user = {"name": display_name, "role": role}
            log_system_event("INFO", "Authentication", f"User logged in as {role}: {display_name}")
            st.rerun()


def ask_gatekeeper_ai(active_module, health_snapshot):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                f"Active module: {active_module}. "
                f"Vault snapshot: API {health_snapshot['api_status']}, DB {health_snapshot['db_status']}, "
                f"companies {health_snapshot['company_count']}, active licenses {health_snapshot['active_licenses']}."
            ),
        },
    ]
    messages.extend(st.session_state.ai_messages[-8:])

    try:
        response = get_ai_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as error:
        return f"Gatekeeper AI is unavailable right now: {error}"


def render_sidebar(active_module, health_snapshot):
    user = st.session_state.user
    st.sidebar.title("EKA Gatekeeper")
    st.sidebar.markdown(
        f"""
        <div class="sidebar-user-card">
            <div style="font-size:12px; color:#64748b;">Current User</div>
            <div style="font-size:18px; font-weight:700; color:#0f172a;">{user['name']}</div>
            <div style="font-size:13px; color:#334155;">Role: {user['role']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    demo_on = st.sidebar.toggle("Enterprise Demo Mode")

    if user["role"] == "Master Admin":
        navigation = [
            "EKA Vault / Dashboard",
            "New Company Registration",
            "System Health & Logs",
            "Renew License",
            "Sales Invoices",
            "Accounts Payable",
            "Chart of Accounts",
            "Vouchers",
        ]
    else:
        navigation = [
            "EKA Vault / Dashboard",
            "System Health & Logs",
            "Sales Invoices",
            "Accounts Payable",
            "Chart of Accounts",
            "Vouchers",
        ]

    selected = st.sidebar.radio("Module Navigation", navigation, index=navigation.index(active_module) if active_module in navigation else 0)

    st.sidebar.markdown('<div class="sidebar-chat-shell">', unsafe_allow_html=True)
    st.sidebar.markdown("### Gatekeeper AI")
    st.sidebar.caption(f"Active module: {selected}")
    for message in st.session_state.ai_messages[-6:]:
        with st.sidebar:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    question = st.sidebar.chat_input("Ask Gatekeeper AI...")
    if question:
        st.session_state.ai_messages.append({"role": "user", "content": question})
        answer = ask_gatekeeper_ai(selected, health_snapshot)
        st.session_state.ai_messages.append({"role": "assistant", "content": answer})
        st.rerun()
    st.sidebar.markdown("</div>", unsafe_allow_html=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown('<div class="logout-wrap">', unsafe_allow_html=True)
    if st.sidebar.button("Secure Logout", width="stretch"):
        st.session_state.clear()
        st.rerun()
    st.sidebar.markdown("</div>", unsafe_allow_html=True)

    return demo_on, selected


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
    inject_css()
    ensure_session_state()
    init_db()

    if not st.session_state.logged_in:
        render_login_gate()
        return

    health_snapshot = get_system_health_snapshot()
    demo_on, active_module = render_sidebar("EKA Vault / Dashboard", health_snapshot)

    render_brand_header()

    if active_module == "EKA Vault / Dashboard":
        show_vault_dashboard_module(demo_on)
    elif active_module == "New Company Registration":
        show_company_registration_module()
    elif active_module == "System Health & Logs":
        show_system_health_module()
    elif active_module == "Renew License":
        show_license_renewal_module()
    elif active_module == "Sales Invoices":
        conn = None if demo_on else get_connection()
        try:
            show_sales_invoices_page(conn, demo_on)
        finally:
            if conn:
                conn.close()
    elif active_module == "Accounts Payable":
        conn = None if demo_on else get_connection()
        try:
            show_accounts_payable_page(conn, demo_on)
        finally:
            if conn:
                conn.close()
    elif active_module == "Chart of Accounts":
        conn = None if demo_on else get_connection()
        try:
            show_chart_of_accounts_page(conn, demo_on)
        finally:
            if conn:
                conn.close()
    elif active_module == "Vouchers":
        conn = None if demo_on else get_connection()
        try:
            show_vouchers_page(conn, demo_on)
        finally:
            if conn:
                conn.close()


if __name__ == "__main__":
    main()
