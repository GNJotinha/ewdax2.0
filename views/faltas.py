# views/faltas.py (versão turbo corrigida)
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("⚠️ Entregadores com 3+ faltas consecutivas (rápido)")

    # ------ Pré-checagens ------
    if "pessoa_entregadora_normalizado" not in df.columns:
        st.error("Coluna 'pessoa_entregadora_normalizado' ausente na base.")
        return
    if "pessoa_entregadora" not in df.columns:
        st.error("Coluna 'pessoa_entregadora' ausente na base.")
        return
    if "data" not in df.columns and "data_do_periodo" not in df.columns:
        st.error("Coluna de data ausente (espere 'data' ou 'data_do_periodo').")
        return

    # ------ Datas & janela ------
    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)
    corte_60d = hoje - timedelta(days=60)  # janela suficiente pro alerta
    corte_15d = hoje - timedelta(days=15)  # critério de "ativo" recente

    # Normaliza coluna de data para tipo date
    df = df.copy()
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    else:
        df["data"] = pd.to_datetime(df["data_do_periodo"], errors="coerce").dt.date
    df = df[df["data"].notna()]
    if df.empty:
        st.success("✅ Sem dados de presença/ausência.")
        return

    # Restrição da janela (performance)
    df_janela = df[df["data"] >= corte_60d].copy()
    if df_janela.empty:
        st.success("✅ Nada na janela dos últimos 60 dias.")
        return

    # ------ Quem é "ativo" (teve presença nos últimos 15 dias) ------
    ativos_norm = (
        df_janela.loc[df_janela["data"] >= corte_15d, "pessoa_entregadora_normalizado"]
        .dropna()
        .unique()
        .tolist()
    )
    if not ativos_norm:
        st.success("✅ Nenhum entregador ativo nos últimos 15 dias.")
        return

    # ------ Última presença por entregador (vetorizado) ------
    # max(data) por pessoa_entregadora_normalizado
    ultimas = (
        df_janela.groupby("pessoa_entregadora_normalizado", dropna=True, as_index=False)["data"]
        .max()
        .rename(columns={"data": "ultima_presenca"})
    )

    # Para pegar o "nome bonito" (linha da última presença), precisamos de datetime consistente
    df_janela = df_janela.copy()
    df_janela["data_dt"] = pd.to_datetime(df_janela["data"], errors="coerce")

    # idx são RÓTULOS do índice do df_janela (sem reset_index) -> compatível com .loc[idx]
    idx = (
        df_janela.dropna(subset=["pessoa_entregadora_normalizado", "data_dt"])
                 .groupby("pessoa_entregadora_normalizado")["data_dt"]
                 .idxmax()
    )

    # Seleciona os nomes na própria base (sem KeyError agora)
    nomes_rec = df_janela.loc[idx, ["pessoa_entregadora_normalizado", "pessoa_entregadora"]]
    ultimas = ultimas.merge(nomes_rec, on="pessoa_entregadora_normalizado", how="left")

    # Mantém apenas os considerados "ativos"
    ultimas = ultimas[ultimas["pessoa_entregadora_normalizado"].isin(ativos_norm)].copy()
    if ultimas.empty:
        st.success("✅ Nenhum entregador ativo com presenças na janela de 60 dias.")
        return

    # ------ Streak de faltas até ontem ------
    ultimas["dias_ausentes"] = (
        pd.to_datetime(ontem) - pd.to_datetime(ultimas["ultima_presenca"])
    ).dt.days

    # Alerta: 4+ dias consecutivos ausente (mantém regra anterior)
    alertas = (
        ultimas[ultimas["dias_ausentes"] >= 4]
        .copy()
        .sort_values("dias_ausentes", ascending=False)
    )

    if alertas.empty:
        st.success("✅ Nenhum entregador ativo com 4+ dias consecutivos ausente.")
        return

    alertas["ultima_presenca_fmt"] = pd.to_datetime(alertas["ultima_presenca"]).dt.strftime("%d/%m")
    alertas["nome_exibir"] = alertas["pessoa_entregadora"].fillna(alertas["pessoa_entregadora_normalizado"])

    # ------ Saídas ------
    # Texto pronto
    linhas = [
        f"• {row['nome_exibir']} – {int(row['dias_ausentes'])} dias consecutivos ausente (última presença: {row['ultima_presenca_fmt']})"
        for _, row in alertas.iterrows()
    ]
    st.text_area("Resultado (texto):", value="\n".join(linhas), height=320)

    # Tabela
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

    # CSV
    st.download_button(
        "⬇️ Baixar CSV",
        data=tabela.to_csv(index=False).encode("utf-8"),
        file_name=f"alerta_faltas_{ontem.strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
