# data_loader.py — FULL SUPABASE
import math
import pandas as pd
import streamlit as st
from utils import normalizar, tempo_para_segundos

TBL = 'Desempenho'  # nome exato da sua tabela

# ---------------------------------------------------------
# Entrada principal (com cache)
# ---------------------------------------------------------
@st.cache_data(show_spinner=False)
def carregar_dados(prefer_drive: bool = False, _ts: float | None = None) -> pd.DataFrame:
    """
    Lê 100% do Supabase, pagina em lotes e padroniza as colunas
    para o restante do app. O parâmetro prefer_drive é ignorado
    (mantido só pra compatibilidade com main.py).
    """
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        st.error("❌ SUPABASE_URL/SUPABASE_KEY ausentes em st.secrets.")
        st.stop()

    df = _ler_supabase(url, key)
    if df is None or df.empty:
        st.warning("⚠️ Supabase retornou vazio.")
        return pd.DataFrame()

    return _pos_processar(df)


# ---------------------------------------------------------
# Leitura da Tabela no Supabase (pagina em lotes)
# ---------------------------------------------------------
def _ler_supabase(url: str, key: str) -> pd.DataFrame:
    from supabase import create_client
    client = create_client(url, key)

    batch = 50000
    frames: list[pd.DataFrame] = []

    # Tentativa de contar linhas para paginar certinho
    try:
        count_resp = client.table(TBL).select('id', count='exact').execute()
        total = getattr(count_resp, "count", None)
    except Exception:
        total = None

    if total is None:
        # fallback: pagina até não vir mais nada
        start = 0
        while True:
            end = start + batch - 1  # range é inclusivo
            data = client.table(TBL).select('*')\
                .order('data_do_periodo', desc=False)\
                .range(start, end)\
                .execute()
            rows = data.data or []
            if not rows:
                break
            frames.append(pd.DataFrame.from_records(rows))
            if len(rows) < batch:
                break
            start += batch
    else:
        pags = math.ceil(total / batch)
        for i in range(pags):
            s = i * batch
            e = s + batch - 1
            data = client.table(TBL).select('*')\
                .order('data_do_periodo', desc=False)\
                .range(s, e)\
                .execute()
            rows = data.data or []
            if rows:
                frames.append(pd.DataFrame.from_records(rows))

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------
# Pós-processamento (formata tudo que o app espera)
# ---------------------------------------------------------
def _pos_processar(df: pd.DataFrame) -> pd.DataFrame:
    # Datas/particionamento
    df["data_do_periodo"] = pd.to_datetime(df.get("data_do_periodo"), errors="coerce")
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["mes_ano"] = df["data_do_periodo"].dt.to_period("M").dt.to_timestamp()

    # Nome/uuid
    df["pessoa_entregadora_normalizado"] = df.get("pessoa_entregadora", "").apply(normalizar)
    if "id_da_pessoa_entregadora" in df.columns:
        df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
    else:
        df["uuid"] = ""

    # ---- segundos_abs_raw: pode vir numérico/texto/tempo ----
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

    # Flag e versão clipada (negativos -> 0) p/ SH/UTR/online
    seg_raw = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
    df["segundos_negativos_flag"] = seg_raw < 0
    df["segundos_abs"] = seg_raw.where(seg_raw >= 0, 0).astype(int)

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

    # Limpeza de colunas comuns que podem vir do banco
    if "created_at" in df.columns:
        # manter se quiser auditar; senão, tudo certo deixar
        pass
    if "id" in df.columns:
        # idem
        pass

    return df
