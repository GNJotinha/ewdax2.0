import io
import zipfile
import pandas as pd
import streamlit as st


# =========================
# IDs fixos (SP)
# =========================
REGION_ID_SP = "3841c245-fac1-40a6-8b8f-8d6876447a6d"

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


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📦 Exportar CSV — Elegibilidade & Prioridade")

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    # validações
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

    # janela: últimos 7 dias incluindo o último dia disponível na base (normalmente "ontem")
    fim = base["dia"].max()
    inicio = fim - pd.Timedelta(days=6)
    st.caption(f"Período considerado: **{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}** (7 dias)")

    recorte = base[(base["dia"] >= inicio) & (base["dia"] <= fim)].copy()
    if recorte.empty:
        st.info("Sem dados no período.")
        return

    # critério: >= 2 rotas (usando completadas como proxy)
    tot = recorte.groupby("uuid")["numero_de_corridas_completadas"].sum()
    drivers = sorted(tot[tot >= 2].index.astype(str).tolist())

    st.metric("Drivers elegíveis (>= 2 em 7 dias)", len(drivers))
    if not drivers:
        st.info("Ninguém bateu o critério no período.")
        return

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
