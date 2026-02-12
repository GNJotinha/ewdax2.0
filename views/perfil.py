import streamlit as st
import pandas as pd
from zoneinfo import ZoneInfo

from db import db_conn, audit_log
from auth import canon_login, hash_password, verify_password, require_admin


DEPARTAMENTOS = ["Administrador", "Operacional", "Financeiro"]
TZ_LOCAL = ZoneInfo("America/Sao_Paulo")


def _fmt_sp(dt) -> str:
    """Converte datetime do banco para dd/mm/aaaa HH:MM no horário de SP."""
    if not dt:
        return "—"
    try:
        d = pd.to_datetime(dt, utc=True, errors="coerce")
        if pd.isna(d):
            d = pd.to_datetime(dt, errors="coerce")
        if pd.isna(d):
            return str(dt)

        # se vier naive, trata como UTC pra evitar cagada
        if getattr(d, "tzinfo", None) is None:
            d = d.tz_localize("UTC")

        d = d.tz_convert(TZ_LOCAL).tz_localize(None)
        return d.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt)


def _bonequinho_svg() -> str:
    """Silhueta neutra (sem emoji)."""
    return """
    <div class="avatar-box">
      <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
        <circle cx="100" cy="72" r="34" fill="rgba(255,255,255,.92)"/>
        <path d="M40 176
                 C40 136, 70 116, 100 116
                 C130 116, 160 136, 160 176
                 L160 190
                 L40 190 Z"
              fill="rgba(255,255,255,.92)"/>
      </svg>
    </div>
    """


def _get_target_user_id() -> str:
    """
    Prepara o modo 'admin vendo outro usuário'.
    No futuro, quando clicar em alguém na tela de admin:
      st.session_state["profile_target_user_id"] = <uuid>
      st.session_state["module"] = "views.perfil"
    """
    me = st.session_state.get("user_id")
    target = (
        st.session_state.get("profile_target_user_id")
        or st.session_state.get("perfil_target_user_id")
    )

    if target and st.session_state.get("is_admin"):
        return target
    return me


def _toggle(label: str, value: bool, key: str):
    """Fallback: st.toggle se existir, senão st.checkbox."""
    if hasattr(st, "toggle"):
        return st.toggle(label, value=value, key=key)
    return st.checkbox(label, value=value, key=key)


def render(_df, _USUARIOS):
    st.markdown("# 👤 Meu Perfil")

    my_user_id = st.session_state.get("user_id")
    if not my_user_id:
        st.error("Sessão inválida. Faz login de novo.")
        st.stop()

    target_user_id = _get_target_user_id()
    viewing_self = (str(target_user_id) == str(my_user_id))
    admin_mode = bool(st.session_state.get("is_admin")) and (not viewing_self)

    if admin_mode:
        require_admin()

    # --- carrega usuário alvo ---
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select login, full_name, department, is_admin, is_active, must_change_password, last_login_at
                from public.app_users
                where id=%s
                """,
                (target_user_id,),
            )
            row = cur.fetchone()

    if not row:
        st.error("Usuário não encontrado no banco.")
        st.stop()

    login, full_name, department, is_admin_db, is_active, must_change_password, last_login_at = row

    # --- layout 2 colunas (robusto p/ versões) ---
    try:
        left, right = st.columns([1.05, 2.0], vertical_alignment="top")
    except Exception:
        left, right = st.columns([1.05, 2.0])

    # =========================
    # ESQUERDA: silhueta + botões
    # =========================
    with left:
        st.markdown(_bonequinho_svg(), unsafe_allow_html=True)

        st.markdown("<div class='profile-left-actions'>", unsafe_allow_html=True)

        if viewing_self:
            # ---------- Alterar apelido ----------
            with st.popover("Alterar apelido (LOGIN)", use_container_width=True):
                new_login = st.text_input(
                    "Novo apelido (login)",
                    value=str(login),
                    help="3–32 chars: a-z 0-9 . _ -",
                    key="pf_new_login",
                ).strip()
                pw_now = st.text_input("Senha atual", type="password", key="pf_pw_for_login")

                if st.button("Salvar apelido", use_container_width=True, key="pf_save_login"):
                    try:
                        new_login2 = canon_login(new_login)
                    except Exception as e:
                        st.error(str(e))
                        st.stop()

                    if not pw_now:
                        st.error("Informe sua senha atual pra confirmar.")
                        st.stop()

                    # valida senha atual
                    with db_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("select password_hash from public.app_users where id=%s", (my_user_id,))
                            pw_hash = cur.fetchone()[0]

                        if not verify_password(pw_now, pw_hash):
                            audit_log("nickname_change_failed", "app_users", str(my_user_id), {"reason": "wrong_password"})
                            st.error("Senha atual incorreta.")
                            st.stop()

                        # atualiza login
                        try:
                            with conn.cursor() as cur:
                                cur.execute(
                                    """
                                    update public.app_users
                                    set login=%s, updated_at=now(), updated_by=%s
                                    where id=%s
                                    """,
                                    (new_login2, my_user_id, my_user_id),
                                )
                            conn.commit()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Não consegui atualizar login (talvez já exista): {e}")
                            st.stop()

                    audit_log("nickname_changed", "app_users", str(my_user_id), {"old": str(login), "new": new_login2})
                    st.session_state.usuario = new_login2
                    st.success("Apelido atualizado!")
                    st.rerun()

            # ---------- Alterar senha ----------
            with st.popover("Alterar senha", use_container_width=True):
                old_pw = st.text_input("Senha antiga", type="password", key="pf_old_pw")
                new_pw = st.text_input("Senha nova", type="password", key="pf_new_pw")
                new_pw2 = st.text_input("Confirmar senha nova", type="password", key="pf_new_pw2")

                if st.button("Salvar nova senha", use_container_width=True, key="pf_save_pw"):
                    if new_pw != new_pw2:
                        st.error("Senha nova e confirmação não batem.")
                        st.stop()

                    if len(new_pw or "") < 6:
                        st.error("Senha muito curta (mínimo 6).")
                        st.stop()

                    with db_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("select password_hash from public.app_users where id=%s", (my_user_id,))
                            pw_hash = cur.fetchone()[0]

                        if not verify_password(old_pw or "", pw_hash):
                            audit_log("password_change_failed", "app_users", str(my_user_id), {"reason": "wrong_old_password"})
                            st.error("Senha antiga incorreta.")
                            st.stop()

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
                                (new_hash, my_user_id, my_user_id),
                            )
                        conn.commit()

                    audit_log("password_changed", "app_users", str(my_user_id), {})
                    st.session_state.must_change_password = False
                    st.success("Senha trocada!")
                    st.rerun()

        else:
            # admin vendo outro usuário
            with st.popover("Alterar informações", use_container_width=True):
                dept_new = st.selectbox(
                    "Departamento",
                    DEPARTAMENTOS,
                    index=DEPARTAMENTOS.index(department) if department in DEPARTAMENTOS else 0,
                    key="pf_adm_dept",
                )
                is_active_new = _toggle("Ativo", bool(is_active), key="pf_adm_active")
                is_admin_new = _toggle("Admin", bool(is_admin_db), key="pf_adm_admin")
                must_change_new = _toggle(
                    "Forçar troca de senha no próximo login",
                    bool(must_change_password),
                    key="pf_adm_must_change",
                )

                if st.button("Salvar alterações", use_container_width=True, key="pf_admin_save"):
                    with db_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                update public.app_users
                                set department=%s,
                                    is_active=%s,
                                    is_admin=%s,
                                    must_change_password=%s,
                                    updated_at=now(),
                                    updated_by=%s
                                where id=%s
                                """,
                                (dept_new, is_active_new, is_admin_new, must_change_new, my_user_id, target_user_id),
                            )
                        conn.commit()

                    audit_log(
                        "user_updated",
                        "app_users",
                        str(target_user_id),
                        {
                            "department": {"old": department, "new": dept_new},
                            "is_active": {"old": bool(is_active), "new": bool(is_active_new)},
                            "is_admin": {"old": bool(is_admin_db), "new": bool(is_admin_new)},
                            "must_change_password": {"old": bool(must_change_password), "new": bool(must_change_new)},
                        },
                    )
                    st.success("Usuário atualizado!")
                    st.rerun()

            if st.button("Voltar pro meu perfil", use_container_width=True, type="secondary"):
                st.session_state.pop("profile_target_user_id", None)
                st.session_state.pop("perfil_target_user_id", None)
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # =========================
    # DIREITA: infos + painel ações
    # =========================
    with right:
        st.markdown(
            f"<div class='profile-title'>{full_name}<span class='profile-nick'>({login})</span></div>"
            f"<div class='profile-line'>Departamento: <b>{department}</b></div>"
            f"<div class='profile-status {'ok' if is_active else 'bad'}'>{'ATIVO' if is_active else 'INATIVO'}</div>"
            f"<div class='profile-lastlogin'>Último login: {_fmt_sp(last_login_at)}</div>",
            unsafe_allow_html=True,
        )

        if viewing_self and must_change_password:
            st.warning("Você precisa trocar sua senha (primeiro acesso / reset).")

        # Painel vermelho: aparece pra admin (igual teu retângulo)
        if st.session_state.get("is_admin"):
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

            with db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        select ts, action, entity, entity_id
                        from public.audit_log
                        where actor_user_id = %s
                        order by ts desc
                        limit 25
                        """,
                        (target_user_id,),
                    )
                    rows = cur.fetchall()

            if not rows:
                st.markdown(
                    "<div class='audit-box'><div class='audit-title'>Últimas ações</div>"
                    "<div style='color:rgba(232,237,246,.70); text-align:center; padding-top:12px;'>Sem registros.</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                html_rows = []
                for ts, action, entity, entity_id in rows:
                    ts_txt = _fmt_sp(ts)
                    ent = entity or "—"
                    eid = entity_id or "—"
                    # IMPORTANTÍSSIMO: sem indentação/markdown, senão vira code block e “quebra”
                    html_rows.append(
                        f"<div class='audit-row'>"
                        f"<div class='audit-ts'>{ts_txt}</div>"
                        f"<div><div class='audit-act'>{action}</div>"
                        f"<div class='audit-meta'>{ent} • {eid}</div></div>"
                        f"</div>"
                    )

                panel_html = (
                    "<div class='audit-box'>"
                    "<div class='audit-title'>Últimas ações</div>"
                    + "".join(html_rows)
                    + "</div>"
                )
                st.markdown(panel_html, unsafe_allow_html=True)
