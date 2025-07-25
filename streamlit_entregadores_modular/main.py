import streamlit as st
from auth import autenticar, USUARIOS
from data_loader import carregar_dados
from relatorios import (
    gerar_dados, gerar_simplicado, gerar_alertas_de_faltas, get_entregadores
)
import pandas as pd

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

# Menu lateral com novo modo
modo = st.sidebar.radio("Escolha uma opção:", [
    "📊 Indicadores Gerais",
    "Ver geral",
    "Simplificada (WhatsApp)",
    "Alertas de Faltas",
    "Relatório Customizado"
])

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

if modo == "📊 Indicadores Gerais":
    import plotly.express as px

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

    if mostrar_ofertadas:
        mensal = df.groupby('mes_ano')['numero_de_corridas_ofertadas'].sum().reset_index()
        mensal['mes_ano'] = mensal['mes_ano'].dt.strftime('%b/%y')
        fig_mensal = px.bar(
            mensal,
            x='mes_ano',
            y='numero_de_corridas_ofertadas',
            text='numero_de_corridas_ofertadas',
            title='📊 Corridas ofertadas por mês',
            labels={"numero_de_corridas_ofertadas": "Corridas"},
            text_auto=True
        )
        st.plotly_chart(fig_mensal, use_container_width=True)

    if mostrar_aceitas:
    mensal = df.groupby('mes_ano')['numero_de_corridas_aceitas'].sum().reset_index()
    mensal['mes_ano'] = mensal['mes_ano'].dt.strftime('%b/%y')
    fig_aceitas = px.bar(
        mensal,
        x='mes_ano',
        y='numero_de_corridas_aceitas',
        text='numero_de_corridas_aceitas',
        title='📊 Corridas aceitas por mês',
        labels={"numero_de_corridas_aceitas": "Corridas Aceitas"},
        text_auto=True
    )
    st.plotly_chart(fig_aceitas, use_container_width=True)

    if mostrar_rejeitadas:
    mensal = df.groupby('mes_ano')['numero_de_corridas_rejeitadas'].sum().reset_index()
    mensal['mes_ano'] = mensal['mes_ano'].dt.strftime('%b/%y')
    fig_rejeitadas = px.bar(
        mensal,
        x='mes_ano',
        y='numero_de_corridas_rejeitadas',
        text='numero_de_corridas_rejeitadas',
        title='📊 Corridas rejeitadas por mês',
        labels={"numero_de_corridas_rejeitadas": "Corridas Rejeitadas"},
        text_auto=True
    )
    st.plotly_chart(fig_rejeitadas, use_container_width=True)

    if mostrar_completas:
    mensal = df.groupby('mes_ano')['numero_de_corridas_completadas'].sum().reset_index()
    mensal['mes_ano'] = mensal['mes_ano'].dt.strftime('%b/%y')
    fig_completas = px.bar(
        mensal,
        x='mes_ano',
        y='numero_de_corridas_completadas',
        text='numero_de_corridas_completadas',
        title='📊 Corridas completadas por mês',
        labels={"numero_de_corridas_completadas": "Corridas Completadas"},
        text_auto=True
    )
    st.plotly_chart(fig_completas, use_container_width=True)

    # Gráfico diário de ofertadas
    mes_atual = pd.Timestamp.today().month
    ano_atual = pd.Timestamp.today().year
    df_mes = df[(df['data'].dt.month == mes_atual) & (df['data'].dt.year == ano_atual)]
    por_dia = df_mes.groupby(df_mes['data'].dt.day)['numero_de_corridas_ofertadas'].sum().reset_index()
    por_dia.rename(columns={'data': 'dia'}, inplace=True)

    fig_dia = px.line(
        por_dia,
        x='dia',
        y='numero_de_corridas_ofertadas',
        markers=True,
        title='📈 Corridas ofertadas por dia (mês atual)',
        labels={'dia': 'Dia', 'numero_de_corridas_ofertadas': 'Corridas'}
    )
    fig_dia.update_traces(line_shape='spline', line_color='royalblue')

    total_mes = int(por_dia['numero_de_corridas_ofertadas'].sum())
    st.metric("🚗 Corridas ofertadas no mês", total_mes)
    st.plotly_chart(fig_dia, use_container_width=True)


# Relatório de Alertas de Faltas
if modo == "Alertas de Faltas":
    mensagens = gerar_alertas_de_faltas(df)
    if mensagens:
        st.text_area("Resultado:", value="\n".join(mensagens), height=400)
    else:
        st.success("✅ Nenhum entregador ativo com faltas consecutivas.")

# --- RELATÓRIO CUSTOMIZADO --- #
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
