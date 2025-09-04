# data_loader.py
import pandas as pd
import streamlit as st
import gdown
from pathlib import Path
from utils import normalizar, tempo_para_segundos

SHEET = "Base 2025"

# 👉 COLE AQUI: pode ser o ID (ex: '1AbC...XYZ') ou o link completo do Drive (ex: 'https://drive.google.com/file/d/ID/view?...')
FILE_ID_OR_URL = "COLE_ID_OU_LINK_AQUI"

@st.cache_data
def carregar_dados(force: bool = False):
    """
    Carrega a planilha local ou baixa do Drive.
    Se force=True, apaga o arquivo local e rebaixa SEMPRE antes de ler.
    """
    destino = Path("Calendarios.xlsx")
    backup  = Path("/mnt/data/Calendarios.xlsx")

    # Força re-download do Drive
    if force:
        try:
            destino.unlink(missing_ok=True)
        except Exception:
            pass
        _baixar_drive_forcado(destino)
        return _ler(destino)

    # Fluxo normal
    if destino.exists() and destino.stat().st_size > 0:
        return _ler(destino)

    if backup.exists() and backup.stat().st_size > 0:
        return _ler(backup)

    # Primeira carga: baixa do Drive
    _baixar_drive_forcado(destino)
    return _ler(destino)


def _baixar_drive_forcado(out: Path) -> None:
    src = (FILE_ID_OR_URL or "").strip()
    if not src or src == "COLE_ID_OU_LINK_AQUI":
        raise RuntimeError("Defina FILE_ID_OR_URL em data_loader.py com o ID ou o LINK do arquivo no Drive.")
    try:
        out.unlink(missing_ok=True)
    except Exception:
        pass
    ok = _baixar_drive(src, out)
    if not ok or (not out.exists() or out.stat().st_size == 0):
        raise RuntimeError("Falha ao baixar Calendarios.xlsx do Google Drive.")


def _baixar_drive(src: str, out: Path) -> bool:
    try:
        # Se vier um LINK do Drive, baixa por URL (fuzzy ajuda com /file/d/ID/view etc.)
        if "drive.google" in src:
            gdown.download(url=src, output=str(out), quiet=True, fuzzy=True)
        else:
            # Caso contrário, assume que é um ID
            gdown.download(id=src, output=str(out), quiet=True)
            # Fallback por URL se necessário
            if not out.exists() or out.stat().st_size == 0:
                url = f"https://drive.google.com/uc?export=download&id={src}"
                gdown.download(url=url, output=str(out), quiet=True, fuzzy=True)
        return out.exists() and out.stat().st_size > 0
    except Exception:
        return False


def _ler(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET)

    # Datas
    df["data_do_periodo"] = pd.to_datetime(df["data_do_periodo"], errors="coerce")
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["mes_ano"] = df["data_do_periodo"].dt.to_period("M").dt.to_timestamp()

    # Normalização de nomes
    if "pessoa_entregadora" in df.columns:
        df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)
    else:
        df["pessoa_entregadora_normalizado"] = ""

    # Colunas numéricas
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

    # Segundos absolutos — robusto
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
                s_norm = (
                    s.apply(lambda x: ":".join(map(str, x)) if isinstance(x, (list, tuple)) else x)
                     .astype(str).str.replace(",", ".", regex=False).str.strip()
                )
                td = pd.to_timedelta(s_norm, errors="coerce")
                if td.notna().any():
                    df["segundos_abs"] = td.dt.total_seconds().fillna(0).astype(int)
                else:
                    df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
        except Exception:
            df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)

    return df
