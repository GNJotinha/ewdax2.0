# home.py
# Home — Supply em card único + Ranking em Streamlit puro (fora de cards)
# ✅ Supply agora com infos extras + comparação vs mês anterior
# ✅ Ranking mantido IGUAL ao original

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


def _fmt_h(h):
    try:
        return f"{float(h):.1f}h".replace(".", ",")
    except Exception:
        return "—"


def _fmt_delta_h(dh):
    if dh is None:
        return "—"
    sign = "+" if dh > 0 else ""
    return f"{sign}{dh:.1f}h".replace(".", ",")


def _fmt_delta_pct(dp):
    if dp is None:
        return "—"
    sign = "+" if dp > 0 else ""
    return f"{sign}{dp:.1f}%".replace(".", ",")


def _arrow(dh):
    if dh is None:
        return "⚪"
    if abs(dh) < 1e-9:
        return "⚪"
    return "🟢⬆" if dh > 0 else "🔴⬇"


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

    # UTR média
    utr_medias = 0.0
    try:
        base_home = utr_por_entregador_turno(df, mes_atual, ano_atual)
        if not base_home.empty:
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
    # COMPARAÇÃO SH vs MÊS ANTERIOR
    # =========================
    if mes_atual == 1:
        mes_prev, ano_prev = 12, ano_atual - 1
    else:
        mes_prev, ano_prev = mes_atual - 1, ano_atual

    df_prev = pd.DataFrame()
    if {"mes", "ano"}.issubset(df.columns):
        df_prev = df[(df["mes"] == mes_prev) & (df["ano"] == ano_prev)].copy()
    elif "mes_ano" in df.columns:
        alvo = pd.Timestamp(year=ano_prev, month=mes_prev, day=1)
        df_prev = df[pd.to_datetime(df["mes_ano"], errors="coerce") == alvo].copy()

    seg_prev = pd.to_numeric(df_prev.get("segundos_abs", 0), errors="coerce").fillna(0).sum() if not df_prev.empty else 0
    horas_prev = float(seg_prev / 3600.0) if seg_prev > 0 else 0.0

    dh = horas_total - horas_prev
    dp = (dh / horas_prev * 100.0) if horas_prev > 0 else None
    prev_txt = f"{mes_prev:02d}/{ano_prev}"
    arrow = _arrow(dh)

    # =========================
    # UI (original)
    # =========================
    st.markdown('<div class="neo-shell">', unsafe_allow_html=True)

    # Topbar
    hL, hR = st.columns([4, 1])
    with hL:
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
    # SUPPLY (card único, agora maior com infos + comparação)
    # =========================
    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="neo-section">Supply</div>', unsafe_allow_html=True)

    horas_media_entregador = (horas_total / entreg_uniq) if entreg_uniq > 0 else 0.0
    horas_media_dia = (horas_total / df_mes[data_col].nunique()) if (data_col and data_col in df_mes.columns) else 0.0

    st.markdown(
        f"""
        <div class="neo-card">
          <div class="neo-label">Supply Hours (SH)</div>

          <div class="neo-value">{horas_total:.1f}h</div>
          <div class="neo-subline">Total no mês ({mes_txt})</div>

          <div style="margin-top:14px; line-height:1.6;">
            <div class="neo-subline">• Entregadores ativos: <b>{entreg_uniq}</b></div>
            <div class="neo-subline">• Média por entregador: <b>{horas_media_entregador:.1f}h</b></div>
            <div class="neo-subline">• Média por dia: <b>{horas_media_dia:.1f}h</b></div>
            <div class="neo-subline">• UTR absoluta: <b>{utr_abs:.2f}</b></div>
          </div>

          <div style="margin-top:14px; line-height:1.6;">
            <div class="neo-subline"><b>Comparação vs mês anterior</b></div>
            <div class="neo-subline">• SH {prev_txt}: <b>{_fmt_h(horas_prev)}</b></div>
            <div class="neo-subline">• Δ: <b>{_fmt_delta_h(dh)}</b> ({_fmt_delta_pct(dp)}) {arrow}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # =========================
    # RANKING (MANTIDO IGUAL AO ORIGINAL)
    # =========================
    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)

    st.subheader("🏆 Top 3 SH")

    if not top3:
        st.info("Sem dados suficientes.")
    else:
        medals = ["🥇", "🥈", "🥉"]
        for i, (nome, horas) in enumerate(top3):
            a, b = st.columns([6, 1])
            with a:
                st.markdown(f"**{medals[i]} {nome}**")
            with b:
                st.markdown(f"**{horas:.1f}h**")

    st.markdown("</div>", unsafe_allow_html=True)
