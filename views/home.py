# views/home.py
# Home — topo sem "bolha" (remove neo-shell) + SH e Ranking com mesma altura
# Ranking renderizado em 1 bloco HTML pra não vazar no DOM do Streamlit

import streamlit as st
import pandas as pd
from relatorios import utr_por_entregador_turno
from utils import calcular_aderencia


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# Render
# ---------------------------------------------------------
def render(df: pd.DataFrame, USUARIOS: dict):
    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    # =========================
    # MÊS ATUAL
    # =========================
    hoje = pd.Timestamp.today()
    mes_atual, ano_atual = int(hoje.month), int(hoje.year)

    if {"mes", "ano"}.issubset(df.columns):
        df_mes = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)].copy()
    elif "mes_ano" in df.columns:
        ultimo_mes = df["mes_ano"].max()
        df_mes = df[df["mes_ano"] == ultimo_mes].copy()
        try:
            mes_atual = int(pd.to_datetime(ultimo_mes).month)
            ano_atual = int(pd.to_datetime(ultimo_mes).year)
        except Exception:
            pass
    else:
        df_mes = df.copy()

    mes_txt = f"{mes_atual:02d}/{ano_atual}"

    # data mais recente
    data_col = _pick_col(df_mes.columns, ["data", "data_do_periodo", "data_do_periodo_de_referencia"])
    data_str = "—"
    if data_col:
        dtmax = pd.to_datetime(df_mes[data_col], errors="coerce").max()
        if pd.notna(dtmax):
            data_str = pd.to_datetime(dtmax).strftime("%d/%m/%Y")

    # =========================
    # KPIs
    # =========================
    ofertadas = int(pd.to_numeric(df_mes.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
    aceitas = int(pd.to_numeric(df_mes.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
    rejeitadas = int(pd.to_numeric(df_mes.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum())

    entreg_uniq = int(df_mes["pessoa_entregadora"].dropna().nunique()) if "pessoa_entregadora" in df_mes.columns else 0

    acc_pct = (aceitas / ofertadas * 100.0) if ofertadas else 0.0
    rej_pct = (rejeitadas / ofertadas * 100.0) if ofertadas else 0.0

    seg_total = pd.to_numeric(df_mes.get("segundos_abs", 0), errors="coerce").fillna(0).sum()
    horas_total = float(seg_total / 3600.0) if seg_total > 0 else 0.0
    utr_abs = (ofertadas / horas_total) if horas_total > 0 else 0.0

    # UTR média (mantém consistência com utr_por_entregador_turno)
    utr_medias = 0.0
    try:
        base_home = utr_por_entregador_turno(df, mes_atual, ano_atual)
        if base_home is not None and not base_home.empty:
            base_pos = base_home[base_home["supply_hours"] > 0]
            if not base_pos.empty:
                utr_medias = float((base_pos["corridas_ofertadas"] / base_pos["supply_hours"]).mean())
    except Exception:
        pass

    # =========================
    # ADERÊNCIA
    # =========================
    ader_pct = 0.0
    ader_reg = 0
    ader_vagas = 0.0
    vagas_incons = False

    vagas_col = _pick_col(df_mes.columns, ["numero_minimo_de_entregadores_regulares_na_escala", "vagas"])
    tag_col = _pick_col(df_mes.columns, ["tag"])
    turno_col = _pick_col(df_mes.columns, ["turno", "tipo_turno", "periodo"])

    if vagas_col and tag_col and data_col and "segundos_abs" in df_mes.columns:
        group_cols = (data_col, turno_col) if turno_col else (data_col,)
        try:
            base_ap = calcular_aderencia(
                df_mes,
                group_cols=group_cols,
                vagas_col=vagas_col,
                tag_col=tag_col,
                tag_regular="REGULAR",
            )
            ader_reg = int(base_ap["regulares_atuaram"].sum())
            ader_vagas = float(base_ap["vagas"].sum())
            ader_pct = round((ader_reg / ader_vagas) * 100.0, 1) if ader_vagas else 0.0
            vagas_incons = bool(base_ap["vagas_inconsistente"].any())
        except Exception:
            pass

    pct_bar = max(0.0, min(float(ader_pct), 100.0))

    # =========================
    # TOP 3 POR HORAS
    # =========================
    top3 = []
    if {"pessoa_entregadora", "segundos_abs"}.issubset(df_mes.columns):
        tmp = df_mes[["pessoa_entregadora", "segundos_abs"]].copy()
        tmp["segundos_abs"] = pd.to_numeric(tmp["segundos_abs"], errors="coerce").fillna(0)

        top = (
            tmp.groupby("pessoa_entregadora", as_index=False)["segundos_abs"]
            .sum()
            .sort_values("segundos_abs", ascending=False)
            .head(3)
        )

        for _, r in top.iterrows():
            top3.append((str(r["pessoa_entregadora"]), float(r["segundos_abs"]) / 3600.0))

    # =========================
    # UI (SEM neo-shell -> sem "bolha" gigante no topo)
    # =========================

    # ---------------------------------------------------------
    # TOPO (sem card) — título + botão
    # ---------------------------------------------------------
    hL, hR = st.columns([6, 2])

    with hL:
        st.markdown(
            f"""
            <div style="padding: 6px 2px 6px 2px;">
              <div style="display:flex; align-items:center; gap:10px;">
                <div style="font-size: 1.95rem; font-weight: 950; letter-spacing: .2px;">
                  📁 Painel de Entregadores
                </div>
              </div>
              <div style="margin-top:6px; font-size: .95rem; color: rgba(232,237,246,.70); font-weight: 650;">
                Dados atualizados • {data_str}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with hR:
        if st.button("Atualizar dados", use_container_width=True):
            st.session_state.force_refresh = True
            st.session_state.just_refreshed = True
            st.cache_data.clear()
            st.rerun()

    # =========================
    # RESUMO
    # =========================
    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="neo-section">Resumo do mês ({mes_txt})</div>', unsafe_allow_html=True)

    aceitas_html = f"{_fmt_int(aceitas)}<span class='pct'>({_fmt_pct(acc_pct)})</span>"
    rejeitadas_html = f"{_fmt_int(rejeitadas)}<span class='pct'>({_fmt_pct(rej_pct)})</span>"

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
          </div>

          <div class="neo-card neo-danger">
            <div class="neo-label">Rejeitadas</div>
            <div class="neo-value">{rejeitadas_html}</div>
          </div>

          <div class="neo-card">
            <div class="neo-label">Entregadores ativos</div>
            <div class="neo-value">{_fmt_int(entreg_uniq)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # =========================
    # ADERÊNCIA
    # =========================
    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="neo-section">Aderência (REGULAR)</div>', unsafe_allow_html=True)

    incons_txt = "⚠️ Vagas inconsistentes." if vagas_incons else ""

    st.markdown(
        f"""
        <div class="neo-grid-2">
          <div class="neo-card">
            <div class="neo-value">{ader_pct:.1f}%</div>
            <div class="neo-subline" style="color:#ffb020">{incons_txt}</div>
            <div class="neo-subline">Regulares: {_fmt_int(ader_reg)} / Vagas: {_fmt_int(ader_vagas)}</div>
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

    # =========================
    # SUPPLY & RANKING (mesma altura, ranking não vaza)
    # =========================
    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="neo-section">Supply & Ranking</div>', unsafe_allow_html=True)

    card_min_h = 220  # ajusta aqui se quiser mais alto/baixo

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(
            f"""
            <div class="neo-card" style="min-height:{card_min_h}px;">
              <div class="neo-label">Supply Hours (SH)</div>
              <div class="neo-value">{horas_total:.1f}h</div>
              <div class="neo-subline">Total no mês ({mes_txt})</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        if not top3:
            rows_html = "<div class='neo-subline' style='margin-top:12px;'>Sem dados suficientes.</div>"
        else:
            medals = ["🥇", "🥈", "🥉"]
            rows = []
            for i, (nome, horas) in enumerate(top3):
                rows.append(
                    f"""
                    <div class="rank-row">
                      <div class="rank-name">{medals[i]}&nbsp;{nome}</div>
                      <div class="rank-hours">{horas:.1f}h</div>
                    </div>
                    """
                )
            rows_html = "\n".join(rows)

        ranking_card_html = f"""
        <div class="neo-card" style="min-height:{card_min_h}px;">
          <div class="neo-label">🏆 Top 3 entregadores (horas)</div>
          <div class="neo-subline">Base: mês {mes_txt}</div>
          {rows_html}
        </div>
        """

        st.markdown(ranking_card_html, unsafe_allow_html=True)
