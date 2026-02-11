import importlib
import pandas as pd
import streamlit as st

from auth import autenticar
from data_loader import carregar_dados

try:
    from db import db_conn
except Exception:
    db_conn = None


# ---------------- Config ----------------
st.set_page_config(
    page_title="Painel de Entregadores",
    initial_sidebar_state="collapsed",  # deixa limpo; navegação vai pro topo
)


def inject_css(path="assets/style.css"):
    # se teu arquivo estiver na raiz, troca pra "style.css"
    with open(path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


inject_css()


# ---------------- Helpers ----------------
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


@st.cache_data(ttl=60)
def _get_last_import_label():
    """
    Puxa último arquivo importado (quando existir).
    Cache curto pra não ficar batendo no banco toda hora.
    """
    if db_conn is None:
        return ""
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select file_name, uploaded_at
                    from public.imports
                    where uploaded_at is not null
                    order by uploaded_at desc
                    limit 1
                    """
                )
                r = cur.fetchone()

        if not r:
            return ""

        fname, ts = r
        try:
            ts_fmt = pd.to_datetime(ts, utc=True, errors="coerce")
            if pd.notna(ts_fmt):
                ts_fmt = ts_fmt.tz_convert("America/Sao_Paulo").tz_localize(None)
                return f"Último upload: {str(fname)} • {ts_fmt.strftime('%d/%m %H:%M')}"
        except Exception:
            pass

        return f"Último upload: {str(fname)}"
    except Exception:
        return ""


def _render_topbar(df: pd.DataFrame, fonte: str):
    last_day = _last_date_str(df)
    last_import = _get_last_import_label()

    left, right = st.columns([3.6, 1.9], vertical_alignment="center")

    with left:
        st.markdown(
            f"""
            <div class="tb-left">
              <div class="tb-title">Painel de Entregadores</div>
              <div class="tb-meta">
                Último dia na base: <b>{last_day or "—"}</b>
                {f'<span class="tb-chip">{fonte}</span>' if fonte else ""}
                {f'<span class="tb-chip tb-chip-muted">{last_import}</span>' if last_import else ""}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        b1, b2, b3, b4 = st.columns([1.25, 0.9, 0.9, 0.55])

        with b1:
            if st.button("Atualizar base", use_container_width=True, key="tb_refresh"):
                st.session_state.force_refresh = True
                st.session_state.just_refreshed = True
                try:
                    st.cache_data.clear()
                except Exception:
                    pass
                st.rerun()

        with b2:
            if st.button("Perfil", type="secondary", use_container_width=True, key="tb_profile"):
                _goto("views.perfil", None)

        with b3:
            if st.button("Sair", type="secondary", use_container_width=True, key="tb_logout"):
                _logout()
                st.rerun()

        with b4:
            with st.popover("≡", use_container_width=True):
                st.markdown("### Navegação")

                q = st.text_input(
                    "Buscar",
                    key="tb_menu_q",
                    label_visibility="collapsed",
                    placeholder="Buscar tela…",
                ).strip().lower()

                if st.button("Início", use_container_width=True, key="tb_go_home"):
                    _goto("views.home", None)

                if st.session_state.get("is_admin"):
                    with st.expander("Admin", expanded=False):
                        if st.button("Usuários", use_container_width=True, key="tb_admin_users"):
                            _goto("views.admin_usuarios", None)
                        if st.button("Auditoria", use_container_width=True, key="tb_admin_audit"):
                            _goto("views.auditoria", None)

                for cat, opts in st.session_state.get("MENU", {}).items():
                    if q:
                        hits = {lbl: mod for lbl, mod in opts.items() if q in lbl.lower() or q in cat.lower()}
                        if not hits:
                            continue
                        opts_to_show = hits
                    else:
                        opts_to_show = opts

                    with st.expander(cat, expanded=False):
                        for label, module in opts_to_show.items():
                            if st.button(label, use_container_width=True, key=f"tb_{cat}_{label}"):
                                _goto(module, cat)

                st.divider()
                st.caption(f"Login: {st.session_state.get('usuario', '-')}")
                st.caption(f"Departamento: {st.session_state.get('department', '-')}")

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


# ---------------- Sidebar (fallback) ----------------
with st.sidebar:
    st.caption("Navegação (fallback)")
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
fonte = getattr(df, "attrs", {}).get("fonte", "base")

if st.session_state.pop("just_refreshed", False):
    st.success(f"Base atualizada ({fonte}).")


# ---------------- Topbar global ----------------
_render_topbar(df, fonte)


# ---------------- Roteador ----------------
try:
    page = importlib.import_module(st.session_state.module)
except Exception as e:
    st.error(f"Erro ao carregar módulo {st.session_state.module}: {e}")
else:
    page.render(df, {})
