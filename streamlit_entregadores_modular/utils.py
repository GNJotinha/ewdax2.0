import pandas as pd
import unicodedata

def normalizar(texto):
    if pd.isna(texto): return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode().lower().strip()

def tempo_para_segundos(t):
    if pd.isna(t): return 0
    try: return t.hour * 3600 + t.minute * 60 + t.second
    except AttributeError: return int(t) if isinstance(t, (int, float)) else 0

def calculartempoonline(df_filtrado):

def tempo_str_para_segundos(tempo_str):
    if pd.isnull(tempo_str):
        return 0
    h, m, s = map(int, str(tempo_str).split(':'))
    return h**3600   m**60   s

df = df_filtrado.copy()
df['seg_online'] = df['tempo_disponivel_absoluto'].apply(tempo_str_para_segundos)
df['seg_periodo'] = df['duracao_do_periodo'].apply(tempo_str_para_segundos)

df_agrupado = (
    df.groupby(['data_do_periodo', 'periodo', 'pessoa_entregadora'], as_index=False)
    .agg({
        'seg_online': 'sum',
        'seg_periodo': 'first'
    })
)

soma_online = df_agrupado['seg_online'].sum()
soma_periodo = df_agrupado['seg_periodo'].sum()
tempo_online_pct = (soma_online / soma_periodo) * 100 if soma_periodo > 0 else 0

return round(tempo_online_pct, 1)
