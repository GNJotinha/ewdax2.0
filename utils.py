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


import pandas as pd

TURNO_VALIDO_MIN_SEG = 10 * 60  # >= 00:10:00


def _entregador_key(df: pd.DataFrame) -> pd.Series:
    """
    Chave única do entregador (anti-duplicidade).
    Prioridade:
      1) uuid
      2) id_da_pessoa_entregadora
      3) pessoa_entregadora_normalizado
      4) pessoa_entregadora
    """
    for col in ("uuid", "id_da_pessoa_entregadora"):
        if col in df.columns:
            s = df[col].astype(str).fillna("").str.strip()
            if (s != "").any():
                return s

    if "pessoa_entregadora_normalizado" in df.columns:
        return df["pessoa_entregadora_normalizado"].astype(str).fillna("").str.strip()

    if "pessoa_entregadora" in df.columns:
        return df["pessoa_entregadora"].astype(str).fillna("").str.strip()

    return pd.Series([""] * len(df), index=df.index, dtype="string")


def mask_turno_valido(df: pd.DataFrame, min_seg: int = TURNO_VALIDO_MIN_SEG) -> pd.Series:
    secs = pd.to_numeric(df.get("segundos_abs", 0), errors="coerce").fillna(0)
    return secs >= float(min_seg)


def contar_ativos(
    df: pd.DataFrame,
    group_cols=("data", "turno"),
    min_seg: int = TURNO_VALIDO_MIN_SEG,
) -> pd.Series:
    """
    Ativos = entregadores únicos que atuaram >= min_seg.
    Considera qualquer tag (REGULAR/EXCESS), porque ativo é quem trabalhou.

    Retorna Series indexada por group_cols com o count de ativos.
    """
    if df is None or df.empty:
        return pd.Series(dtype="float64")

    dfx = df.copy()
    for c in group_cols:
        if c not in dfx.columns:
            raise KeyError(f"Coluna obrigatória não encontrada: {c}")
    if "segundos_abs" not in dfx.columns:
        raise KeyError("Coluna 'segundos_abs' não encontrada (esperada no df carregado).")

    dfx["_key"] = _entregador_key(dfx)
    dfx["_turno_valido"] = mask_turno_valido(dfx, min_seg=min_seg)

    base = dfx[dfx["_turno_valido"]].copy()
    return base.groupby(list(group_cols), dropna=False)["_key"].nunique()


def calcular_presenca_simples(
    df: pd.DataFrame,
    group_cols=("data", "turno"),
    min_seg: int = TURNO_VALIDO_MIN_SEG,
) -> pd.DataFrame:
    """
    Presença simples (operacional):
      presenca_h_por_entregador = SH / ativos

    SH = soma de segundos_abs / 3600 (>=10min)
    ativos = entregadores únicos (>=10min)
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=list(group_cols) + ["ativos", "horas_totais", "presenca_h_por_entregador"])

    dfx = df.copy()
    for c in group_cols:
        if c not in dfx.columns:
            raise KeyError(f"Coluna obrigatória não encontrada: {c}")
    if "segundos_abs" not in dfx.columns:
        raise KeyError("Coluna 'segundos_abs' não encontrada (esperada no df carregado).")

    dfx["_key"] = _entregador_key(dfx)
    dfx["_turno_valido"] = mask_turno_valido(dfx, min_seg=min_seg)

    base = dfx[dfx["_turno_valido"]].copy()

    ativos = base.groupby(list(group_cols), dropna=False)["_key"].nunique()
    horas = base.groupby(list(group_cols), dropna=False)["segundos_abs"].sum() / 3600.0

    out = pd.concat([ativos.rename("ativos"), horas.rename("horas_totais")], axis=1).fillna(0)
    out["presenca_h_por_entregador"] = out.apply(
        lambda r: (r["horas_totais"] / r["ativos"]) if r["ativos"] > 0 else 0.0,
        axis=1,
    )
    return out.reset_index()


def _vagas_robusto(
    df: pd.DataFrame,
    group_cols: list,
    vagas_col: str,
) -> tuple[pd.Series, pd.Series]:
    """
    Vagas robusto pra evitar >100% quando group_cols não inclui praca/sub_praca.
    Regra:
      - calcula max(vagas) por unidade (group + [praca/sub_praca se existirem e não estiverem no group])
      - soma essas vagas no nível do group solicitado
    Retorna (vagas_series, vagas_inconsistente_series)
    """
    extra = []
    for c in ("praca", "sub_praca"):
        if (c in df.columns) and (c not in group_cols):
            extra.append(c)

    if extra:
        vagas_por_unidade = df.groupby(group_cols + extra, dropna=False)[vagas_col].max()
        vagas = vagas_por_unidade.groupby(group_cols, dropna=False).sum()

        nun = df.groupby(group_cols + extra, dropna=False)[vagas_col].nunique()
        incons = nun.groupby(group_cols, dropna=False).max() > 1
        return vagas, incons

    vagas = df.groupby(group_cols, dropna=False)[vagas_col].max()
    incons = df.groupby(group_cols, dropna=False)[vagas_col].nunique() > 1
    return vagas, incons


def calcular_aderencia(
    df: pd.DataFrame,
    group_cols=("data", "turno"),
    vagas_col="numero_minimo_de_entregadores_regulares_na_escala",
    tag_col="tag",
    tag_regular="REGULAR",
    min_seg: int = TURNO_VALIDO_MIN_SEG,
) -> pd.DataFrame:
    """
    Aderência = regulares_atuaram / vagas * 100
    - regulares_atuaram: entregadores únicos REGULAR com >=10min
    - vagas: robusto (soma por praca/sub_praca se group_cols não incluir)
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=list(group_cols) + ["vagas", "vagas_inconsistente", "regulares_atuaram", "aderencia_pct"])

    dfx = df.copy()
    for c in group_cols:
        if c not in dfx.columns:
            raise KeyError(f"Coluna obrigatória não encontrada: {c}")
    for c in (vagas_col, tag_col):
        if c not in dfx.columns:
            raise KeyError(f"Coluna obrigatória não encontrada: {c}")
    if "segundos_abs" not in dfx.columns:
        raise KeyError("Coluna 'segundos_abs' não encontrada (esperada no df carregado).")

    dfx["_key"] = _entregador_key(dfx)
    dfx["_turno_valido"] = mask_turno_valido(dfx, min_seg=min_seg)
    dfx["_tag"] = dfx[tag_col].astype(str).fillna("").str.strip().str.upper()

    gcols = list(group_cols)

    base_reg = dfx[(dfx["_turno_valido"]) & (dfx["_tag"] == str(tag_regular).upper())].copy()
    regulares = base_reg.groupby(gcols, dropna=False)["_key"].nunique()

    vagas, incons = _vagas_robusto(dfx, gcols, vagas_col)

    out = pd.concat(
        [
            vagas.rename("vagas"),
            incons.rename("vagas_inconsistente"),
            regulares.rename("regulares_atuaram"),
        ],
        axis=1,
    ).fillna(0)

    out["aderencia_pct"] = out.apply(
        lambda r: (r["regulares_atuaram"] / r["vagas"] * 100.0) if r["vagas"] > 0 else 0.0,
        axis=1,
    )

    return out.reset_index()


def calcular_aderencia_presenca(
    df: pd.DataFrame,
    group_cols=("data", "turno"),
    vagas_col="numero_minimo_de_entregadores_regulares_na_escala",
    tag_col="tag",
    tag_regular="REGULAR",
    min_seg: int = TURNO_VALIDO_MIN_SEG,
) -> pd.DataFrame:
    """
    Wrapper que devolve tudo:
      - aderência (REGULAR / vagas)
      - presença simples (SH / ativos)
    """
    ad = calcular_aderencia(
        df,
        group_cols=group_cols,
        vagas_col=vagas_col,
        tag_col=tag_col,
        tag_regular=tag_regular,
        min_seg=min_seg,
    )

    pr = calcular_presenca_simples(
        df,
        group_cols=group_cols,
        min_seg=min_seg,
    )

    # merge no nível do group
    key = list(group_cols)
    out = pd.merge(ad, pr, on=key, how="outer").fillna(0)
    return out
