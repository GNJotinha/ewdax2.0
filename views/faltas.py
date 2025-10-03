# faltas.py (versão turbo)
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("⚠️ Entregadores com 3+ faltas consecutivas (rápido)")

    # --- Preparos e recortes (evita processar o histórico inteiro) ---
    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)
    corte_60d = hoje - timedelta(days=60)     # janela suficiente pro alerta
    corte_15d = hoje - timedelta(days=15)     # critério de "ativo" recente

    # datas como date (evita ficar convertendo depois)
    df = df.copy()
    df["data"] = pd.to_datetime(df.get("data"), errors="coerce").dt.date
    df = df[df["data"].notna()]
    if df.empty:
        st.success("✅ Sem dados de presença/ausência.")
        return

    # trabalha só com a janela necessária
    df_janela = df[df["data"] >= corte_60d].copy()
    if df_janela.empty:
        st.success("✅ Nada na janela dos últimos 60 dias.")
        return

    # --- Quem é considerado "ativo" (teve presença nos últimos 15 dias) ---
    ativos_norm = (
        df_janela.loc[df_janela["data"] >= corte_15d, "pessoa_entregadora_normalizado"]
        .dropna()
        .unique()
        .tolist()
    )
    if not ativos_norm:
        st.success("✅ Nenhum entregador ativo nos últimos 15 dias.")
        return

    # --- Última presença por entregador (vetorizado) ---
    # max(data) por pessoa_entregadora_normalizado
    grp = df_janela.groupby("pessoa_entregadora_normalizado", dropna=True, as_index=False)
    ultimas = grp["data"].max().rename(columns={"data": "ultima_presenca"})

    # pega um nome "bonito" pra exibir (o mais recente na janela)
    # truque: para cada normalizado, pega a linha com a maior data e usa o nome original
    idx_max_por_pessoa = (
        df_janela.reset_index()
                .sort_values("data")
                .groupby("pessoa_entregadora_normalizado", as_index=False)["data"]
                .idxmax()["data"]
                .values
                .tolist()
                if "pessoa_entregadora_normalizado" in df_janela.columns else []
    )
    if idx_max_por_pessoa:
        nomes_rec = df_janela.loc[idx_max_por_pessoa, ["pessoa_entregadora_normalizado","pessoa_entregadora"]]
        ultimas = ultimas.merge(nomes_rec, on="pessoa_entregadora_normalizado", how="left")

    # mantém só os ativos
    ultimas = ultimas[ultimas["pessoa_entregadora_normalizado"].isin(ativos_norm)].copy()

    # --- Cálculo do streak de faltas até ONTEM ---
    # dias_consecutivos_ausentes = (ontem - ultima_presenca)
    ultimas["dias_ausentes"] = (pd.to_datetime(ontem) - pd.to_datetime(ultimas["ultima_presenca"])).dt.days

    # filtra quem está com 4+ dias sem aparecer (espelha a regra anterior)
    alertas = ultimas[ultimas["dias_ausentes"] >= 4].copy().sort_values("dias_ausentes", ascending=False)

    if alertas.empty:
        st.success("✅ Nenhum entregador ativo com 4+ dias consecutivos ausente.")
        return

    # monta texto e tabela
    alertas["ultima_presenca_fmt"] = pd.to_datetime(alertas["ultima_presenca"]).dt.strftime("%d/%m")
    alertas["nome_exibir"] = alertas["pessoa_entregadora"].fillna(alertas["pessoa_entregadora_normalizado"])

    linhas = [
        f"• {row['nome_exibir']} – {int(row['dias_ausentes'])} dias consecutivos ausente (última presença: {row['ultima_presenca_fmt']})"
        for _, row in alertas.iterrows()
    ]
    st.text_area("Resultado (texto):", value="\n".join(linhas), height=320)

    st.dataframe(
        alertas[["nome_exibir","dias_ausentes","ultima_presenca"]]
        .rename(columns={"nome_exibir":"Entregador","dias_ausentes":"Dias ausente (consecutivos)","ultima_presenca":"Última presença"})
        .reset_index(drop=True),
        use_container_width=True
    )
