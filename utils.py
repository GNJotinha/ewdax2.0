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


def _turno_valido_mask(df: pd.DataFrame, min_seg: int = TURNO_VALIDO_MIN_SEG) -> pd.Series:
    secs = pd.to_numeric(df.get("segundos_abs", 0), errors="coerce").fillna(0)
    return secs >= float(min_seg)


def sh_e_ativos_do_recorte(df: pd.DataFrame, min_seg: int = TURNO_VALIDO_MIN_SEG) -> tuple[float, int]:
    """
    Retorna (SH_total_horas, ativos_unicos) no recorte atual.

    REGRA:
    - só conta linhas com segundos_abs >= 10min
    - ativos é UNIQUE no recorte inteiro (não por dia/turno), pra não duplicar
    """
    if df is None or df.empty:
        return 0.0, 0

    if "segundos_abs" not in df.columns:
        raise KeyError("Coluna 'segundos_abs' não encontrada (esperada no df carregado).")

    dfx = df.copy()
    dfx["_key"] = _entregador_key(dfx)
    m = _turno_valido_mask(dfx, min_seg=min_seg)

    base = dfx[m].copy()
    sh_h = float(pd.to_numeric(base["segundos_abs"], errors="coerce").fillna(0).sum()) / 3600.0
    ativos = int(base["_key"].dropna().nunique())
    return sh_h, ativos


def presenca_do_recorte(df: pd.DataFrame, min_seg: int = TURNO_VALIDO_MIN_SEG) -> float:
    """
    Presença = SH_total / ativos_unicos (do recorte inteiro).
    """
    sh_h, ativos = sh_e_ativos_do_recorte(df, min_seg=min_seg)
    return (sh_h / ativos) if ativos > 0 else 0.0


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
    group_cols=("data", "periodo"),
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
    dfx["_turno_valido"] = _turno_valido_mask(dfx, min_seg=min_seg)
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
    Mantém compatibilidade com o app:
      - Aderência por grupo (group_cols)
      - Presença simples por grupo (SH/ativos do grupo)

    Obs:
      A presença do RECORTE (mês inteiro) correta continua sendo:
        presenca_do_recorte(df)
      (porque evita duplicar entregador em múltiplos grupos).
    """
    if df is None or df.empty:
        return pd.DataFrame(
            columns=list(group_cols)
            + ["vagas", "vagas_inconsistente", "regulares_atuaram", "aderencia_pct", "ativos", "horas_totais", "presenca_h_por_entregador"]
        )

    # Aderência por grupo
    ad = calcular_aderencia(
        df,
        group_cols=group_cols,
        vagas_col=vagas_col,
        tag_col=tag_col,
        tag_regular=tag_regular,
        min_seg=min_seg,
    )

    # Presença por grupo (SH/ativos do grupo)
    dfx = df.copy()
    for c in group_cols:
        if c not in dfx.columns:
            raise KeyError(f"Coluna obrigatória não encontrada: {c}")
    if "segundos_abs" not in dfx.columns:
        raise KeyError("Coluna 'segundos_abs' não encontrada (esperada no df carregado).")

    dfx["_key"] = _entregador_key(dfx)
    dfx["_turno_valido"] = _turno_valido_mask(dfx, min_seg=min_seg)
    base = dfx[dfx["_turno_valido"]].copy()

    ativos_g = base.groupby(list(group_cols), dropna=False)["_key"].nunique().rename("ativos")
    horas_g = (base.groupby(list(group_cols), dropna=False)["segundos_abs"].sum() / 3600.0).rename("horas_totais")

    pr = pd.concat([ativos_g, horas_g], axis=1).fillna(0).reset_index()
    pr["presenca_h_por_entregador"] = pr.apply(
        lambda r: (r["horas_totais"] / r["ativos"]) if r["ativos"] > 0 else 0.0,
        axis=1,
    )

    # merge final
    out = pd.merge(ad, pr, on=list(group_cols), how="outer").fillna(0)
    return out

