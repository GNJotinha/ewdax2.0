from utils import normalizar, tempo_para_segundos
import pandas as pd
from datetime import datetime, timedelta

# ✅ NOVA FUNÇÃO: Consolida múltiplas linhas no mesmo turno (ex: entregador muda de praça no mesmo período)
def consolidar_turnos_por_nome(df):
    import pandas as pd

    # Converte para data (sem hora)
    df['data'] = pd.to_datetime(df['data_do_periodo']).dt.date

    # Converte colunas de tempo para timedelta
    df['tempo_disponivel_absoluto'] = pd.to_timedelta(df['tempo_disponivel_absoluto'].astype(str) + ':00', errors='coerce')
    df['duracao_do_periodo'] = pd.to_timedelta(df['duracao_do_periodo'].astype(str) + ':00', errors='coerce')

    # Agrupa por entregador + dia + turno
    resumo = df.groupby(['pessoa_entregadora', 'data', 'periodo']).agg({
        'tempo_disponivel_absoluto': 'sum',
        'duracao_do_periodo': 'first'
    }).reset_index()

    # Calcula % de presença
    resumo['percentual_presenca'] = (resumo['tempo_disponivel_absoluto'] / resumo['duracao_do_periodo']) * 100
    resumo['percentual_presenca'] = resumo['percentual_presenca'].round(1)

    return resumo

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
    df["tempo_segundos"] = df["tempo_disponivel_absoluto"].apply(tempo_para_segundos)
    df["duracao_segundos"] = df["duracao_do_periodo"].apply(tempo_para_segundos)
    dados = df[(df["pessoa_entregadora_normalizado"] == nome_norm)]
    if mes and ano:
        dados = dados[(df["mes"] == mes) & (df["ano"] == ano)]
    if dados.empty:
        return None

    tempo_disp = dados["tempo_segundos"].mean()
    duracao_media = dados["duracao_segundos"].mean()
    tempo_pct = round(tempo_disp / duracao_media * 100, 1) if duracao_media else 0.0

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
    tempo_disp = dados["tempo_disponivel_absoluto"].apply(tempo_para_segundos).mean()
    duracao = dados["duracao_do_periodo"].apply(tempo_para_segundos).mean()
    tempo_pct = round(tempo_disp / duracao * 100, 1) if duracao else 0.0
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
