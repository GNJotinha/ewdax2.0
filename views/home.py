import html
import streamlit as st
import pandas as pd
import streamlit.components.v1 as components


MAPA_VIEWER_URL = "https://www.google.com/maps/d/viewer?mid=1CgvVffJ9kL78Ffs-VMkBRwy0a0xkYP8&usp=sharing"


HOME_CARDS = [
    {
        "title": "Mapa operacional",
        "subtitle": "Visualização rápida das subpraças e regiões no Google My Maps.",
        "href": MAPA_VIEWER_URL,
        "badge": "Disponível",
        "kind": "primary",
        "icon": "🗺️",
        "cta": "Abrir mapa",
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
    subtitle = html.escape(card.get("subtitle", ""))
    badge = html.escape(card.get("badge", ""))
    icon = html.escape(card.get("icon", ""))
    cta = html.escape(card.get("cta", "Abrir"))
    href = html.escape(card.get("href", "#"), quote=True)
    kind = html.escape(card.get("kind", "secondary"))

    return f"""
    <a class="home-card {kind}" href="{href}" target="_blank" rel="noopener noreferrer">
      <div class="card-head">
        <span class="card-icon">{icon}</span>
        <span class="card-badge">{badge}</span>
      </div>

      <div class="card-body">
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>

      <div class="card-foot">
        <span>{cta}</span>
        <span class="card-arrow">→</span>
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
            min-height: 42vh;
            display: flex;
            align-items: flex-start;
            justify-content: flex-start;
            padding: 10px 6px;
          }}

          .card-grid {{
            width: 100%;
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(210px, 210px));
            gap: 16px;
            justify-content: flex-start;
          }}

          .home-card {{
            position: relative;
            width: 210px;
            min-height: 210px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 14px;
            padding: 18px;
            border-radius: 24px;
            text-decoration: none;
            color: inherit;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,.08);
            background:
              linear-gradient(180deg, rgba(15, 23, 42, .97), rgba(17, 24, 39, .95)),
              linear-gradient(135deg, #0f172a, #111827);
            box-shadow: 0 18px 40px rgba(2, 6, 23, .18);
            transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
          }}

          .home-card::before {{
            content: "";
            position: absolute;
            inset: 0;
            background:
              radial-gradient(circle at 16% 16%, rgba(255,255,255,.14), transparent 24%),
              radial-gradient(circle at 84% 84%, rgba(56, 189, 248, .16), transparent 26%);
            pointer-events: none;
          }}

          .home-card:hover {{
            transform: translateY(-3px);
            border-color: rgba(255,255,255,.16);
            box-shadow: 0 24px 48px rgba(2, 6, 23, .26);
          }}

          .card-head,
          .card-foot {{
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
          }}

          .card-icon {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 44px;
            height: 44px;
            border-radius: 14px;
            font-size: 22px;
            background: rgba(255,255,255,.08);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
          }}

          .card-badge {{
            display: inline-flex;
            align-items: center;
            padding: 5px 9px;
            border-radius: 999px;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: .04em;
            text-transform: uppercase;
            color: #dbeafe;
            background: rgba(59,130,246,.14);
            border: 1px solid rgba(96,165,250,.22);
          }}

          .card-body {{
            position: relative;
            z-index: 1;
          }}

          .card-body h3 {{
            margin: 0 0 8px;
            font-size: 18px;
            line-height: 1.15;
            font-weight: 800;
            letter-spacing: -.02em;
          }}

          .card-body p {{
            margin: 0;
            font-size: 12px;
            line-height: 1.45;
            color: #cbd5e1;
          }}

          .card-foot span:first-child {{
            font-size: 12px;
            font-weight: 700;
            color: #e2e8f0;
          }}

          .card-arrow {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 30px;
            height: 30px;
            border-radius: 999px;
            font-size: 16px;
            background: rgba(255,255,255,.09);
            border: 1px solid rgba(255,255,255,.08);
          }}

          @media (max-width: 700px) {{
            .home-shell {{
              min-height: auto;
            }}

            .card-grid {{
              grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
            }}

            .home-card {{
              width: 100%;
              min-height: 180px;
              padding: 16px;
            }}
          }}
        </style>

        <div class="home-shell">
          <section class="card-grid">
            {cards_html}
          </section>
        </div>
        """,
        height=320,
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
