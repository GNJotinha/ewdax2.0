# views/presenca_calendario.py
from __future__ import annotations
import pandas as pd
import streamlit as st
from datetime import datetime
import calendar
from io import BytesIO

# opcionais (se quiser filtrar por subpraça como no resto do app)
try:
    from shared import sub_options_with_livre, apply_sub_filter
except Exception:
    sub_options_with_livre = apply_sub_filter = None

EMOJI_OK = "✔️"
EMOJI_NOK = "❌"


# -----------------------------
# Helpers de base / presença
# -----------------------------
def _ensure_date(df: pd.DataFrame) -> pd.DataFrame:
    dfx = df.copy()
    if "data" in dfx.columns:
        dfx["data"] = pd.to_datetime(dfx["data"], errors="coerce")
    elif "data_do_periodo" in dfx.columns:
        dfx["data"] = pd.to_datetime(dfx["data_do_periodo"], errors="coerce")
    else:
        raise ValueError("Coluna de data ausente (esperado 'data' ou 'data_do_periodo').")
    if "pessoa_entregadora" not in dfx.columns:
        raise ValueError("Coluna 'pessoa_entregadora' ausente na base.")
    dfx["ano"] = dfx["data"].dt.year
    dfx["mes"] = dfx["data"].dt.month
    dfx["dia"] = dfx["data"].dt.day
    return dfx


def _presence_flag(dfm: pd.DataFrame) -> pd.DataFrame:
    """
    Marca presença por (pessoa, data): se existir qualquer registro no dia, conta 1.
    """
    base = (
        dfm.dropna(subset=["pessoa_entregadora", "data"])
           .groupby(["pessoa_entregadora", "data"], as_index=False)
           .size()
           .rename(columns={"size": "registros"})
    )
    base["presente"] = 1
    base["dia"] = pd.to_datetime(base["data"]).dt.day
    return base[["pessoa_entregadora", "dia", "presente"]]


def _make_grid(dfm: pd.DataFrame, month: int, year: int) -> pd.DataFrame:
    """
    Retorna DataFrame no formato: nome | 1 | 2 | ... | 31 | Total | %
    com ✔️ / ❌ nas colunas de dias (dias que não existem no mês ficam vazios).
    """
    pres = _presence_flag(dfm)

    pv = pres.pivot_table(
        index="pessoa_entregadora",
        columns="dia",
        values="presente",
        aggfunc="max",
        fill_value=0,
    )

    ndays = int(calendar.monthrange(year, month)[1])
    # garante colunas 1..31
    for d in range(1, 32):
        if d not in pv.columns:
            pv[d] = 0
    pv = pv[[d for d in range(1, 32)]]

    # total e %
    pv["Total de Presenças"] = pv.loc[:, 1:ndays].sum(axis=1).astype(int)
    pv["% Presença"] = (pv["Total de Presenças"] / ndays * 100).round(1)

    # troca 1/0 por emoji nos dias válidos
    def _fmt(x, d):
        if d > ndays:
            return ""  # dia inexistente no mês
        return EMOJI_OK if x == 1 else EMOJI_NOK

    df_view = pv.reset_index().copy()
    for d in range(1, 32):
        df_view[d] = df_view[d].apply(lambda v, dd=d: _fmt(v, dd))

    cols = ["pessoa_entregadora"] + [d for d in range(1, 32)] + ["Total de Presenças", "% Presença"]
    return df_view[cols]


def _weekend_columns(year: int, month: int) -> set[str]:
    """Retorna set com nomes das colunas (str) que são sábado/domingo no mês/ano."""
    ndays = int(calendar.monthrange(year, month)[1])
    weekend = set()
    for d in range(1, ndays + 1):
        w = datetime(year, month, d).weekday()  # 0=seg ... 6=dom
        if w in (5, 6):
            weekend.add(str(d))
    return weekend


def _style_weekend_and_totals(df_: pd.DataFrame, weekend_cols: set[str]) -> pd.DataFrame:
    """Styler pro st.dataframe: pinta finais de semana e destaca a linha de totais."""
    s = pd.DataFrame("", index=df_.index, columns=df_.columns)
    for c in weekend_cols:
        if c in s.columns:
            s[c] = "background-color: rgba(180,180,180,0.10);"  # leve no dark
    # destaca a primeira linha (Total por dia)
    if not df_.empty:
        s.iloc[0, :] = "font-weight: 700; background-color: rgba(0,191,255,0.10);"
    return s


def _download_excel(df_exib: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df_exib.to_excel(writer, sheet_name="Presenças", index=False)
    buf.seek(0)
    return buf.read()


# -----------------------------
# Página
# -----------------------------
def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📋 Lista de Presença (mensal)")

    # base
    try:
        df = _ensure_date(df)
    except Exception as e:
        st.error(str(e))
        return

    # Filtros mês/ano (defaults pelo último dia na base)
    ultimo = pd.to_datetime(df["data"], errors="coerce").max()
    ano_padrao = int(ultimo.year) if pd.notna(ultimo) else int(pd.Timestamp.today().year)
    mes_padrao = int(ultimo.month) if pd.notna(ultimo) else int(pd.Timestamp.today().month)

    c1, c2 = st.columns(2)
    anos_disp = sorted(df["ano"].dropna().unique().tolist(), reverse=True)
    ano = c1.selectbox("Ano", anos_disp, index=0, key="pres_ano")
    meses = list(range(1, 13))
    try:
        idx_mes = meses.index(mes_padrao)
    except Exception:
        idx_mes = 0
    mes = c2.selectbox("Mês", meses, index=idx_mes, format_func=lambda m: calendar.month_name[m], key="pres_mes")

    dfm = df[(df["ano"] == ano) & (df["mes"] == mes)].copy()

    # Filtros opcionais do sistema (subpraça/turno)
    if sub_options_with_livre and apply_sub_filter:
        try:
            sub_opts = sub_options_with_livre(dfm, praca_scope="SAO PAULO")
            sub_sel = st.multiselect("Subpraça", sub_opts, key="pres_sub")
            dfm = apply_sub_filter(dfm, sub_sel, praca_scope="SAO PAULO")
        except Exception:
            pass

    if "periodo" in dfm.columns:
        turnos = sorted([x for x in dfm["periodo"].dropna().unique().tolist()])
        turno_sel = st.multiselect("Turnos", turnos, key="pres_turnos")
        if turno_sel:
            dfm = dfm[dfm["periodo"].isin(turno_sel)]

    # Busca por entregador
    q = st.text_input("Buscar entregador", "", key="pres_q")
    if q.strip():
        dfm = dfm[dfm["pessoa_entregadora"].str.contains(q.strip(), case=False, na=False)]

    if dfm.empty:
        st.info("Sem dados no recorte selecionado.")
        return

    # Grid (igual planilha)
    grid = _make_grid(dfm, mes, ano)

    # Linha 1 = totais por dia
    ndays = int(calendar.monthrange(ano, mes)[1])
    totais_por_dia = {d: int((grid[d] == EMOJI_OK).sum()) if d <= ndays else "" for d in range(1, 32)}
    linha_totais = {"pessoa_entregadora": "Total (presentes)"} | totais_por_dia | {
        "Total de Presenças": grid["Total de Presenças"].sum(),
        "% Presença": "",
    }
    exibir = pd.concat([pd.DataFrame([linha_totais]), grid], ignore_index=True)

    # Filtro rápido “Somente presentes no dia”
    c3, c4 = st.columns([1, 2])
    dia_focus = c3.selectbox(
        "Dia (filtro rápido)",
        [None] + list(range(1, ndays + 1)),
        index=0,
        format_func=lambda x: "—" if x is None else str(x),
        key="pres_dia_focus",
    )
    so_presentes = c4.toggle("Somente presentes no dia", value=False, key="pres_toggle")

    fil = exibir.copy()
    if dia_focus is not None and so_presentes:
        mask = (fil[str(dia_focus)] == EMOJI_OK) | (fil["pessoa_entregadora"] == "Total (presentes)")
        fil = fil[mask]

    # Estilo: finais de semana
    weekend_cols = _weekend_columns(ano, mes)
    st.caption("Estrutura espelhada da planilha: ✔️ presença, ❌ ausência. Linha de totais no topo; colunas de Total/% ao final.")
    st.dataframe(fil.style.apply(_style_weekend_and_totals, weekend_cols=weekend_cols, axis=None), use_container_width=True, hide_index=True)

    # Cards simples
    total_entregadores = grid["pessoa_entregadora"].nunique()
    dia_forte = max([(d, int((grid[d] == EMOJI_OK).sum())) for d in range(1, ndays + 1)], key=lambda kv: kv[1])
    dia_fraco = min([(d, int((grid[d] == EMOJI_OK).sum())) for d in range(1, ndays + 1)], key=lambda kv: kv[1])
    cA, cB, cC = st.columns(3)
    cA.metric("Entregadores (listados)", total_entregadores)
    cB.metric("Dia mais forte", f"{dia_forte[0]}", f"{dia_forte[1]} presentes")
    cC.metric("Dia mais fraco", f"{dia_fraco[0]}", f"{dia_fraco[1]} presentes")

    # Lista de nomes presentes no dia selecionado
    st.markdown("### 👥 Presentes no dia escolhido")
    if dia_focus is None:
        st.info("Escolha um dia no seletor acima para ver a lista de presentes.")
    else:
        # nomes do dia a partir do grid
        nomes = grid.loc[grid[str(dia_focus)] == EMOJI_OK, "pessoa_entregadora"].sort_values().tolist()
        if nomes:
            st.write(f"**{len(nomes)} presentes em {str(dia_focus).zfill(2)}/{str(mes).zfill(2)}/{ano}:**")
            # texto pra copiar
            texto = "\n".join(nomes)
            st.text_area("Copiar lista (Ctrl/Cmd + C)", value=texto, height=180, key="pres_text_copy")
            # download .txt
            st.download_button(
                "⬇️ Baixar .txt da lista",
                data=texto.encode("utf-8"),
                file_name=f"presentes_{ano}_{mes:02d}_{int(dia_focus):02d}.txt",
                mime="text/plain",
                key="pres_txt_dl",
            )
        else:
            st.info("Nenhum presente nesse dia no recorte atual.")

    # Download CSV e Excel
    csv = exibir.to_csv(index=False).encode("utf-8")
    cD, cE = st.columns(2)
    cD.download_button(
        "⬇️ Baixar CSV do mês",
        data=csv,
        file_name=f"presenca_{ano}_{mes:02d}.csv",
        mime="text/csv",
        key="pres_csv",
    )
    bin_xlsx = _download_excel(exibir)
    cE.download_button(
        "⬇️ Baixar Excel do mês",
        data=bin_xlsx,
        file_name=f"presenca_{ano}_{mes:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="pres_xlsx",
    )
