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


# ------------------------------
# Conversão de tempo
# ------------------------------
def tempo_para_segundos(valor):
    """
    Converte "HH:MM:SS" para segundos.
    Se vier NaN/None/"" retorna 0.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0
    s = str(valor).strip()
    if not s:
        return 0
    try:
        parts = s.split(":")
        if len(parts) != 3:
            return 0
        h, m, sec = parts
        return int(h) * 3600 + int(m) * 60 + int(sec)
    except Exception:
        return 0


# ------------------------------
# Regras de turno válido
# ------------------------------
TURNO_VALIDO_MIN_SEG = 30 * 60  # 30min


def mask_turno_valido(df: pd.DataFrame, min_seg: int = TURNO_VALIDO_MIN_SEG) -> pd.Series:
    """Turno válido se segundos_abs >= min_seg."""
    s = pd.to_numeric(df.get("segundos_abs", 0), errors="coerce").fillna(0)
    return s >= int(min_seg)


def _entregador_key(df: pd.DataFrame) -> pd.Series:
    """
    Chave do entregador pra anti-duplicidade.
    Preferência: uuid -> id_da_pessoa_entregadora -> pessoa_entregadora_normalizado -> pessoa_entregadora
    """
    for c in ("uuid", "id_da_pessoa_entregadora", "pessoa_entregadora_normalizado", "pessoa_entregadora"):
        if c in df.columns:
            return df[c].astype(str).fillna("").str.strip()
    return pd.Series([""] * len(df), index=df.index)


def calcular_aderencia(
    df: pd.DataFrame,
    group_cols=("data", "turno"),
    vagas_col="numero_minimo_de_entregadores_regulares_na_escala",
    tag_col="tag",
    tag_regular="REGULAR",
    min_seg: int = TURNO_VALIDO_MIN_SEG,
) -> pd.DataFrame:
    """Calcula **Aderência (REGULAR vs vagas)**.

    Definição:
      aderencia_pct = regulares_atuaram / vagas * 100

    Onde:
      - regulares_atuaram: entregadores únicos (anti-duplicidade) com tag == REGULAR e turno válido (>= min_seg)
      - vagas: soma robusta de vagas. Se `group_cols` NÃO incluir praca/sub_praca e essas colunas existirem,
              faz max por (grupo + praca/sub_praca) e soma no nível do grupo, evitando 133% e afins.

    Retorno:
      group_cols + ["vagas","vagas_inconsistente","regulares_atuaram","aderencia_pct"]
    """

    if df is None or df.empty:
        return pd.DataFrame(
            columns=list(group_cols)
            + ["vagas", "vagas_inconsistente", "regulares_atuaram", "aderencia_pct"]
        )

    dfx = df.copy()

    # normaliza vagas para numérico (suporta pt-BR tipo "1.234" e "4.118,10")
    if not pd.api.types.is_numeric_dtype(dfx[vagas_col]):
        v = dfx[vagas_col].astype("string").str.strip()
        v = v.replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA})
        # remove separador de milhar apenas quando for padrão 1.234 ou 1.234,56
        mask_thou = v.str.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$")
        v = v.where(~mask_thou, v.str.replace(".", "", regex=False))
        v = v.str.replace(",", ".", regex=False)
        dfx[vagas_col] = pd.to_numeric(v, errors="coerce").fillna(0.0)

    # valida colunas mínimas
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

    # -------------------------------------------------
    # REGULARES (turno válido)
    # -------------------------------------------------
    base_reg = dfx[(dfx["_turno_valido"]) & (dfx["_tag"] == str(tag_regular).upper())].copy()
    regulares_atuaram = base_reg.groupby(gcols, dropna=False)["_key"].nunique()

    # -------------------------------------------------
    # VAGAS (robusto)
    # -------------------------------------------------
    extra_vaga_cols = []
    for c in ("praca", "sub_praca"):
        if (c in dfx.columns) and (c not in gcols):
            extra_vaga_cols.append(c)

    vagas_por_unidade = (
        dfx.groupby(gcols + extra_vaga_cols, dropna=False)[vagas_col].max()
        if extra_vaga_cols
        else dfx.groupby(gcols, dropna=False)[vagas_col].max()
    )

    vagas = (
        vagas_por_unidade.groupby(gcols, dropna=False).sum()
        if extra_vaga_cols
        else vagas_por_unidade
    )

    # inconsistência: se dentro do MESMO grupo (considerando as extras) variar a vaga
    if extra_vaga_cols:
        vagas_nunique_unidade = dfx.groupby(gcols + extra_vaga_cols, dropna=False)[vagas_col].nunique()
        vagas_incons = vagas_nunique_unidade.groupby(gcols, dropna=False).max() > 1
    else:
        vagas_incons = dfx.groupby(gcols, dropna=False)[vagas_col].nunique() > 1

    out = pd.concat(
        [
            vagas.rename("vagas"),
            vagas_incons.rename("vagas_inconsistente"),
            regulares_atuaram.rename("regulares_atuaram"),
        ],
        axis=1,
    ).fillna(0)

    out["aderencia_pct"] = out.apply(
        lambda r: (r["regulares_atuaram"] / r["vagas"] * 100.0) if r["vagas"] > 0 else 0.0,
        axis=1,
    )

    cols_keep = gcols + ["vagas", "vagas_inconsistente", "regulares_atuaram", "aderencia_pct"]
    return out.reset_index()[cols_keep]


# ---------------------------------------------------------------------
# Compat: nome antigo (sem "presença" — removido em jan/2026)
# ---------------------------------------------------------------------
def calcular_aderencia_presenca(*args, **kwargs) -> pd.DataFrame:
    """Alias compatível.

    Antes: calculava aderência + presença.
    Agora: retorna **apenas aderência** (mesmas colunas do `calcular_aderencia`).
    """
    return calcular_aderencia(*args, **kwargs)
