import html
import streamlit as st
import pandas as pd
import streamlit.components.v1 as components


MAPA_VIEWER_URL = "https://www.google.com/maps/d/viewer?mid=1CgvVffJ9kL78Ffs-VMkBRwy0a0xkYP8&usp=sharing"


HOME_CARDS = [
    {
        "title": "Mapa",
        "href": MAPA_VIEWER_URL,
        "icon": "🗺️",
    },
]


def _logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]



def _goto(module: str, cat=None):
    st.session_state.module = module
    st.session_state.open_cat = cat
    st.rerun()



def _build_card(card: dict) -> str:
    title = html.escape(card.get("title", ""))
    icon = html.escape(card.get("icon", ""))
    href = html.escape(card.get("href", "#"), quote=True)

    return f"""
    <a class="home-card" href="{href}" target="_blank" rel="noopener noreferrer" aria-label="{title}">
      <div class="card-content">
        <span class="card-icon">{icon}</span>
        <h3>{title}</h3>
      </div>
    </a>
    """



def _render_home_cards():
    cards_html = "".join(_build_card(card) for card in HOME_CARDS)

    components.html(
        f"""
        <style>
          * {{ box-sizing: border-box; }}
          html, body {{
            margin: 0;
            padding: 0;
            background: transparent;
            font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: #f8fafc;
          }}

          .home-shell {{
            min-height: 26vh;
            display: flex;
            align-items: flex-start;
            justify-content: flex-start;
            padding: 8px 6px;
          }}

          .card-grid {{
            width: 100%;
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(140px, 140px));
            gap: 14px;
            justify-content: flex-start;
          }}

          .home-card {{
            width: 140px;
            height: 140px;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 14px;
            border-radius: 24px;
            text-decoration: none;
            color: inherit;
            border: 1px solid rgba(255,255,255,.08);
            background:
              linear-gradient(180deg, rgba(15, 23, 42, .97), rgba(17, 24, 39, .95)),
              linear-gradient(135deg, #0f172a, #111827);
            box-shadow: 0 18px 36px rgba(2, 6, 23, .16);
            transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
          }}

          .home-card:hover {{
            transform: translateY(-3px);
            border-color: rgba(255,255,255,.16);
            box-shadow: 0 22px 42px rgba(2, 6, 23, .22);
          }}

          .card-content {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 10px;
            text-align: center;
          }}

          .card-icon {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 58px;
            height: 58px;
            border-radius: 18px;
            font-size: 30px;
            background: rgba(255,255,255,.08);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
          }}

          .card-content h3 {{
            margin: 0;
            font-size: 15px;
            line-height: 1.1;
            font-weight: 700;
            letter-spacing: -.02em;
            color: #f8fafc;
          }}

          @media (max-width: 700px) {{
            .card-grid {{
              grid-template-columns: repeat(auto-fill, minmax(124px, 124px));
              gap: 12px;
            }}

            .home-card {{
              width: 124px;
              height: 124px;
              padding: 12px;
              border-radius: 20px;
            }}

            .card-icon {{
              width: 52px;
              height: 52px;
              font-size: 27px;
            }}
          }}
        </style>

        <div class="home-shell">
          <section class="card-grid">
            {cards_html}
          </section>
        </div>
        """,
        height=230,
    )



def render(df: pd.DataFrame, _USUARIOS: dict):
    st.markdown(
        """
        <style>
          .block-container {
            padding-top: 0.85rem;
            padding-bottom: 0.8rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100%;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _render_home_cards()
