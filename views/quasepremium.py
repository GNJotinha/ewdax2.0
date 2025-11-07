import streamlit as st
import pandas as pd
import calendar
from relatorios import classificar_entregadores


# =========================
# Helpers
# =========================

def _ativacao_mask(df_chunk: pd.DataFrame) -> pd.Series:
    """True para linhas em que houve atuação (tempo ou corridas)."""
    if df_chunk is None or df_chunk.empty:
        return pd.Series(False, index=(df_chunk.index if df_chunk is not None else []))

    seg = pd.to_numeric(df_chunk.get("segundos_abs", 0), errors="coerce").fillna(0)
    ofe = pd.to_numeric(df_chunk.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
    ace = pd.to_numeric(df_chunk.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
    com = pd.to_numeric(df_chunk.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)

    return (seg > 0) | (ofe > 0) | (ace > 0) | (com > 0)


def _dias_ativos_entregador(df_mes_ent: pd.DataFrame, mes: int, ano: int) -> int:
    """Conta quantos dias do mês o entregador atuou de fato."""
    if df_mes_ent is None or df_mes_ent.empty:
        return 0

    if "data_do_periodo" in df_mes_ent.columns:
        datas = pd.to_datetime(df_mes_ent["data_do_periodo"], errors="coerce")
    else:
        datas = pd.to_datetime(df_mes_ent.get("data"), errors="coerce")

    datas = datas.dropna()
    datas_mes = datas[(datas.dt.year == ano) & (datas.dt.month == mes)]
    if datas_mes.empty:
        return 0

    mask_ativo = _ativacao_mask(df_mes_ent)
    datas_ativas = datas_mes[mask_ativo.reindex(df_mes_ent.index, fill_value=False)]
    if datas_ativas.empty:
        return 0

    return int(datas_ativas.dt.date.nunique())


def _premium_hits(sh: float, acc: float, conc: float,
                  sh_meta: float = 120.0, acc_meta: float = 65.0, conc_meta: float = 95.0) -> tuple[int, str]:
    """Conta quantos critérios Premium o entregador já cumpre (0 a 3)."""
    hits = [
        sh >= sh_meta,
        acc >= acc_meta,
        conc >= conc_meta,
    ]
    n_hits = sum(hits)
    desc = f"{n_hits}/3 critérios Premium"
    return n_hits, desc


def _tag_proximidade(n_hits: int, categoria: str) -> str:
    """Tag visual baseada na quantidade de critérios Premium batidos."""
    if str(categoria) == "Premium":
        return "🏆 Já Premium"
    if n_hits == 2:
        return "🚀 Quase Premium"
    if n_hits == 1:
        return "👀 Bom potencial"
    return "🧱 Longe ainda"


def _fmt_1(v):
    """Formata com 1 casa decimal."""
    try:
        return f"{float(v):.1f}"
    except Exception:
        return v


def _fmt_1_blank_zero(v):
    """1 casa decimal, mas troca zero por '—' pra não poluir."""
    try:
        val = float(v)
        if abs(val) < 1e-9:
            return "—"
        return f"{val:.1f}"
    except Exception:
        return v


# =========================
# View principal
# =========================

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🚀 Quase Premium – Ritmo, Presença e Aceitação")

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    if "mes" not in df.columns or "ano" not in df.columns:
        st.error("Base sem colunas 'mes' e 'ano'.")
        return

    # ---------- Filtro de período ----------
    col1, col2 = st.columns(2)
    mes_sel = col1.selectbox("Mês", list(range(1, 13)))
    anos_disp = sorted(df["ano"].dropna().unique().tolist(), reverse=True)
    ano_sel = col2.selectbox("Ano", anos_disp)

    df_mes = df[(df["mes"] == mes_sel) & (df["ano"] == ano_sel)].copy()
    if df_mes.empty:
        st.info("Nenhum dado para o período selecionado.")
        return

    # ---------- Classificação mensal ----------
    df_cat = classificar_entregadores(df, mes_sel, ano_sel)
    if df_cat.empty:
        st.info("Nenhum entregador classificado para esse período.")
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

    # ---------- Construção da base ----------
    registros = []
    sh_meta, acc_meta, conc_meta = 120.0, 65.0, 95.0
    dias_totais_mes = calendar.monthrange(ano_sel, mes_sel)[1]

    for _, row in df_cat.iterrows():
        nome = row["pessoa_entregadora"]
        categoria = row.get("categoria")

        sh = float(row.get("supply_hours", 0.0))
        acc = float(row.get("aceitacao_%", 0.0))
        conc = float(row.get("conclusao_%", 0.0))

        # recorte do mês só deste entregador
        chunk = df_mes[df_mes["pessoa_entregadora"] == nome].copy()
        dias_ativos = _dias_ativos_entregador(chunk, mes_sel, ano_sel)
        media_sh_dia_ativo = (sh / dias_ativos) if dias_ativos > 0 else 0.0
        sh_proj = media_sh_dia_ativo * dias_totais_mes

        # quanto falta pra bater os critérios de Premium
        faltam_sh = max(sh_meta - sh, 0.0)
        faltam_acc = max(acc_meta - acc, 0.0)
        faltam_conc = max(conc_meta - conc, 0.0)

        n_hits, hits_desc = _premium_hits(sh, acc, conc, sh_meta, acc_meta, conc_meta)
        tag = _tag_proximidade(n_hits, categoria)

        registros.append(
            {
                "pessoa_entregadora": nome,
                "categoria": categoria,
                "supply_hours": sh,
                "sh_proj": sh_proj,
                "aceitacao_%": acc,
                "conclusao_%": conc,
                "dias_ativos": dias_ativos,
                "media_sh_dia_ativo": media_sh_dia_ativo,
                "faltam_sh_para_premium": faltam_sh,
                "faltam_acc_pontos": faltam_acc,
                "faltam_conc_pontos": faltam_conc,
                "premium_hits": n_hits,
                "premium_hits_desc": hits_desc,
                "tag_proximidade": tag,
            }
        )

    base = pd.DataFrame(registros)
    if base.empty:
        st.info("Sem base para análise.")
        return

    # ---------- Filtros ----------
    st.subheader(f"Visão geral – {mes_sel:02d}/{ano_sel}")

    colf1, colf2 = st.columns(2)
    incluir_premium = colf1.checkbox("Incluir quem já é Premium na lista", value=False)
    min_hits = colf2.slider(
        "Mínimo de critérios Premium já batidos",
        min_value=0,
        max_value=3,
        value=1,
        step=1,
        help="0 = mostra todo mundo; 1 = pelo menos um critério; 2 = quem está realmente perto."
    )

    base_f = base.copy()
    if not incluir_premium:
        base_f = base_f[base_f["categoria"] != "Premium"]

    base_f = base_f[base_f["premium_hits"] >= min_hits]

    base_f = base_f.sort_values(
        ["premium_hits", "supply_hours"], ascending=[False, False]
    )

    if base_f.empty:
        st.info("Nenhum entregador dentro dos filtros atuais.")
        return

    # ---------- Destacar SH alto + aceitação baixa ----------
    SH_ALTO = 100  # pode ajustar conforme a operação
    ACEITACAO_BAIXA = 65

    def highlight_row(row):
        if row["supply_hours"] >= SH_ALTO and row["aceitacao_%"] < ACEITACAO_BAIXA:
            return ["background-color: #ffcccc"] * len(row)  # vermelho claro
        return [""] * len(row)

    # ---------- Tabela ----------
    cols_show = [
        "pessoa_entregadora",
        "categoria",
        "tag_proximidade",
        "premium_hits_desc",
        "supply_hours",
        "sh_proj",
        "media_sh_dia_ativo",
        "dias_ativos",
        "aceitacao_%",
        "conclusao_%",
        "faltam_sh_para_premium",
        "faltam_acc_pontos",
        "faltam_conc_pontos",
    ]

    renamed = base_f[cols_show].rename(
        columns={
            "pessoa_entregadora": "Entregador",
            "categoria": "Categoria atual",
            "tag_proximidade": "Tag",
            "premium_hits_desc": "Critérios Premium batidos",
            "supply_hours": "SH no mês (h)",
            "sh_proj": "SH projetado (h)",
            "media_sh_dia_ativo": "Média SH/dia ativo",
            "dias_ativos": "Dias ativos no mês",
            "aceitacao_%": "Aceitação %",
            "conclusao_%": "Conclusão %",
            "faltam_sh_para_premium": "Faltam SH",
            "faltam_acc_pontos": "Faltam p.p. aceitação",
            "faltam_conc_pontos": "Faltam p.p. conclusão",
        }
    )

    styled = (
        renamed.style.format(
            {
                "SH no mês (h)": _fmt_1,
                "SH projetado (h)": _fmt_1,
                "Média SH/dia ativo": _fmt_1,
                "Aceitação %": _fmt_1,
                "Conclusão %": _fmt_1,
                "Faltam SH": _fmt_1_blank_zero,
                "Faltam p.p. aceitação": _fmt_1_blank_zero,
                "Faltam p.p. conclusão": _fmt_1_blank_zero,
            }
        )
        .apply(highlight_row, axis=1)
    )

    st.dataframe(styled, use_container_width=True)

    # ---------- Download ----------
    csv = renamed.to_csv(index=False, decimal=",").encode("utf-8")
    st.download_button(
        "⬇️ Baixar CSV (quase Premium)",
        data=csv,
        file_name=f"quase_premium_{ano_sel}_{mes_sel:02d}.csv",
        mime="text/csv",
    )

    # ---------- Explicação ----------
    with st.expander("ℹ️ Entenda os cálculos"):
        st.markdown(
            """
            **Critérios de Premium (os mesmos da tela de Categorias):**
            - SH (Supply Hours) ≥ **120h** no mês  
            - Aceitação ≥ **65%**  
            - Conclusão ≥ **95%**

            **Projeção de SH:**  
            - Calculada como `média de SH por dia ativo × total de dias do mês`.
            - Mostra o **potencial** se o entregador mantiver o mesmo ritmo de horas/dia ativo.

            **Destaque em vermelho:**  
            - Mostra quem tem **SH alto (≥ 100h)** mas **aceitação baixa (< 65%)**.  
              São os entregadores que trabalham muito, mas rejeitam demais as corridas.

            **Tags de proximidade:**  
            - 🏆 Já Premium → já está Premium  
            - 🚀 Quase Premium → cumpre 2 de 3 critérios  
            - 👀 Bom potencial → cumpre 1 de 3  
            - 🧱 Longe ainda → ainda não bateu nenhum critério
            """
        )
