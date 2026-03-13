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
    components.html(
        f"""
        <div style="width:100%; padding:0; margin:0;">
          <iframe
            src="{MAPA_HOME_SRC}"
            style="
              width:100%;
              height:78vh;
              min-height:620px;
              max-height:820px;
              border:0;
              border-radius:18px;
              overflow:hidden;
              box-shadow: 0 14px 34px rgba(0,0,0,.35);
              background: rgba(255,255,255,.02);
            "
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade">
          </iframe>
        </div>
        """,
        height=840,
    )


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.markdown(
        """
        <style>
          .block-container {
            padding-top: 1.2rem;
            padding-bottom: 1rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _render_home_map()
