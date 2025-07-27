import streamlit as st
import pandas as pd
import plotly.express as px

from auth import autenticar, USUARIOS
from data_loader import carregar_dados
from relatorios import (
    gerar_dados, gerar_simplicado, gerar_alertas_de_faltas, get_entregadores
)

# Estilo
st.markdown(
    """
    <style>
        body {
            background-color: #0e1117;
            color: #c9d1d9;
        }
        .stButton>button {
            background-color: #1f6feb;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            font-weight: bold;
        }
        .stButton>button:hover {
            background-color: #388bfd;
        }
        .stSidebar {
            background-color: #161b22;
        }
        h1, h2, h3 {
            color: #58a6ff;
        }
        .stSelectbox, .stMultiSelect, .stTextInput {
            background-color: #21262d;
            color: #c9d1d9;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# Autenticação do usuário
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

st.set_page_config(page_title="Painel de Entregadores", page_icon="📋")
st.sidebar.success(f"Bem-vindo, {st.session_state.usuario}!")

# Dois menus separados para indicadores e relatórios
st.sidebar.markdown("## 📊 Indicadores")
modo_indicador = st.sidebar.selectbox(
    "Selecione um indicador:",
    ["Nenhum", "Indicadores Gerais"]
)

st.sidebar.markdown("## 📄 Relatórios")
modo_relatorio = st.sidebar.selectbox(
    "Selecione um relatório:",
    ["Nenhum", "Ver geral", "Simplificada (WhatsApp)", "Alertas de Faltas", "Relatório Customizado"]
)

# Definir modo final com base na prioridade: indicadores primeiro
if modo_indicador != "Nenhum":
    modo = modo_indicador
elif modo_relatorio != "Nenhum":
    modo = modo_relatorio
else:
    st.stop()

if not modo:
    st.stop()

# --- Carregamento e pré-processamento dos dados ---
df = carregar_dados()

# Garante que 'data' está em datetime
df["data"] = pd.to_datetime(df["data"])

# Cria 'mes_ano' para gráficos agregados
df["mes_ano"] = df["data"].dt.to_period("M").dt.to_timestamp()

entregadores = get_entregadores(df)

# Permissão admin
nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
if nivel == "admin":
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

# Relatórios
if modo in ["Ver geral", "Simplificada (WhatsApp)"]:
    with st.form("formulario"):
        entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
        nome = st.selectbox(
            "🔎 Selecione o entregador:",
            options=[None] + entregadores_lista,
            format_func=lambda x: "" if x is None else x,
            key="select_entregador"
        )

        if modo == "Simplificada (WhatsApp)":
            col1, col2 = st.columns(2)
            mes1 = col1.selectbox("1º Mês:", list(range(1, 13)), key="mes1")
            ano1 = col2.selectbox("1º Ano:", sorted(df["ano"].unique(), reverse=True), key="ano1")
            mes2 = col1.selectbox("2º Mês:", list(range(1, 13)), key="mes2")
            ano2 = col2.selectbox("2º Ano:", sorted(df["ano"].unique(), reverse=True), key="ano2")

        gerar = st.form_submit_button("🔍 Gerar relatório")

    if gerar and nome:
        with st.spinner("Gerando relatório..."):
            if modo == "Ver geral":
                texto = gerar_dados(nome, None, None, df[df["pessoa_entregadora"] == nome])
                st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=400)

            elif modo == "Simplificada (WhatsApp)":
                t1 = gerar_simplicado(nome, mes1, ano1, df)
                t2 = gerar_simplicado(nome, mes2, ano2, df)
                st.text_area("Resultado:", value="\n\n".join([t for t in [t1, t2] if t]), height=600)

# Indicadores Gerais
if modo == "📊 Indicadores Gerais":
    st.subheader("🔎 Escolha o indicador que deseja visualizar:")

    tipo_grafico = st.radio(
        "Tipo de gráfico:",
        options=[
            "Corridas ofertadas",
            "Corridas aceitas",
            "Corridas rejeitadas",
            "Corridas completadas"
        ],
        index=0,
        horizontal=True
    )

    def grafico_barras(df, coluna, titulo, label_y):
        mensal = df.groupby('mes_ano')[coluna].sum().reset_index()
        mensal['mes_ano'] = mensal['mes_ano'].dt.strftime('%b/%y')

        fig = px.bar(
            mensal,
            x='mes_ano',
            y=coluna,
            text=coluna,
            title=titulo,
            labels={coluna: label_y},
            template='plotly_dark',
            color_discrete_sequence=['#00F7FF'],
            text_auto=True
        )

        fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='white'),
            title_font=dict(size=22),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor='gray')
        )

        st.plotly_chart(fig, use_container_width=True)

    coluna_map = {
        "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Corridas"),
        "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas Aceitas"),
        "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas Rejeitadas"),
        "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas Completadas")
    }

    col, titulo, label = coluna_map[tipo_grafico]
    grafico_barras(df, col, titulo, label)

    mes_atual = pd.Timestamp.today().month
    ano_atual = pd.Timestamp.today().year
    df_mes = df[(df['data'].dt.month == mes_atual) & (df['data'].dt.year == ano_atual)]

    por_dia = df_mes.groupby(df_mes['data'].dt.day)[col].sum().reset_index()
    por_dia.rename(columns={'data': 'dia'}, inplace=True)

    fig_dia = px.line(
        por_dia,
        x='dia',
        y=col,
        markers=True,
        title=f"{tipo_grafico} por dia (mês atual)",
        labels={'dia': 'Dia', col: label},
        template='plotly_dark',
        color_discrete_sequence=['#f778ba']
    )
    fig_dia.update_traces(line_shape='spline')

    total_mes = int(por_dia[col].sum())
    st.metric(f"🚗 {label} no mês", total_mes)
    st.plotly_chart(fig_dia, use_container_width=True)# Gráfico diário
    mes_atual = pd.Timestamp.today().month
    ano_atual = pd.Timestamp.today().year
    df_mes = df[(df['data'].dt.month == mes_atual) & (df['data'].dt.year == ano_atual)]

    coluna_dia, titulo_dia, label_dia = None, None, None
    if mostrar_ofertadas:
        coluna_dia = 'numero_de_corridas_ofertadas'
        titulo_dia = '📈 Corridas ofertadas por dia (mês atual)'
        label_dia = 'Corridas Ofertadas'
    elif mostrar_aceitas:
        coluna_dia = 'numero_de_corridas_aceitas'
        titulo_dia = '📈 Corridas aceitas por dia (mês atual)'
        label_dia = 'Corridas Aceitas'
    elif mostrar_rejeitadas:
        coluna_dia = 'numero_de_corridas_rejeitadas'
        titulo_dia = '📈 Corridas rejeitadas por dia (mês atual)'
        label_dia = 'Corridas Rejeitadas'
    elif mostrar_completas:
        coluna_dia = 'numero_de_corridas_completadas'
        titulo_dia = '📈 Corridas completadas por dia (mês atual)'
        label_dia = 'Corridas Completadas'

    if coluna_dia:
        por_dia = df_mes.groupby(df_mes['data'].dt.day)[coluna_dia].sum().reset_index()
        por_dia.rename(columns={'data': 'dia'}, inplace=True)

        fig_dia = px.line(
            por_dia,
            x='dia',
            y=coluna_dia,
            markers=True,
            title=titulo_dia,
            labels={'dia': 'Dia', coluna_dia: label_dia},
            template='plotly_dark',
            color_discrete_sequence=['#f778ba']
        )
        fig_dia.update_traces(line_shape='spline')

        total_mes = int(por_dia[coluna_dia].sum())
        st.metric(f"🚗 {label_dia} no mês", total_mes)
        st.plotly_chart(fig_dia, use_container_width=True)

# Alertas de faltas
if modo == "Alertas de Faltas":
    mensagens = gerar_alertas_de_faltas(df)
    if mensagens:
        st.text_area("Resultado:", value="\n".join(mensagens), height=400)
    else:
        st.success("✅ Nenhum entregador ativo com faltas consecutivas.")

# Relatório Customizado
if modo == "Relatório Customizado":
    st.header("Relatório Customizado do Entregador")

    entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
    entregador = st.selectbox(
        "🔎 Selecione o entregador:",
        options=[None] + entregadores_lista,
        format_func=lambda x: "" if x is None else x,
        key="select_custom"
    )

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
        if isinstance(periodo, (list, tuple)):
            if len(periodo) == 2:
                dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
            elif len(periodo) == 1:
                dias_escolhidos = [periodo[0]]
        elif isinstance(periodo, pd.Timestamp):
            dias_escolhidos = [periodo]
    else:
        dias_opcoes = sorted(df["data"].unique())
        dias_escolhidos = st.multiselect(
            "Selecione os dias desejados:",
            dias_opcoes,
            format_func=lambda x: x.strftime("%d/%m/%Y")
        )
        st.caption("Dica: Para escolher vários dias, segure Ctrl (ou Command no Mac) ao clicar.")

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
