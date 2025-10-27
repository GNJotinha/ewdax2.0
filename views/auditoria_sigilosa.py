# views/auditoria_sigilosa.py
from datetime import date
import pandas as pd
import streamlit as st
from utils import normalizar
from auditoria_loader import load_operacional_from_drive, load_faturamento_from_drive

# ----------------- Senha no padrão pedido -----------------
def soma_digitos(n: int) -> int:
    return sum(int(c) for c in str(abs(int(n))))

def senha_por_formula(palavra_base: str, d: date | None = None) -> str:
    d = d or date.today()
    dia, mes = int(d.day), int(d.month)
    valor = (dia * mes) + soma_digitos(dia)
    return f"{palavra_base}@{valor}"

def _gate():
    st.subheader("🔐 Acesso sigiloso")
    palavra = st.secrets.get("SIGILOSO_PALAVRA", "Palavra")
    st.caption("Padrão: <PALAVRA>@(dia*mes + soma_dígitos_dia). Ex.: 27/10 → Palavra@279")

    entrada = st.text_input("Senha", type="password")
    key_tries = "_sig_tries"
    if key_tries not in st.session_state:
        st.session_state[key_tries] = 0

    if st.button("Validar", type="primary", use_container_width=True):
        esperada = senha_por_formula(palavra)
        if entrada and entrada.strip() == esperada:
            st.session_state[key_tries] = 0
            st.session_state["_sig_ok"] = True
            st.success("Acesso liberado.")
            st.rerun()
        else:
            st.session_state[key_tries] += 1
            st.error("Senha incorreta.")

    if st.session_state.get(key_tries, 0) >= 5:
        st.error("Muitas tentativas. Tente novamente mais tarde.")
        st.stop()

    if not st.session_state.get("_sig_ok", False):
        st.stop()

# ----------------- Loaders -----------------
def _load_operacional_df() -> pd.DataFrame:
    df = load_operacional_from_drive()
    # data
    if "data_do_periodo" in df.columns:
        df["data"] = pd.to_datetime(df["data_do_periodo"], errors="coerce").dt.date
    elif "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    else:
        df["data"] = pd.NaT
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
    df[col_val] = pd.to_numeric(df[col_val], errors="coerce").fillna(0).astype("Int64")
    df["valor_operacional"] = df[col_val].fillna(0).astype(float) / 100.0
    # agrega
    return (df.groupby(["data", "ent_id", "ent_norm", "ent_nome", "turno"], dropna=False)
              .agg(valor_operacional=("valor_operacional", "sum"))
              .reset_index())

def _load_faturamento_df() -> pd.DataFrame:
    df = load_faturamento_from_drive()
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
    # agrega
    return (df.groupby(["data", "ent_id", "ent_norm", "ent_nome", "turno"], dropna=False)
              .agg(valor_faturamento=("valor_faturamento", "sum"))
              .reset_index())

# ----------------- Merge e UI -----------------
def _merge_and_compare(op: pd.DataFrame, fat: pd.DataFrame) -> pd.DataFrame:
    # 1) por ID
    m = pd.merge(op, fat, on=["data", "ent_id", "turno"], how="outer", suffixes=("_op", "_fat"))
    # 2) fallback por nome normalizado quando ent_id vazio
    sem_id = m[m["ent_id"].astype(str) == ""]
    if not sem_id.empty:
        m_name = pd.merge(
            op[op["ent_id"].astype(str) == ""],
            fat[fat["ent_id"].astype(str) == ""],
            on=["data", "ent_norm", "turno"],
            how="outer",
            suffixes=("_op", "_fat"),
        )
        base = pd.concat([m[m["ent_id"].astype(str) != ""], m_name], ignore_index=True, sort=False)
    else:
        base = m
    base["valor_operacional"] = pd.to_numeric(base.get("valor_operacional"), errors="coerce")
    base["valor_faturamento"] = pd.to_numeric(base.get("valor_faturamento"), errors="coerce")
    base["delta"] = base["valor_operacional"].fillna(0) - base["valor_faturamento"].fillna(0)
    base["pct_diff"] = None
    mask = base["valor_faturamento"].fillna(0) != 0
    base.loc[mask, "pct_diff"] = (base.loc[mask, "delta"] / base.loc[mask, "valor_faturamento"]) * 100
    return base.sort_values(["data", "ent_nome", "turno"], na_position="last").reset_index(drop=True)

def render(_df_unused: pd.DataFrame, _USUARIOS: dict):
    st.header("🕵️ Auditoria Sigilosa — Operacional × Faturamento (Concluídas)")
    _gate()

    c1, c2, c3 = st.columns([1, 1, 1])
    tol_pct = c1.number_input("Tolerância % (flag)", 0.0, 100.0, 2.0, 0.5)
    tol_abs = c2.number_input("Tolerância R$ (flag)", 0.0, 1.00, 0.50, format="%.2f")
    refresh = c3.button("🔄 Atualizar do Drive", use_container_width=True)
    go = st.button("Gerar comparação", type="primary", use_container_width=True)

    if refresh:
        st.cache_data.clear()
        st.success("Base atualizada do Drive.")

    if not go:
        st.stop()

    with st.spinner("Baixando do Drive e calculando…"):
        op = load_operacional_from_drive(_ts=pd.Timestamp.now().timestamp() if refresh else None)
        fat = load_faturamento_from_drive(_ts=pd.Timestamp.now().timestamp() if refresh else None)
        base = _merge_and_compare(_load_operacional_df() if op is None else _load_operacional_df(),
                                  _load_faturamento_df() if fat is None else _load_faturamento_df())
        # Nota: usamos as funções _load_* que aplicam a limpeza/agregação sobre os DataFrames baixados

    if base.empty:
        st.info("Nada a exibir.")
        st.stop()

    base["data_ts"] = pd.to_datetime(base["data"], errors="coerce")
    min_d, max_d = base["data_ts"].min().date(), base["data_ts"].max().date()
    periodo = st.date_input("Período:", (min_d, max_d), min_value=min_d, max_value=max_d, format="DD/MM/YYYY")
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        base = base[(base["data_ts"] >= pd.to_datetime(periodo[0])) & (base["data_ts"] <= pd.to_datetime(periodo[1]))]

    nomes = sorted([n for n in base["ent_nome"].dropna().unique()])
    turnos = sorted([t for t in base["turno"].dropna().unique()])
    f1, f2 = st.columns(2)
    s_nome = f1.multiselect("Entregador(es)", nomes)
    s_turno = f2.multiselect("Turno(s)", turnos)
    if s_nome: base = base[base["ent_nome"].isin(s_nome)]
    if s_turno: base = base[base["turno"].isin(s_turno)]

    base["flag_pct"] = base["pct_diff"].abs() > tol_pct
    base["flag_abs"] = base["delta"].abs() > tol_abs
    base["flag"] = base[["flag_pct", "flag_abs"]].any(axis=1)

    tot_op = float(base["valor_operacional"].sum())
    tot_fa = float(base["valor_faturamento"].sum())
    delta = tot_op - tot_fa
    pct = (delta / tot_fa * 100.0) if tot_fa != 0 else None

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Operacional (R$)", f"{tot_op:,.2f}".replace(",", "."))
    m2.metric("Faturamento (R$)", f"{tot_fa:,.2f}".replace(",", "."))
    m3.metric("Δ (R$)", f"{delta:,.2f}".replace(",", "."))
    m4.metric("Δ% x Faturamento", "—" if pct is None else f"{pct:.2f}%".replace(".", ","))

    vis = base[["data", "ent_nome", "turno", "valor_operacional", "valor_faturamento", "delta", "pct_diff", "flag"]].copy()
    vis.rename(columns={
        "data": "Data", "ent_nome": "Entregador", "turno": "Turno",
        "valor_operacional": "Operacional (R$)",
        "valor_faturamento": "Faturamento (R$)",
        "delta": "Δ (R$)", "pct_diff": "Δ%", "flag": "⚑"
    }, inplace=True)
    vis["Δ%"] = vis["Δ%"].map(lambda x: None if pd.isna(x) else round(float(x), 2))

    st.dataframe(
        vis.style.format({
            "Operacional (R$)": "{:.2f}",
            "Faturamento (R$)": "{:.2f}",
            "Δ (R$)": "{:.2f}",
            "Δ%": "{:.2f}",
        }),
        use_container_width=True
    )

    st.download_button("⬇️ Baixar CSV", vis.to_csv(index=False).encode("utf-8"),
                       file_name="auditoria_operacional_vs_faturamento.csv", mime="text/csv")
    st.caption("Somente auditoria interna. Gate por senha sigilosa.")
