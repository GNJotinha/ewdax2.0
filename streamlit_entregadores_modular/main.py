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
if modo == "📊 Indicadores Gerais":
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

        # usar a coluna correta no eixo X (mes_ao para rótulo)
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

# -------------------------------------------------------------------
# UTR por Entregador, Turno e Dia — visão simples (linha diária + CSV)
# -------------------------------------------------------------------
# -------------------------------------------------------------------
# UTR — Barras por dia (mês selecionado), legenda com todos os dias
# -------------------------------------------------------------------
if modo == "UTR":
    import plotly.graph_objects as go  # para construir um trace por dia (legenda completa)

    st.header("🧭 UTR – Corridas ofertadas por hora (média diária)")
    col1, col2, col3 = st.columns([1,1,2])

    # --- Período (mês/ano) mantido ---
    mes_sel = col1.selectbox("Mês", list(range(1, 13)))
    ano_sel = col2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

    # Base completa do mês/ano (para CSV geral e para filtrar na visualização)
    base_full = utr_por_entregador_turno(df, mes_sel, ano_sel)

    if base_full.empty:
        st.info("Nenhum dado encontrado para o período selecionado.")
        st.stop()

    # HH:MM:SS (apenas para CSV)
    if "supply_hours" in base_full.columns:
        base_full["tempo_hms"] = base_full["supply_hours"].apply(_hms_from_hours)

    # --- Turno: UI mais clean (um só valor) ---
    turnos_disponiveis = ["Todos os turnos"]
    if "periodo" in base_full.columns:
        turnos_disponiveis += sorted([t for t in base_full["periodo"].dropna().unique()])
    turno_sel = col3.selectbox("Turno", options=turnos_disponiveis, index=0)

    # Filtra só para o GRÁFICO (se escolher um turno específico)
    base_plot = base_full.copy()
    if turno_sel != "Todos os turnos":
        base_plot = base_plot[base_plot["periodo"] == turno_sel]

    if base_plot.empty:
        st.info("Sem dados para o turno selecionado.")
        st.stop()

    # Garantir datetime p/ agrupar por dia
    base_plot["data"] = pd.to_datetime(base_plot["data"])

    # ======= Média diária de UTR (depois do filtro de turno, se houver) =======
    serie = (
        base_plot.groupby(base_plot["data"].dt.day)["UTR"]
        .mean()
        .reset_index()
        .rename(columns={"data": "dia", "UTR": "utr_media", "data": "dia_num"})
    )
    serie.columns = ["dia_num", "utr_media"]  # dia do mês (1..31), valor médio

    # ======= Gráfico de BARRAS com legenda contendo TODOS os dias =======
    # (um trace por dia → a legenda lista cada dia e você pode ligar/desligar)
    fig = go.Figure()
    for _, row in serie.sort_values("dia_num").iterrows():
        d = int(row["dia_num"])
        fig.add_bar(
            name=f"Dia {d}",
            x=[d],          # cada trace aparece em seu próprio dia no eixo
            y=[row["utr_media"]],
            hovertemplate="Dia %{x}<br>UTR médio %{y:.2f}<extra></extra>",
        )

    titulo_turno = turno_sel if turno_sel != "Todos os turnos" else "Todos os turnos"
    fig.update_layout(
        title=f"UTR médio por dia – {mes_sel:02d}/{ano_sel} • {titulo_turno}",
        xaxis_title="Dia do mês",
        yaxis_title="UTR (média do dia)",
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        title_font=dict(size=22),
        barmode="group",           # mantém cada barra separada (um trace por dia)
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="gray", rangemode="tozero"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ======= Resumo rápido =======
    colm1, colm2, colm3 = st.columns(3)
    colm1.metric("Média UTR no mês", f"{serie['utr_media'].mean():.2f}")
    colm2.metric("Mediana UTR no mês", f"{serie['utr_media'].median():.2f}")
    pico = serie.loc[serie['utr_media'].idxmax()] if not serie.empty else None
    if pico is not None:
        colm3.metric("Pico (dia)", f"{int(pico['dia_num'])} — {pico['utr_media']:.2f}")

    # ======= CSV GERAL (ignora filtro de turno) =======
    st.caption("📄 O botão abaixo baixa o **CSV GERAL** (sem filtro de turno).")
    cols_csv = ["data","pessoa_entregadora","periodo","tempo_hms","corridas_ofertadas","UTR"]
    base_csv = base_full.copy()

    # Formata data e tipos
    try:
        base_csv["data"] = pd.to_datetime(base_csv["data"]).dt.strftime("%d/%m/%Y")
    except Exception:
        base_csv["data"] = base_csv["data"].astype(str)

    for c in cols_csv:
        if c not in base_csv.columns:
            base_csv[c] = None

    base_csv["UTR"] = pd.to_numeric(base_csv["UTR"], errors="coerce").round(2)
    base_csv["corridas_ofertadas"] = pd.to_numeric(base_csv["corridas_ofertadas"], errors="coerce").fillna(0).astype(int)

    csv_bin = base_csv[cols_csv].to_csv(index=False, decimal=",").encode("utf-8")
    st.download_button(
        "⬇️ Baixar CSV (GERAL)",
        data=csv_bin,
        file_name=f"utr_entregador_turno_diario_{mes_sel:02d}_{ano_sel}.csv",
        mime="text/csv",
        help="Exporta o CSV geral do mês/ano, ignorando o filtro de turno."
    )

