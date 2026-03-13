import streamlit as st
import pandas as pd
import streamlit.components.v1 as components


MAPA_HOME_SRC = "https://www.google.com/maps/d/embed?mid=1CgvVffJ9kL78Ffs-VMkBRwy0a0xkYP8&ehbc=2E312F"
MAPA_VIEWER_URL = "https://www.google.com/maps/d/viewer?mid=1CgvVffJ9kL78Ffs-VMkBRwy0a0xkYP8&usp=sharing"


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
        <style>
          * {{ box-sizing: border-box; }}
          html, body {{ margin: 0; padding: 0; background: transparent; }}

          .map-shell {{
            position: relative;
            width: 100%;
            min-height: 84vh;
            border-radius: 28px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,.09);
            background:
              radial-gradient(circle at top left, rgba(40, 67, 135, .18), transparent 28%),
              radial-gradient(circle at bottom right, rgba(19, 184, 255, .12), transparent 30%),
              linear-gradient(180deg, rgba(11,15,24,.98), rgba(7,10,17,.98));
            box-shadow:
              0 24px 60px rgba(0,0,0,.42),
              inset 0 1px 0 rgba(255,255,255,.04);
          }}

          .map-shell::after {{
            content: "";
            position: absolute;
            inset: 0;
            border-radius: 28px;
            pointer-events: none;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.04);
          }}

          .map-toolbar {{
            position: absolute;
            top: 16px;
            right: 16px;
            z-index: 3;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
          }}

          .map-chip {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 14px;
            border-radius: 999px;
            text-decoration: none;
            color: #f8fafc;
            font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: .01em;
            background: rgba(10,14,22,.62);
            border: 1px solid rgba(255,255,255,.12);
            backdrop-filter: blur(10px);
            box-shadow: 0 10px 24px rgba(0,0,0,.24);
            transition: transform .18s ease, background .18s ease, border-color .18s ease;
          }}

          .map-chip:hover {{
            transform: translateY(-1px);
            background: rgba(17,24,39,.78);
            border-color: rgba(255,255,255,.2);
          }}

          .map-chip svg {{
            width: 14px;
            height: 14px;
            flex: 0 0 14px;
          }}

          .map-frame-wrap {{
            width: 100%;
            height: 84vh;
            min-height: 680px;
          }}

          .map-frame {{
            width: 100%;
            height: 100%;
            border: 0;
            display: block;
            background: #0b1220;
          }}

          @media (max-width: 900px) {{
            .map-shell {{
              border-radius: 22px;
              min-height: 78vh;
            }}

            .map-frame-wrap {{
              height: 78vh;
              min-height: 560px;
            }}

            .map-toolbar {{
              top: 12px;
              right: 12px;
            }}

            .map-chip {{
              padding: 9px 12px;
              font-size: 12px;
            }}
          }}
        </style>

        <div class="map-shell">
          <div class="map-toolbar">
            <a class="map-chip" href="{MAPA_VIEWER_URL}" target="_blank" rel="noopener noreferrer">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M14 5H19V10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M10 14L19 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M19 14V19H5V5H10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              Abrir visualização
            </a>
          </div>

          <div class="map-frame-wrap">
            <iframe
              class="map-frame"
              src="{MAPA_HOME_SRC}"
              loading="lazy"
              referrerpolicy="no-referrer-when-downgrade"
              allowfullscreen>
            </iframe>
          </div>
        </div>
        """,
        height=900,
    )


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.markdown(
        """
        <style>
          .block-container {
            padding-top: 0.7rem;
            padding-bottom: 0.7rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100%;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _render_home_map()
