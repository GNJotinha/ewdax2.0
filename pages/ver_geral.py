import streamlit as st
import pandas as pd
from relatorios import gerar_dados

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("Desempenho do Entregador — Ver geral")
    nomes = sorted(df["pessoa_entregadora"].dropna().unique())
    nome = st.selectbox("🔎 Selecione o entregador:", [None] + nomes, format_func=lambda x: "" if x is None else x)
    if st.button("Gerar relatório", disabled=not bool(nome), use_container_width=True):
        if not nome:
            st.warning("Selecione um entregador.")
            return
        texto = gerar_dados(nome, None, None, df[df['pessoa_entregadora']==nome])
        st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=400)
