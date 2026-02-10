import importlib
import pandas as pd
import streamlit as st
from zoneinfo import ZoneInfo

from auth import autenticar, USUARIOS
from data_loader import carregar_dados

TZ = ZoneInfo("America/Sao_Paulo")


def get_df_once():
    # Home seta force_refresh=True quando clica em "Atualizar base"
    force = st.session_state.pop("force_refresh", False)
    ts = pd.Timestamp.now().timestamp() if force else None
    return carregar_dados(prefer_drive=False, _ts=ts)


st.set_page_config(
    page_title="Painel de Entregadores",
    page_icon="📋",
    initial_sidebar_state="expanded",
)

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

    header[data-testid="stHeader"]{
      background: transparent !important;
      box-shadow: none !important;
      border: 0 !important;
    }
    header [data-testid="stToolbar"]{
      visibility: hidden !important;
    }

    /* mata o botão << do sidebar */
    div[data-testid="stSidebarHeader"] button[data-testid="baseButton-header"],
    div[data-testid="stSidebarHeader"] button[kind="headerNoPadding"]{
      display: none !important;
    }

    /* fallback por aria/title */
    div[data-testid="stSidebarHeader"] button[aria-label*="collapse" i],
    div[data-testid="stSidebarHeader"] button[aria-label*="close" i],
    div[data-testid="stSidebarHeader"] button[aria-label*="recolher" i],
    div[data-testid="stSidebarHeader"] button[aria-label*="fechar" i],
    div[data-testid="stSidebarHeader"] button[title*="collapse" i],
    div[data-testid="stSidebarHeader"] button[title*="close" i],
    div[data-testid="stSidebarHeader"] button[title*="recolher" i],
    div[data-testid="stSidebarHeader"] button[title*="fechar" i]{
      display: none !important;
    }

    [data-testid="collapsedControl"]{
      visibility: visible !important;
      z-index: 999999 !important;
    }

    footer{ display:none !important; }
    #MainMenu{ visibility:hidden !important; }
    [data-testid="stAppViewContainer"]{ padding-top: 0rem !important; }
    div[data-testid="stDecoration"]{ display:none !important; }

    body{
      background:
        radial-gradient(900px 500px at 15% 10%, rgba(88,166,255,.15), transparent 60%),
        radial-gradient(700px 420px at 85% 0%, rgba(167,139,250,.14), transparent 55%),
        radial-gradient(700px 420px at 70% 95%, rgba(0,212,255,.08), transparent 55%),
        linear-gradient(180deg, #070a0f 0%, #0b0f14 45%, #0b0f14 100%);
      color: var(--text);
    }

    .block-container{
      max-width: 1180px !important;
      padding-top: 1.2rem !important;
      padding-bottom: 2.0rem !important;
    }
    [data-testid="stVerticalBlock"]{ gap: 0.65rem; }

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
    .stButton>button:hover{
      filter: brightness(1.08);
      border-color: rgba(255,255,255,.18);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------- Estado inicial ----------------
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""

if "module" not in st.session_state:
    st.session_state.module = "views.home"

if "open_cat" not in st.session_state:
    st.session_state.open_cat = None

# ---------------- Login ----------------
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

# ---------------- Menu ----------------
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
}

with st.sidebar:
    st.success(f"Bem-vindo, {st.session_state.usuario}!")
    st.markdown("### Navegação")

    if st.button("Início", use_container_width=True):
        st.session_state.module = "views.home"
        st.session_state.open_cat = None
        st.rerun()

    for cat, opts in MENU.items():
        expanded = (st.session_state.open_cat == cat)
        with st.expander(cat, expanded=expanded):
            for label, module in opts.items():
                if st.button(label, key=f"btn_{cat}_{label}", use_container_width=True):
                    st.session_state.module = module
                    st.session_state.open_cat = cat
                    st.rerun()

# --------------- Dados ---------------
df = get_df_once()
fonte = df.attrs.get("fonte", "?")
st.sidebar.caption(f"📦 Fonte de dados: {fonte}")

if st.session_state.pop("just_refreshed", False):
    st.success(f"✅ Base atualizada a partir do {fonte}.")

# --------------- Roteador ---------------
try:
    page = importlib.import_module(st.session_state.module)
except Exception as e:
    st.error(f"Erro ao carregar módulo **{st.session_state.module}**: {e}")
else:
    page.render(df, USUARIOS)
