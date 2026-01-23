import streamlit as st
import pandas as pd
from utils import calcular_aderencia
from relatorios import utr_por_entregador_turno


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


def render(df: pd.DataFrame, USUARIOS: dict):

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    # =========================
    # RECORTE: mês/ano ATUAL (igual teu home antigo)
    # =========================
    hoje = pd.Timestamp.today()
    mes_atual, ano_atual = int(hoje.month), int(hoje.year)

    if ("mes" in df.columns) and ("ano" in df.columns):
        df_mes = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)].copy()
    else:
        # fallback: se não existir mes/ano, usa mes_ano
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

    mes_txt = f"{mes_atual:02d}/{ano_atual}"

    # data mais recente (igual teu antigo: df["data"])
    data_str = "—"
    if "data" in df_mes.columns:
        try:
            ultimo_dia = pd.to_datetime(df_mes["data"], errors="coerce").max()
            if pd.notna(ultimo_dia):
                data_str = pd.to_datetime(ultimo_dia).strftime("%d/%m/%Y")
        except Exception:
            pass

    # =========================
    # KPIs (mês atual)
    # =========================
    ofertadas = float(pd.to_numeric(df_mes.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
    aceitas = float(pd.to_numeric(df_mes.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
    rejeitadas = float(pd.to_numeric(df_mes.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum())

    acc_pct = (aceitas / ofertadas * 100.0) if ofertadas > 0 else 0.0
    rej_pct = (rejeitadas / ofertadas * 100.0) if ofertadas > 0 else 0.0

    entreg_uniq = 0
    if "pessoa_entregadora" in df_mes.columns:
        entreg_uniq = int(df_mes["pessoa_entregadora"].dropna().nunique())

    # UTR abs (igual tua lógica antiga)
    if not df_mes.empty:
        seg = pd.to_numeric(df_mes.get("segundos_abs", 0), errors="coerce").fillna(0).sum()
        horas = seg / 3600.0 if seg > 0 else 0.0
        utr_abs = (ofertadas / horas) if horas > 0 else 0.0
    else:
        utr_abs = 0.0

    # UTR média (igual teu antigo: utr_por_entregador_turno(df, mes, ano))
    utr_medias = 0.0
    try:
        base_home = utr_por_entregador_turno(df, mes_atual, ano_atual)
        if not base_home.empty and "supply_hours" in base_home.columns and "corridas_ofertadas" in base_home.columns:
            base_pos = base_home[base_home["supply_hours"] > 0].copy()
            utr_medias = float((base_pos["corridas_ofertadas"] / base_pos["supply_hours"]).mean()) if not base_pos.empty else 0.0
    except Exception:
        pass

    # =========================
    # ADERÊNCIA (igual teu antigo, mas mantendo UI nova)
    # =========================
    ader_pct = None
    ader_reg = 0
    ader_vagas = 0.0
    vagas_incons = False

    if (
        not df_mes.empty
        and ("numero_minimo_de_entregadores_regulares_na_escala" in df_mes.columns)
        and ("tag" in df_mes.columns)
        and ("data" in df_mes.columns)
    ):
        turno_col = next((c for c in ("turno", "tipo_turno", "periodo") if c in df_mes.columns), None)
        group_cols = ("data", turno_col) if turno_col else ("data",)
        try:
            base_ap = calcular_aderencia(df_mes, group_cols=group_cols)
            ader_reg = int(pd.to_numeric(base_ap.get("regulares_atuaram", 0), errors="coerce").fillna(0).sum())
            ader_vagas = float(pd.to_numeric(base_ap.get("vagas", 0), errors="coerce").fillna(0).sum())
            if ader_vagas > 0:
                ader_pct = round((ader_reg / ader_vagas) * 100.0, 1)
            if "vagas_inconsistente" in base_ap.columns:
                vagas_incons = bool(base_ap["vagas_inconsistente"].fillna(False).any())
        except Exception:
            ader_pct = None

    pct_bar = max(0.0, min(float(ader_pct) if ader_pct is not None else 0.0, 100.0))

    # =========================
    # UI (igual teu layout novo)
    # =========================
    st.markdown('<div class="neo-shell">', unsafe_allow_html=True)

    topL, topR = st.columns([4, 1])
    with topL:
        st.markdown(
            f"""
            <div class="neo-topbar">
              <div>
                <div class="neo-title">🗂️&nbsp;Painel de Entregadores</div>
                <div class="neo-sub">Dados atualizados • {data_str}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with topR:
        if st.button("Atualizar dados", use_container_width=True, key="btn_refresh_drive"):
            st.session_state.force_refresh = True
            st.session_state.just_refreshed = True
            st.cache_data.clear()
            st.rerun()

    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="neo-section">Resumo do mês ({mes_txt})</div>', unsafe_allow_html=True)

    aceitas_html = f"{_fmt_int(aceitas)}<span class='pct'>({_fmt_pct(acc_pct, 1)})</span>"
    rejeitadas_html = f"{_fmt_int(rejeitadas)}<span class='pct'>({_fmt_pct(rej_pct, 1)})</span>"

    st.markdown(
        f"""
        <div class="neo-grid-4">
          <div class="neo-card">
            <div class="neo-label">Ofertadas – UTR</div>
            <div class="neo-value">{_fmt_int(ofertadas)}</div>
            <div class="neo-subline">Absoluto {utr_abs:.2f} • Média {utr_medias:.2f}</div>
          </div>

          <div class="neo-card neo-success">
            <div class="neo-label">Aceitas</div>
            <div class="neo-value">{aceitas_html}</div>
            <div class="neo-subline">&nbsp;</div>
          </div>

          <div class="neo-card neo-danger">
            <div class="neo-label">Rejeitadas</div>
            <div class="neo-value">{rejeitadas_html}</div>
            <div class="neo-subline">&nbsp;</div>
          </div>

          <div class="neo-card">
            <div class="neo-label">Entregadores ativos</div>
            <div class="neo-value">{_fmt_int(entreg_uniq)}</div>
            <div class="neo-subline">&nbsp;</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="neo-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="neo-section">Aderência <span style="font-weight:700;color:rgba(232,237,246,.70)">(REGULAR)</span></div>',
        unsafe_allow_html=True
    )

    if ader_pct is None:
        st.markdown(
            """
            <div class="neo-grid-2">
              <div class="neo-card">
                <div class="neo-value">—</div>
                <div class="neo-subline">Sem dados de aderência neste período.</div>
              </div>
              <div class="neo-card">
                <div class="neo-label">Regulares: — / Vagas: —</div>
                <div class="neo-progress-wrap">
                  <div class="neo-progress"><div style="width:0%"></div></div>
                  <div class="neo-scale"><span>0%</span><span>50%</span><span>100%</span></div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        warn_html = ""
        if vagas_incons:
            warn_html = "<div class='neo-subline' style='margin-top:10px;color:rgba(255,176,32,.95)'>⚠️ Vagas inconsistentes em alguns dias/turnos.</div>"

        st.markdown(
            f"""
            <div class="neo-grid-2">
              <div class="neo-card">
                <div class="neo-value">{ader_pct:.1f}%</div>
                <div class="neo-subline">Regulares: {_fmt_int(ader_reg)} / Vagas: {_fmt_int(ader_vagas)}</div>
                {warn_html}
              </div>

              <div class="neo-card">
                <div class="neo-label">Regulares: {_fmt_int(ader_reg)} / Vagas: {_fmt_int(ader_vagas)}</div>
                <div class="neo-progress-wrap">
                  <div class="neo-progress">
                    <div style="width:{pct_bar:.1f}%;"></div>
                  </div>
                  <div class="neo-scale">
                    <span>0%</span><span>50%</span><span>100%</span>
                  </div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("</div>", unsafe_allow_html=True)
