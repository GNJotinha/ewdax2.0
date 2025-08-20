import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from relatorios import (
    gerar_dados,
    gerar_simplicado,
    gerar_alertas_de_faltas,
    get_entregadores,
    classificar_entregadores,
    utr_por_entregador_turno,
    utr_pivot_por_entregador
)
from auth import autenticar, USUARIOS
from data_loader import carregar_dados

def _hms_from_hours(h):
    try:
        total_seconds = int(round(float(h) * 3600))
        horas, resto = divmod(total_seconds, 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"
    except Exception:
        return "00:00:00"



# -------------------------------------------------------------------
# Config da página (coloque antes de qualquer renderização Streamlit)
# -------------------------------------------------------------------
st.set_page_config(page_title="Painel de Entregadores", page_icon="📋")

# -------------------------------------------------------------------
# Estilo
# -------------------------------------------------------------------
st.markdown(
    """
    <style>
        body { background-color: #0e1117; color: #c9d1d9; }
        .stButton>button {
            background-color: #1f6feb;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            font-weight: bold;
        }
        .stButton>button:hover { background-color: #388bfd; }
        .stSidebar { background-color: #161b22; }
        h1, h2, h3 { color: #58a6ff; }
        .stSelectbox, .stMultiSelect, .stTextInput {
            background-color: #21262d;
            color: #c9d1d9;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# -------------------------------------------------------------------
# Autenticação
# -------------------------------------------------------------------
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""

if not st.session_state.logado:
    st.title("🔐 Login do Painel")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if autenticar(usuario, senha):
            st.session_state.logado = True
            st.session_state.usuario = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()

st.sidebar.success(f"Bem-vindo, {st.session_state.usuario}!")

# -------------------------------------------------------------------
# Menu
# -------------------------------------------------------------------
modo = st.sidebar.radio("Escolha uma opção:", [
    "📊 Indicadores Gerais",
    "Ver geral",
    "Simplificada (WhatsApp)",
    "Alertas de Faltas",
    "Relatório Customizado",
    "Categorias de Entregadores",
    "UTR"
])

if not modo:
    st.stop()

# -------------------------------------------------------------------
# Dados
# -------------------------------------------------------------------
df = carregar_dados()
df["data"] = pd.to_datetime(df["data"])
df["mes_ano"] = df["data"].dt.to_period("M").dt.to_timestamp()

entregadores = get_entregadores(df)

nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
if nivel == "admin":
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

# -------------------------------------------------------------------
# Ver geral / Simplificada
# -------------------------------------------------------------------
if modo in ["Ver geral", "Simplificada (WhatsApp)"]:
    with st.form("formulario"):
        entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
        nome = st.selectbox("🔎 Selecione o entregador:", [None] + entregadores_lista, format_func=lambda x: "" if x is None else x)

        if modo == "Simplificada (WhatsApp)":
            col1, col2 = st.columns(2)
            mes1 = col1.selectbox("1º Mês:", list(range(1, 13)))
            ano1 = col2.selectbox("1º Ano:", sorted(df["ano"].unique(), reverse=True))
            mes2 = col1.selectbox("2º Mês:", list(range(1, 13)))
            ano2 = col2.selectbox("2º Ano:", sorted(df["ano"].unique(), reverse=True))

        gerar = st.form_submit_button("🔍 Gerar relatório")

    if gerar and nome:
        with st.spinner("Gerando relatório..."):
            if modo == "Ver geral":
                texto = gerar_dados(nome, None, None, df[df["pessoa_entregadora"] == nome])
                st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=400)
            else:
                t1 = gerar_simplicado(nome, mes1, ano1, df)
                t2 = gerar_simplicado(nome, mes2, ano2, df)
                st.text_area("Resultado:", value="\n\n".join([t for t in [t1, t2] if t]), height=600)

# -------------------------------------------------------------------
# Indicadores Gerais
# -------------------------------------------------------------------
# -------------------------------------------------------------------
# Indicadores Gerais
# -------------------------------------------------------------------
if modo == "📊 Indicadores Gerais":
    st.subheader("Indicadores")

    # === Tabs: Visão Geral (existente) | Por Turno & Dias (nova) ===
    tab1, tab2 = st.tabs(["Visão Geral", "Por Turno & Dias"])

    # =========================
    # TAB 1: Visão Geral (SEU CÓDIGO ATUAL)
    # =========================
    with tab1:
        st.subheader("🔎 Escolha o indicador que deseja visualizar:")

        tipo_grafico = st.radio("Tipo de gráfico:", [
            "Corridas ofertadas",
            "Corridas aceitas",
            "Corridas rejeitadas",
            "Corridas completadas"
        ], index=0, horizontal=True)

        coluna_map = {
            "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Corridas"),
            "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas Aceitas"),
            "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas Rejeitadas"),
            "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas Completadas")
        }

        col, titulo, label = coluna_map[tipo_grafico]

        def grafico_barras(df_, coluna, titulo_, label_y):
            mensal = df_.groupby('mes_ano')[coluna].sum().reset_index()
            mensal['mes_ao'] = mensal['mes_ano'].dt.strftime('%b/%y')
            mensal["_x"] = mensal['mes_ao']

            fig = px.bar(
                mensal, x="_x", y=coluna, text=coluna, title=titulo_,
                labels={coluna: label_y, "_x": "Mês/Ano"}, template='plotly_dark',
                color_discrete_sequence=['#00F7FF'], text_auto=True
            )
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white'), title_font=dict(size=22),
                xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='gray')
            )
            st.plotly_chart(fig, use_container_width=True)

        grafico_barras(df, col, titulo, label)

        coluna_dia_map = {
            "Corridas ofertadas": ('numero_de_corridas_ofertadas', '📈 Corridas ofertadas por dia (mês atual)', 'Corridas Ofertadas'),
            "Corridas aceitas": ('numero_de_corridas_aceitas', '📈 Corridas aceitas por dia (mês atual)', 'Corridas Aceitas'),
            "Corridas rejeitadas": ('numero_de_corridas_rejeitadas', '📈 Corridas rejeitadas por dia (mês atual)', 'Corridas Rejeitadas'),
            "Corridas completadas": ('numero_de_corridas_completadas', '📈 Corridas completadas por dia (mês atual)', 'Corridas Completadas')
        }

        coluna_dia, titulo_dia, label_dia = coluna_dia_map[tipo_grafico]

        mes_atual = pd.Timestamp.today().month
        ano_atual = pd.Timestamp.today().year
        df_mes = df[(df['data'].dt.month == mes_atual) & (df['data'].dt.year == ano_atual)]

        por_dia = df_mes.groupby(df_mes['data'].dt.day)[coluna_dia].sum().reset_index()
        por_dia.rename(columns={'data': 'dia'}, inplace=True)

        fig_dia = px.line(
            por_dia, x='dia', y=coluna_dia, markers=True,
            title=titulo_dia, labels={'dia': 'Dia', coluna_dia: label_dia},
            template='plotly_dark', color_discrete_sequence=['#f778ba']
        )
        fig_dia.update_traces(line_shape='spline')

        total_mes = int(por_dia[coluna_dia].sum())
        st.metric(f"🚗 {label_dia} no mês", total_mes)
        st.plotly_chart(fig_dia, use_container_width=True)

    # =========================
    # TAB 2: Por Turno & Dias (NOVA)
    # =========================
    with tab2:
        st.subheader("Por Turno & Dias")

        # ---------- Controles ----------
        colA, colB = st.columns(2)
        with colA:
            # Combos de mês/ano com base no DF
            meses_disponiveis = sorted(df["mes"].dropna().unique())
            anos_disponiveis = sorted(df["ano"].dropna().unique(), reverse=True)
            mes_sel = st.selectbox("Mês", meses_disponiveis)
            ano_sel = st.selectbox("Ano", anos_disponiveis)

            tipo_periodo = st.radio("Como deseja escolher as datas?",
                                    ("Período contínuo", "Dias específicos"), index=0)
        with colB:
            # Turnos e subpraça
            turnos_disponiveis = sorted(df["periodo"].dropna().unique()) if "periodo" in df.columns else []
            turnos_sel = st.multiselect("Turnos", turnos_disponiveis, default=turnos_disponiveis)

            subpracas = sorted(df["sub_praca"].dropna().unique()) if "sub_praca" in df.columns else []
            sub_sel = st.multiselect("Subpraça (opcional)", subpracas)

        # Métrica + visual + ordenação
        col1, col2, col3 = st.columns(3)
        with col1:
            metrica = st.radio(
                "Métrica",
                ["Ofertadas", "Aceitas", "Rejeitadas", "Completadas"],
                horizontal=True, index=0
            )
        with col2:
            visual = st.radio("Visual", ["Agrupado", "Empilhado"], horizontal=True, index=0)
        with col3:
            ordenacao = st.selectbox("Ordenar por", ["Dia asc", "Métrica desc"], index=0)

        # Extras
        colx, coly, colz = st.columns(3)
        with colx:
            comparar_anterior = st.toggle("Comparar mês anterior", value=False)
        with coly:
            mostrar_acumulado = st.toggle("Mostrar acumulado (total/dia)", value=False)
        with colz:
            mostrar_tabela = st.toggle("Mostrar tabela/CSV", value=True)

        # ---------- Preparação de período ----------
        # Limites do mês/ano
        inicio_mes = pd.Timestamp(year=int(ano_sel), month=int(mes_sel), day=1)
        # Próximo mês - 1 dia
        if mes_sel == 12:
            fim_mes = pd.Timestamp(year=int(ano_sel)+1, month=1, day=1) - pd.Timedelta(days=1)
        else:
            fim_mes = pd.Timestamp(year=int(ano_sel), month=int(mes_sel)+1, day=1) - pd.Timedelta(days=1)

        # UI para período
        if tipo_periodo == "Período contínuo":
            periodo = st.date_input(
                "Intervalo de datas (limitado ao mês escolhido):",
                [inicio_mes.date(), min(fim_mes.date(), pd.Timestamp.today().date())],
                format="DD/MM/YYYY",
                min_value=inicio_mes.date(),
                max_value=fim_mes.date()
            )
            if isinstance(periodo, list) and len(periodo) == 2:
                datas_escolhidas = pd.date_range(periodo[0], periodo[1]).date
            else:
                st.info("Selecione início e fim do período.")
                st.stop()
        else:
            # Dias 1..N válidos no mês
            dias_validos = list(range(1, int(fim_mes.day) + 1))
            dias_mult = st.multiselect("Selecione os dias do mês:", dias_validos, default=dias_validos[:5])
            # Converte para datas completas
            datas_escolhidas = []
            invalidos = []
            for d in dias_mult:
                if 1 <= int(d) <= int(fim_mes.day):
                    datas_escolhidas.append(pd.Timestamp(year=int(ano_sel), month=int(mes_sel), day=int(d)).date())
                else:
                    invalidos.append(d)
            if invalidos:
                st.warning(f"Alguns dias não existem em {mes_sel}/{ano_sel}: {invalidos} — foram ignorados.")

        if not datas_escolhidas:
            st.info("Nenhum dia selecionado.")
            st.stop()

        # ---------- Filtragem base ----------
        base = df.copy()
        base["data"] = pd.to_datetime(base["data"])
        base = base[(base["data"].dt.year == int(ano_sel)) & (base["data"].dt.month == int(mes_sel))]
        base["dia"] = base["data"].dt.day

        # Subpraça
        if sub_sel:
            base = base[base["sub_praca"].isin(sub_sel)]

        # Turnos
        if turnos_sel:
            base = base[base["periodo"].isin(turnos_sel)]
        # Se a coluna 'periodo' não existir ou ficou vazio, segue com base atual

        # Datas escolhidas
        base = base[base["data"].dt.date.isin(list(datas_escolhidas))]

        if base.empty:
            st.info("Nenhum dado para os filtros selecionados.")
            st.stop()

        # ---------- Métrica selecionada ----------
        col_map = {
            "Ofertadas": "numero_de_corridas_ofertadas",
            "Aceitas": "numero_de_corridas_aceitas",
            "Rejeitadas": "numero_de_corridas_rejeitadas",
            "Completadas": "numero_de_corridas_completadas",
        }
        col_val = col_map[metrica]

        # ---------- Agregação por dia x turno ----------
        agg = (
            base.groupby(["dia", "periodo"], dropna=False)[col_val]
            .sum()
            .reset_index()
        )

        # Completar dias faltantes (para eixo X completo)
        todos_dias = sorted({pd.Timestamp(d).day for d in pd.to_datetime(list(datas_escolhidas))})
        if "periodo" in base.columns and len(turnos_sel) > 0:
            todos_turnos = turnos_sel
        else:
            todos_turnos = sorted(base["periodo"].dropna().unique()) if "periodo" in base.columns else []

        if len(todos_turnos) > 0:
            idx = pd.MultiIndex.from_product([todos_dias, todos_turnos], names=["dia", "periodo"])
            agg = agg.set_index(["dia", "periodo"]).reindex(idx, fill_value=0).reset_index()
        else:
            # Sem coluna periodo: agregue só por dia
            agg = (
                base.groupby(["dia"])[col_val]
                .sum()
                .reindex(todos_dias, fill_value=0)
                .rename_axis("dia")
                .reset_index()
            )
            agg["periodo"] = "(todos)"

        # Para ordenação por métrica desc (somatório do dia)
        soma_por_dia = agg.groupby("dia")[col_val].sum().reset_index().rename(columns={col_val: "__total_dia__"})
        agg = agg.merge(soma_por_dia, on="dia", how="left")

        if ordenacao == "Métrica desc":
            ordem_dias = soma_por_dia.sort_values("__total_dia__", ascending=False)["dia"].tolist()
            agg["dia"] = pd.Categorical(agg["dia"], categories=ordem_dias, ordered=True)
            agg = agg.sort_values(["dia", "periodo"]).reset_index(drop=True)
        else:
            agg = agg.sort_values(["dia", "periodo"]).reset_index(drop=True)

        # ---------- Gráfico ----------
        barmode = "group" if visual == "Agrupado" else "relative"
        fig = px.bar(
            agg, x="dia", y=col_val, color="periodo",
            title=f"{metrica} – {mes_sel:02d}/{ano_sel}",
            labels={"dia": "Dia do mês", col_val: metrica, "periodo": "Turno"},
            template="plotly_dark",
        )
        fig.update_layout(
            barmode=barmode,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='white'), title_font=dict(size=22),
            xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='gray')
        )

        # Linha de acumulado (total/dia)
        if mostrar_acumulado:
            curva = agg.groupby("dia")[col_val].sum().sort_index()
            fig.add_scatter(
                x=curva.index.tolist(),
                y=curva.cumsum().tolist(),
                name="Acumulado (total/dia)",
                mode="lines+markers"
            )

        # Linha do mês anterior (comparação)
        if comparar_anterior:
            # mês anterior
            if mes_sel == 1:
                mes_ant, ano_ant = 12, int(ano_sel) - 1
            else:
                mes_ant, ano_ant = int(mes_sel) - 1, int(ano_sel)

            ini_ant = pd.Timestamp(year=ano_ant, month=mes_ant, day=1)
            if mes_ant == 12:
                fim_ant = pd.Timestamp(year=ano_ant+1, month=1, day=1) - pd.Timedelta(days=1)
            else:
                fim_ant = pd.Timestamp(year=ano_ant, month=mes_ant+1, day=1) - pd.Timedelta(days=1)

            # mapear apenas os dias selecionados (se dia 31 não existe, ignora)
            dias_ant_validos = [d for d in todos_dias if d <= int(fim_ant.day)]
            datas_ant = [pd.Timestamp(year=ano_ant, month=mes_ant, day=int(d)).date() for d in dias_ant_validos]

            base_ant = df.copy()
            base_ant["data"] = pd.to_datetime(base_ant["data"])
            base_ant = base_ant[(base_ant["data"].dt.year == ano_ant) & (base_ant["data"].dt.month == mes_ant)]
            if sub_sel:
                base_ant = base_ant[base_ant["sub_praca"].isin(sub_sel)]
            if "periodo" in base_ant.columns and turnos_sel:
                base_ant = base_ant[base_ant["periodo"].isin(turnos_sel)]
            base_ant = base_ant[base_ant["data"].dt.date.isin(datas_ant)]
            base_ant["dia"] = base_ant["data"].dt.day

            if not base_ant.empty:
                comp = (
                    base_ant.groupby("dia")[col_val]
                    .sum()
                    .reindex(dias_ant_validos, fill_value=0)
                    .reset_index()
                )
                fig.add_scatter(
                    x=comp["dia"].tolist(),
                    y=comp[col_val].tolist(),
                    name=f"Mês anterior ({mes_ant:02d}/{ano_ant})",
                    mode="lines+markers"
                )
            else:
                st.caption("ℹ️ Sem dados no mês anterior para esse recorte.")

        st.plotly_chart(fig, use_container_width=True)

        # ---------- Cards de resumo ----------
        total_periodo = int(agg[col_val].sum())
        media_por_dia = float(agg.groupby("dia")[col_val].sum().mean())
        top_dia_row = agg.groupby("dia")[col_val].sum().sort_values(ascending=False).head(1)
        top_dia = int(top_dia_row.index[0]) if not top_dia_row.empty else None
        top_val = int(top_dia_row.iloc[0]) if not top_dia_row.empty else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("🧮 Total no período", f"{total_periodo:,}".replace(",", "."))
        c2.metric("📊 Média por dia", f"{media_por_dia:.1f}")
        c3.metric("🏆 Pico (dia)", f"{top_dia} — {top_val}")

        # ---------- Tabela e CSV ----------
        if mostrar_tabela:
            st.subheader("Tabela (dias × turnos)")
            tabela = agg.pivot_table(index="dia", columns="periodo", values=col_val, aggfunc="sum", fill_value=0)
            tabela["Total do dia"] = tabela.sum(axis=1)
            st.dataframe(tabela, use_container_width=True)

            csv = tabela.reset_index().to_csv(index=False, decimal=",").encode("utf-8")
            st.download_button(
                "⬇️ Baixar CSV",
                data=csv,
                file_name=f"por_turno_e_dias_{metrica.lower()}_{mes_sel:02d}_{ano_sel}.csv",
                mime="text/csv",
            )

# -------------------------------------------------------------------
# Alertas de Faltas
# -------------------------------------------------------------------
if modo == "Alertas de Faltas":
    st.subheader("⚠️ Entregadores com 3+ faltas consecutivas")

    hoje = datetime.now().date()
    ultimos_15_dias = hoje - timedelta(days=15)
    df["data"] = pd.to_datetime(df["data"]).dt.date

    ativos = df[df["data"] >= ultimos_15_dias]["pessoa_entregadora_normalizado"].unique()
    mensagens = []

    for nome in ativos:
        entregador = df[df["pessoa_entregadora_normalizado"] == nome]
        if entregador.empty:
            continue

        dias = pd.date_range(end=hoje - timedelta(days=1), periods=30).to_pydatetime()
        dias = [d.date() for d in dias]
        presencas = set(entregador["data"])

        sequencia = 0
        for dia in sorted(dias):
            if dia in presencas:
                sequencia = 0
            else:
                sequencia += 1

        if sequencia >= 4:
            nome_original = entregador["pessoa_entregadora"].iloc[0]
            ultima_data = entregador["data"].max().strftime('%d/%m')
            mensagens.append(
                f"• {nome_original} – {sequencia} dias consecutivos ausente (última presença: {ultima_data})"
            )

    if mensagens:
        st.text_area("Resultado:", value="\n".join(mensagens), height=400)
    else:
        st.success("✅ Nenhum entregador ativo com faltas consecutivas.")

# -------------------------------------------------------------------
# Relatório Customizado
# -------------------------------------------------------------------
if modo == "Relatório Customizado":
    st.header("Relatório Customizado do Entregador")

    entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
    entregador = st.selectbox("🔎 Selecione o entregador:", [None] + entregadores_lista, format_func=lambda x: "" if x is None else x)

    subpracas = sorted(df["sub_praca"].dropna().unique())
    filtro_subpraca = st.multiselect("Filtrar por subpraça:", subpracas)

    turnos = sorted(df["periodo"].dropna().unique())
    filtro_turno = st.multiselect("Filtrar por turno:", turnos)

    df['data_do_periodo'] = pd.to_datetime(df['data_do_periodo'])
    df['data'] = df['data_do_periodo'].dt.date

    tipo_periodo = st.radio("Como deseja escolher as datas?", ("Período contínuo", "Dias específicos"))
    dias_escolhidos = []

    if tipo_periodo == "Período contínuo":
        data_min = df["data"].min()
        data_max = df["data"].max()
        periodo = st.date_input("Selecione o intervalo de datas:", [data_min, data_max], format="DD/MM/YYYY")
        if len(periodo) == 2:
            dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
        elif len(periodo) == 1:
            dias_escolhidos = [periodo[0]]
    else:
        dias_opcoes = sorted(df["data"].unique())
        dias_escolhidos = st.multiselect(
            "Selecione os dias desejados:",
            dias_opcoes,
            format_func=lambda x: x.strftime("%d/%m/%Y")
        )

    gerar_custom = st.button("Gerar relatório customizado")

    if gerar_custom and entregador:
        df_filt = df[df["pessoa_entregadora"] == entregador]
        if filtro_subpraca:
            df_filt = df_filt[df_filt["sub_praca"].isin(filtro_subpraca)]
        if filtro_turno:
            df_filt = df_filt[df_filt["periodo"].isin(filtro_turno)]
        if dias_escolhidos:
            df_filt = df_filt[df_filt["data"].isin(dias_escolhidos)]

        texto = gerar_dados(entregador, None, None, df_filt)
        st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=400)

# -------------------------------------------------------------------
# Categorias de Entregadores
# -------------------------------------------------------------------
if modo == "Categorias de Entregadores":
    st.header("📚 Categorias de Entregadores")

    tipo_cat = st.radio("Período de análise:", ["Mês/Ano", "Todo o histórico"], horizontal=True, index=0)
    mes_sel_cat = ano_sel_cat = None
    if tipo_cat == "Mês/Ano":
        col1, col2 = st.columns(2)
        mes_sel_cat = col1.selectbox("Mês", list(range(1, 13)))
        ano_sel_cat = col2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

    df_cat = classificar_entregadores(df, mes_sel_cat, ano_sel_cat) if tipo_cat == "Mês/Ano" else classificar_entregadores(df)

    if df_cat.empty:
        st.info("Nenhum dado encontrado para o período selecionado.")
    else:
        # SH -> HH:MM:SS SEMPRE para exibição/CSV
        if "supply_hours" in df_cat.columns:
            df_cat["tempo_hms"] = df_cat["supply_hours"].apply(_hms_from_hours)

        # Resumo por categoria
        contagem = df_cat["categoria"].value_counts().reindex(["Premium","Conectado","Casual","Flutuante"]).fillna(0).astype(int)
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("🚀 Premium", int(contagem.get("Premium",0)))
        c2.metric("🎯 Conectado", int(contagem.get("Conectado",0)))
        c3.metric("👍 Casual", int(contagem.get("Casual",0)))
        c4.metric("↩ Flutuante", int(contagem.get("Flutuante",0)))

        # Tabela (usa HH:MM:SS)
        st.subheader("Tabela de classificação")
        cols_cat = ["pessoa_entregadora","categoria","tempo_hms","aceitacao_%","conclusao_%","ofertadas","aceitas","completas","criterios_atingidos"]
        st.dataframe(
            df_cat[cols_cat].style.format({"aceitacao_%":"{:.1f}","conclusao_%":"{:.1f}"}),
            use_container_width=True
        )

        # CSV com vírgula e HH:MM:SS
        csv_cat = df_cat[cols_cat].to_csv(index=False, decimal=",").encode("utf-8")
        st.download_button("⬇️ Baixar CSV", data=csv_cat, file_name="categorias_entregadores.csv", mime="text/csv")

# -------------------------------------------------------------------
# UTR por Entregador, Turno e Dia (DIÁRIO, sem pivot)
# -------------------------------------------------------------------

if modo == "UTR":
    st.header("🧭 UTR – Corridas ofertadas por hora (diário, por entregador e turno)")

    # Seleção de período
    tipo_utr = st.radio("Período:", ["Mês/Ano", "Todo o histórico"], horizontal=True, index=0)
    mes_sel_utr = ano_sel_utr = None
    if tipo_utr == "Mês/Ano":
        col1, col2 = st.columns(2)
        mes_sel_utr = col1.selectbox("Mês", list(range(1, 13)))
        ano_sel_utr = col2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

    base = (
        utr_por_entregador_turno(df, mes_sel_utr, ano_sel_utr)
        if tipo_utr == "Mês/Ano"
        else utr_por_entregador_turno(df)
    )

    if base.empty:
        st.info("Nenhum dado encontrado para o período selecionado.")
    else:
        # HH:MM:SS derivado de supply_hours
        if "supply_hours" in base.columns:
            base["tempo_hms"] = base["supply_hours"].apply(_hms_from_hours)

        # ===== Preparar dataframe para exibição =====
        cols_utr = ["data","pessoa_entregadora","periodo","tempo_hms","corridas_ofertadas","UTR"]
        df_view = base[cols_utr].copy()

        # Ajustes de formato
        try:
            df_view["data"] = pd.to_datetime(df_view["data"]).dt.strftime("%d/%m/%Y")
        except Exception:
            df_view["data"] = df_view["data"].astype(str)

        df_view["UTR"] = pd.to_numeric(df_view["UTR"], errors="coerce").round(2)
        df_view["corridas_ofertadas"] = (
            pd.to_numeric(df_view["corridas_ofertadas"], errors="coerce")
            .fillna(0)
            .astype(int)
        )

        # ===== Métricas =====
        st.metric("Média UTR (geral)", float(df_view["UTR"].mean().round(2)))
        st.metric("Mediana UTR (geral)", float(df_view["UTR"].median().round(2)))

        # ===== Tabela =====
        st.subheader("Tabela por dia, entregador e turno")
        st.dataframe(
            df_view,
            use_container_width=True,
            column_config={
                "data": st.column_config.TextColumn("Data"),
                "pessoa_entregadora": st.column_config.TextColumn("Entregador"),
                "periodo": st.column_config.TextColumn("Turno"),
                "tempo_hms": st.column_config.TextColumn("Tempo (HH:MM:SS)"),
                "corridas_ofertadas": st.column_config.NumberColumn("Corridas", format="%d"),
                "UTR": st.column_config.NumberColumn("UTR", format="%.2f"),
            },
        )

        # ===== Download CSV =====
        csv_utr = df_view.to_csv(index=False, decimal=",").encode("utf-8")
        st.download_button(
            "⬇️ Baixar CSV",
            data=csv_utr,
            file_name="utr_entregador_turno_diario.csv",
            mime="text/csv",
        )
