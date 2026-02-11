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
    col = _pick_col(cols, ["data_do_periodo", "data", "Data", "DATA", "dt", "timestamp", "ts"])
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

    # centraliza o conteúdo pra não ficar tudo espalhado
    _, mid, _ = st.columns([1, 2.3, 1], vertical_alignment="top")

    with mid:
        topL, topR = st.columns([3.2, 1.2], vertical_alignment="center")

        with topL:
            st.markdown(
                f"""
                <div class="home-head">
                  <div class="home-title">Painel de Entregadores</div>
                  <div class="home-meta">
                    Último dia na base: <b>{last_day or "—"}</b>
                    {f'<span class="home-chip">{fonte}</span>' if fonte else ""}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with topR:
            a, b = st.columns(2)
            with a:
                if st.button("Perfil", type="secondary", use_container_width=True, key="home_profile"):
                    st.session_state.module = "views.perfil"
                    st.session_state.open_cat = None
                    st.rerun()
            with b:
                if st.button("Sair", type="secondary", use_container_width=True, key="home_logout"):
                    _logout()
                    st.rerun()

        st.markdown("<div class='neo-divider'></div>", unsafe_allow_html=True)

        st.markdown("""<div class="neo-section">Acessos rápidos</div>""", unsafe_allow_html=True)

        menu = st.session_state.get("MENU", {})
        options = []
        map_opt = {}

        for cat, opts in menu.items():
            for label, module in opts.items():
                key = f"{cat} • {label}"
                options.append(key)
                map_opt[key] = (module, cat)

        # admin também entra no "Ir para…" (mas sem ficar poluindo sidebar)
        if st.session_state.get("is_admin"):
            key_u = "Admin • Usuários"
            key_a = "Admin • Auditoria"
            options.extend([key_u, key_a])
            map_opt[key_u] = ("views.admin_usuarios", None)
            map_opt[key_a] = ("views.auditoria", None)

        # ir para
        row1, row2 = st.columns([3.2, 1])
        with row1:
            choice = st.selectbox("Ir para", options=options, label_visibility="collapsed")
        with row2:
            if st.button("Abrir", use_container_width=True, key="home_go"):
                module, cat = map_opt[choice]
                st.session_state.module = module
                st.session_state.open_cat = cat
                st.rerun()

        # admin (botões simples, sem card)
        if st.session_state.get("is_admin"):
            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
            st.markdown("""<div class="neo-section">Admin</div>""", unsafe_allow_html=True)

            c1, c2, _sp = st.columns([1, 1, 2.6])
            with c1:
                if st.button("Usuários", use_container_width=True, key="home_admin_users"):
                    st.session_state.module = "views.admin_usuarios"
                    st.session_state.open_cat = None
                    st.rerun()
            with c2:
                if st.button("Auditoria", use_container_width=True, key="home_admin_audit"):
                    st.session_state.module = "views.auditoria"
                    st.session_state.open_cat = None
                    st.rerun()
