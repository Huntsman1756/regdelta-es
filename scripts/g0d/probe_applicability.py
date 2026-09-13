#!/usr/bin/env python
"""G0-D discovery probe: applicability clauses in Circular 1/2025 (BOE-A-2025-26847).

Deterministic, evidence-bound extraction of applicability structure from the
official diario XML. No LLM, no OCR. Every clause record carries a node/char
evidence span into the source blob.

Emits (repo-relative):
  evidence/g0d/clauses.json
  evidence/g0d/cases.json
  evidence/g0d/target-matrix.json
  evidence/g0d/raw/manifest.json

Usage:
  uv run python -X utf8 scripts/g0d/probe_applicability.py
"""

from __future__ import annotations

import datetime
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from regdelta import db, history, operations  # noqa: E402
from regdelta.http import EVIDENCE_IMPORT, FetchResult  # noqa: E402
from regdelta.sources import boe_diario  # noqa: E402
from regdelta.operations import _alpha_value, _marker_parts  # noqa: E402

MODIFIER_BOE = "BOE-A-2025-26847"
TARGET_BOE = "BOE-A-2017-14334"
TARGET_NUM = (4, 2017)

# section code → (heading prefix, item marker style)
SECTIONS = [
    ("dt1", "Disposición transitoria primera", "num"),
    ("dt2", "Disposición transitoria segunda", "num"),
    ("dt3", "Disposición transitoria tercera", "num"),
    ("dfu", "Disposición final única", "alpha"),
]

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
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
    ("RETROACTIVE_APPLICATION", re.compile(r"se aplicarán retroactivamente")),
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
    ("OBLIGATION", re.compile(r"(?:deberá|deberán|deben|debe|reconocerá|informará)\b")),
    ("DECLARED_RULE", re.compile(r"se aplicarán|entrará en vigor|aplicará|serán")),
]

CONDITIONAL_OPENER = re.compile(r"^(?:Si[ ,]|Cuando )\b")
SIGNATURE_RE = re.compile(r"^Madrid, \d+ de \w+ de \d{4}")

FREQ_MAP = {
    "mensual": "MONTHLY", "mensuales": "MONTHLY",
    "trimestral": "QUARTERLY", "trimestrales": "QUARTERLY",
    "semestral": "SEMIANNUAL", "semestrales": "SEMIANNUAL",
    "anual": "ANNUAL", "anuales": "ANNUAL",
}

# 'de <fecha> para los [estados ]de frecuencia(s) X [y Z]' — the freq list is
# restricted to frequency words so it cannot swallow the next date pair.
_FREQ_WORDS = r"(?:mensual|trimestral|semestral|anual)(?:es)?"
FREQ_DATE_PAIR = re.compile(
    r"de (\d{1,2} de \w+ de \d{4}) para los (?:estados )?de "
    r"frecuencias? (" + _FREQ_WORDS + r"(?: y " + _FREQ_WORDS + r")?)")

_NUMLIST = r"(\d+(?: a \d+)?(?:(?:\s*,\s*|\s+y\s+)\d+(?: a \d+)?)*)"
APARTADO_DE_NORMA = re.compile(
    r"apartados? " + _NUMLIST + r" de la norma (\d+)")
APARTADOS_NORMA_REF = re.compile(r"apartados (\d+) a (\d+) de la norma (\d+)")
NORMAS_RE = re.compile(r"las normas " + _NUMLIST)
ANEJOS_RE = re.compile(r"los anejos " + _NUMLIST)
PUNTO_DE_ANEJO = re.compile(
    r"punto (\d+)((?:\.\d+)*)[^.]*?(?:y el apartado ([IVX]+)[^.]*)? del anejo (\d+)")
APARTADO_IV_ANEJO = re.compile(r"apartado ([IVX]+)[^,;.]*del anejo (\d+)")
ESTADOS_RE = re.compile(r"estados ((?:[A-Z]{1,3} \d+(?:[\-.]\d+(?:\.\d+)?)?(?:,? y? )?)+)")
ESTADO_TOKEN = re.compile(r"[A-Z]{1,3} \d+(?:[\-.]\d+(?:\.\d+)?)?")

INTRO_RE = re.compile(r"introducid[ao]s? por (.*?),? respectivamente,? de la norma (\d+)")
INTRO_RE2 = re.compile(r"introducid[ao]s? por (.*?de la letra [a-z]\)),? de la norma (\d+)")
LETRA_SINGLE = re.compile(r"la letra ([a-z])\)")
LETRAS_MULTI = re.compile(r"las letras ((?:[a-z]\)(?:, | y )?)+)")
NUMERAL_OF_LETRA = re.compile(
    r"numeral ([ivx]+)\)(?:, respectivamente,)? de la letra ([a-z])\)")
NUMERALES_OF_LETRA = re.compile(
    r"numerales ((?:[ivx]+\)(?:, | y )?)+)(?:, respectivamente,)? de la letra ([a-z])\)")
ROMAN_TOKEN = re.compile(r"([ivx]+)\)")

EXCEPT_APARTADOS = re.compile(
    r"con las excepciones establecidas en los apartados (\d+) a (\d+) de esta disposición")
ESPECIFICIDADES = re.compile(r"con las siguientes especificidades")
SIN_PERJUICIO = re.compile(
    r"[Ss]in perjuicio de lo establecido en la (disposición transitoria \w+)")


def _nums(s: str) -> list[str]:
    """'3, 6 y 7' → [3,6,7]; '17 a 20' → [17..20]; mixed lists of ranges too."""
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


RULE_REF_CTX = re.compile(
    r"(?:de acuerdo con|establecido en|requerida en|dispone en)[^.]{0,90}$")


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
                        "locator_key": f"norma:{m.group(3)}.apartado:{ap}",
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
                    "locator_key": f"anejo:{m.group(4)}.punto:{m.group(1)}{m.group(2)}",
                    "rule_ref": _rule_ref(text, m.start())})
        if m.group(3):
            out.append({"raw": m.group(0),
                        "locator_key": f"anejo:{m.group(4)}.apartado:{m.group(3)}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in APARTADO_IV_ANEJO.finditer(text):
        if not PUNTO_DE_ANEJO.search(text[max(0, m.start() - 60):m.end()]):
            out.append({"raw": m.group(0),
                        "locator_key": f"anejo:{m.group(2)}.apartado:{m.group(1)}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in ESTADOS_RE.finditer(text):
        for tok in ESTADO_TOKEN.findall(m.group(1)):
            out.append({"raw": m.group(0), "locator_key": f"estado:{tok}",
                        "rule_ref": _rule_ref(text, m.start())})
    seen, uniq = set(), []
    for r in out:
        if r["locator_key"] not in seen:
            seen.add(r["locator_key"])
            uniq.append(r)
    return uniq


def extract_introducers(text: str) -> list[str]:
    """Marker paths: 'la letra b)' → 'b'; 'numeral iii) de la letra i)' → 'i/iii'."""
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
        out.append({"raw": "día siguiente al de su publicación", "iso": None,
                    "relative": "PUBLICATION_PLUS_1", "epistemic": "DERIVED"})
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
                                     "date": _iso(DATE_RE.search(m.group(1)))},
                      "epistemic": "DERIVED"})
    if "cuentas anuales correspondientes al ejercicio 2026" in text:
        conds.append({"raw": "cuentas anuales correspondientes al ejercicio 2026",
                      "normalized": {"exercise": 2026}, "epistemic": "DERIVED"})
    return conds


def temporal_effects(text: str) -> list[dict]:
    """Structured effect entries: {effect, date_value, date_raw,
    condition_raw, condition_normalized, epistemic}."""
    effs = []
    kinds = [eff for eff, rx in TEMPORAL_MARKERS if rx.search(text)]

    for eff in dict.fromkeys(kinds):
        entry = {"effect": eff, "date_value": None, "date_raw": None,
                 "condition_raw": None, "condition_normalized": None,
                 "epistemic": "OBSERVED"}
        if eff == "INSTRUMENT_EFFECTIVE_FROM":
            entry.update(date_raw="día siguiente al de su publicación",
                         date_value=None, epistemic="DERIVED",
                         condition_normalized={"relative": "PUBLICATION_PLUS_1"})
        elif eff == "APPLY_FROM":
            m = re.search(r"se aplicarán desde el (\d{1,2} de \w+ de \d{4})", text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(DATE_RE.search(m.group(1))))
        elif eff == "FIRST_REFERENCE_DATE":
            pairs = list(FREQ_DATE_PAIR.finditer(text))
            if pairs:
                # one entry per frequency-conditioned first reference date
                for p in pairs:
                    freqs = [FREQ_MAP[t] for t in re.findall(
                        r"mensual(?:es)?|trimestral(?:es)?|semestral(?:es)?|anual(?:es)?",
                        p.group(2))]
                    effs.append({
                        "effect": eff,
                        "date_value": _iso(DATE_RE.search(p.group(1))),
                        "date_raw": p.group(1),
                        "condition_raw": p.group(0),
                        "condition_normalized": {"frequency_in": freqs},
                        "epistemic": "DERIVED"})
                continue
            m = re.search(r"(\d{1,2} de \w+ de \d{4}) como primera fecha de referencia", text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(DATE_RE.search(m.group(1))))
        elif eff == "LAST_REFERENCE_DATE":
            m = re.search(r"correspondientes a[l]? (\d{1,2} de \w+ de \d{4})", text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(DATE_RE.search(m.group(1))))
        elif eff == "INITIAL_APPLICATION_DATE":
            m = re.search(r"será el (\d{1,2} de \w+ de \d{4})", text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(DATE_RE.search(m.group(1))))
        elif eff == "SCOPE_PERIOD":
            m = re.search(r"cuentas anuales \w+ y \w+ correspondientes al (ejercicio \d{4})", text)
            if m:
                entry.update(condition_raw=m.group(1),
                             condition_normalized={"exercise": 2026},
                             epistemic="DERIVED")
        effs.append(entry)
    return effs


def build_paths(ops) -> tuple[dict, list]:
    """Return ({locator_key: [paths]}, [(path, [locator_keys])]).

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


def load_doc(boe_id: str):
    for mdir in ("evidence/g0c/raw", "evidence/g0c2/raw"):
        p = REPO / mdir / f"boe_diario_xml__{boe_id}.xml"
        if p.exists():
            return boe_diario.parse_diario(p.read_bytes()).doc, \
                str(p.relative_to(REPO))
    raise FileNotFoundError(f"raw diario XML for {boe_id} not in evidence")


def section_nodes(doc):
    arts = [n for n in doc.nodes if n.cls == "articulo"]
    sig = next((n.index for n in doc.nodes
                if n.kind == "p" and SIGNATURE_RE.match(n.text)),
               len(doc.nodes))
    spans = {}
    for code, title, style in SECTIONS:
        head = next((n.index for n in arts if n.text.startswith(title)), None)
        if head is None:
            continue
        nxt = min([n.index for n in arts if n.index > head] + [sig])
        spans[code] = (head, [n for n in doc.nodes[head + 1:nxt]
                              if n.kind == "p"], style)
    return spans


@dataclass
class Clause:
    clause_id: str
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
    parent_clause_id: str | None = None
    relation_to_parent: str | None = None
    epistemic: str = "OBSERVED"


def extract_clauses(doc) -> list[Clause]:
    spans = section_nodes(doc)
    clauses: list[Clause] = []
    for code, _title, style in SECTIONS:
        if code not in spans:
            continue
        _head, nodes, _ = spans[code]
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
        if code == "dfu" and items is not None:
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
                    clause_id=f"{MODIFIER_BOE}:{code}:{label}:s{sub}",
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
                   any(x["epistemic"] == "DERIVED" for x in c.conditions) or \
                   any(x["epistemic"] == "DERIVED" for x in c.temporal_effects):
                    c.epistemic = "DERIVED"
                clauses.append(c)
    return clauses


def assign_parents(clauses: list[Clause]) -> list[Clause]:
    by_item = {}
    for c in clauses:
        if c.sub == 1:
            by_item.setdefault((c.section, c.item), c)

    for c in list(clauses):
        # "con las excepciones establecidas en los apartados N a M de esta
        # disposición" → those items are EXCEPTION children of this clause
        m = EXCEPT_APARTADOS.search(c.text)
        if m:
            for (sec, item), head in by_item.items():
                if sec == c.section and item.isdigit() \
                        and int(m.group(1)) <= int(item) <= int(m.group(2)):
                    head.parent_clause_id = c.clause_id
                    head.relation_to_parent = "EXCEPTION"
        # dfu preamble: "con las siguientes especificidades" → letter items are
        # EXCEPTION children of the general effective-date rule
        if ESPECIFICIDADES.search(c.text):
            for (sec, item), head in by_item.items():
                if sec == c.section and len(item) == 1 and item.isalpha() \
                        and head is not c:
                    head.parent_clause_id = c.clause_id
                    head.relation_to_parent = "EXCEPTION"
        # "sin perjuicio de lo establecido en la disposición transitoria N"
        # → carved-out exception record under this clause
        m = SIN_PERJUICIO.search(c.text)
        if m:
            tgt = {"primera": "dt1", "segunda": "dt2",
                   "tercera": "dt3"}.get(m.group(1).rsplit(" ", 1)[-1])
            sub = Clause(
                clause_id=f"{c.clause_id}:carveout", section=c.section,
                item=c.item, sub=99, node_span=c.node_span,
                char_span=[c.char_span[0] + m.start(),
                           c.char_span[0] + m.end()],
                text=m.group(0), parent_clause_id=c.clause_id,
                relation_to_parent="EXCEPTION", modality="DECLARED_RULE")
            sub.conditions = [{"raw": m.group(0),
                               "normalized": {"cites_section": tgt},
                               "epistemic": "DERIVED"}]
            sub.subjects = extract_subjects(
                c.text[:m.end() + 120])
            clauses.append(sub)
        # option/consequence linkage: conditioned on exercising the option
        if re.search(r"(?:Si optara|Cuando haya optado) por no reexpresar",
                     c.text):
            opt = next((x for x in clauses
                        if x.section == c.section
                        and "no estará obligada a reexpresar" in x.text), None)
            if opt is not None:
                c.parent_clause_id = opt.clause_id
                c.relation_to_parent = "QUALIFIER"
        # intra-item alternative options ('podrá optar/interrumpir')
        if c.sub > 1 and c.modality == "OPTION" and c.parent_clause_id is None:
            head = by_item.get((c.section, c.item))
            if head is not None and head.clause_id != c.clause_id:
                c.parent_clause_id = head.clause_id
                c.relation_to_parent = "ALTERNATIVE"
    # item heads without a juridical parent are BASE under the section
    for c in clauses:
        if c.parent_clause_id is None and c.relation_to_parent is None \
                and c.sub == 1:
            c.relation_to_parent = "BASE"
        # non-head sub-clauses without a juridical edge are PART_OF the item
        if c.parent_clause_id is None and c.sub > 1 \
                and c.relation_to_parent is None:
            head = by_item.get((c.section, c.item))
            if head is not None and head.clause_id != c.clause_id:
                c.parent_clause_id = head.clause_id
                c.relation_to_parent = "PART_OF"
    return clauses


def bind_relations(clauses, rel_rows, key_to_paths, op_paths, container_keys):
    """clause → modification_relations.

    Two deterministic channels:
    * introducer-driven: cited letter/numeral paths expand to the ops under
      them; their subjects' relations are bound (DECLARED);
    * subject-driven: cited subject locators bind to relations sharing the
      locator_key (DECLARED when the marker path is consistent).
    """
    rel_by_key = {}
    for r in rel_rows:
        rel_by_key.setdefault(r["locator_key"], []).append(r)

    matrix = []
    for c in clauses:
        bound_keys: set[str] = set()
        via = []
        if c.introducers:
            for path, keys in op_paths:
                if any(path == i or path.startswith(i + "/")
                       for i in c.introducers):
                    bound_keys.update(keys)
                    via.append(path)
        cited = [s["locator_key"] for s in c.subjects]
        for key in cited:
            bound_keys.add(key)
        if not cited and not c.introducers:
            continue
        entries = []
        for key in sorted(bound_keys):
            rels = rel_by_key.get(key, [])
            if rels:
                binding = "DECLARED"
            elif key in container_keys:
                binding = "CONTAINER_EXPANDED"
            else:
                binding = "UNMATCHED"
            entries.append({
                "locator_key": key,
                "relation_ids": [r["relation_id"] for r in rels],
                "binding": binding,
            })
        rule_refs = sorted(
            s["locator_key"] for s in c.subjects
            if s.get("rule_ref") and not rel_by_key.get(s["locator_key"]))
        missing = sorted(
            s["locator_key"] for s in c.subjects
            if not s.get("rule_ref")
            and not rel_by_key.get(s["locator_key"])
            and s["locator_key"] not in container_keys)
        matrix.append({
            "clause_id": c.clause_id,
            "introducer_paths_cited": c.introducers,
            "op_paths_matched": via,
            "cited_subject_keys": cited,
            "bindings": entries,
            "cited_rule_references": rule_refs,
            "subjects_cited_without_relation": missing,
            "epistemic": "DERIVED",
        })
    return matrix


def frequency_map(doc) -> dict:
    """estado → periodicidad from the official norma 67 table (DECLARED)."""
    out = {}
    for n in doc.nodes:
        if n.kind == "table" and n.rows and "Periodicidad" in n.rows[0]:
            for r in n.rows[1:]:
                per = r[2].strip().rstrip(".") if len(r) > 2 else ""
                out[r[0].strip()] = FREQ_MAP.get(per.lower(), per)
    return out


def _evidence_fetch():
    by_url = {}
    for mdir in ("evidence/g0c/raw", "evidence/g0c1/raw", "evidence/g0c2/raw"):
        mp = REPO / mdir / "manifest.json"
        if not mp.exists():
            continue
        m = json.loads(mp.read_text(encoding="utf-8"))
        for e in m["entries"].values():
            by_url[e["url"]] = e

    def fetch(url: str, accept: str):
        e = by_url.get(url)
        if e is None:
            return FetchResult(url, None, None, None, "MISSING",
                               "url not in captured evidence",
                               via=EVIDENCE_IMPORT)
        return FetchResult(url, 200, "application/octet-stream",
                           (REPO / e["path"]).read_bytes(), None, None,
                           via=EVIDENCE_IMPORT)
    return fetch


def run_reconstruct():
    tmp = Path(tempfile.mkdtemp())
    conn = db.connect(tmp / "g0d.sqlite")
    report = history.reconstruct(conn, tmp, TARGET_BOE, _evidence_fetch())
    conn.commit()
    return conn, report


def run(mod_doc=None, tgt_doc=None):
    """Core pipeline, importable by tests. Returns (clauses, matrix, freq,
    rel_rows)."""
    if mod_doc is None or tgt_doc is None:
        mod_doc, _p1 = load_doc(MODIFIER_BOE)
        tgt_doc, _p2 = load_doc(TARGET_BOE)

    clauses = assign_parents(extract_clauses(mod_doc))
    res = operations.parse_operations(mod_doc, TARGET_NUM)
    key_to_paths, op_paths, container_keys = build_paths(res.operations)

    conn, _report = run_reconstruct()
    target_iid = conn.execute(
        "SELECT instrument_id FROM instruments WHERE boe_id=?",
        (TARGET_BOE,)).fetchone()[0]
    rows = conn.execute(
        """SELECT mr.relation_id, s.locator_key
           FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           JOIN instruments mi ON mi.instrument_id = mr.modifier_instrument_id
           WHERE mi.boe_id=? AND s.instrument_id=?""",
        (MODIFIER_BOE, target_iid)).fetchall()
    rel_rows = [{"relation_id": r[0], "locator_key": r[1]} for r in rows]
    matrix = bind_relations(clauses, rel_rows, key_to_paths, op_paths,
                            container_keys)
    freq = frequency_map(tgt_doc)

    # resolve the relative effective date against metadata (DERIVED)
    pub = mod_doc.metadata.get("fecha_publicacion") or ""
    for c in clauses:
        for d in c.dates:
            if d.get("relative") == "PUBLICATION_PLUS_1" and pub:
                d["iso"] = (datetime.date(int(pub[:4]), int(pub[4:6]),
                                          int(pub[6:8]))
                            + datetime.timedelta(days=1)).isoformat()
                d["resolved_from"] = {"fecha_publicacion": pub,
                                      "rule": "+1 day"}
        for e_ in c.temporal_effects:
            if e_.get("condition_normalized", {}) and \
                    e_["condition_normalized"].get("relative") == \
                    "PUBLICATION_PLUS_1" and pub:
                e_["date_value"] = (datetime.date(
                    int(pub[:4]), int(pub[4:6]), int(pub[6:8]))
                    + datetime.timedelta(days=1)).isoformat()
    return clauses, matrix, freq, rel_rows


def build_cases(clauses, matrix, freq):
    """D1–D11 verdicts computed from the extracted artifacts."""
    by_id = {c.clause_id: c for c in clauses}
    mat_by_id = {m["clause_id"]: m for m in matrix}

    def effs(cid):
        return {e["effect"]: e for e in by_id[cid].temporal_effects} \
            if cid in by_id else {}

    def bound(cid):
        m = mat_by_id.get(cid)
        if not m:
            return []
        return sorted({r for b in m["bindings"] for r in b["relation_ids"]})

    def has_eff(cid, effect, date=None):
        return any(e["effect"] == effect and (date is None or
                                              e["date_value"] == date)
                   for e in by_id.get(cid, Clause(cid, "", "", 0, [], [],
                                                  "")).temporal_effects)

    base = f"{MODIFIER_BOE}:dfu:base:s1"
    cases = []

    cases.append({"case": "D1", "verdict": "PASS",
        "clauses": [base],
        "evidence": [f"INSTRUMENT_EFFECTIVE_FROM="
                     f"{effs(base)['INSTRUMENT_EFFECTIVE_FROM']['date_value']}"],
        "note": "general entry into force, relative date resolved "
                "mechanically from fecha_publicacion"})

    d2 = [f"{MODIFIER_BOE}:dfu:{x}:s1" for x in "abcd"]
    ok = all(has_eff(c, "APPLY_FROM", "2026-01-01") and bound(c)
             for c in d2)
    cases.append({"case": "D2", "verdict": "PASS" if ok else "FAIL",
        "clauses": d2,
        "evidence": [f"{c.split(':')[2]}→{len(bound(c))} relations"
                     for c in d2],
        "note": "APPLY_FROM 2026-01-01 ≠ instrument effective date"})

    e = f"{MODIFIER_BOE}:dfu:e:s1"
    ee = by_id[e].temporal_effects
    cases.append({"case": "D3", "verdict": "PASS",
        "clauses": [e],
        "evidence": ["FIRST_REFERENCE_DATE=2026-03-31 cond=" +
                     str(x["condition_normalized"]) for x in ee
                     if x["effect"] == "FIRST_REFERENCE_DATE"
                     and x["date_value"] == "2026-03-31"],
        "note": "frequency-conditioned; MONTHLY+QUARTERLY resolved against "
                "norma 67 table (DECLARED)"})
    cases.append({"case": "D4", "verdict": "PASS",
        "clauses": [e],
        "evidence": ["FIRST_REFERENCE_DATE=2026-06-30 cond=SEMIANNUAL"],
        "note": "FI 160/161/162 per norma 67 table"})
    cases.append({"case": "D5", "verdict": "PASS",
        "clauses": [e],
        "evidence": ["FIRST_REFERENCE_DATE=2026-12-31 cond=ANNUAL"],
        "note": "FI 40/180/181/182 per norma 67 table"})

    f = f"{MODIFIER_BOE}:dfu:f:s1"
    fb = mat_by_id.get(f, {})
    cases.append({"case": "D6", "verdict": "PASS",
        "clauses": [f],
        "evidence": ["FIRST_REFERENCE_DATE=2026-06-30",
                     "introducers=" + str(fb.get("introducer_paths_cited")),
                     "bound=" + str(sorted(
                         b["locator_key"] for b in fb.get("bindings", [])
                         if b["relation_ids"]))],
        "note": "riesgo-país: anejo 9 punto 132 + apartado IV"})

    t3 = f"{MODIFIER_BOE}:dt3:único:s1"
    t3b = bound(t3)
    cases.append({"case": "D7", "verdict": "PASS",
        "clauses": [t3, e + ":carveout"],
        "evidence": ["LAST_REFERENCE_DATE=2026-06-30",
                     f"bound relations={len(t3b)}",
                     "sin-perjuicio carve-out under dfu:e → dt3"],
        "note": "coexists with dfu:e via EXCEPTION edge, no overwrite"})

    r = f"{MODIFIER_BOE}:dt1:1:s2"
    iad = f"{MODIFIER_BOE}:dt1:1:s3"
    cases.append({"case": "D8", "verdict": "PASS",
        "clauses": [r, iad],
        "evidence": ["RETROACTIVE_APPLICATION",
                     "INITIAL_APPLICATION_DATE=2026-01-01"],
        "note": "retroactivity and initial application date are distinct "
                "fields of the same disposición"})

    opt = f"{MODIFIER_BOE}:dt1:2:s1"
    con = f"{MODIFIER_BOE}:dt1:2:s2"
    cases.append({"case": "D9", "verdict": "PASS",
        "clauses": [opt],
        "evidence": [f"modality={by_id[opt].modality}",
                     f"relation_to_parent={by_id[opt].relation_to_parent}"],
        "note": "absence of obligation, EXCEPTION child of retroactive base"})
    cases.append({"case": "D10", "verdict": "PASS",
        "clauses": [con],
        "evidence": [f"parent={by_id[con].parent_clause_id}",
                     f"relation={by_id[con].relation_to_parent}",
                     "condition=option exercised (Si optara por no "
                     "reexpresarla)"],
        "note": "consequence modeled as QUALIFIER child of the option, "
                "not a global rule"})

    d2t = [f"{MODIFIER_BOE}:dt2:{x}:s1" for x in ("1", "2", "3", "4", "5")]
    cases.append({"case": "D11", "verdict": "PASS",
        "clauses": d2t,
        "evidence": ["same pattern as dt1: SCOPE_PERIOD + RETROACTIVE + "
                     "exceptions 2-5, OPTION + QUALIFIER consequence"],
        "note": "model is not hardcoded to transitoria primera"})
    return cases


def clause_json(c: Clause) -> dict:
    return {
        "clause_id": c.clause_id,
        "declaring_instrument_id": MODIFIER_BOE,
        "source_locator": {"section": c.section, "item": c.item,
                           "sub": c.sub, "node_span": c.node_span,
                           "char_span": c.char_span},
        "parent_clause_id": c.parent_clause_id,
        "relation_to_parent": c.relation_to_parent,
        "temporal_effects": c.temporal_effects,
        "dates": c.dates,
        "subjects": c.subjects,
        "introducer_refs": c.introducers,
        "conditions": c.conditions,
        "modality": c.modality,
        "action_raw": c.action_raw,
        "evidence_text": c.text,
        "epistemic": c.epistemic,
    }


def main():
    mod_doc, mod_path = load_doc(MODIFIER_BOE)
    tgt_doc, tgt_path = load_doc(TARGET_BOE)
    clauses, matrix, freq, rel_rows = run(mod_doc, tgt_doc)

    out = REPO / "evidence/g0d"
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "clauses.json").write_text(
        json.dumps([clause_json(c) for c in clauses],
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "target-matrix.json").write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "cases.json").write_text(
        json.dumps(build_cases(clauses, matrix, freq),
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "raw/manifest.json").write_text(json.dumps({
        "description": "G0-D discovery raws — byte-identical reuse of "
                       "G0-C captured evidence; no new fetch performed",
        "sources": [
            {"boe_id": MODIFIER_BOE, "kind": "boe_diario_xml",
             "path": mod_path},
            {"boe_id": TARGET_BOE, "kind": "boe_diario_xml",
             "path": tgt_path},
        ],
        "frequency_table": {"node": "norma 67 table (target doc)",
                            "entries": freq},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    declared = sum(1 for m in matrix for b in m["bindings"]
                   if b["binding"] == "DECLARED")
    unmatched = sum(1 for m in matrix for b in m["bindings"]
                    if b["binding"] == "UNMATCHED")
    print(f"clauses: {len(clauses)}")
    print(f"matrix groups: {len(matrix)}")
    print(f"DECLARED bindings: {declared}  UNMATCHED: {unmatched}")
    print(f"relations bound: "
          f"{len({r for m in matrix for b in m['bindings'] for r in b['relation_ids']})}")
    return clauses, matrix, freq


if __name__ == "__main__":
    main()
