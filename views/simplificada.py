import streamlit as st
import pandas as pd
from relatorios import gerar_simplicado


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("Desempenho do Entregador — Simplificada (WhatsApp)")

    # lista de entregadores
    nomes = sorted(df["pessoa_entregadora"].dropna().unique())

    with st.form("simp"):
        # seleção de entregador
        nome = st.selectbox(
            "🔎 Entregador:",
            [None] + nomes,
            format_func=lambda x: "" if x is None else x
        )

        col1, col2 = st.columns(2)

        # primeiro mês/ano
        mes1 = col1.selectbox("1º Mês:", list(range(1, 13)), index=0)
        ano1 = col2.selectbox("1º Ano:", sorted(df["ano"].unique(), reverse=True))

        # segundo mês/ano
        mes2 = col1.selectbox("2º Mês:", list(range(1, 13)), index=1)
        ano2 = col2.selectbox("2º Ano:", sorted(df["ano"].unique(), reverse=True))

        gerar = st.form_submit_button("Gerar", use_container_width=True)

    if not (gerar and nome):
        return

    # gera blocos por mês (sem repetir o nome dentro do texto)
    t1 = gerar_simplicado(nome, mes1, ano1, df)
    t2 = gerar_simplicado(nome, mes2, ano2, df)

    blocos = [t for t in [t1, t2] if t]

    # montagem final:
    # *Nome*
    #
    # *Mês1*...
    #
    # *Mês2*...
    if blocos:
        corpo = "\n\n".join(blocos)  # quebra em branco só ENTRE meses
        saida = f"*{nome}*\n\n{corpo}"
    else:
        saida = f"*{nome}*\n\nSem dados para os meses selecionados."

    st.text_area("Resultado:", value=saida.strip(), height=600)
