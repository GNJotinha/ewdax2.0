import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

from relatorios import gerar_dados


def _copy_to_clipboard(text: str):
    # ✅ Copia de verdade (JS). Sem frescura.
    safe = (text or "").replace("\\", "\\\\").replace("`", "\\`").replace("</", "<\\/")
    components.html(
        f"""
        <script>
          const txt = `{safe}`;
          navigator.clipboard.writeText(txt).then(() => {{
            console.log("copiado");
          }});
        </script>
        """,
        height=0,
    )


def render(df: pd.DataFrame, _USUARIOS: dict):
    # Centraliza tudo
    _, mid, _ = st.columns([1, 2.6, 1])

    with mid:
        st.markdown("<h1 style='text-align:center; margin-bottom: 0.2rem;'>Desempenho geral</h1>", unsafe_allow_html=True)
        st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)

        # Card de seleção
        with st.container(border=True):
            nomes = sorted(df["pessoa_entregadora"].dropna().unique())

            nome = st.selectbox(
                "Selecione o entregador",
                [None] + nomes,
                format_func=lambda x: "" if x is None else x,
                key="vg_nome",
            )

            gerar = st.button("Gerar relatório", disabled=not bool(nome), use_container_width=True, key="vg_gerar")

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # Resultado (card)
        if "vg_texto" not in st.session_state:
            st.session_state["vg_texto"] = ""

        if gerar and nome:
            texto = gerar_dados(nome, None, None, df[df["pessoa_entregadora"] == nome])
            st.session_state["vg_texto"] = texto or "Nenhum dado encontrado."

        if st.session_state["vg_texto"]:
            with st.container(border=True):
                st.text_area(
                    label="",
                    value=st.session_state["vg_texto"],
                    height=360,
                    key="vg_result",
                )

                # botão embaixo (alinhado à direita)
                spacer, btncol = st.columns([5, 1])
                with btncol:
                    if st.button("Copiar", use_container_width=True, key="vg_copy"):
                        _copy_to_clipboard(st.session_state["vg_texto"])
                        if hasattr(st, "toast"):
                            st.toast("Copiado!")
                        else:
                            st.success("Copiado!")
