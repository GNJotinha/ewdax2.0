# data_loader.py — Supabase-only / paginação estável / normalização / compatível com main.py
import pandas as pd
import streamlit as st
from supabase import create_client

# ---------------------------
# Conexão
# ---------------------------
def _client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]          # use service_role no Cloud para ver TUDO
    return create_client(url, key)

# ---------------------------
# Contagem total + paginação estável (id -> data_do_periodo)
# ---------------------------
def _total_rows(client, table: str) -> int:
    res = client.table(table).select("id", count="exact").limit(1).execute()
    return int(res.count or 0)

def _fetch_all_ordered(client, table: str, page_size: int = 1000) -> list[dict]:
    # coluna de ordenação estável
    order_col = "id"
    try:
        client.table(table).select("id").limit(1).execute()
    except Exception:
        order_col = "data_do_periodo"

    total = _total_rows(client, table)
    out, start = [], 0

    while True:
        end = start + page_size - 1
        res = (
            client.table(table)
                  .select("*")
                  .order(order_col, desc=False)
                  .range(start, end)
                  .execute()
        )
        rows = res.data or []
        out.extend(rows)

        got = len(rows)
        start += got

        if got < page_size or len(out) >= total:
            break

    return out

# ---------------------------
# Normalização
# ---------------------------
def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    # Datas base (UTC -> naive) + derivadas
    base_dt = pd.to_datetime(
        df.get("data_do_periodo", df.get("data")),
        errors="coerce",
        utc=True
    ).dt.tz_convert(None)

    df["data_do_periodo"] = base_dt
    df["data"] = base_dt.dt.date

    # mes/ano podem vir como texto → força numérico
    df["mes"] = pd.to_numeric(df.get("mes", base_dt.dt.month), errors="coerce").fillna(base_dt.dt.month).astype(int)
    df["ano"] = pd.to_numeric(df.get("ano", base_dt.dt.year),  errors="coerce").fillna(base_dt.dt.year).astype(int)
    df["mes_ano"] = base_dt.dt.to_period("M").dt.to_timestamp()

    # UUID (fallback se a view não trouxer)
    if "uuid" not in df.columns:
        df["uuid"] = df.get("id_da_pessoa_entregadora", "").astype(str)

    # Segundos absolutos (se a view não trouxer pronto)
    if "segundos_abs_raw" not in df.columns:
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

    # Dedup (segurança contra paginação)
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"]).reset_index(drop=True)
    else:
        df = df.drop_duplicates().reset_index(drop=True)

    return df

# ---------------------------
# API pública (compatível com main.py)
# ---------------------------
@st.cache_data(show_spinner=False)
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None) -> pd.DataFrame:
    """
    Mantém a assinatura usada no main.py. `prefer_drive` é ignorado.
    Carrega SEMPRE do Supabase. Se falhar, exibe erro e interrompe.
    Use `_ts` para invalidar o cache quando clicar em "Atualizar dados".
    """
    try:
        client = _client()
        source = st.secrets.get("SUPABASE_SOURCE", "view_movee_base")
        table = source.split(".")[-1]  # supabase-py não usa schema qualifier
        rows = _fetch_all_ordered(client, table, page_size=1000)
        if not rows:
            st.error("❌ Supabase retornou 0 linhas.")
            st.stop()
        df = pd.DataFrame(rows)
        df = _normalize_df(df)

        # Debug opcional: total carregado (útil na Home)
        st.session_state["_debug_total_rows"] = len(df)

        return df
    except Exception as e:
        # Mostra o erro real para você saber o que ajustar (permissão/RLS/pacote)
        st.exception(e)
        st.stop()
