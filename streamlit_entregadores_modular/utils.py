import pandas as pd
import unicodedata

def normalizar(texto):
    if pd.isna(texto): 
        return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode().lower().strip()

def tempo_para_segundos(t):
    if pd.isna(t): 
        return 0
    try:
        h, m, s = map(int, str(t).split(':'))
        return h*3600 + m*60 + s
    except Exception:
        return int(t) if isinstance(t, (int, float)) else 0

def calcular_tempo_online(df_filtrado):
    """
    Retorna SEMPRE em 0–100 (%).
    A coluna 'tempo_disponivel_escalado' já está em escala percentual (0–100).
    """
    if "tempo_disponivel_escalado" not in df_filtrado.columns:
        return 0.0
    df_valid = df_filtrado[df_filtrado["tempo_disponivel_escalado"].notnull()]
    if df_valid.empty:
        return 0.0
    media_pct = df_valid["tempo_disponivel_escalado"].mean()
    return round(float(media_pct), 2)
