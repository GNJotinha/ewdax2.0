import os
import io
import re
import csv
import hashlib

import streamlit as st
import pandas as pd
import psycopg


# 🔒 TRAVADO: não dá pra editar no app
RAW_TABLE = "base_2025_raw"
IMPORTS_TABLE = "imports"


def _get_dsn() -> str:
    dsn = None
    try:
        dsn = st.secrets.get("SUPABASE_DB_DSN")
    except Exception:
        dsn = None

    if not dsn:
        dsn = os.environ.get("SUPABASE_DB_DSN")

    if not dsn:
        raise RuntimeError(
            "SUPABASE_DB_DSN não encontrado. Coloca no Streamlit Secrets ou em variável de ambiente."
        )
    return dsn


_ident_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not _ident_re.match(name or ""):
        raise ValueError(f"Identificador inseguro/ inválido: {name!r}")
    return name


def _decode_csv_bytes(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")  # remove BOM se tiver
    except Exception:
        return data.decode("latin1")


def _sniff_delimiter(text: str) -> str:
    first_line = text.splitlines()[0] if text else ""
    return ";" if first_line.count(";") >= first_line.count(",") else ","


def _parse_header_and_count(text: str, delimiter: str) -> tuple[list[str], int]:
    f = io.StringIO(text)
    reader = csv.reader(f, delimiter=delimiter, quotechar='"')
    rows = list(reader)
    if not rows:
        raise ValueError("CSV vazio.")
    header = [c.strip() for c in rows[0]]
    for h in header:
        _safe_ident(h)
    return header, max(0, len(rows) - 1)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        select 1
        from information_schema.tables
        where table_schema='public' and table_name=%s
        limit 1
        """,
        (table,),
    )
    return cur.fetchone() is not None


def _get_columns(cur, table: str) -> list[tuple[str, str]]:
    cur.execute(
        """
        select column_name, data_type
        from information_schema.columns
        where table_schema='public' and table_name=%s
        order by ordinal_position
        """,
        (table,),
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


def _pick_first(cols: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None


def _ensure_imports_table(cur, table: str):
    if _table_exists(cur, table):
        return

    cur.execute(
        f"""
        create table if not exists public.{_safe_ident(table)} (
          id bigserial primary key,
          source_name text unique,
          sha256 text unique,
          row_count integer,
          imported_at timestamptz default now()
        );
        """
    )


def _imports_lookup(cur, table: str, filename: str, sha: str) -> dict | None:
    cols = {c for c, _ in _get_columns(cur, table)}
    id_col = _pick_first(cols, ["id", "import_id"])
    sha_col = _pick_first(cols, ["sha256", "hash"])
    name_col = _pick_first(cols, ["source_name", "file_name", "filename", "nome_arquivo"])

    if not id_col:
        return None

    # 1) tenta sha primeiro (mais seguro)
    if sha_col:
        cur.execute(
            f"select {_safe_ident(id_col)} from public.{_safe_ident(table)} where {_safe_ident(sha_col)}=%s limit 1",
            (sha,),
        )
        r = cur.fetchone()
        if r:
            return {"import_id": int(r[0]), "by": "sha256"}

    # 2) depois filename
    if name_col:
        cur.execute(
            f"select {_safe_ident(id_col)} from public.{_safe_ident(table)} where {_safe_ident(name_col)}=%s limit 1",
            (filename,),
        )
        r = cur.fetchone()
        if r:
            return {"import_id": int(r[0]), "by": "filename"}

    return None


def _imports_insert(cur, table: str, filename: str, sha: str, row_count: int) -> int:
    cols = {c for c, _ in _get_columns(cur, table)}

    id_col = _pick_first(cols, ["id", "import_id"])
    if not id_col:
        raise RuntimeError(f"Tabela public.{table} precisa ter coluna id (ou import_id).")

    name_col = _pick_first(cols, ["source_name", "file_name", "filename", "nome_arquivo"])
    sha_col = _pick_first(cols, ["sha256", "hash"])
    rc_col = _pick_first(cols, ["row_count", "linhas", "qtd_linhas"])

    fields, params, values = [], [], []

    if name_col:
        fields.append(_safe_ident(name_col))
        params.append("%s")
        values.append(filename)

    if sha_col:
        fields.append(_safe_ident(sha_col))
        params.append("%s")
        values.append(sha)

    if rc_col:
        fields.append(_safe_ident(rc_col))
        params.append("%s")
        values.append(int(row_count))

    if fields:
        cur.execute(
            f"""
            insert into public.{_safe_ident(table)} ({", ".join(fields)})
            values ({", ".join(params)})
            returning {_safe_ident(id_col)}
            """,
            tuple(values),
        )
        return int(cur.fetchone()[0])

    cur.execute(
        f"""
        insert into public.{_safe_ident(table)} default values
        returning {_safe_ident(id_col)}
        """
    )
    return int(cur.fetchone()[0])


def _import_one_csv(conn, filename: str, data: bytes) -> dict:
    text = _decode_csv_bytes(data)
    delimiter = _sniff_delimiter(text)
    header, row_count_guess = _parse_header_and_count(text, delimiter)
    sha = _sha256(data)

    with conn.cursor() as cur:
        _ensure_imports_table(cur, IMPORTS_TABLE)

        dup = _imports_lookup(cur, IMPORTS_TABLE, filename, sha)
        if dup:
            conn.rollback()
            return {
                "status": "skip",
                "filename": filename,
                "reason": f"já importado ({dup['by']})",
                "import_id": dup["import_id"],
                "rows": row_count_guess,
            }

        if not _table_exists(cur, RAW_TABLE):
            raise RuntimeError(f"Tabela public.{RAW_TABLE} não existe.")

        raw_cols = [c for c, _ in _get_columns(cur, RAW_TABLE)]
        raw_set = set(raw_cols)

        missing = [h for h in header if h not in raw_set]
        if missing:
            raise RuntimeError(
                f"CSV tem colunas que não existem em public.{RAW_TABLE}: {', '.join(missing)}"
            )

        if "import_id" not in raw_set or "row_number" not in raw_set:
            raise RuntimeError(f"Tabela public.{RAW_TABLE} precisa ter colunas import_id e row_number.")

        import_id = _imports_insert(cur, IMPORTS_TABLE, filename, sha, row_count_guess)

        tmp = f"tmp_csv_{import_id}"
        cols_def = ", ".join([f"{_safe_ident(h)} text" for h in header])
        cur.execute(f"create temp table {_safe_ident(tmp)} ({cols_def}) on commit drop")

        copy_sql = (
            f"COPY {_safe_ident(tmp)} ({', '.join(header)}) FROM STDIN "
            f"WITH (FORMAT csv, HEADER true, DELIMITER '{delimiter}', QUOTE '\"')"
        )
        with cur.copy(copy_sql) as cp:
            cp.write(text.encode("utf-8"))

        cur.execute(f"select count(*) from {_safe_ident(tmp)}")
        real_rows = int(cur.fetchone()[0])

        insert_cols = ["import_id", "row_number"] + header
        insert_cols_sql = ", ".join([_safe_ident(c) for c in insert_cols])
        select_cols_sql = ", ".join([_safe_ident(c) for c in header])

        cur.execute(
            f"""
            insert into public.{_safe_ident(RAW_TABLE)} ({insert_cols_sql})
            select %s as import_id,
                   row_number() over () as row_number,
                   {select_cols_sql}
            from {_safe_ident(tmp)}
            """,
            (import_id,),
        )

        cols = {c for c, _ in _get_columns(cur, IMPORTS_TABLE)}
        rc_col = _pick_first(cols, ["row_count", "linhas", "qtd_linhas"])
        id_col = _pick_first(cols, ["id", "import_id"])
        if rc_col and id_col:
            cur.execute(
                f"update public.{_safe_ident(IMPORTS_TABLE)} set {_safe_ident(rc_col)}=%s where {_safe_ident(id_col)}=%s",
                (real_rows, import_id),
            )

    conn.commit()

    return {
        "status": "ok",
        "filename": filename,
        "rows": real_rows,
        "sha256": sha,
        "import_id": import_id,
    }


def render(df, USUARIOS: dict):
    st.markdown("# 📥 Importar CSV")

    usuario = st.session_state.get("usuario")
    user_entry = (USUARIOS or {}).get(usuario, {}) or {}
    nivel = user_entry.get("nivel", "")

    allowed = set()
    try:
        allowed = set(st.secrets.get("IMPORTADORES", []))
    except Exception:
        allowed = set()

    if allowed:
        pode = usuario in allowed
    else:
        pode = nivel in ("admin", "dev", "operacional")

    if not pode:
        st.error("Você não tem permissão pra importar CSV aqui.")
        st.info("Peça pro admin colocar teu usuário em IMPORTADORES (secrets).")
        return

    st.caption("Arrasta o CSV do dia aqui. O app sobe pro Supabase e evita duplicado automaticamente.")
    st.caption(f"Destino fixo: public.{RAW_TABLE}  |  Controle: public.{IMPORTS_TABLE}")

    files = st.file_uploader(
        "CSV(s)",
        type=["csv"],
        accept_multiple_files=True,
        help="Nome recomendado: YYYY-MM-DD.csv",
    )

    if not files:
        st.info("Envie um ou mais CSVs para importar.")
        return

    with st.expander("👀 Preview do primeiro arquivo", expanded=False):
        try:
            b0 = files[0].getvalue()
            txt0 = _decode_csv_bytes(b0)
            delim0 = _sniff_delimiter(txt0)
            preview = pd.read_csv(io.StringIO(txt0), sep=delim0, dtype=str, nrows=20)
            st.dataframe(preview, use_container_width=True)
        except Exception as e:
            st.warning(f"Não consegui gerar preview: {e}")

    if st.button("🚀 Importar agora", use_container_width=True):
        try:
            dsn = _get_dsn()
        except Exception as e:
            st.error(str(e))
            return

        conn = psycopg.connect(dsn)
        conn.autocommit = False

        prog = st.progress(0)
        results = []

        try:
            total = len(files)
            for i, f in enumerate(files, start=1):
                fname = f.name
                data = f.getvalue()

                st.write(f"📄 Importando: **{fname}**")
                try:
                    res = _import_one_csv(conn, fname, data)
                    results.append(res)

                    if res["status"] == "ok":
                        st.success(f"✅ {fname}: {res['rows']} linhas (import_id={res['import_id']})")
                    else:
                        st.info(f"⏭️ {fname}: {res['reason']}")

                except Exception as e:
                    conn.rollback()
                    st.error(f"❌ {fname}: {e}")

                prog.progress(int(i / total * 100))

        finally:
            try:
                conn.close()
            except Exception:
                pass

        if any(r.get("status") == "ok" for r in results):
            st.session_state.force_refresh = True
            st.session_state.just_refreshed = True
            st.cache_data.clear()
            st.success("Importação concluída. Volta no Início — os dados já vão estar atualizados.")
