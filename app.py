import streamlit as st
import datetime
import pandas as pd
import requests

# --- PAYSTACK & BUSINESS CONFIG ---
PAYSTACK_PUBLIC_KEY = "pk_test_187173o2e1df8ea7dc68c6163" 
ADMIN_EMAIL = "kwakache@gmail.com"
HELPLINE_WHATSAPP = "+233546044673"
HELPLINE_CALL = "+233507017767"
PRICE_MONTHLY = 200
PRICE_YEARLY = 1800

def subscription_gate():
    # Session state keeps the user logged in while the browser tab is open
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False

    if not st.session_state['authenticated']:
        st.title("🛡️ Tally Pro ERP - Access Portal")
        st.warning("Your subscription has expired or you are a new user.")
        
        tab1, tab2 = st.tabs(["💳 Pay Now", "🔑 Enter License Key"])
        
        with tab1:
            st.subheader("Select Your Plan")
            plan = st.radio("Choose Duration", [f"Monthly - {PRICE_MONTHLY} GHS", f"Yearly - {PRICE_YEARLY} GHS"])
            amount = PRICE_MONTHLY if "Monthly" in plan else PRICE_YEARLY
            
            st.info(f"**Payment Methods:** MoMo, Visa, Mastercard (USD/GBP/GHS accepted)")
            
            if st.button(f"Proceed to Secure Payment ({amount} GHS)"):
                st.write(f"Redirecting to Paystack... (Please pay to E.K.A Financial Consultancy)")
                st.success(f"Once paid, WhatsApp a screenshot to {HELPLINE_WHATSAPP} to receive your Key.")

        with tab2:
            st.subheader("Activate License")
            key = st.text_input("Enter the 8-digit key sent to your email", type="password")
            if st.button("Unlock ERP"):
                # MASTER KEY
                if key == "KAY-PRO-2026": 
                    st.session_state['authenticated'] = True
                    st.rerun()
                else:
                    st.error("Invalid Key. Please contact support.")
        
        st.divider()
        st.markdown(f"**WhatsApp Support (Only):** {HELPLINE_WHATSAPP}")
        st.markdown(f"**Call Support:** {HELPLINE_CALL} | **Email:** {ADMIN_EMAIL}")
        st.stop() # This locks the app until authenticated is True

# --- EXECUTE THE GATEKEEPER ---
subscription_gate()

# ==========================================
# YOUR EXISTING ERP CODE STARTS BELOW THIS LINE
# ==========================================

st.title("📊 Tally Pro ERP Dashboard")
st.write("Welcome back, Emmanuel. Your system is fully active.")

# Example Placeholder for your ERP content
with st.expander("Company Configuration"):
    st.text_input("Company Name", value="E.K.A Financial Consultancy")
    st.text_input("TIN Number")