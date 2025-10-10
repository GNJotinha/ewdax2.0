# views/meu_modo.py
import streamlit as st
import pandas as pd
from utils import calcular_tempo_online

def _fmt_pct(x: float) -> str:
    try:
        return f"{float(x):.2f}%".replace(".", ",")
    except Exception:
        return "0,00%"

def _num(x) -> int:
    try:
        return int(pd.to_numeric(x, errors="coerce").fillna(0))
    except Exception:
        return 0

def _tem_atuacao(df_chunk: pd.DataFrame) -> bool:
    if df_chunk is None or df_chunk.empty:
        return False
    soma = (
        pd.to_numeric(df_chunk.get("segundos_abs", 0), errors="coerce").fillna(0)
      + pd.to_numeric(df_chunk.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
      + pd.to_numeric(df_chunk.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
      + pd.to_numeric(df_chunk.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)
    )
    return bool((soma > 0).any())

def _bloco_whatsapp(nome: str, df_chunk: pd.DataFrame) -> str:
    """Monta o bloco no formato pedido."""
    if df_chunk is None or df_chunk.empty or not _tem_atuacao(df_chunk):
        return f"*{nome}*\n\n✘ Sem atuação no período"

    # métricas
    ofertadas  = int(pd.to_numeric(df_chunk.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
    aceitas    = int(pd.to_numeric(df_chunk.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
    rejeitadas = int(pd.to_numeric(df_chunk.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum())
    completas  = int(pd.to_numeric(df_chunk.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0).sum())

    acc_pct  = (aceitas   / ofertadas * 100.0) if ofertadas  > 0 else 0.0
    rej_pct  = (rejeitadas/ ofertadas * 100.0) if ofertadas  > 0 else 0.0
    comp_pct = (completas / aceitas   * 100.0) if aceitas    > 0 else 0.0

    online_pct = calcular_tempo_online(df_chunk)

    linhas = [
        f"*{nome}*",
        f"- Tempo online: {_fmt_pct(online_pct)}",
        f"- Ofertadas: {ofertadas}",
        f"- Aceitas: {aceitas} ({_fmt_pct(acc_pct)})",
        f"- Rejeitadas: {rejeitadas} ({_fmt_pct(rej_pct)})",
        f"- Completas: {completas} ({_fmt_pct(comp_pct)})",
    ]
    return "\n".join(linhas)

def render(df: pd.DataFrame, USUARIOS: dict):
    # --- trava de admin ---
    user  = st.session_state.get("usuario", "")
    nivel = USUARIOS.get(user, {}).get("nivel", "")
    if nivel != "dev":
        st.error("Acesso negado.")
        st.stop()

    st.header("Relatório de saídas")

    # normaliza data
    base = df.copy()
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

    data_min = pd.to_datetime(base["data"]).min().date()
    data_max = pd.to_datetime(base["data"]).max().date()

    # filtros
    c1, c2 = st.columns([2, 3])
    with c1:
        nomes = sorted(base["pessoa_entregadora"].dropna().unique().tolist())
        sel = st.multiselect("Entregadores", nomes, help="Você pode escolher vários.")
    with c2:
        periodo = st.date_input("Período", [data_min, data_max], format="DD/MM/YYYY")

    gerar = st.button("Gerar texto", type="primary", use_container_width=True, disabled=(len(sel) == 0))

    if not gerar:
        st.caption("Selecione entregadores.")
        return

    # aplica período
    df_filtrado = base.copy()
    if len(periodo) == 2:
        ini, fim = pd.to_datetime(periodo[0]), pd.to_datetime(periodo[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df_filtrado = df_filtrado[(df_filtrado["data"] >= ini) & (df_filtrado["data"] <= fim)]
    elif len(periodo) == 1:
        dia = pd.to_datetime(periodo[0])
        df_filtrado = df_filtrado[df_filtrado["data"].dt.date == dia.date()]

    # monta blocos
    blocos = []
    for nome in sel:
        chunk = df_filtrado[df_filtrado["pessoa_entregadora"] == nome].copy()
        # para o cálculo de online, manteremos colunas originais; já protegemos na função
        texto = _bloco_whatsapp(nome, chunk)
        blocos.append(texto)

    saida = "\n\n".join(blocos).strip()
    st.text_area("Relatório de saídas", value=saida, height=500)




