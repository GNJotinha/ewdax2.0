import html
import streamlit as st
import pandas as pd
from relatorios import utr_por_entregador_turno
from utils import calcular_aderencia


def _fmt_int(x):
    try:
        return f"{int(round(float(x))):,}".replace(",", ".")
    except Exception:
        return "0"


def _fmt_pct(x, nd=1):
    try:
        return f"{float(x):.{nd}f}%".replace(".", ",")
    except Exception:
        return "0,0%"


def _pick_col(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    return None


def render(df: pd.DataFrame, USUARIOS: dict):
    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    # =========================
    # MÊS ATUAL
    # =========================
    hoje = pd.Timestamp.today()
    mes_atual, ano_atual = int(hoje.month), int(hoje.year)

    if ("mes" in df.columns) and ("ano" in df.columns):
        df_mes = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)].copy()
    else:
        if "mes_ano" in df.columns:
            ultimo_mes = df["mes_ano"].max()
            df_mes = df[df["mes_ano"] == ultimo_mes].copy()
            try:
                mes_atual = int(pd.to_datetime(ultimo_mes).month)
                ano_atual = int(pd.to_datetime(ultimo_mes).year)
            except Exception:
                pass
        else:
            df_mes = df.copy()

    # =========================
    # COLUNAS (auto)
    # =========================
    cols = set(df_mes.columns)

    data_col = _pick_col(cols, ["data", "data_do_periodo", "Data", "DATA"])
    turno_col = _pick_col(cols, ["turno", "periodo", "Turno", "PERIODO"])
    vagas_col = _pick_col(cols, ["numero_minimo_de_entregadores_regulares_na_escala", "vagas", "VAGAS"])
    tag_col = _pick_col(cols, ["tag", "TAG"])

    # =========================
    # MÉTRICAS BÁSICAS
    # =========================
    corr_of = float(pd.to_numeric(df_mes.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
    corr_ac = float(pd.to_numeric(df_mes.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
    corr_rej = float(pd.to_numeric(df_mes.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum())

    ativos = 0
    if "uuid" in df_mes.columns:
        ativos = int(df_mes["uuid"].nunique())
    elif "id_da_pessoa_entregadora" in df_mes.columns:
        ativos = int(df_mes["id_da_pessoa_entregadora"].nunique())

    # =========================
    # SUPPLY HOURS (SH)
    # =========================
    supply_hours = 0.0
    try:
        supply_hours = float(pd.to_numeric(df_mes.get("segundos_abs", 0), errors="coerce").fillna(0).sum()) / 3600.0
    except Exception:
        pass

    # =========================
    # UTR MÉDIA (simples)
    # =========================
    utr_media = 0.0
    utr_abs = 0.0
    try:
        if supply_hours > 0:
            utr_abs = float(corr_of / supply_hours)
        utr_media = float((df_mes["numero_de_corridas_ofertadas"] / (df_mes["segundos_abs"] / 3600.0)).mean())
    except Exception:
        pass

    # =========================
    # ADERÊNCIA
    # =========================
    ader_pct = 0.0
    ader_reg = 0
    ader_vagas = 0.0
    vagas_incons = False

    if data_col and vagas_col and tag_col and ("segundos_abs" in df_mes.columns):
        group_cols = (data_col, turno_col) if turno_col else (data_col,)
        try:
            base_ap = calcular_aderencia(
                df_mes,
                group_cols=group_cols,
                vagas_col=vagas_col,
                tag_col=tag_col,
                tag_regular="REGULAR",
            )
            ader_reg = int(pd.to_numeric(base_ap.get("regulares_atuaram", 0), errors="coerce").fillna(0).sum())
            ader_vagas = float(pd.to_numeric(base_ap.get("vagas", 0), errors="coerce").fillna(0).sum())
            if ader_vagas > 0:
                ader_pct = round((ader_reg / ader_vagas) * 100.0, 1)
            vagas_incons = bool(base_ap.get("vagas_inconsistente", False).fillna(False).any())
        except Exception:
            pass

    pct_bar = max(0.0, min(float(ader_pct), 100.0))

    # =========================
    # TOP 3 POR HORAS
    # =========================
    top3 = []
    if ("pessoa_entregadora" in df_mes.columns) and ("segundos_abs" in df_mes.columns):
        tmp_h = df_mes[["pessoa_entregadora", "segundos_abs"]].copy()
        tmp_h["horas"] = pd.to_numeric(tmp_h["segundos_abs"], errors="coerce").fillna(0) / 3600.0
        top = tmp_h.groupby("pessoa_entregadora", dropna=False)["horas"].sum().sort_values(ascending=False).head(3)
        for nome, horas in top.items():
            top3.append((str(nome), float(horas)))

    # =========================
    # DATA “atualizada”
    # =========================
    data_str = ""
    try:
        dtmax = pd.to_datetime(df_mes["data_do_periodo"], errors="coerce").max()
        if pd.notna(dtmax):
            data_str = dtmax.strftime("%d/%m/%Y")
    except Exception:
        pass

    # =========================
    # HEADER (SEM HTML)
    # =========================
    hL, hR = st.columns([4, 1])
    with hL:
        st.title("Painel de Entregadores")
        st.caption(f"Dados atualizados • {data_str}")
    with hR:
        if st.button("Atualizar base", use_container_width=True, key="btn_refresh_home"):
            st.session_state.force_refresh = True
            st.session_state.just_refreshed = True
            st.cache_data.clear()
            st.rerun()

    # =========================
    # CONTEÚDO
    # =========================
    st.markdown("#### Resumo do mês ({:02d}/{})".format(mes_atual, ano_atual))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Ofertadas – UTR</div>
              <div class="neo-value">{_fmt_int(corr_of)}</div>
              <div class="neo-subline">Absoluto {_fmt_int(utr_abs)} • Média {str(round(utr_media,2)).replace(".",",")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        pct = (corr_ac / corr_of * 100.0) if corr_of > 0 else 0.0
        st.markdown(
            f"""
            <div class="neo-card neo-success">
              <div class="neo-label">Aceitas</div>
              <div class="neo-value">{_fmt_int(corr_ac)}<span class="pct">({_fmt_pct(pct)})</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        pct = (corr_rej / corr_of * 100.0) if corr_of > 0 else 0.0
        st.markdown(
            f"""
            <div class="neo-card neo-danger">
              <div class="neo-label">Rejeitadas</div>
              <div class="neo-value">{_fmt_int(corr_rej)}<span class="pct">({_fmt_pct(pct)})</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c4:
        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Entregadores ativos</div>
              <div class="neo-value">{_fmt_int(ativos)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### Aderência (REGULAR)")
    a1, a2 = st.columns([1, 2])
    with a1:
        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Aderência</div>
              <div class="neo-value">{str(ader_pct).replace(".",",")}%</div>
              <div class="neo-subline">Regulares: {_fmt_int(ader_reg)} / Vagas: {_fmt_int(ader_vagas)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if vagas_incons:
            st.warning("⚠️ Vagas variando dentro do mesmo grupo (possível inconsistência).")

    with a2:
        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Regulares: {_fmt_int(ader_reg)} / Vagas: {_fmt_int(ader_vagas)}</div>
              <div class="neo-progress-wrap">
                <div class="neo-progress"><div style="width:{pct_bar}%;"></div></div>
                <div class="neo-scale"><span>0%</span><span>50%</span><span>100%</span></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### Supply & Ranking")
    s1, s2 = st.columns([1.3, 1.0])
    with s1:
        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Supply Hours (SH)</div>
              <div class="neo-value">{str(round(supply_hours,1)).replace(".",",")}h</div>
              <div class="neo-subline">Total no mês ({mes_atual:02d}/{ano_atual})</div>
              <div class="neo-divider"></div>
              <div class="toprow">
                <div class="name">👤 Média por entregador</div>
                <div class="hours">{str(round((supply_hours / ativos) if ativos else 0,1)).replace(".",",")}h</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with s2:
        rows = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, (nome, horas) in enumerate(top3):
            rows += f"""
            <div class="toprow">
              <div class="name">{medals[i]} {html.escape(nome)}</div>
              <div class="hours">{str(round(horas,1)).replace(".",",")}h</div>
            </div>
            """
        if not rows:
            rows = "<div class='neo-subline'>Sem ranking disponível.</div>"

        st.markdown(
            f"""
            <div class="neo-card">
              <div class="neo-label">Top 3 entregadores (horas)</div>
              {rows}
            </div>
            """,
            unsafe_allow_html=True,
        )
