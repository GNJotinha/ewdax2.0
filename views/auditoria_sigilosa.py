# views/auditoria_sigilosa.py
from datetime import date
import pandas as pd
import streamlit as st

from auditoria_loader import (
    load_operacional_from_drive,
    load_faturamento_from_drive,
)

# ----------------- Gate de senha (simples) -----------------
def senha_por_formula(palavra_base: str) -> str:
    """
    Senha = <PALAVRA>@(dia+mês)
    Ex.: 27/10 -> Movee@37
    """
    hoje = date.today()
    return f"{str(palavra_base).strip()}@{hoje.day + hoje.month}"

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

# ----------------- Preparação dos dataframes -----------------
def _prep_operacional(df: pd.DataFrame) -> pd.DataFrame:
    """
    Espera colunas mínimas do operacional:
      - data_do_periodo OU data
      - periodo
      - id_da_pessoa_entregadora
      - pessoa_entregadora
      - soma_das_taxas_das_corridas_aceitas (em centavos)
    Retorna agregado por (data, ent_id, ent_nome, turno) com VLROP (R$).
    """
    # data
    if "data_do_periodo" in df.columns:
        df["data"] = pd.to_datetime(df["data_do_periodo"], errors="coerce").dt.date
    else:
        df["data"] = pd.to_datetime(df.get("data"), errors="coerce").dt.date

    # turno, id e nome
    df["turno"] = df.get("periodo")
    df["ent_id"] = df.get("id_da_pessoa_entregadora")
    df["ent_nome"] = df.get("pessoa_entregadora")

    # valor aceitas (centavos → reais)
    col_val = "soma_das_taxas_das_corridas_aceitas"
    if col_val not in df.columns:
        st.error(f"Coluna ausente no operacional: {col_val}")
        st.stop()

    df["valor_operacional"] = pd.to_numeric(df[col_val], errors="coerce").fillna(0) / 100.0

    grp = (
        df.groupby(["data", "ent_id", "ent_nome", "turno"], dropna=False)["valor_operacional"]
          .sum()
          .reset_index()
          .rename(columns={"valor_operacional": "VLROP"})
    )
    return grp

def _prep_faturamento(df: pd.DataFrame) -> pd.DataFrame:
    """
    Espera colunas mínimas do faturamento:
      - uma das datas: data_do_periodo_de_referencia | data_do_periodo | data_do_lancamento_financeiro | data_do_repasse
      - periodo
      - id_da_pessoa_entregadora
      - recebedor ou pessoa_entregadora
      - valor (R$)
      - descricao (texto) -> filtramos "conclu"
    Retorna agregado por (data, ent_id, ent_nome, turno) com VLRFAT (R$).
    """
    # data referência
    date_col = None
    for c in ["data_do_periodo_de_referencia", "data_do_periodo", "data_do_lancamento_financeiro", "data_do_repasse"]:
        if c in df.columns:
            date_col = c
            break
    if not date_col:
        st.error("Nenhuma coluna de data na aba Base do FATURAMENTO.")
        st.stop()

    df["data"] = pd.to_datetime(df[date_col], errors="coerce").dt.date

    # turno, id e nome
    df["turno"] = df.get("periodo")
    df["ent_id"] = df.get("id_da_pessoa_entregadora")
    nome = df.get("recebedor")
    if nome is None or (isinstance(nome, pd.Series) and nome.isna().all()):
        nome = df.get("pessoa_entregadora", "")
    df["ent_nome"] = nome.astype(str) if isinstance(nome, pd.Series) else str(nome)

    # valor + filtro concluídas
    if "valor" not in df.columns:
        st.error("Coluna 'valor' ausente no FATURAMENTO.")
        st.stop()
    if "descricao" not in df.columns:
        st.error("Coluna 'descricao' ausente no FATURAMENTO.")
        st.stop()

    df = df[df["descricao"].astype(str).str.lower().str.contains("conclu")].copy()
    df["VLRFAT"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)

    grp = (
        df.groupby(["data", "ent_id", "ent_nome", "turno"], dropna=False)["VLRFAT"]
          .sum()
          .reset_index()
    )
    return grp

def _merge_oper_fat(op: pd.DataFrame, fat: pd.DataFrame) -> pd.DataFrame:
    """
    Merge por (data, ent_id, turno). Mantemos ent_nome de ambos para seleção por nome.
    """
    base = pd.merge(
        op, fat,
        on=["data", "ent_id", "turno"],
        how="outer",
        suffixes=("_op", "_fat")
    )
    # Entregador: preferir nome do operacional; se NaN, usar do faturamento
    base["ent_nome"] = base["ent_nome_op"].fillna(base["ent_nome_fat"])
    return base[["data", "ent_id", "ent_nome", "turno", "VLROP", "VLRFAT"]]

# ----------------- View -----------------
def render(_df_unused: pd.DataFrame, _USUARIOS: dict):
    st.header("🕵️ Auditoria Sigilosa — Operacional × Faturamento (Concluídas)")
    _gate()

    # Controles de atualização
    cols = st.columns([1, 1])
    refresh = cols[0].button("🔄 Atualizar do Drive", use_container_width=True)

    # Carrega do Drive (rápido com cache) e prepara
    with st.spinner("Baixando planilhas do Drive..."):
        raw_op = load_operacional_from_drive(force=refresh)
        raw_fa = load_faturamento_from_drive(force=refresh)

        op = _prep_operacional(raw_op)
        fa = _prep_faturamento(raw_fa)
        base = _merge_oper_fat(op, fa)

    if base.empty:
        st.info("Nenhum dado encontrado.")
        st.stop()

    # Filtro de período
    base["data_ts"] = pd.to_datetime(base["data"], errors="coerce")
    min_d, max_d = base["data_ts"].min().date(), base["data_ts"].max().date()
    periodo = st.date_input(
        "Período:",
        (min_d, max_d),
        min_value=min_d,
        max_value=max_d,
        format="DD/MM/YYYY",
    )
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        base = base[
            (base["data_ts"] >= pd.to_datetime(periodo[0])) &
            (base["data_ts"] <= pd.to_datetime(periodo[1]))
        ]

    # Escolha do entregador (por nome)
    nomes = sorted([n for n in base["ent_nome"].dropna().unique()])
    nome = st.selectbox(
        "Entregador",
        [None] + nomes,
        index=0,
        format_func=lambda x: "" if x is None else x
    )
    if not nome:
        st.info("Selecione um entregador para ver a lista.")
        st.stop()

    df_sel = base[base["ent_nome"] == nome].copy()

    # Lista no formato pedido: DATA | TURNO | VLROP | VLRFAT
    saida = (
        df_sel.groupby(["data", "turno"], dropna=False)
              .agg(VLROP=("VLROP", "sum"), VLRFAT=("VLRFAT", "sum"))
              .reset_index()
              .sort_values(["data", "turno"], ascending=[True, True])
              .rename(columns={"data": "DATA", "turno": "TURNO"})
    )

    st.subheader(f"Lista — {nome}")
    st.dataframe(
        saida[["DATA", "TURNO", "VLROP", "VLRFAT"]]
             .assign(VLROP=lambda d: d["VLROP"].round(2),
                     VLRFAT=lambda d: d["VLRFAT"].round(2))
             .style.format({"VLROP": "{:.2f}", "VLRFAT": "{:.2f}"}),
        use_container_width=True
    )

    st.download_button(
        "⬇️ Baixar CSV",
        saida[["DATA", "TURNO", "VLROP", "VLRFAT"]].to_csv(index=False).encode("utf-8"),
        file_name=f"auditoria_{nome.replace(' ', '_')}.csv",
        mime="text/csv",
        use_container_width=True
    )
