import streamlit as st
import pandas as pd
from utils import calcular_aderencia
from relatorios import utr_por_entregador_turno


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


def render(df: pd.DataFrame, _USUARIOS: dict):

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    # mês atual
    ultimo_mes = df["mes_ano"].max()
    base = df[df["mes_ano"] == ultimo_mes].copy()
    mes_txt = pd.to_datetime(ultimo_mes).strftime("%m/%Y")

    # data mais recente do mês (pra mostrar no topo)
    data_str = None
    for c in ("data_do_periodo", "data", "data_do_periodo_de_referencia"):
        if c in base.columns:
            dt = pd.to_datetime(base[c], errors="coerce").max()
            if pd.notna(dt):
                data_str = pd.to_datetime(dt).strftime("%d/%m/%Y")
                break

    # KPIs
    ofertadas = float(pd.to_numeric(base.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
    aceitas = float(pd.to_numeric(base.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
    rejeitadas = float(pd.to_numeric(base.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum())

    # % aceitação / rejeição (sobre ofertadas)
    acc_pct = (aceitas / ofertadas * 100.0) if ofertadas > 0 else 0.0
    rej_pct = (rejeitadas / ofertadas * 100.0) if ofertadas > 0 else 0.0

    # ativos
    m_act = (
        pd.to_numeric(base.get("segundos_abs", 0), errors="coerce").fillna(0)
        + pd.to_numeric(base.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
        + pd.to_numeric(base.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
        + pd.to_numeric(base.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)
    ) > 0
    ativos = int(base.loc[m_act, "pessoa_entregadora"].dropna().nunique()) if "pessoa_entregadora" in base.columns else 0

    # UTR abs + média
    seg = float(pd.to_numeric(base.get("segundos_abs", 0), errors="coerce").fillna(0).sum())
    horas = seg / 3600.0 if seg > 0 else 0.0
    utr_abs = (ofertadas / horas) if horas > 0 else 0.0

    utr_base = utr_por_entregador_turno(base)
    if not utr_base.empty and "supply_hours" in utr_base.columns and "corridas_ofertadas" in utr_base.columns:
        tmp = utr_base.copy()
        tmp["supply_hours"] = pd.to_numeric(tmp["supply_hours"], errors="coerce").fillna(0)
        tmp["corridas_ofertadas"] = pd.to_numeric(tmp["corridas_ofertadas"], errors="coerce").fillna(0)
        tmp = tmp[tmp["supply_hours"] > 0]
        utr_med = float((tmp["corridas_ofertadas"] / tmp["supply_hours"]).mean()) if not tmp.empty else 0.0
    else:
        utr_med = 0.0

    # Aderência
    ader = None
    reg = vagas = 0
    if ("numero_minimo_de_entregadores_regulares_na_escala" in base.columns) and ("tag" in base.columns):
        try:
            ap = calcular_aderencia(base)
            reg = int(ap["regulares_atuaram"].sum())
            vagas = float(ap["vagas"].sum())
            ader = (reg / vagas * 100.0) if vagas > 0 else 0.0
        except Exception:
            ader = None

    pct = max(0.0, min(float(ader) if ader is not None else 0.0, 100.0))

    # ==========================================================
    # SHELL + TOPBAR
    # ==========================================================
    st.markdown('<div class="neo-shell">', unsafe_allow_html=True)

    topL, topR = st.columns([4, 1])
    with topL:
        st.markdown(
            f"""
            <div class="neo-topbar">
              <div>
                <div class="neo-title">🗂️&nbsp;Painel de Entregadores</div>
                <div class="neo-sub">Dados atualizados • {data_str if data_str else "mês atual"}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with topR:
        if st.button("Atualizar dados", use_container_width=True):
            st.session_state.force_refresh = True
            st.session_state.just_refreshed = True
            st.rerun()

    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)

    # ==========================================================
    # RESUMO DO MÊS
    # ==========================================================
    st.markdown(f'<div class="neo-section">Resumo do mês ({mes_txt})</div>', unsafe_allow_html=True)

    aceitas_label = f"{_fmt_int(aceitas)} ({_fmt_pct(acc_pct, 1)})"
    rejeitadas_label = f"{_fmt_int(rejeitadas)} ({_fmt_pct(rej_pct, 1)})"

    st.markdown(
        f"""
        <div class="neo-grid-4">
          <div class="neo-card">
            <div class="neo-label">Ofertadas – UTR</div>
            <div class="neo-value">{_fmt_int(ofertadas)}</div>
            <div class="neo-subline">Absoluto {utr_abs:.2f} • Média {utr_med:.2f}</div>
          </div>

          <div class="neo-card neo-success">
            <div class="neo-label">Aceitas</div>
            <div class="neo-value">{aceitas_label}</div>
            <div class="neo-subline">&nbsp;</div>
          </div>

          <div class="neo-card neo-danger">
            <div class="neo-label">Rejeitadas</div>
            <div class="neo-value">{rejeitadas_label}</div>
            <div class="neo-subline">&nbsp;</div>
          </div>

          <div class="neo-card">
            <div class="neo-label">Entregadores ativos</div>
            <div class="neo-value">{_fmt_int(ativos)}</div>
            <div class="neo-subline">&nbsp;</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ==========================================================
    # ADERÊNCIA
    # ==========================================================
    if ader is not None:
        st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="neo-section">Aderência <span style="font-weight:700;color:rgba(232,237,246,.70)">(REGULAR)</span></div>',
            unsafe_allow_html=True
        )

        st.markdown(
            f"""
            <div class="neo-grid-2">
              <div class="neo-card">
                <div class="neo-value">{ader:.1f}%</div>
                <div class="neo-subline">Regulares: {_fmt_int(reg)} / Vagas: {_fmt_int(vagas)}</div>
              </div>

              <div class="neo-card">
                <div class="neo-label">Regulares: {_fmt_int(reg)} / Vagas: {_fmt_int(vagas)}</div>

                <div class="neo-progress-wrap">
                  <div class="neo-progress">
                    <div style="width:{pct:.1f}%;"></div>
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

    st.markdown("</div>", unsafe_allow_html=True)
