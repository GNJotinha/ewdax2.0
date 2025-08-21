# data_loader.py
import pandas as pd
import streamlit as st
import gdown
from pathlib import Path
from utils import normalizar

SHEET = "Base 2025"

@st.cache_data
def carregar_dados():
    destino = Path("Calendarios.xlsx")

    # 1) Local primeiro (evita depender do Drive quando já existe)
    if destino.exists() and destino.stat().st_size > 0:
        return _ler(destino)

    # 2) Backup do ambiente (se você subir junto ao app)
    backup = Path("/mnt/data/Calendarios.xlsx")
    if backup.exists() and backup.stat().st_size > 0:
        st.warning("⚠️ Usando cópia local de backup (/mnt/data/Calendarios.xlsx).")
        return _ler(backup)

    # 3) Drive (robusto)
    file_id = st.secrets.get("CALENDARIO_FILE_ID", "1Dmmg1R-xmmC0tfi5-1GVS8KLqhZJUqm5")  # seu atual
    if not _baixar_drive(file_id, destino):
        st.error("❌ Falha ao baixar do Google Drive. Verifique ID e compartilhamento (Qualquer pessoa com o link → Leitor).")
        st.stop()

    return _ler(destino)

def _baixar_drive(file_id: str, out: Path) -> bool:
    try:
        # preferir ID (evita cair em /share)
        gdown.download(id=file_id, output=str(out), quiet=False)
        if out.exists() and out.stat().st_size > 0:
            return True

        # fallback com export=download + fuzzy
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        gdown.download(url=url, output=str(out), quiet=False, fuzzy=True)
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        st.warning(f"Download falhou: {e}")
        return False

def _ler(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET)
    df["data_do_periodo"] = pd.to_datetime(df["data_do_periodo"])
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)
    return df
