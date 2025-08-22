import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from utils import tempo_para_segundos  

from relatorios import (
    gerar_dados,
    gerar_simplicado,
    gerar_alertas_de_faltas,
    get_entregadores,
    classificar_entregadores,
    utr_por_entregador_turno,
    utr_pivot_por_entregador,
    _horas_from_abs,
    utr_por_entregador_turno

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
# -------------------------------------------------------------------
# Indicadores Gerais
# -------------------------------------------------------------------
if modo == "📊 Indicadores Gerais":
    st.subheader("🔎 Escolha o indicador que deseja visualizar:")

    tipo_grafico = st.radio(
        "Tipo de gráfico:",
        ["Corridas ofertadas", "Corridas aceitas", "Corridas rejeitadas", "Corridas completadas"],
        index=0, horizontal=True
    )

    # ----- Agregação mensal (contagens) -----
    agg_counts = (
        df.groupby("mes_ano")
          .agg(
              ofertadas=("numero_de_corridas_ofertadas", "sum"),
              aceitas=("numero_de_corridas_aceitas", "sum"),
              rejeitadas=("numero_de_corridas_rejeitadas", "sum"),
              completas=("numero_de_corridas_completadas", "sum"),
          )
    ).reset_index()

    # Horas (se quiser manter para outras análises)
    horas = (
        df.groupby("mes_ano")
          .apply(lambda g: _horas_from_abs(g))
          .rename("horas")
          .reset_index()
    )

    agregado = agg_counts.merge(horas, on="mes_ano", how="left").fillna({"horas": 0.0})
    agregado["mes_label"] = agregado["mes_ano"].dt.strftime("%b/%y")

    # ===== UTR mensal com a MESMA lógica da tela UTR =====
    # (média dos UTR diários, considerando todos os turnos e todos os entregadores)
    def utr_mensal_mesma_logica(df_all, ts):
        mes = int(ts.month)
        ano = int(ts.year)
        base = utr_por_entregador_turno(df_all, mes, ano)  # mesma função da tela UTR
        if base.empty:
            return 0.0
        # média diária: média de UTR por dia e depois média dessas médias
        # (equivalente ao que a tela UTR faz)
        # base['data'] já vem como date; garantimos datetime só por segurança:
        try:
            d = pd.to_datetime(base["data"])
        except Exception:
            d = pd.to_datetime(base["data"].astype(str), errors="coerce")
        base = base.copy()
        base["__d__"] = d.dt.date
        daily_mean = base.groupby("__d__")["UTR"].mean()
        return float(daily_mean.mean()) if not daily_mean.empty else 0.0

    agregado["utr_mes_v2"] = agregado["mes_ano"].apply(lambda ts: round(utr_mensal_mesma_logica(df, ts), 2))

    # % com proteções contra zero
    ofertadas_safe = agregado["ofertadas"].replace(0, pd.NA)
    aceitas_safe   = agregado["aceitas"].replace(0, pd.NA)

    agregado["acc_pct"]  = (agregado["aceitas"]    / ofertadas_safe * 100).round(1)
    agregado["rej_pct"]  = (agregado["rejeitadas"] / ofertadas_safe * 100).round(1)
    agregado["comp_pct"] = (agregado["completas"]  / aceitas_safe   * 100).round(1)

    # Seleção de métrica e rótulo do topo
    if tipo_grafico == "Corridas ofertadas":
        y_col = "ofertadas"
        text_col = "utr_mes_v2"     # UTR mensal (MESMA lógica da tela UTR)
        text_fmt = "<b>%{text:.2f}</b>"
        titulo = "Corridas ofertadas por mês"
        subtitulo = "Rótulo = UTR mensal (média dos UTR diários)"
    elif tipo_grafico == "Corridas aceitas":
        y_col = "aceitas"
        text_col = "acc_pct"
        text_fmt = "<b>%{text:.1f}%</b>"
        titulo = "Corridas aceitas por mês"
        subtitulo = "Rótulo = % de aceitação (aceitas ÷ ofertadas)"
    elif tipo_grafico == "Corridas rejeitadas":
        y_col = "rejeitadas"
        text_col = "rej_pct"
        text_fmt = "<b>%{text:.1f}%</b>"
        titulo = "Corridas rejeitadas por mês"
        subtitulo = "Rótulo = % de rejeição (rejeitadas ÷ ofertadas)"
    else:  # "Corridas completadas"
        y_col = "completas"
        text_col = "comp_pct"
        text_fmt = "<b>%{text:.1f}%</b>"
        titulo = "Corridas completadas por mês"
        subtitulo = "Rótulo = % de conclusão (completas ÷ aceitas)"

    agregado[text_col] = agregado[text_col].fillna(0)

    # ---- Gráfico (clean, dark, label fora) ----
    fig = px.bar(
        agregado,
        x="mes_label",
        y=y_col,
        text=text_col,
        title=titulo,
        labels={y_col: y_col.capitalize(), "mes_label": "Mês/Ano"},
        template="plotly_dark",
        color_discrete_sequence=["#00BFFF"],
    )
    fig.update_traces(
        texttemplate=text_fmt,
        textposition="outside",
        textfont=dict(size=16, color="white"),
        marker_line_color="rgba(255,255,255,0.25)",
        marker_line_width=0.5,
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        title_font=dict(size=22),
        xaxis=dict(showgrid=False, tickfont=dict(size=14)),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.15)", tickfont=dict(size=14)),
        bargap=0.25,
        margin=dict(t=70, r=20, b=60, l=60),
        showlegend=False,
    )

    st.caption(f"💡 {subtitulo}")
    st.plotly_chart(fig, use_container_width=True)

    # ---- Série diária (mês atual) segue igual ----
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

    # ---- Horas Realizadas (mês atual) ---------------------------------
    # Soma diária do tempo_disponivel_absoluto (HH:MM:SS) -> segundos -> horas
    df_mes_horas = df_mes[df_mes["tempo_disponivel_absoluto"].notna()].copy()
    if not df_mes_horas.empty:
        # to_timedelta é veloz e robusto para HH:MM:SS
        df_mes_horas["segundos_abs"] = pd.to_timedelta(
            df_mes_horas["tempo_disponivel_absoluto"]
        ).dt.total_seconds()

        horas_por_dia = (
            df_mes_horas.groupby(df_mes_horas["data"].dt.day, as_index=False)["segundos_abs"]
            .sum()
            .rename(columns={"data": "dia", "segundos_abs": "segundos"})
        )
        horas_por_dia["horas_float"] = (horas_por_dia["segundos"] / 3600.0)
        # rótulo bonitinho no ponto: exibe em HH:MM:SS
        horas_por_dia["hms"] = horas_por_dia["horas_float"].apply(_hms_from_hours)

        # Gráfico em linha/área (onda)
        fig_horas = px.area(
            horas_por_dia,
            x="dia",
            y="horas_float",
            title="⏱️ Horas Realizadas por dia (mês atual)",
            labels={"dia": "Dia", "horas_float": "Horas"},
            template="plotly_dark",
        )
        fig_horas.update_traces(
            mode="lines+markers",
            marker=dict(size=6, line=dict(width=0)),
            line_shape="spline",
            # mostra o rótulo HH:MM:SS no topo de cada ponto
            text=horas_por_dia["hms"],
            textposition="top center",
            textfont=dict(size=12),
        )
        fig_horas.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
            title_font=dict(size=22),
            xaxis=dict(showgrid=False, tickmode="linear", dtick=1),
            yaxis=dict(
                title="Horas",
                showgrid=True,
                gridcolor="rgba(255,255,255,0.15)",
                rangemode="tozero",
            ),
            margin=dict(t=70, r=20, b=60, l=60),
        )

        total_seg_mes = int(horas_por_dia["segundos"].sum())
        total_horas_mes = total_seg_mes / 3600.0  # float, para converter pra HH:MM:SS
        st.metric("⏱️ Horas Realizadas no mês", _hms_from_hours(total_horas_mes))
        st.plotly_chart(fig_horas, use_container_width=True)
    else:
        st.info("Sem dados de tempo disponível absoluto para o mês atual.")


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
# UTR — Barras limpas (1 cor), números grandes e dia embaixo de cada barra
# -------------------------------------------------------------------
if modo == "UTR":
    st.header("🧭 UTR – Corridas ofertadas por hora (média diária)")

    # --- Período (mês/ano) ---
    col1, col2 = st.columns(2)
    mes_sel = col1.selectbox("Mês", list(range(1, 13)))
    ano_sel = col2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

    # Base completa (para gráfico e CSV geral)
    base_full = utr_por_entregador_turno(df, mes_sel, ano_sel)
    if base_full.empty:
        st.info("Nenhum dado encontrado para o período selecionado.")
        st.stop()

    if "supply_hours" in base_full.columns:
        base_full["tempo_hms"] = base_full["supply_hours"].apply(_hms_from_hours)

    # --- Turno (limpo) ---
    turnos_opts = ["Todos os turnos"]
    if "periodo" in base_full.columns:
        turnos_opts += sorted([t for t in base_full["periodo"].dropna().unique()])
    turno_sel = st.selectbox("Turno", options=turnos_opts, index=0)

    # Filtra só para o gráfico
    base_plot = base_full if turno_sel == "Todos os turnos" else base_full[base_full["periodo"] == turno_sel]
    if base_plot.empty:
        st.info("Sem dados para o turno selecionado.")
        st.stop()

    # Série: média UTR por dia
    base_plot["data"] = pd.to_datetime(base_plot["data"])
    serie = (
        base_plot.groupby(base_plot["data"].dt.day)["UTR"]
        .mean()
        .reset_index()
        .rename(columns={"data": "dia_num", "UTR": "utr_media"})
    )
    serie.columns = ["dia_num", "utr_media"]
    serie = serie.sort_values("dia_num")
    y_max = (serie["utr_media"].max() or 0) * 1.25  # espaço para labels fora da barra

    # ======= Gráfico de barras (1 cor) =======
    import plotly.express as px
    titulo_turno = turno_sel if turno_sel != "Todos os turnos" else "Todos os turnos"
    fig = px.bar(
        serie,
        x="dia_num",
        y="utr_media",
        text="utr_media",
        title=f"UTR médio por dia – {mes_sel:02d}/{ano_sel} • {titulo_turno}",
        labels={"dia_num": "Dia do mês", "utr_media": "UTR médio"},
        template="plotly_dark",
        color_discrete_sequence=["#00BFFF"],  # 1 cor só
    )

    # Números grandes/visíveis
    fig.update_traces(
        texttemplate="<b>%{text:.2f}</b>",
        textposition="outside",
        textfont=dict(size=18, color="white"),
        marker_line_color="rgba(255,255,255,0.25)",
        marker_line_width=0.5,
    )

    # Eixo X com todos os dias visíveis (1,2,3,...)
    fig.update_xaxes(
        tickmode="linear", dtick=1, tick0=1,
        tickfont=dict(size=14),
        showgrid=False, showline=True, linewidth=1, linecolor="rgba(255,255,255,0.2)"
    )

    # Y com espaço pra label e sem cortar topo
    fig.update_yaxes(
        range=[0, max(y_max, 1)],  # evita range muito baixo
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

    # ======= Métrica única =======
    st.metric("Média UTR no mês", f"{serie['utr_media'].mean():.2f}")

    # ======= CSV GERAL (ignora filtro de turno) =======
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

