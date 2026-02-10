import os
import json
from contextlib import contextmanager

import psycopg
import streamlit as st


def get_dsn() -> str:
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


@contextmanager
def db_conn():
    conn = psycopg.connect(get_dsn(), connect_timeout=10)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def fetch_all(conn, sql: str, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        cols = [c.name for c in cur.description] if cur.description else []
        rows = cur.fetchall()
    return cols, rows


def ensure_table_exists(conn, table: str) -> bool:
    cols, rows = fetch_all(
        conn,
        """
        select 1
        from information_schema.tables
        where table_schema='public' and table_name=%s
        limit 1
        """,
        (table,),
    )
    return len(rows) > 0


def ensure_import_columns(conn):
    # garante colunas de "quem importou"
    with conn.cursor() as cur:
        cur.execute(
            """
            alter table public.imports
              add column if not exists imported_by_user_id uuid,
              add column if not exists imported_by_login text;
            """
        )
    conn.commit()


def audit_log(action: str, entity: str | None = None, entity_id: str | None = None, metadata: dict | None = None):
    """Loga evento no audit_log usando o usuário logado no session_state."""
    actor_user_id = st.session_state.get("user_id")
    actor_login = st.session_state.get("usuario")

    meta = metadata or {}
    try:
        meta_json = json.dumps(meta, ensure_ascii=False)
    except Exception:
        meta_json = "{}"

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.audit_log (actor_user_id, actor_login, action, entity, entity_id, metadata)
                values (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (actor_user_id, actor_login, action, entity, entity_id, meta_json),
            )
        conn.commit()
