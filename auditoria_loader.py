# auditoria_loader.py
import os
import re
from pathlib import Path
import pandas as pd
import streamlit as st
import gdown

SHEET_RE = re.compile(r"/d/([a-zA-Z0-9_-]{20,})/")  # captura o ID de uma URL do Drive

def _get_file_id(key: str) -> str:
    """
    Lê do st.secrets[key] OU os.environ[key].
    Aceita ID direto ou URL do Google Drive; se for URL, extrai o ID.
    """
    raw = st.secrets.get(key) or os.environ.get(key)
    if not raw:
        st.error(f"{key} não configurado em st.secrets nem em variável de ambiente.")
        st.stop()

    raw = str(raw).strip()
    # Se for URL, tenta extrair ID
    if "http" in raw or "/d/" in raw:
        m = SHEET_RE.search(raw)
        if not m:
            st.error(f"{key} contém uma URL, mas não consegui extrair o ID: {raw}")
            st.stop()
        return m.group(1)
    # Se parece um ID (comprimento razoável), retorna
    if len(raw) >= 20:
        return raw

    st.error(f"{key} parece inválido: '{raw}'")
    st.stop()

def _download(file_id: str, out: Path):
    # tenta por id
    gdown.download(id=file_id, output=str(out), quiet=True)
    if not (out.exists() and out.stat().st_size > 0):
        # tenta por url
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        gdown.download(url=url, output=str(out), quiet=False, fuzzy=True)
    if not (out.exists() and out.stat().st_size > 0):
        st.error(f"Falha ao baixar do Drive: {file_id}")
        st.stop()

@st.cache_data(show_spinner=False)
def load_operacional_from_drive(_ts=None) -> pd.DataFrame:
    file_id = _get_file_id("OPERACIONAL_FILE_ID")
    out = Path("OPERACIONAL.xlsx")
    _download(file_id, out)
    try:
        return pd.read_excel(out, sheet_name="Dados")
    except Exception as e:
        st.error(f"Erro lendo OPERACIONAL.xlsx (aba 'Dados'). Verifique o nome da aba. Detalhe: {e}")
        st.stop()

@st.cache_data(show_spinner=False)
def load_faturamento_from_drive(_ts=None) -> pd.DataFrame:
    file_id = _get_file_id("FATURAMENTO_FILE_ID")
    out = Path("FATURAMENTO.xlsx")
    _download(file_id, out)
    try:
        return pd.read_excel(out, sheet_name="Base")
    except Exception as e:
        st.error(f"Erro lendo FATURAMENTO.xlsx (aba 'Base'). Verifique o nome da aba. Detalhe: {e}")
        st.stop()
