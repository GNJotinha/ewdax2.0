import pandas as pd
import unicodedata

def normalizar(texto):
    if pd.isna(texto): return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode().lower().strip()

def tempo_para_segundos(t):
    if pd.isna(t): return 0
    try: return t.hour * 3600 + t.minute * 60 + t.second
    except AttributeError: return int(t) if isinstance(t, (int, float)) else 0
