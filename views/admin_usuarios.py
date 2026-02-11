import json
import secrets
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db import db_conn, audit_log
from auth import canon_login, hash_password, require_admin


TZ_LOCAL = ZoneInfo("America/Sao_Paulo")

DEPARTAMENTOS = ["Administrador", "Operacional", "Financeiro"]

PAGE_SIZE = 30
K_PAGE = "adm_users_page"

K_Q = "adm_users_q"
K_DEPT = "adm_users_dept"
K_STATUS = "adm_users_status"
K_ADMINF = "adm_users_adminf"

K_EDIT_USER_ID = "adm_edit_user_id"
K_GENPW = "adm_users_gen_pw"

# create form keys
K_C_NAME = "adm_create_full_name"
K_C_LOGIN = "adm_create_login"
K_C_DEPT = "adm_create_dept"
K_C_ADMIN = "adm_create_is_admin"
K_C_ACTIVE = "adm_create_is_active"
K_C_PW = "adm_create_password"
K_C_MUST = "adm_create_must_change"


def _gen_temp_password() -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#%&*"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def _fmt_dt(x):
    if not x:
        return ""
    try:
        dt = pd.to_datetime(x, utc=True, errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(x, errors="coerce")
        if pd.isna(dt):
            return str(x)
        if dt.tzinfo is None:
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        return dt.tz_convert(TZ_LOCAL).tz_localize(None).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return str(x)


@st.cache_data(ttl=120)
def _stats_users():
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                  count(*) as total,
                  sum(case when is_active then 1 else 0 end) as ativos,
                  sum(case when is_admin then 1 else 0 end) as admins,
                  sum(case when must_change_password then 1 else 0 end) as must_change
                from public.app_users
                """
            )
            r = cur.fetchone()
    total, ativos, admins, must_change = [int(x or 0) for x in r]
    return total, ativos, admins, must_change


def _build_where(q: str, dept: str, status: str, adminf: str):
    where = []
    params = []

    q = (q or "").strip()
    if q:
        where.append("(login ilike %s or full_name ilike %s)")
        params.extend([f"%{q}%", f"%{q}%"])

    if dept and dept != "Todos":
        where.append("department = %s")
        params.append(dept)

    if status == "Ativos":
        where.append("is_active = true")
    elif status == "Inativos":
        where.append("is_active = false")

    if adminf == "Só admin":
        where.append("is_admin = true")
    elif adminf == "Só não-admin":
        where.append("is_admin = false")

    where_sql = ("where " + " and ".join(where)) if where else ""
    return where_sql, params


def _fetch_page(q: str, dept: str, status: str, adminf: str, page: int):
    where_sql, params = _build_where(q, dept, status, adminf)
    offset = page * PAGE_SIZE

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"select count(*) from public.app_users {where_sql}", tuple(params))
            total = int(cur.fetchone()[0] or 0)

            cur.execute(
                f"""
                select id, login, full_name, department, is_admin, is_active,
                       must_change_password, last_login_at, created_at
                from public.app_users
                {where_sql}
                order by lower(login)
                limit %s offset %s
                """,
                tuple(params + [PAGE_SIZE + 1, offset]),
            )
            rows = cur.fetchall()

    has_next = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]
    return total, has_next, rows


@st.cache_data(ttl=120)
def _user_choices():
    """Lista pra selectbox de edição (independente de filtro/página)."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, login, full_name, is_active, is_admin
                from public.app_users
                order by lower(login)
                """
            )
            rows = cur.fetchall()

    choices = []
    for (uid, login, full_name, is_active, is_admin) in rows:
        flags = []
        if is_admin:
            flags.append("admin")
        if not is_active:
            flags.append("inativo")
        tag = f" ({', '.join(flags)})" if flags else ""
        label = f"{login} — {full_name}{tag}"
        choices.append((str(uid), label))
    return choices


def _get_user_by_id(user_id: str):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, login, full_name, department, is_admin, is_active, must_change_password,
                       last_login_at, created_at
                from public.app_users
                where id = %s
                limit 1
                """,
                (user_id,),
            )
            return cur.fetchone()


def _init_defaults():
    st.session_state.setdefault(K_PAGE, 0)
    st.session_state.setdefault(K_Q, "")
    st.session_state.setdefault(K_DEPT, "Todos")
    st.session_state.setdefault(K_STATUS, "Ativos")
    st.session_state.setdefault(K_ADMINF, "Todos")

    # create tab defaults
    st.session_state.setdefault(K_C_NAME, "")
    st.session_state.setdefault(K_C_LOGIN, "")
    st.session_state.setdefault(K_C_DEPT, "Operacional")
    st.session_state.setdefault(K_C_ADMIN, False)
    st.session_state.setdefault(K_C_ACTIVE, True)
    st.session_state.setdefault(K_C_PW, "")
    st.session_state.setdefault(K_C_MUST, True)


def render(_df, _USUARIOS):
    require_admin()
    _init_defaults()

    st.markdown("# 🛠️ Admin • Usuários")

    # Cards
    total_u, ativos_u, admins_u, must_u = _stats_users()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Usuários</div>
              <div class="neo-value">{total_u}</div>
              <div class="neo-subline">Total cadastrados</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="neo-card neo-success">
              <div class="neo-label">Ativos</div>
              <div class="neo-value">{ativos_u}</div>
              <div class="neo-subline">Podem logar</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Admins</div>
              <div class="neo-value">{admins_u}</div>
              <div class="neo-subline">Acesso total</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="neo-card neo-danger">
              <div class="neo-label">Trocar senha</div>
              <div class="neo-value">{must_u}</div>
              <div class="neo-subline">Forçado no próximo login</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    tabs = st.tabs(["👥 Usuários", "✏️ Editar usuário", "➕ Criar usuário"])

    # =========================================================
    # TAB 1: USUÁRIOS (LISTA + FILTROS + PAGINAÇÃO)
    # =========================================================
    with tabs[0]:
        st.markdown("""<div class="neo-section">Lista</div>""", unsafe_allow_html=True)

        f1, f2, f3, f4 = st.columns([1.7, 1.0, 1.0, 1.0])
        with f1:
            st.text_input("Buscar (login ou nome)", key=K_Q)
        with f2:
            st.selectbox("Departamento", ["Todos"] + DEPARTAMENTOS, key=K_DEPT)
        with f3:
            st.selectbox("Status", ["Ativos", "Inativos", "Todos"], key=K_STATUS)
        with f4:
            st.selectbox("Admin", ["Todos", "Só admin", "Só não-admin"], key=K_ADMINF)

        # Botões menores (sem ocupar a tela inteira)
        b1, b2, _sp = st.columns([1, 1, 3])
        with b1:
            if st.button("🔄 Aplicar", key="btn_users_apply"):
                st.session_state[K_PAGE] = 0
                st.cache_data.clear()
                st.rerun()
        with b2:
            if st.button("🧹 Limpar", key="btn_users_clear"):
                st.session_state[K_Q] = ""
                st.session_state[K_DEPT] = "Todos"
                st.session_state[K_STATUS] = "Ativos"
                st.session_state[K_ADMINF] = "Todos"
                st.session_state[K_PAGE] = 0
                st.cache_data.clear()
                st.rerun()

        page = max(0, int(st.session_state[K_PAGE]))
        total, has_next, rows = _fetch_page(
            st.session_state[K_Q],
            st.session_state[K_DEPT],
            st.session_state[K_STATUS],
            st.session_state[K_ADMINF],
            page,
        )

        if total == 0:
            st.info("Nada encontrado com esses filtros.")
            return

        df = pd.DataFrame(
            rows,
            columns=[
                "id",
                "login",
                "full_name",
                "department",
                "is_admin",
                "is_active",
                "must_change_password",
                "last_login_at",
                "created_at",
            ],
        )

        df["last_login_at"] = df["last_login_at"].apply(_fmt_dt)
        df["created_at"] = df["created_at"].apply(_fmt_dt)

        st.dataframe(
            df.drop(columns=["id"]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "login": st.column_config.TextColumn("Login"),
                "full_name": st.column_config.TextColumn("Nome"),
                "department": st.column_config.TextColumn("Departamento"),
                "is_admin": st.column_config.CheckboxColumn("Admin"),
                "is_active": st.column_config.CheckboxColumn("Ativo"),
                "must_change_password": st.column_config.CheckboxColumn("Trocar senha"),
                "last_login_at": st.column_config.TextColumn("Último login"),
                "created_at": st.column_config.TextColumn("Criado em"),
            },
        )

        # Paginação com setinhas pequenas
        st.divider()
        left, mid, right = st.columns([1, 6, 1])

        offset = page * PAGE_SIZE
        start_n = offset + 1
        end_n = offset + len(df)
        max_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        with left:
            if st.button("⬅️", disabled=(page == 0), key="btn_users_prev"):
                st.session_state[K_PAGE] = page - 1
                st.rerun()
        with mid:
            st.markdown(
                f"<div style='text-align:center; padding-top:6px;'><b>Página {page+1}/{max_pages}</b> — {start_n} a {end_n} de {total}</div>",
                unsafe_allow_html=True,
            )
        with right:
            if st.button("➡️", disabled=(not has_next), key="btn_users_next"):
                st.session_state[K_PAGE] = page + 1
                st.rerun()

        st.caption("Pra editar: vai na aba **Editar usuário** ali em cima.")

    # =========================================================
    # TAB 2: EDITAR USUÁRIO
    # =========================================================
    with tabs[1]:
        st.markdown("""<div class="neo-section">Editar</div>""", unsafe_allow_html=True)

        choices = _user_choices()
        if not choices:
            st.info("Sem usuários cadastrados.")
            return

        # default selection
        if K_EDIT_USER_ID not in st.session_state:
            st.session_state[K_EDIT_USER_ID] = choices[0][0]

        # selectbox (id como value)
        id_to_label = {uid: label for uid, label in choices}
        labels = [label for _, label in choices]
        current_id = st.session_state[K_EDIT_USER_ID]
        current_label = id_to_label.get(current_id, labels[0])

        selected_label = st.selectbox(
            "Selecione um usuário",
            options=labels,
            index=labels.index(current_label) if current_label in labels else 0,
            key="edit_user_select_label",
        )

        # converte label -> id
        selected_id = None
        for uid, label in choices:
            if label == selected_label:
                selected_id = uid
                break
        if not selected_id:
            selected_id = choices[0][0]

        st.session_state[K_EDIT_USER_ID] = selected_id

        row = _get_user_by_id(selected_id)
        if not row:
            st.error("Usuário não encontrado.")
            return

        (
            user_id,
            login,
            full_name,
            department,
            is_admin,
            is_active,
            must_change_password,
            last_login_at,
            created_at,
        ) = row

        actor_id = str(st.session_state.get("user_id") or "")
        is_self = (str(user_id) == actor_id)

        tedit, treset = st.tabs(["✏️ Dados", "🔁 Resetar senha"])

        with tedit:
            with st.form("edit_user_form"):
                e1, e2 = st.columns([1, 2])
                with e1:
                    e_login = st.text_input("Login", value=str(login)).strip().lower()
                with e2:
                    e_full_name = st.text_input("Nome completo", value=str(full_name))

                e3, e4, e5, e6 = st.columns([1.2, 1.0, 1.0, 1.2])
                with e3:
                    e_dept = st.selectbox(
                        "Departamento",
                        DEPARTAMENTOS,
                        index=DEPARTAMENTOS.index(department) if department in DEPARTAMENTOS else 1,
                    )
                with e4:
                    e_is_admin = st.checkbox("Admin", value=bool(is_admin))
                with e5:
                    e_is_active = st.checkbox("Ativo", value=bool(is_active))
                with e6:
                    e_must_change = st.checkbox("Forçar troca de senha", value=bool(must_change_password))

                st.caption(f"ID: {user_id}")
                st.caption(f"Criado em: {_fmt_dt(created_at)} | Último login: {_fmt_dt(last_login_at)}")

                save = st.form_submit_button("💾 Salvar")

            if save:
                if is_self and (not e_is_active):
                    st.error("Você tá tentando se desativar. Não vou deixar pra você não se trancar fora.")
                    st.stop()
                if is_self and (not e_is_admin):
                    st.error("Você tá tentando tirar seu admin. Não vou deixar pra você não se ferrar depois.")
                    st.stop()

                try:
                    e_login2 = canon_login(e_login)
                except Exception as e:
                    st.error(str(e))
                    st.stop()

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
                                    must_change_password=%s,
                                    updated_at=now(),
                                    updated_by=%s
                                where id=%s
                                """,
                                (
                                    e_login2,
                                    e_full_name.strip(),
                                    e_dept,
                                    e_is_admin,
                                    e_is_active,
                                    e_must_change,
                                    actor_id or None,
                                    user_id,
                                ),
                            )
                        conn.commit()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Erro ao salvar (login já existe?): {e}")
                        st.stop()

                audit_log(
                    "user_updated",
                    "app_users",
                    str(user_id),
                    {
                        "login": e_login2,
                        "department": e_dept,
                        "is_admin": bool(e_is_admin),
                        "is_active": bool(e_is_active),
                        "must_change_password": bool(e_must_change),
                    },
                )
                st.success("Atualizado!")
                st.cache_data.clear()
                st.rerun()

        with treset:
            # gera senha
            gen_cols = st.columns([1, 3])
            with gen_cols[0]:
                if st.button("🎲 Gerar", key="btn_reset_genpw"):
                    st.session_state[K_GENPW] = _gen_temp_password()
            gen = st.session_state.get(K_GENPW)

            if gen:
                st.info(f"Senha gerada: `{gen}` (copia e manda pro usuário)")

            new_pw = st.text_input("Nova senha", type="password", value=gen or "", key="reset_pw_input")
            force_change = st.checkbox("Forçar trocar senha no próximo login?", value=True, key="reset_force_change")

            if st.button("🔁 Resetar senha", key="btn_reset_pw"):
                if not new_pw or len(new_pw) < 6:
                    st.error("Informe uma senha (mín. 6).")
                    st.stop()

                pw_hash = hash_password(new_pw)

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
                            (pw_hash, bool(force_change), actor_id or None, user_id),
                        )
                    conn.commit()

                audit_log("password_reset", "app_users", str(user_id), {"target_login": str(login)})
                st.success("Senha resetada!")
                st.session_state.pop(K_GENPW, None)
                st.cache_data.clear()
                st.rerun()

    # =========================================================
    # TAB 3: CRIAR USUÁRIO
    # =========================================================
    with tabs[2]:
        st.markdown("""<div class="neo-section">Criar novo usuário</div>""", unsafe_allow_html=True)

        # botões pequenos no topo
        g1, g2, _sp = st.columns([1, 1, 4])
        with g1:
            if st.button("🎲 Gerar senha", key="btn_create_genpw"):
                st.session_state[K_C_PW] = _gen_temp_password()
        with g2:
            if st.button("🧹 Limpar campos", key="btn_create_clear"):
                st.session_state[K_C_NAME] = ""
                st.session_state[K_C_LOGIN] = ""
                st.session_state[K_C_DEPT] = "Operacional"
                st.session_state[K_C_ADMIN] = False
                st.session_state[K_C_ACTIVE] = True
                st.session_state[K_C_PW] = ""
                st.session_state[K_C_MUST] = True
                st.rerun()

        if st.session_state.get(K_C_PW):
            st.info(f"Senha atual: `{st.session_state[K_C_PW]}`")

        with st.form("create_user_form"):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.text_input("Nome completo", key=K_C_NAME)
            with c2:
                st.text_input("Login (sem espaço)", key=K_C_LOGIN, help="3–32 chars: a-z 0-9 . _ -")

            c3, c4, c5 = st.columns([1.2, 1.0, 1.0])
            with c3:
                # IMPORTANTE: sem `index=` aqui, porque a key já tá no session_state (evita o warning)
                st.selectbox("Departamento", DEPARTAMENTOS, key=K_C_DEPT)
            with c4:
                st.checkbox("É admin?", key=K_C_ADMIN)
            with c5:
                st.checkbox("Ativo?", key=K_C_ACTIVE)

            st.text_input("Senha inicial", type="password", key=K_C_PW)
            st.checkbox("Forçar trocar senha no 1º login?", key=K_C_MUST)

            submit = st.form_submit_button("➕ Criar usuário")

        if submit:
            full_name = (st.session_state[K_C_NAME] or "").strip()
            login_in = (st.session_state[K_C_LOGIN] or "").strip().lower()
            dept = st.session_state[K_C_DEPT]
            is_admin = bool(st.session_state[K_C_ADMIN])
            is_active = bool(st.session_state[K_C_ACTIVE])
            temp_pw = st.session_state[K_C_PW] or ""
            must_change = bool(st.session_state[K_C_MUST])

            if not full_name:
                st.error("Nome completo é obrigatório.")
                st.stop()

            try:
                login2 = canon_login(login_in)
            except Exception as e:
                st.error(str(e))
                st.stop()

            if not temp_pw:
                st.error("Informe uma senha inicial (ou gere).")
                st.stop()

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
                            (login2, full_name, dept, is_admin, is_active, pw_hash, must_change, actor_id, actor_id),
                        )
                        new_id = cur.fetchone()[0]
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    st.error(f"Erro ao criar usuário (login já existe?): {e}")
                    st.stop()

            audit_log("user_created", "app_users", str(new_id), {"login": login2, "department": dept, "is_admin": is_admin})
            st.success("Usuário criado!")

            # tira a senha da tela depois de criar (segurança e estética)
            st.session_state[K_C_PW] = ""
            st.cache_data.clear()
            st.rerun()
