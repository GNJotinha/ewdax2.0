def render(_df_unused, _USUARIOS):
    st.header("🕵️ Auditoria Sigilosa — Operacional × Faturamento (Concluídas)")
    _gate()

    # Baixa do Drive e prepara (sem tolerância, sem flags)
    with st.spinner("Baixando planilhas do Drive..."):
        raw_op = load_operacional_from_drive()
        raw_fa = load_faturamento_from_drive()
        op = _prep_operacional(raw_op)   # agrega por data/entregador/turno
        fa = _prep_faturamento(raw_fa)  # agrega por data/entregador/turno
        base = _merge_and_compare(op, fa)

    if base.empty:
        st.info("Nenhum dado encontrado.")
        st.stop()

    # === Filtros simples ===
    base["data_ts"] = pd.to_datetime(base["data"], errors="coerce")
    min_d, max_d = base["data_ts"].min().date(), base["data_ts"].max().date()
    periodo = st.date_input("Período:", (min_d, max_d), min_value=min_d, max_value=max_d, format="DD/MM/YYYY")
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        base = base[(base["data_ts"] >= pd.to_datetime(periodo[0])) & (base["data_ts"] <= pd.to_datetime(periodo[1]))]

    # === Escolha do entregador ===
    nomes = sorted([n for n in base["ent_nome"].dropna().unique()])
    nome = st.selectbox("Entregador", [None] + nomes, format_func=lambda x: "" if x is None else x, index=0)

    if not nome:
        st.info("Selecione um entregador para ver a lista.")
        st.stop()

    # === Tabela no formato pedido ===
    fat_cols = ["data", "turno", "valor_faturamento"]
    op_cols  = ["data", "turno", "valor_operacional"]

    df_sel = base[base["ent_nome"] == nome].copy()
    # Garante as colunas (caso venham ausentes de algum lado)
    for c in fat_cols + op_cols:
        if c not in df_sel.columns:
            df_sel[c] = None

    # Agrupa por data/turno
    saida = (
        df_sel.groupby(["data", "turno"], dropna=False)
              .agg(VLROP=("valor_operacional","sum"),
                   VLRFAT=("valor_faturamento","sum"))
              .reset_index()
              .sort_values(["data","turno"], ascending=[True, True])
    )

    # Renomeia cabecalho conforme pediu
    saida.rename(columns={"data": "DATA", "turno": "TURNO"}, inplace=True)

    # Formatação de valores
    st.subheader(f"Lista — {nome}")
    st.dataframe(
        saida[["DATA","TURNO","VLROP","VLRFAT"]]
             .assign(VLROP=lambda d: d["VLROP"].round(2),
                     VLRFAT=lambda d: d["VLRFAT"].round(2))
             .style.format({"VLROP":"{:.2f}","VLRFAT":"{:.2f}"}),
        use_container_width=True
    )

    # Download CSV no mesmo layout
    st.download_button(
        "⬇️ Baixar CSV",
        saida[["DATA","TURNO","VLROP","VLRFAT"]].to_csv(index=False).encode("utf-8"),
        file_name=f"auditoria_{nome.replace(' ','_')}.csv",
        mime="text/csv"
    )
