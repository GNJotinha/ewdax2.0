import streamlit as st
from auth import autenticar, USUARIOS
from data_loader import carregar_dados
from relatorios import (
    gerar_dados, gerar_simplicado, gerar_alertas_de_faltas, get_entregadores
)
import pandas as pd

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


# Menu lateral organizado por seções
modo = st.sidebar.radio("Escolha uma opção:", [
    "📊 Indicadores Gerais",
    "Ver geral",
    "Simplificada (WhatsApp)",
    "Alertas de Faltas",
    "Relatório Customizado"
])


# Para manter compatibilidade com o restante do código
if not modo:
    st.stop()

df = carregar_dados()
entregadores = get_entregadores(df)

# Permissão de admin para atualizar dados
nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
if nivel == "admin":
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

# Relatórios "Ver geral" e "Simplificada (WhatsApp)"
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
    st.subheader("🔎 Escolha os indicadores que deseja visualizar:")
    col1, col2 = st.columns(2)
    with col1:
        mostrar_ofertadas = st.checkbox("Corridas ofertadas", value=True)
        mostrar_rejeitadas = st.checkbox("Corridas rejeitadas")
    with col2:
        mostrar_aceitas = st.checkbox("Corridas aceitas")
        mostrar_completas = st.checkbox("Corridas completas")

    df['data'] = pd.to_datetime(df['data_do_periodo'])
    df['mes_ano'] = df['data'].dt.to_period('M')

    def grafico_barras(dados, coluna, titulo, label):
        dados = dados.groupby('mes_ano')[coluna].sum().reset_index()
        dados['mes_ano'] = dados['mes_ano'].dt.strftime('%b/%y')
        fig = px.bar(
            dados,
            x='mes_ano',
            y=coluna,
            text=coluna,
            title=titulo,
            labels={coluna: label},
            template="plotly_dark",
            color_discrete_sequence=['#58a6ff'],
            text_auto=True
        )
        st.plotly_chart(fig, use_container_width=True)

    if mostrar_ofertadas:
        grafico_barras(df, 'numero_de_corridas_ofertadas', '📊 Corridas ofertadas por mês', 'Corridas')

    if mostrar_aceitas:
        grafico_barras(df, 'numero_de_corridas_aceitas', '📊 Corridas aceitas por mês', 'Corridas Aceitas')

    if mostrar_rejeitadas:
        grafico_barras(df, 'numero_de_corridas_rejeitadas', '📊 Corridas rejeitadas por mês', 'Corridas Rejeitadas')

    if mostrar_completas:
        grafico_barras(df, 'numero_de_corridas_completadas', '📊 Corridas completadas por mês', 'Corridas Completadas')

    mes_atual = pd.Timestamp.today().month
    ano_atual = pd.Timestamp.today().year
    df_mes = df[(df['data'].dt.month == mes_atual) & (df['data'].dt.year == ano_atual)]

    coluna_dia = None
    titulo_dia = None
    label_dia = None

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

# Relatório de Alertas de Faltas
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

    # Filtro por subpraça
    subpracas = sorted(df["sub_praca"].dropna().unique())
    filtro_subpraca = st.multiselect("Filtrar por subpraça:", subpracas)

    # Filtro por turno (periodo)
    turnos = sorted(df["periodo"].dropna().unique())
    filtro_turno = st.multiselect("Filtrar por turno:", turnos)

    # Garante datas no formato correto
    df['data_do_periodo'] = pd.to_datetime(df['data_do_periodo'])
    df['data'] = df['data_do_periodo'].dt.date

    # Filtro de datas
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
