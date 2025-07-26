
import streamlit as st
from auth import autenticar, USUARIOS
from data_loader import carregar_dados
from relatorios import (
    gerar_dados, gerar_simplicado, gerar_alertas_de_faltas, get_entregadores
)
from promocoes_loader import carregar_promocoes, estruturar_promocoes
from utils import calcular_tempo_online
import pandas as pd
from datetime import datetime, time

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

modo = st.sidebar.radio("Escolha uma opção:", [
    "📈 Apurador de Promoções",
    "📊 Indicadores Gerais",
    "Ver geral",
    "Simplificada (WhatsApp)",
    "Alertas de Faltas",
    "Relatório Customizado"
], key="modo_radio")

df = carregar_dados()
entregadores = get_entregadores(df)

nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
if nivel == "admin":
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

if modo == "📈 Apurador de Promoções":
    st.title("📈 Apurador de Promoções")

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
df["data_date"] = df["data"].dt.date

    df_promocoes, df_fases, df_criterios, df_faixas = carregar_promocoes()
    PROMOCOES = estruturar_promocoes(df_promocoes, df_fases, df_criterios, df_faixas)

    nomes_promos = [p["nome"] for p in PROMOCOES]
    selecionada = st.selectbox("Selecione uma promoção:", nomes_promos)
    promo = next(p for p in PROMOCOES if p["nome"] == selecionada)

    st.subheader(promo["nome"])
    tipo = promo["tipo"]

    if tipo == "fases":
        resultados = []
        for nome in df["pessoa_entregadora"].dropna().unique():
            entregador_ok = True
            total_por_fase = []
            for fase in promo["fases"]:
                inicio = datetime.combine(fase["inicio"], time.min)
                fim = datetime.combine(fase["fim"], time.max)
                df_fase = df[(df["data"] >= inicio) & (df["data"] <= fim)]
                total = df_fase[df_fase["pessoa_entregadora"] == nome]["numero_de_corridas_completadas"].sum()
                total_por_fase.append((fase["nome"], total))
                if total < fase["min_rotas"]:
                    entregador_ok = False
            if entregador_ok:
                total_geral = sum(t for _, t in total_por_fase)
                resultados.append((nome, total_geral))

        df_result = pd.DataFrame(resultados, columns=["Entregador", "Total de Rotas"]).sort_values(
            by="Total de Rotas", ascending=False)
        st.dataframe(df_result, use_container_width=True)

    elif tipo == "por_hora":
        turno = promo["turno"]
        data = promo["data_inicio"]
        req = promo["criterios"]
        df_turno = df[(df["data"].dt.date == data) & (df["periodo"] == turno)]
        resultados = []
        for nome in df_turno["pessoa_entregadora"].dropna().unique():
            dados = df_turno[df_turno["pessoa_entregadora"] == nome]
            if dados.empty: continue
            tempo_pct = calcular_tempo_online(dados)
            ofertadas = dados["numero_de_corridas_ofertadas"].sum()
            aceitas = dados["numero_de_corridas_aceitas"].sum()
            completas = dados["numero_de_corridas_completadas"].sum()
            tx_aceitacao = aceitas / ofertadas if ofertadas else 0
            tx_conclusao = completas / aceitas if aceitas else 0
            elegivel = (
                tempo_pct >= req["min_pct_online"] and
                tx_aceitacao >= req["min_aceitacao"] and
                tx_conclusao >= req["min_conclusao"]
            )
            if elegivel:
                resultados.append((nome, completas))

        df_result = pd.DataFrame(resultados, columns=["Entregador", "Total de Rotas"]).sort_values(
            by="Total de Rotas", ascending=False)
        st.dataframe(df_result, use_container_width=True)

    elif tipo == "ranking":
        inicio, fim = promo["data_inicio"], promo["data_fim"]
        inicio_dt = datetime.combine(inicio, time.min)
        fim_dt = datetime.combine(fim, time.max)
        df_rk = df[(df["data_date"] >= inicio) & (df["data_date"] <= fim)]
        qtd = int(promo["ranking_top"])
        ranking = (
            df_rk.groupby("pessoa_entregadora")["numero_de_corridas_completadas"]
            .sum()
            .sort_values(ascending=False)
            .head(qtd)
            .reset_index()
        )
        st.dataframe(ranking.rename(columns={
            "pessoa_entregadora": "Entregador",
            "numero_de_corridas_completadas": "Total de Rotas"
        }), use_container_width=True)

    elif tipo == "faixa_rotas":
        inicio, fim = promo["data_inicio"], promo["data_fim"]
        inicio_dt = datetime.combine(inicio, time.min)
        fim_dt = datetime.combine(fim, time.max)
        df_per = df[(df["data"] >= inicio_dt) & (df["data"] <= fim_dt)]
        resultados = []
        for nome in df_per["pessoa_entregadora"].dropna().unique():
            total = df_per[df_per["pessoa_entregadora"] == nome]["numero_de_corridas_completadas"].sum()
            premio = 0
            for faixa in promo["faixas"]:
                if faixa["faixa_min"] <= total <= faixa["faixa_max"]:
                    premio = faixa["valor_premio"]
                    break
            if premio:
                resultados.append((nome, total, premio))

        df_result = pd.DataFrame(resultados, columns=["Entregador", "Total de Rotas", "Valor do Prêmio"]).sort_values(
            by="Total de Rotas", ascending=False)
        st.dataframe(df_result, use_container_width=True)
