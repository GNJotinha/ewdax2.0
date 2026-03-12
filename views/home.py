import streamlit as st
import pandas as pd
from datetime import date, timedelta

from db import db_conn, fetch_all, ensure_table_exists


IMPORTS_TABLE = "imports"


def _datas_importadas_faltando() -> list[date]:
    """Retorna os dias faltantes na sequência de file_date da tabela imports.

    Regras:
    - usa somente imports.file_date válidas
    - compara do menor dia importado até o menor entre:
      * maior file_date importado
      * ontem
    - hoje nunca entra como faltando
    - se não houver base suficiente, retorna []
    """
    try:
        with db_conn() as conn:
            if not ensure_table_exists(conn, IMPORTS_TABLE):
                return []

            cols, rows = fetch_all(
                conn,
                """
                select file_date
                from public.imports
                where file_date is not null
                order by file_date asc
                """,
            )
    except Exception:
        return []

    if not rows:
        return []

    datas = pd.to_datetime([r[0] for r in rows], errors="coerce").dropna()
    if len(datas) == 0:
        return []

    datas_set = {d.date() for d in datas}
    if not datas_set:
        return []

    inicio = min(datas_set)
    fim_importado = max(datas_set)
    ontem = date.today() - timedelta(days=1)
    fim = min(fim_importado, ontem)

    if inicio > fim:
        return []

    faltando: list[date] = []
    cursor = inicio
    while cursor <= fim:
        if cursor not in datas_set:
            faltando.append(cursor)
        cursor += timedelta(days=1)

    return faltando


def _fmt_datas_br(datas: list[date]) -> str:
    return ", ".join(d.strftime("%d/%m/%Y") for d in datas)


def render(_df: pd.DataFrame, _USUARIOS: dict):
    faltando = _datas_importadas_faltando()

    if faltando:
        st.error(
            "⚠️ Atenção: há dia(s) sem importação detectados: "
            f"{_fmt_datas_br(faltando)}"
        )

    st.markdown("# PÁGINA INICIAL EM MANUTENÇÃO")
