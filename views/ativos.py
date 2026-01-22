# views/relatorios_unificado.py
import streamlit as st
import pandas as pd
import numpy as np

from shared import sub_options_with_livre, apply_sub_filter
from utils import calcular_tempo_online, tempo_para_segundos, calcular_aderencia_presenca


# ------------------------------
# Regras de "turno válido" p/ contagem
# ------------------------------
LIMIAR_ABS_SEG = 9 * 60 + 59  # 00:09:59 -> 599s


def _turno_valido_mask(df: pd.DataFrame) -> pd.Series:
    """True quando a linha deve contar como 1 turno (>=00:09:59 no absoluto).

    Obs:
      - NÃO mexe em ofertadas/aceitas/completas; isso é só contagem.
      - Reaproveita 'segundos_abs_raw' quando existir.
      - Remove sentinela -10:00 (-600) e qualquer absoluto < 599s.
    """
    if df is None or df.empty:
        return pd.Series([], dtype=bool)

    if "segundos_abs_raw" in df.columns:
        sec = pd.to_numeric(df["segundos_abs_raw"], errors="coerce").fillna(0)
    elif "segundos_abs" in df.columns:
        sec = pd.to_numeric(df["segundos_abs"], errors="coerce").fillna(0)
    elif "tempo_disponivel_absoluto" in df.columns:
        sec = df["tempo_disponivel_absoluto"].apply(tempo_para_segundos)
        sec = pd.to_numeric(sec, errors="coerce").fillna(0)
    else:
        sec = pd.Series([0] * len(df), index=df.index, dtype=float)

    return (sec != -600) & (sec >= LIMIAR_ABS_SEG)


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


def _format_date_br(dt) -> str:
    try:
        return pd.to_datetime(dt).strftime("%d/%m/%Y")
    except Exception:
        return str(dt)


def _normalize_praca_sigla(df: pd.DataFrame) -> str | None:
    """Tenta inferir uma sigla curta (ex: SAO PAULO -> SP)."""
    if "praca" not in df.columns:
        return None
    vals = df["praca"].dropna().astype(str).unique().tolist()
    if not vals:
        return None
    # se tiver mais de uma praça, não chuta
    if len(vals) != 1:
        return None
    v = vals[0].strip().upper()
    if v in ("SAO PAULO", "SÃO PAULO"):
        return "SP"
    return v


def _periodo_txt(periodo) -> str:
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        d0 = _format_date_br(periodo[0])
        d1 = _format_date_br(periodo[1])
        return f"{d0} a {d1}"
    if isinstance(periodo, (list, tuple)) and len(periodo) == 1:
        d0 = _format_date_br(periodo[0])
        return f"{d0}"
    return ""


def _build_title(
    sub_sel: list[str],
    turnos_sel: list[str],
    periodo,
    has_filter: bool,
    praca_sigla: str | None,
) -> str:
    if not has_filter:
        return "Visão geral (sem filtros)"

    left = ""
    if sub_sel:
        left = sub_sel[0] if len(sub_sel) == 1 else f"{len(sub_sel)} subpraças"
    if praca_sigla:
        left = f"{left} - {praca_sigla}" if left else praca_sigla

    middle = ""
    if turnos_sel:
        middle = turnos_sel[0] if len(turnos_sel) == 1 else f"{len(turnos_sel)} turnos"

    ptxt = _periodo_txt(periodo)
    right = f"Período {ptxt}" if ptxt else ""

    parts = [p for p in (left, middle, right) if p]
    return " — ".join(parts).strip()


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

    # UTR absoluto (agregado)
    utr_abs = (ofe / horas) if horas > 0 else 0.0

    # UTR "Médias": média do (ofertadas/horas) por linha com horas>0
    df_ok = df_slice.copy()
    df_ok["segundos_abs"] = pd.to_numeric(df_ok.get("segundos_abs", 0), errors="coerce").fillna(0)
    df_ok["numero_de_corridas_ofertadas"] = pd.to_numeric(
        df_ok.get("numero_de_corridas_ofertadas", 0), errors="coerce"
    ).fillna(0)

    df_ok = df_ok[df_ok["segundos_abs"] > 0]
    if not df_ok.empty:
        df_ok["horas_linha"] = df_ok["segundos_abs"] / 3600.0
        df_ok = df_ok[df_ok["horas_linha"] > 0]
        if not df_ok.empty:
            df_ok["utr_linha"] = df_ok["numero_de_corridas_ofertadas"] / df_ok["horas_linha"]
            utr_med = float(df_ok["utr_linha"].mean())
        else:
            utr_med = 0.0
    else:
        utr_med = 0.0

    ativos = 0
    if "pessoa_entregadora" in df_slice.columns:
        ativos = int(df_slice.loc[_activity_mask(df_slice), "pessoa_entregadora"].dropna().nunique())

    return dict(
        ofe=ofe,
        ace=ace,
        rej=rej,
        com=com,
        horas=horas,
        acc=acc,
        rejp=rejp,
        comp=comp,
        utr_abs=utr_abs,
        utr_med=utr_med,
        ativos=ativos,
    )


def _agg_individual(df_sel: pd.DataFrame) -> pd.DataFrame:
    # Contagem de "turnos" deve ignorar linhas com absoluto < 00:09:59.
    # (sem mexer nas rotas: ofertadas/aceitas/completas seguem contando tudo.)
    base = df_sel.copy()
    base["_turno_ok"] = _turno_valido_mask(base).astype(int)

    agg = (
        base.groupby(["pessoa_entregadora"], dropna=True)
        .agg(
            turnos=("_turno_ok", "sum"),
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

    online_vals = []
    for nome in agg["pessoa_entregadora"].tolist():
        chunk = df_sel[df_sel["pessoa_entregadora"] == nome].copy()
        online_vals.append(float(calcular_tempo_online(chunk)))
    agg["tempo_online_%"] = online_vals

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
    st.header("📑 Relatórios")

    if df is None or df.empty:
        st.info("Sem dados carregados.")
        return

    base = _ensure_datetime(df)
    if base.empty:
        st.info("Sem datas válidas.")
        return

    base = _ensure_uuid(base)

    data_min = pd.to_datetime(base["data"]).min().date()
    data_max = pd.to_datetime(base["data"]).max().date()

    praca_sigla = _normalize_praca_sigla(base)

    # filtros (sem legendas)
    f1, f2, f3 = st.columns(3)

    if "sub_praca" in base.columns:
        sub_opts = sub_options_with_livre(base, praca_scope="SAO PAULO")
        sub_sel = f1.multiselect("Subpraça", sub_opts, key="ru_sub")
    else:
        sub_sel = []

    if "periodo" in base.columns:
        turnos = sorted([x for x in base["periodo"].dropna().unique().tolist()])
        turnos_sel = f2.multiselect("Turno", turnos, key="ru_turno")
    else:
        turnos_sel = []

    periodo = f3.date_input("Período", [data_min, data_max], format="DD/MM/YYYY", key="ru_periodo")

    # aplica filtros
    df_sel = base.copy()

    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        ini = pd.to_datetime(periodo[0])
        fim = pd.to_datetime(periodo[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df_sel = df_sel[(df_sel["data"] >= ini) & (df_sel["data"] <= fim)]
    elif isinstance(periodo, (list, tuple)) and len(periodo) == 1:
        dia = pd.to_datetime(periodo[0]).date()
        df_sel = df_sel[df_sel["data"].dt.date == dia]

    if sub_sel:
        df_sel = apply_sub_filter(df_sel, sub_sel, praca_scope="SAO PAULO")

    if turnos_sel and "periodo" in df_sel.columns:
        df_sel = df_sel[df_sel["periodo"].isin(turnos_sel)]

    # sem filtro "de verdade" (período default + sem sub/turno)
    period_is_default = False
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        try:
            period_is_default = (periodo[0] == data_min and periodo[1] == data_max)
        except Exception:
            period_is_default = False

    has_filter = bool(sub_sel or turnos_sel or (not period_is_default))
    titulo = _build_title(sub_sel, turnos_sel, periodo, has_filter, praca_sigla)

    st.subheader(titulo)

    if df_sel.empty:
        st.info("❌ Nenhum dado encontrado com os filtros.")
        return

    # ------------------------------
    # KPIs na ordem:
    # Ofertadas  | Completas(%)
    # Aceitas(%) | Rejeitadas(%)
    # Entregadores | Horas
    # UTR (Abs.) | UTR (Médias)
    # ------------------------------
    k = _kpis(df_sel)

    completas_label = f"{_fmt_int(k['com'])} ({_fmt_pct(k['comp'], 1)})"
    aceitas_label = f"{_fmt_int(k['ace'])} ({_fmt_pct(k['acc'], 1)})"
    rejeitadas_label = f"{_fmt_int(k['rej'])} ({_fmt_pct(k['rejp'], 1)})"

    r1c1, r1c2 = st.columns(2)
    r1c1.metric("📦 Ofertadas", _fmt_int(k["ofe"]))
    r1c2.metric("🏁 Completas", completas_label)

    r2c1, r2c2 = st.columns(2)
    r2c1.metric("👍 Aceitas", aceitas_label)
    r2c2.metric("👎 Rejeitadas", rejeitadas_label)

    r3c1, r3c2 = st.columns(2)
    r3c1.metric("👤 Entregadores", _fmt_int(k["ativos"]))
    r3c2.metric("🕒 Horas", f"{k['horas']:.1f}h")

    r4c1, r4c2 = st.columns(2)
    r4c1.metric("🧭 UTR (Abs.)", f"{k['utr_abs']:.2f}")
    r4c2.metric("📊 UTR (Médias)", f"{k['utr_med']:.2f}")

    # ------------------------------
    # Aderência & Presença (no recorte)
    # ------------------------------
    if ("numero_minimo_de_entregadores_regulares_na_escala" in df_sel.columns) and ("tag" in df_sel.columns):
        turno_col_ap = next((c for c in ("turno", "tipo_turno", "periodo") if c in df_sel.columns), None)
        group_cols_ap = ("data", turno_col_ap) if turno_col_ap else ("data",)
        try:
            base_ap = calcular_aderencia_presenca(df_sel, group_cols=group_cols_ap)
            reg = int(base_ap["regulares_atuaram"].sum())
            vagas = float(base_ap["vagas"].sum())
            ader = (reg / vagas * 100.0) if vagas > 0 else 0.0
            htot = float(base_ap["horas_totais"].sum())
            pres = float(base_ap["entregadores_presentes"].sum())
            pres_h = (htot / pres) if pres > 0 else 0.0

            r5c1, r5c2 = st.columns(2)
            r5c1.metric("📌 Aderência (REGULAR)", f"{ader:.1f}%")
            r5c1.caption(f"Regulares: **{reg}** / Vagas: **{int(vagas)}**")
            if bool(base_ap["vagas_inconsistente"].any()):
                r5c1.warning("⚠️ Vagas inconsistentes em alguns dias/turnos (coluna variando dentro do mesmo grupo).")
            r5c2.metric("🧍 Presença", f"{pres_h:.2f} h/entregador")
        except Exception:
            pass

    st.divider()

    # ------------------------------
    # Lista de presentes (Nome/UUID)
    # ------------------------------
    m = _activity_mask(df_sel)
    ativos_df = (
        df_sel.loc[m, ["pessoa_entregadora", "uuid"]]
        .dropna(subset=["pessoa_entregadora"])
        .drop_duplicates()
        .sort_values("pessoa_entregadora")
        .reset_index(drop=True)
        .rename(columns={"pessoa_entregadora": "Nome", "uuid": "UUID"})
    )

    with st.expander("👤 Lista de entregadores presentes (Nome/UUID)", expanded=True):
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
    # Individual (checkbox)
    # ------------------------------
    show_ind = st.checkbox("📈 Mostrar desempenhos individuais", value=False)

    if not show_ind:
        return

    st.subheader("📋 Desempenhos individuais (por entregador)")

    df_ind_base = df_sel.loc[_activity_mask(df_sel)].copy()
    if df_ind_base.empty:
        st.info("Sem atuação real no recorte.")
        return

    df_ind = _agg_individual(df_ind_base)

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

    show_txt = st.checkbox("📝 Mostrar texto detalhado (WhatsApp)", value=True)
    if show_txt:
        txt = _to_whatsapp_text(df_ind, titulo=titulo)
        st.text_area("Texto pronto", value=txt, height=520)
