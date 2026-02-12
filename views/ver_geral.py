# views/ver_geral.py
import re
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from relatorios import gerar_dados

_EMOJI_RE = re.compile(
    r"["
    r"\U0001F300-\U0001F5FF"
    r"\U0001F600-\U0001F64F"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F700-\U0001F77F"
    r"\U0001F780-\U0001F7FF"
    r"\U0001F800-\U0001F8FF"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA00-\U0001FAFF"
    r"\u2600-\u26FF"
    r"\u2700-\u27BF"
    r"]+",
    flags=re.UNICODE,
)

def _strip_emojis(txt: str) -> str:
    if not txt:
        return ""
    out = _EMOJI_RE.sub("", txt)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _centered_container():
    _, mid, _ = st.columns([1, 2.6, 1], vertical_alignment="top")
    return mid


def _copy_button_bottom(text: str, key: str, label: str = "Copiar"):
    """Botão copiar alinhado embaixo (lado direito)."""
    safe = json.dumps(text or "")
    html = f"""
    <div style="display:flex; justify-content:flex-end; margin: .65rem 0 0 0;">
      <button
        id="btn_{key}"
        style="
          background: rgba(255,255,255,.04);
          color: rgba(232,237,246,.92);
          border: 1px solid rgba(255,255,255,.14);
          border-radius: 12px;
          padding: .45rem .9rem;
          font-weight: 850;
          cursor: pointer;
        "
      >
        {label}
      </button>

      <span id="ok_{key}" style="margin-left:10px; opacity:.75; font-weight:750;"></span>
    </div>

    <script>
      (function() {{
        const text = {safe};
        const btn  = document.getElementById("btn_{key}");
        const ok   = document.getElementById("ok_{key}");

        function done(msg) {{
          ok.textContent = msg;
          setTimeout(() => ok.textContent = "", 1500);
        }}

        btn.addEventListener("click", async () => {{
          try {{
            await navigator.clipboard.writeText(text);
            done("Copiado ✅");
          }} catch (e) {{
            const ta = document.createElement("textarea");
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            document.body.removeChild(ta);
            done("Copiado ✅");
          }}
        }});
      }})();
    </script>
    """
    components.html(html, height=52)


def render(df: pd.DataFrame, _USUARIOS: dict):
    if df is None or df.empty or "pessoa_entregadora" not in df.columns:
        st.info("Sem dados carregados.")
        return

    nomes = sorted(df["pessoa_entregadora"].dropna().unique().tolist())

    st.session_state.setdefault("vg_nome", None)
    st.session_state.setdefault("vg_texto", "")

    with _centered_container():
        # título centralizado junto do card
        st.markdown(
            "<div style='text-align:center; font-weight:950; font-size:2.05rem; margin: 0 0 .75rem 0;'>"
            "Desempenho geral"
            "</div>",
            unsafe_allow_html=True,
        )

        # Card de seleção + gerar
        with st.container(border=True):
            st.markdown(
                "<div style='text-align:center; font-weight:900; font-size:1.05rem; opacity:.92;'>"
                "Selecione o entregador</div>",
                unsafe_allow_html=True,
            )

            nome = st.selectbox(
                "Selecione o entregador:",
                [None] + nomes,
                index=([None] + nomes).index(st.session_state.get("vg_nome"))
                if st.session_state.get("vg_nome") in nomes else 0,
                format_func=lambda x: "" if x is None else x,
                label_visibility="collapsed",
                key="vg_select_nome",
            )

            gerar = st.button(
                "Gerar relatório",
                disabled=not bool(nome),
                use_container_width=True,
                key="vg_btn_gerar",
            )

            if gerar:
                texto = gerar_dados(nome, None, None, df[df["pessoa_entregadora"] == nome])
                texto = _strip_emojis(texto or "Nenhum dado encontrado")
                st.session_state["vg_nome"] = nome
                st.session_state["vg_texto"] = texto

        texto_final = (st.session_state.get("vg_texto") or "").strip()
        if not texto_final:
            return

        # ✅ Card do texto (sem "Resultado") + Copiar embaixo
        with st.container(border=True):
            st.text_area(
                label="",
                value=texto_final,
                height=420,
                label_visibility="collapsed",
                key="vg_text_area",
            )
            _copy_button_bottom(texto_final, key="vg_copy_bottom", label="Copiar")
