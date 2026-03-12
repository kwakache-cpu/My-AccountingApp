def login_ui():
    st.title("🛡️ E.K.A Cloud Accounting")
    t1, t2 = st.tabs(["Login", "Forgot Password"])
    with t1:
        key_in = st.text_input("License Key", type="password")
        if st.button("Unlock"):
            # RESTORE DEVELOPER ACCESS: This must be the first check
            if key_in == "JUANMANUEL2":
                st.session_state.auth = True
                st.session_state.user = {"name": "Developer", "role": "Dev", "key": "ADMIN"}
                st.rerun()
            
            conn = get_connection()
            # 1. Master Admin Check
            res = conn.execute("SELECT key, name FROM companies WHERE key=?", (key_in,)).fetchone()
            if res:
                st.session_state.auth, st.session_state.user = True, {"key": res[0], "name": res[1], "role": "Master Admin"}
                st.rerun()
                
            # 2. Sub-Admin Check
            res_s = conn.execute("SELECT key, name FROM companies WHERE sub_admin_key=?", (key_in,)).fetchone()
            if res_s:
                st.session_state.auth, st.session_state.user = True, {"key": res_s[0], "name": res_s[1], "role": "Sub-Admin"}
                st.rerun()
                
            # 3. Staff Check
            if key_in.endswith("-staff"):
                k = key_in.replace("-staff", "")
                res_st = conn.execute("SELECT key, name FROM companies WHERE key=?", (k,)).fetchone()
                if res_st:
                    st.session_state.auth, st.session_state.user = True, {"key": res_st[0], "name": res_st[1], "role": "Staff"}
                    st.rerun()
            
            st.error("Access Denied. Please check your key or contact support.")