import streamlit as st
import pandas as pd
from relatorios import utr_por_entregador_turno
from shared import hms_from_hours

def render(df: pd.DataFrame, USUARIOS: dict):
    st.title("📋 Painel de Entregadores")

    nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
    logo_admin = st.secrets.get("LOGO_ADMIN_URL", "")
    logo_user  = st.secrets.get("LOGO_USER_URL", "")
    bg_logo = logo_admin if nivel == "admin" and logo_admin else logo_user
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

    try:
        ultimo_dia = pd.to_datetime(df["data"]).max().date()
        ultimo_dia_txt = ultimo_dia.strftime("%d/%m/%Y")
    except Exception:
        ultimo_dia_txt = "—"

    c1, c2 = st.columns([1,2])
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

    hoje = pd.Timestamp.today()
    mes_atual, ano_atual = int(hoje.month), int(hoje.year)
    df_mes = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)].copy()

    ofertadas  = int(df_mes.get("numero_de_corridas_ofertadas", 0).sum())
    aceitas    = int(df_mes.get("numero_de_corridas_aceitas", 0).sum())
    rejeitadas = int(df_mes.get("numero_de_corridas_rejeitadas", 0).sum())
    entreg_uniq = int(df_mes.get("pessoa_entregadora", pd.Series(dtype=object)).dropna().nunique())

    acc_pct = round((aceitas / ofertadas) * 100, 1) if ofertadas > 0 else 0.0
    rej_pct = round((rejeitadas / ofertadas) * 100, 1) if ofertadas > 0 else 0.0

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
    ano = int(hoje.year)
    total_corridas_ano = int(df[df["ano"] == ano]["numero_de_corridas_completadas"].sum())
    st.metric("Total de corridas completadas no ano", f"{total_corridas_ano:,}".replace(",", "."))
    st.markdown("</div>", unsafe_allow_html=True)
