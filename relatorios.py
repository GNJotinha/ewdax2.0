# relatorios.py

from utils import normalizar, tempo_para_segundos, calcular_tempo_online
from datetime import datetime, timedelta, date
import pandas as pd


# =========================
# Utilidades / básicos
# =========================

def get_entregadores(df):
    return [""] + sorted(df["pessoa_entregadora"].dropna().unique().tolist())


def gerar_texto(nome, periodo, dias_esperados, presencas, faltas, tempo_pct,
                turnos, ofertadas, aceitas, rejeitadas, completas,
                tx_aceitas, tx_rejeitadas, tx_completas):
    return f"""📋 {nome} – {periodo}

📆 Dias esperados: {dias_esperados}
✅ Presenças: {presencas}
❌ Faltas: {faltas}

⏱️ Tempo online: {tempo_pct}%

🧾 Turnos realizados: {turnos}

🚗 Corridas:
• 📦 Ofertadas: {ofertadas}
• 👍 Aceitas: {aceitas} ({tx_aceitas}%)
• 👎 Rejeitadas: {rejeitadas} ({tx_rejeitadas}%)
• 🏁 Completas: {completas} ({tx_completas}%)
"""


def gerar_dados(nome, mes, ano, df):
    nome_norm = normalizar(nome)
    dados = df[(df["pessoa_entregadora_normalizado"] == nome_norm)]
    if mes and ano:
        # FIX: filtra sobre 'dados' (não sobre df)
        dados = dados[(dados["mes"] == mes) & (dados["ano"] == ano)]
    if dados.empty:
        return None

    tempo_pct = calcular_tempo_online(dados)

    presencas = dados["data"].nunique()
    if mes and ano:
        dias_no_mes = pd.date_range(start=f"{ano}-{mes:02d}-01", periods=31, freq="D")
        dias_no_mes = dias_no_mes[dias_no_mes.month == mes]
        faltas = len(dias_no_mes) - presencas
        dias_esperados = len(dias_no_mes)
    else:
        min_data = dados["data"].min()
        max_data = dados["data"].max()
        dias_esperados = (max_data - min_data).days + 1
        faltas = dias_esperados - presencas

    turnos = len(dados)
    ofertadas = int(dados["numero_de_corridas_ofertadas"].sum())
    aceitas   = int(dados["numero_de_corridas_aceitas"].sum())
    rejeitadas= int(dados["numero_de_corridas_rejeitadas"].sum())
    completas = int(dados["numero_de_corridas_completadas"].sum())

    tx_aceitas    = round(aceitas    / ofertadas * 100, 1) if ofertadas else 0.0
    tx_rejeitadas = round(rejeitadas / ofertadas * 100, 1) if ofertadas else 0.0
    tx_completas  = round(completas  / aceitas   * 100, 1) if aceitas   else 0.0

    if mes and ano:
        meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        periodo = f"{meses_pt[mes - 1]}/{ano}"
    else:
        min_data = dados["data"].min().strftime("%d/%m/%Y")
        max_data = dados["data"].max().strftime("%d/%m/%Y")
        periodo = f"{min_data} a {max_data}"

    return gerar_texto(nome, periodo, dias_esperados, presencas, faltas, tempo_pct,
