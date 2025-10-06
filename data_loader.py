from __future__ import annotations

# -------------------- imports --------------------
import os, math, base64, json, re, socket, time
import pandas as pd
import httpx
import streamlit as st
from supabase import create_client
from utils import normalizar, tempo_para_segundos

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

# ==================== helpers: base-url .co/.in ====================
def _b64url_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.b64decode(s + pad)

def _extract_ref_from_jwt(key: str) -> str | None:
    # JWT: header.payload.signature
    try:
        parts = key.split(".")
        if len(parts) < 2:
            return None
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        return payload.get("ref")
    except Exception:
        return None

def _candidate_urls(url: str, key: str) -> list[str]:
    """
    Candidatas:
      - a que veio no secrets (sanitizada)
      - https://<ref>.supabase.co
      - https://<ref>.supabase.in
    """
    out = []
    if url:
        u = url.strip().rstrip("/")
        if not re.match(r"^https?://", u, flags=re.I):
            u = "https://" + u
        out.append(u)
    ref = _extract_ref_from_jwt(key)
    if ref:
        out += [f"https://{ref}.supabase.co", f"https://{ref}.supabase.in"]
    # dedup preservando ordem
    seen = set(); uniq = []
    for u in out:
        if u not in seen:
            uniq.append(u); seen.add(u)
    return uniq

def _dns_ok(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443)
        return True
    except Exception:
        return False

def _http_warmup(u: str, k: str, tries: int = 5, base: float = 0.7) -> bool:
    last = None
    for i in range(tries):
        try:
            r = httpx.get(
                u.rstrip("/") + "/rest/v1/",
                headers={"apikey": k, "Authorization": f"Bearer {k}"},
                timeout=10.0,
            )
            if r.status_code in (200, 401, 404):
                return True
            last = RuntimeError(f"HTTP {r.status_code}")
        except httpx.HTTPError as he:
            last = he
        time.sleep(base * (2 ** i))
    if last:
        raise last
    return False

def _choose_working_base_url(url: str, key: str) -> str:
    """
    Escolhe a primeira candidata que resolve DNS e responde HTTP.
    """
    cands = _candidate_urls(url, key)
    if not cands:
        raise RuntimeError("Sem candidatas de URL para Supabase.")
    errs = []
    for u in cands:
        host = u.replace("https://", "").split("/")[0]
        if not _dns_ok(host):
            errs.append(f"DNS falhou para {u}")
            continue
        try:
            if _http_warmup(u, key):
                return u.rstrip("/")
        except Exception as e:
            errs.append(f"{u} warmup: {type(e).__name__}: {e}")
    raise RuntimeError("Nenhuma URL funcionou. Tentativas:\n- " + "\n- ".join(errs))

# ==================== leitura Supabase ====================
def _ler_supabase(url: str, key: str) -> pd.DataFrame:
    """
    Escolhe automaticamente uma base URL funcional (.co/.in), faz warm-up,
    pagina a tabela e retorna o DataFrame.
    """
    base_url = _choose_working_base_url(url, key)
    st.caption(f"✅ Supabase base URL: {base_url}")

    client = create_client(base_url, key)
    TBL = "Desempenho"
    batch = 50000
    frames: list[pd.DataFrame] = []

    def _paged(start: int, end: int):
        return client.table(TBL).select("*")\
            .order("data_do_periodo", desc=False)\
            .range(start, end)\
            .execute()

    # contar, mas seguir se falhar
    total = None
    try:
        resp = client.table(TBL).select("id", count="exact").execute()
        total = getattr(resp, "count", None)
    except Exception:
        pass

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

    # segundos_abs_raw (pode vir texto/numérico/td)
    if "tempo_disponivel_absoluto" in df.columns:
        s = df["tempo_disponivel_absoluto"]
        try:
            if pd.api.types.is_timedelta64_dtype(s):
                df["segundos_abs_raw"] = s.dt.total_seconds().fillna(0).astype(int)
            elif pd.api.types.is_numeric_dtype(s):
                df["segundos_abs_raw"] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)
            else:
                td = pd.to_timedelta(s.astype(str).str.strip(), errors="coerce")
                if td.notna().any():
                    df["segundos_abs_raw"] = td.dt.total_seconds().fillna(0).astype(int)
                else:
                    df["segundos_abs_raw"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
        except Exception:
            df["segundos_abs_raw"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
    else:
        df["segundos_abs_raw"] = 0

    # clip para métricas de SH/UTR/online (negativo → 0)
    seg_raw = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
    df["segundos_negativos_flag"] = seg_raw < 0
    df["segundos_abs"] = seg_raw.where(seg_raw >= 0, 0).astype(int)

    # numéricos chave
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
    O parâmetro prefer_drive só existe por compatibilidade.
    """
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")
    if not url or not key:
        st.error("❌ SUPABASE_URL/SUPABASE_KEY ausentes (secrets ou env).")
        st.stop()

    df = _ler_supabase(url, key)
    if df is None or df.empty:
        st.warning("⚠️ Supabase retornou vazio.")
        return pd.DataFrame()

    return _pos_processar(df)
