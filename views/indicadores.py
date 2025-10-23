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


def _calc_utr_media_mensal(df_mes: pd.DataFrame, mes: int, ano: int) -> float:
    """
    UTR 'Médias' por mês: média de (ofertadas/horas) nas linhas de (pessoa, turno, dia) com horas>0.
    Usa relatorios.utr_por_entregador_turno para uma definição consistente com o módulo UTR.
    """
    base = utr_por_entregador_turno(df_mes, mes, ano)
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
        ["Corridas ofertadas","Corridas aceitas","Corridas rejeitadas",
         "Corridas completadas","Horas realizadas","Entregadores ativos"],
        index=0, horizontal=True
    )

    utr_modo = None
    if tipo_grafico == "Corridas ofertadas":
        utr_modo = st.radio("UTR no mensal", ["Absoluto","Médias"], index=0, horizontal=True,
                            help="Escolhe como calcular a UTR mostrada nas labels do gráfico MENSAL de ofertadas.")

    hoje = pd.Timestamp.today()
    mes_atual = int(hoje.month)
    ano_atual = int(hoje.year)
    df = _ensure_mes_ano(df)
    df_mes_atual = df[(df.get("mes") == mes_atual) & (df.get("ano") == ano_atual)].copy()

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
            mensal_horas, x="mes_rotulo", y="horas", text="horas",
            title="Horas realizadas por mês",
            labels={"mes_rotulo":"Mês/Ano","horas":"Horas"},
            template="plotly_dark", color_discrete_sequence=PRIMARY_COLOR
        )
        fig_m.update_traces(texttemplate="<b>%{text:.1f}h</b>", textposition="outside")
        fig_m.update_layout(margin=dict(t=60, b=30, l=40, r=40))
        st.plotly_chart(fig_m, use_container_width=True)

        if not df_mes_atual.empty:
            por_dia = (
                df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                           .groupby("dia", as_index=False)["segundos_abs"].sum()
                           .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
                           .sort_values("dia")
            )
            fig_d = px.line(
                por_dia, x="dia", y="horas",
                title="📈 Horas por dia (mês atual)",
                labels={"dia":"Dia","horas":"Horas"},
                template="plotly_dark"
            )
            fig_d.update_layout(margin=dict(t=60, b=30, l=40, r=40))
            st.metric("⏱️ Horas realizadas no mês", f"{por_dia['horas'].sum():.2f}h")
            st.plotly_chart(fig_d, use_container_width=True)
        else:
            st.info("Sem dados no mês atual.")
        return

    # ---------------------------------------------------------
    # Entregadores ativos
    # ---------------------------------------------------------
    if tipo_grafico == "Entregadores ativos":
        mensal = (
            df.groupby("mes_ano", as_index=False)["pessoa_entregadora"].nunique()
              .rename(columns={"pessoa_entregadora":"entregadores"})
        )
        mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

        fig = px.bar(
            mensal, x="mes_rotulo", y="entregadores", text="entregadores",
            title="Entregadores ativos por mês",
            template="plotly_dark", color_discrete_sequence=PRIMARY_COLOR
        )
        fig.update_traces(texttemplate="<b>%{text}</b>", textposition="outside")
        fig.update_layout(margin=dict(t=60, b=30, l=40, r=40))
        st.plotly_chart(fig, use_container_width=True)

        if not df_mes_atual.empty:
            por_dia = (
                df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                            .groupby("dia", as_index=False)["pessoa_entregadora"].nunique()
                            .rename(columns={"pessoa_entregadora":"entregadores"})
                            .sort_values("dia")
            )
            fig2 = px.line(
                por_dia, x="dia", y="entregadores",
                title="📈 Entregadores por dia (mês atual)",
                labels={"dia":"Dia","entregadores":"Entregadores"},
                template="plotly_dark"
            )
            fig2.update_layout(margin=dict(t=60, b=30, l=40, r=40))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados no mês atual.")
        return

    # ---------------------------------------------------------
    # Genéricos: ofertadas/aceitas/rejeitadas/completadas
    # ---------------------------------------------------------
    col_map = {
        "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Corridas"),
        "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas Aceitas"),
        "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas Rejeitadas"),
        "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas Completadas"),
    }
    col, titulo, label = col_map[tipo_grafico]

    mensal = df.groupby("mes_ano", as_index=False)[col].sum().rename(columns={col: "valor"})
    mensal["mes_rotulo"] = pd.to_datetime(mensal["mes_ano"]).dt.strftime("%b/%y")

    if tipo_grafico == "Corridas ofertadas":
        secs_mensal = df.groupby("mes_ano", as_index=False)["segundos_abs"].sum().rename(columns={"segundos_abs":"segundos"})
        mensal = mensal.merge(secs_mensal, on="mes_ano", how="left")
        mensal["horas"] = pd.to_numeric(mensal["segundos"], errors="coerce").fillna(0) / 3600.0

        if utr_modo == "Médias":
            def _calc_row_utr_media(row):
                ts = pd.to_datetime(row["mes_ano"])
                mes_i, ano_i = int(ts.month), int(ts.year)
                return _calc_utr_media_mensal(df, mes_i, ano_i)
            mensal["utr"] = mensal.apply(_calc_row_utr_media, axis=1)
        else:
            m
