import pandas as pd
import streamlit as st
from utils import normalizar

# Opção: manter suporte a Google Drive SEM usar por padrão
try:
    import gdown  # segue no requirements, mas o app funciona sem se você escolher "Local"
except Exception:
    gdown = None

@st.cache_data(show_spinner=False)
def carregar_dados(
    fonte: str = "Local",                       # "Local" (padrão) ou "Drive"
    caminho_local: str = "Calendarios.xlsx",     # usado quando fonte=="Local"
    aba: str = "Base 2025",                      # nome da planilha
    file_id: str = "1Dmmg1R-xmmC0tfi5-1GVS8KLqhZJUqm5"  # usado quando fonte=="Drive"
):
    """
    Lê os dados da planilha local (padrão) ou do Google Drive.
    Cria colunas auxiliares e normaliza nomes de entregadores.
    """
    if fonte == "Drive":
        if gdown is None:
            raise RuntimeError("gdown não está disponível nesta execução. Selecione 'Local' ou instale gdown.")
        url = f"https://drive.google.com/uc?id={file_id}"
        output = "Calendarios.xlsx"
        gdown.download(url, output, quiet=True)
        df = pd.read_excel(output, sheet_name=aba)
    else:
        df = pd.read_excel(caminho_local, sheet_name=aba)

    # Colunas auxiliares
    df["data_do_periodo"] = pd.to_datetime(df["data_do_periodo"])
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)
    
    return df
