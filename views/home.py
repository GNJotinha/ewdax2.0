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
    col = _pick_col(list(df.columns), ["data_do_periodo", "data", "Data", "DATA", "dt", "timestamp", "ts"])
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


def _goto(module: str, cat: str | None = None):
    st.session_state.module = module
    st.session_state.open_cat = cat
    st.rerun()


def render(df: pd.DataFrame, _USUARIOS: dict):
    last_day = _last_date_str(df)
    fonte = getattr(df, "attrs", {}).get("fonte", "") if df is not None else ""

    # centraliza o conteúdo pra parecer "home"
    _, mid, _ = st.columns([1, 2.6, 1], vertical_alignment="top")
    with mid:
        # topo
        L, R = st.columns([3.4, 1.2], vertical_alignment="center")
        with L:
            st.markdown(
                f"""
                <div class="home-wrap">
                  <div class="home-title">Painel de Entregadores</div>
                  <div class="home-meta">
                    Último dia na base: <b>{last_day or "—"}</b>
                    {f'<span class="home-chip">{fonte}</span>' if fonte else ""}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with R:
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Perfil", type="secondary", use_container_width=True, key="home_profile"):
                    _goto("views.perfil", None)
            with b2:
                if st.button("Sair", type="secondary", use_container_width=True, key="home_logout"):
                    _logout()
                    st.rerun()

        st.markdown("<div class='neo-divider'></div>", unsafe_allow_html=True)

        # Corpo: 2 colunas (Navegação / Admin)
        left, right = st.columns([2.2, 1.2], vertical_alignment="top")

        menu = st.session_state.get("MENU", {})

        with left:
            st.markdown("""<div class="neo-section">Navegação</div>""", unsafe_allow_html=True)

            # launcher por seção (sem dropdown)
            for cat, opts in menu.items():
                with st.expander(cat, expanded=(cat == "Desempenho do Entregador")):
                    # botões em grid 2 colunas pra ficar com cara de painel
                    keys = list(opts.keys())
                    cols = st.columns(2)
                    for i, label in enumerate(keys):
                        c = cols[i % 2]
                        with c:
                            if st.button(label, use_container_width=True, key=f"home_nav_{cat}_{label}"):
                                _goto(opts[label], cat)

        with right:
            st.markdown("""<div class="neo-section">Admin</div>""", unsafe_allow_html=True)

            if st.session_state.get("is_admin"):
                if st.button("Usuários", use_container_width=True, key="home_admin_users"):
                    _goto("views.admin_usuarios", None)
                if st.button("Auditoria", use_container_width=True, key="home_admin_audit"):
                    _goto("views.auditoria", None)
            else:
                st.caption("Sem acesso admin.")

            st.markdown("<div class='neo-divider'></div>", unsafe_allow_html=True)
            st.markdown("""<div class="neo-section">Conta</div>""", unsafe_allow_html=True)
            st.caption(f"Login: {st.session_state.get('usuario','-')}")
            st.caption(f"Departamento: {st.session_state.get('department','-')}")
