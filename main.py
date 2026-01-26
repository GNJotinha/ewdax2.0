import importlib
import pandas as pd
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from auth import autenticar, USUARIOS
from data_loader import carregar_dados

TZ = ZoneInfo("America/Sao_Paulo")

def get_df_once():
    prefer = st.session_state.pop("force_refresh", False)
    ts = pd.Timestamp.now().timestamp() if prefer else None
    return carregar_dados(prefer_drive=prefer, _ts=ts)

st.set_page_config(
    page_title="Painel de Entregadores",
    page_icon="📋",
    initial_sidebar_state="expanded"
)

# =========================
# CSS GLOBAL (PATCH FINAL)
# =========================
st.markdown(
    """
    <style>
    :root{
      --bg: #0b0f14;
      --text: #e8edf6;
    }

    /* ❌ NÃO matar o header */
    header[data-testid="stHeader"]{
      background: transparent !important;
      box-shadow: none !important;
      border: 0 !important;
    }

    /* ❌ esconde toolbar feia */
    header [data-testid="stToolbar"]{
      visibility: hidden !important;
    }

    /* ✅ FORÇA botão ☰ do sidebar */
    header [data-testid="collapsedControl"]{
      visibility: visible !important;
      display: flex !important;
      position: fixed !important;
      top: 0.75rem !important;
      left: 0.75rem !important;
      z-index: 999999 !important;
    }

    #MainMenu{ visibility:hidden !important; }
    footer{ display:none !important; }
    div[data-testid="stDecoration"]{ display:none !important; }

    body{
      background:
        linear-gradient(180deg, #070a0f 0%, #0b0f14 100%);
      color: var(--text);
    }

    section[data-testid="stSidebar"]{
      background: rgba(18,22,30,.95);
      border-right: 1px solid rgba(255,255,255,.08);
    }

    .stButton>button{
      background: linear-gradient(135deg, #58a6ff, #3b82f6);
      color: white;
      border-radius: 14px;
      font-weight: 800;
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

st.sidebar.success(f"Bem-vindo, {st.session_state.usuario}!")

MENU = {
    "Promoção da virada": {"Ranking": "views.promo_virada"},
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

def _sig_ok_now() -> bool:
    ok = bool(st.session_state.get("_sig_ok"))
    if not ok:
        return False
    until = st.session_state.get("_sig_until")
    if until is None:
        return True
    try:
        dt_until = datetime.fromisoformat(until)
    except Exception:
        return False
    return datetime.now(TZ) <= dt_until

with st.sidebar:
    st.markdown("### Navegação")

    if st.button("Início", use_container_width=True):
        st.session_state.module = "views.home"
        st.session_state.open_cat = None
        st.rerun()

    admins_list = set(st.secrets.get("ADMINS", []))
    user_entry = USUARIOS.get(st.session_state.usuario, {}) or {}
    nivel = user_entry.get("nivel", "")
    is_sigiloso = (nivel in ("admin", "dev")) or (st.session_state.usuario in admins_list)

    if is_sigiloso:
        with st.expander("Acesso restrito"):
            if st.button("Comparativo entregador", use_container_width=True):
                st.session_state.sig_target = "by_entregador"
                st.session_state.module = "views.auditoria_sigilosa" if st.session_state.get("_sig_ok") else "views.auditoria_gate"
                st.session_state.open_cat = None
                st.rerun()

            if st.button("Comparativo geral", use_container_width=True):
                st.session_state.sig_target = "geral"
                st.session_state.module = "views.auditoria_sigilosa" if st.session_state.get("_sig_ok") else "views.auditoria_gate"
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
mod = st.session_state.module
if mod in ("views.auditoria_sigilosa", "views.auditoria_gate"):
    df = pd.DataFrame()
else:
    df = get_df_once()
    if st.session_state.pop("just_refreshed", False):
        st.success("✅ Base atualizada a partir do Google Drive.")

# --------------- Roteador ---------------
try:
    page = importlib.import_module(st.session_state.module)
except Exception as e:
    st.error(f"Erro ao carregar módulo **{st.session_state.module}**: {e}")
else:
    page.render(df, USUARIOS)
