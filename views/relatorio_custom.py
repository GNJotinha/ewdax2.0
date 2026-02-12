import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

from shared import sub_options_with_livre, apply_sub_filter
from relatorios import gerar_dados
from utils import normalizar


def _copy_to_clipboard(text: str):
    safe = (text or "").replace("\\", "\\\\").replace("`", "\\`").replace("</", "<\\/")
    components.html(
        f"""
        <script>
          const txt = `{safe}`;
          navigator.clipboard.writeText(txt);
        </script>
        """,
        height=0,
    )


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    dfx = df.copy()

    # garante data
    if "data" not in dfx.columns:
        if "data_do_periodo" in dfx.columns:
            dfx["data_do_periodo"] = pd.to_datetime(dfx["data_do_periodo"], errors="coerce")
            dfx["data"] = dfx["data_do_periodo"].dt.date
        else:
            # tenta converter alguma coluna "data"
            raise ValueError("Não encontrei coluna 'data' nem 'data_do_periodo'.")

    else:
        dfx["data"] = pd.to_datetime(dfx["data"], errors="coerce").dt.date

    dfx = dfx.dropna(subset=["data"])

    # garante normalizado (gerar_dados usa isso)
    if "pessoa_entregadora_normalizado" not in dfx.columns:
        dfx["pessoa_entregadora_normalizado"] = dfx["pessoa_entregadora"].astype(str).apply(normalizar)

    # garante mes/ano (pra outras funções; gerar_dados não exige, mas é bom ter)
    if "mes" not in dfx.columns:
        dfx["mes"] = pd.to_datetime(dfx["data"], errors="coerce").dt.month
    if "ano" not in dfx.columns:
        dfx["ano"] = pd.to_datetime(dfx["data"], errors="coerce").dt.year

    return dfx


def render(df: pd.DataFrame, _USUARIOS: dict):
    # centraliza igual o "Desempenho geral"
    _, mid, _ = st.columns([1, 2.6, 1])

    with mid:
        st.markdown("<h1 style='text-align:center; margin-bottom: 0.25rem;'>Relatório customizado</h1>", unsafe_allow_html=True)

        if df is None or df.empty:
            st.info("Sem dados carregados.")
            return

        try:
            dfx = _ensure_columns(df)
        except Exception as e:
            st.error(f"Erro preparando dados: {e}")
            return

        entregadores_lista = sorted(dfx["pessoa_entregadora"].dropna().unique().tolist())

        # estado do texto
        st.session_state.setdefault("rc_texto", "")

        # filtros (card)
        with st.container(border=True):
            with st.form("rc_form"):
                entregador = st.selectbox(
                    "Selecione o entregador",
                    [None] + entregadores_lista,
                    format_func=lambda x: "" if x is None else x,
                    key="rc_ent",
                )

                # subpraça
                subpracas = sub_options_with_livre(dfx, praca_scope="SAO PAULO") if "sub_praca" in dfx.columns else []
                filtro_subpraca = st.multiselect("Subpraça", subpracas, key="rc_sub")

                # turno
                if "periodo" in dfx.columns:
                    turnos = sorted(dfx["periodo"].dropna().unique().tolist())
                    filtro_turno = st.multiselect("Turno", turnos, key="rc_turno")
                else:
                    filtro_turno = []

                tipo_periodo = st.radio(
                    "Datas",
                    ("Período contínuo", "Dias específicos"),
                    horizontal=True,
                    key="rc_tipo",
                )

                dias_escolhidos = []
                if tipo_periodo == "Período contínuo":
                    data_min = dfx["data"].min()
                    data_max = dfx["data"].max()
                    periodo = st.date_input(
                        "Intervalo",
                        [data_min, data_max],
                        format="DD/MM/YYYY",
                        key="rc_periodo",
                    )
                    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
                        dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
                    elif isinstance(periodo, (list, tuple)) and len(periodo) == 1:
                        dias_escolhidos = [periodo[0]]
                else:
                    dias_opcoes = sorted(dfx["data"].unique().tolist())
                    dias_escolhidos = st.multiselect(
                        "Dias",
                        dias_opcoes,
                        format_func=lambda x: pd.to_datetime(x).strftime("%d/%m/%Y"),
                        key="rc_dias",
                    )

                gerar = st.form_submit_button("Gerar relatório", use_container_width=True, disabled=not bool(entregador))

        # gera
        if gerar and entregador:
            df_filt = dfx[dfx["pessoa_entregadora"] == entregador].copy()

            # subpraça (mesma regra do seu sistema)
            if "sub_praca" in df_filt.columns:
                df_filt = apply_sub_filter(df_filt, filtro_subpraca, praca_scope="SAO PAULO")

            # turno
            if filtro_turno and "periodo" in df_filt.columns:
                df_filt = df_filt[df_filt["periodo"].isin(filtro_turno)]

            # datas
            if dias_escolhidos:
                df_filt = df_filt[df_filt["data"].isin(dias_escolhidos)]

            # 👇 aqui é o ponto crítico: se df_filt vazio, a gente AVISA
            if df_filt.empty:
                st.session_state["rc_texto"] = "Nenhum dado encontrado com os filtros aplicados."
            else:
                texto = gerar_dados(entregador, None, None, df_filt)
                st.session_state["rc_texto"] = texto or "Nenhum dado encontrado."

        # saída (sempre aparece quando existe texto)
        texto_out = (st.session_state.get("rc_texto") or "").strip()
        if texto_out:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            with st.container(border=True):
                st.text_area(label="", value=texto_out, height=420, key="rc_out", label_visibility="collapsed")

                spacer, btncol = st.columns([5, 1])
                with btncol:
                    if st.button("Copiar", use_container_width=True, key="rc_copy"):
                        _copy_to_clipboard(texto_out)
                        if hasattr(st, "toast"):
                            st.toast("Copiado!")
                        else:
                            st.success("Copiado!")
