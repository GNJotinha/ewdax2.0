from utils import normalizar, tempo_para_segundos, calcular_tempo_online
from datetime import date
import pandas as pd

# ==== utilidades internas ====
COL_OFERTADAS = "corridas_ofertadas"
COL_ACEITAS   = "corridas_aceitas"
COL_REJEITADAS= "corridas_rejeitadas"
COL_COMPLETAS = "corridas_completadas"
COL_TEMPO_ABS = "tempo_disponivel_absoluto"  # em HH:MM:SS ou segundos
COL_TURNO     = "periodo"                      # manhã/tarde/noite, se existir

# -----------------------------

def get_entregadores(df):
    return [""] + sorted(df["pessoa_entregadora"].dropna().unique().tolist())

# -----------------------------

def _filtros_base(df, nome=None, mes=None, ano=None, subpraca=None, turno=None, data_ini=None, data_fim=None):
    dados = df.copy()
    if nome:
        dados = dados[dados["pessoa_entregadora_normalizado"] == normalizar(nome)]
    if mes is not None:
        dados = dados[dados["mes"] == int(mes)]
    if ano is not None:
        dados = dados[dados["ano"] == int(ano)]
    if subpraca and "subpraca" in dados.columns:
        dados = dados[dados["subpraca"].astype(str) == str(subpraca)]
    if turno and COL_TURNO in dados.columns:
        dados = dados[dados[COL_TURNO].astype(str) == str(turno)]
    if data_ini:
        dados = dados[pd.to_datetime(dados["data"]) >= pd.to_datetime(data_ini)]
    if data_fim:
        dados = dados[pd.to_datetime(dados["data"]) <= pd.to_datetime(data_fim)]
    return dados

# -----------------------------

def gerar_dados(df, nome=None, mes=None, ano=None, subpraca=None, turno=None, data_ini=None, data_fim=None):
    dados = _filtros_base(df, nome, mes, ano, subpraca, turno, data_ini, data_fim)
    if dados.empty:
        return None

    # Presenças e faltas
    presencas = dados["data"].nunique()
    if mes and ano:
        # dias úteis esperados ~ total de dias do mês presentes na base (semelhante ao seu comportamento)
        dias_mes = pd.date_range(start=f"{int(ano)}-{int(mes):02d}-01", periods=31, freq="D")
        dias_mes = dias_mes[dias_mes.month == int(mes)]
        dias_esperados = len(dias_mes)
        faltas = max(dias_esperados - presencas, 0)
    else:
        dias_esperados = presencas
        faltas = 0

    # Tempo online (0–100)
    tempo_pct = calcular_tempo_online(dados)

    # Totais de corridas
    def _soma(col):
        return int(dados.get(col, pd.Series(dtype=float)).fillna(0).sum())

    ofertadas  = _soma(COL_OFERTADAS)
    aceitas    = _soma(COL_ACEITAS)
    rejeitadas = _soma(COL_REJEITADAS)
    completas  = _soma(COL_COMPLETAS)

    # Taxas
    tx_aceitas    = round((aceitas   / ofertadas)*100, 1) if ofertadas > 0 else 0.0
    tx_rejeitadas = round((rejeitadas/ ofertadas)*100, 1) if ofertadas > 0 else 0.0
    tx_completas  = round((completas / ofertadas)*100, 1) if ofertadas > 0 else 0.0

    turnos = dados[COL_TURNO].dropna().unique().tolist() if COL_TURNO in dados.columns else []

    periodo_txt = (
        f"{mes:02d}/{ano}" if mes and ano else
        f"{pd.to_datetime(dados['data']).min():%d/%m/%Y} a {pd.to_datetime(dados['data']).max():%d/%m/%Y}"
    )

    return {
        "nome": nome or "Geral",
        "periodo": periodo_txt,
        "dias_esperados": int(dias_esperados),
        "presencas": int(presencas),
        "faltas": int(faltas),
        "tempo_pct": float(tempo_pct),
        "turnos": turnos,
        "ofertadas": int(ofertadas),
        "aceitas": int(aceitas),
        "rejeitadas": int(rejeitadas),
        "completas": int(completas),
        "tx_aceitas": float(tx_aceitas),
        "tx_rejeitadas": float(tx_rejeitadas),
        "tx_completas": float(tx_completas),
        "dados": dados,
    }

# -----------------------------

def gerar_simplificado(df, nome=None, mes1=None, ano1=None, mes2=None, ano2=None):
    d1 = gerar_dados(df, nome=nome, mes=mes1, ano=ano1)
    d2 = gerar_dados(df, nome=nome, mes=mes2, ano=ano2)
    return d1, d2

# -----------------------------

def gerar_alertas_de_faltas(df, dias_olho: int = 30, sequencia_min: int = 4):
    # considera quem teve atividade nos últimos 15 dias ou que exista na base recente
    ref_data = pd.to_datetime(df["data"]).max() if not df.empty else pd.Timestamp(date.today())
    janela_ini = ref_data - pd.Timedelta(days=dias_olho)
    recente = df[(pd.to_datetime(df["data"]) >= janela_ini)]

    alertas = []
    for nome in recente["pessoa_entregadora"].dropna().unique():
        sub = recente[recente["pessoa_entregadora"] == nome]
        dias = sorted(pd.to_datetime(sub["data"]).dt.normalize().unique())
        # construir sequência de faltas comparando dias corridos
        faltas_atual = 0
        max_faltas = 0
        # percorre do início ao fim da janela
        dia = janela_ini.normalize()
        while dia <= ref_data.normalize():
            if dia in dias:
                faltas_atual = 0
            else:
                faltas_atual += 1
                max_faltas = max(max_faltas, faltas_atual)
            dia += pd.Timedelta(days=1)
        if max_faltas >= sequencia_min:
            alertas.append({"pessoa_entregadora": nome, "maior_sequencia_faltas": int(max_faltas)})

    out = pd.DataFrame(alertas).sort_values("maior_sequencia_faltas", ascending=False)
    return out

# -----------------------------

def classificar_entregadores(df):
    registros = []
    for nome, grp in df.groupby("pessoa_entregadora"):
        # Supply Hours
        if COL_TEMPO_ABS in grp.columns:
            segundos = grp[COL_TEMPO_ABS].fillna(0).apply(tempo_para_segundos).sum()
        else:
            segundos = 0
        sh = segundos / 3600.0

        # taxas
        ofertadas = grp.get(COL_OFERTADAS, pd.Series(dtype=float)).fillna(0).sum()
        aceitas   = grp.get(COL_ACEITAS,   pd.Series(dtype=float)).fillna(0).sum()
        completas = grp.get(COL_COMPLETAS, pd.Series(dtype=float)).fillna(0).sum()
        tx_aceit  = (aceitas/ ofertadas)*100 if ofertadas>0 else 0.0
        tx_comp   = (completas/ofertadas)*100 if ofertadas>0 else 0.0

        # classificação (regras do seu app)
        hits = 0
        if sh >= 120 and tx_comp >= 95 and tx_aceit >= 65:
            categoria = "Premium"
        else:
            if sh >= 60: hits += 1
            if tx_comp >= 80: hits += 1
            if tx_aceit >= 45: hits += 1
            if hits >= 2:
                categoria = "Conectado"
            elif hits >= 1:
                categoria = "Casual"
            else:
                categoria = "Flutuante"

        registros.append({
            "pessoa_entregadora": nome,
            "supply_hours": round(sh,1),
            "taxa_aceitacao": round(tx_aceit,1),
            "taxa_conclusao": round(tx_comp,1),
            "categoria": categoria,
        })

    return pd.DataFrame(registros).sort_values(["categoria","supply_hours"], ascending=[True, False])

# -----------------------------

def utr_por_entregador_turno(df):
    linhas = []
    for (nome, turno), grp in df.groupby(["pessoa_entregadora", COL_TURNO], dropna=True):
        # horas
        segundos = grp.get(COL_TEMPO_ABS, pd.Series(dtype=float)).fillna(0).apply(tempo_para_segundos).sum()
        horas = segundos/3600.0
        ofertadas = grp.get(COL_OFERTADAS, pd.Series(dtype=float)).fillna(0).sum()
        utr = (ofertadas/horas) if horas>0 else 0.0
        linhas.append({
            "pessoa_entregadora": nome,
            COL_TURNO: turno,
            "horas": round(horas,1),
            COL_OFERTADAS: int(ofertadas),
            "UTR": round(float(utr),2)
        })
    return pd.DataFrame(linhas)

# -----------------------------

def utr_pivot_por_entregador(df):
    base = utr_por_entregador_turno(df)
    if base.empty:
        return base
    piv = base.pivot_table(index="pessoa_entregadora", columns=COL_TURNO, values="UTR", aggfunc="mean").fillna(0.0)
    piv["__media__"] = piv.mean(axis=1)
    piv = piv.sort_values("__media__", ascending=False).drop(columns="__media__")
    return piv.round(2)
