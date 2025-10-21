# views/presenca_calendario.py
from __future__ import annotations
import pandas as pd
import streamlit as st
from datetime import date
import calendar

# opcionais (só se quiser filtrar por subpraça igual outros relatórios)
try:
    from shared import sub_options_with_livre, apply_sub_filter
except Exception:
    sub_options_with_livre = apply_sub_filter = None

EMOJI_OK = "✔️"
EMOJI_NOK = "❌"

def _ensure_date(df: pd.DataFrame) -> pd.DataFrame:
    dfx = df.copy()
    if "data" in dfx.columns:
        dfx["data"] = pd.to_datetime(dfx["data"], errors="coerce")
    elif "data_do_periodo" in dfx.columns:
        dfx["data"] = pd.to_datetime(dfx["data_do_periodo"], errors="coerce")
    else:
        raise ValueError("Coluna de data ausente (esperado 'data' ou 'data_do_periodo').")
    dfx["ano"] = dfx["data"].dt.year
    dfx["mes"] = dfx["data"].dt.month
    dfx["dia"] = dfx["data"].dt.day
    return dfx

def _presence_flag(dfm: pd.DataFrame) -> pd.DataFrame:
    """
    Marca presença por (pessoa, data): se existir qualquer registro no dia, conta 1.
    """
    base = (
        dfm.dropna(subset=["pessoa_entregadora","data"])
           .groupby(["pessoa_entregadora","data"], as_index=False)
           .size()
           .rename(columns={"size":"registros"})
    )
    base["presente"] = 1  # qualquer registro conta como presente
    base["dia"] = pd.to_datetime(base["data"]).dt.day
    return base[["pessoa_entregadora","dia","presente"]]

def _make_grid(dfm: pd.DataFrame, month: int, year: int) -> pd.DataFrame:
    """
    Retorna DataFrame no formato: nome | 1 | 2 | ... | 31 | Total | %
    com ✔️ / ❌ nas colunas de dias.
    """
    pres = _presence_flag(dfm)
    # pivot para colunas de dia (1..31)
    pv = pres.pivot_table(index="pessoa_entregadora", columns="dia", values="presente", aggfunc="max", fill_value=0)
    # garante todas as colunas 1..31
    ndays = calendar.monthrange(year, month)[1]
    for d in range(1, 32):
        if d not in pv.columns:
            pv[d] = 0
    pv = pv[[d for d in range(1, 32)]]  # ordena

    # total e %
    pv["Total de Presenças"] = pv.loc[:, 1:ndays].sum(axis=1).astype(int)
    pv["% Presença"] = (pv["Total de Presenças"] / ndays * 100).round(1)

    # troca 1/0 por emoji somente nos dias válidos do mês; fora do mês deixa vazio
    def _fmt(x, d):
        if d > ndays:  # dia que não existe no mês
            return ""
        return EMOJI_OK if x == 1 else EMOJI_NOK

    df_view = pv.reset_index().copy()
    for d in range(1, 32):
        df_view[d] = df_view[d].apply(lambda v, dd=d: _fmt(v, dd))

    # remove dias que não existem no mês do header visual (mantém coluna mas vazia)
    # (mantemos 1..31 pra ficar idêntico à planilha)
    # ordena colunas finais
    cols = ["pessoa_entregadora"] + [d for d in range(1, 32)] + ["Total de Presenças","% Presença"]
    return df_view[cols]

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📋 Lista de Presença (mensal)")

    try:
        df = _ensure_date(df)
    except Exception as e:
        st.error(str(e))
        return

    # ---- filtros básicos: mês/ano ----
    ultimo = pd.to_datetime(df["data"], errors="coerce").max()
    ano_padrao = int(ultimo.year) if pd.notna(ultimo) else int(pd.Timestamp.today().year)
    mes_padrao = int(ultimo.month) if pd.notna(ultimo) else int(pd.Timestamp.today().month)

    c1, c2 = st.columns(2)
    ano = c1.selectbox("Ano", sorted(df["ano"].dropna().unique().tolist(), reverse=True), index=0)
    meses = list(range(1, 13))
    mes = c2.selectbox("Mês", meses, index=mes_padrao-1, format_func=lambda m: calendar.month_name[m])

    dfm = df[(df["ano"] == ano) & (df["mes"] == mes)].copy()

    # ---- filtros opcionais (iguais ao resto do app) ----
    if sub_options_with_livre and apply_sub_filter:
        try:
            sub_opts = sub_options_with_livre(dfm, praca_scope="SAO PAULO")
            sub_sel = st.multiselect("Subpraça", sub_opts)
            dfm = apply_sub_filter(dfm, sub_sel, praca_scope="SAO PAULO")
        except Exception:
            pass

    if "periodo" in dfm.columns:
        turnos = sorted([x for x in dfm["periodo"].dropna().unique().tolist()])
        turno_sel = st.multiselect("Turnos", turnos)
        if turno_sel:
            dfm = dfm[dfm["periodo"].isin(turno_sel)]

    # ---- busca por entregador ----
    q = st.text_input("Buscar entregador", "")
    if q.strip():
        dfm = dfm[dfm["pessoa_entregadora"].str.contains(q.strip(), case=False, na=False)]

    if dfm.empty:
        st.info("Sem dados no recorte selecionado.")
        return

    # ---- grid de presença (igual à planilha) ----
    grid = _make_grid(dfm, mes, ano)

    # linha de totais por dia (primeira linha)
    ndays = calendar.monthrange(ano, mes)[1]
    totais_por_dia = {d: int((grid[d] == EMOJI_OK).sum()) if d <= ndays else "" for d in range(1, 32)}
    linha_totais = {"pessoa_entregadora": "Total (presentes)"} | totais_por_dia | {
        "Total de Presenças": grid["Total de Presenças"].sum(),
        "% Presença": ""
    }
    exibir = pd.concat([pd.DataFrame([linha_totais]), grid], ignore_index=True)

    # ---- filtro rápido: “Somente presentes no dia” ----
    c3, c4 = st.columns([1,2])
    dia_focus = c3.selectbox("Dia (filtro rápido)", [None] + list(range(1, ndays+1)), index=0, format_func=lambda x: "—" if x is None else x)
    so_presentes = c4.toggle("Somente presentes no dia", value=False)
    fil = exibir.copy()
    if dia_focus is not None and so_presentes:
        mask = (fil[str(dia_focus)] == EMOJI_OK) | (fil["pessoa_entregadora"] == "Total (presentes)")
        fil = fil[mask]

    st.caption("Estrutura espelhada da planilha: ✔️ presença, ❌ ausência. Linha de totais no topo; colunas de Total/% ao final.")
    st.dataframe(fil, use_container_width=True, hide_index=True)

    # ---- cards simples ----
    total_entregadores = grid["pessoa_entregadora"].nunique()
    dia_forte = max([(d, int((grid[d] == EMOJI_OK).sum())) for d in range(1, ndays+1)], key=lambda kv: kv[1])
    dia_fraco = min([(d, int((grid[d] == EMOJI_OK).sum())) for d in range(1, ndays+1)], key=lambda kv: kv[1])
    cA, cB, cC = st.columns(3)
    cA.metric("Entregadores (listados)", total_entregadores)
    cB.metric("Dia mais forte", f"{dia_forte[0]}", f"{dia_forte[1]} presentes")
    cC.metric("Dia mais fraco", f"{dia_fraco[0]}", f"{dia_fraco[1]} presentes")

    # ---- download (CSV/Excel) ----
    csv = exibir.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Baixar CSV do mês", data=csv, file_name=f"presenca_{ano}_{mes:02d}.csv", mime="text/csv")
