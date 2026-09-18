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
from .operations import _disp_ord_alt, _ordinal_num, _positional_node
from .profile import active_profile
from .document import DiarioDoc

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

def articulo_spans(doc: DiarioDoc, head_word: str,
                   ordinal: str) -> list[tuple[int, int]]:
    """Every 'Norma cuarta.' / 'Disposición transitoria primera.'-class
    heading matching head_word+ordinal, each spanning to the next
    articulo heading. Duplicates surface as separate candidates."""
    p = active_profile()
    art = p.document_model.classes["articulo"]
    head_re = p.locator_grammar.articulo_head
    want = _ordinal_num(ordinal)
    hits: list[int] = []
    for n in doc.nodes:
        if n.cls != art:
            continue
        m = head_re.match(n.text)
        if m and m.group(1).lower() == head_word \
                and _ordinal_num(m.group(2).rstrip(".")) == want:
            hits.append(n.index)
    bounds = sorted(h.index for h in doc.nodes if h.cls == art)
    out = []
    for h in hits:
        nxt = next((b for b in bounds if b > h), len(doc.nodes))
        out.append((h, nxt))
    return out


def disp_spans(doc: DiarioDoc, tipo: str,
               ordinal: str) -> list[tuple[int, int]]:
    p = active_profile()
    dm = p.document_model
    art = dm.classes["articulo"]
    pat = re.compile(
        p.locator_grammar.disposicion_head.format(
            tipo=tipo, ord=_disp_ord_alt(ordinal)),
        re.IGNORECASE)
    centro = dm.class_prefixes.get("centro")
    # unnumbered class-keyed dispositions ('Norma transitoria') may
    # head in centro_* display classes in old-format sources; the
    # pattern itself already rejects heads that carry an ordinal
    def headish(n) -> bool:
        if n.cls == art:
            return True
        return bool(not ordinal and centro
                    and n.cls.startswith(centro))
    hits = [n.index for n in doc.nodes
            if n.kind == dm.kinds["paragraph"] and n.text
            and headish(n) and pat.search(n.text)]
    bounds = sorted(n.index for n in doc.nodes
                    if n.cls == art
                    or (not ordinal and centro
                        and n.cls.startswith(centro)))
    return [(h, next((b for b in bounds if b > h), len(doc.nodes)))
            for h in hits]


def _fichero_name(text: str) -> str:
    fg = active_profile().annex_state.fichero
    t = fg.dash_collapse.sub("-", text.strip().casefold())
    return fg.note_strip.sub("", t)


def _fichero_tokens(text: str) -> tuple[str, ...]:
    fg = active_profile().annex_state.fichero
    return tuple(t for t in re.split(fg.token_split,
                                     _fichero_name(text))
                 if t and t not in fg.connectors)


def _fichero_eq(a: str, b: str) -> bool:
    return _fichero_name(a) == _fichero_name(b) \
        or _fichero_tokens(a) == _fichero_tokens(b)


def fichero_spans(doc: DiarioDoc, name: str) -> list[tuple[int, int]]:
    """Every data-file description block named ``name``: 'Fichero:
    <name>'; a centered bare title under a FICHERO label; or the
    capitulo_num 'Fichero' + capitulo_tit pair. Block closes at the
    next fichero heading, next articulo, or the signature."""
    p = active_profile()
    dm = p.document_model
    fg = p.annex_state.fichero
    nodes = doc.nodes
    starts: list[int] = []
    for k, n in enumerate(nodes):
        if n.kind != dm.kinds["paragraph"]:
            continue
        txt = _fichero_name(n.text)
        m = fg.head.match(txt)
        if m and _fichero_eq(txt[m.end():], name):
            starts.append(n.index)
        elif n.cls.startswith(dm.class_prefixes["centro"]) \
                and _fichero_eq(txt, name):
            starts.append(n.index)
        elif n.cls == dm.classes["capitulo_num"] and txt == fg.word \
                and k + 1 < len(nodes) \
                and nodes[k + 1].cls == dm.classes["capitulo_tit"] \
                and _fichero_eq(nodes[k + 1].text, name):
            starts.append(n.index)
    out = []
    for start in starts:
        end = len(nodes)
        for i in range(start + 1, len(nodes)):
            n = nodes[i]
            txt = _fichero_name(n.text)
            if n.cls == dm.classes["articulo"] \
                    or fg.boundary.match(txt) \
                    or (txt == fg.word
                        and n.cls != dm.classes["parrafo"]):
                end = i
                break
        out.append((start, end))
    return out


def anejo_spans(doc: DiarioDoc, num: str) -> list[tuple[int, int]]:
    """Every 'ANEJO <n>' region in the document. Only the declared
    digit form matches — roman/arabic renumbering is never normalized
    away (B5/§14). Region ends at the next anejo heading, an articulo,
    or the signature."""
    p = active_profile()
    dm = p.document_model
    lg = p.locator_grammar
    head = re.compile(lg.anejo_head.format(num=re.escape(num)),
                      re.IGNORECASE)
    hits = [i for i, n in enumerate(doc.nodes)
            if n.kind == dm.kinds["paragraph"]
            and head.match(n.text.strip())]
    out = []
    for h in hits:
        end = len(doc.nodes)
        for i in range(h + 1, len(doc.nodes)):
            n = doc.nodes[i]
            if n.cls == dm.classes["articulo"] or (
                    n.kind == dm.kinds["paragraph"]
                    and lg.anejo_boundary.match(n.text.strip())):
                end = i
                break
        out.append((h, end))
    return out


# ---------------------------------------------------------------------------
# candidate enumeration — sub-locators inside a proven parent scope
# ---------------------------------------------------------------------------

# A candidate region ends at the next marker of its own level or any
# outer level — never at a child marker: 'a)' opens content *inside*
# apartado 1, it does not start a new apartado. Marker grammar and the
# kind->boundary map are profile data; the span policy is core.
def _level_boundary(kind: str, val: str = "") -> re.Pattern:
    lg = active_profile().locator_grammar
    spec = lg.level_boundary.get(kind)
    if spec is None:
        return lg.markers[lg.default_boundary]
    # a lettered level is bounded by lettered siblings, not by the
    # numeric children inside it — '1.' under 'B)' must not close the
    # apartado:B region
    if val.isalpha() and spec == ("numeric",) \
            and "uletra" in lg.markers:
        spec = ("uletra",)
    return re.compile(
        "|".join(lg.markers[m].pattern for m in spec))


def sub_region_candidates(doc: DiarioDoc, span: tuple[int, int],
                          pattern: re.Pattern,
                          boundary: re.Pattern | None = None,
                          ) -> list[tuple[int, int]]:
    """Every node matching ``pattern`` inside ``span``; each candidate
    spans to the next same-or-outer-level marker or the parent span
    end. Matches outside the parent scope are never considered (B2)."""
    if boundary is None:
        lg = active_profile().locator_grammar
        boundary = lg.markers[lg.default_boundary]
    starts = [i for i in range(*span)
              if doc.nodes[i].kind
              == active_profile().document_model.kinds["paragraph"]
              and pattern.match(doc.nodes[i].text)]
    out = []
    for start in starts:
        end = span[1]
        for i in range(start + 1, span[1]):
            if boundary.match(doc.nodes[i].text):
                end = i
                break
        out.append((start, end))
    return out


def _locator_parts(locator_key: str) -> list[str]:
    """Split a locator key into 'kind:value' components.

    A bare segment that looks like a value fragment — a digit, an
    uppercase letter or a declared ordinal word — continues the
    previous component's dotted value (apartado '9.1',
    disp 'transitoria.primera', anejo '7.3'). Any other bare segment
    (anejo '5' + 'indice') keeps its own component and will fail
    sub-resolution as an unmodelled kind, exactly as before."""
    lg = active_profile().locator_grammar
    raw = locator_key.split(".")
    parts = [raw[0]]
    for p in raw[1:]:
        if ":" in p:
            parts.append(p)
        elif lg.value_continuation.match(p) or p in lg.ordinals:
            parts[-1] += "." + p
        else:
            parts.append(p)
    return parts


def _sub_pattern(kind: str, val: str) -> re.Pattern | None:
    lg = active_profile().locator_grammar
    v = re.escape(val)
    if "." in val and kind in lg.sub_markers_compound:
        src, flags = lg.sub_markers_compound[kind]
        return re.compile(src.format(v=v), flags)
    ent = lg.sub_markers.get(kind)
    if ent is None:
        return None
    src, flags = ent
    return re.compile(src.format(v=v), flags)


def text_region_candidates(doc: DiarioDoc,
                           locator_key: str) -> list[tuple[int, int]]:
    """Hierarchical candidate spans for a textual subject (B2).

    Resolves the head, then each 'kind:val' part only inside the
    candidate parent scopes. Every surviving leaf span is a candidate —
    callers apply B1 to decide."""
    parts = _locator_parts(locator_key)
    head = parts[0]
    if head.startswith("norma:"):
        cands = articulo_spans(
            doc, active_profile().locator_grammar.head_forms[
                "norma"][0], head[6:])
    elif head.startswith("disp:"):
        tipo, _, ordinal = head[5:].partition(".")
        cands = disp_spans(doc, tipo, ordinal)
    elif head.startswith("fichero:"):
        cands = fichero_spans(doc, head[8:])
    elif head.startswith("anejo:"):
        cands = anejo_spans(doc, head[6:])
    else:
        return []
    lg = active_profile().locator_grammar
    for part in parts[1:]:
        kind, _, val = part.partition(":")
        if kind in lg.positional_kinds:
            # WS-C: the Nth positional node inside each candidate
            # parent span — position IS the declared identity
            n_val = _ordinal_num(val)
            if n_val is None or n_val < 1:
                return []
            nxt = []
            for sp in cands:
                pos = [i for i in range(*sp)
                       if _positional_node(doc.nodes[i], kind)]
                if len(pos) >= n_val:
                    nxt.append((pos[n_val - 1], pos[n_val - 1] + 1))
            cands = nxt
            if not cands:
                return []
            continue
        pat = _sub_pattern(kind, val)
        if pat is None:
            return []
        bnd = _level_boundary(kind, val)
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
    p = active_profile()
    dm = p.document_model
    annex_start = None
    for n in doc.nodes:
        if n.cls == dm.classes["anexo"] or (
                n.kind == dm.kinds["paragraph"]
                and n.text.strip() == dm.annex_literal):
            annex_start = n.index
            break
    if annex_start is None:
        return {}
    code_header = p.annex_state.patterns["annex_code_header"]
    starts: list[tuple[int, str]] = []
    for i in range(annex_start, len(doc.nodes)):
        n = doc.nodes[i]
        if n.kind == dm.kinds["paragraph"]:
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

# Frozen-evaluator compatibility (PORT-2R): _ORDINALS resolves to the
# active profile's locator grammar.
def __getattr__(name: str):
    if name == "_ORDINALS":
        return active_profile().locator_grammar.ordinals
    raise AttributeError(name)
