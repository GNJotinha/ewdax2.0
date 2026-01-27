import io
import re
import unicodedata
from datetime import datetime, time

import pandas as pd
import streamlit as st

# ------------------------------------------------------------
# CONFIG / REGRAS
# ------------------------------------------------------------
REGIAO_FIXA = "São Paulo"

# Aceita CPF no formato:
# - 000.000.000-00
# - 000.000.000.00
# - 00000000000
CPF_LINE_RE = re.compile(r"^\s*CPF\s*:\s*([0-9.\-\s]+)\s*$", re.IGNORECASE)

# Session keys
_RAW_KEY = "ct_raw_text"
_BATCHES_KEY = "ct_batches"
_CLEAR_RAW_FLAG = "ct_clear_raw"
_FLASH_KEY = "ct_flash"

# Colunas finais (na ordem que você pediu)
COLS = [
    "DataHoraDeRegistro",
    "DataDoSLOT",
    "Regiao",
    "Subpraca",
    "Entregador",
    "CPF",
    "E-mail",
    "Turno",
    "CELULAR",
]


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def _norm_ascii_upper(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.strip().upper().split())


def _cpf_out(cpf_raw: str) -> tuple[str, str]:
    """Retorna (cpf_digits, cpf_export).

    - cpf_digits: só números (ex.: 41312134399)
    - cpf_export: com as 2 vírgulas no final (ex.: 41312134399,,)
    """
    digits = re.sub(r"\D", "", str(cpf_raw or ""))
    return digits, (f"{digits},," if digits else "")


def _pick_col(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    return None


def _dedup_keep_order(items: list[dict]) -> list[dict]:
    """Remove duplicados preservando ordem.

    - Se tiver cpf_digits, dedup por cpf_digits
    - Senão, dedup por nome
    """
    seen = set()
    out = []
    for it in items:
        cpf = (it.get("cpf_digits") or "").strip()
        nome = (it.get("nome") or "").strip()
        key = ("cpf", cpf) if cpf else ("nome", nome)
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _parse_people(raw: str) -> list[dict]:
    """Extrai pessoas do bloco no formato:

    <NOME>\nCPF: xxx.xxx.xxx-xx\nTudo certo\n\n...

    Regra robusta: sempre que achar uma linha CPF, pega o último 'candidato a nome' acima dela.
    """
    if not raw or not str(raw).strip():
        return []

    txt = str(raw).replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in txt.split("\n")]

    items: list[dict] = []
    last_candidate = None

    for ln in lines:
        s = ln.strip()
        if not s:
            continue

        if s.lower() == "tudo certo":
            continue

        m = CPF_LINE_RE.match(s)
        if m:
            cpf_raw = m.group(1)
            cpf_digits, cpf_export = _cpf_out(cpf_raw)
            if last_candidate:
                items.append(
                    {
                        "nome": last_candidate,
                        "cpf_digits": cpf_digits,
                        "cpf_export": cpf_export,
                        "cpf_raw": cpf_raw,
                    }
                )
            last_candidate = None
            continue

        # candidato a nome (preserva como colado; só tira espaços nas pontas)
        if "cpf" not in s.lower():
            last_candidate = s

    # fallback: se não teve CPF nenhum, assume que são nomes em linhas
    if not items:
        out = []
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if s.lower() == "tudo certo":
                continue
            if "cpf" in s.lower():
                continue
            out.append({"nome": s, "cpf_digits": "", "cpf_export": "", "cpf_raw": ""})
        items = out

    return items


def _sub_options_with_livre(df_praca: pd.DataFrame, praca_selecionada: str) -> list[str]:
    """Subpraças com 'LIVRE' quando a praça selecionada for São Paulo."""
    subs_col = df_praca.get("sub_praca", pd.Series(dtype=object))
    subs_validas = sorted([x for x in subs_col.dropna().unique().tolist() if str(x).strip() != ""])

    pr = _norm_ascii_upper(praca_selecionada)
    if pr == "SAO PAULO":
        return ["LIVRE"] + subs_validas

    return subs_validas


def _render_context_selectors(df: pd.DataFrame):
    """Seletores reaproveitando a base (praça/sub/turno) + data/hora."""
    cols = list(df.columns) if df is not None else []

    praca_opts = []
    if df is not None and "praca" in cols:
        praca_opts = sorted([x for x in df["praca"].dropna().unique().tolist()])

    turno_col = _pick_col(cols, ["turno", "tipo_turno", "periodo"])
    turno_opts = []
    if df is not None and turno_col:
        turno_opts = sorted([x for x in df[turno_col].dropna().unique().tolist()])

    c1, c2, c3 = st.columns([1.2, 1.6, 1.2])

    # Praça (só pra filtrar subpraça e habilitar LIVRE)
    if praca_opts:
        praca = c1.selectbox("Praça", praca_opts, index=0)
    else:
        praca = c1.text_input("Praça", value="")

    # Subpraça (com LIVRE pra São Paulo)
    if df is not None and praca and ("praca" in cols) and ("sub_praca" in cols):
        df_praca = df[df["praca"] == praca]
        subs = _sub_options_with_livre(df_praca, praca)
        if subs:
            sub = c2.selectbox("Subpraça", subs, index=0)
        else:
            sub = c2.text_input("Subpraça", value="")
    else:
        sub = c2.text_input("Subpraça", value="")

    data_slot = c3.date_input("DataDoSLOT", format="DD/MM/YYYY")

    c4, c5 = st.columns([1.2, 1.0])
    c4.caption("DataHoraDeRegistro = DataDoSLOT + Hora do registro")
    hora_registro = c5.time_input("Hora do registro", value=time(9, 0))

    if turno_opts:
        turno = st.selectbox("Turno", turno_opts, index=0)
    else:
        turno = st.text_input("Turno", value="")

    return praca, sub, data_slot, hora_registro, turno


def _build_lote_df(people: list[dict], data_slot, hora_registro, subpraca: str, turno: str) -> pd.DataFrame:
    total = len(people)
    dt_registro = datetime.combine(data_slot, hora_registro) if data_slot else None

    df_lote = pd.DataFrame(
        {
            "DataHoraDeRegistro": [dt_registro] * total,
            "DataDoSLOT": [data_slot] * total,
            "Regiao": [REGIAO_FIXA] * total,
            "Subpraca": [subpraca] * total,
            "Entregador": [p.get("nome", "").strip() for p in people],
            "CPF": [p.get("cpf_export", "").strip() for p in people],
            "E-mail": [""] * total,
            "Turno": [turno] * total,
            "CELULAR": [""] * total,
        }
    )
    return df_lote[COLS]


def _to_xlsx_bytes(df_registros: pd.DataFrame) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df_registros.to_excel(writer, index=False, sheet_name="registros")

        # Ajustes simples de largura / wrap
        try:
            from openpyxl.styles import Alignment

            wrap = Alignment(wrap_text=True, vertical="top")
            ws = writer.book["registros"]

            widths = {
                "A": 20,  # DataHoraDeRegistro
                "B": 14,  # DataDoSLOT
                "C": 14,  # Regiao
                "D": 34,  # Subpraca
                "E": 38,  # Entregador
                "F": 16,  # CPF (com ",,")
                "G": 24,  # E-mail
                "H": 34,  # Turno
                "I": 18,  # CELULAR
            }
            for col, w in widths.items():
                ws.column_dimensions[col].width = w

            for row in ws.iter_rows(min_row=2, min_col=1, max_col=9):
                for cell in row:
                    cell.alignment = wrap
        except Exception:
            pass

    bio.seek(0)
    return bio.getvalue()


# ------------------------------------------------------------
# STREAMLIT PAGE
# ------------------------------------------------------------
def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📄 Confirmação de Turno — XLSX organizado")
    st.caption(
        "Filtra praça/sub/data/turno, cola a lista do sistema externo e acumula vários lotes num único XLSX."
    )

    # init memória
    if _RAW_KEY not in st.session_state:
        st.session_state[_RAW_KEY] = ""
    if _BATCHES_KEY not in st.session_state:
        st.session_state[_BATCHES_KEY] = []
    if _CLEAR_RAW_FLAG not in st.session_state:
        st.session_state[_CLEAR_RAW_FLAG] = False

    # flash (pra não sumir no rerun)
    flash = st.session_state.pop(_FLASH_KEY, None)
    if flash:
        level, msg = flash
        {"success": st.success, "warning": st.warning, "info": st.info}.get(level, st.info)(msg)

    # Se pediram pra limpar o text_area, faz ANTES do widget existir
    if st.session_state.get(_CLEAR_RAW_FLAG):
        st.session_state[_RAW_KEY] = ""
        st.session_state[_CLEAR_RAW_FLAG] = False

    praca, subpraca, data_slot, hora_registro, turno = _render_context_selectors(df)

    st.info(
        "No arquivo: **Regiao = São Paulo (fixo)**. "
        "Subpraça mostra **LIVRE** quando a praça selecionada for **São Paulo**."
    )

    st.divider()
    st.subheader("1) Cole a lista do sistema externo")

    raw = st.text_area(
        "Texto bruto (Nome / CPF / Tudo certo)",
        key=_RAW_KEY,
        height=240,
        placeholder="Cole aqui…",
    )

    people_raw = _parse_people(raw)

    dedup = st.checkbox(
        "Remover duplicados (por CPF quando existir)",
        value=True,
        help="Evita linhas duplicadas no lote se o sistema externo repetir o mesmo CPF.",
    )
    people = _dedup_keep_order(people_raw) if dedup else people_raw

    total = len(people)
    cpfs_digits = [(p.get("cpf_digits") or "").strip() for p in people]
    invalid_cpfs = [c for c in cpfs_digits if c and len(c) != 11]
    missing_cpfs = sum(1 for c in cpfs_digits if not c)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pessoas detectadas", total)
    c2.metric("CPF vazio", missing_cpfs)
    c3.metric("CPF tamanho ≠ 11", len(invalid_cpfs))
    c4.metric("Lotes acumulados", len(st.session_state[_BATCHES_KEY]))

    if invalid_cpfs:
        st.warning(
            "Tem CPF que não deu 11 dígitos. Vou exportar do mesmo jeito (só números + ',,'), "
            "mas vale conferir."
        )

    if people:
        with st.expander("Prévia (Entregador / CPF export)", expanded=False):
            prev = pd.DataFrame(
                {
                    "Entregador": [p.get("nome", "") for p in people],
                    "CPF (export)": [p.get("cpf_export", "") for p in people],
                }
            )
            st.dataframe(prev, use_container_width=True, height=320)

    st.divider()
    st.subheader("2) Memória: ir juntando vários lotes")

    df_lote = _build_lote_df(people, data_slot, hora_registro, subpraca, turno) if total else pd.DataFrame(columns=COLS)

    b1, b2, b3 = st.columns(3)

    add_disabled = (total == 0) or (not subpraca) or (not turno) or (data_slot is None)

    if b1.button("➕ Adicionar lote ao acumulado", use_container_width=True, disabled=add_disabled):
        st.session_state[_BATCHES_KEY].append(df_lote)
        st.session_state[_CLEAR_RAW_FLAG] = True
        st.session_state[_FLASH_KEY] = ("success", "Lote adicionado! Troca a subpraça e cola o próximo bloco.")
        st.rerun()

    if b2.button("↩️ Desfazer último lote", use_container_width=True, disabled=(len(st.session_state[_BATCHES_KEY]) == 0)):
        st.session_state[_BATCHES_KEY].pop()
        st.session_state[_FLASH_KEY] = ("warning", "Último lote removido.")
        st.rerun()

    if b3.button("🧹 Limpar tudo", use_container_width=True, disabled=(len(st.session_state[_BATCHES_KEY]) == 0)):
        st.session_state[_BATCHES_KEY] = []
        st.session_state[_FLASH_KEY] = ("warning", "Acumulado zerado.")
        st.rerun()

    batches = st.session_state[_BATCHES_KEY]
    df_all = pd.concat(batches, ignore_index=True) if batches else pd.DataFrame(columns=COLS)

    dedup_all = st.checkbox(
        "Remover duplicados no acumulado (CPF + DataDoSLOT + Turno + Subpraca)",
        value=True,
    )
    if dedup_all and not df_all.empty:
        df_all = df_all.drop_duplicates(subset=["CPF", "DataDoSLOT", "Turno", "Subpraca"], keep="first")

    st.divider()
    st.subheader("3) Baixar XLSX")

    st.metric("Linhas no acumulado", int(len(df_all)))

    if df_all.empty:
        st.info("Ainda não tem nada no acumulado. Adiciona um lote ali em cima.")
        return

    xlsx_bytes = _to_xlsx_bytes(df_all)

    # nome do arquivo (pega a maior DataDoSLOT no acumulado)
    try:
        max_dt = pd.to_datetime(df_all["DataDoSLOT"]).max()
        suffix = max_dt.strftime("%Y-%m-%d") if pd.notna(max_dt) else "data"
    except Exception:
        suffix = "data"

    filename = f"confirmacao_turno_{suffix}.xlsx"

    st.download_button(
        "⬇️ Baixar XLSX (acumulado)",
        data=xlsx_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    with st.expander("Prévia do acumulado", expanded=False):
        st.dataframe(df_all, use_container_width=True, height=420)
