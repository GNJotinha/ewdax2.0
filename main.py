import importlib
import streamlit as st

from auth import autenticar, USUARIOS
from data_loader import carregar_dados

# =========================================================
# 🔄 Carga ÚNICA do DF por render + suporte a hard refresh
# =========================================================
def get_df_once():
    """
    Carrega o df uma única vez por render.
    Se o usuário clicou em 'Atualizar dados', força baixar do Drive.
    """
    prefer = st.session_state.pop("force_refresh", False)
    ts = pd.Timestamp.now().timestamp() if prefer else None
    return carregar_dados(prefer_drive=prefer, _ts=ts)


# -------------------------------------------------------------------
# Config da página
# -------------------------------------------------------------------
st.set_page_config(page_title="Painel de Entregadores", page_icon="📋")

# -------------------------------------------------------------------
# Estilo
# -------------------------------------------------------------------
st.markdown(
    """
    <style>
        body { background-color: #0e1117; color: #c9d1d9; }
        .stButton>button {
            background-color: #1f6feb;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            font-weight: bold;
        }
        .stButton>button:hover { background-color: #388bfd; }
        .stSidebar { background-color: #161b22; }
        h1, h2, h3 { color: #58a6ff; }
        .stSelectbox, .stMultiSelect, .stTextInput {
            background-color: #21262d;
            color: #c9d1d9;
        }
    </style>
    """,
    unsafe_allow_html=True
)



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

user = st.session_state.usuario
nivel = USUARIOS.get(user, {}).get("nivel", "")

if nivel == "dev":  # ou "admin", se quiser
    MENU["Saídas"] = "views.saidas"


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
