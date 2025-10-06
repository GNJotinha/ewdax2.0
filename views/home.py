import streamlit as st
import pandas as pd
from relatorios import utr_por_entregador_turno
from shared import hms_from_hours

DEBUG_MODE = bool(st.secrets.get("DEBUG_MODE", False))

def render(df: pd.DataFrame, USUARIOS: dict):
    st.title("📋 Painel de Entregadores")

    # ---------------------------------------------------------
    # Logo de fundo (muda conforme nível do usuário)
    # ---------------------------------------------------------
    nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
    logo_admin = st.secrets.get("LOGO_ADMIN_URL", "")
    logo_user  = st.secrets.get("LOGO_USER_URL", "")
    bg_logo = logo_admin if (nivel == "admin" and logo_admin) else logo_user
    if bg_logo:
        st.markdown(f'''
            <style>
              .home-bg:before {{
                content: "";
                position: absolute; inset: 0;
                background-image: url("{bg_logo}");
                background-repeat: no-repeat;
                background-position: center 20%;
                background-size: 40%;
                opacity: 0.06; pointer-events: none;
              }}
            </style>
        ''', unsafe_allow_html=True)
    st.markdown("<div class='home-bg' style='position:relative;'>", unsafe_allow_html=True)

    # ---------------------------------------------------------
    # Diagnóstico opcional (ativado com DEBUG_MODE=true no secrets)
    # ---------------------------------------------------------
    if DEBUG_MODE:
        st.info("🧪 DEBUG — Diagnóstico do dataset carregado")
        try:
            base_dt = pd.to_datetime(df.get("data"), errors="coerce")
            dmin, dmax = base_dt.min(), base_dt.max()
            st.caption(f"Min/Max data no DF: {dmin} → {dmax}")
        except Exception as e:
            st.caption(f"Erro lendo datas: {e}")

        try:
            cont_mes = (
                pd.to_datetime(df.get("data"), errors="coerce")
                  .dt.to_period("M").value_counts().sort_index()
                  .rename("linhas").to_frame()
            )
            st.write("Contagem por mês (no DF):")
            st.dataframe(cont_mes, use_container_width=True)
        except Exception as e:
            st.caption(f"Erro contando meses: {e}")

        try:
            # Amostra do mês atual para conferir se o filtro bate
            hoje = pd.Timestamp.today()
            amostra = df[(df.get("mes") == hoje.month) & (df.get("ano") == hoje.year)].head(5)
            st.write("Amostra do mês atual (no DF):")
            st.dataframe(amostra, use_container_width=True)
        except Exception as e:
            st.caption(f"Erro exibindo amostra do mês atual: {e}")

        # URL do Supabase (útil para conferir se é o projeto certo)
        try:
            supa_url = st.secrets.get("SUPABASE_URL", "—")
            st.caption(f"🔌 Supabase em uso: {supa_url}")
        except Exception:
            pass

    # ---------------------------------------------------------
    # Cabeçalho: último dia com dados + botão de atualização
    # ---------------------------------------------------------
    try:
        ultimo_dia = pd.to_datetime(df.get("data"), errors="coerce").max().date()
        ultimo_dia_txt = ultimo_dia.strftime("%d/%m/%Y")
    except Exception:
        ultimo_dia_txt = "—"

    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("Dados mais recentes")
        st.metric("", ultimo_dia_txt)
    with c2:
        st.subheader("Atualização de base")
        if st.button("Atualizar dados", use_container_width=True, key="btn_refresh_drive"):
            st.session_state.force_refresh = True
            st.session_state.just_refreshed = True
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # ---------------------------------------------------------
    # Resumo do mês atual
    # ---------------------------------------------------------
    hoje = pd.Timestamp.today()
    mes_atual, ano_atual = int(hoje.month), int(hoje.year)
    df_mes = df[(df.get("mes") == mes_atual) & (df.get("ano") == ano_atual)].copy()

    ofertadas  = int(pd.to_numeric(df_mes.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
    aceitas    = int(pd.to_numeric(df_mes.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
    rejeitadas = int(pd.to_numeric(df_mes.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum())
    entreg_uniq = int(df_mes.get("pessoa_entregadora", pd.Series(dtype=object)).dropna().nunique())

    acc_pct = round((aceitas / ofertadas) * 100, 1) if ofertadas > 0 else 0.0
    rej_pct = round((rejeitadas / ofertadas) * 100, 1) if ofertadas > 0 else 0.0

    # UTRs (Absoluto e Médias)
    base_home = utr_por_entregador_turno(df, mes_atual, ano_atual)
    if not df_mes.empty:
        seg = pd.to_numeric(df_mes.get("segundos_abs", 0), errors="coerce").fillna(0).sum()
        horas = seg / 3600.0 if seg > 0 else 0.0
        utr_abs = (ofertadas / horas) if horas > 0 else 0.0
    else:
        utr_abs = 0.0
    if not base_home.empty:
        base_pos = base_home[base_home["supply_hours"] > 0].copy()
        utr_medias = (base_pos["corridas_ofertadas"] / base_pos["supply_hours"]).mean() if not base_pos.empty else 0.0
    else:
        utr_medias = 0.0

    st.subheader(f"📦 Resumo do mês atual ({mes_atual:02d}/{ano_atual})")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ofertadas - UTR", f"{ofertadas:,}".replace(",", "."))
    m1.caption(f"Absoluto: **{utr_abs:.2f}**")
    m1.caption(f"Médias: **{utr_medias:.2f}**")
    m2.metric("Aceitas", f"{aceitas:,}".replace(",", "."), f"{acc_pct:.1f}%")
    m3.metric("Rejeitadas", f"{rejeitadas:,}".replace(",", "."), f"{rej_pct:.1f}%")
    m4.metric("Entregadores ativos", f"{entreg_uniq}")

    st.divider()

    # ---------------------------------------------------------
    # Curiosidades / Destaques do ano atual
    # ---------------------------------------------------------
    ano = int(hoje.year)
    total_corridas_ano = int(pd.to_numeric(df[df.get("ano") == ano].get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0).sum())
    st.metric("Total de corridas completadas no ano", f"{total_corridas_ano:,}".replace(",", "."))

    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------------------------------------------------
    # Pós-refresh feedback
    # ---------------------------------------------------------
    if st.session_state.pop("just_refreshed", False):
        st.success("✅ Base atualizada a partir do Supabase.")
