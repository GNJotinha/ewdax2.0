# ui.py  (compatível com Python 3.8/3.9)
from pathlib import Path
from typing import Optional, List, Tuple
import streamlit as st

def inject_css():
    css_path = Path(__file__).resolve().parent / "assets" / "style.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    else:
        st.warning("⚠️ assets/style.css não encontrado. O visual customizado não será aplicado.")

def topbar(title: str, right_chip: Optional[str] = None):
    st.markdown(
        """
        <style>
          .topbar{
            background: linear-gradient(180deg, rgba(21,27,34,.85), rgba(21,27,34,.45));
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            padding: 12px 14px;
            box-shadow: 0 6px 24px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.02);
            display:flex; align-items:center; gap:10px;
          }
          .topbar .title{ font-size:1.05rem; color: #8b949e; }
          .topbar .chip{
            background: #0b1220;
            border:1px solid rgba(255,255,255,0.08);
            border-radius: 999px;
            padding: 4px 10px; font-size:.9rem; color: #c9d1d9;
          }
          .section-title{ margin:8px 0 12px 0; font-weight:700; font-size:1.05rem; color:#c9d1d9; opacity:.9; }
          .kpi-row{ display:grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
          @media (max-width: 1100px){ .kpi-row{ grid-template-columns: repeat(2,1fr);} }
          @media (max-width: 640px){ .kpi-row{ grid-template-columns: 1fr;} }
          .kpi{
            background: rgba(15,23,42,.5);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 16px 18px;
            box-shadow: 0 6px 24px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.02);
          }
          .kpi .kpi-label{ color: #8b949e; font-size:.86rem; }
          .kpi .kpi-value{ font-size: 1.8rem; font-weight: 800; margin-top: 6px; }
          .kpi .kpi-sub{ color: #8b949e; font-size:.85rem; margin-top: 4px; }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        u"""
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
    st.markdown('<div class="section-title">{}</div>'.format(title), unsafe_allow_html=True)

def kpi(label: str, value: str, sub: str = ""):
    st.markdown(
        u"""
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
        unsafe_allow_html=True
    )

def kpi_row(items: List[Tuple[str, str, str]]):
    st.markdown('<div class="kpi-row">', unsafe_allow_html=True)
    for (label, value, sub) in items:
        kpi(label, value, sub)
    st.markdown('</div>', unsafe_allow_html=True)
