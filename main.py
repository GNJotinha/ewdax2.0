import importlib
import pandas as pd
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from auth import autenticar, USUARIOS
from data_loader import carregar_dados

TZ = ZoneInfo("America/Sao_Paulo")

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
st.markdown("""
<style>
/* Centraliza e limita largura do conteúdo principal */
.block-container {
  max-width: 1100px !important;
  padding-top: 2.0rem;
}

/* "Shell" do painel (moldura grande) */
.panel-shell {
  background: radial-gradient(1200px 400px at 20% 0%, rgba(255,255,255,0.06), transparent 60%),
              linear-gradient(180deg, rgba(255,255,255,0.04), rgba(0,0,0,0.10));
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 22px;
  padding: 18px 18px 22px 18px;
  box-shadow: 0 25px 60px rgba(0,0,0,0.55);
}

/* Topbar dentro do painel */
.panel-topbar {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap: 12px;
  background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 16px;
  padding: 12px 14px;
  margin-bottom: 14px;
}

.panel-topbar .left {
  display:flex;
  align-items:center;
  gap:10px;
  color:#f3f4f6;
  font-weight:700;
}

.panel-topbar .meta {
  margin-top:2px;
  color:#9ca3af;
  font-size:0.82rem;
  font-weight:500;
}

/* Linha divisória sutil dentro do painel */
.panel-divider {
  height:1px;
  background: rgba(255,255,255,0.08);
  margin: 14px 0;
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

# ---------------------------------------------------------
# Helper: validade do acesso sigiloso
# ---------------------------------------------------------
def _sig_ok_now() -> bool:
    ok = bool(st.session_state.get("_sig_ok"))
    if not ok:
        return False
    until = st.session_state.get("_sig_until")  # ISO str ou None (sessão-only)
    if until is None:
        return True
    try:
        dt_until = datetime.fromisoformat(until)
    except Exception:
        return False
    return datetime.now(TZ) <= dt_until

# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### Navegação")
    # Botão Home dedicado
    if st.button("Início", use_container_width=True):
        st.session_state.module = "views.home"
        st.session_state.open_cat = None
        st.rerun()

    # --- Área Sigilosa no menu esquerdo (apenas admin/dev) ---
    admins_list = set(st.secrets.get("ADMINS", []))
    user_entry = USUARIOS.get(st.session_state.usuario, {}) or {}
    nivel = user_entry.get("nivel", "")
    is_sigiloso = (nivel in ("admin", "dev")) or (st.session_state.usuario in admins_list)

    if is_sigiloso:
        with st.expander("Acesso restrito", expanded=False):
            # Lista por entregador
            if st.button("Comparativo entregador", use_container_width=True):
                st.session_state.sig_target = "by_entregador"
                if st.session_state.get("_sig_ok"):  # já validou nesta sessão
                    st.session_state.sig_modo = "by_entregador"
                    st.session_state.module = "views.auditoria_sigilosa"
                else:
                    st.session_state.module = "views.auditoria_gate"
                st.session_state.open_cat = None
                st.rerun()

            # Lista geral
            if st.button("Comparativo geral", use_container_width=True):
                st.session_state.sig_target = "geral"
                if st.session_state.get("_sig_ok"):  # já validou nesta sessão
                    st.session_state.sig_modo = "geral"
                    st.session_state.module = "views.auditoria_sigilosa"
                else:
                    st.session_state.module = "views.auditoria_gate"
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
# Dados (evita carregar a base inteira na área sigilosa)
# ---------------------------------------------------------
mod = st.session_state.module
if mod in ("views.auditoria_sigilosa", "views.auditoria_gate"):
    df = pd.DataFrame()  # não precisa aqui
else:
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
