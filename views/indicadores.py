import streamlit as st
import pandas as pd
import plotly.express as px
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

    # ---------------------------------------------------------
    # Tipo de gráfico
    # ---------------------------------------------------------
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
    # Base temporal
    # ---------------------------------------------------------
    hoje = pd.Timestamp.today()
    mes_atual = int(hoje.month)
    ano_atual = int(hoje.year)

    df = _ensure_mes_ano(df)

    # ---------------------------------------------------------
    # Filtros (Praça / Turno)
    # ---------------------------------------------------------
    praca_col = next((c for c in ("praca", "praça", "subpraca", "sub_praca") if c in df.columns), None)
    turno_col = next((c for c in ("turno", "tipo_turno", "periodo") if c in df.columns), None)

    col_f1, col_f2 = st.columns(2)
    praca_sel, turno_sel = None, None

    if praca_col:
        op_praca = ["Todas"] + sorted(df[praca_col].dropna().unique().tolist())
        praca_sel = col_f1.selectbox("Praça", op_praca, index=0)
    if turno_col:
        op_turno = ["Todos"] + sorted(df[turno_col].dropna().unique().tolist())
        turno_sel = col_f2.selectbox("Turno", op_turno, index=0)

    if praca_col and praca_sel not in (None, "Todas"):
        df = df[df[praca_col] == praca_sel]
    if turno_col and turno_sel not in (None, "Todos"):
        df = df[df[turno_col] == turno_sel]

    # ---------------------------------------------------------
    # recortes do ano e do mês
    # ---------------------------------------------------------
    if "ano" in df.columns:
        df_ano_atual = df[df["ano"] == ano_atual].copy()
    else:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        df_ano_atual = df[df["data"].dt.year == ano_atual].copy()

    if {"mes", "ano"}.issubset(df.columns):
        df_mes_atual = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)].copy()
    else:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        df_mes_atual = df[(df["data"].dt.month == mes_atual) & (df["data"].dt.year == ano_atual)].copy()

    # ---------------------------------------------------------
    # Gráficos principais
    # ---------------------------------------------------------
    col_map = {
        "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Corridas"),
        "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas Aceitas"),
        "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas Rejeitadas"),
        "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas Completadas"),
    }

    if tipo_grafico not in col_map and tipo_grafico != "Horas realizadas" and tipo_grafico != "Entregadores ativos":
        st.stop()

    # === Corridas (geral) ===
    if tipo_grafico in col_map:
        col, titulo, label = col_map[tipo_grafico]
        mensal = df.groupby("mes_ano", as_index=False)[col].sum().rename(columns={col: "valor"})
        mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

        if tipo_grafico == "Corridas ofertadas":
            secs_mensal = df.groupby("mes_ano", as_index=False)["segundos_abs"].sum().rename(columns={"segundos_abs": "segundos"})
            mensal = mensal.merge(secs_mensal, on="mes_ano", how="left")
            mensal["horas"] = mensal["segundos"] / 3600.0
            if utr_modo == "Médias":
                mensal["utr"] = mensal["mes_ano"].apply(lambda x: _utr_media_mensal(df, x.month, x.year))
            else:
                mensal["utr"] = mensal.apply(lambda r: (r["valor"] / r["horas"]) if r["horas"] > 0 else 0.0, axis=1)
            mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['utr']:.2f} UTR)", axis=1)

        elif tipo_grafico == "Corridas aceitas":
            ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(columns={"numero_de_corridas_ofertadas": "ref"})
            mensal = mensal.merge(ref, on="mes_ano", how="left")
            mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).fillna(0)
            mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.0f}%)", axis=1)

        elif tipo_grafico == "Corridas rejeitadas":
            ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum().rename(columns={"numero_de_corridas_ofertadas": "ref"})
            mensal = mensal.merge(ref, on="mes_ano", how="left")
            mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).fillna(0)
            mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.0f}%)", axis=1)

        elif tipo_grafico == "Corridas completadas":
            ref = df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"].sum().rename(columns={"numero_de_corridas_aceitas": "ref"})
            mensal = mensal.merge(ref, on="mes_ano", how="left")
            mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).fillna(0)
            mensal["label"] = mensal.apply(lambda r: f"{int(r['valor'])} ({r['pct']:.0f}%)", axis=1)

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
        st.plotly_chart(fig, use_container_width=True)

        if not df_mes_atual.empty:
            por_dia = (
                df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                .groupby("dia", as_index=False)[col]
                .sum()
                .rename(columns={col: "valor"})
            )
            fig2 = px.line(
                por_dia,
                x="dia",
                y="valor",
                title=f"📈 {label} por dia (mês atual)",
                template="plotly_dark",
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ---------------------------------------------------------
    # 📅 Números gerais do ano (embaixo, letra maior)
    # ---------------------------------------------------------
    st.divider()
    st.markdown("Números gerais do ano atual")

    tot_ofert = df_ano_atual.get("numero_de_corridas_ofertadas", pd.Series(dtype=float)).sum()
    tot_aceit = df_ano_atual.get("numero_de_corridas_aceitas", pd.Series(dtype=float)).sum()
    tot_rej = df_ano_atual.get("numero_de_corridas_rejeitadas", pd.Series(dtype=float)).sum()
    tot_comp = df_ano_atual.get("numero_de_corridas_completadas", pd.Series(dtype=float)).sum()

    tx_aceit_ano = (tot_aceit / tot_ofert * 100) if tot_ofert > 0 else 0
    tx_rej_ano = (tot_rej / tot_ofert * 100) if tot_ofert > 0 else 0
    tx_comp_ano = (tot_comp / tot_aceit * 100) if tot_aceit > 0 else 0

    # Ativos (SH): quantidade de entregadores únicos no ano
    tot_sh = df_ano_atual["pessoa_entregadora"].nunique() if "pessoa_entregadora" in df_ano_atual.columns else 0

    st.markdown(
        f"<div style='font-size:1.2rem; line-height:1.6; margin-top:1em;'>"
        f"<b>Ofertadas:</b> {int(tot_ofert):,}<br>"
        f"<b>Aceitas:</b> {int(tot_aceit):,} ({tx_aceit_ano:.1f}%)<br>"
        f"<b>Rejeitadas:</b> {int(tot_rej):,} ({tx_rej_ano:.1f}%)<br>"
        f"<b>Completadas:</b> {int(tot_comp):,} ({tx_comp_ano:.1f}%)<br>"
        f"<b>Ativos (SH):</b> {int(tot_sh):,}"
        f"</div>",
        unsafe_allow_html=True,
    )
