import streamlit as st
import pandas as pd
import calendar

from relatorios import classificar_entregadores
from shared import hms_from_hours


def _calc_quantis_por_categoria(df_cat: pd.DataFrame) -> dict:
    """
    Calcula, por categoria, quantis de SH e aceitação.
    Retorna dict: { "Premium": {"sh_lo":..., "sh_hi":..., "acc_lo":..., "acc_hi":...}, ... }
    """
    quantis = {}
    if df_cat.empty:
        return quantis

    for cat in sorted(df_cat["categoria"].dropna().astype(str).unique()):
        sub = df_cat[df_cat["categoria"].astype(str) == cat]
        if sub.empty:
            continue
        quantis[cat] = {
            "sh_lo": float(sub["supply_hours"].quantile(0.25)),
            "sh_hi": float(sub["supply_hours"].quantile(0.75)),
            "acc_lo": float(sub["aceitacao_%"].quantile(0.25)),
            "acc_hi": float(sub["aceitacao_%"].quantile(0.75)),
        }
    return quantis


def _add_projecao_sh(df_cat: pd.DataFrame, mes: int, ano: int, df_original: pd.DataFrame) -> pd.DataFrame:
    """
    Projeta SH do mês atual (se o mês/ano forem o mês corrente dos dados).
    Projeção simples: SH_atual / dias_passados * dias_totais.
    """
    if df_cat.empty:
        return df_cat

    # Última data registrada nesse mês
    base_mes = df_original[(df_original["mes"] == mes) & (df_original["ano"] == ano)].copy()
    if base_mes.empty:
        return df_cat

    try:
        ult_data = pd.to_datetime(base_mes["data"]).max()
    except Exception:
        return df_cat

    if pd.isna(ult_data):
        return df_cat

    dia_atual = int(ult_data.day)
    dias_totais = calendar.monthrange(ano, mes)[1]
    if dia_atual <= 0:
        return df_cat

    df_cat = df_cat.copy()
    df_cat["sh_atual"] = df_cat["supply_hours"].astype(float)
    df_cat["sh_projetado"] = (df_cat["sh_atual"] / dia_atual * dias_totais).round(1)

    # metas de SH por categoria (base nas regras do classificar_entregadores)
    metas_sh = {
        "Premium": 120.0,
        "Conectado": 60.0,
        "Casual": 20.0,
        "Flutuante": 0.0,
    }
    df_cat["meta_sh_categoria"] = df_cat["categoria"].astype(str).map(metas_sh).fillna(0.0)
    df_cat["vai_bater_meta_sh"] = df_cat["sh_projetado"] >= df_cat["meta_sh_categoria"]

    return df_cat


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("⚖️ SH x Aceitação — Entregadores Desequilibrados")

    if df is None or df.empty:
        st.info("❌ Sem dados carregados.")
        return

    if "mes" not in df.columns or "ano" not in df.columns:
        st.error("Base sem colunas 'mes' e 'ano'. Verifique o carregamento dos dados.")
        return

    # ==============================
    # Seleção de mês/ano
    # ==============================
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

    # Base de categorias (já traz SH, aceitação, conclusão, etc.)
    df_cat = classificar_entregadores(df, mes_sel, ano_sel)
    if df_cat.empty:
        st.info("❌ Nenhum dado encontrado para o período selecionado.")
        return

    # ==============================
    # Controles (sliders/inputs)
    # ==============================
    st.subheader("Filtros de sensibilidade")

    col_a, col_b = st.columns(2)
    min_sh_alto = float(
        col_a.number_input(
            "Mínimo de SH para considerar 'alto SH'",
            min_value=0.0,
            value=40.0,
            step=5.0,
        )
    )
    max_sh_baixo = float(
        col_b.number_input(
            "Máximo de SH para considerar 'baixo SH'",
            min_value=0.0,
            value=20.0,
            step=5.0,
        )
    )

    col_c, col_d = st.columns(2)
    max_acc_ruim = float(
        col_c.number_input(
            "Máx. de aceitação (%) para considerar 'ruim'",
            min_value=0.0,
            max_value=100.0,
            value=60.0,
            step=1.0,
        )
    )
    min_acc_boa = float(
        col_d.number_input(
            "Mín. de aceitação (%) para considerar 'boa'",
            min_value=0.0,
            max_value=100.0,
            value=80.0,
            step=1.0,
        )
    )

    # ==============================
    # Quantis por categoria
    # ==============================
    quantis = _calc_quantis_por_categoria(df_cat)

    def _get_q(cat: str, key: str, default: float) -> float:
        c = str(cat)
        if c in quantis and key in quantis[c]:
            return quantis[c][key]
        return default

    df_cat = df_cat.copy()
    df_cat["q_sh_lo"] = df_cat["categoria"].astype(str).apply(
        lambda c: _get_q(c, "sh_lo", df_cat["supply_hours"].quantile(0.25))
    )
    df_cat["q_sh_hi"] = df_cat["categoria"].astype(str).apply(
        lambda c: _get_q(c, "sh_hi", df_cat["supply_hours"].quantile(0.75))
    )
    df_cat["q_acc_lo"] = df_cat["categoria"].astype(str).apply(
        lambda c: _get_q(c, "acc_lo", df_cat["aceitacao_%"].quantile(0.25))
    )
    df_cat["q_acc_hi"] = df_cat["categoria"].astype(str).apply(
        lambda c: _get_q(c, "acc_hi", df_cat["aceitacao_%"].quantile(0.75))
    )

    # ==============================
    # Projeção de SH (mês atual)
    # ==============================
    hoje = pd.Timestamp.today()
    if hoje.month == mes_sel and hoje.year == ano_sel:
        df_cat = _add_projecao_sh(df_cat, mes_sel, ano_sel, df)
        projecao_ativa = True
    else:
        projecao_ativa = False

    # ==============================
    # Máscaras: "desequilibrados"
    # ==============================
    # 1) Alto SH x Baixa aceitação
    mask_high_sh = (df_cat["supply_hours"] >= df_cat["q_sh_hi"]) & (
        df_cat["supply_hours"] >= min_sh_alto
    )
    mask_low_acc = (df_cat["aceitacao_%"] <= df_cat["q_acc_lo"]) & (
        df_cat["aceitacao_%"] <= max_acc_ruim
    )

    # 2) Alta aceitação x Baixo SH
    mask_high_acc = (df_cat["aceitacao_%"] >= df_cat["q_acc_hi"]) & (
        df_cat["aceitacao_%"] >= min_acc_boa
    )
    mask_low_sh = (df_cat["supply_hours"] <= df_cat["q_sh_lo"]) & (
        df_cat["supply_hours"] <= max_sh_baixo
    )

    df_alto_sh_baixa_acc = df_cat[mask_high_sh & mask_low_acc].copy()
    df_baixa_sh_alta_acc = df_cat[mask_high_acc & mask_low_sh].copy()

    # ==============================
    # Tabela 1: Alto SH, baixa aceitação
    # ==============================
    st.subheader("🚀 Muito SH, mas aceitação ruim")

    if df_alto_sh_baixa_acc.empty:
        st.info("Nenhum entregador com **SH alto e aceitação baixa** nos critérios atuais.")
    else:
        df_alto_sh_baixa_acc["SH (HH:MM:SS)"] = df_alto_sh_baixa_acc["supply_hours"].apply(hms_from_hours)

        cols_show = [
            "pessoa_entregadora",
            "categoria",
            "supply_hours",
            "SH (HH:MM:SS)",
            "aceitacao_%",
            "conclusao_%",
            "ofertadas",
            "aceitas",
            "completas",
        ]

        if projecao_ativa and "sh_projetado" in df_alto_sh_baixa_acc.columns:
            df_alto_sh_baixa_acc["SH proj. (h)"] = df_alto_sh_baixa_acc["sh_projetado"]
            df_alto_sh_baixa_acc["Meta SH cat."] = df_alto_sh_baixa_acc["meta_sh_categoria"]
            df_alto_sh_baixa_acc["Bate meta?"] = df_alto_sh_baixa_acc["vai_bater_meta_sh"].map(
                {True: "✅", False: "❌"}
            )
            cols_show += ["SH proj. (h)", "Meta SH cat.", "Bate meta?"]

        df_alto_sh_baixa_acc = df_alto_sh_baixa_acc.sort_values(
            by=["supply_hours", "aceitacao_%"], ascending=[False, True]
        )

        st.dataframe(
            df_alto_sh_baixa_acc[cols_show]
            .rename(
                columns={
                    "pessoa_entregadora": "Entregador",
                    "categoria": "Categoria",
                    "supply_hours": "SH (h)",
                    "aceitacao_%": "Aceitação (%)",
                    "conclusao_%": "Conclusão (%)",
                }
            )
            .style.format(
                {
                    "SH (h)": "{:.1f}",
                    "SH proj. (h)": "{:.1f}",
                    "Meta SH cat.": "{:.0f}",
                    "Aceitação (%)": "{:.1f}",
                    "Conclusão (%)": "{:.1f}",
                }
            ),
            use_container_width=True,
        )

    # ==============================
    # Tabela 2: Baixo SH, alta aceitação
    # ==============================
    st.subheader("💤 Pouco SH, mas aceitação boa")

    if df_baixa_sh_alta_acc.empty:
        st.info("Nenhum entregador com **SH baixo e aceitação boa** nos critérios atuais.")
    else:
        df_baixa_sh_alta_acc["SH (HH:MM:SS)"] = df_baixa_sh_alta_acc["supply_hours"].apply(hms_from_hours)

        cols_show2 = [
            "pessoa_entregadora",
            "categoria",
            "supply_hours",
            "SH (HH:MM:SS)",
            "aceitacao_%",
            "conclusao_%",
            "ofertadas",
            "aceitas",
            "completas",
        ]

        if projecao_ativa and "sh_projetado" in df_baixa_sh_alta_acc.columns:
            df_baixa_sh_alta_acc["SH proj. (h)"] = df_baixa_sh_alta_acc["sh_projetado"]
            df_baixa_sh_alta_acc["Meta SH cat."] = df_baixa_sh_alta_acc["meta_sh_categoria"]
            df_baixa_sh_alta_acc["Bate meta?"] = df_baixa_sh_alta_acc["vai_bater_meta_sh"].map(
                {True: "✅", False: "❌"}
            )
            cols_show2 += ["SH proj. (h)", "Meta SH cat.", "Bate meta?"]

        df_baixa_sh_alta_acc = df_baixa_sh_alta_acc.sort_values(
            by=["aceitacao_%", "supply_hours"], ascending=[False, True]
        )

        st.dataframe(
            df_baixa_sh_alta_acc[cols_show2]
            .rename(
                columns={
                    "pessoa_entregadora": "Entregador",
                    "categoria": "Categoria",
                    "supply_hours": "SH (h)",
                    "aceitacao_%": "Aceitação (%)",
                    "conclusao_%": "Conclusão (%)",
                }
            )
            .style.format(
                {
                    "SH (h)": "{:.1f}",
                    "SH proj. (h)": "{:.1f}",
                    "Meta SH cat.": "{:.0f}",
                    "Aceitação (%)": "{:.1f}",
                    "Conclusão (%)": "{:.1f}",
                }
            ),
            use_container_width=True,
        )

    # ==============================
    # Download (CSV)
    # ==============================
    col_dl1, col_dl2 = st.columns(2)

    if not df_alto_sh_baixa_acc.empty:
        with col_dl1:
            st.download_button(
                "⬇️ Baixar CSV — SH alto / Aceitação baixa",
                data=df_alto_sh_baixa_acc.to_csv(index=False, decimal=",").encode("utf-8"),
                file_name=f"sh_alto_acc_baixa_{ano_sel}_{mes_sel:02d}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    if not df_baixa_sh_alta_acc.empty:
        with col_dl2:
            st.download_button(
                "⬇️ Baixar CSV — SH baixo / Aceitação alta",
                data=df_baixa_sh_alta_acc.to_csv(index=False, decimal=",").encode("utf-8"),
                file_name=f"sh_baixo_acc_alta_{ano_sel}_{mes_sel:02d}.csv",
                mime="text/csv",
                use_container_width=True,
            )
