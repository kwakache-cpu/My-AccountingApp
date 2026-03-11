import streamlit as st
import pandas as pd
import requests

# --- 1. SETTINGS & CONFIGURATION ---
ADMIN_EMAIL = "kwakache@gmail.com"
HELPLINE_WHATSAPP = "+233546044673"
HELPLINE_CALL = "+233507017767"

# --- 2. THE GATEKEEPER ---
def check_access():
    if 'authorized' not in st.session_state:
        st.session_state['authorized'] = False

    if not st.session_state['authorized']:
        st.title("🛡️ Tally Pro - Access Portal")
        st.warning("Subscription required to access E.K.A Financial ERP.")
        
        tab1, tab2 = st.tabs(["💳 Get Access", "🔑 Enter License Key"])
        
        with tab1:
            st.subheader("Select a Plan")
            st.write("• Monthly: 200 GHS")
            st.write("• Yearly: 1,800 GHS")
            if st.button("Proceed to Payment"):
                st.info(f"Please WhatsApp a screenshot of your payment to {HELPLINE_WHATSAPP}")
        
        with tab2:
            st.subheader("Activate System")
            key = st.text_input("License Key", type="password")
            if st.button("Unlock Dashboard"):
                if key == "KAY-PRO-2026":
                    st.session_state['authorized'] = True
                    st.rerun()
                else:
                    st.error("Invalid Key. Check your spelling or contact support.")
        
        st.divider()
        st.markdown(f"**WhatsApp Support (Only):** {HELPLINE_WHATSAPP}")
        st.markdown(f"**Call Support:** {HELPLINE_CALL} | **Email:** {ADMIN_EMAIL}")
        st.stop()

# Run the gate
check_access()

# --- 3. THE ERP DASHBOARD (Only visible after unlocking) ---
st.set_page_config(page_title="Tally Pro ERP", layout="wide")

# Sidebar Navigation
st.sidebar.title("Tally Pro Menu")
menu = st.sidebar.selectbox("Go to:", ["📊 Dashboard", "📈 Stock Watchlist", "⚙️ Settings"])

if menu == "📊 Dashboard":
    st.title("📊 Tally Pro ERP Dashboard")
    st.success("Welcome back, Emmanuel. System is fully active.")

    # Company Configuration Section
    with st.expander("🏢 Company Configuration", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Company Name", value="E.K.A Financial Consultancy")
        with col2:
            tin = st.text_input("TIN Number", placeholder="e.g. P000784560X")
        
        # THE MISSING SUBMIT BUTTON
        if st.button("💾 Save & Initialize Dashboard"):
            st.toast(f"Configuration for {name} Saved!")
            st.balloons()

    # Financial Metrics
    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Revenue", "0.00 GHS", "0%")
    m2.metric("Expenses", "0.00 GHS", "0%")
    m3.metric("Net Profit", "0.00 GHS", "0%")

elif menu == "📈 Stock Watchlist":
    st.title("📈 Ghana Stock Watchlist")
    st.info("Monitoring SIC, CAL, and MTNGH for 'Best Buy' opportunities.")
    
    # Custom Table for your specific stocks
    stock_data = {
        "Ticker": ["MTNGH", "CAL", "SIC"],
        "Last Price (GHS)": [2.15, 0.48, 0.25],
        "Market Sentiment": ["Bullish", "Neutral", "Waiting"]
    }
    df = pd.DataFrame(stock_data)
    st.table(df)
    st.caption("Last updated: Wednesday Market Close")

elif menu == "⚙️ Settings":
    st.title("⚙️ System Settings")
    st.write(f"**Administrator:** {ADMIN_EMAIL}")
    if st.button("Log Out"):
        st.session_state['authorized'] = False
        st.rerun()