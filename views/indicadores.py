import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from relatorios import utr_por_entregador_turno
from shared import sub_options_with_livre, apply_sub_filter  # 👈 filtro por subpraça
from utils import calcular_aderencia

PRIMARY_COLOR = ["#00BFFF"]  # paleta padrão


def _clean_sub_praca_inplace(df: pd.DataFrame) -> pd.DataFrame:
    """Evita o bug do filtro com 2 'LIVRE': normaliza ''/espaço/'null' etc pra NA."""
    if "sub_praca" not in df.columns:
        return df
    s = df["sub_praca"].astype("object")
    s = s.map(lambda x: x.strip() if isinstance(x, str) else x)
    s = s.replace("", pd.NA)
    s = s.map(lambda x: pd.NA if isinstance(x, str) and x.lower() in ("none", "null", "nan", "na") else x)
    df["sub_praca"] = s
    return df


def _colors_by_week(dates: pd.Series, c1: str = "#00BFFF", c2: str = "#2B2B2B") -> list[str]:
    """Alterna cores por semana (Seg-Dom) usando o início da semana (segunda)."""
    d = pd.to_datetime(dates, errors="coerce")
    week_start = d - pd.to_timedelta(d.dt.weekday.fillna(0).astype(int), unit="D")
    codes = pd.factorize(week_start)[0]
    return [c1 if (i % 2 == 0) else c2 for i in codes]


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

    # 👇 Seletor de modo (Quantidade vs %) para aceitas/rejeitadas/completadas
    pct_modo = None
    if tipo_grafico in ("Corridas aceitas", "Corridas rejeitadas", "Corridas completadas"):
        pct_modo = st.radio(
            "Modo do gráfico",
            ["Quantidade", "%"],
            index=0,
            horizontal=True,
            help="Quantidade mantém o total e mostra a taxa entre parênteses. % plota direto a taxa.",
        )

    # Garante mes_ano
    df = _ensure_mes_ano(df)
    df["data"] = pd.to_datetime(df.get("data_do_periodo", df.get("data")), errors="coerce")

    # 🔧 corrige sub_praca vindo como string vazia/espacos (evita 2 'LIVRE')
    df = _clean_sub_praca_inplace(df)

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

    # Slices de tempo
    df_mes_ref = df[(df.get("mes") == mes_diario) & (df.get("ano") == ano_diario)].copy()
    df_ano_ref = df[df.get("ano") == ano_diario].copy()

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

            por_dia["data_ref"] = pd.to_datetime(
                dict(year=ano_diario, month=mes_diario, day=por_dia["dia"]),
                errors="coerce",
            )
            cores_semana = _colors_by_week(por_dia["data_ref"], c1=PRIMARY_COLOR[0], c2="#2B2B2B")

            fig_d = go.Figure()
            fig_d.add_bar(
                x=por_dia["dia"],
                y=por_dia["aderencia_pct"],
                text=por_dia["aderencia_pct"].map(lambda v: f"{v:.1f}%"),
                textposition="outside",
                marker=dict(color=cores_semana),
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

            por_dia["data_ref"] = pd.to_datetime(
                dict(year=ano_diario, month=mes_diario, day=por_dia["dia"]),
                errors="coerce",
            )
            cores_semana = _colors_by_week(por_dia["data_ref"], c1=PRIMARY_COLOR[0], c2="#2B2B2B")
            # 🔧 só BARRAS, eixo X 1..31
            fig_d = go.Figure()
            fig_d.add_bar(
                x=por_dia["dia"],
                y=por_dia["horas"],
                text=por_dia["horas"].map(lambda v: f"{v:.1f}h"),
                textposition="outside",
                marker=dict(color=cores_semana),
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

            por_dia["data_ref"] = pd.to_datetime(
                dict(year=ano_diario, month=mes_diario, day=por_dia["dia"]),
                errors="coerce",
            )
            cores_semana = _colors_by_week(por_dia["data_ref"], c1=PRIMARY_COLOR[0], c2="#2B2B2B")
            # 🔧 só BARRAS, eixo X 1..31
            fig2 = go.Figure()
            fig2.add_bar(
                x=por_dia["dia"],
                y=por_dia["entregadores"],
                text=por_dia["entregadores"].astype(int).astype(str),
                textposition="outside",
                marker=dict(color=cores_semana),
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
        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1)
    elif tipo_grafico == "Corridas rejeitadas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(
            columns={"numero_de_corridas_ofertadas": "ref"}
        )
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1)
    elif tipo_grafico == "Corridas completadas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"].sum().rename(
            columns={"numero_de_corridas_aceitas": "ref"}
        )
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1)
    else:
        mensal["label"] = mensal["valor"].astype(str)

    # Se o modo for %, plota a taxa (mantém a quantidade no texto)
    y_mensal = "valor"
    label_mensal = label
    if pct_modo == "%" and tipo_grafico in ("Corridas aceitas", "Corridas rejeitadas", "Corridas completadas"):
        y_mensal = "pct"
        label_mensal = f"{label} (%)"
        mensal["label"] = mensal.apply(lambda r: f"{r['pct']:.1f}% ({int(r['valor'])})", axis=1)

    titulo_plot = titulo
    if pct_modo == "%" and tipo_grafico in ("Corridas aceitas", "Corridas rejeitadas", "Corridas completadas"):
        titulo_plot = titulo.replace("por mês", "(%) por mês") if "por mês" in titulo else f"{titulo} (%)"

    fig = px.bar(
        mensal,
        x="mes_rotulo",
        y=y_mensal,
        text="label",
        title=titulo_plot,
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

    # Cores alternadas por semana (Seg-Dom)
    por_dia_base["data_ref"] = pd.to_datetime(
        dict(year=ano_diario, month=mes_diario, day=por_dia_base["dia"]),
        errors="coerce",
    )
    cores_semana = _colors_by_week(por_dia_base["data_ref"], c1=PRIMARY_COLOR[0], c2="#2B2B2B")

    # Seleção de métrica de rótulo nas barras (sem linha)
    if tipo_grafico == "Corridas ofertadas":
        y_bar = por_dia_base["ofe"]
        label_bar = por_dia_base.apply(lambda r: f"{int(r['ofe'])} ({r['utr']:.2f} UTR)", axis=1)
        y_title = "Corridas"
    elif tipo_grafico == "Corridas aceitas":
        if pct_modo == "%":
            y_bar = por_dia_base["acc_pct"]
            label_bar = por_dia_base.apply(lambda r: f"{r['acc_pct']:.1f}% ({int(r['ace'])})", axis=1)
            y_title = "Aceitas (%)"
        else:
            y_bar = por_dia_base["ace"]
            label_bar = por_dia_base.apply(lambda r: f"{int(r['ace'])} ({r['acc_pct']:.1f}%)", axis=1)
            y_title = "Corridas Aceitas"
    elif tipo_grafico == "Corridas rejeitadas":
        if pct_modo == "%":
            y_bar = por_dia_base["rej_pct"]
            label_bar = por_dia_base.apply(lambda r: f"{r['rej_pct']:.1f}% ({int(r['rej'])})", axis=1)
            y_title = "Rejeitadas (%)"
        else:
            y_bar = por_dia_base["rej"]
            label_bar = por_dia_base.apply(lambda r: f"{int(r['rej'])} ({r['rej_pct']:.1f}%)", axis=1)
            y_title = "Corridas Rejeitadas"
    else:  # "Corridas completadas"
        if pct_modo == "%":
            y_bar = por_dia_base["comp_pct"]
            label_bar = por_dia_base.apply(lambda r: f"{r['comp_pct']:.1f}% ({int(r['com'])})", axis=1)
            y_title = "Completadas (%)"
        else:
            y_bar = por_dia_base["com"]
            label_bar = por_dia_base.apply(lambda r: f"{int(r['com'])} ({r['comp_pct']:.1f}%)", axis=1)
            y_title = "Corridas Completadas"

    fig2 = go.Figure()
    fig2.add_bar(
        x=por_dia_base["dia"],
        y=y_bar,
        text=label_bar,
        textposition="outside",
        name=y_title,
        marker=dict(color=cores_semana),
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

    _render_resumo_ano()
