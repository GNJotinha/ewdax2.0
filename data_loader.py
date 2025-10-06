from __future__ import annotations

# -------------------- imports --------------------
import os, math
import pandas as pd
import streamlit as st
from supabase import create_client
from utils import normalizar, tempo_para_segundos

TBL = "Desempenho"

# ==================== helpers: secrets/env ====================
def _get_secret(name: str, default: str = "") -> str:
    """Busca primeiro em st.secrets, depois em variáveis de ambiente."""
    try:
        v = st.secrets.get(name)
        if v is not None:
            return str(v).strip()
    except Exception:
        pass
    return os.environ.get(name, default).strip()

# ==================== leitura Supabase ====================
def _ler_supabase(url: str, key: str) -> pd.DataFrame:
    """
    Lê a tabela do Supabase usando EXATAMENTE a URL dos secrets
    (sem autodetect .co/.in, do jeitinho que está no Project URL).
    """
    base_url = url.strip().rstrip("/")
    st.caption(f"✅ Supabase base URL: {base_url}")

    client = create_client(base_url, key)
    frames: list[pd.DataFrame] = []
    batch = 50000

    # tentar contar; se falhar, pagina até esvaziar
    total = None
    try:
        resp = client.table(TBL).select("id", count="exact").execute()
        total = getattr(resp, "count", None)
    except Exception:
        pass

    def _paged(start: int, end: int):
        return (
            client.table(TBL)
            .select("*")
            .order("data_do_periodo", desc=False)
            .range(start, end)
            .execute()
        )

    if total is None:
        start = 0
        while True:
            end = start + batch - 1
            data = _paged(start, end)
            rows = data.data or []
            if not rows:
                break
            frames.append(pd.DataFrame.from_records(rows))
            if len(rows) < batch:
                break
            start += batch
    else:
        for i in range(math.ceil(total / batch)):
            s, e = i * batch, (i + 1) * batch - 1
            data = _paged(s, e)
            rows = data.data or []
            if rows:
                frames.append(pd.DataFrame.from_records(rows))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)

# ==================== pós-processamento ====================
def _pos_processar(df: pd.DataFrame) -> pd.DataFrame:
    # Datas e partições
    df["data_do_periodo"] = pd.to_datetime(df.get("data_do_periodo"), errors="coerce")
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["mes_ano"] = df["data_do_periodo"].dt.to_period("M").dt.to_timestamp()

    # Nome e uuid
    df["pessoa_entregadora_normalizado"] = df.get("pessoa_entregadora", "").apply(normalizar)
    if "id_da_pessoa_entregadora" in df.columns:
        df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
    else:
        df["uuid"] = ""

    # ---------- segundos_abs (COMPORTAMENTO ANTIGO) ----------
    # Nada de clipe: mantém o valor "cru", inclusive negativos (-10:00 → -600)
    if "tempo_disponivel_absoluto" in df.columns:
        s = df["tempo_disponivel_absoluto"]
        try:
            if pd.api.types.is_timedelta64_dtype(s):
                df["segundos_abs"] = s.dt.total_seconds().fillna(0).astype(int)
            elif pd.api.types.is_numeric_dtype(s):
                df["segundos_abs"] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)
            else:
                td = pd.to_timedelta(s.astype(str).str.strip(), errors="coerce")
                if td.notna().any():
                    df["segundos_abs"] = td.dt.total_seconds().fillna(0).astype(int)
                else:
                    df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
        except Exception:
            df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
    else:
        df["segundos_abs"] = 0

    # Numéricos chave
    for c in [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_rejeitadas",
        "numero_de_corridas_completadas",
        "tempo_disponivel_escalado",
        "numero_de_corridas_canceladas_pela_pessoa_entregadora",
        "numero_de_pedidos_aceitos_e_concluidos",
        "soma_das_taxas_das_corridas_aceitas",
        "numero_minimo_de_entregadores_regulares_na_escala",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    return df

# ==================== entrada pública ====================
@st.cache_data(show_spinner=False)
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None) -> pd.DataFrame:
    """
    Lê 100% do Supabase, pagina e padroniza colunas para o app.
    (Sem fallback para Excel/Drive.)
    """
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")
    if not url or not key:
        st.error("❌ SUPABASE_URL/SUPABASE_KEY
