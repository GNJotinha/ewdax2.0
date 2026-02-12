import importlib
import pandas as pd
import streamlit as st

from auth import autenticar
from data_loader import carregar_dados


# ---------------- Config ----------------
st.set_page_config(
    page_title="Painel de Entregadores",
    initial_sidebar_state="expanded",  # menu lateral ON
)


def inject_css():
    for path in ("assets/style.css", "style.css"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
            return
        except FileNotFoundError:
            continue


inject_css()


def get_df_once():
    force = st.session_state.pop("force_refresh", False)
    ts = pd.Timestamp.now().timestamp() if force else None
    return carregar_dados(prefer_drive=False, _ts=ts)


def _pick_col(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    return None


def _last_date_str(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""
    col = _pick_col(list(df.columns), ["data_do_periodo", "data", "Data", "DATA", "dt", "timestamp", "ts"])
    if not col:
        return ""
    dtmax = pd.to_datetime(df[col], errors="coerce").max()
    if pd.notna(dtmax):
        return dtmax.strftime("%d/%m/%Y")
    return ""


def _logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def _goto(module: str, cat=None):
    st.session_state.module = module
    st.session_state.open_cat = cat
    st.rerun()


def _render_topbar(df: pd.DataFrame):
    last_day = _last_date_str(df)

    st.markdown("<div class='app-topbar'>", unsafe_allow_html=True)

    left, right = st.columns([3.4, 2.0], vertical_alignment="center")

    with left:
        st.markdown(
            f"""
            <div class="tb-left">
              <div class="tb-title">Painel de Entregadores</div>
              <div class="tb-meta">Último dia na base: <b>{last_day or "—"}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        c1, c2, c3, c4 = st.columns([0.65, 1.05, 1.05, 0.65])

        with c1:
            if st.button("⌂", type="secondary", use_container_width=True, key="tb_home"):
                _goto("views.home", None)
    
    with c2:
        if st.button("Perfil", type="secondary", use_container_width=True, key="tb_profile"):
            # "Perfil" aqui é SEMPRE o meu perfil, então limpa alvo do admin
            for k in ("profile_target_user_id", "perfil_target_user_id", "profile_back_module"):
                st.session_state.pop(k, None)
    
            _goto("views.perfil", None)

        with c3:
            if st.button("Sair", type="secondary", use_container_width=True, key="tb_logout"):
                _logout()
                st.rerun()

        # ✅ bagulho da direita: só admin
        with c4:
            with st.popover("≡", use_container_width=True):
                if st.session_state.get("is_admin"):
                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button("Usuários", use_container_width=True, key="pop_admin_users"):
                            _goto("views.admin_usuarios", None)
                    with a2:
                        if st.button("Auditoria", use_container_width=True, key="pop_admin_audit"):
                            _goto("views.auditoria", None)
                else:
                    st.caption("Sem opções de admin.")

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='tb-divider'></div>", unsafe_allow_html=True)


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
            st.session_state.module = "views.perfil" if st.session_state.must_change_password else "views.home"
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
st.session_state["MENU"] = MENU


# ---------------- Sidebar (UMA vez só) ----------------
with st.sidebar:

    for cat, opts in MENU.items():
        expanded = (st.session_state.open_cat == cat)
        with st.expander(cat, expanded=expanded):
            for label, module in opts.items():
                if st.button(label, key=f"sb_{cat}_{label}", use_container_width=True):
                    st.session_state.module = module
                    st.session_state.open_cat = cat
                    st.rerun()


# ---------------- Toast ----------------
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


# ---------------- Topbar ----------------
_render_topbar(df)


# ---------------- Roteador ----------------
try:
    page = importlib.import_module(st.session_state.module)
except Exception as e:
    st.error(f"Erro ao carregar módulo **{st.session_state.module}**: {e}")
else:
    page.render(df, {})
