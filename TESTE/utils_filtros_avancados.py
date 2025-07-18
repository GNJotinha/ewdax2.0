# 🔍 FILTRO AVANÇADO DE RELATÓRIOS
import pandas as pd
from datetime import date

def filtrar_dados_avancado(df, data_ini=None, data_fim=None, dias_especificos=None,
                            turnos=None, pracas=None, entregador=None):
    df['data'] = pd.to_datetime(df['data_do_periodo']).dt.date

    filtro = pd.Series([True] * len(df))

    if data_ini:
        filtro &= df['data'] >= data_ini
    if data_fim:
        filtro &= df['data'] <= data_fim
    if dias_especificos:
        filtro &= df['data'].apply(lambda d: d.day in dias_especificos)
    if turnos:
        filtro &= df['periodo'].isin(turnos)
    if pracas:
        filtro &= df['praca'].isin(pracas)
    if entregador and entregador != "Todos":
        filtro &= df['pessoa_entregadora'] == entregador

    return df[filtro]