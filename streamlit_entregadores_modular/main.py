# main.py — versão clean, focada em legibilidade e grid
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


# =========================
# CONFIG & THEME
# =========================
st.set_page_config(page_title="Painel de Entregadores", page_icon="📦", layout="wide")

CSS = """
<style>
:root{
  --bg:#0c0f14; --panel:#11151c; --ink:#e8eef6; --muted:#8b98a5; --line:#1b222c;
  --primary:#4ea1ff; --accent:#2bd4a3; --warn:#ffcf5c; --danger:#ff6b6b;
}
html, body, .stApp{background:var(--bg); color:var(--ink);}
.block-container{padding-top:1rem; max-width:1180px;}
h1,h2,h3{color:var(--ink); letter-spacing:.2px;}
small, .muted{color:var(--muted);}
hr{border:none; border-top:1px solid var(--line); margin:1rem 0;}

.topbar{
  display:flex; align-items:center; justify-content:space-between;
  padding:.6rem .9rem; background:var(--panel); border:1px solid var(--line);
  border-radius:14px; margin-bottom:.8rem;
}
.brand{font-weight:700; letter-spacing:.3px;}
.userpill{font-size:.85rem; color:var(--muted)}

.kpi-grid{display:grid; grid-template-columns:repeat(4,1fr); gap:.75rem; margin:.4rem 0 1rem;}
@media (max-width: 1000px){ .kpi-grid{grid-template-columns:repeat(2,1fr);} }
@media (max-width: 600px){ .kpi-grid{grid-template-columns:1fr;} }

.kpi{
  background:var(--panel); border:1px solid var(--line); border-radius:14px;
  padding:12px 14px;
}
.kpi .v{font-size:26px; font-weight:800;}
.kpi .l{font-size:12px; color:var(--muted); margin-top:2px}

.card{
  background:var(--panel); border:1px solid var(--line); border-radius:14px;
  padding:12px 14px;
}
.selectbox>div>div{background:var(--panel)!important}

.stTabs [data-baseweb="tab-list"]{gap:.35rem}
.stTabs [data-baseweb="tab"]{background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:.4rem .7rem}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# =========================
# AUTH
# =========================
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario = ""

if not st.session_state.logado:
    st.title("🔐 Login")
    u = st.text_input("Usuário")
    p = st.text_input("Senha", type="password")
    if st.button("Entrar", use_container_width=True):
        if autenticar(u, p):
            st.session_state.logado = True
            st.session_state.usuario = u
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()

nivel = USUARIOS.get(st.session_state.usuario, {}).get("nivel", "")


# =========================
# DATA
# =========================
df = carregar_dados()
df["data"] = pd.to_datetime(df["data"])
df["mes_ano"] = df["data"].dt.to_period("M").dt.to_timestamp()
entregadores = get_entregadores(df)

def hms_from_hours(h):
    try:
        s = int(round(float(h) * 3600))
        hh, r = divmod(s, 3600); mm, ss = divmod(r, 60)
        return f"{hh:02d}:{mm:02d}:{ss:02d}"
    except:
        return "00:00:00"


# =========================
# TOP BAR
# =========================
with st.container():
    st.markdown(
        f"""
        <div class="topbar">
          <div class="brand">Painel de Entregadores</div>
          <div class="userpill">Logado como <b>{st.session_state.usuario}</b>{' · admin' if nivel=='admin' else ''}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# admin: botão de atualizar cache
colA, colB = st.columns([1,6])
with colA:
    if nivel == "admin" and st.button("🔄 Recarregar dados (cache)"):
        st.cache_data.clear()
        st.rerun()

# =========================
# NAV (TABS)
# =========================
tabs = st.tabs(["📊 Estatísticas", "🚗 Desempenho", "⚠ Faltas", "🧾 Relatório", "🏷️ Categorias"])

# --------- 📊 Estatísticas
with tabs[0]:
    # KPIs gerais
    total_ofert = int(df["numero_de_corridas_ofertadas"].sum())
    total_aceit = int(df["numero_de_corridas_aceitas"].sum())
    total_rej   = int(df["numero_de_corridas_rejeitadas"].sum())
    total_comp  = int(df["numero_de_corridas_completadas"].sum())
    tx_acc  = round((total_aceit/total_ofert)*100,1) if total_ofert else 0.0
    tx_comp = round((total_comp/total_aceit)*100,1) if total_aceit else 0.0
    unicos   = df["pessoa_entregadora"].nunique()

    st.markdown('<div class="kpi-grid">', unsafe_allow_html=True)
    for label, val in [
        ("Corridas ofertadas", f"{total_ofert:,}".replace(",", ".")),
        ("Aceitação (%)", f"{tx_acc:.1f}%"),
        ("Conclusão (%)", f"{tx_comp:.1f}%"),
        ("Entregadores únicos", f"{unicos}")
    ]:
        st.markdown(f'<div class="kpi"><div class="v">{val}</div><div class="l">{label}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # seletor simples p/ gráfico
    with st.container():
        c1, c2 = st.columns([2,1])
        with c1:
            tipo = st.radio(
                "Indicador", 
                ["Ofertadas","Aceitas","Rejeitadas","Completadas"],
                horizontal=True, index=0
            )
        with c2:
            st.caption(" ")

    col_map = {
        "Ofertadas": ("numero_de_corridas_ofertadas", "Corridas ofertadas por mês"),
        "Aceitas":   ("numero_de_corridas_aceitas",   "Corridas aceitas por mês"),
        "Rejeitadas":("numero_de_corridas_rejeitadas","Corridas rejeitadas por mês"),
        "Completadas":("numero_de_corridas_completadas","Corridas completadas por mês"),
    }
    col, titulo = col_map[tipo]

    # barra mensal
    mensal = df.groupby('mes_ano')[col].sum().reset_index()
    mensal['mes_ao'] = mensal['mes_ano'].dt.strftime('%b/%y')
    fig = px.bar(
        mensal, x='mes_ao', y=col, text=col, title=titulo,
        labels={col:"Quantidade", "mes_ao":"Mês/Ano"},
        template="plotly_dark"
    )
    fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False)
    fig.update_layout(margin=dict(l=10,r=10,t=50,b=10), height=420, xaxis=dict(showgrid=False))
    st.plotly_chart(fig, use_container_width=True)

    # evolução diária do mês atual
    mes_atual, ano_atual = pd.Timestamp.today().month, pd.Timestamp.today().year
    df_mes = df[(df['data'].dt.month==mes_atual) & (df['data'].dt.year==ano_atual)]
    por_dia = df_mes.groupby(df_mes['data'].dt.day)[col].sum().reset_index().rename(columns={'data':'dia'})
    fig2 = px.line(por_dia, x='dia', y=col, markers=True, title=f"{tipo} por dia (mês atual)", template="plotly_dark")
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # --- UTR compacto (na mesma aba, sem poluir)
    st.subheader("UTR (corridas ofertadas por hora)")
    periodo = st.radio("Período", ["Mês/Ano", "Histórico"], horizontal=True, index=0)
    mesU = anoU = None
    if periodo == "Mês/Ano":
        c1, c2 = st.columns(2)
        mesU = c1.selectbox("Mês", list(range(1,13)))
        anoU = c2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))
    base = utr_por_entregador_turno(df, mesU, anoU) if periodo=="Mês/Ano" else utr_por_entregador_turno(df)

    if base.empty:
        st.info("Sem dados para o período.")
    else:
        if "supply_hours" in base.columns:
            base["tempo_hms"] = base["supply_hours"].apply(hms_from_hours)
        c1, c2 = st.columns(2)
        c1.metric("UTR média", round(base["UTR"].mean(), 2))
        c2.metric("UTR mediana", round(base["UTR"].median(), 2))

        cols = ["pessoa_entregadora","periodo","tempo_hms","corridas_ofertadas","UTR"]
        st.dataframe(base[cols].style.format({"UTR":"{:.2f}"}), use_container_width=True)
        st.download_button("⬇️ CSV UTR", base[cols].to_csv(index=False, decimal=",").encode("utf-8"),
                           file_name="utr_entregador_turno.csv", mime="text/csv")

# --------- 🚗 Desempenho
with tabs[1]:
    left, right = st.columns([1,1])

    with left:
        st.subheader("Ver geral")
        with st.form("f_geral"):
            nomes = sorted(df["pessoa_entregadora"].dropna().unique())
            nome = st.selectbox("Entregador", [None]+nomes, index=0, placeholder="Selecione", key="g_nome")
            gerar = st.form_submit_button("Gerar")
        if gerar and nome:
            txt = gerar_dados(nome, None, None, df[df["pessoa_entregadora"]==nome])
            st.text_area("Resultado", value=txt or "❌ Nenhum dado", height=380)

    with right:
        st.subheader("Simplificada (WhatsApp)")
        with st.form("f_wpp"):
            nomes = sorted(df["pessoa_entregadora"].dropna().unique())
            nome2 = st.selectbox("Entregador", [None]+nomes, index=0, placeholder="Selecione", key="w_nome")
            c1, c2 = st.columns(2)
            mes1 = c1.selectbox("1º Mês", list(range(1,13)))
            ano1 = c2.selectbox("1º Ano", sorted(df["ano"].unique(), reverse=True))
            mes2 = c1.selectbox("2º Mês", list(range(1,13)))
            ano2 = c2.selectbox("2º Ano", sorted(df["ano"].unique(), reverse=True))
            gerar2 = st.form_submit_button("Gerar")
        if gerar2 and nome2:
            t1 = gerar_simplicado(nome2, mes1, ano1, df)
            t2 = gerar_simplicado(nome2, mes2, ano2, df)
            st.text_area("Resultado", value="\n\n".join([t for t in [t1,t2] if t]), height=380)

# --------- ⚠ Faltas
with tabs[2]:
    st.subheader("Alertas de faltas")
    hoje = datetime.now().date()
    ultimos_15 = hoje - timedelta(days=15)
    df["data_date"] = pd.to_datetime(df["data"]).dt.date

    ativos = df[df["data_date"] >= ultimos_15]["pessoa_entregadora_normalizado"].unique()
    msgs = []
    for nome in ativos:
        ent = df[df["pessoa_entregadora_normalizado"]==nome]
        if ent.empty: 
            continue
        dias = pd.date_range(end=hoje - timedelta(days=1), periods=30).date
        pres = set(ent["data_date"])
        seq = 0
        for d in sorted(dias):
            seq = 0 if d in pres else seq + 1
        if seq >= 4:
            nome_ori = ent["pessoa_entregadora"].iloc[0]
            last = max(pres).strftime("%d/%m") if pres else "--/--"
            msgs.append(f"• {nome_ori} – {seq} dias consecutivos ausente (última presença: {last})")

    if msgs:
        st.text_area("Resultado", value="\n".join(msgs), height=380)
    else:
        st.success("✅ Nenhum entregador ativo com faltas consecutivas.")

# --------- 🧾 Relatório
with tabs[3]:
    st.subheader("Relatório Customizado")
    nomes = sorted(df["pessoa_entregadora"].dropna().unique())
    entregador = st.selectbox("Entregador", [None]+nomes, index=0, placeholder="Selecione")

    subpracas = sorted(df["sub_praca"].dropna().unique())
    turnos = sorted(df["periodo"].dropna().unique())
    c1, c2 = st.columns(2)
    f_sub = c1.multiselect("Subpraça", subpracas)
    f_turno = c2.multiselect("Turno", turnos)

    df['data_do_periodo'] = pd.to_datetime(df['data_do_periodo'])
    df['data_date'] = df['data_do_periodo'].dt.date

    tipo = st.radio("Tipo de período", ["Intervalo", "Dias específicos"], horizontal=True, index=0)
    dias_escolhidos = []
    if tipo == "Intervalo":
        dmin, dmax = df["data_date"].min(), df["data_date"].max()
        per = st.date_input("Intervalo", [dmin, dmax], format="DD/MM/YYYY")
        if len(per)==2: dias_escolhidos = list(pd.date_range(per[0], per[1]).date)
    else:
        op = sorted(df["data_date"].unique())
        dias_escolhidos = st.multiselect("Dias", op, format_func=lambda x: x.strftime("%d/%m/%Y"))

    if st.button("Gerar", type="primary"):
        if entregador:
            base = df[df["pessoa_entregadora"]==entregador]
            if f_sub:   base = base[base["sub_praca"].isin(f_sub)]
            if f_turno: base = base[base["periodo"].isin(f_turno)]
            if dias_escolhidos: base = base[base["data_date"].isin(dias_escolhidos)]
            txt = gerar_dados(entregador, None, None, base)
            st.text_area("Resultado", value=txt or "❌ Nenhum dado", height=380)
        else:
            st.warning("Selecione um entregador.")

# --------- 🏷️ Categorias
with tabs[4]:
    st.subheader("Categorias de Entregadores")
    tipo = st.radio("Período", ["Mês/Ano", "Histórico"], horizontal=True, index=0)
    mesC = anoC = None
    if tipo == "Mês/Ano":
        c1, c2 = st.columns(2)
        mesC = c1.selectbox("Mês", list(range(1,13)))
        anoC = c2.selectbox("Ano", sorted(df["ano"].unique(), reverse=True))

    dfc = classificar_entregadores(df, mesC, anoC) if tipo=="Mês/Ano" else classificar_entregadores(df)
    if dfc.empty:
        st.info("Sem dados para o período.")
    else:
        if "supply_hours" in dfc.columns:
            dfc["tempo_hms"] = dfc["supply_hours"].apply(hms_from_hours)

        cont = dfc["categoria"].value_counts().reindex(["Premium","Conectado","Casual","Flutuante"]).fillna(0).astype(int)
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("🚀 Premium", int(cont.get("Premium",0)))
        c2.metric("🎯 Conectado", int(cont.get("Conectado",0)))
        c3.metric("👍 Casual", int(cont.get("Casual",0)))
        c4.metric("↩ Flutuante", int(cont.get("Flutuante",0)))

        cols = ["pessoa_entregadora","categoria","tempo_hms","aceitacao_%","conclusao_%","ofertadas","aceitas","completas","criterios_atingidos"]
        st.dataframe(dfc[cols].style.format({"aceitacao_%":"{:.1f}","conclusao_%":"{:.1f}"}), use_container_width=True)
        st.download_button("⬇️ CSV categorias", dfc[cols].to_csv(index=False, decimal=",").encode("utf-8"),
                           file_name="categorias_entregadores.csv", mime="text/csv")
