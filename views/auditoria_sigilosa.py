# views/auditoria_sigilosa.py
from datetime import date
import pandas as pd
import streamlit as st

from auditoria_loader import (
    load_operacional_from_drive,
    load_faturamento_from_drive,
)

# =======================
# Estilo (opcional)
# =======================
st.markdown("""
<style>
details[open] summary { border-bottom: 1px solid #2d333b; }
details { border: 1px solid #2d333b; border-radius: 8px; padding: 4px 8px; }
summary { font-weight: 600; }
section[data-testid="stSelectbox"] > div { background: #161b22 !important; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# =======================
# Gate: senha PALAVRA@(dia*mes)
# =======================
def senha_por_formula(palavra_base: str) -> str:
    hoje = date.today()
    dia, mes = hoje.day, hoje.month
    valor = dia * mes
    return f"{str(palavra_base).strip()}@{valor}"

def _gate():
    st.subheader("Acesso restrito")
    palavra = st.secrets.get("SIGILOSO_PALAVRA", "Movee")
    entrada = st.text_input("Senha", type="password")
    if st.button("Validar", type="primary", use_container_width=True):
        esperada = senha_por_formula(palavra)
        if entrada and entrada.strip() == esperada:
            st.session_state["_sig_ok"] = True
            st.success("Acesso liberado.")
            st.rerun()
        else:
            st.error("Senha incorreta.")
    if not st.session_state.get("_sig_ok", False):
        st.stop()

# =======================
# Helpers de preparo
# =======================
def _prep_operacional(df: pd.DataFrame) -> pd.DataFrame:
    """
    Espera colunas do loader enxuto:
      data, periodo, id_da_pessoa_entregadora, pessoa_entregadora,
      soma_das_taxas_das_corridas_aceitas
    """
    df = df.copy()
    df["turno"] = df.get("periodo").astype(str) if "periodo" in df.columns else None
    df["ent_id"] = df.get("id_da_pessoa_entregadora", "").astype(str)
    df["ent_nome"] = df.get("pessoa_entregadora", "").astype(str)
    df["valor_operacional"] = pd.to_numeric(
        df.get("soma_das_taxas_das_corridas_aceitas"), errors="coerce"
    ).fillna(0) / 100.0
    grp = (
        df.groupby(["data", "ent_id", "ent_nome", "turno"], dropna=False)["valor_operacional"]
          .sum()
          .reset_index()
    )
    return grp

def _prep_faturamento(df: pd.DataFrame) -> pd.DataFrame:
    """
    Espera colunas do loader enxuto:
      data, periodo, id_da_pessoa_entregadora, ent_nome, valor, descricao
    Filtra somente 'conclu' e agrega por data/entregador/turno.
    """
    df = df.copy()
    df["turno"] = df.get("periodo").astype(str) if "periodo" in df.columns else None
    df["ent_id"] = df.get("id_da_pessoa_entregadora", "").astype(str)
    df["ent_nome"] = df.get("ent_nome", "").astype(str)
    df["valor"] = pd.to_numeric(df.get("valor"), errors="coerce").fillna(0.0)
    df = df[df.get("descricao", "").astype(str).str.lower().str.contains("conclu", na=False)].copy()
    grp = (
        df.groupby(["data", "ent_id", "ent_nome", "turno"], dropna=False)["valor"]
          .sum()
          .reset_index()
          .rename(columns={"valor": "valor_faturamento"})
    )
    return grp

def _merge_all(op: pd.DataFrame, fa: pd.DataFrame) -> pd.DataFrame:
    """
    Merge por (data, ent_id, turno). Corrige 'ent_nome' preferindo o que existir.
    """
    base = pd.merge(
        op, fa,
        on=["data", "ent_id", "turno"],
        how="outer",
        suffixes=("_op", "_fat")
    )

    # preferir nome do op; se vazio/NaN, usar nome do fat
    if "ent_nome_op" in base.columns or "ent_nome_fat" in base.columns:
        name_op = base.get("ent_nome_op")
        name_fat = base.get("ent_nome_fat")
        if name_op is None:
            base["ent_nome"] = name_fat
        elif name_fat is None:
            base["ent_nome"] = name_op
        else:
            base["ent_nome"] = name_op.where(
                name_op.notna() & (name_op.astype(str).str.strip() != ""), name_fat
            )
        base.drop(columns=[c for c in ["ent_nome_op", "ent_nome_fat"] if c in base.columns], inplace=True)
    else:
        base["ent_nome"] = base.get("ent_nome")

    base["valor_operacional"] = pd.to_numeric(base.get("valor_operacional"), errors="coerce").fillna(0.0)
    base["valor_faturamento"] = pd.to_numeric(base.get("valor_faturamento"), errors="coerce").fillna(0.0)
    base["delta"] = base["valor_operacional"] - base["valor_faturamento"]
    return base

# =======================
# View
# =======================
def render(_df_unused: pd.DataFrame, _USUARIOS: dict):
    st.header("Acesso restrito")
    _gate()

    # Atualização de base
    col_a, col_b = st.columns([1, 3])
    refresh = col_a.button("🔄 Atualizar do Drive", use_container_width=True)

    with st.spinner("Carregando bases..."):
        raw_op = load_operacional_from_drive(force=refresh)
        raw_fa = load_faturamento_from_drive(force=refresh)
        op = _prep_operacional(raw_op)
        fa = _prep_faturamento(raw_fa)
        base = _merge_all(op, fa)

    if base.empty:
        st.info("Sem dados.")
        st.stop()

    # Menu de modos (expander estilo sistema)
    with st.expander("📂 Modos", expanded=False):
        modo = st.selectbox(
            "Selecione um modo",
            ["Lista por entregador", "Lista geral (todos)"],
            index=0
        )

    # Filtro de período global
    min_d, max_d = base["data"].min(), base["data"].max()
    periodo = st.date_input(
        "Período:", (min_d, max_d), min_value=min_d, max_value=max_d, format="DD/MM/YYYY"
    )
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        d0, d1 = pd.to_datetime(periodo[0]).date(), pd.to_datetime(periodo[1]).date()
        base = base[(base["data"] >= d0) & (base["data"] <= d1)]

    # ----------------- Modo: Lista por entregador -----------------
    if modo == "Lista por entregador":
        nomes = sorted(pd.Series(base["ent_nome"]).dropna().unique().tolist())
        nome = st.selectbox("Entregador", [None] + nomes, format_func=lambda x: "" if x is None else x, index=0)

        if not nome:
            st.info("Selecione um entregador para ver a lista.")
            st.stop()

        df_sel = base[base["ent_nome"] == nome].copy()
        saida = (
            df_sel.groupby(["data", "turno"], dropna=False)
                  .agg(VLROP=("valor_operacional", "sum"),
                       VLRFAT=("valor_faturamento", "sum"))
                  .reset_index()
        )
        saida["DELTA"] = saida["VLROP"] - saida["VLRFAT"]
        saida = saida.sort_values(["data", "turno"]).reset_index(drop=True)
        saida.rename(columns={"data": "DATA", "turno": "TURNO"}, inplace=True)

        vis = saida[["DATA", "TURNO", "VLROP", "VLRFAT", "DELTA"]].copy()
        for c in ["VLROP", "VLRFAT", "DELTA"]:
            vis[c] = vis[c].round(2)
        st.subheader(f"Lista — {nome}")
        st.dataframe(vis, use_container_width=True)

        st.download_button(
            "⬇️ Baixar CSV",
            vis.to_csv(index=False).encode("utf-8"),
            file_name=f"auditoria_{nome.replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True
        )

    # ----------------- Modo: Lista geral (todos) -----------------
    else:
        saida = (
            base.groupby(["data", "ent_nome", "turno"], dropna=False)
                .agg(VLROP=("valor_operacional", "sum"),
                     VLRFAT=("valor_faturamento", "sum"))
                .reset_index()
        )
        saida["DELTA"] = saida["VLROP"] - saida["VLRFAT"]
        saida = saida.sort_values(["data", "ent_nome", "turno"]).reset_index(drop=True)
        saida.rename(columns={"data": "DATA", "ent_nome": "ENTREGADOR", "turno": "TURNO"}, inplace=True)

        only_diff = st.checkbox("Mostrar só divergências (DELTA ≠ 0)", value=False)
        if only_diff:
            saida = saida[saida["DELTA"].round(2) != 0]

        vis = saida[["DATA", "ENTREGADOR", "TURNO", "VLROP", "VLRFAT", "DELTA"]].copy()
        for c in ["VLROP", "VLRFAT", "DELTA"]:
            vis[c] = vis[c].round(2)
        st.subheader("Lista geral")
        st.dataframe(vis, use_container_width=True)

        st.download_button(
            "⬇️ Baixar CSV (geral)",
            vis.to_csv(index=False).encode("utf-8"),
            file_name="auditoria_geral.csv",
            mime="text/csv",
            use_container_width=True
        )
