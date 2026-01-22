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
      - Ignora apenas linhas com -10:00 (segundos_abs_raw == -600).
      - Auto-escalona a origem:
          * mediana <= 1   -> assume 0–1      (multiplica por 100)
          * <= 100         -> assume 0–100    (usa como está)
          * > 100          -> assume 0–10000  (divide por 100)
      - Clip final em [0, 100] e retorna com 1 casa.
    """
    if df_filtrado is None or df_filtrado.empty:
        return 0.0

    d = df_filtrado.copy()

    # ignora -10:00 no cálculo do online
    if "segundos_abs_raw" in d.columns:
        d = d[d["segundos_abs_raw"] != -600]

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

# ---------------------------------------------------------
# Aderência (REGULAR vs vagas) e Presença (h/entregador)
# ---------------------------------------------------------
TURNO_VALIDO_MIN_SEG = 10 * 60  # 00:10:00 (>= 9:59)


def _entregador_key(df: pd.DataFrame) -> pd.Series:
    """
    Chave única do entregador (anti-duplicidade).
    Prioridade:
      1) uuid
      2) pessoa_entregadora_normalizado
      3) pessoa_entregadora
    """
    if "uuid" in df.columns:
        s = df["uuid"].astype(str).fillna("").str.strip()
        if (s != "").any():
            return s

    if "pessoa_entregadora_normalizado" in df.columns:
        return df["pessoa_entregadora_normalizado"].astype(str).fillna("").str.strip()

    return df.get("pessoa_entregadora", "").astype(str).fillna("").str.strip()


def mask_turno_valido(df: pd.DataFrame, min_seg: int = TURNO_VALIDO_MIN_SEG) -> pd.Series:
    secs = pd.to_numeric(df.get("segundos_abs", 0), errors="coerce").fillna(0)
    return secs >= float(min_seg)


def calcular_aderencia_presenca(
    df: pd.DataFrame,
    group_cols=("data", "turno", "praca", "sub_praca"),
    vagas_col="numero_minimo_de_entregadores_regulares_na_escala",
    tag_col="tag",
    tag_regular="REGULAR",
    min_seg: int = TURNO_VALIDO_MIN_SEG,
) -> pd.DataFrame:
    """
    REGRA DE OURO:
    - SOMENTE REGULAR entra em TUDO (aderência, presença, horas).
    - EXCESS é completamente ignorado.

    Anti-duplicidade:
    - Entregador conta no máximo 1x por grupo (ex.: data+turno+praça+subpraça),
      mesmo que troque de praça ou saia/volte no mesmo turno.
    """

    if df is None or df.empty:
        return pd.DataFrame(
            columns=list(group_cols)
            + [
                "vagas",
                "regulares_atuaram",
                "entregadores_presentes",
                "horas_totais",
                "aderencia_pct",
                "presenca_h_por_entregador",
                "vagas_inconsistente",
            ]
        )

    dfx = df.copy()

    # valida colunas
    for c in group_cols:
        if c not in dfx.columns:
            raise KeyError(f"Coluna obrigatória não encontrada: {c}")
    if vagas_col not in dfx.columns:
        raise KeyError(f"Coluna de vagas não encontrada: {vagas_col}")
    if tag_col not in dfx.columns:
        raise KeyError(f"Coluna de tag não encontrada: {tag_col}")

    # chave única e regras
    dfx["_key"] = _entregador_key(dfx)
    dfx["_turno_valido"] = mask_turno_valido(dfx, min_seg=min_seg)

    dfx["_tag"] = (
        dfx[tag_col]
        .astype(str)
        .fillna("")
        .str.strip()
        .str.upper()
    )

    # 🚨 REGRA FUNDAMENTAL
    base_regular = dfx[
        (dfx["_tag"] == tag_regular.upper())
        & (dfx["_turno_valido"])
    ].copy()

    # -------------------------
    # PRESENÇA (SÓ REGULAR)
    # -------------------------
    presentes = (
        base_regular
        .groupby(list(group_cols), dropna=False)["_key"]
        .nunique()
    )

    horas = (
        base_regular
        .groupby(list(group_cols), dropna=False)["segundos_abs"]
        .sum()
        / 3600.0
    )

    # -------------------------
    # ADERÊNCIA (SÓ REGULAR)
    # -------------------------
    regulares = presentes.rename("regulares_atuaram")

    # vagas (pode repetir por linha)
    vagas_stats = (
        dfx
        .groupby(list(group_cols), dropna=False)[vagas_col]
        .agg(vagas_max="max", vagas_min="min", vagas_nunique="nunique")
    )

    # -------------------------
    # OUTPUT
    # -------------------------
    out = pd.concat(
        [
            vagas_stats,
            regulares,
            presentes.rename("entregadores_presentes"),
            horas.rename("horas_totais"),
        ],
        axis=1,
    ).fillna(0)

    out["vagas"] = out["vagas_max"]
    out["vagas_inconsistente"] = out["vagas_nunique"] > 1

    out["aderencia_pct"] = out.apply(
        lambda r: min((r["regulares_atuaram"] / r["vagas"] * 100.0), 100.0)
        if r["vagas"] > 0 else 0.0,
        axis=1,
    )

    out["presenca_h_por_entregador"] = out.apply(
        lambda r: (r["horas_totais"] / r["entregadores_presentes"])
        if r["entregadores_presentes"] > 0 else 0.0,
        axis=1,
    )

    return out.reset_index()[
        list(group_cols)
        + [
            "vagas",
            "regulares_atuaram",
            "entregadores_presentes",
            "horas_totais",
            "aderencia_pct",
            "presenca_h_por_entregador",
            "vagas_inconsistente",
        ]
    ]
