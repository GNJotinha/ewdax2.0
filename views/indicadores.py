import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from relatorios import utr_por_entregador_turno
from shared import sub_options_with_livre, apply_sub_filter

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
    """UTR média do mês (ofertadas/horas por entregador/turno/dia)."""
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

    utr_modo = None
    if tipo_grafico == "Corridas ofertadas":
        utr_modo = st.radio(
            "UTR no mensal",
            ["Absoluto", "Médias"],
            index=0,
            horizontal=True,
            help="Como calcular a UTR exibida no gráfico MENSAL de ofertadas.",
        )

    # ---------------------------------------------------------
    # Filtros: Subpraça (com LIVRE) + Turno
    # ---------------------------------------------------------
    df = _ensure_mes_ano(df)

    sub_opts = sub_options_with_livre(df)
    filtro_sub = st.multiselect("Filtrar por subpraça:", sub_opts)
    turno_col = next((c for c in ("turno", "tipo_turno", "periodo") if c in df.columns), None)
    turno_sel = None
    if turno_col is not None:
        op_turno = ["Todos"] + sorted(df[turno_col].dropna().unique().tolist())
        turno_sel = st.selectbox("Turno", op_turno, index=0)

    df = apply_sub_filter(df, filtro_sub)
    if turno_col is not None and turno_sel not in (None, "Todos"):
        df = df[df[turno_col] == turno_sel]

    # ---------------------------------------------------------
    # Recorte temporal
    # ---------------------------------------------------------
    hoje = pd.Timestamp.today()
    mes_atual, ano_atual = int(hoje.month), int(hoje.year)
    df_mes_atual = df[(df.get("mes") == mes_atual) & (df.get("ano") == ano_atual)].copy()
    df_ano_atual = df[df.get("ano") == ano_atual].copy()

    # ---------------------------------------------------------
    # Resumo anual
    # ---------------------------------------------------------
    def _render_resumo_ano():
        tot_ofe = df_ano_atual.get("numero_de_corridas_ofertadas", pd.Series(dtype=float)).sum()
        tot_ace = df_ano_atual.get("numero_de_corridas_aceitas", pd.Series(dtype=float)).sum()
        tot_rej = df_ano_atual.get("numero_de_corridas_rejeitadas", pd.Series(dtype=float)).sum()
        tot_com = df_ano_atual.get("numero_de_corridas_completadas", pd.Series(dtype=float)).sum()

        tx_ace = (tot_ace / tot_ofe * 100) if tot_ofe > 0 else 0.0
        tx_rej = (tot_rej / tot_ofe * 100) if tot_ofe > 0 else 0.0
        tx_com = (tot_com / tot_ace * 100) if tot_ace > 0 else 0.0
        tot_sh = df_ano_atual["pessoa_entregadora"].nunique() if "pessoa_entregadora" in df_ano_atual.columns else 0
        tot_horas = df_ano_atual.get("segundos_abs", pd.Series(dtype=float)).sum() / 3600.0

        st.divider()
        st.markdown("### 📅 Números gerais do ano atual")
        st.markdown(
            f"""
            <div style='font-size:1.1rem;line-height:1.7;'>
            <b>Ofertadas:</b> {int(tot_ofe):,}<br>
            <b>Aceitas:</b> {int(tot_ace):,} ({tx_ace:.1f}%)<br>
            <b>Rejeitadas:</b> {int(tot_rej):,} ({tx_rej:.1f}%)<br>
            <b>Completadas:</b> {int(tot_com):,} ({tx_com:.1f}%)<br>
            <b>Ativos (SH):</b> {int(tot_sh):,}<br>
            <b>Horas realizadas:</b> {tot_horas:.1f}h
            </div>
            """.replace(",", "."),
            unsafe_allow_html=True,
        )

    # ---------------------------------------------------------
    # Horas realizadas
    # ---------------------------------------------------------
    if tipo_grafico == "Horas realizadas":
        mensal = (
            df.groupby("mes_ano", as_index=False)["segundos_abs"].sum()
            .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
        )
        mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

        fig = px.bar(
            mensal,
            x="mes_rotulo",
            y="horas",
            text="horas",
            title="Horas realizadas por mês",
            labels={"mes_rotulo": "Mês/Ano", "horas": "Horas"},
            template="plotly_dark",
            color_discrete_sequence=PRIMARY_COLOR,
        )
        fig.update_traces(texttemplate="<b>%{text:.1f}h</b>", textposition="outside")
        fig.update_layout(margin=dict(t=60, b=30, l=40, r=40))
        st.plotly_chart(fig, use_container_width=True)

        if not df_mes_atual.empty:
            por_dia = (
                df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                .groupby("dia", as_index=False)["segundos_abs"]
                .sum()
                .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
                .sort_values("dia")
            )
            fig2 = px.bar(
                por_dia,
                x="dia",
                y="horas",
                text="horas",
                title="📊 Horas por dia (mês atual)",
                labels={"dia": "Dia", "horas": "Horas"},
                template="plotly_dark",
                color_discrete_sequence=PRIMARY_COLOR,
            )
            fig2.update_traces(texttemplate="<b>%{text:.1f}h</b>", textposition="outside")
            fig2.update_layout(
                margin=dict(t=60, b=30, l=40, r=40),
                xaxis=dict(tickmode="linear", tick0=1, dtick=1),
            )
            st.metric("⏱️ Horas realizadas no mês", f"{por_dia['horas'].sum():.2f}h")
            st.plotly_chart(fig2, use_container_width=True)
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
            fig2 = px.bar(
                por_dia,
                x="dia",
                y="entregadores",
                text="entregadores",
                title="📊 Entregadores por dia (mês atual)",
                labels={"dia": "Dia", "entregadores": "Entregadores"},
                template="plotly_dark",
                color_discrete_sequence=PRIMARY_COLOR,
            )
            fig2.update_traces(texttemplate="<b>%{text}</b>", textposition="outside")
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
    # Corridas ofertadas / aceitas / rejeitadas / completadas
    # ---------------------------------------------------------
    col_map = {
        "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Corridas"),
        "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas Aceitas"),
        "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas Rejeitadas"),
        "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas Completadas"),
    }
    col, titulo, label = col_map[tipo_grafico]

    # MENSAL
    mensal = df.groupby("mes_ano", as_index=False)[col].sum().rename(columns={col: "valor"})
    mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

    if tipo_grafico == "Corridas ofertadas":
        secs = df.groupby("mes_ano", as_index=False)["segundos_abs"].sum().rename(columns={"segundos_abs": "seg"})
        mensal = mensal.merge(secs, on="mes_ano", how="left")
        mensal["horas"] = mensal["seg"] / 3600.0
        mensal["utr"] = mensal.apply(lambda r: (r["valor"]/r["horas"]) if r["horas"]>0 else 0.0, axis=1)
        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['utr']:.2f} UTR)", axis=1)
    elif tipo_grafico == "Corridas aceitas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(columns={"numero_de_corridas_ofertadas":"ref"})
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"]/mensal["ref"]*100).where(mensal["ref"]>0,0)
        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1)
    elif tipo_grafico == "Corridas rejeitadas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(columns={"numero_de_corridas_ofertadas":"ref"})
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"]/mensal["ref"]*100).where(mensal["ref"]>0,0)
        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1)
    elif tipo_grafico == "Corridas completadas":
        ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"].sum().rename(columns={"numero_de_corridas_aceitas":"ref"})
        mensal = mensal.merge(ref, on="mes_ano", how="left")
        mensal["pct"] = (mensal["valor"]/mensal["ref"]*100).where(mensal["ref"]>0,0)
        mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.1f}%)", axis=1)

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

    # DIÁRIO
    por_dia = (
        df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
        .groupby("dia", as_index=False)
        .agg({
            "numero_de_corridas_ofertadas": "sum",
            "numero_de_corridas_aceitas": "sum",
            "numero_de_corridas_rejeitadas": "sum",
            "numero_de_corridas_completadas": "sum",
            "segundos_abs": "sum",
        })
        .sort_values("dia")
    )

    por_dia["horas"] = por_dia["segundos_abs"] / 3600.0
    por_dia["acc_pct"] = (por_dia["numero_de_corridas_aceitas"]/por_dia["numero_de_corridas_ofertadas"]*100).where(por_dia["numero_de_corridas_ofertadas"]>0,0)
    por_dia["rej_pct"] = (por_dia["numero_de_corridas_rejeitadas"]/por_dia["numero_de_corridas_ofertadas"]*100).where(por_dia["numero_de_corridas_ofertadas"]>0,0)
    por_dia["comp_pct"] = (por_dia["numero_de_corridas_completadas"]/por_dia["numero_de_corridas_aceitas"]*100).where(por_dia["numero_de_corridas_aceitas"]>0,0)
    por_dia["utr"] = (por_dia["numero_de_corridas_ofertadas"]/por_dia["horas"]).where(por_dia["horas"]>0,0)

    if tipo_grafico == "Corridas ofertadas":
        por_dia["valor"] = por_dia["numero_de_corridas_ofertadas"]
        por_dia["label"] = por_dia.apply(lambda r: f"{int(r['valor'])} ({r['utr']:.2f} UTR)", axis=1)
    elif tipo_grafico == "Corridas aceitas":
        por_dia["valor"] = por_dia["numero_de_corridas_aceitas"]
        por_dia["label"] = por_dia.apply(lambda r: f"{int(r['valor'])} ({r['acc_pct']:.1f}%)", axis=1)
    elif tipo_grafico == "Corridas rejeitadas":
        por_dia["valor"] = por_dia["numero_de_corridas_rejeitadas"]
        por_dia["label"] = por_dia.apply(lambda r: f"{int(r['valor'])} ({r['rej_pct']:.1f}%)", axis=1)
    elif tipo_grafico == "Corridas completadas":
        por_dia["valor"] = por_dia["numero_de_corridas_completadas"]
        por_dia["label"] = por_dia.apply(lambda r: f"{int(r['valor'])} ({r['comp_pct']:.1f}%)", axis=1)

    fig2 = px.bar(
        por_dia,
        x="dia",
        y="valor",
        text="label",
        title=f"📊 {label} por dia (mês atual)",
        labels={"dia": "Dia", "valor": label},
        template="plotly_dark",
        color_discrete_sequence=PRIMARY_COLOR,
    )
    fig2.update_traces(texttemplate="<b>%{text}</b>", textposition="outside")
    fig2.update_layout(
        margin=dict(t=60, b=30, l=40, r=40),
        xaxis=dict
    )
