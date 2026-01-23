# views/home.py
# Topbar sem cápsula + Top3 alinhado DENTRO do card (HTML correto)

import html
import streamlit as st
import pandas as pd
from relatorios import utr_por_entregador_turno
from utils import calcular_aderencia


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


def render(df: pd.DataFrame, USUARIOS: dict):
    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    # =========================
    # MÊS ATUAL
    # =========================
    hoje = pd.Timestamp.today()
    mes_atual, ano_atual = int(hoje.month), int(hoje.year)

    if ("mes" in df.columns) and ("ano" in df.columns):
        df_mes = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)].copy()
    else:
        if "mes_ano" in df.columns:
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

    # data mais recente (topo)
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

    entreg_uniq = 0
    if "pessoa_entregadora" in df_mes.columns:
        entreg_uniq = int(df_mes["pessoa_entregadora"].dropna().nunique())

    acc_pct = (aceitas / ofertadas * 100.0) if ofertadas > 0 else 0.0
    rej_pct = (rejeitadas / ofertadas * 100.0) if ofertadas > 0 else 0.0

    seg_total = pd.to_numeric(df_mes.get("segundos_abs", 0), errors="coerce").fillna(0).sum()
    horas_total = float(seg_total / 3600.0) if seg_total > 0 else 0.0
    utr_abs = (ofertadas / horas_total) if horas_total > 0 else 0.0

    # UTR média
    utr_medias = 0.0
    try:
        base_home = utr_por_entregador_turno(df, mes_atual, ano_atual)
        if not base_home.empty and "supply_hours" in base_home.columns and "corridas_ofertadas" in base_home.columns:
            base_pos = base_home[base_home["supply_hours"] > 0].copy()
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

    if (not df_mes.empty) and vagas_col and tag_col and data_col and ("segundos_abs" in df_mes.columns):
        group_cols = (data_col, turno_col) if turno_col else (data_col,)
        try:
            base_ap = calcular_aderencia(
                df_mes,
                group_cols=group_cols,
                vagas_col=vagas_col,
                tag_col=tag_col,
                tag_regular="REGULAR",
            )
            ader_reg = int(pd.to_numeric(base_ap.get("regulares_atuaram", 0), errors="coerce").fillna(0).sum())
            ader_vagas = float(pd.to_numeric(base_ap.get("vagas", 0), errors="coerce").fillna(0).sum())
            if ader_vagas > 0:
                ader_pct = round((ader_reg / ader_vagas) * 100.0, 1)
            vagas_incons = bool(base_ap.get("vagas_inconsistente", False).fillna(False).any())
        except Exception:
            pass

    pct_bar = max(0.0, min(float(ader_pct), 100.0))

    # =========================
    # SUPPLY HOURS + TOP 3 POR HORAS
    # =========================
    sh_total = horas_total

    top3 = []
    if ("pessoa_entregadora" in df_mes.columns) and ("segundos_abs" in df_mes.columns):
        tmp_h = df_mes[["pessoa_entregadora", "segundos_abs"]].copy()
        tmp_h["segundos_abs"] = pd.to_numeric(tmp_h["segundos_abs"], errors="coerce").fillna(0)

        top = (
            tmp_h.groupby("pessoa_entregadora", as_index=False)["segundos_abs"]
            .sum()
            .sort_values("segundos_abs", ascending=False)
            .head(3)
        )

        for _, r in top.iterrows():
            nome = str(r["pessoa_entregadora"])
            horas = float(r["segundos_abs"]) / 3600.0
            top3.append((nome, horas))

    # =========================
    # UI
    # =========================
    st.markdown('<div class="neo-shell">', unsafe_allow_html=True)

    topL, topR = st.columns([4, 1])
    with topL:
        st.markdown(
            f"""
            <div class="neo-topbar">
              <div>
                <div class="neo-title">📁&nbsp;Painel de Entregadores</div>
                <div class="neo-sub">Dados atualizados • {data_str}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with topR:
        if st.button("Atualizar dados", use_container_width=True, key="btn_refresh_home"):
            st.session_state.force_refresh = True
            st.session_state.just_refreshed = True
            st.cache_data.clear()
            st.rerun()

    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
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
    st.markdown(
        '<div class="neo-section">Aderência <span style="font-weight:700;color:rgba(232,237,246,.70)">(REGULAR)</span></div>',
        unsafe_allow_html=True
    )

    incons_html = (
        "<div class='neo-subline' style='color:rgba(255,176,32,.95)'>⚠️ Vagas inconsistentes.</div>"
        if vagas_incons else ""
    )

    st.markdown(
        f"""
        <div class="neo-grid-2">
          <div class="neo-card">
            <div class="neo-value">{ader_pct:.1f}%</div>
            <div class="neo-subline">Regulares: {_fmt_int(ader_reg)} / Vagas: {_fmt_int(ader_vagas)}</div>
            {incons_html}
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
    # Supply & Ranking
    # =========================
    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="neo-section">Supply & Ranking</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 2])

    with c1:
        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Supply Hours (SH)</div>
              <div class="neo-value">{sh_total:.1f}h</div>
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
            for i, (nome, horas) in enumerate(top3[:3]):
                m = medals[i]
                nome_safe = html.escape(str(nome))
                rows += f"""
                  <div class="toprow">
                    <div class="name">{m}&nbsp;{nome_safe}</div>
                    <div class="hours">{horas:.1f}h</div>
                  </div>
                """

        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Top 3 entregadores (horas)</div>
              {rows}
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("</div>", unsafe_allow_html=True)
