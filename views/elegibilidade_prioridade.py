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

    return {"valid": valid, "invalid": invalid, "duplicates": duplicates, "total_tokens": total_tokens}


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📦 Exportar CSV — Elegibilidade & Prioridade")


    st.subheader("1) Suba o TXT de ativos")
    uploaded = st.file_uploader(
        "Arquivo .txt (1 id por linha)",
        type=["txt"],
        accept_multiple_files=False,
        help="Dica: pode ter linhas vazias. Linha começando com # é ignorada.",
    )

    with st.expander("ou cole os IDs aqui (opcional)"):
        pasted = st.text_area(
            "Cole aqui (1 id por linha)",
            height=160,
        )

    txt = _decode_upload_to_text(uploaded) if uploaded is not None else (pasted or "")
    parsed = _parse_driver_ids_from_text(txt)

    drivers = parsed["valid"]
    invalid = parsed["invalid"]
    duplicates = parsed["duplicates"]
    total_tokens = parsed["total_tokens"]

    cA, cB, cC, cD = st.columns(4)
    with cA:
        st.metric("IDs no TXT (lidos)", total_tokens)
    with cB:
        st.metric("UUID válidos", len(drivers))
    with cC:
        st.metric("Inválidos (não UUID)", len(invalid))
    with cD:
        st.metric("Duplicados (ignorados)", duplicates)

    if not txt.strip():
        st.info("Suba (ou cole) o TXT de ativos pra liberar os downloads.")
        return

    if invalid:
        st.warning(
            "Tem coisa no TXT que **não é UUID**. Se isso entrar no CSV, o sistema interno pode explodir. "
            "Por padrão eu **ignoro** esses inválidos."
        )
        with st.expander("Ver exemplos de inválidos"):
            st.write(invalid[:200])

        # segurança: se sobrar 0 válido, não faz nada
        if not drivers:
            st.error("Depois de ignorar inválidos, **não sobrou nenhum UUID válido**. Corrige o TXT.")
            return

        # opcional: exigir confirmação pra seguir
        ok = st.checkbox("Ok, entendi — gerar CSV ignorando os inválidos", value=False)
        if not ok:
            st.info("Marque a caixinha acima pra liberar os downloads.")
            return

    if not drivers:
        st.info("Nenhum UUID válido encontrado no TXT.")
        return

    # checagem opcional: quantos do TXT aparecem na base (só pra diagnóstico)
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
        in_base = sum(1 for d in drivers if d in base_set)
        st.caption(
            f"Diagnóstico: **{in_base}/{len(drivers)}** IDs do TXT aparecem na base carregada (isso não bloqueia nada)."
        )

    # =========================
    # PRIORIDADE (1 linha por driver)
    # =========================
    prioridade_df = pd.DataFrame({"driver_id": drivers})
    prioridade_df["priority"] = "HIGH"

    # =========================
    # ELEGIBILIDADE (REGION + TODAS SUB_REGION)
    # =========================
    reg_out = pd.DataFrame(
        {
            "driver_id": drivers,
            "reference_id": REGION_ID_SP,
            "type": "REGION",
            "enabled": "TRUE",
        }
    )

    sub_out = pd.DataFrame(
        [(d, sub_id) for d in drivers for sub_id in SUB_IDS_SP],
        columns=["driver_id", "reference_id"],
    )
    sub_out["type"] = "SUB_REGION"
    sub_out["enabled"] = "TRUE"

    elegibilidade_df = pd.concat([reg_out, sub_out], ignore_index=True)

    st.caption(
        f"Linhas no elegibilidade.csv: **{len(elegibilidade_df)}** "
        f"(≈ {1 + len(SUB_IDS_SP)} por driver)"
    )

    # =========================
    # Downloads
    # =========================
    c1, c2 = st.columns(2)
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

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("elegibilidade.csv", elegibilidade_df.to_csv(index=False))
        z.writestr("prioridade.csv", prioridade_df.to_csv(index=False))
    zip_buf.seek(0)

    st.download_button(
        "📦 Baixar ZIP (2 CSV)",
        data=zip_buf.getvalue(),
        file_name="exports_elegibilidade_prioridade.zip",
        mime="application/zip",
        use_container_width=True,
    )

    st.divider()
    st.subheader("Prévia")
    st.write("**elegibilidade.csv**")
    st.dataframe(elegibilidade_df.head(25), use_container_width=True)
    st.write("**prioridade.csv**")
    st.dataframe(prioridade_df.head(25), use_container_width=True)
