# main.py

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import unicodedata

from utils import tempo_para_segundos  # fallback (se precisar)

from relatorios import (
    gerar_dados,
    gerar_simplicado,
    gerar_alertas_de_faltas,
    get_entregadores,
    classificar_entregadores,
    utr_por_entregador_turno,
    utr_pivot_por_entregador,
    _horas_from_abs
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


# ========= HELPERS P/ UTR =========

def _is_medias(texto: str) -> bool:
    """Retorna True quando o usuário escolhe 'Médias' (robusto a acento/variação)."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode().lower().strip()
    return t.startswith("med")  # 'Médias', 'Medias', etc.

def _is_absoluto(texto: str) -> bool:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode().lower().strip()
    return t.startswith("abso")  # 'Absoluto'


def _utr_media_das_medias(rows: pd.DataFrame) -> float:
    """
    'Médias': média aritmética dos UTRs linha-a-linha (pessoa/turno/dia).
    Não pondera por horas.
    """
    if rows.empty:
        return 0.0
    base = rows[rows["supply_hours"] > 0].copy()
    if base.empty:
        return 0.0
    return (base["corridas_ofertadas"] / base["supply_hours"]).mean()


def _serie_diaria_utr(base_plot: pd.DataFrame, metodo: str) -> pd.DataFrame:
    """
    Série diária de UTR:
      - Absoluto: (ofertadas no dia) / (horas no dia)  [ponderada por hora]
      - Médias:   média aritmética dos UTRs dos entregadores no dia
    Retorna ['dia_num','utr_val'].
    """
    if base_plot.empty:
        return pd.DataFrame(columns=["dia_num", "utr_val"])

    df_d = base_plot.copy()
    df_d["data"] = pd.to_datetime(df_d["data"])
    df_d["dia_num"] = df_d["data"].dt.day

    if _is_medias(metodo):
        df_d = df_d[df_d["supply_hours"] > 0].copy()
        if df_d.empty:
            return pd.DataFrame(columns=["dia_num", "utr_val"])
        df_d["utr_linha"] = df_d["corridas_ofertadas"] / df_d["supply_hours"]
        out = df_d.groupby("dia_num", as_index=False)["utr_linha"].mean()
        return out.rename(columns={"utr_linha": "utr_val"}).sort_values("dia_num")

    # Absoluto (ponderada por hora)
    agg = (df_d.groupby("dia_num", as_index=False)
                 .agg(ofertadas=("corridas_ofertadas", "sum"),
                      horas=("supply_hours", "sum")))
    agg["utr_val"] = agg.apply(
        lambda r: (r["ofertadas"] / r["horas"]) if r["horas"] > 0 else 0.0, axis=1
    )
    return agg[["dia_num", "utr_val"]].sort_values("dia_num")


def _utr_mensal_media_das_medias(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula, pra CADA mês, a 'Médias' de UTR.
    1) Agrupa no nível (pessoa, periodo, data) somando ofertadas e segundos.
    2) Calcula UTR linha-a-linha (ofertadas/horas).
    3) Tira a média ARITMÉTICA por mês (mes_ano).
    Retorna: ['mes_ano','utr_mmm']
    """
    if df.empty:
        return pd.DataFrame(columns=["mes_ano", "utr_mmm"])

    dados = df.copy()
    if "periodo" not in dados.columns:
        dados = dados.assign(periodo="(sem turno)")

    g = (
        dados
        .groupby(["pessoa_entregadora", "periodo", "data"], dropna=False)
        .agg(
            ofertadas=("numero_de_corridas_ofertadas", "sum"),
            segundos=("segundos_abs", "sum")
        )
        .reset_index()
    )
    g["horas"] = g["segundos"] / 3600.0
    g = g[g["horas"] > 0]
    if g.empty:
        return pd.DataFrame(columns=["mes_ano", "utr_mmm"])

    g["UTR"] = g["ofertadas"] / g["horas"]
    g["data"] = pd.to_datetime(g["data"], errors="coerce")
    g["mes_ano"] = g["data"].dt.to_period("M").dt.to_timestamp()

    out = g.groupby("mes_ano", as_index=False)["UTR"].mean().rename(columns={"UTR": "utr_mmm"})
    return out


# =========================================================
# 🔄 Carga ÚNICA do DF por render + suporte a hard refresh
# =========================================================
def get_df_once():
    """
    Carrega o df uma única vez por render.
    Se o usuário clicou em 'Atualizar dados', força baixar do Drive.
    """
    prefer = st.session_state.pop("force_refresh", False)
    ts = pd.Timestamp.now().timestamp() if prefer else None
    return carregar_dados(prefer_drive=prefer, _ts=ts)


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
        "Relatórios Subpraças",
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
    st.markdown("Navegação")

    if st.button("Início", use_container_width=True):
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
# Dados (carga única por render)
# -------------------------------------------------------------------
df = get_df_once()

@st.cache_data
def _utr_mensal_cached(df_key, mes: int, ano: int, turno: str | None):
    """
    UTR mensal em 'Absoluto' (ponderada) = ofertadas_totais / horas_totais,
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


# Feedback pós-refresh (opcional)
if st.session_state.pop("just_refreshed", False):
    st.success("✅ Base atualizada a partir do Google Drive.")

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

    # --- Horas realizadas
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

    # --- Demais gráficos (com tratamento especial para Corridas ofertadas)
    if tipo_grafico == "Corridas ofertadas":
        metodo_utr = st.radio(
            "Método",
            ["Absoluto", "Médias"],
            horizontal=True,
            index=0,
            help="Absoluto = soma de ofertadas ÷ soma de horas. Médias = média simples dos UTRs por entregador/dia."
        )

        mensal = df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum()
        mensal["mes_rotulo"] = mensal["mes_ano"].dt.strftime("%b/%y")

        if _is_absoluto(metodo_utr):
            mensal = mensal.merge(horas_mensais, on="mes_ano", how="left")
            mensal["UTR_calc"] = mensal.apply(
                lambda r: (float(r["numero_de_corridas_ofertadas"]) / float(r["horas"]))
                if (pd.notna(r["horas"]) and float(r["horas"]) > 0) else 0.0,
                axis=1
            )
        else:
            utr_mmm = _utr_mensal_media_das_medias(df)  # ['mes_ano','utr_mmm']
            mensal = mensal.merge(utr_mmm, on="mes_ano", how="left")
            mensal["UTR_calc"] = mensal["utr_mmm"].fillna(0.0)

        mensal["__label_text__"] = mensal.apply(
            lambda r: f"{int(r['numero_de_corridas_ofertadas'])}\nUTR {float(r['UTR_calc']):.2f}",
            axis=1
        )

        fig = px.bar(
            mensal,
            x="mes_rotulo",
            y="numero_de_corridas_ofertadas",
            text="__label_text__",
            title=f"Corridas ofertadas por mês • {metodo_utr}",
            labels={"numero_de_corridas_ofertadas": "Corridas", "mes_rotulo": "Mês/Ano"},
            template="plotly_dark",
            color_discrete_sequence=["#00BFFF"]
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
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.15)"),
            bargap=0.25, margin=dict(t=80, r=20, b=60, l=60), showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        # diário (quantidade de ofertadas no mês atual)
        por_dia = (
            df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                        .groupby("dia", as_index=False)["numero_de_corridas_ofertadas"].sum()
                        .sort_values("dia")
        )
        fig_dia = px.line(
            por_dia, x="dia", y="numero_de_corridas_ofertadas",
            title="📈 Corridas ofertadas por dia (mês atual)",
            labels={"dia": "Dia", "numero_de_corridas_ofertadas": "Corridas"},
            template="plotly_dark"
        )
        fig_dia.update_traces(line_shape="spline", mode="lines+markers")
        total_mes = int(por_dia["numero_de_corridas_ofertadas"].sum())
        st.metric("🚗 Corridas ofertadas no mês", total_mes)
        st.plotly_chart(fig_dia, use_container_width=True)

        st.stop()

    # --- Genérico para aceitas / rejeitadas / completadas (com % no rótulo)
    coluna_map = {
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

    # diário do mês atual (quantidade)
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
# UTR — ABSOLUTO e MÉDIAS
# -------------------------------------------------------------------
# -------------------------------------------------------------------
# UTR — ABSOLUTO e MÉDIAS (com filtro de Subpraça)
# -------------------------------------------------------------------
if modo == "UTR":
    st.header("🧭 UTR – Corridas ofertadas por hora")

    col1, col2 = st.columns(2)
    mes_sel = col1.selectbox("Mês", list(range(1, 13)))
    ano_sel = col2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

    # 🔎 Subpraça (opcional)
    # lista de subpraças relevantes para o recorte mês/ano (se tiver)
    df_mm = df[(df["mes"] == mes_sel) & (df["ano"] == ano_sel)]
    if "sub_praca" in df.columns:
        subpracas_opts = sorted([x for x in df_mm.get("sub_praca", pd.Series(dtype=object)).dropna().unique()])
        subpraca_sel = st.multiselect("Filtrar por subpraça (opcional):", subpracas_opts)
    else:
        subpraca_sel = []

    # aplica filtro de subpraça ANTES de montar a base do UTR
    df_base = df.copy()
    if subpraca_sel:
        if "sub_praca" not in df_base.columns:
            st.warning("⚠️ Coluna 'sub_praca' não encontrada na base.")
        else:
            df_base = df_base[df_base["sub_praca"].isin(subpraca_sel)]

    # monta base UTR já com filtros aplicados
    base_full = utr_por_entregador_turno(df_base, mes_sel, ano_sel)
    if base_full.empty:
        st.info("Nenhum dado encontrado para o período e filtros selecionados.")
        st.stop()

    if "supply_hours" in base_full.columns:
        base_full["tempo_hms"] = base_full["supply_hours"].apply(_hms_from_hours)

    # Turno
    turnos_opts = ["Todos os turnos"]
    if "periodo" in base_full.columns:
        turnos_opts += sorted([t for t in base_full["periodo"].dropna().unique()])
    turno_sel = st.selectbox("Turno", options=turnos_opts, index=0)

    # Método (Absoluto x Médias)
    metodo = st.radio(
        "Método",
        ["Absoluto", "Médias"],
        horizontal=True,
        index=0,
        help="Absoluto = soma de ofertadas ÷ soma de horas. Médias = média simples dos UTRs por entregador/dia."
    )

    # aplica filtro de turno para o gráfico diário
    base_plot = base_full if turno_sel == "Todos os turnos" else base_full[base_full["periodo"] == turno_sel]
    if base_plot.empty:
        st.info("Sem dados para o turno selecionado dentro dos filtros.")
        st.stop()

    # Série diária conforme método (ponderado x média simples)
    serie = _serie_diaria_utr(base_plot, metodo)
    y_max = float(serie["utr_val"].max()) * 1.25 if not serie.empty else 1.0

    # monta sufixo do título com subpraças (se houver filtro)
    sub_sufixo = ""
    if subpraca_sel:
        sub_sufixo = " • Subpraça: " + (", ".join(subpraca_sel) if len(subpraca_sel) <= 3 else f"{len(subpraca_sel)} selecionadas")

    fig = px.bar(
        serie,
        x="dia_num",
        y="utr_val",
        text="utr_val",
        title=(
            f"UTR por dia – {mes_sel:02d}/{ano_sel} • "
            f"{('Todos os turnos' if turno_sel=='Todos os turnos' else turno_sel)} • {metodo}{sub_sufixo}"
        ),
        labels={"dia_num": "Dia do mês", "utr_val": "UTR (ofertadas/hora)"},
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

    # ✅ Métrica do mês conforme método (respeitando subpraça + turno)
    if _is_absoluto(metodo):
        ofertadas_totais = base_plot["corridas_ofertadas"].sum()
        horas_totais     = base_plot["supply_hours"].sum()
        utr_mes          = (ofertadas_totais / horas_totais) if horas_totais > 0 else 0.0
    else:
        utr_mes = _utr_media_das_medias(base_plot)

    st.metric(f"Média UTR no mês ({metodo.lower()})", f"{utr_mes:.2f}")

    # 📄 Export: sempre no detalhado (sem filtrar turno), mas já com subpraça aplicada
    st.caption("📄 O botão abaixo baixa o **CSV GERAL** (sem filtro de turno), respeitando os filtros de subpraça.")
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

    file_name = f"utr_entregador_turno_diario_{mes_sel:02d}_{ano_sel}"
    if subpraca_sel:
        # evita nomes gigantes: concatena primeiras e quantidade total
        tag = "_".join([s.replace(" ", "") for s in subpraca_sel[:2]])
        if len(subpraca_sel) > 2:
            tag += f"_e{len(subpraca_sel)-2}mais"
        file_name += f"_{tag}"

    csv_bin = base_csv[cols_csv].to_csv(index=False, decimal=",").encode("utf-8")
    st.download_button(
        "⬇️ Baixar CSV (GERAL)",
        data=csv_bin,
        file_name=f"{file_name}.csv",
        mime="text/csv",
        help="Exporta o CSV geral do mês/ano com os filtros aplicados (subpraça), ignorando o filtro de turno."
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
            st.subheader("Dados mais recentes")
            st.metric(label="", value=ultimo_dia_txt)
        with c2:
            st.subheader("Atualização de base")
            if st.button("Atualizar dados", use_container_width=True, key="btn_refresh_drive"):
                st.session_state.force_refresh = True
                st.session_state.just_refreshed = True
                st.cache_data.clear()
                st.rerun()

    st.divider()

    # Resumo do mês atual
    hoje = pd.Timestamp.today()
    mes_atual, ano_atual = int(hoje.month), int(hoje.year)
    df_mes = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)].copy()

    ofertadas  = int(df_mes.get("numero_de_corridas_ofertadas", 0).sum())
    aceitas    = int(df_mes.get("numero_de_corridas_aceitas", 0).sum())
    rejeitadas = int(df_mes.get("numero_de_corridas_rejeitadas", 0).sum())
    entreg_uniq = int(df_mes.get("pessoa_entregadora", pd.Series(dtype=object)).dropna().nunique())

    acc_pct = round((aceitas / ofertadas) * 100, 1) if ofertadas > 0 else 0.0
    rej_pct = round((rejeitadas / ofertadas) * 100, 1) if ofertadas > 0 else 0.0

    # UTR do mês (Absoluto) — cacheada
    utr_mes = round(_utr_mensal_cached(df_key, mes_atual, ano_atual, None), 2)

    # UTR do mês — Médias (não ponderada)
    base_home = utr_por_entregador_turno(df, mes_atual, ano_atual)
    utr_medias = round(_utr_media_das_medias(base_home), 2)

    st.subheader(f"📦 Resumo do mês atual ({mes_atual:02d}/{ano_atual})")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Ofertadas - UTR", f"{ofertadas:,}".replace(",", "."))
        st.caption(f"Absoluto: **{utr_mes:.2f}**")
        st.caption(f"Médias: **{utr_medias:.2f}**")
    with m2:
        st.metric("Aceitas", f"{aceitas:,}".replace(",", "."), f"{acc_pct:.1f}%")
    with m3:
        st.metric("Rejeitadas", f"{rejeitadas:,}".replace(",", "."), f"{rej_pct:.1f}%")
    with m4:
        st.metric("Entregadores ativos", f"{entreg_uniq}")

    # ----------------------------------------------------
    # Curiosidade do ano (separado dos cards mensais)
    # ----------------------------------------------------
    st.divider()
    st.subheader("🎲 Curiosidade")

    ano_atual = pd.Timestamp.today().year
    total_corridas_ano = int(df[df["ano"] == ano_atual]["numero_de_corridas_completadas"].sum())

    st.metric("🏁 Total de corridas completadas no ano", f"{total_corridas_ano:,}".replace(",", "."))

    st.markdown("</div>", unsafe_allow_html=True)


#SUBPRAÇA

if modo == "Relatórios Subpraças":
    st.header("Relatórios por região")

    # ===== Verificações de colunas obrigatórias =====
    obrig = ["sub_praca", "periodo", "data", "numero_de_corridas_ofertadas",
             "numero_de_corridas_aceitas", "numero_de_corridas_rejeitadas",
             "numero_de_corridas_completadas", "pessoa_entregadora"]
    faltando = [c for c in obrig if c not in df.columns]
    if faltando:
        st.error("Colunas ausentes no dataset: " + ", ".join(faltando))
        st.stop()

    # ===== Filtros =====
    subpracas = sorted(df["sub_praca"].dropna().unique())
    sub_sel = st.selectbox("Selecione a subpraça:", subpracas)

    turnos = sorted(df["periodo"].dropna().unique())
    turnos_sel = st.multiselect("Filtrar por turnos:", turnos)

    # ===== Base filtrada =====
    df_area = df[df["sub_praca"] == sub_sel].copy()
    if turnos_sel:
        df_area = df_area[df_area["periodo"].isin(turnos_sel)]

    # --- Período (contínuo ou dias específicos), mesmo padrão do resto ---
    # garante colunas de data bem formadas
    df_area["data_do_periodo"] = pd.to_datetime(df_area.get("data_do_periodo", df_area.get("data")), errors="coerce")
    df_area["data"] = df_area["data_do_periodo"].dt.date

    tipo_periodo = st.radio("Como deseja escolher as datas?", ("Período contínuo", "Dias específicos"), horizontal=True)
    dias_escolhidos = []

    if tipo_periodo == "Período contínuo":
        data_min = df_area["data"].min()
        data_max = df_area["data"].max()
        periodo = st.date_input("Selecione o intervalo de datas:", [data_min, data_max], format="DD/MM/YYYY")
        if len(periodo) == 2:
            dias_escolhidos = list(pd.date_range(start=periodo[0], end=periodo[1]).date)
        elif len(periodo) == 1:
            dias_escolhidos = [periodo[0]]
    else:
        dias_opcoes = sorted([d for d in df_area["data"].dropna().unique()])
        dias_escolhidos = st.multiselect(
            "Selecione os dias desejados:",
            dias_opcoes,
            format_func=lambda x: x.strftime("%d/%m/%Y")
        )

    if dias_escolhidos:
        df_area = df_area[df_area["data"].isin(dias_escolhidos)]

    if df_area.empty:
        st.info("❌ Nenhum dado encontrado para esse filtro.")
        st.stop()

    # ===== KPIs =====
    ofertadas  = int(pd.to_numeric(df_area["numero_de_corridas_ofertadas"], errors="coerce").fillna(0).sum())
    aceitas    = int(pd.to_numeric(df_area["numero_de_corridas_aceitas"], errors="coerce").fillna(0).sum())
    rejeitadas = int(pd.to_numeric(df_area["numero_de_corridas_rejeitadas"], errors="coerce").fillna(0).sum())
    completas  = int(pd.to_numeric(df_area["numero_de_corridas_completadas"], errors="coerce").fillna(0).sum())
    entreg_uniq = int(df_area["pessoa_entregadora"].dropna().nunique())

    st.markdown("Números da região")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📦 Ofertadas", f"{ofertadas:,}".replace(",", "."))
    c2.metric("👍 Aceitas", f"{aceitas:,}".replace(",", "."), f"{(aceitas/ofertadas*100 if ofertadas else 0):.1f}%")
    c3.metric("👎 Rejeitadas", f"{rejeitadas:,}".replace(",", "."), f"{(rejeitadas/ofertadas*100 if ofertadas else 0):.1f}%")
    c4.metric("🏁 Completas", f"{completas:,}".replace(",", "."), f"{(completas/aceitas*100 if aceitas else 0):.1f}%")
    c5.metric("👤 Entregadores", entreg_uniq)

    # período legível na legenda
    try:
        dmin = pd.to_datetime(df_area["data"]).min().strftime("%d/%m/%Y")
        dmax = pd.to_datetime(df_area["data"]).max().strftime("%d/%m/%Y")
        periodo_txt = f"{dmin} a {dmax}"
    except Exception:
        periodo_txt = "—"

    st.caption(
        "ℹ️ Filtros → "
        f"Subpraça: **{sub_sel}**"
        + (f" • Turnos: {', '.join(turnos_sel)}" if turnos_sel else " • Todos os turnos")
        + f" • Período: **{periodo_txt}**"
    )



