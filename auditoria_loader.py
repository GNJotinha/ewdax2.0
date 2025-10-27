# auditoria_loader.py
import streamlit as st
import pandas as pd
import gdown
from pathlib import Path

@st.cache_data(show_spinner=False)
def load_operacional_from_drive(_ts=None) -> pd.DataFrame:
    file_id = st.secrets.get("OPERACIONAL_FILE_ID")
    if not file_id:
        st.error("OPERACIONAL_FILE_ID não configurado em st.secrets.")
        st.stop()
    out = Path("OPERACIONAL.xlsx")
    _download(file_id, out)
    return pd.read_excel(out, sheet_name="Dados")

@st.cache_data(show_spinner=False)
def load_faturamento_from_drive(_ts=None) -> pd.DataFrame:
    file_id = st.secrets.get("FATURAMENTO_FILE_ID")
    if not file_id:
        st.error("FATURAMENTO_FILE_ID não configurado em st.secrets.")
        st.stop()
    out = Path("FATURAMENTO.xlsx")
    _download(file_id, out)
    return pd.read_excel(out, sheet_name="Base")

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
