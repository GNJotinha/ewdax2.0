import streamlit as st
import pandas as pd
from shared import sub_options_with_livre, apply_sub_filter
from relatorios import gerar_dados

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("Relatório Customizado do Entregador")

    entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
    entregador = st.selectbox("🔎 Selecione o entregador:", [None] + entregadores_lista,
                              format_func=lambda x: "" if x is None else x)

    subpracas = sub_options_with_livre(df, praca_scope="SAO PAULO")
    filtro_subpraca = st.multiselect("Filtrar por subpraça:", subpracas)

    if "periodo" in df.columns:
        turnos = sorted(df["periodo"].dropna().unique())
        filtro_turno = st.multiselect("Filtrar por turno:", turnos)
    else:
        filtro_turno = []

    df['data_do_periodo'] = pd.to_datetime(df['data_do_periodo'])
    df['data'] = df['data_do_periodo'].dt.date

    tipo_periodo = st.radio("Como deseja escolher as datas?", ("Período contínuo", "Dias específicos"))
    dias_escolhidos = []

    if tipo_periodo == "Período contínuo":
        data_min = df["data"].min()
        data_max = df["data"].max()
        periodo = st.date_input("Selecione o intervalo de datas:", [data_min, data_max], format="DD/MM/YYYY")
        if len(periodo) == 2:
            dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
        elif len(periodo) == 1:
            dias_escolhidos = [periodo[0]]
    else:
        dias_opcoes = sorted(df["data"].unique())
        dias_escolhidos = st.multiselect(
            "Selecione os dias desejados:",
            dias_opcoes,
            format_func=lambda x: x.strftime("%d/%m/%Y")
        )

    gerar_custom = st.button("Gerar relatório customizado", use_container_width=True)

    if gerar_custom and entregador:
        df_filt = df[df["pessoa_entregadora"] == entregador]
        df_filt = apply_sub_filter(df_filt, filtro_subpraca, praca_scope="SAO PAULO")
        if filtro_turno:
            df_filt = df_filt[df_filt["periodo"].isin(filtro_turno)]
        if dias_escolhidos:
            df_filt = df_filt[df_filt["data"].isin(dias_escolhidos)]

        texto = gerar_dados(entregador, None, None, df_filt)
        st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=400)
