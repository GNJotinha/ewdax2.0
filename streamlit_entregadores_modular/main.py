import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

from relatorios import (
    gerar_dados,
    gerar_simplificado,
    gerar_alertas_de_faltas,
    get_entregadores,
    classificar_entregadores,
    utr_por_entregador_turno,
    utr_pivot_por_entregador,
)
from auth import autenticar, USUARIOS
from data_loader import carregar_dados

st.set_page_config(page_title="Indicadores", page_icon="📊", layout="wide")

# =====================
# Login
# =====================
with st.sidebar:
    st.markdown("### Login")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    ok = autenticar(usuario, senha)
    if not ok:
        st.stop()

    st.success(f"Bem-vindo, {usuario}!")

    # Fonte de dados
    st.markdown("---")
    st.markdown("### Fonte de dados")
    fonte = st.radio("Selecionar", ["Local", "Drive"], index=0, horizontal=True)
    caminho_local = st.text_input("Arquivo local", value="Calendarios.xlsx")
    aba = st.text_input("Aba da planilha", value="Base 2025")

# =====================
# Carregar dados
# =====================
with st.spinner("Carregando dados..."):
    df = carregar_dados(fonte=fonte, caminho_local=caminho_local, aba=aba)

st.markdown("## 📊 Indicadores Gerais")
col_a, col_b = st.columns(2)

# Gráfico: corridas por mês (ofertadas)
if "mes" in df.columns and "ano" in df.columns and "corridas_ofertadas" in df.columns:
    serie = (
        df.groupby(["ano","mes"], as_index=False)["corridas_ofertadas"].sum()
        .sort_values(["ano","mes"])
    )
    fig1 = px.bar(serie, x=serie.apply(lambda r: f"{int(r['mes']):02d}/{int(r['ano'])}", axis=1), y="corridas_ofertadas", title="Corridas ofertadas por mês")
    col_a.plotly_chart(fig1, use_container_width=True)

# Gráfico: dia do mês atual
if "data" in df.columns and "corridas_ofertadas" in df.columns:
    atual = pd.to_datetime(df["data"]).max()
    filtro = (pd.to_datetime(df["data"]).dt.to_period('M') == atual.to_period('M'))
    serie_dia = df.loc[filtro].groupby("data", as_index=False)["corridas_ofertadas"].sum()
    fig2 = px.line(serie_dia, x="data", y="corridas_ofertadas", title=f"Ofertadas no mês atual ({atual:%m/%Y})")
    col_b.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# =====================
# Ver geral
# =====================
st.markdown("### Ver geral")
col1, col2, col3, col4 = st.columns(4)
mes = col1.number_input("Mês", min_value=1, max_value=12, value=int(datetime.now().month))
ano = col2.number_input("Ano", min_value=2000, max_value=2100, value=int(datetime.now().year))
nome = col3.selectbox("Entregador", get_entregadores(df))
turno = col4.selectbox("Turno", sorted(df["periodo"].dropna().unique()) if "periodo" in df.columns else [""])

info = gerar_dados(df, nome=nome or None, mes=mes, ano=ano, turno=turno or None)
if info:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Dias esperados", info["dias_esperados"])
    m2.metric("Presenças", info["presencas"])
    m3.metric("Faltas", info["faltas"])
    m4.metric("Tempo online (%)", info["tempo_pct"])

    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Ofertadas", info["ofertadas"])
    n2.metric("Aceitas", info["aceitas"])
    n3.metric("Rejeitadas", info["rejeitadas"])
    n4.metric("Completas", info["completas"])

    k1, k2, k3 = st.columns(3)
    k1.metric("% Aceitação", info["tx_aceitas"])
    k2.metric("% Rejeição", info["tx_rejeitadas"])
    k3.metric("% Conclusão", info["tx_completas"])
else:
    st.info("Sem dados para os filtros escolhidos.")

# =====================
# Simplificada (WhatsApp)
# =====================
st.markdown("---")
st.markdown("### Simplificada (WhatsApp)")
col_ = st.columns(4)
mes1 = col_[0].number_input("Mês A", 1, 12, value=int(datetime.now().month))
ano1 = col_[1].number_input("Ano A", 2000, 2100, value=int(datetime.now().year))
mes2 = col_[2].number_input("Mês B", 1, 12, value=max(1, int(datetime.now().month)-1))
ano2 = col_[3].number_input("Ano B", 2000, 2100, value=int(datetime.now().year))

A, B = gerar_simplificado(df, nome=nome or None, mes1=mes1, ano1=ano1, mes2=mes2, ano2=ano2)
if A and B:
    st.write(f"**{A['nome']}** — {A['periodo']} vs {B['periodo']}")
    comp = pd.DataFrame([
        {"Métrica":"Ofertadas","A":A['ofertadas'],"B":B['ofertadas']},
        {"Métrica":"Aceitas","A":A['aceitas'],"B":B['aceitas']},
        {"Métrica":"Rejeitadas","A":A['rejeitadas'],"B":B['rejeitadas']},
        {"Métrica":"Completas","A":A['completas'],"B":B['completas']},
        {"Métrica":"Tempo online (%)","A":A['tempo_pct'],"B":B['tempo_pct']},
    ])
    st.dataframe(comp, use_container_width=True)

# =====================
# Alertas de Faltas
# =====================
st.markdown("---")
st.markdown("### Alertas de Faltas")
alertas = gerar_alertas_de_faltas(df)
st.dataframe(alertas, use_container_width=True)

# =====================
# Relatório Customizado
# =====================
st.markdown("---")
st.markdown("### Relatório Customizado")
colA = st.columns(4)
_nm = colA[0].selectbox("Entregador", get_entregadores(df))
_sb = colA[1].selectbox("Subpraça", sorted(df["subpraca"].dropna().unique()) if "subpraca" in df.columns else [""])
_tr = colA[2].selectbox("Turno", sorted(df["periodo"].dropna().unique()) if "periodo" in df.columns else [""])

colB = st.columns(2)
_dt1 = colB[0].date_input("Início", value=None)
_dt2 = colB[1].date_input("Fim", value=None)

info2 = gerar_dados(
    df,
    nome=_nm or None,
    subpraca=_sb or None,
    turno=_tr or None,
    data_ini=_dt1 if _dt1 else None,
    data_fim=_dt2 if _dt2 else None,
)

if info2:
    st.json({k:v for k,v in info2.items() if k != "dados"})

# =====================
# Categorias de Entregadores
# =====================
st.markdown("---")
st.markdown("### Categorias de Entregadores")
cls = classificar_entregadores(df)
st.dataframe(cls, use_container_width=True)

# =====================
# UTR
# =====================
st.markdown("---")
st.markdown("### UTR")
base = utr_por_entregador_turno(df)
piv = utr_pivot_por_entregador(df)

st.markdown("#### Por turno")
st.dataframe(base, use_container_width=True)

st.markdown("#### Pivot por entregador × turno")
st.dataframe(piv, use_container_width=True)
