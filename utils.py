import pandas as pd
import unicodedata

# ---------------------------------------------------------
# Normalização de texto
# ---------------------------------------------------------
def normalizar(texto):
    """Remove acentos, espaços extras e põe em minúsculas."""
    if pd.isna(texto):
        return ""
    return (
        unicodedata.normalize("NFKD", str(texto))
        .encode("ASCII", "ignore")
        .decode()
        .lower()
        .strip()
    )


# ---------------------------------------------------------
# Conversão de tempo (HH:MM:SS → segundos)
# ---------------------------------------------------------
def tempo_para_segundos(t):
    """
    Converte strings de tempo em segundos.
    Aceita formatos: HH:MM:SS, HH:MM, H, ou números puros (segundos).
    Preserva o sinal (ex: '-00:10:00' → -600).
    """
    if pd.isna(t):
        return 0
    s = str(t).strip()
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    try:
        parts = s.split(":")
        if len(parts) == 3:
            h, m, s2 = map(int, parts)
            total = h * 3600 + m * 60 + s2
        elif len(parts) == 2:
            h, m = map(int, parts)
            total = h * 3600 + m * 60
        else:
            total = int(float(s))
        return sign * total
    except Exception:
        try:
            return sign * int(float(s))
        except Exception:
            return 0


# ---------------------------------------------------------
# Cálculo de tempo online (%)
# ---------------------------------------------------------
def calcular_tempo_online(df_filtrado: pd.DataFrame) -> float:
    """
    Tempo online = média de 'tempo_disponivel_escalado' em %.
    Regras:
      - Ignora linhas "inválidas" de tempo absoluto:
          * sentinela -10:00 (segundos_abs_raw == -600)
          * absoluto < 00:09:59 (599s)  -> não entra no % online
      - Auto-escalona a origem:
          * mediana <= 1   -> assume 0–1      (multiplica por 100)
          * <= 100         -> assume 0–100    (usa como está)
          * > 100          -> assume 0–10000  (divide por 100)
      - Clip final em [0, 100] e retorna com 1 casa.
    """
    if df_filtrado is None or df_filtrado.empty:
        return 0.0

    d = df_filtrado.copy()

    # -----------------------------
    # 1) Filtro por tempo absoluto
    #    - remove sentinela -10:00
    #    - remove "turno fantasma" (< 00:09:59)
    # -----------------------------
    LIMIAR_ABS_SEG = 9 * 60 + 59  # 00:09:59 -> 599s

    if "segundos_abs_raw" in d.columns:
        abs_raw = pd.to_numeric(d["segundos_abs_raw"], errors="coerce").fillna(0)
    elif "segundos_abs" in d.columns:
        # fallback: já clipado pelo loader
        abs_raw = pd.to_numeric(d["segundos_abs"], errors="coerce").fillna(0)
    elif "tempo_disponivel_absoluto" in d.columns:
        abs_raw = d["tempo_disponivel_absoluto"].apply(tempo_para_segundos)
        abs_raw = pd.to_numeric(abs_raw, errors="coerce").fillna(0)
    else:
        abs_raw = None

    if abs_raw is not None:
        # remove sentinela -10:00 e qualquer coisa abaixo do limiar
        d = d[(abs_raw != -600) & (abs_raw >= LIMIAR_ABS_SEG)].copy()

    # se tudo foi filtrado, não tem online %
    if d.empty:
        return 0.0

    esc = pd.to_numeric(d.get("tempo_disponivel_escalado"), errors="coerce").dropna()
    if esc.empty:
        return 0.0

    med = esc.median()
    mean_val = float(esc.mean())

    if med <= 1.0:
        val = mean_val * 100.0       # origem 0–1
    elif med <= 100.0:
        val = mean_val               # origem 0–100
    else:
        val = mean_val / 100.0       # origem 0–10000 (basis points)

    # saneamento final
    val = max(0.0, min(100.0, val))
    return round(val, 1)
