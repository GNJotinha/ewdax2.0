# views/ver_geral.py
import re
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from relatorios import gerar_dados

# -----------------------------
# Helpers
# -----------------------------
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
    # Remove emojis e limpa espaços “sobrando”
    out = _EMOJI_RE.sub("", txt)
    out = re.sub(r"[ \t]+", " ", out)          # colapsa espaços
    out = re.sub(r"\n{3,}", "\n\n", out)       # limita linhas vazias
    out = out.strip()
    return out

def _copy_button(text: str, key: str, label: str = "Copiar"):
    """
    Botão copiar via HTML/JS (Streamlit não tem clipboard nativo confiável em todas versões).
    """
    safe = json.dumps(text or "")
    html = f"""
    <div style="display:flex; justify-content:center; margin: 0.25rem 0 0.75rem 0;">
      <button
        id="btn_{key}"
        style="
          background: rgba(255,255,255,.04);
          color: rgba(232,237,246,.92);
          border: 1px solid rgba(255,255,255,.14);
          border-radius: 14px;
          padding: .55rem 1.0rem;
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
            // fallback tosco porém funciona
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
    components.html(html, height=60)

def _centered_container():
    # Centraliza “na moral” usando colunas laterais vazias
    _, mid, _ = st.columns([1, 2.6, 1], vertical_alignment="top")
    return mid


# -----------------------------
# View
# -----------------------------
def render(df: pd.DataFrame, _USUARIOS: dict):
    # Título: só texto, sem emoji
    st.markdown("# Desempenho geral")

    if df is None or df.empty or "pessoa_entregadora" not in df.columns:
        st.info("Sem dados carregados.")
        return

    nomes = sorted(df["pessoa_entregadora"].dropna().unique().tolist())

    # Estado do resultado (pra não sumir ao mexer em select)
    st.session_state.setdefault("vg_nome", None)
    st.session_state.setdefault("vg_texto", "")

    with _centered_container():
        # Card dos controles
        with st.container(border=True):
            st.markdown(
                "<div style='text-align:center; font-weight:900; font-size:1.05rem; opacity:.92;'>"
                "Selecione o entregador</div>",
                unsafe_allow_html=True,
            )

            nome = st.selectbox(
                "Selecione o entregador:",
                [None] + nomes,
                index=([None] + nomes).index(st.session_state.get("vg_nome")) if st.session_state.get("vg_nome") in nomes else 0,
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
                if not nome:
                    st.warning("Selecione um entregador.")
                else:
                    texto = gerar_dados(
                        nome,
                        None,
                        None,
                        df[df["pessoa_entregadora"] == nome]
                    )
                    texto = _strip_emojis(texto or "Nenhum dado encontrado")
                    st.session_state["vg_nome"] = nome
                    st.session_state["vg_texto"] = texto

        # Resultado
        texto_final = (st.session_state.get("vg_texto") or "").strip()
        if texto_final:
            st.markdown(
                "<div style='text-align:center; font-weight:950; font-size:1.10rem; margin-top:.75rem;'>"
                "Resultado</div>",
                unsafe_allow_html=True,
            )

            # Botão copiar (sem emoji no texto, conforme você pediu)
            _copy_button(texto_final, key="vg_copy", label="Copiar")

            with st.container(border=True):
                st.text_area(
                    label="",
                    value=texto_final,
                    height=420,
                    label_visibility="collapsed",
                    key="vg_text_area",
                )
