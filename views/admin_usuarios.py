from zoneinfo import ZoneInfo
import secrets

import pandas as pd
import streamlit as st

from db import db_conn, audit_log
from auth import require_admin, canon_login, hash_password


TZ_LOCAL = ZoneInfo("America/Sao_Paulo")
DEPARTAMENTOS = ["Administrador", "Operacional", "Financeiro","Desenvolvedor"]
PAGE_SIZE = 40

# views
K_VIEW = "adm_users_view"  # "list" | "create"
K_PAGE = "adm_users_page"

# criar usuário
K_C_NAME = "adm_create_full_name"
K_C_LOGIN = "adm_create_login"
K_C_DEPT = "adm_create_dept"
K_C_ADMIN = "adm_create_is_admin"
K_C_ACTIVE = "adm_create_is_active"
K_C_PW = "adm_create_password"
K_C_MUST = "adm_create_must_change"


def _init_defaults():
    st.session_state.setdefault(K_VIEW, "list")
    st.session_state.setdefault(K_PAGE, 0)

    st.session_state.setdefault(K_C_NAME, "")
    st.session_state.setdefault(K_C_LOGIN, "")
    st.session_state.setdefault(K_C_DEPT, "Operacional")
    st.session_state.setdefault(K_C_ADMIN, False)
    st.session_state.setdefault(K_C_ACTIVE, True)
    st.session_state.setdefault(K_C_PW, "")
    st.session_state.setdefault(K_C_MUST, True)


def _toggle(label: str, value: bool, key: str):
    """Fallback: st.toggle se existir, senão st.checkbox."""
    if hasattr(st, "toggle"):
        return st.toggle(label, value=value, key=key)
    return st.checkbox(label, value=value, key=key)


def _fmt_dt(x):
    if not x:
        return "—"
    try:
        dt = pd.to_datetime(x, utc=True, errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(x, errors="coerce")
        if pd.isna(dt):
            return str(x)
        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        return dt.tz_convert(TZ_LOCAL).tz_localize(None).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(x)


def _fetch_users_page(conn, page: int):
    offset = page * PAGE_SIZE
    sql = """
    select
      id, login, full_name, department, is_admin, is_active, must_change_password, last_login_at,
      count(*) over() as total_count
    from public.app_users
    order by lower(full_name), lower(login)
    limit %s offset %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (PAGE_SIZE + 1, offset))
        rows = cur.fetchall()

    if not rows:
        return 0, False, []

    total = int(rows[0][-1] or 0)
    has_next = len(rows) > PAGE_SIZE
    rows = [r[:-1] for r in rows[:PAGE_SIZE]]
    return total, has_next, rows


def _goto_profile(user_id: str):
    st.session_state["profile_target_user_id"] = str(user_id)

    # guarda pra onde voltar
    st.session_state["profile_back_module"] = "views.admin_usuarios"
    st.session_state["adm_users_view"] = "list"  # garante lista quando voltar

    st.session_state.module = "views.perfil"
    st.session_state.open_cat = None
    st.rerun()



def _gen_temp_password() -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#%&*"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def _clear_create_form():
    st.session_state[K_C_NAME] = ""
    st.session_state[K_C_LOGIN] = ""
    st.session_state[K_C_DEPT] = "Operacional"
    st.session_state[K_C_ADMIN] = False
    st.session_state[K_C_ACTIVE] = True
    st.session_state[K_C_PW] = ""
    st.session_state[K_C_MUST] = True


def _render_create_view():
    st.markdown("# Criar usuário")

    if st.button("⬅️ Voltar", use_container_width=True):
        st.session_state[K_VIEW] = "list"
        st.rerun()

    st.divider()

    a, b = st.columns([1, 1])
    with a:
        if st.button("🎲 Gerar senha", use_container_width=True):
            st.session_state[K_C_PW] = _gen_temp_password()
    with b:
        if st.button("🧹 Limpar", use_container_width=True):
            _clear_create_form()
            st.rerun()

    if st.session_state.get(K_C_PW):
        st.info(f"Senha atual (copie): `{st.session_state[K_C_PW]}`")

    with st.form("form_create_user"):
        st.text_input("Nome completo", key=K_C_NAME)
        st.text_input("Login (apelido)", key=K_C_LOGIN, help="3–32 chars: a-z 0-9 . _ -")

        c1, c2, c3 = st.columns([1.2, 1.0, 1.0])
        with c1:
            st.selectbox("Departamento", DEPARTAMENTOS, key=K_C_DEPT)
        with c2:
            _toggle("Admin?", bool(st.session_state[K_C_ADMIN]), key=K_C_ADMIN)
        with c3:
            _toggle("Ativo?", bool(st.session_state[K_C_ACTIVE]), key=K_C_ACTIVE)

        st.text_input("Senha inicial", type="password", key=K_C_PW)
        _toggle("Forçar troca de senha no 1º login?", bool(st.session_state[K_C_MUST]), key=K_C_MUST)

        ok = st.form_submit_button("✅ Criar usuário", use_container_width=True)

    if not ok:
        return

    full_name = (st.session_state[K_C_NAME] or "").strip()
    login_in = (st.session_state[K_C_LOGIN] or "").strip().lower()
    dept = st.session_state[K_C_DEPT]
    is_admin = bool(st.session_state[K_C_ADMIN])
    is_active = bool(st.session_state[K_C_ACTIVE])
    temp_pw = st.session_state[K_C_PW] or ""
    must_change = bool(st.session_state[K_C_MUST])
    actor_id = st.session_state.get("user_id")

    if not full_name:
        st.error("Nome obrigatório.")
        st.stop()

    try:
        login2 = canon_login(login_in)
    except Exception as e:
        st.error(str(e))
        st.stop()

    if not temp_pw or len(temp_pw) < 6:
        st.error("Senha inicial obrigatória (mínimo 6).")
        st.stop()

    pw_hash = hash_password(temp_pw)

    with db_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    insert into public.app_users
                    (login, full_name, department, is_admin, is_active,
                     password_hash, must_change_password, created_by, updated_by)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    returning id
                    """,
                    (login2, full_name, dept, is_admin, is_active, pw_hash, must_change, actor_id, actor_id),
                )
                new_id = cur.fetchone()[0]
                conn.commit()
            except Exception as e:
                conn.rollback()
                st.error(f"Erro ao criar (login já existe?): {e}")
                st.stop()

    audit_log("user_created", "app_users", str(new_id), {"login": login2, "department": dept, "is_admin": is_admin})
    st.success("Usuário criado!")

    if st.button("Voltar pra lista", use_container_width=True):
        _clear_create_form()
        st.session_state[K_VIEW] = "list"
        st.session_state[K_PAGE] = 0
        st.rerun()


def _render_list_view():
    # topo limpo: só título + botão criar
    left, right = st.columns([6, 2])
    with left:
        st.markdown("# Usuários")
    with right:
        if st.button("➕ Criar usuário", use_container_width=True):
            st.session_state[K_VIEW] = "create"
            st.rerun()

    page = max(0, int(st.session_state.get(K_PAGE, 0)))

    with db_conn() as conn:
        with st.spinner("Carregando usuários…"):
            total, has_next, rows = _fetch_users_page(conn, page)

    if total == 0:
        st.info("Nenhum usuário encontrado.")
        return

    # lista
    for (uid, login, full_name, dept, is_admin, is_active, must_change, last_login_at) in rows:
        try:
            box = st.container(border=True)
        except TypeError:
            box = st.container()

        with box:
            try:
                a, b, c, d = st.columns([2.8, 1.1, 1.3, 1.4], vertical_alignment="center")
            except Exception:
                a, b, c, d = st.columns([2.8, 1.1, 1.3, 1.4])

            with a:
                # Nome clicável -> dentro só "Exibir perfil"
                label = f"{full_name}  (@{login})"
                with st.expander(label, expanded=False):
                    if st.button("👁️ Exibir perfil", use_container_width=True, key=f"view_{uid}"):
                        _goto_profile(uid)

            with b:
                st.markdown(f"<span class='user-pill'>{dept}</span>", unsafe_allow_html=True)

            with c:
                st.markdown(
                    f"<span class='user-pill {'ok' if is_active else 'bad'}'>{'ATIVO' if is_active else 'INATIVO'}</span>",
                    unsafe_allow_html=True,
                )
                if is_admin:
                    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
                    st.markdown("<span class='user-pill admin'>ADMIN</span>", unsafe_allow_html=True)
                if must_change:
                    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
                    st.markdown("<span class='user-pill warn'>TROCAR SENHA</span>", unsafe_allow_html=True)

            with d:
                st.markdown(
                    f"<div class='user-lastlogin'>Último login<br><b>{_fmt_dt(last_login_at)}</b></div>",
                    unsafe_allow_html=True,
                )

    # paginação
    st.divider()
    left, mid, right = st.columns([1, 6, 1])

    offset = page * PAGE_SIZE
    shown = len(rows)
    start_n = offset + 1
    end_n = offset + shown
    max_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    with left:
        if st.button("⬅️", disabled=(page == 0), key="btn_users_prev"):
            st.session_state[K_PAGE] = page - 1
            st.rerun()
    with mid:
        st.markdown(
            f"<div style='text-align:center; padding-top:6px;'><b>Página {page+1}/{max_pages}</b> — {start_n} a {end_n} de {total}</div>",
            unsafe_allow_html=True,
        )
    with right:
        if st.button("➡️", disabled=(not has_next), key="btn_users_next"):
            st.session_state[K_PAGE] = page + 1
            st.rerun()


def render(_df, _USUARIOS):
    require_admin()
    _init_defaults()

    if st.session_state.get(K_VIEW) == "create":
        _render_create_view()
    else:
        _render_list_view()
