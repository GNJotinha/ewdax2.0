import streamlit as st
import importlib
from auth import autenticar, USUARIOS
from data_loader import carregar_dados

st.set_page_config(page_title="Painel de Entregadores", page_icon="📋")

# Auth
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""

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

MENU = {
    "Início": "views.home",
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

if "modo" not in st.session_state:
    st.session_state.modo = "Início"
if "module" not in st.session_state:
    st.session_state.module = "views.home"
if "open_cat" not in st.session_state:
    st.session_state.open_cat = None

with st.sidebar:
    st.markdown("### Navegação")
    if st.button("🏠 Início", use_container_width=True):
        st.session_state.modo = "Início"
        st.session_state.module = "views.home"
        st.session_state.open_cat = None
        st.rerun()
    for cat, opts in MENU.items():
        if isinstance(opts, str):
            if st.button(cat, use_container_width=True):
                st.session_state.modo = cat
                st.session_state.module = opts
                st.session_state.open_cat = None
                st.rerun()
        else:
            expanded = (st.session_state.open_cat == cat)
            with st.expander(cat, expanded=expanded):
                for label, module in opts.items():
                    if st.button(label, key=f"btn_{cat}_{label}", use_container_width=True):
                        st.session_state.modo = label
                        st.session_state.module = module
                        st.session_state.open_cat = cat
                        st.rerun()

# Carrega dados (1x por render). Suporta refresh via botão da Home.
df = carregar_dados(prefer_drive=st.session_state.pop("force_refresh", False))

if st.session_state.pop("just_refreshed", False):
    st.success("✅ Base atualizada a partir do Google Drive.")

# Roteia
page = importlib.import_module(st.session_state.module)
page.render(df, USUARIOS)
