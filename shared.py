import pandas as pd
import unicodedata

def hms_from_hours(horas_float) -> str:
    try:
        h = float(horas_float)
        if h < 0 or not (h == h):
            h = 0.0
    except Exception:
        h = 0.0
    total_seg = int(round(h * 3600))
    hh = total_seg // 3600
    mm = (total_seg % 3600) // 60
    ss = total_seg % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"

def sub_options_with_livre(df_slice: pd.DataFrame, praca_scope: str = "SAO PAULO") -> list[str]:
    subs_col = df_slice.get("sub_praca", pd.Series(dtype=object))
    subs_validas = sorted([x for x in subs_col.dropna().unique()])

    # Torna robusto quando 'praca' não existir
    praca_series = df_slice.get("praca")
    if praca_series is None:
        tem_livre = False
    else:
        tem_livre = ((praca_series == praca_scope) & (subs_col.isna())).any()

    return (["LIVRE"] + subs_validas) if tem_livre else subs_validas

def apply_sub_filter(df_base: pd.DataFrame, selecionadas: list[str], praca_scope: str = "SAO PAULO") -> pd.DataFrame:
    if not selecionadas:
        return df_base
    mask = pd.Series(False, index=df_base.index)
    reais = [s for s in selecionadas if s != "LIVRE"]
    if reais:
        mask |= df_base.get("sub_praca").isin(reais)
    if "LIVRE" in selecionadas:
        mask |= ((df_base.get("praca") == praca_scope) & (df_base.get("sub_praca").isna()))
    return df_base[mask]

def _norm(txt: str) -> str:
    return unicodedata.normalize("NFKD", str(txt)).encode("ASCII", "ignore").decode().lower().strip()

def is_medias(txt: str) -> bool:
    return _norm(txt).startswith("med")

def is_absoluto(txt: str) -> bool:
    return _norm(txt).startswith("abso")
