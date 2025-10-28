# views/auditoria_gate.py
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import streamlit as st

TZ = ZoneInfo("America/Sao_Paulo")

def _senha_por_formula(palavra_base: str) -> str:
    # padrão: PALAVRA@(dia*mes)
    hoje = date.today()
    return f"{str(palavra_base).strip()}@{hoje.day * hoje.month}"

def _ts_now():
    return datetime.now(TZ)

def render(_df_unused, _USUARIOS):
    st.header("🔒 Área Sigilosa")
    st.subheader("Acesso restrito")

    palavra = st.secrets.get("SIGILOSO_PALAVRA", "Movee")
    ttl_min_default = int(st.secrets.get("SIGILOSO_TTL_MIN", 60))  # padrão 60 min

    senha = st.text_input("Senha", type="password")

    st.markdown("**Validade do acesso**")
    modo_valid = st.radio(
        "Escolha a validade:",
        ["1 hora (recomendado)", "Somente nesta sessão (expira ao recarregar/logoff)"],
        index=0
    )

    col1, col2 = st.columns([1,1])
    go = col1.button("Validar", type="primary", use_container_width=True)
    back = col2.button("Cancelar", use_container_width=True)

    if back:
        st.session_state.module = "views.home"
        st.rerun()

    if go:
        esperada = _senha_por_formula(palavra)
        if senha and senha.strip() == esperada:
            now = _ts_now()
            st.session_state["_sig_ok"] = True
            st.session_state["_sig_issued_at"] = now.isoformat()

            if modo_valid == "1 hora (recomendado)":
                ttl = int(ttl_min_default)
                st.session_state["_sig_until"] = (now + timedelta(minutes=ttl)).isoformat()
                st.session_state["_sig_session_only"] = False
            else:
                # expira ao fechar/reiniciar a sessão (sem timestamp)
                st.session_state["_sig_until"] = None
                st.session_state["_sig_session_only"] = True

            # para onde ir após validar?
            destino = st.session_state.get("sig_target", "by_entregador")
            st.session_state.module = "views.auditoria_sigilosa"
            st.session_state.sig_modo = destino
            st.success("Acesso liberado.")
            st.rerun()
        else:
            st.error("Senha incorreta.")
