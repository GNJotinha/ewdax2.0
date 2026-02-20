import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from relatorios import utr_por_entregador_turno
from shared import sub_options_with_livre, apply_sub_filter
from utils import calcular_aderencia

# =========================
# Cores (vivas) — cicla por semana
# =========================
WEEK_PALETTE = [
    "#00E5FF",  # ciano neon
    "#FF2D55",  # rosa/vermelho neon
    "#39FF14",  # verde neon
    "#FFD60A",  # amarelo forte
    "#BF5AF2",  # roxo neon
    "#FF9F0A",  # laranja forte
    "#64D2FF",  # azul claro forte
    "#FF375F",  # vermelho vivo
]

PRIMARY_COLOR = ["#00E5FF"]


def _clean_sub_praca_inplace(df: pd.DataFrame) -> pd.DataFrame:
    """Deixa sub_praca consistente: trim, '' -> NA, 'nan/null/none/na' -> NA (case-insensitive)."""
    if "sub_praca" not in df.columns:
        return df
    s = df["sub_praca"].astype("object")
    s = s.map(lambda x: x.strip() if isinstance(x, str) else x)
    s = s.replace("", pd.NA)
    s = s.map(
        lambda x: pd.NA
        if isinstance(x, str) and x.strip().lower() in ("none", "null", "nan", "na")
        else x
    )
    df["sub_praca"] = s
    return df


def _week_start(dates: pd.Series) -> pd.Series:
    """Início da semana (segunda-feira)."""
    d = pd.to_datetime(dates, errors="coerce")
    return d - pd.to_timedelta(d.dt.weekday.fillna(0).astype(int), unit="D")


def _colors_by_week(dates: pd.Series) -> list[str]:
    ws = _week_start(dates)
    codes = pd.factorize(ws)[0]
    pal = WEEK_PALETTE
    return [pal[i % len(pal)] if i >= 0 else pal[0] for i in codes]


def _weekday_label(series_dt: pd.Series) -> pd.Series:
    d = pd.to_datetime(series_dt, errors="coerce")
    labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    return d.dt.weekday.map(lambda i: labels[int(i)] if pd.notna(i) else "")


def _add_week_separators(fig: go.Figure, dates: pd.Series):
    """Linha vertical no começo de cada semana (no gráfico diário por DIA DO MÊS)."""
    d = pd.to_datetime(dates, errors="coerce")
    if d.isna().all():
        return
    ws = _week_start(d)
    starts = sorted(pd.Series(ws.dropna().unique()).tolist())
    for s in starts[1:]:
        # x é "dia do mês" (número)
        fig.add_vline(
            x=int(pd.to_datetime(s).day),
            line_width=1,
            line_dash="dot",
            line_color="rgba(255,255,255,0.25)",
        )


def _ensure_time_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Blindagem:
    - garante df['data'] datetime
    - garante df['mes'], df['ano'] (Int64)
    - garante df['mes_ano'] (timestamp do 1º dia do mês)
    """
    dfx = df.copy()

    # 1) data base
    base = None
    if "data_do_periodo" in dfx.columns:
        base = dfx["data_do_periodo"]
    elif "data" in dfx.columns:
        base = dfx["data"]

    dfx["data"] = pd.to_datetime(base, errors="coerce") if base is not None else pd.NaT

    # 2) mes/ano
    if "mes" not in dfx.columns:
        dfx["mes"] = dfx["data"].dt.month.astype("Int64")
    else:
        dfx["mes"] = pd.to_numeric(dfx["mes"], errors="coerce").astype("Int64")

    if "ano" not in dfx.columns:
        dfx["ano"] = dfx["data"].dt.year.astype("Int64")
    else:
        dfx["ano"] = pd.to_numeric(dfx["ano"], errors="coerce").astype("Int64")

    # 3) mes_ano
    dfx["mes_ano"] = dfx["data"].dt.to_period("M").dt.to_timestamp()

    return dfx


def _sanitize_numbers(df: pd.DataFrame) -> pd.DataFrame:
    """Evita cagadas de segundos negativos / NaN."""
    dfx = df.copy()
    if "segundos_abs" in dfx.columns:
        dfx["segundos_abs"] = (
            pd.to_numeric(dfx["segundos_abs"], errors="coerce")
            .fillna(0)
            .clip(lower=0)
        )
    return dfx


def _utr_media_mensal(df: pd.DataFrame, mes: int, ano: int) -> float:
    base = utr_por_entregador_turno(df, mes, ano)
    if base is None or base.empty:
        return 0.0
    base = base[base.get("supply_hours", 0) > 0].copy()
    if base.empty:
        return 0.0
    return float((base["corridas_ofertadas"] / base["supply_hours"]).mean())


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("Indicadores Gerais")

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
        ],
        index=0,
        horizontal=True,
    )

    utr_modo = None
    if tipo_grafico == "Corridas ofertadas":
        utr_modo = st.radio("UTR no mensal", ["Absoluto", "Médias"], index=0, horizontal=True)

    pct_modo = None
    if tipo_grafico in ("Corridas aceitas", "Corridas rejeitadas", "Corridas completadas"):
        pct_modo = st.radio("Modo do gráfico", ["Quantidade", "%"], index=0, horizontal=True)

    comparar_semanas = st.checkbox("Comparar semanas (overlay Seg..Dom)", value=False)

    # ---------------- normalização base ----------------
    df = _ensure_time_cols(df)
    df = _sanitize_numbers(df)
    df = _clean_sub_praca_inplace(df)

    if df["data"].isna().all():
        st.warning("Não encontrei uma coluna de data válida (data_do_periodo/data).")
        return

    # ---------------- filtros ----------------
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])

    sub_opts = sub_options_with_livre(df, praca_scope="SAO PAULO")
    sub_sel = col_f1.multiselect("Subpraça", sub_opts)
    df = apply_sub_filter(df, sub_sel, praca_scope="SAO PAULO")

    # turno (se existir)
    turno_col = next((c for c in ("turno", "tipo_turno", "periodo") if c in df.columns), None)
    if turno_col is not None:
        op_turno = ["Todos"] + sorted(df[turno_col].dropna().unique().tolist())
        turno_sel = col_f2.selectbox("Turno", op_turno, index=0)
        if turno_sel != "Todos":
            df = df[df[turno_col] == turno_sel]

    # entregador (se existir)
    if "pessoa_entregadora" in df.columns:
        ent_opts = sorted(df["pessoa_entregadora"].dropna().unique().tolist())
        ent_sel = col_f3.multiselect("Entregador(es)", ent_opts)
        if ent_sel:
            df = df[df["pessoa_entregadora"].isin(ent_sel)]
    else:
        ent_sel = []
        col_f3.caption("Coluna pessoa_entregadora não encontrada (filtro desativado).")

    if df.empty:
        st.info("Sem dados com esses filtros.")
        return

    # -------------- mês/ano diário --------------
    ultimo_dt = pd.to_datetime(df["data"]).max()
    default_mes = int(ultimo_dt.month) if pd.notna(ultimo_dt) else 1
    default_ano = int(ultimo_dt.year) if pd.notna(ultimo_dt) else 2025

    anos_disp = sorted([int(x) for x in df["ano"].dropna().unique().tolist()], reverse=True) or [default_ano]
    c1, c2 = st.columns(2)
    mes_diario = c1.selectbox("Mês (diário)", list(range(1, 13)), index=max(0, default_mes - 1))
    ano_idx = anos_disp.index(default_ano) if default_ano in anos_disp else 0
    ano_diario = c2.selectbox("Ano (diário)", anos_disp, index=ano_idx)

    df_mes_ref = df[(df["mes"] == mes_diario) & (df["ano"] == ano_diario)].copy()
    df_ano_ref = df[df["ano"] == ano_diario].copy()

    def _render_resumo_ano():
        tot_ofert = df_ano_ref.get("numero_de_corridas_ofertadas", pd.Series(dtype=float)).sum()
        tot_aceit = df_ano_ref.get("numero_de_corridas_aceitas", pd.Series(dtype=float)).sum()
        tot_rej = df_ano_ref.get("numero_de_corridas_rejeitadas", pd.Series(dtype=float)).sum()
        tot_comp = df_ano_ref.get("numero_de_corridas_completadas", pd.Series(dtype=float)).sum()

        tx_aceit_ano = (tot_aceit / tot_ofert * 100) if tot_ofert > 0 else 0.0
        tx_rej_ano = (tot_rej / tot_ofert * 100) if tot_ofert > 0 else 0.0
        tx_comp_ano = (tot_comp / tot_aceit * 100) if tot_aceit > 0 else 0.0

        tot_sh = int(df_ano_ref.get("pessoa_entregadora", pd.Series(dtype=object)).dropna().nunique())
        tot_horas = df_ano_ref.get("segundos_abs", pd.Series(dtype=float)).sum() / 3600.0

        st.divider()
        st.markdown("### Números gerais do ano selecionado")
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
            st.info("Precisa das colunas 'numero_minimo_de_entregadores_regulares_na_escala' e 'tag'.")
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
        mensal["aderencia_pct"] = mensal.apply(
            lambda r: (r["regulares"] / r["vagas"] * 100.0) if r["vagas"] else 0.0,
            axis=1,
        )

        fig_m = px.bar(
            mensal,
            x="mes_rotulo",
            y="aderencia_pct",
            text=mensal["aderencia_pct"].map(lambda v: f"{v:.1f}%"),
            title="Aderência por mês",
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig_m.update_traces(textposition="outside")
        st.plotly_chart(fig_m, use_container_width=True)

        if df_mes_ref.empty:
            st.info("Sem dados no mês selecionado.")
            _render_resumo_ano()
            return

        base_ap_mes = calcular_aderencia(df_mes_ref.dropna(subset=["data"]).copy(), group_cols=grp)

        por_dia = (
            base_ap_mes.assign(data_ref=lambda d: pd.to_datetime(d["data"]))
            .groupby(pd.to_datetime(base_ap_mes["data"]).dt.day, as_index=False)
            .agg(vagas=("vagas", "sum"), regulares=("regulares_atuaram", "sum"), data_ref=("data_ref", "min"))
        )
        por_dia = por_dia.rename(columns={por_dia.columns[0]: "dia"}).sort_values("dia")

        por_dia["aderencia_pct"] = por_dia.apply(
            lambda r: (r["regulares"] / r["vagas"] * 100.0) if r["vagas"] else 0.0,
            axis=1,
        )
        por_dia["week_start"] = _week_start(por_dia["data_ref"])
        por_dia["dow"] = _weekday_label(por_dia["data_ref"])
        por_dia["cor"] = _colors_by_week(por_dia["data_ref"])

        if comparar_semanas:
            num_sem = st.slider("Quantas semanas (no mês)", 2, 8, 4)
            ws_ord = sorted(por_dia["week_start"].dropna().unique())[-num_sem:]
            figw = go.Figure()
            for i, ws in enumerate(ws_ord):
                dws = por_dia[por_dia["week_start"] == ws].copy()
                figw.add_trace(
                    go.Scatter(
                        x=dws["dow"],
                        y=dws["aderencia_pct"],
                        mode="lines+markers",
                        name=pd.to_datetime(ws).strftime("%d/%m"),
                        line=dict(color=WEEK_PALETTE[i % len(WEEK_PALETTE)], width=3),
                    )
                )
            figw.update_layout(
                title=f"Aderência por dia da semana (overlay) - {mes_diario:02d}/{ano_diario}",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia da semana",
                yaxis_title="Aderência (%)",
            )
            st.plotly_chart(figw, use_container_width=True)
        else:
            fig_d = go.Figure()
            fig_d.add_bar(
                x=por_dia["dia"],
                y=por_dia["aderencia_pct"],
                text=por_dia["aderencia_pct"].map(lambda v: f"{v:.1f}%"),
                textposition="outside",
                marker=dict(color=por_dia["cor"], line=dict(width=0.5, color="rgba(255,255,255,0.25)")),
                name="Aderência",
            )
            _add_week_separators(fig_d, por_dia["data_ref"])
            fig_d.update_layout(
                title=f"Aderência por dia ({mes_diario:02d}/{ano_diario})",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia",
                yaxis_title="Aderência (%)",
                xaxis=dict(tickmode="linear", dtick=1),
            )
            st.plotly_chart(fig_d, use_container_width=True)

        _render_resumo_ano()
        return

    # =========================
    # Horas realizadas
    # =========================
    if tipo_grafico == "Horas realizadas":
        if "segundos_abs" not in df.columns:
            st.info("Precisa da coluna 'segundos_abs' para horas realizadas.")
            _render_resumo_ano()
            return

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
            title="Horas por mês",
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig_m.update_traces(textposition="outside")
        st.plotly_chart(fig_m, use_container_width=True)

        if df_mes_ref.empty:
            st.info("Sem dados no mês selecionado.")
            _render_resumo_ano()
            return

        por_dia = (
            df_mes_ref.assign(
                data_ref=lambda d: pd.to_datetime(d["data"]),
                dia=lambda d: pd.to_datetime(d["data"]).dt.day,
            )
            .groupby("dia", as_index=False)
            .agg(seg=("segundos_abs", "sum"), data_ref=("data_ref", "min"))
            .assign(horas=lambda d: d["seg"] / 3600.0)
            .sort_values("dia")
        )
        por_dia["week_start"] = _week_start(por_dia["data_ref"])
        por_dia["dow"] = _weekday_label(por_dia["data_ref"])
        por_dia["cor"] = _colors_by_week(por_dia["data_ref"])

        if comparar_semanas:
            num_sem = st.slider("Quantas semanas (no mês)", 2, 8, 4)
            ws_ord = sorted(por_dia["week_start"].dropna().unique())[-num_sem:]
            figw = go.Figure()
            for i, ws in enumerate(ws_ord):
                dws = por_dia[por_dia["week_start"] == ws].copy()
                figw.add_trace(
                    go.Scatter(
                        x=dws["dow"],
                        y=dws["horas"],
                        mode="lines+markers",
                        name=pd.to_datetime(ws).strftime("%d/%m"),
                        line=dict(color=WEEK_PALETTE[i % len(WEEK_PALETTE)], width=3),
                    )
                )
            figw.update_layout(
                title=f"Horas por dia da semana (overlay) - {mes_diario:02d}/{ano_diario}",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia da semana",
                yaxis_title="Horas",
            )
            st.plotly_chart(figw, use_container_width=True)
        else:
            fig_d = go.Figure()
            fig_d.add_bar(
                x=por_dia["dia"],
                y=por_dia["horas"],
                text=por_dia["horas"].map(lambda v: f"{v:.1f}h"),
                textposition="outside",
                marker=dict(color=por_dia["cor"], line=dict(width=0.5, color="rgba(255,255,255,0.25)")),
                name="Horas",
            )
            _add_week_separators(fig_d, por_dia["data_ref"])
            fig_d.update_layout(
                title=f"Horas por dia ({mes_diario:02d}/{ano_diario})",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia",
                yaxis_title="Horas",
                xaxis=dict(tickmode="linear", dtick=1),
            )
            st.plotly_chart(fig_d, use_container_width=True)

        _render_resumo_ano()
        return

    # =========================
    # Entregadores ativos
    # =========================
    if tipo_grafico == "Entregadores ativos":
        if "pessoa_entregadora" not in df.columns:
            st.info("Precisa da coluna 'pessoa_entregadora' para entregadores ativos.")
            _render_resumo_ano()
            return

        mensal = (
            df.groupby("mes_ano", as_index=False)["pessoa_entregadora"].nunique()
            .rename(columns={"pessoa_entregadora": "entregadores"})
        )
        mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

        fig = px.bar(
            mensal,
            x="mes_rotulo",
            y="entregadores",
            text="entregadores",
            title="Entregadores ativos por mês",
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

        if df_mes_ref.empty:
            st.info("Sem dados no mês selecionado.")
            _render_resumo_ano()
            return

        por_dia = (
            df_mes_ref.assign(
                data_ref=lambda d: pd.to_datetime(d["data"]),
                dia=lambda d: pd.to_datetime(d["data"]).dt.day,
            )
            .groupby("dia", as_index=False)
            .agg(entregadores=("pessoa_entregadora", "nunique"), data_ref=("data_ref", "min"))
            .sort_values("dia")
        )
        por_dia["week_start"] = _week_start(por_dia["data_ref"])
        por_dia["dow"] = _weekday_label(por_dia["data_ref"])
        por_dia["cor"] = _colors_by_week(por_dia["data_ref"])

        if comparar_semanas:
            num_sem = st.slider("Quantas semanas (no mês)", 2, 8, 4)
            ws_ord = sorted(por_dia["week_start"].dropna().unique())[-num_sem:]
            figw = go.Figure()
            for i, ws in enumerate(ws_ord):
                dws = por_dia[por_dia["week_start"] == ws].copy()
                figw.add_trace(
                    go.Scatter(
                        x=dws["dow"],
                        y=dws["entregadores"],
                        mode="lines+markers",
                        name=pd.to_datetime(ws).strftime("%d/%m"),
                        line=dict(color=WEEK_PALETTE[i % len(WEEK_PALETTE)], width=3),
                    )
                )
            figw.update_layout(
                title=f"Entregadores por dia da semana (overlay) - {mes_diario:02d}/{ano_diario}",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia da semana",
                yaxis_title="Entregadores",
            )
            st.plotly_chart(figw, use_container_width=True)
        else:
            fig2 = go.Figure()
            fig2.add_bar(
                x=por_dia["dia"],
                y=por_dia["entregadores"],
                text=por_dia["entregadores"].astype(int).astype(str),
                textposition="outside",
                marker=dict(color=por_dia["cor"], line=dict(width=0.5, color="rgba(255,255,255,0.25)")),
                name="Entregadores",
            )
            _add_week_separators(fig2, por_dia["data_ref"])
            fig2.update_layout(
                title=f"Entregadores por dia ({mes_diario:02d}/{ano_diario})",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia",
                yaxis_title="Entregadores",
                xaxis=dict(tickmode="linear", dtick=1),
            )
            st.plotly_chart(fig2, use_container_width=True)

        _render_resumo_ano()
        return

    # =========================
    # Corridas (ofertadas/aceitas/rejeitadas/completadas)
    # =========================
    col_map = {
        "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Ofertadas"),
        "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Aceitas"),
        "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Rejeitadas"),
        "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Completadas"),
    }
    col, titulo, label = col_map[tipo_grafico]

    # garante colunas mínimas pra não sumir tudo com KeyError
    needed = {col, "numero_de_corridas_ofertadas", "numero_de_corridas_aceitas", "numero_de_corridas_rejeitadas", "numero_de_corridas_completadas"}
    missing = [c for c in needed if c not in df.columns]
    if missing:
        st.info(f"Faltando colunas pra esse gráfico: {', '.join(missing)}")
        _render_resumo_ano()
        return

    mensal = df.groupby("mes_ano", as_index=False)[col].sum().rename(columns={col: "valor"})
    mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

    if tipo_grafico == "Corridas ofertadas":
        secs_mensal = df.groupby("mes_ano", as_index=False)["segundos_abs"].sum().rename(columns={"segundos_abs": "segundos"})
        mensal = mensal.merge(secs_mensal, on="mes_ano", how="left")
        mensal["segundos"] = pd.to_numeric(mensal.get("segundos", 0), errors="coerce").fillna(0).clip(lower=0)
        mensal["horas"] = mensal["segundos"] / 3600.0

        if utr_modo == "Médias":
            def _calc_row_utr_media(row: pd.Series) -> float:
                ts = pd.to_datetime(row["mes_ano"])
                return _utr_media_mensal(df, int(ts.month), int(ts.year))
            mensal["utr"] = mensal.apply(_calc_row_utr_media, axis=1)
        else:
            mensal["utr"] = mensal.apply(lambda r: (r["valor"] / r["horas"]) if r["horas"] > 0 else 0.0, axis=1)

        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['utr']:.2f} UTR)", axis=1)
        y_mensal = "valor"
        y_label = label
        titulo_plot = titulo

    elif tipo_grafico == "Corridas aceitas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(columns={"numero_de_corridas_ofertadas": "ref"})
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        y_mensal = "pct" if pct_modo == "%" else "valor"
        y_label = f"{label} (%)" if pct_modo == "%" else label
        titulo_plot = (titulo.replace("por mês", "(%) por mês")) if pct_modo == "%" else titulo
        mensal["label"] = mensal.apply(
            lambda r: f"{r['pct']:.1f}% ({int(r['valor'])})" if pct_modo == "%" else f"{int(r['valor'])} ({r['pct']:.1f}%)",
            axis=1,
        )

    elif tipo_grafico == "Corridas rejeitadas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(columns={"numero_de_corridas_ofertadas": "ref"})
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        y_mensal = "pct" if pct_modo == "%" else "valor"
        y_label = f"{label} (%)" if pct_modo == "%" else label
        titulo_plot = (titulo.replace("por mês", "(%) por mês")) if pct_modo == "%" else titulo
        mensal["label"] = mensal.apply(
            lambda r: f"{r['pct']:.1f}% ({int(r['valor'])})" if pct_modo == "%" else f"{int(r['valor'])} ({r['pct']:.1f}%)",
            axis=1,
        )

    else:  # completadas
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"].sum().rename(columns={"numero_de_corridas_aceitas": "ref"})
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        y_mensal = "pct" if pct_modo == "%" else "valor"
        y_label = f"{label} (%)" if pct_modo == "%" else label
        titulo_plot = (titulo.replace("por mês", "(%) por mês")) if pct_modo == "%" else titulo
        mensal["label"] = mensal.apply(
            lambda r: f"{r['pct']:.1f}% ({int(r['valor'])})" if pct_modo == "%" else f"{int(r['valor'])} ({r['pct']:.1f}%)",
            axis=1,
        )

    figm = px.bar(
        mensal,
        x="mes_rotulo",
        y=y_mensal,
        text="label",
        title=titulo_plot,
        labels={"mes_rotulo": "Mês/Ano", y_mensal: y_label},
        template="plotly_dark",
        color_discrete_sequence=PRIMARY_COLOR,
    )
    figm.update_traces(textposition="outside")
    st.plotly_chart(figm, use_container_width=True)

    if df_mes_ref.empty:
        st.info("Sem dados no mês selecionado.")
        _render_resumo_ano()
        return

    base = (
        df_mes_ref.assign(
            data_ref=lambda d: pd.to_datetime(d["data"]),
            dia=lambda d: pd.to_datetime(d["data"]).dt.day,
        )
        .groupby("dia", as_index=False)
        .agg(
            ofe=("numero_de_corridas_ofertadas", "sum"),
            ace=("numero_de_corridas_aceitas", "sum"),
            rej=("numero_de_corridas_rejeitadas", "sum"),
            com=("numero_de_corridas_completadas", "sum"),
            seg=("segundos_abs", "sum"),
            data_ref=("data_ref", "min"),
        )
        .sort_values("dia")
    )
    base["seg"] = pd.to_numeric(base["seg"], errors="coerce").fillna(0).clip(lower=0)
    base["horas"] = base["seg"] / 3600.0
    base["acc_pct"] = (base["ace"] / base["ofe"] * 100).where(base["ofe"] > 0, 0.0)
    base["rej_pct"] = (base["rej"] / base["ofe"] * 100).where(base["ofe"] > 0, 0.0)
    base["comp_pct"] = (base["com"] / base["ace"] * 100).where(base["ace"] > 0, 0.0)
    base["utr"] = (base["ofe"] / base["horas"]).where(base["horas"] > 0, 0.0)

    base["week_start"] = _week_start(base["data_ref"])
    base["dow"] = _weekday_label(base["data_ref"])
    base["cor"] = _colors_by_week(base["data_ref"])

    if tipo_grafico == "Corridas ofertadas":
        y = base["ofe"]
        txt = base.apply(lambda r: f"{int(r['ofe'])} ({r['utr']:.2f} UTR)", axis=1)
        ytitle = "Ofertadas"
    elif tipo_grafico == "Corridas aceitas":
        if pct_modo == "%":
            y = base["acc_pct"]
            ytitle = "Aceitas (%)"
            txt = base.apply(lambda r: f"{r['acc_pct']:.1f}% ({int(r['ace'])})", axis=1)
        else:
            y = base["ace"]
            ytitle = "Aceitas"
            txt = base.apply(lambda r: f"{int(r['ace'])} ({r['acc_pct']:.1f}%)", axis=1)
    elif tipo_grafico == "Corridas rejeitadas":
        if pct_modo == "%":
            y = base["rej_pct"]
            ytitle = "Rejeitadas (%)"
            txt = base.apply(lambda r: f"{r['rej_pct']:.1f}% ({int(r['rej'])})", axis=1)
        else:
            y = base["rej"]
            ytitle = "Rejeitadas"
            txt = base.apply(lambda r: f"{int(r['rej'])} ({r['rej_pct']:.1f}%)", axis=1)
    else:
        if pct_modo == "%":
            y = base["comp_pct"]
            ytitle = "Completadas (%)"
            txt = base.apply(lambda r: f"{r['comp_pct']:.1f}% ({int(r['com'])})", axis=1)
        else:
            y = base["com"]
            ytitle = "Completadas"
            txt = base.apply(lambda r: f"{int(r['com'])} ({r['comp_pct']:.1f}%)", axis=1)

    if comparar_semanas:
        num_sem = st.slider("Quantas semanas (no mês)", 2, 8, 4)
        ws_ord = sorted(base["week_start"].dropna().unique())[-num_sem:]
        figw = go.Figure()
        for i, ws in enumerate(ws_ord):
            dws = base[base["week_start"] == ws].copy()
            if tipo_grafico == "Corridas ofertadas":
                yy = dws["ofe"]
            elif tipo_grafico == "Corridas aceitas":
                yy = dws["acc_pct"] if pct_modo == "%" else dws["ace"]
            elif tipo_grafico == "Corridas rejeitadas":
                yy = dws["rej_pct"] if pct_modo == "%" else dws["rej"]
            else:
                yy = dws["comp_pct"] if pct_modo == "%" else dws["com"]

            figw.add_trace(
                go.Scatter(
                    x=dws["dow"],
                    y=yy,
                    mode="lines+markers",
                    name=pd.to_datetime(ws).strftime("%d/%m"),
                    line=dict(color=WEEK_PALETTE[i % len(WEEK_PALETTE)], width=3),
                )
            )
        figw.update_layout(
            title=f"{ytitle} por dia da semana (overlay) - {mes_diario:02d}/{ano_diario}",
            template="plotly_dark",
            margin=dict(t=60, b=30, l=40, r=40),
            xaxis_title="Dia da semana",
            yaxis_title=ytitle,
        )
        st.plotly_chart(figw, use_container_width=True)
    else:
        figd = go.Figure()
        figd.add_bar(
            x=base["dia"],
            y=y,
            text=txt,
            textposition="outside",
            marker=dict(color=base["cor"], line=dict(width=0.5, color="rgba(255,255,255,0.25)")),
            name=ytitle,
        )
        _add_week_separators(figd, base["data_ref"])
        figd.update_layout(
            title=f"{ytitle} por dia ({mes_diario:02d}/{ano_diario})",
            template="plotly_dark",
            margin=dict(t=60, b=30, l=40, r=40),
            xaxis_title="Dia",
            yaxis_title=ytitle,
            xaxis=dict(tickmode="linear", dtick=1),
        )
        st.plotly_chart(figd, use_container_width=True)

    _render_resumo_ano()
