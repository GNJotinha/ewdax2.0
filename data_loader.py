# data_loader.py (Supabase-only)
import os
import re
import pandas as pd
import streamlit as st
from utils import normalizar, tempo_para_segundos

SHEET = "Base 2025"  # não usado mais, mas deixo pra não quebrar import antigo

_RE_MILHAR_DEC = re.compile(r"^\d{1,3}(\.\d{3})+,\d+$")  # 4.118,10
_RE_SO_DEC     = re.compile(r"^\d+,\d+$")               # 12,5
_RE_SO_MILHAR  = re.compile(r"^\d{1,3}(\.\d{3})+$")     # 1.234

def _to_float_ptbr(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    s = s.replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA})

    m = s.str.match(_RE_MILHAR_DEC)
    if m.any():
        s = s.where(~m, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))

    m = s.str.match(_RE_SO_DEC)
    if m.any():
        s = s.where(~m, s.str.replace(",", ".", regex=False))

    m = s.str.match(_RE_SO_MILHAR)
    if m.any():
        s = s.where(~m, s.str.replace(".", "", regex=False))

    return pd.to_numeric(s, errors="coerce").fillna(0)

def _to_int_ptbr(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip().replace({"": pd.NA})
    s = s.str.replace(".", "", regex=False)  # remove milhar
    return pd.to_numeric(s, errors="coerce").fillna(0).astype(int)

@st.cache_data(show_spinner=False)
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None):
    """
    Agora é Supabase-only.
    prefer_drive ficou só pra compatibilidade com o main.py (ignorado).
    _ts serve pra quebrar cache quando você aperta atualizar.
    """
    dsn = None
    try:
        dsn = st.secrets.get("SUPABASE_DB_DSN")
    except Exception:
        pass
    dsn = dsn or os.getenv("SUPABASE_DB_DSN")

    if not dsn:
        st.error("❌ SUPABASE_DB_DSN não configurado (secrets/env).")
        st.stop()

    try:
        import psycopg
    except Exception:
        st.error("❌ psycopg não instalado no ambiente do app.")
        st.stop()

    sql = """
      select
        import_id,
        row_number,
        data_do_periodo,
        periodo,
        duracao_do_periodo,
        numero_minimo_de_entregadores_regulares_na_escala,
        tag,
        id_da_pessoa_entregadora,
        pessoa_entregadora,
        praca,
        sub_praca,
        origem,
        tempo_disponivel_escalado,
        tempo_disponivel_absoluto,
        numero_de_corridas_ofertadas,
        numero_de_corridas_aceitas,
        numero_de_corridas_rejeitadas,
        numero_de_corridas_completadas,
        numero_de_corridas_canceladas_pela_pessoa_entregadora,
        numero_de_pedidos_aceitos_e_concluidos,
        soma_das_taxas_das_corridas_aceitas
      from base_2025_raw
    """

    try:
        with psycopg.connect(dsn) as conn:
            df = pd.read_sql_query(sql, conn)
    except Exception as e:
        st.error(f"❌ Falha ao ler Supabase: {e}")
        st.stop()

    # ---- pós-processamento igual ao Excel ----
    df["data_do_periodo"] = pd.to_datetime(df["data_do_periodo"], errors="coerce")
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["mes_ano"] = df["data_do_periodo"].dt.to_period("M").dt.to_timestamp()

    df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)

    df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)

    # tempo disponível absoluto -> segundos
    s = df["tempo_disponivel_absoluto"]
    td = pd.to_timedelta(s.astype(str).str.strip(), errors="coerce")
    if td.notna().any():
        df["segundos_abs_raw"] = td.dt.total_seconds().fillna(0).astype(int)
    else:
        df["segundos_abs_raw"] = s.apply(tempo_para_segundos).fillna(0).astype(int)

    df["segundos_negativos_flag"] = df["segundos_abs_raw"] < 0
    seg_raw = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
    df["segundos_abs"] = seg_raw.where(seg_raw >= 0, 0).astype(int)

    # numéricos principais
    df["tempo_disponivel_escalado"] = _to_float_ptbr(df["tempo_disponivel_escalado"])

    for c in [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
    ]:
        df[c] = _to_int_ptbr(df[c])

    df.attrs["fonte"] = "supabase"
    return df
