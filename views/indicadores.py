import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from relatorios import utr_por_entregador_turno
from shared import sub_options_with_livre, apply_sub_filter
from utils import calcular_aderencia, tempo_para_segundos


# =========================
# Estilo / Paletas
# =========================
PRIMARY_COLOR = ["#00BFFF"]

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


# =========================
# Helpers
# =========================
def _clean_sub_praca_inplace(dfx: pd.DataFrame) -> pd.DataFrame:
    """Deixa sub_praca decente: '', 'nan', 'null' viram NA (pra 'LIVRE' funcionar direito)."""
    if "sub_praca" not in dfx.columns:
        return dfx
    s = dfx["sub_praca"].astype("object")
    s = s.map(lambda x: x.strip() if isinstance(x, str) else x)
    s = s.replace("", pd.NA)
    s = s.map(lambda x: pd.NA if isinstance(x, str) and x.strip().lower() in ("nan", "null", "none", "na") else x)
    dfx["sub_praca"] = s
    return dfx


def _ensure_time_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Garante data/mes/ano/mes_ano + segundos_abs numérico."""
    dfx = df.copy()

    # data
    if "data" not in dfx.columns:
        dfx["data"] = pd.to_datetime(dfx.get("data_do_periodo", dfx.get("data")), errors="coerce")
    else:
        dfx["data"] = pd.to_datetime(dfx["data"], errors="coerce")

    # mes/ano
    if "mes" not in dfx.columns:
        dfx["mes"] = dfx["data"].dt.month.astype("Int64")
    else:
        dfx["mes"] = pd.to_numeric(dfx["mes"], errors="coerce").astype("Int64")

    if "ano" not in dfx.columns:
        dfx["ano"] = dfx["data"].dt.year.astype("Int64")
    else:
        dfx["ano"] = pd.to_numeric(dfx["ano"], errors="coerce").astype("Int64")

    # mes_ano (timestamp do 1º dia)
    if "mes_ano" not in dfx.columns:
        dfx["mes_ano"] = dfx["data"].dt.to_period("M").dt.to_timestamp()

    # segundos_abs (fallback: tempo_disponivel_absoluto)
    if "segundos_abs" not in dfx.columns:
        if "tempo_disponivel_absoluto" in dfx.columns:
            dfx["segundos_abs"] = dfx["tempo_disponivel_absoluto"].apply(tempo_para_segundos)
        else:
            dfx["segundos_abs"] = 0

    dfx["segundos_abs"] = pd.to_numeric(dfx["segundos_abs"], errors="coerce").fillna(0).clip(lower=0)

    # colunas de corridas (pra não quebrar groupby)
    for c in (
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
    ):
        if c not in dfx.columns:
            dfx[c] = 0

    if "pessoa_entregadora" not in dfx.columns:
        dfx["pessoa_entregadora"] = pd.NA

    dfx = _clean_sub_praca_inplace(dfx)
    return dfx


def _utr_media_mensal(df_base: pd.DataFrame, mes: int, ano: int) -> float:
    """
    UTR 'Médias' por mês: média de UTR (por pessoa+turno+dia) com supply_hours>0.
    """
    try:
        base = utr_por_entregador_turno(df_base, mes, ano)
    except Exception:
        return 0.0
    if base is None or base.empty:
        return 0.0
    if "supply_hours" not in base.columns:
        return 0.0
    base = base[pd.to_numeric(base["supply_hours"], errors="coerce").fillna(0) > 0].copy()
    if base.empty:
        return 0.0
    # relatorios.py já calcula UTR na coluna "UTR"
    if "UTR" in base.columns:
        return float(pd.to_numeric(base["UTR"], errors="coerce").fillna(0).mean())
    # fallback
    if ("corridas_ofertadas" in base.columns) and ("supply_hours" in base.columns):
        return float((base["corridas_ofertadas"] / base["supply_hours"]).mean())
    return 0.0


# =========================
# Semanal (modo clean)
# =========================
def _render_comparar_semanas(df_day: pd.DataFrame, y_col: str, yaxis_title: str, chart_title: str, key_prefix: str):
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

    with st.expander("Semanas", expanded=False):
        sel = st.multiselect(
            "Semanas (início na segunda-feira):",
            options=all_labels,
            default=all_labels,  # TODAS por padrão
            key=f"{key_prefix}_weeks",
            label_visibility="collapsed",
        )

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
    df_cmp_ref: pd.DataFrame,
    month_start: pd.Timestamp,
    month_end: pd.Timestamp,
    mes_ref: int,
    ano_ref: int,
    turno_col,
):
    """
    Tela semanal:
      - Seg..Dom (dia a dia) com várias semanas (linhas)
      - Semana 1,2,3... (total) em barras
    """
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

    df_scope = df_cmp_ref.dropna(subset=["data"]).copy()
    if df_scope.empty:
        st.info("Sem dados no período selecionado pra montar o semanal.")
        return

    # ---------------- Aderência ----------------
    if indicador == "Aderência (%)":
        if ("numero_minimo_de_entregadores_regulares_na_escala" not in df_scope.columns) or ("tag" not in df_scope.columns):
            st.info("Aderência precisa das colunas 'numero_minimo_de_entregadores_regulares_na_escala' e 'tag'.")
            return

        grp = ("data", turno_col) if turno_col is not None else ("data",)
        try:
            base_ap = calcular_aderencia(df_scope.copy(), group_cols=grp)
        except Exception as e:
            st.info(f"Não deu pra calcular aderência: {e}")
            return

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
        y_wk = "aderencia_pct"
        yaxis = "Aderência (%)"
        text_wk = por_semana["aderencia_pct"].map(lambda v: f"{v:.1f}%")

        title_cmp = f"Comparação semanal (Seg–Dom) — {yaxis}"
        title_wk = f"Totais por semana (Seg–Dom) — {mes_ref:02d}/{ano_ref}"

    # ---------------- Corridas / Horas / Entregadores ----------------
    else:
        tmp = df_scope.copy()
        tmp["date"] = pd.to_datetime(tmp["data"]).dt.normalize()
        tmp["weekday"] = tmp["date"].dt.weekday
        tmp["weekday_label"] = tmp["weekday"].map(WEEKDAY_LABELS)
        tmp["week_start"] = tmp["date"] - pd.to_timedelta(tmp["weekday"], unit="D")
        tmp["week_end"] = tmp["week_start"] + pd.Timedelta(days=6)

        tmp = tmp[(tmp["week_end"] >= month_start) & (tmp["week_start"] <= month_end)].copy()
        if tmp.empty:
            st.info("Sem semanas disponíveis (com esse mês/ano) pra comparar.")
            return

        por_data_cmp = (
            tmp.groupby(["week_start", "weekday_label"], as_index=False)
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
            tmp.groupby("week_start", as_index=False)
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

        if indicador == "Corridas ofertadas":
            wk_metric = st.radio("Métrica", ["Corridas", "UTR"], index=0, horizontal=True, key=f"wk_metric_{mes_ref}_{ano_ref}")
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
def render(df: pd.DataFrame, _USUARIOS=None):
    st.title("Indicadores Gerais")

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    df = _ensure_time_cols(df)
    df = df.dropna(subset=["data"]).copy()

    # ---------------- Tipo de gráfico (inclui semanal) ----------------
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

    # Só para o MENSAL de ofertadas (fora do semanal)
    utr_modo = None
    if tipo_grafico == "Corridas ofertadas":
        utr_modo = st.radio(
            "UTR no mensal",
            ["Absoluto", "Médias"],
            index=0,
            horizontal=True,
            help="Como calcular a UTR exibida no gráfico MENSAL de ofertadas.",
        )

    # Para aceitas/rejeitadas/completadas: quantidade vs %
    modo_taxa = None
    if tipo_grafico in ("Corridas aceitas", "Corridas rejeitadas", "Corridas completadas"):
        modo_taxa = st.radio(
            "Modo",
            ["Quantidade", "%"],
            index=0,
            horizontal=True,
            help="Quantidade: mostra corridas (com % no texto).  %: mostra a taxa (com quantidade no texto).",
        )

    # ---------------- Filtros ----------------
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])

    praca_scope = "SAO PAULO"
    sub_opts = sub_options_with_livre(df, praca_scope=praca_scope)
    sub_sel = col_f1.multiselect("Subpraça", sub_opts)
    df = apply_sub_filter(df, sub_sel, praca_scope=praca_scope)

    turno_col = next((c for c in ("turno", "tipo_turno", "periodo") if c in df.columns), None)
    if turno_col is not None:
        op_turno = ["Todos"] + sorted(df[turno_col].dropna().unique().tolist())
        turno_sel = col_f2.selectbox("Turno", op_turno, index=0)
        if turno_sel != "Todos":
            df = df[df[turno_col] == turno_sel].copy()

    ent_opts = sorted(df["pessoa_entregadora"].dropna().unique().tolist())
    ent_sel = col_f3.multiselect("Entregador(es)", ent_opts)
    if ent_sel:
        df = df[df["pessoa_entregadora"].isin(ent_sel)].copy()

    if df.empty:
        st.warning("Sem dados com esses filtros.")
        return

    # ---------------- Mês/Ano do diário ----------------
    ultimo_ts = pd.to_datetime(df["mes_ano"]).max()
    default_mes = int(ultimo_ts.month) if pd.notna(ultimo_ts) else int(pd.to_datetime(df["data"]).dt.month.max())
    default_ano = int(ultimo_ts.year) if pd.notna(ultimo_ts) else int(pd.to_datetime(df["data"]).dt.year.max())

    anos_disp = sorted([int(x) for x in df["ano"].dropna().unique().tolist()], reverse=True) or [default_ano]

    col_p1, col_p2 = st.columns(2)
    mes_diario = col_p1.selectbox("Mês (gráfico diário)", list(range(1, 13)), index=max(0, default_mes - 1))
    ano_idx = anos_disp.index(default_ano) if default_ano in anos_disp else 0
    ano_diario = col_p2.selectbox("Ano (gráfico diário)", anos_disp, index=ano_idx)

    # ---------------- Slices de tempo ----------------
    df_mes_ref = df[(df["mes"] == mes_diario) & (df["ano"] == ano_diario)].copy()
    df_ano_ref = df[df["ano"] == ano_diario].copy()

    month_start = pd.Timestamp(int(ano_diario), int(mes_diario), 1)
    month_end = month_start + pd.offsets.MonthEnd(1)

    # base estendida só pro semanal (semana completa)
    cmp_start = month_start - pd.Timedelta(days=6)
    cmp_end = month_end + pd.Timedelta(days=6)
    df_cmp_ref = df[(df["data"] >= cmp_start) & (df["data"] <= cmp_end)].copy()

    # ---------------- Modo semanal ----------------
    if tipo_grafico == "Comparativo semanal":
        _render_modo_semanal(
            df_cmp_ref=df_cmp_ref,
            month_start=month_start,
            month_end=month_end,
            mes_ref=mes_diario,
            ano_ref=ano_diario,
            turno_col=turno_col,
        )
        return

    # ---------------- Resumo anual (só fora do semanal) ----------------
    def _render_resumo_ano():
        tot_ofert = df_ano_ref["numero_de_corridas_ofertadas"].sum()
        tot_aceit = df_ano_ref["numero_de_corridas_aceitas"].sum()
        tot_rej = df_ano_ref["numero_de_corridas_rejeitadas"].sum()
        tot_comp = df_ano_ref["numero_de_corridas_completadas"].sum()

        tx_aceit_ano = (tot_aceit / tot_ofert * 100) if tot_ofert > 0 else 0.0
        tx_rej_ano = (tot_rej / tot_ofert * 100) if tot_ofert > 0 else 0.0
        tx_comp_ano = (tot_comp / tot_aceit * 100) if tot_aceit > 0 else 0.0

        tot_sh = int(df_ano_ref["pessoa_entregadora"].dropna().nunique())
        tot_horas = df_ano_ref["segundos_abs"].sum() / 3600.0

        st.divider()
        st.markdown("### 📅 Números gerais do ano selecionado")
        st.markdown(
            (
                "<div style='font-size:1.1rem; line-height:1.7; margin-top:0.5em;'>"
                f"<b>Ofertadas:</b> {int(tot_ofert):,}<br>"
                f"<b>Aceitas:</b> {int(tot_aceit):,} ({tx_aceit_ano:.1f}%)<br>"
                f"<b>Rejeitadas:</b> {int(tot_rej):,} ({tx_rej_ano:.1f}%)<br>"
                f"<b>Completadas:</b> {int(tot_comp):,} ({tx_comp_ano:.1f}%)<br>"
                f"<b>Ativos (SH):</b> {int(tot_sh):,}<br>"
                f"<b>Horas realizadas:</b> {tot_horas:.1f} h"
                "</div>"
            ).replace(",", "."),
            unsafe_allow_html=True,
        )

    # =========================
    # Aderência (%)
    # =========================
    if tipo_grafico == "Aderência (%)":
        if ("numero_minimo_de_entregadores_regulares_na_escala" not in df.columns) or ("tag" not in df.columns):
            st.info("Esse indicador precisa das colunas 'numero_minimo_de_entregadores_regulares_na_escala' e 'tag'.")
            _render_resumo_ano()
            return

        grp = ("data", turno_col) if turno_col is not None else ("data",)

        base_ap = calcular_aderencia(df.dropna(subset=["data"]).copy(), group_cols=grp)
        base_ap["mes_ano"] = pd.to_datetime(base_ap["data"]).dt.to_period("M").dt.to_timestamp()
        base_ap["mes_rotulo"] = pd.to_datetime(base_ap["mes_ano"]).dt.strftime("%b/%y")

        mensal = (
            base_ap.groupby(["mes_ano", "mes_rotulo"], as_index=False)
            .agg(vagas=("vagas", "sum"), regulares=("regulares_atuaram", "sum"))
            .sort_values("mes_ano")
        )
        mensal["aderencia_pct"] = mensal.apply(lambda r: (r["regulares"] / r["vagas"] * 100.0) if r["vagas"] else 0.0, axis=1)

        fig_m = px.bar(
            mensal,
            x="mes_rotulo",
            y="aderencia_pct",
            text=mensal["aderencia_pct"].map(lambda v: f"{v:.1f}%"),
            title="Aderência (REGULAR / vagas) por mês",
            labels={"mes_rotulo": "Mês/Ano", "aderencia_pct": "Aderência (%)"},
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig_m.update_traces(textposition="outside")
        fig_m.update_layout(margin=dict(t=60, b=30, l=40, r=40))
        st.plotly_chart(fig_m, use_container_width=True)

        if not df_mes_ref.empty:
            base_ap_mes = calcular_aderencia(df_mes_ref.dropna(subset=["data"]).copy(), group_cols=grp)
            base_ap_mes["dia"] = pd.to_datetime(base_ap_mes["data"]).dt.day
            por_dia = (
                base_ap_mes.groupby("dia", as_index=False)
                .agg(vagas=("vagas", "sum"), regulares=("regulares_atuaram", "sum"))
                .sort_values("dia")
            )
            por_dia["aderencia_pct"] = por_dia.apply(lambda r: (r["regulares"] / r["vagas"] * 100.0) if r["vagas"] else 0.0, axis=1)

            fig_d = go.Figure()
            fig_d.add_bar(
                x=por_dia["dia"],
                y=por_dia["aderencia_pct"],
                text=por_dia["aderencia_pct"].map(lambda v: f"{v:.1f}%"),
                textposition="outside",
                marker=dict(color=PRIMARY_COLOR[0]),
                name="Aderência",
            )
            fig_d.update_layout(
                title=f"📊 Aderência por dia ({mes_diario:02d}/{ano_diario})",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia",
                yaxis_title="Aderência (%)",
                xaxis=dict(tickmode="linear", dtick=1),
            )
            st.plotly_chart(fig_d, use_container_width=True)
        else:
            st.info("Sem dados no mês selecionado.")

        _render_resumo_ano()
        return

    # =========================
    # Horas realizadas
    # =========================
    if tipo_grafico == "Horas realizadas":
        mensal_horas = (
            df.groupby("mes_ano", as_index=False)["segundos_abs"].sum()
            .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
        )
        mensal_horas["mes_rotulo"] = pd.to_datetime(mensal_horas["mes_ano"]).dt.strftime("%b/%y")

        fig_m = px.bar(
            mensal_horas,
            x="mes_rotulo",
            y="horas",
            text=mensal_horas["horas"].map(lambda v: f"{v:.1f}h"),
            title="Horas realizadas por mês",
            labels={"mes_rotulo": "Mês/Ano", "horas": "Horas"},
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig_m.update_traces(texttemplate="<b>%{text}</b>", textposition="outside")
        fig_m.update_layout(margin=dict(t=60, b=30, l=40, r=40))
        st.plotly_chart(fig_m, use_container_width=True)

        if not df_mes_ref.empty:
            por_dia = (
                df_mes_ref.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                .groupby("dia", as_index=False)["segundos_abs"].sum()
                .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
                .sort_values("dia")
            )
            fig_d = go.Figure()
            fig_d.add_bar(
                x=por_dia["dia"],
                y=por_dia["horas"],
                text=por_dia["horas"].map(lambda v: f"{v:.1f}h"),
                textposition="outside",
                marker=dict(color=PRIMARY_COLOR[0]),
                name="Horas",
            )
            fig_d.update_layout(
                title=f"📊 Horas por dia ({mes_diario:02d}/{ano_diario})",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia",
                yaxis_title="Horas",
                xaxis=dict(tickmode="linear", dtick=1),
            )
            st.plotly_chart(fig_d, use_container_width=True)
        else:
            st.info("Sem dados no mês selecionado.")

        _render_resumo_ano()
        return

    # =========================
    # Entregadores ativos
    # =========================
    if tipo_grafico == "Entregadores ativos":
        mensal = (
            df.groupby("mes_ano", as_index=False)["pessoa_entregadora"].nunique()
            .rename(columns={"pessoa_entregadora": "entregadores"})
        )
        mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

        fig = px.bar(
            mensal,
            x="mes_rotulo",
            y="entregadores",
            text=mensal["entregadores"].astype(int).astype(str),
            title="Entregadores ativos por mês",
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig.update_traces(texttemplate="<b>%{text}</b>", textposition="outside")
        fig.update_layout(margin=dict(t=60, b=30, l=40, r=40))
        st.plotly_chart(fig, use_container_width=True)

        if not df_mes_ref.empty:
            por_dia = (
                df_mes_ref.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                .groupby("dia", as_index=False)["pessoa_entregadora"].nunique()
                .rename(columns={"pessoa_entregadora": "entregadores"})
                .sort_values("dia")
            )
            fig2 = go.Figure()
            fig2.add_bar(
                x=por_dia["dia"],
                y=por_dia["entregadores"],
                text=por_dia["entregadores"].astype(int).astype(str),
                textposition="outside",
                marker=dict(color=PRIMARY_COLOR[0]),
                name="Entregadores",
            )
            fig2.update_layout(
                title=f"📊 Entregadores por dia ({mes_diario:02d}/{ano_diario})",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia",
                yaxis_title="Entregadores",
                xaxis=dict(tickmode="linear", dtick=1),
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados no mês selecionado.")

        _render_resumo_ano()
        return

    # =========================
    # Corridas (genéricos)
    # =========================
    col_map = {
        "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Corridas"),
        "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas"),
        "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas"),
        "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas"),
    }
    col, titulo, label = col_map[tipo_grafico]

    mensal = df.groupby("mes_ano", as_index=False)[col].sum().rename(columns={col: "valor"})
    mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

    if tipo_grafico == "Corridas ofertadas":
        secs_mensal = df.groupby("mes_ano", as_index=False)["segundos_abs"].sum().rename(columns={"segundos_abs": "segundos"})
        mensal = mensal.merge(secs_mensal, on="mes_ano", how="left")
        mensal["segundos"] = pd.to_numeric(mensal.get("segundos", 0), errors="coerce").fillna(0)
        mensal["horas"] = mensal["segundos"] / 3600.0

        if utr_modo == "Médias":
            mensal["utr"] = mensal["mes_ano"].apply(lambda ts: _utr_media_mensal(df, int(pd.to_datetime(ts).month), int(pd.to_datetime(ts).year)))
        else:
            mensal["utr"] = mensal.apply(lambda r: (r["valor"] / r["horas"]) if r["horas"] > 0 else 0.0, axis=1)

        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['utr']:.2f} UTR)", axis=1)
        y_mensal = "valor"
        titulo_m = titulo

    elif tipo_grafico == "Corridas aceitas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(columns={"numero_de_corridas_ofertadas": "ref"})
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        if modo_taxa == "%":
            mensal["label"] = mensal.apply(lambda r: f"{r['pct']:.1f}% ({int(r['valor'])})", axis=1)
            y_mensal = "pct"
            titulo_m = "Taxa de aceite por mês"
            label = "Taxa (%)"
        else:
            mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1)
            y_mensal = "valor"
            titulo_m = titulo

    elif tipo_grafico == "Corridas rejeitadas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(columns={"numero_de_corridas_ofertadas": "ref"})
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        if modo_taxa == "%":
            mensal["label"] = mensal.apply(lambda r: f"{r['pct']:.1f}% ({int(r['valor'])})", axis=1)
            y_mensal = "pct"
            titulo_m = "Taxa de rejeição por mês"
            label = "Taxa (%)"
        else:
            mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1)
            y_mensal = "valor"
            titulo_m = titulo

    else:  # Corridas completadas
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"].sum().rename(columns={"numero_de_corridas_aceitas": "ref"})
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        if modo_taxa == "%":
            mensal["label"] = mensal.apply(lambda r: f"{r['pct']:.1f}% ({int(r['valor'])})", axis=1)
            y_mensal = "pct"
            titulo_m = "Taxa de conclusão por mês"
            label = "Taxa (%)"
        else:
            mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1)
            y_mensal = "valor"
            titulo_m = titulo

    fig = px.bar(
        mensal,
        x="mes_rotulo",
        y=y_mensal,
        text="label",
        title=titulo_m,
        labels={"mes_rotulo": "Mês/Ano", y_mensal: label},
        template="plotly_dark",
        color_discrete_sequence=PRIMARY_COLOR,
    )
    fig.update_traces(texttemplate="<b>%{text}</b>", textposition="outside")
    fig.update_layout(margin=dict(t=60, b=30, l=40, r=40))
    st.plotly_chart(fig, use_container_width=True)

    if df_mes_ref.empty:
        st.info("Sem dados no mês selecionado.")
        _render_resumo_ano()
        return

    por_dia_base = (
        df_mes_ref.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
        .groupby("dia", as_index=False)
        .agg(
            ofe=("numero_de_corridas_ofertadas", "sum"),
            ace=("numero_de_corridas_aceitas", "sum"),
            rej=("numero_de_corridas_rejeitadas", "sum"),
            com=("numero_de_corridas_completadas", "sum"),
            seg=("segundos_abs", "sum"),
            entregadores=("pessoa_entregadora", "nunique"),
        )
        .sort_values("dia")
    )

    por_dia_base["horas"] = por_dia_base["seg"] / 3600.0
    por_dia_base["acc_pct"] = (por_dia_base["ace"] / por_dia_base["ofe"] * 100).where(por_dia_base["ofe"] > 0, 0.0)
    por_dia_base["rej_pct"] = (por_dia_base["rej"] / por_dia_base["ofe"] * 100).where(por_dia_base["ofe"] > 0, 0.0)
    por_dia_base["comp_pct"] = (por_dia_base["com"] / por_dia_base["ace"] * 100).where(por_dia_base["ace"] > 0, 0.0)
    por_dia_base["utr"] = (por_dia_base["ofe"] / por_dia_base["horas"]).where(por_dia_base["horas"] > 0, 0.0)

    if tipo_grafico == "Corridas ofertadas":
        y_bar = por_dia_base["ofe"]
        label_bar = por_dia_base.apply(lambda r: f"{int(r['ofe'])} ({r['utr']:.2f} UTR)", axis=1)
        y_title = "Corridas ofertadas"

    elif tipo_grafico == "Corridas aceitas":
        if modo_taxa == "%":
            y_bar = por_dia_base["acc_pct"]
            label_bar = por_dia_base.apply(lambda r: f"{r['acc_pct']:.1f}% ({int(r['ace'])})", axis=1)
            y_title = "Taxa de aceite (%)"
        else:
            y_bar = por_dia_base["ace"]
            label_bar = por_dia_base.apply(lambda r: f"{int(r['ace'])} ({r['acc_pct']:.1f}%)", axis=1)
            y_title = "Corridas aceitas"

    elif tipo_grafico == "Corridas rejeitadas":
        if modo_taxa == "%":
            y_bar = por_dia_base["rej_pct"]
            label_bar = por_dia_base.apply(lambda r: f"{r['rej_pct']:.1f}% ({int(r['rej'])})", axis=1)
            y_title = "Taxa de rejeição (%)"
        else:
            y_bar = por_dia_base["rej"]
            label_bar = por_dia_base.apply(lambda r: f"{int(r['rej'])} ({r['rej_pct']:.1f}%)", axis=1)
            y_title = "Corridas rejeitadas"

    else:  # Corridas completadas
        if modo_taxa == "%":
            y_bar = por_dia_base["comp_pct"]
            label_bar = por_dia_base.apply(lambda r: f"{r['comp_pct']:.1f}% ({int(r['com'])})", axis=1)
            y_title = "Taxa de conclusão (%)"
        else:
            y_bar = por_dia_base["com"]
            label_bar = por_dia_base.apply(lambda r: f"{int(r['com'])} ({r['comp_pct']:.1f}%)", axis=1)
            y_title = "Corridas completadas"

    fig2 = go.Figure()
    fig2.add_bar(
        x=por_dia_base["dia"],
        y=y_bar,
        text=label_bar,
        textposition="outside",
        name=y_title,
        marker=dict(color=PRIMARY_COLOR[0]),
    )
    fig2.update_layout(
        title=f"📊 {y_title} por dia ({mes_diario:02d}/{ano_diario})",
        template="plotly_dark",
        margin=dict(t=60, b=30, l=40, r=40),
        xaxis_title="Dia",
        yaxis_title=y_title,
        xaxis=dict(tickmode="linear", dtick=1),
    )
    st.plotly_chart(fig2, use_container_width=True)

    _render_resumo_ano()
