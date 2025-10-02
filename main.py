import importlib
import streamlit as st

from auth import autenticar, USUARIOS
from data_loader import carregar_dados

# ---------------------------------------------------------
# Config
# ---------------------------------------------------------
st.set_page_config(page_title="Painel de Entregadores", page_icon="📋", layout="wide")

# THEME CSS — cola inteiro abaixo do set_page_config
st.markdown("""
<style>
:root{
  --bg:#0E1117;
  --bg-2:#151A24;
  --sidebar:#1B212D;
  --accent:#00BFFF;   /* cor principal */
  --accent-2:#1E90FF; /* hover */
  --text:#F5F7FA;
  --muted:#9AA4B2;
  --card:#0F1520;
  --border:#232B3A;
  --shadow:0 10px 30px rgba(0,0,0,.35);
}

/* fundo geral */
html, body, [data-testid="stAppViewContainer"]{
  background: var(--bg) !important;
  color: var(--text) !important;
}

/* topo do app */
header[data-testid="stHeader"]{
  background: linear-gradient(180deg, rgba(0,0,0,.25), rgba(0,0,0,0)) !important;
  border-bottom: 1px solid var(--border) !important;
}

/* sidebar */
section[data-testid="stSidebar"]{
  background: var(--sidebar) !important;
  border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] .stAlert{
  background: linear-gradient(180deg, #1f2937 0%, #111827 100%) !important;
  border: 1px solid var(--border) !important;
  border-radius: 14px !important;
}
section[data-testid="stSidebar"] h1, 
section[data-testid="stSidebar"] h2, 
section[data-testid="stSidebar"] h3{
  color: var(--text) !important;
}

/* botões genéricos */
.stButton>button{
  background: var(--accent) !important;
  color: #ffffff !important;
  border: 0 !important;
  border-radius: 14px !important;
  padding: .75rem 1rem !important;
  font-weight: 700 !important;
  box-shadow: var(--shadow) !important;
  transition: all .15s ease-in-out !important;
}
.stButton>button:hover{ background: var(--accent-2) !important; transform: translateY(-1px); }
.stButton>button:active{ transform: translateY(0); }

/* botões da sidebar (inclui os dentro de expanders) */
section[data-testid="stSidebar"] .stButton>button{
  width: 100% !important;
  margin-bottom: .35rem !important;
  background: linear-gradient(180deg, var(--accent) 0%, #00a6ff 100%) !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"]{
  background: var(--bg-2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 14px !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary{
  color: var(--text) !important;
  font-weight: 700 !important;
}

/* inputs / selects */
.stTextInput>div>div>input,
.stPassword>div>div>input,
.stSelectbox>div>div>div{
  background: var(--bg-2) !important;
  color: var(--text) !important;
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
}

/* métricas mais elegantes */
[data-testid="stMetric"]{
  background: var(--card) !important;
  border: 1px solid var(--border) !important;
  border-radius: 16px !important;
  padding: .9rem .95rem !important;
  box-shadow: var(--shadow);
}
[data-testid="stMetricLabel"]{ color: var(--muted) !important; font-weight:600!important;}
[data-testid="stMetricValue"]{ color: #ffffff !important; font-weight:800!important; letter-spacing:.2px;}

/* separadores */
hr{ border-color: var(--border) !important; }

/* tabelas */
[data-testid="stDataFrame"]{
  background: var(--card) !important;
  border-radius: 14px !important;
  border: 1px solid var(--border) !important;
}

/* alerts/info */
.stAlert{
  border-radius: 14px !important;
  border: 1px solid var(--border) !important;
  background: var(--bg-2) !important;
}

/* títulos principais */
h1, h2, h3{
  color: var(--text) !important;
  text-shadow: 0 2px 24px rgba(0,0,0,.35);
}

/* espaçamento compacto */
.block-container{ padding-top: 1.2rem !important; }

/* botão download */
.stDownloadButton>button{
  background: transparent !important;
  color: var(--accent) !important;
  border: 1px solid var(--accent) !important;
}
.stDownloadButton>button:hover{
  background: var(--accent) !important;
  color: #0E1117 !important;
}

/* cards leves para colunas (usa st.container) */
.card{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1rem 1.1rem;
  box-shadow: var(--shadow);
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Estado inicial
# ---------------------------------------------------------
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""

if "module" not in st.session_state:
    # default = Home
    st.session_state.module = "views.home"

if "open_cat" not in st.session_state:
    st.session_state.open_cat = None

# ---------------------------------------------------------
# Login
# ---------------------------------------------------------
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

st.sidebar.success(f"Bem-vindo, {st.session_state.usuario}!")

# ---------------------------------------------------------
# Menu (sem item duplicado de Início)
# ---------------------------------------------------------
MENU = {
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
    },
    "Dashboards": {
        "UTR": "views.utr",
        "Indicadores Gerais": "views.indicadores",
    },
}

with st.sidebar:
    st.markdown("### Navegação")
    # Botão Home dedicado
    if st.button("Início", use_container_width=True):
        st.session_state.module = "views.home"
        st.session_state.open_cat = None
        st.rerun()

    # Submenus
    for cat, opts in MENU.items():
        if isinstance(opts, str):
            if st.button(cat, use_container_width=True):
                st.session_state.module = opts
                st.session_state.open_cat = None
                st.rerun()
        else:
            expanded = (st.session_state.open_cat == cat)
            with st.expander(cat, expanded=expanded):
                for label, module in opts.items():
                    if st.button(label, key=f"btn_{cat}_{label}", use_container_width=True):
                        st.session_state.module = module
                        st.session_state.open_cat = cat
                        st.rerun()

# ---------------------------------------------------------
# Dados (suporta refresh disparado pela Home)
# ---------------------------------------------------------
df = carregar_dados(prefer_drive=st.session_state.pop("force_refresh", False))

if st.session_state.pop("just_refreshed", False):
    st.success("✅ Base atualizada a partir do Google Drive.")

# ---------------------------------------------------------
# Roteador
# ---------------------------------------------------------
try:
    page = importlib.import_module(st.session_state.module)
except Exception as e:
    st.error(f"Erro ao carregar módulo **{st.session_state.module}**: {e}")
else:
    page.render(df, USUARIOS)
