import importlib
import pandas as pd
import streamlit as st

from auth import autenticar
from data_loader import carregar_dados


st.set_page_config(
    page_title="Painel de Entregadores",
    initial_sidebar_state="collapsed",  # sidebar fica OFF via CSS
)


def inject_css(path="assets/style.css"):
    with open(path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


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
    try:
        dtmax = pd.to_datetime(df[col], errors="coerce").max()
        if pd.notna(dtmax):
            return dtmax.strftime("%d/%m/%Y")
    except Exception:
        pass
    return ""


def _logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def _goto(module: str, cat=None):
    st.session_state.module = module
    st.session_state.open_cat = cat
    st.rerun()


def _toggle_left_menu():
    st.session_state.show_left_menu = not st.session_state.get("show_left_menu", False)
    st.rerun()


def _render_topbar(df: pd.DataFrame):
    last_day = _last_date_str(df)

    st.markdown("<div class='app-topbar'>", unsafe_allow_html=True)

    left, right = st.columns([3.2, 2.2], vertical_alignment="center")

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
        c0, c1, c2, c3, c4 = st.columns([0.65, 0.65, 1.05, 1.05, 0.65])

        # botão NOVO: abre/fecha menu na esquerda
        with c0:
            if st.button("≡", type="secondary", use_container_width=True, key="tb_leftmenu"):
                _toggle_left_menu()

        # home (ícone)
        with c1:
            if st.button("⌂", type="secondary", use_container_width=True, key="tb_home"):
                _goto("views.home", None)

        with c2:
            if st.button("Perfil", type="secondary", use_container_width=True, key="tb_profile"):
                _goto("views.perfil", None)

        with c3:
            if st.button("Sair", type="secondary", use_container_width=True, key="tb_logout"):
                _logout()
                st.rerun()

        # botão da direita reservado (sem navegação)
        with c4:
            with st.popover("⋯", use_container_width=True):
                st.caption("Reservado")

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='tb-divider'></div>", unsafe_allow_html=True)


def _render_left_menu(menu: dict):
    st.markdown("<div class='left-drawer'>", unsafe_allow_html=True)

    # Admin aqui (Usuários / Auditoria) — sai do popover da direita
    if st.session_state.get("is_admin"):
        a1, a2 = st.columns(2)
        with a1:
            if st.button("Usuários", use_container_width=True, key="lm_admin_users"):
                _goto("views.admin_usuarios", None)
        with a2:
            if st.button("Auditoria", use_container_width=True, key="lm_admin_audit"):
                _goto("views.auditoria", None)

        st.markdown("<div class='left-divider'></div>", unsafe_allow_html=True)

    q = st.text_input(
        "",
        key="lm_q",
        placeholder="Buscar tela…",
        label_visibility="collapsed",
    ).strip().lower()

    for cat, opts in menu.items():
        if q:
            hits = {lbl: mod for lbl, mod in opts.items() if q in lbl.lower() or q in cat.lower()}
            if not hits:
                continue
            opts_to_show = hits
        else:
            opts_to_show = opts

        expanded = (st.session_state.get("open_cat") == cat)
        with st.expander(cat, expanded=expanded):
            for label, module in opts_to_show.items():
                if st.button(label, use_container_width=True, key=f"lm_{cat}_{label}"):
                    st.session_state.open_cat = cat
                    _goto(module, cat)

    st.markdown("</div>", unsafe_allow_html=True)


# ---------------- Estado inicial ----------------
st.session_state.setdefault("logado", False)
st.session_state.setdefault("usuario", "")
st.session_state.setdefault("module", "views.home")
st.session_state.setdefault("open_cat", None)
st.session_state.setdefault("show_left_menu", False)


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


# ---------------- MENU (mesmo de antes) ----------------
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

# ---------------- Layout: Drawer esquerda + conteúdo ----------------
if st.session_state.get("show_left_menu", False):
    col_menu, col_main = st.columns([1.15, 2.85], gap="large")
    with col_menu:
        _render_left_menu(MENU)

    with col_main:
        try:
            page = importlib.import_module(st.session_state.module)
        except Exception as e:
            st.error(f"Erro ao carregar módulo **{st.session_state.module}**: {e}")
        else:
            page.render(df, {})
else:
    try:
        page = importlib.import_module(st.session_state.module)
    except Exception as e:
        st.error(f"Erro ao carregar módulo **{st.session_state.module}**: {e}")
    else:
        page.render(df, {})
