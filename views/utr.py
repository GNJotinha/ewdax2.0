import streamlit as st
import pandas as pd
import plotly.express as px
from relatorios import utr_por_entregador_turno
from shared import is_absoluto, is_medias, sub_options_with_livre, apply_sub_filter, hms_from_hours

def _serie_diaria(base_plot: pd.DataFrame, metodo: str) -> pd.DataFrame:
    if base_plot.empty:
        return pd.DataFrame(columns=["dia_num","utr_val"])
    d = base_plot.copy()
    d["data"] = pd.to_datetime(d["data"])
    d["dia_num"] = d["data"].dt.day
    if is_medias(metodo):
        d = d[d["supply_hours"] > 0].copy()
        if d.empty: return pd.DataFrame(columns=["dia_num","utr_val"])
        d["utr_linha"] = d["corridas_ofertadas"] / d["supply_hours"]
        out = d.groupby("dia_num", as_index=False)["utr_linha"].mean().rename(columns={"utr_linha":"utr_val"})
        return out.sort_values("dia_num")
    agg = d.groupby("dia_num", as_index=False).agg(ofertadas=("corridas_ofertadas","sum"), horas=("supply_hours","sum"))
    agg["utr_val"] = agg.apply(lambda r: (r["ofertadas"]/r["horas"]) if r["horas"]>0 else 0.0, axis=1)
    return agg[["dia_num","utr_val"]].sort_values("dia_num")

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🧭 UTR – Corridas ofertadas por hora")
    col1, col2 = st.columns(2)
    mes_sel = col1.selectbox("Mês", list(range(1, 13)))
    ano_sel = col2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

    df_mm = df[(df["mes"] == mes_sel) & (df["ano"] == ano_sel)]
    if "sub_praca" in df.columns:
        sub_opts = sub_options_with_livre(df_mm, praca_scope="SAO PAULO")
        sub_sel = st.multiselect("Filtrar por subpraça (opcional):", sub_opts)
    else:
        sub_sel = []

    df_base = apply_sub_filter(df.copy(), sub_sel, praca_scope="SAO PAULO")
    base_full = utr_por_entregador_turno(df_base, mes_sel, ano_sel)
    if base_full.empty:
        st.info("Nenhum dado encontrado para o período/filtros.")
        return

    if "supply_hours" in base_full.columns:
        base_full["tempo_hms"] = base_full["supply_hours"].apply(hms_from_hours)

    turnos = ["Todos os turnos"]
    if "periodo" in base_full.columns:
        turnos += sorted([t for t in base_full["periodo"].dropna().unique()])
    turno_sel = st.selectbox("Turno", options=turnos, index=0)

    metodo = st.radio("Método", ["Absoluto","Médias"], horizontal=True, index=0)

    base_plot = base_full if turno_sel == "Todos os turnos" else base_full[base_full["periodo"] == turno_sel]
    if base_plot.empty:
        st.info("Sem dados para o turno selecionado dentro dos filtros.")
        return

    serie = _serie_diaria(base_plot, metodo)
    y_max = float(serie["utr_val"].max())*1.25 if not serie.empty else 1.0

    sub_sufixo = ""
    if sub_sel:
        sub_sufixo = " • Subpraça: " + (", ".join(sub_sel) if len(sub_sel)<=3 else f"{len(sub_sel)} selecionadas")

    fig = px.bar(serie, x="dia_num", y="utr_val", text="utr_val",
                 title=f"UTR por dia – {mes_sel:02d}/{ano_sel} • {(turno_sel if turno_sel!='Todos os turnos' else 'Todos os turnos')} • {metodo}{sub_sufixo}",
                 labels={"dia_num":"Dia do mês","utr_val":"UTR (ofertadas/hora)"}, template="plotly_dark",
                 color_discrete_sequence=["#00BFFF"])
    fig.update_traces(texttemplate="<b>%{text:.2f}</b>", textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    # Métrica do mês
    if is_absoluto(metodo):
        ofertadas = base_plot["corridas_ofertadas"].sum()
        horas = base_plot["supply_hours"].sum()
        utr_mes = (ofertadas/horas) if horas>0 else 0.0
    else:
        base_ok = base_plot[base_plot["supply_hours"]>0]
        utr_mes = (base_ok["corridas_ofertadas"]/base_ok["supply_hours"]).mean() if not base_ok.empty else 0.0

    st.metric(f"Média UTR no mês ({metodo.lower()})", f"{utr_mes:.2f}")

    # CSV (geral, sem filtro de turno)
    cols_csv = ["data","pessoa_entregadora","periodo","tempo_hms","corridas_ofertadas","UTR"]
    base_csv = base_full.copy()
    try: base_csv["data"] = pd.to_datetime(base_csv["data"]).dt.strftime("%d/%m/%Y")
    except Exception: base_csv["data"] = base_csv["data"].astype(str)
    for c in cols_csv:
        if c not in base_csv.columns: base_csv[c] = None
    base_csv["UTR"] = pd.to_numeric(base_csv["UTR"], errors="coerce").round(2)
    base_csv["corridas_ofertadas"] = pd.to_numeric(base_csv["corridas_ofertadas"], errors="coerce").fillna(0).astype(int)

    file_name = f"utr_entregador_turno_diario_{mes_sel:02d}_{ano_sel}"
    if sub_sel:
        tag = "_".join([s.replace(" ","") for s in sub_sel[:2]])
        if len(sub_sel)>2: tag += f"_e{len(sub_sel)-2}mais"
        file_name += f"_{tag}"
    st.download_button("⬇️ Baixar CSV (GERAL)", data=base_csv[cols_csv].to_csv(index=False).encode("utf-8"),
                       file_name=f"{file_name}.csv", mime="text/csv")
