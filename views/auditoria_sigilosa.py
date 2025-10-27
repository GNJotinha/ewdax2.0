# views/auditoria_sigilosa.py
from datetime import date
import pandas as pd
import streamlit as st

from auditoria_loader import (
    load_operacional_from_drive,
    load_faturamento_from_drive,
)

# ----------------- Gate: senha super simples -----------------
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

# ----------------- Helpers de preparo -----------------
def _prep_operacional(df: pd.DataFrame) -> pd.DataFrame:
    """
    Espera colunas (vêm do loader enxuto):
      data, periodo, id_da_pessoa_entregadora, pessoa_entregadora,
      soma_das_taxas_das_corridas_aceitas
    Converte centavos -> reais e agrega por data/entregador/turno.
    """
    # data já vem como date no loader
    df = df.copy()

    # turno
    df["turno"] = df.get("periodo").astype(str) if "periodo" in df.columns else None

    # identificadores
    df["ent_id"] = df.get("id_da_pessoa_entregadora", "").astype(str)
    df["ent_nome"] = df.get("pessoa_entregadora", "").astype(str)

    # valor aceitas (centavos → reais)
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
    Espera colunas (vêm do loader enxuto):
      data, periodo, id_da_pessoa_entregadora, ent_nome, valor, descricao
    Filtra somente 'conclu' e agrega por data/entregador/turno.
    """
    df = df.copy()

    # turno / identificadores
    df["turno"] = df.get("periodo").astype(str) if "periodo" in df.columns else None
    df["ent_id"] = df.get("id_da_pessoa_entregadora", "").astype(str)
    df["ent_nome"] = df.get("ent_nome", "").astype(str)

    # valor (reais) + filtro concluídas
    df["valor"] = pd.to_numeric(df.get("valor"), errors="coerce").fillna(0.0)
    df = df[df.get("descricao", "").astype(str).str.lower().str.contains("conclu", na=False)].copy()

    grp = (
        df.groupby(["data", "ent_id", "ent_nome", "turno"], dropna=False)["valor"]
          .sum()
          .reset_index()
          .rename(columns={"valor": "valor_faturamento"})
    )
    return grp

# ----------------- View -----------------
def render(_df_unused: pd.DataFrame, _USUARIOS: dict):
    st.header("🕵️ Auditoria Sigilosa — Operacional × Faturamento (Concluídas)")
    _gate()

    # Controles de atualização
    col_a, col_b = st.columns([1, 3])
    refresh = col_a.button("🔄 Atualizar do Drive", use_container_width=True)

    with st.spinner("Carregando bases..."):
        # Baixa (ou usa cache) e prepara
        raw_op = load_operacional_from_drive(force=refresh)
        raw_fa = load_faturamento_from_drive(force=refresh)

        op = _prep_operacional(raw_op)   # data, ent_id, ent_nome, turno, valor_operacional
        fa = _prep_faturamento(raw_fa)   # data, ent_id, ent_nome, turno, valor_faturamento

    # Lista de entregadores (união dos nomes nas duas bases)
    nomes = sorted(pd.Index(op["ent_nome"]).union(pd.Index(fa["ent_nome"])).dropna().unique().tolist())
    nome = st.selectbox("Entregador", [None] + nomes, format_func=lambda x: "" if x is None else x, index=0)

    if not nome:
        st.info("Selecione um entregador para ver a lista.")
        st.stop()

    # Filtra por entregador escolhido
    op_sel = op[op["ent_nome"] == nome].copy()
    fa_sel = fa[fa["ent_nome"] == nome].copy()

    # Datas disponíveis e filtro de período
    if not op_sel.empty or not fa_sel.empty:
        min_d = pd.concat([op_sel["data"], fa_sel["data"]], ignore_index=True).min()
        max_d = pd.concat([op_sel["data"], fa_sel["data"]], ignore_index=True).max()
    else:
        min_d = max_d = None

    if min_d is None or max_d is None:
        st.info("Sem dados para este entregador.")
        st.stop()

    periodo = st.date_input("Período:", (min_d, max_d), min_value=min_d, max_value=max_d, format="DD/MM/YYYY")
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        d0, d1 = pd.to_datetime(periodo[0]).date(), pd.to_datetime(periodo[1]).date()
        op_sel = op_sel[(op_sel["data"] >= d0) & (op_sel["data"] <= d1)]
        fa_sel = fa_sel[(fa_sel["data"] >= d0) & (fa_sel["data"] <= d1)]

    # Reagrega por DATA|TURNO (garantindo colunas)
    op_day = (
        op_sel.groupby(["data", "turno"], dropna=False)["valor_operacional"]
              .sum().reset_index()
              .rename(columns={"valor_operacional": "VLROP"})
    )
    fa_day = (
        fa_sel.groupby(["data", "turno"], dropna=False)["valor_faturamento"]
              .sum().reset_index()
              .rename(columns={"valor_faturamento": "VLRFAT"})
    )

    # Merge por data/turno (outer pra cobrir linhas presentes só de um lado)
    saida = pd.merge(op_day, fa_day, on=["data", "turno"], how="outer")
    # Preenche ausentes com 0.0 para exibição amigável
    saida["VLROP"] = pd.to_numeric(saida.get("VLROP"), errors="coerce").fillna(0.0)
    saida["VLRFAT"] = pd.to_numeric(saida.get("VLRFAT"), errors="coerce").fillna(0.0)

    # Ordena e renomeia cabeçalho
    saida = saida.sort_values(["data", "turno"], ascending=[True, True]).reset_index(drop=True)
    saida.rename(columns={"data": "DATA", "turno": "TURNO"}, inplace=True)

    # Exibição
    st.subheader(f"Lista — {nome}")
    vis = (
        saida[["DATA", "TURNO", "VLROP", "VLRFAT"]]
            .assign(VLROP=lambda d: d["VLROP"].round(2),
                    VLRFAT=lambda d: d["VLRFAT"].round(2))
            .style.format({"VLROP": "{:.2f}", "VLRFAT": "{:.2f}"})
    )
    st.dataframe(vis, use_container_width=True)

    # Download CSV no mesmo layout
    st.download_button(
        "⬇️ Baixar CSV",
        saida[["DATA", "TURNO", "VLROP", "VLRFAT"]].to_csv(index=False).encode("utf-8"),
        file_name=f"auditoria_{nome.replace(' ', '_')}.csv",
        mime="text/csv",
        use_container_width=True
    )
