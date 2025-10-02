import streamlit as st
import pandas as pd
from relatorios import gerar_simplicado

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("Desempenho do Entregador — Simplificada (WhatsApp)")
    nomes = sorted(df["pessoa_entregadora"].dropna().unique())
    with st.form("simp"):
        nome = st.selectbox("🔎 Entregador:", [None] + nomes, format_func=lambda x: "" if x is None else x)
        col1, col2 = st.columns(2)
        mes1 = col1.selectbox("1º Mês:", list(range(1, 13)))
        ano1 = col2.selectbox("1º Ano:", sorted(df["ano"].unique(), reverse=True))
        mes2 = col1.selectbox("2º Mês:", list(range(1, 13)))
        ano2 = col2.selectbox("2º Ano:", sorted(df["ano"].unique(), reverse=True))
        gerar = st.form_submit_button("Gerar")
    if gerar and nome:
        t1 = gerar_simplicado(nome, mes1, ano1, df)
        t2 = gerar_simplicado(nome, mes2, ano2, df)
        st.text_area("Resultado:", value="\n\n".join([t for t in [t1, t2] if t]), height=600)
