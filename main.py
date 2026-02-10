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

    /* =============================
       FIX DO SIDEBAR (Cloud)
       - NÃO esconder o header
       ============================= */
    header[data-testid="stHeader"]{
      background: transparent !important;
      box-shadow: none !important;
      border: 0 !important;
    }

    header [data-testid="stToolbar"]{
      visibility: hidden !important;
    }

    /* =============================
       ✅ MATA O BOTÃO SAFADO "<<" (recolher)
       Ele fica no header do sidebar.
       Isso deixa o sidebar fixo aberto.
       ============================= */
    div[data-testid="stSidebarHeader"] button[data-testid="baseButton-header"],
    div[data-testid="stSidebarHeader"] button[kind="headerNoPadding"]{
      display: none !important;
    }

    /* Fallback: algumas versões usam aria-label/title */
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

    /* mantém o botão de ABRIR caso o Cloud inicie fechado (não mexe nisso) */
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

    .neo-shell{
      position: relative;
      border-radius: 22px;
      padding: 18px 18px 22px 18px;
      background: rgba(255,255,255,.03) !important;
      border: 1px solid rgba(255,255,255,.08);
      box-shadow:
        0 28px 70px rgba(0,0,0,.60) !important,
        inset 0 1px 0 rgba(255,255,255,.05);
      overflow: hidden;
    }
    .neo-shell::before,
    .neo-shell::after{
      display:none !important;
      content:none !important;
    }

    .neo-divider{
      height: 1px;
      background: rgba(255,255,255,.08);
      margin: 14px 0;
    }

    .neo-section{
      font-size: 1.2rem;
      font-weight: 900;
      margin: 6px 2px 12px 2px;
      color: rgba(232,237,246,.92);
    }

    .neo-grid-4{
      display:grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .neo-grid-2{
      display:grid;
      grid-template-columns: 340px 1fr;
      gap: 14px;
      align-items: stretch;
    }

    .neo-card{
      position: relative;
      border-radius: 16px;
      padding: 16px 16px 14px 16px;
      background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02));
      border: 1px solid rgba(255,255,255,.09);
      box-shadow:
        0 16px 34px rgba(0,0,0,.40),
        inset 0 1px 0 rgba(255,255,255,.05);
      overflow:hidden;
      min-height: 120px;
    }
    .neo-card:after{
      content:"";
      position:absolute;
      inset:-1px;
      border-radius: 16px;
      padding: 1px;
      background: linear-gradient(135deg, rgba(88,166,255,.22), rgba(167,139,250,.12), rgba(0,212,255,.12));
      -webkit-mask:
        linear-gradient(#000 0 0) content-box,
        linear-gradient(#000 0 0);
      -webkit-mask-composite: xor;
      mask-composite: exclude;
      pointer-events:none;
      opacity:.65;
    }

    .neo-label{
      font-size: .92rem;
      font-weight: 800;
      letter-spacing: .02em;
      color: rgba(232,237,246,.85);
      margin-bottom: 10px;
    }

    .neo-value{
      font-size: 2.3rem;
      font-weight: 950;
      letter-spacing: .4px;
      line-height: 1.05;
      color: rgba(255,255,255,.96);
    }

    .neo-value .pct{
      display:block;
      margin-top: 6px;
      font-size: 1.65rem;
      font-weight: 900;
      letter-spacing: .2px;
      color: rgba(232,237,246,.92);
      opacity: .95;
    }

    .neo-subline{
      margin-top: 10px;
      font-size: .90rem;
      color: rgba(232,237,246,.70);
      font-weight: 650;
    }

    .neo-success{ border-color: rgba(55,214,122,.22); }
    .neo-success .neo-value{ color: rgba(160,255,205,.98); }

    .neo-danger{ border-color: rgba(255,77,77,.22); }
    .neo-danger .neo-value{ color: rgba(255,110,110,.98); }

    .neo-progress-wrap{ margin-top: 14px; }
    .neo-progress{
      width:100%;
      height: 12px;
      border-radius: 999px;
      background: rgba(255,255,255,.08);
      border: 1px solid rgba(255,255,255,.10);
      overflow:hidden;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
    }
    .neo-progress > div{
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg,
        rgba(255,77,77,.95),
        rgba(255,176,32,.95),
        rgba(55,214,122,.95),
        rgba(0,212,255,.80)
      );
      filter: drop-shadow(0 6px 14px rgba(0,0,0,.35));
    }
    .neo-scale{
      display:flex;
      justify-content:space-between;
      margin-top: 8px;
      font-size: .88rem;
      color: rgba(232,237,246,.60);
      font-weight: 700;
    }

    @media (max-width: 1100px){
      .neo-grid-4{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .neo-grid-2{ grid-template-columns: 1fr; }
    }
    .toprow{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:12px;
      margin: 10px 0;
      padding: 8px 10px;
      border-radius: 12px;
      background: rgba(255,255,255,.03);
      border: 1px solid rgba(255,255,255,.06);
    }
    .toprow .name{
      font-weight: 800;
      color: rgba(232,237,246,.92);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .toprow .hours{
      font-weight: 900;
      color: rgba(232,237,246,.70);
      flex-shrink: 0;
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


# --------------- Dados ---------------
mod = st.session_state.module
if mod in ("views.auditoria_sigilosa", "views.auditoria_gate"):
    df = pd.DataFrame()
else:
    df = get_df_once()
    fonte = df.attrs.get("fonte", "?")
    st.sidebar.caption(f"📦 Fonte de dados: {fonte}")
    if st.session_state.pop("just_refreshed", False):
        fonte = getattr(df, "attrs", {}).get("fonte", "dados")
        st.success(f"✅ Base atualizada a partir do {fonte}.")

# --------------- Roteador ---------------
try:
    page = importlib.import_module(st.session_state.module)
except Exception as e:
    st.error(f"Erro ao carregar módulo **{st.session_state.module}**: {e}")
else:
    page.render(df, USUARIOS)
