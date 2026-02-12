import streamlit as st
import pandas as pd


def _goto(module: str, cat=None):
    st.session_state.module = module
    st.session_state.open_cat = cat
    st.rerun()


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.markdown(
        """
        <div class="home-hero">
          <div class="home-title">Bem-vindo</div>
          <div class="home-sub">Escolhe uma opção no menu lateral ou usa os atalhos abaixo.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='neo-divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='neo-section'>Atalhos</div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Ver geral", use_container_width=True, key="home_short_vergeral"):
            _goto("views.ver_geral", "Desempenho do Entregador")

    with c2:
        if st.button("Simplificada (WhatsApp)", use_container_width=True, key="home_short_simpl"):
            _goto("views.simplificada", "Desempenho do Entregador")

    with c3:
        if st.button("Indicadores Gerais", use_container_width=True, key="home_short_indic"):
            _goto("views.indicadores", "Dashboards")

    st.caption(f"Login: {st.session_state.get('usuario','-')} • Departamento: {st.session_state.get('department','-')}")
