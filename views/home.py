import streamlit as st
import pandas as pd


def _pick_col(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    return None


def _last_date_str(df: pd.DataFrame) -> str:
    """Tenta descobrir o último dia registrado na base."""
    if df is None or df.empty:
        return ""

    cols = list(df.columns)
    cand = [
        "data_do_periodo",
        "data",
        "Data",
        "DATA",
        "dt",
        "timestamp",
        "ts",
    ]
    col = _pick_col(cols, cand)
    if not col:
        return ""

    try:
        dtmax = pd.to_datetime(df[col], errors="coerce").max()
        if pd.notna(dtmax):
            return dtmax.strftime("%d/%m/%Y")
    except Exception:
        pass
    return ""


def _logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def render(df: pd.DataFrame, _USUARIOS: dict):
    last_day = _last_date_str(df)
    fonte = getattr(df, "attrs", {}).get("fonte", "") if df is not None else ""

    hL, hR = st.columns([4, 1.6], vertical_alignment="center")
    with hL:
        st.markdown(
            f"""
            <div style="margin-top:6px;">
              <div style="font-size:3.0rem; font-weight:950; line-height:1.05;">Painel de Entregadores</div>
              <div style="margin-top:10px; color: rgba(232,237,246,.70); font-weight:700;">
                Último dia na base: <b>{last_day or '—'}</b>{(' • ' + fonte) if fonte else ''}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with hR:
        b1, b2 = st.columns([1, 1])
        with b1:
            if st.button("👤 Perfil", key="home_profile", type="secondary"):
                st.session_state.module = "views.perfil"
                st.session_state.open_cat = None
                st.rerun()
        with b2:
            if st.button("🚪 Sair", key="home_logout", type="secondary"):
                _logout()
                st.rerun()

    st.markdown("<div class='neo-divider'></div>", unsafe_allow_html=True)

    if st.session_state.get("is_admin"):
        st.markdown("""<div class="neo-section">Admin</div>""", unsafe_allow_html=True)
        a1, a2 = st.columns([1, 1])
        with a1:
            if st.button("🛠️ Usuários", key="home_admin_users"):
                st.session_state.module = "views.admin_usuarios"
                st.session_state.open_cat = None
                st.rerun()
        with a2:
            if st.button("🧾 Auditoria", key="home_admin_audit"):
                st.session_state.module = "views.auditoria"
                st.session_state.open_cat = None
                st.rerun()
