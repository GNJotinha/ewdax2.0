import streamlit as st
import pandas as pd
import streamlit.components.v1 as components


MAPA_HOME_SRC = "https://www.google.com/maps/d/embed?mid=1CgvVffJ9kL78Ffs-VMkBRwy0a0xkYP8&ehbc=2E312F"


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


def _goto(module: str, cat=None):
    st.session_state.module = module
    st.session_state.open_cat = cat
    st.rerun()


def _render_home_map():
    st.markdown(
        """
        <div style="
            margin-top: 18px;
            padding: 16px;
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,.10);
            background: rgba(255,255,255,.03);
            box-shadow: 0 14px 34px rgba(0,0,0,.35);
        ">
          <div style="
              font-size: 1.05rem;
              font-weight: 950;
              margin-bottom: 12px;
              color: rgba(255,255,255,.96);
          ">Mapa operacional</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    components.html(
        f"""
        <div style="width:100%;">
          <iframe
            src="{MAPA_HOME_SRC}"
            width="100%"
            height="520"
            style="border:0; border-radius:14px; overflow:hidden;"
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade">
          </iframe>
        </div>
        """,
        height=540,
    )


def render(df: pd.DataFrame, _USUARIOS: dict):
    last_day = _last_date_str(df)
    fonte = getattr(df, "attrs", {}).get("fonte", "") if df is not None else ""

    # Centraliza o conteúdo (pra não ficar largado no vazio)
    _, mid, _ = st.columns([1, 2.6, 1], vertical_alignment="top")

    with mid:
        # Topo: Título + meta + botões
        L, R = st.columns([3.6, 1.4], vertical_alignment="center")

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
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Perfil", type="secondary", use_container_width=True, key="home_profile"):
                    _goto("views.perfil", None)
            with c2:
                if st.button("Sair", type="secondary", use_container_width=True, key="home_logout"):
                    _logout()
                    st.rerun()

        st.markdown("<div class='neo-divider'></div>", unsafe_allow_html=True)

        # Admin (somente o que NÃO está na lateral)
        if st.session_state.get("is_admin"):
            st.markdown("""<div class="neo-section">Admin</div>""", unsafe_allow_html=True)

            a1, a2, _sp = st.columns([1, 1, 2.8])
            with a1:
                if st.button("Usuários", use_container_width=True, key="home_admin_users"):
                    _goto("views.admin_usuarios", None)
            with a2:
                if st.button("Auditoria", use_container_width=True, key="home_admin_audit"):
                    _goto("views.auditoria", None)

        _render_home_map()

        # Rodapé discreto
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        st.caption(f"Login: {st.session_state.get('usuario','-')}")
        st.caption(f"Departamento: {st.session_state.get('department','-')}")
