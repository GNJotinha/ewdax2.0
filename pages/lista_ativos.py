import streamlit as st
import pandas as pd
from shared import sub_options_with_livre, apply_sub_filter

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("👤 Lista de Entregadores Ativos")

    if "uuid" not in df.columns:
        if "id_da_pessoa_entregadora" in df.columns:
            df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
        else:
            df["uuid"] = ""

    df["data"] = pd.to_datetime(df.get("data"), errors="coerce")
    data_min = pd.to_datetime(df["data"]).min().date()
    data_max = pd.to_datetime(df["data"]).max().date()
    periodo = st.date_input("Selecione o intervalo:", [data_min, data_max], format="DD/MM/YYYY")

    sub_opts = sub_options_with_livre(df, praca_scope="SAO PAULO")
    filtro_sub = st.multiselect("Filtrar por subpraça:", sub_opts)
    turnos = sorted([x for x in df.get("periodo", pd.Series(dtype=object)).dropna().unique()])
    filtro_turno = st.multiselect("Filtrar por turno:", turnos)

    df_sel = df.copy()
    if len(periodo) == 2:
        ini, fim = pd.to_datetime(periodo[0]), pd.to_datetime(periodo[1])
        df_sel = df_sel[(df_sel["data"] >= ini) & (df_sel["data"] <= fim)]
    elif len(periodo) == 1:
        dia = pd.to_datetime(periodo[0])
        df_sel = df_sel[df_sel["data"] == dia]

    df_sel = apply_sub_filter(df_sel, filtro_sub, praca_scope="SAO PAULO")
    if filtro_turno:
        df_sel = df_sel[df_sel["periodo"].isin(filtro_turno)]

    soma = (
        pd.to_numeric(df_sel.get("segundos_abs", 0), errors="coerce").fillna(0)
      + pd.to_numeric(df_sel.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
      + pd.to_numeric(df_sel.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
      + pd.to_numeric(df_sel.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)
    )
    df_sel = df_sel.loc[soma > 0]

    if df_sel.empty:
        st.info("❌ Nenhum entregador ativo no período/filtros selecionados.")
    else:
        base = (df_sel[["pessoa_entregadora","uuid"]]
                .dropna(subset=["pessoa_entregadora"])
                .drop_duplicates()
                .sort_values("pessoa_entregadora"))
        st.metric("Total de ativos no período", int(base.shape[0]))
        st.dataframe(base.rename(columns={"pessoa_entregadora":"Nome","uuid":"UUID"}).reset_index(drop=True), use_container_width=True)
        st.download_button("⬇️ Baixar CSV", data=base.to_csv(index=False).encode("utf-8"),
                           file_name="lista_ativos.csv", mime="text/csv")
