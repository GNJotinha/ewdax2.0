import streamlit as st
from auth import autenticar, USUARIOS
from data_loader import carregar_dados
from relatorios import (
    gerar_dados, gerar_simplicado, gerar_alertas_de_faltas, get_entregadores
)
from promocoes_loader import carregar_promocoes, estruturar_promocoes
from utils import calcular_tempo_online
import pandas as pd
from datetime import datetime, time

# Autenticação
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""

if not st.session_state.logado:
    st.title("🔐 Login do Painel")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if autenticar(usuario, senha):
            st.session_state.logado = True
            st.session_state.usuario = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()

# Página principal
st.set_page_config(page_title="Painel de Entregadores", page_icon="📋")
st.sidebar.success(f"Bem-vindo, {st.session_state.usuario}!")

modo = st.sidebar.radio("Escolha uma opção:", [
    "📈 Apurador de Promoções",
    "📊 Indicadores Gerais",
    "Ver geral",
    "Simplificada (WhatsApp)",
    "Alertas de Faltas",
    "Relatório Customizado"
], key="modo_radio")

df = carregar_dados()
entregadores = get_entregadores(df)

nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
if nivel == "admin":
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

# Modo de Apurador de Promoções
if modo == "📈 Apurador de Promoções":
    st.title("📈 Apurador de Promoções")

    # Conversão de datas
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["data_date"] = df["data"].dt.date

    df_promocoes, df_fases, df_criterios, df_faixas = carregar_promocoes()
    PROMOCOES = estruturar_promocoes(df_promocoes, df_fases, df_criterios, df_faixas)

    nomes_promos = [p["nome"] for p in P]()_
