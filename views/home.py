import html
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from relatorios import utr_por_entregador_turno
from utils import calcular_aderencia

TZ_SP = ZoneInfo("America/Sao_Paulo")


def _fmt_int(x):
    try:
        return f"{int(round(float(x))):,}".replace(",", ".")
    except Exception:
        return "0"


def _fmt_pct(x, nd=1):
    try:
        return f"{float(x):.{nd}f}%".replace(".", ",")
    except Exception:
        return "0,0%"


def _pick_col(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    return None


def _sum_numeric(df: pd.DataFrame, col: str) -> float:
    """Soma numérica segura: se não existir coluna, retorna 0; se existir, converte e soma."""
    if not col or col not in df.columns:
        return 0.0
    s = pd.to_numeric(df[col], errors="coerce").fillna(0)
    try:
        return float(s.sum())
    except Exception:
        return 0.0


def _to_mes_ano_dt(series: pd.Series) -> pd.Series:
    """Converte coluna mes_ano (vários formatos) pra datetime (primeiro dia do mês)."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")

    s = series.astype(str).str.strip()
    # limpa "nan"/vazios
    s = s.replace({"nan": None, "NaT": None, "None": None, "": None})

    valid = s.dropna()
    if not valid.empty and valid.str.fullmatch(r"\d{6}").all():
        # YYYYMM
        return pd.to_datetime(s, format="%Y%m", errors="coerce")

    # tenta parse geral (dd/mm/aaaa, mm/aaaa, aaaa-mm, etc.)
    return pd.to_datetime(s, errors="coerce", dayfirst=True)


def _fmt_hm_from_seconds(seconds: float) -> str:
    try:
        sec = float(seconds)
    except Exception:
        return "0m"

    if sec <= 0:
        return "0m"

    mins = int(round(sec / 60.0))
    h = mins // 60
    m = mins % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def _calc_utr_media_fallback(df_mes: pd.DataFrame, ofert_col: str, seg_col: str, turno_col: str | None) -> float:
    """Fallback da UTR média direto do df_mes, caso utr_por_entregador_turno falhe."""
    if df_mes is None or df_mes.empty:
        return 0.0
    if not ofert_col or ofert_col not in df_mes.columns:
        return 0.0
    if not seg_col or seg_col not in df_mes.columns:
        return 0.0
    if "pessoa_entregadora" not in df_mes.columns:
        return 0.0

    group_cols = ["pessoa_entregadora"]
    if turno_col and turno_col in df_mes.columns:
        group_cols.append(turno_col)

    tmp = df_mes[group_cols + [ofert_col, seg_col]].copy()
    tmp["pessoa_entregadora"] = tmp["pessoa_entregadora"].astype(str).str.strip()

    # remove nomes vazios
    tmp = tmp[tmp["pessoa_entregadora"].notna() & (tmp["pessoa_entregadora"] != "")]

    tmp["_ofert"] = pd.to_numeric(tmp[ofert_col], errors="coerce").fillna(0)
    tmp["_sh"] = pd.to_numeric(tmp[seg_col], errors="coerce").fillna(0) / 3600.0

    agg = tmp.groupby(group_cols, as_index=False).agg({"_ofert": "sum", "_sh": "sum"})
    agg = agg[agg["_sh"] > 0]

    if agg.empty:
        return 0.0

    return float((agg["_ofert"] / agg["_sh"]).mean())


def render(df: pd.DataFrame, USUARIOS: dict):
    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    debug_home = bool(st.session_state.get("debug_home", False))

    # =========================
    # MÊS ATUAL (timezone SP)
    # =========================
    now_sp = datetime.now(TZ_SP)
    mes_atual, ano_atual = int(now_sp.month), int(now_sp.year)

    # tenta filtrar por mes/ano
    if ("mes" in df.columns) and ("ano" in df.columns):
        df_mes = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)].copy()
    else:
        # fallback por mes_ano (robusto)
        if "mes_ano" in df.columns:
            mes_ano_dt = _to_mes_ano_dt(df["mes_ano"])
            ultimo_mes_dt = mes_ano_dt.max()
            if pd.notna(ultimo_mes_dt):
                df_mes = df[mes_ano_dt == ultimo_mes_dt].copy()
                mes_atual = int(pd.to_datetime(ultimo_mes_dt).month)
                ano_atual = int(pd.to_datetime(ultimo_mes_dt).year)
            else:
                df_mes = df.copy()
        else:
            df_mes = df.copy()

    mes_txt = f"{mes_atual:02d}/{ano_atual}"

    # =========================
    # data mais recente (topo)
    # =========================
    data_col = _pick_col(df_mes.columns, ["data", "data_do_periodo", "data_do_periodo_de_referencia"])
    data_str = "—"
    if data_col and (data_col in df_mes.columns) and (not df_mes.empty):
        dtmax = pd.to_datetime(df_mes[data_col], errors="coerce").max()
        if pd.notna(dtmax):
            try:
                data_str = pd.to_datetime(dtmax).strftime("%d/%m/%Y")
            except Exception:
                data_str = str(dtmax)

    # =========================
    # KPIs (colunas com fallback)
    # =========================
    ofert_col = _pick_col(df_mes.columns, ["numero_de_corridas_ofertadas", "corridas_ofertadas"])
    aceitas_col = _pick_col(df_mes.columns, ["numero_de_corridas_aceitas", "corridas_aceitas"])
    rejeit_col = _pick_col(df_mes.columns, ["numero_de_corridas_rejeitadas", "corridas_rejeitadas"])
    seg_col = _pick_col(df_mes.columns, ["segundos_abs"])

    ofertadas = int(_sum_numeric(df_mes, ofert_col))
    aceitas = int(_sum_numeric(df_mes, aceitas_col))
    rejeitadas = int(_sum_numeric(df_mes, rejeit_col))

    # entregadores ativos (trim pra não contar "João" e "João " como 2)
    entreg_uniq = 0
    if "pessoa_entregadora" in df_mes.columns and not df_mes.empty:
        s_ent = df_mes["pessoa_entregadora"].dropna().astype(str).str.strip()
        s_ent = s_ent[s_ent != ""]
        entreg_uniq = int(s_ent.nunique())

    acc_pct = (aceitas / ofertadas * 100.0) if ofertadas > 0 else 0.0
    rej_pct = (rejeitadas / ofertadas * 100.0) if ofertadas > 0 else 0.0

    seg_total = _sum_numeric(df_mes, seg_col)
    horas_total = float(seg_total / 3600.0) if seg_total > 0 else 0.0
    utr_abs = (ofertadas / horas_total) if horas_total > 0 else 0.0

    # =========================
    # UTR média (coerente com o mês)
    # =========================
    turno_col = _pick_col(df_mes.columns, ["turno", "tipo_turno", "periodo"])
    utr_medias = 0.0

    # tenta função existente primeiro
    try:
        base_home = utr_por_entregador_turno(df_mes, mes_atual, ano_atual)
        if (
            isinstance(base_home, pd.DataFrame)
            and (not base_home.empty)
            and ("supply_hours" in base_home.columns)
            and ("corridas_ofertadas" in base_home.columns)
        ):
            base_pos = base_home.copy()
            base_pos["supply_hours"] = pd.to_numeric(base_pos["supply_hours"], errors="coerce").fillna(0)
            base_pos["corridas_ofertadas"] = pd.to_numeric(base_pos["corridas_ofertadas"], errors="coerce").fillna(0)
            base_pos = base_pos[base_pos["supply_hours"] > 0]
            if not base_pos.empty:
                utr_medias = float((base_pos["corridas_ofertadas"] / base_pos["supply_hours"]).mean())
        else:
            # fallback local
            utr_medias = _calc_utr_media_fallback(df_mes, ofert_col, seg_col, turno_col)
    except Exception as e:
        # fallback local
        utr_medias = _calc_utr_media_fallback(df_mes, ofert_col, seg_col, turno_col)
        if debug_home:
            st.warning("Erro calculando UTR média via utr_por_entregador_turno; usando fallback.")
            st.exception(e)

    # =========================
    # ADERÊNCIA
    # =========================
    ader_pct = 0.0
    ader_reg = 0
    ader_vagas = 0.0
    vagas_incons = False

    vagas_col = _pick_col(df_mes.columns, ["numero_minimo_de_entregadores_regulares_na_escala", "vagas"])
    tag_col = _pick_col(df_mes.columns, ["tag"])

    if (not df_mes.empty) and vagas_col and tag_col and data_col and seg_col:
        group_cols = (data_col, turno_col) if turno_col else (data_col,)
        try:
            base_ap = calcular_aderencia(
                df_mes,
                group_cols=group_cols,
                vagas_col=vagas_col,
                tag_col=tag_col,
                tag_regular="REGULAR",
            )

            if isinstance(base_ap, pd.DataFrame) and not base_ap.empty:
                ader_reg = int(_sum_numeric(base_ap, "regulares_atuaram"))
                ader_vagas = float(_sum_numeric(base_ap, "vagas"))

                if ader_vagas > 0:
                    ader_pct = round((ader_reg / ader_vagas) * 100.0, 1)

                if "vagas_inconsistente" in base_ap.columns:
                    vagas_incons = bool(base_ap["vagas_inconsistente"].fillna(False).astype(bool).any())
        except Exception as e:
            if debug_home:
                st.warning("Erro calculando aderência; deixando zerado.")
                st.exception(e)

    pct_bar = max(0.0, min(float(ader_pct), 100.0))

    # =========================
    # TOP 3 POR HORAS (mais estável / legível)
    # =========================
    top3 = []
    if ("pessoa_entregadora" in df_mes.columns) and seg_col and (seg_col in df_mes.columns) and (not df_mes.empty):
        tmp_h = df_mes[["pessoa_entregadora", seg_col]].copy()
        tmp_h["pessoa_entregadora"] = tmp_h["pessoa_entregadora"].astype(str).str.strip()
        tmp_h = tmp_h[tmp_h["pessoa_entregadora"].notna() & (tmp_h["pessoa_entregadora"] != "")]

        tmp_h["_seg"] = pd.to_numeric(tmp_h[seg_col], errors="coerce").fillna(0)

        top = (
            tmp_h.groupby("pessoa_entregadora", as_index=False)["_seg"]
            .sum()
            .sort_values(["_seg", "pessoa_entregadora"], ascending=[False, True], kind="mergesort")
            .head(3)
        )

        for _, r in top.iterrows():
            top3.append((str(r["pessoa_entregadora"]), float(r["_seg"])))

    # =========================
    # HEADER
    # =========================
    hL, hR = st.columns([4, 1])
    with hL:
        st.title("📁 Painel de Entregadores")
        st.caption(f"Dados atualizados • {data_str}")
    with hR:
        if st.button("Atualizar dados", use_container_width=True, key="btn_refresh_home"):
            st.session_state.force_refresh = True
            st.session_state.just_refreshed = True
            # tirei o st.cache_data.clear(): o main já faz refresh com _ts/prefer_drive
            st.rerun()

    # =========================
    # CONTEÚDO
    # =========================
    st.markdown(f'<div class="neo-section">Resumo do mês ({mes_txt})</div>', unsafe_allow_html=True)

    aceitas_html = f"{_fmt_int(aceitas)}<span class='pct'>({_fmt_pct(acc_pct, 1)})</span>"
    rejeitadas_html = f"{_fmt_int(rejeitadas)}<span class='pct'>({_fmt_pct(rej_pct, 1)})</span>"

    st.markdown(
        f"""
        <div class="neo-grid-4">
          <div class="neo-card">
            <div class="neo-label">Ofertadas – UTR</div>
            <div class="neo-value">{_fmt_int(ofertadas)}</div>
            <div class="neo-subline">Absoluto {utr_abs:.2f} • Média {utr_medias:.2f}</div>
          </div>

          <div class="neo-card neo-success">
            <div class="neo-label">Aceitas</div>
            <div class="neo-value">{aceitas_html}</div>
            <div class="neo-subline">&nbsp;</div>
          </div>

          <div class="neo-card neo-danger">
            <div class="neo-label">Rejeitadas</div>
            <div class="neo-value">{rejeitadas_html}</div>
            <div class="neo-subline">&nbsp;</div>
          </div>

          <div class="neo-card">
            <div class="neo-label">Entregadores ativos</div>
            <div class="neo-value">{_fmt_int(entreg_uniq)}</div>
            <div class="neo-subline">&nbsp;</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="neo-section">Aderência (REGULAR)</div>', unsafe_allow_html=True)

    incons_txt = "⚠️ Vagas inconsistentes." if vagas_incons else ""

    st.markdown(
        f"""
        <div class="neo-grid-2">
          <div class="neo-card">
            <div class="neo-value">{ader_pct:.1f}%</div>
            <div class="neo-subline">Regulares: {_fmt_int(ader_reg)} / Vagas: {_fmt_int(ader_vagas)}</div>
            <div class="neo-subline" style="color:rgba(255,176,32,.95)">{incons_txt}</div>
          </div>

          <div class="neo-card">
            <div class="neo-label">Regulares: {_fmt_int(ader_reg)} / Vagas: {_fmt_int(ader_vagas)}</div>
            <div class="neo-progress-wrap">
              <div class="neo-progress">
                <div style="width:{pct_bar:.1f}%;"></div>
              </div>
              <div class="neo-scale">
                <span>0%</span><span>50%</span><span>100%</span>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="neo-section">Supply & Ranking</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Supply Hours (SH)</div>
              <div class="neo-value">{_fmt_hm_from_seconds(seg_total)}</div>
              <div class="neo-subline">Total no mês ({mes_txt})</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        medals = ["🥇", "🥈", "🥉"]

        if not top3:
            rows = "<div class='neo-subline'>Sem dados suficientes.</div>"
        else:
            rows = ""
            for i, (nome, seg) in enumerate(top3[:3]):
                nome_safe = html.escape(str(nome))
                horas_txt = _fmt_hm_from_seconds(seg)

                # inline styles pra ellipsis funcionar melhor em flex (mesmo se o CSS não ajudar)
                rows += f"""
                  <div class="toprow" style="display:flex;align-items:center;gap:.5rem;">
                    <div class="name" style="min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                      {medals[i]}&nbsp;{nome_safe}
                    </div>
                    <div class="hours" style="flex:0 0 auto;text-align:right;">{horas_txt}</div>
                  </div>
                """

        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Top 3 entregadores (horas)</div>
              <div class="neo-subline">Período: {mes_txt}</div>
              {rows}
            </div>
            """,
            unsafe_allow_html=True
        )
