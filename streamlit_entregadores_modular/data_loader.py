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

    # 1) Local primeiro
    if destino.exists() and destino.stat().st_size > 0:
        return _ler(destino)

    # 2) Backup silencioso
    backup = Path("/mnt/data/Calendarios.xlsx")
    if backup.exists() and backup.stat().st_size > 0:
        return _ler(backup)

    # 3) Drive
    file_id = st.secrets.get("CALENDARIO_FILE_ID", "").strip()
    if not file_id:
        raise RuntimeError("CALENDARIO_FILE_ID não definido em st.secrets.")
    if not _baixar_drive(file_id, destino):
        raise RuntimeError("Falha ao baixar Calendarios.xlsx do Google Drive.")

    return _ler(destino)

def _baixar_drive(file_id: str, out: Path) -> bool:
    try:
        gdown.download(id=file_id, output=str(out), quiet=True)
        if out.exists() and out.stat().st_size > 0:
            return True
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        gdown.download(url=url, output=str(out), quiet=True, fuzzy=True)
        return out.exists() and out.stat().st_size > 0
    except Exception:
        return False

def _ler(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET)
    df["data_do_periodo"] = pd.to_datetime(df["data_do_periodo"])
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)
    df["mes_ano"] = df["data_do_periodo"].dt.to_period("M").dt.to_timestamp()

    if "tempo_disponivel_absoluto" in df.columns:
        td = pd.to_timedelta(df["tempo_disponivel_absoluto"], errors="coerce")
        df["segundos_abs"] = td.dt.total_seconds().fillna(0).astype(int)
    else:
        df["segundos_abs"] = 0

    num_cols = [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
        "tempo_disponivel_escalado",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    return df
