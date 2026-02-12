import streamlit as st
import pandas as pd
from relatorios import gerar_dados


def render(df: pd.DataFrame, _USUARIOS: dict):

    st.markdown("## Perfil — Ver geral")

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    nomes = sorted(df["pessoa_entregadora"].dropna().unique())

    with st.container(border=True):
        nome = st.selectbox(
            "Selecione o entregador:",
            [None] + nomes,
            format_func=lambda x: "" if x is None else x
        )

    gerar = st.button(
        "Gerar relatório",
        disabled=not bool(nome),
        use_container_width=True
    )

    if not gerar:
        return

    if not nome:
        st.warning("Selecione um entregador.")
        return

    texto = gerar_dados(
        nome,
        None,
        None,
        df[df["pessoa_entregadora"] == nome]
    )

    st.markdown("### Resultado")

    st.markdown(
        f"""
        <div style="
            background-color:#111827;
            padding:1.5rem;
            border-radius:14px;
            border:1px solid #1f2937;
            font-size:0.95rem;
            line-height:1.6;
            white-space:pre-wrap;
            font-family:monospace;
        ">
        {texto or "Nenhum dado encontrado"}
        </div>
        """,
        unsafe_allow_html=True
    )
