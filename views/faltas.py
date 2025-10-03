# views/faltas.py — robusto e rápido
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("⚠️ Entregadores com 3+ faltas consecutivas (rápido)")

    # ------ Pré-checagens mínimas ------
    if "pessoa_entregadora_normalizado" not in df.columns:
        st.error("Coluna 'pessoa_entregadora_normalizado' ausente na base.")
        return
    if "pessoa_entregadora" not in df.columns:
        st.warning("Coluna 'pessoa_entregadora' ausente; vou exibir o nome normalizado.")
    tem_nome_original = "pessoa_entregadora" in df.columns

    # ------ Normaliza data para 'data' (tipo date) ------
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

    # ------ Janela e critérios ------
    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)
    corte_60d = hoje - timedelta(days=60)  # janela suficiente pro alerta
    corte_15d = hoje - timedelta(days=15)  # critério de "ativo" recente

    df_janela = df[df["data"] >= corte_60d].copy()
    if df_janela.empty:
        st.success("✅ Nada na janela dos últimos 60 dias.")
        return

    # Quem é "ativo" (teve presença nos últimos 15 dias)
    ativos_norm = (
        df_janela.loc[df_janela["data"] >= corte_15d, "pessoa_entregadora_normalizado"]
        .dropna()
        .unique()
        .tolist()
    )
    if not ativos_norm:
        st.success("✅ Nenhum entregador ativo nos últimos 15 dias.")
        return

    # ------ Última presença por entregador (sem ['data'].max()) ------
    ultimas = (
        df_janela
        .groupby("pessoa_entregadora_normalizado", dropna=True, as_index=False)
        .agg(ultima_presenca=("data", "max"))
    )

    # Para recuperar o nome “bonito”, cria coluna datetime e usa idxmax no PRÓPRIO índice
    df_janela["data_dt"] = pd.to_datetime(df_janela["data"], errors="coerce")
    base_idx = (
        df_janela.dropna(subset=["pessoa_entregadora_normalizado", "data_dt"])
                 .groupby("pessoa_entregadora_normalizado")["data_dt"]
                 .idxmax()
    )

    if tem_nome_original:
        nomes_rec = df_janela.loc[base_idx, ["pessoa_entregadora_normalizado", "pessoa_entregadora"]]
        ultimas = ultimas.merge(nomes_rec, on="pessoa_entregadora_normalizado", how="left")

    # Mantém apenas ativos
    ultimas = ultimas[ultimas["pessoa_entregadora_normalizado"].isin(ativos_norm)].copy()
    if ultimas.empty:
        st.success("✅ Nenhum entregador ativo com presenças na janela de 60 dias.")
        return

    # ------ Streak de faltas até ontem ------
    ultimas["dias_ausentes"] = (
        pd.to_datetime(ontem) - pd.to_datetime(ultimas["ultima_presenca"])
    ).dt.days

    # Alerta: 4+ dias consecutivos ausente
    alertas = (
        ultimas[ultimas["dias_ausentes"] >= 4]
        .copy()
        .sort_values("dias_ausentes", ascending=False)
    )

    if alertas.empty:
        st.success("✅ Nenhum entregador ativo com 4+ dias consecutivos ausente.")
        return

    alertas["ultima_presenca_fmt"] = pd.to_datetime(alertas["ultima_presenca"]).dt.strftime("%d/%m")
    if tem_nome_original:
        alertas["nome_exibir"] = alertas["pessoa_entregadora"].fillna(alertas["pessoa_entregadora_normalizado"])
    else:
        alertas["nome_exibir"] = alertas["pessoa_entregadora_normalizado"]

    # ------ Saídas ------
    linhas = [
        f"• {row['nome_exibir']} – {int(row['dias_ausentes'])} dias consecutivos ausente (última presença: {row['ultima_presenca_fmt']})"
        for _, row in alertas.iterrows()
    ]
    st.text_area("Resultado (texto):", value="\n".join(linhas), height=320)

    tabela = (
        alertas[["nome_exibir", "dias_ausentes", "ultima_presenca"]]
        .rename(columns={
            "nome_exibir": "Entregador",
            "dias_ausentes": "Dias ausente (consecutivos)",
            "ultima_presenca": "Última presença"
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
