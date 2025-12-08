# views/adicional_por_turno.py
import streamlit as st
import pandas as pd
from utils import calcular_tempo_online  # usa a mesma lógica do resto do sistema

VALOR_ADICIONAL_HORA = 2.15
LIMIAR_ACEITACAO = 70.0  # %

def _num(x) -> int:
    try:
        return int(pd.to_numeric(x, errors="coerce").fillna(0))
    except Exception:
        return 0

def _pct(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return float(num / den * 100.0)

def _linha_status(df_chunk: pd.DataFrame) -> pd.Series:
    """
    Calcula métricas para um (entregador, data, turno) e retorna:
    - horas_online
    - aceitacao_%
    - online_%
    - recebe (bool)
    - valor_adicional_hora
    """
    if df_chunk is None or df_chunk.empty:
        return pd.Series({
            "horas_online": 0.0,
            "aceitacao_%": 0.0,
            "online_%": 0.0,
            "recebe": False,
            "valor_adicional_hora": 0.0,
        })

    ofertadas = pd.to_numeric(
        df_chunk.get("numero_de_corridas_ofertadas", 0),
        errors="coerce"
    ).fillna(0).sum()
    aceitas = pd.to_numeric(
        df_chunk.get("numero_de_corridas_aceitas", 0),
        errors="coerce"
    ).fillna(0).sum()

    # segundos_abs já vem clipado (sem negativos) :contentReference[oaicite:0]{index=0}
    seg = pd.to_numeric(
        df_chunk.get("segundos_abs", 0),
        errors="coerce"
    ).fillna(0).sum()
    horas = float(seg) / 3600.0 if seg > 0 else 0.0

    acc_pct = _pct(aceitas, ofertadas)
    online_pct = calcular_tempo_online(df_chunk)  # 0–100 já tratado :contentReference[oaicite:1]{index=1}

    recebe = (acc_pct >= LIMIAR_ACEITACAO) and (online_pct > 0)
    valor_h = VALOR_ADICIONAL_HORA if recebe else 0.0

    return pd.Series({
        "horas_online": horas,
        "aceitacao_%": acc_pct,
        "online_%": online_pct,
        "recebe": recebe,
        "valor_adicional_hora": valor_h,
    })

def _style_status(val):
    if val == "SIM":
        # verde
        return "background-color:#163d24; color:#2ecc71; font-weight:bold;"
    else:
        # vermelho
        return "background-color:#3d1616; color:#e74c3c; font-weight:bold;"

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("💸 Adicional por turno — Lista por período")

    base = df.copy()

    # Normaliza data
    if "data" in base.columns:
        base["data"] = pd.to_datetime(base["data"], errors="coerce")
    elif "data_do_periodo" in base.columns:
        base["data"] = pd.to_datetime(base["data_do_periodo"], errors="coerce")
    else:
        st.error("Coluna de data ausente (espere 'data' ou 'data_do_periodo').")
        return

    base = base.dropna(subset=["data"])
    if base.empty:
        st.info("Sem dados válidos.")
        return

    # Filtros básicos
    data_min = pd.to_datetime(base["data"]).min().date()
    data_max = pd.to_datetime(base["data"]).max().date()

    c1, c2, c3 = st.columns([2, 2, 1])

    with c1:
        periodo = st.date_input(
            "Período",
            [data_min, data_max],
            format="DD/MM/YYYY"
        )

    with c2:
        nomes = sorted(base["pessoa_entregadora"].dropna().unique().tolist())
        filtro_nomes = st.multiselect(
            "Filtrar entregadores (opcional)",
            nomes,
            help="Se vazio, mostra todos."
        )

    with c3:
        turnos = sorted(
            [x for x in base.get("periodo", pd.Series(dtype=object)).dropna().unique()]
        )
        filtro_turnos = st.multiselect(
            "Turnos",
            turnos
        )

    # Aplica filtro de período
    df_filtrado = base.copy()
    if len(periodo) == 2:
        ini = pd.to_datetime(periodo[0])
        fim = pd.to_datetime(periodo[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df_filtrado = df_filtrado[(df_filtrado["data"] >= ini) & (df_filtrado["data"] <= fim)]
    elif len(periodo) == 1:
        dia = pd.to_datetime(periodo[0])
        df_filtrado = df_filtrado[df_filtrado["data"].dt.date == dia.date()]

    if filtro_nomes:
        df_filtrado = df_filtrado[df_filtrado["pessoa_entregadora"].isin(filtro_nomes)]

    if filtro_turnos:
        df_filtrado = df_filtrado[df_filtrado["periodo"].isin(filtro_turnos)]

    # Garante colunas essenciais
    if "pessoa_entregadora" not in df_filtrado.columns:
        st.error("Coluna 'pessoa_entregadora' não encontrada na base.")
        return
    if "periodo" not in df_filtrado.columns:
        df_filtrado["periodo"] = "(sem turno)"

    if df_filtrado.empty:
        st.info("❌ Nenhum dado no período/filtros selecionados.")
        return

    df_filtrado["data_dia"] = df_filtrado["data"].dt.date

    # Agrupa por Entregador + Data + Turno
    group_cols = ["pessoa_entregadora", "data_dia", "periodo"]
    agrupado = (
        df_filtrado
        .groupby(group_cols, dropna=False)
        .apply(_linha_status)
        .reset_index()
    )

    if agrupado.empty:
        st.info("❌ Nenhum dado após o agrupamento.")
        return

    # Monta coluna de status legível
    agrupado["Recebe adicional?"] = agrupado["recebe"].map(lambda x: "SIM" if x else "NÃO")

    # Ordenação padrão
    agrupado = agrupado.sort_values(
        by=["data_dia", "pessoa_entregadora", "periodo"]
    ).reset_index(drop=True)

    # Monta tabela final
    tabela = agrupado[[
        "data_dia",
        "pessoa_entregadora",
        "periodo",
        "horas_online",
        "aceitacao_%",
        "online_%",
        "valor_adicional_hora",
        "Recebe adicional?",
    ]].rename(columns={
        "data_dia": "Data",
        "pessoa_entregadora": "Entregador",
        "periodo": "Turno",
        "horas_online": "Horas online",
        "aceitacao_%": "Aceitação %",
        "online_%": "Tempo online %",
        "valor_adicional_hora": "R$/h adicional",
    })

    # KPIs gerais
    total_sim = int((tabela["Recebe adicional?"] == "SIM").sum())
    total_nao = int((tabela["Recebe adicional?"] == "NÃO").sum())
    ent_unicos = tabela["Entregador"].nunique()

    c_k1, c_k2, c_k3 = st.columns(3)
    c_k1.metric("Linhas recebendo adicional", f"{total_sim}")
    c_k2.metric("Linhas sem adicional", f"{total_nao}")
    c_k3.metric("Entregadores únicos no período", f"{ent_unicos}")

    # Estilo verde/vermelho na coluna de status
    styled = (
        tabela
        .style
        .applymap(_style_status, subset=["Recebe adicional?"])
        .format({
            "Horas online": "{:.2f}",
            "Aceitação %": "{:.2f}",
            "Tempo online %": "{:.1f}",
            "R$/h adicional": "R$ {:.2f}",
        })
    )

    st.dataframe(styled, use_container_width=True)

    # Download CSV
    st.download_button(
        "⬇️ Baixar CSV",
        data=tabela.to_csv(index=False, decimal=",").encode("utf-8"),
        file_name="adicional_por_turno_lista.csv",
        mime="text/csv",
        use_container_width=True,
    )
