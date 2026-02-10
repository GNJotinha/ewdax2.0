import secrets
import streamlit as st

from db import db_conn, audit_log
from auth import canon_login, hash_password, require_admin


DEPARTAMENTOS = ["Administrador", "Operacional", "Financeiro"]


def _gen_temp_password() -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#%&*"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def render(_df, _USUARIOS):
    require_admin()

    st.markdown("# 🛠️ Admin • Usuários")

    # ------- Criar usuário -------
    with st.expander("➕ Criar novo usuário", expanded=True):
        full_name = st.text_input("Nome completo")
        login = st.text_input("Login (sem espaço) — usado pra entrar", help="3–32 chars: a-z 0-9 . _ -").strip().lower()
        department = st.selectbox("Departamento", DEPARTAMENTOS, index=1)
        is_admin = st.checkbox("É administrador?", value=False)
        is_active = st.checkbox("Ativo?", value=True)

        c1, c2 = st.columns([1, 1])
        with c1:
            temp_pw = st.text_input("Senha inicial (ou gera)", type="password")
        with c2:
            if st.button("🎲 Gerar senha", use_container_width=True):
                st.session_state._gen_pw = _gen_temp_password()
        if st.session_state.get("_gen_pw"):
            st.info(f"Senha gerada: `{st.session_state._gen_pw}` (copia e manda pra pessoa)")
            if not temp_pw:
                temp_pw = st.session_state._gen_pw

        must_change = st.checkbox("Forçar trocar senha no 1º login?", value=True)

        if st.button("Criar usuário", use_container_width=True):
            try:
                login2 = canon_login(login)
            except Exception as e:
                st.error(str(e))
                return

            if not full_name.strip():
                st.error("Nome completo é obrigatório.")
                return

            if not temp_pw:
                st.error("Informe uma senha inicial (ou gere).")
                return

            pw_hash = hash_password(temp_pw)

            actor_id = st.session_state.get("user_id")

            with db_conn() as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            insert into public.app_users
                            (login, full_name, department, is_admin, is_active, password_hash, must_change_password, created_by, updated_by)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            returning id
                            """,
                            (login2, full_name.strip(), department, is_admin, is_active, pw_hash, must_change, actor_id, actor_id),
                        )
                        new_id = cur.fetchone()[0]
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    st.error(f"Erro ao criar usuário (login já existe?): {e}")
                    return

            audit_log("user_created", "app_users", str(new_id), {"login": login2, "department": department, "is_admin": is_admin})
            st.success("Usuário criado!")
            st.rerun()

    st.divider()

    # ------- Lista / edição -------
    st.markdown("## 👥 Usuários cadastrados")

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, login, full_name, department, is_admin, is_active, must_change_password, last_login_at, created_at
                from public.app_users
                order by lower(login)
                """
            )
            rows = cur.fetchall()

    if not rows:
        st.info("Nenhum usuário cadastrado.")
        return

    # seleção
    options = {f"{r[1]} — {r[2]}": r for r in rows}
    selected_label = st.selectbox("Selecione um usuário para editar", list(options.keys()))
    r = options[selected_label]

    user_id, login, full_name, department, is_admin, is_active, must_change_password, last_login_at, created_at = r

    st.markdown("### ✏️ Editar usuário")
    e_full_name = st.text_input("Nome completo", value=full_name)
    e_login = st.text_input("Login (sem espaço)", value=login).strip().lower()
    e_dept = st.selectbox("Departamento", DEPARTAMENTOS, index=DEPARTAMENTOS.index(department) if department in DEPARTAMENTOS else 1)
    e_is_admin = st.checkbox("Administrador", value=bool(is_admin))
    e_is_active = st.checkbox("Ativo", value=bool(is_active))

    st.caption(f"ID: {user_id}")
    st.caption(f"Criado em: {created_at} | Último login: {last_login_at}")

    if st.button("Salvar alterações", use_container_width=True):
        try:
            e_login2 = canon_login(e_login)
        except Exception as e:
            st.error(str(e))
            return

        actor_id = st.session_state.get("user_id")

        with db_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        update public.app_users
                        set login=%s,
                            full_name=%s,
                            department=%s,
                            is_admin=%s,
                            is_active=%s,
                            updated_at=now(),
                            updated_by=%s
                        where id=%s
                        """,
                        (e_login2, e_full_name.strip(), e_dept, e_is_admin, e_is_active, actor_id, user_id),
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                st.error(f"Erro ao salvar (login já existe?): {e}")
                return

        audit_log(
            "user_updated",
            "app_users",
            str(user_id),
            {"login": e_login2, "department": e_dept, "is_admin": e_is_admin, "is_active": e_is_active},
        )
        st.success("Atualizado!")
        st.rerun()

    st.divider()

    st.markdown("### 🔁 Resetar senha")
    new_pw = st.text_input("Nova senha (reset)", type="password")
    force_change = st.checkbox("Forçar trocar senha no próximo login?", value=True)

    if st.button("Resetar senha", use_container_width=True):
        if not new_pw or len(new_pw) < 6:
            st.error("Informe uma senha (mín. 6).")
            return

        pw_hash = hash_password(new_pw)
        actor_id = st.session_state.get("user_id")

        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update public.app_users
                    set password_hash=%s,
                        must_change_password=%s,
                        updated_at=now(),
                        updated_by=%s
                    where id=%s
                    """,
                    (pw_hash, force_change, actor_id, user_id),
                )
            conn.commit()

        audit_log("password_reset", "app_users", str(user_id), {"target_login": login})
        st.success("Senha resetada!")
        st.rerun()
