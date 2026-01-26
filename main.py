import importlib
import pandas as pd
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from auth import autenticar, USUARIOS
from data_loader import carregar_dados

# =============================
# CONFIG BÁSICA
# =============================
st.set_page_config(
    page_title="Painel de Entregadores",
    page_icon="📋",
    initial_sidebar_state="expanded"  # evita iniciar fechado
)

TZ = ZoneInfo("America/Sao_Paulo")


def get_df_once():
    prefer = st.session_state.pop("force_refresh", False)
    ts = pd.Timestamp.now().timestamp() if prefer else None
    return carregar_dados(prefer_drive=prefer, _ts=ts)


# =============================
# CSS GLOBAL (SOLUÇÃO 1 AQUI)
# =============================
st.markdown(
    """
    <style>
    :root{
      --bg: #0b0f14;
      --text: #e8edf6;
      --muted: rgba(232,237,246,.70);
      --blue: #58a6ff;
      --blue2: #3b82f6;
      --cyan: #00d4ff;
      --purple: #a78bfa;
      --red: #ff4d4d;
      --orange: #ffb020;
      --green: #37d67a;
    }

    /* 🔑 SOLUÇÃO 1 — NÃO MATAR O HEADER */
    header[data-testid="stHeader"]{
      background: transparent !important;
      height: 0px !important;
      min-height: 0px !important;
      padding: 0px !important;
      margin: 0px !important;
      border: 0px !important;
    }
    header[data-testid="stHeader"] *{
      visibility: hidden !important;
    }

    footer{ display:none !important; }
    #MainMenu{ visibility:hidden !important; }
    div[data-testid="stDecoration"]{ display:none !important; }

    [data-testid="stAppViewContainer"]{
      padding-top: 0rem !important;
    }

    body{
      background:
        radial-gradient(900px 500px at 15% 10%, rgba(88,166,255,.15), transparent 60%),
        radial-gradient(700px 420px at 85% 0%, rgba(167,139,250,.14), transparent 55%),
        radial-gradient(700px 420px at 70% 95%, rgba(0,212,255,.08), transparent 55%),
        linear-gradient(180deg, #070a0f 0%, #0b0f14 45%, #0b0f14 100%);
      color: var(--text);
    }

    section[data-testid="stSidebar"]{
      background: rgba(18,22,30,.92);
      border-right: 1px solid rgba(255,255,255,.07);
    }

    .stButton>button{
      background: linear-gradient(135deg, rgba(88,166,255,.92), rgba(59,130,246,.92));
      color: white;
      border: 1px solid rgba(255,255,255,.12);
      border-radius: 14px;
      padding: .70rem 1.20rem;
      font-weight: 800;
      box-shadow: 0 12px 26px rgba(0,0,0,.45);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =============================
# ESTADO INICIAL
# =============================
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""

if "module" not in st.session_state:
    st.session_state.module = "views.home"

if "open_cat" not in st.session_state:
    st.session_state.open_cat = None


# =============================
# LOGIN
# =============================
if not st.session_state.logado:
    st.title("🔐 Login do Painel")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar", use_container_width=True):
        if autenticar(usuario, senha):
            st.session_state.logado = True
            st.session_state.usuario = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")

    st.stop()


# =============================
# SIDEBAR
# =============================
st.sidebar.success(f"Bem-vindo, {st.session_state.usuario}!")

MENU = {
    "Promoção da virada": {
        "Ranking": "views.promo_virada",
    },
    "Desempenho do Entregador": {
        "Ver geral": "views.ver_geral",
        "Simplificada (WhatsApp)": "views.simplificada",
        "Relatório Customizado": "views.relatorio_custom",
        "Perfil do Entregador": "views.perfil_entregador",
    },
    "Relatórios": {
        "Relatório de faltas": "views.faltas",
        "Relatório de faltas 2": "views.comparar",
        "Ativos": "views.ativos",
        "Comparação de datas": "views.resumos",
        "Saídas": "views.saidas",
        "Adicional por Hora (Turno)": "views.adicional_turno",
        "Lista adicional": "views.lista_adicional",
    },
    "Dashboards": {
        "UTR": "views.utr",
        "Indicadores Gerais": "views.indicadores",
    },
}

with st.sidebar:
    st.markdown("### Navegação")

    if st.button("🏠 Início", use_container_width=True):
        st.session_state.module = "views.home"
        st.session_state.open_cat = None
        st.rerun()

    for cat, opts in MENU.items():
        expanded = (st.session_state.open_cat == cat)
        with st.expander(cat, expanded=expanded):
            for label, module in opts.items():
                if st.button(label, key=f"{cat}_{label}", use_container_width=True):
                    st.session_state.module = module
                    st.session_state.open_cat = cat
                    st.rerun()


# =============================
# DADOS
# =============================
df = get_df_once()


# =============================
# ROTEADOR DE VIEWS
# =============================
try:
    page = importlib.import_module(st.session_state.module)
except Exception as e:
    st.error(f"Erro ao carregar módulo {st.session_state.module}: {e}")
else:
    page.render(df, USUARIOS)
