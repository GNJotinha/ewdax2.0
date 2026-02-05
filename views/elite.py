import streamlit as st
import pandas as pd
from io import BytesIO

META_ELITE = 300
COL_ELITE = "numero_de_pedidos_aceitos_e_concluidos"

# meses pt-br (abreviação)
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}


def _fmt_mes(ts) -> str:
    ts = pd.to_datetime(ts)
    return f"{MESES_PT.get(ts.month, ts.month)}/{ts.year}"


def _ensure_mes_ano(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()

    if "mes_ano" in d.columns:
        d["mes_ano"] = pd.to_datetime(d["mes_ano"], errors="coerce")
        return d

    # fallback: tenta derivar de data_do_periodo ou data
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
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
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

    # normaliza coluna elite
    d[COL_ELITE] = pd.to_numeric(d[COL_ELITE], errors="coerce").fillna(0)

    meses = sorted([m for m in d["mes_ano"].dropna().unique().tolist()])
    if not meses:
        st.info("Sem meses válidos na base.")
        return

    mes_sel = st.selectbox(
        "Mês",
        meses,
        index=len(meses) - 1,  # último mês disponível na base (mais seguro do que "mês do relógio")
        format_func=_fmt_mes,
    )

    d_mes = d[d["mes_ano"] == pd.to_datetime(mes_sel)].copy()
    if d_mes.empty:
        st.info("Sem dados no mês selecionado.")
        return

    # tabela base (lista completa)
    base = (
        d_mes.groupby(["uuid", "pessoa_entregadora"], as_index=False)[COL_ELITE]
        .sum()
        .rename(columns={"pessoa_entregadora": "nome", COL_ELITE: "pedidos_ok_mes"})
    )

    base["faltam_p_300"] = (META_ELITE - base["pedidos_ok_mes"]).clip(lower=0).astype(int)
    base["elite"] = base["pedidos_ok_mes"] >= META_ELITE
    base["progresso"] = (base["pedidos_ok_mes"] / META_ELITE).clip(upper=1.0)

    # ordenação: quem tá mais perto aparece em cima (sem chamar de ranking)
    # (elite primeiro, depois maior pedidos_ok_mes)
    base = base.sort_values(["elite", "pedidos_ok_mes"], ascending=[False, False]).reset_index(drop=True)

    # ===== Busca =====
    st.subheader("🔎 Buscar entregador")

    busca = st.text_input("Digite um nome (ou parte do nome):", value="").strip()

    def _match_nome(x: str) -> bool:
        return busca.lower() in str(x).lower()

    if busca:
        achados = base[base["nome"].apply(_match_nome)].copy()

        if achados.empty:
            st.warning("Não achei ninguém com esse nome nesse mês.")
        else:
            # mostra “a linha dele” (ou linhas, se bater mais de um)
            st.caption("Resultado(s):")
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

    # ===== Lista completa + download =====
    st.subheader("📋 Lista completa do mês")

    col_a, col_b = st.columns([1, 1])
    only_close = col_a.checkbox("Mostrar só quem tá perto (faltam ≤ 50)", value=False)
    only_not_elite = col_b.checkbox("Ocultar quem já é ELITE", value=False)

    view = base.copy()
    if only_close:
        view = view[view["faltam_p_300"] <= 50].copy()
    if only_not_elite:
        view = view[~view["elite"]].copy()

    # barrinha na coluna "% da meta"
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

    # download XLSX
    xlsx_bytes = _to_xlsx_bytes(show, sheet_name=_fmt_mes(mes_sel))
    st.download_button(
        "⬇️ Baixar XLSX",
        data=xlsx_bytes,
        file_name=f"elite_{pd.to_datetime(mes_sel).strftime('%Y_%m')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=False,
    )
