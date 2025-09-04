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

    # 🔹 NOVO: segundos_abs robusto (aguenta números, HH:MM:SS, vírgulas, lixo…)
    df["segundos_abs"] = 0
    col = "tempo_disponivel_absoluto"
    if col in df.columns:
        s = df[col]

        try:
            # 1) Já é timedelta?
            if pd.api.types.is_timedelta64_dtype(s):
                df["segundos_abs"] = s.dt.total_seconds().fillna(0).astype(int)

            # 2) Já é numérico? (assumimos segundos)
            elif pd.api.types.is_numeric_dtype(s):
                df["segundos_abs"] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)

            else:
                # 3) Normaliza casos bizarros: listas/tuplas → "h:m:s", vírgula → ponto
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
                    # 4) Último recurso: parser manual
                    df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)

            # (Opcional) Mostra exemplos inválidos, se tiver
            invalid_mask = df["segundos_abs"].isna() | (df["segundos_abs"] < 0)
            if invalid_mask.any():
                exemplos = s[invalid_mask].dropna().astype(str).unique().tolist()[:3]
                import streamlit as st
                st.warning(f"⚠️ Valores de tempo inválidos detectados em '{col}'. Exemplos: {exemplos}")

        except Exception:
            # Se der ruim, cai no parser manual, sem travar o app
            df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
