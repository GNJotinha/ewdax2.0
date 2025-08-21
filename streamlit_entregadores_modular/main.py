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
