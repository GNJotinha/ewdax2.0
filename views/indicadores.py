import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from relatorios import utr_por_entregador_turno
from shared import sub_options_with_livre, apply_sub_filter  # 👈 filtro por subpraça
from utils import calcular_aderencia

PRIMARY_COLOR = ["#00BFFF"]  # paleta padrão

# Paleta viva pra "blocos" de semana (Seg–Dom). Cada semana recebe uma cor diferente.
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

WEEKDAY_LABELS = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
WEEKDAY_ORDER = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _add_semana_cor_por_dia(por_dia: pd.DataFrame, ano: int, mes: int) -> pd.DataFrame:
    """
    Recebe um DF agregado por 'dia' (1..31) e adiciona:
      - date (YYYY-MM-DD)
      - week_start (segunda-feira da semana)
      - weekday / weekday_label
      - cor (uma cor por semana)
    """
    if por_dia is None or por_dia.empty or "dia" not in por_dia.columns:
        return por_dia

    out = por_dia.copy()
    out["date"] = pd.to_datetime(dict(year=int(ano), month=int(mes), day=out["dia"]), errors="coerce")
    out["weekday"] = out["date"].dt.weekday
    out["weekday_label"] = out["weekday"].map(WEEKDAY_LABELS)

    out["week_start"] = out["date"] - pd.to_timedelta(out["weekday"], unit="D")

    weeks = sorted(out["week_start"].dropna().unique().tolist())
    color_map = {ws: WEEK_PALETTE[i % len(WEEK_PALETTE)] for i, ws in enumerate(weeks)}
    out["cor"] = out["week_start"].map(color_map)

    return out


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

    # Labels bonitinhas: "dd/mm (seg)"
    week_labels = {ws: pd.to_datetime(ws).strftime("%d/%m/%Y") for ws in weeks}
    default = weeks[-2:] if len(weeks) >= 2 else weeks
    default_labels = [week_labels[w] for w in default]

    sel = st.multiselect(
        "Semanas (início na segunda-feira):",
        options=[week_labels[w] for w in weeks],
        default=default_labels,
        key=f"{key_prefix}_weeks",
    )
    sel_weeks = [w for w in weeks if week_labels[w] in sel]
    if not sel_weeks:
        st.info("Selecione pelo menos uma semana.")
        return

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

def _ensure_mes_ano(df: pd.DataFrame) -> pd.DataFrame:
    """Garante a coluna 'mes_ano' (timestamp do 1º dia do mês)."""
    if "mes_ano" in df.columns:
        return df
    base_dt = pd.to_datetime(df.get("data_do_periodo", df.get("data")), errors="coerce")
    dfx = df.copy()
    dfx["mes_ano"] = base_dt.dt.to_period("M").dt.to_timestamp()
    return dfx


def _utr_media_mensal(df: pd.DataFrame, mes: int, ano: int) -> float:
    """
    UTR 'Médias' por mês: média de (ofertadas/horas) nas linhas de (pessoa, turno, dia) com horas>0.
    Usa relatorios.utr_por_entregador_turno para manter consistência com a tela de UTR.
    """
    base = utr_por_entregador_turno(df, mes, ano)
    if base is None or base.empty:
        return 0.0
    base = base[base.get("supply_hours", 0) > 0].copy()
    if base.empty:
        return 0.0
    return float((base["corridas_ofertadas"] / base["supply_hours"]).mean())


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📊 Indicadores Gerais")

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

    # 👇 Seletor só para o MENSAL de ofertadas
    utr_modo = None
    if tipo_grafico == "Corridas ofertadas":
        utr_modo = st.radio(
            "UTR no mensal",
            ["Absoluto", "Médias"],
            index=0,
            horizontal=True,
            help="Como calcular a UTR exibida no gráfico MENSAL de ofertadas.",
        )


    # 👇 Seletor para ACEITAS/REJEITADAS/COMPLETADAS (Quantidade vs %)
    modo_taxa = None
    if tipo_grafico in ("Corridas aceitas", "Corridas rejeitadas", "Corridas completadas"):
        modo_taxa = st.radio(
            "Modo do gráfico",
            ["Quantidade", "%"],
            index=0,
            horizontal=True,
            help="Quantidade: mostra corridas (com % no texto).  %: mostra a taxa (com quantidade no texto).",
        )

    # Garante mes_ano
    df = _ensure_mes_ano(df)
    df["data"] = pd.to_datetime(df.get("data_do_periodo", df.get("data")), errors="coerce")

    # Blindagem: evita sumir gráfico quando o CSV não tem 'mes'/'ano' ou vem zoado.
    df["ano"] = df["data"].dt.year.astype("Int64")
    df["mes"] = df["data"].dt.month.astype("Int64")

    # segundos_abs precisa ser numérico e nunca negativo (senão quebra horas/UTR)
    if "segundos_abs" in df.columns:
        df["segundos_abs"] = pd.to_numeric(df["segundos_abs"], errors="coerce").fillna(0).clip(lower=0)

    # ---------------------------------------------------------
    # Filtros (subpraça), turno e entregador
    # ---------------------------------------------------------
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])

    # Subpraça (com 'LIVRE' quando praca=SAO PAULO e sub_praca nulo)
    sub_opts = sub_options_with_livre(df, praca_scope="SAO PAULO")
    sub_sel = col_f1.multiselect("Subpraça", sub_opts)
    df = apply_sub_filter(df, sub_sel, praca_scope="SAO PAULO")

    # Turno (se existir)
    turno_col = next((c for c in ("turno", "tipo_turno", "periodo") if c in df.columns), None)
    if turno_col is not None:
        op_turno = ["Todos"] + sorted(df[turno_col].dropna().unique().tolist())
        turno_sel = col_f2.selectbox("Turno", op_turno, index=0)
        if turno_sel != "Todos":
            df = df[df[turno_col] == turno_sel]

    # Entregador(es)
    ent_opts = sorted(df.get("pessoa_entregadora", pd.Series(dtype=object)).dropna().unique().tolist())
    ent_sel = col_f3.multiselect("Entregador(es)", ent_opts)
    if ent_sel:
        df = df[df["pessoa_entregadora"].isin(ent_sel)]

    # ---------------------------------------------------------
    # Seletor de Mês/Ano para o GRÁFICO DIÁRIO (passa a obedecer filtros)
    # ---------------------------------------------------------
    # pega o último mês/ano disponível já considerando filtros aplicados
    try:
        ultimo_ts = pd.to_datetime(df["mes_ano"]).max()
        default_mes = int(ultimo_ts.month) if pd.notna(ultimo_ts) else int(pd.to_datetime(df["mes_ano"]).dt.month.max())
        default_ano = int(ultimo_ts.year) if pd.notna(ultimo_ts) else int(pd.to_datetime(df["mes_ano"]).dt.year.max())
    except Exception:
        default_mes = int(pd.to_datetime(df.get("data_do_periodo", df.get("data")), errors="coerce").dt.month.max())
        default_ano = int(pd.to_datetime(df.get("data_do_periodo", df.get("data")), errors="coerce").dt.year.max())

    anos_disp = sorted([int(x) for x in df.get("ano", pd.Series(dtype=object)).dropna().unique().tolist()], reverse=True) or [default_ano]
    col_p1, col_p2 = st.columns(2)
    mes_diario = col_p1.selectbox("Mês (gráfico diário)", list(range(1, 13)), index=max(0, default_mes - 1))
    ano_idx = anos_disp.index(default_ano) if default_ano in anos_disp else 0
    ano_diario = col_p2.selectbox("Ano (gráfico diário)", anos_disp, index=ano_idx)

    colorir_diario_por_semana = st.checkbox(
        "🎨 Colorir gráfico diário por semana (Seg–Dom)",
        value=True,
        help="Cada bloco de segunda a domingo recebe uma cor diferente. Ajuda a enxergar a semana no gráfico diário.",
    )

    # Slices de tempo
    df_mes_ref = df[(df["mes"] == mes_diario) & (df["ano"] == ano_diario)].copy()
    df_ano_ref = df[df["ano"] == ano_diario].copy()

    # ---------------------------------------------------------
    # Helper: resumo anual (do ano selecionado no seletor)
    # ---------------------------------------------------------
    def _render_resumo_ano():
        """Mostra os números gerais do ANO selecionado (em baixo, letra maior)."""
        tot_ofert = df_ano_ref.get("numero_de_corridas_ofertadas", pd.Series(dtype=float)).sum()
        tot_aceit = df_ano_ref.get("numero_de_corridas_aceitas", pd.Series(dtype=float)).sum()
        tot_rej = df_ano_ref.get("numero_de_corridas_rejeitadas", pd.Series(dtype=float)).sum()
        tot_comp = df_ano_ref.get("numero_de_corridas_completadas", pd.Series(dtype=float)).sum()

        tx_aceit_ano = (tot_aceit / tot_ofert * 100) if tot_ofert > 0 else 0.0
        tx_rej_ano = (tot_rej / tot_ofert * 100) if tot_ofert > 0 else 0.0
        tx_comp_ano = (tot_comp / tot_aceit * 100) if tot_aceit > 0 else 0.0

        # Ativos = entregadores únicos no ano
        tot_sh = int(df_ano_ref.get("pessoa_entregadora", pd.Series(dtype=object)).dropna().nunique())

        # Horas realizadas no ano
        tot_horas = df_ano_ref.get("segundos_abs", pd.Series(dtype=float)).sum() / 3600.0

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

    # ---------------------------------------------------------
    # Aderência (%)
    # ---------------------------------------------------------
    if tipo_grafico == "Aderência (%)":
        # valida colunas
        if ("numero_minimo_de_entregadores_regulares_na_escala" not in df.columns) or ("tag" not in df.columns):
            st.info("Esses indicadores precisam das colunas 'numero_minimo_de_entregadores_regulares_na_escala' e 'tag'.")
            _render_resumo_ano()
            return

        turno_col_ap = turno_col  # já definido acima
        grp = ("data", turno_col_ap) if turno_col_ap is not None else ("data",)

        base_ap = calcular_aderencia(df.dropna(subset=["data"]).copy(), group_cols=grp)
        base_ap["mes_ano"] = pd.to_datetime(base_ap["data"]).dt.to_period("M").dt.to_timestamp()
        base_ap["mes_rotulo"] = pd.to_datetime(base_ap["mes_ano"]).dt.strftime("%b/%y")

        mensal = (
            base_ap.groupby(["mes_ano", "mes_rotulo"], as_index=False)
            .agg(
                vagas=("vagas", "sum"),
                regulares=("regulares_atuaram", "sum"),
            )
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

        # ------------------------------
        # Diário (mês selecionado)
        # ------------------------------
        if not df_mes_ref.empty:
            base_ap_mes = calcular_aderencia(df_mes_ref.dropna(subset=["data"]).copy(), group_cols=grp)
            base_ap_mes["dia"] = pd.to_datetime(base_ap_mes["data"]).dt.day
            por_dia = (
                base_ap_mes.groupby("dia", as_index=False)
                .agg(
                    vagas=("vagas", "sum"),
                    regulares=("regulares_atuaram", "sum"),
                )
                .sort_values("dia")
            )
            por_dia["aderencia_pct"] = por_dia.apply(lambda r: (r["regulares"] / r["vagas"] * 100.0) if r["vagas"] else 0.0, axis=1)

            # Cores por semana (Seg–Dom) no diário
            por_dia = _add_semana_cor_por_dia(por_dia, ano_diario, mes_diario)
            marker_color = por_dia["cor"] if (colorir_diario_por_semana and "cor" in por_dia.columns) else PRIMARY_COLOR[0]

            fig_d = go.Figure()
            fig_d.add_bar(
                x=por_dia["dia"],
                y=por_dia["aderencia_pct"],
                text=por_dia["aderencia_pct"].map(lambda v: f"{v:.1f}%"),
                textposition="outside",
                marker=dict(color=marker_color),
                name="Aderência"
            )
            fig_d.update_layout(
                title=f"📊 Aderência por dia ({mes_diario:02d}/{ano_diario})",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia",
                yaxis_title="Aderência (%)",
                xaxis=dict(tickmode="linear", dtick=1)
            )
            st.metric(
                "📌 Aderência no mês selecionado",
                f"{por_dia['regulares'].sum() / por_dia['vagas'].sum() * 100.0:.1f}%" if por_dia['vagas'].sum() > 0 else "0,0%",
            )
            st.plotly_chart(fig_d, use_container_width=True)
        else:
            st.info("Sem dados no mês selecionado.")

        _render_resumo_ano()
        return


    # ---------------------------------------------------------
    # Horas realizadas
    # ---------------------------------------------------------
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
            text="horas",
            title="Horas realizadas por mês",
            labels={"mes_rotulo": "Mês/Ano", "horas": "Horas"},
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig_m.update_traces(texttemplate="<b>%{text:.1f}h</b>", textposition="outside")
        fig_m.update_layout(margin=dict(t=60, b=30, l=40, r=40))
        st.plotly_chart(fig_m, use_container_width=True)

        if not df_mes_ref.empty:
            por_dia = (
                df_mes_ref.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                .groupby("dia", as_index=False)["segundos_abs"].sum()
                .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
                .sort_values("dia")
            )
            # Cores por semana (Seg–Dom) no diário
            por_dia = _add_semana_cor_por_dia(por_dia, ano_diario, mes_diario)
            marker_color = por_dia["cor"] if (colorir_diario_por_semana and "cor" in por_dia.columns) else PRIMARY_COLOR[0]

            # 🔧 só BARRAS, eixo X 1..31
            fig_d = go.Figure()
            fig_d.add_bar(
                x=por_dia["dia"],
                y=por_dia["horas"],
                text=por_dia["horas"].map(lambda v: f"{v:.1f}h"),
                textposition="outside",
                marker=dict(color=marker_color),
                name="Horas"
            )
            fig_d.update_layout(
                title=f"📊 Horas por dia ({mes_diario:02d}/{ano_diario})",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia",
                yaxis_title="Horas",
                xaxis=dict(tickmode="linear", dtick=1)  # dias certinhos
            )
            st.metric("⏱️ Horas no mês selecionado", f"{por_dia['horas'].sum():.2f}h")
            st.plotly_chart(fig_d, use_container_width=True)
        else:
            st.info("Sem dados no mês selecionado.")

        _render_resumo_ano()
        return

    # ---------------------------------------------------------
    # Entregadores ativos
    # ---------------------------------------------------------
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
            text="entregadores",
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
            # Cores por semana (Seg–Dom) no diário
            por_dia = _add_semana_cor_por_dia(por_dia, ano_diario, mes_diario)
            marker_color = por_dia["cor"] if (colorir_diario_por_semana and "cor" in por_dia.columns) else PRIMARY_COLOR[0]

            # 🔧 só BARRAS, eixo X 1..31
            fig2 = go.Figure()
            fig2.add_bar(
                x=por_dia["dia"],
                y=por_dia["entregadores"],
                text=por_dia["entregadores"].astype(int).astype(str),
                textposition="outside",
                marker=dict(color=marker_color),
                name="Entregadores"
            )
            fig2.update_layout(
                title=f"📊 Entregadores por dia ({mes_diario:02d}/{ano_diario})",
                template="plotly_dark",
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis_title="Dia",
                yaxis_title="Entregadores",
                xaxis=dict(tickmode="linear", dtick=1)  # dias certinhos
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados no mês selecionado.")

        _render_resumo_ano()
        return

    # ---------------------------------------------------------
    # Genéricos: ofertadas/aceitas/rejeitadas/completadas
    # ---------------------------------------------------------
    col_map = {
        "Corridas ofertadas": (
            "numero_de_corridas_ofertadas",
            "Corridas ofertadas por mês",
            "Corridas",
        ),
        "Corridas aceitas": (
            "numero_de_corridas_aceitas",
            "Corridas aceitas por mês",
            "Corridas Aceitas",
        ),
        "Corridas rejeitadas": (
            "numero_de_corridas_rejeitadas",
            "Corridas rejeitadas por mês",
            "Corridas Rejeitadas",
        ),
        "Corridas completadas": (
            "numero_de_corridas_completadas",
            "Corridas completadas por mês",
            "Corridas Completadas",
        ),
    }
    col, titulo, label = col_map[tipo_grafico]

    # ---------- Mensal ----------
    mensal = df.groupby("mes_ano", as_index=False)[col].sum().rename(columns={col: "valor"})
    mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

    if tipo_grafico == "Corridas ofertadas":
        # Horas por mês
        secs_mensal = df.groupby("mes_ano", as_index=False)["segundos_abs"].sum().rename(columns={"segundos_abs": "segundos"})
        mensal = mensal.merge(secs_mensal, on="mes_ano", how="left")
        mensal["segundos"] = pd.to_numeric(mensal.get("segundos", 0), errors="coerce").fillna(0)
        mensal["horas"] = mensal["segundos"] / 3600.0

        # UTR por mês conforme modo
        if utr_modo == "Médias":
            def _calc_row_utr_media(row: pd.Series) -> float:
                ts = pd.to_datetime(row["mes_ano"])
                return _utr_media_mensal(df, int(ts.month), int(ts.year))
            mensal["utr"] = mensal.apply(_calc_row_utr_media, axis=1)
        else:
            mensal["utr"] = mensal.apply(lambda r: (r["valor"] / r["horas"]) if r["horas"] > 0 else 0.0, axis=1)

        # Label no formato: "N (x.xx UTR)"
        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['utr']:.2f} UTR)", axis=1)
    elif tipo_grafico == "Corridas aceitas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(
            columns={"numero_de_corridas_ofertadas": "ref"}
        )
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        mensal["label"] = mensal.apply(lambda r: (f"{r['pct']:.1f}% ({int(r['valor'])})" if modo_taxa == "%" else f"{int(r['valor'])} ({r['pct']:.1f}%)"), axis=1)
    elif tipo_grafico == "Corridas rejeitadas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(
            columns={"numero_de_corridas_ofertadas": "ref"}
        )
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        mensal["label"] = mensal.apply(lambda r: (f"{r['pct']:.1f}% ({int(r['valor'])})" if modo_taxa == "%" else f"{int(r['valor'])} ({r['pct']:.1f}%)"), axis=1)
    elif tipo_grafico == "Corridas completadas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"].sum().rename(
            columns={"numero_de_corridas_aceitas": "ref"}
        )
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        mensal["label"] = mensal.apply(lambda r: (f"{r['pct']:.1f}% ({int(r['valor'])})" if modo_taxa == "%" else f"{int(r['valor'])} ({r['pct']:.1f}%)"), axis=1)
    else:
        mensal["label"] = mensal["valor"].astype(str)

    # Decide eixo Y no mensal (Quantidade vs %)
    y_mensal = "valor"
    titulo_mensal = titulo
    label_mensal = label
    if tipo_grafico in ("Corridas aceitas", "Corridas rejeitadas", "Corridas completadas") and modo_taxa == "%":
        y_mensal = "pct"
        if tipo_grafico == "Corridas aceitas":
            titulo_mensal = "Taxa de aceite por mês"
            label_mensal = "Taxa de aceite (%)"
        elif tipo_grafico == "Corridas rejeitadas":
            titulo_mensal = "Taxa de rejeição por mês"
            label_mensal = "Taxa de rejeição (%)"
        else:
            titulo_mensal = "Taxa de conclusão por mês"
            label_mensal = "Taxa de conclusão (%)"

    fig = px.bar(
        mensal,
        x="mes_rotulo",
        y=y_mensal,
        text="label",
        title=titulo_mensal,
        labels={"mes_rotulo": "Mês/Ano", y_mensal: label_mensal},
        template="plotly_dark",
        color_discrete_sequence=PRIMARY_COLOR,
    )
    fig.update_traces(texttemplate="<b>%{text}</b>", textposition="outside")
    fig.update_layout(margin=dict(t=60, b=30, l=40, r=40))
    st.plotly_chart(fig, use_container_width=True)

    # ---------- Por dia (mês SELECIONADO) — SÓ BARRAS ----------
    por_dia_base = (
        df_mes_ref.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
        .groupby("dia", as_index=False)[
            [
                "numero_de_corridas_ofertadas",
                "numero_de_corridas_aceitas",
                "numero_de_corridas_rejeitadas",
                "numero_de_corridas_completadas",
                "segundos_abs",
                "pessoa_entregadora",
            ]
        ]
        .agg({
            "numero_de_corridas_ofertadas": "sum",
            "numero_de_corridas_aceitas": "sum",
            "numero_de_corridas_rejeitadas": "sum",
            "numero_de_corridas_completadas": "sum",
            "segundos_abs": "sum",
            "pessoa_entregadora": "nunique",
        })
        .rename(columns={
            "numero_de_corridas_ofertadas": "ofe",
            "numero_de_corridas_aceitas": "ace",
            "numero_de_corridas_rejeitadas": "rej",
            "numero_de_corridas_completadas": "com",
            "segundos_abs": "seg",
            "pessoa_entregadora": "entregadores",
        })
        .sort_values("dia")
    )

    if por_dia_base.empty:
        st.info("Sem dados no mês selecionado.")
        _render_resumo_ano()
        return

    por_dia_base["horas"] = por_dia_base["seg"] / 3600.0
    por_dia_base["acc_pct"] = (por_dia_base["ace"] / por_dia_base["ofe"] * 100).where(por_dia_base["ofe"] > 0, 0.0)
    por_dia_base["rej_pct"] = (por_dia_base["rej"] / por_dia_base["ofe"] * 100).where(por_dia_base["ofe"] > 0, 0.0)
    por_dia_base["comp_pct"] = (por_dia_base["com"] / por_dia_base["ace"] * 100).where(por_dia_base["ace"] > 0, 0.0)
    por_dia_base["utr"] = (por_dia_base["ofe"] / por_dia_base["horas"]).where(por_dia_base["horas"] > 0, 0.0)

    # Cores por semana (Seg–Dom) no diário
    por_dia_base = _add_semana_cor_por_dia(por_dia_base, ano_diario, mes_diario)
    marker_color = por_dia_base["cor"] if (colorir_diario_por_semana and "cor" in por_dia_base.columns) else PRIMARY_COLOR[0]

    # Seleção de métrica (Quantidade vs %) no diário
    if tipo_grafico == "Corridas ofertadas":
        y_col = "ofe"
        y_title = "Corridas ofertadas"
        label_bar = por_dia_base.apply(lambda r: f"{int(r['ofe'])} ({r['utr']:.2f} UTR)", axis=1)

    elif tipo_grafico == "Corridas aceitas":
        if modo_taxa == "%":
            y_col = "acc_pct"
            y_title = "Taxa de aceite (%)"
            label_bar = por_dia_base.apply(lambda r: f"{r['acc_pct']:.1f}% ({int(r['ace'])})", axis=1)
        else:
            y_col = "ace"
            y_title = "Corridas aceitas"
            label_bar = por_dia_base.apply(lambda r: f"{int(r['ace'])} ({r['acc_pct']:.1f}%)", axis=1)

    elif tipo_grafico == "Corridas rejeitadas":
        if modo_taxa == "%":
            y_col = "rej_pct"
            y_title = "Taxa de rejeição (%)"
            label_bar = por_dia_base.apply(lambda r: f"{r['rej_pct']:.1f}% ({int(r['rej'])})", axis=1)
        else:
            y_col = "rej"
            y_title = "Corridas rejeitadas"
            label_bar = por_dia_base.apply(lambda r: f"{int(r['rej'])} ({r['rej_pct']:.1f}%)", axis=1)

    else:  # "Corridas completadas"
        if modo_taxa == "%":
            y_col = "comp_pct"
            y_title = "Taxa de conclusão (%)"
            label_bar = por_dia_base.apply(lambda r: f"{r['comp_pct']:.1f}% ({int(r['com'])})", axis=1)
        else:
            y_col = "com"
            y_title = "Corridas completadas"
            label_bar = por_dia_base.apply(lambda r: f"{int(r['com'])} ({r['comp_pct']:.1f}%)", axis=1)

    y_bar = por_dia_base[y_col]
    fig2 = go.Figure()
    fig2.add_bar(
        x=por_dia_base["dia"],
        y=y_bar,
        text=label_bar,
        textposition="outside",
        name=y_title,
        marker=dict(color=marker_color),
    )
    fig2.update_layout(
        title=f"📊 {y_title} por dia ({mes_diario:02d}/{ano_diario})",
        template="plotly_dark",
        margin=dict(t=60, b=30, l=40, r=40),
        xaxis_title="Dia",
        yaxis_title=y_title,
        xaxis=dict(tickmode="linear", dtick=1),  # dias 1,2,3...
    )
    st.plotly_chart(fig2, use_container_width=True)

    # 🔎 Comparar várias semanas (Seg–Dom) em um gráfico (linhas)
    with st.expander("📅 Comparar semanas (Seg–Dom)", expanded=False):
        if tipo_grafico == "Corridas ofertadas":
            cmp_metric = st.radio(
                "Métrica da comparação",
                ["Corridas", "UTR"],
                index=0,
                horizontal=True,
                key=f"cmp_metric_{mes_diario}_{ano_diario}",
            )
            y_cmp = "ofe" if cmp_metric == "Corridas" else "utr"
            yaxis = "Corridas ofertadas" if cmp_metric == "Corridas" else "UTR"
            title_cmp = f"Comparação semanal (Seg–Dom) — {yaxis}"
            _render_comparar_semanas(por_dia_base, y_cmp, yaxis, title_cmp, key_prefix=f"cmp_ofe_{mes_diario}_{ano_diario}")
        else:
            title_cmp = f"Comparação semanal (Seg–Dom) — {y_title}"
            _render_comparar_semanas(por_dia_base, y_col, y_title, title_cmp, key_prefix=f"cmp_{y_col}_{mes_diario}_{ano_diario}")


    _render_resumo_ano()
