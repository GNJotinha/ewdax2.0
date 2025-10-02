import importlib
import streamlit as st

from auth import autenticar, USUARIOS
from data_loader import carregar_dados

st.markdown("""
<style>
:root{
  /* troque só aqui se quiser outra paleta */
  --accent:#12A4F7;      /* azul suave principal */
  --accent-hover:#0F8EDB;/* hover */
  --chip:#1E2A38;        /* contorno/realce sutil */
  --bg:#0E1117;          /* fundo */
  --text:#F4F7FA;        /* texto */
  --muted:#9AA4B2;
  --border:#223047;
  --shadow:0 8px 28px rgba(0,0,0,.35);
}

/* fundo e textos */
html, body, [data-testid="stAppViewContainer"]{
  background: var(--bg) !important; color: var(--text) !important;
}

/* SIDEBAR */
section[data-testid="stSidebar"]{
  background: #16202C !important; border-right:1px solid var(--border)!important;
}
section[data-testid="stSidebar"] .stAlert{
  background: linear-gradient(180deg,#1f2937 0%,#111827 100%)!important;
  border:1px solid var(--border)!important; border-radius:14px!important;
}

/* BOTÕES GERAIS (página) */
.stButton>button{
  background: var(--accent) !important; color:#fff!important; border:0!important;
  border-radius:14px!important; padding:.65rem 1rem!important; font-weight:700!important;
  box-shadow: var(--shadow) !important; transition: all .15s ease-in-out!important;
}
.stButton>button:hover{ background: var(--accent-hover)!important; transform: translateY(-1px); }
.stButton>button:active{ transform: translateY(0); }

/* BOTÕES DA SIDEBAR — INATIVOS = ghost elegante */
section[data-testid="stSidebar"] .stButton > button{
  width:100% !important; margin-bottom:.4rem!important; 
  background: transparent !important; color: var(--text)!important;
  border:1px solid var(--chip)!important; box-shadow:none!important;
}

/* “Ativo” (quando botão recebe focus por clique) ganha preenchido */
section[data-testid="stSidebar"] .stButton > button:focus,
section[data-testid="stSidebar"] .stButton > button:focus-visible{
  background: var(--accent)!important; color:#fff!important; outline:none!important;
  border-color: var(--accent)!important; box-shadow: var(--shadow)!important;
}

/* EXPANDERS DO MENU */
section[data-testid="stSidebar"] [data-testid="stExpander"]{
  background:#121a24!important; border:1px solid var(--chip)!important; border-radius:14px!important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary{ font-weight:700!important; }

/* INPUTS */
.stTextInput>div>div>input, .stPassword>div>div>input, .stSelectbox>div>div>div{
  background:#0f1520!important; color:var(--text)!important; border:1px solid var(--border)!important;
  border-radius:12px!important;
}

/* MÉTRICAS EM “CARD” */
[data-testid="stMetric"]{
  background:#0f1520!important; border:1px solid var(--border)!important; border-radius:16px!important;
  padding:.9rem .95rem!important; box-shadow: var(--shadow);
}
[data-testid="stMetricLabel"]{ color:var(--muted)!important; font-weight:600!important; }
[data-testid="stMetricValue"]{ color:#fff!important; font-weight:800!important; letter-spacing:.2px; }

/* DOWNLOAD “outline” */
.stDownloadButton>button{
  background:transparent!important; color:var(--accent)!important; border:1px solid var(--accent)!important;
  border-radius:12px!important;
}
.stDownloadButton>button:hover{ background:var(--accent)!important; color:#0E1117!important; }

/* separadores e tabelas */
hr{ border-color: var(--border)!important; }
[data-testid="stDataFrame"]{ background:#0f1520!important; border:1px solid var(--border)!important; border-radius:14px!important; }
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
