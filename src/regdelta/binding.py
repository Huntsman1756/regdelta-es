"""G1 structural binder — proof-or-abstain resolution (B1–B6).

Pure structure -> candidates -> decision. No persistence, no DB writes,
no network. ``history.reconstruct`` consumes ``BindingResult`` and
materializes a representation only when ``status == BOUND``.

Policy:

* every resolver enumerates candidates; it never returns "the first
  match" (B1);
* sub-locators are searched only inside the proven parent scope (B2);
* modifier-global locator lookups are never used for ``after`` content —
  it must come from operation-owned content or a modifier annex the
  operation explicitly points to (B3);
* a proven chain predecessor supplies ``before`` verbatim (B4);
* ambiguity degrades: N>1 candidates -> AMBIGUOUS, never first-wins (B5);
* roman/arabic locator renumbering is not normalized away — only the
  digit and declared linguistic-ordinal forms of the same number match;
  unproven alternates are NOT_PROVABLE, never silently equivalent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import annexmap
from .operations import _ORDINALS, _ordinal_num
from .profile import active_profile
from .sources.boe_diario import DiarioDoc

PARSER_NAME = "structural_binding"
PARSER_VERSION = "cov-v1"

BOUND = "BOUND"
NOT_FOUND = "NOT_FOUND"
AMBIGUOUS = "AMBIGUOUS"
NOT_PROVABLE = "NOT_PROVABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"
STATUSES = frozenset(
    {BOUND, NOT_FOUND, AMBIGUOUS, NOT_PROVABLE, NOT_APPLICABLE})


@dataclass(frozen=True)
class Candidate:
    instrument_boe_id: str
    snapshot_id: str | None
    representation_kind: str          # TEXT | TABLE | IMAGE
    structural_scope: str             # 'document', 'norma:4', 'anejo:2'…
    node_span: tuple[int, int] | None
    locator: dict                     # artifact_locator payload
    source: str                       # resolution rule label
    text: str | None = None           # serialized content for TEXT/TABLE
    representation_id: str | None = None   # set for CHAIN_PREDECESSOR

    def brief(self) -> dict:
        return {"instrument": self.instrument_boe_id,
                "kind": self.representation_kind,
                "scope": self.structural_scope,
                "node_span": list(self.node_span)
                if self.node_span else None,
                "representation_id": self.representation_id,
                "source": self.source}


@dataclass(frozen=True)
class BindingResult:
    status: str
    method: str
    locator_key: str
    candidate_count: int
    candidates: tuple[Candidate, ...] = ()
    chosen: Candidate | None = None
    reason: str | None = None
    predecessor_relation_id: str | None = None
    predecessor_representation_id: str | None = None

    @property
    def proof(self) -> dict:
        return {
            "status": self.status,
            "method": self.method,
            "locator_key": self.locator_key,
            "candidate_count": self.candidate_count,
            "candidates": [c.brief() for c in self.candidates],
            "chosen": self.chosen.brief() if self.chosen else None,
            "predecessor_relation_id": self.predecessor_relation_id,
            "predecessor_representation_id":
                self.predecessor_representation_id,
            "reason": self.reason}


def decide(candidates: list[Candidate], method: str,
           locator_key: str) -> BindingResult:
    """B1: 0 -> NOT_FOUND, 1 -> BOUND, >1 -> AMBIGUOUS. No fallback."""
    if not candidates:
        return BindingResult(NOT_FOUND, method, locator_key, 0,
                             reason="no_structural_candidate")
    if len(candidates) == 1:
        return BindingResult(BOUND, method, locator_key, 1,
                             tuple(candidates), candidates[0])
    return BindingResult(AMBIGUOUS, method, locator_key,
                         len(candidates), tuple(candidates),
                         reason="candidate_count>1")


def abstain(status: str, method: str, locator_key: str,
            reason: str) -> BindingResult:
    return BindingResult(status, method, locator_key, 0, reason=reason)


# ---------------------------------------------------------------------------
# candidate enumeration — headings
# ---------------------------------------------------------------------------

_ARTICULO_HEAD_RE = re.compile(
    r"^(?:\[[^\]]*\]\s*)?([A-Za-zÁÉÍÓÚáéíóúñü]+)\s+(\S+)",
    re.IGNORECASE)


def _ordinal_alt(ordinal: str) -> str:
    """Regex alternation matching an ordinal written as digit or
    linguistic word (feminine forms: normas/disposiciones)."""
    num = _ordinal_num(ordinal)
    if num is None:
        return re.escape(ordinal)
    words = {w for w, v in _ORDINALS.items() if v == num}
    return "(?:" + "|".join(
        re.escape(w) for w in sorted(words | {str(num)})) + ")"


def articulo_spans(doc: DiarioDoc, head_word: str,
                   ordinal: str) -> list[tuple[int, int]]:
    """Every 'Norma cuarta.' / 'Disposición transitoria primera.'-class
    heading matching head_word+ordinal, each spanning to the next
    articulo heading. Duplicates surface as separate candidates."""
    want = _ordinal_num(ordinal)
    hits: list[int] = []
    for n in doc.nodes:
        if n.cls != "articulo":
            continue
        m = _ARTICULO_HEAD_RE.match(n.text)
        if m and m.group(1).lower() == head_word \
                and _ordinal_num(m.group(2).rstrip(".")) == want:
            hits.append(n.index)
    bounds = sorted(h.index for h in doc.nodes if h.cls == "articulo")
    out = []
    for h in hits:
        nxt = next((b for b in bounds if b > h), len(doc.nodes))
        out.append((h, nxt))
    return out


def disp_spans(doc: DiarioDoc, tipo: str,
               ordinal: str) -> list[tuple[int, int]]:
    pat = re.compile(
        rf"^(?:\[[^\]]*\]\s*)?Disposici[oó]n\s+{tipo}\s+"
        rf"{_ordinal_alt(ordinal)}\b",
        re.IGNORECASE)
    hits = [n.index for n in doc.nodes
            if n.cls == "articulo" and pat.search(n.text)]
    bounds = sorted(n.index for n in doc.nodes if n.cls == "articulo")
    return [(h, next((b for b in bounds if b > h), len(doc.nodes)))
            for h in hits]


def _fichero_name(text: str) -> str:
    t = re.sub(r"\s*-\s*", "-", text.strip().casefold())
    return re.sub(r"\s*\(\s*\*+\s*\)\s*$", "", t)


_FICHERO_CONNECTORS = frozenset(
    {"a", "ante", "con", "de", "del", "e", "el", "en", "la", "las",
     "los", "para", "por", "sobre", "y"})


def _fichero_tokens(text: str) -> tuple[str, ...]:
    return tuple(t for t in re.split(r"[^\wáéíóúñü]+",
                                     _fichero_name(text))
                 if t and t not in _FICHERO_CONNECTORS)


def _fichero_eq(a: str, b: str) -> bool:
    return _fichero_name(a) == _fichero_name(b) \
        or _fichero_tokens(a) == _fichero_tokens(b)


def fichero_spans(doc: DiarioDoc, name: str) -> list[tuple[int, int]]:
    """Every data-file description block named ``name``: 'Fichero:
    <name>'; a centered bare title under a FICHERO label; or the
    capitulo_num 'Fichero' + capitulo_tit pair. Block closes at the
    next fichero heading, next articulo, or the signature."""
    head = re.compile(r"^fichero\s*:")
    boundary = re.compile(r"^(?:fichero\s*:|madrid\s*,)")
    nodes = doc.nodes
    starts: list[int] = []
    for k, n in enumerate(nodes):
        if n.kind != "p":
            continue
        txt = _fichero_name(n.text)
        m = head.match(txt)
        if m and _fichero_eq(txt[m.end():], name):
            starts.append(n.index)
        elif n.cls.startswith("centro") and _fichero_eq(txt, name):
            starts.append(n.index)
        elif n.cls == "capitulo_num" and txt == "fichero" \
                and k + 1 < len(nodes) \
                and nodes[k + 1].cls == "capitulo_tit" \
                and _fichero_eq(nodes[k + 1].text, name):
            starts.append(n.index)
    out = []
    for start in starts:
        end = len(nodes)
        for i in range(start + 1, len(nodes)):
            n = nodes[i]
            txt = _fichero_name(n.text)
            if n.cls == "articulo" or boundary.match(txt) \
                    or (txt == "fichero" and n.cls != "parrafo"):
                end = i
                break
        out.append((start, end))
    return out


def anejo_spans(doc: DiarioDoc, num: str) -> list[tuple[int, int]]:
    """Every 'ANEJO <n>' region in the document. Only the declared
    digit form matches — roman/arabic renumbering is never normalized
    away (B5/§14). Region ends at the next anejo heading, an articulo,
    or the signature."""
    head = re.compile(rf"^anejo\s+{re.escape(num)}\b", re.IGNORECASE)
    bound = re.compile(r"^anejo\s+\S|^anexos?\b|madrid\s*,",
                       re.IGNORECASE)
    hits = [i for i, n in enumerate(doc.nodes)
            if n.kind == "p" and head.match(n.text.strip())]
    out = []
    for h in hits:
        end = len(doc.nodes)
        for i in range(h + 1, len(doc.nodes)):
            n = doc.nodes[i]
            if n.cls == "articulo" or (
                    n.kind == "p" and bound.match(n.text.strip())):
                end = i
                break
        out.append((h, end))
    return out


# ---------------------------------------------------------------------------
# candidate enumeration — sub-locators inside a proven parent scope
# ---------------------------------------------------------------------------

_NUMERIC_MARKER_RE = re.compile(
    r"^(?:\d+\.|\d{1,3}(?:\.\d+)*\s+[A-ZÁÉÍÓÚÑ¿«(])")
_LETRA_MARKER_RE = re.compile(r"^[a-zA-Z]\)")
_SIBLING_MARKER_RE = re.compile(
    r"^(?:\d+\.|[a-zA-Z]\)|[ivxlcdmIVXLCDM]+\s*[.)]"
    r"|\d{1,3}(?:\.\d+)*\s+[A-ZÁÉÍÓÚÑ¿«(])")

# A candidate region ends at the next marker of its own level or any
# outer level — never at a child marker: 'a)' opens content *inside*
# apartado 1, it does not start a new apartado.
_LEVEL_BOUNDARY = {
    "apartado": _NUMERIC_MARKER_RE,
    "punto": _NUMERIC_MARKER_RE,
    "letra": re.compile(
        _NUMERIC_MARKER_RE.pattern + "|" + _LETRA_MARKER_RE.pattern),
}


def sub_region_candidates(doc: DiarioDoc, span: tuple[int, int],
                          pattern: re.Pattern,
                          boundary: re.Pattern = _SIBLING_MARKER_RE,
                          ) -> list[tuple[int, int]]:
    """Every node matching ``pattern`` inside ``span``; each candidate
    spans to the next same-or-outer-level marker or the parent span
    end. Matches outside the parent scope are never considered (B2)."""
    starts = [i for i in range(*span)
              if doc.nodes[i].kind == "p" and pattern.match(
                  doc.nodes[i].text)]
    out = []
    for start in starts:
        end = span[1]
        for i in range(start + 1, span[1]):
            if boundary.match(doc.nodes[i].text):
                end = i
                break
        out.append((start, end))
    return out


_VALUE_CONT_RE = re.compile(r"[\dA-ZÁÉÍÓÚÑ]")


def _locator_parts(locator_key: str) -> list[str]:
    """Split a locator key into 'kind:value' components.

    A bare segment that looks like a value fragment — a digit, an
    uppercase letter or a declared ordinal word — continues the
    previous component's dotted value (apartado '9.1',
    disp 'transitoria.primera', anejo '7.3'). Any other bare segment
    (anejo '5' + 'indice') keeps its own component and will fail
    sub-resolution as an unmodelled kind, exactly as before."""
    raw = locator_key.split(".")
    parts = [raw[0]]
    for p in raw[1:]:
        if ":" in p:
            parts.append(p)
        elif _VALUE_CONT_RE.match(p) or p in _ORDINALS:
            parts[-1] += "." + p
        else:
            parts.append(p)
    return parts


def _sub_pattern(kind: str, val: str) -> re.Pattern | None:
    v = re.escape(val)
    if kind in ("apartado", "punto"):
        if "." in val:
            # a compound code ('9.1', 'II.B.2') must not prefix-match a
            # deeper sibling code ('9.10', '9.1.2')
            return re.compile(rf"^{v}(?!\.\d|\w)(?:\s*\.|\s|$)")
        # official markers: '2.' / '2. ' dotted, or '2 Texto' undotted —
        # the undotted form requires capitalised text so that '2 de
        # julio' / '2 000' prose is never a structural marker
        return re.compile(
            rf"^{v}(?!\d)(?:\s*\.|\s+[A-ZÁÉÍÓÚÑ¿«(]|$)")
    if kind == "letra":
        return re.compile(rf"^{v}\s*\)")
    if kind == "nota":
        return re.compile(rf"^[«(]+\s*\(?{v}\)?", re.IGNORECASE)
    if kind == "numeral":
        return re.compile(rf"^{v}\s*[.)]", re.IGNORECASE)
    return None


def text_region_candidates(doc: DiarioDoc,
                           locator_key: str) -> list[tuple[int, int]]:
    """Hierarchical candidate spans for a textual subject (B2).

    Resolves the head, then each 'kind:val' part only inside the
    candidate parent scopes. Every surviving leaf span is a candidate —
    callers apply B1 to decide."""
    parts = _locator_parts(locator_key)
    head = parts[0]
    if head.startswith("norma:"):
        cands = articulo_spans(doc, "norma", head[6:])
    elif head.startswith("disp:"):
        tipo, _, ordinal = head[5:].partition(".")
        cands = disp_spans(doc, tipo, ordinal)
    elif head.startswith("fichero:"):
        cands = fichero_spans(doc, head[8:])
    elif head.startswith("anejo:"):
        cands = anejo_spans(doc, head[6:])
    else:
        return []
    for part in parts[1:]:
        kind, _, val = part.partition(":")
        pat = _sub_pattern(kind, val)
        if pat is None:
            return []
        bnd = _LEVEL_BOUNDARY.get(kind, _SIBLING_MARKER_RE)
        nxt: list[tuple[int, int]] = []
        for sp in cands:
            nxt.extend(sub_region_candidates(doc, sp, pat, bnd))
        cands = nxt
        if not cands:
            return []
    return cands


# ---------------------------------------------------------------------------
# candidate enumeration — estado/anejo code regions inside an annex
# ---------------------------------------------------------------------------

def annex_code_regions(doc: DiarioDoc) -> dict[str, list[tuple[int, int]]]:
    """Estado-code -> every node span inside the document's annex.

    Unlike the G0 ``structured_annex``, duplicate code headers are NOT
    collapsed: each region is a distinct candidate (B1)."""
    annex_start = None
    for n in doc.nodes:
        if n.cls == "anexo" or (
                n.kind == "p" and n.text.strip() == "ANEJO"):
            annex_start = n.index
            break
    if annex_start is None:
        return {}
    code_header = active_profile().annex_state.patterns[
        "annex_code_header"]
    starts: list[tuple[int, str]] = []
    for i in range(annex_start, len(doc.nodes)):
        n = doc.nodes[i]
        if n.kind == "p":
            m = code_header.match(n.text)
            if m:
                starts.append((i, annexmap._norm_code(
                    m.group(1), m.group(2))))
    regions: dict[str, list[tuple[int, int]]] = {}
    for pos, (i, code) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) \
            else len(doc.nodes)
        regions.setdefault(code, []).append((i, end))
    return regions
