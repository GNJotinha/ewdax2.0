import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from relatorios import utr_por_entregador_turno

PRIMARY_COLOR = ["#00BFFF"]  # paleta padrão


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

    # Garante mes_ano
    df = _ensure_mes_ano(df)

    # ---------------------------------------------------------
    # Filtros por praça / turno (se existirem)
    # ---------------------------------------------------------
    praca_col = next(
        (c for c in ("praca", "praça", "subpraca", "sub_praca") if c in df.columns),
        None,
    )
    turno_col = next(
        (c for c in ("turno", "tipo_turno", "periodo") if c in df.columns),
        None,
    )

    col_f1, col_f2 = st.columns(2)
    praca_sel = turno_sel = None

    if praca_col is not None:
        op_praca = ["Todas"] + sorted(df[praca_col].dropna().unique().tolist())
        praca_sel = col_f1.selectbox("Praça", op_praca, index=0)

    if turno_col is not None:
        op_turno = ["Todos"] + sorted(df[turno_col].dropna().unique().tolist())
        turno_sel = col_f2.selectbox("Turno", op_turno, index=0)

    # aplica filtros
    if praca_col is not None and praca_sel not in (None, "Todas"):
        df = df[df[praca_col] == praca_sel]
    if turno_col is not None and turno_sel not in (None, "Todos"):
        df = df[df[turno_col] == turno_sel]

    # ---------------------------------------------------------
    # Recortes temporais
    # ---------------------------------------------------------
    hoje = pd.Timestamp.today()
    mes_atual = int(hoje.month)
    ano_atual = int(hoje.year)

    df_mes_atual = df[(df.get("mes") == mes_atual) & (df.get("ano") == ano_atual)].copy()
    df_ano_atual = df[df.get("ano") == ano_atual].copy()

    # ---------------------------------------------------------
    # Helper: resumo anual
    # ---------------------------------------------------------
    def _render_resumo_ano():
        """Mostra os números gerais do ano (em baixo, letra maior)."""
        tot_ofert = df_ano_atual.get(
            "numero_de_corridas_ofertadas", pd.Series(dtype=float)
        ).sum()
        tot_aceit = df_ano_atual.get(
            "numero_de_corridas_aceitas", pd.Series(dtype=float)
        ).sum()
        tot_rej = df_ano_atual.get(
            "numero_de_corridas_rejeitadas", pd.Series(dtype=float)
        ).sum()
        tot_comp = df_ano_atual.get(
            "numero_de_corridas_completadas", pd.Series(dtype=float)
        ).sum()

        tx_aceit_ano = (tot_aceit / tot_ofert * 100) if tot_ofert > 0 else 0.0
        tx_rej_ano = (tot_rej / tot_ofert * 100) if tot_ofert > 0 else 0.0
        tx_comp_ano = (tot_comp / tot_aceit * 100) if tot_aceit > 0 else 0.0

        # Ativos = entregadores únicos no ano
        if "pessoa_entregadora" in df_ano_atual.columns:
            tot_sh = df_ano_atual["pessoa_entregadora"].nunique()
        else:
            tot_sh = 0

        # Horas realizadas no ano
        tot_horas = (
            df_ano_atual.get("segundos_abs", pd.Series(dtype=float)).sum() / 3600.0
        )

        st.divider()
        st.markdown("### 📅 Números gerais do ano atual")
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
    # Horas realizadas
    # ---------------------------------------------------------
    if tipo_grafico == "Horas realizadas":
        mensal_horas = (
            df.groupby("mes_ano", as_index=False)["segundos_abs"].sum()
            .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
        )
        mensal_horas["mes_rotulo"] = pd.to_datetime(
            mensal_horas["mes_ano"]
        ).dt.strftime("%b/%y")

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

        if not df_mes_atual.empty:
            por_dia = (
                df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                .groupby("dia", as_index=False)["segundos_abs"]
                .sum()
                .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
                .sort_values("dia")
            )
            # linha separada (como era antes)
            fig_d = px.line(
                por_dia,
                x="dia",
                y="horas",
                title="📈 Horas por dia (mês atual)",
                labels={"dia": "Dia", "horas": "Horas"},
                template="plotly_dark",
            )
            fig_d.update_layout(
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis=dict(tickmode="linear", tick0=1, dtick=1),
            )
            st.metric("⏱️ Horas realizadas no mês", f"{por_dia['horas'].sum():.2f}h")
            st.plotly_chart(fig_d, use_container_width=True)
        else:
            st.info("Sem dados no mês atual.")

        _render_resumo_ano()
        return

    # ---------------------------------------------------------
    # Entregadores ativos
    # ---------------------------------------------------------
    if tipo_grafico == "Entregadores ativos":
        mensal = (
            df.groupby("mes_ano", as_index=False)["pessoa_entregadora"]
            .nunique()
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

        if not df_mes_atual.empty:
            por_dia = (
                df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                .groupby("dia", as_index=False)["pessoa_entregadora"]
                .nunique()
                .rename(columns={"pessoa_entregadora": "entregadores"})
                .sort_values("dia")
            )
            fig2 = px.line(
                por_dia,
                x="dia",
                y="entregadores",
                title="📈 Entregadores por dia (mês atual)",
                labels={"dia": "Dia", "entregadores": "Entregadores"},
                template="plotly_dark",
            )
            fig2.update_layout(
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis=dict(tickmode="linear", tick0=1, dtick=1),
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados no mês atual.")

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
    mensal = (
        df.groupby("mes_ano", as_index=False)[col]
        .sum()
        .rename(columns={col: "valor"})
    )
    mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

    if tipo_grafico == "Corridas ofertadas":
        # Horas por mês
        secs_mensal = (
            df.groupby("mes_ano", as_index=False)["segundos_abs"]
            .sum()
            .rename(columns={"segundos_abs": "segundos"})
        )
        mensal = mensal.merge(secs_mensal, on="mes_ano", how="left")
        mensal["segundos"] = pd.to_numeric(
            mensal.get("segundos", 0), errors="coerce"
        ).fillna(0)
        mensal["horas"] = mensal["segundos"] / 3600.0

        # UTR por mês conforme modo
        if utr_modo == "Médias":
            def _calc_row_utr_media(row: pd.Series) -> float:
                ts = pd.to_datetime(row["mes_ano"])
                return _utr_media_mensal(df, int(ts.month), int(ts.year))

            mensal["utr"] = mensal.apply(_calc_row_utr_media, axis=1)
        else:
            mensal["utr"] = mensal.apply(
                lambda r: (r["valor"] / r["horas"]) if r["horas"] > 0 else 0.0,
                axis=1,
            )

        # Label no formato: "N (x.xx UTR)"
        mensal["label"] = mensal.apply(
            lambda r: f"{int(r['valor'])} ({r['utr']:.2f} UTR)", axis=1
        )

    elif tipo_grafico == "Corridas aceitas":
        ref = (
            df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"]
            .sum()
            .rename(columns={"numero_de_corridas_ofertadas": "ref"})
        )
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        mensal["label"] = mensal.apply(
            lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1
        )

    elif tipo_grafico == "Corridas rejeitadas":
        ref = (
            df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"]
            .sum()
            .rename(columns={"numero_de_corridas_ofertadas": "ref"})
        )
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        mensal["label"] = mensal.apply(
            lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1
        )

    elif tipo_grafico == "Corridas completadas":
        ref = (
            df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"]
            .sum()
            .rename(columns={"numero_de_corridas_aceitas": "ref"})
        )
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).where(mensal["ref"] > 0, 0.0)
        mensal["label"] = mensal.apply(
            lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1
        )
    else:
        mensal["label"] = mensal["valor"].astype(str)

    fig = px.bar(
        mensal,
        x="mes_rotulo",
        y="valor",
        text="label",
        title=titulo,
        labels={"mes_rotulo": "Mês/Ano", "valor": label},
        template="plotly_dark",
        color_discrete_sequence=PRIMARY_COLOR,
    )
    fig.update_traces(texttemplate="<b>%{text}</b>", textposition="outside")
    fig.update_layout(margin=dict(t=60, b=30, l=40, r=40))
    st.plotly_chart(fig, use_container_width=True)

    # ---------- Por dia (mês atual) — BARRAS (sem linha) + opcional linha separada ----------
    por_dia_base = (
        df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
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
        st.info("Sem dados no mês atual.")
        _render_resumo_ano()
        return

    por_dia_base["horas"] = por_dia_base["seg"] / 3600.0
    por_dia_base["acc_pct"]  = (por_dia_base["ace"] / por_dia_base["ofe"] * 100).where(por_dia_base["ofe"] > 0, 0.0)
    por_dia_base["rej_pct"]  = (por_dia_base["rej"] / por_dia_base["ofe"] * 100).where(por_dia_base["ofe"] > 0, 0.0)
    por_dia_base["comp_pct"] = (por_dia_base["com"] / por_dia_base["ace"] * 100).where(por_dia_base["ace"] > 0, 0.0)
    por_dia_base["utr"] = (por_dia_base["ofe"] / por_dia_base["horas"]).where(por_dia_base["horas"] > 0, 0.0)

    # Seleção por tipo (barras + labels)
    if tipo_grafico == "Corridas ofertadas":
        y_bar = por_dia_base["ofe"]
        bar_label = por_dia_base.apply(lambda r: f"{int(r['ofe'])} ({r['utr']:.2f} UTR)", axis=1)
        line_series = por_dia_base["utr"]
        line_title = "UTR diária"
        line_y_label = "UTR (ofertadas/h)"
    elif tipo_grafico == "Corridas aceitas":
        y_bar = por_dia_base["ace"]
        bar_label = por_dia_base.apply(lambda r: f"{int(r['ace'])} ({r['acc_pct']:.1f}%)", axis=1)
        line_series = por_dia_base["acc_pct"]
        line_title = "% aceitação (diário)"
        line_y_label = "%"
    elif tipo_grafico == "Corridas rejeitadas":
        y_bar = por_dia_base["rej"]
        bar_label = por_dia_base.apply(lambda r: f"{int(r['rej'])} ({r['rej_pct']:.1f}%)", axis=1)
        line_series = por_dia_base["rej_pct"]
        line_title = "% rejeição (diário)"
        line_y_label = "%"
    elif tipo_grafico == "Corridas completadas":
        y_bar = por_dia_base["com"]
        bar_label = por_dia_base.apply(lambda r: f"{int(r['com'])} ({r['comp_pct']:.1f}%)", axis=1)
        line_series = por_dia_base["comp_pct"]
        line_title = "% conclusão (diário)"
        line_y_label = "%"
    else:
        # fallback
        y_bar = por_dia_base["ofe"]
        bar_label = por_dia_base["ofe"].astype(int).astype(str)
        line_series = None
        line_title = ""
        line_y_label = ""

    # Barras (sem linha)
    fig_b = go.Figure()
    fig_b.add_bar(
        x=por_dia_base["dia"],
        y=y_bar,
        text=bar_label,
        textposition="outside",
        cliponaxis=False,
        name=label,
        marker=dict(color="#00BFFF"),
    )
    fig_b.update_layout(
        title=f"📊 {label} por dia (mês atual)",
        template="plotly_dark",
        margin=dict(t=80, b=30, l=40, r=40),
        bargap=0.25,
        xaxis=dict(
            title="Dia",
            tickmode="linear",  # 1 em 1
            tick0=1,
            dtick=1,
        ),
        yaxis=dict(title=label),
        showlegend=False,
    )
    st.plotly_chart(fig_b, use_container_width=True)

    # Opcional: gráfico de linha separado (como antes)
    if st.toggle("Mostrar gráfico de linha separado (tendência)", value=False) and line_series is not None:
        fig_l = px.line(
            por_dia_base,
            x="dia",
            y=line_series,
            title=f"📈 {line_title}",
            labels={"dia": "Dia", "y": line_y_label},
            template="plotly_dark",
        )
        fig_l.update_layout(
            margin=dict(t=60, b=30, l=40, r=40),
            xaxis=dict(tickmode="linear", tick0=1, dtick=1),
        )
        st.plotly_chart(fig_l, use_container_width=True)

    _render_resumo_ano()
