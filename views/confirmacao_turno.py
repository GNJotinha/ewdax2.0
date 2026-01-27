import io
import re
from datetime import datetime, time

import pandas as pd
import streamlit as st


# Aceita CPF no formato 000.000.000-00, 000.000.000.00, 00000000000 etc.
CPF_LINE_RE = re.compile(r"^\s*CPF\s*:\s*([0-9.\-\s]+)\s*$", re.IGNORECASE)


def _cpf_only_digits(cpf_raw: str) -> str:
    """Converte '413.121.343-99' ou '413.121.343.99' -> '41312134399'."""
    return re.sub(r"\D", "", str(cpf_raw or ""))


def _pick_col(cols, candidates):
    for c in candidates:
        if c in cols:
            return c
    return None


def _dedup_keep_order(items: list[dict]) -> list[dict]:
    """Remove duplicados preservando ordem.

    - Se tiver CPF, dedup por CPF (mais seguro)
    - Senão, dedup por nome
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
            cpf = _cpf_only_digits(cpf_raw)
            if last_candidate:
                items.append({"nome": last_candidate, "cpf": cpf, "cpf_raw": cpf_raw})
            last_candidate = None
            continue

        # candidato a nome (preserva como colado; só tira espaços nas pontas)
        # evita capturar a própria linha do CPF (caso venha torta)
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
            out.append({"nome": s, "cpf": "", "cpf_raw": ""})
        items = out

    return items


def _render_context_selectors(df: pd.DataFrame):
    """Seletores reaproveitando a base (praça/sub/turno) + data/hora."""
    cols = list(df.columns) if df is not None else []

    praca_opts = []
    if df is not None and "praca" in cols:
        praca_opts = sorted([x for x in df["praca"].dropna().unique().tolist()])

    sub_opts = []
    if df is not None and "sub_praca" in cols:
        sub_opts = sorted([x for x in df["sub_praca"].dropna().unique().tolist()])

    turno_col = _pick_col(cols, ["turno", "tipo_turno", "periodo"])
    turno_opts = []
    if df is not None and turno_col:
        turno_opts = sorted([x for x in df[turno_col].dropna().unique().tolist()])

    c1, c2, c3 = st.columns([1.2, 1.6, 1.2])

    # Praça (só pra filtrar subpraça, se tiver)
    if praca_opts:
        praca = c1.selectbox("Praça", praca_opts, index=0)
    else:
        praca = c1.text_input("Praça", value="")

    # Subpraça dependente da praça
    if df is not None and praca and ("praca" in cols) and ("sub_praca" in cols):
        base = df[df["praca"] == praca]
        subs = sorted([x for x in base["sub_praca"].dropna().unique().tolist()])
        if subs:
            sub = c2.selectbox("Subpraça", subs, index=0)
        else:
            sub = c2.text_input("Subpraça", value="")
    else:
        if sub_opts:
            sub = c2.selectbox("Subpraça", sub_opts, index=0)
        else:
            sub = c2.text_input("Subpraça", value="")

    data_slot = c3.date_input("DataDoSLOT", format="DD/MM/YYYY")

    # Registro: mesma data do slot + hora editável
    c4, c5 = st.columns([1.2, 1.0])
    c4.caption("DataHoraDeRegistro = data do slot + hora")
    hora_registro = c5.time_input("Hora do registro", value=time(9, 0))

    if turno_opts:
        turno = st.selectbox("Turno", turno_opts, index=0)
    else:
        turno = st.text_input("Turno", value="")

    return praca, sub, data_slot, hora_registro, turno


def _default_template() -> str:
    return (
        "Olá, {NOME}! Tudo bem?\n\n"
        "Estamos entrando em contato para confirmar se você terá disponibilidade para atuar no turno {TURNO} "
        "no dia {DATA}, conforme o preenchimento do formulário, na região do {SUBPRACA}.\n\n"
        "Pedimos que confirme com \"SIM\" ou \"NÃO\" sua disponibilidade.\n\n"
        "Desde já, agradecemos sua atenção. Boas entregas!"
    )


def _fill_template(tpl: str, nome: str, data_slot, turno: str, praca: str, sub: str) -> str:
    data_txt = pd.to_datetime(data_slot).strftime("%d/%m/%Y") if data_slot else ""
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


def _to_xlsx_bytes(df_registros: pd.DataFrame, df_msgs: pd.DataFrame | None = None) -> bytes:
    """Gera XLSX em memória.

    - Aba 1: 'registros' (layout que vocês pediram)
    - Aba opcional: 'mensagens'
    """
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df_registros.to_excel(writer, index=False, sheet_name="registros")

        if df_msgs is not None:
            df_msgs.to_excel(writer, index=False, sheet_name="mensagens")

        # Ajustes simples de largura / wrap
        try:
            from openpyxl.styles import Alignment

            wrap = Alignment(wrap_text=True, vertical="top")

            ws = writer.book["registros"]
            # A: DataHoraDeRegistro, B: DataDoSLOT, C: Regiao, D: Subpraca, E: Entregador,
            # F: CPF, G: E-mail, H: Turno, I: CELULAR
            widths = {
                "A": 20,
                "B": 14,
                "C": 14,
                "D": 34,
                "E": 38,
                "F": 14,
                "G": 26,
                "H": 34,
                "I": 18,
            }
            for col, w in widths.items():
                ws.column_dimensions[col].width = w

            for row in ws.iter_rows(min_row=2, min_col=1, max_col=9):
                for cell in row:
                    cell.alignment = wrap

            if df_msgs is not None:
                ws2 = writer.book["mensagens"]
                ws2.column_dimensions["A"].width = 34
                ws2.column_dimensions["B"].width = 18
                ws2.column_dimensions["C"].width = 90
                for row in ws2.iter_rows(min_row=2, min_col=1, max_col=3):
                    for cell in row:
                        cell.alignment = wrap

        except Exception:
            pass

    bio.seek(0)
    return bio.getvalue()


def render(df: pd.DataFrame, _USUARIOS: dict):
    st.header("📄 Confirmação de Turno — XLSX organizado")
    st.caption(
        "Você seleciona Subpraça/Data/Turno, cola a lista do sistema externo e baixa um XLSX pronto pra colar no Google Sheets."
    )

    praca, subpraca, data_slot, hora_registro, turno = _render_context_selectors(df)

    st.info("Regiao no arquivo sai fixo como **São Paulo** (como você pediu).")

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
        help="Se o sistema externo repetir o mesmo nome/CPF, isso evita linhas duplicadas.",
    )
    people = _dedup_keep_order(people_raw) if dedup else people_raw

    # métricas / validações
    total = len(people)
    cpfs = [(p.get("cpf") or "").strip() for p in people]
    invalid_cpfs = [c for c in cpfs if c and len(c) != 11]
    missing_cpfs = sum(1 for c in cpfs if not c)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pessoas detectadas", total)
    c2.metric("CPF vazio", missing_cpfs)
    c3.metric("CPF com tamanho ≠ 11", len(invalid_cpfs))
    c4.metric("Subpraça", subpraca or "(vazio)")

    if invalid_cpfs:
        st.warning(
            "Tem CPF com formato estranho (não deu 11 dígitos). Vou exportar do mesmo jeito (só números), "
            "mas vale conferir a lista."
        )

    if people:
        with st.expander("Prévia (Entregador / CPF)", expanded=False):
            prev = pd.DataFrame(
                {
                    "Entregador": [p.get("nome", "") for p in people],
                    "CPF (só números)": [p.get("cpf", "") for p in people],
                }
            )
            st.dataframe(prev, use_container_width=True, height=320)

    st.divider()
    st.subheader("2) Gerar XLSX")

    include_msgs = st.checkbox(
        "(Opcional) Gerar também aba 'mensagens' com texto pronto",
        value=False,
    )

    tpl = None
    if include_msgs:
        tpl = st.text_area(
            "Template (use {NOME}, {TURNO}, {DATA}, {PRACA}, {SUBPRACA})",
            value=_default_template(),
            height=200,
        )

    disabled = total == 0
    if st.button("Gerar planilha", use_container_width=True, disabled=disabled):
        dt_registro = datetime.combine(data_slot, hora_registro) if data_slot else None

        df_reg = pd.DataFrame(
            {
                "DataHoraDeRegistro": [dt_registro] * total,
                "DataDoSLOT": [data_slot] * total,
                "Regiao": ["São Paulo"] * total,
                "Subpraca": [subpraca] * total,
                "Entregador": [p.get("nome", "").strip() for p in people],
                "CPF": [p.get("cpf", "").strip() for p in people],
                "E-mail": [""] * total,
                "Turno": [turno] * total,
                "CELULAR": [""] * total,
            }
        )

        df_msgs = None
        if include_msgs and tpl is not None:
            df_msgs = pd.DataFrame({"Nome": df_reg["Entregador"].tolist()})
            df_msgs["Telefone"] = ""  # pra preencher depois
            df_msgs["Mensagem"] = [
                _fill_template(tpl, n, data_slot, turno, praca, subpraca)
                for n in df_msgs["Nome"].tolist()
            ]

        xlsx_bytes = _to_xlsx_bytes(df_reg, df_msgs)
        filename = f"confirmacao_turno_{pd.to_datetime(data_slot).strftime('%Y-%m-%d') if data_slot else 'data'}.xlsx"

        st.success("✅ Planilha gerada!")
        st.download_button(
            "⬇️ Baixar XLSX",
            data=xlsx_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        with st.expander("Prévia da aba 'registros'", expanded=False):
            st.dataframe(df_reg, use_container_width=True, height=360)

        if df_msgs is not None:
            with st.expander("Prévia da aba 'mensagens'", expanded=False):
                st.dataframe(df_msgs, use_container_width=True, height=360)
