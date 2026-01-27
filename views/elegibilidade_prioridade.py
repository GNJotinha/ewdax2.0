# views/elegibilidade_prioridade.py
import io
import zipfile
import pandas as pd
import streamlit as st


# =========================
# MAPEAMENTOS (colados do seu envio)
# =========================
REGION_IDS = {
    "SAO PAULO": "3841c245-fac1-40a6-8b8f-8d6876447a6d",
}

SUB_REGION_IDS = {
    "PERDIZES - SP": "c838bd2d-5be4-401a-8ad2-b9d6a9d87a58",
    "INTERLAGOS - SP": "04c47ecb-c69d-43f6-b4be-49c21afc0e7b",
    "PANAMBY E VILA SONIA - SP": "0340dc65-ce67-416b-b114-07cc468c290d",
    "PINHEIROS - SP": "ff380776-9d85-403d-9214-068c6eba6d09",
    "ITAIM E BROOKLIN E INDIANAPOLIS - SP": "6934118f-3fb0-4acd-962b-e9bb68c3699c",
    "SAO PAULO - CAMPO BELO - (MINI BTU FD)": "98aafe66-f452-4e64-b323-05e17831f325",
    "ACLIMACAO - SP": "87791f8f-9c75-4119-b5fa-9b6bd949fb6a",
    "SAO PAULO - JARDINS - (MINI BTU FD)": "4e14aa79-7fdb-4299-94ba-b35e12128288",
    "JABAQUARA E SANTO AMARO - SP": "695dfbe5-bd3a-4e2b-a654-8b8af0eeba8b",
}


def _k(x) -> str:
    # normaliza chave pra bater com variações de espaço/caixa
    return " ".join(str(x).strip().upper().split())


REGION_IDS_N = {_k(k): v for k, v in REGION_IDS.items()}
SUB_REGION_IDS_N = {_k(k): v for k, v in SUB_REGION_IDS.items()}


def _as_true_str(_: int) -> str:
    return "TRUE"


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🧾 Exportar CSV — Elegibilidade & Prioridade")

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        st.stop()

    base = df.copy()

    # data base
    if "data_do_periodo" not in base.columns:
        st.error("Coluna 'data_do_periodo' não existe na base.")
        st.stop()

    base["data_do_periodo"] = pd.to_datetime(base["data_do_periodo"], errors="coerce")
    base = base.dropna(subset=["data_do_periodo"])
    if base.empty:
        st.info("Sem datas válidas na base.")
        st.stop()

    # colunas essenciais
    for col in ("uuid", "praca", "sub_praca", "numero_de_corridas_completadas"):
        if col not in base.columns:
            st.error(f"Coluna obrigatória ausente: '{col}'")
            st.stop()

    base["uuid"] = base["uuid"].astype(str).fillna("").str.strip()
    base = base[base["uuid"] != ""].copy()

    base["numero_de_corridas_completadas"] = pd.to_numeric(
        base["numero_de_corridas_completadas"], errors="coerce"
    ).fillna(0)

    # janela 7 dias (inclui o último dia da base)
    base["dia"] = base["data_do_periodo"].dt.normalize()
    fim = base["dia"].max()
    inicio = fim - pd.Timedelta(days=6)

    st.caption(f"Período considerado: **{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}** (7 dias)")

    recorte = base[(base["dia"] >= inicio) & (base["dia"] <= fim)].copy()
    if recorte.empty:
        st.info("Sem dados no período.")
        st.stop()

    # quem fez >= 2 completas no período
    compl = recorte.groupby("uuid", as_index=True)["numero_de_corridas_completadas"].sum()
    elegiveis = compl[compl >= 2].index.astype(str).tolist()

    st.metric("Drivers elegíveis (>=2 completas em 7 dias)", len(elegiveis))

    if not elegiveis:
        st.info("Ninguém bateu o critério no período.")
        st.stop()

    recorte_e = recorte[recorte["uuid"].isin(elegiveis)].copy()

    # =========================
    # CSV PRIORIDADE
    # =========================
    prioridade_df = (
        pd.DataFrame({"driver_id": sorted(set(elegiveis))})
        .assign(priority="HIGH")
    )

    # =========================
    # CSV ELEGIBILIDADE
    # =========================
    # REGION
    reg_pairs = recorte_e[["uuid", "praca"]].dropna().drop_duplicates()
    reg_pairs["praca_n"] = reg_pairs["praca"].map(_k)
    reg_pairs["reference_id"] = reg_pairs["praca_n"].map(REGION_IDS_N)

    reg_missing = reg_pairs[reg_pairs["reference_id"].isna()]["praca"].dropna().unique().tolist()
    if reg_missing:
        st.warning(f"⚠️ Praça sem UUID mapeado (vou ignorar no CSV): {sorted(map(str, reg_missing))}")

    reg_out = reg_pairs.dropna(subset=["reference_id"]).copy()
    reg_out = reg_out.rename(columns={"uuid": "driver_id"})[["driver_id", "reference_id"]]
    reg_out["type"] = "REGION"
    reg_out["enabled"] = "TRUE"

    # SUB_REGION
    sub_pairs = recorte_e[["uuid", "sub_praca"]].dropna().drop_duplicates()
    sub_pairs["sub_n"] = sub_pairs["sub_praca"].map(_k)
    sub_pairs["reference_id"] = sub_pairs["sub_n"].map(SUB_REGION_IDS_N)

    sub_missing = sub_pairs[sub_pairs["reference_id"].isna()]["sub_praca"].dropna().unique().tolist()
    if sub_missing:
        st.warning(f"⚠️ Subpraça sem UUID mapeado (vou ignorar no CSV): {sorted(map(str, sub_missing))}")

    sub_out = sub_pairs.dropna(subset=["reference_id"]).copy()
    sub_out = sub_out.rename(columns={"uuid": "driver_id"})[["driver_id", "reference_id"]]
    sub_out["type"] = "SUB_REGION"
    sub_out["enabled"] = "TRUE"

    elegibilidade_df = pd.concat([reg_out, sub_out], ignore_index=True)
    elegibilidade_df = elegibilidade_df.drop_duplicates().sort_values(["driver_id", "type", "reference_id"])

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

    # (melhoria) ZIP com os dois
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
    st.subheader("Prévia (primeiras linhas)")
    st.write("**elegibilidade.csv**")
    st.dataframe(elegibilidade_df.head(30), use_container_width=True)
    st.write("**prioridade.csv**")
    st.dataframe(prioridade_df.head(30), use_container_width=True)
