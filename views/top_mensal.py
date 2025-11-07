import streamlit as st
import pandas as pd
from shared import sub_options_with_livre, apply_sub_filter


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🏆 Top Entregadores do Mês")

    if df is None or df.empty:
        st.info("❌ Sem dados carregados.")
        return

    # Garante colunas de mês/ano
    if "mes" not in df.columns or "ano" not in df.columns:
        st.error("Base sem colunas 'mes' e 'ano'. Verifique o carregamento dos dados.")
        return

    # ----------------------------
    # Escolha do mês/ano
    # ----------------------------
    mes_default = int(df["mes"].max())
    anos_disp = sorted(df["ano"].dropna().unique().tolist(), reverse=True)
    ano_default = int(max(anos_disp)) if anos_disp else None

    c1, c2 = st.columns(2)
    mes_sel = c1.selectbox("Mês", list(range(1, 13)), index=mes_default - 1)
    ano_sel = c2.selectbox(
        "Ano",
        anos_disp,
        index=anos_disp.index(ano_default) if ano_default in anos_disp else 0,
    )

    df_mes = df[(df["mes"] == mes_sel) & (df["ano"] == ano_sel)].copy()
    if df_mes.empty:
        st.info("❌ Nenhum dado para o mês/ano selecionado.")
        return

    # ----------------------------
    # Filtros extras (subpraça / turno)
    # ----------------------------
    cols1, cols2 = st.columns(2)

    # Subpraça (com LIVRE quando existir)
    if "sub_praca" in df_mes.columns:
        sub_opts = sub_options_with_livre(df_mes, praca_scope="SAO PAULO")
        sub_sel = cols1.multiselect("Filtrar por subpraça (opcional):", sub_opts)
    else:
        sub_sel = []

    # Turno
    if "periodo" in df_mes.columns:
        turnos = sorted(df_mes["periodo"].dropna().unique().tolist())
        turno_sel = cols2.multiselect("Filtrar por turnos (opcional):", turnos)
    else:
        turno_sel = []

    # Aplica filtros
    df_filtrado = apply_sub_filter(df_mes, sub_sel, praca_scope="SAO PAULO")
    if turno_sel:
        df_filtrado = df_filtrado[df_filtrado["periodo"].isin(turno_sel)]

    if df_filtrado.empty:
        st.info("❌ Nenhum dado após aplicar os filtros.")
        return

    # ----------------------------
    # Parâmetros do ranking
    # ----------------------------
    col_a, col_b = st.columns(2)
    min_ofertadas = int(
        col_a.number_input(
            "Mínimo de corridas ofertadas no mês para entrar no ranking",
            min_value=0,
            value=20,
            step=5,
        )
    )
    min_aceitas = int(
        col_b.number_input(
            "Mínimo de corridas aceitas no mês",
            min_value=0,
            value=10,
            step=5,
        )
    )

    # ----------------------------
    # Agrupamento por entregador
    # ----------------------------
    for c in [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_completadas",
    ]:
        if c in df_filtrado.columns:
            df_filtrado[c] = pd.to_numeric(df_filtrado[c], errors="coerce").fillna(0)

    base = (
        df_filtrado.groupby("pessoa_entregadora", dropna=True)
        .agg(
            ofertadas=("numero_de_corridas_ofertadas", "sum"),
            aceitas=("numero_de_corridas_aceitas", "sum"),
            completas=("numero_de_corridas_completadas", "sum"),
        )
        .reset_index()
    )

    if base.empty:
        st.info("❌ Nenhum entregador com atuação no período selecionado.")
        return

    # ----------------------------
    # Cálculo das taxas
    # ----------------------------
    base["ofertadas"] = base["ofertadas"].astype(int)
    base["aceitas"] = base["aceitas"].astype(int)
    base["completas"] = base["completas"].astype(int)

    # Proteção contra divisão por zero
    base["taxa_aceitacao"] = 0.0
    mask_ofe = base["ofertadas"] > 0
    base.loc[mask_ofe, "taxa_aceitacao"] = (
        base.loc[mask_ofe, "aceitas"] / base.loc[mask_ofe, "ofertadas"] * 100.0
    )

    base["taxa_conclusao"] = 0.0
    mask_ace = base["aceitas"] > 0
    base.loc[mask_ace, "taxa_conclusao"] = (
        base.loc[mask_ace, "completas"] / base.loc[mask_ace, "aceitas"] * 100.0
    )

    base["taxa_aceitacao"] = base["taxa_aceitacao"].round(2)
    base["taxa_conclusao"] = base["taxa_conclusao"].round(2)

    # ----------------------------
    # Filtro: conclusão 100% + mínimos
    # ----------------------------
    top = base.copy()
    # tolerância leve pra float (>= 99.99)
    top = top[
        (top["taxa_conclusao"] >= 99.99)
        & (top["ofertadas"] >= min_ofertadas)
        & (top["aceitas"] >= min_aceitas)
    ]

    if top.empty:
        st.info("⚠️ Nenhum entregador com 100% de conclusão dentro dos critérios mínimos.")
        return

    # Ordena por taxa de aceitação (desc), depois por aceitas
    top = top.sort_values(
        by=["taxa_aceitacao", "aceitas"], ascending=[False, False]
    ).reset_index(drop=True)

    top.insert(0, "Rank", top.index + 1)

    # ----------------------------
    # Tabela final
    # ----------------------------
    st.subheader(f"Ranking — {mes_sel:02d}/{ano_sel} (Conclusão 100%)")

    vis = (
        top[
            [
                "Rank",
                "pessoa_entregadora",
                "ofertadas",
                "aceitas",
                "completas",
                "taxa_aceitacao",
                "taxa_conclusao",
            ]
        ]
        .rename(
            columns={
                "pessoa_entregadora": "Entregador",
                "ofertadas": "Ofertadas",
                "aceitas": "Aceitas",
                "completas": "Completas",
                "taxa_aceitacao": "Aceitação (%)",
                "taxa_conclusao": "Conclusão (%)",
            }
        )
    )

    st.dataframe(
        vis.style.format(
            {
                "Aceitação (%)": "{:.2f}",
                "Conclusão (%)": "{:.2f}",
            }
        ),
        use_container_width=True,
    )

    st.caption(
        "🔍 Critério: apenas entregadores com **100% de conclusão no mês** "
        "e que atingem os mínimos de corridas ofertadas/aceitas definidos acima."
    )

    # ----------------------------
    # Download CSV
    # ----------------------------
    st.download_button(
        "⬇️ Baixar CSV (Top entregadores do mês)",
        data=top.to_csv(index=False, decimal=",").encode("utf-8"),
        file_name=f"top_entregadores_{ano_sel}_{mes_sel:02d}.csv",
        mime="text/csv",
        use_container_width=True,
    )
