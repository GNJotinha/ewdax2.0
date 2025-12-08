import streamlit as st
import pandas as pd
from io import BytesIO

from shared import hms_from_hours
from utils import calcular_tempo_online

# Tentativa de importar Pillow (para gerar a imagem dos cards)
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
# TEXTO E IMAGEM DOS CARDS
# ================================
def _gerar_imagem_cards(resumo: pd.DataFrame, nome: str, periodo_txt: str) -> BytesIO | None:
    """
    Gera uma imagem única com "cards" empilhados (como se fosse a união
    dos cards da tela) para envio via WhatsApp.
    """
    if Image is None:
        return None

    # Ordena para garantir consistência
    resumo = resumo.sort_values(["data", "turno"]).copy()

    # Layout básico da imagem
    largura = 1080
    margin_x = 40
    margin_y = 40
    espacamento_cards = 30
    card_altura = 230  # altura de cada card
    header_altura = 110

    n_cards = resumo.shape[0]
    altura_total = margin_y * 2 + header_altura + n_cards * card_altura + (n_cards - 1) * espacamento_cards

    # Cria imagem base (fundo escuro, na pegada do painel)
    img = Image.new("RGB", (largura, altura_total), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    # Fonte
    try:
        fonte_titulo = ImageFont.truetype("arial.ttf", 40)
        fonte_sub = ImageFont.truetype("arial.ttf", 30)
        fonte_txt = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        fonte_titulo = fonte_sub = fonte_txt = ImageFont.load_default()

    # Header com nome e período
    y = margin_y
    draw.text((margin_x, y), f"{nome}", font=fonte_titulo, fill=(240, 240, 240))
    y += 55
    draw.text((margin_x, y), f"Período: {periodo_txt}", font=fonte_sub, fill=(200, 200, 200))
    y += header_altura - 55

    # Helper para desenhar um "card" simples
    def draw_card(x0, y0, x1, y1, fill, outline):
        draw.rounded_rectangle([x0, y0, x1, y1], radius=25, fill=fill, outline=outline, width=2)

    # Desenha um card por turno
    for _, row in resumo.iterrows():
        card_top = y
        card_bottom = y + card_altura
        card_left = margin_x
        card_right = largura - margin_x

        # Card principal (fundo)
        draw_card(card_left, card_top, card_right, card_bottom, fill=(24, 33, 58), outline=(37, 99, 235))

        # Título
        data_txt = pd.to_datetime(row["data"]).strftime("%d/%m/%Y")
        titulo = f"{data_txt} • {row['turno']}"
        draw.text((card_left + 25, card_top + 18), titulo, font=fonte_sub, fill=(226, 232, 240))

        # Linhas de texto dentro do card
        y_txt = card_top + 70
        x_txt = card_left + 35

        linhas = [
            f"Aceitação: {_fmt_pct(row['acc_pct'])}",
            f"Completas: {_fmt_pct(row['comp_pct'])}",
            f"Tempo online: {row['tempo_online_hms']}",
            f"Online (%): {_fmt_pct(row['online_pct'])}",
            f"Ofertadas/Aceitas/Completas: {row['ofertadas']}/{row['aceitas']}/{row['completas']}",
        ]

        for lin in linhas:
            draw.text((x_txt, y_txt), lin, font=fonte_txt, fill=(209, 213, 219))
            y_txt += 32

        # Badge de elegível/inelegível no canto direito
        badge_width = 330
        badge_height = 70
        bx0 = card_right - badge_width - 30
        by0 = card_top + 30
        bx1 = bx0 + badge_width
        by1 = by0 + badge_height

        if row["elegivel"]:
            badge_fill = (21, 83, 45)
            badge_outline = (22, 163, 74)
            badge_text1 = "Elegível ao adicional"
            badge_text2 = f"Valor: {_fmt_moeda(row['valor_adicional'])}"
            text_color1 = (187, 247, 208)
            text_color2 = (220, 252, 231)
        else:
            badge_fill = (69, 10, 10)
            badge_outline = (220, 38, 38)
            badge_text1 = "Inelegível ao adicional"
            # motivos simples
            motivos = []
            if row["acc_pct"] < ACEITACAO_MIN:
                motivos.append(f"aceitação < {ACEITACAO_MIN:.0f}%")
            if row["comp_pct"] < COMPLETAS_MIN:
                motivos.append(f"completas < {COMPLETAS_MIN:.0f}%")
            if row["horas_online"] <= 0:
                motivos.append("sem horas online")
            badge_text2 = "; ".join(motivos) if motivos else "critérios não atendidos"
            text_color1 = (254, 226, 226)
            text_color2 = (254, 202, 202)

        draw_card(bx0, by0, bx1, by1, fill=badge_fill, outline=badge_outline)
        draw.text((bx0 + 18, by0 + 10), badge_text1, font=fonte_txt, fill=text_color1)
        draw.text((bx0 + 18, by0 + 38), badge_text2, font=fonte_txt, fill=text_color2)

        # Avança para o próximo card
        y = card_bottom + espacamento_cards

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
    #    (só quem atuou no período)
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
    # DETALHADO DIA → TURNO (CARDS)
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

                            # Caixinhas estilizadas (verde/vermelho), fonte padrão da página
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
    # IMAGEM ÚNICA DOS CARDS (WHATSAPP)
    # ================================
    st.subheader("📲 Baixar imagem com todos os cards (WhatsApp)")

    if Image is None:
        st.info("Para gerar a imagem, adicione a dependência `Pillow` no ambiente (requirements.txt).")
        return

    img_bytes = _gerar_imagem_cards(resumo, nome, periodo_txt)
    if img_bytes:
        st.download_button(
            "⬇️ Baixar imagem (PNG)",
            data=img_bytes,
            file_name=f"adicional_{nome.replace(' ','_')}.png",
            mime="image/png",
            use_container_width=True,
        )
