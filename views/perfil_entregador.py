import streamlit as st
import pandas as pd
import plotly.express as px
from relatorios import utr_por_entregador_turno
from shared import hms_from_hours

META_ELITE = 300
COL_ELITE = "numero_de_pedidos_aceitos_e_concluidos"


def _safe_num_sum(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("👤 Perfil do Entregador")

    if df is None or df.empty:
        st.info("Sem dados.")
        return

    if "pessoa_entregadora" not in df.columns:
        st.error("Coluna `pessoa_entregadora` não encontrada na base.")
        return

    nomes = sorted(df["pessoa_entregadora"].dropna().unique())
    nome = st.selectbox(
        "Selecione o entregador:",
        [None] + nomes,
        format_func=lambda x: "" if x is None else x,
    )
    if not nome:
        return

    df_e = df[df["pessoa_entregadora"] == nome].copy()
    if df_e.empty:
        st.info("❌ Nenhum dado para esse entregador no histórico.")
        return

    # -------- Normaliza mes_ano (mês de referência) --------
    if "mes_ano" in df_e.columns:
        df_e["mes_ano"] = pd.to_datetime(df_e["mes_ano"], errors="coerce")
    else:
        # fallback: tenta data_do_periodo ou data
        if "data_do_periodo" in df_e.columns:
            df_e["data_do_periodo"] = pd.to_datetime(df_e["data_do_periodo"], errors="coerce")
            df_e["mes_ano"] = df_e["data_do_periodo"].dt.to_period("M").dt.to_timestamp()
        elif "data" in df_e.columns:
            df_e["data"] = pd.to_datetime(df_e["data"], errors="coerce")
            df_e["mes_ano"] = df_e["data"].dt.to_period("M").dt.to_timestamp()
        else:
            st.error("Não achei coluna de data (mes_ano/data_do_periodo/data).")
            return

    meses = sorted([m for m in df_e["mes_ano"].dropna().unique().tolist()])
    mes_sel = None
    if meses:
        mes_sel = st.selectbox(
            "Mês de referência (ELITE + visão mensal)",
            meses,
            index=len(meses) - 1,  # último mês disponível na base
            format_func=lambda ts: pd.to_datetime(ts).strftime("%b/%Y"),
        )

    # -------- Visão (mês selecionado OU histórico) --------
    modo = st.radio("Visão", ["Mês selecionado", "Histórico"], horizontal=True, index=0)
    if modo == "Mês selecionado" and mes_sel is not None:
        df_base = df_e[df_e["mes_ano"] == pd.to_datetime(mes_sel)].copy()
    else:
        df_base = df_e

    # ===================== ELITE (sempre do mês selecionado) =====================
    st.subheader("🏆 ELITE no mês")

    if mes_sel is None:
        st.warning("Não encontrei meses válidos na base para este entregador.")
    else:
        df_mes = df_e[df_e["mes_ano"] == pd.to_datetime(mes_sel)].copy()

        if COL_ELITE not in df_mes.columns:
            st.error(f"Coluna `{COL_ELITE}` não encontrada na base.")
        else:
            atual = int(_safe_num_sum(df_mes, COL_ELITE))
            faltam = max(0, META_ELITE - atual)
            pct = min(1.0, atual / META_ELITE) if META_ELITE else 0.0

            c1, c2, c3 = st.columns(3)
            c1.metric("Pedidos aceitos e concluídos (mês)", f"{atual:,}".replace(",", "."))
            c2.metric("Meta ELITE", f"{META_ELITE}")
            c3.metric("Status", "ELITE ✅" if atual >= META_ELITE else f"Faltam {faltam}")

            st.progress(pct)
            st.caption(f"{atual}/{META_ELITE} • {('ELITE ✅' if atual >= META_ELITE else f'faltam {faltam}')}")

            # histórico mensal do ELITE (opcional, mas útil pra contexto)
            hist = (
                df_e.assign(_elite=pd.to_numeric(df_e[COL_ELITE], errors="coerce").fillna(0))
                .groupby("mes_ano", as_index=False)["_elite"]
                .sum()
                .rename(columns={"_elite": "pedidos_ok_mes"})
                .sort_values("mes_ano")
            )
            hist["Mês"] = pd.to_datetime(hist["mes_ano"]).dt.strftime("%b/%Y")
            hist["ELITE"] = hist["pedidos_ok_mes"] >= META_ELITE
            hist["faltam"] = (META_ELITE - hist["pedidos_ok_mes"]).clip(lower=0).astype(int)

            with st.expander("Ver histórico ELITE por mês", expanded=False):
                st.dataframe(
                    hist[["Mês", "pedidos_ok_mes", "faltam", "ELITE"]]
                    .rename(columns={"pedidos_ok_mes": "pedidos_ok (mês)"})
                    .style.format({"pedidos_ok (mês)": "{:.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                )

    st.divider()

    # ===================== KPIs (mês ou histórico) =====================
    ofertadas = int(_safe_num_sum(df_base, "numero_de_corridas_ofertadas"))
    aceitas = int(_safe_num_sum(df_base, "numero_de_corridas_aceitas"))
    rejeitadas = int(_safe_num_sum(df_base, "numero_de_corridas_rejeitadas"))
    completas = int(_safe_num_sum(df_base, "numero_de_corridas_completadas"))

    acc_pct = (aceitas / ofertadas * 100) if ofertadas > 0 else 0.0
    rej_pct = (rejeitadas / ofertadas * 100) if ofertadas > 0 else 0.0
    comp_pct = (completas / aceitas * 100) if aceitas > 0 else 0.0

    horas_total = (df_base["segundos_abs"].sum() / 3600.0) if "segundos_abs" in df_base.columns else 0.0
    utr_abs = (ofertadas / horas_total) if horas_total > 0 else 0.0

    base_u = utr_por_entregador_turno(df_base)
    if not base_u.empty:
        base_u = base_u[base_u["supply_hours"] > 0]
        utr_medias = (
            (base_u["corridas_ofertadas"] / base_u["supply_hours"]).mean()
            if not base_u.empty
            else 0.0
        )
    else:
        utr_medias = 0.0

    # datas (se tiver)
    ultima_txt = "—"
    dias_ativos = 0
    if "data" in df_base.columns:
        df_base["data"] = pd.to_datetime(df_base["data"], errors="coerce")
        dias_ativos = int(df_base["data"].dt.date.nunique())
        ultima_atividade = df_base["data"].max()
        ultima_txt = ultima_atividade.strftime("%d/%m/%y") if pd.notna(ultima_atividade) else "—"

    st.subheader("📌 KPIs " + ("(mês)" if modo == "Mês selecionado" else "(histórico)"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("UTR (Absoluto)", f"{utr_abs:.2f}")
    c2.metric("UTR (Médias)", f"{utr_medias:.2f}")
    c3.metric("Aceitas", f"{aceitas:,}".replace(",", "."))
    c4.metric("Completas", f"{completas:,}".replace(",", "."))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Ofertadas", f"{ofertadas:,}".replace(",", "."))
    c6.metric("Rejeitadas", f"{rejeitadas:,}".replace(",", "."))
    c6.caption(f"Rejeição: {rej_pct:.2f}%")
    c7.metric("Aceitação", f"{acc_pct:.2f}%")
    c8.metric("Conclusão", f"{comp_pct:.2f}%")

    c9, c10 = st.columns(2)
    c9.metric("SH", hms_from_hours(horas_total))
    c10.metric("Últ. dia", ultima_txt)

    st.divider()

    # ===================== Gráfico histórico (completas por mês) =====================
    mens = (
        df_e.groupby("mes_ano", as_index=False)
        .agg(
            ofertadas=("numero_de_corridas_ofertadas", "sum"),
            aceitas=("numero_de_corridas_aceitas", "sum"),
            completas=("numero_de_corridas_completadas", "sum"),
        )
        .sort_values("mes_ano")
    )
    mens["acc_pct"] = mens.apply(
        lambda r: (r["aceitas"] / r["ofertadas"] * 100) if r["ofertadas"] > 0 else 0.0,
        axis=1,
    )
    mens["mes_rotulo"] = pd.to_datetime(mens["mes_ano"]).dt.strftime("%b/%y")
    mens["__label_text__"] = mens.apply(lambda r: f"{int(r['completas'])} • acc {r['acc_pct']:.0f}%", axis=1)

    fig = px.bar(
        mens,
        x="mes_rotulo",
        y="completas",
        text="__label_text__",
        labels={"mes_rotulo": "Mês", "completas": "Completas"},
        title="Completas por mês • rótulo: N • acc%",
        template="plotly_dark",
        color_discrete_sequence=["#00BFFF"],
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        xaxis_title="Mês",
        yaxis_title="Completas",
        margin=dict(l=20, r=20, t=60, b=30),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)
