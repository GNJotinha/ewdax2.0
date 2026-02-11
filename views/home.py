import streamlit as st
import pandas as pd


def _pick_col(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    return None


def _last_date_str(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""

    cols = list(df.columns)
    cand = ["data_do_periodo", "data", "Data", "DATA", "dt", "timestamp", "ts"]
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

    # HERO
    left, right = st.columns([4.2, 1.4], vertical_alignment="center")

    with left:
        st.markdown(
            f"""
            <div class="home-hero">
              <div class="home-title">Painel de Entregadores</div>
              <div class="home-sub">
                Último dia na base: <b>{last_day or "—"}</b>
                {f'<span class="pill">📦 {fonte}</span>' if fonte else ''}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        # cola os botões (colunas + espaçador)
        r1, r2, _sp = st.columns([1, 1, 2])
        with r1:
            if st.button("👤 Perfil", key="home_profile", type="secondary"):
                st.session_state.module = "views.perfil"
                st.session_state.open_cat = None
                st.rerun()
        with r2:
            if st.button("🚪 Sair", key="home_logout", type="secondary"):
                _logout()
                st.rerun()

    st.markdown("<div class='neo-divider'></div>", unsafe_allow_html=True)

    # ADMIN tiles (só admin)
    if st.session_state.get("is_admin"):
        st.markdown("""<div class="neo-section">Admin</div>""", unsafe_allow_html=True)

        # deixa os dois tiles juntos na esquerda
        c1, c2, _sp = st.columns([1, 1, 2.5], vertical_alignment="top")

        with c1:
            st.markdown(
                """
                <div class="action-tile">
                  <div class="action-title">🛠️ Usuários</div>
                  <div class="action-desc">Criar, editar, resetar senha e permissões.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Abrir Usuários", key="home_admin_users", type="primary"):
                st.session_state.module = "views.admin_usuarios"
                st.session_state.open_cat = None
                st.rerun()

        with c2:
            st.markdown(
                """
                <div class="action-tile action-tile-blue">
                  <div class="action-title">🧾 Auditoria</div>
                  <div class="action-desc">Logs do sistema (import, senha, criação, etc).</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Abrir Auditoria", key="home_admin_audit", type="primary"):
                st.session_state.module = "views.auditoria"
                st.session_state.open_cat = None
                st.rerun()

        st.caption("A home vai ficar enxuta mesmo. Quando você for liberando features, a gente coloca mais tiles aqui.")
