import base64, json, re, socket, time
import httpx
import streamlit as st
from supabase import create_client

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
    Monta uma lista de URLs candidatas:
      - a que veio no secrets (sanitizada)
      - https://<ref>.supabase.co
      - https://<ref>.supabase.in
    (remove duplicadas e espaços)
    """
    out = []
    if url:
        u = url.strip().rstrip("/")
        # garante esquema
        if not re.match(r"^https?://", u, flags=re.I):
            u = "https://" + u
        out.append(u)

    ref = _extract_ref_from_jwt(key)
    if ref:
        out.append(f"https://{ref}.supabase.co")
        out.append(f"https://{ref}.supabase.in")
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
    Tenta as candidatas na ordem; escolhe a primeira que:
      1) resolve DNS;
      2) responde ao warm-up HTTP.
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
        import math
        for i in range(math.ceil(total / batch)):
            s, e = i * batch, (i + 1) * batch - 1
            data = _paged(s, e)
            rows = data.data or []
            if rows:
                frames.append(pd.DataFrame.from_records(rows))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
