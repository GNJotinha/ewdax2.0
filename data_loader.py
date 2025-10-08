# data_loader.py — Supabase-only, paginação ordenada, normalização e cache
import pandas as pd
import streamlit as st
from supabase import create_client

# =========================
# Conexão
# =========================
def _client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

# =========================
# Fetch paginado COM ordem estável
# =========================
def _fetch_all_ordered(client, table: str, chunk: int = 5000) -> list[dict]:
    """
    Busca todos os registros em páginas ordenadas, evitando duplicação/perda.
    Tenta ordenar por 'id'; se não existir, usa 'data_do_periodo'.
    """
    # decide coluna de ordenação
    order_col = "id"
    try:
        client.table(table).select("id").limit(1).execute()
    except Exception:
        order_col = "data_do_periodo"

    out, start = [], 0
    while True:
        end = start + chunk - 1
        q = (client.table(table)
                    .select("*")
                    .order(order_col, desc=False)
                    .range(start, end))
        res = q.execute()
        rows = res.data or []
        out.extend(rows)
        if len(rows) < chunk:
            break
        start = end + 1
    return out

# =========================
# Normalização de DF
# =========================
def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    # Datas base (UTC→naive) e colunas derivadas
    base_dt = pd.to_datetime(
        df.get("data_do_periodo", df.get("data")),
        errors="coerce",
        utc=True
    ).dt.tz_convert(None)

    df["data_do_periodo"] = base_dt
    df["data"] = base_dt.dt.date

    # mes/ano podem vir como texto: força numérico
    if "mes" in df.columns:
        df["mes"] = pd.to_numeric(df["mes"], errors="coerce")
    else:
        df["mes"] = base_dt.dt.month
    if "ano" in df.columns:
        df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    else:
        df["ano"] = base_dt.dt.year

    df["mes"] = df["mes"].fillna(base_dt.dt.month).astype(int)
    df["ano"] = df["ano"].fillna(base_dt.dt.year).astype(int)
    df["mes_ano"] = base_dt.dt.to_period("M").dt.to_timestamp()

    # UUID
    if "uuid" not in df.columns:
        if "id_da_pessoa_entregadora" in df.columns:
            df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
        else:
            df["uuid"] = ""

    # Segundos absolutos (se a view não trouxer pronto)
    if "segundos_abs_raw" not in df.columns:
        # se não existe na origem, define 0; cálculo detalhado já é feito na view
        df["segundos_abs_raw"] = 0
    df["segundos_abs"] = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
    df["segundos_abs"] = df["segundos_abs"].where(df["segundos_abs"] >= 0, 0).astype(int)
    df["segundos_negativos_flag"] = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0) < 0

    # Numéricas chave
    for c in [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
        "tempo_disponivel_escalado",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Dedup
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"]).reset_index(drop=True)
    else:
        df = df.drop_duplicates().reset_index(drop=True)

    return df

# =========================
# API pública — sem fallback
# =========================
@st.cache_data(show_spinner=False)
def carregar_dados(_ts: float | None = None) -> pd.DataFrame:
    """
    Sempre carrega do Supabase. Se der erro, exibe o stack e interrompe.
    Use _ts para 'quebrar' o cache quando clicar em Atualizar dados.
    """
    try:
        client = _client()
        source = st.secrets.get("SUPABASE_SOURCE", "view_movee_base")
        table = source.split(".")[-1]  # supabase-py usa só o nome (sem schema)
        rows = _fetch_all_ordered(client, table)
        if not rows:
            st.error("❌ Supabase retornou 0 linhas.")
            st.stop()
        df = pd.DataFrame(rows)
        return _normalize_df(df)
    except Exception as e:
        # Mostra o erro real para debug (em produção você pode trocar por st.error)
        st.exception(e)
        st.stop()
