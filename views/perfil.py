import streamlit as st
import bcrypt

from db import db_conn, audit_log
from auth import canon_login, hash_password, verify_password


DEPARTAMENTOS = ["Administrador", "Operacional", "Financeiro", "Desenvolvedor"]  # <-- aqui


def render(_df, _USUARIOS):
    st.markdown("# 👤 Meu Perfil")

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("Sessão inválida. Faz login de novo.")
        st.stop()

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select login, full_name, department, is_admin, is_active, must_change_password, last_login_at
                from public.app_users
                where id=%s
                """,
                (user_id,),
            )
            row = cur.fetchone()

    if not row:
        st.error("Usuário não encontrado no banco.")
        st.stop()

    login, full_name, department, is_admin, is_active, must_change_password, last_login_at = row

    c1, c2 = st.columns([1.2, 1.0])
    with c1:
        st.write(f"**Nome:** {full_name}")

        # ✅ Admin consegue mudar o próprio departamento aqui
        if is_admin:
            dept_base = department if department in DEPARTAMENTOS else (DEPARTAMENTOS[0] if DEPARTAMENTOS else "")
            new_dept = st.selectbox(
                "Departamento",
                DEPARTAMENTOS,
                index=DEPARTAMENTOS.index(dept_base) if dept_base in DEPARTAMENTOS else 0,
                key="profile_dept",
            )

            if st.button("Salvar departamento", use_container_width=True, key="btn_save_dept"):
                if new_dept == department:
                    st.info("Nada mudou.")
                else:
                    with db_conn() as conn:
                        try:
                            with conn.cursor() as cur:
                                cur.execute(
                                    """
                                    update public.app_users
                                    set department=%s, updated_at=now(), updated_by=%s
                                    where id=%s
                                    """,
                                    (new_dept, user_id, user_id),
                                )
                            conn.commit()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Não consegui atualizar departamento: {e}")
                            st.stop()

                    audit_log("department_changed", "app_users", str(user_id), {"old": department, "new": new_dept})
                    st.success("Departamento atualizado!")
                    st.rerun()
        else:
            st.write(f"**Departamento:** {department}")

        st.write(f"**Admin:** {'Sim' if is_admin else 'Não'}")
        st.write(f"**Ativo:** {'Sim' if is_active else 'Não'}")

    with c2:
        st.write(f"**Login atual:** `{login}`")
        if last_login_at:
            st.caption(f"Último login: {str(last_login_at)}")
        if must_change_password:
            st.warning("Você precisa trocar sua senha (primeiro acesso / reset).")

    st.divider()

    st.markdown("## ✏️ Alterar login (apelido)")
    new_login = st.text_input("Novo login (sem espaço)", value=str(login), help="3–32 chars: a-z 0-9 . _ -").strip()

    if st.button("Salvar login", use_container_width=True):
        try:
            new_login2 = canon_login(new_login)
        except Exception as e:
            st.error(str(e))
            return

        if new_login2 == str(login).lower():
            st.info("Nada mudou.")
            return

        with db_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        update public.app_users
                        set login=%s, updated_at=now(), updated_by=%s
                        where id=%s
                        """,
                        (new_login2, user_id, user_id),
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                st.error(f"Não consegui atualizar login (talvez já exista): {e}")
                return

        audit_log("nickname_changed", "app_users", user_id, {"old": str(login), "new": new_login2})

        # atualiza sessão
        st.session_state.usuario = new_login2
        st.success("Login atualizado!")
        st.rerun()

    st.divider()

    st.markdown("## 🔑 Trocar senha")
    old_pw = st.text_input("Senha atual", type="password")
    new_pw = st.text_input("Nova senha", type="password")
    new_pw2 = st.text_input("Confirmar nova senha", type="password")

    if st.button("Trocar senha", use_container_width=True):
        if new_pw != new_pw2:
            st.error("Nova senha e confirmação não batem.")
            return

        if len(new_pw or "") < 6:
            st.error("Senha muito curta (mínimo 6).")
            return

        # valida senha atual
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("select password_hash from public.app_users where id=%s", (user_id,))
                pw_hash = cur.fetchone()[0]

            if not verify_password(old_pw or "", pw_hash):
                audit_log("password_change_failed", "app_users", user_id, {"reason": "wrong_old_password"})
                st.error("Senha atual incorreta.")
                return

            new_hash = hash_password(new_pw)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    update public.app_users
                    set password_hash=%s,
                        must_change_password=false,
                        updated_at=now(),
                        updated_by=%s
                    where id=%s
                    """,
                    (new_hash, user_id, user_id),
                )
            conn.commit()

        audit_log("password_changed", "app_users", user_id, {})
        st.success("Senha trocada com sucesso!")
        st.rerun()
