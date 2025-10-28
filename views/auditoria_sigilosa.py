# --- Área Sigilosa no menu esquerdo (apenas admin/dev) ---
admins_list = set(st.secrets.get("ADMINS", []))
user_entry = USUARIOS.get(st.session_state.usuario, {}) or {}
nivel = user_entry.get("nivel", "")
is_sigiloso = (nivel in ("admin", "dev")) or (st.session_state.usuario in admins_list)

if is_sigiloso:
    with st.expander("🔒 Área Sigilosa", expanded=True):
        if st.button("Auditoria — Lista por entregador", use_container_width=True):
            st.session_state.module = "views.auditoria_sigilosa"
            st.session_state.sig_modo = "by_entregador"
            st.session_state.open_cat = None
            st.rerun()

        if st.button("Auditoria — Lista geral", use_container_width=True):
            st.session_state.module = "views.auditoria_sigilosa"
            st.session_state.sig_modo = "geral"
            st.session_state.open_cat = None
            st.rerun()
