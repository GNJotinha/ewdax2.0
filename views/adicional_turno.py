import streamlit as st
import pandas as pd
from io import BytesIO

from shared import hms_from_hours
from utils import calcular_tempo_online

# Tentativa de importar Pillow (pra gerar a imagem dos cards)
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
# IMAGEM ÚNICA COM TODOS OS CARDS
# ================================
def _gerar_imagem_cards(resumo: pd.DataFrame) -> BytesIO | None:
    """
    Gera UMA imagem que é basicamente a união dos cards de turno:
      - um card por linha (data + turno + métricas)
      - bloco verde/vermelho embaixo, igual ao da interface
      - tudo empilhado em uma única imagem vertical
    """
    if Image is None:
        return None

    resumo = resumo.sort_values(["data", "turno"]).copy()

    # Layout do card
    largura = 1080
    margin_x = 40
    margin_y = 40
    espacamento_cards = 30
    card_altura = 270       # card preto (título + métricas)
    block_altura = 90       # bloco verde/vermelho embaixo

    n_cards = resumo.shape[0]
    altura_total = (
        margin_y * 2
        + n_cards * (card_altura + block_altura)
        + (n_cards - 1) * espacamento_cards
    )

    bg_color = (15, 23, 42)   # fundo geral
    card_color = (24, 33, 58) # card preto

    img = Image.new("RGB", (largura, altura_total), bg_color)
    draw = ImageDraw.Draw(img)

    # Fontes
    try:
        fonte_titulo = ImageFont.truetype("arial.ttf", 40)
        fonte_turno = ImageFont.truetype("arial.ttf", 34)
        fonte_txt = ImageFont.truetype("arial.ttf", 26)
        fonte_small = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        fonte_titulo = fonte_turno = fonte_txt = fonte_small = ImageFont.load_default()

    def draw_rounded(x0, y0, x1, y1, radius, fill, outline, width=2):
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)

    y = margin_y

    for _, row in resumo.iterrows():
        # ---- CARD PRETO (título + métricas) ----
        card_top = y
        card_bottom = y + card_altura
        card_left = margin_x
        card_right = largura - margin_x

        draw_rounded(
            card_left,
            card_top,
            card_right,
            card_bottom,
            radius=30,
            fill=card_color,
            outline=(55, 65, 81),
            width=2,
        )

        # Data e turno (estilo parecido com a UI)
        data_txt = pd.to_datetime(row["data"]).strftime("%d/%m/%Y")
        turno_txt = f"Turno: {row['turno']}"

        draw.text(
            (card_left + 30, card_top + 20),
            data_txt,
            font=fonte_titulo,
            fill=(248, 250, 252),
        )
        draw.text(
            (card_left + 30, card_top + 70),
            turno_txt,
            font=fonte_turno,
            fill=(248, 250, 252),
        )

        # Métricas
        x_txt = card_left + 40
        y_txt = card_top + 120
        linhas = [
            f"Aceitação: {_fmt_pct(row['acc_pct'])}",
            f"Completas: {_fmt_pct(row['comp_pct'])}",
            f"Tempo online: {row['tempo_online_hms']}",
            f"Online (%): {_fmt_pct(row['online_pct'])}",
            f"Ofertadas: {row['ofertadas']}",
            f"Aceitas: {row['aceitas']}",
            f"Completas: {row['completas']}",
        ]
        for lin in linhas:
            draw.text((x_txt, y_txt), lin, font=fonte_txt, fill=(229, 231, 235))
            y_txt += 30

        # ---- BLOCO VERDE / VERMELHO ABAIXO (igual card de resultado) ----
        block_top = card_bottom + 8
        block_bottom = block_top + block_altura
        block_left = card_left
        block_right = card_right

        if row["elegivel"]:
            fill = (22, 101, 52)
            outline = (34, 197, 94)
            title = "✅ Elegível ao adicional!"
            sub1 = f"Valor: {_fmt_moeda(row['valor_adicional'])}"
            sub2 = f"({row['horas_online']:.2f} h × {_fmt_moeda(VALOR_ADICIONAL_HORA)}/h)"
            txt_color = (240, 253, 244)
            sub_color = (220, 252, 231)
        else:
            fill = (127, 29, 29)
            outline = (248, 113, 113)
            title = "❌ Inelegível ao adicional"
            motivos = []
            if row["acc_pct"] < ACEITACAO_MIN:
                motivos.append(f"aceitação < {ACEITACAO_MIN:.0f}%")
            if row["comp_pct"] < COMPLETAS_MIN:
                motivos.append(f"completas < {COMPLETAS_MIN:.0f}%")
            if row["horas_online"] <= 0:
                motivos.append("sem horas online")
            sub1 = "; ".join(motivos) if motivos else "critérios não atendidos"
            sub2 = ""
            txt_color = (254, 242, 242)
            sub_color = (254, 226, 226)

        draw_rounded(
            block_left,
            block_top,
            block_right,
            block_bottom,
            radius=25,
            fill=fill,
            outline=outline,
            width=2,
        )

        draw.text(
            (block_left + 30, block_top + 10),
            title,
            font=fonte_txt,
            fill=txt_color,
        )
        draw.text(
            (block_left + 30, block_top + 45),
            sub1,
            font=fonte_txt,
            fill=sub_color,
        )
        if sub2:
            draw.text(
                (block_left + 30, block_top + 70),
                sub2,
                font=fonte_small,
                fill=sub_color,
            )

        # Próximo card (pula card + bloco + espaçamento)
        y = block_bottom + espacamento_cards

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
    # DETALHADO DIA → TURNO (CARDS NA TELA)
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
    # IMAGEM ÚNICA PRA WHATSAPP
    # ================================
    st.subheader("📲 Baixar imagem única com todos os cards")

    if Image is None:
        st.info("Para gerar a imagem, adicione `Pillow` no requirements (ex: Pillow>=10).")
        return

    img_bytes = _gerar_imagem_cards(resumo)
    if img_bytes:
        st.download_button(
            "⬇️ Baixar imagem (PNG)",
            data=img_bytes,
            file_name=f"adicional_{nome.replace(' ', '_')}.png",
            mime="image/png",
            use_container_width=True,
        )
