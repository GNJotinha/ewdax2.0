import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
import bcrypt

TZ = ZoneInfo("America/Sao_Paulo")

# login sem espaço: 3 a 32, só a-z 0-9 . _ -
LOGIN_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


def canon_login(login: str) -> str:
    s = (login or "").strip()
    if " " in s:
        raise ValueError("Login não pode ter espaço.")
    s = s.lower()
    if not LOGIN_RE.match(s):
        raise ValueError("Login inválido. Use 3–32 chars: a-z 0-9 . _ -")
    return s


def hash_password(password: str) -> str:
    pw = (password or "").encode("utf-8")
    if len(pw) < 6:
        raise ValueError("Senha muito curta (mín. 6).")
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def _get_dsn() -> str:
    dsn = None
    try:
        dsn = st.secrets.get("SUPABASE_DB_DSN")
    except Exception:
        dsn = None

    if not dsn:
        dsn = os.environ.get("SUPABASE_DB_DSN")

    if not dsn:
        raise RuntimeError("SUPABASE_DB_DSN não configurado (Secrets ou env).")

    return dsn


def _lock_policy(failed_attempts: int):
    # 5 erros = lock 10min
    if failed_attempts >= 5:
        return True, timedelta(minutes=10)
    return False, None


def autenticar(login: str, senha: str):
    """
    Retorna SEMPRE: (ok: bool, user: dict|None, msg: str)

    user (quando ok):
      id, login, full_name, department, is_admin, must_change_password
    """
    try:
        login_norm = canon_login(login)
    except Exception as e:
        return False, None, str(e)

    senha = senha or ""
    if not senha:
        return False, None, "Informe a senha."

    try:
        import psycopg
    except Exception as e:
        return False, None, f"psycopg não instalado no ambiente. Erro: {e}"

    # conexão
    try:
        conn = psycopg.connect(_get_dsn(), connect_timeout=10)
    except Exception as e:
        return False, None, (
            "Falha ao conectar no Supabase. "
            "Se você estiver usando DSN Direct (5432/IPv6), troque pro Pooler (Transaction 6543). "
            f"Erro: {e}"
        )

    try:
        with conn.cursor() as cur:
            # pega usuário (case-insensitive)
            cur.execute(
                """
                select
                  id, login, full_name, department, is_admin, is_active,
                  password_hash, must_change_password,
                  failed_attempts, locked_until
                from public.app_users
                where lower(login) = lower(%s)
                limit 1
                """,
                (login_norm,),
            )
            row = cur.fetchone()

        if not row:
            return False, None, "Usuário não encontrado."

        (
            user_id,
            db_login,
            full_name,
            department,
            is_admin,
            is_active,
            password_hash_db,
            must_change_password,
            failed_attempts,
            locked_until,
        ) = row

        if not is_active:
            return False, None, "Usuário desativado."

        # lock
        if locked_until:
            try:
                now = datetime.now(TZ)
                if now < locked_until:
                    mins = int((locked_until - now).total_seconds() // 60) + 1
                    return False, None, f"Usuário bloqueado. Tente novamente em ~{mins} min."
            except Exception:
                pass

        # valida senha
        ok = verify_password(senha, password_hash_db)
        if not ok:
            failed_attempts = int(failed_attempts or 0) + 1
            lock, delta = _lock_policy(failed_attempts)
            new_locked_until = (datetime.now(TZ) + delta) if lock else None

            with conn.cursor() as cur:
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
            return False, None, "Senha incorreta."

        # sucesso: zera tentativas + last_login
        with conn.cursor() as cur:
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
            "login": str(db_login),  # mantém como tá no banco (BALA, bala, etc)
            "full_name": str(full_name),
            "department": str(department),
            "is_admin": bool(is_admin),
            "must_change_password": bool(must_change_password),
        }
        return True, user, "ok"

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, None, f"Erro ao consultar/validar usuário no Supabase: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


def is_admin() -> bool:
    return bool(st.session_state.get("is_admin"))


def require_admin():
    if not is_admin():
        st.error("Acesso exclusivo de Administrador.")
        st.stop()
