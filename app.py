import streamlit as st
import datetime
import requests

# --- PAYSTACK & BUSINESS CONFIG ---
PAYSTACK_PUBLIC_KEY = "pk_test_187173o2e1df8ea7dc68c6163" # From your screenshot
ADMIN_EMAIL = "kwakache@gmail.com"
HELPLINE = "+233546044673"
PRICE_MONTHLY = 200
PRICE_YEARLY = 1800

def subscription_gate():
    # In a full Level 3 version, we will store this in a database. 
    # For now, this is your Manual Gatekeeper.
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
            
            # This is a placeholder for the Paystack JS Trigger
            if st.button(f"Proceed to Secure Payment ({amount} GHS)"):
                st.write(f"Redirecting to Paystack... (Please pay to E.K.A Financial Consultancy)")
                st.success(f"Once paid, send a screenshot to {HELPLINE} to receive your Key.")

        with tab2:
            st.subheader("Activate License")
            key = st.text_input("Enter the 8-digit key sent to your email", type="password")
            if st.button("Unlock ERP"):
                # SECRET KEY LOGIC: You can change this '2026' key whenever you want
                if key == "KAY-PRO-2026": 
                    st.session_state['authenticated'] = True
                    st.rerun()
                else:
                    st.error("Invalid Key. Please contact the helpline.")
        
        st.divider()
        st.markdown(f"**Support:** {HELPLINE} | {ADMIN_EMAIL}")
        st.stop() # Stops the ERP from loading below

# --- EXECUTE GATEKEEPER ---
subscription_gate()

# ... YOUR EXISTING ERP CODE STARTS HERE ...