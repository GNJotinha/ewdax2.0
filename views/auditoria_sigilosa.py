# views/auditoria_sigilosa.py
from datetime import date
import pandas as pd
import streamlit as st
from utils import normalizar
from auditoria_loader import load_operacional_from_drive, load_faturamento_from_drive

# ----------------- Senha super simples -----------------
def senha_por_formula(palavra_base: str) -> str:
    hoje = date.today()
    dia, mes = hoje.day, hoje.month
    valor = dia + mes
    return f"{str(palavra_base).strip()}@{valor}"

def _gate():
    st.subheader("🔐 Acesso sigiloso")
    st.caption("Padrão: <PALAVRA>@(dia+mês) — Ex.: 27/10 → Movee@37")

    palavra = st.secrets.get("SIGILOSO_PALAVRA", "Movee")
    entrada = st.text_input("Senha", type="password")

    if st.button("Validar", type="primary", use_container_width=True):
        esperada = senha_por_formula(palavra)
        if entrada and entrada.strip() == esperada:
            st.session_state["_sig_ok"] = True
            st.success("Acesso liberado.")
            st.rerun()
        else:
            st.error(f"Senha incorreta. (Dica: hoje seria {esperada})")

    if not st.session_state.get("_sig_ok", False):
        st.stop()

# ----------------- Carregamento e limpeza -----------------
def _prep_operacional(df: pd.DataFrame) -> pd.DataFrame:
    if "data_do_periodo" in df.columns:
        df["data"] = pd.to_datetime(df["data_do_periodo"], errors="coerce").dt.date
    else:
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    df["turno"] = df.get("periodo").astype(str) if "periodo" in df.columns else None
    df["ent_id"] = df.get("id_da_pessoa_entregadora", "").astype(str)
    df["ent_nome"] = df.get("pessoa_entregadora", "").astype(str)
    df["ent_norm"] = df["ent_nome"].apply(normalizar)
    df["valor_operacional"] = pd.to_numeric(df["soma_das_taxas_das_corridas_aceitas"], errors="coerce").fillna(0) / 100
    return df.groupby(["data","ent_id","ent_nome","turno"], dropna=False)["valor_operacional"].sum().reset_index()

def _prep_faturamento(df: pd.DataFrame) -> pd.DataFrame:
    date_col = None
    for c in ["data_do_periodo_de_referencia","data_do_periodo","data_do_lancamento_financeiro","data_do_repasse"]:
        if c in df.columns:
            date_col = c; break
    df["data"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    df["turno"] = df.get("periodo").astype(str) if "periodo" in df.columns else None
    df["ent_id"] = df.get("id_da_pessoa_entregadora", "").astype(str)
    df["ent_nome"] = df.get("recebedor", df.get("pessoa_entregadora", "")).astype(str)
    df["ent_norm"] = df["ent_nome"].apply(normalizar)
    df["valor_faturamento"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0)
    df = df[df["descricao"].astype(str).str.lower().str.contains("conclu")].copy()
    return df.groupby(["data","ent_id","ent_nome","turno"], dropna=False)["valor_faturamento"].sum().reset_index()

def _merge_and_compare(op: pd.DataFrame, fat: pd.DataFrame) -> pd.DataFrame:
    base = pd.merge(op, fat, on=["data","ent_id","turno"], how="outer", suffixes=("_op","_fat"))
    base["delta"] = base["valor_operacional"].fillna(0) - base["valor_faturamento"].fillna(0)
    mask = base["valor_faturamento"].fillna(0) != 0
    base["pct_diff"] = None
    base.loc[mask,"pct_diff"] = (base.loc[mask,"delta"]/base.loc[mask,"valor_faturamento"])*100
    return base

# ----------------- View -----------------
def render(_df_unused, _USUARIOS):
    st.header("🕵️ Auditoria Sigilosa — Operacional × Faturamento (Concluídas)")
    _gate()

    tol_pct = st.number_input("Tolerância %", 0.0, 100.0, 2.0)
    tol_abs = st.number_input("Tolerância R$", 0.0, 100.0, 1.0, format="%.2f")
    if st.button("Gerar comparação", type="primary", use_container_width=True):

        with st.spinner("Baixando planilhas do Drive..."):
            op = _prep_operacional(load_operacional_from_drive())
            fa = _prep_faturamento(load_faturamento_from_drive())
            base = _merge_and_compare(op, fa)

        if base.empty:
            st.info("Nenhum dado encontrado.")
            st.stop()

        base["flag"] = (base["delta"].abs() > tol_abs) | (base["pct_diff"].abs() > tol_pct)

        tot_op = base["valor_operacional"].sum()
        tot_fa = base["valor_faturamento"].sum()
        delta = tot_op - tot_fa
        pct = (delta / tot_fa * 100) if tot_fa else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Operacional (R$)", f"{tot_op:,.2f}".replace(",", "."))
        m2.metric("Faturamento (R$)", f"{tot_fa:,.2f}".replace(",", "."))
        m3.metric("Δ (R$)", f"{delta:,.2f}".replace(",", "."))
        m4.metric("Δ% x Fat", f"{pct:.2f}%".replace(".", ","))

        vis = base[["data","ent_nome","turno","valor_operacional","valor_faturamento","delta","pct_diff","flag"]]
        vis.rename(columns={
            "data":"Data","ent_nome":"Entregador","turno":"Turno",
            "valor_operacional":"Operacional (R$)","valor_faturamento":"Faturamento (R$)",
            "delta":"Δ (R$)","pct_diff":"Δ%","flag":"⚑"
        }, inplace=True)

        st.dataframe(vis.style.format({
            "Operacional (R$)":"{:.2f}",
            "Faturamento (R$)":"{:.2f}",
            "Δ (R$)":"{:.2f}",
            "Δ%":"{:.2f}"
        }), use_container_width=True)

        st.download_button("⬇️ Baixar CSV", vis.to_csv(index=False).encode("utf-8"),
                           file_name="auditoria_operacional_vs_faturamento.csv", mime="text/csv")
