# main.py
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


# ==============================
# Helpers de formatação
# ==============================
def _hms_from_hours(h):
    try:
        total_seconds = int(round(float(h) * 3600))
        horas, resto = divmod(total_seconds, 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"
    except Exception:
        return "00:00:00"


def kpi_cards(items, cols=4):
    """
    items: lista de dicts: {"label": "Corridas", "value": "24.8K", "help": "total do período"}
    """
    rows = (len(items) + cols - 1) // cols
    idx = 0
    for _ in range(rows):
        columns = st.columns(cols)
        for c in columns:
            if idx >= len(items): 
                break
            it = items[idx]
            with c:
                st.markdown(
                    f"""
                    <div class="kpi-card">
                        <div class="kpi-value">{it.get('value','-')}</div>
                        <div class="kpi-label">{it.get('label','')}</div>
                        <div class="kpi-help">{it.get('help','')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            idx += 1


def section_title(emoji, title, subtitle=None):
    st.markdown(f"<h1 class='title'>{emoji} {title}</h1>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<p class='subtitle'>{subtitle}</p>", unsafe_allow_html=True)


# ==============================
# Config inicial
# ==============================
st.set_page_config(
    page_title="Painel de Entregadores",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Tema (toggle claro/escuro simples)
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

with st.sidebar:
    st.write("🎛️ Aparência")
    theme_choice = st.radio("Tema", ["Escuro", "Claro"], index=0 if st.session_state.theme=="dark" else 1, horizontal=True)
    st.session_state.theme = "dark" if theme_choice == "Escuro" else "light"

# CSS: dois temas
DARK_CSS = """
<style>
:root {
  --bg: #0d1117;
  --panel: #111827;
  --muted: #9aa4b2;
  --txt: #e5e7eb;
  --primary: #1f6feb;
  --accent: #22c55e;
  --danger: #f43f5e;
  --warn: #f59e0b;
  --card: #0f172a;
  --card-border: #1e293b;
}
body, .stApp { background: var(--bg); color: var(--txt); }
.block-container { padding-top: 1.2rem; }
h1,h2,h3,h4 { color: #58a6ff; }
.sidebar .sidebar-content { background: var(--panel); }
.stTabs [data-baseweb="tab-list"] { gap: .5rem; }
.kpi-card{
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 6px 14px rgba(0,0,0,.25);
  margin-bottom: 12px;
}
.kpi-value{ font-size: 28px; font-weight: 700; line-height: 1; }
.kpi-label{ font-size: 13px; opacity:.9; margin-top: 6px;}
.kpi-help{ font-size: 12px; color: var(--muted); margin-top: 2px;}
.title{ color:#58a6ff; margin: .2rem 0 0; }
.subtitle{ color: var(--muted); margin: .2rem 0 1rem; }
hr{ border: none; border-top: 1px solid var(--card-border); margin: 1rem 0; }
table td, table th { color: var(--txt)!important; }
</style>
"""

LIGHT_CSS = """
<style>
:root {
  --bg: #f6f8fa;
  --panel: #ffffff;
  --muted: #6b7280;
  --txt: #111827;
  --primary: #1f6feb;
  --accent: #16a34a;
  --danger: #ef4444;
  --warn: #d97706;
  --card: #ffffff;
  --card-border: #e5e7eb;
}
body, .stApp { background: var(--bg); color: var(--txt); }
.block-container { padding-top: 1.2rem; }
h1,h2,h3,h4 { color: #0f172a; }
.kpi-card{
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 6px 14px rgba(17,17,26,.08);
  margin-bottom: 12px;
}
.kpi-value{ font-size: 28px; font-weight: 800; line-height: 1; color:#0f172a;}
.kpi-label{ font-size: 13px; color:#334155; margin-top: 6px;}
.kpi-help{ font-size: 12px; color: var(--muted); margin-top: 2px;}
.title{ color:#0f172a; margin:.2rem 0 0;}
.subtitle{ color: var(--muted); margin:.2rem 0 1rem;}
hr{ border: none; border-top: 1px solid var(--card-border); margin: 1rem 0; }
</style>
"""

st.markdown(DARK_CSS if st.session_state.theme=="dark" else LIGHT_CSS, unsafe_allow_html=True)


# ==============================
# Autenticação
# ==============================
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""

if not st.session_state.logado:
    st.title("🔐 Login do Painel")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar", use_container_width=True):
        if autenticar(usuario, senha):
            st.session_state.logado = True
            st.session_state.usuario = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()

st.sidebar.success(f"Bem-vindo, **{st.session_state.usuario}** 👋")

# ==============================
# Sidebar (seções)
# ==============================
st.sidebar.markdown("## 📚 Seções")
menu = st.sidebar.selectbox(
    "Navegação",
    [
        "📊 Estatísticas",
        "🚗 Desempenho",
        "⚠ Alertas de Faltas",
        "🧾 Relatório Customizado",
        "🏷️ Categorias de Entregadores",
    ],
    label_visibility="collapsed"
)

nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
if nivel == "admin":
    if st.sidebar.button("🔄 Atualizar dados (cache)"):
        st.cache_data.clear()
        st.rerun()

# ==============================
# Dados
# ==============================
df = carregar_dados()
df["data"] = pd.to_datetime(df["data"])
df["mes_ano"] = df["data"].dt.to_period("M").dt.to_timestamp()
entregadores = get_entregadores(df)


# ==============================
# 1) ESTATÍSTICAS
# ==============================
if menu == "📊 Estatísticas":
    section_title("📊", "Estatísticas", "Indicadores gerais e UTR")

    tab1, tab2 = st.tabs(["Indicadores Gerais", "UTR"])

    # -------- Indicadores Gerais --------
    with tab1:
        st.markdown("### Visão Geral por Mês")

        # KPIs do período total
        total_ofertadas = int(df["numero_de_corridas_ofertadas"].sum())
        total_aceitas = int(df["numero_de_corridas_aceitas"].sum())
        total_rejeitadas = int(df["numero_de_corridas_rejeitadas"].sum())
        total_completas = int(df["numero_de_corridas_completadas"].sum())
        taxa_aceit = round((total_aceitas / total_ofertadas) * 100, 1) if total_ofertadas else 0.0
        taxa_conc = round((total_completas / total_aceitas) * 100, 1) if total_aceitas else 0.0

        kpi_cards([
            {"label":"Corridas ofertadas", "value": f"{total_ofertadas:,}".replace(",",".")},
            {"label":"Aceitação (%)", "value": f"{taxa_aceit:.1f}%"},
            {"label":"Conclusão (%)", "value": f"{taxa_conc:.1f}%"},
            {"label":"Entregadores únicos", "value": f"{df['pessoa_entregadora'].nunique()}"},
        ], cols=4)

        tipo_grafico = st.radio(
            "Tipo de gráfico:", 
            ["Corridas ofertadas","Corridas aceitas","Corridas rejeitadas","Corridas completadas"],
            index=0, horizontal=True
        )
        coluna_map = {
            "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Corridas"),
            "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas Aceitas"),
            "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas Rejeitadas"),
            "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas Completadas")
        }
        col, titulo, label = coluna_map[tipo_grafico]

        mensal = df.groupby('mes_ano')[col].sum().reset_index()
        mensal['mes_ao'] = mensal['mes_ano'].dt.strftime('%b/%y')
        mensal["_x"] = mensal['mes_ao']

        fig = px.bar(
            mensal, x="_x", y=col, text=col, title=titulo,
            labels={col: label, "_x": "Mês/Ano"}, template='plotly_dark' if st.session_state.theme=="dark" else "plotly_white",
        )
        fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False)
        fig.update_layout(
            xaxis=dict(showgrid=False), 
            yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,.25)'),
            margin=dict(l=10,r=10,t=60,b=10),
            height=420
        )
        st.plotly_chart(fig, use_container_width=True)

        # Por dia (mês atual)
        st.markdown("### Mês Atual – Evolução diária")
        mes_atual = pd.Timestamp.today().month
        ano_atual = pd.Timestamp.today().year
        df_mes = df[(df['data'].dt.month == mes_atual) & (df['data'].dt.year == ano_atual)]

        coluna_dia_map = {
            "Corridas ofertadas": ('numero_de_corridas_ofertadas', '📈 Ofertadas por dia', 'Ofertadas'),
            "Corridas aceitas": ('numero_de_corridas_aceitas', '📈 Aceitas por dia', 'Aceitas'),
            "Corridas rejeitadas": ('numero_de_corridas_rejeitadas', '📈 Rejeitadas por dia', 'Rejeitadas'),
            "Corridas completadas": ('numero_de_corridas_completadas', '📈 Completas por dia', 'Completas')
        }
        coluna_dia, titulo_dia, label_dia = coluna_dia_map[tipo_grafico]
        por_dia = df_mes.groupby(df_mes['data'].dt.day)[coluna_dia].sum().reset_index()
        por_dia.rename(columns={'data': 'dia'}, inplace=True)

        fig_dia = px.line(
            por_dia, x='dia', y=coluna_dia, markers=True, title=titulo_dia,
            labels={'dia':'Dia', coluna_dia: label_dia},
            template='plotly_dark' if st.session_state.theme=="dark" else "plotly_white",
        )
        st.metric(f"Total no mês ({label_dia})", int(por_dia[coluna_dia].sum()))
        st.plotly_chart(fig_dia, use_container_width=True)

    # -------- UTR --------
    with tab2:
        st.markdown("### UTR – Corridas ofertadas por hora (por entregador e turno)")
        tipo_utr = st.radio("Período:", ["Mês/Ano", "Todo o histórico"], horizontal=True, index=0)
        mes_sel_utr = ano_sel_utr = None
        if tipo_utr == "Mês/Ano":
            c1, c2 = st.columns(2)
            mes_sel_utr = c1.selectbox("Mês", list(range(1, 13)))
            ano_sel_utr = c2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

        base = utr_por_entregador_turno(df, mes_sel_utr, ano_sel_utr) if tipo_utr == "Mês/Ano" else utr_por_entregador_turno(df)

        if base.empty:
            st.info("Nenhum dado encontrado para o período selecionado.")
        else:
            if "supply_hours" in base.columns:
                base["tempo_hms"] = base["supply_hours"].apply(_hms_from_hours)

            c1, c2 = st.columns(2)
            c1.metric("UTR média (geral)", round(base["UTR"].mean(), 2))
            c2.metric("UTR mediana (geral)", round(base["UTR"].median(), 2))

            st.subheader("Tabela por entregador e turno")
            cols_utr = ["pessoa_entregadora","periodo","tempo_hms","corridas_ofertadas","UTR"]
            st.dataframe(base[cols_utr].style.format({"UTR":"{:.2f}"}), use_container_width=True)

            csv_utr = base[cols_utr].to_csv(index=False, decimal=",").encode("utf-8")
            st.download_button("⬇️ Baixar CSV", data=csv_utr, file_name="utr_entregador_turno.csv", mime="text/csv")

            piv = utr_pivot_por_entregador(df, mes_sel_utr, ano_sel_utr) if tipo_utr == "Mês/Ano" else utr_pivot_por_entregador(df)
            if not piv.empty:
                st.subheader("Pivot por entregador x turno")
                st.dataframe(piv, use_container_width=True)
                piv_csv = piv.to_csv(decimal=",").encode("utf-8")
                st.download_button("⬇️ Baixar Pivot CSV", data=piv_csv, file_name="utr_pivot_por_turno.csv", mime="text/csv")


# ==============================
# 2) DESEMPENHO
# ==============================
elif menu == "🚗 Desempenho":
    section_title("🚗", "Desempenho", "Relatório geral e versão WhatsApp")

    tab1, tab2 = st.tabs(["Ver geral", "Simplificada (WhatsApp)"])

    with tab1:
        with st.form("form_geral"):
            entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
            nome = st.selectbox("🔎 Entregador", [None] + entregadores_lista, format_func=lambda x: "" if x is None else x)
            gerar = st.form_submit_button("🔍 Gerar relatório")
        if gerar and nome:
            texto = gerar_dados(nome, None, None, df[df["pessoa_entregadora"] == nome])
            st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=420)

    with tab2:
        with st.form("form_whats"):
            entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
            nome = st.selectbox("🔎 Entregador", [None] + entregadores_lista, format_func=lambda x: "" if x is None else x)
            col1, col2 = st.columns(2)
            mes1 = col1.selectbox("1º Mês", list(range(1, 13)))
            ano1 = col2.selectbox("1º Ano", sorted(df["ano"].unique(), reverse=True))
            mes2 = col1.selectbox("2º Mês", list(range(1, 13)))
            ano2 = col2.selectbox("2º Ano", sorted(df["ano"].unique(), reverse=True))
            gerar = st.form_submit_button("🔍 Gerar simplificado")
        if gerar and nome:
            t1 = gerar_simplicado(nome, mes1, ano1, df)
            t2 = gerar_simplicado(nome, mes2, ano2, df)
            st.text_area("Resultado:", value="\n\n".join([t for t in [t1, t2] if t]), height=520)


# ==============================
# 3) ALERTAS DE FALTAS
# ==============================
elif menu == "⚠ Alertas de Faltas":
    section_title("⚠", "Alertas de Faltas", "Entregadores com ausências consecutivas")

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
        st.text_area("Resultado:", value="\n".join(mensagens), height=420)
    else:
        st.success("✅ Nenhum entregador ativo com faltas consecutivas.")

# ==============================
# 4) RELATÓRIO CUSTOMIZADO
# ==============================
elif menu == "🧾 Relatório Customizado":
    section_title("🧾", "Relatório Customizado")

    entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
    entregador = st.selectbox("🔎 Entregador", [None] + entregadores_lista, format_func=lambda x: "" if x is None else x)

    subpracas = sorted(df["sub_praca"].dropna().unique())
    filtro_subpraca = st.multiselect("Filtrar por subpraça", subpracas)

    turnos = sorted(df["periodo"].dropna().unique())
    filtro_turno = st.multiselect("Filtrar por turno", turnos)

    df['data_do_periodo'] = pd.to_datetime(df['data_do_periodo'])
    df['data'] = df['data_do_periodo'].dt.date

    tipo_periodo = st.radio("Como deseja escolher as datas?", ("Período contínuo", "Dias específicos"), horizontal=True)
    dias_escolhidos = []

    if tipo_periodo == "Período contínuo":
        data_min = df["data"].min()
        data_max = df["data"].max()
        periodo = st.date_input("Intervalo de datas", [data_min, data_max], format="DD/MM/YYYY")
        if len(periodo) == 2:
            dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
        elif len(periodo) == 1:
            dias_escolhidos = [periodo[0]]
    else:
        dias_opcoes = sorted(df["data"].unique())
        dias_escolhidos = st.multiselect("Dias desejados", dias_opcoes, format_func=lambda x: x.strftime("%d/%m/%Y"))

    if st.button("Gerar relatório", type="primary"):
        if entregador:
            df_filt = df[df["pessoa_entregadora"] == entregador]
            if filtro_subpraca:
                df_filt = df_filt[df_filt["sub_praca"].isin(filtro_subpraca)]
            if filtro_turno:
                df_filt = df_filt[df_filt["periodo"].isin(filtro_turno)]
            if dias_escolhidos:
                df_filt = df_filt[df_filt["data"].isin(dias_escolhidos)]

            texto = gerar_dados(entregador, None, None, df_filt)
            st.text_area("Resultado:", value=texto or "❌ Nenhum dado encontrado", height=420)
        else:
            st.warning("Selecione um entregador.")

# ==============================
# 5) CATEGORIAS
# ==============================
elif menu == "🏷️ Categorias de Entregadores":
    section_title("🏷️", "Categorias de Entregadores", "SH, aceitação, conclusão e regras")

    tipo_cat = st.radio("Período de análise", ["Mês/Ano", "Todo o histórico"], horizontal=True, index=0)
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
