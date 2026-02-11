import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db import db_conn
from auth import require_admin


TZ_LOCAL = ZoneInfo("America/Sao_Paulo")
TZ_UTC = ZoneInfo("UTC")

# Session keys (pra reset funcionar sem dor)
K_PRESET = "audit_preset"
K_DI = "audit_di"
K_DF = "audit_df"
K_ACTOR_MODE = "audit_actor_mode"
K_ACTOR_SEL = "audit_actor_sel"
K_ACTOR_TEXT = "audit_actor_text"
K_ACTION_MODE = "audit_action_mode"
K_ACTION_SEL = "audit_action_sel"
K_ACTION_TEXT = "audit_action_text"
K_ENTITY = "audit_entity"
K_ENTITY_ID = "audit_entity_id"
K_ONLY_FAILED = "audit_only_failed"
K_LIMIT = "audit_limit"
K_FLASH = "audit_flash"


def _safe_json(x):
    """Garante dict/list pro st.json, mesmo se vier string ou None."""
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
    """String compacta pro grid (sem quebrar a tela)."""
    obj = _safe_json(x)
    try:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else (s[:limit] + "…")


@st.cache_data(ttl=300)
def _load_filter_options():
    """Opções pros filtros sem espancar o banco o tempo todo."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select distinct actor_login
                from public.audit_log
                where actor_login is not null and actor_login <> ''
                order by actor_login
                limit 300
                """
            )
            actors = [r[0] for r in cur.fetchall()]

            cur.execute(
                """
                select distinct action
                from public.audit_log
                where action is not null and action <> ''
                order by action
                limit 500
                """
            )
            actions = [r[0] for r in cur.fetchall()]

            cur.execute(
                """
                select distinct entity
                from public.audit_log
                where entity is not null and entity <> ''
                order by entity
                limit 300
                """
            )
            entities = [r[0] for r in cur.fetchall()]

    return actors, actions, entities


def _init_defaults():
    hoje = date.today()
    if K_PRESET not in st.session_state:
        st.session_state[K_PRESET] = "7 dias"
    if K_DI not in st.session_state:
        st.session_state[K_DI] = hoje - timedelta(days=7)
    if K_DF not in st.session_state:
        st.session_state[K_DF] = hoje

    st.session_state.setdefault(K_ACTOR_MODE, "Escolher na lista")
    st.session_state.setdefault(K_ACTOR_SEL, [])
    st.session_state.setdefault(K_ACTOR_TEXT, "")

    st.session_state.setdefault(K_ACTION_MODE, "Escolher na lista")
    st.session_state.setdefault(K_ACTION_SEL, [])
    st.session_state.setdefault(K_ACTION_TEXT, "")

    st.session_state.setdefault(K_ENTITY, "(todas)")
    st.session_state.setdefault(K_ENTITY_ID, "")
    st.session_state.setdefault(K_ONLY_FAILED, False)
    st.session_state.setdefault(K_LIMIT, 300)


def _reset_filters():
    hoje = date.today()
    st.session_state[K_PRESET] = "7 dias"
    st.session_state[K_DI] = hoje - timedelta(days=7)
    st.session_state[K_DF] = hoje

    st.session_state[K_ACTOR_MODE] = "Escolher na lista"
    st.session_state[K_ACTOR_SEL] = []
    st.session_state[K_ACTOR_TEXT] = ""

    st.session_state[K_ACTION_MODE] = "Escolher na lista"
    st.session_state[K_ACTION_SEL] = []
    st.session_state[K_ACTION_TEXT] = ""

    st.session_state[K_ENTITY] = "(todas)"
    st.session_state[K_ENTITY_ID] = ""
    st.session_state[K_ONLY_FAILED] = False
    st.session_state[K_LIMIT] = 300


def _compute_window(preset: str, di: date, df: date):
    """
    Retorna (start_local_aware, end_local_aware, label)
    end é exclusivo (bom pra SQL).
    """
    now_local = datetime.now(TZ_LOCAL)

    if preset == "24h":
        start = now_local - timedelta(hours=24)
        end = now_local
        label = f"Últimas 24h: {start:%d/%m %H:%M} → {end:%d/%m %H:%M}"
        return start, end, label

    if preset == "7 dias":
        start = now_local - timedelta(days=7)
        end = now_local
        label = f"Últimos 7 dias: {start:%d/%m %H:%M} → {end:%d/%m %H:%M}"
        return start, end, label

    if preset == "30 dias":
        start = now_local - timedelta(days=30)
        end = now_local
        label = f"Últimos 30 dias: {start:%d/%m %H:%M} → {end:%d/%m %H:%M}"
        return start, end, label

    if preset == "Mês atual":
        start = datetime(now_local.year, now_local.month, 1, 0, 0, 0, tzinfo=TZ_LOCAL)
        end = now_local
        label = f"Mês atual: {start:%d/%m %H:%M} → {end:%d/%m %H:%M}"
        return start, end, label

    # Custom (por data)
    start = datetime.combine(di, time.min, tzinfo=TZ_LOCAL)
    end = datetime.combine(df + timedelta(days=1), time.min, tzinfo=TZ_LOCAL)  # exclusivo
    label = f"Custom: {di:%d/%m/%Y} → {df:%d/%m/%Y}"
    return start, end, label


def render(_df, _USUARIOS):
    require_admin()
    _init_defaults()

    st.markdown("# 🧾 Auditoria")

    actors, actions, entities = _load_filter_options()

    flash = st.session_state.pop(K_FLASH, None)
    if flash:
        level, msg = flash
        {"success": st.success, "warning": st.warning, "info": st.info}.get(level, st.info)(msg)

    # -----------------------------
    # UI - FILTROS
    # -----------------------------
    with st.expander("Filtros", expanded=True):
        top1, top2 = st.columns([1, 1])
        with top1:
            st.radio(
                "Atalho de período",
                options=["24h", "7 dias", "30 dias", "Mês atual", "Custom"],
                horizontal=True,
                key=K_PRESET,
            )
        with top2:
            # botão de reset fora do form (pra funcionar sempre)
            if st.button("🧹 Limpar filtros", use_container_width=True):
                _reset_filters()
                st.session_state[K_FLASH] = ("info", "Filtros resetados.")
                st.rerun()

        preset = st.session_state[K_PRESET]

        # Mostra date_input só quando for Custom
        di = st.session_state[K_DI]
        df = st.session_state[K_DF]

        if preset == "Custom":
            periodo = st.date_input(
                "Período (início / fim)",
                value=(di, df),
                format="DD/MM/YYYY",
            )
            if isinstance(periodo, tuple) and len(periodo) == 2:
                st.session_state[K_DI], st.session_state[K_DF] = periodo[0], periodo[1]
        else:
            # Só pra visual, sem editar (pra não confundir)
            st.caption("Período vindo do atalho (mexe no rádio ali em cima).")

        with st.form("audit_filters_form"):
            c1, c2, c3 = st.columns([1.2, 1.2, 1.0])

            c1.selectbox(
                "Filtro de login",
                ["Escolher na lista", "Buscar por texto"],
                key=K_ACTOR_MODE,
            )
            if st.session_state[K_ACTOR_MODE] == "Escolher na lista":
                c1.multiselect("Quem fez (login)", options=actors, key=K_ACTOR_SEL)
                st.session_state[K_ACTOR_TEXT] = ""
            else:
                c1.text_input("Login contém", key=K_ACTOR_TEXT)
                st.session_state[K_ACTOR_SEL] = []

            c2.selectbox(
                "Filtro de ação",
                ["Escolher na lista", "Buscar por texto"],
                key=K_ACTION_MODE,
            )
            if st.session_state[K_ACTION_MODE] == "Escolher na lista":
                c2.multiselect("Ação", options=actions, key=K_ACTION_SEL)
                st.session_state[K_ACTION_TEXT] = ""
            else:
                c2.text_input("Ação contém (ex: import_csv)", key=K_ACTION_TEXT)
                st.session_state[K_ACTION_SEL] = []

            c3.slider("Limite", min_value=50, max_value=2000, step=50, key=K_LIMIT)

            c4, c5, c6 = st.columns([1.2, 1.2, 1.0])
            c4.selectbox("Entidade", options=["(todas)"] + entities, key=K_ENTITY)
            c5.text_input("Entity ID contém (opcional)", key=K_ENTITY_ID)
            c6.checkbox("Só falhas (action contém 'failed')", key=K_ONLY_FAILED)

            apply = st.form_submit_button("Aplicar filtros")

        # label do range (sempre)
        start_local, end_local, range_label = _compute_window(
            st.session_state[K_PRESET],
            st.session_state[K_DI],
            st.session_state[K_DF],
        )
        st.caption(f"Janela: **{range_label}** (filtro aplicado em horário SP)")

    # -----------------------------
    # BUILD QUERY
    # -----------------------------
    # Mesmo sem clicar em "Aplicar", a gente usa o state atual.
    where = []
    params = []

    start_utc = start_local.astimezone(TZ_UTC)
    end_utc = end_local.astimezone(TZ_UTC)

    where.append("ts >= %s")
    params.append(start_utc)
    where.append("ts < %s")
    params.append(end_utc)

    # Actor
    actor_sel = st.session_state.get(K_ACTOR_SEL, [])
    actor_text = (st.session_state.get(K_ACTOR_TEXT, "") or "").strip()
    if actor_sel:
        where.append("actor_login = any(%s)")
        params.append(actor_sel)
    elif actor_text:
        where.append("actor_login ILIKE %s")
        params.append(f"%{actor_text}%")

    # Action
    action_sel = st.session_state.get(K_ACTION_SEL, [])
    action_text = (st.session_state.get(K_ACTION_TEXT, "") or "").strip()
    if action_sel:
        where.append("action = any(%s)")
        params.append(action_sel)
    elif action_text:
        where.append("action ILIKE %s")
        params.append(f"%{action_text}%")

    # Entity
    entity = st.session_state.get(K_ENTITY, "(todas)")
    if entity and entity != "(todas)":
        where.append("entity = %s")
        params.append(entity)

    # Entity ID
    entity_id = (st.session_state.get(K_ENTITY_ID, "") or "").strip()
    if entity_id:
        where.append("cast(entity_id as text) ILIKE %s")
        params.append(f"%{entity_id}%")

    # Só falhas
    if st.session_state.get(K_ONLY_FAILED, False):
        where.append("action ILIKE %s")
        params.append("%failed%")

    where_sql = ("where " + " and ".join(where)) if where else ""

    limit = int(st.session_state.get(K_LIMIT, 300))

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
                tuple(params + [limit]),
            )
            rows = cur.fetchall()

    if not rows:
        st.info("Nada encontrado nessa janela / filtros.")
        return

    df = pd.DataFrame(rows, columns=["ts", "actor_login", "action", "entity", "entity_id", "metadata"])

    # -----------------------------
    # FORMAT DATA
    # -----------------------------
    # UTC -> SP, remove tz pra Streamlit formatar bonito
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce").dt.tz_convert(TZ_LOCAL).dt.tz_localize(None)

    # Metadata: objeto pros detalhes + string compacta no grid
    df["_meta_obj"] = df["metadata"].apply(_safe_json)
    df["metadata"] = df["metadata"].apply(_compact_json)

    # -----------------------------
    # HEADER METRICS
    # -----------------------------
    m1, m2, m3 = st.columns(3)
    m1.metric("Eventos", int(len(df)))
    m2.metric("Usuários únicos", int(df["actor_login"].fillna("").nunique()))
    try:
        m3.metric("Janela (resultado)", f"{df['ts'].min():%d/%m/%Y} → {df['ts'].max():%d/%m/%Y}")
    except Exception:
        m3.metric("Janela (resultado)", "-")

    st.download_button(
        "⬇️ Baixar CSV (resultado filtrado)",
        data=df.drop(columns=["_meta_obj"]).to_csv(index=False).encode("utf-8-sig"),
        file_name="auditoria_filtrada.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.dataframe(
        df.drop(columns=["_meta_obj"]),
        use_container_width=True,
        column_config={
            "ts": st.column_config.DatetimeColumn("Data/Hora (SP)", format="DD/MM/YYYY HH:mm:ss"),
            "actor_login": st.column_config.TextColumn("Quem fez"),
            "action": st.column_config.TextColumn("Ação"),
            "entity": st.column_config.TextColumn("Entidade"),
            "entity_id": st.column_config.TextColumn("ID"),
            "metadata": st.column_config.TextColumn("Metadata (compacto)"),
        },
    )

    with st.expander("🔎 Ver detalhes de um registro (metadata JSON bonitinho)", expanded=False):
        # Não explode o selectbox se vier muita coisa
        df_pick = df.head(300).copy()

        labels = []
        for i, r in df_pick.iterrows():
            labels.append(
                f"{i} | {r['ts']:%d/%m/%Y %H:%M:%S} | {r.get('actor_login','')} | {r.get('action','')} | {r.get('entity','')} | {r.get('entity_id','')}"
            )

        pick = st.selectbox("Escolha um evento (até 300 do resultado)", options=labels, index=0)
        idx = int(pick.split("|", 1)[0].strip())
        row = df.loc[idx]

        st.write("**Resumo:**")
        st.code(
            f"ts: {row['ts']:%d/%m/%Y %H:%M:%S}\n"
            f"actor_login: {row.get('actor_login','')}\n"
            f"action: {row.get('action','')}\n"
            f"entity: {row.get('entity','')}\n"
            f"entity_id: {row.get('entity_id','')}",
            language="text",
        )

        st.write("**metadata:**")
        st.json(row["_meta_obj"])
