import pandas as pd
import streamlit as st

from db import db_conn
from auth import require_admin


def render(_df, _USUARIOS):
    require_admin()
    st.markdown("# 🧾 Auditoria")

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        actor = st.text_input("Filtrar por login (quem fez)")
    with c2:
        action = st.text_input("Filtrar por ação (ex: import_csv_done)")
    with c3:
        limit = st.number_input("Limite", min_value=50, max_value=2000, value=300, step=50)

    where = []
    params = []

    if actor.strip():
        where.append("lower(actor_login) like lower(%s)")
        params.append(f"%{actor.strip()}%")

    if action.strip():
        where.append("lower(action) like lower(%s)")
        params.append(f"%{action.strip()}%")

    where_sql = ("where " + " and ".join(where)) if where else ""

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                select ts, actor_login, action, entity, entity_id, metadata
                from public.audit_log
                {where_sql}
                order by ts desc
                limit %s
                """,
                tuple(params + [int(limit)]),
            )
            rows = cur.fetchall()

    if not rows:
        st.info("Nada encontrado.")
        return

    df = pd.DataFrame(rows, columns=["ts", "actor_login", "action", "entity", "entity_id", "metadata"])
    st.dataframe(df, use_container_width=True)
