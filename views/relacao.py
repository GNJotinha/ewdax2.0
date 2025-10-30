import streamlit as st
import pandas as pd
import numpy as np
from shared import sub_options_with_livre, apply_sub_filter
from relatorios import gerar_dados  # mantido do original
from utils import calcular_tempo_online


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
    # filtros
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
    dias_escolhidos: list = []

    periodo_txt = ""
    if tipo_periodo == "Período contínuo":
        data_min = df_f["data"].min()
        data_max = df_f["data"].max()
        periodo = st.date_input(
            "Selecione o intervalo de datas:",
            [data_min, data_max],
            format="DD/MM/YYYY",
        )
        if len(periodo) == 2:
            dias_escolhidos = list(
                pd.date_range(start=periodo[0], end=periodo[1]).date
            )
            periodo_txt = f"{periodo[0].strftime('%d/%m')} á {periodo[1].strftime('%d/%m')}"
        elif len(periodo) == 1:
            dias_escolhidos = [periodo[0]]
            periodo_txt = periodo[0].strftime("%d/%m")
    else:
        dias_opcoes = sorted([d for d in df_f["data"].dropna().unique()])
        dias_escolhidos = st.multiselect(
            "Selecione os dias desejados:",
            dias_opcoes,
            format_func=lambda x: x.strftime("%d/%m/%Y"),
        )
        if dias_escolhidos:
            if len(dias_escolhidos) == 1:
                periodo_txt = dias_escolhidos[0].strftime("%d/%m")
            else:
                periodo_txt = (
                    f"{min(dias_escolhidos).strftime('%d/%m')} á "
                    f"{max(dias_escolhidos).strftime('%d/%m')}"
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

        # se não montou período no radio, monta aqui do próprio df
        if not periodo_txt:
            dmin = df_sel["data"].min()
            dmax = df_sel["data"].max()
            periodo_txt = f"{dmin.strftime('%d/%m')} á {dmax.strftime('%d/%m')}"

        # ====================================================
        # 🔢 agregação por entregador
        # ====================================================
        agg = (
            df_sel.groupby("pessoa_entregadora", dropna=True)
            .agg(
                turnos=("data", "count"),
                ofertadas=("numero_de_corridas_ofertadas", "sum"),
                aceitas=("numero_de_corridas_aceitas", "sum"),
                rejeitadas=("numero_de_corridas_rejeitadas", "sum"),
                completas=("numero_de_corridas_completadas", "sum"),
            )
            .reset_index()
        )

        # garante int
        for c in ["ofertadas", "aceitas", "rejeitadas", "completas", "turnos"]:
            agg[c] = pd.to_numeric(agg[c], errors="coerce").fillna(0).astype(int)

        # taxas
        agg["Aceitação (%)"] = (
            (agg["aceitas"] / agg["ofertadas"])
            .replace([np.inf, -np.inf], 0)
            .fillna(0)
            * 100
        ).round(1)
        agg["Rejeição (%)"] = (
            (agg["rejeitadas"] / agg["ofertadas"])
            .replace([np.inf, -np.inf], 0)
            .fillna(0)
            * 100
        ).round(1)
        agg["Conclusão (%)"] = (
            (agg["completas"] / agg["aceitas"])
            .replace([np.inf, -np.inf], 0)
            .fillna(0)
            * 100
        ).round(1)

        # ordena do melhor pro pior
        agg = agg.sort_values("Aceitação (%)", ascending=False).reset_index(drop=True)

        # ====================================================
        # 📊 tabela estilizada
        # ====================================================
        st.subheader("👤 Entregadores encontrados (ordenado por aceitação)")

        tabela = agg.rename(
            columns={
                "pessoa_entregadora": "Entregador",
                "ofertadas": "Ofertadas",
                "aceitas": "Aceitas",
                "rejeitadas": "Rejeitadas",
                "completas": "Completas",
                "turnos": "Turnos",
            }
        )

        cols_show = [
            "Entregador",
            "Aceitação (%)",
            "Rejeição (%)",
            "Conclusão (%)",
            "Ofertadas",
            "Aceitas",
            "Rejeitadas",
            "Completas",
            "Turnos",
        ]
        tabela = tabela[cols_show]

        # função pra pintar a aceitação
        def colorir_aceitacao(val):
            try:
                v = float(val)
            except Exception:
                v = 0.0
            color = "#2ECC71" if v >= 60 else "#E74C3C"
            return f"background-color: {color}; color: white;"

        styled = (
            tabela.style
            .format({
                "Aceitação (%)": "{:.1f}",
                "Rejeição (%)": "{:.1f}",
                "Conclusão (%)": "{:.1f}",
            })
            .applymap(colorir_aceitacao, subset=["Aceitação (%)"])
        )

        st.dataframe(styled, use_container_width=True)

        # ====================================================
        # 🧾 relatório estilo "saídas"
        # ====================================================
        blocos = []

        # cabeçalho
        blocos.append(f"*Período de análise {periodo_txt}*")

        # por entregador (na mesma ordem da tabela)
        for _, row in tabela.iterrows():
            nome = row["Entregador"]
            # recorte do cara pra calcular tempo online real
            chunk = df_sel[df_sel["pessoa_entregadora"] == nome].copy()
            tempo_online = calcular_tempo_online(chunk)  # já vem %
            ofert = int(row["Ofertadas"])
            aceit = int(row["Aceitas"])
            rejei = int(row["Rejeitadas"])
            compl = int(row["Completas"])

            pct_acc = row["Aceitação (%)"]
            pct_rej = row["Rejeição (%)"]
            pct_comp = row["Conclusão (%)"]

            linhas = [
                f"*{nome}*",
                f"- Tempo online: {tempo_online:.2f}%",
                f"- Ofertadas: {ofert}",
                f"- Aceitas: {aceit} ({pct_acc:.2f}%)",
                f"- Rejeitadas: {rejei} ({pct_rej:.2f}%)",
                f"- Completas: {compl} ({pct_comp:.2f}%)",
            ]
            blocos.append("\n".join(linhas))

        texto_final = "\n\n".join(blocos)
        st.text_area("Resultado:", value=texto_final, height=500)
