import streamlit as st
import pandas as pd

# --- 1. CLIENT LICENSE DATABASE ---
# When a client pays, add their 'Key' and 'Company Name' here.
# Each key is unique to that specific business.
CLIENT_REGISTRY = {
    "KAY-PRO-2026": "E.K.A Financial Consultancy",
    "GHS-RETAIL-77": "Accra Market Square Ltd",
    "LOG-PRO-441": "Speedway Logistics Ghana",
    "MOMO-VEND-99": "Daily Cash Services"
}

# --- 2. CONFIGURATION ---
ADMIN_EMAIL = "kwakache@gmail.com"
HELPLINE_WHATSAPP = "+233546044673"
HELPLINE_CALL = "+233507017767"

# --- 3. THE SECURITY GATEKEEPER ---
def check_access():
    if 'authorized' not in st.session_state:
        st.session_state['authorized'] = False
        st.session_state['client_name'] = ""

    if not st.session_state['authorized']:
        # NEW NAME: E.K.A Cloud Accounting
        st.title("🛡️ E.K.A Cloud Accounting - Access Portal")
        st.warning("Please enter your business license key to unlock your dashboard.")
        
        tab1, tab2 = st.tabs(["💳 Get Access", "🔑 Unlock System"])
        
        with tab1:
            st.subheader("Subscription Plans")
            st.write("• Monthly: 200 GHS | • Yearly: 1,800 GHS")
            if st.button("Request New Access"):
                st.info(f"WhatsApp your business name to {HELPLINE_WHATSAPP}")
        
        with tab2:
            st.subheader("Client Login")
            entered_key = st.text_input("License Key", type="password")
            if st.button("Unlock Dashboard"):
                # Check if the key exists in our registry
                if entered_key in CLIENT_REGISTRY:
                    st.session_state['authorized'] = True
                    # This tells the app which company name to display
                    st.session_state['client_name'] = CLIENT_REGISTRY[entered_key]
                    st.rerun()
                else:
                    st.error("Invalid Key. Check your spelling or WhatsApp support.")
        
        st.divider()
        st.markdown(f"**WhatsApp Support (Only):** {HELPLINE_WHATSAPP}")
        st.markdown(f"**Call Support:** {HELPLINE_CALL} | **Email:** {ADMIN_EMAIL}")
        st.stop()

# Run the gate
check_access()

# --- 4. THE ERP DASHBOARD (Only visible after unlocking) ---
st.set_page_config(page_title="E.K.A Cloud Accounting", layout="wide")

# Sidebar - Branded to the specific client
st.sidebar.title(f"🏢 {st.session_state['client_name']}")
menu = st.sidebar.selectbox("Main Menu", ["📊 Dashboard", "⚙️ Settings"])

if menu == "📊 Dashboard":
    st.title(f"📊 Dashboard: {st.session_state['client_name']}")
    st.success(f"Verified Access: {st.session_state['client_name']}")

    # Business Profile Section
    with st.expander("🏢 Business Configuration", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            # Displays the name based on the key they used
            st.text_input("Business Name", value=st.session_state['client_name'], disabled=True)
        with col2:
            st.text_input("TIN Number", placeholder="e.g. P000784560X")
        
        if st.button("💾 Save Profile Settings"):
            st.toast("Settings Saved!")
            st.balloons()

    # Accounting Metrics
    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Revenue", "0.00 GHS")
    m2.metric("Expenses", "0.00 GHS")
    m3.metric("Net Profit", "0.00 GHS")

elif menu == "⚙️ Settings":
    st.title("⚙️ System Settings")
    st.write(f"Logged in as: **{st.session_state['client_name']}**")
    if st.button("Log Out"):
        st.session_state['authorized'] = False
        st.rerun()