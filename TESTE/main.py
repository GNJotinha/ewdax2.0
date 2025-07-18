import streamlit as st
import pandas as pd
from relatorio_detalhado import relatorio_detalhado

st.set_page_config(page_title="Relatório Detalhado", layout="wide")

st.title("📊 Painel de Entregadores – Relatório Detalhado")

# Simulação de carregamento do DataFrame principal (substitua pela leitura real da planilha)
@st.cache_data
def carregar_dados():
    # Exemplo de simulação, deve ser trocado por leitura de planilha real
    return pd.read_excel("Calendarios.xlsx")

df = carregar_dados()

relatorio_detalhado(df)