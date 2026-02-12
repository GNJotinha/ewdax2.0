import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

from shared import sub_options_with_livre, apply_sub_filter
from relatorios import gerar_dados


def _copy_to_clipboard(text: str):
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
    _, mid, _ = st.columns([1, 2.6, 1])

    with mid:
        st.markdown("<h1 style='text-align:center; margin-bottom: 0.2rem;'>Relatório customizado</h1>", unsafe_allow_html=True)
        st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)

        if df is None or df.empty:
            st.info("Sem dados carregados.")
            return

        # Normaliza data (sem ficar quebrando)
        dfx = df.copy()
        if "data_do_periodo" in dfx.columns:
            dfx["data_do_periodo"] = pd.to_datetime(dfx["data_do_periodo"], errors="coerce")
            dfx["data"] = dfx["data_do_periodo"].dt.date
        elif "data" in dfx.columns:
            dfx["data"] = pd.to_datetime(dfx["data"], errors="coerce").dt.date
        else:
            st.error("Não achei coluna de data.")
            return

        dfx = dfx.dropna(subset=["data"])

        # Card filtros
        with st.container(border=True):
            entregadores_lista = sorted(dfx["pessoa_entregadora"].dropna().unique())
            entregador = st.selectbox(
                "Selecione o entregador",
                [None] + entregadores_lista,
                format_func=lambda x: "" if x is None else x,
                key="rc_ent",
            )

            # Subpraça
            subpracas = sub_options_with_livre(dfx, praca_scope="SAO PAULO") if "sub_praca" in dfx.columns else []
            filtro_subpraca = st.multiselect("Subpraça", subpracas, key="rc_sub")

            # Turno
            if "periodo" in dfx.columns:
                turnos = sorted(dfx["periodo"].dropna().unique())
                filtro_turno = st.multiselect("Turno", turnos, key="rc_turno")
            else:
                filtro_turno = []

            tipo_periodo = st.radio(
                "Como deseja escolher as datas?",
                ("Período contínuo", "Dias específicos"),
                horizontal=True,
                key="rc_tipo",
            )

            dias_escolhidos = []

            if tipo_periodo == "Período contínuo":
                data_min = dfx["data"].min()
                data_max = dfx["data"].max()
                periodo = st.date_input(
                    "Intervalo de datas",
                    [data_min, data_max],
                    format="DD/MM/YYYY",
                    key="rc_periodo",
                )
                if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
                    dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
                elif isinstance(periodo, (list, tuple)) and len(periodo) == 1:
                    dias_escolhidos = [periodo[0]]
            else:
                dias_opcoes = sorted(dfx["data"].unique())
                dias_escolhidos = st.multiselect(
                    "Dias específicos",
                    dias_opcoes,
                    format_func=lambda x: pd.to_datetime(x).strftime("%d/%m/%Y"),
                    key="rc_dias",
                )

            gerar_custom = st.button("Gerar relatório", use_container_width=True, disabled=not bool(entregador), key="rc_gerar")

        # Resultado
        if "rc_texto" not in st.session_state:
            st.session_state["rc_texto"] = ""

        if gerar_custom and entregador:
            df_filt = dfx[dfx["pessoa_entregadora"] == entregador].copy()

            if filtro_subpraca and "sub_praca" in df_filt.columns:
                df_filt = apply_sub_filter(df_filt, filtro_subpraca, praca_scope="SAO PAULO")

            if filtro_turno and "periodo" in df_filt.columns:
                df_filt = df_filt[df_filt["periodo"].isin(filtro_turno)]

            if dias_escolhidos:
                df_filt = df_filt[df_filt["data"].isin(dias_escolhidos)]

            texto = gerar_dados(entregador, None, None, df_filt)
            st.session_state["rc_texto"] = texto or "Nenhum dado encontrado."

        if st.session_state["rc_texto"]:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            with st.container(border=True):
                st.text_area(label="", value=st.session_state["rc_texto"], height=420, key="rc_out")

                spacer, btncol = st.columns([5, 1])
                with btncol:
                    if st.button("Copiar", use_container_width=True, key="rc_copy"):
                        _copy_to_clipboard(st.session_state["rc_texto"])
                        if hasattr(st, "toast"):
                            st.toast("Copiado!")
                        else:
                            st.success("Copiado!")
