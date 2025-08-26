# ui.py
import streamlit as st

def inject_css():
    st.markdown(
        '<style>' + open("assets/style.css", "r", encoding="utf-8").read() + '</style>',
        unsafe_allow_html=True
    )

def topbar(title: str, right_chip: str | None = None):
    col = st.container()
    with col:
        st.markdown(
            f"""
            <div class="topbar">
              <div class="title">📋 {title}</div>
              {'<div style="flex:1"></div><div class="chip">'+right_chip+'</div>' if right_chip else ''}
            </div>
            """,
            unsafe_allow_html=True
        )

def section(title: str):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)

def kpi(label: str, value: str, sub: str = ""):
    st.markdown(
        f"""
        <div class="kpi">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
          {f'<div class="kpi-sub">{sub}</div>' if sub else ''}
        </div>
        """,
        unsafe_allow_html=True
    )

def kpi_row(items: list[tuple[str, str, str]]):
    st.markdown('<div class="kpi-row">', unsafe_allow_html=True)
    for (label, value, sub) in items:
        kpi(label, value, sub)
    st.markdown('</div>', unsafe_allow_html=True)
