import streamlit as st
import pandas as pd
from utils import calcular_aderencia
from relatorios import utr_por_entregador_turno

def _fmt_int(x):
    try:
        return f"{int(x):,}".replace(",", ".")
    except Exception:
        return "0"

def render(df: pd.DataFrame, _USUARIOS: dict):

    # =========================
    # HEADER
    # =========================
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown("## 📋 Painel de Entregadores")
        st.caption("Dados mais recentes")

    with c2:
        if st.button("🔄 Atualizar dados", use_container_width=True):
            st.session_state.force_refresh = True
            st.session_state.just_refreshed = True
            st.rerun()

    st.divider()

    # =========================
    # BASE MÊS ATUAL
    # =========================
    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    ultimo_mes = df["mes_ano"].max()
    base = df[df["mes_ano"] == ultimo_mes].copy()

    # =========================
    # KPIs
    # =========================
    ofertadas = int(base["numero_de_corridas_ofertadas"].sum())
    aceitas   = int(base["numero_de_corridas_aceitas"].sum())
    rejeitadas= int(base["numero_de_corridas_rejeitadas"].sum())

    ativos = base.loc[
        (base["numero_de_corridas_ofertadas"]
        + base["numero_de_corridas_aceitas"]
        + base["numero_de_corridas_completadas"]
        + base["segundos_abs"]) > 0,
        "pessoa_entregadora"
    ].nunique()

    sh = base["segundos_abs"].sum() / 3600 if base["segundos_abs"].sum() > 0 else 0
    utr_abs = ofertadas / sh if sh > 0 else 0

    utr_base = utr_por_entregador_turno(base)
    utr_med = (
        (utr_base["corridas_ofertadas"] / utr_base["supply_hours"])
        .replace([float("inf"), -float("inf")], 0)
        .dropna()
        .mean()
        if not utr_base.empty else 0
    )

    # =========================
    # CARDS
    # =========================
    cols = st.columns(4)

    def card(col, titulo, valor, sub=None):
        with col:
            st.markdown(
                f"""
                <div class="card">
                    <div class="card-title">{titulo}</div>
                    <div class="card-value">{valor}</div>
                    {f'<div class="card-sub">{sub}</div>' if sub else ''}
                </div>
                """,
                unsafe_allow_html=True
            )

    card(cols[0], "Ofertadas – UTR", _fmt_int(ofertadas), f"Absoluto {utr_abs:.2f} • Média {utr_med:.2f}")
    card(cols[1], "Aceitas", _fmt_int(aceitas))
    card(cols[2], "Rejeitadas", _fmt_int(rejeitadas))
    card(cols[3], "Entregadores ativos", _fmt_int(ativos))

    st.divider()

    # =========================
    # ADERÊNCIA
    # =========================
    if (
        "numero_minimo_de_entregadores_regulares_na_escala" in base.columns
        and "tag" in base.columns
    ):
        try:
            ap = calcular_aderencia(base)
            reg = int(ap["regulares_atuaram"].sum())
            vagas = int(ap["vagas"].sum())
            ader = (reg / vagas * 100) if vagas > 0 else 0

            st.markdown(
                f"""
                <div class="card" style="max-width:420px">
                    <div class="card-title">Aderência (REGULAR)</div>
                    <div class="card-value">{ader:.1f}%</div>
                    <div class="card-sub">Regulares: {reg} / Vagas: {vagas}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
        except Exception:
            pass
