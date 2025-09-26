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

import pandas as pd

# ---- Helpers de tempo ----
def _hms_from_hours(horas_float) -> str:
    """Converte horas (float) -> 'HH:MM:SS' (sem dias), robusto a NaN/strings."""
    try:
        h = float(horas_float)
        if h < 0 or not (h == h):  # NaN
            h = 0.0
    except Exception:
        h = 0.0
    total_seg = int(round(h * 3600))
    hh = total_seg // 3600
    mm = (total_seg % 3600) // 60
    ss = total_seg % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"



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
        "Perfil do Entregador",
    ],
    "Relatórios": [
        "Alertas de Faltas",
        "Relação de Entregadores",
        "Categorias de Entregadores",
        "Relatórios Subpraças",
        "Resumos",
        "Lista de Ativos",
        "Comparar ativos",
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
            "Entregadores ativos",   # 👈 novo
        ],
        index=0,
        horizontal=True,
    )

    mes_atual = pd.Timestamp.today().month
    ano_atual = pd.Timestamp.today().year
    df_mes_atual = df[(df["mes"] == mes_atual) & (df["ano"] == ano_atual)]

    # ================================================================
    # 1) Horas realizadas (mensal + diário)
    # ================================================================
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

    # ================================================================
    # 2) Entregadores ativos (mensal + diário)  👈 NOVO
    # ================================================================
    elif tipo_grafico == "Entregadores ativos":
        mensal_ents = (
            df.groupby("mes_ano", as_index=False)["pessoa_entregadora"]
              .nunique()
              .rename(columns={"pessoa_entregadora": "entregadores"})
        )
        mensal_ents["mes_rotulo"] = mensal_ents["mes_ano"].dt.strftime("%b/%y")

        fig_mensal = px.bar(
            mensal_ents, x="mes_rotulo", y="entregadores", text="entregadores",
            title="Entregadores ativos por mês",
            labels={"mes_rotulo": "Mês/Ano", "entregadores": "Entregadores ativos"},
            template="plotly_dark", color_discrete_sequence=["#00BFFF"],
        )
        fig_mensal.update_traces(
            texttemplate="<b>%{text}</b>", textposition="outside",
            textfont=dict(size=16, color="white"),
            marker_line_color="rgba(255,255,255,0.25)", marker_line_width=0.5,
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
            por_dia_ent = (
                df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                            .groupby("dia", as_index=False)["pessoa_entregadora"]
                            .nunique()
                            .rename(columns={"pessoa_entregadora": "entregadores"})
                            .sort_values("dia")
            )
            fig_dia = px.line(
                por_dia_ent, x="dia", y="entregadores",
                title="📈 Entregadores ativos por dia (mês atual)",
                labels={"dia": "Dia", "entregadores": "Entregadores ativos"},
                template="plotly_dark",
            )
            fig_dia.update_traces(mode="lines+markers", line_shape="spline",
                                  hovertemplate="Dia %{x}<br>%{y} entregadores<extra></extra>")
            fig_dia.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"), title_font=dict(size=22),
                xaxis=dict(showgrid=False, tickmode="linear", dtick=1),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.15)"),
                margin=dict(t=60, r=20, b=60, l=60),
            )
            total_unicos_mes = int(df_mes_atual["pessoa_entregadora"].dropna().nunique())
            st.metric("👤 Entregadores ativos no mês", total_unicos_mes)
            st.plotly_chart(fig_dia, use_container_width=True)
        else:
            st.info("Sem dados no mês atual para plotar entregadores por dia.")
        st.stop()

    # ================================================================
    # 3) Corridas ofertadas (mensal + diário) com UTR (Absoluto/Médias)
    # ================================================================
    elif tipo_grafico == "Corridas ofertadas":
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

    # ================================================================
    # 4) Genérico: Aceitas / Rejeitadas / Completadas (mensal + diário)
    # ================================================================
    # ================================================================
    # 4) Genérico: Aceitas / Rejeitadas / Completadas (mensal + diário)
    # ================================================================
    else:
        coluna_map = {
            "Corridas aceitas": ("numero_de_corridas_aceitas", "Corridas aceitas por mês", "Corridas Aceitas"),
            "Corridas rejeitadas": ("numero_de_corridas_rejeitadas", "Corridas rejeitadas por mês", "Corridas Rejeitadas"),
            "Corridas completadas": ("numero_de_corridas_completadas", "Corridas completadas por mês", "Corridas Completadas"),
        }
        if tipo_grafico not in coluna_map:
            st.warning("Tipo de gráfico inválido.")
            st.stop()

        col, titulo, label = coluna_map[tipo_grafico]

        # 🔀 Toggle de base para COMPLETADAS
        if tipo_grafico == "Corridas completadas":
            base_pct = st.radio(
                "Base de cálculo da %:",
                ["Aceitas", "Ofertadas"],
                index=0,
                horizontal=True,
                help="Escolha se a % de completas será em cima das Aceitas (taxa de conclusão) ou das Ofertadas."
            )
        else:
            base_pct = "Ofertadas"

        # ---- Mensal
        mensal = df.groupby("mes_ano", as_index=False)[col].sum()
        mensal["mes_rotulo"] = mensal["mes_ano"].dt.strftime("%b/%y")

        # Denominadores possíveis
        mensal_ofert = (
            df.groupby("mes_ano", as_index=False)["numero_de_corridas_ofertadas"].sum()
              .rename(columns={"numero_de_corridas_ofertadas": "ofertadas_total"})
        )
        mensal = mensal.merge(mensal_ofert, on="mes_ano", how="left")

        if tipo_grafico == "Corridas completadas" and base_pct == "Aceitas":
            mensal_aceitas = (
                df.groupby("mes_ano", as_index=False)["numero_de_corridas_aceitas"].sum()
                  .rename(columns={"numero_de_corridas_aceitas": "aceitas_total"})
            )
            mensal = mensal.merge(mensal_aceitas, on="mes_ano", how="left")
            denom_col = "aceitas_total"
        else:
            denom_col = "ofertadas_total"

        def _pct(v, base):
            try:
                v = float(v); base = float(base)
                return f"{(v/base*100):.1f}%" if base > 0 else "0.0%"
            except Exception:
                return "0.0%"

        mensal["__label_text__"] = mensal.apply(
            lambda r: f"{int(r[col])} ({_pct(r[col], r.get(denom_col, 0))})",
            axis=1
        )

        fig = px.bar(
            mensal, x="mes_rotulo", y=col, text="__label_text__", title=titulo + (f" • Base: {base_pct}" if tipo_grafico=="Corridas completadas" else ""),
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

        # ---- Diário (mês atual)
        por_dia = (
            df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                        .groupby("dia", as_index=False)[col].sum()
                        .sort_values("dia")
        )
        fig_dia = px.line(
            por_dia, x="dia", y=col,
            title=f"📈 {label} por dia (mês atual)" + (f" • Base: {base_pct}" if tipo_grafico=="Corridas completadas" else ""),
            labels={"dia": "Dia", col: label},
            template="plotly_dark"
        )
        fig_dia.update_traces(line_shape="spline", mode="lines+markers")
        total_mes = int(por_dia[col].sum())
        st.metric(f"🚗 {label} no mês", total_mes)
        st.plotly_chart(fig_dia, use_container_width=True)

        st.stop()



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

    ano_atual = pd.Timestamp.today().year
    total_corridas_ano = int(df[df["ano"] == ano_atual]["numero_de_corridas_completadas"].sum())

    st.metric("Total de corridas completadas no ano", f"{total_corridas_ano:,}".replace(",", "."))

    st.markdown("</div>", unsafe_allow_html=True)


#SUBPRAÇA

# -------------------------------------------------------------------
# 👤 Perfil do Entregador (histórico completo, sem filtros extras)
# -------------------------------------------------------------------
if modo == "Perfil do Entregador":
    st.header("👤 Perfil do Entregador")

    # --- Filtro único: nome
    entregadores_lista = sorted(df["pessoa_entregadora"].dropna().unique())
    nome = st.selectbox("Selecione o entregador:", [None] + entregadores_lista,
                        format_func=lambda x: "" if x is None else x)
    if not nome:
        st.stop()

    # --- Recorte: histórico completo do entregador
    df_e = df[df["pessoa_entregadora"] == nome].copy()
    if df_e.empty:
        st.info("❌ Nenhum dado para esse entregador no histórico.")
        st.stop()

    # Garantias de tipos
    df_e["data"] = pd.to_datetime(df_e["data"], errors="coerce")
    df_e["mes_ano"] = df_e["data"].dt.to_period("M").dt.to_timestamp()

    # Helper: segundos -> HH:MM:SS (sem "dias")
    def _sec_to_hms(sec_total: float | int) -> str:
        try:
            sec = int(round(float(sec_total)))
        except Exception:
            sec = 0
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    # ======================
    # KPIs (histórico total)
    # ======================
    ofertadas  = int(pd.to_numeric(df_e.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
    aceitas    = int(pd.to_numeric(df_e.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
    rejeitadas = int(pd.to_numeric(df_e.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum())
    completas  = int(pd.to_numeric(df_e.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0).sum())

    acc_pct  = (aceitas   / ofertadas * 100) if ofertadas > 0 else 0.0
    rej_pct  = (rejeitadas/ ofertadas * 100) if ofertadas > 0 else 0.0
    comp_pct = (completas / aceitas   * 100) if aceitas   > 0 else 0.0

    # Horas totais
    horas_total = (df_e["segundos_abs"].sum() / 3600.0) if "segundos_abs" in df_e.columns else _horas_from_abs(df_e)

    # UTR (histórico) — Absoluto e Médias
    utr_abs_hist = (ofertadas / horas_total) if horas_total > 0 else 0.0
    base_u = utr_por_entregador_turno(df_e)
    if not base_u.empty:
        base_u = base_u[base_u["supply_hours"] > 0]
        utr_medias_hist = (base_u["corridas_ofertadas"] / base_u["supply_hours"]).mean() if not base_u.empty else 0.0
    else:
        utr_medias_hist = 0.0

    # Tempo online médio: auto-normaliza (0–1 ou 0–100) para 0–100
    try:
        from utils import calcular_tempo_online
        _t = float(calcular_tempo_online(df_e))
        t_online_pct = _t if _t > 1.0001 else _t * 100.0
        t_online_pct = max(0.0, min(100.0, t_online_pct))
    except Exception:
        t_online_pct = 0.0

    # Dias ativos e última atividade (label curto pra não cortar)
    dias_ativos = int(df_e["data"].dt.date.nunique())
    ultima_atividade = df_e["data"].max()
    ultima_txt = ultima_atividade.strftime("%d/%m/%y") if pd.notna(ultima_atividade) else "—"

    # --- Ajuste fino de UI nas métricas (opcional)
    st.markdown("""
    <style>
      div[data-testid="stMetric"] > label { font-size: 0.90rem; color: #9aa4b2; }
      div[data-testid="stMetric"] > div:nth-child(2) { font-size: 2rem; }
    </style>
    """, unsafe_allow_html=True)

    # ======================
    # KPIs — layout limpo + legendas %
    # ======================

    # 1ª linha (4 colunas)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("UTR (Absoluto)", f"{utr_abs_hist:.2f}")
    with c2:
        st.metric("UTR (Médias)",   f"{utr_medias_hist:.2f}")
    with c3:
        st.metric("Aceitas",        f"{aceitas:,}".replace(",","."))      # sem delta
        st.caption(f"Acc: {acc_pct:.2f}%")
    with c4:
        st.metric("Completas",      f"{completas:,}".replace(",","."))    # sem delta
        st.caption(f"Conclusão: {comp_pct:.2f}%")

    # 2ª linha (4 colunas) — Ofertadas, Rejeitadas, Online médio, SH (HH:MM:SS)
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.metric("Ofertadas",      f"{ofertadas:,}".replace(",","."))    # sem delta
    with c6:
        st.metric("Rejeitadas",     f"{rejeitadas:,}".replace(",","."))   # sem delta
        st.caption(f"Rejeição: {rej_pct:.2f}%")
    with c7:
        st.metric("Online médio",   f"{t_online_pct:.2f}%")
    with c8:
        st.metric("SH (hist.)",     _sec_to_hms(horas_total * 3600))      # HH:MM:SS

    # 3ª linha — Dias ativos + Últ. dia
    c9, c10 = st.columns(2)
    with c9:
        st.metric("Dias ativos",    f"{dias_ativos}")
    with c10:
        st.metric("Últ. dia",       ultima_txt)  # ex.: 14/09/25

    # ============================
    # 📈 Evolução mensal (barras)
    # — barras com COMPLETAS e rótulo "N (acc%)"
    # ============================
    st.subheader("📈 Evolução mensal")
    mens = (df_e.groupby("mes_ano", as_index=False)
              .agg(ofertadas=("numero_de_corridas_ofertadas","sum"),
                   aceitas=("numero_de_corridas_aceitas","sum"),
                   completas=("numero_de_corridas_completadas","sum")))
    mens["acc_pct"] = mens.apply(lambda r: (r["aceitas"]/r["ofertadas"]*100) if r["ofertadas"]>0 else 0.0, axis=1)
    mens["mes_rotulo"] = pd.to_datetime(mens["mes_ano"]).dt.strftime("%b/%y")
    mens["__label_text__"] = mens.apply(lambda r: f"{int(r['completas'])} ({r['acc_pct']:.2f}%)", axis=1)

    fig_evo = px.bar(
        mens, x="mes_rotulo", y="completas", text="__label_text__",
        labels={"mes_rotulo":"Mês","completas":"Completas"},
        title="Completas por mês • rótulo: N (acc%)",
        template="plotly_dark", color_discrete_sequence=["#00BFFF"]
    )
    fig_evo.update_traces(
        textposition="outside",
        texttemplate="%{text}",
        marker_line_color="rgba(255,255,255,0.25)",
        marker_line_width=0.5,
    )
    fig_evo.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"), title_font=dict(size=22),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.15)"),
        bargap=0.25, margin=dict(t=70, r=20, b=60, l=60), showlegend=False,
    )
    st.plotly_chart(fig_evo, use_container_width=True)

    # =======================================
    # 🏷️ Histórico de categoria (por mês) — SH em HH:MM:SS
    # =======================================
    st.subheader("🏷️ Histórico de categoria (por mês)")
    meses_unicos = (df["mes_ano"].dropna().sort_values().unique().tolist())
    hist_cat = []
    for ts in meses_unicos:
        ts = pd.to_datetime(ts)
        mes_i, ano_i = int(ts.month), int(ts.year)
        df_cat = classificar_entregadores(df, mes_i, ano_i)
        row = df_cat[df_cat["pessoa_entregadora"] == nome]
        if not row.empty:
            hist_cat.append({
                "mes_ano": ts,
                "categoria": str(row.iloc[0]["categoria"]),
                "supply_hours": float(row.iloc[0]["supply_hours"]),  # horas (float)
                "aceitacao_%": float(row.iloc[0]["aceitacao_%"]),
                "conclusao_%": float(row.iloc[0]["conclusao_%"]),
            })

    if hist_cat:
        cat_df = pd.DataFrame(hist_cat).sort_values("mes_ano")
        cat_df["mês"] = cat_df["mes_ano"].dt.strftime("%b/%y")
        # converter horas (float) -> segundos -> HH:MM:SS
        cat_df["Supply Hours (HH:MM:SS)"] = cat_df["supply_hours"].apply(lambda h: _sec_to_hms(h * 3600))

        st.dataframe(
            cat_df[["mês","categoria","Supply Hours (HH:MM:SS)","aceitacao_%","conclusao_%"]]
                .rename(columns={
                    "mês":"Mês",
                    "categoria":"Categoria",
                    "aceitacao_%":"Aceitação %",
                    "conclusao_%":"Conclusão %",
                })
                .style.format({
                    "Aceitação %": "{:.2f}",
                    "Conclusão %": "{:.2f}",
                }),
            use_container_width=True
        )
    else:
        st.caption("Sem categoria calculada nos meses desse histórico.")

    # ==========================
    # 🏁 Top turnos (histórico) — por nº de dias no turno, com SH em HH:MM:SS
    # ==========================
    st.subheader("🏁 Top turnos (histórico)")
    if "periodo" in df_e.columns:
        base_turno = df_e.copy()
        base_turno["dia"] = base_turno["data"].dt.date  # contar dias únicos por turno

        top_turnos = (
            base_turno
            .groupby("periodo", as_index=False)
            .agg(
                dias=("dia", "nunique"),
                seg=("segundos_abs", "sum"),
                ofertadas=("numero_de_corridas_ofertadas", "sum"),
                aceitas=("numero_de_corridas_aceitas", "sum"),
                completas=("numero_de_corridas_completadas", "sum"),
            )
        )

        # SH somente em HH:MM:SS (sem dias)
        top_turnos["Supply Hours (HH:MM:SS)"] = top_turnos["seg"].apply(_sec_to_hms)

        # % de aceitação com 2 casas
        top_turnos["Aceitação %"] = top_turnos.apply(
            lambda r: (r["aceitas"] / r["ofertadas"] * 100) if r["ofertadas"] > 0 else 0.0,
            axis=1
        )

        # Ordena por nº de dias desc; desempate por SH (segundos) desc
        top_turnos = top_turnos.sort_values(["dias", "seg"], ascending=[False, False]).reset_index(drop=True)

        cols_show = [
            "periodo",
            "dias",
            "Supply Hours (HH:MM:SS)",
            "aceitas",
            "completas",
            "Aceitação %",
        ]
        st.dataframe(
            top_turnos[cols_show]
            .rename(columns={
                "periodo": "Turno",
                "dias": "Dias ativos",
                "aceitas": "Aceitas",
                "completas": "Completas",
            })
            .style.format({
                "Aceitação %": "{:.2f}",
            }),
            use_container_width=True
        )
    else:
        st.caption("—")

# -------------------------------------------------------------------
# 🧾 Resumo (Mensal/Semanal) — com texto pronto e setas 🟢/🔴
# -------------------------------------------------------------------
# -------------------------------------------------------------------
# 🧾 Resumo (Mensal/Semanal) — texto pronto com setas por sinal (🟢⬆ / 🔴⬇ / ⚪)
# -------------------------------------------------------------------
if modo == "Resumos":
    st.header("🧾 Resumo (Mensal/Semanal)")

    import pandas as pd
    import calendar

    # ------------- Helpers -------------
    def _sec_to_hms(sec_total: float | int) -> str:
        try:
            sec = int(round(float(sec_total)))
        except Exception:
            sec = 0
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def fmt_int(v: float | int) -> str:
        try:
            return f"{int(round(float(v))):,}".replace(",", ".")
        except Exception:
            return "0"

    def fmt_dec(v: float, casas=2) -> str:
        try:
            return f"{float(v):.{casas}f}".replace(".", ",")
        except Exception:
            return "0,00"

    def fmt_pct(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v:+.2f}%".replace(".", ",")

    def fmt_pp(v: float | None) -> str:
        if v is None:
            return "—"
        num = f"{v:+.2f}".replace(".", ",")
        return f"{num} p.p."

    # 🔁 Setas apenas pelo sinal do delta (sem interpretar “bom/ruim”)
    def arrow(delta: float | None) -> str:
        if delta is None or abs(delta) < 1e-9:
            return "⚪"
        return "🟢⬆" if delta > 0 else "🔴⬇"

    def calc_utr_medias(df_slice: pd.DataFrame) -> float:
        """Média dos UTRs por linha (pessoa/turno/dia). Usa helper se existir, senão fallback."""
        try:
            from relatorios import utr_por_entregador_turno
            b = utr_por_entregador_turno(df_slice)
            if b is None or b.empty:
                return 0.0
            b = b[b["supply_hours"] > 0]
            return float((b["corridas_ofertadas"] / b["supply_hours"]).mean()) if not b.empty else 0.0
        except Exception:
            if "segundos_abs" not in df_slice.columns:
                return 0.0
            tmp = df_slice.copy()
            tmp["h"]  = pd.to_numeric(tmp["segundos_abs"], errors="coerce").fillna(0) / 3600.0
            tmp["co"] = pd.to_numeric(tmp.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
            tmp = tmp[tmp["h"] > 0]
            if tmp.empty:
                return 0.0
            return float((tmp["co"] / tmp["h"]).mean())

    def kpis(df_slice: pd.DataFrame):
        ofe = pd.to_numeric(df_slice.get("numero_de_corridas_ofertadas",   0), errors="coerce").fillna(0).sum()
        ace = pd.to_numeric(df_slice.get("numero_de_corridas_aceitas",     0), errors="coerce").fillna(0).sum()
        rej = pd.to_numeric(df_slice.get("numero_de_corridas_rejeitadas",  0), errors="coerce").fillna(0).sum()
        com = pd.to_numeric(df_slice.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0).sum()
        seg = pd.to_numeric(df_slice.get("segundos_abs",                   0), errors="coerce").fillna(0).sum()
        sh_h = float(seg) / 3600.0
        acc  = float(ace / ofe * 100) if ofe > 0 else 0.0
        rejp = float(rej / ofe * 100) if ofe > 0 else 0.0
        # ativos: quem tem alguma atividade no período
        if "pessoa_entregadora" in df_slice.columns:
            atividade = df_slice[["segundos_abs",
                                   "numero_de_corridas_ofertadas",
                                   "numero_de_corridas_aceitas",
                                   "numero_de_corridas_completadas"]].fillna(0).sum(axis=1) > 0
            ativos = int(df_slice.loc[atividade, "pessoa_entregadora"].nunique())
        else:
            ativos = 0
        utr_abs = float(ofe / sh_h) if sh_h > 0 else 0.0
        utr_med = float(calc_utr_medias(df_slice))
        return dict(ofe=ofe, ace=ace, rej=rej, com=com, seg=seg, sh_h=sh_h,
                    acc=acc, rejp=rejp, ativos=ativos, utr_abs=utr_abs, utr_med=utr_med)

    def delta_pct(cur_v, prev_v):
        """Variação %; None quando não dá pra calcular (prev=0 e cur>0)."""
        if prev_v is None or prev_v == 0:
            if cur_v == 0:
                return 0.0
            return None
        return float((cur_v - prev_v) / prev_v * 100.0)

    def delta_pp(cur_v, prev_v):
        """Variação em pontos percentuais (p.p.)."""
        if prev_v is None:
            return None
        return float(cur_v - prev_v)

    # ------------- Seletores -------------
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    data_min = pd.to_datetime(df["data"]).min().date()
    data_max = pd.to_datetime(df["data"]).max().date()

    tipo = st.radio("Período", ["Semanal (Seg–Dom)", "Mensal"], horizontal=True, index=0)

    if tipo.startswith("Semanal"):
        # escolhe qualquer dia dentro da semana (default: última data da base)
        ref_date = st.date_input(
            "Escolha um dia da semana (Seg–Dom)",
            value=data_max, min_value=data_min, max_value=data_max, format="DD/MM/YYYY"
        )
        ref_ts = pd.to_datetime(ref_date)
        dow = ref_ts.weekday()  # 0 = segunda
        ini = (ref_ts - pd.Timedelta(days=dow)).normalize()
        fim = ini + pd.Timedelta(days=6)
        # semana anterior
        ini_prev = ini - pd.Timedelta(days=7)
        fim_prev = fim - pd.Timedelta(days=7)

        semana_label = f"Semana {int(ref_ts.isocalendar().week)}"
        header = f"Resumo semanal — {semana_label} ({ini.strftime('%d/%m')}–{fim.strftime('%d/%m')}) • vs semana anterior"

        df_cur  = df[(df["data"] >= ini) & (df["data"] <= fim)].copy()
        df_prev = df[(df["data"] >= ini_prev) & (df["data"] <= fim_prev)].copy()

    else:
        # default: último mês com dados
        ultimo = pd.to_datetime(df["data"]).max()
        mes_default, ano_default = int(ultimo.month), int(ultimo.year)

        c1, c2 = st.columns(2)
        mes_sel = c1.selectbox("Mês", list(range(1, 13)), index=mes_default-1)
        anos_disp = sorted(df["data"].dt.year.dropna().unique().tolist(), reverse=True)
        ano_sel = c2.selectbox("Ano", anos_disp, index=anos_disp.index(ano_default))

        ini = pd.Timestamp(year=ano_sel, month=mes_sel, day=1)
        ndias = calendar.monthrange(ano_sel, mes_sel)[1]
        fim = pd.Timestamp(year=ano_sel, month=mes_sel, day=ndias)
        # mês anterior
        if mes_sel == 1:
            ano_prev, mes_prev = ano_sel - 1, 12
        else:
            ano_prev, mes_prev = ano_sel, mes_sel - 1
        ndias_prev = calendar.monthrange(ano_prev, mes_prev)[1]
        ini_prev = pd.Timestamp(year=ano_prev, month=mes_prev, day=1)
        fim_prev = pd.Timestamp(year=ano_prev, month=mes_prev, day=ndias_prev)

        header = f"Resumo mensal — {ini.strftime('%b/%Y').capitalize()} • vs {ini_prev.strftime('%b/%Y').capitalize()}"

        df_cur  = df[(df["data"] >= ini) & (df["data"] <= fim)].copy()
        df_prev = df[(df["data"] >= ini_prev) & (df["data"] <= fim_prev)].copy()

    # ------------- KPIs & Deltas -------------
    cur  = kpis(df_cur)
    prev = kpis(df_prev)

    d_com_pct = delta_pct(cur["com"],      prev["com"])
    d_acc_pct = delta_pct(cur["acc"],      prev["acc"])
    d_rej_pct = delta_pct(cur["rejp"],     prev["rejp"])
    d_sh_pct  = delta_pct(cur["sh_h"],     prev["sh_h"])
    d_ati_pct = delta_pct(cur["ativos"],   prev["ativos"])
    d_uab_pct = delta_pct(cur["utr_abs"],  prev["utr_abs"])
    d_ume_pct = delta_pct(cur["utr_med"],  prev["utr_med"])
    d_ofe_pct = delta_pct(cur["ofe"],      prev["ofe"])


    # ------------- Texto final (parágrafos vazios) -------------
    linhas = [
        f"Completas: {fmt_int(cur['com'])} ({fmt_pct(d_com_pct)}) {arrow(d_com_pct)}",
        f"Ofertadas: {fmt_int(cur['ofe'])} ({fmt_pct(d_ofe_pct)}) {arrow(d_ofe_pct)}",
        f"Aceitação: {fmt_dec(cur['acc'])}% ({fmt_pct(d_acc_pct)}) {arrow(d_acc_pct)}",
        f"Rejeição: {fmt_dec(cur['rejp'])}% ({fmt_pct(d_rej_pct)}) {arrow(d_rej_pct)}",
        f"Total SH: {_sec_to_hms(cur['seg'])} ({fmt_pct(d_sh_pct)}) {arrow(d_sh_pct)}",
        f"Ativos: {fmt_int(cur['ativos'])} ({fmt_pct(d_ati_pct)}) {arrow(d_ati_pct)}",
        f"UTR (Abs.): {fmt_dec(cur['utr_abs'])} ({fmt_pct(d_uab_pct)}) {arrow(d_uab_pct)}",
        f"UTR (Médias): {fmt_dec(cur['utr_med'])} ({fmt_pct(d_ume_pct)}) {arrow(d_ume_pct)}",
    ]
    texto = header + "\n\n" + "\n\n".join(linhas)

    st.subheader("📝 Texto pronto")
    st.text_area("Copie e cole:", value=texto, height=300)



#SUBPRAÇA
#SUBPRAÇA
#SUBPRAÇA
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


# -------------------------------------------------------------------
# Quem NÃO atuou no mês atual (seleciona 1+ meses de origem; união)
# -------------------------------------------------------------------

if modo == "Comparar ativos":
    st.header("🚫 Quem NÃO atuou no mês atual")

    # Garante UUID
    if "uuid" not in df.columns:
        if "id_da_pessoa_entregadora" in df.columns:
            df["uuid"] = df["id_da_pessoa_entregadora"].astype(str)
        else:
            df["uuid"] = ""

    # Define mês atual pela última data da base
    df["data"] = pd.to_datetime(df.get("data"), errors="coerce")
    last_day = pd.to_datetime(df["data"]).max()
    if pd.isna(last_day):
        st.error("Sem datas válidas na base.")
        st.stop()

    mes_atual = int(last_day.month)
    ano_atual = int(last_day.year)

    # Monta lista de meses disponíveis (exceto o atual)
    meses_labels = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    base_meses = (
        df.dropna(subset=["data"])
          .assign(ano=df["data"].dt.year, mes=df["data"].dt.month)
          .groupby(["ano","mes"], as_index=False)
          .size()
          .sort_values(["ano","mes"], ascending=[False, False])
    )
    base_meses = base_meses[~((base_meses["ano"] == ano_atual) & (base_meses["mes"] == mes_atual))]

    def _fmt_opt(row):
        return f"{int(row['mes']):02d}/{int(row['ano'])} - {meses_labels[int(row['mes'])-1]}"

    opcoes = [_fmt_opt(r) for _, r in base_meses.iterrows()]
    pares  = [(int(r["ano"]), int(r["mes"])) for _, r in base_meses.iterrows()]
    mapa_label_para_par = dict(zip(opcoes, pares))

    st.caption(f"Mês atual de comparação: **{mes_atual:02d}/{ano_atual} - {meses_labels[mes_atual-1]}**")

    # Multiselect de 1+ meses de origem
    escolhidos = st.multiselect(
        "Selecione 1 ou mais meses de ORIGEM:",
        options=opcoes,
        help="Mostra quem atuou em QUALQUER um desses meses e não atuou no mês atual."
    )

    # Helper para calcular ativos
    def _ativos(df_base, mes, ano):
        d = df_base[(df_base["mes"] == mes) & (df_base["ano"] == ano)].copy()
        if d.empty:
            return set()

        soma = (
            pd.to_numeric(d.get("segundos_abs", 0), errors="coerce").fillna(0)
          + pd.to_numeric(d.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
          + pd.to_numeric(d.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
          + pd.to_numeric(d.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)
        )
        d = d.loc[soma > 0]

        if d.empty:
            return set()

        if "uuid" not in d.columns and "id_da_pessoa_entregadora" in d.columns:
            d["uuid"] = d["id_da_pessoa_entregadora"].astype(str)
        d["uuid"] = d["uuid"].astype(str)

        d = d[["pessoa_entregadora","uuid"]].dropna(subset=["pessoa_entregadora"]).drop_duplicates()
        return set(zip(d["pessoa_entregadora"], d["uuid"]))

    # Botão
    disabled = (len(escolhidos) == 0)
    if st.button("Gerar lista", type="primary", use_container_width=True, disabled=disabled):
        # Ativos no mês atual
        ativos_atual = _ativos(df, mes_atual, ano_atual)

        # Ativos nos meses de origem (UNIÃO)
        conjuntos = []
        for label in escolhidos:
            ano_i, mes_i = mapa_label_para_par[label]
            conjuntos.append(_ativos(df, mes_i, ano_i))
        origem = set.union(*conjuntos) if conjuntos else set()

        # Diferença
        nao_atuou_no_atual = origem - ativos_atual

        # Métricas
        c1,c2,c3 = st.columns(3)
        c1.metric("Total nas origens", len(origem))
        c2.metric("Ativos no atual", len(ativos_atual))
        c3.metric("Não atuaram no atual", len(nao_atuou_no_atual))

        st.divider()

        # Tabela + CSV
        def _to_df(s): return pd.DataFrame(sorted(list(s)), columns=["Nome","UUID"])

        st.subheader("🚫 Lista – Não atuaram no mês atual")
        df_out = _to_df(nao_atuou_no_atual)
        if df_out.empty:
            st.success("Todos da(s) origem(ns) atuaram no mês atual. 🔥")
        else:
            st.dataframe(df_out, use_container_width=True)
            st.download_button(
                "⬇️ Baixar CSV",
                data=df_out.to_csv(index=False).encode("utf-8"),
                file_name=f"nao_atuou_mes_atual_{ano_atual}_{mes_atual:02d}.csv",
                mime="text/csv"
            )
    else:
        if disabled:
            st.info("Selecione pelo menos **1** mês de origem para habilitar o botão.")


