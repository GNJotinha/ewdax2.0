# ---------- Por dia (mês atual) ----------
por_dia = (
    df_mes_atual.assign(dia=lambda d: pd.to_datetime(d["data"]).dt.day)
                .groupby("dia", as_index=False)[col].sum()
                .sort_values("dia")
)

# 🔥 Personalização SOMENTE para "Corridas ofertadas":
if "ofertadas" in tipo_grafico.lower():
    # Garante coluna de segundos válida
    df_mes_atual["segundos_abs"] = pd.to_numeric(df_mes_atual.get("segundos_abs", 0), errors="coerce").fillna(0)
    sh_por_dia = (
        df_mes_atual.assign(dia=pd.to_datetime(df_mes_atual["data"]).dt.day)
                    .groupby("dia", as_index=False)["segundos_abs"].sum()
                    .rename(columns={"segundos_abs": "segundos"})
    )
    por_dia = por_dia.merge(sh_por_dia, on="dia", how="left")
    por_dia["horas"] = por_dia["segundos"].fillna(0) / 3600.0
    por_dia["utr"] = por_dia.apply(
        lambda r: (r[col] / r["horas"]) if r["horas"] > 0 else 0.0, axis=1
    )

    # 🪄 Força a label personalizada sempre
    por_dia["label"] = por_dia.apply(
        lambda r: f"{int(r[col])} ofertadas ({r['utr']:.2f} UTR)", axis=1
    )

    fig2 = px.bar(
        por_dia, x="dia", y=col, text="label",
        title=f"📈 {label} por dia (mês atual)",
        labels={"dia": "Dia", col: label},
        template="plotly_dark"
    )
    fig2.update_traces(texttemplate="<b>%{text}</b>", textposition="outside")
else:
    fig2 = px.line(
        por_dia, x="dia", y=col,
        title=f"📈 {label} por dia (mês atual)",
        labels={"dia": "Dia", col: label}, template="plotly_dark"
    )
