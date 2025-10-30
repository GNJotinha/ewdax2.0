        # ====================================================
        # 🧾 relatório estilo zap
        # ====================================================

        # 1) Subpraça no topo
        if filtro_subpraca:
            # usuário escolheu
            if len(filtro_subpraca) == 1:
                sub_txt = f"**Subpraça:** {filtro_subpraca[0]}"
            else:
                sub_txt = f"**Subpraça:** {', '.join(filtro_subpraca)}"
        else:
            # usuário não escolheu → tenta descobrir do df filtrado
            subs_df = df_sel.get("sub_praca")
            if subs_df is not None:
                subs_unicas = [s for s in subs_df.dropna().unique().tolist() if s != ""]
                if len(subs_unicas) == 1:
                    sub_txt = f"**Subpraça:** {subs_unicas[0]}"
                elif len(subs_unicas) > 1:
                    sub_txt = f"**Subpraça:** {', '.join(subs_unicas)}"
                else:
                    sub_txt = "**Subpraça:** TODOS"
            else:
                sub_txt = "**Subpraça:** TODOS"

        # 2) Turno no topo
        if filtro_turno:
            if len(filtro_turno) == 1:
                turno_txt = f"**Turno:** {filtro_turno[0]}"
            else:
                turno_txt = f"**Turno:** {', '.join(filtro_turno)}"
        else:
            # tenta descobrir pelos dados filtrados
            turnos_df = df_sel.get("periodo")
            if turnos_df is not None:
                turnos_unicos = [t for t in turnos_df.dropna().unique().tolist() if t != ""]
                if len(turnos_unicos) == 1:
                    turno_txt = f"**Turno:** {turnos_unicos[0]}"
                elif len(turnos_unicos) > 1:
                    turno_txt = f"**Turno:** {', '.join(turnos_unicos)}"
                else:
                    turno_txt = "**Turno:** TODOS"
            else:
                turno_txt = "**Turno:** TODOS"

        blocos = []
        blocos.append(sub_txt)
        blocos.append(turno_txt)
        blocos.append(f"*Período de análise {periodo_txt}*")

        for _, row in tabela.iterrows():
            nome = row["Entregador"]
            chunk = df_sel[df_sel["pessoa_entregadora"] == nome].copy()
            tempo_online = calcular_tempo_online(chunk)

            ofert = int(row["Ofertadas"])
            aceit = int(row["Aceitas"])
            rejei = int(row["Rejeitadas"])
            compl = int(row["Completas"])

            pct_acc = float(row["Aceitação (%)"])
            pct_rej = float(row["Rejeição (%)"])
            pct_comp = float(row["Conclusão (%)"])

            linhas = [
                f"*{nome}*",
                f"- Tempo online: {tempo_online:.2f}%",
                f"- Ofertadas: {ofert}",
                f"- Aceitas: {aceit} ({pct_acc:.2f}%)",
                f"- Rejeitadas: {rejei} ({pct_rej:.2f}%)",
                f"- Completas: {compl} ({pct_comp:.2f}%)",
            ]
            blocos.append("\n".join(linhas))

        texto_final = "\n\n".join(blocos)
        st.text_area("Resultado:", value=texto_final, height=500)
