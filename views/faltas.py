import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("⚠️ Entregadores com 3+ faltas consecutivas")
    hoje = datetime.now().date()
    ultimos_15_dias = hoje - timedelta(days=15)
    df["data"] = pd.to_datetime(df["data"]).dt.date

    ativos = df[df["data"] >= ultimos_15_dias]["pessoa_entregadora_normalizado"].unique()
    mensagens = []
    for nome in ativos:
        entregador = df[df["pessoa_entregadora_normalizado"] == nome]
        if entregador.empty:
            continue
        dias = pd.date_range(end=hoje - timedelta(days=1), periods=30).date
        presencas = set(entregador["data"])
        seq = 0
        for dia in sorted(dias):
            seq = 0 if dia in presencas else seq + 1
        if seq >= 4:
            nome_original = entregador["pessoa_entregadora"].iloc[0]
            mensagens.append(f"• {nome_original} – {seq} dias consecutivos ausente (última presença: {max(presencas).strftime('%d/%m') if presencas else '—'})")

    if mensagens:
        st.text_area("Resultado:", value="\n".join(mensagens), height=400)
    else:
        st.success("✅ Nenhum entregador ativo com faltas consecutivas.")
