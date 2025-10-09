# saidas.py
import streamlit as st
import pandas as pd
from utils import calcular_tempo_online

# ✅ QUEM PODE ENTRAR AQUI
ALLOWED_USERS = set(
    st.secrets.get("USUARIOS_PRIVADOS", {}).get("BUSCA_MULTI", [])
)

def _fmt_pct_br(v: float, casas: int = 2) -> str:
    try:
        return f"{float(v):.{casas}f}%".replace(".", ",")
    except Exception:
        return "0,00%"

def _pct(num: float, den: float) -> str:
    try:
        if den is None or den == 0:
            return "0,00%"
        return f"{(float(num)/float(den))*100:.2f}%".replace(".", ",")
    except Exception:
        return "0,00%"

def _mk_bloco(nome: str, df_p: pd.DataFrame) -> str:
    # Sem dados (nenhuma linha) => sem atuação
    if df_p.empty:
        return f"*{nome}*\nX Sem dados de atuação"

    # Filtra linhas com algum sinal de atividade
    soma = (
        pd.to_numeric(df_p.get("segundos_abs", 0), errors="coerce").fillna(0)
      + pd.to_numeric(df_p.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
      + pd.to_numeric(df_p.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
      + pd.to_numeric(df_p.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)
    )
    df_act = df_p.loc[soma > 0].copy()
    if df_act.empty:
        return f"*{nome}*\nX Sem dados de atuação"

    turnos = int(df_act.shape[0])
    ofertadas  = int(pd.to_numeric(df_act.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
    aceitas    = int(pd.to_numeric(df_act.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
    rejeitadas = int(pd.to_numeric(df_act.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum())
    completas  = int(pd.to_numeric(df_act.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0).sum())

    online = calcular_tempo_online(df_act)  # 0–100
    online_str = _fmt_pct_br(online, 2)

    aceitas_pct    = _pct(aceitas, ofertadas)
    rejeitadas_pct = _pct(rejeitadas, ofertadas)
    completas_pct  = _pct(completas, aceitas)   # conclusão sobre aceitas

    linhas = [
        f"*{nome}*",
        f"Tempo Online: {online_str}",
        f"Turnos: {turnos}",
        f"Ofertadas: {ofertadas}",
        f"Aceitas: {aceitas} ({aceitas_pct})",
        f"Rejeitadas: {rejeitadas} ({rejeitadas_pct})",
        f"Completas: {completas} ({completas_pct})",
    ]
    return "\n".join(linhas)

def render(df: pd.DataFrame, USUARIOS: dict):
    # 🔒 bloqueio total: só quem estiver em ALLOWED_USERS entra
    user = st.session_state.get("usuario", "")
    if user not in ALLOWED_USERS:
        st.stop()

    st.header("🔎 Busca múltipla (privado) — Whats")

    # datas do dataframe (assumindo coluna 'data' já normalizada no loader)
    df_local = df.copy()
    df_local["data"] = pd.to_datetime(df_local.get("data"), errors="coerce").dt.date
    data_min = pd.Series(df_local["data"]).dropna().min()
    data_max = pd.Series(df_local["data"]).dropna().max()

    c1, c2 = st.columns([2, 1])
    with c1:
        periodo = st.date_input(
            "Período contínuo:",
            value=[data_min, data_max],
            min_value=data_min, max_value=data_max,
            format="DD/MM/YYYY"
        )
    with c2:
        st.caption("Selecione os nomes e clique em **Gerar Whats**.")

    nomes = sorted(df_local["pessoa_entregadora"].dropna().unique().tolist())
    escol = st.multiselect("Entregadores (multi):", nomes)

    if st.button("Gerar Whats", type="primary", use_container_width=True, disabled=(len(escol)==0)):
        df_cut = df_local.copy()
        if len(periodo) == 2 and periodo[0] and periodo[1]:
            ini, fim = periodo
            df_cut = df_cut[(df_cut["data"] >= ini) & (df_cut["data"] <= fim)]

        blocos = []
        for nome in escol:
            chunk = df_cut[df_cut["pessoa_entregadora"] == nome].copy()
            blocos.append(_mk_bloco(nome, chunk))

        if len(periodo) == 2:
            header = f"Período de análise: {periodo[0].strftime('%d/%m/%Y')} a {periodo[1].strftime('%d/%m/%Y')}"
        elif len(periodo) == 1:
            header = f"Período de análise: {periodo[0].strftime('%d/%m/%Y')}"
        else:
            header = "Período de análise"

        texto = header + "\n\n" + "\n\n".join(blocos)
        st.text_area("Resultado (copiar p/ Whats):", value=texto, height=500)
        st.download_button("⬇️ Baixar .txt", data=texto.encode("utf-8"), file_name="busca_multi_whats.txt", mime="text/plain")
