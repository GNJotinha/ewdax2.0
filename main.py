import streamlit as st
import pandas as pd
from io import BytesIO

from shared import hms_from_hours
from utils import calcular_tempo_online

# Tentativa de importar Pillow (pra imagem do WhatsApp)
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

# ================================
# CONFIGURAÇÕES DO ADICIONAL
# ================================
VALOR_ADICIONAL_HORA = 2.15  # R$/hora
ACEITACAO_MIN = 70.0
COMPLETAS_MIN = 95.0

# ================================
# FORMATADORES
# ================================
def _fmt_pct(x: float) -> str:
    try:
        return f"{float(x):.2f}%".replace(".", ",")
    except Exception:
        return "0,00%"

def _fmt_moeda(x: float) -> str:
    try:
        return f"R$ {float(x):.2f}".replace(".", ",")
    except Exception:
        return "R$ 0,00"

# ================================
# IMAGEM PRO WHATSAPP
# ================================
def _montar_texto_whatsapp(resumo: pd.DataFrame, nome: str, periodo_txt: str) -> str:
    linhas = []
    linhas.append(f"{nome}")
    linhas.append(f"Período: {periodo_txt}")
    linhas.append("")

    for data, df_dia in resumo.groupby("data"):
        data_txt = pd.to_datetime(data).strftime("%d/%m/%Y")
        linhas.append(f"📅 {data_txt}")
        for _, row in df_dia.sort_values("turno").iterrows():
            status = "✅ Elegível" if row["elegivel"] else "❌ Inelegível"
            lin_turno = [
                f"  • Turno: {row['turno']}",
                f"    - Aceitação: {_fmt_pct(row['acc_pct'])}",
                f"    - Completas: {_fmt_pct(row['comp_pct'])}",
                f"    - Tempo online: {row['tempo_online_hms']}",
                f"    - Online (%): {_fmt_pct(row['online_pct'])}",
                f"    - Ofertadas/Aceitas/Completas: {row['ofertadas']}/{row['aceitas']}/{row['completas']}",
                f"    - {status}",
            ]
            if row["elegivel"]:
                lin_turno.append(f"    - Valor: {_fmt_moeda(row['valor_adicional'])}")
            linhas.extend(lin_turno)
        linhas.append("")

    return "\n".join(linhas).strip()


def _gerar_imagem_whatsapp(resumo: pd.DataFrame, nome: str, periodo_txt: str) -> BytesIO | None:
    if Image is None:
        return None

    texto = _montar_texto_whatsapp(resumo, nome, periodo_txt)

    # Configs básicas
    largura = 1080
    padding = 60
    linha_altura = 42

    linhas = texto.split("\n")
    altura = padding * 2 + linha_altura * len(linhas)

    img = Image.new("RGB", (largura, altura), (15, 23, 42))  # fundo dark
    draw = ImageDraw.Draw(img)

    try:
        fonte = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        fonte = ImageFont.load_default()

    y = padding
    for linha in linhas:
        draw.text((padding, y), linha, font=fonte, fill=(230, 230, 230))
        y += linha_altura

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ================================
# VIEW PRINCIPAL
# ================================
def render(df: pd.DataFrame, _USUARIOS: dict):

    st.header("💰 Adicional por Hora — Detalhado por Turno")

    # --------------------------
    # NORMALIZA DATA
    # --------------------------
    base = df.copy()
    if "data" in base.columns:
        base["data"] = pd.to_datetime(base["data"], errors="coerce")
    elif "data_do_periodo" in base.columns:
        base["data"] = pd.to_datetime(base["data_do_periodo"], errors="coerce")
    else:
        st.error("Coluna de data ausente (data ou data_do_periodo).")
        return

    base = base.dropna(subset=["data"])
    if base.empty:
        st.info("Sem dados válidos.")
        return

    # --------------------------
    # 1) FILTRO DE PERÍODO (ANTES)
    # --------------------------
    data_min = base["data"].min().date()
    data_max = base["data"].max().date()
    periodo = st.date_input(
        "Período de análise:",
        [data_min, data_max],
        format="DD/MM/YYYY",
    )

    base_periodo = base.copy()
    if len(periodo) == 2:
        ini, fim = pd.to_datetime(periodo[0]), pd.to_datetime(periodo[1])
        base_periodo = base_periodo[(base_periodo["data"] >= ini) & (base_periodo["data"] <= fim)]

    if base_periodo.empty:
        st.info("❌ Nenhum dado no período selecionado.")
        return

    if len(periodo) == 2:
        periodo_txt = f"{pd.to_datetime(periodo[0]).strftime('%d/%m/%Y')} a {pd.to_datetime(periodo[1]).strftime('%d/%m/%Y')}"
    else:
        periodo_txt = pd.to_datetime(periodo[0]).strftime("%d/%m/%Y")

    # --------------------------
    # 2) SELETOR DE ENTREGADOR (APÓS PERÍODO)
    #    (só nomes que atuaram no período)
    # --------------------------
    nomes = sorted(base_periodo["pessoa_entregadora"].dropna().unique().tolist())
    nome = st.selectbox(
        "🔎 Selecione o entregador:",
        [None] + nomes,
        format_func=lambda x: "" if x is None else x,
    )
    if not nome:
        st.caption("Escolha um entregador para visualizar.")
        return

    ent = base_periodo[base_periodo["pessoa_entregadora"] == nome].copy()
    if ent.empty:
        st.info("❌ Nenhum turno encontrado para esse entregador no período.")
        return

    # --------------------------
    # GARANTE COLUNA DE TURNO
    # --------------------------
    if "periodo" not in ent.columns:
        ent["periodo"] = "(sem turno)"

    # --------------------------
    # AGREGA POR DIA + TURNO
    # --------------------------
    linhas = []

    for (dt, turno), chunk in ent.groupby(["data", "periodo"], dropna=False):

        seg_online = pd.to_numeric(chunk.get("segundos_abs", 0), errors="coerce").fillna(0).sum()
        horas_online = seg_online / 3600.0 if seg_online > 0 else 0.0
        tempo_online_hms = hms_from_hours(horas_online)

        ofertadas = int(pd.to_numeric(chunk.get("numero_de_corridas_ofertadas", 0), errors="coerce").fillna(0).sum())
        aceitas   = int(pd.to_numeric(chunk.get("numero_de_corridas_aceitas", 0), errors="coerce").fillna(0).sum())
        completas = int(pd.to_numeric(chunk.get("numero_de_corridas_completadas", 0), errors="coerce").fillna(0).sum())

        acc_pct  = (aceitas / ofertadas * 100) if ofertadas > 0 else 0.0
        comp_pct = (completas / aceitas * 100) if aceitas > 0 else 0.0

        online_pct = calcular_tempo_online(chunk)

        elegivel = (
            acc_pct >= ACEITACAO_MIN
            and comp_pct >= COMPLETAS_MIN
            and horas_online > 0
        )
        valor = horas_online * VALOR_ADICIONAL_HORA if elegivel else 0.0

        linhas.append({
            "data": dt.date(),
            "turno": str(turno),
            "ofertadas": ofertadas,
            "aceitas": aceitas,
            "completas": completas,
            "acc_pct": acc_pct,
            "comp_pct": comp_pct,
            "horas_online": horas_online,
            "tempo_online_hms": tempo_online_hms,
            "online_pct": online_pct,
            "elegivel": elegivel,
            "valor_adicional": valor,
        })

    if not linhas:
        st.info("Nenhum turno encontrado.")
        return

    resumo = pd.DataFrame(linhas).sort_values(["data", "turno"])

    # --------------------------
    # RESUMO GERAL
    # --------------------------
    total_elegiveis = resumo["elegivel"].sum()
    total_valor = resumo.loc[resumo["elegivel"], "valor_adicional"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Turnos elegíveis", int(total_elegiveis))
    c2.metric("Total adicional", _fmt_moeda(total_valor))
    c3.metric("Turnos totais", int(resumo.shape[0]))

    st.divider()

    # ================================
    # DETALHADO DIA → TURNO
    # ================================
    for data, df_dia in resumo.groupby("data"):

        data_txt = pd.to_datetime(data).strftime("%d/%m/%Y")
        n_turnos = df_dia.shape[0]
        total_valor_dia = df_dia.loc[df_dia["elegivel"], "valor_adicional"].sum()

        with st.container(border=True):
            st.subheader(f"📅 {data_txt} — {n_turnos} turno(s)")
            st.caption(
                f"Elegíveis: {int(df_dia['elegivel'].sum())}/{n_turnos} • "
                f"Total do dia: {_fmt_moeda(total_valor_dia)}"
            )

            registros = df_dia.to_dict(orient="records")
            for i in range(0, len(registros), 2):
                cols = st.columns(2)
                for col, row in zip(cols, registros[i:i+2]):
                    with col:
                        elegivel = bool(row["elegivel"])
                        with st.container(border=True):

                            st.markdown(f"### 🕒 Turno: **{row['turno']}**")

                            st.markdown(
                                f"- **Aceitação:** {_fmt_pct(row['acc_pct'])}  \n"
                                f"- **Completas:** {_fmt_pct(row['comp_pct'])}  \n"
                                f"- **Tempo online:** {row['tempo_online_hms']}  \n"
                                f"- **Online (%):** {_fmt_pct(row['online_pct'])}  \n"
                                f"- **Ofertadas:** {row['ofertadas']}  \n"
                                f"- **Aceitas:** {row['aceitas']}  \n"
                                f"- **Completas:** {row['completas']}"
                            )

                            # Caixinhas estilizadas em vez do success padrão
                            if elegivel:
                                st.markdown(
                                    f"""
                                    <div style="
                                        margin-top:0.5rem;
                                        padding:0.75rem 1rem;
                                        border-radius:0.75rem;
                                        background-color:#14532d;
                                        border:1px solid #16a34a;
                                        color:#e5e7eb;
                                        font-size:0.95rem;">
                                        <div style="font-weight:600;color:#bbf7d0;">
                                            ✅ Elegível ao adicional!
                                        </div>
                                        <div style="margin-top:0.25rem;">
                                            Valor: <b>{_fmt_moeda(row['valor_adicional'])}</b>
                                        </div>
                                        <div style="margin-top:0.25rem;font-size:0.85rem;color:#9ca3af;">
                                            ({row['horas_online']:.2f} h × {_fmt_moeda(VALOR_ADICIONAL_HORA)}/h)
                                        </div>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )
                            else:
                                motivos = []
                                if row["acc_pct"] < ACEITACAO_MIN:
                                    motivos.append(f"aceitação < {ACEITACAO_MIN:.0f}%")
                                if row["comp_pct"] < COMPLETAS_MIN:
                                    motivos.append(f"completas < {COMPLETAS_MIN:.0f}%")
                                if row["horas_online"] <= 0:
                                    motivos.append("sem horas online")
                                motivos_txt = "; ".join(motivos) if motivos else "critérios não atendidos"

                                st.markdown(
                                    f"""
                                    <div style="
                                        margin-top:0.5rem;
                                        padding:0.75rem 1rem;
                                        border-radius:0.75rem;
                                        background-color:#450a0a;
                                        border:1px solid #dc2626;
                                        color:#fee2e2;
                                        font-size:0.95rem;">
                                        <div style="font-weight:600;">
                                            ❌ Inelegível ao adicional
                                        </div>
                                        <div style="margin-top:0.25rem;font-size:0.85rem;color:#fecaca;">
                                            Motivo: {motivos_txt}
                                        </div>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )

    st.divider()

    # ================================
    # IMAGEM PRO WHATSAPP
    # ================================
    st.subheader("📲 Exportar visão em imagem (WhatsApp)")

    if Image is None:
        st.info("Para gerar a imagem, adicione a dependência `Pillow` no ambiente (requirements.txt).")
    else:
        img_bytes = _gerar_imagem_whatsapp(resumo, nome, periodo_txt)
        if img_bytes:
            st.image(img_bytes, caption="Prévia da imagem para WhatsApp", use_column_width=True)
            st.download_button(
                "⬇️ Baixar imagem (PNG)",
                data=img_bytes,
                file_name=f"adicional_{nome.replace(' ','_')}.png",
                mime="image/png",
                use_container_width=True,
            )
