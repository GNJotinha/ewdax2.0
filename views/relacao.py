import streamlit as st
import pandas as pd
import numpy as np
from shared import sub_options_with_livre, apply_sub_filter
from relatorios import gerar_dados


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("Relação de Entregadores")

    df_f = df.copy()
    df_f["data_do_periodo"] = pd.to_datetime(df_f.get("data_do_periodo", df_f.get("data")), errors="coerce")
    df_f["data"] = df_f["data_do_periodo"].dt.date

    subpracas = sub_options_with_livre(df_f, praca_scope="SAO PAULO")
    filtro_subpraca = st.multiselect("Filtrar por subpraça:", subpracas)

    turnos = sorted([x for x in df_f.get("periodo", pd.Series(dtype=object)).dropna().unique()])
    filtro_turno = st.multiselect("Filtrar por turno:", turnos)

    tipo_periodo = st.radio("Como deseja escolher as datas?", ("Período contínuo", "Dias específicos"), horizontal=True)
    dias_escolhidos = []

    if tipo_periodo == "Período contínuo":
        data_min = df_f["data"].min()
        data_max = df_f["data"].max()
        periodo = st.date_input("Selecione o intervalo de datas:", [data_min, data_max], format="DD/MM/YYYY")
        if len(periodo) == 2:
            dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
        elif len(periodo) == 1:
            dias_escolhidos = [periodo[0]]
    else:
        dias_opcoes = sorted([d for d in df_f["data"].dropna().unique()])
        dias_escolhidos = st.multiselect("Selecione os dias desejados:", dias_opcoes,
                                         format_func=lambda x: x.strftime("%d/%m/%Y"))

    if st.button("Gerar", use_container_width=True):
        df_sel = df_f.copy()
        df_sel = apply_sub_filter(df_sel, filtro_subpraca, praca_scope="SAO PAULO")
        if filtro_turno:
            df_sel = df_sel[df_sel["periodo"].isin(filtro_turno)]
        if dias_escolhidos:
            df_sel = df_sel[df_sel["data"].isin(dias_escolhidos)]

        if df_sel.empty:
            st.info("❌ Nenhum entregador encontrado com os filtros aplicados.")
            return

        # ============================
        # 🔢 Calcula score (taxa + volume)
        # ============================
        agg = (
            df_sel
            .groupby("pessoa_entregadora", dropna=True)
            .agg(
                ofertadas=("numero_de_corridas_ofertadas", "sum"),
                aceitas=("numero_de_corridas_aceitas", "sum"),
                turnos=("data", "count")
            )
            .reset_index()
        )

        # taxa de aceitação
        agg["tx_acc"] = agg.apply(lambda r: (r["aceitas"] / r["ofertadas"]) if r["ofertadas"] else 0.0, axis=1)

        # estabilidade (log normalizado)
        max_ofertadas = max(1, agg["ofertadas"].max())
        agg["estab"] = np.log1p(agg["ofertadas"]) / np.log1p(max_ofertadas)

        # score final (peso taxa 70%, estabilidade 30%)
        PESO_TAXA = 0.7
        PESO_ESTAB = 0.3
        agg["score"] = (PESO_TAXA * agg["tx_acc"]) + (PESO_ESTAB * agg["estab"])

        # ordena do melhor pro pior
        agg = agg.sort_values(["score", "ofertadas"], ascending=[False, False])

        # ============================
        # 📋 Exibição (igual antes)
        # ============================
        nomes_ordenados = agg["pessoa_entregadora"].tolist()
        st.subheader("👤 Entregadores encontrados")
        st.dataframe(pd.DataFrame({"pessoa_entregadora": nomes_ordenados}), use_container_width=True)

        # ============================
        # 🧾 Blocos de texto (mesma ordem)
        # ============================
        blocos = []
        for nome in nomes_ordenados:
            chunk = df_sel[df_sel["pessoa_entregadora"] == nome]
            bloco = gerar_dados(nome, None, None, chunk)
            if bloco:
                blocos.append(bloco.strip())

        texto_final = "\n" + ("\n" + "—"*40 + "\n").join(blocos) if blocos else "Sem blocos gerados para os filtros."
        st.text_area("Resultado:", value=texto_final, height=500)
