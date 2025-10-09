# data_loader.py
import pandas as pd
import streamlit as st
import gdown
from pathlib import Path
from utils import normalizar, tempo_para_segundos

# ========= SUA PARTE (Drive/Excel) =========
SHEET = "Base 2025"

@st.cache_data(show_spinner=False)  # 👈 evita ficar mostrando "Running..." toda hora
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None):
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

# ========= NOVO: Supabase (v3) =========
# Lê agregados diretos da materialized view v3.mv_resumo_mes
try:
    from supabase import create_client
except Exception:
    create_client = None
    st.warning("⚠️ Para usar Supabase, adicione 'supabase>=2.6.0' ao requirements.txt e configure st.secrets['supabase'].")

def _sb_client():
    if create_client is None:
        raise RuntimeError("Biblioteca 'supabase' não disponível.")
    SB_URL = st.secrets["supabase"]["url"]
    SB_KEY = st.secrets["supabase"]["service_key"]  # service_role no backend
    # cache do client
    if "_sb" not in st.session_state:
        st.session_state["_sb"] = create_client(SB_URL, SB_KEY)
    return st.session_state["_sb"]

@st.cache_data(ttl=60, show_spinner=False)
def get_resumo_mes(ano: int, mes: int, praca: str | None = None, subpraca: str | None = None) -> pd.DataFrame:
    """
    Lê a MV v3.mv_resumo_mes para o mês/filtros informados.
    Retorna: mes, praca, sub_praca, periodo, ofertadas, aceitas, rejeitadas, concluidas, utr, valor_total_rs
    """
    sb = _sb_client()
    mes_iso = pd.Timestamp(ano, mes, 1).date().isoformat()
    q = (sb.table("v3.mv_resumo_mes")
            .select("mes,praca,sub_praca,periodo,ofertadas,aceitas,rejeitadas,concluidas,utr,valor_total_rs")
            .eq("mes", mes_iso)
            .limit(20000))
    if praca:
        q = q.eq("praca", praca)
    if subpraca:
        q = q.eq("sub_praca", subpraca)
    data = q.execute().data or []
    df = pd.DataFrame(data)
    if df.empty:
        return df
    # tipagem
    df["mes"] = pd.to_datetime(df["mes"], errors="coerce").dt.date
    for c in ["ofertadas", "aceitas", "rejeitadas", "concluidas"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["utr"] = pd.to_numeric(df["utr"], errors="coerce")
    df["valor_total_rs"] = pd.to_numeric(df["valor_total_rs"], errors="coerce").fillna(0.0)
    return df

@st.cache_data(ttl=60, show_spinner=False)
def get_last_dia():
    """Último dia com dados (v3.vw_resumo_diario) — útil pra mostrar status na Home."""
    sb = _sb_client()
    try:
        res = (sb.table("v3.vw_resumo_diario")
                 .select("dia")
                 .order("dia", desc=True)
                 .limit(1)
                 .execute()).data
        if res:
            return pd.to_datetime(res[0]["dia"]).date()
    except Exception:
        return None
    return None
