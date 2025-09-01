import pandas as pd
import unicodedata

def normalizar(texto):
    if pd.isna(texto): return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode().lower().strip()

def tempo_para_segundos(t):
    if pd.isna(t): return 0
    try:
        h, m, s = map(int, str(t).split(':'))
        return h*3600 + m*60 + s
    except Exception:
        return int(t) if isinstance(t, (int, float)) else 0

import pandas as pd

def calcular_tempo_online(df_filtrado):
    col = "tempo_disponivel_escalado"
    if col not in df_filtrado.columns:
        return 0.0

    s = pd.to_numeric(df_filtrado[col], errors="coerce").dropna()
    if s.empty:
        return 0.0

    m = float(s.mean())
    # Autodetecta escala:
    # - média <= 1.0  → assume [0,1]  → converte pra %
    # - média >  1.0  → assume [0,100]→ já está em %
    pct = m * 100 if m <= 1.0 else m
    return round(pct, 1)  # retorna pronto para exibir com "%"


