# data_loader.py — Supabase-first com fallback opcional p/ Excel
import pandas as pd
import streamlit as st
from supabase import create_client
from pathlib import Path
from utils import normalizar, tempo_para_segundos

SHEET = "Base 2025"  # usado só no fallback Excel

# --------------------------
# Conexão Supabase
# --------------------------
def _client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def _fetch_all(client, table: str, chunk: int = 5000) -> list[dict]:
    """Baixa tudo em páginas para evitar truncar resultados."""
    out, start = [], 0
    while True:
        end = start + chunk - 1
        res = client.table(table).select("*").range(start, end).execute()
        rows = res.data or []
        out.extend(rows)
        if len(rows) < chunk:
            break
        start = end + 1
    return out

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    # Datas básicas
    if "data_do_periodo" in df.columns:
        df["data_do_periodo"] = pd.to_datetime(df["data_do_periodo"], errors="coerce")
        df["data"]    = df["data_do_periodo"].dt.date
        df["mes"]     = df["data_do_periodo"].dt.month
        df["ano"]     = df["data_do_periodo"].dt.year
        df["mes_ano"] = df["data_do_periodo"].dt.to_period("M").dt.to_timestamp()
    elif "data" in df.columns:
        df["data"]    = pd.to_datetime(df["data"], errors="coerce")
        df["mes"]     = df["data"].dt.month
        df["ano"]     = df["data"].dt.year
        df["mes_ano"] = df["data"].dt.to_period("M").dt.to_timestamp()
        df["data"]    = df["data"].dt.date

    # Nome normalizado
    if "pessoa_entregadora" in df.columns and "pessoa_entregadora_normalizado" not in df.columns:
        df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)

    # UUID
    if "uuid" not in df.columns:
        if "id_da_pessoa_entregadora" in df.columns:
            df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
        else:
            df["uuid"] = ""

    # Segundos abs (raw + clip) — se já vier na view, respeita
    if "segundos_abs_raw" not in df.columns:
        if "tempo_disponivel_absoluto" in df.columns:
            df["segundos_abs_raw"] = df["tempo_disponivel_absoluto"].apply(tempo_para_segundos).fillna(0).astype(int)
        else:
            df["segundos_abs_raw"] = 0
    df["segundos_negativos_flag"] = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0) < 0
    if "segundos_abs" not in df.columns:
        sr = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
        df["segundos_abs"] = sr.where(sr >= 0, 0).astype(int)

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

    return df

def _carregar_supabase() -> pd.DataFrame:
    client = _client()
    source = st.secrets.get("SUPABASE_SOURCE", "view_movee_base")  # recomendado
    table_name = source.split(".")[-1]  # supabase-py usa só o nome sem schema
    rows = _fetch_all(client, table_name)
    df = pd.DataFrame(rows)
    if df.empty:
        st.error(f"❌ Supabase retornou 0 linhas da fonte: {table_name}.")
        st.stop()
    return _normalize_df(df)

# --------------------------
# Fallback Excel (opcional)
# --------------------------
def _ler_excel(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET)
    return _normalize_df(df)

# --------------------------
# API pública do app
# --------------------------
@st.cache_data(show_spinner=False)
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None) -> pd.DataFrame:
    """
    Carrega dados do Supabase. Se falhar e existir Calendarios.xlsx local,
    usa como fallback.
    """
    try:
        return _carregar_supabase()
    except Exception as e:
        st.warning(f"⚠️ Falha ao ler do Supabase: {e}")
        backup = Path("Calendarios.xlsx")
        if backup.exists() and backup.stat().st_size > 0:
            st.info("Usando fallback local: Calendarios.xlsx")
            return _ler_excel(backup)
        st.stop()
