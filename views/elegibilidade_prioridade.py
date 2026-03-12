import io
import zipfile
import re
import pandas as pd
import streamlit as st

REGION_ID_SP = "3841c245-fac1-40a6-8b8f-8d6876447a6d"

SUB_IDS_SP = [
    "c838bd2d-5be4-401a-8ad2-b9d6a9d87a58",  # PERDIZES - SP
    "04c47ecb-c69d-43f6-b4be-49c21afc0e7b",  # INTERLAGOS - SP
    "0340dc65-ce67-416b-b114-07cc468c290d",  # PANAMBY E VILA SONIA - SP
    "ff380776-9d85-403d-9214-068c6eba6d09",  # PINHEIROS - SP
    "6934118f-3fb0-4acd-962b-e9bb68c3699c",  # ITAIM E BROOKLIN E INDIANAPOLIS - SP
    "98aafe66-f452-4e64-b323-05e17831f325",  # CAMPO BELO (MINI BTU FD)
    "87791f8f-9c75-4119-b5fa-9b6bd949fb6a",  # ACLIMACAO - SP
    "695dfbe5-bd3a-4e2b-a654-8b8af0eeba8b",  # JABAQUARA E SANTO AMARO - SP
    "fe841dac-692b-4855-aa0b-383a17054038",  # CIDADE DAS FLORES
    "fa9edb08-29d7-494b-80ba-8c2af20f2ceb",  # MOOCA
    "4e14aa79-7fdb-4299-94ba-b35e12128288",  # JARDINS (MINI BTU FD)
]

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _decode_upload_to_text(uploaded) -> str:
    if uploaded is None:
        return ""
    data = uploaded.getvalue()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            pass
    return data.decode("utf-8", errors="replace")


def _parse_driver_ids_from_text(txt: str) -> dict:
    if not txt:
        return {"valid": [], "invalid": [], "duplicates": 0, "total_tokens": 0}

    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    duplicates = 0
    total_tokens = 0

    for raw in txt.splitlines():
        line = (raw or "").strip()
        if not line:
            continue
        if line.startswith("#"):
            continue

        token = line.split()[0].strip().lower()
        if not token:
            continue

        total_tokens += 1

        if not _UUID_RE.match(token):
            invalid.append(token)
            continue

        if token in seen:
            duplicates += 1
            continue

        seen.add(token)
        valid.append(token)

    return {
        "valid": valid,
        "invalid": invalid,
        "duplicates": duplicates,
        "total_tokens": total_tokens,
    }


def _show_parse_feedback(parsed: dict, titulo: str, require_confirm_key: str | None = None) -> bool:
    """
    Mostra métricas/avisos da lista parseada.
    Retorna True se pode seguir, False se deve parar.
    """
    valid = parsed["valid"]
    invalid = parsed["invalid"]
    duplicates = parsed["duplicates"]
    total_tokens = parsed["total_tokens"]

    st.markdown(f"**{titulo}**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("IDs lidos", total_tokens)
    c2.metric("UUID válidos", len(valid))
    c3.metric("Inválidos", len(invalid))
    c4.metric("Duplicados", duplicates)

    if invalid:
        st.warning(
            "Tem coisa aí que **não é UUID válido**. "
            "Por padrão eu vou ignorar esses inválidos."
        )
        with st.expander(f"Ver exemplos de inválidos — {titulo}"):
            st.write(invalid[:200])

        if require_confirm_key:
            ok = st.checkbox(
                f"Ok, entendi — seguir ignorando inválidos em: {titulo}",
                value=False,
                key=require_confirm_key,
            )
            if not ok:
                st.info("Marque a confirmação pra liberar a geração.")
                return False

    return True


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📦 Exportar CSV — Elegibilidade & Prioridade")

    # =========================================================
    # 1) LISTA PRINCIPAL
    # =========================================================
    st.subheader("1) Lista principal de UUIDs")
    uploaded = st.file_uploader(
        "Arquivo .txt principal (1 id por linha)",
        type=["txt"],
        accept_multiple_files=False,
        help="Pode ter linhas vazias. Linha começando com # é ignorada.",
        key="elig_main_upload",
    )

    with st.expander("ou cole os IDs principais aqui"):
        pasted = st.text_area(
            "Cole aqui a lista principal (1 id por linha)",
            height=180,
            key="elig_main_pasted",
        )

    txt_main = _decode_upload_to_text(uploaded) if uploaded is not None else (pasted or "")
    parsed_main = _parse_driver_ids_from_text(txt_main)

    if not txt_main.strip():
        st.info("Suba ou cole a lista principal pra continuar.")
        return

    can_continue_main = _show_parse_feedback(
        parsed_main,
        titulo="Resumo da lista principal",
        require_confirm_key="elig_confirm_main_invalid",
    )
    if not can_continue_main:
        return

    drivers_main = parsed_main["valid"]

    if not drivers_main:
        st.error("Depois de ignorar inválidos, não sobrou nenhum UUID válido na lista principal.")
        return

    # =========================================================
    # 2) LISTA DE REMOÇÃO (INATIVOS / NÃO SUBIRAM)
    # =========================================================
    st.divider()
    st.subheader("2) Lista de UUIDs para remover (opcional)")

    uploaded_remove = st.file_uploader(
        "Arquivo .txt com UUIDs inativos / que não subiram",
        type=["txt"],
        accept_multiple_files=False,
        help="Essa lista será removida da lista principal antes de gerar os CSVs.",
        key="elig_remove_upload",
    )

    with st.expander("ou cole os UUIDs para remover aqui"):
        pasted_remove = st.text_area(
            "Cole aqui os UUIDs para remover (1 id por linha)",
            height=180,
            key="elig_remove_pasted",
        )

    txt_remove = _decode_upload_to_text(uploaded_remove) if uploaded_remove is not None else (pasted_remove or "")
    parsed_remove = _parse_driver_ids_from_text(txt_remove)

    remove_ids = parsed_remove["valid"] if txt_remove.strip() else []

    if txt_remove.strip():
        can_continue_remove = _show_parse_feedback(
            parsed_remove,
            titulo="Resumo da lista de remoção",
            require_confirm_key="elig_confirm_remove_invalid",
        )
        if not can_continue_remove:
            return
    else:
        st.caption("Nenhuma lista de remoção informada. Vou usar a lista principal inteira.")

    # =========================================================
    # 3) SUBTRAÇÃO DAS LISTAS
    # =========================================================
    remove_set = set(remove_ids)
    removed_from_main = [d for d in drivers_main if d in remove_set]
    final_drivers = [d for d in drivers_main if d not in remove_set]

    st.divider()
    st.subheader("3) Resultado da limpeza")

    a, b, c, d = st.columns(4)
    a.metric("Lista principal válida", len(drivers_main))
    b.metric("Lista remoção válida", len(remove_ids))
    c.metric("Removidos da principal", len(removed_from_main))
    d.metric("Lista final", len(final_drivers))

    if remove_ids:
        not_found_remove = [d for d in remove_ids if d not in set(drivers_main)]
        st.caption(
            f"Da lista de remoção, **{len(removed_from_main)}** estavam na principal "
            f"e **{len(not_found_remove)}** não estavam."
        )

        with st.expander("Ver UUIDs efetivamente removidos"):
            st.write(removed_from_main[:500])

        if not_found_remove:
            with st.expander("Ver UUIDs da remoção que não estavam na lista principal"):
                st.write(not_found_remove[:500])

    if not final_drivers:
        st.error("Depois da limpeza, não sobrou nenhum UUID pra gerar os CSVs.")
        return

    # =========================================================
    # 4) DIAGNÓSTICO COM A BASE
    # =========================================================
    if df is not None and not df.empty and "uuid" in df.columns:
        base_ids = (
            df["uuid"]
            .astype(str)
            .fillna("")
            .str.strip()
            .str.lower()
            .replace({"": None})
            .dropna()
            .unique()
            .tolist()
        )
        base_set = set(base_ids)
        in_base = sum(1 for d in final_drivers if d in base_set)
        st.caption(
            f"Diagnóstico: **{in_base}/{len(final_drivers)}** IDs da lista final aparecem na base carregada "
            f"(isso não bloqueia nada)."
        )

    # =========================================================
    # 5) GERAÇÃO DOS ARQUIVOS
    # =========================================================
    prioridade_df = pd.DataFrame({"driver_id": final_drivers})
    prioridade_df["priority"] = "HIGH"

    reg_out = pd.DataFrame(
        {
            "driver_id": final_drivers,
            "reference_id": REGION_ID_SP,
            "type": "REGION",
            "enabled": "TRUE",
        }
    )

    sub_out = pd.DataFrame(
        [(d, sub_id) for d in final_drivers for sub_id in SUB_IDS_SP],
        columns=["driver_id", "reference_id"],
    )
    sub_out["type"] = "SUB_REGION"
    sub_out["enabled"] = "TRUE"

    elegibilidade_df = pd.concat([reg_out, sub_out], ignore_index=True)

    final_txt = "\n".join(final_drivers) + "\n"

    st.caption(
        f"Linhas no elegibilidade.csv: **{len(elegibilidade_df)}** "
        f"(≈ {1 + len(SUB_IDS_SP)} por driver da lista final)"
    )

    # =========================================================
    # 6) DOWNLOADS
    # =========================================================
    st.divider()
    st.subheader("Downloads")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.download_button(
            "⬇️ Baixar elegibilidade.csv",
            data=elegibilidade_df.to_csv(index=False).encode("utf-8"),
            file_name="elegibilidade.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with c2:
        st.download_button(
            "⬇️ Baixar prioridade.csv",
            data=prioridade_df.to_csv(index=False).encode("utf-8"),
            file_name="prioridade.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with c3:
        st.download_button(
            "⬇️ Baixar ativos_filtrados.txt",
            data=final_txt.encode("utf-8"),
            file_name="ativos_filtrados.txt",
            mime="text/plain",
            use_container_width=True,
        )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("elegibilidade.csv", elegibilidade_df.to_csv(index=False))
        z.writestr("prioridade.csv", prioridade_df.to_csv(index=False))
        z.writestr("ativos_filtrados.txt", final_txt)
    zip_buf.seek(0)

    st.download_button(
        "📦 Baixar ZIP (CSV + TXT limpo)",
        data=zip_buf.getvalue(),
        file_name="exports_elegibilidade_prioridade.zip",
        mime="application/zip",
        use_container_width=True,
    )

    # =========================================================
    # 7) PRÉVIA
    # =========================================================
    st.divider()
    st.subheader("Prévia")

    st.write("**Lista final de UUIDs**")
    st.dataframe(pd.DataFrame({"driver_id": final_drivers}).head(25), use_container_width=True)

    st.write("**elegibilidade.csv**")
    st.dataframe(elegibilidade_df.head(25), use_container_width=True)

    st.write("**prioridade.csv**")
    st.dataframe(prioridade_df.head(25), use_container_width=True)
