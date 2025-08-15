from utils import normalizar, tempo_para_segundos, calcular_tempo_online
from datetime import datetime, timedelta, date
import pandas as pd

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
        dados = dados[(df["mes"] == mes) & (df["ano"] == ano)]
    if dados.empty:
        return None

    tempo_pct = calcular_tempo_online(dados)

    presencas = dados["data"].nunique()
    if mes and ano:
        dias_no_mes = pd.date_range(start=f"{ano}-{mes:02d}-01", periods=31, freq='D')
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
    aceitas = int(dados["numero_de_corridas_aceitas"].sum())
    rejeitadas = int(dados["numero_de_corridas_rejeitadas"].sum())
    completas = int(dados["numero_de_corridas_completadas"].sum())

    tx_aceitas = round(aceitas / ofertadas * 100, 1) if ofertadas else 0.0
    tx_rejeitadas = round(rejeitadas / ofertadas * 100, 1) if ofertadas else 0.0
    tx_completas = round(completas / aceitas * 100, 1) if aceitas else 0.0

    if mes and ano:
        meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        periodo = f"{meses_pt[mes - 1]}/{ano}"
    else:
        min_data = dados["data"].min().strftime('%d/%m/%Y')
        max_data = dados["data"].max().strftime('%d/%m/%Y')
        periodo = f"{min_data} a {max_data}"

    return gerar_texto(nome, periodo, dias_esperados, presencas, faltas, tempo_pct,
                       turnos, ofertadas, aceitas, rejeitadas, completas,
                       tx_aceitas, tx_rejeitadas, tx_completas)

def gerar_simplicado(nome, mes, ano, df):
    nome_norm = normalizar(nome)
    dados = df[(df["pessoa_entregadora_normalizado"] == nome_norm) &
               (df["mes"] == mes) & (df["ano"] == ano)]
    if dados.empty:
        return None

    tempo_pct = calcular_tempo_online(dados)
    turnos = len(dados)
    ofertadas = int(dados["numero_de_corridas_ofertadas"].sum())
    aceitas = int(dados["numero_de_corridas_aceitas"].sum())
    rejeitadas = int(dados["numero_de_corridas_rejeitadas"].sum())
    completas = int(dados["numero_de_corridas_completadas"].sum())
    tx_aceitas = round(aceitas / ofertadas * 100, 1) if ofertadas else 0.0
    tx_rejeitadas = round(rejeitadas / ofertadas * 100, 1) if ofertadas else 0.0
    tx_completas = round(completas / aceitas * 100, 1) if aceitas else 0.0
    meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    periodo = f"{meses_pt[mes-1]}/{ano}"
    return f"""{nome} – {periodo}

Tempo online: {tempo_pct}%

Turnos realizados: {turnos}

Corridas:
* Ofertadas: {ofertadas}
* Aceitas: {aceitas} ({tx_aceitas}%)
* Rejeitadas: {rejeitadas} ({tx_rejeitadas}%)
* Completas: {completas} ({tx_completas}%)
"""

def gerar_alertas_de_faltas(df):
    hoje = datetime.now().date()
    ultimos_15_dias = hoje - timedelta(days=15)
    ativos = df[df["data"] >= ultimos_15_dias]["pessoa_entregadora_normalizado"].unique()
    mensagens = []

    for nome in ativos:
        entregador = df[df["pessoa_entregadora_normalizado"] == nome]
        if entregador.empty:
            continue
        dias = pd.date_range(end=hoje - timedelta(days=1), periods=30).date
        presencas = set(entregador["data"])
        sequencia = 0
        for dia in sorted(dias):
            sequencia = 0 if dia in presencas else sequencia + 1
        if sequencia >= 4:
            nome_original = entregador["pessoa_entregadora"].iloc[0]
            mensagens.append(
                f"• {nome_original} – {sequencia} dias consecutivos ausente (última presença: {entregador['data'].max().strftime('%d/%m')})"
            )
    return mensagens

def gerar_por_praca_data_turno(df, nome=None, praca=None, data_inicio=None, data_fim=None, turno=None, datas_especificas=None):
    df = df.copy()

    if nome:
        nome_norm = normalizar(nome)
        df = df[df["pessoa_entregadora_normalizado"] == nome_norm]

    if praca:
        df = df[df["praca"] == praca]

    if datas_especificas:
        df = df[df["data"].isin(datas_especificas)]
    elif data_inicio and data_fim:
        df = df[(df["data"] >= data_inicio) & (df["data"] <= data_fim)]

    if turno and "turno" in df.columns:
        df = df[df["turno"] == turno]

    if df.empty:
        return "❌ Nenhum dado encontrado com os filtros aplicados."

# ===== SH mensal e classificação por categoria =====

import pandas as pd
from utils import tempo_para_segundos

def _sh_mensal(dados: pd.DataFrame) -> float:
    """
    Calcula SH (Supply Hours) mensal somando 'tempo_disponivel_absoluto' (HH:MM:SS) e convertendo para horas.
    """
    if "tempo_disponivel_absoluto" not in dados.columns:
        return 0.0
    segundos = dados["tempo_disponivel_absoluto"].apply(tempo_para_segundos).sum()
    return round(segundos / 3600.0, 1)

def _metricas_mensais(dados: pd.DataFrame) -> dict:
    ofertadas = float(dados.get("numero_de_corridas_ofertadas", 0).sum())
    aceitas   = float(dados.get("numero_de_corridas_aceitas", 0).sum())
    completas = float(dados.get("numero_de_corridas_completadas", 0).sum())

    acc_pct  = round((aceitas   / ofertadas) * 100, 1) if ofertadas > 0 else 0.0  # aceitação
    comp_pct = round((completas / aceitas)   * 100, 1) if aceitas   > 0 else 0.0  # conclusão
    sh       = _sh_mensal(dados)

    return {
        "SH": sh,
        "aceitacao_%": acc_pct,
        "conclusao_%": comp_pct,
        "ofertadas": int(ofertadas),
        "aceitas": int(aceitas),
        "completas": int(completas),
    }

def _categoria(sh: float, comp_pct: float, acc_pct: float) -> tuple[str, int, str]:
    """
    Regras:
      Premium     = 3/3:  SH>=120, comp>=95, acc>=65
      Conectado   = >=2/3: SH>=60,  comp>=80, acc>=45
      Casual      = >=1/3: SH>=20,  comp>=60, acc>=30
      Flutuante   = 0/3
    """
    def hits(th):
        return [
            sh       >= th["sh"],
            comp_pct >= th["comp"],
            acc_pct  >= th["acc"],
        ]

    # Premium (precisa bater os 3)
    prem = {"sh": 120, "comp": 95, "acc": 65}
    hp = hits(prem)
    if sum(hp) == 3:
        return "Premium", 3, "SH≥120, comp≥95%, acc≥65%"

    # Conectado (bate 2 ou 3)
    con = {"sh": 60, "comp": 80, "acc": 45}
    hc = hits(con); n = sum(hc)
    if n >= 2:
        desc = []
        if hc[0]: desc.append("SH≥60")
        if hc[1]: desc.append("comp≥80%")
        if hc[2]: desc.append("acc≥45%")
        return "Conectado", n, ", ".join(desc)

    # Casual (bate pelo menos 1)
    cas = {"sh": 20, "comp": 60, "acc": 30}
    hcas = hits(cas); n = sum(hcas)
    if n >= 1:
        desc = []
        if hcas[0]: desc.append("SH≥20")
        if hcas[1]: desc.append("comp≥60%")
        if hcas[2]: desc.append("acc≥30%")
        return "Casual", n, ", ".join(desc)

    return "Flutuante", 0, "nenhum critério"

def classificar_entregadores(df: pd.DataFrame, mes: int | None = None, ano: int | None = None) -> pd.DataFrame:
    """
    Retorna, por entregador, SH (horas), % aceitação, % conclusão, categoria e critérios atingidos.
    Se mes/ano informados, calcula no recorte mensal; senão, usa todo o período carregado.
    """
    dados = df.copy()
    if mes is not None and ano is not None:
        dados = dados[(dados["mes"] == mes) & (dados["ano"] == ano)]
    if dados.empty:
        return pd.DataFrame(columns=[
            "pessoa_entregadora","supply_hours","aceitacao_%","conclusao_%",
            "ofertadas","aceitas","completas","categoria","criterios_atingidos","qtd_criterios"
        ])

    registros = []
    for nome, chunk in dados.groupby("pessoa_entregadora", dropna=True):
        m = _metricas_mensais(chunk)
        cat, qtd, txt = _categoria(m["SH"], m["conclusao_%"], m["aceitacao_%"])
        registros.append({
            "pessoa_entregadora": nome,
            "supply_hours": m["SH"],
            "aceitacao_%": m["aceitacao_%"],
            "conclusao_%": m["conclusao_%"],
            "ofertadas": m["ofertadas"],
            "aceitas": m["aceitas"],
            "completas": m["completas"],
            "categoria": cat,
            "criterios_atingidos": txt,
            "qtd_criterios": qtd
        })

    out = pd.DataFrame(registros)
    if out.empty:
        return out

    ordem = pd.CategoricalDtype(categories=["Premium", "Conectado", "Casual", "Flutuante"], ordered=True)
    out["categoria"] = out["categoria"].astype(ordem)
    out = out.sort_values(by=["categoria", "supply_hours"], ascending=[True, False]).reset_index(drop=True)
    return out

