import streamlit as st
import pandas as pd
from shared import sub_options_with_livre

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("Relatórios por região")

    obrig = ["sub_praca","periodo","data","numero_de_corridas_ofertadas","numero_de_corridas_aceitas","numero_de_corridas_rejeitadas","numero_de_corridas_completadas","pessoa_entregadora"]
    faltando = [c for c in obrig if c not in df.columns]
    if faltando:
        st.error("Colunas ausentes no dataset: " + ", ".join(faltando))
        return

    subpracas = sub_options_with_livre(df, praca_scope="SAO PAULO")
    sub_sel = st.selectbox("Selecione a subpraça:", subpracas)

    turnos = sorted(df["periodo"].dropna().unique())
    turnos_sel = st.multiselect("Filtrar por turnos:", turnos)

    if sub_sel == "LIVRE":
        df_area = df[(df["praca"] == "SAO PAULO") & (df["sub_praca"].isna())].copy()
    else:
        df_area = df[df["sub_praca"] == sub_sel].copy()
    if turnos_sel:
        df_area = df_area[df_area["periodo"].isin(turnos_sel)]

    df_area["data_do_periodo"] = pd.to_datetime(df_area.get("data_do_periodo", df_area.get("data")), errors="coerce")
    df_area["data"] = df_area["data_do_periodo"].dt.date

    tipo_periodo = st.radio("Como deseja escolher as datas?", ("Período contínuo","Dias específicos"), horizontal=True)
    dias_escolhidos = []
    if tipo_periodo == "Período contínuo":
        data_min = df_area["data"].min()
        data_max = df_area["data"].max()
        periodo = st.date_input("Selecione o intervalo de datas:", [data_min, data_max], format="DD/MM/YYYY")
        if len(periodo) == 2:
            dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
        elif len(periodo) == 1:
            dias_escolhidos = [periodo[0]]
    else:
        dias_opcoes = sorted([d for d in df_area["data"].dropna().unique()])
        dias_escolhidos = st.multiselect("Selecione os dias desejados:", dias_opcoes, format_func=lambda x: x.strftime("%d/%m/%Y"))

    if dias_escolhidos:
        df_area = df_area[df_area["data"].isin(dias_escolhidos)]

    if df_area.empty:
        st.info("❌ Nenhum dado encontrado para esse filtro.")
        return

    ofertadas  = int(pd.to_numeric(df_area["numero_de_corridas_ofertadas"], errors="coerce").fillna(0).sum())
    aceitas    = int(pd.to_numeric(df_area["numero_de_corridas_aceitas"], errors="coerce").fillna(0).sum())
    rejeitadas = int(pd.to_numeric(df_area["numero_de_corridas_rejeitadas"], errors="coerce").fillna(0).sum())
    completas  = int(pd.to_numeric(df_area["numero_de_corridas_completadas"], errors="coerce").fillna(0).sum())
    entreg_uniq = int(df_area["pessoa_entregadora"].dropna().nunique())

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📦 Ofertadas", f"{ofertadas:,}".replace(",", "."))
    c2.metric("👍 Aceitas", f"{aceitas:,}".replace(",", "."), f"{(aceitas/ofertadas*100 if ofertadas else 0):.1f}%")
    c3.metric("👎 Rejeitadas", f"{rejeitadas:,}".replace(",", "."), f"{(rejeitadas/ofertadas*100 if ofertadas else 0):.1f}%")
    c4.metric("🏁 Completas", f"{completas:,}".replace(",", "."), f"{(completas/aceitas*100 if aceitas else 0):.1f}%")
    c5.metric("👤 Entregadores", entreg_uniq)
