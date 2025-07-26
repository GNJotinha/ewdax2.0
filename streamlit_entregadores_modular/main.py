
import streamlit as st
from auth import autenticar, USUARIOS
from data_loader import carregar_dados
from relatorios import (
    gerar_dados, gerar_simplicado, gerar_alertas_de_faltas, get_entregadores
)
from promocoes_loader import carregar_promocoes, estruturar_promocoes
from utils import calcular_tempo_online
import pandas as pd

# Autenticação
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
])

df = carregar_dados()
entregadores = get_entregadores(df)

nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
if nivel == "admin":
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

if modo == "📈 Apurador de Promoções":
    st.title("📈 Apurador de Promoções")

    df_promocoes, df_fases, df_criterios, df_faixas = carregar_promocoes()
    PROMOCOES = estruturar_promocoes(df_promocoes, df_fases, df_criterios, df_faixas)

    for promo in PROMOCOES:
        st.subheader(promo["nome"])
        tipo = promo["tipo"]

        if tipo == "fases":
            resultados = {}
            for fase in promo["fases"]:
                df_fase = df[(df["data"] >= fase["inicio"]) & (df["data"] <= fase["fim"])]
                for nome in df_fase["pessoa_entregadora"].dropna().unique():
                    total = df_fase[df_fase["pessoa_entregadora"] == nome]["numero_de_corridas_completadas"].sum()
                    if nome not in resultados:
                        resultados[nome] = []
                    resultados[nome].append((fase["nome"], total >= fase["min_rotas"], int(total)))
            for nome, fases in resultados.items():
                texto = f"🔹 {nome}"
                for fase, ok, total in fases:
                    status = "✔" if ok else "❌"
                    texto += f" | {fase}: {total} rotas {status}"
                st.text(texto)

        elif tipo == "por_hora":
            turno = promo["turno"]
            data = promo["data_inicio"]
            req = promo["criterios"]
            df_turno = df[(df["data"] == data) & (df["periodo"] == turno)]
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
                status = "✅" if elegivel else "❌"
                st.text(f"{status} {nome} – Online: {tempo_pct*100:.1f}%, Aceites: {tx_aceitacao*100:.1f}%, Conclusão: {tx_conclusao*100:.1f}%")

        elif tipo == "ranking":
            inicio, fim = promo["data_inicio"], promo["data_fim"]
            qtd = int(promo["ranking_top"])
            df_rk = df[(df["data"] >= inicio) & (df["data"] <= fim)]
            ranking = (
                df_rk.groupby("pessoa_entregadora")["numero_de_corridas_completadas"]
                .sum()
                .sort_values(ascending=False)
                .head(qtd)
                .reset_index()
            )
            st.dataframe(ranking, use_container_width=True)

        elif tipo == "faixa_rotas":
            inicio, fim = promo["data_inicio"], promo["data_fim"]
            df_per = df[(df["data"] >= inicio) & (df["data"] <= fim)]
            for nome in df_per["pessoa_entregadora"].dropna().unique():
                total = df_per[df_per["pessoa_entregadora"] == nome]["numero_de_corridas_completadas"].sum()
                premio = 0
                for faixa in promo["faixas"]:
                    if faixa["faixa_min"] <= total <= faixa["faixa_max"]:
                        premio = faixa["valor_premio"]
                        break
                if premio:
                    st.success(f"🏅 {nome} – {int(total)} rotas → R${premio}")
                else:
                    st.warning(f"{nome} – {int(total)} rotas → Não atingiu nenhuma faixa.")
