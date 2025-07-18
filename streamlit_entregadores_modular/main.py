import streamlit as st
from auth import autenticar, USUARIOS
from data_loader import carregar_dados
from relatorios import (
    gerar_dados, gerar_simplicado, gerar_alertas_de_faltas, get_entregadores,
    gerar_por_praca_data_turno
)
from datetime import date

st.set_page_config(page_title="Painel de Entregadores", page_icon="📋")

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
modo = st.sidebar.radio("Escolha uma opção:", [
    "Ver 1 mês", "Ver 2 meses", "Ver geral",
    "Simplificada (WhatsApp)", "Alertas de Faltas",
    "Relatório por Praça/Data/Turno"
])

df = carregar_dados()
entregadores = get_entregadores(df)

nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
if nivel == "admin":
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

if modo in ["Ver 1 mês", "Ver 2 meses", "Ver geral", "Simplificada (WhatsApp)"]:
    with st.form("formulario"):
        nome = st.selectbox("Nome do entregador:", entregadores)

        if modo == "Ver 1 mês":
            col1, col2 = st.columns(2)
            mes = col1.selectbox("Mês:", list(range(1, 13)))
            ano = col2.selectbox("Ano:", sorted(df["ano"].unique(), reverse=True))

        elif modo in ["Ver 2 meses", "Simplificada (WhatsApp)"]:
            col1, col2 = st.columns(2)
            mes1 = col1.selectbox("1º Mês:", list(range(1, 13)), key="mes1")
            ano1 = col2.selectbox("1º Ano:", sorted(df["ano"].unique(), reverse=True), key="ano1")
            mes2 = col1.selectbox("2º Mês:", list(range(1, 13)), key="mes2")
            ano2 = col2.selectbox("2º Ano:", sorted(df["ano"].unique(), reverse=True), key="ano2")

        gerar = st.form_submit_button("🔍 Gerar relatório")

    if gerar and nome:
        with st.spinner("Gerando relatório..."):
            if modo == "Ver 1 mês":
                texto = gerar_dados(nome, mes, ano, df)
                st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=350)

            elif modo == "Ver 2 meses":
                t1 = gerar_dados(nome, mes1, ano1, df)
                t2 = gerar_dados(nome, mes2, ano2, df)
                st.text_area("Resultado:", value=(t1 or "") + "\n\n" + (t2 or ""), height=700)

            elif modo == "Ver geral":
                texto = gerar_dados(nome, None, None, df[df["pessoa_entregadora"] == nome])
                st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=400)

            elif modo == "Simplificada (WhatsApp)":
                t1 = gerar_simplicado(nome, mes1, ano1, df)
                t2 = gerar_simplicado(nome, mes2, ano2, df)
                st.text_area("Resultado:", value="\n\n".join([t for t in [t1, t2] if t]), height=600)

elif modo == "Alertas de Faltas":
    mensagens = gerar_alertas_de_faltas(df)
    if mensagens:
        st.text_area("Resultado:", value="\n".join(mensagens), height=400)
    else:
        st.success("✅ Nenhum entregador ativo com faltas consecutivas.")

elif modo == "Relatório por Praça/Data/Turno":
    st.subheader("📍 Relatório por Praça / Data / Turno")

    pracas = sorted(df["praca"].dropna().unique().tolist()) if "praca" in df.columns else []
    entregadores = get_entregadores(df)

    col1, col2 = st.columns(2)
    nome = col1.selectbox("Entregador:", entregadores)
    praca = col2.selectbox("Praça:", [""] + pracas if pracas else [""])

    filtro = st.radio("Filtro de período:", ["Intervalo de datas", "Últimos 1 dia", "Últimos 3 dias", "Últimos 7 dias"])
    data_inicio = data_fim = dias = None

    if filtro == "Intervalo de datas":
        col3, col4 = st.columns(2)
        data_inicio = col3.date_input("Data início")
        data_fim = col4.date_input("Data fim")
    else:
        dias = int(filtro.split()[1])

    turno = st.selectbox("Turno:", ["", "manhã", "tarde", "noite"] if "turno" in df.columns else [""])

    gerar = st.button("🔍 Gerar relatório")

    if gerar:
        texto = gerar_por_praca_data_turno(
            df,
            nome=nome or None,
            praca=praca or None,
            data_inicio=data_inicio,
            data_fim=data_fim,
            dias=dias,
            turno=turno or None
        )
        st.text_area("Resultado:", value=texto, height=600)
