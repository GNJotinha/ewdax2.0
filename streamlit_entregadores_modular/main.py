# main.py

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from utils import normalizar, tempo_para_segundos

from relatorios import (
    gerar_dados,
    gerar_simplicado,
    gerar_alertas_de_faltas,
    get_entregadores,
    classificar_entregadores,
    utr_por_entregador_turno,
    utr_pivot_por_entregador,
    _horas_from_abs,
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


# =========================
# Helpers de performance
# =========================
@st.cache_data
def _utr_mensal_cached(df_key, mes: int, ano: int, turno: str | None):
    """
    UTR mensal (ponderada no absoluto) = ofertadas_totais / horas_totais,
    opcionalmente filtrando por turno. Cacheia por (df_key, mes, ano, turno).
    """
    dados = df[(df["mes"] == mes) & (df["ano"] == ano)]
    if turno and turno != "Todos os turnos" and "periodo" in dados.columns:
        dados = dados[dados["periodo"] == turno]

    if dados.empty:
        return 0.0

    ofertadas = float(dados["numero_de_corridas_ofertadas"].sum())
    if "segundos_abs" in dados.columns:
        horas = dados["segundos_abs"].sum() / 3600.0
    else:
        horas = _horas_from_abs(dados)

    return (ofertadas / horas) if horas > 0 else 0.0


# -------------------------------------------------------------------
# Config da página
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

MENU = {
    "Desempenho do Entregador": [
        "Ver geral",
        "Simplificada (WhatsApp)",
        "Relatório Customizado",
    ],
    "Relatórios": [
        "Alertas de Faltas",
        "Relação de Entregadores",
        "Categorias de Entregadores",
    ],
    "Dashboards": [
        "UTR",
        "Indicadores Gerais",
    ],
}

if "modo" not in st.session_state:
    st.session_state.modo = "Início"
if "open_cat" not in st.session_state:
    st.session_state.open_cat = None

with st.sidebar:
    st.markdown("### 🧭 Navegação")

    if st.button("🏠 Início", use_container_width=True):
        st.session_state.modo = "Início"
        st.session_state.open_cat = None
        st.rerun()

    for cat, opts in MENU.items():
        expanded = (st.session_state.open_cat == cat)
        with st.expander(cat, expanded=expanded):
            for opt in opts:
                if st.button(opt, key=f"btn_{cat}_{opt}", use_container_width=True):
                    st.session_state.modo = opt
                    st.session_state.open_cat = cat
                    st.rerun()

modo = st.session_state.modo

# -------------------------------------------------------------------
# Dados
# -------------------------------------------------------------------
df = carregar_dados()

# Fallbacks robustos (caso o loader não traga prontos)
if "mes_ano" not in df.columns:
    base_dt = pd.to_datetime(df.get("data_do_periodo", df.get("data")), errors="coerce")
    df["mes_ano"] = base_dt.dt.to_period("M").dt.to_timestamp()

if "segundos_abs" not in df.columns:
    col = "tempo_disponivel_absoluto"
    if col in df.columns:
        s = df[col]
        try:
            if pd.api.types.is_timedelta64_dtype(s):
                df["segundos_abs"] = s.dt.total_seconds().fillna(0).astype(int)
            elif pd.api.types.is_numeric_dtype(s):
                df["segundos_abs"] = pd.to_numeric(s, errors="coerce").fillna(0).astype(int)
            else:
                td = pd.to_timedelta(s.astype(str), errors="coerce")
                if td.notna().any():
                    df["segundos_abs"] = td.dt.total_seconds().fillna(0).astype(int)
                else:
                    df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
        except Exception:
            df["segundos_abs"] = s.apply(tempo_para_segundos).fillna(0).astype(int)
    else:
        df["segundos_abs"] = 0

# chave leve do dataset para cache (muda quando entram linhas novas ou última data muda)
df_key = (df.shape, pd.to_datetime(df["data"]).max())

# horas por mês pré-agregadas (reuso nos gráficos)
horas_mensais = (
    df.groupby("mes_ano", as_index=False)["segundos_abs"]
      .sum()
      .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
      .drop(columns="segundos_abs")
)

entregadores = get_entregadores(df)

# -------------------------------------------------------------------
# Ver geral / Simplificada
# -------------------------------------------------------------------
if modo in ["Ver geral", "Simplificada (WhatsApp)"]:
    with st.form("formulario"):
        entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
        nome = st.selectbox(
            "🔎 Selecione o entregador:",
            [None] + entregadores_lista,
            format_func=lambda x: "" if x is None else x
        )

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
# 📊 Indicadores Gerais (com % e UTR alinhado)
# -------------------------------------------------------------------
if modo == "Indicadores Gerais":
    st.subheader("🔎 Escolha o indicador que deseja visualizar:")

    tipo_grafico = st.radio(
        "Tipo de gráfico:",
        [
            "Corridas ofertadas",
            "Corridas aceitas",
            "Corridas rejeitadas",
            "Corridas completadas",
            "Horas realizadas",
        ],
        index=0,
        horizontal=True,
    )

    mes_atual = pd.Timestamp.today().month
    ano_atual = pd.Timestamp.today().year
    df_mes_atual = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)]

    if tipo_grafico == "Horas realizadas":
        mensal_horas = (
            df.groupby("mes_ano", as_index=False)["segundos_abs"].sum()
              .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
        )
        mensal_horas["mes_rotulo"] = mensal_horas["mes_ano"].dt.strftime("%b/%y")

        fig_mensal = px.bar(
            mensal_horas,
            x="mes_rotulo",
            y="horas",
            text="horas",
            title="Horas realizadas por mês",
            labels={"mes_rotulo": "Mês/Ano", "horas": "Horas"},
            template="plotly_dark",
            color_discrete_sequence=["#00BFFF"],
        )
        fig_mensal.update_traces(
            texttemplate="<b>%{text:.1f}h</b>",
            textposition="outside",
            textfont=dict(size=16, color="white"),
            marker_line_color="rgba(255,255,255,0.25)",
            marker_line_width=0.5,
        )
        fig_mensal.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"), title_font=dict(size=22),
            xaxis=dict(showgrid=False, tickfont=dict(size=14)),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.15)", tickfont=dict(size=14)),
            bargap=0.25, margin=dict(t=70, r=20, b=60, l=60), showlegend=False,
        )
        st.plotly_chart(fig_mensal, use_container_width=True)

        if not df_mes_atual.empty:
            por_dia_h = (
                df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                           .groupby("dia", as_index=False)["segundos_abs"].sum()
                           .assign(horas=lambda d: d["segundos_abs"] / 3600.0)
                           .sort_values("dia")
            )
            fig_linha = px.line(
                por_dia_h, x="dia", y="horas",
                title="📈 Horas realizadas por dia (mês atual)",
                labels={"dia": "Dia", "horas": "Horas"},
                template="plotly_dark",
            )
            fig_linha.update_traces(mode="lines", line_shape="spline",
                                    hovertemplate="Dia %{x}<br>%{y:.2f}h<extra></extra>")
            fig_linha.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"), title_font=dict(size=22),
                xaxis=dict(showgrid=False, tickmode="linear", dtick=1),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.15)"),
                margin=dict(t=60, r=20, b=60, l=60),
            )
            total_horas_mes = por_dia_h["horas"].sum()
            st.metric("⏱️ Horas realizadas no mês", _hms_from_hours(total_horas_mes))
            st.plotly_chart(fig_linha, use_container_width=True)
        else:
            st.info("Sem dados no mês atual para plotar as horas diárias.")
        st.stop()

    coluna_map = {
        "Corridas ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês", "Corridas"),
        "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas Aceitas"),
        "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas Rejeitadas"),
        "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas Completadas"),
    }
    if tipo_grafico not in coluna_map:
        st.warning("Tipo de gráfico inválido.")
        st.stop()

    col, titulo, label = coluna_map[tipo_grafico]

    mensal = df.groupby("mes_ano", as_index=False)[col].sum()
    mensal["mes_rotulo"] = mensal["mes_ano"].dt.strftime("%b/%y")

    if tipo_grafico in ["Corridas aceitas", "Corridas rejeitadas"]:
        # % sobre OFERTADAS (mantém)
        mensal_ofert = (
            df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum()
              .rename(columns={"numero_de_corridas_ofertadas": "ofertadas_total"})
        )
        mensal = mensal.merge(mensal_ofert, on="mes_ano", how="left")

        def _pct(v, base):
            try:
                v = float(v); base = float(base)
                return f"{(v/base*100):.1f}%" if base > 0 else "0.0%"
            except Exception:
                return "0.0%"

        mensal["__label_text__"] = mensal.apply(
            lambda r: f"{int(r[col])} ({_pct(r[col], r.get('ofertadas_total', 0))})",
            axis=1
        )

    elif tipo_grafico == "Corridas completadas":
        # ✅ % sobre ACEITAS (alinhado com os relatórios)
        mensal_aceit = (
            df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"].sum()
              .rename(columns={"numero_de_corridas_aceitas": "aceitas_total"})
        )
        mensal = mensal.merge(mensal_aceit, on="mes_ano", how="left")

        def _pct_sobre_aceitas(completas, aceitas):
            try:
                completas = float(completas); aceitas = float(aceitas)
                return f"{(completas/aceitas*100):.1f}%" if aceitas > 0 else "0.0%"
            except Exception:
                return "0.0%"

        mensal["__label_text__"] = mensal.apply(
            lambda r: f"{int(r[col])} ({_pct_sobre_aceitas(r[col], r.get('aceitas_total', 0))})",
            axis=1
        )

    elif tipo_grafico == "Corridas ofertadas":
        # Rótulo com UTR médio (ofertadas/hora)
        mensal = mensal.merge(horas_mensais, on="mes_ano", how="left")
        mensal["UTR_medio"] = mensal.apply(
            lambda r: (float(r[col]) / float(r["horas"])) if (pd.notna(r["horas"]) and r["horas"] > 0) else 0.0,
            axis=1
        )
        mensal["__label_text__"] = mensal.apply(
            lambda r: f"{int(r[col])}\nUTR {float(r['UTR_medio']):.2f}",
            axis=1
        )
    else:
        mensal["__label_text__"] = mensal[col].fillna(0).astype(int).astype(str)

    fig = px.bar(
        mensal, x="mes_rotulo", y=col, text="__label_text__", title=titulo,
        labels={col: label, "mes_rotulo": "Mês/Ano"},
        template="plotly_dark", color_discrete_sequence=["#00BFFF"]
    )
    fig.update_traces(
        texttemplate="%{text}",
        textposition="outside",
        textfont=dict(size=16, color="white"),
        marker_line_color="rgba(255,255,255,0.25)",
        marker_line_width=0.5,
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"), title_font=dict(size=22),
        xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.15)"),
        bargap=0.25, margin=dict(t=80, r=20, b=60, l=60), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Captions deixando explícita a base do %
    if tipo_grafico == "Corridas completadas":
        st.caption("ℹ️ A porcentagem mostrada é **completadas ÷ aceitas** (alinhado aos relatórios).")
    elif tipo_grafico in ["Corridas aceitas", "Corridas rejeitadas"]:
        st.caption("ℹ️ A porcentagem mostrada é **sobre ofertadas**.")

    por_dia = (
        df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                    .groupby("dia", as_index=False)[col].sum()
                    .sort_values("dia")
    )
    fig_dia = px.line(
        por_dia, x="dia", y=col,
        title=f"📈 {label} por dia (mês atual)",
        labels={"dia": "Dia", col: label},
        template="plotly_dark"
    )
    fig_dia.update_traces(line_shape="spline", mode="lines+markers")
    total_mes = int(por_dia[col].sum())
    st.metric(f"🚗 {label} no mês", total_mes)
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
    entregador = st.selectbox("🔎 Selecione o entregador:", [None] + entregadores_lista,
                              format_func=lambda x: "" if x is None else x)

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
            dias_escolhidos if len(dias_escolhidos) else dias_opcoes,
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

# -------------------------------------------------------------------
# UTR — PONDERADA no ABSOLUTO (dia e mês)
# -------------------------------------------------------------------
if modo == "UTR":
    st.header("🧭 UTR – Corridas ofertadas por hora (ponderada no absoluto)")

    col1, col2 = st.columns(2)
    mes_sel = col1.selectbox("Mês", list(range(1, 13)))
    ano_sel = col2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

    base_full = utr_por_entregador_turno(df, mes_sel, ano_sel)
    if base_full.empty:
        st.info("Nenhum dado encontrado para o período selecionado.")
        st.stop()

    if "supply_hours" in base_full.columns:
        base_full["tempo_hms"] = base_full["supply_hours"].apply(_hms_from_hours)

    turnos_opts = ["Todos os turnos"]
    if "periodo" in base_full.columns:
        turnos_opts += sorted([t for t in base_full["periodo"].dropna().unique()])
    turno_sel = st.selectbox("Turno", options=turnos_opts, index=0)

    base_plot = base_full if turno_sel == "Todos os turnos" else base_full[base_full["periodo"] == turno_sel]
    if base_plot.empty:
        st.info("Sem dados para o turno selecionado.")
        st.stop()

    # --- DIÁRIO PONDERADO (ofertadas do dia ÷ horas do dia, ambas no absoluto) ---
    base_plot["data"] = pd.to_datetime(base_plot["data"])
    serie = (
        base_plot
          .assign(dia_num=lambda d: d["data"].dt.day)
          .groupby("dia_num", as_index=False)
          .agg(ofertadas=("corridas_ofertadas", "sum"),
               horas=("supply_hours", "sum"))
    )
    serie["utr_media"] = serie.apply(
        lambda r: (r["ofertadas"] / r["horas"]) if r["horas"] > 0 else 0.0,
        axis=1
    )
    serie = serie[["dia_num", "utr_media"]].sort_values("dia_num")

    y_max = (serie["utr_media"].max() or 0) * 1.25

    fig = px.bar(
        serie,
        x="dia_num",
        y="utr_media",
        text="utr_media",
        title=f"UTR por dia – {mes_sel:02d}/{ano_sel} • {('Todos os turnos' if turno_sel=='Todos os turnos' else turno_sel)}",
        labels={"dia_num": "Dia do mês", "utr_media": "UTR (ofertadas/hora)"},
        template="plotly_dark",
        color_discrete_sequence=["#00BFFF"],
    )
    fig.update_traces(
        texttemplate="<b>%{text:.2f}</b>",
        textposition="outside",
        textfont=dict(size=18, color="white"),
        marker_line_color="rgba(255,255,255,0.25)",
        marker_line_width=0.5,
    )
    fig.update_xaxes(
        tickmode="linear", dtick=1, tick0=1,
        tickfont=dict(size=14),
        showgrid=False, showline=True, linewidth=1, linecolor="rgba(255,255,255,0.2)"
    )
    fig.update_yaxes(
        range=[0, max(y_max, 1)],
        showgrid=True, gridcolor="gray", rangemode="tozero",
        tickfont=dict(size=14)
    )
    fig.update_layout(
        bargap=0.25,
        uniformtext_minsize=14, uniformtext_mode="show",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        title_font=dict(size=22),
        showlegend=False,
        margin=dict(t=70, r=20, b=60, l=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ✅ MÉTRICA DO MÊS PONDERADA (absoluto) COERENTE COM A TELA INICIAL
    ofertadas_totais = base_plot["corridas_ofertadas"].sum()
    horas_totais     = base_plot["supply_hours"].sum()
    utr_mes          = (ofertadas_totais / horas_totais) if horas_totais > 0 else 0.0
    st.metric("Média UTR no mês (ponderada)", f"{utr_mes:.2f}")

    st.caption("📄 O botão abaixo baixa o **CSV GERAL** (sem filtro de turno).")
    cols_csv = ["data","pessoa_entregadora","periodo","tempo_hms","corridas_ofertadas","UTR"]
    base_csv = base_full.copy()
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

# -------------------------------------------------------------------
# Relação de Entregadores (listar por filtros)
# -------------------------------------------------------------------
if modo == "Relação de Entregadores":
    st.header("Relatório")

    df_filtros = df.copy()
    df_filtros["data_do_periodo"] = pd.to_datetime(df_filtros["data_do_periodo"], errors="coerce")
    df_filtros["data"] = df_filtros["data_do_periodo"].dt.date

    subpracas = sorted([x for x in df_filtros["sub_praca"].dropna().unique()])
    filtro_subpraca = st.multiselect("Filtrar por subpraça:", subpracas)

    turnos = sorted([x for x in df_filtros["periodo"].dropna().unique()])
    filtro_turno = st.multiselect("Filtrar por turno:", turnos)

    tipo_periodo = st.radio("Como deseja escolher as datas?", ("Período contínuo", "Dias específicos"))
    dias_escolhidos = []

    if tipo_periodo == "Período contínuo":
        data_min = df_filtros["data"].min()
        data_max = df_filtros["data"].max()
        periodo = st.date_input("Selecione o intervalo de datas:", [data_min, data_max], format="DD/MM/YYYY")
        if len(periodo) == 2:
            dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
        elif len(periodo) == 1:
            dias_escolhidos = [periodo[0]]
    else:
        dias_opcoes = sorted(df_filtros["data"].unique())
        dias_escolhidos = st.multiselect(
            "Selecione os dias desejados:",
            dias_opcoes,
            format_func=lambda x: x.strftime("%d/%m/%Y")
        )

    gerar = st.button("Gerar")

    if gerar:
        df_sel = df_filtros.copy()
        if filtro_subpraca:
            df_sel = df_sel[df_sel["sub_praca"].isin(filtro_subpraca)]
        if filtro_turno:
            df_sel = df_sel[df_sel["periodo"].isin(filtro_turno)]
        if dias_escolhidos:
            df_sel = df_sel[df_sel["data"].isin(dias_escolhidos)]

        if df_sel.empty:
            st.info("❌ Nenhum entregador encontrado com os filtros aplicados.")
            st.stop()

        nomes_filtrados = sorted(df_sel["pessoa_entregadora"].dropna().unique())

        st.subheader("👤 Entregadores encontrados")
        st.dataframe(pd.DataFrame({"pessoa_entregadora": nomes_filtrados}), use_container_width=True)

        from relatorios import gerar_dados
        st.subheader("Números")
        blocos = []
        for nome in nomes_filtrados:
            chunk = df_sel[df_sel["pessoa_entregadora"] == nome]
            bloco = gerar_dados(nome, None, None, chunk)
            if bloco:
                blocos.append(bloco.strip())

        texto_final = "\n" + ("\n" + "—" * 40 + "\n").join(blocos) if blocos else "Sem blocos gerados para os filtros."
        st.text_area("Resultado:", value=texto_final, height=500)

# ================================
# 🏠 TELA INICIAL
# ================================
if modo == "Início":
    st.title("📋 Painel de Entregadores")

    # Logo de fundo por nível
    nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")
    logo_admin = st.secrets.get("LOGO_ADMIN_URL", "")
    logo_user  = st.secrets.get("LOGO_USER_URL", "")
    bg_logo = logo_admin if nivel == "admin" and logo_admin else logo_user

    if bg_logo:
        st.markdown(
            f"""
            <style>
              .home-bg {{
                position: relative;
                overflow: hidden;
              }}
              .home-bg:before {{
                content: "";
                position: absolute;
                inset: 0;
                background-image: url('{bg_logo}');
                background-repeat: no-repeat;
                background-position: center 20%;
                background-size: 40%;
                opacity: 0.06;
                pointer-events: none;
              }}
            </style>
            """,
            unsafe_allow_html=True
        )
    st.markdown("<div class='home-bg'>", unsafe_allow_html=True)

    # Último dia com dados
    try:
        ultimo_dia = pd.to_datetime(df["data"]).max().date()
        ultimo_dia_txt = ultimo_dia.strftime("%d/%m/%Y")
    except Exception:
        ultimo_dia_txt = "—"

    # Card Atualizar dados
    with st.container():
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("🗓️ Último dia com dados")
            st.metric(label="Data mais recente", value=ultimo_dia_txt)
        with c2:
            st.subheader("🔄 Atualização de base")
            st.caption("Este botão só aparece na tela inicial.")
            if st.button("Atualizar dados agora", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    st.divider()

    # Resumo do mês atual
    hoje = pd.Timestamp.today()
    mes_atual, ano_atual = int(hoje.month), int(hoje.year)
    df_mes = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)].copy()

    ofertadas = int(df_mes.get("numero_de_corridas_ofertadas", 0).sum())
    aceitas   = int(df_mes.get("numero_de_corridas_aceitas", 0).sum())
    rejeitadas= int(df_mes.get("numero_de_corridas_rejeitadas", 0).sum())
    entreg_uniq = int(df_mes.get("pessoa_entregadora", pd.Series(dtype=object)).dropna().nunique())

    acc_pct  = round((aceitas / ofertadas) * 100, 1) if ofertadas > 0 else 0.0
    rej_pct  = round((rejeitadas / ofertadas) * 100, 1) if ofertadas > 0 else 0.0

    # ✅ UTR do mês (ofertadas por hora, absoluto) — cacheada
    utr_mes = round(_utr_mensal_cached(df_key, mes_atual, ano_atual, None), 2)

    st.subheader(f"📦 Resumo do mês atual ({mes_atual:02d}/{ano_atual})")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Corridas ofertadas (UTR)", f"{ofertadas:,}".replace(",", "."), help="Total de corridas ofertadas no mês. UTR ao lado.")
        st.caption(f"UTR (ponderada): **{utr_mes:.2f}**")
    with m2:
        st.metric("Corridas aceitas", f"{aceitas:,}".replace(",", "."), f"{acc_pct:.1f}%", help="% sobre ofertadas")
    with m3:
        st.metric("Rejeições", f"{rejeitadas:,}".replace(",", "."), f"{rej_pct:.1f}%", help="% sobre ofertadas")
    with m4:
        st.metric("Entregadores ativos", f"{entreg_uniq}", help="Quantidade de pessoas diferentes que atuaram no mês")

    st.markdown("</div>", unsafe_allow_html=True)

