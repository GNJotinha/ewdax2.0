import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import bcrypt
import streamlit as st

from db import db_conn, audit_log

TZ = ZoneInfo("America/Sao_Paulo")

LOGIN_RE = re.compile(r"^[a-z0-9._-]{3,32}$")  # sem espaço


def canon_login(login: str) -> str:
    s = (login or "").strip().lower()
    if " " in s:
        raise ValueError("Login não pode ter espaço.")
    if not LOGIN_RE.match(s):
        raise ValueError("Login inválido. Use 3–32 chars: a-z 0-9 . _ -")
    return s


def hash_password(password: str) -> str:
    pw = (password or "").encode("utf-8")
    if len(pw) < 6:
        raise ValueError("Senha muito curta (mínimo 6).")
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def _lock_policy(failed_attempts: int):
    # simples e útil
    # 5 tentativas erradas = lock de 10 minutos
    if failed_attempts >= 5:
        return True, timedelta(minutes=10)
    return False, None


def autenticar(login: str, senha: str):
    """
    Retorna (ok: bool, user: dict|None, msg: str)
    user contém: id, login, full_name, department, is_admin, must_change_password
    """
    try:
        login = canon_login(login)
    except Exception as e:
        return False, None, str(e)

    senha = senha or ""
    if not senha:
        return False, None, "Informe a senha."

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, login, full_name, department, is_admin, is_active,
                       password_hash, must_change_password,
                       failed_attempts, locked_until
                from public.app_users
                where lower(login)=lower(%s)
                limit 1
                """,
                (login,),
            )
            row = cur.fetchone()

            if not row:
                audit_log("login_failed", "app_users", login, {"reason": "user_not_found"})
                return False, None, "Usuário não encontrado."

            (
                user_id, db_login, full_name, department, is_admin, is_active,
                password_hash_db, must_change, failed_attempts, locked_until
            ) = row

            if not is_active:
                audit_log("login_failed", "app_users", str(user_id), {"reason": "inactive"})
                return False, None, "Usuário desativado."

            if locked_until and datetime.now(TZ) < locked_until:
                mins = int((locked_until - datetime.now(TZ)).total_seconds() // 60) + 1
                audit_log("login_failed", "app_users", str(user_id), {"reason": "locked"})
                return False, None, f"Usuário bloqueado. Tenta de novo em ~{mins} min."

            ok = verify_password(senha, password_hash_db)
            if not ok:
                failed_attempts = int(failed_attempts or 0) + 1
                lock, delta = _lock_policy(failed_attempts)
                new_locked_until = (datetime.now(TZ) + delta) if lock else None

                cur.execute(
                    """
                    update public.app_users
                    set failed_attempts=%s,
                        locked_until=%s,
                        updated_at=now()
                    where id=%s
                    """,
                    (failed_attempts, new_locked_until, user_id),
                )
                conn.commit()

                audit_log("login_failed", "app_users", str(user_id), {"reason": "wrong_password"})
                return False, None, "Senha incorreta."

            # sucesso: zera tentativas, atualiza last_login
            cur.execute(
                """
                update public.app_users
                set failed_attempts=0,
                    locked_until=null,
                    last_login_at=now(),
                    updated_at=now()
                where id=%s
                """,
                (user_id,),
            )
            conn.commit()

    user = {
        "id": str(user_id),
        "login": db_login,
        "full_name": full_name,
        "department": department,
        "is_admin": bool(is_admin),
        "must_change_password": bool(must_change),
    }

    audit_log("login_success", "app_users", user["id"], {"login": user["login"]})
    return True, user, "ok"


def is_admin() -> bool:
    return bool(st.session_state.get("is_admin"))


def require_admin():
    if not is_admin():
        st.error("Acesso exclusivo de Administrador.")
        st.stop()
