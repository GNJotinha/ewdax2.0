import streamlit as st
import pandas as pd
import calendar

def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("🧾 Resumo (Mensal/Semanal)")

    def _sec_to_hms(sec_total: float | int) -> str:
        try: sec = int(round(float(sec_total)))
        except Exception: sec = 0
        h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def kpis(df_slice: pd.DataFrame):
        ofe = pd.to_numeric(df_slice.get("numero_de_corridas_ofertadas",0), errors="coerce").fillna(0).sum()
        ace = pd.to_numeric(df_slice.get("numero_de_corridas_aceitas",0), errors="coerce").fillna(0).sum()
        rej = pd.to_numeric(df_slice.get("numero_de_corridas_rejeitadas",0), errors="coerce").fillna(0).sum()
        com = pd.to_numeric(df_slice.get("numero_de_corridas_completadas",0), errors="coerce").fillna(0).sum()
        seg = pd.to_numeric(df_slice.get("segundos_abs",0), errors="coerce").fillna(0).sum()
        sh_h = float(seg)/3600.0
        acc = float(ace/ofe*100) if ofe>0 else 0.0
        rejp= float(rej/ofe*100) if ofe>0 else 0.0
        if "pessoa_entregadora" in df_slice.columns:
            atividade = df_slice[["segundos_abs","numero_de_corridas_ofertadas","numero_de_corridas_aceitas","numero_de_corridas_completadas"]].fillna(0).sum(axis=1) > 0
            ativos = int(df_slice.loc[atividade, "pessoa_entregadora"].nunique())
        else:
            ativos = 0
        # UTRs
        utr_abs = float(ofe / sh_h) if sh_h>0 else 0.0
        from relatorios import utr_por_entregador_turno
        b = utr_por_entregador_turno(df_slice)
        if b is None or b.empty: utr_med = 0.0
        else:
            b = b[b["supply_hours"]>0]
            utr_med = float((b["corridas_ofertadas"]/b["supply_hours"]).mean()) if not b.empty else 0.0
        return dict(ofe=ofe, ace=ace, rej=rej, com=com, seg=seg, sh_h=sh_h, acc=acc, rejp=rejp, ativos=ativos, utr_abs=utr_abs, utr_med=utr_med)

    def delta_pct(cur, prev):
        if prev is None or prev == 0:
            return None if cur>0 else 0.0
        return float((cur - prev)/prev * 100.0)
    def fmt_pct(v): 
        if v is None: return "—"
        return f"{v:+.2f}%".replace(".", ",")
    def fmt_int(v): 
        try: return f"{int(round(float(v))):,}".replace(",", ".")
        except Exception: return "0"
    def fmt_dec(v): 
        try: return f"{float(v):.2f}".replace(".", ",")
        except Exception: return "0,00"
    def arrow(d): 
        if d is None or abs(d) < 1e-9: return "⚪"
        return "🟢⬆" if d>0 else "🔴⬇"

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    data_min = pd.to_datetime(df["data"]).min().date()
    data_max = pd.to_datetime(df["data"]).max().date()

    tipo = st.radio("Período", ["Semanal (Seg–Dom)","Mensal"], horizontal=True, index=0)

    if tipo.startswith("Semanal"):
        ref_date = st.date_input("Escolha um dia da semana (Seg–Dom)", value=data_max, min_value=data_min, max_value=data_max, format="DD/MM/YYYY")
        ref_ts = pd.to_datetime(ref_date); dow = ref_ts.weekday()
        ini = (ref_ts - pd.Timedelta(days=dow)).normalize(); fim = ini + pd.Timedelta(days=6)
        ini_prev = ini - pd.Timedelta(days=7); fim_prev = fim - pd.Timedelta(days=7)
        header = f"Resumo semanal — Semana {int(ref_ts.isocalendar().week)} ({ini.strftime('%d/%m')}–{fim.strftime('%d/%m')}) • vs semana anterior"
        df_cur  = df[(df["data"] >= ini) & (df["data"] <= fim)].copy()
        df_prev = df[(df["data"] >= ini_prev) & (df["data"] <= fim_prev)].copy()
    else:
        ultimo = pd.to_datetime(df["data"]).max()
        mes_default, ano_default = int(ultimo.month), int(ultimo.year)
        c1, c2 = st.columns(2)
        mes_sel = c1.selectbox("Mês", list(range(1, 13)), index=mes_default-1)
        anos_disp = sorted(df["data"].dt.year.dropna().unique().tolist(), reverse=True)
        ano_sel = c2.selectbox("Ano", anos_disp, index=anos_disp.index(ano_default))
        ndias = calendar.monthrange(ano_sel, mes_sel)[1]
        ini = pd.Timestamp(year=ano_sel, month=mes_sel, day=1)
        fim = pd.Timestamp(year=ano_sel, month=mes_sel, day=ndias)
        if mes_sel == 1: ano_prev, mes_prev = ano_sel-1, 12
        else: ano_prev, mes_prev = ano_sel, mes_sel-1
        ndias_prev = calendar.monthrange(ano_prev, mes_prev)[1]
        ini_prev = pd.Timestamp(year=ano_prev, month=mes_prev, day=1)
        fim_prev = pd.Timestamp(year=ano_prev, month=mes_prev, day=ndias_prev)
        header = f"Resumo mensal — {ini.strftime('%b/%Y').capitalize()} • vs {ini_prev.strftime('%b/%Y').capitalize()}"
        df_cur  = df[(df["data"] >= ini) & (df["data"] <= fim)].copy()
        df_prev = df[(df["data"] >= ini_prev) & (df["data"] <= fim_prev)].copy()

    cur  = kpis(df_cur); prev = kpis(df_prev)
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
