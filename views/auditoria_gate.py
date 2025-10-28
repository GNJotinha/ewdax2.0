# views/auditoria_gate.py
from datetime import date
import streamlit as st

def _senha_por_formula(palavra_base: str) -> str:
    # padrão: PALAVRA@(dia*mes)
    hoje = date.today()
    return f"{str(palavra_base).strip()}@{hoje.day * hoje.month}"

def render(_df_unused, _USUARIOS):
    st.header("🔒 Área Sigilosa")
    st.subheader("Acesso restrito")

    palavra = st.secrets.get("SIGILOSO_PALAVRA", "Movee")
    senha = st.text_input("Senha", type="password")

    col1, col2 = st.columns([1,1])
    go = col1.button("Validar", type="primary", use_container_width=True)
    back = col2.button("Cancelar", use_container_width=True)

    if back:
        st.session_state.module = "views.home"
        st.rerun()

    if go:
        esperada = _senha_por_formula(palavra)
        if senha and senha.strip() == esperada:
            # válido APENAS nesta sessão; se deslogar/fechar, perde
            st.session_state["_sig_ok"] = True
            destino = st.session_state.get("sig_target", "by_entregador")
            st.session_state.module = "views.auditoria_sigilosa"
            st.session_state.sig_modo = destino
            st.success("Acesso liberado.")
            st.rerun()
        else:
            st.error("Senha incorreta.")
