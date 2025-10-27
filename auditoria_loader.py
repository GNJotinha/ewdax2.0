# auditoria_loader.py — cache local + parquet + colunas reduzidas
import time
from pathlib import Path
import pandas as pd
import streamlit as st
import requests
import gdown

# IDs fixos (ou leia do secrets depois)
FATURAMENTO_FILE_ID = "1aG0OORxTd2XGyAS8ukZs137nHWhfHMU4"
OPERACIONAL_FILE_ID = "1f7x-bn-B_6XeT3HXWS7YtUxHkgT3GVoQ"

CACHE_DIR = Path("./.cache_drive")
CACHE_DIR.mkdir(exist_ok=True)
MAX_AGE_MINUTES = 60

def _is_fresh(p: Path, max_age_minutes: int = MAX_AGE_MINUTES) -> bool:
    if not p.exists(): return False
    age_min = (time.time() - p.stat().st_mtime)/60.0
    return age_min <= max_age_minutes and p.stat().st_size > 0

def _export_xlsx(file_id: str, out: Path) -> bool:
    url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
    try:
        r = requests.get(url, timeout=60)
        if r.status_code == 200 and r.content and len(r.content) > 1024:
            out.write_bytes(r.content)
            return True
        return False
    except Exception:
        return False

def _download_gdown(file_id: str, out: Path) -> bool:
    try:
        gdown.download(id=file_id, output=str(out), quiet=True)
        return out.exists() and out.stat().st_size > 0
    except Exception:
        return False

def _get_file(file_id: str, cache_name: str, force: bool=False) -> Path:
    xlsx = CACHE_DIR / cache_name
    if not force and _is_fresh(xlsx): return xlsx
    ok = _export_xlsx(file_id, xlsx) or _download_gdown(file_id, xlsx)
    if not ok:
        st.error(f"Falha ao baixar do Drive: {file_id}")
        st.stop()
    return xlsx

# --------- Filtros de colunas para reduzir RAM ----------
OP_USECOLS = [
    "data_do_periodo","data",
    "periodo",
    "id_da_pessoa_entregadora","pessoa_entregadora",
    "soma_das_taxas_das_corridas_aceitas",
]
FAT_USECOLS = [
    "data_do_periodo_de_referencia","data_do_periodo","data_do_lancamento_financeiro","data_do_repasse",
    "periodo",
    "id_da_pessoa_entregadora","pessoa_entregadora","recebedor",
    "valor","descricao",
]

def _read_excel_memory_safe(path: Path, sheet: str, usecols: list[str]) -> pd.DataFrame:
    # lê só as colunas necessárias; dtype leve pra strings
    return pd.read_excel(
        path, sheet_name=sheet, usecols=lambda c: c in usecols, dtype="object", engine="openpyxl"
    )

def _parquet_of(xlsx_path: Path) -> Path:
    return xlsx_path.with_suffix(".parquet")

@st.cache_data(show_spinner=False)
def load_operacional_from_drive(force: bool=False) -> pd.DataFrame:
    xlsx = _get_file(OPERACIONAL_FILE_ID, "OPERACIONAL.xlsx", force=force)
    pq = _parquet_of(xlsx)
    if not force and _is_fresh(pq):
        return pd.read_parquet(pq)

    df = _read_excel_memory_safe(xlsx, "Dados", OP_USECOLS)
    # conversões leves
    if "data_do_periodo" in df.columns:
        df["data"] = pd.to_datetime(df["data_do_periodo"], errors="coerce").dt.date
    elif "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    else:
        df["data"] = pd.NaT

    df["periodo"] = df.get("periodo")
    df["id_da_pessoa_entregadora"] = df.get("id_da_pessoa_entregadora")
    df["pessoa_entregadora"] = df.get("pessoa_entregadora")
    df["soma_das_taxas_das_corridas_aceitas"] = pd.to_numeric(
        df.get("soma_das_taxas_das_corridas_aceitas"), errors="coerce"
    ).fillna(0)

    df = df[["data","periodo","id_da_pessoa_entregadora","pessoa_entregadora","soma_das_taxas_das_corridas_aceitas"]]

    df.to_parquet(pq, index=False)
    return df

@st.cache_data(show_spinner=False)
def load_faturamento_from_drive(force: bool=False) -> pd.DataFrame:
    xlsx = _get_file(FATURAMENTO_FILE_ID, "FATURAMENTO.xlsx", force=force)
    pq = _parquet_of(xlsx)
    if not force and _is_fresh(pq):
        return pd.read_parquet(pq)

    df = _read_excel_memory_safe(xlsx, "Base", FAT_USECOLS)

    # escolher data
    date_col = None
    for c in ["data_do_periodo_de_referencia","data_do_periodo","data_do_lancamento_financeiro","data_do_repasse"]:
        if c in df.columns: date_col = c; break
    if not date_col:
        st.error("Nenhuma coluna de data encontrada na aba Base do FATURAMENTO.")
        st.stop()

    df["data"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    df["periodo"] = df.get("periodo")
    df["id_da_pessoa_entregadora"] = df.get("id_da_pessoa_entregadora")
    df["pessoa_entregadora"] = df.get("pessoa_entregadora", "")
    df["recebedor"] = df.get("recebedor", "")
    nome = df["recebedor"].where(df["recebedor"].notna() & (df["recebedor"]!=""), df["pessoa_entregadora"])
    df["ent_nome"] = nome.astype(str)

    df["valor"] = pd.to_numeric(df.get("valor"), errors="coerce").fillna(0.0)
    df["descricao"] = df.get("descricao").astype(str)

    df = df[["data","periodo","id_da_pessoa_entregadora","ent_nome","valor","descricao"]]
    df.to_parquet(pq, index=False)
    return df
