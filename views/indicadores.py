import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from relatorios import utr_por_entregador_turno
from shared import sub_options_with_livre, apply_sub_filter


# =========================
# Paletas / rótulos
# =========================

WEEKDAY_LABELS = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
WEEKDAY_ORDER = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

WEEK_PALETTE = [
    "#00E5FF",  # ciano neon
    "#FF2D55",  # rosa/vermelho neon
    "#39FF14",  # verde neon
    "#FFD60A",  # amarelo forte
    "#BF5AF2",  # roxo
    "#FF9F0A",  # laranja
    "#64D2FF",  # azul claro
    "#FF375F",  # vermelho vivo
]

PRIMARY_COLOR = ["#00BFFF"]


# =========================
# Helpers de dados
# =========================

def _ensure_data_mes_ano(df: pd.DataFrame) -> pd.DataFrame:
    """Garante colunas data/mes/ano, mesmo que o CSV não tenha."""
    df = df.copy()

    # data
    if "data" not in df.columns:
        df["data"] = pd.to_datetime(df.get("data_do_periodo", df.get("data")), errors="coerce")
    else:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")

    # mes/ano (blindado)
    if "mes" not in df.columns:
        df["mes"] = df["data"].dt.month.astype("Int64")
    else:
        df["mes"] = pd.to_numeric(df["mes"], errors="coerce").astype("Int64")

    if "ano" not in df.columns:
        df["ano"] = df["data"].dt.year.astype("Int64")
    else:
        df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")

    df["mes_ano"] = df["data"].dt.strftime("%m/%Y")

    # segundos_abs (evita negativo/NaN virar cagada em UTR/horas)
    if "segundos_abs" in df.columns:
        df["segundos_abs"] = pd.to_numeric(df["segundos_abs"], errors="coerce").fillna(0).clip(lower=0)

    return df


def calcular_aderencia(df: pd.DataFrame, group_cols=("data",)):
    """
    Aderência = regulares_atuaram / vagas
    - vagas: numero_minimo_de_entregadores_regulares_na_escala
    - regulares_atuaram: entregadores com tag == 'REGULAR'
    """
    df = df.copy()
    if "tag" not in df.columns:
        df["tag"] = pd.NA
    if "numero_minimo_de_entregadores_regulares_na_escala" not in df.columns:
        df["numero_minimo_de_entregadores_regulares_na_escala"] = 0

    df["vagas"] = pd.to_numeric(df["numero_minimo_de_entregadores_regulares_na_escala"], errors="coerce").fillna(0).clip(lower=0)
    df["is_regular"] = df["tag"].astype(str).str.upper().str.contains("REGULAR", na=False)

    base = (
        df.groupby(list(group_cols), as_index=False)
        .agg(
            vagas=("vagas", "sum"),
            regulares_atuaram=("is_regular", "sum"),
        )
        .sort_values(list(group_cols))
    )
    base["aderencia"] = (base["regulares_atuaram"] / base["vagas"] * 100.0).where(base["vagas"] > 0, 0.0)
    return base


# =========================
# Semanal (clean)
# =========================

def _render_comparar_semanas(df_day: pd.DataFrame, y_col: str, yaxis_title: str, chart_title: str, key_prefix: str):
    """
    Compara várias semanas no formato Seg..Dom (linhas).
    Espera df_day com colunas: week_start, weekday_label e y_col.
    """
    if df_day is None or df_day.empty or "week_start" not in df_day.columns:
        st.info("Sem dados suficientes pra comparar semanas.")
        return
    if y_col not in df_day.columns:
        st.info("Coluna de métrica não encontrada pra comparar semanas.")
        return

    weeks = sorted(df_day["week_start"].dropna().unique().tolist())
    if not weeks:
        st.info("Sem semanas disponíveis pra comparar.")
        return

    week_labels = {ws: pd.to_datetime(ws).strftime("%d/%m/%Y") for ws in weeks}
    all_labels = [week_labels[w] for w in weeks]

    # UI clean: por padrão mostra TODAS as semanas.
    with st.expander("Semanas", expanded=False):
        sel = st.multiselect(
            "Semanas (início na segunda-feira):",
            options=all_labels,
            default=all_labels,
            key=f"{key_prefix}_weeks",
            label_visibility="collapsed",
        )

    # Se o usuário desmarcar tudo, assume "todas"
    sel_weeks = [w for w in weeks if week_labels[w] in sel] if sel else weeks

    fig = go.Figure()
    for i, ws in enumerate(sel_weeks):
        part = df_day[df_day["week_start"] == ws].copy()
        part = part.set_index("weekday_label").reindex(WEEKDAY_ORDER)
        y = pd.to_numeric(part[y_col], errors="coerce").fillna(0)

        fig.add_trace(
            go.Scatter(
                x=WEEKDAY_ORDER,
                y=y,
                mode="lines+markers",
                name=week_labels[ws],
                line=dict(color=WEEK_PALETTE[i % len(WEEK_PALETTE)]),
            )
        )

    fig.update_layout(
        title=chart_title,
        template="plotly_dark",
        margin=dict(t=60, b=30, l=40, r=40),
        xaxis_title="Dia da semana",
        yaxis_title=yaxis_title,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_modo_semanal(
    df_filtrado: pd.DataFrame,
    df_mes_ref: pd.DataFrame,
    df_cmp_ref: pd.DataFrame,
    month_start: pd.Timestamp,
    month_end: pd.Timestamp,
    mes_ref: int,
    ano_ref: int,
    turno_col: str | None,
):
    """Tela dedicada pro comparativo semanal (sem checkbox espalhado)."""

    indicador = st.radio(
        "",
        [
            "Corridas ofertadas",
            "Corridas aceitas",
            "Corridas rejeitadas",
            "Corridas completadas",
            "Horas realizadas",
            "Entregadores ativos",
            "Aderência (%)",
        ],
        index=0,
        horizontal=True,
        key=f"wk_indicador_{mes_ref}_{ano_ref}",
        label_visibility="collapsed",
    )

    # Sempre usa semana completa no comparativo semanal (Seg–Dom) pra não perder dias quando cruza mês
    df_scope = (df_cmp_ref if (df_cmp_ref is not None and not df_cmp_ref.empty) else df_mes_ref).copy()

    # Blindagem de colunas (dataset diferente não pode quebrar a tela)
    for _c in [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
        "segundos_abs",
    ]:
        if _c not in df_scope.columns:
            df_scope[_c] = 0

    if "pessoa_entregadora" not in df_scope.columns:
        df_scope["pessoa_entregadora"] = pd.NA

    df_scope = df_scope.dropna(subset=["data"]).copy()
    if df_scope.empty:
        st.info("Sem dados no período selecionado pra montar o semanal.")
        return

    # Aderência (%): usa calcular_aderencia porque não é soma simples
    if indicador == "Aderência (%)":
        if ("numero_minimo_de_entregadores_regulares_na_escala" not in df_scope.columns) or ("tag" not in df_scope.columns):
            st.info("Aderência precisa das colunas 'numero_minimo_de_entregadores_regulares_na_escala' e 'tag'.")
            return

        grp = ("data", turno_col) if turno_col is not None else ("data",)
        base_ap = calcular_aderencia(df_scope.copy(), group_cols=grp)

        base_ap["date"] = pd.to_datetime(base_ap["data"]).dt.normalize()
        base_ap["weekday"] = base_ap["date"].dt.weekday
        base_ap["weekday_label"] = base_ap["weekday"].map(WEEKDAY_LABELS)
        base_ap["week_start"] = base_ap["date"] - pd.to_timedelta(base_ap["weekday"], unit="D")
        base_ap["week_end"] = base_ap["week_start"] + pd.Timedelta(days=6)

        base_ap = base_ap[(base_ap["week_end"] >= month_start) & (base_ap["week_start"] <= month_end)].copy()
        if base_ap.empty:
            st.info("Sem semanas disponíveis (com esse mês/ano) pra comparar.")
            return

        por_data_cmp = (
            base_ap.groupby(["week_start", "weekday_label"], as_index=False)
            .agg(vagas=("vagas", "sum"), regulares=("regulares_atuaram", "sum"))
        )
        por_data_cmp["aderencia_pct"] = por_data_cmp.apply(
            lambda r: (r["regulares"] / r["vagas"] * 100.0) if r["vagas"] else 0.0, axis=1
        )

        por_semana = (
            base_ap.groupby("week_start", as_index=False)
            .agg(vagas=("vagas", "sum"), regulares=("regulares_atuaram", "sum"))
            .sort_values("week_start")
            .reset_index(drop=True)
        )
        por_semana["aderencia_pct"] = por_semana.apply(
            lambda r: (r["regulares"] / r["vagas"] * 100.0) if r["vagas"] else 0.0, axis=1
        )
        por_semana["semana_n"] = por_semana.index + 1
        por_semana["semana_lbl"] = por_semana.apply(
            lambda r: (
                f"Semana {int(r['semana_n'])}<br>"
                f"{pd.to_datetime(r['week_start']).strftime('%d/%m')}–{(pd.to_datetime(r['week_start']) + pd.Timedelta(days=6)).strftime('%d/%m')}"
            ),
            axis=1,
        )

        y_cmp = "aderencia_pct"
        yaxis = "Aderência (%)"
        y_wk = "aderencia_pct"
        text_wk = por_semana["aderencia_pct"].map(lambda v: f"{v:.1f}%")
        title_cmp = f"Comparação semanal (Seg–Dom) — {yaxis}"
        title_wk = f"Totais por semana (Seg–Dom) — {mes_ref:02d}/{ano_ref}"

    else:
        tmp_day = df_scope.copy()
        tmp_day["date"] = pd.to_datetime(tmp_day["data"]).dt.normalize()
        tmp_day["weekday"] = tmp_day["date"].dt.weekday
        tmp_day["weekday_label"] = tmp_day["weekday"].map(WEEKDAY_LABELS)
        tmp_day["week_start"] = tmp_day["date"] - pd.to_timedelta(tmp_day["weekday"], unit="D")
        tmp_day["week_end"] = tmp_day["week_start"] + pd.Timedelta(days=6)

        # Mantém só semanas que encostam no mês selecionado
        tmp_day = tmp_day[(tmp_day["week_end"] >= month_start) & (tmp_day["week_start"] <= month_end)].copy()
        if tmp_day.empty:
            st.info("Sem semanas disponíveis (com esse mês/ano) pra comparar.")
            return

        por_data_cmp = (
            tmp_day.groupby(["week_start", "weekday_label"], as_index=False)
            .agg(
                ofe=("numero_de_corridas_ofertadas", "sum"),
                ace=("numero_de_corridas_aceitas", "sum"),
                rej=("numero_de_corridas_rejeitadas", "sum"),
                com=("numero_de_corridas_completadas", "sum"),
                seg=("segundos_abs", "sum"),
                entregadores=("pessoa_entregadora", "nunique"),
            )
        )
        por_data_cmp["horas"] = por_data_cmp["seg"] / 3600.0
        por_data_cmp["utr"] = (por_data_cmp["ofe"] / por_data_cmp["horas"]).where(por_data_cmp["horas"] > 0, 0.0)
        por_data_cmp["acc_pct"] = (por_data_cmp["ace"] / por_data_cmp["ofe"] * 100).where(por_data_cmp["ofe"] > 0, 0.0)
        por_data_cmp["rej_pct"] = (por_data_cmp["rej"] / por_data_cmp["ofe"] * 100).where(por_data_cmp["ofe"] > 0, 0.0)
        por_data_cmp["comp_pct"] = (por_data_cmp["com"] / por_data_cmp["ace"] * 100).where(por_data_cmp["ace"] > 0, 0.0)

        por_semana = (
            tmp_day.groupby("week_start", as_index=False)
            .agg(
                ofe=("numero_de_corridas_ofertadas", "sum"),
                ace=("numero_de_corridas_aceitas", "sum"),
                rej=("numero_de_corridas_rejeitadas", "sum"),
                com=("numero_de_corridas_completadas", "sum"),
                seg=("segundos_abs", "sum"),
                entregadores=("pessoa_entregadora", "nunique"),
            )
            .sort_values("week_start")
            .reset_index(drop=True)
        )
        por_semana["horas"] = por_semana["seg"] / 3600.0
        por_semana["utr"] = (por_semana["ofe"] / por_semana["horas"]).where(por_semana["horas"] > 0, 0.0)
        por_semana["acc_pct"] = (por_semana["ace"] / por_semana["ofe"] * 100).where(por_semana["ofe"] > 0, 0.0)
        por_semana["rej_pct"] = (por_semana["rej"] / por_semana["ofe"] * 100).where(por_semana["ofe"] > 0, 0.0)
        por_semana["comp_pct"] = (por_semana["com"] / por_semana["ace"] * 100).where(por_semana["ace"] > 0, 0.0)

        por_semana["semana_n"] = por_semana.index + 1
        por_semana["semana_lbl"] = por_semana.apply(
            lambda r: (
                f"Semana {int(r['semana_n'])}<br>"
                f"{pd.to_datetime(r['week_start']).strftime('%d/%m')}–{(pd.to_datetime(r['week_start']) + pd.Timedelta(days=6)).strftime('%d/%m')}"
            ),
            axis=1,
        )

        # Métricas / modos
        if indicador == "Corridas ofertadas":
            wk_metric = st.radio(
                "Métrica",
                ["Corridas", "UTR"],
                index=0,
                horizontal=True,
                key=f"wk_metric_ofe_{mes_ref}_{ano_ref}",
            )
            if wk_metric == "UTR":
                y_cmp, yaxis = "utr", "UTR"
                y_wk = "utr"
                text_wk = por_semana.apply(lambda r: f"{r['utr']:.2f} ({int(r['ofe'])} corr.)", axis=1)
            else:
                y_cmp, yaxis = "ofe", "Corridas ofertadas"
                y_wk = "ofe"
                text_wk = por_semana.apply(lambda r: f"{int(r['ofe'])} ({r['utr']:.2f} UTR)", axis=1)

        elif indicador == "Corridas aceitas":
            modo = st.radio("Modo", ["Quantidade", "%"], index=0, horizontal=True, key=f"wk_mode_ace_{mes_ref}_{ano_ref}")
            if modo == "%":
                y_cmp, yaxis = "acc_pct", "Taxa de aceite (%)"
                y_wk = "acc_pct"
                text_wk = por_semana.apply(lambda r: f"{r['acc_pct']:.1f}% ({int(r['ace'])})", axis=1)
            else:
                y_cmp, yaxis = "ace", "Corridas aceitas"
                y_wk = "ace"
                text_wk = por_semana.apply(lambda r: f"{int(r['ace'])} ({r['acc_pct']:.1f}%)", axis=1)

        elif indicador == "Corridas rejeitadas":
            modo = st.radio("Modo", ["Quantidade", "%"], index=0, horizontal=True, key=f"wk_mode_rej_{mes_ref}_{ano_ref}")
            if modo == "%":
                y_cmp, yaxis = "rej_pct", "Taxa de rejeição (%)"
                y_wk = "rej_pct"
                text_wk = por_semana.apply(lambda r: f"{r['rej_pct']:.1f}% ({int(r['rej'])})", axis=1)
            else:
                y_cmp, yaxis = "rej", "Corridas rejeitadas"
                y_wk = "rej"
                text_wk = por_semana.apply(lambda r: f"{int(r['rej'])} ({r['rej_pct']:.1f}%)", axis=1)

        elif indicador == "Corridas completadas":
            modo = st.radio("Modo", ["Quantidade", "%"], index=0, horizontal=True, key=f"wk_mode_com_{mes_ref}_{ano_ref}")
            if modo == "%":
                y_cmp, yaxis = "comp_pct", "Taxa de conclusão (%)"
                y_wk = "comp_pct"
                text_wk = por_semana.apply(lambda r: f"{r['comp_pct']:.1f}% ({int(r['com'])})", axis=1)
            else:
                y_cmp, yaxis = "com", "Corridas completadas"
                y_wk = "com"
                text_wk = por_semana.apply(lambda r: f"{int(r['com'])} ({r['comp_pct']:.1f}%)", axis=1)

        elif indicador == "Horas realizadas":
            y_cmp, yaxis = "horas", "Horas"
            y_wk = "horas"
            text_wk = por_semana["horas"].map(lambda v: f"{v:.1f}h")

        else:  # Entregadores ativos
            y_cmp, yaxis = "entregadores", "Entregadores"
            y_wk = "entregadores"
            text_wk = por_semana["entregadores"].map(lambda v: f"{int(v)}")

        title_cmp = f"Comparação semanal (Seg–Dom) — {yaxis}"
        title_wk = f"Totais por semana (Seg–Dom) — {mes_ref:02d}/{ano_ref}"

    # Render: duas visões
    tab1, tab2 = st.tabs(["📅 Seg–Dom (dia a dia)", "🧱 Semana 1, 2, 3... (total)"])

    with tab1:
        _render_comparar_semanas(
            por_data_cmp,
            y_cmp,
            yaxis,
            title_cmp,
            key_prefix=f"wk_cmp_{mes_ref}_{ano_ref}_{indicador}",
        )

    with tab2:
        fig_wk = px.bar(
            por_semana,
            x="semana_lbl",
            y=y_wk,
            text=text_wk,
            title=title_wk,
            labels={"semana_lbl": "Semana (Seg–Dom)", y_wk: yaxis},
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig_wk.update_traces(texttemplate="<b>%{text}</b>", textposition="outside", cliponaxis=False)
        fig_wk.update_layout(margin=dict(t=60, b=40, l=40, r=40))
        st.plotly_chart(fig_wk, use_container_width=True)


# =========================
# Render principal
# =========================

def render(df: pd.DataFrame):
    st.title("Indicadores Gerais")

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    df = _ensure_data_mes_ano(df)
    df = df.dropna(subset=["data"]).copy()

    # =========================
    # Tipo de gráfico (inclui semanal)
    # =========================
    tipo_grafico = st.radio(
        "Tipo de gráfico:",
        [
            "Corridas ofertadas",
            "Corridas aceitas",
            "Corridas rejeitadas",
            "Corridas completadas",
            "Horas realizadas",
            "Entregadores ativos",
            "Aderência (%)",
            "Comparativo semanal",
        ],
        index=0,
        horizontal=True,
    )

    # controles condicionais
    utr_modo = None
    if tipo_grafico == "Corridas ofertadas":
        utr_modo = st.radio(
            "UTR no mensal",
            ["Absoluto", "Médias"],
            index=0,
            horizontal=True,
            help="Como calcular a UTR exibida no gráfico MENSAL de ofertadas.",
        )

    modo_taxa = None
    if tipo_grafico in ("Corridas aceitas", "Corridas rejeitadas", "Corridas completadas"):
        modo_taxa = st.radio(
            "Modo do gráfico",
            ["Quantidade", "%"],
            index=0,
            horizontal=True,
            help="Quantidade: mostra corridas (com % no texto).  %: mostra a taxa (com quantidade no texto).",
        )

    # =========================
    # Filtros (subpraça / turno / entregador)
    # =========================
    c1, c2, c3 = st.columns(3)

    with c1:
        praca_scope = "SAO PAULO"
        subs = sub_options_with_livre(df[df.get("praca") == praca_scope], praca_scope=praca_scope)
        sub_sel = st.multiselect("Subpraça", options=subs, default=[])

    with c2:
        turno_col = "turno" if "turno" in df.columns else None
        turno_options = ["Todos"]
        if turno_col is not None:
            turno_options += sorted([t for t in df[turno_col].dropna().unique().tolist()])
        turno_sel = st.selectbox("Turno", options=turno_options, index=0)

    with c3:
        ent_col = "pessoa_entregadora" if "pessoa_entregadora" in df.columns else None
        ent_options = []
        if ent_col is not None:
            ent_options = sorted([e for e in df[ent_col].dropna().unique().tolist()])
        ent_sel = st.multiselect("Entregador(es)", options=ent_options, default=[])

    # aplica filtros
    if sub_sel:
        df = apply_sub_filter(df, sub_sel, praca_scope=praca_scope)

    if turno_col is not None and turno_sel != "Todos":
        df = df[df[turno_col] == turno_sel].copy()

    if ent_col is not None and ent_sel:
        df = df[df[ent_col].isin(ent_sel)].copy()

    if df.empty:
        st.warning("Sem dados com esses filtros.")
        return

    # =========================
    # Seleção mês/ano do diário
    # =========================
    colm, cola = st.columns(2)
    with colm:
        meses_disponiveis = sorted([int(m) for m in df["mes"].dropna().unique().tolist()])
        mes_diario = st.selectbox("Mês (gráfico diário)", options=meses_disponiveis, index=len(meses_disponiveis) - 1)
    with cola:
        anos_disponiveis = sorted([int(a) for a in df["ano"].dropna().unique().tolist()])
        ano_diario = st.selectbox("Ano (gráfico diário)", options=anos_disponiveis, index=len(anos_disponiveis) - 1)

    # =========================
    # Slices de tempo (mês / ano / comparativo semanal com semana completa)
    # =========================
    month_start = pd.Timestamp(int(ano_diario), int(mes_diario), 1)
    month_end = month_start + pd.offsets.MonthEnd(1)

    cmp_start = month_start - pd.Timedelta(days=6)
    cmp_end = month_end + pd.Timedelta(days=6)

    df_mes_ref = df[(df["mes"] == mes_diario) & (df["ano"] == ano_diario)].copy()
    df_ano_ref = df[df["ano"] == ano_diario].copy()
    df_cmp_ref = df[(df["data"] >= cmp_start) & (df["data"] <= cmp_end)].copy()

    # =========================
    # Modo semanal (limpo) como tipo de gráfico
    # =========================
    if tipo_grafico == "Comparativo semanal":
        _render_modo_semanal(
            df_filtrado=df,
            df_mes_ref=df_mes_ref,
            df_cmp_ref=df_cmp_ref,
            month_start=month_start,
            month_end=month_end,
            mes_ref=mes_diario,
            ano_ref=ano_diario,
            turno_col=turno_col,
        )
        return

    # =========================
    # A partir daqui: modos normais (mensal + diário) do tipo escolhido
    # =========================

    # --- agregados mensais
    df_mensal = (
        df_ano_ref.groupby("mes_ano", as_index=False)
        .agg(
            ofertadas=("numero_de_corridas_ofertadas", "sum") if "numero_de_corridas_ofertadas" in df_ano_ref.columns else ("mes_ano", "size"),
            aceitas=("numero_de_corridas_aceitas", "sum") if "numero_de_corridas_aceitas" in df_ano_ref.columns else ("mes_ano", "size"),
            rejeitadas=("numero_de_corridas_rejeitadas", "sum") if "numero_de_corridas_rejeitadas" in df_ano_ref.columns else ("mes_ano", "size"),
            completadas=("numero_de_corridas_completadas", "sum") if "numero_de_corridas_completadas" in df_ano_ref.columns else ("mes_ano", "size"),
            segundos=("segundos_abs", "sum") if "segundos_abs" in df_ano_ref.columns else ("mes_ano", "size"),
            entregadores=("pessoa_entregadora", "nunique") if "pessoa_entregadora" in df_ano_ref.columns else ("mes_ano", "size"),
        )
    )

    df_mensal["horas"] = pd.to_numeric(df_mensal["segundos"], errors="coerce").fillna(0).clip(lower=0) / 3600.0
    df_mensal["utr_abs"] = (df_mensal["ofertadas"] / df_mensal["horas"]).where(df_mensal["horas"] > 0, 0.0)

    # UTR médias (mesmo padrão do seu projeto)
    try:
        df_utr_medias = utr_por_entregador_turno(df_ano_ref.copy())
        # df_utr_medias deve ter colunas mes_ano e utr_por_entregador_turno (dependendo do seu relatorios.py)
        if "mes_ano" in df_utr_medias.columns:
            if "utr_por_entregador_turno" in df_utr_medias.columns:
                df_utr_medias = df_utr_medias.groupby("mes_ano", as_index=False).agg(utr_medias=("utr_por_entregador_turno", "mean"))
            elif "utr" in df_utr_medias.columns:
                df_utr_medias = df_utr_medias.groupby("mes_ano", as_index=False).agg(utr_medias=("utr", "mean"))
            else:
                df_utr_medias["utr_medias"] = 0.0
        else:
            df_utr_medias = pd.DataFrame({"mes_ano": df_mensal["mes_ano"], "utr_medias": 0.0})
    except Exception:
        df_utr_medias = pd.DataFrame({"mes_ano": df_mensal["mes_ano"], "utr_medias": 0.0})

    df_mensal = df_mensal.merge(df_utr_medias, on="mes_ano", how="left")
    df_mensal["utr_medias"] = pd.to_numeric(df_mensal.get("utr_medias", 0), errors="coerce").fillna(0)

    # --- agregados diários (mês selecionado)
    df_diario = (
        df_mes_ref.groupby(df_mes_ref["data"].dt.date, as_index=False)
        .agg(
            ofertadas=("numero_de_corridas_ofertadas", "sum") if "numero_de_corridas_ofertadas" in df_mes_ref.columns else ("data", "size"),
            aceitas=("numero_de_corridas_aceitas", "sum") if "numero_de_corridas_aceitas" in df_mes_ref.columns else ("data", "size"),
            rejeitadas=("numero_de_corridas_rejeitadas", "sum") if "numero_de_corridas_rejeitadas" in df_mes_ref.columns else ("data", "size"),
            completadas=("numero_de_corridas_completadas", "sum") if "numero_de_corridas_completadas" in df_mes_ref.columns else ("data", "size"),
            segundos=("segundos_abs", "sum") if "segundos_abs" in df_mes_ref.columns else ("data", "size"),
            entregadores=("pessoa_entregadora", "nunique") if "pessoa_entregadora" in df_mes_ref.columns else ("data", "size"),
        )
    )
    df_diario = df_diario.rename(columns={"data": "dia"}).copy()
    df_diario["dia"] = pd.to_datetime(df_diario["dia"])
    df_diario["horas"] = pd.to_numeric(df_diario["segundos"], errors="coerce").fillna(0).clip(lower=0) / 3600.0
    df_diario["utr"] = (df_diario["ofertadas"] / df_diario["horas"]).where(df_diario["horas"] > 0, 0.0)

    # taxas
    df_diario["acc_pct"] = (df_diario["aceitas"] / df_diario["ofertadas"] * 100).where(df_diario["ofertadas"] > 0, 0.0)
    df_diario["rej_pct"] = (df_diario["rejeitadas"] / df_diario["ofertadas"] * 100).where(df_diario["ofertadas"] > 0, 0.0)
    df_diario["comp_pct"] = (df_diario["completadas"] / df_diario["aceitas"] * 100).where(df_diario["aceitas"] > 0, 0.0)

    # =========================
    # Render dos gráficos (mensal + diário)
    # =========================

    def _plot_mensal(y_col: str, y_title: str, title: str, text_col=None):
        fig = px.bar(
            df_mensal,
            x="mes_ano",
            y=y_col,
            text=text_col,
            title=title,
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        if text_col is not None:
            fig.update_traces(texttemplate="<b>%{text}</b>", textposition="outside", cliponaxis=False)
        fig.update_layout(margin=dict(t=60, b=40, l=40, r=40), yaxis_title=y_title, xaxis_title="Mês/Ano")
        st.plotly_chart(fig, use_container_width=True)

    def _plot_diario(y_col: str, y_title: str, title: str, text_series=None):
        fig2 = px.bar(
            df_diario,
            x=df_diario["dia"].dt.day,
            y=y_col,
            title=title,
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        if text_series is not None:
            fig2.update_traces(text=text_series, texttemplate="<b>%{text}</b>", textposition="outside", cliponaxis=False)
        fig2.update_layout(
            margin=dict(t=60, b=40, l=40, r=40),
            xaxis_title="Dia",
            yaxis_title=y_title,
            xaxis=dict(tickmode="linear", dtick=1),  # dias 1,2,3...
        )
        st.plotly_chart(fig2, use_container_width=True)

    # --- Corridas ofertadas (com UTR no mensal)
    if tipo_grafico == "Corridas ofertadas":
        st.markdown("### Corridas ofertadas por mês")
        if utr_modo == "Médias":
            # mostra ofertadas e UTR médias no texto
            df_mensal["text_ofe"] = df_mensal.apply(lambda r: f"{int(r['ofertadas'])} ({r['utr_medias']:.2f} UTR)", axis=1)
            _plot_mensal("ofertadas", "Corridas", "Corridas ofertadas por mês", text_col="text_ofe")
        else:
            df_mensal["text_ofe"] = df_mensal.apply(lambda r: f"{int(r['ofertadas'])} ({r['utr_abs']:.2f} UTR)", axis=1)
            _plot_mensal("ofertadas", "Corridas", "Corridas ofertadas por mês", text_col="text_ofe")

        st.markdown("### Corridas ofertadas por dia")
        df_diario["text_ofe_d"] = df_diario.apply(lambda r: f"{int(r['ofertadas'])} ({r['utr']:.2f} UTR)", axis=1)
        _plot_diario("ofertadas", "Corridas", f"Corridas ofertadas — {mes_diario:02d}/{ano_diario}", text_series=df_diario["text_ofe_d"])

    # --- Aceitas / Rejeitadas / Completadas com modo Quantidade vs %
    elif tipo_grafico == "Corridas aceitas":
        st.markdown("### Corridas aceitas por mês")
        df_mensal["acc_pct"] = (df_mensal["aceitas"] / df_mensal["ofertadas"] * 100).where(df_mensal["ofertadas"] > 0, 0.0)

        if modo_taxa == "%":
            df_mensal["text_acc"] = df_mensal.apply(lambda r: f"{r['acc_pct']:.1f}% ({int(r['aceitas'])})", axis=1)
            _plot_mensal("acc_pct", "Taxa (%)", "Taxa de aceite por mês", text_col="text_acc")
        else:
            df_mensal["text_acc"] = df_mensal.apply(lambda r: f"{int(r['aceitas'])} ({r['acc_pct']:.1f}%)", axis=1)
            _plot_mensal("aceitas", "Corridas", "Corridas aceitas por mês", text_col="text_acc")

        st.markdown("### Corridas aceitas por dia")
        if modo_taxa == "%":
            df_diario["text_acc_d"] = df_diario.apply(lambda r: f"{r['acc_pct']:.1f}% ({int(r['aceitas'])})", axis=1)
            _plot_diario("acc_pct", "Taxa (%)", f"Taxa de aceite — {mes_diario:02d}/{ano_diario}", text_series=df_diario["text_acc_d"])
        else:
            df_diario["text_acc_d"] = df_diario.apply(lambda r: f"{int(r['aceitas'])} ({r['acc_pct']:.1f}%)", axis=1)
            _plot_diario("aceitas", "Corridas", f"Corridas aceitas — {mes_diario:02d}/{ano_diario}", text_series=df_diario["text_acc_d"])

    elif tipo_grafico == "Corridas rejeitadas":
        st.markdown("### Corridas rejeitadas por mês")
        df_mensal["rej_pct"] = (df_mensal["rejeitadas"] / df_mensal["ofertadas"] * 100).where(df_mensal["ofertadas"] > 0, 0.0)

        if modo_taxa == "%":
            df_mensal["text_rej"] = df_mensal.apply(lambda r: f"{r['rej_pct']:.1f}% ({int(r['rejeitadas'])})", axis=1)
            _plot_mensal("rej_pct", "Taxa (%)", "Taxa de rejeição por mês", text_col="text_rej")
        else:
            df_mensal["text_rej"] = df_mensal.apply(lambda r: f"{int(r['rejeitadas'])} ({r['rej_pct']:.1f}%)", axis=1)
            _plot_mensal("rejeitadas", "Corridas", "Corridas rejeitadas por mês", text_col="text_rej")

        st.markdown("### Corridas rejeitadas por dia")
        if modo_taxa == "%":
            df_diario["text_rej_d"] = df_diario.apply(lambda r: f"{r['rej_pct']:.1f}% ({int(r['rejeitadas'])})", axis=1)
            _plot_diario("rej_pct", "Taxa (%)", f"Taxa de rejeição — {mes_diario:02d}/{ano_diario}", text_series=df_diario["text_rej_d"])
        else:
            df_diario["text_rej_d"] = df_diario.apply(lambda r: f"{int(r['rejeitadas'])} ({r['rej_pct']:.1f}%)", axis=1)
            _plot_diario("rejeitadas", "Corridas", f"Corridas rejeitadas — {mes_diario:02d}/{ano_diario}", text_series=df_diario["text_rej_d"])

    elif tipo_grafico == "Corridas completadas":
        st.markdown("### Corridas completadas por mês")
        df_mensal["comp_pct"] = (df_mensal["completadas"] / df_mensal["aceitas"] * 100).where(df_mensal["aceitas"] > 0, 0.0)

        if modo_taxa == "%":
            df_mensal["text_com"] = df_mensal.apply(lambda r: f"{r['comp_pct']:.1f}% ({int(r['completadas'])})", axis=1)
            _plot_mensal("comp_pct", "Taxa (%)", "Taxa de conclusão por mês", text_col="text_com")
        else:
            df_mensal["text_com"] = df_mensal.apply(lambda r: f"{int(r['completadas'])} ({r['comp_pct']:.1f}%)", axis=1)
            _plot_mensal("completadas", "Corridas", "Corridas completadas por mês", text_col="text_com")

        st.markdown("### Corridas completadas por dia")
        if modo_taxa == "%":
            df_diario["text_com_d"] = df_diario.apply(lambda r: f"{r['comp_pct']:.1f}% ({int(r['completadas'])})", axis=1)
            _plot_diario("comp_pct", "Taxa (%)", f"Taxa de conclusão — {mes_diario:02d}/{ano_diario}", text_series=df_diario["text_com_d"])
        else:
            df_diario["text_com_d"] = df_diario.apply(lambda r: f"{int(r['completadas'])} ({r['comp_pct']:.1f}%)", axis=1)
            _plot_diario("completadas", "Corridas", f"Corridas completadas — {mes_diario:02d}/{ano_diario}", text_series=df_diario["text_com_d"])

    # --- Horas realizadas
    elif tipo_grafico == "Horas realizadas":
        st.markdown("### Horas realizadas por mês")
        df_mensal["text_h"] = df_mensal["horas"].map(lambda v: f"{v:.1f}h")
        _plot_mensal("horas", "Horas", "Horas realizadas por mês", text_col="text_h")

        st.markdown("### Horas realizadas por dia")
        df_diario["text_h_d"] = df_diario["horas"].map(lambda v: f"{v:.1f}h")
        _plot_diario("horas", "Horas", f"Horas realizadas — {mes_diario:02d}/{ano_diario}", text_series=df_diario["text_h_d"])

    # --- Entregadores ativos
    elif tipo_grafico == "Entregadores ativos":
        st.markdown("### Entregadores ativos por mês")
        df_mensal["text_e"] = df_mensal["entregadores"].map(lambda v: f"{int(v)}")
        _plot_mensal("entregadores", "Entregadores", "Entregadores ativos por mês", text_col="text_e")

        st.markdown("### Entregadores ativos por dia")
        df_diario["text_e_d"] = df_diario["entregadores"].map(lambda v: f"{int(v)}")
        _plot_diario("entregadores", "Entregadores", f"Entregadores ativos — {mes_diario:02d}/{ano_diario}", text_series=df_diario["text_e_d"])

    # --- Aderência (%)
    elif tipo_grafico == "Aderência (%)":
        st.markdown("### Aderência por mês")
        grp = ("data", turno_col) if turno_col is not None else ("data",)
        base_ad = calcular_aderencia(df_ano_ref.copy(), group_cols=grp)
        base_ad["mes_ano"] = pd.to_datetime(base_ad["data"]).dt.strftime("%m/%Y")
        ad_m = base_ad.groupby("mes_ano", as_index=False).agg(vagas=("vagas", "sum"), reg=("regulares_atuaram", "sum"))
        ad_m["ader"] = (ad_m["reg"] / ad_m["vagas"] * 100.0).where(ad_m["vagas"] > 0, 0.0)
        ad_m["text"] = ad_m["ader"].map(lambda v: f"{v:.1f}%")
        fig = px.bar(
            ad_m,
            x="mes_ano",
            y="ader",
            text="text",
            title="Aderência (%) por mês",
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig.update_traces(texttemplate="<b>%{text}</b>", textposition="outside", cliponaxis=False)
        fig.update_layout(margin=dict(t=60, b=40, l=40, r=40), yaxis_title="Aderência (%)", xaxis_title="Mês/Ano")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Aderência por dia")
        base_ad_m = calcular_aderencia(df_mes_ref.copy(), group_cols=grp)
        base_ad_m["dia"] = pd.to_datetime(base_ad_m["data"])
        base_ad_m["text"] = base_ad_m["aderencia"].map(lambda v: f"{v:.1f}%")
        fig2 = px.bar(
            base_ad_m,
            x=base_ad_m["dia"].dt.day,
            y="aderencia",
            text="text",
            title=f"Aderência (%) — {mes_diario:02d}/{ano_diario}",
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig2.update_traces(texttemplate="<b>%{text}</b>", textposition="outside", cliponaxis=False)
        fig2.update_layout(
            margin=dict(t=60, b=40, l=40, r=40),
            xaxis_title="Dia",
            yaxis_title="Aderência (%)",
            xaxis=dict(tickmode="linear", dtick=1),
        )
        st.plotly_chart(fig2, use_container_width=True)
