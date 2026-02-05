import streamlit as st
import pandas as pd
from io import BytesIO
import re

META_ELITE = 300
COL_ELITE = "numero_de_pedidos_aceitos_e_concluidos"

# meses pt-br (abreviação)
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}


def _fmt_mes(ts) -> str:
    """Somente para exibir no UI (pode ter /)."""
    ts = pd.to_datetime(ts)
    return f"{MESES_PT.get(ts.month, ts.month)}/{ts.year}"


def _safe_sheet_name(name: str) -> str:
    """
    openpyxl rules:
      - max 31 chars
      - cannot contain: : \\ / ? * [ ]
    """
    if name is None:
        return "ELITE"
    # remove chars proibidos
    name = re.sub(r'[:\\\/\?\*\[\]]', "-", str(name))
    name = name.strip() or "ELITE"
    # limita 31
    return name[:31]


def _ensure_mes_ano(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()

    if "mes_ano" in d.columns:
        d["mes_ano"] = pd.to_datetime(d["mes_ano"], errors="coerce")
        return d

    if "data_do_periodo" in d.columns:
        d["data_do_periodo"] = pd.to_datetime(d["data_do_periodo"], errors="coerce")
        d["mes_ano"] = d["data_do_periodo"].dt.to_period("M").dt.to_timestamp()
        return d

    if "data" in d.columns:
        d["data"] = pd.to_datetime(d["data"], errors="coerce")
        d["mes_ano"] = d["data"].dt.to_period("M").dt.to_timestamp()
        return d

    raise ValueError("Não achei coluna de data (mes_ano/data_do_periodo/data).")


def _ensure_uuid(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    if "uuid" in d.columns:
        d["uuid"] = d["uuid"].astype(str)
        return d

    if "id_da_pessoa_entregadora" in d.columns:
        d["uuid"] = d["id_da_pessoa_entregadora"].astype(str)
        return d

    d["uuid"] = ""
    return d


def _to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "ELITE"):
    out = BytesIO()
    safe = _safe_sheet_name(sheet_name)
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=safe)
    out.seek(0)
    return out.getvalue()


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🏆 ELITE do mês")

    if df is None or df.empty:
        st.info("Sem dados.")
        return

    if COL_ELITE not in df.columns:
        st.error(f"Coluna obrigatória não encontrada: `{COL_ELITE}`")
        return

    if "pessoa_entregadora" not in df.columns:
        st.error("Coluna `pessoa_entregadora` não encontrada.")
        return

    try:
        d = _ensure_mes_ano(df)
    except ValueError as e:
        st.error(str(e))
        return

    d = _ensure_uuid(d)

    d[COL_ELITE] = pd.to_numeric(d[COL_ELITE], errors="coerce").fillna(0)

    meses = sorted([m for m in d["mes_ano"].dropna().unique().tolist()])
    if not meses:
        st.info("Sem meses válidos na base.")
        return

    mes_sel = st.selectbox(
        "Mês",
        meses,
        index=len(meses) - 1,
        format_func=_fmt_mes,
    )

    d_mes = d[d["mes_ano"] == pd.to_datetime(mes_sel)].copy()
    if d_mes.empty:
        st.info("Sem dados no mês selecionado.")
        return

    # Tabela base (lista completa)
    base = (
        d_mes.groupby(["uuid", "pessoa_entregadora"], as_index=False)[COL_ELITE]
        .sum()
        .rename(columns={"pessoa_entregadora": "nome", COL_ELITE: "pedidos_ok_mes"})
    )

    base["faltam_p_300"] = (META_ELITE - base["pedidos_ok_mes"]).clip(lower=0).astype(int)
    base["elite"] = base["pedidos_ok_mes"] >= META_ELITE
    base["progresso"] = (base["pedidos_ok_mes"] / META_ELITE).clip(upper=1.0)

    # ordenação útil (ELITE primeiro, depois quem tem mais)
    base = base.sort_values(["elite", "pedidos_ok_mes"], ascending=[False, False]).reset_index(drop=True)

    # ===================== BUSCA com sugestão/typeahead =====================
    st.subheader("🔎 Buscar entregador")

    nomes = base["nome"].fillna("").astype(str).tolist()

    col1, col2 = st.columns([2, 3])
    # 1) Busca padrão tipo “filtro”: você digita e ele filtra a lista automaticamente
    nome_pick = col1.selectbox(
        "Digite para buscar (sugestões):",
        options=[""] + sorted(set(nomes)),
        index=0,
        help="Começa a digitar (ex: 'W') e selecione o nome.",
    )

    # 2) (Opcional) manter input livre também — útil pra achar parcialmente e trazer múltiplos
    busca = col2.text_input("Ou busque por parte do nome:", value="").strip()

    achados = base.copy()
    if nome_pick:
        achados = achados[achados["nome"] == nome_pick].copy()
    elif busca:
        b = busca.lower()
        achados = achados[achados["nome"].str.lower().str.contains(b, na=False)].copy()

    if (nome_pick or busca):
        if achados.empty:
            st.warning("Não achei ninguém com esse nome nesse mês.")
        else:
            st.dataframe(
                achados[["uuid", "nome", "pedidos_ok_mes", "faltam_p_300", "elite", "progresso"]]
                .rename(
                    columns={
                        "pedidos_ok_mes": "pedidos_ok (mês)",
                        "faltam_p_300": "faltam p/ 300",
                        "elite": "ELITE",
                        "progresso": "% da meta",
                    }
                )
                .assign(ELITE=lambda x: x["ELITE"].map(lambda v: "✅" if v else "")),
                use_container_width=True,
                hide_index=True,
            )

    st.divider()

    # ===================== LISTA COMPLETA + DOWNLOAD =====================
    st.subheader("📋 Lista completa do mês")

    # (mantive só esse filtro pq você comentou antes que era útil)
    only_not_elite = st.checkbox("Ocultar quem já é ELITE", value=False)

    view = base.copy()
    if only_not_elite:
        view = view[~view["elite"]].copy()

    def _bar(s):
        return [
            f"background: linear-gradient(90deg, rgba(0,191,255,0.45) {p*100:.1f}%, transparent {p*100:.1f}%);"
            for p in s
        ]

    show = (
        view[["uuid", "nome", "pedidos_ok_mes", "faltam_p_300", "elite", "progresso"]]
        .rename(
            columns={
                "pedidos_ok_mes": "pedidos_ok (mês)",
                "faltam_p_300": "faltam p/ 300",
                "elite": "ELITE",
                "progresso": "% da meta",
            }
        )
        .copy()
    )
    show["ELITE"] = show["ELITE"].map(lambda v: "✅" if v else "")

    st.dataframe(
        show.style.format({"% da meta": "{:.0%}"}).apply(_bar, subset=["% da meta"]),
        use_container_width=True,
        hide_index=True,
    )

    # Nome de aba seguro (sem /)
    sheet = f"ELITE {_fmt_mes(mes_sel)}"
    xlsx_bytes = _to_xlsx_bytes(show, sheet_name=sheet)

    st.download_button(
        "⬇️ Baixar XLSX",
        data=xlsx_bytes,
        file_name=f"elite_{pd.to_datetime(mes_sel).strftime('%Y_%m')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=False,
    )
