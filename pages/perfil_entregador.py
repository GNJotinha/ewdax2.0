import streamlit as st
import pandas as pd
import plotly.express as px
from relatorios import utr_por_entregador_turno, classificar_entregadores
from shared import hms_from_hours

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("👤 Perfil do Entregador")

    nomes = sorted(df["pessoa_entregadora"].dropna().unique())
    nome = st.selectbox("Selecione o entregador:", [None] + nomes, format_func=lambda x: "" if x is None else x)
    if not nome:
        return

    df_e = df[df["pessoa_entregadora"] == nome].copy()
    if df_e.empty:
        st.info("❌ Nenhum dado para esse entregador no histórico.")
        return

    df_e["data"] = pd.to_datetime(df_e["data"], errors="coerce")
    df_e["mes_ano"] = df_e["data"].dt.to_period("M").dt.to_timestamp()

    ofertadas  = int(pd.to_numeric(df_e.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
    aceitas    = int(pd.to_numeric(df_e.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
    rejeitadas = int(pd.to_numeric(df_e.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum())
    completas  = int(pd.to_numeric(df_e.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0).sum())

    acc_pct  = (aceitas / ofertadas * 100) if ofertadas > 0 else 0.0
    rej_pct  = (rejeitadas/ ofertadas * 100) if ofertadas > 0 else 0.0
    comp_pct = (completas / aceitas * 100) if aceitas > 0 else 0.0

    horas_total = (df_e["segundos_abs"].sum() / 3600.0) if "segundos_abs" in df_e.columns else 0.0
    utr_abs_hist = (ofertadas / horas_total) if horas_total > 0 else 0.0
    base_u = utr_por_entregador_turno(df_e)
    if not base_u.empty:
        base_u = base_u[base_u["supply_hours"] > 0]
        utr_medias_hist = (base_u["corridas_ofertadas"] / base_u["supply_hours"]).mean() if not base_u.empty else 0.0
    else:
        utr_medias_hist = 0.0

    dias_ativos = int(df_e["data"].dt.date.nunique())
    ultima_atividade = df_e["data"].max()
    ultima_txt = ultima_atividade.strftime("%d/%m/%y") if pd.notna(ultima_atividade) else "—"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("UTR (Absoluto)", f"{utr_abs_hist:.2f}")
    c2.metric("UTR (Médias)",   f"{utr_medias_hist:.2f}")
    c3.metric("Aceitas",        f"{aceitas:,}".replace(",","."))
    c4.metric("Completas",      f"{completas:,}".replace(",","."))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Ofertadas", f"{ofertadas:,}".replace(",","."))
    c6.metric("Rejeitadas", f"{rejeitadas:,}".replace(",",".")); c6.caption(f"Rejeição: {rej_pct:.2f}%")
    c7.metric("Aceitação", f"{acc_pct:.2f}%")
    c8.metric("SH (hist.)", hms_from_hours(horas_total))

    c9, c10 = st.columns(2)
    c9.metric("Dias ativos", f"{dias_ativos}")
    c10.metric("Últ. dia", ultima_txt)

    mens = (df_e.groupby("mes_ano", as_index=False)
              .agg(ofertadas=("numero_de_corridas_ofertadas","sum"),
                   aceitas=("numero_de_corridas_aceitas","sum"),
                   completas=("numero_de_corridas_completadas","sum")))
    mens["acc_pct"] = mens.apply(lambda r: (r["aceitas"]/r["ofertadas"]*100) if r["ofertadas"]>0 else 0.0, axis=1)
    mens["mes_rotulo"] = pd.to_datetime(mens["mes_ano"]).dt.strftime("%b/%y")
    mens["__label_text__"] = mens.apply(lambda r: f"{int(r['completas'])} ({r['acc_pct']:.2f}%)", axis=1)

    fig = px.bar(mens, x="mes_rotulo", y="completas", text="__label_text__",
                 labels={"mes_rotulo":"Mês","completas":"Completas"},
                 title="Completas por mês • rótulo: N (acc%)",
                 template="plotly_dark", color_discrete_sequence=["#00BFFF"])
    st.plotly_chart(fig, use_container_width=True)

    # Histórico de categoria por mês
    meses_unicos = (df["mes_ano"].dropna().sort_values().unique().tolist())
    hist = []
    for ts in meses_unicos:
        ts = pd.to_datetime(ts)
        mes_i, ano_i = int(ts.month), int(ts.year)
        df_cat = classificar_entregadores(df, mes_i, ano_i)
        row = df_cat[df_cat["pessoa_entregadora"] == nome]
        if not row.empty:
            hist.append({ "mes_ano": ts, "categoria": str(row.iloc[0]["categoria"]),
                          "supply_hours": float(row.iloc[0]["supply_hours"]),
                          "aceitacao_%": float(row.iloc[0]["aceitacao_%"]),
                          "conclusao_%": float(row.iloc[0]["conclusao_%"]), })
    if hist:
        hist_df = pd.DataFrame(hist).sort_values("mes_ano")
        hist_df["Mês"] = hist_df["mes_ano"].dt.strftime("%b/%y")
        hist_df["SH (HH:MM:SS)"] = hist_df["supply_hours"].apply(hms_from_hours)
        st.dataframe(hist_df[["Mês","categoria","SH (HH:MM:SS)","aceitacao_%","conclusao_%"]]
                     .rename(columns={"categoria":"Categoria","aceitacao_%":"Aceitação %","conclusao_%":"Conclusão %"})
                     .style.format({"Aceitação %":"{:.2f}","Conclusão %":"{:.2f}"}),
                     use_container_width=True)
