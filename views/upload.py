import os
import io
import re
import csv
import hashlib
from datetime import datetime, timezone

import streamlit as st
import pandas as pd
import psycopg

from db import get_dsn, ensure_import_columns, audit_log


RAW_TABLE = "base_2025_raw"
IMPORTS_TABLE = "imports"

_ident_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_date_in_name = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _safe_ident(name: str) -> str:
    if not _ident_re.match(name or ""):
        raise ValueError(f"Identificador inválido: {name!r}")
    return name


def _decode_csv_bytes(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except Exception:
        return data.decode("latin1")


def _sniff_delimiter(text: str) -> str:
    first = text.splitlines()[0] if text else ""
    return ";" if first.count(";") >= first.count(",") else ","


def _parse_header(text: str, delimiter: str) -> list[str]:
    f = io.StringIO(text)
    reader = csv.reader(f, delimiter=delimiter, quotechar='"')
    rows = list(reader)
    if not rows:
        raise ValueError("CSV vazio.")
    header = [c.strip() for c in rows[0]]
    for h in header:
        _safe_ident(h)
    return header


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        select 1 from information_schema.tables
        where table_schema='public' and table_name=%s
        limit 1
        """,
        (table,),
    )
    return cur.fetchone() is not None


def _get_columns(cur, table: str) -> list[str]:
    cur.execute(
        """
        select column_name
        from information_schema.columns
        where table_schema='public' and table_name=%s
        order by ordinal_position
        """,
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def _parse_file_date(filename: str):
    """
    Tenta extrair YYYY-MM-DD do nome do arquivo (ex: 2026-02-10.csv).
    Retorna date ou None.
    """
    m = _date_in_name.search(filename or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except Exception:
        return None


def _imports_lookup(cur, filename: str, sha: str):
    cols = set(_get_columns(cur, IMPORTS_TABLE))

    # se tiver hash no schema, usa ele (mantém o comportamento antigo)
    if "sha256" in cols:
        cur.execute(
            f"select id from public.{_safe_ident(IMPORTS_TABLE)} where sha256=%s limit 1",
            (sha,),
        )
        r = cur.fetchone()
        if r:
            return int(r[0]), "sha256"

    # no teu schema REAL tem file_name (e é o que vale)
    if "file_name" in cols:
        cur.execute(
            f"select id from public.{_safe_ident(IMPORTS_TABLE)} where file_name=%s limit 1",
            (filename,),
        )
        r = cur.fetchone()
        if r:
            return int(r[0]), "file_name"

    # compat antigo
    if "source_name" in cols:
        cur.execute(
            f"select id from public.{_safe_ident(IMPORTS_TABLE)} where source_name=%s limit 1",
            (filename,),
        )
        r = cur.fetchone()
        if r:
            return int(r[0]), "source_name"

    return None, None


def _imports_insert(cur, filename: str, sha: str, row_count_guess: int):
    cols = set(_get_columns(cur, IMPORTS_TABLE))
    fields, params, values = [], [], []

    # ✅ FIX PRINCIPAL: teu schema exige file_name NOT NULL
    if "file_name" in cols:
        fields.append("file_name"); params.append("%s"); values.append(filename)

    # file_date opcional (tira do nome se der)
    if "file_date" in cols:
        fields.append("file_date"); params.append("%s"); values.append(_parse_file_date(filename))

    # ✅ geralmente NOT NULL: uploaded_at
    if "uploaded_at" in cols:
        fields.append("uploaded_at"); params.append("%s"); values.append(datetime.now(timezone.utc))

    # compat antigo (se um dia existir)
    if "source_name" in cols:
        fields.append("source_name"); params.append("%s"); values.append(filename)
    if "sha256" in cols:
        fields.append("sha256"); params.append("%s"); values.append(sha)
    if "row_count" in cols:
        fields.append("row_count"); params.append("%s"); values.append(int(row_count_guess))

    # quem importou (se existir coluna)
    actor_id = st.session_state.get("user_id")
    actor_login = st.session_state.get("usuario")

    if "imported_by_user_id" in cols:
        fields.append("imported_by_user_id"); params.append("%s"); values.append(actor_id)
    if "imported_by_login" in cols:
        fields.append("imported_by_login"); params.append("%s"); values.append(actor_login)

    if not fields:
        raise RuntimeError(
            f"Tabela {IMPORTS_TABLE} não tem colunas esperadas. Colunas atuais: {sorted(cols)}"
        )

    cur.execute(
        f"""
        insert into public.{_safe_ident(IMPORTS_TABLE)} ({", ".join(fields)})
        values ({", ".join(params)})
        returning id
        """,
        tuple(values),
    )
    return int(cur.fetchone()[0])


def render(_df, _USUARIOS):
    st.markdown("# 📥 Importar CSV")
    st.caption(f"Destino fixo: public.{RAW_TABLE} | Controle: public.{IMPORTS_TABLE}")

    files = st.file_uploader("CSV(s)", type=["csv"], accept_multiple_files=True)
    if not files:
        st.info("Arraste um ou mais CSVs aqui.")
        return

    with st.expander("👀 Preview do primeiro arquivo", expanded=False):
        try:
            b0 = files[0].getvalue()
            txt0 = _decode_csv_bytes(b0)
            delim0 = _sniff_delimiter(txt0)
            preview = pd.read_csv(io.StringIO(txt0), sep=delim0, dtype=str, nrows=20)
            st.dataframe(preview, use_container_width=True)
        except Exception as e:
            st.warning(f"Preview falhou: {e}")

    if not st.button("🚀 Importar agora", use_container_width=True):
        return

    dsn = get_dsn()
    conn = psycopg.connect(dsn, connect_timeout=10)
    conn.autocommit = False

    try:
        # garante colunas de importador
        ensure_import_columns(conn)

        prog = st.progress(0)
        total = len(files)

        for i, f in enumerate(files, start=1):
            fname = getattr(f, "name", None) or f"upload_{i}.csv"
            data = f.getvalue()
            txt = _decode_csv_bytes(data)
            delim = _sniff_delimiter(txt)
            header = _parse_header(txt, delim)
            sha = _sha256(data)

            try:
                with conn.cursor() as cur:
                    if not _table_exists(cur, RAW_TABLE):
                        raise RuntimeError(f"Tabela public.{RAW_TABLE} não existe.")
                    if not _table_exists(cur, IMPORTS_TABLE):
                        raise RuntimeError(f"Tabela public.{IMPORTS_TABLE} não existe.")

                    raw_cols = set(_get_columns(cur, RAW_TABLE))
                    missing = [h for h in header if h not in raw_cols]
                    if missing:
                        raise RuntimeError(f"CSV tem colunas não existentes na RAW: {', '.join(missing)}")

                    if "import_id" not in raw_cols or "row_number" not in raw_cols:
                        raise RuntimeError("RAW precisa ter colunas import_id e row_number.")

                    dup_id, dup_by = _imports_lookup(cur, fname, sha)
                    if dup_id:
                        conn.rollback()
                        st.info(f"{fname}: já importado ({dup_by})")
                        audit_log("import_csv_skipped", "imports", str(dup_id), {"filename": fname, "by": dup_by})
                        prog.progress(int(i / total * 100))
                        continue

                    # row_count_guess
                    row_count_guess = max(0, len(txt.splitlines()) - 1)

                    import_id = _imports_insert(cur, fname, sha, row_count_guess)

                    tmp = f"tmp_csv_{import_id}"
                    cols_def = ", ".join([f"{_safe_ident(h)} text" for h in header])
                    cur.execute(f"create temp table {_safe_ident(tmp)} ({cols_def}) on commit drop")

                    copy_sql = (
                        f"COPY {_safe_ident(tmp)} ({', '.join(header)}) FROM STDIN "
                        f"WITH (FORMAT csv, HEADER true, DELIMITER '{delim}', QUOTE '\"')"
                    )
                    with cur.copy(copy_sql) as cp:
                        cp.write(txt.encode("utf-8"))

                    cur.execute(f"select count(*) from {_safe_ident(tmp)}")
                    real_rows = int(cur.fetchone()[0])

                    insert_cols = ["import_id", "row_number"] + header
                    cur.execute(
                        f"""
                        insert into public.{_safe_ident(RAW_TABLE)} ({", ".join(map(_safe_ident, insert_cols))})
                        select %s as import_id,
                               row_number() over () as row_number,
                               {", ".join(map(_safe_ident, header))}
                        from {_safe_ident(tmp)}
                        """,
                        (import_id,),
                    )

                conn.commit()
                st.success(f"✅ {fname}: {real_rows} linhas (import_id={import_id})")
                audit_log("import_csv_done", "imports", str(import_id), {"filename": fname, "rows": real_rows})

            except Exception as e:
                conn.rollback()
                st.error(f"❌ {fname}: {e}")
                audit_log("import_csv_failed", "imports", fname, {"error": str(e)})

            prog.progress(int(i / total * 100))

    finally:
        try:
            conn.close()
        except Exception:
            pass

    # refresh geral
    st.session_state.force_refresh = True
    st.session_state.just_refreshed = True
    st.cache_data.clear()
    st.success("Importação finalizada. Volta no Início — já tá no banco.")
