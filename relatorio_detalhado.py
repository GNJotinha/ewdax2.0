import streamlit as st
from relatorios import consolidar_turnos_por_nome
from utils_filtros_avancados import filtrar_dados_avancado

def relatorio_detalhado(df):
    st.header("📌 Relatório Detalhado por Filtros")

    entregadores = sorted(df["pessoa_entregadora"].dropna().unique().tolist())
    entregador = st.selectbox("Entregador", ["Todos"] + entregadores)

    data_ini = st.date_input("Data inicial")
    data_fim = st.date_input("Data final")

    dias_especificos = st.multiselect("Filtrar por dias do mês", list(range(1, 32)))

    turnos = sorted(df["periodo"].dropna().unique())
    turnos_escolhidos = st.multiselect("Turnos", turnos)

    pracas_disponiveis = sorted(df["praca"].dropna().unique())
    pracas = st.multiselect("Praças", pracas_disponiveis)

    if st.button("Gerar relatório detalhado"):
        df_filtrado = filtrar_dados_avancado(
            df,
            data_ini=data_ini,
            data_fim=data_fim,
            dias_especificos=dias_especificos,
            turnos=turnos_escolhidos,
            pracas=pracas,
            entregador=entregador
        )

        if df_filtrado.empty:
            st.warning("Nenhum dado encontrado com os filtros aplicados.")
            return

        # Indicadores gerais
        ofertadas = int(df_filtrado["numero_de_corridas_ofertadas"].sum())
        aceitas = int(df_filtrado["numero_de_corridas_aceitas"].sum())
        rejeitadas = int(df_filtrado["numero_de_corridas_rejeitadas"].sum())
        completas = int(df_filtrado["numero_de_corridas_completadas"].sum())

        tx_aceitas = round(aceitas / ofertadas * 100, 1) if ofertadas else 0.0
        tx_rejeitadas = round(rejeitadas / ofertadas * 100, 1) if ofertadas else 0.0
        tx_completas = round(completas / aceitas * 100, 1) if aceitas else 0.0

        st.markdown(f"""
        ### 🚗 Corridas (com base nos filtros):
        - 📦 Ofertadas: `{ofertadas}`
        - 👍 Aceitas: `{aceitas}` ({tx_aceitas}%)
        - 👎 Rejeitadas: `{rejeitadas}` ({tx_rejeitadas}%)
        - 🏁 Completadas: `{completas}` ({tx_completas}%)
        """)

        resumo = consolidar_turnos_por_nome(df_filtrado)
        st.dataframe(resumo)

        media_presenca = resumo['percentual_presenca'].mean().round(1)
        st.markdown(f"### 📊 Média de Presença: {media_presenca}%")

        csv = resumo.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Baixar CSV", csv, "relatorio_detalhado.csv", "text/csv")