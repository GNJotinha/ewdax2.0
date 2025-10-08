# data_loader.py
import pandas as pd
import streamlit as st
import gdown
from pathlib import Path
from utils import normalizar, tempo_para_segundos

SHEET = "Base 2025"

@st.cache_data(show_spinner=False)  # 👈 evita ficar mostrando "Running..." toda hora
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None):# data_loader.py — Supabase-only, paginação ordenada, normalização e cache
import pandas as pd
import streamlit as st
from supabase import create_client

# =========================
# Conexão
# =========================
def _client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

# =========================
# Fetch paginado COM ordem estável
# =========================
def _fetch_all_ordered(client, table: str, chunk: int = 5000) -> list[dict]:
    """
    Busca todos os registros em páginas ordenadas, evitando duplicação/perda.
    Tenta ordenar por 'id'; se não existir, usa 'data_do_periodo'.
    """
    # decide coluna de ordenação
    order_col = "id"
    try:
        client.table(table).select("id").limit(1).execute()
    except Exception:
        order_col = "data_do_periodo"

    out, start = [], 0
    while True:
        end = start + chunk - 1
        q = (client.table(table)
                    .select("*")
                    .order(order_col, desc=False)
                    .range(start, end))
        res = q.execute()
        rows = res.data or []
        out.extend(rows)
        if len(rows) < chunk:
            break
        start = end + 1
    return out

# =========================
# Normalização de DF
# =========================
def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    # Datas base (UTC→naive) e colunas derivadas
    base_dt = pd.to_datetime(
        df.get("data_do_periodo", df.get("data")),
        errors="coerce",
        utc=True
    ).dt.tz_convert(None)

    df["data_do_periodo"] = base_dt
    df["data"] = base_dt.dt.date

    # mes/ano podem vir como texto: força numérico
    if "mes" in df.columns:
        df["mes"] = pd.to_numeric(df["mes"], errors="coerce")
    else:
        df["mes"] = base_dt.dt.month
    if "ano" in df.columns:
        df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    else:
        df["ano"] = base_dt.dt.year

    df["mes"] = df["mes"].fillna(base_dt.dt.month).astype(int)
    df["ano"] = df["ano"].fillna(base_dt.dt.year).astype(int)
    df["mes_ano"] = base_dt.dt.to_period("M").dt.to_timestamp()

    # UUID
    if "uuid" not in df.columns:
        if "id_da_pessoa_entregadora" in df.columns:
            df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
        else:
            df["uuid"] = ""

    # Segundos absolutos (se a view não trouxer pronto)
    if "segundos_abs_raw" not in df.columns:
        # se não existe na origem, define 0; cálculo detalhado já é feito na view
        df["segundos_abs_raw"] = 0
    df["segundos_abs"] = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
    df["segundos_abs"] = df["segundos_abs"].where(df["segundos_abs"] >= 0, 0).astype(int)
    df["segundos_negativos_flag"] = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0) < 0

    # Numéricas chave
    for c in [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
        "tempo_disponivel_escalado",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Dedup
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"]).reset_index(drop=True)
    else:
        df = df.drop_duplicates().reset_index(drop=True)

    return df

# =========================
# API pública — sem fallback
# =========================
@st.cache_data(show_spinner=False)
def carregar_dados(_ts: float | None = None) -> pd.DataFrame:
    """
    Sempre carrega do Supabase. Se der erro, exibe o stack e interrompe.
    Use _ts para 'quebrar' o cache quando clicar em Atualizar dados.
    """
    try:
        client = _client()
        source = st.secrets.get("SUPABASE_SOURCE", "view_movee_base")
        table = source.split(".")[-1]  # supabase-py usa só o nome (sem schema)
        rows = _fetch_all_ordered(client, table)
        if not rows:
            st.error("❌ Supabase retornou 0 linhas.")
            st.stop()
        df = pd.DataFrame(rows)
        return _normalize_df(df)
    except Exception as e:
        # Mostra o erro real para debug (em produção você pode trocar por st.error)
        st.exception(e)
        st.stop()

    """
    Carrega a base com 3 estratégias:
      1) Local
      2) Backup (/mnt/data)
      3) Google Drive

    Se prefer_drive=True, ignora (1) e (2) e baixa do Drive novamente.
    _ts: só serve para 'quebrar' o cache quando pedirmos refresh.
    """
    destino = Path("Calendarios.xlsx")

    if prefer_drive:
        _baixar_fresco_do_drive(destino)
        return _ler(destino)

    # 1) Local
    if destino.exists() and destino.stat().st_size > 0:
        return _ler(destino)

    # 2) Backup do ambiente
    backup = Path("/mnt/data/Calendarios.xlsx")
    if backup.exists() and backup.stat().st_size > 0:
        st.warning("⚠️ Usando cópia local de backup (/mnt/data/Calendarios.xlsx).")
        return _ler(backup)

    # 3) Drive (padrão)
    _baixar_fresco_do_drive(destino)
    return _ler(destino)

def _baixar_fresco_do_drive(out: Path):
    """Baixa SEMPRE do Drive, sobrescrevendo local, e valida tamanho."""
    file_id = st.secrets.get("CALENDARIO_FILE_ID", "1Dmmg1R-xmmC0tfi5-1GVS8KLqhZJUqm5")
    try:
        if out.exists():
            out.unlink(missing_ok=True)  # remove local pra não cair no passo (1)
    except Exception:
        pass

    ok = _baixar_drive(file_id, out)
    if not ok:
        st.error("❌ Falha ao baixar do Google Drive. Verifique compartilhamento e ID.")
        st.stop()

def _baixar_drive(file_id: str, out: Path) -> bool:
    try:
        gdown.download(id=file_id, output=str(out), quiet=False)
        if out.exists() and out.stat().st_size > 0:
            return True
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        gdown.download(url=url, output=str(out), quiet=False, fuzzy=True)
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        st.warning(f"Download falhou: {e}")
        return False

def _ler(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET)

    # Datas básicas
    df["data_do_periodo"] = pd.to_datetime(df["data_do_periodo"], errors="coerce")
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["mes_ano"] = df["data_do_periodo"].dt.to_period("M").dt.to_timestamp()

    # Nome normalizado
    df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)

    # ID único do entregador
    if "id_da_pessoa_entregadora" in df.columns:
        df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
    else:
        df["uuid"] = ""

    # -----------------------------------------------
    # segundos_abs_raw: versão original (pode ser negativa)
    # segundos_abs: versão CLIPADA (negativos viram 0) p/ SH/UTR/online
    # -----------------------------------------------
    if "tempo_disponivel_absoluto" in df.columns:
        s = df["tempo_disponivel_absoluto"]
        try:
            if pd.api.types.is_timedelta64_dtype(s):
                df["segundos_abs_raw"] = s.dt.total_seconds().fillna(0).astype(int)
            elif pd.api.types.is_numeric_dtype(s):
                df["segundos_abs_raw"] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)
            else:
                # tenta parser timedelta; se não der, usa nosso parser robusto
                td = pd.to_timedelta(s.astype(str).str.strip(), errors="coerce")
                if td.notna().any():
                    df["segundos_abs_raw"] = td.dt.total_seconds().fillna(0).astype(int)
                else:
                    df["segundos_abs_raw"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
        except Exception:
            df["segundos_abs_raw"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
    else:
        df["segundos_abs_raw"] = 0

    # Flag só pra auditoria (útil pra debug/QA)
    df["segundos_negativos_flag"] = df["segundos_abs_raw"] < 0

    # CLIP: qualquer negativo vira 0 para não contaminar supply_hours/online
    # (inclui o caso específico de -10:00 = -600s)
    seg_raw = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
    df["segundos_abs"] = seg_raw.where(seg_raw >= 0, 0).astype(int)

    # -----------------------------------------------
    # Normalização numérica de colunas-chave
    # -----------------------------------------------
    for c in [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
        "tempo_disponivel_escalado",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    return df
