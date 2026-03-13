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
            min-height: 82vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px 8px;
            background:
              radial-gradient(circle at top left, rgba(34, 197, 94, .10), transparent 25%),
              radial-gradient(circle at top right, rgba(59, 130, 246, .16), transparent 30%),
              radial-gradient(circle at bottom center, rgba(14, 165, 233, .10), transparent 28%);
          }}

          .card-grid {{
            width: 100%;
            max-width: 980px;
            display: grid;
            grid-template-columns: repeat(12, minmax(0, 1fr));
            gap: 18px;
          }}

          .home-card {{
            grid-column: 2 / span 10;
            position: relative;
            display: flex;
            flex-direction: column;
            gap: 28px;
            min-height: 300px;
            padding: 32px;
            border-radius: 30px;
            text-decoration: none;
            color: inherit;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,.08);
            box-shadow: 0 28px 70px rgba(2, 6, 23, .28);
            transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
          }}

          .home-card::before {{
            content: "";
            position: absolute;
            inset: 0;
            background:
              radial-gradient(circle at 15% 18%, rgba(255,255,255,.16), transparent 22%),
              radial-gradient(circle at 86% 82%, rgba(125, 211, 252, .18), transparent 24%);
            pointer-events: none;
          }}

          .home-card:hover {{
            transform: translateY(-4px);
            border-color: rgba(255,255,255,.16);
            box-shadow: 0 36px 90px rgba(2, 6, 23, .38);
          }}

          .home-card.primary {{
            background:
              linear-gradient(135deg, rgba(15, 23, 42, .96), rgba(17, 24, 39, .94)),
              linear-gradient(180deg, #0f172a, #111827);
          }}

          .card-head,
          .card-foot {{
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
          }}

          .card-icon {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 60px;
            height: 60px;
            border-radius: 18px;
            font-size: 30px;
            background: rgba(255,255,255,.08);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.06);
          }}

          .card-badge {{
            display: inline-flex;
            align-items: center;
            padding: 8px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: .03em;
            text-transform: uppercase;
            color: #dbeafe;
            background: rgba(59,130,246,.14);
            border: 1px solid rgba(96,165,250,.24);
          }}

          .card-body {{
            position: relative;
            z-index: 1;
            max-width: 620px;
          }}

          .card-body h3 {{
            margin: 0 0 12px;
            font-size: clamp(28px, 3.6vw, 40px);
            line-height: 1.04;
            font-weight: 800;
            letter-spacing: -.04em;
          }}

          .card-body p {{
            margin: 0;
            font-size: 17px;
            line-height: 1.7;
            color: #cbd5e1;
          }}

          .card-foot span:first-child {{
            font-size: 15px;
            font-weight: 700;
            color: #e2e8f0;
          }}

          .card-arrow {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 42px;
            height: 42px;
            border-radius: 999px;
            font-size: 24px;
            background: rgba(255,255,255,.09);
            border: 1px solid rgba(255,255,255,.08);
          }}

          @media (max-width: 900px) {{
            .home-shell {{
              min-height: 70vh;
              padding-top: 10px;
            }}

            .home-card {{
              grid-column: span 12;
              min-height: 240px;
              padding: 22px;
              border-radius: 26px;
              gap: 20px;
            }}
          }}
        </style>

        <div class="home-shell">
          <section class="card-grid">
            {cards_html}
          </section>
        </div>
        """,
        height=560,
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
