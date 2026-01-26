import importlib
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
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
    initial_sidebar_state="expanded",  # ajuda a não iniciar fechado no Cloud
)

# ---------------- Estado inicial ----------------
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""

if "module" not in st.session_state:
    st.session_state.module = "views.home"

if "open_cat" not in st.session_state:
    st.session_state.open_cat = None

# ✅ trava sidebar por padrão (desativa o “recuar”)
if "sidebar_locked" not in st.session_state:
    st.session_state.sidebar_locked = True


# ---------------- CSS GLOBAL (tema original + fix Cloud) ----------------
BASE_CSS = r"""
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

/* ✅ NÃO mate o header (no Cloud é onde mora o controle do sidebar) */
header[data-testid="stHeader"]{
  background: transparent !important;
  box-shadow: none !important;
  border: 0 !important;
}

/* some com a toolbar do Streamlit, mas deixa header vivo */
header [data-testid="stToolbar"]{
  visibility:hidden !important;
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
"""

LOCK_SIDEBAR_CSS = r"""
/* 🔒 trava o recolher do menu lateral */
[data-testid="collapsedControl"]{
  display:none !important;
}

/* fallbacks (mudam entre versões/idiomas) */
button[aria-label*="collapse sidebar" i],
button[aria-label*="recolher" i],
button[title*="collapse sidebar" i],
button[title*="recolher" i]{
  display:none !important;
}
"""

st.markdown(
    f"<style>{BASE_CSS}{LOCK_SIDEBAR_CSS if st.session_state.sidebar_locked else ''}</style>",
    unsafe_allow_html=True
)

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

# =========================
# MENU ADAPTADO (fora do sidebar)
# =========================
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

# opções do dropdown
options = ["🏠 Início"]
for cat, items in MENU.items():
    for label in items:
        options.append(f"{cat} • {label}")

# index atual
current = "🏠 Início" if st.session_state.module == "views.home" else None
if current is None:
    for cat, items in MENU.items():
        for label, mod in items.items():
            if mod == st.session_state.module:
                current = f"{cat} • {label}"
                break
        if current:
            break
current_idx = options.index(current) if current in options else 0

c1, c2, c3 = st.columns([3, 1, 1])
with c1:
    sel = st.selectbox("Navegação rápida", options=options, index=current_idx)
with c2:
    if st.button("🧹 Recuperar menu", use_container_width=True, help="Se o Cloud travar sidebar fechada, isso tenta destravar."):
        components.html(
            """
            <script>
              try{
                const ls = window.top?.localStorage || window.parent?.localStorage || window.localStorage;
                if(ls){
                  for (const k of Object.keys(ls)) {
                    const kk = (k||"").toLowerCase();
                    if (kk.includes("sidebar") || kk.includes("collapsed") || kk.includes("streamlit")) ls.removeItem(k);
                  }
                }
              }catch(e){}
              try{
                const doc = window.top?.document || window.parent?.document || document;
                const btn = doc.querySelector('[data-testid="collapsedControl"] button')
                        || doc.querySelector('button[aria-label*="sidebar" i]')
                        || doc.querySelector('button[title*="sidebar" i]');
                if(btn) btn.click();
              }catch(e){}
              window.location.reload();
            </script>
            """,
            height=0,
        )
with c3:
    st.toggle("🔒 Travar menu lateral", key="sidebar_locked", help="Desativa o botão de recolher o sidebar.")

# aplica navegação selecionada
if sel == "🏠 Início" and st.session_state.module != "views.home":
    st.session_state.module = "views.home"
    st.session_state.open_cat = None
    st.rerun()
elif sel != "🏠 Início":
    cat, label = sel.split(" • ", 1)
    mod = MENU[cat][label]
    if st.session_state.module != mod:
        st.session_state.module = mod
        st.session_state.open_cat = cat
        st.rerun()


# =========================
# SIDEBAR (continua existindo, mas agora você não depende dele)
# =========================
st.sidebar.success(f"Bem-vindo, {st.session_state.usuario}!")

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
        with st.expander("Acesso restrito", expanded=False):
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
