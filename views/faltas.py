# views/faltas.py — só tabela e download
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("⚠️ Entregadores com 3+ faltas consecutivas")

    # ------ Normaliza data ------
    df = df.copy()
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    elif "data_do_periodo" in df.columns:
        df["data"] = pd.to_datetime(df["data_do_periodo"], errors="coerce").dt.date
    else:
        st.error("Coluna de data ausente (espere 'data' ou 'data_do_periodo').")
        return
    df = df[df["data"].notna()]
    if df.empty:
        st.success("✅ Sem dados de presença/ausência.")
        return

    # ------ Datas ------
    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)
    corte_60d = hoje - timedelta(days=60)
    corte_15d = hoje - timedelta(days=15)

    df_janela = df[df["data"] >= corte_60d].copy()
    if df_janela.empty:
        st.success("✅ Nada na janela dos últimos 60 dias.")
        return

    # ------ Ativos (últimos 15 dias) ------
    ativos_norm = (
        df_janela.loc[df_janela["data"] >= corte_15d, "pessoa_entregadora_normalizado"]
        .dropna()
        .unique()
        .tolist()
    )
    if not ativos_norm:
        st.success("✅ Nenhum entregador ativo nos últimos 15 dias.")
        return

    # ------ Última presença por entregador ------
    ultimas = (
        df_janela
        .groupby("pessoa_entregadora_normalizado", dropna=True, as_index=False)
        .agg(ultima_presenca=("data", "max"))
    )

    df_janela["data_dt"] = pd.to_datetime(df_janela["data"], errors="coerce")
    base_idx = (
        df_janela.dropna(subset=["pessoa_entregadora_normalizado", "data_dt"])
                 .groupby("pessoa_entregadora_normalizado")["data_dt"]
                 .idxmax()
    )

    colunas_merge = ["pessoa_entregadora_normalizado"]
    if "pessoa_entregadora" in df_janela.columns:
        colunas_merge.append("pessoa_entregadora")
    nomes_rec = df_janela.loc[base_idx, colunas_merge]
    ultimas = ultimas.merge(nomes_rec, on="pessoa_entregadora_normalizado", how="left")

    ultimas = ultimas[ultimas["pessoa_entregadora_normalizado"].isin(ativos_norm)].copy()
    if ultimas.empty:
        st.success("✅ Nenhum entregador ativo com presenças na janela de 60 dias.")
        return

    # ------ Streak de faltas ------
    ultimas["dias_ausentes"] = (
        pd.to_datetime(ontem) - pd.to_datetime(ultimas["ultima_presenca"])
    ).dt.days
    alertas = ultimas[ultimas["dias_ausentes"] >= 4].copy().sort_values("dias_ausentes", ascending=False)

    if alertas.empty:
        st.success("✅ Nenhum entregador ativo com 4+ dias consecutivos ausente.")
        return

    alertas["ultima_presenca_fmt"] = pd.to_datetime(alertas["ultima_presenca"]).dt.strftime("%d/%m")
    if "pessoa_entregadora" in alertas.columns:
        alertas["Entregador"] = alertas["pessoa_entregadora"].fillna(alertas["pessoa_entregadora_normalizado"])
    else:
        alertas["Entregador"] = alertas["pessoa_entregadora_normalizado"]

    # ------ Só a tabela ------
    tabela = (
        alertas[["Entregador", "dias_ausentes", "ultima_presenca_fmt"]]
        .rename(columns={
            "dias_ausentes": "Dias ausente (consecutivos)",
            "ultima_presenca_fmt": "Última presença"
        })
        .reset_index(drop=True)
    )

    st.dataframe(tabela, use_container_width=True)
    st.download_button(
        "⬇️ Baixar CSV",
        data=tabela.to_csv(index=False).encode("utf-8"),
        file_name=f"alerta_faltas_{ontem.strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
