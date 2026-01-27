import io
import re

import pandas as pd
import streamlit as st


CPF_LINE_RE = re.compile(
    r"^\s*CPF\s*:\s*(\d{3}\.\d{3}\.\d{3}-\d{2})\s*$",
    re.IGNORECASE,
)


def _pick_col(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    return None


def _dedup_keep_order(items: list[dict]) -> list[dict]:
    """Remove duplicados preservando ordem.

    Se tiver CPF, dedup por CPF (mais seguro). Se não tiver, dedup por nome.
    """
    seen = set()
    out = []
    for it in items:
        cpf = (it.get("cpf") or "").strip()
        nome = (it.get("nome") or "").strip()
        key = ("cpf", cpf) if cpf else ("nome", nome)
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _parse_people(raw: str) -> list[dict]:
    """Extrai pessoas do bloco:

    <NOME>\nCPF: xxx.xxx.xxx-xx\nTudo certo\n\n...

    Regra principal: sempre que achar uma linha CPF, pega o último candidato a nome acima.
    """
    if not raw or not str(raw).strip():
        return []

    lines = [ln.rstrip() for ln in str(raw).replace("\r\n", "\n").replace("\r", "\n").split("\n")]

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
            cpf = m.group(1)
            if last_candidate:
                items.append({"nome": last_candidate, "cpf": cpf})
            last_candidate = None
            continue

        # candidato a nome (preserva exatamente como colado; só tira espaços nas pontas)
        if "cpf" not in s.lower():
            last_candidate = s

    # fallback: se não teve CPF nenhum, assume que são nomes em linhas
    if not items:
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if s.lower() == "tudo certo":
                continue
            if "cpf" in s.lower():
                continue
            items.append({"nome": s, "cpf": ""})

    return items


def _render_context_selectors(df: pd.DataFrame):
    cols = list(df.columns) if df is not None else []

    praca_opts = []
    if df is not None and "praca" in cols:
        praca_opts = sorted([x for x in df["praca"].dropna().unique().tolist()])

    turno_col = _pick_col(cols, ["turno", "tipo_turno", "periodo"])
    turno_opts = []
    if df is not None and turno_col:
        turno_opts = sorted([x for x in df[turno_col].dropna().unique().tolist()])

    c1, c2, c3 = st.columns([1.2, 1.6, 1.2])

    # Praça
    if praca_opts:
        praca = c1.selectbox("Praça", praca_opts, index=0)
    else:
        praca = c1.text_input("Praça", value="")

    # Subpraça dependente da praça, se der
    if df is not None and praca and ("praca" in cols) and ("sub_praca" in cols):
        base = df[df["praca"] == praca]
        subs = sorted([x for x in base["sub_praca"].dropna().unique().tolist()])
        if subs:
            sub = c2.selectbox("Subpraça", subs, index=0)
        else:
            sub = c2.text_input("Subpraça", value="")
    else:
        sub = c2.text_input("Subpraça", value="")

    data_turno = c3.date_input("Data do turno", format="DD/MM/YYYY")

    # Turno
    if turno_opts:
        turno = st.selectbox("Turno", turno_opts, index=0)
    else:
        turno = st.text_input("Turno", value="")

    return praca, sub, data_turno, turno


def _default_template() -> str:
    return (
        "Olá, {NOME}! Tudo bem?\n\n"
        "Estamos entrando em contato para confirmar se você terá disponibilidade para atuar no turno {TURNO} "
        "no dia {DATA}, conforme o preenchimento do formulário, na região do {SUBPRACA}.\n\n"
        "Pedimos que confirme com \"SIM\" ou \"NÃO\" sua disponibilidade.\n\n"
        "Desde já, agradecemos sua atenção. Boas entregas!"
    )


def _fill_template(tpl: str, nome: str, data_turno, turno: str, praca: str, sub: str) -> str:
    data_txt = pd.to_datetime(data_turno).strftime("%d/%m/%Y") if data_turno else ""
    sub_txt = (sub or "").strip() or (praca or "").strip()

    out = str(tpl)
    repl = {
        "{NOME}": nome,
        "{DATA}": data_txt,
        "{TURNO}": str(turno or "").strip(),
        "{PRACA}": str(praca or "").strip(),
        "{SUBPRACA}": sub_txt,
    }
    for k, v in repl.items():
        out = re.sub(re.escape(k), v, out, flags=re.IGNORECASE)
    return out


def _to_xlsx_bytes(df_out: pd.DataFrame) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="mensagens")
        ws = writer.book["mensagens"]

        # Larguras: Nome / Telefone / Mensagem
        try:
            ws.column_dimensions["A"].width = 34
            ws.column_dimensions["B"].width = 18
            ws.column_dimensions["C"].width = 90
        except Exception:
            pass

        # Wrap na mensagem
        try:
            from openpyxl.styles import Alignment

            wrap = Alignment(wrap_text=True, vertical="top")
            for row in ws.iter_rows(min_row=2, min_col=1, max_col=3):
                for cell in row:
                    cell.alignment = wrap
        except Exception:
            pass

    bio.seek(0)
    return bio.getvalue()


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📨 Confirmação de Turno — Planilha de Mensagens")
    st.caption("Selecione praça/sub/turno/data, cole a lista do sistema externo e baixe um XLSX pronto pra colar no Google Sheets.")

    praca, subpraca, data_turno, turno = _render_context_selectors(df)

    st.divider()
    st.subheader("1) Cole a lista do sistema externo")

    raw = st.text_area(
        "Texto bruto (Nome / CPF / Tudo certo)",
        height=240,
        placeholder="Cole aqui…",
    )

    people_raw = _parse_people(raw)

    dedup = st.checkbox(
        "Remover duplicados (por CPF quando existir)",
        value=True,
        help="Se o sistema externo repetir o mesmo nome/CPF, isso evita mandar duas mensagens.",
    )
    people = _dedup_keep_order(people_raw) if dedup else people_raw
    names = [p.get("nome", "").strip() for p in people if p.get("nome")]

    c1, c2, c3 = st.columns(3)
    c1.metric("Pessoas detectadas", len(people))
    c2.metric("Subpraça", subpraca or "(vazio)")
    c3.metric("Turno", turno or "(vazio)")

    if people:
        with st.expander("Prévia (Nome/CPF)", expanded=False):
            prev = pd.DataFrame(people)
            show_cols = [c for c in ("nome", "cpf") if c in prev.columns]
            st.dataframe(prev[show_cols].rename(columns={"nome": "Nome", "cpf": "CPF"}), use_container_width=True, height=260)

    st.divider()
    st.subheader("2) Template da mensagem")
    tpl = st.text_area(
        "Template (use {NOME}, {TURNO}, {DATA}, {PRACA}, {SUBPRACA})",
        value=_default_template(),
        height=220,
    )

    st.divider()
    st.subheader("3) Gerar XLSX")
    if st.button("Gerar planilha", use_container_width=True, disabled=not bool(names)):
        out = pd.DataFrame({"Nome": names})
        out["Telefone"] = ""  # coluna vazia pro time preencher
        out["Mensagem"] = [_fill_template(tpl, n, data_turno, turno, praca, subpraca) for n in names]

        xlsx_bytes = _to_xlsx_bytes(out)
        filename = f"mensagens_confirmacao_{pd.to_datetime(data_turno).strftime('%Y-%m-%d')}.xlsx"

        st.success("✅ Planilha gerada!")
        st.download_button(
            "⬇️ Baixar XLSX",
            data=xlsx_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        with st.expander("Prévia da planilha", expanded=False):
            st.dataframe(out, use_container_width=True, height=340)
