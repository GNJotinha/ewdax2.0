# data_loader.py — compatível com main.py (aceita prefer_drive e ignora)

import pandas as pd
import streamlit as st
from supabase import create_client

def _client():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def _fetch_all_ordered(client, table: str, chunk: int = 5000) -> list[dict]:
    # tenta ordenar por 'id'; se não existir, usa 'data_do_periodo'
    order_col = "id"
    try:
        client.table(table).select("id").limit(1).execute()
    except Exception:
        order_col = "data_do_periodo"

    out, start = [], 0
    while True:
        end = start + chunk - 1
        res = (client.table(table)
                    .select("*")
                    .order(order_col, desc=False)
                    .range(start, end)
                    .execute())
        rows = res.data or []
        out.extend(rows)
        if len(rows) < chunk:
            break
        start = end + 1
    return out

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    base_dt = pd.to_datetime(df.get("data_do_periodo", df.get("data")), errors="coerce", utc=True).dt.tz_convert(None)
    df["data_do_periodo"] = base_dt
    df["data"] = base_dt.dt.date

    df["mes"] = pd.to_numeric(df.get("mes", base_dt.dt.month), errors="coerce").fillna(base_dt.dt.month).astype(int)
    df["ano"] = pd.to_numeric(df.get("ano", base_dt.dt.year),  errors="coerce").fillna(base_dt.dt.year).astype(int)
    df["mes_ano"] = base_dt.dt.to_period("M").dt.to_timestamp()

    if "uuid" not in df.columns:
        df["uuid"] = df.get("id_da_pessoa_entregadora", "").astype(str)

    if "segundos_abs_raw" not in df.columns:
        df["segundos_abs_raw"] = 0
    df["segundos_abs"] = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
    df["segundos_abs"] = df["segundos_abs"].where(df["segundos_abs"] >= 0, 0).astype(int)
    df["segundos_negativos_flag"] = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0) < 0

    for c in ["numero_de_corridas_ofertadas","numero_de_corridas_aceitas","numero_de_corridas_rejeitadas","numero_de_corridas_completadas","tempo_disponivel_escalado"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"]).reset_index(drop=True)
    else:
        df = df.drop_duplicates().reset_index(drop=True)
    return df

@st.cache_data(show_spinner=False)
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None) -> pd.DataFrame:
    """
    Mantém a mesma assinatura do main.py.
    `prefer_drive` é ignorado (não há fallback). Usa sempre Supabase.
    `_ts` pode ser passado para forçar recarregar o cache.
    """
    client = _client()
    source = st.secrets.get("SUPABASE_SOURCE", "view_movee_base")
    table = source.split(".")[-1]

    rows = _fetch_all_ordered(client, table)
    if not rows:
        st.error("❌ Supabase retornou 0 linhas.")
        st.stop()

    df = pd.DataFrame(rows)
    return _normalize_df(df)
