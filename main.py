import importlib
import streamlit as st

from auth import autenticar, USUARIOS
from data_loader import carregar_dados

# THEME — clean e funcional (sem .streamlit/config)
st.markdown("""
<style>
:root{
  /* paleta sóbria */
  --bg:#0E1117;           /* fundo */
  --sidebar:#141B25;      /* fundo sidebar */
  --card:#0F1520;         /* cartões/métricas */
  --text:#E6E9EE;         /* texto */
  --muted:#9AA4B2;        /* texto secundário */
  --border:#1F2A3A;       /* borda sutil */

  --accent:#3B82F6;       /* azul discreto */
  --accent-hover:#2563EB; /* hover */
}

/*** base ***/
html,body,[data-testid="stAppViewContainer"]{background:var(--bg)!important;color:var(--text)!important;}
header[data-testid="stHeader"]{background:transparent!important;border-bottom:1px solid rgba(255,255,255,.04)!important;}
.block-container{padding-top:1.2rem!important}

/*** sidebar ***/
section[data-testid="stSidebar"]{
  background:var(--sidebar)!important;border-right:1px solid var(--border)!important;
}
section[data-testid="stSidebar"] .stAlert{
  background:linear-gradient(180deg,#1f2937 0%,#111827 100%)!important;
  border:1px solid var(--border)!important;border-radius:12px!important;
}

/* botões da SIDEBAR: ghost elegante (sem preenchido azul) */
section[data-testid="stSidebar"] .stButton>button{
  width:100%!important;margin-bottom:.40rem!important;
  background:transparent!important;color:var(--text)!important;
  border:1px solid var(--border)!important;border-radius:12px!important;
  padding:.60rem .8rem!important;font-weight:600!important;box-shadow:none!important;
}
section[data-testid="stSidebar"] .stButton>button:hover{
  background:#182233!important;border-color:#2A3A52!important;
}

/* expanders do menu */
section[data-testid="stSidebar"] [data-testid="stExpander"]{
  background:#111823!important;border:1px solid var(--border)!important;border-radius:12px!important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary{font-weight:700!important}

/*** botões NA PÁGINA: primários (azul discreto) ***/
[data-testid="stAppViewContainer"] .stButton>button{
  background:var(--accent)!important;color:#fff!important;border:0!important;
  border-radius:14px!important;padding:.70rem 1rem!important;font-weight:700!important;
  box-shadow:0 6px 20px rgba(0,0,0,.25)!important;transition:.12s ease-in-out!important;
}
[data-testid="stAppViewContainer"] .stButton>button:hover{background:var(--accent-hover)!important;transform:translateY(-1px);}
[data-testid="stAppViewContainer"] .stButton>button:active{transform:translateY(0);}

/*** inputs ***/
.stTextInput>div>div>input,.stPassword>div>div>input,.stSelectbox>div>div>div{
  background:#0f1520!important;color:var(--text)!important;border:1px solid var(--border)!important;border-radius:12px!important;
}

/*** métricas em “card” ***/
[data-testid="stMetric"]{
  background:var(--card)!important;border:1px solid var(--border)!important;border-radius:14px!important;
  padding:.9rem .95rem!important;box-shadow:0 10px 30px rgba(0,0,0,.25);
}
[data-testid="stMetricLabel"]{color:var(--muted)!important;font-weight:600!important}
[data-testid="stMetricValue"]{color:#fff!important;font-weight:800!important;letter-spacing:.2px}

/*** tabelas & separadores ***/
[data-testid="stDataFrame"]{background:var(--card)!important;border:1px solid var(--border)!important;border-radius:12px!important}
hr{border-color:var(--border)!important}
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
