import streamlit as st
import pandas as pd
import calendar

from relatorios import utr_por_entregador_turno
from shared import sub_options_with_livre, apply_sub_filter  # mesmo esquema do indicadores.py


DOW_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]  # weekday(): seg=0


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🧾 Resumo (Mensal/Semanal/Diário)")

    if df is None or df.empty:
        st.info("Sem dados.")
        return

    base = df.copy()
    base["data"] = pd.to_datetime(base.get("data_do_periodo", base.get("data")), errors="coerce")
    base = base.dropna(subset=["data"])
    if base.empty:
        st.info("Sem datas válidas.")
        return

    data_min = base["data"].min().date()
    data_max = base["data"].max().date()

    # =========================================================
    # FILTROS (igual vibe do sistema)
    # =========================================================
    st.subheader("Filtros")
    f1, f2, f3, f4 = st.columns([1.3, 1, 1.7, 1.4])

    # Subpraça + LIVRE (mesmo shared.py)
    sub_opts = sub_options_with_livre(base, praca_scope="SAO PAULO")
    sub_sel = f1.multiselect("Subpraça", sub_opts)
    base = apply_sub_filter(base, sub_sel, praca_scope="SAO PAULO")

    # Turno (se existir)
    turno_col = next((c for c in ("turno", "tipo_turno", "periodo") if c in base.columns), None)
    if turno_col is not None:
        op_turno = ["Todos"] + sorted(base[turno_col].dropna().unique().tolist())
        turno_sel = f2.selectbox("Turno", op_turno, index=0)
        if turno_sel != "Todos":
            base = base[base[turno_col] == turno_sel]

    # Entregador(es)
    ent_opts = sorted(base.get("pessoa_entregadora", pd.Series(dtype=object)).dropna().unique().tolist())
    ent_sel = f3.multiselect("Entregador(es)", ent_opts)
    if ent_sel:
        base = base[base["pessoa_entregadora"].isin(ent_sel)]

    # Filtro opcional de intervalo "universo"
    usar_intervalo = f4.checkbox("Limitar por intervalo", value=False)
    if usar_intervalo:
        cini, cfim = st.columns(2)
        dt_ini = cini.date_input("De", value=data_min, min_value=data_min, max_value=data_max, format="DD/MM/YYYY")
        dt_fim = cfim.date_input("Até", value=data_max, min_value=data_min, max_value=data_max, format="DD/MM/YYYY")
        ini_u = pd.to_datetime(dt_ini).normalize()
        fim_u_excl = pd.to_datetime(dt_fim).normalize() + pd.Timedelta(days=1)
        base = base[(base["data"] >= ini_u) & (base["data"] < fim_u_excl)].copy()

    if base.empty:
        st.warning("Com esses filtros não sobrou dado.")
        return

    # =========================================================
    # HELPERS
    # =========================================================
    def _sec_to_hms(sec_total: float | int) -> str:
        try:
            sec = int(round(float(sec_total)))
        except Exception:
            sec = 0
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def kpis(df_slice: pd.DataFrame) -> dict:
        ofe = pd.to_numeric(df_slice.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum()
        ace = pd.to_numeric(df_slice.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum()
        rej = pd.to_numeric(df_slice.get("numero_de_corridas_rejeitadas", 0), errors="coerce").fillna(0).sum()
        com = pd.to_numeric(df_slice.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0).sum()
        seg = pd.to_numeric(df_slice.get("segundos_abs", 0), errors="coerce").fillna(0).sum()

        sh_h = float(seg) / 3600.0 if seg else 0.0
        acc = float(ace / ofe * 100) if ofe > 0 else 0.0
        rejp = float(rej / ofe * 100) if ofe > 0 else 0.0

        if "pessoa_entregadora" in df_slice.columns:
            seg_s = pd.to_numeric(df_slice.get("segundos_abs", 0), errors="coerce").fillna(0)
            ofe_s = pd.to_numeric(df_slice.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0)
            ace_s = pd.to_numeric(df_slice.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0)
            com_s = pd.to_numeric(df_slice.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0)
            atividade = (seg_s + ofe_s + ace_s + com_s) > 0
            ativos = int(df_slice.loc[atividade, "pessoa_entregadora"].dropna().nunique())
        else:
            ativos = 0

        utr_abs = float(ofe / sh_h) if sh_h > 0 else 0.0

        b = utr_por_entregador_turno(df_slice)
        if b is None or b.empty:
            utr_med = 0.0
        else:
            b = b[b.get("supply_hours", 0) > 0].copy()
            utr_med = float((b["corridas_ofertadas"] / b["supply_hours"]).mean()) if not b.empty else 0.0

        return dict(ofe=ofe, ace=ace, rej=rej, com=com, seg=seg, sh_h=sh_h, acc=acc, rejp=rejp,
                    ativos=ativos, utr_abs=utr_abs, utr_med=utr_med)

    def delta_pct(cur, prev):
        if prev is None or prev == 0:
            return None if cur > 0 else 0.0
        return float((cur - prev) / prev * 100.0)

    def fmt_pct(v):
        if v is None:
            return "—"
        return f"{v:+.2f}%".replace(".", ",")

    def fmt_int(v):
        try:
            return f"{int(round(float(v))):,}".replace(",", ".")
        except Exception:
            return "0"

    def fmt_dec(v):
        try:
            return f"{float(v):.2f}".replace(".", ",")
        except Exception:
            return "0,00"

    def arrow(d):
        if d is None or abs(d) < 1e-9:
            return "⚪"
        return "🟢⬆" if d > 0 else "🔴⬇"

    # =========================================================
    # SELETOR DE MODO
    # =========================================================
    st.subheader("Comparação")
    tipo = st.radio(
        "Modo",
        ["Semanal (Seg–Dom)", "Mensal", "Diário (comparar dias)"],
        horizontal=True,
        index=0,
    )

    # Normaliza pra facilitar filtros de dia
    base["dow"] = base["data"].dt.weekday  # seg=0

    if tipo.startswith("Semanal"):
        ref_date = st.date_input(
            "Escolha um dia da semana (Seg–Dom)",
            value=base["data"].max().date(),
            min_value=base["data"].min().date(),
            max_value=base["data"].max().date(),
            format="DD/MM/YYYY",
        )

        ref_ts = pd.to_datetime(ref_date).normalize()
        ini = ref_ts - pd.Timedelta(days=ref_ts.weekday())
        fim_excl = ini + pd.Timedelta(days=7)

        ini_prev = ini - pd.Timedelta(days=7)
        fim_prev_excl = fim_excl - pd.Timedelta(days=7)

        header = (
            f"Resumo semanal — {ini.strftime('%d/%m')}–{(fim_excl - pd.Timedelta(days=1)).strftime('%d/%m')} "
            f"• vs semana anterior"
        )

        df_cur = base[(base["data"] >= ini) & (base["data"] < fim_excl)].copy()
        df_prev = base[(base["data"] >= ini_prev) & (base["data"] < fim_prev_excl)].copy()

    elif tipo == "Mensal":
        ultimo = base["data"].max()
        mes_default, ano_default = int(ultimo.month), int(ultimo.year)

        c1, c2 = st.columns(2)
        mes_sel = c1.selectbox("Mês", list(range(1, 13)), index=mes_default - 1)

        anos_disp = sorted(base["data"].dt.year.dropna().unique().tolist(), reverse=True)
        ano_sel = c2.selectbox("Ano", anos_disp, index=anos_disp.index(ano_default) if ano_default in anos_disp else 0)

        ndias = calendar.monthrange(ano_sel, mes_sel)[1]
        ini = pd.Timestamp(year=ano_sel, month=mes_sel, day=1)
        fim_excl = ini + pd.Timedelta(days=ndias)

        # mês anterior
        if mes_sel == 1:
            ano_prev, mes_prev = ano_sel - 1, 12
        else:
            ano_prev, mes_prev = ano_sel, mes_sel - 1

        ndias_prev = calendar.monthrange(ano_prev, mes_prev)[1]
        ini_prev = pd.Timestamp(year=ano_prev, month=mes_prev, day=1)
        fim_prev_excl = ini_prev + pd.Timedelta(days=ndias_prev)

        header = f"Resumo mensal — {mes_sel:02d}/{ano_sel} • vs {mes_prev:02d}/{ano_prev}"

        df_cur = base[(base["data"] >= ini) & (base["data"] < fim_excl)].copy()
        df_prev = base[(base["data"] >= ini_prev) & (base["data"] < fim_prev_excl)].copy()

    else:
        # =====================================================
        # DIÁRIO: compara MESMOS DIAS DA SEMANA
        # Ex: seg com seg, ou seg-ter-qua com seg-ter-qua
        # =====================================================
        ref_date = st.date_input(
            "Escolha um dia (pra definir a semana base)",
            value=base["data"].max().date(),
            min_value=base["data"].min().date(),
            max_value=base["data"].max().date(),
            format="DD/MM/YYYY",
        )

        dias_sel = st.multiselect(
            "Dias pra comparar (mesmo conjunto no período anterior)",
            options=list(range(7)),
            default=[0],  # seg
            format_func=lambda i: DOW_LABELS[i],
        )
        if not dias_sel:
            st.warning("Escolhe pelo menos 1 dia.")
            return

        ref_ts = pd.to_datetime(ref_date).normalize()
        ini = ref_ts - pd.Timedelta(days=ref_ts.weekday())  # segunda
        fim_excl = ini + pd.Timedelta(days=7)

        ini_prev = ini - pd.Timedelta(days=7)
        fim_prev_excl = fim_excl - pd.Timedelta(days=7)

        dias_txt = "-".join([DOW_LABELS[i].lower() for i in dias_sel])
        header = (
            f"Resumo diário — {dias_txt} "
            f"({ini.strftime('%d/%m')}–{(fim_excl - pd.Timedelta(days=1)).strftime('%d/%m')}) "
            f"• vs semana anterior (mesmos dias)"
        )

        df_cur = base[(base["data"] >= ini) & (base["data"] < fim_excl) & (base["dow"].isin(dias_sel))].copy()
        df_prev = base[(base["data"] >= ini_prev) & (base["data"] < fim_prev_excl) & (base["dow"].isin(dias_sel))].copy()

    # =========================================================
    # KPIs + TEXTO
    # =========================================================
    cur = kpis(df_cur)
    prev = kpis(df_prev)

    d = {
        "com": delta_pct(cur["com"], prev["com"]),
        "ofe": delta_pct(cur["ofe"], prev["ofe"]),
        "acc": delta_pct(cur["acc"], prev["acc"]),
        "rej": delta_pct(cur["rejp"], prev["rejp"]),
        "sh":  delta_pct(cur["sh_h"], prev["sh_h"]),
        "ati": delta_pct(cur["ativos"], prev["ativos"]),
        "uab": delta_pct(cur["utr_abs"], prev["utr_abs"]),
        "ume": delta_pct(cur["utr_med"], prev["utr_med"]),
    }

    linhas = [
        f"Completas: {fmt_int(cur['com'])} ({fmt_pct(d['com'])}) {arrow(d['com'])}",
        f"Ofertadas: {fmt_int(cur['ofe'])} ({fmt_pct(d['ofe'])}) {arrow(d['ofe'])}",
        f"Aceitação: {fmt_dec(cur['acc'])}% ({fmt_pct(d['acc'])}) {arrow(d['acc'])}",
        f"Rejeição: {fmt_dec(cur['rejp'])}% ({fmt_pct(d['rej'])}) {arrow(d['rej'])}",
        f"Total SH: {_sec_to_hms(cur['seg'])} ({fmt_pct(d['sh'])}) {arrow(d['sh'])}",
        f"Ativos: {fmt_int(cur['ativos'])} ({fmt_pct(d['ati'])}) {arrow(d['ati'])}",
        f"UTR (Abs.): {fmt_dec(cur['utr_abs'])} ({fmt_pct(d['uab'])}) {arrow(d['uab'])}",
        f"UTR (Médias): {fmt_dec(cur['utr_med'])} ({fmt_pct(d['ume'])}) {arrow(d['ume'])}",
    ]

    st.text_area("📝 Texto pronto", value=header + "\n\n" + "\n\n".join(linhas), height=320)
