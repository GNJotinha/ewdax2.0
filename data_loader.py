from __future__ import annotations

# -------------------- imports --------------------
import os, math
import pandas as pd
import streamlit as st
from supabase import create_client
from urllib.parse import urlparse

from utils import normalizar, tempo_para_segundos

# -------------------- constantes --------------------
TBL = "Desempenho"
DEBUG_MODE = bool(st.secrets.get("DEBUG_MODE", False))

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

def _normalize_supabase_url(raw: str) -> str:
    """
    Normaliza/valida a URL do Supabase para evitar erros tipo:
    [Errno -2] Name or service not known (DNS).
    """
    raw = (raw or "").strip().strip("'").strip('"')
    if not raw:
        raise ValueError("SUPABASE_URL vazio.")

    # tolerante a falta de esquema
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = "https://" + raw

    u = urlparse(raw)
    if not u.scheme or not u.netloc:
        raise ValueError(f"SUPABASE_URL inválido: {raw!r}")

    if not (u.netloc.endswith(".supabase.co") or u.netloc.endswith(".supabase.in")):
        raise ValueError(f"Domínio inesperado para SUPABASE_URL: {u.netloc!r}")

    # retorna só scheme+host (sem path), que é o que o client espera
    return f"{u.scheme}://{u.netloc}"

# ==================== leitura Supabase ====================
def _ler_supabase(url: str, key: str) -> pd.DataFrame:
    """
    Lê a tabela do Supabase usando EXATAMENTE a URL dos secrets,
    com validação/normalização.
    """
    base_url = _normalize_supabase_url(url)
    if DEBUG_MODE:
        st.caption(f"🔌 Supabase base URL normalizada: {base_url}")

    client = create_client(base_url, key)
    frames: list[pd.DataFrame] = []
    batch = 50000

    # tentar contar; se falhar, pagina até esvaziar
    total = None
    try:
        resp = client.table(TBL).select("id", count="exact").execute()
        total = getattr(resp, "count", None)
    except Exception:
        # sem count; vamos paginar até acabar
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
    """
    Padroniza colunas esperadas pelo app.
    - Datas/partições: data, mes, ano, mes_ano
    - Nome normalizado e uuid
    - segundos_abs preservando negativos (ex: -10min)
    - Coerção de numéricos chave
    """
    d = df.copy()

    # Datas e partições
    # (na sua tabela, data_do_periodo é DATE; errors='coerce' mantém robustez)
    d["data_do_periodo"] = pd.to_datetime(d.get("data_do_periodo"), errors="coerce")
    d["data"] = d["data_do_periodo"].dt.date
    d["mes"] = d["data_do_periodo"].dt.month
    d["ano"] = d["data_do_periodo"].dt.year
    d["mes_ano"] = d["data_do_periodo"].dt.to_period("M").dt.to_timestamp()

    # Nome e uuid (robusto quando não há coluna)
    if "pessoa_entregadora" in d.columns:
        d["pessoa_entregadora_normalizado"] = d["pessoa_entregadora"].apply(normalizar)
    else:
        d["pessoa_entregadora_normalizado"] = ""

    if "id_da_pessoa_entregadora" in d.columns:
        d["uuid"] = d["id_da_pessoa_entregadora"].astype(str)
    else:
        d["uuid"] = ""

    # ---------- segundos_abs (COMPORTAMENTO ANTIGO) ----------
    # Mantém o valor "cru", inclusive negativos (-10:00 → -600)
    if "tempo_disponivel_absoluto" in d.columns:
        s = d["tempo_disponivel_absoluto"]
        try:
            if pd.api.types.is_timedelta64_dtype(s):
                d["segundos_abs"] = s.dt.total_seconds().fillna(0).astype(int)
            elif pd.api.types.is_numeric_dtype(s):
                d["segundos_abs"] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)
            else:
                # tenta parse como timedelta; se falhar, usa parser custom
                td = pd.to_timedelta(s.astype(str).str.strip(), errors="coerce")
                if td.notna().any():
                    d["segundos_abs"] = td.dt.total_seconds().fillna(0).astype(int)
                else:
                    d["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
        except Exception:
            d["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
    else:
        d["segundos_abs"] = 0

    # Numéricos chave (coerção)
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
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)

    # Padroniza 'periodo' se vier com outro nome
    if "periodo" not in d.columns:
        if "turno" in d.columns:
            d["periodo"] = d["turno"]
        else:
            d["periodo"] = None

    return d

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
        st.error("❌ SUPABASE_URL/SUPABASE_KEY não configurados em st.secrets ou variáveis de ambiente.")
        return pd.DataFrame()

    try:
        bruto = _ler_supabase(url, key)
        if not isinstance(bruto, pd.DataFrame) or bruto.empty:
            st.warning("⚠️ Supabase retornou vazio.")
            return pd.DataFrame()

        df = _pos_processar(bruto)

        if DEBUG_MODE:
            try:
                dmin = pd.to_datetime(df.get("data_do_periodo"), errors="coerce").min()
                dmax = pd.to_datetime(df.get("data_do_periodo"), errors="coerce").max()
                st.caption(f"📦 DF carregado: {len(df)} linhas • {dmin} → {dmax}")
            except Exception:
                pass

        return df

    except ValueError as ve:
        # erros “bonitos” de configuração (ex.: URL inválida)
        st.error(f"❌ Configuração inválida do Supabase: {ve}")
        return pd.DataFrame()
    except Exception as e:
        # erros de rede/conexão/API
        st.error(f"❌ Erro de conexão com Supabase: {e}")
        return pd.DataFrame()
