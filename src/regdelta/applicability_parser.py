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

# F7 disposicion/clause vocabulary (dates, frequencies, temporal and
# modal lexemes, subject-reference and introducer patterns) is owned by
# the active profile's applicability_language facet; clause assembly,
# epistemic derivation and parent wiring below are core policy.
# Disposicion headings are discovered, not enumerated: the code is
# type-prefix + ordinal word so any N-th disposicion parses ('dt1',
# 'df2', 'da3', 'ddu').

def _date_re() -> re.Pattern:
    al = active_profile().applicability_language
    return re.compile(
        r"(\d{1,2}) de (" + "|".join(al.months) + r") de (\d{4})")


# 'estados FI 1, FI 2 y FI 3' scope lists and the code token — state-
# code vocabulary owned by the active profile's annex_state facet
# (PORT-2 C-016); the scope-resolution policy consuming them is core.

def _nums(s: str) -> list[str]:
    """'3, 6 y 7' → [3,6,7]; '17 a 20' → [17..20]."""
    al = active_profile().applicability_language
    out = []
    for part in re.split(al.nums_split, s.strip()):
        m = al.nums_range.match(part.strip())
        if m:
            out.extend(str(i) for i in range(int(m.group(1)),
                                             int(m.group(2)) + 1))
        else:
            out.extend(re.findall(r"\d+", part))
    return out


def _iso(m) -> str:
    months = active_profile().applicability_language.months
    return f"{m.group(3)}-{months[m.group(2)]:02d}-{int(m.group(1)):02d}"


def _rule_ref(text: str, start: int) -> bool:
    """True when the citation sits inside an applied-rule reference rather
    than naming a modified subject."""
    return bool(active_profile().applicability_language
                .rule_patterns["rule_ref_ctx"].search(text[:start]))


def extract_subjects(text: str) -> list[dict]:
    al = active_profile().applicability_language
    out = []
    for m in al.subject_refs["apartado_de_norma"].finditer(text):
        for ap in _nums(m.group(1)):
            out.append({"raw": m.group(0),
                        "locator_key": f"norma:{m.group(2)}.apartado:{ap}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in al.subject_refs["apartados_norma_ref"].finditer(text):
        for ap in range(int(m.group(1)), int(m.group(2)) + 1):
            out.append({"raw": m.group(0),
                        "locator_key":
                            f"norma:{m.group(3)}.apartado:{ap}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in al.subject_refs["normas"].finditer(text):
        for n in _nums(m.group(1)):
            out.append({"raw": m.group(0), "locator_key": f"norma:{n}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in al.subject_refs["anejos"].finditer(text):
        for n in _nums(m.group(1)):
            out.append({"raw": m.group(0), "locator_key": f"anejo:{n}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in al.subject_refs["punto_de_anejo"].finditer(text):
        out.append({"raw": m.group(0),
                    "locator_key":
                        f"anejo:{m.group(4)}.punto:{m.group(1)}{m.group(2)}",
                    "rule_ref": _rule_ref(text, m.start())})
        if m.group(3):
            out.append({"raw": m.group(0),
                        "locator_key":
                            f"anejo:{m.group(4)}.apartado:{m.group(3)}",
                        "rule_ref": _rule_ref(text, m.start())})
    for m in al.subject_refs["apartado_iv_anejo"].finditer(text):
        if not al.subject_refs["punto_de_anejo"].search(
                text[max(0, m.start() - 60):m.end()]):
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
    ip = active_profile().applicability_language.introducer_patterns
    paths: list[str] = []
    for m in (list(ip["intro"].finditer(text))
              + list(ip["intro_letra"].finditer(text))):
        frag = m.group(1)
        for mm in ip["numerales_of_letra"].finditer(frag):
            for tok in ip["roman_token"].findall(mm.group(1)):
                paths.append(f"{mm.group(2)}/{tok}")
        rest = ip["numerales_of_letra"].sub("", frag)
        for mm in ip["numeral_of_letra"].finditer(rest):
            paths.append(f"{mm.group(2)}/{mm.group(1)}")
        rest = ip["numeral_of_letra"].sub("", rest)
        for mm in ip["letras_multi"].finditer(rest):
            paths.extend(re.findall(r"([a-z])\)", mm.group(1)))
        rest = ip["letras_multi"].sub("", rest)
        for mm in ip["letra_single"].finditer(rest):
            paths.append(mm.group(1))
    return paths


def extract_dates(text: str) -> list[dict]:
    al = active_profile().applicability_language
    out = [{"raw": m.group(0), "iso": _iso(m), "epistemic": "OBSERVED"}
           for m in _date_re().finditer(text)]
    if al.pub_relative in text:
        out.append({"raw": al.pub_relative,
                    "iso": None, "relative": "PUBLICATION_PLUS_1",
                    "epistemic": "DERIVED"})
    return out


def split_sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) char spans; '. ' before uppercase/«/digit. Marker-only
    spans ('1.', 'a)') merge forward into the next sentence."""
    al = active_profile().applicability_language
    spans, start = [], 0
    for m in al.sentence_boundary.finditer(text):
        spans.append((start, m.end()))
        start = m.end()
    spans.append((start, len(text)))
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if not text[s:e].strip():
            continue
        if merged and re.fullmatch(al.marker_only,
                                   text[merged[-1][0]:merged[-1][1]]):
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def classify_modality(text: str) -> tuple[str, str]:
    for mod, rx in active_profile().applicability_language \
            .modality_markers:
        m = rx.search(text)
        if m:
            return mod, text[m.start():m.start() + 80].split(".")[0].strip()
    return "DECLARED_RULE", ""


def extract_conditions(text: str) -> list[dict]:
    al = active_profile().applicability_language
    conds = [{"raw": m.group(0).rstrip(",."), "normalized": None,
              "epistemic": "OBSERVED"}
             for m in al.condition_scan.finditer(text)]
    for m in al.freq_date_pair.finditer(text):
        freqs = [al.freq_map[t] for t in
                 al.freq_word_scan.findall(m.group(2))]
        conds.append({"raw": m.group(0),
                      "normalized": {"frequency_in": freqs,
                                     "date": _iso(
                                         _date_re().search(m.group(1)))},
                      "epistemic": "DERIVED"})
    if al.exercise_literal in text:
        conds.append({
            "raw": al.exercise_literal,
            "normalized": {"exercise": al.exercise_value},
            "epistemic": "DERIVED"})
    return conds


def temporal_effects(text: str) -> list[dict]:
    """Structured effects: {effect, date_value, date_raw, condition_raw,
    condition_normalized, epistemic}."""
    al = active_profile().applicability_language
    effs = []
    kinds = [eff for eff, rx in al.temporal_markers if rx.search(text)]

    for eff in dict.fromkeys(kinds):
        entry = {"effect": eff, "date_value": None, "date_raw": None,
                 "condition_raw": None, "condition_normalized": None,
                 "epistemic": "OBSERVED"}
        if eff == "INSTRUMENT_EFFECTIVE_FROM":
            entry.update(date_raw=al.pub_relative,
                         date_value=None, epistemic="DERIVED",
                         condition_normalized={
                             "relative": "PUBLICATION_PLUS_1"})
        elif eff == "APPLY_FROM":
            m = re.search(al.effect_date_patterns["APPLY_FROM"], text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(_date_re()
                                             .search(m.group(1))))
        elif eff == "FIRST_REFERENCE_DATE":
            pairs = list(al.freq_date_pair.finditer(text))
            if pairs:
                for p in pairs:
                    freqs = [al.freq_map[t] for t in
                             al.freq_word_scan.findall(p.group(2))]
                    effs.append({
                        "effect": eff,
                        "date_value": _iso(_date_re().search(p.group(1))),
                        "date_raw": p.group(1),
                        "condition_raw": p.group(0),
                        "condition_normalized": {"frequency_in": freqs},
                        "epistemic": "DERIVED"})
                continue
            m = re.search(
                al.effect_date_patterns["FIRST_REFERENCE_DATE"], text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(_date_re()
                                             .search(m.group(1))))
        elif eff == "LAST_REFERENCE_DATE":
            m = re.search(
                al.effect_date_patterns["LAST_REFERENCE_DATE"], text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(_date_re()
                                             .search(m.group(1))))
        elif eff == "INITIAL_APPLICATION_DATE":
            m = re.search(
                al.effect_date_patterns["INITIAL_APPLICATION_DATE"], text)
            if m:
                entry.update(date_raw=m.group(1),
                             date_value=_iso(_date_re()
                                             .search(m.group(1))))
        elif eff == "SCOPE_PERIOD":
            m = al.exercise_pattern.search(text)
            if m:
                entry.update(condition_raw=m.group(1),
                             condition_normalized={
                                 "exercise": al.exercise_value},
                             epistemic="DERIVED")
        effs.append(entry)
    return effs


def section_nodes(doc: DiarioDoc) -> dict:
    al = active_profile().applicability_language
    dm = active_profile().document_model
    arts = [n for n in doc.nodes if n.cls == dm.classes["articulo"]]
    sig = next((n.index for n in doc.nodes
                if n.kind == dm.kinds["paragraph"]
                and dm.boundary["signature"].match(n.text)),
               len(doc.nodes))
    spans = {}
    for a in arts:
        m = al.disp_head.match(a.text)
        if m is None:
            continue
        code = al.disp_prefix[m.group(1).lower()] + (
            al.disp_ordinal.get(m.group(2).lower(), m.group(2).lower())
            if m.group(2) else "u")
        if code in spans:  # second unnumbered provision of same type
            code = f"{code}.{sum(1 for k in spans if k.split('.')[0] == code)}"
        head = a.index
        nxt = min([n.index for n in arts if n.index > head] + [sig])
        nodes = [n for n in doc.nodes[head + 1:nxt]
                 if n.kind == dm.kinds["paragraph"]]
        style = ("num" if any(re.match(al.num_item, n.text)
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
        item_re = re.compile(
            active_profile().applicability_language
            .item_markers[style])
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
                has_core = bool(
                    temporal_effects(sent)
                    or classify_modality(sent)[1]
                    or active_profile().applicability_language
                    .conditional_opener.match(sent))
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
        al = active_profile().applicability_language
        m = al.rule_patterns["except_apartados"].search(c.text)
        if m:
            for (sec, item), head in by_item.items():
                if sec == c.section and item.isdigit() \
                        and int(m.group(1)) <= int(item) <= int(m.group(2)):
                    head.parent_key = c.clause_key
                    head.relation_to_parent = "EXCEPTION"
        if al.rule_patterns["especificidades"].search(c.text):
            for (sec, item), head in by_item.items():
                if sec == c.section and len(item) == 1 and item.isalpha() \
                        and head is not c:
                    head.parent_key = c.clause_key
                    head.relation_to_parent = "EXCEPTION"
        m = al.rule_patterns["sin_perjuicio"].search(c.text)
        if m:
            tgt = al.sin_perjuicio_targets.get(
                m.group(1).rsplit(" ", 1)[-1])
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
        if al.rule_patterns["opt_out_trigger"].search(c.text):
            opt = next((x for x in clauses
                        if x.section == c.section
                        and al.opt_out_phrase in x.text),
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
    al = active_profile().applicability_language
    for n in doc.nodes:
        if n.kind == active_profile().document_model.kinds["table"] \
                and n.rows and al.periodicity_header in n.rows[0]:
            out = {}
            for r in n.rows[1:]:
                per = r[2].strip().rstrip(".") if len(r) > 2 else ""
                out[r[0].strip()] = al.freq_map.get(per.lower(), per)
            return out, n.index
    return {}, None
