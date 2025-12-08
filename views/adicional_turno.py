import streamlit as st
import pandas as pd
from shared import hms_from_hours
from utils import calcular_tempo_online

# ================================
# CONFIGURAÇÕES DO ADICIONAL
# ================================
VALOR_ADICIONAL_HORA = 2.15  # R$/hora
ACEITACAO_MIN = 70.0
COMPLETAS_MIN = 95.0

# ================================
# FORMATADORES
# ================================
def _fmt_pct(x: float) -> str:
    try:
        return f"{float(x):.2f}%".replace(".", ",")
    except:
        return "0,00%"

def _fmt_moeda(x: float) -> str:
    try:
        return f"R$ {float(x):.2f}".replace(".", ",")
    except:
        return "R$ 0,00"

# ================================
# VIEW PRINCIPAL
# ================================
def render(df: pd.DataFrame, _USUARIOS: dict):

    st.header("💰 Adicional por Hora — Detalhado por Turno")

    # --------------------------
    # NORMALIZA DATA
    # --------------------------
    base = df.copy()
    if "data" in base.columns:
        base["data"] = pd.to_datetime(base["data"], errors="coerce")
    elif "data_do_periodo" in base.columns:
        base["data"] = pd.to_datetime(base["data_do_periodo"], errors="coerce")
    else:
        st.error("Coluna de data ausente (data ou data_do_periodo).")
        return

    base = base.dropna(subset=["data"])
    if base.empty:
        st.info("Sem dados válidos.")
        return

    # --------------------------
    # SELETOR DE ENTREGADOR
    # --------------------------
    nomes = sorted(base["pessoa_entregadora"].dropna().unique().tolist())
    nome = st.selectbox(
        "🔎 Selecione o entregador:",
        [None] + nomes,
        format_func=lambda x: "" if x is None else x,
    )
    if not nome:
        st.caption("Escolha um entregador para visualizar.")
        return

    # --------------------------
    # FILTRO DE PERÍODO
    # --------------------------
    data_min = base["data"].min().date()
    data_max = base["data"].max().date()
    periodo = st.date_input(
        "Período de análise:",
        [data_min, data_max],
        format="DD/MM/YYYY",
    )

    ent = base[base["pessoa_entregadora"] == nome].copy()

    if len(periodo) == 2:
        ini, fim = pd.to_datetime(periodo[0]), pd.to_datetime(periodo[1])
        ent = ent[(ent["data"] >= ini) & (ent["data"] <= fim)]

    if ent.empty:
        st.info("❌ Nenhum turno encontrado no período.")
        return

    # --------------------------
    # GARANTE COLUNA DE TURNO
    # --------------------------
    if "periodo" not in ent.columns:
        ent["periodo"] = "(sem turno)"

    # --------------------------
    # AGREGA POR DIA + TURNO
    # --------------------------
    linhas = []

    for (dt, turno), chunk in ent.groupby(["data", "periodo"], dropna=False):

        # Tempo online (segundos_abs já vem clipado)
        seg_online = pd.to_numeric(chunk.get("segundos_abs", 0), errors="coerce").fillna(0).sum()
        horas_online = seg_online / 3600.0 if seg_online > 0 else 0.0
        tempo_online_hms = hms_from_hours(horas_online)

        ofertadas = int(pd.to_numeric(chunk.get("numero_de_corridas_ofertadas"), errors="coerce").fillna(0).sum())
        aceitas   = int(pd.to_numeric(chunk.get("numero_de_corridas_aceitas"), errors="coerce").fillna(0).sum())
        completas = int(pd.to_numeric(chunk.get("numero_de_corridas_completadas"), errors="coerce").fillna(0).sum())

        acc_pct  = (aceitas / ofertadas * 100) if ofertadas > 0 else 0.0
        comp_pct = (completas / aceitas * 100) if aceitas > 0 else 0.0

        online_pct = calcular_tempo_online(chunk)

        elegivel = (
            acc_pct >= ACEITACAO_MIN
            and comp_pct >= COMPLETAS_MIN
            and horas_online > 0
        )
        valor = horas_online * VALOR_ADICIONAL_HORA if elegivel else 0.0

        linhas.append({
            "data": dt.date(),
            "turno": turno,
            "ofertadas": ofertadas,
            "aceitas": aceitas,
            "completas": completas,
            "acc_pct": acc_pct,
            "comp_pct": comp_pct,
            "horas_online": horas_online,
            "tempo_online_hms": tempo_online_hms,
            "online_pct": online_pct,
            "elegivel": elegivel,
            "valor_adicional": valor,
        })

    if not linhas:
        st.info("Nenhum turno encontrado.")
        return

    resumo = pd.DataFrame(linhas).sort_values(["data", "turno"])

    # --------------------------
    # RESUMO GERAL DO PERÍODO
    # --------------------------
    total_elegiveis = resumo["elegivel"].sum()
    total_valor = resumo.loc[resumo["elegivel"], "valor_adicional"].sum()

    c1, c2 = st.columns(2)
    c1.metric("Turnos elegíveis", int(total_elegiveis))
    c2.metric("Total adicional no período", _fmt_moeda(total_valor))

    st.divider()

    # ================================
    # DETALHADO DIA → TURNO A TURNO
    # ================================
    for data, df_dia in resumo.groupby("data"):

        data_txt = pd.to_datetime(data).strftime("%d/%m/%Y")
        n_turnos = df_dia.shape[0]
        total_valor_dia = df_dia.loc[df_dia["elegivel"], "valor_adicional"].sum()

        with st.container(border=True):
            st.subheader(f"📅 {data_txt} — {n_turnos} turno(s)")
            st.caption(
                f"Elegíveis: {int(df_dia['elegivel'].sum())}/{n_turnos} • "
                f"Total do dia: {_fmt_moeda(total_valor_dia)}"
            )

            # ORGANIZA EM 2 COLUNAS
            registros = df_dia.to_dict(orient="records")
            for i in range(0, len(registros), 2):
                cols = st.columns(2)
                for col, row in zip(cols, registros[i:i+2]):
                    with col:
                        elegivel = bool(row["elegivel"])
                        with st.container(border=True):

                            st.markdown(f"### 🕒 Turno: **{row['turno']}**")

                            st.markdown(
                                f"- **Aceitação:** {_fmt_pct(row['acc_pct'])}  \n"
                                f"- **Completas:** {_fmt_pct(row['comp_pct'])}  \n"
                                f"- **Tempo online:** {row['tempo_online_hms']}  \n"
                                f"- **Online (%)**: {_fmt_pct(row['online_pct'])}  \n"
                                f"- **Ofertadas:** {row['ofertadas']}  \n"
                                f"- **Aceitas:** {row['aceitas']}  \n"
                                f"- **Completas:** {row['completas']}"
                            )

                            if elegivel:
                                st.success(
                                    f"**Elegível ao adicional!**\n\n"
                                    f"Valor: **{_fmt_moeda(row['valor_adicional'])}**\n"
                                    f"({row['horas_online']:.2f} h × R$ {VALOR_ADICIONAL_HORA:.2f}/h)"
                                )
                            else:
                                motivos = []
                                if row["acc_pct"] < ACEITACAO_MIN:
                                    motivos.append(f"aceitação < {ACEITACAO_MIN:.0f}%")
                                if row["comp_pct"] < COMPLETAS_MIN:
                                    motivos.append(f"completas < {COMPLETAS_MIN:.0f}%")
                                if row["horas_online"] <= 0:
                                    motivos.append("sem horas online")

                                motivos_txt = "; ".join(motivos) if motivos else "critérios não atendidos"

                                st.error(
                                    f"**Inelegível ao adicional**\n\n"
                                    f"_Motivo: {motivos_txt}_"
                                )

    st.divider()
    st.caption("Fim do relatório.")
