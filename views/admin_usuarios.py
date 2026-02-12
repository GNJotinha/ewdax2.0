import secrets
import streamlit as st

from db import db_conn, audit_log
from auth import canon_login, hash_password, require_admin

DEPARTAMENTOS = ["Administrador", "Operacional", "Financeiro"]


def _gen_temp_password() -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#%&*"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def _goto_users():
    st.session_state.module = "views.admin_usuarios"
    st.session_state.open_cat = None
    st.rerun()


def _toggle(label: str, value: bool, key: str):
    if hasattr(st, "toggle"):
        return st.toggle(label, value=value, key=key)
    return st.checkbox(label, value=value, key=key)


def render(_df, _USUARIOS):
    require_admin()

    st.markdown("# ➕ Admin • Criar usuário")

    top1, top2 = st.columns([1, 1])
    with top1:
        if st.button("⬅️ Voltar", use_container_width=True):
            _goto_users()
    with top2:
        st.caption("Crie com calma. Depois copie a senha e mande pro usuário.")

    st.divider()

    # Estado
    st.session_state.setdefault("cu_full_name", "")
    st.session_state.setdefault("cu_login", "")
    st.session_state.setdefault("cu_dept", "Operacional")
    st.session_state.setdefault("cu_is_admin", False)
    st.session_state.setdefault("cu_is_active", True)
    st.session_state.setdefault("cu_password", "")
    st.session_state.setdefault("cu_must_change", True)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("🎲 Gerar senha", use_container_width=True):
            st.session_state["cu_password"] = _gen_temp_password()
    with c2:
        if st.button("🧹 Limpar", use_container_width=True):
            st.session_state["cu_full_name"] = ""
            st.session_state["cu_login"] = ""
            st.session_state["cu_dept"] = "Operacional"
            st.session_state["cu_is_admin"] = False
            st.session_state["cu_is_active"] = True
            st.session_state["cu_password"] = ""
            st.session_state["cu_must_change"] = True
            st.rerun()

    if st.session_state["cu_password"]:
        st.info(f"Senha atual (copie agora): `{st.session_state['cu_password']}`")

    st.markdown("<div class='neo-section'>Dados do usuário</div>", unsafe_allow_html=True)

    with st.form("form_create_user"):
        st.text_input("Nome completo", key="cu_full_name")
        st.text_input("Login (apelido)", key="cu_login", help="3–32 chars: a-z 0-9 . _ -")

        a, b, c = st.columns([1.2, 1.0, 1.0])
        with a:
            st.selectbox("Departamento", DEPARTAMENTOS, key="cu_dept")
        with b:
            _toggle("Admin?", bool(st.session_state["cu_is_admin"]), key="cu_is_admin")
        with c:
            _toggle("Ativo?", bool(st.session_state["cu_is_active"]), key="cu_is_active")

        st.text_input("Senha inicial", type="password", key="cu_password")
        _toggle("Forçar troca de senha no 1º login?", bool(st.session_state["cu_must_change"]), key="cu_must_change")

        ok = st.form_submit_button("✅ Criar usuário", use_container_width=True)

    if not ok:
        return

    # validações
    full_name = (st.session_state["cu_full_name"] or "").strip()
    login_in = (st.session_state["cu_login"] or "").strip().lower()
    dept = st.session_state["cu_dept"]
    is_admin = bool(st.session_state["cu_is_admin"])
    is_active = bool(st.session_state["cu_is_active"])
    temp_pw = st.session_state["cu_password"] or ""
    must_change = bool(st.session_state["cu_must_change"])
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

    # insere no banco
    with db_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    insert into public.app_users
                    (login, full_name, department, is_admin, is_active, password_hash, must_change_password, created_by, updated_by)
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
    st.success("Usuário criado com sucesso!")

    # opcional: volta pra lista
    if st.button("Voltar para Usuários", use_container_width=True):
        _goto_users()
