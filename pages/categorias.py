import streamlit as st
import pandas as pd
from relatorios import classificar_entregadores
from shared import hms_from_hours

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📚 Categorias de Entregadores")

    tipo_cat = st.radio("Período de análise:", ["Mês/Ano", "Todo o histórico"], horizontal=True, index=0)
    mes_sel = ano_sel = None
    if tipo_cat == "Mês/Ano":
        col1, col2 = st.columns(2)
        mes_sel = col1.selectbox("Mês", list(range(1, 13)))
        ano_sel = col2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

    df_cat = classificar_entregadores(df, mes_sel, ano_sel) if tipo_cat == "Mês/Ano" else classificar_entregadores(df)
    if df_cat.empty:
        st.info("Nenhum dado encontrado para o período selecionado.")
        return

    if "supply_hours" in df_cat.columns:
        df_cat["tempo_hms"] = df_cat["supply_hours"].apply(hms_from_hours)

    cont = df_cat["categoria"].value_counts().reindex(["Premium","Conectado","Casual","Flutuante"]).fillna(0).astype(int)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("🚀 Premium", int(cont.get("Premium",0)))
    c2.metric("🎯 Conectado", int(cont.get("Conectado",0)))
    c3.metric("👍 Casual", int(cont.get("Casual",0)))
    c4.metric("↩ Flutuante", int(cont.get("Flutuante",0)))

    cols_show = ["pessoa_entregadora","categoria","tempo_hms","aceitacao_%","conclusao_%","ofertadas","aceitas","completas","criterios_atingidos"]
    st.dataframe(df_cat[cols_show].style.format({"aceitacao_%":"{:.1f}","conclusao_%":"{:.1f}"}), use_container_width=True)

    st.download_button("⬇️ Baixar CSV", data=df_cat[cols_show].to_csv(index=False, decimal=",").encode("utf-8"),
                       file_name="categorias_entregadores.csv", mime="text/csv")
