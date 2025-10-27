# auditoria_loader.py  — versão rápida com cache local + export direto
import time
from pathlib import Path
import pandas as pd
import streamlit as st
import requests
import gdown

# IDs fixos (troque pelos seus se quiser)
FATURAMENTO_FILE_ID = "1aG0OORxTd2XGyAS8ukZs137nHWhfHMU4"
OPERACIONAL_FILE_ID = "1f7x-bn-B_6XeT3HXWS7YtUxHkgT3GVoQ"

# Config de cache local
CACHE_DIR = Path("./.cache_drive")
CACHE_DIR.mkdir(exist_ok=True)
MAX_AGE_MINUTES = 60  # tempo máximo de “validade” do arquivo local

def _is_fresh(p: Path, max_age_minutes: int = MAX_AGE_MINUTES) -> bool:
    if not p.exists(): 
        return False
    age_min = (time.time() - p.stat().st_mtime) / 60.0
    return age_min <= max_age_minutes and p.stat().st_size > 0

def _export_xlsx(file_id: str, out: Path) -> bool:
    """Tenta baixar via export do Google Sheets (geralmente mais rápido)."""
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

def _get_file(file_id: str, cache_name: str, force: bool = False) -> Path:
    """Retorna caminho do arquivo local, usando cache. Baixa se necessário."""
    out = CACHE_DIR / cache_name
    if not force and _is_fresh(out):
        return out

    # tenta export direto (rápido); se falhar, usa gdown (mais lento)
    ok = _export_xlsx(file_id, out)
    if not ok:
        ok = _download_gdown(file_id, out)

    if not ok:
        st.error(f"Falha ao baixar do Drive (id={file_id}).")
        st.stop()
    return out

@st.cache_data(show_spinner=False)
def load_operacional_from_drive(force: bool = False) -> pd.DataFrame:
    p = _get_file(OPERACIONAL_FILE_ID, "OPERACIONAL.xlsx", force=force)
    try:
        return pd.read_excel(p, sheet_name="Dados")
    except Exception as e:
        st.error(f"Erro lendo OPERACIONAL.xlsx (aba 'Dados'). Detalhe: {e}")
        st.stop()

@st.cache_data(show_spinner=False)
def load_faturamento_from_drive(force: bool = False) -> pd.DataFrame:
    p = _get_file(FATURAMENTO_FILE_ID, "FATURAMENTO.xlsx", force=force)
    try:
        return pd.read_excel(p, sheet_name="Base")
    except Exception as e:
        st.error(f"Erro lendo FATURAMENTO.xlsx (aba 'Base'). Detalhe: {e}")
        st.stop()
