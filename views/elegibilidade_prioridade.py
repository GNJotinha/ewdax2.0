import io
import zipfile
import re
import pandas as pd
import streamlit as st


# =========================
# IDs fixos (SP)
# =========================
REGION_ID_SP = "3841c245-fac1-40a6-8b8f-8d6876447a6d

SUB_IDS_SP = [
    "c838bd2d-5be4-401a-8ad2-b9d6a9d87a58",  # PERDIZES - SP
    "04c47ecb-c69d-43f6-b4be-49c21afc0e7b",  # INTERLAGOS - SP
    "0340dc65-ce67-416b-b114-07cc468c290d",  # PANAMBY E VILA SONIA - SP
    "ff380776-9d85-403d-9214-068c6eba6d09",  # PINHEIROS - SP
    "6934118f-3fb0-4acd-962b-e9bb68c3699c",  # ITAIM E BROOKLIN E INDIANAPOLIS - SP
    "98aafe66-f452-4e64-b323-05e17831f325",  # CAMPO BELO (MINI BTU FD)
    "87791f8f-9c75-4119-b5fa-9b6bd949fb6a",  # ACLIMACAO - SP
    "4e14aa79-7fdb-4299-94ba-b35e12128288",  # JARDINS (MINI BTU FD)
    "695dfbe5-bd3a-4e2b-a654-8b8af0eeba8b",  # JABAQUARA E SANTO AMARO - SP
]


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _parse_driver_ids_from_text(txt: str) -> list[str]:
    """Parseia um TXT com **1 id por linha**.

    Regras (pra não virar zona):
      - ignora linha vazia
      - ignora comentários: linha começando com #
      - remove espaços
      - dedup preservando ordem
      - normaliza pra lowercase
    """
    if not txt:
        return []

    out: list[str] = []
    seen: set[str] = set()

    for raw in txt.splitlines():
        line = (raw or "").strip()
        if not line:
            continue
        if line.startswith("#"):
            continue

        driver_id = line.split()[0].strip().lower()
        if not driver_id:
            continue
        if driver_id in seen:
            continue
        seen.add(driver_id)
        out.append(driver_id)

    return out


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


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📦 Exportar CSV — Elegibilidade & Prioridade")

    st.write(
        "Aqui a **fonte da verdade** é o TXT de ativos (1 `driver_id` por linha). "
        "Se o cara saiu, ele não tá no TXT — e aí você não gera CSV com ID fantasma (que dá pau no sistema interno)."
    )

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
            placeholder="3841c245-fac1-40a6-8b8f-8d6876447a6d\n...",
        )

    txt = _decode_upload_to_text(uploaded) if uploaded is not None else (pasted or "")
    drivers = _parse_driver_ids_from_text(txt)

    cA, cB, cC = st.columns(3)
    with cA:
        st.metric("Drivers no TXT", len(drivers))
    with cB:
        invalid = [d for d in drivers if not _UUID_RE.match(d)]
        st.metric("IDs fora do padrão UUID", len(invalid))
    with cC:
        st.metric("SUB_REGION por driver", len(SUB_IDS_SP))

    if invalid:
        st.warning(
            "Tem ID no TXT que **não parece UUID**. Se o sistema interno exigir UUID, isso pode dar merda. "
            f"Exemplos: {', '.join(invalid[:5])}" + (" …" if len(invalid) > 5 else "")
        )

    if not drivers:
        st.info("Suba (ou cole) o TXT de ativos pra liberar os downloads.")

        # modo antigo fica escondido — só pra emergência
        with st.expander("⚠️ Emergência: gerar pela base (modo antigo)"):
            st.caption(
                "Isso volta a regra velha (>= 2 completadas em 7 dias) e **pode incluir ex-entregador**, "
                "ou seja: pode voltar o erro no sistema interno."
            )
            usar_base = st.toggle("Usar modo antigo agora", value=False)

            if usar_base:
                if df is None or df.empty:
                    st.error("Sem base carregada. Não dá pra usar o modo antigo.")
                    return

                for col in ("data_do_periodo", "uuid", "numero_de_corridas_completadas"):
                    if col not in df.columns:
                        st.error(f"Coluna obrigatória ausente: '{col}'")
                        return

                base = df.copy()
                base["data_do_periodo"] = pd.to_datetime(base["data_do_periodo"], errors="coerce")
                base = base.dropna(subset=["data_do_periodo"]).copy()
                base["dia"] = base["data_do_periodo"].dt.normalize()

                base["uuid"] = base["uuid"].astype(str).fillna("").str.strip()
                base = base[base["uuid"] != ""].copy()

                base["numero_de_corridas_completadas"] = pd.to_numeric(
                    base["numero_de_corridas_completadas"], errors="coerce"
                ).fillna(0)

                fim = base["dia"].max()
                inicio = fim - pd.Timedelta(days=6)
                st.caption(
                    f"Período considerado: **{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}** (7 dias)"
                )

                recorte = base[(base["dia"] >= inicio) & (base["dia"] <= fim)].copy()
                if recorte.empty:
                    st.info("Sem dados no período.")
                    return

                tot = recorte.groupby("uuid")["numero_de_corridas_completadas"].sum()
                drivers = sorted(tot[tot >= 2].index.astype(str).tolist())
                st.metric("Drivers elegíveis (>= 2 em 7 dias)", len(drivers))

        if not drivers:
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
    reg_out = pd.DataFrame({
        "driver_id": drivers,
        "reference_id": REGION_ID_SP,
        "type": "REGION",
        "enabled": "TRUE",
    })

    sub_out = pd.DataFrame(
        [(d, sub_id) for d in drivers for sub_id in SUB_IDS_SP],
        columns=["driver_id", "reference_id"],
    )
    sub_out["type"] = "SUB_REGION"
    sub_out["enabled"] = "TRUE"

    elegibilidade_df = pd.concat([reg_out, sub_out], ignore_index=True)

    st.caption(f"Linhas no elegibilidade.csv: **{len(elegibilidade_df)}** (≈ {1+len(SUB_IDS_SP)} por driver)")

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
