import streamlit as st
import pandas as pd

META_ELITE = 300
COL_ELITE = "numero_de_pedidos_aceitos_e_concluidos"


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🏆 Ranking ELITE (por mês)")
    st.caption("ELITE = soma de `numero_de_pedidos_aceitos_e_concluidos` no mês ≥ 300.")

    if df is None or df.empty:
        st.info("Sem dados.")
        return

    if COL_ELITE not in df.columns:
        st.error(f"Coluna obrigatória não encontrada: `{COL_ELITE}`")
        return

    d = df.copy()

    # garante mes_ano
    if "mes_ano" in d.columns:
        d["mes_ano"] = pd.to_datetime(d["mes_ano"], errors="coerce")
    elif "data_do_periodo" in d.columns:
        d["data_do_periodo"] = pd.to_datetime(d["data_do_periodo"], errors="coerce")
        d["mes_ano"] = d["data_do_periodo"].dt.to_period("M").dt.to_timestamp()
    elif "data" in d.columns:
        d["data"] = pd.to_datetime(d["data"], errors="coerce")
        d["mes_ano"] = d["data"].dt.to_period("M").dt.to_timestamp()
    else:
        st.error("Não achei coluna de data (mes_ano/data_do_periodo/data).")
        return

    meses = sorted([m for m in d["mes_ano"].dropna().unique().tolist()])
    if not meses:
        st.info("Sem meses válidos na base.")
        return

    mes_sel = st.selectbox(
        "Mês de referência",
        meses,
        index=len(meses) - 1,  # último mês disponível na base
        format_func=lambda ts: pd.to_datetime(ts).strftime("%b/%Y"),
    )

    d = d[d["mes_ano"] == pd.to_datetime(mes_sel)].copy()
    if d.empty:
        st.info("Sem dados no mês selecionado.")
        return

    # normaliza pedidos
    d[COL_ELITE] = pd.to_numeric(d[COL_ELITE], errors="coerce").fillna(0)

    # uuid
    if "uuid" not in d.columns:
        if "id_da_pessoa_entregadora" in d.columns:
            d["uuid"] = d["id_da_pessoa_entregadora"].astype(str)
        else:
            d["uuid"] = ""

    if "pessoa_entregadora" not in d.columns:
        st.error("Coluna `pessoa_entregadora` não encontrada.")
        return

    rank = (
        d.groupby(["uuid", "pessoa_entregadora"], as_index=False)[COL_ELITE]
        .sum()
        .rename(columns={COL_ELITE: "pedidos_ok_mes", "pessoa_entregadora": "nome"})
        .sort_values("pedidos_ok_mes", ascending=False)
    )

    rank["faltam_p_300"] = (META_ELITE - rank["pedidos_ok_mes"]).clip(lower=0).astype(int)
    rank["pct_meta"] = (rank["pedidos_ok_mes"] / META_ELITE).clip(upper=1.0)
    rank["elite"] = rank["pedidos_ok_mes"] >= META_ELITE

    c1, c2, c3 = st.columns(3)
    c1.metric("Entregadores no mês", f"{len(rank):,}".replace(",", "."))
    c2.metric("ELITEs", f"{int(rank['elite'].sum()):,}".replace(",", "."))
    c3.metric("Maior pontuação", f"{int(rank['pedidos_ok_mes'].max()):,}".replace(",", "."))

    only_close = st.checkbox("Mostrar só quem está perto (faltam ≤ 50)", value=False)
    if only_close:
        rank = rank[rank["faltam_p_300"] <= 50].copy()

    hide_elite = st.checkbox("Ocultar quem já é ELITE", value=False)
    if hide_elite:
        rank = rank[~rank["elite"]].copy()

    topn = st.slider("Top N", 20, 500, 100, step=10)
    rank = rank.head(topn).copy()

    # exibição com barra no % da meta
    def _bar(s):
        return [
            f"background: linear-gradient(90deg, rgba(0,191,255,0.45) {p*100:.1f}%, transparent {p*100:.1f}%);"
            for p in s
        ]

    show = rank[["uuid", "nome", "pedidos_ok_mes", "faltam_p_300", "elite", "pct_meta"]].copy()
    show["elite"] = show["elite"].map(lambda x: "✅" if x else "")
    show = show.rename(
        columns={
            "pedidos_ok_mes": "pedidos_ok (mês)",
            "faltam_p_300": "faltam p/ 300",
            "pct_meta": "% da meta",
        }
    )

    st.dataframe(
        show.style.format({"% da meta": "{:.0%}"}).apply(_bar, subset=["% da meta"]),
        use_container_width=True,
        hide_index=True,
    )
