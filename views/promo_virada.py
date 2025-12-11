import streamlit as st
import pandas as pd

ACEITACAO_MIN = 75.0
CONCLUSAO_MIN = 95.0


def _pct(num, den):
    if den is None or den == 0:
        return 0.0
    try:
        return float(num) / float(den) * 100.0
    except Exception:
        return 0.0


def _style_row(row):
    """
    Estilo visual da linha no dataframe exibido.

    Regras:
      - TODO elegível: fundo verde suave.
      - TOP 20 & elegível: verde mais forte.
      - TOP 3 & elegível: verde bem destacado + negrito.
      - TOP 20 & NÃO elegível: vermelho forte (alerta, sobrescreve qualquer coisa).
      - Demais: padrão.

    Obs: aqui os nomes já estão RENOMEADOS: 'Posição' e 'Elegível'.
    """
    pos = row["Posição"]
    elegivel = (row["Elegível"] == "Sim")

    # base: sem estilo
    styles = [""] * len(row)

    # base para qualquer elegível (inclusive fora do top 20)
    if elegivel:
        styles = [
            "background-color: #101f18; color: #d4f6df;"
        ] * len(row)

    # top 20 elegível: reforça o verde
    if pos <= 20 and elegivel:
        styles = [
            "background-color: #123322; color: #d4f6df;"
        ] * len(row)

    # top 3 elegível: ainda mais destaque
    if pos <= 3 and elegivel:
        styles = [
            "background-color: #0f3b22; color: #d4f6df; font-weight: bold;"
        ] * len(row)

    # top 20 NÃO elegível: vermelho (sempre sobrescreve)
    if pos <= 20 and not elegivel:
        styles = [
            "background-color: #4a1111; color: #ffb3b3; font-weight: bold;"
        ] * len(row)

    return styles


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🎉 Promoção da Virada — Ranking")

    # valida coluna de valor
    if "soma_das_taxas_das_corridas_aceitas" not in df.columns:
        st.error("Coluna 'soma_das_taxas_das_corridas_aceitas' não encontrada na base.")
        st.stop()

    # garante coluna de data
    base = df.copy()
    if "data" in base.columns:
        base["data"] = pd.to_datetime(base["data"], errors="coerce")
    elif "data_do_periodo" in base.columns:
        base["data"] = pd.to_datetime(base["data_do_periodo"], errors="coerce")
    else:
        st.error("Coluna de data ausente (esperado 'data' ou 'data_do_periodo').")
        st.stop()

    base = base.dropna(subset=["data"])
    if base.empty:
        st.info("Sem dados válidos.")
        st.stop()

    # 📆 Período fixo da promoção
    inicio_promo = pd.Timestamp(2025, 12, 8)
    fim_promo = pd.Timestamp(2026, 1, 20)

    st.caption(
        f"Período da promoção: **{inicio_promo.strftime('%d/%m/%Y')} a {fim_promo.strftime('%d/%m/%Y')}**"
    )
    st.caption(
        f"Critérios de elegibilidade: Aceitação ≥ {ACEITACAO_MIN:.0f}% • Conclusão ≥ {CONCLUSAO_MIN:.0f}% (no período)"
    )

    base_periodo = base[(base["data"] >= inicio_promo) & (base["data"] <= fim_promo)].copy()
    if base_periodo.empty:
        st.info("❌ Nenhum dado no período da promoção.")
        st.stop()

    # normaliza números principais
    for c in [
        "numero_de_corridas_ofertadas",
        "numero_de_corridas_aceitas",
        "numero_de_corridas_completadas",
        "soma_das_taxas_das_corridas_aceitas",
    ]:
        if c in base_periodo.columns:
            base_periodo[c] = pd.to_numeric(base_periodo[c], errors="coerce").fillna(0)

    # =========================
    # 🧮 RANKING GERAL PROMO
    # =========================

    # agrupa por entregador (período inteiro)
    grp = (
        base_periodo
        .groupby("pessoa_entregadora", dropna=True, as_index=False)
        .agg(
            ofertadas=("numero_de_corridas_ofertadas", "sum"),
            aceitas=("numero_de_corridas_aceitas", "sum"),
            completas=("numero_de_corridas_completadas", "sum"),
            valor_centavos=("soma_das_taxas_das_corridas_aceitas", "sum"),
        )
    )

    if grp.empty:
        st.info("Nenhum entregador com dados no período.")
        st.stop()

    # métricas de % e valor R$
    grp["aceitacao_%"] = grp.apply(lambda r: _pct(r["aceitas"], r["ofertadas"]), axis=1)
    grp["conclusao_%"] = grp.apply(lambda r: _pct(r["completas"], r["aceitas"]), axis=1)
    grp["valor_reais"] = grp["valor_centavos"] / 100.0

    # ranking geral: só quem teve atuação real
    ranking = grp.copy()
    ranking = ranking[(ranking["ofertadas"] > 0) & (ranking["aceitas"] > 0)]
    if ranking.empty:
        st.info("Ninguém com ofertadas/aceitas > 0 no período.")
        st.stop()

    # ordena por valor e gera posição
    ranking = ranking.sort_values("valor_reais", ascending=False).reset_index(drop=True)
    ranking["posicao"] = ranking.index + 1

    # flag de elegibilidade
    ranking["elegivel"] = (
        (ranking["aceitacao_%"] >= ACEITACAO_MIN)
        & (ranking["conclusao_%"] >= CONCLUSAO_MIN)
    )

    total_participantes = int(ranking.shape[0])
    total_elegiveis = int(ranking[ranking["elegivel"]].shape[0])

    c1, c2 = st.columns(2)
    c1.metric("Total no ranking (geral)", total_participantes)
    c2.metric("Elegíveis (bateram os critérios)", total_elegiveis)

    st.divider()

    # 🔘 filtro: só elegíveis (visão geral)
    only_eligible = st.checkbox("Mostrar apenas elegíveis (ranking geral)", value=False)

    # visão principal: até o 75º colocado
    view = ranking[ranking["posicao"] <= 75].copy()
    if only_eligible:
        view = view[view["elegivel"]]

    if view.empty:
        st.info("Nenhum entregador para mostrar com os filtros atuais.")
    else:
        # prepara colunas visíveis (sem ofertadas/aceitas)
        cols_show = [
            "posicao",
            "pessoa_entregadora",
            "completas",
            "aceitacao_%",
            "conclusao_%",
            "valor_reais",
            "elegivel",
        ]
        view = view[cols_show].copy()
        view["aceitacao_%"] = view["aceitacao_%"].round(2)
        view["conclusao_%"] = view["conclusao_%"].round(2)
        view["valor_reais"] = view["valor_reais"].round(2)
        view["elegivel"] = view["elegivel"].map({True: "Sim", False: "Não"})

        # renomeia pra exibição
        df_display = view.rename(
            columns={
                "posicao": "Posição",
                "pessoa_entregadora": "Entregador",
                "completas": "Completas",
                "aceitacao_%": "Aceitação (%)",
                "conclusao_%": "Conclusão (%)",
                "valor_reais": "Valor (R$)",
                "elegivel": "Elegível",
            }
        )

        view_styled = (
            df_display.style
            .apply(_style_row, axis=1)
            .format(
                {
                    "Aceitação (%)": "{:.2f}",
                    "Conclusão (%)": "{:.2f}",
                    "Valor (R$)": "{:.2f}",
                }
            )
            .hide(axis="index")
        )

        st.subheader("🏆 Ranking Geral (até o 75º colocado)")
        st.caption(
            "🟢 Todos os elegíveis aparecem em verde (Top 3 e Top 20 com mais destaque) • "
            "🔴 Em vermelho: quem está no TOP 20 em valor mas NÃO bateu os critérios."
        )
        st.dataframe(view_styled, use_container_width=True)

    # 📥 Download CSV – ranking completo (na mesma pegada visual)
    csv_cols = [
        "posicao",
        "pessoa_entregadora",
        "completas",
        "aceitacao_%",
        "conclusao_%",
        "valor_reais",
        "elegivel",
    ]
    csv_out = ranking[csv_cols].copy()
    csv_out["aceitacao_%"] = csv_out["aceitacao_%"].round(2)
    csv_out["conclusao_%"] = csv_out["conclusao_%"].round(2)
    csv_out["valor_reais"] = csv_out["valor_reais"].round(2)
    csv_out["elegivel"] = csv_out["elegivel"].map({True: "Sim", False: "Não"})

    st.download_button(
        "⬇️ Baixar ranking completo (com flag de elegibilidade)",
        data=csv_out.to_csv(index=False, decimal=",").encode("utf-8"),
        file_name="promocao_virada_ranking_completo.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # =========================
    # 🏅 TOP 10 SEMANAL (SEG–DOM)
    # =========================

    st.divider()
    st.subheader("🏅 Top 10 Semanal (Seg a Dom)")

    # cria coluna de semana (semana termina no domingo -> começa na segunda)
    base_periodo["semana"] = base_periodo["data"].dt.to_period("W-SUN")

    # agrupa por semana + entregador
    grp_semana = (
        base_periodo
        .groupby(["semana", "pessoa_entregadora"], dropna=True, as_index=False)
        .agg(
            ofertadas=("numero_de_corridas_ofertadas", "sum"),
            aceitas=("numero_de_corridas_aceitas", "sum"),
            completas=("numero_de_corridas_completadas", "sum"),
            valor_centavos=("soma_das_taxas_das_corridas_aceitas", "sum"),
        )
    )

    if grp_semana.empty:
        st.info("Nenhum dado semanal disponível no período.")
        return

    # opções de semana existentes (ordenadas da mais recente pra mais antiga)
    semanas_unicas = sorted(grp_semana["semana"].unique().tolist(), reverse=True)

    def _format_semana(p: pd.Period) -> str:
        ini = p.start_time
        fim = p.end_time
        # ex: 08/12 a 14/12/2025
        if ini.year == fim.year:
            return f"{ini.strftime('%d/%m')} a {fim.strftime('%d/%m/%Y')}"
        # caso pegue virada de ano
        return f"{ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"

    semana_sel = st.selectbox(
        "Selecione a semana (Seg–Dom):",
        options=semanas_unicas,
        format_func=_format_semana,
    )

    # filtra só a semana escolhida
    semana_df = grp_semana[grp_semana["semana"] == semana_sel].copy()

    if semana_df.empty:
        st.info("Sem dados para a semana selecionada.")
        return

    # métricas semanais
    semana_df["aceitacao_%"] = semana_df.apply(lambda r: _pct(r["aceitas"], r["ofertadas"]), axis=1)
    semana_df["conclusao_%"] = semana_df.apply(lambda r: _pct(r["completas"], r["aceitas"]), axis=1)
    semana_df["valor_reais"] = semana_df["valor_centavos"] / 100.0

    # só quem de fato atuou
    semana_rank = semana_df[(semana_df["ofertadas"] > 0) & (semana_df["aceitas"] > 0)].copy()
    if semana_rank.empty:
        st.info("Ninguém com ofertadas/aceitas > 0 na semana selecionada.")
        return

    # ordena por valor e pega posição
    semana_rank = semana_rank.sort_values("valor_reais", ascending=False).reset_index(drop=True)
    semana_rank["posicao"] = semana_rank.index + 1

    # flag de elegibilidade semanal
    semana_rank["elegivel"] = (
        (semana_rank["aceitacao_%"] >= ACEITACAO_MIN)
        & (semana_rank["conclusao_%"] >= CONCLUSAO_MIN)
    )

    total_part_semana = int(semana_rank.shape[0])
    total_eleg_semana = int(semana_rank[semana_rank["elegivel"]].shape[0])

    c3, c4 = st.columns(2)
    c3.metric("Participantes na semana", total_part_semana)
    c4.metric("Elegíveis na semana", total_eleg_semana)

    # checkbox pra ver só elegíveis no ranking semanal
    only_eligible_week = st.checkbox("Mostrar apenas elegíveis (Top 10 semanal)", value=False)

    # recorta Top 10
    semana_view = semana_rank[semana_rank["posicao"] <= 10].copy()
    if only_eligible_week:
        semana_view = semana_view[semana_view["elegivel"]]

    if semana_view.empty:
        st.info("Nenhum entregador para mostrar com os filtros atuais (Top 10).")
        return

    cols_week_show = [
        "posicao",
        "pessoa_entregadora",
        "completas",
        "aceitacao_%",
        "conclusao_%",
        "valor_reais",
        "elegivel",
    ]
    semana_view = semana_view[cols_week_show].copy()
    semana_view["aceitacao_%"] = semana_view["aceitacao_%"].round(2)
    semana_view["conclusao_%"] = semana_view["conclusao_%"].round(2)
    semana_view["valor_reais"] = semana_view["valor_reais"].round(2)
    semana_view["elegivel"] = semana_view["elegivel"].map({True: "Sim", False: "Não"})

    df_week_display = semana_view.rename(
        columns={
            "posicao": "Posição",
            "pessoa_entregadora": "Entregador",
            "completas": "Completas",
            "aceitacao_%": "Aceitação (%)",
            "conclusao_%": "Conclusão (%)",
            "valor_reais": "Valor (R$)",
            "elegivel": "Elegível"
        }
    )

    week_styled = (
        df_week_display.style
        .apply(_style_row, axis=1)
        .format(
            {
                "Aceitação (%)": "{:.2f}",
                "Conclusão (%)": "{:.2f}",
                "Valor (R$)": "{:.2f}",
            }
        )
        .hide(axis="index")
    )

    st.caption("Top 10 da semana, ordenado por **Valor (R$)**, com os mesmos critérios de elegibilidade da promoção.")
    st.dataframe(week_styled, use_container_width=True)
