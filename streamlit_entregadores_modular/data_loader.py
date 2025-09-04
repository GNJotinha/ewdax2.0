# data_loader.py
from __future__ import annotations

import pandas as pd
import streamlit as st
import gdown
from pathlib import Path
from typing import Optional
from utils import normalizar, tempo_para_segundos

# Aba padrão; pode ser sobrescrita via st.secrets["CALENDARIO_SHEET"]
SHEET_DEFAULT = "Base 2025"


@st.cache_data
def carregar_dados() -> pd.DataFrame:
    """
    Carrega a base a partir de:
      1) arquivo local "Calendarios.xlsx" (se existir),
      2) backup em /mnt/data/Calendarios.xlsx (se existir),
      3) download do Google Drive usando CALENDARIO_FILE_ID (st.secrets).
    Retorna DataFrame já com colunas derivadas e tipos tratados.
    """
    destino = Path("Calendarios.xlsx")

    # 1) Local primeiro
    if destino.exists() and destino.stat().st_size > 0:
        _debug_excel_info(destino)
        return _ler(destino)

    # 2) Backup do ambiente
    backup = Path("/mnt/data/Calendarios.xlsx")
    if backup.exists() and backup.stat().st_size > 0:
        st.warning("⚠️ Usando cópia local de backup (/mnt/data/Calendarios.xlsx).")
        _debug_excel_info(backup)
        return _ler(backup)

    # 3) Drive
    file_id = st.secrets.get("CALENDARIO_FILE_ID", "").strip()
    if not file_id:
        st.error("❌ CALENDARIO_FILE_ID não definido em st.secrets.")
        st.stop()

    if not _baixar_drive(file_id, destino):
        st.error("❌ Falha ao baixar do Google Drive. Verifique o ID e o compartilhamento (link de leitor).")
        st.stop()

    _debug_excel_info(destino)
    return _ler(destino)


def _baixar_drive(file_id: str, out: Path) -> bool:
    """Baixa um arquivo do Google Drive, tentando por ID direto e fallback por URL."""
    try:
        # Preferir por ID
        gdown.download(id=file_id, output=str(out), quiet=False)
        if out.exists() and out.stat().st_size > 0:
            return True

        # Fallback com URL (export=download) e fuzzy
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        gdown.download(url=url, output=str(out), quiet=False, fuzzy=True)
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        st.warning(f"Download falhou: {e}")
        return False


def _escolher_aba(xls: pd.ExcelFile) -> str:
    """Escolhe a aba: tenta usar a de st.secrets (ou default) e, se não existir, usa a primeira."""
    preferida = st.secrets.get("CALENDARIO_SHEET", SHEET_DEFAULT)
    if preferida in xls.sheet_names:
        return preferida

    st.warning(
        f"⚠️ Aba preferida '{preferida}' não encontrada. "
        f"Usando a primeira disponível: '{xls.sheet_names[0]}'.\n"
        f"Aba(s) existentes: {', '.join(xls.sheet_names)}"
    )
    return xls.sheet_names[0]


def _ler(path: Path) -> pd.DataFrame:
    """Lê a planilha e aplica todos os tratamentos/derivações necessários."""
    try:
        xls = pd.ExcelFile(path)
    except Exception as e:
        st.error(f"❌ Não consegui abrir o Excel '{path}': {e}")
        st.stop()

    sheet = _escolher_aba(xls)

    # Lê a aba escolhida
    df = pd.read_excel(xls, sheet_name=sheet)

    # ========================
    # Datas (robusto)
    # ========================
    # Tenta 'data_do_periodo'; se não houver, tenta 'data'.
    base_dt = None
    if "data_do_periodo" in df.columns:
        base_dt = pd.to_datetime(df["data_do_periodo"], errors="coerce")
    elif "data" in df.columns:
        base_dt = pd.to_datetime(df["data"], errors="coerce")
        st.info("🛈 Coluna 'data_do_periodo' não encontrada; usando 'data' para montar derivadas.")
        df["data_do_periodo"] = base_dt  # padroniza
    else:
        st.error("❌ Não encontrei coluna de data ('data_do_periodo' ou 'data').")
        st.stop()

    df["data_do_periodo"] = base_dt
    df["data"] = base_dt.dt.date
    df["mes"] = base_dt.dt.month
    df["ano"] = base_dt.dt.year
    df["mes_ano"] = base_dt.dt.to_period("M").dt.to_timestamp()

    # ========================
    # Normalização de nomes
    # ========================
    if "pessoa_entregadora" in df.columns:
        df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)
    else:
        st.warning("⚠️ Coluna 'pessoa_entregadora' não encontrada. Algumas telas podem ficar limitadas.")
        df["pessoa_entregadora"] = None
        df["pessoa_entregadora_normalizado"] = ""

    # ========================
    # Numéricos com coerção
    # ========================
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
            # cria a coluna faltante pra não quebrar telas que somam/formatam
            df[c] = 0

    # ========================
    # Segundos absolutos (MURO)
    # ========================
    df["segundos_abs"] = 0
    col = "tempo_disponivel_absoluto"
    if col in df.columns:
        s = df[col]
        try:
            # 1) Já é timedelta?
            if pd.api.types.is_timedelta64_dtype(s):
                df["segundos_abs"] = s.dt.total_seconds().fillna(0).astype(int)

            # 2) Numérico? (assumimos segundos)
            elif pd.api.types.is_numeric_dtype(s):
                df["segundos_abs"] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)

            else:
                # 3) Normaliza: listas/tuplas -> "h:m:s", troca vírgula por ponto
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
                    # 4) Último recurso: parser manual (utils.tempo_para_segundos)
                    df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)

            # Aviso (não bloqueante) se tiver valores claramente inválidos
            invalid_mask = df["segundos_abs"].isna() | (df["segundos_abs"] < 0)
            if invalid_mask.any():
                exemplos = s[invalid_mask].dropna().astype(str).unique().tolist()[:3]
                st.warning(f"⚠️ Valores de tempo inválidos detectados em '{col}'. Exemplos: {exemplos}")

        except Exception:
            # Se der ruim, cai no parser manual, sem travar o app
            df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
    else:
        st.info("🛈 Coluna 'tempo_disponivel_absoluto' não encontrada; 'segundos_abs' ficará em 0 para todos.")

    return df


def _debug_excel_info(path: Path) -> None:
    """
    Mostra no app as abas do Excel e as primeiras colunas da aba escolhida.
    Útil pra diagnosticar divergência de nomes.
    """
    try:
        xls = pd.ExcelFile(path)
        st.warning(f"🧪 Debug Excel: {path.name} | Abas: {', '.join(xls.sheet_names)}")
        alvo = _escolher_aba(xls)
        df_head = pd.read_excel(xls, sheet_name=alvo, nrows=3)
        st.info(f"🧪 Aba usada: '{alvo}' | Colunas: {', '.join(map(str, df_head.columns.tolist()))}")
    except Exception as e:
        st.error(f"❌ Debug Excel falhou: {e}")
