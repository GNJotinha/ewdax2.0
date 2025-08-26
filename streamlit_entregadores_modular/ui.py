# ui.py  — helpers visuais para Streamlit
# compatível com Python 3.8/3.9/3.10+

from pathlib import Path
from typing import Optional, List, Tuple
import streamlit as st


# =========================
#  CSS global (externo)
# =========================
def inject_css():
    """
    Injeta assets/style.css. Usa caminho absoluto ancorado no arquivo,
    com fallback para a pasta de trabalho atual.
    """
    css_path = Path(__file__).resolve().parent / "assets" / "style.css"
    if not css_path.exists():
        alt = Path.cwd() / "assets" / "style.css"
        if alt.exists():
            css_path = alt

    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    else:
        st.warning("⚠️ assets/style.css não encontrado. O visual customizado não será aplicado.")


# =========================
#  Componentes de layout
# =========================
def topbar(title: str, right_chip: Optional[str] = None):
    """
    Barra superior simples.
    O visual (cores/bordas) vem do style.css pelas classes .topbar, .title, .chip.
    """
    st.markdown(
        """
        <div class="topbar">
          <div class="title">📋 {title}</div>
          {chip}
        </div>
        """.format(
            title=title,
            chip=('<div style="flex:1"></div><div class="chip">{}</div>'.format(right_chip)) if right_chip else ""
        ),
        unsafe_allow_html=True,
    )


def section(title: str):
    """Título de seção padronizado."""
    st.markdown('<div class="section-title">{}</div>'.format(title), unsafe_allow_html=True)


# =========================
#  KPIs (cards)
# =========================
def kpi(label: str, value: str, sub: str = ""):
    """
    Um card KPI. Estilo via .kpi, .kpi-label, .kpi-value, .kpi-sub no style.css.
    """
    st.markdown(
        """
        <div class="kpi">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
          {sub}
        </div>
        """.format(
            label=label,
            value=value,
            sub=('<div class="kpi-sub">{}</div>'.format(sub)) if sub else ""
        ),
        unsafe_allow_html=True,
    )


def kpi_row(items: List[Tuple[str, str, str]]):
    """
    Renderiza uma grade de KPIs.
    items: lista de tuples (label, value, sub)
    """
    st.markdown('<div class="kpi-row">', unsafe_allow_html=True)
    for (label, value, sub) in items:
        kpi(label, value, sub)
    st.markdown('</div>', unsafe_allow_html=True)


# =========================
#  Extras opcionais
# =========================
def card_start():
    """Abre um bloco com moldura (usa .card do style.css)."""
    st.markdown('<div class="card">', unsafe_allow_html=True)

def card_end():
    """Fecha o bloco aberto por card_start()."""
    st.markdown('</div>', unsafe_allow_html=True)

def spacer(h: int = 8):
    """Espaço vertical (px)."""
    st.markdown(f"<div style='height:{int(h)}px'></div>", unsafe_allow_html=True)
