import streamlit as st
import pandas as pd

from relatorios import gerar_dados, gerar_simplicado
from shared import sub_options_with_livre, apply_sub_filter


# =========================================================
# Helpers
# =========================================================
def _ensure_date_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    O sistema tem bases com 'data' OU 'data_do_periodo'.
    O customizado original converte 'data_do_periodo' -> date em 'data'.
    Aqui padronizamos SEM destruir o df original.
    """
    d = df.copy()
    if "data" in d.columns:
        d["data"] = pd.to_datetime(d["data"], errors="coerce")
        d["data_dia"] = d["data"].dt.date
        return d

    if "data_do_periodo" in d.columns:
        d["data_do_periodo"] = pd.to_datetime(d["data_do_periodo"], errors="coerce")
        d["data"] = d["data_do_periodo"]
        d["data_dia"] = d["data_do_periodo"].dt.date
        return d

    # fallback: cria colunas vazias (evita crash)
    d["data"] = pd.NaT
    d["data_dia"] = pd.NaT
    return d


def _pretty_header(title: str, subtitle: str | None = None, emoji: str = "📌"):
    st.markdown(
        f"""
        <div style="
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 16px 18px;
            background: rgba(255,255,255,0.03);
            margin-bottom: 10px;
        ">
            <div style="font-size: 22px; font-weight: 800;">{emoji} {title}</div>
            {f'<div style="opacity: 0.8; margin-top: 4px;">{subtitle}</div>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _segmented_radio(label: str, options: list[str], key: str):
    # Streamlit não tem segmented control nativo; radio horizontal fica bem próximo.
    return st.radio(label, options, horizontal=True, key=key)


# =========================================================
# View
# =========================================================
def render(df: pd.DataFrame, _USUARIOS: dict):
    _pretty_header(
        "Desempenho do Entregador (unificado)",
        "Aqui você tem o Ver geral + Simplificada (WhatsApp) + Customizado, tudo na mesma tela — sem perder as características.",
        "🧠",
    )

    if df is None or df.empty:
        st.info("❌ Sem dados carregados.")
        return

    if "pessoa_entregadora" not in df.columns:
        st.error("Coluna 'pessoa_entregadora' não encontrada na base.")
        return

    base = _ensure_date_cols(df)

    # =========================================================
    # Seletor global do entregador
    # =========================================================
    with st.container():
        c1, c2 = st.columns([3, 2])
        with c1:
            nomes = sorted(base["pessoa_entregadora"].dropna().unique().tolist())
            nome = st.selectbox(
                "🔎 Selecione o entregador",
                [None] + nomes,
                format_func=lambda x: "" if x is None else x,
                key="unif_nome",
            )
        with c2:
            # info rápida do recorte
            if pd.notna(base["data"].max()):
                dmin = pd.to_datetime(base["data"].min()).date()
                dmax = pd.to_datetime(base["data"].max()).date()
                st.caption("📅 Período da base")
                st.write(f"**{dmin.strftime('%d/%m/%Y')} → {dmax.strftime('%d/%m/%Y')}**")
            else:
                st.caption("📅 Período da base: —")

    st.divider()

    if not nome:
        st.caption("Selecione um entregador pra liberar os modos.")
        return

    df_e = base[base["pessoa_entregadora"] == nome].copy()
    if df_e.empty:
        st.info("❌ Nenhum dado para esse entregador.")
        return

    # =========================================================
    # Modo (um único lugar, mas preserva 100% o comportamento)
    # =========================================================
    modo = _segmented_radio(
        "Modo",
        ["👀 Ver geral", "📲 Simplificada (WhatsApp)", "🛠️ Customizado"],
        key="unif_modo",
    )

    # =========================================================
    # 👀 Ver geral (mesmo comportamento do ver_geral.py)
    # =========================================================
    if modo == "👀 Ver geral":
        _pretty_header("Ver geral", "Gera o relatório completo do entregador, sem filtros extras.", "👀")

        col_a, col_b = st.columns([1, 2])
        with col_a:
            gerar = st.button("Gerar relatório", use_container_width=True, key="btn_vergeral")
        with col_b:
            st.caption("Saída idêntica ao modo antigo: `gerar_dados(nome, None, None, df_do_entregador)`.")

        if gerar:
            texto = gerar_dados(nome, None, None, df_e)
            st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=420)

    # =========================================================
    # 📲 Simplificada (WhatsApp) (característica: comparar 2 meses)
    # =========================================================
    elif modo == "📲 Simplificada (WhatsApp)":
        _pretty_header("Simplificada (WhatsApp)", "Comparar 2 meses/anos e cuspir o texto pronto.", "📲")

        if "mes" not in base.columns or "ano" not in base.columns:
            st.error("Base sem colunas 'mes' e 'ano'. Não dá pra rodar o simplificado.")
            return

        anos_disp = sorted([int(x) for x in base["ano"].dropna().unique().tolist()], reverse=True)
        if not anos_disp:
            st.error("Sem anos válidos na base.")
            return

        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            mes1 = c1.selectbox("1º Mês", list(range(1, 13)), index=0, key="unif_simp_mes1")
            ano1 = c2.selectbox("1º Ano", anos_disp, index=0, key="unif_simp_ano1")
            mes2 = c3.selectbox("2º Mês", list(range(1, 13)), index=1 if 1 < 12 else 0, key="unif_simp_mes2")
            ano2 = c4.selectbox("2º Ano", anos_disp, index=0, key="unif_simp_ano2")

        col_a, col_b = st.columns([1, 2])
        with col_a:
            gerar = st.button("Gerar simplificada", use_container_width=True, key="btn_simp")
        with col_b:
            st.caption("Mesma lógica do main antigo: gera 2 blocos e junta com linha em branco.")

        if gerar:
            t1 = gerar_simplicado(nome, mes1, ano1, base)
            t2 = gerar_simplicado(nome, mes2, ano2, base)
            texto = "\n\n".join([t for t in [t1, t2] if t]) or "❌ Nenhum dado encontrado"
            st.text_area("Resultado:", value=texto, height=600)

            st.download_button(
                "⬇️ Baixar .txt",
                data=texto.encode("utf-8"),
                file_name=f"simplificada_{str(nome).strip().replace(' ', '_')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

    # =========================================================
    # 🛠️ Customizado (mesma característica do relatorio_custom.py)
    # =========================================================
    else:
        _pretty_header("Customizado", "Filtra por subpraça, turno e datas (intervalo ou dias específicos).", "🛠️")

        # subpraças (usa o helper do projeto, como no relatorio_custom.py)
        subpracas = sub_options_with_livre(base, praca_scope="SAO PAULO")
        filtro_subpraca = st.multiselect("Filtrar por subpraça:", subpracas, key="unif_cust_sub")

        # turnos (relatorio_custom usa 'periodo', vamos respeitar)
        if "periodo" in base.columns:
            turnos = sorted(base["periodo"].dropna().unique().tolist())
            filtro_turno = st.multiselect("Filtrar por turno:", turnos, key="unif_cust_turno")
        else:
            filtro_turno = []

        tipo_periodo = st.radio(
            "Como deseja escolher as datas?",
            ("Período contínuo", "Dias específicos"),
            horizontal=True,
            key="unif_cust_tipo",
        )

        dias_escolhidos: list = []
        datas_validas = sorted([d for d in df_e["data_dia"].dropna().unique().tolist()])
        if not datas_validas:
            st.info("Sem datas válidas para esse entregador.")
            return

        if tipo_periodo == "Período contínuo":
            data_min = min(datas_validas)
            data_max = max(datas_validas)
            periodo = st.date_input(
                "Selecione o intervalo de datas:",
                [data_min, data_max],
                format="DD/MM/YYYY",
                key="unif_cust_periodo",
            )
            if len(periodo) == 2:
                dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
            elif len(periodo) == 1:
                dias_escolhidos = [periodo[0]]
        else:
            dias_opcoes = datas_validas
            dias_escolhidos = st.multiselect(
                "Selecione os dias desejados:",
                dias_opcoes,
                format_func=lambda x: x.strftime("%d/%m/%Y"),
                key="unif_cust_dias",
            )

        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            gerar = st.button("Gerar relatório customizado", use_container_width=True, key="btn_cust")
        with col_b:
            limpar = st.button("Limpar filtros", use_container_width=True, key="btn_cust_clear")
        with col_c:
            st.caption("Dica: se ficar vazio, normalmente é filtro de subpraça/turno pegando nada.")

        if limpar:
            # reset leve (não dá pra limpar widgets direto, mas dá pra rerun limpando chaves)
            for k in [
                "unif_cust_sub",
                "unif_cust_turno",
                "unif_cust_tipo",
                "unif_cust_periodo",
                "unif_cust_dias",
            ]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

        if gerar:
            df_filt = df_e.copy()
            df_filt = apply_sub_filter(df_filt, filtro_subpraca, praca_scope="SAO PAULO")
            if filtro_turno:
                df_filt = df_filt[df_filt["periodo"].isin(filtro_turno)]
            if dias_escolhidos:
                df_filt = df_filt[df_filt["data_dia"].isin(dias_escolhidos)]

            texto = gerar_dados(nome, None, None, df_filt)
            st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=420)

            st.download_button(
                "⬇️ Baixar .txt",
                data=(texto or "").encode("utf-8"),
                file_name=f"custom_{str(nome).strip().replace(' ', '_')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
