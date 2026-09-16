"""G0-D applicability parser: disposiciones transitorias/finales of a
diario document → deterministic applicability clauses.

Pure extraction over ``boe_diario.DiarioDoc`` — no database, no network,
no LLM. Ported verbatim-semantics from the frozen G0-D discovery probe
(``scripts/g0d/probe_applicability.py``); the only deliberate deltas are:

* ``clause_key`` carries no instrument prefix (identity is composed at
  persistence time);
* a root clause gets ``parent_key=None / relation_to_parent=None`` —
  ``BASE`` was a discovery label, not a stored edge;
* ``PUBLICATION_PLUS_1`` resolves against the document's own
  ``fecha_publicacion`` metadata here.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

from .operations import _alpha_value, _marker_parts
from .profile import active_profile
from .sources.boe_diario import DiarioDoc

PARSER_NAME = "applicability"
PARSER_VERSION = "g0d-v3"

# disposición headings are discovered, not enumerated: the code is
# type-prefix + ordinal word so any N-th disposición parses ('dt1',
# 'df2', 'da3', 'ddu')
_DISP_HEAD_RE = re.compile(
    r"^\s*disposici[oó]n\s+(transitoria|final|adicional|derogatoria)"
    r"(?:\s+(\w+))?", re.IGNORECASE)
_DISP_PREFIX = {"transitoria": "dt", "final": "df", "adicional": "da",
                "derogatoria": "dd"}
_DISP_ORDINAL = {
    "única": "u", "unica": "u", "primera": "1", "primero": "1",
    "segunda": "2", "segundo": "2", "tercera": "3", "tercero": "3",
    "cuarta": "4", "cuarto": "4", "quinta": "5", "quinto": "5",
    "sexta": "6", "sexto": "6", "séptima": "7", "septima": "7",
    "séptimo": "7", "octava": "8", "octavo": "8", "novena": "9",
    "noveno": "9", "décima": "10", "decima": "10", "décimo": "10",
    "undécima": "11", "undecima": "11", "duodécima": "12",
    "duodecima": "12",
}

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
DATE_RE = re.compile(r"(\d{1,2}) de (" + "|".join(MONTHS) + r") de (\d{4})")

TEMPORAL_MARKERS = [
    ("INSTRUMENT_EFFECTIVE_FROM",
     re.compile(r"entrará en vigor el día siguiente al de su publicación")),
    ("APPLY_FROM", re.compile(r"se aplicarán desde el")),
    ("FIRST_REFERENCE_DATE",
     re.compile(r"se aplicarán por primera vez para los datos")),
    ("FIRST_REFERENCE_DATE", re.compile(r"primera fecha de referencia")),
    ("LAST_REFERENCE_DATE", re.compile(r"últimos datos")),
    ("RETROACTIVE_APPLICATION",
     re.compile(r"se aplicarán retroactivamente")),
    ("INITIAL_APPLICATION_DATE",
     re.compile(r"fecha de aplicación inicial[^.]*será el")),
    ("PROSPECTIVE_APPLICATION",
     re.compile(r"aplicar (?:las modificaciones )?prospectivamente")),
    ("SCOPE_PERIOD", re.compile(r"aplicará esta disposición transitoria")),
]

MODALITY_MARKERS = [
    ("ABSENCE_OF_OBLIGATION", re.compile(r"no estará obligada? a")),
    ("NON_APPLICATION", re.compile(r"no aplicará")),
    ("OPTION", re.compile(r"podrá(?:n)? (?:optar|interrumpir)")),
    ("OBLIGATION",
     re.compile(r"(?:deberá|deberán|deben|debe|reconocerá|informará)\b")),
    ("DECLARED_RULE",
     re.compile(r"se aplicarán|entrará en vigor|aplicará|serán")),
]

CONDITIONAL_OPENER = re.compile(r"^(?:Si[ ,]|Cuando )\b")
SIGNATURE_RE = re.compile(r"^Madrid, \d+ de \w+ de \d{4}")

FREQ_MAP = {
    "mensual": "MONTHLY", "mensuales": "MONTHLY",
    "trimestral": "QUARTERLY", "trimestrales": "QUARTERLY",
    "semestral": "SEMIANNUAL", "semestrales": "SEMIANNUAL",
    "anual": "ANNUAL", "anuales": "ANNUAL",
}

_FREQ_WORDS = r"(?:mensual|trimestral|semestral|anual)(?:es)?"
FREQ_DATE_PAIR = re.compile(
    r"de (\d{1,2} de \w+ de \d{4}) para los (?:estados )?de "
    r"frecuencias? (" + _FREQ_WORDS + r"(?: y " + _FREQ_WORDS + r")?)")

_NUMLIST = r"(\d+(?: a \d+)?(?:(?:\s*,\s*|\s+y\s+)\d+(?: a \d+)?)*)"
APARTADO_DE_NORMA = re.compile(
    r"apartados? " + _NUMLIST + r" de la norma (\d+)")
APARTADOS_NORMA_REF = re.compile(
    r"apartados (\d+) a (\d+) de la norma (\d+)")
NORMAS_RE = re.compile(r"las normas " + _NUMLIST)
ANEJOS_RE = re.compile(r"los anejos " + _NUMLIST)
PUNTO_DE_ANEJO = re.compile(
    r"punto (\d+)((?:\.\d+)*)[^.]*?"
    r"(?:y el apartado ([IVX]+)[^.]*)? del anejo (\d+)")
APARTADO_IV_ANEJO = re.compile(r"apartado ([IVX]+)[^,;.]*del anejo (\d+)")
# 'estados FI 1, FI 2 y FI 3' scope lists and the code token — state-
# code vocabulary owned by the active profile's annex_state facet
# (PORT-2 C-016); the scope-resolution policy consuming them is core.

INTRO_RE = re.compile(
    r"introducid[ao]s? por (.*?),? respectivamente,? de la norma (\d+)")
INTRO_RE2 = re.compile(
    r"introducid[ao]s? por (.*?de la letra [a-z]\)),? de la norma (\d+)")
LETRA_SINGLE = re.compile(r"la letra ([a-z])\)")
LETRAS_MULTI = re.compile(r"las letras ((?:[a-z]\)(?:, | y )?)+)")
NUMERAL_OF_LETRA = re.compile(
    r"numeral ([ivx]+)\)(?:, respectivamente,)? de la letra ([a-z])\)")
NUMERALES_OF_LETRA = re.compile(
    r"numerales ((?:[ivx]+\)(?:, | y )?)+)"
    r"(?:, respectivamente,)? de la letra ([a-z])\)")
ROMAN_TOKEN = re.compile(r"([ivx]+)\)")

EXCEPT_APARTADOS = re.compile(
    r"con las excepciones establecidas en los apartados (\d+) a (\d+)"
    r" de esta disposición")
ESPECIFICIDADES = re.compile(r"con las siguientes especificidades")
SIN_PERJUICIO = re.compile(
    r"[Ss]in perjuicio de lo establecido en la (disposición transitoria"
    r" \w+)")

RULE_REF_CTX = re.compile(
    r"(?:de acuerdo con|establecido en|requerida en|dispone en)"
    r"[^.]{0,90}$")


def _nums(s: str) -> list[str]:
    """'3, 6 y 7' → [3,6,7]; '17 a 20' → [17..20]."""
    out = []
    for part in re.split(r",| y ", s.strip()):
        m = re.match(r"^(\d+) a (\d+)$", part.strip())
        if m:
            out.extend(str(i) for i in range(int(m.group(1)),
                                             int(m.group(2)) + 1))
        else:
            out.extend(re.findall(r"\d+", part))
    return out


def _iso(m) -> str:
    return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"


def _rule_ref(text: str, start: int) -> bool:
    """True when the citation sits inside an applied-rule reference rather
    than naming a modified subject."""
    return bool(RULE_REF_CTX.search(text[:start]))


def extract_subjects(text: str) -> list[dict]:
    out = []
    for m in APARTADO_DE_NORMA.finditer(text):
        for ap in _nums(m.group(1)):
            out.append({"raw": m.group(0),
                        "locator_key": f"norma:{m.group(2)}.apartado:{ap}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in APARTADOS_NORMA_REF.finditer(text):
        for ap in range(int(m.group(1)), int(m.group(2)) + 1):
            out.append({"raw": m.group(0),
                        "locator_key":
                            f"norma:{m.group(3)}.apartado:{ap}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in NORMAS_RE.finditer(text):
        for n in _nums(m.group(1)):
            out.append({"raw": m.group(0), "locator_key": f"norma:{n}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in ANEJOS_RE.finditer(text):
        for n in _nums(m.group(1)):
            out.append({"raw": m.group(0), "locator_key": f"anejo:{n}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in PUNTO_DE_ANEJO.finditer(text):
        out.append({"raw": m.group(0),
                    "locator_key":
                        f"anejo:{m.group(4)}.punto:{m.group(1)}{m.group(2)}",
                    "rule_ref": _rule_ref(text, m.start())})
        if m.group(3):
            out.append({"raw": m.group(0),
                        "locator_key":
                            f"anejo:{m.group(4)}.apartado:{m.group(3)}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in APARTADO_IV_ANEJO.finditer(text):
        if not PUNTO_DE_ANEJO.search(text[max(0, m.start() - 60):m.end()]):
            out.append({"raw": m.group(0),
                        "locator_key":
                            f"anejo:{m.group(2)}.apartado:{m.group(1)}",
                        "rule_ref": _rule_ref(text, m.start())})
    apats = active_profile().annex_state.patterns
    for m in apats["estados_list"].finditer(text):
        for tok in apats["estado_token"].findall(m.group(1)):
            out.append({"raw": m.group(0), "locator_key": f"estado:{tok}",
                        "rule_ref": _rule_ref(text, m.start())})
    seen, uniq = set(), []
    for r in out:
        if r["locator_key"] not in seen:
            seen.add(r["locator_key"])
            uniq.append(r)
    return uniq


def extract_introducers(text: str) -> list[str]:
    """Marker paths: 'la letra b)' → 'b'; 'numeral iii) de la letra i)'
    → 'i/iii'."""
    paths: list[str] = []
    for m in list(INTRO_RE.finditer(text)) + list(INTRO_RE2.finditer(text)):
        frag = m.group(1)
        for mm in NUMERALES_OF_LETRA.finditer(frag):
            for tok in ROMAN_TOKEN.findall(mm.group(1)):
                paths.append(f"{mm.group(2)}/{tok}")
        rest = NUMERALES_OF_LETRA.sub("", frag)
        for mm in NUMERAL_OF_LETRA.finditer(rest):
            paths.append(f"{mm.group(2)}/{mm.group(1)}")
        rest = NUMERAL_OF_LETRA.sub("", rest)
        for mm in LETRAS_MULTI.finditer(rest):
            paths.extend(re.findall(r"([a-z])\)", mm.group(1)))
        rest = LETRAS_MULTI.sub("", rest)
        for mm in LETRA_SINGLE.finditer(rest):
            paths.append(mm.group(1))
    return paths


def extract_dates(text: str) -> list[dict]:
    out = [{"raw": m.group(0), "iso": _iso(m), "epistemic": "OBSERVED"}
           for m in DATE_RE.finditer(text)]
    if "día siguiente al de su publicación" in text:
        out.append({"raw": "día siguiente al de su publicación",
                    "iso": None, "relative": "PUBLICATION_PLUS_1",
                    "epistemic": "DERIVED"})
    return out


def split_sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) char spans; '. ' before uppercase/«/digit. Marker-only
    spans ('1.', 'a)') merge forward into the next sentence."""
    spans, start = [], 0
    for m in re.finditer(r"\.\s+(?=[A-ZÁÉÍÓÚÑ«0-9(])", text):
        spans.append((start, m.end()))
        start = m.end()
    spans.append((start, len(text)))
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if not text[s:e].strip():
            continue
        if merged and re.fullmatch(r"(?:\d+\.|[a-z]\))\.?\s*",
                                   text[merged[-1][0]:merged[-1][1]]):
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def classify_modality(text: str) -> tuple[str, str]:
    for mod, rx in MODALITY_MARKERS:
        m = rx.search(text)
        if m:
            return mod, text[m.start():m.start() + 80].split(".")[0].strip()
    return "DECLARED_RULE", ""


def extract_conditions(text: str) -> list[dict]:
    conds = [{"raw": m.group(0).rstrip(",."), "normalized": None,
              "epistemic": "OBSERVED"}
             for m in re.finditer(r"(?:Si|Cuando) [^.]*?(?:,|\.)", text)]
    for m in FREQ_DATE_PAIR.finditer(text):
        freqs = [FREQ_MAP[t] for t in re.findall(
            r"mensual(?:es)?|trimestral(?:es)?|semestral(?:es)?|anual(?:es)?",
            m.group(2))]
        conds.append({"raw": m.group(0),
                      "normalized": {"frequency_in": freqs,
                                     "date": _iso(
                                         DATE_RE.search(m.group(1)))},
                      "epistemic": "DERIVED"})
    if "cuentas anuales correspondientes al ejercicio 2026" in text:
        conds.append({
            "raw": "cuentas anuales correspondientes al ejercicio 2026",
            "normalized": {"exercise": 2026}, "epistemic": "DERIVED"})
    return conds


def temporal_effects(text: str) -> list[dict]:
    """Structured effects: {effect, date_value, date_raw, condition_raw,
    condition_normalized, epistemic}."""
    effs = []
    kinds = [eff for eff, rx in TEMPORAL_MARKERS if rx.search(text)]

    for eff in dict.fromkeys(kinds):
        entry = {"effect": eff, "date_value": None, "date_raw": None,
                 "condition_raw": None, "condition_normalized": None,
                 "epistemic": "OBSERVED"}
        if eff == "INSTRUMENT_EFFECTIVE_FROM":
            entry.update(date_raw="día siguiente al de su publicación",
                         date_value=None, epistemic="DERIVED",
                         condition_normalized={
                             "relative": "PUBLICATION_PLUS_1"})
        elif eff == "APPLY_FROM":
            m = re.search(
                r"se aplicarán desde el (\d{1,2} de \w+ de \d{4})", text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(DATE_RE.search(m.group(1))))
        elif eff == "FIRST_REFERENCE_DATE":
            pairs = list(FREQ_DATE_PAIR.finditer(text))
            if pairs:
                for p in pairs:
                    freqs = [FREQ_MAP[t] for t in re.findall(
                        r"mensual(?:es)?|trimestral(?:es)?|"
                        r"semestral(?:es)?|anual(?:es)?", p.group(2))]
                    effs.append({
                        "effect": eff,
                        "date_value": _iso(DATE_RE.search(p.group(1))),
                        "date_raw": p.group(1),
                        "condition_raw": p.group(0),
                        "condition_normalized": {"frequency_in": freqs},
                        "epistemic": "DERIVED"})
                continue
            m = re.search(
                r"(\d{1,2} de \w+ de \d{4}) como primera fecha de referencia",
                text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(DATE_RE.search(m.group(1))))
        elif eff == "LAST_REFERENCE_DATE":
            m = re.search(
                r"correspondientes a[l]? (\d{1,2} de \w+ de \d{4})", text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(DATE_RE.search(m.group(1))))
        elif eff == "INITIAL_APPLICATION_DATE":
            m = re.search(r"será el (\d{1,2} de \w+ de \d{4})", text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(DATE_RE.search(m.group(1))))
        elif eff == "SCOPE_PERIOD":
            m = re.search(
                r"cuentas anuales \w+ y \w+ correspondientes al"
                r" (ejercicio \d{4})", text)
            if m:
                entry.update(condition_raw=m.group(1),
                             condition_normalized={"exercise": 2026},
                             epistemic="DERIVED")
        effs.append(entry)
    return effs


def section_nodes(doc: DiarioDoc) -> dict:
    arts = [n for n in doc.nodes if n.cls == "articulo"]
    sig = next((n.index for n in doc.nodes
                if n.kind == "p" and SIGNATURE_RE.match(n.text)),
               len(doc.nodes))
    spans = {}
    for a in arts:
        m = _DISP_HEAD_RE.match(a.text)
        if m is None:
            continue
        code = _DISP_PREFIX[m.group(1).lower()] + (
            _DISP_ORDINAL.get(m.group(2).lower(), m.group(2).lower())
            if m.group(2) else "u")
        if code in spans:  # second unnumbered provision of same type
            code = f"{code}.{sum(1 for k in spans if k.split('.')[0] == code)}"
        head = a.index
        nxt = min([n.index for n in arts if n.index > head] + [sig])
        nodes = [n for n in doc.nodes[head + 1:nxt] if n.kind == "p"]
        style = ("num" if any(re.match(r"^\d+\.\s", n.text)
                              for n in nodes) else "alpha")
        spans[code] = (head, nodes, style)
    return spans


@dataclass
class Clause:
    clause_key: str             # stable within the instrument: 'dt1:2:s1'
    section: str
    item: str
    sub: int
    node_span: list
    char_span: list
    text: str
    temporal_effects: list = field(default_factory=list)
    modality: str = ""
    action_raw: str = ""
    subjects: list = field(default_factory=list)
    introducers: list = field(default_factory=list)
    conditions: list = field(default_factory=list)
    dates: list = field(default_factory=list)
    parent_key: str | None = None
    relation_to_parent: str | None = None
    epistemic: str = "OBSERVED"


def extract_clauses(doc: DiarioDoc) -> list[Clause]:
    spans = section_nodes(doc)
    clauses: list[Clause] = []
    for code, (head, nodes, style) in spans.items():
        items: list[tuple[str, list]] = []
        cur_label, cur_nodes = None, []
        item_re = (re.compile(r"^(\d+)\.\s") if style == "num"
                   else re.compile(r"^([a-z])\)\s"))
        for n in nodes:
            m = item_re.match(n.text)
            if m:
                if cur_label is not None:
                    items.append((cur_label, cur_nodes))
                cur_label, cur_nodes = m.group(1), [n]
            elif cur_label is not None:
                cur_nodes.append(n)
        if cur_label is not None:
            items.append((cur_label, cur_nodes))
        if not items and nodes:
            items = [("único", nodes)]
        # dfu: a leading unmarked paragraph before 'a)' is the base rule
        if code == "dfu" and items:
            pre = [n for n in nodes if n.index < items[0][1][0].index]
            if pre:
                items = [("base", pre)] + items

        for label, nnodes in items:
            text = " ".join(n.text for n in nnodes)
            pos, offs = 0, []
            for n in nnodes:
                offs.append((n.index, pos))
                pos += len(n.text) + 1
            sub = 0
            for s, e in split_sentences(text):
                sent = text[s:e].strip()
                has_core = bool(temporal_effects(sent)
                                or classify_modality(sent)[1]
                                or CONDITIONAL_OPENER.match(sent))
                if clauses and not has_core:
                    clauses[-1].text += " " + sent
                    clauses[-1].char_span[1] = e
                    continue
                sub += 1
                node_ix = next((ix for ix, off in offs if off <= s),
                               nnodes[0].index)
                c = Clause(
                    clause_key=f"{code}:{label}:s{sub}",
                    section=code, item=label, sub=sub,
                    node_span=[node_ix, node_ix], char_span=[s, e],
                    text=sent)
                c.temporal_effects = temporal_effects(sent)
                c.modality, c.action_raw = classify_modality(sent)
                c.subjects = extract_subjects(sent)
                c.introducers = extract_introducers(sent)
                c.conditions = extract_conditions(sent)
                c.dates = extract_dates(sent)
                if any(d["epistemic"] == "DERIVED" for d in c.dates) or \
                   any(x["epistemic"] == "DERIVED"
                       for x in c.conditions) or \
                   any(x["epistemic"] == "DERIVED"
                       for x in c.temporal_effects):
                    c.epistemic = "DERIVED"
                clauses.append(c)
    return clauses


def assign_parents(clauses: list[Clause]) -> list[Clause]:
    """Wire juridical parent/child edges. Root clauses keep
    parent_key=None / relation_to_parent=None (the discovery label BASE
    is not a stored edge)."""
    by_item = {}
    for c in clauses:
        if c.sub == 1:
            by_item.setdefault((c.section, c.item), c)

    for c in list(clauses):
        m = EXCEPT_APARTADOS.search(c.text)
        if m:
            for (sec, item), head in by_item.items():
                if sec == c.section and item.isdigit() \
                        and int(m.group(1)) <= int(item) <= int(m.group(2)):
                    head.parent_key = c.clause_key
                    head.relation_to_parent = "EXCEPTION"
        if ESPECIFICIDADES.search(c.text):
            for (sec, item), head in by_item.items():
                if sec == c.section and len(item) == 1 and item.isalpha() \
                        and head is not c:
                    head.parent_key = c.clause_key
                    head.relation_to_parent = "EXCEPTION"
        m = SIN_PERJUICIO.search(c.text)
        if m:
            tgt = {"primera": "dt1", "segunda": "dt2",
                   "tercera": "dt3"}.get(m.group(1).rsplit(" ", 1)[-1])
            sub = Clause(
                clause_key=f"{c.clause_key}:carveout", section=c.section,
                item=c.item, sub=99, node_span=c.node_span,
                char_span=[c.char_span[0] + m.start(),
                           c.char_span[0] + m.end()],
                text=m.group(0), parent_key=c.clause_key,
                relation_to_parent="EXCEPTION", modality="DECLARED_RULE")
            sub.conditions = [{"raw": m.group(0),
                               "normalized": {"cites_section": tgt},
                               "epistemic": "DERIVED"}]
            sub.subjects = extract_subjects(c.text[:m.end() + 120])
            clauses.append(sub)
        if re.search(r"(?:Si optara|Cuando haya optado) por no reexpresar",
                     c.text):
            opt = next((x for x in clauses
                        if x.section == c.section
                        and "no estará obligada a reexpresar" in x.text),
                       None)
            if opt is not None:
                c.parent_key = opt.clause_key
                c.relation_to_parent = "QUALIFIER"
        if c.sub > 1 and c.modality == "OPTION" \
                and c.parent_key is None:
            head = by_item.get((c.section, c.item))
            if head is not None and head.clause_key != c.clause_key:
                c.parent_key = head.clause_key
                c.relation_to_parent = "ALTERNATIVE"
    for c in clauses:
        if c.parent_key is None and c.sub > 1 \
                and c.relation_to_parent is None:
            head = by_item.get((c.section, c.item))
            if head is not None and head.clause_key != c.clause_key:
                c.parent_key = head.clause_key
                c.relation_to_parent = "PART_OF"
    return clauses


def resolve_relative_dates(clauses: list[Clause],
                           fecha_publicacion: str) -> None:
    """PUBLICATION_PLUS_1 → concrete ISO date. The phrase is OBSERVED; the
    computed date is DERIVED."""
    if not fecha_publicacion:
        return
    iso = (datetime.date(int(fecha_publicacion[:4]),
                         int(fecha_publicacion[4:6]),
                         int(fecha_publicacion[6:8]))
           + datetime.timedelta(days=1)).isoformat()
    for c in clauses:
        for d in c.dates:
            if d.get("relative") == "PUBLICATION_PLUS_1":
                d["iso"] = iso
                d["resolved_from"] = {"fecha_publicacion": fecha_publicacion,
                                      "rule": "+1 day"}
        for e_ in c.temporal_effects:
            cn = e_.get("condition_normalized") or {}
            if cn.get("relative") == "PUBLICATION_PLUS_1":
                e_["date_value"] = iso


def build_paths(ops) -> tuple[dict, list, set]:
    """({locator_key: [paths]}, [(path, [locator_keys])], container_keys).

    Marker paths mirror operations.py resolution: each 'Norma N.' section
    restarts a top-level letter sequence; nested items are roman numerals
    under the current letter."""
    key_to_paths: dict[str, list[str]] = {}
    op_paths: list[tuple[str, list[str]]] = []
    container_keys: set[str] = set()
    top = 0
    top_marker = ""
    for op in ops:
        parts = _marker_parts(op.clause_text)
        if parts is None:
            continue
        st, val = parts
        aval = _alpha_value(val) if st in ("alpha", "amb") else 0
        if val == "a":
            top = 0
        if st in ("alpha", "amb") and aval == top + 1:
            top, top_marker = aval, val
            path = val
        else:
            path = f"{top_marker}/{val}" if top_marker else val
        keys = [s.locator_key for s in op.subjects]
        op_paths.append((path, keys))
        if op.is_container:
            container_keys.update(keys)
        for k in keys:
            key_to_paths.setdefault(k, []).append(path)
    return key_to_paths, op_paths, container_keys


def frequency_table(doc: DiarioDoc) -> tuple[dict, int | None]:
    """estado → periodicidad from the official norma 67 table of the
    *target* document — DECLARED, never inferred from the state name.

    Returns ({estado: FREQ}, table_node_index)."""
    for n in doc.nodes:
        if n.kind == "table" and n.rows and "Periodicidad" in n.rows[0]:
            out = {}
            for r in n.rows[1:]:
                per = r[2].strip().rstrip(".") if len(r) > 2 else ""
                out[r[0].strip()] = FREQ_MAP.get(per.lower(), per)
            return out, n.index
    return {}, None
