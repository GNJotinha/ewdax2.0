import streamlit as st
import pandas as pd
import calendar
from relatorios import classificar_entregadores


# ---------------------- Helpers básicos ---------------------- #

def _ativacao_mask(df_chunk: pd.DataFrame) -> pd.Series:
    """True para linhas em que houve alguma atuação (SH, corridas etc.)."""
    if df_chunk is None or df_chunk.empty:
        return pd.Series(False, index=(df_chunk.index if df_chunk is not None else []))

    seg = pd.to_numeric(df_chunk.get("segundos_abs", 0), errors="coerce").fillna(0)
    ofe = pd.to_numeric(df_chunk.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
    ace = pd.to_numeric(df_chunk.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
    com = pd.to_numeric(df_chunk.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)
    return (seg > 0) | (ofe > 0) | (ace > 0) | (com > 0)


def _projecao_sh(df_mes: pd.DataFrame, sh_atual: float, mes: int, ano: int) -> tuple[float, int, int, int]:
    """
    Retorna (sh_proj, dias_mes, dias_passados, dias_ativos).

    Projeção conservadora:
      - exige pelo menos 3 dias ativos no mês
      - limita média SH/dia ativo em 10h
      - projeta SH_extra = média_dia_ativo * dias_restantes
      - cap de SH projetado em 180h (não precisa mais que isso pra saber se bate 120)
    """
    dias_mes = calendar.monthrange(ano, mes)[1]

    if df_mes.empty or sh_atual <= 0:
        return 0.0, dias_mes, 0, 0

    # datas do mês
    if "data_do_periodo" in df_mes.columns:
        datas = pd.to_datetime(df_mes["data_do_periodo"], errors="coerce")
    else:
        datas = pd.to_datetime(df_mes["data"], errors="coerce")
    datas = datas.dropna()

    if datas.empty:
        return float(sh_atual), dias_mes, 0, 0

    # considera só datas do mês/ano alvo
    datas_mes = datas[(datas.dt.month == mes) & (datas.dt.year == ano)]
    if datas_mes.empty:
        return float(sh_atual), dias_mes, 0, 0

    ultimo_dia = datas_mes.max()
    dia_atual_mes = int(ultimo_dia.day)

    # dias com atuação
    mask_ativo = _ativacao_mask(df_mes)
    datas_ativas = datas_mes[mask_ativo.reindex(df_mes.index, fill_value=False)]
    dias_ativos = int(datas_ativas.dt.date.nunique()) if not datas_ativas.empty else 0

    # pouco dado => não inventa projeção
    if dias_ativos < 3 or dia_atual_mes <= 0:
        return float(sh_atual), dias_mes, dia_atual_mes, dias_ativos

    # média por dia ativo, com teto
    media_sh_dia_ativo = sh_atual / dias_ativos
    media_sh_dia_ativo = float(min(media_sh_dia_ativo, 10.0))  # teto 10h/dia

    dias_restantes = max(dias_mes - dia_atual_mes, 0)
    sh_extra = media_sh_dia_ativo * dias_restantes

    # cap em 180h pra não ficar bizarro
    sh_proj = min(sh_atual + sh_extra, 180.0)
    return float(sh_proj), dias_mes, dia_atual_mes, dias_ativos


def _score_proximidade(
    sh_proj: float,
    acc: float,
    conc: float,
    sh_meta: float = 120.0,
    acc_meta: float = 65.0,
    conc_meta: float = 95.0,
) -> float:
    """
    Score 0–100 de quão perto está do Premium, usando projeção de SH.
    Penaliza base muito baixa e clampa em [0, 100].
    """
    # normaliza cada critério em [0,1]
    p_sh = min(max(sh_proj / sh_meta, 0.0), 1.0) if sh_meta > 0 else 0.0
    p_acc = min(max(acc / acc_meta, 0.0), 1.0) if acc_meta > 0 else 0.0
    p_con = min(max(conc / conc_meta, 0.0), 1.0) if conc_meta > 0 else 0.0

    score = (0.4 * p_sh + 0.3 * p_acc + 0.3 * p_con) * 100.0

    # se os números ainda são muito baixos, dá uma segurada
    if sh_proj < 40 or acc < 40 or conc < 60:
        score *= 0.7

    score = max(0.0, min(score, 100.0))
    return float(round(score, 1))


def _tipo_acao(
    row,
    sh_meta: float = 120.0,
    acc_meta: float = 65.0,
    conc_meta: float = 95.0,
) -> str:
    """Texto de qual “coaching” faz mais sentido."""
    cat = str(row.get("categoria", "") or "")
    if cat == "Premium":
        return "✅ Já Premium"

    sh_proj = float(row.get("sh_proj", 0.0))
    acc = float(row.get("aceitacao_%", 0.0))
    conc = float(row.get("conclusao_%", 0.0))

    need_sh = sh_proj + 1e-6 < sh_meta
    need_acc = acc + 1e-6 < acc_meta
    need_conc = conc + 1e-6 < conc_meta

    if not need_sh and (need_acc or need_conc):
        return "🎯 Ajustar qualidade (aceitação/conclusão)"
    if need_sh and not (need_acc or need_conc):
        return "⏱️ Aumentar SH"
    if need_sh and (need_acc or need_conc):
        return "🔁 Ajustar SH + qualidade"
    return "✅ Manter performance"


# ---------------------- View principal ---------------------- #

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🚀 Quase Premium – Projeção e Oportunidades")

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    if "mes" not in df.columns or "ano" not in df.columns:
        st.error("Base sem colunas 'mes' e 'ano'.")
        return

    # Filtro de período (igual outras telas)
    col1, col2 = st.columns(2)
    mes_sel = col1.selectbox("Mês", list(range(1, 13)))
    anos_disp = sorted(df["ano"].dropna().unique().tolist(), reverse=True)
    ano_sel = col2.selectbox("Ano", anos_disp)

    df_mes = df[(df["mes"] == mes_sel) & (df["ano"] == ano_sel)].copy()
    if df_mes.empty:
        st.info("Nenhum dado para o período selecionado.")
        return

    # Classificação mensal usando as regras já existentes
    df_cat = classificar_entregadores(df, mes_sel, ano_sel)
    if df_cat.empty:
        st.info("Nenhum entregador classificado para esse período.")
        return

    # Garante coluna 'data' (date)
    if "data" not in df_mes.columns:
        if "data_do_periodo" in df_mes.columns:
            df_mes["data"] = pd.to_datetime(df_mes["data_do_periodo"], errors="coerce").dt.date
        else:
            st.error("Base sem coluna de data ('data' ou 'data_do_periodo').")
            return

    # KPIs gerais de categoria
    cont = (
        df_cat["categoria"]
        .value_counts()
        .reindex(["Premium", "Conectado", "Casual", "Flutuante"])
        .fillna(0)
        .astype(int)
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏆 Premium", int(cont.get("Premium", 0)))
    c2.metric("🎯 Conectado", int(cont.get("Conectado", 0)))
    c3.metric("👍 Casual", int(cont.get("Casual", 0)))
    c4.metric("↩ Flutuante", int(cont.get("Flutuante", 0)))

    # ---------------------- Monta base com projeção ---------------------- #

    registros = []
    sh_meta, acc_meta, conc_meta = 120.0, 65.0, 95.0

    for _, row in df_cat.iterrows():
        nome = row["pessoa_entregadora"]
        chunk = df_mes[df_mes["pessoa_entregadora"] == nome].copy()

        sh_atual = float(row.get("supply_hours", 0.0))
        acc = float(row.get("aceitacao_%", 0.0))
        conc = float(row.get("conclusao_%", 0.0))

        sh_proj, dias_mes, dias_passados, dias_ativos = _projecao_sh(chunk, sh_atual, mes_sel, ano_sel)
        media_dia_ativo = (sh_atual / dias_ativos) if dias_ativos > 0 else 0.0

        faltam_sh = max(sh_meta - sh_proj, 0.0)
        faltam_acc = max(acc_meta - acc, 0.0)
        faltam_conc = max(conc_meta - conc, 0.0)

        score = _score_proximidade(
            sh_proj,
            acc,
            conc,
            sh_meta=sh_meta,
            acc_meta=acc_meta,
            conc_meta=conc_meta,
        )

        registros.append(
            {
                "pessoa_entregadora": nome,
                "categoria": row.get("categoria"),
                "supply_hours": sh_atual,
                "aceitacao_%": acc,
                "conclusao_%": conc,
                "dias_ativos": dias_ativos,
                "dias_passados_no_mes": dias_passados,
                "dias_mes": dias_mes,
                "media_sh_dia_ativo": media_dia_ativo,
                "sh_proj": sh_proj,
                "faltam_sh_para_premium": faltam_sh,
                "faltam_acc_pontos": faltam_acc,
                "faltam_conc_pontos": faltam_conc,
                "score_proximidade": score,
            }
        )

    base = pd.DataFrame(registros)
    if base.empty:
        st.info("Sem base para projeção.")
        return

    base["tipo_acao"] = base.apply(_tipo_acao, axis=1)

    # badge visual pros bem próximos
    def _badge_score(row):
        s = float(row["score_proximidade"])
        if s >= 95:
            return "🔥 Muito perto"
        if s >= 85:
            return "🚀 Quase lá"
        if s >= 70:
            return "👀 Bom potencial"
        return "🧱 Longe ainda"

    base["tag_proximidade"] = base.apply(_badge_score, axis=1)

    # ---------------------- Filtros e exibição ---------------------- #

    score_min = st.slider(
        "Filtrar por score mínimo de proximidade",
        min_value=0,
        max_value=100,
        value=70,
        step=5,
        help="Mostra apenas quem está mais perto de virar Premium, considerando projeção de SH + aceitação + conclusão.",
    )

    # (opcional) não mostrar já Premium se quiser focar em 'quase'
    mostrar_premium = st.checkbox("Incluir quem já é Premium na lista", value=False)

    base_f = base[base["score_proximidade"] >= score_min].copy()
    if not mostrar_premium:
        base_f = base_f[base_f["categoria"] != "Premium"]

    base_f = base_f.sort_values(
        ["score_proximidade", "supply_hours"], ascending=[False, False]
    )

    st.subheader(f"Candidatos a Premium – {mes_sel:02d}/{ano_sel}")

    if base_f.empty:
        st.info("Nenhum entregador com score acima do limite selecionado.")
    else:
        cols_show = [
            "pessoa_entregadora",
            "categoria",
            "score_proximidade",
            "tag_proximidade",
            "supply_hours",
            "sh_proj",
            "media_sh_dia_ativo",
            "dias_ativos",
            "aceitacao_%",
            "conclusao_%",
            "faltam_sh_para_premium",
            "faltam_acc_pontos",
            "faltam_conc_pontos",
            "tipo_acao",
        ]

        fmt = {
            "score_proximidade": "{:.1f}",
            "supply_hours": "{:.1f}",
            "sh_proj": "{:.1f}",
            "media_sh_dia_ativo": "{:.2f}",
            "aceitacao_%": "{:.1f}",
            "conclusao_%": "{:.1f}",
            "faltam_sh_para_premium": "{:.1f}",
            "faltam_acc_pontos": "{:.1f}",
            "faltam_conc_pontos": "{:.1f}",
        }

        st.dataframe(
            base_f[cols_show]
            .rename(
                columns={
                    "pessoa_entregadora": "Entregador",
                    "categoria": "Categoria",
                    "score_proximidade": "Score proximidade",
                    "tag_proximidade": "Tag",
                    "supply_hours": "SH atual (h)",
                    "sh_proj": "SH proj. (h)",
                    "media_sh_dia_ativo": "Média SH/dia ativo",
                    "dias_ativos": "Dias ativos",
                    "aceitacao_%": "Aceitação %",
                    "conclusao_%": "Conclusão %",
                    "faltam_sh_para_premium": "Faltam SH (proj.)",
                    "faltam_acc_pontos": "Faltam p.p. aceitação",
                    "faltam_conc_pontos": "Faltam p.p. conclusão",
                    "tipo_acao": "Tipo de ação",
                }
            )
            .style.format(fmt),
            use_container_width=True,
        )

        csv = base_f[cols_show].to_csv(index=False, decimal=",").encode("utf-8")
        st.download_button(
            "⬇️ Baixar CSV (candidatos a Premium)",
            data=csv,
            file_name=f"quase_premium_{ano_sel}_{mes_sel:02d}.csv",
            mime="text/csv",
        )

    with st.expander("ℹ️ Como o score é calculado?"):
        st.markdown(
            """
            - O **score de proximidade (0–100)** considera:
              - Projeção de **SH** até o fim do mês (peso 40%)
              - **Aceitação** atual (peso 30%)
              - **Conclusão** atual (peso 30%)
            - Metas usadas para Premium:
              - SH ≥ **120h**
              - Aceitação ≥ **65%**
              - Conclusão ≥ **95%**
            - A projeção de SH:
              - usa média de horas por **dia ativo**
              - exige pelo menos **3 dias ativos** no mês
              - limita a média em 10h/dia e o total projetado em 180h,
                pra evitar projeções irreais no começo do mês.
            """
        )
