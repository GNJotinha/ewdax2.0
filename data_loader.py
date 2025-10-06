# data_loader.py — versão Supabase (lendo da view)
import streamlit as st
import pandas as pd
from supabase import create_client, Client

SHEET = "Base 2025"  # só mantido pra compat, não é mais usado

# ----------------------------
# Conexão (lazy) com Supabase
# ----------------------------
@st.cache_resource(show_spinner=False)
def _get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

# ----------------------------
# Fetch paginado da view
# ----------------------------
def _fetch_all_from_view(view_name: str, order_col: str = "data_do_periodo", page_size: int = 2000):
    sb = _get_client()
    off = 0
    rows = []
    while True:
        # PostgREST usa range inclusivo
        start = off
        end = off + page_size - 1
        q = (
            sb.table(view_name)
              .select("*")
              .order(order_col, desc=False)
              .range(start, end)
        )
        res = q.execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        off += page_size
    return rows

@st.cache_data(show_spinner=True)
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None) -> pd.DataFrame:
    """
    Lê *direto* da view `public.view_movee_base` no Supabase.
    `prefer_drive` e `_ts` permanecem só para manter compat com a Home (forçar recarregar = limpar cache).
    """
    # compat: se vier pedido de "refresh", só derruba o cache
    _ = _ts  # não usamos, só pra assinatura igual

    rows = _fetch_all_from_view("view_movee_base", order_col="data_do_periodo", page_size=5000)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Tipos essenciais (só reforçando, a view já manda certinho)
    # Datas
    for col in ["data_do_periodo", "data", "mes_ano"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "data" in df.columns:
        # manter 'data' como date (o app usa .dt.date em alguns pontos)
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
        df["mes"] = df.get("mes", pd.to_datetime(df["data"], errors="coerce")).astype("int", errors="ignore")
    # Numéricos críticos
    num_cols = [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
        "numero_de_corridas_canceladas_pela_pessoa_entregadora",
        "numero_de_pedidos_aceitos_e_concluidos",
        "soma_das_taxas_das_corridas_aceitas",
        "tempo_disponivel_escalado",  # bps 0..10000
        "segundos_abs_raw",
        "segundos_abs",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Garantias mínimas de schema que o app usa em várias telas
    if "uuid" not in df.columns and "id_da_pessoa_entregadora" in df.columns:
        df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
    if "pessoa_entregadora_normalizado" not in df.columns and "pessoa_entregadora" in df.columns:
        # fallback: minúsculo sem acento ficava na view; aqui só garante algo
        df["pessoa_entregadora_normalizado"] = (
            df["pessoa_entregadora"].astype(str).str.normalize("NFKD")
              .str.encode("ascii", "ignore").str.decode("ascii").str.lower().str.strip()
        )

    return df
