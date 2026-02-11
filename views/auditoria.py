import json
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db import db_conn
from auth import require_admin


TZ_LOCAL = ZoneInfo("America/Sao_Paulo")
TZ_UTC = ZoneInfo("UTC")

PAGE_SIZE = 30
K_PAGE = "audit_page"


def _safe_json(x):
    if x is None:
        return {}
    if isinstance(x, (dict, list)):
        return x
    s = str(x)
    try:
        return json.loads(s)
    except Exception:
        return {"raw": s}


def _compact_json(x, limit=2000):
    obj = _safe_json(x)
    try:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else (s[:limit] + "…")


def render(_df, _USUARIOS):
    require_admin()
    st.markdown("# 🧾 Auditoria")

    if K_PAGE not in st.session_state:
        st.session_state[K_PAGE] = 0

    page = int(st.session_state[K_PAGE])
    if page < 0:
        page = 0
        st.session_state[K_PAGE] = 0

    offset = page * PAGE_SIZE

    # Puxa 31 pra saber se existe próxima página
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select ts, actor_login, action, entity, entity_id, metadata
                from public.audit_log
                order by ts desc
                limit %s offset %s
                """,
                (PAGE_SIZE + 1, offset),
            )
            rows = cur.fetchall()

    has_next = len(rows) > PAGE_SIZE
    if has_next:
        rows = rows[:PAGE_SIZE]

    if not rows and page > 0:
        # Se por algum motivo a página ficou inválida (dados diminuíram), volta 1
        st.session_state[K_PAGE] = page - 1
        st.rerun()

    if not rows:
        st.info("Sem registros.")
        return

    df = pd.DataFrame(rows, columns=["ts", "actor_login", "action", "entity", "entity_id", "metadata"])

    # UTC -> SP, e tira tz pra formatar bonito no Streamlit
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce").dt.tz_convert(TZ_LOCAL).dt.tz_localize(None)
    df["metadata"] = df["metadata"].apply(_compact_json)

    # Grid
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ts": st.column_config.DatetimeColumn("Data/Hora (SP)", format="DD/MM/YYYY HH:mm:ss"),
            "actor_login": st.column_config.TextColumn("Quem fez"),
            "action": st.column_config.TextColumn("Ação"),
            "entity": st.column_config.TextColumn("Entidade"),
            "entity_id": st.column_config.TextColumn("ID"),
            "metadata": st.column_config.TextColumn("Metadata (compacto)"),
        },
    )

    # Paginação (setinhas embaixo)
    st.divider()
    left, mid, right = st.columns([1, 2, 1])

    with left:
        prev_disabled = page == 0
        if st.button("⬅️", use_container_width=True, disabled=prev_disabled):
            st.session_state[K_PAGE] = max(0, page - 1)
            st.rerun()

    with mid:
        start_n = offset + 1
        end_n = offset + len(df)
        st.markdown(
            f"<div style='text-align:center; padding-top:6px;'>"
            f"<b>Página {page + 1}</b> — mostrando {start_n} a {end_n}"
            f"</div>",
            unsafe_allow_html=True,
        )

    with right:
        if st.button("➡️", use_container_width=True, disabled=(not has_next)):
            st.session_state[K_PAGE] = page + 1
            st.rerun()
