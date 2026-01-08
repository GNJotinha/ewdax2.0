# views/relatorios_unificado.py
import streamlit as st
import pandas as pd
import numpy as np

from shared import sub_options_with_livre, apply_sub_filter
from utils import calcular_tempo_online


# ------------------------------
# Helpers
# ------------------------------
def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "data" in d.columns:
        d["data"] = pd.to_datetime(d["data"], errors="coerce")
    elif "data_do_periodo" in d.columns:
        d["data"] = pd.to_datetime(d["data_do_periodo"], errors="coerce")
    else:
        d["data"] = pd.NaT
    d = d.dropna(subset=["data"])
    return d


def _ensure_uuid(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "uuid" not in d.columns:
        if "id_da_pessoa_entregadora" in d.columns:
            d["uuid"] = d["id_da_pessoa_entregadora"].astype(str)
        else:
            d["uuid"] = ""
    d["uuid"] = d["uuid"].astype(str)
    return d


def _activity_mask(df: pd.DataFrame) -> pd.Series:
    seg = pd.to_numeric(df.get("segundos_abs", 0), errors="coerce").fillna(0)
    ofe = pd.to_numeric(df.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
    ace = pd.to_numeric(df.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
    com = pd.to_numeric(df.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)
    return (seg + ofe + ace + com) > 0


def _fmt_int(x) -> str:
    try:
        return f"{int(round(float(x))):,}".replace(",", ".")
    except Exception:
        return "0"


def _fmt_pct(x, nd=1) -> str:
    try:
        return f"{float(x):.{nd}f}%".replace(".", ",")
    except Exception:
        return "0,0%"


def _periodo_txt(periodo) -> str:
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        d0 = pd.to_datetime(periodo[0]).strftime("%d/%m")
        d1 = pd.to_datetime(periodo[1]).strftime("%d/%m")
        return f"{d0} a {d1}"
    if isinstance(periodo, (list, tuple)) and len(periodo) == 1:
        d0 = pd.to_datetime(periodo[0]).strftime("%d/%m")
        return f"{d0}"
    return ""


def _kpis(df_slice: pd.DataFrame) -> dict:
    ofe = pd.to_numeric(df_slice.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum()
    ace = pd.to_numeric(df_slice.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum()
    rej = pd.to_numeric(df_slice.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum()
    com = pd.to_numeric(df_slice.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0).sum()
    seg = pd.to_numeric(df_slice.get("segundos_abs", 0), errors="coerce").fillna(0).sum()

    horas = float(seg) / 3600.0 if seg > 0 else 0.0
    acc = (ace / ofe * 100.0) if ofe > 0 else 0.0
    rejp = (rej / ofe * 100.0) if ofe > 0 else 0.0
    comp = (com / ace * 100.0) if ace > 0 else 0.0
    utr = (ofe / horas) if horas > 0 else 0.0

    ativos = 0
    if "pessoa_entregadora" in df_slice.columns:
        m = _activity_mask(df_slice)
        ativos = int(df_slice.loc[m, "pessoa_entregadora"].dropna().nunique())

    return dict(ofe=ofe, ace=ace, rej=rej, com=com, seg=seg, horas=horas, acc=acc, rejp=rejp, comp=comp, utr=utr, ativos=ativos)


def _sec_to_hms(sec_total: float | int) -> str:
    try:
        sec = int(round(float(sec_total)))
    except Exception:
        sec = 0
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _build_title(sub_sel: list[str], turnos_sel: list[str], periodo, has_filter: bool) -> str:
    if not has_filter:
        return "Visão geral (sem filtros)"

    parts = []
    if sub_sel:
        parts.append(sub_sel[0] if len(sub_sel) == 1 else f"{len(sub_sel)} subpraças")
    if turnos_sel:
        parts.append(turnos_sel[0] if len(turnos_sel) == 1 else f"{len(turnos_sel)} turnos")
    ptxt = _periodo_txt(periodo)
    if ptxt:
        parts.append(f"Período {ptxt}")
    return " — ".join([p for p in parts if p])


def _agg_individual(df_sel: pd.DataFrame) -> pd.DataFrame:
    # agrega corridas + turnos
    agg = (
        df_sel.groupby(["pessoa_entregadora"], dropna=True)
        .agg(
            turnos=("data", "count"),
            ofertadas=("numero_de_corridas_ofertadas", "sum"),
            aceitas=("numero_de_corridas_aceitas", "sum"),
            rejeitadas=("numero_de_corridas_rejeitadas", "sum"),
            completas=("numero_de_corridas_completadas", "sum"),
            segundos=("segundos_abs", "sum"),
        )
        .reset_index()
    )

    for c in ["turnos", "ofertadas", "aceitas", "rejeitadas", "completas", "segundos"]:
        agg[c] = pd.to_numeric(agg.get(c, 0), errors="coerce").fillna(0)

    agg["aceitacao_%"] = np.where(agg["ofertadas"] > 0, (agg["aceitas"] / agg["ofertadas"]) * 100.0, 0.0)
    agg["rejeicao_%"] = np.where(agg["ofertadas"] > 0, (agg["rejeitadas"] / agg["ofertadas"]) * 100.0, 0.0)
    agg["conclusao_%"] = np.where(agg["aceitas"] > 0, (agg["completas"] / agg["aceitas"]) * 100.0, 0.0)

    agg["horas"] = agg["segundos"] / 3600.0
    agg["UTR_abs"] = np.where(agg["horas"] > 0, agg["ofertadas"] / agg["horas"], 0.0)

    # tempo online % (por entregador) — usa a função já existente
    online_vals = []
    for nome in agg["pessoa_entregadora"].tolist():
        chunk = df_sel[df_sel["pessoa_entregadora"] == nome].copy()
        online_vals.append(float(calcular_tempo_online(chunk)))
    agg["tempo_online_%"] = online_vals

    # ordena por aceitação (igual “relação” antiga)
    agg = agg.sort_values(by=["aceitacao_%", "ofertadas"], ascending=[False, False]).reset_index(drop=True)
    return agg


def _to_whatsapp_text(df_ind: pd.DataFrame, titulo: str) -> str:
    blocos = [f"*{titulo}*"]
    for _, r in df_ind.iterrows():
        nome = str(r["pessoa_entregadora"])
        blocos.append(
            "\n".join(
                [
                    f"*{nome}*",
                    f"- Tempo online: {_fmt_pct(r.get('tempo_online_%', 0), nd=2)}",
                    f"- Ofertadas: {int(r.get('ofertadas', 0))}",
                    f"- Aceitas: {int(r.get('aceitas', 0))} ({_fmt_pct(r.get('aceitacao_%', 0), nd=2)})",
                    f"- Rejeitadas: {int(r.get('rejeitadas', 0))} ({_fmt_pct(r.get('rejeicao_%', 0), nd=2)})",
                    f"- Completas: {int(r.get('completas', 0))} ({_fmt_pct(r.get('conclusao_%', 0), nd=2)})",
                ]
            )
        )
    return "\n\n".join(blocos).strip()


# ------------------------------
# View principal
# ------------------------------
def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📑 Relatórios — Unificado")

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    base = _ensure_datetime(df)
    if base.empty:
        st.info("Sem datas válidas.")
        return

    base = _ensure_uuid(base)

    # ------------------------------
    # Filtros (topo)
    # ------------------------------
    data_min = pd.to_datetime(base["data"]).min().date()
    data_max = pd.to_datetime(base["data"]).max().date()

    st.caption("Filtros (opcional) — sem filtro = visão geral")
    c1, c2, c3 = st.columns([2, 2, 2])

    # Subpraça (com LIVRE)
    if "sub_praca" in base.columns:
        sub_opts = sub_options_with_livre(base, praca_scope="SAO PAULO")
        sub_sel = c1.multiselect("Subpraça", sub_opts)
    else:
        sub_sel = []

    # Turno
    if "periodo" in base.columns:
        turnos = sorted([x for x in base["periodo"].dropna().unique().tolist()])
        turnos_sel = c2.multiselect("Turno", turnos)
    else:
        turnos_sel = []

    # Período
    periodo = c3.date_input("Período", [data_min, data_max], format="DD/MM/YYYY")

    # aplica período
    df_sel = base.copy()
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        ini = pd.to_datetime(periodo[0])
        fim = pd.to_datetime(periodo[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df_sel = df_sel[(df_sel["data"] >= ini) & (df_sel["data"] <= fim)]
    elif isinstance(periodo, (list, tuple)) and len(periodo) == 1:
        dia = pd.to_datetime(periodo[0]).date()
        df_sel = df_sel[df_sel["data"].dt.date == dia]

    # aplica subpraça
    if sub_sel:
        df_sel = apply_sub_filter(df_sel, sub_sel, praca_scope="SAO PAULO")

    # aplica turno
    if turnos_sel and "periodo" in df_sel.columns:
        df_sel = df_sel[df_sel["periodo"].isin(turnos_sel)]

    has_filter = bool(sub_sel or turnos_sel or (isinstance(periodo, (list, tuple)) and len(periodo) >= 1))
    titulo = _build_title(sub_sel, turnos_sel, periodo, has_filter)

    st.subheader(titulo)

    if df_sel.empty:
        st.info("❌ Nenhum dado encontrado com os filtros.")
        return

    # ------------------------------
    # KPIs (estilo subpraça) — sempre aparece
    # ------------------------------
    k = _kpis(df_sel)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("📦 Ofertadas", _fmt_int(k["ofe"]))
    m2.metric("👍 Aceitas", _fmt_int(k["ace"]), _fmt_pct(k["acc"], 1))
    m3.metric("👎 Rejeitadas", _fmt_int(k["rej"]), _fmt_pct(k["rejp"], 1))
    m4.metric("🏁 Completas", _fmt_int(k["com"]), _fmt_pct(k["comp"], 1))
    m5.metric("👤 Entregadores (ativos)", _fmt_int(k["ativos"]))

    c6, c7, c8 = st.columns(3)
    c6.metric("⏱️ Total SH", _sec_to_hms(k["seg"]))
    c7.metric("🧭 UTR (Abs.)", f"{k['utr']:.2f}")
    c8.metric("🕒 Horas", f"{k['horas']:.1f}h")

    st.divider()

    # ------------------------------
    # Lista de presentes/ativos (default)
    # ------------------------------
    st.subheader("👤 Entregadores presentes (ativos no recorte)")

    m = _activity_mask(df_sel)
    ativos_df = (
        df_sel.loc[m, ["pessoa_entregadora", "uuid"]]
        .dropna(subset=["pessoa_entregadora"])
        .drop_duplicates()
        .sort_values("pessoa_entregadora")
        .reset_index(drop=True)
        .rename(columns={"pessoa_entregadora": "Nome", "uuid": "UUID"})
    )

    st.metric("Total de presentes", int(ativos_df.shape[0]))
    st.dataframe(ativos_df, use_container_width=True)

    st.download_button(
        "⬇️ Baixar CSV — presentes (Nome/UUID)",
        data=ativos_df.to_csv(index=False).encode("utf-8"),
        file_name="presentes_nome_uuid.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.divider()

    # ------------------------------
    # Botão: Desempenhos individuais (modo relação)
    # ------------------------------
    if "show_individuais" not in st.session_state:
        st.session_state.show_individuais = False

    colb1, colb2 = st.columns([2, 3])
    if colb1.button(
        "📈 Desempenhos individuais",
        type="primary" if not st.session_state.show_individuais else "secondary",
        use_container_width=True,
    ):
        st.session_state.show_individuais = not st.session_state.show_individuais

    colb2.caption("Alterna para a visão estilo “Relação de entregadores” usando o MESMO recorte acima.")

    if not st.session_state.show_individuais:
        return

    st.subheader("📋 Desempenhos individuais (por entregador)")

    # só considera quem atuou (pra não poluir)
    df_ind_base = df_sel.loc[_activity_mask(df_sel)].copy()
    if df_ind_base.empty:
        st.info("Sem atuação real no recorte (ativo=0).")
        return

    df_ind = _agg_individual(df_ind_base)

    # tabela
    tabela = df_ind.rename(
        columns={
            "pessoa_entregadora": "Entregador",
            "turnos": "Turnos",
            "tempo_online_%": "Tempo online (%)",
            "ofertadas": "Ofertadas",
            "aceitas": "Aceitas",
            "rejeitadas": "Rejeitadas",
            "completas": "Completas",
            "aceitacao_%": "Aceitação (%)",
            "rejeicao_%": "Rejeição (%)",
            "conclusao_%": "Conclusão (%)",
            "UTR_abs": "UTR (Abs.)",
        }
    )

    cols_show = [
        "Entregador",
        "Tempo online (%)",
        "Turnos",
        "Aceitação (%)",
        "Rejeição (%)",
        "Conclusão (%)",
        "Ofertadas",
        "Aceitas",
        "Rejeitadas",
        "Completas",
        "UTR (Abs.)",
    ]

    st.dataframe(
        tabela[cols_show].style.format(
            {
                "Tempo online (%)": "{:.2f}",
                "Aceitação (%)": "{:.2f}",
                "Rejeição (%)": "{:.2f}",
                "Conclusão (%)": "{:.2f}",
                "UTR (Abs.)": "{:.2f}",
            }
        ),
        use_container_width=True,
    )

    st.download_button(
        "⬇️ Baixar CSV — desempenhos individuais",
        data=tabela[cols_show].to_csv(index=False, decimal=",").encode("utf-8"),
        file_name="desempenhos_individuais.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # texto detalhado
    show_txt = st.checkbox("Mostrar texto detalhado (WhatsApp)", value=True)
    if show_txt:
        txt = _to_whatsapp_text(df_ind, titulo=titulo)
        st.text_area("📝 Texto pronto", value=txt, height=520)
