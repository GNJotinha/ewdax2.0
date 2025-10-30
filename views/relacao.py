import streamlit as st
import pandas as pd
import numpy as np
from shared import sub_options_with_livre, apply_sub_filter
from relatorios import gerar_dados


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("Relação de Entregadores")

    # ---------------------------
    # base normalizada
    # ---------------------------
    df_f = df.copy()
    df_f["data_do_periodo"] = pd.to_datetime(
        df_f.get("data_do_periodo", df_f.get("data")), errors="coerce"
    )
    df_f["data"] = df_f["data_do_periodo"].dt.date

    # ---------------------------
    # filtros (iguais ao original)
    # ---------------------------
    subpracas = sub_options_with_livre(df_f, praca_scope="SAO PAULO")
    filtro_subpraca = st.multiselect("Filtrar por subpraça:", subpracas)

    turnos = sorted(
        [x for x in df_f.get("periodo", pd.Series(dtype=object)).dropna().unique()]
    )
    filtro_turno = st.multiselect("Filtrar por turno:", turnos)

    tipo_periodo = st.radio(
        "Como deseja escolher as datas?",
        ("Período contínuo", "Dias específicos"),
        horizontal=True,
    )
    dias_escolhidos: list[pd.Timestamp] = []

    if tipo_periodo == "Período contínuo":
        data_min = df_f["data"].min()
        data_max = df_f["data"].max()
        periodo = st.date_input(
            "Selecione o intervalo de datas:", [data_min, data_max], format="DD/MM/YYYY"
        )
        if len(periodo) == 2:
            dias_escolhidos = list(
                pd.date_range(start=periodo[0], end=periodo[1]).date
            )
        elif len(periodo) == 1:
            dias_escolhidos = [periodo[0]]
    else:
        dias_opcoes = sorted([d for d in df_f["data"].dropna().unique()])
        dias_escolhidos = st.multiselect(
            "Selecione os dias desejados:",
            dias_opcoes,
            format_func=lambda x: x.strftime("%d/%m/%Y"),
        )

    # ---------------------------
    # botão
    # ---------------------------
    if st.button("Gerar", use_container_width=True):
        # aplica filtros
        df_sel = df_f.copy()
        df_sel = apply_sub_filter(df_sel, filtro_subpraca, praca_scope="SAO PAULO")
        if filtro_turno:
            df_sel = df_sel[df_sel["periodo"].isin(filtro_turno)]
        if dias_escolhidos:
            df_sel = df_sel[df_sel["data"].isin(dias_escolhidos)]

        if df_sel.empty:
            st.info("❌ Nenhum entregador encontrado com os filtros aplicados.")
            return

        # ====================================================
        # 🔢 agregação por entregador
        # ====================================================
        agg = (
            df_sel.groupby("pessoa_entregadora", dropna=True)
            .agg(
                turnos=("data", "count"),
                ofertadas=(
                    "numero_de_corridas_ofertadas",
                    "sum",
                ),
                aceitas=(
                    "numero_de_corridas_aceitas",
                    "sum",
                ),
                rejeitadas=(
                    "numero_de_corridas_rejeitadas",
                    "sum",
                ),
                completas=(
                    "numero_de_corridas_completadas",
                    "sum",
                ),
            )
            .reset_index()
        )

        # proteções
        agg["ofertadas"] = pd.to_numeric(agg["ofertadas"], errors="coerce").fillna(0)
        agg["aceitas"] = pd.to_numeric(agg["aceitas"], errors="coerce").fillna(0)
        agg["rejeitadas"] = pd.to_numeric(agg["rejeitadas"], errors="coerce").fillna(0)
        agg["completas"] = pd.to_numeric(agg["completas"], errors="coerce").fillna(0)
        agg["turnos"] = pd.to_numeric(agg["turnos"], errors="coerce").fillna(0)

        # taxa de aceitação
        agg["tx_acc"] = agg.apply(
            lambda r: (r["aceitas"] / r["ofertadas"]) if r["ofertadas"] > 0 else 0.0,
            axis=1,
        )

        # estabilidade (volume dentro do próprio período)
        max_ofertadas = max(1, float(agg["ofertadas"].max()))
        agg["estab"] = np.log1p(agg["ofertadas"]) / np.log1p(max_ofertadas)

        # score final: 70% taxa + 30% volume
        PESO_TAXA = 0.7
        PESO_ESTAB = 0.3
        agg["score"] = (PESO_TAXA * agg["tx_acc"]) + (PESO_ESTAB * agg["estab"])

        # ORDEM: melhor -> pior
        agg = agg.sort_values(
            ["score", "ofertadas"], ascending=[False, False]
        ).reset_index(drop=True)

        # ============================
        # 📊 tabela final (com números)
        # ============================
        st.subheader("👤 Entregadores encontrados")

        tabela = agg.copy()
        tabela["Aceitação (%)"] = (tabela["tx_acc"] * 100).round(1)
        tabela["Estabilidade (%)"] = (tabela["estab"] * 100).round(0)
        tabela["Score (0-100)"] = (tabela["score"] * 100).round(1)

        cols_show = [
            "pessoa_entregadora",
            "Aceitação (%)",
            "ofertadas",
            "aceitas",
            "rejeitadas",
            "completas",
            "turnos",
            "Estabilidade (%)",
            "Score (0-100)",
        ]
        tabela = tabela[cols_show].rename(
            columns={
                "pessoa_entregadora": "Entregador",
                "ofertadas": "Ofertadas",
                "aceitas": "Aceitas",
                "rejeitadas": "Rejeitadas",
                "completas": "Completas",
                "turnos": "Turnos",
            }
        )

        st.dataframe(tabela, use_container_width=True)

        # ============================
        # 🧾 blocos de texto na MESMA ordem
        # ============================
        blocos = []
        for nome in agg["pessoa_entregadora"].tolist():
            chunk = df_sel[df_sel["pessoa_entregadora"] == nome]
            bloco = gerar_dados(nome, None, None, chunk)
            if bloco:
                blocos.append(bloco.strip())

        texto_final = (
            "\n" + ("\n" + "—" * 40 + "\n").join(blocos)
            if blocos
            else "Sem blocos gerados para os filtros."
        )
        st.text_area("Resultado:", value=texto_final, height=500)
