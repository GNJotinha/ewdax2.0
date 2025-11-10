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

    # ---------------------------------------------------------
    # Datas base
    # ---------------------------------------------------------
    hoje = pd.Timestamp.today()
    mes_atual = int(hoje.month)
    ano_atual = int(hoje.year)

    df = _ensure_mes_ano(df)

    # ---------------------------------------------------------
    # Filtros por praça / turno (se existirem)
    # ---------------------------------------------------------
    praca_col = None
    for cand in ("praca", "praça", "subpraca", "sub_praca"):
        if cand in df.columns:
            praca_col = cand
            break

    turno_col = None
    for cand in ("turno", "tipo_turno", "periodo"):
        if cand in df.columns:
            turno_col = cand
            break

    col_f1, col_f2 = st.columns(2)

    praca_sel = None
    if praca_col is not None:
        op_praca = ["Todas"] + sorted(df[praca_col].dropna().unique().tolist())
        praca_sel = col_f1.selectbox("Praça", op_praca, index=0)

    turno_sel = None
    if turno_col is not None:
        op_turno = ["Todos"] + sorted(df[turno_col].dropna().unique().tolist())
        turno_sel = col_f2.selectbox("Turno", op_turno, index=0)

    # aplica filtros
    if praca_col is not None and praca_sel not in (None, "Todas"):
        df = df[df[praca_col] == praca_sel]
    if turno_col is not None and turno_sel not in (None, "Todos"):
        df = df[df[turno_col] == turno_sel]

    # ---------------------------------------------------------
    # recortes de ano e mês (já filtrados por praça/turno)
    # ---------------------------------------------------------
    if "ano" in df.columns:
        df_ano_atual = df[df["ano"] == ano_atual].copy()
    else:
        if "data" in df.columns:
            df["data"] = pd.to_datetime(df["data"], errors="coerce")
            df_ano_atual = df[df["data"].dt.year == ano_atual].copy()
        else:
            df_ano_atual = df.copy()

    if {"mes", "ano"}.issubset(df.columns):
        df_mes_atual = df[(df.get("mes") == mes_atual) & (df.get("ano") == ano_atual)].copy()
    else:
        if "data" in df.columns:
            df["data"] = pd.to_datetime(df["data"], errors="coerce")
            df_mes_atual = df[
                (df["data"].dt.month == mes_atual) & (df["data"].dt.year == ano_atual)
            ].copy()
        else:
            df_mes_atual = df.copy()

    # ---------------------------------------------------------
    # Horas realizadas
    # ---------------------------------------------------------
    if tipo_grafico == "Horas realizadas":
        mensal_horas = (
            df.groupby("mes_ano", as_index=False)["segundos_abs"]
            .sum()
            .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
        )
        mensal_horas["mes_rotulo"] = pd.to_datetime(mensal_horas["mes_ano"]).dt.strftime(
            "%b/%y"
        )

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
            fig_d = px.line(
                por_dia,
                x="dia",
                y="horas",
                title="📈 Horas por dia (mês atual)",
                labels={"dia": "Dia", "horas": "Horas"},
                template="plotly_dark",
            )
            fig_d.update_layout(margin=dict(t=60, b=30, l=40, r=40))
            st.metric("⏱️ Horas realizadas no mês", f"{por_dia['horas'].sum():.2f}h")
            st.plotly_chart(fig_d, use_container_width=True)
        else:
            st.info("Sem dados no mês atual.")

    # ---------------------------------------------------------
    # Entregadores ativos
    # ---------------------------------------------------------
    elif tipo_grafico == "Entregadores ativos":
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
            fig2.update_layout(margin=dict(t=60, b=30, l=40, r=40))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados no mês atual.")

    # ---------------------------------------------------------
    # Corridas ofertadas / aceitas / rejeitadas / completadas
    # ---------------------------------------------------------
    else:
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
            mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).fillna(0)
            mensal["label"] = mensal.apply(
                lambda r: f"{int(r['valor'])} ({r['pct']:.0f}%)", axis=1
            )

        elif tipo_grafico == "Corridas rejeitadas":
            ref = (
                df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"]
                .sum()
                .rename(columns={"numero_de_corridas_ofertadas": "ref"})
            )
            mensal = mensal.merge(ref, on="mes_ano", how="left")
            mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).fillna(0)
            mensal["label"] = mensal.apply(
                lambda r: f"{int(r['valor'])} ({r['pct']:.0f}%)", axis=1
            )

        elif tipo_grafico == "Corridas completadas":
            ref = (
                df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"]
                .sum()
                .rename(columns={"numero_de_corridas_aceitas": "ref"})
            )
            mensal = mensal.merge(ref, on="mes_ano", how="left")
            mensal["pct"] = (mensal["valor"] / mensal["ref"] * 100).fillna(0)
            mensal["label"] = mensal.apply(
                lambda r: f"{int(r['valor'])} ({r['pct']:.0f}%)", axis=1
            )
        else:
            mensal["label"] = mensal["valor"].astype(str)

        # ---------- Gráfico mensal ----------
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

        # ---------- Por dia (mês atual) ----------
        if not df_mes_atual.empty:
            por_dia = (
                df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                .groupby("dia", as_index=False)[col]
                .sum()
                .rename(columns={col: "valor"})
                .sort_values("dia")
            )

            fig2 = px.line(
                por_dia,
                x="dia",
                y="valor",
                title=f"📈 {label} por dia (mês atual)",
                labels={"dia": "Dia", "valor": label},
                template="plotly_dark",
            )
            fig2.update_layout(margin=dict(t=60, b=30, l=40, r=40))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados no mês atual.")

    # ---------------------------------------------------------
    # 📅 Números gerais do ano (embaixo, linha por linha)
    # ---------------------------------------------------------
    st.divider()
    st.markdown("### 📅 Números gerais do ano atual")

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

    tx_aceit_ano = (tot_aceit / tot_ofert * 100) if tot_ofert > 0 else 0
    tx_rej_ano = (tot_rej / tot_ofert * 100) if tot_ofert > 0 else 0
    tx_comp_ano = (tot_comp / tot_aceit * 100) if tot_aceit > 0 else 0

    # Ativos (SH) – tenta achar a coluna mais provável
    tot_sh = 0
    for cand in ("sh", "ativos", "entregadores_ativos", "pessoa_entregadora"):
        if cand in df_ano_atual.columns:
            if cand == "pessoa_entregadora":
                tot_sh = df_ano_atual[cand].nunique()
            else:
                tot_sh = df_ano_atual[cand].sum()
            break

    st.markdown(
        f"**Ofertadas:** {int(tot_ofert):,}".replace(",", ".")
    )
    st.markdown(
        f"**Aceitas:** {int(tot_aceit):,} ({tx_aceit_ano:.1f}%)".replace(",", ".")
    )
    st.markdown(
        f"**Rejeitadas:** {int(tot_rej):,} ({tx_rej_ano:.1f}%)".replace(",", ".")
    )
    st.markdown(
        f"**Completadas:** {int(tot_comp):,} ({tx_comp_ano:.1f}%)".replace(",", ".")
    )
    st.markdown(
        f"**Ativos (SH):** {int(tot_sh):,}".replace(",", ".")
    )
