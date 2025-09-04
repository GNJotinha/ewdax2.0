# data_loader.py
from __future__ import annotations

import pandas as pd
import streamlit as st
import gdown
from pathlib import Path
from utils import normalizar, tempo_para_segundos

SHEET = "Base 2025"  # carrega exatamente essa aba, como antes

@st.cache_data
def carregar_dados() -> pd.DataFrame:
    destino = Path("Calendarios.xlsx")

    # 1) Local primeiro
    if destino.exists() and destino.stat().st_size > 0:
        return _ler(destino)

    # 2) Backup do ambiente (se você subir junto ao app)
    backup = Path("/mnt/data/Calendarios.xlsx")
    if backup.exists() and backup.stat().st_size > 0:
        return _ler(backup)

    # 3) Google Drive (usando CALENDARIO_FILE_ID em st.secrets)
    file_id = st.secrets.get("CALENDARIO_FILE_ID", "").strip()
    if not file_id:
        # sem ID: falha “seca” (sem aviso na tela)
        raise RuntimeError("CALENDARIO_FILE_ID não definido em st.secrets.")
    if not _baixar_drive(file_id, destino):
        raise RuntimeError("Falha ao baixar Calendarios.xlsx do Google Drive.")

    return _ler(destino)


def _baixar_drive(file_id: str, out: Path) -> bool:
    try:
        # Preferir por ID direto
        gdown.download(id=file_id, output=str(out), quiet=True)
        if out.exists() and out.stat().st_size > 0:
            return True
        # Fallback por URL export=download
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        gdown.download(url=url, output=str(out), quiet=True, fuzzy=True)
        return out.exists() and out.stat().st_size > 0
    except Exception:
        return False


def _ler(path: Path) -> pd.DataFrame:
    # Lê exatamente a aba definida em SHEET (sem avisos)
    df = pd.read_excel(path, sheet_name=SHEET)

    # ------ Datas e derivados ------
    base_dt = pd.to_datetime(df["data_do_periodo"], errors="coerce")
    df["data_do_periodo"] = base_dt
    df["data"] = base_dt.dt.date
    df["mes"] = base_dt.dt.month
    df["ano"] = base_dt.dt.year
    df["mes_ano"] = base_dt.dt.to_period("M").dt.to_timestamp()

    # ------ Normalização de nomes ------
    if "pessoa_entregadora" in df.columns:
        df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)
    else:
        df["pessoa_entregadora"] = None
        df["pessoa_entregadora_normalizado"] = ""

    # ------ Numéricos com coerção ------
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
        else:
            df[c] = 0

    # ------ segundos_abs robusto (silencioso) ------
    df["segundos_abs"] = 0
    col = "tempo_disponivel_absoluto"
    if col in df.columns:
        s = df[col]
        try:
            if pd.api.types.is_timedelta64_dtype(s):
                df["segundos_abs"] = s.dt.total_seconds().fillna(0).astype(int)
            elif pd.api.types.is_numeric_dtype(s):
                df["segundos_abs"] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)
            else:
                # normaliza string/tupla/lista, aceita vírgula
                s_norm = (
                    s.apply(lambda x: ":".join(map(str, x)) if isinstance(x, (list, tuple)) else x)
                     .astype(str)
                     .str.replace(",", ".", regex=False)
                     .str.strip()
                )
                td = pd.to_timedelta(s_norm, errors="coerce")
                if td.notna().any():
                    df["segundos_abs"] = td.dt.total_seconds().fillna(0).astype(int)
                else:
                    df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
        except Exception:
            df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)

    return df
