import streamlit as st
import pandas as pd

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🚫 Quem NÃO atuou no mês atual")

    if "uuid" not in df.columns:
        if "id_da_pessoa_entregadora" in df.columns:
            df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
        else:
            df["uuid"] = ""

    df["data"] = pd.to_datetime(df.get("data"), errors="coerce")
    last_day = pd.to_datetime(df["data"]).max()
    if pd.isna(last_day):
        st.error("Sem datas válidas na base.")
        return
    mes_atual = int(last_day.month); ano_atual = int(last_day.year)

    meses_labels = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    base_meses = (
        df.dropna(subset=["data"])
          .assign(ano=df["data"].dt.year, mes=df["data"].dt.month)
          .groupby(["ano","mes"], as_index=False).size()
          .sort_values(["ano","mes"], ascending=[False, False])
    )
    base_meses = base_meses[~((base_meses["ano"] == ano_atual) & (base_meses["mes"] == mes_atual))]
    opcoes = [f"{int(r['mes']):02d}/{int(r['ano'])} - {meses_labels[int(r['mes'])-1]}" for _, r in base_meses.iterrows()]
    pares  = [(int(r["ano"]), int(r["mes"])) for _, r in base_meses.iterrows()]
    mapa = dict(zip(opcoes, pares))

    st.caption(f"Mês atual de comparação: **{mes_atual:02d}/{ano_atual} - {meses_labels[mes_atual-1]}**")
    escolhidos = st.multiselect("Selecione 1 ou mais meses de ORIGEM:", options=opcoes,
                                help="Mostra quem atuou em QUALQUER um desses meses e não atuou no mês atual.")

    def _ativos(df_base, mes, ano):
        d = df_base[(df_base["mes"] == mes) & (df_base["ano"] == ano)].copy()
        if d.empty: return set()
        soma = (
            pd.to_numeric(d.get("segundos_abs", 0), errors="coerce").fillna(0)
          + pd.to_numeric(d.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
          + pd.to_numeric(d.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
          + pd.to_numeric(d.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)
        )
        d = d.loc[soma > 0]
        if d.empty: return set()
        if "uuid" not in d.columns and "id_da_pessoa_entregadora" in d.columns:
            d["uuid"] = d["id_da_pessoa_entregadora"].astype(str)
        d["uuid"] = d["uuid"].astype(str)
        d = d[["pessoa_entregadora","uuid"]].dropna(subset=["pessoa_entregadora"]).drop_duplicates()
        return set(zip(d["pessoa_entregadora"], d["uuid"]))

    disabled = (len(escolhidos) == 0)
    if st.button("Gerar lista", type="primary", use_container_width=True, disabled=disabled):
        ativos_atual = _ativos(df, mes_atual, ano_atual)
        conjuntos = []
        for label in escolhidos:
            ano_i, mes_i = mapa[label]
            conjuntos.append(_ativos(df, mes_i, ano_i))
        origem = set.union(*conjuntos) if conjuntos else set()
        nao_atuou = origem - ativos_atual

        c1,c2,c3 = st.columns(3)
        c1.metric("Total nas origens", len(origem))
        c2.metric("Ativos no atual", len(ativos_atual))
        c3.metric("Não atuaram no atual", len(nao_atuou))

        def _to_df(s): return pd.DataFrame(sorted(list(s)), columns=["Nome","UUID"])
        out = _to_df(nao_atuou)
        if out.empty:
            st.success("Todos da(s) origem(ns) atuaram no mês atual. 🔥")
        else:
            st.dataframe(out, use_container_width=True)
            st.download_button("⬇️ Baixar CSV", data=out.to_csv(index=False).encode("utf-8"),
                               file_name=f"nao_atuou_{ano_atual}_{mes_atual:02d}.csv", mime="text/csv")
    else:
        if disabled:
            st.info("Selecione pelo menos **1** mês de origem para habilitar o botão.")
