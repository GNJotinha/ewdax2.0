import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
import bcrypt

TZ = ZoneInfo("America/Sao_Paulo")

# Fallback antigo (se você ainda tiver USUARIOS no secrets)
USUARIOS = {}
try:
    USUARIOS = st.secrets.get("USUARIOS", {}) or {}
except Exception:
    USUARIOS = {}


LOGIN_RE = re.compile(r"^[a-z0-9._-]{3,32}$")  # sem espaço


def canon_login(login: str) -> str:
    s = (login or "").strip().lower()
    if " " in s:
        raise ValueError("Login não pode ter espaço.")
    if not LOGIN_RE.match(s):
        raise ValueError("Login inválido. Use 3–32 chars: a-z 0-9 . _ -")
    return s


def _get_dsn() -> str | None:
    try:
        dsn = st.secrets.get("SUPABASE_DB_DSN")
        if dsn:
            return dsn
    except Exception:
        pass

    dsn = os.environ.get("SUPABASE_DB_DSN")
    return dsn or None


def _db_enabled() -> bool:
    dsn = _get_dsn()
    if not dsn:
        return False

    try:
        import psycopg  # noqa
        return True
    except Exception:
        return False


def _table_exists(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            select 1
            from information_schema.tables
            where table_schema='public' and table_name=%s
            limit 1
            """,
            (table,),
        )
        return cur.fetchone() is not None


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def autenticar(login: str, senha: str):
    """
    SEMPRE retorna: (ok: bool, user: dict|None, msg: str)

    user contém (quando ok):
      id, login, full_name, department, is_admin, must_change_password
    """
    try:
        login = canon_login(login)
    except Exception as e:
        return False, None, str(e)

    senha = senha or ""
    if not senha:
        return False, None, "Informe a senha."

    # =========================
    # 1) TENTA BANCO (Supabase)
    # =========================
    if _db_enabled():
        try:
            import psycopg

            dsn = _get_dsn()
            conn = psycopg.connect(dsn, connect_timeout=8)
            try:
                if _table_exists(conn, "app_users"):
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
                        return False, None, "Usuário não encontrado."

                    (
                        user_id, db_login, full_name, department, is_admin, is_active,
                        password_hash_db, must_change, failed_attempts, locked_until
                    ) = row

                    if not is_active:
                        return False, None, "Usuário desativado."

                    if locked_until:
                        try:
                            now = datetime.now(TZ)
                            if now < locked_until:
                                mins = int((locked_until - now).total_seconds() // 60) + 1
                                return False, None, f"Usuário bloqueado. Tente em ~{mins} min."
                        except Exception:
                            pass

                    ok = _verify_password(senha, password_hash_db)
                    if not ok:
                        # incrementa tentativas e trava com 5 erros por 10 min (simples e útil)
                        failed_attempts = int(failed_attempts or 0) + 1
                        new_locked_until = None
                        if failed_attempts >= 5:
                            new_locked_until = datetime.now(TZ) + timedelta(minutes=10)

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

                    # sucesso: zera tentativas, atualiza last_login
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
                        "login": str(db_login),
                        "full_name": str(full_name),
                        "department": str(department),
                        "is_admin": bool(is_admin),
                        "must_change_password": bool(must_change),
                    }
                    return True, user, "ok"

            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        except Exception:
            # se deu ruim no banco, NÃO derruba o app: cai pro fallback
            pass

    # =========================
    # 2) FALLBACK: USUARIOS secrets
    # =========================
    if login in USUARIOS:
        entry = USUARIOS.get(login)

        # formatos aceitos:
        # USUARIOS[login] = {"senha": "...", "department": "...", "is_admin": true, "full_name": "..."}
        # ou USUARIOS[login] = "senha"
        if isinstance(entry, dict):
            senha_ok = (entry.get("senha") == senha) or (entry.get("password") == senha)
            if not senha_ok:
                return False, None, "Senha incorreta."

            dept = entry.get("department") or entry.get("setor") or entry.get("departamento") or "Operacional"
            # se no secrets antigo tiver "nivel": "admin"
            nivel = (entry.get("nivel") or "").lower()
            is_admin = bool(entry.get("is_admin")) or (nivel == "admin") or (dept.lower() == "administrador")

            user = {
                "id": login,  # sem uuid no fallback
                "login": login,
                "full_name": entry.get("full_name") or entry.get("nome") or login,
                "department": dept,
                "is_admin": is_admin,
                "must_change_password": False,
            }
            return True, user, "ok"

        else:
            # entry é senha direta
            if str(entry) != senha:
                return False, None, "Senha incorreta."
            user = {
                "id": login,
                "login": login,
                "full_name": login,
                "department": "Operacional",
                "is_admin": False,
                "must_change_password": False,
            }
            return True, user, "ok"

    return False, None, "Usuário não encontrado."


def is_admin() -> bool:
    return bool(st.session_state.get("is_admin"))


def require_admin():
    if not is_admin():
        st.error("Acesso exclusivo de Administrador.")
        st.stop()
