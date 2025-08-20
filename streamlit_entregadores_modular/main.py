import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from relatorios import (
    gerar_dados,
    gerar_alertas_de_faltas,
    get_entregadores,
    classificar_entregadores,
    utr_por_entregador_turno,
)
from auth import autenticar, USUARIOS
from data_loader import carregar_dados

# =============================================
# CONFIG BÁSICA
# =============================================
st.set_page_config(page_title="Painel de Entregadores", page_icon="🚀", layout="wide")

# =============================================
# TEMA & ESTILO (Dark elegante + cartões)
# =============================================
st.markdown(
    """
    <style>
    :root{
        --bg:#0b0f16;          /* fundo principal */
        --bg-2:#0f1724;        /* painéis */
        --bg-3:#121a28;        /* hover/containers */
        --txt:#e6edf3;         /* texto */
        --muted:#9aa4b2;       /* texto secundário */
        --pri:#6ea8fe;         /* primária */
        --pri-2:#5ab0ff;       /* primária 2 */
        --acc:#00e0ff;         /* destaque */
        --good:#2ecc71;        /* verde */
        --warn:#f39c12;        /* amarelo */
        --bad:#ff6b6b;         /* vermelho */
        --radius:18px;
        --shadow:0 10px 30px rgba(0,0,0,.35);
    }

    html, body, .block-container{ background: var(--bg); color: var(--txt); }
    .stSidebar{ background: linear-gradient(180deg, #0d1320 0%, #0b0f16 100%) !important; }

    /* Botões padrão -> pill */
    .stButton>button { border:0; border-radius: 999px; padding:.65rem 1rem; font-weight:700; color:#0b0f16; background: linear-gradient(90deg, var(--pri), var(--acc)); box-shadow: var(--shadow); }
    .stButton>button:hover { filter:brightness(1.08); transform: translateY(-1px); }

    h1, h2, h3 { color: var(--pri); }

    /* Inputs */
    .stSelectbox, .stMultiSelect, .stTextInput, .stDateInput, .stRadio, .stSegmentedControl{
        background: var(--bg-2) !important; color: var(--txt) !important;
    }

    /* Card bonito */
    .app-card{
        background: radial-gradient(1200px 400px at -20% -10%, rgba(0,224,255,.06), transparent 40%),
                    linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.02));
        border:1px solid rgba(255,255,255,.06);
        border-radius: var(--radius);
        padding: 20px; height: 140px; position: relative; overflow:hidden;
        box-shadow: var(--shadow);
        transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
    }
    .app-card:hover{ transform: translateY(-4px); border-color: rgba(94,171,255,.35); box-shadow: 0 14px 40px rgba(30,90,170,.35); }
    .app-card h3{ margin:0; color:#fff; font-size: 1.05rem; }
    .app-card .sub{ color: var(--muted); font-size:.9rem; margin-top:.35rem }
    .app-card .emoji{ font-size:1.35rem; position:absolute; right:16px; bottom:16px; opacity:.9 }

    /* Grupos da sidebar */
    .menu-group { font-weight:800; margin: .5rem 0 .15rem; color: #94a3b8; text-transform: uppercase; font-size: .75rem; letter-spacing:.06em; }
    .menu-divider { height:1px; background: rgba(255,255,255,.06); margin:.35rem 0 1rem }

    /* Container/seções */
    .panel{ background: var(--bg-2); border:1px solid rgba(255,255,255,.06); border-radius: var(--radius); padding:18px; box-shadow: var(--shadow) }
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================================
# AUTENTICAÇÃO
# =============================================
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

# =============================================
# CARREGAMENTO DE DADOS
# =============================================
@st.cache_data(show_spinner=False)
def _carregar():
    df = carregar_dados()
    df["data"] = pd.to_datetime(df["data"])
    df["mes_ano"] = df["data"].dt.to_period("M").dt.to_timestamp()
    return df

df = _carregar()

nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
with st.sidebar:
    if nivel == "admin":
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()

# =============================================
# NAVEGAÇÃO (Home com cards + Drill-down na sidebar)
# =============================================
GROUPS = {
    "📊 Gráficos e estatísticas": ["Indicadores gerais", "UTR"],
    "🚴 Desempenho do entregador": ["Categorias de Entregadores", "Ver geral", "Relatório Customizado"],
    "⚠️ Avisos": ["Alertas de Faltas"],
}

if "page" not in st.session_state:
    st.session_state.page = "home"  # home | sub | leaf
if "group" not in st.session_state:
    st.session_state.group = None
if "leaf" not in st.session_state:
    st.session_state.leaf = None

# ----- Sidebar: drill-down elegante -----
with st.sidebar:
    st.markdown("<div class='menu-group'>Navegação</div>", unsafe_allow_html=True)
    top_choice = st.radio("Grupos", list(GROUPS.keys()), index=0)
    if top_choice != st.session_state.group:
        st.session_state.group = top_choice
        st.session_state.page = "sub"
        st.session_state.leaf = None
    st.markdown("<div class='menu-divider'></div>", unsafe_allow_html=True)

    sub_options = GROUPS[st.session_state.group]
    sub_choice = st.radio("Opções", sub_options, index=0, label_visibility="collapsed")
    if sub_choice != st.session_state.leaf:
        st.session_state.leaf = sub_choice
        st.session_state.page = "leaf"

# ----- Header com breadcrumb -----
if st.session_state.page == "home":
    st.title("🚀 Painel – Início")
else:
    bc = f"**Início** / **{st.session_state.group}**"
    if st.session_state.page == "leaf" and st.session_state.leaf:
        bc += f" / **{st.session_state.leaf}**"
    cols = st.columns([1,6,1])
    with cols[0]:
        if st.button("⬅ Voltar"):
            if st.session_state.page == "leaf":
                st.session_state.page = "sub"
                st.rerun()
            else:
                st.session_state.page = "home"
                st.rerun()
    with cols[1]:
        st.markdown(bc)

# ----- HOME: cards lindões para grupos -----
if st.session_state.page == "home":
    st.subheader("Escolha um grupo para entrar")
    c1, c2, c3 = st.columns(3)

    def card(title: str, subtitle: str, emoji: str, key: str):
        with st.container(border=False):
            st.markdown(f"""
            <div class='app-card'>
                <h3>{title}</h3>
                <div class='sub'>{subtitle}</div>
                <div class='emoji'>{emoji}</div>
            </div>
            """, unsafe_allow_html=True)
            st.button("Abrir", key=key, use_container_width=True, type="secondary")

    with c1:
        card("Gráficos e estatísticas", "Indicadores gerais, UTR", "📊", "go_grp_1")
        if st.session_state.get("go_grp_1"):
            st.session_state.group = list(GROUPS.keys())[0]
            st.session_state.page = "sub"
            st.rerun()
    with c2:
        card("Desempenho do entregador", "Categorias, Relatórios", "🚴", "go_grp_2")
        if st.session_state.get("go_grp_2"):
            st.session_state.group = list(GROUPS.keys())[1]
            st.session_state.page = "sub"
            st.rerun()
    with c3:
        card("Avisos", "Alertas e faltas", "⚠️", "go_grp_3")
        if st.session_state.get("go_grp_3"):
            st.session_state.group = list(GROUPS.keys())[2]
            st.session_state.page = "sub"
            st.rerun()

# ----- SUB: mostra cards dos itens do grupo -----
if st.session_state.page == "sub":
    st.title(st.session_state.group)
    st.subheader("Selecione uma opção")
    items = GROUPS[st.session_state.group]
    cols = st.columns(3)
    for i, item in enumerate(items):
        with cols[i % 3]:
            st.markdown(f"""
            <div class='app-card'>
                <h3>{item}</h3>
                <div class='sub'>Abrir {item}</div>
                <div class='emoji'>➡️</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Abrir", key=f"open_{i}", use_container_width=True):
                st.session_state.leaf = item
                st.session_state.page = "leaf"
                st.rerun()

# =============================================
# PÁGINAS (LEAF)
# =============================================

def _hms_from_hours(h):
    try:
        total_seconds = int(round(float(h) * 3600))
        horas, resto = divmod(total_seconds, 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"
    except Exception:
        return "00:00:00"

leaf = st.session_state.leaf

if st.session_state.page == "leaf" and leaf:
    # ----------------- Indicadores gerais -----------------
    if leaf == "Indicadores gerais":
        st.title("📊 Indicadores gerais")
        tipo_grafico = st.radio("Tipo de gráfico:", [
            "Corridas ofertadas",
            "Corridas aceitas",
            "Corridas rejeitadas",
            "Corridas completadas",
        ], index=0, horizontal=True)

        coluna_map = {
            "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Corridas"),
            "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas Aceitas"),
            "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas Rejeitadas"),
            "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas Completadas"),
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
            "Corridas completadas": ('numero_de_corridas_completadas', '📈 Corridas completadas por dia (mês atual)', 'Corridas Completadas'),
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
        c1, c2 = st.columns(2)
        c1.metric(f"🚗 {label_dia} no mês", total_mes)
        c2.metric("Dias com dados", int(por_dia.shape[0]))
        st.plotly_chart(fig_dia, use_container_width=True)

    # ----------------- UTR -----------------
    elif leaf == "UTR":
        st.title("🧭 UTR – Corridas ofertadas por hora")
        tipo_utr = st.radio("Período:", ["Mês/Ano", "Todo o histórico"], horizontal=True, index=0)
        mes_sel_utr = ano_sel_utr = None
        if tipo_utr == "Mês/Ano":
            col1, col2 = st.columns(2)
            mes_sel_utr = col1.selectbox("Mês", list(range(1, 13)))
            ano_sel_utr = col2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))
        base = (utr_por_entregador_turno(df, mes_sel_utr, ano_sel_utr) if tipo_utr == "Mês/Ano" else utr_por_entregador_turno(df))
        if base.empty:
            st.info("Nenhum dado encontrado para o período selecionado.")
        else:
            if "supply_hours" in base.columns:
                base["tempo_hms"] = base["supply_hours"].apply(_hms_from_hours)
            cols_utr = ["data","pessoa_entregadora","periodo","tempo_hms","corridas_ofertadas","UTR"]
            df_view = base[cols_utr].copy()
            try:
                df_view["data"] = pd.to_datetime(df_view["data"]).dt.strftime("%d/%m/%Y")
            except Exception:
                df_view["data"] = df_view["data"].astype(str)
            df_view["UTR"] = pd.to_numeric(df_view["UTR"], errors="coerce").round(2)
            df_view["corridas_ofertadas"] = pd.to_numeric(df_view["corridas_ofertadas"], errors="coerce").fillna(0).astype(int)
            st.metric("Média UTR (geral)", float(df_view["UTR"].mean().round(2)))
            st.metric("Mediana UTR (geral)", float(df_view["UTR"].median().round(2)))
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
            csv_utr = df_view.to_csv(index=False, decimal=",").encode("utf-8")
            st.download_button("⬇️ Baixar CSV", data=csv_utr, file_name="utr_entregador_turno_diario.csv", mime="text/csv")

    # ----------------- Categorias -----------------
    elif leaf == "Categorias de Entregadores":
        st.title("📚 Categorias de Entregadores")
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
            if "supply_hours" in df_cat.columns:
                df_cat["tempo_hms"] = df_cat["supply_hours"].apply(_hms_from_hours)
            contagem = df_cat["categoria"].value_counts().reindex(["Premium","Conectado","Casual","Flutuante"]).fillna(0).astype(int)
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("🚀 Premium", int(contagem.get("Premium",0)))
            c2.metric("🎯 Conectado", int(contagem.get("Conectado",0)))
            c3.metric("👍 Casual", int(contagem.get("Casual",0)))
            c4.metric("↩ Flutuante", int(contagem.get("Flutuante",0)))
            st.subheader("Tabela de classificação")
            cols_cat = ["pessoa_entregadora","categoria","tempo_hms","aceitacao_%","conclusao_%","ofertadas","aceitas","completas","criterios_atingidos"]
            st.dataframe(
                df_cat[cols_cat].style.format({"aceitacao_%":"{:.1f}","conclusao_%":"{:.1f}"}),
                use_container_width=True
            )
            csv_cat = df_cat[cols_cat].to_csv(index=False, decimal=",").encode("utf-8")
            st.download_button("⬇️ Baixar CSV", data=csv_cat, file_name="categorias_entregadores.csv", mime="text/csv")

    # ----------------- Ver geral -----------------
    elif leaf == "Ver geral":
        st.title("🔎 Desempenho do entregador – Visão geral")
        entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
        with st.form("form_ver_geral"):
            nome = st.selectbox("Selecione o entregador:", [None] + entregadores_lista, format_func=lambda x: "" if x is None else x)
            gerar = st.form_submit_button("🔍 Gerar relatório")
        if gerar and nome:
            with st.spinner("Gerando relatório..."):
                texto = gerar_dados(nome, None, None, df[df["pessoa_entregadora"] == nome])
                st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=400)

    # ----------------- Relatório Customizado -----------------
    elif leaf == "Relatório Customizado":
        st.title("🧩 Relatório Customizado")
        entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
        entregador = st.selectbox("Entregador:", [None] + entregadores_lista, format_func=lambda x: "" if x is None else x)
        subpracas = sorted(df["sub_praca"].dropna().unique())
        filtro_subpraca = st.multiselect("Filtrar por subpraça:", subpracas)
        turnos = sorted(df["periodo"].dropna().unique())
        filtro_turno = st.multiselect("Filtrar por turno:", turnos)
        df['data'] = pd.to_datetime(df['data']).dt.date
        tipo_periodo = st.radio("Como deseja escolher as datas?", ("Período contínuo", "Dias específicos"), horizontal=True)
        dias_escolhidos = []
        if tipo_periodo == "Período contínuo":
            data_min = min(df["data"]) if len(df["data"]) else None
            data_max = max(df["data"]) if len(df["data"]) else None
            if data_min and data_max:
                periodo = st.date_input("Intervalo:", [data_min, data_max], format="DD/MM/YYYY")
                if len(periodo) == 2:
                    dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
                elif len(periodo) == 1:
                    dias_escolhidos = [periodo[0]]
        else:
            dias_opcoes = sorted(pd.unique(df["data"]))
            dias_escolhidos = st.multiselect(
                "Selecione os dias:",
                dias_opcoes,
                format_func=lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else str(x)
            )
        if st.button("Gerar relatório customizado") and entregador:
            df_filt = df[df["pessoa_entregadora"] == entregador]
            if filtro_subpraca:
                df_filt = df_filt[df_filt["sub_praca"].isin(filtro_subpraca)]
            if filtro_turno:
                df_filt = df_filt[df_filt["periodo"].isin(filtro_turno)]
            if dias_escolhidos:
                df_filt = df_filt[df_filt["data"].isin(dias_escolhidos)]
            texto = gerar_dados(entregador, None, None, df_filt)
            st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=400)

    # ----------------- Alertas de Faltas -----------------
    elif leaf == "Alertas de Faltas":
        st.title("⚠️ Alertas de Faltas")
        hoje = datetime.now().date()
        ultimos_15_dias = hoje - timedelta(days=15)
        df_date = pd.to_datetime(df["data"]).dt.date
        ativos = pd.Series(df_date >= ultimos_15_dias).sum()
        st.metric("Registros no período (15 dias)", int(ativos))
        mensagens = []
        df_copy = df.copy()
        df_copy["data"] = pd.to_datetime(df_copy["data"]).dt.date
        for nome in sorted(df_copy["pessoa_entregadora"].dropna().unique()):
            entregador = df_copy[df_copy["pessoa_entregadora"] == nome]
            if entregador.empty:
                continue
            dias = pd.date_range(end=hoje - timedelta(days=1), periods=30).to_pydatetime()
            dias = [d.date() for d in dias]
            presencas = set(entregador["data"])  # tipos date
            sequencia = 0
            for dia in sorted(dias):
                if dia in presencas:
                    sequencia = 0
                else:
                    sequencia += 1
            if sequencia >= 4:
                ultima_data = pd.to_datetime(max(presencas)).strftime('%d/%m') if presencas else "—"
                mensagens.append(f"• {nome} – {sequencia} dias consecutivos ausente (última presença: {ultima_data})")
        if mensagens:
            st.text_area("Resultado:", value="\n".join(mensagens), height=400)
        else:
            st.success("✅ Nenhum entregador ativo com faltas consecutivas.")

# Fim
