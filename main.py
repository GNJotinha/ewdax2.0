# main.py
# ============================================================
# SISTEMA MOVEE — MAIN
# ============================================================

import streamlit as st
import importlib
import pandas as pd
from data_loader import carregar_dados
from auth import autenticar
from utils import aplicar_estilo

# ============================================================
# CONFIGURAÇÃO INICIAL
# ============================================================
st.set_page_config(
    page_title="Sistema Movee",
    layout="wide",
    page_icon="🟢"
)
aplicar_estilo()

# ============================================================
# CARREGAR USUÁRIOS / PERMISSÕES
# ============================================================
USUARIOS = st.secrets.get("USUARIOS", {})
USUARIOS_PRIVADOS = st.secrets.get("USUARIOS_PRIVADOS", {})

# ============================================================
# MENU BASE (todas as páginas públicas)
# ============================================================
MENU_BASE = {
    "Desempenho do Entregador": {
        "Ver geral": "views.ver_geral",
        "Simplificada (WhatsApp)": "views.simplificada",
        "Relatório Customizado": "views.relatorio_custom",
        "Perfil do Entregador": "views.perfil_entregador",
    },
    "Relatórios": {
        "Alertas de Faltas": "views.faltas",
        "Relação de Entregadores": "views.relacao",
        "Categorias de Entregadores": "views.categorias",
        "Relatórios Subpraças": "views.rel_subpraca",
        "Resumos": "views.resumos",
        "Lista de Ativos": "views.lista_ativos",
        "Comparar ativos": "views.comparar",
        # "Saídas (privado)" não aparece aqui — será injetado dinamicamente
    },
    "Dashboards": {
        "UTR": "views.utr",
        "Indicadores Gerais": "views.indicadores",
    },
}

# ============================================================
# ESTADO INICIAL
# ============================================================
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""
if "module" not in st.session_state:
    st.session_state.module = "views.home"

# ============================================================
# LOGIN
# ============================================================
if not st.session_state.logado:
    usuario, senha = autenticar()
    if usuario:
        st.session_state.usuario = usuario
        st.session_state.logado = True
        st.experimental_rerun()
    st.stop()

# ============================================================
# CARREGAR DADOS
# ============================================================
with st.spinner("Carregando dados..."):
    df = carregar_dados()

# ============================================================
# MENU LATERAL (dinâmico)
# ============================================================
user = st.session_state.get("usuario", "")
allowed_saidas = set(USUARIOS_PRIVADOS.get("SAIDAS", []))

# Clona o menu base
MENU = {k: dict(v) for k, v in MENU_BASE.items()}

# 🔒 Adiciona “Saídas (privado)” só pra quem pode
if user in allowed_saidas:
    MENU.setdefault("Relatórios", {})
    MENU["Relatórios"]["Saídas (privado)"] = "views.saidas"

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.image("https://i.imgur.com/p3vjjKZ.png", width=180)
    st.markdown("---")
    st.markdown(f"👤 **Usuário:** `{user}`")
    st.markdown("---")

    # Montar menu dinâmico
    selected_section = st.selectbox("📂 Módulo", list(MENU.keys()))
    selected_page = st.selectbox(
        "📄 Página",
        list(MENU[selected_section].keys())
    )

    st.session_state.module = MENU[selected_section][selected_page]

    st.markdown("---")
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.logado = False
        st.session_state.usuario = ""
        st.experimental_rerun()

# ============================================================
# RENDERIZAR PÁGINA SELECIONADA
# ============================================================
try:
    mod = importlib.import_module(st.session_state.module)
    mod.render(df, USUARIOS)
except Exception as e:
    st.error(f"Erro ao carregar a página: {e}")
