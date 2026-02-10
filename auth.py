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
    """Gera hash bcrypt (string) pra salvar em app_users.password_hash."""
    pw = (password or "").encode("utf-8")
    if len(pw) < 6:
        raise ValueError("Senha muito curta (mín. 6).")
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    """Valida senha contra hash bcrypt (inclui hash vindo do Postgres crypt(...,'bf'))."""
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


def _get_columns(conn, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema='public' and table_name=%s
            """,
            (table,),
        )
        return {r[0] for r in cur.fetchall()}


def autenticar(login: str, senha: str):
    """
    SEMPRE retorna: (ok: bool, user: dict|None, msg: str)

    user contém (quando ok):
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

    # Conecta
    try:
        conn = psycopg.connect(_get_dsn(), connect_timeout=10)
    except Exception as e:
        return False, None, (
            "Falha ao conectar no Supabase. "
            "Se estiver usando DSN Direct (5432/IPv6), troque pro Pooler (Transaction 6543). "
            f"Erro: {e}"
        )

    try:
        cols = _get_columns(conn, "app_users")
        if not cols:
            return False, None, "Tabela public.app_users não encontrada (ou sem colunas)."

        def pick(candidates):
            for c in candidates:
                if c in cols:
                    return c
            return None

        # obrigatórias
        id_col = pick(["id"])
        login_col = pick(["login"])
        full_name_col = pick(["full_name"])
        dept_col = pick(["department"])
        is_admin_col = pick(["is_admin"])
        is_active_col = pick(["is_active"])
        pw_col = pick(["password_hash"])

        missing = [name for name, col in [
            ("id", id_col),
            ("login", login_col),
            ("full_name", full_name_col),
            ("department", dept_col),
            ("is_admin", is_admin_col),
            ("is_active", is_active_col),
            ("password_hash", pw_col),
        ] if not col]
        if missing:
            return False, None, f"Tabela app_users sem colunas obrigatórias: {', '.join(missing)}"

        # opcionais
        must_change_col = pick(["must_change_password"])
        failed_attempts_col = pick(["failed_attempts"])
        locked_until_col = pick(["locked_until"])
        last_login_col = pick(["last_login_at"])
        updated_at_col = pick(["updated_at"])

        select_cols = [id_col, login_col, full_name_col, dept_col, is_admin_col, is_active_col, pw_col]
        if must_change_col:
            select_cols.append(must_change_col)
        if failed_attempts_col:
            select_cols.append(failed_attempts_col)
        if locked_until_col:
            select_cols.append(locked_until_col)

        idx = {c: i for i, c in enumerate(select_cols)}

        with conn.cursor() as cur:
            cur.execute(
                f"""
                select {", ".join(select_cols)}
                from public.app_users
                where lower({login_col}) = lower(%s)
                limit 1
                """,
                (login_norm,),
            )
            row = cur.fetchone()

        if not row:
            return False, None, "Usuário não encontrado."

        user_id = row[idx[id_col]]
        db_login = row[idx[login_col]]
        full_name = row[idx[full_name_col]]
        department = row[idx[dept_col]]
        is_admin = bool(row[idx[is_admin_col]])
        is_active = bool(row[idx[is_active_col]])
        password_hash_db = row[idx[pw_col]]

        must_change = bool(row[idx[must_change_col]]) if must_change_col else False
        failed_attempts = int(row[idx[failed_attempts_col]] or 0) if failed_attempts_col else 0
        locked_until = row[idx[locked_until_col]] if locked_until_col else None

        if not is_active:
            return False, None, "Usuário desativado."

        # lock (se existir)
        if locked_until is not None:
            try:
                now = datetime.now(TZ)
                if now < locked_until:
                    mins = int((locked_until - now).total_seconds() // 60) + 1
                    return False, None, f"Usuário bloqueado. Tente em ~{mins} min."
            except Exception:
                pass

        ok = verify_password(senha, password_hash_db)
        if not ok:
            # se tiver colunas de lockout, atualiza
            if failed_attempts_col:
                failed_attempts += 1
                new_locked_until = None
                if locked_until_col:
                    lock, delta = _lock_policy(failed_attempts)
                    new_locked_until = (datetime.now(TZ) + delta) if lock else None

                with conn.cursor() as cur:
                    sets = [f"{failed_attempts_col}=%s"]
                    params = [failed_attempts]
                    if locked_until_col:
                        sets.append(f"{locked_until_col}=%s")
                        params.append(new_locked_until)
                    if updated_at_col:
                        sets.append(f"{updated_at_col}=now()")
                    cur.execute(
                        f"update public.app_users set {', '.join(sets)} where {id_col}=%s",
                        tuple(params + [user_id]),
                    )
                conn.commit()

            return False, None, "Senha incorreta."

        # sucesso: zera lock e atualiza last_login (se existir)
        with conn.cursor() as cur:
            sets = []
            params = []

            if failed_attempts_col:
                sets.append(f"{failed_attempts_col}=%s")
                params.append(0)
            if locked_until_col:
                sets.append(f"{locked_until_col}=null")
            if last_login_col:
                sets.append(f"{last_login_col}=now()")
            if updated_at_col:
                sets.append(f"{updated_at_col}=now()")

            if sets:
                cur.execute(
                    f"update public.app_users set {', '.join(sets)} where {id_col}=%s",
                    tuple(params + [user_id]),
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
