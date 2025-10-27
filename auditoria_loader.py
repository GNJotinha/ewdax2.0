# auditoria_loader.py
import pandas as pd
import streamlit as st
import gdown
from pathlib import Path

# IDs fixos do Google Drive (coloca os seus)
FATURAMENTO_FILE_ID = "1aG0OORxTd2XGyAS8ukZs137nHWhfHMU4"
OPERACIONAL_FILE_ID = "1f7x-bn-B_6XeT3HXWS7YtUxHkgT3GVoQ"

def _download(file_id: str, out: Path):
    """Baixa o arquivo do Google Drive usando gdown."""
    try:
        gdown.download(id=file_id, output=str(out), quiet=False)
    except Exception as e:
        st.error(f"Erro ao baixar arquivo do Drive: {e}")
        st.stop()

@st.cache_data(show_spinner=False)
def load_operacional_from_drive(_ts=None) -> pd.DataFrame:
    out = Path("OPERACIONAL.xlsx")
    _download(OPERACIONAL_FILE_ID, out)
    try:
        return pd.read_excel(out, sheet_name="Dados")
    except Exception as e:
        st.error(f"Erro lendo aba 'Dados' de OPERACIONAL.xlsx: {e}")
        st.stop()

@st.cache_data(show_spinner=False)
def load_faturamento_from_drive(_ts=None) -> pd.DataFrame:
    out = Path("FATURAMENTO.xlsx")
    _download(FATURAMENTO_FILE_ID, out)
    try:
        return pd.read_excel(out, sheet_name="Base")
    except Exception as e:
        st.error(f"Erro lendo aba 'Base' de FATURAMENTO.xlsx: {e}")
        st.stop()
