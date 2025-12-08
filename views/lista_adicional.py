import io
import streamlit as st
import pandas as pd

from utils import calcular_tempo_online          # online %
from shared import hms_from_hours               # HH:MM:SS

VALOR_ADICIONAL_HORA = 2.15
LIMIAR_ACEITACAO = 70.0  # %

# ------------------------------ #
#   Funções auxiliares
# ------------------------------ #

def _pct(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return float(num / den * 100.0)


def _agg_entregador_turno(df_chunk: pd.DataFrame) -> pd.Series:
    """
    Agrega por (entregador, turno) dentro do período filtrado.
    """
    if df_chunk is None or df_chunk.empty:
        return pd.Series({
            "horas_online": 0.0,
            "horas_hms": "00:00:00",
            "aceitacao_%": 0.0,
            "completas_%": 0.0,
            "recebe": False,
            "valor_total": 0.0,
        })

    ofertadas = pd.to_numeric(df_chunk["numero_de_corridas_ofertadas"], errors="coerce").fillna(0).sum()
    aceitas = pd.to_numeric(df_chunk["numero_de_corridas_aceitas"], errors="coerce").fillna(0).sum()
    completas = pd.to_numeric(df_chunk["numero_de_corridas_completadas"], errors="coerce").fillna(0).sum()

    seg = pd.to_numeric(df_chunk["segundos_abs"], errors="coerce").fillna(0).sum()
    horas = float(seg) / 3600.0 if seg > 0 else 0.0
    horas_hms = hms_from_hours(horas)

    acc_pct = _pct(aceitas, ofertadas)
    comp_pct = _pct(completas, aceitas)

    online_pct = calcular_tempo_online(df_chunk)  # 0–100%

    recebe = (acc_pct >= LIMIAR_ACEITACAO) and (online_pct > 0)
    valor_total = horas * VALOR_ADICIONAL_HORA if recebe else 0.0

    return pd.Series({
        "horas_online": horas,
        "horas_hms": horas_hms,
        "aceitacao_%": acc_pct,
        "completas_%": comp_pct,
        "recebe": recebe,
        "valor_total": valor_total,
    })


def _style_status(val):
    if val == "SIM":
        return "background-color:#163d24; color:#2ecc71; font-weight:bold;"
    else:
        return "background-color:#3d1616; color:#e74c3c; font-weight:bold;"


# ------------------------------ #
#   VIEW PRINCIPAL
# ------------------------------ #

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("💸 Adicional por Turno — Lista consolidada por período")

    base = df.copy()

    # ---------------------- #
    # Normalização de data
    # ---------------------- #
    if "data" in base.columns:
        base["data"] = pd.to_datetime(base["data"], errors="coerce")
    elif "data_do_periodo" in base.columns:
        base["data"] = pd.to_datetime(base["data_do_periodo"], errors="coerce")
    else:
        st.error("Coluna de data ausente ('data' ou 'data_do_periodo').")
        return

    base = base.dropna(subset=["data"])
    if base.empty:
        st.info("Sem dados válidos.")
        return

    # ---------------------- #
    # 1) FILTRO DE PERÍODO
    # ---------------------- #
    data_min = base["data"].min().date()
    data_max = base["data"].max().date()

    periodo = st.date_input(
        "Período de análise",
        [data_min, data_max],
        format="DD/MM/YYYY"
    )

    df_periodo = base.copy()

    if len(periodo) == 2:
        ini = pd.to_datetime(periodo[0])
        fim = pd.to_datetime(periodo[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df_periodo = df_periodo[(df_periodo["data"] >= ini) & (df_periodo["data"] <= fim)]
    elif len(periodo) == 1:
        dia = pd.to_datetime(periodo[0])
        df_periodo = df_periodo[df_periodo["data"].dt.date == dia.date()]

    if df_periodo.empty:
        st.info("❌ Nenhum dado no período selecionado.")
        return

    # ---------------------- #
    # 2) FILTROS ADICIONAIS
    # ---------------------- #
    c1, c2, c3 = st.columns([2, 2, 1])

    with c1:
        nomes = sorted(df_periodo["pessoa_entregadora"].dropna().unique())
        filtro_nomes = st.multiselect("Filtrar entregadores (opcional)", nomes)

    with c2:
        turnos = sorted(df_periodo["periodo"].dropna().unique() if "periodo" in df_periodo else [])
        filtro_turnos = st.multiselect("Filtrar turnos (opcional)", turnos)

    with c3:
        gerar = st.button("Gerar lista", type="primary", use_container_width=True)

    if not gerar:
        st.caption("Selecione o período e clique em **Gerar lista**.")
        return

    df_filtrado = df_periodo.copy()
    if filtro_nomes:
        df_filtrado = df_filtrado[df_filtrado["pessoa_entregadora"].isin(filtro_nomes)]
    if filtro_turnos:
        df_filtrado = df_filtrado[df_filtrado["periodo"].isin(filtro_turnos)]

    if df_filtrado.empty:
        st.info("❌ Sem dados com os filtros aplicados.")
        return

    if "periodo" not in df_filtrado.columns:
        df_filtrado["periodo"] = "(sem turno)"

    # ---------------------- #
    # 3) AGRUPA POR ENTREGADOR + TURNO
    # ---------------------- #
    agrupado = (
        df_filtrado
        .groupby(["pessoa_entregadora", "periodo"], dropna=False)
        .apply(_agg_entregador_turno)
        .reset_index()
    )

    if agrupado.empty:
        st.info("❌ Nenhum dado após o agrupamento.")
        return

    agrupado["Recebe adicional?"] = agrupado["recebe"].map(lambda x: "SIM" if x else "NÃO")

    # ---------------------- #
    # Monta tabela final
    # ---------------------- #
    tabela = agrupado[[
        "pessoa_entregadora",
        "periodo",
        "horas_hms",
        "aceitacao_%",
        "completas_%",
        "Recebe adicional?",
        "valor_total",
    ]].rename(columns={
        "pessoa_entregadora": "Entregador",
        "periodo": "Turno",
        "horas_hms": "Horas online (HH:MM:SS)",
        "aceitacao_%": "Aceitação %",
        "completas_%": "Completas %",
        "valor_total": "Valor R$",
    })

    # arredondamentos
    tabela["Aceitação %"] = tabela["Aceitação %"].round(2)
    tabela["Completas %"] = tabela["Completas %"].round(2)
    tabela["Valor R$"] = tabela["Valor R$"].round(2)

    # ---------------------- #
    # KPIs
    # ---------------------- #
    total_sim = int((tabela["Recebe adicional?"] == "SIM").sum())
    total_nao = int((tabela["Recebe adicional?"] == "NÃO").sum())
    ent_unicos = tabela["Entregador"].nunique()

    k1, k2, k3 = st.columns(3)
    k1.metric("Recebem adicional", f"{total_sim}")
    k2.metric("Sem adicional", f"{total_nao}")
    k3.metric("Entregadores no período", f"{ent_unicos}")

    # ---------------------- #
    # Tabela com estilo (cores)
    # ---------------------- #
    styled = (
        tabela
        .style
        .applymap(_style_status, subset=["Recebe adicional?"])
        .format({
            "Aceitação %": "{:.2f}",
            "Completas %": "{:.2f}",
            "Valor R$": "R$ {:.2f}",
        })
    )

    st.dataframe(styled, use_container_width=True)

    # ---------------------- #
    # Exportar XLSX (openpyxl)
    # ---------------------- #
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        tabela.to_excel(writer, index=False, sheet_name="Adicional_por_turno")

    buffer.seek(0)

    st.download_button(
        "⬇️ Baixar XLSX",
        data=buffer.getvalue(),
        file_name="adicional_por_turno_lista.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
