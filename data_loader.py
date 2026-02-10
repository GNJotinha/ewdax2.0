# data_loader.py
import os
import re
import pandas as pd
import streamlit as st
import gdown
from pathlib import Path
from utils import normalizar, tempo_para_segundos

SHEET = "Base 2025"

# -----------------------------
# Helpers: parse número PT-BR
# -----------------------------
_RE_MILHAR_DEC = re.compile(r"^\d{1,3}(\.\d{3})+,\d+$")   # 4.118,10
_RE_SO_DEC     = re.compile(r"^\d+,\d+$")                # 12,5
_RE_SO_MILHAR  = re.compile(r"^\d{1,3}(\.\d{3})+$")      # 1.234

def _to_float_ptbr(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()

    # vazio -> NA
    s = s.replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA})

    # 4.118,10 -> 4118.10
    m = s.str.match(_RE_MILHAR_DEC)
    if m.any():
        s = s.where(~m, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))

    # 12,5 -> 12.5
    m = s.str.match(_RE_SO_DEC)
    if m.any():
        s = s.where(~m, s.str.replace(",", ".", regex=False))

    # 1.234 -> 1234
    m = s.str.match(_RE_SO_MILHAR)
    if m.any():
        s = s.where(~m, s.str.replace(".", "", regex=False))

    return pd.to_numeric(s, errors="coerce").fillna(0)

def _to_int_ptbr(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip().replace({"": pd.NA})
    # remove separador de milhar se vier
    s = s.str.replace(".", "", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0).astype(int)


@st.cache_data(show_spinner=False)
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None):
    """
    Carrega a base com estratégias:
      0) Supabase (se SUPABASE_DB_DSN existir)
      1) Local Excel
      2) Backup (/mnt/data)
      3) Google Drive

    prefer_drive=True força Excel/Drive (ignora Supabase).
    _ts quebra cache quando pedimos refresh.
    """
    if not prefer_drive:
        df = _tentar_supabase()
        if df is not None:
            return df

    destino = Path("Calendarios.xlsx")

    if prefer_drive:
        _baixar_fresco_do_drive(destino)
        return _posprocessar(_ler_excel(destino))

    if destino.exists() and destino.stat().st_size > 0:
        return _posprocessar(_ler_excel(destino))

    backup = Path("/mnt/data/Calendarios.xlsx")
    if backup.exists() and backup.stat().st_size > 0:
        st.warning("⚠️ Usando cópia local de backup (/mnt/data/Calendarios.xlsx).")
        return _posprocessar(_ler_excel(backup))

    _baixar_fresco_do_drive(destino)
    return _posprocessar(_ler_excel(destino))


def _tentar_supabase() -> pd.DataFrame | None:
    dsn = None
    try:
        dsn = st.secrets.get("SUPABASE_DB_DSN")
    except Exception:
        pass
    dsn = dsn or os.getenv("SUPABASE_DB_DSN")

    if not dsn:
        return None

    try:
        import psycopg
    except Exception:
        st.warning("⚠️ SUPABASE_DB_DSN definido, mas psycopg não está instalado.")
        return None

    # lê RAW (fiel) e tipa no Python, igual fazia no Excel
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
        return _posprocessar(df, fonte="supabase")
    except Exception as e:
        st.warning(f"⚠️ Falha ao ler Supabase, caindo pro Excel. Erro: {e}")
        return None


def _ler_excel(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=SHEET)


def _baixar_fresco_do_drive(out: Path):
    file_id = st.secrets.get("CALENDARIO_FILE_ID", "1Dmmg1R-xmmC0tfi5-1GVS8KLqhZJUqm5")
    try:
        if out.exists():
            out.unlink(missing_ok=True)
    except Exception:
        pass

    ok = _baixar_drive(file_id, out)
    if not ok:
        st.error("❌ Falha ao baixar do Google Drive. Verifique compartilhamento e ID.")
        st.stop()


def _baixar_drive(file_id: str, out: Path) -> bool:
    try:
        gdown.download(id=file_id, output=str(out), quiet=False)
        if out.exists() and out.stat().st_size > 0:
            return True
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        gdown.download(url=url, output=str(out), quiet=False, fuzzy=True)
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        st.warning(f"Download falhou: {e}")
        return False


def _posprocessar(df: pd.DataFrame, fonte: str = "excel") -> pd.DataFrame:
    # Datas
    df["data_do_periodo"] = pd.to_datetime(df["data_do_periodo"], errors="coerce")
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["mes_ano"] = df["data_do_periodo"].dt.to_period("M").dt.to_timestamp()

    # Nome normalizado
    df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)

    # uuid
    if "id_da_pessoa_entregadora" in df.columns:
        df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
    else:
        df["uuid"] = ""

    # segundos_abs_raw / segundos_abs
    if "tempo_disponivel_absoluto" in df.columns:
        s = df["tempo_disponivel_absoluto"]
        try:
            if pd.api.types.is_timedelta64_dtype(s):
                df["segundos_abs_raw"] = s.dt.total_seconds().fillna(0).astype(int)
            elif pd.api.types.is_numeric_dtype(s):
                df["segundos_abs_raw"] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)
            else:
                td = pd.to_timedelta(s.astype(str).str.strip(), errors="coerce")
                if td.notna().any():
                    df["segundos_abs_raw"] = td.dt.total_seconds().fillna(0).astype(int)
                else:
                    df["segundos_abs_raw"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
        except Exception:
            df["segundos_abs_raw"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
    else:
        df["segundos_abs_raw"] = 0

    df["segundos_negativos_flag"] = df["segundos_abs_raw"] < 0
    seg_raw = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
    df["segundos_abs"] = seg_raw.where(seg_raw >= 0, 0).astype(int)

    # Normalização numérica (agora com suporte BR se vier string)
    if "tempo_disponivel_escalado" in df.columns:
        if pd.api.types.is_numeric_dtype(df["tempo_disponivel_escalado"]):
            df["tempo_disponivel_escalado"] = pd.to_numeric(df["tempo_disponivel_escalado"], errors="coerce").fillna(0)
        else:
            df["tempo_disponivel_escalado"] = _to_float_ptbr(df["tempo_disponivel_escalado"])

    for c in [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
    ]:
        if c in df.columns:
            if pd.api.types.is_numeric_dtype(df[c]):
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
            else:
                df[c] = _to_int_ptbr(df[c])

    df.attrs["fonte"] = fonte
    return df
