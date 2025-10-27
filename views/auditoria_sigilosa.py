# views/auditoria_sigilosa.py
from datetime import date
import pandas as pd
import streamlit as st

from utils import normalizar
from auditoria_loader import (
    load_operacional_from_drive,
    load_faturamento_from_drive,
)

# ----------------- Senha super simples -----------------
def senha_por_formula(palavra_base: str) -> str:
    """
    Senha = <PALAVRA>@(dia+mês)
    Ex.: 27/10 -> Movee@37
    """
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

# ----------------- Preparação dos dataframes -----------------
def _prep_operacional(df: pd.DataFrame) -> pd.DataFrame:
    # data
    if "data_do_periodo" in df.columns:
        df["data"] = pd.to_datetime(df["data_do_periodo"], errors="coerce").dt.date
    else:
        df["data"] = pd.to_datetime(df.get("data"), errors="coerce").dt.date

    # turno
    df["turno"] = df.get("periodo").astype(str) if "periodo" in df.columns else None

    # entregador
    df["ent_id"] = df.get("id_da_pessoa_entregadora", "").astype(str)
    df["ent_nome"] = df.get("pessoa_entregadora", "").astype(str)
    df["ent_norm"] = df["ent_nome"].apply(normalizar)

    # valor aceitas (centavos → reais)
    col_val = "soma_das_taxas_das_corridas_aceitas"
    if col_val not in df.columns:
        st.error(f"Coluna ausente no operacional: {col_val}")
        st.stop()
    df[col_val] = pd.to_numeric(df[col_val], errors="coerce").fillna(0)
    df["valor_operacional"] = df[col_val] / 100.0

    # agrega por dia/entregador/turno
    grp = (
        df.groupby(["data", "ent_id", "ent_norm", "ent_nome", "turno"], dropna=False)
          .agg(valor_operacional=("valor_operacional", "sum"))
          .reset_index()
    )
    return grp

def _prep_faturamento(df: pd.DataFrame) -> pd.DataFrame:
    # data referência
    date_col = None
    for c in ["data_do_periodo_de_referencia", "data_do_periodo", "data_do_lancamento_financeiro", "data_do_repasse"]:
        if c in df.columns:
            date_col = c; break
    if not date_col:
        st.error("Nenhuma coluna de data na aba Base do FATURAMENTO.")
        st.stop()
    df["data"] = pd.to_datetime(df[date_col], errors="coerce").dt.date

    # turno
    df["turno"] = df.get("periodo").astype(str) if "periodo" in df.columns else None

    # entregador
    df["ent_id"] = df.get("id_da_pessoa_entregadora", "").astype(str)
    nome_col = "recebedor" if "recebedor" in df.columns else ("pessoa_entregadora" if "pessoa_entregadora" in df.columns else None)
    df["ent_nome"] = df[nome_col].astype(str) if nome_col else ""
    df["ent_norm"] = df["ent_nome"].apply(normalizar)

    # valor (reais) + filtro concluídas
    if "valor" not in df.columns:
        st.error("Coluna 'valor' ausente no FATURAMENTO.")
        st.stop()
    if "descricao" not in df.columns:
        st.error("Coluna 'descricao' ausente no FATURAMENTO.")
        st.stop()
    df["valor_faturamento"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df = df[df["descricao"].astype(str).str.lower().str.contains("conclu")].copy()

    # agrega por dia/entregador/turno
    grp = (
        df.groupby(["data", "ent_id", "ent_norm", "ent_nome", "turno"], dropna=False)
          .agg(valor_faturamento=("valor_faturamento", "sum"))
          .reset_index()
    )
    return grp

# ----------------- Merge -----------------
def _merge_oper_fat(op: pd.DataFrame, fat: pd.DataFrame) -> pd.DataFrame:
    """
    Merge principal por (data, ent_id, turno). Se algum lado não tiver ent_id,
    ainda assim teremos os valores por nome (pois agregamos com ent_nome junto),
    mas o merge base aqui é por ID pra reduzir falsos positivos.
    """
    base = pd.merge(op, fat, on=["data", "ent_id", "turno"], how="outer", suffixes=("_op", "_fat"))

    # Se quiser fallback por nome normalizado quando ent_id estiver vazio em ambos os lados,
    # dá pra implementar; mas como você pediu só a lista por entregador selecionado,
    # vamos filtrar depois por ent_nome diretamente.
    return base

# ----------------- View -----------------
def render(_df_unused: pd.DataFrame, _USUARIOS: dict):
    st.header("🕵️ Auditoria Sigilosa — Operacional × Faturamento (Concluídas)")
    _gate()

    # Baixa do Drive e prepara
    with st.spinner("Baixando planilhas do Drive..."):
        raw_op = load_operacional_from_drive()
        raw_fa = load_faturamento_from_drive()
        op = _prep_operacional(raw_op)   # agrega por data/entregador/turno
        fa = _prep_faturamento(raw_fa)  # agrega por data/entregador/turno
        base = _merge_oper_fat(op, fa)

    if base.empty:
        st.info("Nenhum dado encontrado.")
        st.stop()

    # Filtros de período
    base["data_ts"] = pd.to_datetime(base["data"], errors="coerce")
    min_d, max_d = base["data_ts"].min().date(), base["data_ts"].max().date()
    periodo = st.date_input("Período:", (min_d, max_d), min_value=min_d, max_value=max_d, format="DD/MM/YYYY")
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        base = base[(base["data_ts"] >= pd.to_datetime(periodo[0])) & (base["data_ts"] <= pd.to_datetime(periodo[1]))]

    # Escolha do entregador
    nomes = sorted([n for n in pd.concat([base["ent_nome"]], ignore_index=True).dropna().unique()])
    nome = st.selectbox("Entregador", [None] + nomes, format_func=lambda x: "" if x is None else x, index=0)

    if not nome:
        st.info("Selecione um entregador para ver a lista.")
        st.stop()

    # Filtra pelo entregador escolhido
    df_sel = base[(base["ent_nome"] == nome)].copy()

    # Garante colunas
    for c in ["valor_operacional", "valor_faturamento"]:
        if c not in df_sel.columns:
            df_sel[c] = 0.0

    # Agrega por DATA | TURNO
    saida = (
        df_sel.groupby(["data", "turno"], dropna=False)
              .agg(VLROP=("valor_operacional","sum"),
                   VLRFAT=("valor_faturamento","sum"))
              .reset_index()
              .sort_values(["data","turno"], ascending=[True, True])
    )

    # Renomeia cabeçalho
    saida.rename(columns={"data": "DATA", "turno": "TURNO"}, inplace=True)

    # Exibe na forma solicitada
    st.subheader(f"Lista — {nome}")
    grid = (
        saida[["DATA","TURNO","VLROP","VLRFAT"]]
             .assign(VLROP=lambda d: d["VLROP"].round(2),
                     VLRFAT=lambda d: d["VLRFAT"].round(2))
             .style.format({"VLROP":"{:.2f}","VLRFAT":"{:.2f}"})
    )
    st.dataframe(grid, use_container_width=True)

    # Download CSV
    st.download_button(
        "⬇️ Baixar CSV",
        saida[["DATA","TURNO","VLROP","VLRFAT"]].to_csv(index=False).encode("utf-8"),
        file_name=f"auditoria_{nome.replace(' ','_')}.csv",
        mime="text/csv"
    )
