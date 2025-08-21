# -------------------------------------------------------------------
# 📊 Indicadores Gerais (rápido, legível e com rótulos certos)
# -------------------------------------------------------------------
if modo == "📊 Indicadores Gerais":
    from plotly import graph_objects as go

    st.subheader("🔎 Escolha o indicador que deseja visualizar:")

    tipo_grafico = st.radio(
        "Tipo de gráfico:",
        ["Corridas ofertadas", "Corridas aceitas", "Corridas rejeitadas", "Corridas completadas"],
        index=0, horizontal=True
    )

    # ---------- Helpers cacheados ---------- #
    @st.cache_data(show_spinner=False)
    def _agg_counts(df_):
        g = (
            df_.groupby("mes_ano")
               .agg(
                   ofertadas=("numero_de_corridas_ofertadas", "sum"),
                   aceitas=("numero_de_corridas_aceitas", "sum"),
                   rejeitadas=("numero_de_corridas_rejeitadas", "sum"),
                   completas=("numero_de_corridas_completadas", "sum"),
               )
               .reset_index()
        )
        g["mes_label"] = pd.to_datetime(g["mes_ano"]).dt.strftime("%b/%y")
        return g

    @st.cache_data(show_spinner=False)
    def _utr_mes_media_diaria(df_, ts_mensal):
        """
        UTR mensal com MESMA lógica da tela UTR:
        - pega base diária por entregador/turno
        - faz média por DIA
        - depois média das médias de cada dia
        """
        mes = int(pd.to_datetime(ts_mensal).month)
        ano = int(pd.to_datetime(ts_mensal).year)
        base = utr_por_entregador_turno(df_, mes, ano)
        if base.empty:
            return 0.0
        # garantir datetime e agrupar por dia
        base = base.copy()
        base["data"] = pd.to_datetime(base["data"], errors="coerce")
        daily_mean = base.groupby(base["data"].dt.date)["UTR"].mean()
        return float(daily_mean.mean()) if not daily_mean.empty else 0.0

    @st.cache_data(show_spinner=False)
    def _prepara_agregado(df_):
        agg = _agg_counts(df_)
        # UTR do mês (média dos UTR diários) mês a mês
        agg["utr_mes"] = [round(_utr_mes_media_diaria(df_, ts), 2) for ts in agg["mes_ano"]]

        # % com proteção a zero
        ofertadas_safe = agg["ofertadas"].replace(0, pd.NA)
        aceitas_safe   = agg["aceitas"].replace(0, pd.NA)

        agg["acc_pct"]  = (agg["aceitas"]    / ofertadas_safe * 100).round(1)  # aceitação
        agg["rej_pct"]  = (agg["rejeitadas"] / ofertadas_safe * 100).round(1)  # rejeição
        agg["comp_pct"] = (agg["completas"]  / aceitas_safe   * 100).round(1)  # conclusão

        # preencher NaN só pra exibição
        for c in ["acc_pct", "rej_pct", "comp_pct", "utr_mes"]:
            agg[c] = agg[c].fillna(0)
        return agg

    agregado = _prepara_agregado(df)

    # ---------- Seleção por indicador ---------- #
    if tipo_grafico == "Corridas ofertadas":
        y_col    = "ofertadas"
        top_col  = "utr_mes"
        top_fmt  = lambda v: f"{v:.2f}"
        titulo   = "Corridas ofertadas por mês"
        subtitulo = "Rótulo no topo = UTR do mês (média dos UTR diários)"
    elif tipo_grafico == "Corridas aceitas":
        y_col    = "aceitas"
        top_col  = "acc_pct"
        top_fmt  = lambda v: f"{v:.1f}%"
        titulo   = "Corridas aceitas por mês"
        subtitulo = "Rótulo no topo = % de aceitação (aceitas ÷ ofertadas)"
    elif tipo_grafico == "Corridas rejeitadas":
        y_col    = "rejeitadas"
        top_col  = "rej_pct"
        top_fmt  = lambda v: f"{v:.1f}%"
        titulo   = "Corridas rejeitadas por mês"
        subtitulo = "Rótulo no topo = % de rejeição (rejeitadas ÷ ofertadas)"
    else:  # completadas
        y_col    = "completas"
        top_col  = "comp_pct"
        top_fmt  = lambda v: f"{v:.1f}%"
        titulo   = "Corridas completadas por mês"
        subtitulo = "Rótulo no topo = % de conclusão (completas ÷ aceitas)"

    # ---------- Opções de performance ---------- #
    col_op1, col_op2 = st.columns([1,1])
    fast = col_op1.toggle("⚡ Modo rápido (gráfico estático)", value=True, key=f"fast_{y_col}")
    show_inside = col_op2.toggle("Mostrar número dentro da barra (pode ficar mais lento)", value=False, key=f"in_{y_col}")

    # ---------- Gráfico ---------- #
    fig = go.Figure()

    # Barras com rótulo do topo (UTR ou %)
    fig.add_bar(
        x=agregado["mes_label"],
        y=agregado[y_col],
        text=[top_fmt(v) for v in agregado[top_col]],
        textposition="outside",
        marker=dict(color="#00BFFF", line=dict(color="rgba(255,255,255,0.25)", width=0.5)),
        hovertemplate="<b>%{x}</b><br>" + f"{y_col.capitalize()}: " + "%{y:.0f}<extra></extra>",
        name=y_col.capitalize(),
    )

    # (Opcional) número ABS dentro da barra (segundo trace transparente)
    if show_inside:
        fig.add_bar(
            x=agregado["mes_label"],
            y=agregado[y_col],
            text=[f"{int(v)}" for v in agregado[y_col]],
            textposition="inside",
            insidetextfont=dict(size=18, color="white"),
            marker=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            showlegend=False,
        )
        fig.update_layout(barmode="overlay")

    # Layout limpo
    fig.update_layout(
        title=titulo,
        xaxis_title="Mês/Ano",
        yaxis_title=y_col.capitalize(),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        title_font=dict(size=22),
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=14),
            categoryorder="array",
            categoryarray=list(agregado["mes_label"])
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.15)",
            tickfont=dict(size=14),
            rangemode="tozero"
        ),
        bargap=0.25,
        margin=dict(t=70, r=20, b=60, l=60),
        showlegend=False,
        uniformtext_minsize=14,
        uniformtext_mode="show",
    )

    st.caption(f"💡 {subtitulo}")

    cfg = {"displayModeBar": False}
    if fast:
        cfg["staticPlot"] = True
    st.plotly_chart(fig, use_container_width=True, config=cfg)

    # ---------- Série diária (mês atual) — mantém tua lógica ---------- #
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
