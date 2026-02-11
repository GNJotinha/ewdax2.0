import importlib
import pandas as pd
import streamlit as st

from auth import autenticar
from data_loader import carregar_dados


def get_df_once():
    force = st.session_state.pop("force_refresh", False)
    ts = pd.Timestamp.now().timestamp() if force else None
    return carregar_dados(prefer_drive=False, _ts=ts)


st.set_page_config(
    page_title="Painel de Entregadores",
    initial_sidebar_state="expanded",
)


def inject_css(path="assets/style.css"):
    with open(path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


inject_css()


# ---------------- Estado inicial ----------------
st.session_state.setdefault("logado", False)
st.session_state.setdefault("usuario", "")
st.session_state.setdefault("module", "views.home")
st.session_state.setdefault("open_cat", None)


# ---------------- Login ----------------
if not st.session_state.logado:
    st.title("Login")
    login = st.text_input("Login").strip().lower()
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar", use_container_width=True):
        ok, user, msg = autenticar(login, senha)
        if ok:
            st.session_state.logado = True
            st.session_state.user_id = user["id"]
            st.session_state.usuario = user["login"]
            st.session_state.full_name = user["full_name"]
            st.session_state.department = user["department"]
            st.session_state.is_admin = user["is_admin"]
            st.session_state.must_change_password = user["must_change_password"]

            st.session_state.show_welcome = True

            if st.session_state.must_change_password:
                st.session_state.module = "views.perfil"
            else:
                st.session_state.module = "views.home"

            st.rerun()
        else:
            st.error(msg)

    st.stop()


# ---------------- MENU ----------------
MENU = {
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
        "Elegibilidade": "views.elegibilidade_prioridade",
        "Confirmação de Turno (Mensagens)": "views.confirmacao_turno",
    },
    "Dashboards": {
        "UTR": "views.utr",
        "Indicadores Gerais": "views.indicadores",
    },
    "Dados": {
        "Importar CSV": "views.upload",
    },
}

# deixa acessível na Home
st.session_state["MENU"] = MENU


# ---------------- Sidebar (só navegação) ----------------
with st.sidebar:
    if st.button("Início", use_container_width=True, type="secondary", key="sb_home"):
        st.session_state.module = "views.home"
        st.session_state.open_cat = None
        st.rerun()

    st.markdown("### Navegação")

    for cat, opts in MENU.items():
        expanded = (st.session_state.open_cat == cat)
        with st.expander(cat, expanded=expanded):
            for label, module in opts.items():
                if st.button(label, key=f"btn_{cat}_{label}", use_container_width=True):
                    st.session_state.module = module
                    st.session_state.open_cat = cat
                    st.rerun()


# ---------------- Toast de boas-vindas ----------------
if st.session_state.pop("show_welcome", False):
    msg = f"Bem-vindo, {st.session_state.usuario}!"
    if hasattr(st, "toast"):
        try:
            st.toast(msg)
        except Exception:
            st.info(msg)
    else:
        st.info(msg)


# ---------------- Dados ----------------
df = get_df_once()

fonte = getattr(df, "attrs", {}).get("fonte", "base")
st.sidebar.caption(f"Fonte de dados: {fonte}")

if st.session_state.pop("just_refreshed", False):
    st.success(f"Base atualizada ({fonte}).")


# ---------------- Roteador ----------------
try:
    page = importlib.import_module(st.session_state.module)
except Exception as e:
    st.error(f"Erro ao carregar módulo **{st.session_state.module}**: {e}")
else:
    page.render(df, {})
