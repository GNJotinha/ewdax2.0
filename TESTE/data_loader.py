import pandas as pd
import streamlit as st
import gdown
from utils import normalizar

@st.cache_data
def carregar_dados():
    file_id = "1Dmmg1R-xmmC0tfi5-1GVS8KLqhZJUqm5"
    url = f"https://drive.google.com/uc?id={file_id}"
    output = "Calendarios.xlsx"
    gdown.download(url, output, quiet=True)
    df = pd.read_excel(output, sheet_name="Base 2025")
    df["data_do_periodo"] = pd.to_datetime(df["data_do_periodo"])
    df["data"] = df["data_do_periodo"].dt.date
    df["mes"] = df["data_do_periodo"].dt.month
    df["ano"] = df["data_do_periodo"].dt.year
    df["pessoa_entregadora_normalizado"] = df["pessoa_entregadora"].apply(normalizar)
    return df
