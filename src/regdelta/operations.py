"""Deterministic parser for amendment clauses in BOE modifier instruments.

Pure structure -> structure: consumes the document-order node list produced
by ``sources.boe_diario`` and yields typed operations. No legal
interpretation is attempted: an operation is a clause containing a Spanish
amendment verb (modifica/sustituye/añade/suprime/elimina/introduce/
incorpora/denomina...) or a "En la norma/anejo/estado ..." locator that
opens a context for nested clauses.

Scope rules proven necessary by the G0-C corpus:

* only ``articulo``-headed sections whose heading names the target
  instrument ("Modificación de la Circular 4/2017...") produce operations;
  sections targeting other instruments are counted, not materialized;
* clause markers nest: lettered items (``a)``) open contexts that roman
  items (``i.``, ``ii)``) inherit; numbered items (``3.``) are the
  top-level markers of correction documents;
* markers ``i)``, ``v)``, ``x)``... are lexically ambiguous between alpha
  and roman sequences; they resolve by position (child of an open
  container vs. continuation of the top-level alpha sequence);
* non-locator paragraphs may still set context (e.g. "Se introducen los
  siguientes cambios en el anejo 9 ... :" before lettered point ops);
* amendment verbs are the op filter: marker paragraphs inside quoted
  replacement content (numbered rows, lettered lists of new articles) lack
  them and are correctly left inside the content span.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .profile import active_profile
from .document import DiarioDoc, Node

PARSER_NAME = "boe_operations"
PARSER_VERSION = "v4"

# operation-owned content link taxonomy (G1 §17–18): an ``after``
# representation may only be produced from content the operation is
# proven to own.
CONTENT_LINK_METHODS = (
    "INLINE_QUOTED_CONTENT",       # «quoted» content fused in locator node
    "EXPLICIT_FOLLOWING_CONTENT",  # pointer + attached following block
    "EXPLICIT_ANNEX_REFERENCE",    # 'que figura en el anejo de esta circular'
    "DECLARED_LITERAL_ONLY",       # donde dice / debe decir literals only
    "NO_PROVEN_CONTENT",
)

# ---------------------------------------------------------------------------
# markers / verbs / patterns
#
# Locator-declaration, marker and ordinal grammar lives in the active
# profile's locator_grammar facet; normalization parameters and the
# «» convention in text_normalization; fichero vocabulary in
# annex_state.fichero (PORT-2 F1–F3). Enumeration, tokenization and
# adjudication below are core policy.
# ---------------------------------------------------------------------------

def _has_operative_verb(head: str) -> bool:
    """An amendment verb in operative position.

    Passive-fate verbs ('queda redactado', 'pasa a ser', 'donde dice')
    are operative even inside a relative clause — 'La letra a) del
    apartado 1, que queda redactada en los siguientes términos' is a
    canonical amendment clause. Active 'se <verb>' matches are
    operative only in main position: subordinate occurrences
    ('que se introduce en la Circular X', 'criterios ... que se
    modifican mediante ...') describe or cross-reference the subject,
    they do not amend it.
    """
    og = active_profile().operative_grammar
    if og.amend_verb_passive.search(head):
        return True
    for m in og.amend_verb_active.finditer(head):
        seg = head[:m.start()]
        if not og.subordinator_tail.search(seg):
            return True
    return False


def _target_refs(text: str) -> list[tuple[int, int]]:
    """All 'Circular N/AAAA' references in text, incl. the
    'Circular del Banco de España N/AAAA' word order."""
    ir = active_profile().identity_reference
    return [(int(a), int(b)) for a, b in ir.target_ref.findall(text)]


# "...que consta en el anejo de la Circular del Banco de España
# 4/2008, de actualización de la Circular 2/2005" — the ref governed by
# "anejo de la Circular" names the instrument whose annex holds the
# fichero; a second ref nested in its description is not an owner.
def _clause_targets(text: str) -> list[tuple[int, int]]:
    """Circular refs that attribute a clause to another instrument.

    An owner construction ('...que consta/figura en el anejo de la
    Circular N/AAAA') wins over every other mention; without it, only a
    single unambiguous ref attributes the clause — multiple competing
    refs are descriptive, not attributive.
    """
    owners = [(int(m.group(1)), int(m.group(2)))
              for m in active_profile().identity_reference
              .fichero_owner.finditer(text)]
    if owners:
        return owners
    refs = _target_refs(
        active_profile().text_normalization.quoted_span.sub("", text))
    uniq = list(dict.fromkeys(refs))
    return uniq if len(uniq) == 1 else []

def _letters(raw: str) -> list[str]:
    # case-sensitive on purpose: 'letra B)' is an ordinal-style
    # reference the corpus never uses as a locator declaration
    item = active_profile().locator_grammar.letra_item
    return [m.group(0).lstrip("(").rstrip(")")
            for m in item.finditer(raw)]


def _numlist(raw: str) -> list[tuple[str, ...]]:
    """Tokenize a numeric enumeration preserving ranges and
    hierarchical values: a 'lo a hi' pair stays a 2-tuple; each other
    element is a singleton, dotted identifiers included."""
    lg = active_profile().locator_grammar
    out: list[tuple[str, ...]] = []
    for tok in re.split(lg.numlist_split, raw):
        tok = re.sub(r"\s*\.\s*", ".", tok.strip())
        m = lg.numlist_range.fullmatch(tok)
        if m:
            out.append((m.group(1), m.group(2)))
        elif re.fullmatch(lg.numlist_atom, tok, re.IGNORECASE):
            out.append((tok,))
    return out

def _norm(s: str) -> str:
    tn = active_profile().text_normalization
    s = unicodedata.normalize(tn.form, s)
    if tn.strip_combining:
        s = "".join(c for c in s if not unicodedata.combining(c))
    if tn.collapse_ws:
        s = re.sub(r"\s+", " ", s)
    return getattr(s, tn.fold)().strip()


def _locator_mentions(key: str) -> tuple[list[str], list[str]]:
    """(head mention alternatives, deep mention alternatives) for an
    operative-clause search — the deep list carries one normalized
    'kind val' pair plus the bare value for each sub-locator part, and
    falls back to the head alternatives when the key has none."""
    parts = key.split(".")
    kind, _, body = parts[0].partition(":")
    tok = _norm(body)
    lg = active_profile().locator_grammar
    heads = []
    for h in lg.head_forms.get(kind, (kind,)):
        heads.append(f"{h} {tok}")
        if kind == "disp" and len(parts) > 1:
            heads.append(f"{h} {tok} {_norm(parts[1])}")
    if kind in ("norma", "anejo", "anexo", "articulo"):
        word = lg.ordinal_words.get(tok)
        for h in lg.head_forms.get(kind, (kind,)):
            if word:
                heads.append(f"{h} {word}")
            if tok in lg.roman:
                heads.append(f"{h} {lg.roman[tok]}")
    deep = []
    for p in parts[1:]:
        k, _, v = p.partition(":")
        deep.append(f"{k} {_norm(v)}")
        deep.append(_norm(v))
    if not deep:
        deep = list(heads)
    return heads, deep


def _clause_op_kind(text: str) -> str | None:
    """Kind of the earliest-position amendment verb in the clause —
    the same derivation the frozen evaluator applies, under this
    parser's own verb vocabulary."""
    masked = active_profile().text_normalization.quoted_span.sub(
        " ", text)
    best: tuple[int, str] | None = None
    for kind, rx in active_profile().operative_grammar.op_kinds:
        m = rx.search(masked)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), kind)
    return best[1] if best else None


def subject_operation_kind(clause_text: str, locator_key: str,
                           default: str) -> str:
    """Per-subject operation kind inside a mixed-verb clause — the
    nearest-verb derivation the frozen evaluator re-applies.

    Index/cuadro clauses combine verbs: one state renamed while its
    neighbours are eliminated in the same sentence. A subject adopts
    the verb nearest preceding its deepest mention; a following verb
    is used only when nothing precedes the mention.
    """
    _, deep = _locator_mentions(locator_key)
    masked = active_profile().text_normalization.quoted_span.sub(
        lambda mm: " " * len(mm.group(0)), clause_text)
    # lowercase keeps positions aligned with the raw clause while
    # _OP_KINDS patterns stay accent-aware (ñ, á) — _norm would both
    # shift offsets and break 'añade'
    low = masked.lower()
    mpos = None
    for d in deep:
        if not d:
            continue
        rx = (rf"(?<!\w){re.escape(d)}(?!\w)" if len(d) >= 3
              else rf"(?<!\w){re.escape(d)}(?=[).])")
        for m in re.finditer(rx, low):
            mpos = m.start() if mpos is None \
                else max(mpos, m.start())
    if mpos is None:
        return _clause_op_kind(clause_text) or default
    verbs: list[tuple[int, str]] = []
    for kind, rx in active_profile().operative_grammar.op_kinds:
        verbs.extend((m.start(), kind) for m in rx.finditer(low))
    verbs.sort()
    prev = [v for v in verbs if v[0] <= mpos]
    if prev:
        return prev[-1][1]
    nxt = [v for v in verbs if v[0] > mpos]
    if nxt:
        return nxt[0][1]
    return _clause_op_kind(clause_text) or default


# ---------------------------------------------------------------------------
# data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubjectRef:
    """A subject mentioned by an operation, as a structured locator key."""

    locator_key: str            # 'estado:FI 105', 'norma:33', 'anejo:9.punto:46'
    label: str                  # human label ('estado FI 105')
    kind: str                   # NORMA|ESTADO|ANEJO|PUNTO|APARTADO|INDICE|DISPOSICION|NOTA
    page_ref: int | None = None # explicit BOE page (corrections)
    # per-component declaration provenance (G2.1 §20-21): tuples of
    # (kind, value, provenance, node_index|None, scope_name|None) with
    # provenance in EXPLICIT_CLAUSE|INHERITED|INHERITED_PARENT
    proof_components: tuple = ()


@dataclass
class Operation:
    node_index: int             # locator node index in doc.nodes
    marker: str                 # 'a)', 'i.', '3.', '' for preamble ops
    clause_text: str            # normalized locator clause
    operation_kind: str         # SUBSTITUTE|MODIFY|ADD|DELETE|CORRECT
    subjects: list[SubjectRef]
    content_span: tuple[int, int]  # (start,end) exclusive, nodes after locator
    is_container: bool
    annex_ref: bool             # 'por el que figura en el anejo de esta circular'
    literals: list[tuple[str, str]]  # declared (old,new) literal pairs
    context: dict[str, str]     # inherited context used for resolution
    section_index: int          # articulo index opening the section
    inline_content: str = ""    # quoted content fused into the locator node
    targets: list[tuple[int, int]] = field(default_factory=list)
    # circular refs the clause itself names (unmarked ops inside
    # sections whose heading names no circular)
    content_link_method: str = "NO_PROVEN_CONTENT"
    content_link_evidence: dict = field(default_factory=dict)
    # G2.1 ownership evidence (populated by parse_all_operations):
    prefix: str = ""            # unmarked-op context prefix before ':'
    section_heading: str = ""   # articulo heading text
    section_targets: list[tuple[int, int]] = field(default_factory=list)
    # per-context-key provenance: kind -> {"value","node_index","scope"}
    context_scope: dict = field(default_factory=dict)


@dataclass
class Section:
    heading: str
    node_start: int
    node_end: int               # exclusive
    targets: list[tuple[int, int]]  # (num, year) circular refs in heading


@dataclass
class OpsResult:
    operations: list[Operation]
    sections: list[Section]
    out_of_target_ops: int      # marker+verb paragraphs outside target sections


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ordinal_num(word: str) -> int | None:
    w = word.lower()
    if w.isdigit():
        return int(w)
    return active_profile().locator_grammar.ordinals.get(w)


def _marker_parts(text: str) -> tuple[str, str] | None:
    lg = active_profile().locator_grammar
    m = lg.clause_marker.match(text)
    if not m:
        return None
    tok = m.group("m").replace(" ", "")
    body = tok.rstrip(").")
    if body.isdigit():
        return "num", body
    return "amb" if body.lower() in lg.marker_amb_values \
        else "alpha", body


def _is_locator(node: Node) -> bool:
    p = active_profile()
    dm, lg, tn = p.document_model, p.locator_grammar, \
        p.text_normalization
    if node.kind not in (dm.kinds["paragraph"],
                         dm.kinds["blockquote"]) \
            or node.cls not in dm.locator_classes:
        return False
    # a blockquote may fuse the locator clause and its quoted replacement
    # content into a single node; only the span before « is locator prose
    text = node.text.split(tn.quote_open, 1)[0] \
        if node.kind == dm.kinds["blockquote"] else node.text
    m = lg.clause_marker.match(text)
    if not m:
        return False
    rest = text[m.end():].lstrip()
    head = text[:260]
    if _has_operative_verb(head):
        return True
    # subject-scoped clauses without an operative verb are containers
    # announcing nested operations ("En la norma 60, sobre «...»:"); a
    # non-container 'En el ...' clause without an operative verb is
    # referential prose, not an amendment ("En el estado T.10 ... se
    # deberá enviar").
    if text.rstrip().endswith(":") and (
            p.operative_grammar.en_subject.search(rest)
            or p.operative_grammar.bare_subject.match(rest)):
        return True
    return False


def _is_container(text: str) -> bool:
    """A container opens a nested context; it carries no content of its own.

    Only true for clauses ending ':' that either have no amendment verb
    ("En el estado FI 106-2.1:") or announce nested modifications
    ("se realizan las siguientes modificaciones:"). A clause like
    "se sustituyen las líneas:" has a verb and its own following content.
    """
    t = text.rstrip()
    og = active_profile().operative_grammar
    if not t.endswith(":") or og.content_pointer.search(t):
        return False
    if og.container.search(t):
        return True
    if not (og.amend_verb_active.search(t)
            or og.amend_verb_passive.search(t)):
        return True
    # "se modifican:" with no object announces nested clauses
    return bool(og.container_close.search(t))


def _op_kind(text: str) -> str:
    for kind, rx in active_profile().operative_grammar.op_kinds:
        if rx.search(text):
            return kind
    return "MODIFY"


def _norm_state_code(prefix: str, num: str) -> str:
    num = re.sub(r"\s+", "", num).rstrip(".")
    # "FI 150.9" is the same state written with a dot separator
    if "." in num and "-" not in num:
        num = num.replace(".", "-", 1)
    return f"{prefix} {num}"


def _extract_mentions(text: str) -> dict[str, object]:
    """Pull subject mentions out of a clause.

    Quoted «...» spans are stripped first: quoted text is replacement
    content, not locator — except estado codes quoted right after
    "estados", which are the entities being added ("los nuevos estados
    «FI 151 ...»").
    """
    # state-code, locator-declaration and quoting grammar live in the
    # active profile (PORT-2 C-016/C-019/C-045); the mention/anchor
    # policy below is core
    prof = active_profile()
    pats = prof.annex_state.patterns
    lg = prof.locator_grammar
    tn = prof.text_normalization
    quoted_states: list[str] = []
    for m in pats["quoted_state"].finditer(text):
        for qm in pats["quoted_code"].finditer(m.group(1)):
            quoted_states.append(
                _norm_state_code(qm.group(1), qm.group(2)))

    stripped = tn.quoted_span.sub(tn.quote_open + tn.quote_close, text)

    # positional anchors are excluded by span range, not by code value
    # ("por el formato de estado FI 142-1.1" must not kill the subject
    # mention of the same code earlier in the clause)
    anchor_spans = [m.span(1)
                    for m in pats["state_anchor_span"].finditer(stripped)]

    out: dict[str, object] = {}
    for key, rx in lg.declarations.items():
        if key in lg.enum_kinds:
            vals: list = []
            for m in rx.finditer(stripped):
                vals.extend(_numlist(m.group(1)))
        else:
            vals = [tuple(g for g in m.groups())
                    for m in rx.finditer(stripped)]
        # a node may serialize the same sentence twice (blockquote
        # label+body artifact): each distinct mention counts once
        vals = list(dict.fromkeys(vals))
        if vals:
            out[key] = vals
    letras: list[str] = []
    for m in lg.letra_list.finditer(stripped):
        for lt in _letters(m.group(1)):
            if lt not in letras:
                letras.append(lt)
    if letras:
        out["letra"] = letras
    estados: list[str] = []
    for m in pats["state_code"].finditer(stripped):
        code = _norm_state_code(m.group(1), m.group(2))
        if any(a <= m.start() < b for a, b in anchor_spans):
            continue
        if code not in estados:
            estados.append(code)
    for pm in pats["paren_state"].finditer(stripped):
        for cm in pats["paren_code"].finditer(pm.group(1)):
            pos = pm.start(1) + cm.start()
            if any(a <= pos < b for a, b in anchor_spans):
                continue
            code = _norm_state_code(cm.group(1), cm.group(2))
            if code not in estados:
                estados.append(code)
    for code in quoted_states:
        if code not in estados:
            estados.append(code)
    if estados:
        out["estado"] = estados
    ficheros = [re.sub(r"\s+", " ", m.group(1)).strip()
                for m in prof.annex_state.fichero.subject.finditer(text)]
    if ficheros:
        out["fichero"] = ficheros
    return out


def _compose_keys(mentions: dict[str, object],
                  ctx: dict[str, str], scope: dict | None = None,
                  node_index: int | None = None) -> list[SubjectRef]:
    """Compose locator keys from clause mentions + inherited context.

    Root-family exclusivity (G2.1 §22): when the clause itself declares
    a root (norma/anejo/disposición), inherited roots of the other
    families are suppressed for this composition. ``scope`` carries
    per-context-key provenance (kind -> {"node_index","scope"}) so each
    emitted SubjectRef records where every key component was declared.
    """
    subs: list[SubjectRef] = []

    def prov(kind: str) -> tuple:
        if mentions.get(kind):
            return ("EXPLICIT_CLAUSE", node_index, "CLAUSE")
        e = (scope or {}).get(kind) or {}
        return ("INHERITED", e.get("node_index"), e.get("scope"))

    def comp(kind: str, value) -> tuple:
        return (kind, str(value)) + prov(kind)

    # root families the clause itself declares suppress the inherited
    # roots of other families
    clause_roots = {r for r in
                    active_profile().operative_grammar.root_families
                    if mentions.get(r)}

    estados = mentions.get("estado") or []
    for code in estados:
        subs.append(SubjectRef(f"estado:{code}", f"estado {code}",
                               "ESTADO",
                               proof_components=(
                                   comp("estado", code),)))
    if estados:
        return subs

    ficheros = mentions.get("fichero") or []
    for name in ficheros:
        subs.append(SubjectRef(f"fichero:{name}", f"fichero {name}",
                               "FICHERO",
                               proof_components=(
                                   comp("fichero", name),)))
    if ficheros:
        return subs

    def first(key):
        v = mentions.get(key)
        return v[0] if v else None

    def _values(key: str) -> list[str]:
        """Every declared value of a mention kind, expanding 'lo a hi'
        range tuples and keeping hierarchical identifiers whole."""
        out: list[str] = []
        for t in mentions.get(key) or []:
            t = tuple(str(x) for x in t)
            if len(t) > 1 and t[0].isdigit() and t[1].isdigit():
                out.extend(str(v)
                           for v in range(int(t[0]), int(t[1]) + 1))
            else:
                out.append(re.sub(r"\s+", "", t[0]))
        return out

    norma_vals = [n for n in (_ordinal_num(v) for v in _values("norma"))
                  if n is not None]
    if not norma_vals and "norma" in ctx \
            and not (clause_roots - {"norma"}):
        norma_vals = [int(ctx["norma"])]

    anejo_vals = _values("anejo")
    if not anejo_vals and not (clause_roots - {"anejo"}):
        if ctx.get("anejo"):
            anejo_vals = [ctx["anejo"]]

    disp_mentioned = mentions.get("disposicion") or []
    disp_vals = [str(t[0]).lower() + "." + str(t[1]).lower()
                 for t in disp_mentioned]
    if not disp_vals and ctx.get("disposicion") \
            and not (clause_roots - {"disposicion"}):
        disp_vals = [ctx["disposicion"]]
    # a sub-locator under a disposición composes with it
    # ('apartado 1 de la disposición transitoria primera'); the bare
    # disposición key is emitted only when the clause itself names it
    if disp_mentioned and not any(
            mentions.get(k)
            for k in ("apartado", "punto", "letra", "numeral", "nota")):
        for d in disp_vals:
            subs.append(SubjectRef(
                f"disp:{d}", "disposición " + d.replace(".", " "),
                "DISPOSICION",
                proof_components=(comp("disposicion", d),)))

    # root-family precedence for sub-locators: disposición, then
    # norma, then anejo
    if disp_vals:
        root_kind, root_vals = "disposicion", disp_vals
    elif norma_vals:
        root_kind = "norma"
        root_vals = [str(n) for n in norma_vals]
    elif anejo_vals:
        root_kind, root_vals = "anejo", anejo_vals
    else:
        root_kind, root_vals = None, []

    def root_comp(root_v: str) -> tuple:
        if root_kind in ("norma", "anejo"):
            return (comp(root_kind, root_v),)
        return ()

    indice = mentions.get("indice")
    if indice is not None:
        for a in anejo_vals:
            subs.append(SubjectRef(
                f"anejo:{a}.indice", f"índice del anejo {a}",
                "INDICE",
                proof_components=(comp("anejo", a),
                                  ("indice", "indice", "EXPLICIT_CLAUSE",
                                   node_index, "CLAUSE"))))

    punto_vals = _values("punto")
    apartado_vals = _values("apartado")
    letras = list(mentions.get("letra") or [])
    numeral = first("numeral")
    nota = first("nota")

    def tail_comps(letra_v) -> tuple:
        out = []
        if letra_v is not None:
            out.append(comp("letra", letra_v))
        if numeral is not None:
            out.append(comp("numeral", str(numeral[0]).lower()))
        if nota is not None:
            out.append(comp("nota", nota[0]))
        return tuple(out)

    if apartado_vals:
        for rv in (root_vals or [None]):
            for n in apartado_vals:
                as_punto = root_kind == "anejo" and n.isdigit()
                if root_kind == "disposicion":
                    base = f"disp:{rv}.apartado:{n}"
                    comps = [comp("disposicion", rv)]
                elif root_kind == "norma":
                    base = f"norma:{rv}.apartado:{n}"
                    comps = [comp("norma", rv)]
                elif as_punto:
                    # numbered units inside an anejo are its "puntos"
                    # even when the clause calls them "apartado"
                    base = f"anejo:{rv}.punto:{n}"
                    comps = [comp("anejo", rv),
                             ("punto", str(n)) + prov("apartado")]
                elif root_kind == "anejo":
                    base = f"anejo:{rv}.apartado:{n}"
                    comps = [comp("anejo", rv)]
                else:
                    base = f"apartado:{n}"
                    comps = []
                if not as_punto:
                    comps.append(comp("apartado", n))
                for lv in (letras or [None]):
                    k = base + (f".letra:{lv}" if lv is not None else "")
                    if numeral is not None:
                        k += f".numeral:{numeral[0].lower()}"
                    if nota is not None:
                        k += f".nota:{nota[0]}"
                    subs.append(SubjectRef(
                        k, k.replace(":", " "), "APARTADO",
                        proof_components=tuple(comps)
                        + tail_comps(lv)))
    elif punto_vals:
        for rv in (root_vals or [None]):
            for n in punto_vals:
                if root_kind == "disposicion":
                    key = f"disp:{rv}.punto:{n}"
                elif root_kind == "norma":
                    key = f"norma:{rv}.punto:{n}"
                elif root_kind == "anejo":
                    key = f"anejo:{rv}.punto:{n}"
                else:
                    key = f"punto:{n}"
                comps = list(root_comp(rv)) if rv is not None else []
                comps.append(("punto", str(n)) + prov("punto"))
                for lv in (letras or [None]):
                    k = key + (f".letra:{lv}" if lv is not None else "")
                    subs.append(SubjectRef(
                        k, k.replace(":", " "), "PUNTO",
                        proof_components=tuple(comps)
                        + tail_comps(lv)))
    elif letras and norma_vals:
        for nv in norma_vals:
            for lv in letras:
                subs.append(SubjectRef(
                    f"norma:{nv}.letra:{lv}",
                    f"norma {nv} letra {lv}", "APARTADO",
                    proof_components=(comp("norma", nv),)
                    + tail_comps(lv)))
    elif numeral is not None and norma_vals:
        for nv in norma_vals:
            subs.append(SubjectRef(
                f"norma:{nv}.numeral:{numeral[0].lower()}",
                f"norma {nv} numeral {numeral[0]}", "APARTADO",
                proof_components=(comp("norma", nv),)
                + tail_comps(None)))
    elif nota is not None and norma_vals:
        for nv in norma_vals:
            subs.append(SubjectRef(
                f"norma:{nv}.nota:{nota[0]}",
                f"norma {nv} nota {nota[0]}", "NOTA",
                proof_components=(comp("norma", nv),)
                + tail_comps(None)))

    if not subs:
        if norma_vals and anejo_vals:
            for a in anejo_vals:
                subs.append(SubjectRef(
                    f"anejo:{a}", f"anejo {a}", "ANEJO",
                    proof_components=(comp("anejo", a),)))
        elif anejo_vals:
            for a in anejo_vals:
                subs.append(SubjectRef(
                    f"anejo:{a}", f"anejo {a}", "ANEJO",
                    proof_components=(comp("anejo", a),)))
        elif norma_vals:
            for nv in norma_vals:
                subs.append(SubjectRef(
                    f"norma:{nv}", f"norma {nv}", "NORMA",
                    proof_components=(comp("norma", nv),)))
        elif disp_vals:
            for d in disp_vals:
                subs.append(SubjectRef(
                    f"disp:{d}", "disp " + d, "DISPOSICION",
                    proof_components=(comp("disposicion", d),)))
        elif ctx.get("subject"):
            key = ctx["subject"]
            e = (scope or {}).get("subject") or {}
            subs.append(SubjectRef(
                key, key.replace(":", " "), key.split(":", 1)[0].upper(),
                proof_components=(
                    ("subject", key, "INHERITED_PARENT",
                     e.get("node_index"), e.get("scope")),)))

    # one locator key = one subject, however many mentions composed it
    seen: set[str] = set()
    subs = [s for s in subs
            if s.locator_key not in seen and not seen.add(s.locator_key)]
    return subs


# ---------------------------------------------------------------------------
# CORE-GAP WS-A — redesignation (old locator -> new locator) parsing
#
# A redesignation clause carries TWO locator roles: the old address is
# the subject (left of 'pasa(n) a ser/denominarse'), the right side is
# the destination. Composing subjects from the full clause merges both
# roles — the R2 false locators. The verb boundary and denomination
# grammar are profile facets; segmentation, pairing, classification and
# refusal are core. Classification ports the adjudicated EXP-B1
# mechanism (verdict PORT): a pair is an edge only when the destination
# declares a DIFFERENT code for the subject's leaf kind
# (CODE_REDESIGNATION); same-code denominations are relabels, not
# moves; unparseable destinations are refused, never guessed.
# ---------------------------------------------------------------------------

_REDESIG_KIND_ALIAS = {"disposicion": "disp"}

# leading connectors/articles that may precede a destination designator
_DEST_LEAD_RE = re.compile(
    r"^\s*(?:(?:el|la|los|las|lo|un|una|unos|unas|como|por|del|de|"
    r"al|en|con|su|sus|mismo|misma|mismos|mismas)\s+)*")


def _mask_quoted(text: str) -> str:
    """Quoted spans blanked to spaces, positions preserved."""
    tn = active_profile().text_normalization
    return tn.quoted_span.sub(
        lambda m: " " * (m.end() - m.start()), text)


def _redesig_matches(text: str) -> list:
    """All redesig-verb matches on quote-masked text (a verb inside a
    «...» denomination is content, never an operative verb)."""
    og = active_profile().operative_grammar
    if og.redesig_verb is None:
        return []
    return list(og.redesig_verb.finditer(_mask_quoted(text)))


def _segment_end(text: str, start: int) -> int:
    """End of the operative segment beginning at ``start``: the first
    unquoted ';', '.', content pointer, coordinated subject phrase
    (', y la letra o) pasa a ser…') or ANY operative-verb match —
    whichever comes first. A coordinated operation in the same node
    ('…, y se suprimen los estados…') bounds the destination zone, so
    later operations are never swallowed."""
    og = active_profile().operative_grammar
    masked = _mask_quoted(text)
    end = len(text)
    m = re.search(r"[;.]", masked[start:])
    if m:
        end = start + m.start()
    cp = og.content_pointer.search(masked, start)
    if cp:
        end = min(end, cp.start())
    for _kind, rx in og.op_kinds:
        vm = rx.search(masked, start)
        if vm:
            end = min(end, vm.start())
    # a coordinated subject phrase opens the next operation's left
    # side — '…«X», y la letra o) pasa a ser…' / '…, y la nota (4) y
    # se añaden…' (EXP-B1's next-operation boundary, generalized over
    # the profile's designator vocabulary)
    heads = "|".join(sorted(
        (re.escape(h) for h in _dest_designators() if len(h) > 1),
        key=len, reverse=True))
    if heads:
        cm = re.search(
            r",?\s*(?:y|e)\s+(?:el|la|los|las|otro|otra|otros|otras)?"
            r"\s*(?:" + heads + r")\b",
            masked[start:], re.IGNORECASE)
        if cm:
            end = min(end, start + cm.start())
    return end


def _norm_dest(kind: str | None, v) -> str | None:
    """Normalize a destination value with the same rules _compose_keys
    applies to subject components (ordinals, whitespace, case)."""
    if isinstance(v, tuple):
        if kind == "disposicion":
            return ".".join(str(x).lower() for x in v[:2])
        v = v[0]
    v = str(v)
    if kind == "norma":
        n = _ordinal_num(v)
        return None if n is None else str(n)
    if kind == "anejo":
        return re.sub(r"\s+", "", v)
    if kind == "letra":
        return v.lower()
    return v


def _dest_designators() -> set[str]:
    """All surface forms that may head a structural destination —
    the profile's redesig_designators vocabulary plus its locator
    head forms (singular and plural)."""
    lg = active_profile().locator_grammar
    heads: set[str] = set(
        h.lower().rstrip(".ªº")
        for h in active_profile().operative_grammar.redesig_designators)
    for forms in lg.head_forms.values():
        for h in forms:
            h = h.lower().rstrip(".ªº")
            heads.add(h)
            heads.add(h + "s")
            heads.add(h + "es")
    return heads


def _parse_dests(zone: str):
    """Ordered destination slots in one post-verb segment.

    Returns None when the segment does not open with a structural
    designator ('pasa a ser aplicable a las normas 3 y 4' is scope
    prose, not a redesignation — its mentions stay ordinary subjects).
    Otherwise a list of ``(kind, value)`` slots — ``kind=None`` marks
    a bare destination (quoted denomination or numeric/letter
    enumeration) resolved against the paired old locator's leaf — or
    a ``{kind: value}`` dict for a full-path destination. An EMPTY
    list is a structural redesignation whose destination is
    unprovable: emission must refuse, never guess."""
    og = active_profile().operative_grammar
    lead = _DEST_LEAD_RE.sub("", zone)
    # profile-level admissible prefixes ('los nuevos 10, 11 y 13')
    if og.redesig_dest_prefix is not None:
        pm = og.redesig_dest_prefix.match(lead)
        if pm:
            lead = _DEST_LEAD_RE.sub("", lead[pm.end():])
    first = re.split(r"[\s,.;:()]", lead, 1)[0].lower().rstrip(".ªº")
    structural = (
        lead.startswith(("«", "\"", "'"))
        or first in _dest_designators()
        or bool(re.match(r"\d", lead)))
    if not structural:
        return None
    masked = _mask_quoted(zone)
    colon = masked.find(":")
    if colon >= 0:
        zone = zone[:colon]
    mentions = _extract_mentions(zone.strip().rstrip("."))

    def leaf_vals(kind, vals):
        # 'letras e) y f)' enumerates e and f — a bare 'y'/'e' without
        # the ')' marker is the conjunction, not a destination value
        if kind != "letra":
            return list(vals)
        return [v for v in vals
                if re.search(rf"(?<!\w){re.escape(str(v))}\)", zone)]

    dests: list = []
    if len(mentions) == 1:
        kind, vals = next(iter(mentions.items()))
        vals = leaf_vals(kind, vals)
        for v in vals:
            if isinstance(v, tuple) and len(v) > 1 \
                    and all(str(x).isdigit() for x in v):
                # a 'lo a hi' range expands into consecutive slots
                for n in range(int(v[0]), int(v[1]) + 1):
                    dests.append((kind, str(n)))
            else:
                nv = _norm_dest(kind, v)
                if nv is None:
                    return []
                dests.append((kind, nv))
    elif len(mentions) > 1:
        # a full-path destination: kinds with a single value are shared
        # context ('las letras e) y f) de dicho apartado 2' anchors
        # apartado 2); exactly one kind may carry the enumerated leaf
        # values — two multi-valued kinds is unprovable ambiguity
        composite = {}
        leaf_kind = leaf_values = None
        multi = 0
        for kind, vals in mentions.items():
            vals = leaf_vals(kind, vals)
            if not vals:
                continue
            if len(vals) != 1:
                multi += 1
                leaf_kind, leaf_values = kind, vals
                continue
            nv = _norm_dest(kind, vals[0])
            if nv is None:
                return []
            composite[kind] = nv
        if multi > 1:
            return []
        if leaf_values is None:
            dests = [composite]
        else:
            dests = []
            for v in leaf_values:
                nv = _norm_dest(leaf_kind, v)
                if nv is None:
                    return []
                dests.append(dict(composite, **{leaf_kind: nv}))
    bare: list = []
    if og.redesig_bare_dest is not None:
        bm = og.redesig_bare_dest.search(zone)
        if bm:
            raw = bm.group(1).strip()
            if raw.startswith("«") and raw.endswith("»"):
                # quoted-name destination ('pasa a denominarse «X»')
                name = raw[1:-1].strip()
                bare = [(None, name)] if name else []
            else:
                vals = _expand_numlist(raw)
                if not vals:
                    # bare letter/digit enumerations ('los apartados
                    # A, B, C y D', 'los nuevos 10, 11 y 12'); any
                    # non-enum token other than the 'respectivamente'
                    # terminator voids the destination — no guessing
                    vals = []
                    for p in re.split(r",|\s+[ye]\s+", raw):
                        p = p.strip().rstrip(".")
                        if re.fullmatch(r"\d+|[A-Za-z]", p):
                            vals.append(p)
                        elif p.lower() != "respectivamente":
                            vals = []
                            break
                bare = [(None, str(v)) for v in vals]
    # the bare-destination grammar captures the explicit enumeration
    # whole; mention extraction may truncate it at a lookahead. A
    # strictly longer bare list is the real destination set; equal or
    # shorter keeps the richer typed mentions.
    if len(bare) > len(dests):
        dests = bare
    return dests


def redesignation_segments(clause_text: str) -> list:
    """Structural redesignation segments of a clause:
    ``(verb_start, verb_end, segment_end, dests)``. Non-structural
    'pasa a ser <non-designator>' matches are not segments."""
    out = []
    for m in _redesig_matches(clause_text):
        seg_end = _segment_end(clause_text, m.end())
        dests = _parse_dests(clause_text[m.end():seg_end])
        if dests is not None:
            out.append((m.start(), m.end(), seg_end, dests))
    return out


def _subject_zone(text: str) -> str:
    """Mentions outside every structural redesignation segment; the
    destination side never composes subjects. Only the verb-to-
    segment-end span is removed — later operations in the same node
    ('«X»; se suprimen los estados…') keep their subjects."""
    segs = redesignation_segments(text)
    if not segs:
        return text
    out, last = [], 0
    for vs, _ve, se, _d in segs:
        out.append(text[last:vs])
        last = se
    out.append(text[last:])
    return "".join(out)


# canonical nesting depth — roots share 0; the dict-destination leaf
# is its deepest component, the rest are shared path context
_REDESIG_DEPTH = {
    "pagina": -1, "indice": 0,
    "norma": 0, "anejo": 0, "anexo": 0, "disposicion": 0, "disp": 0,
    "estado": 0, "fichero": 0,
    "seccion": 1, "apartado": 2, "punto": 2, "numero": 2,
    "letra": 3, "numeral": 4, "nota": 4}


def _dest_leaf_kinds(dests) -> set:
    """The leaf kind each destination slot rewrites — for full-path
    dicts the deepest component; shallower dict entries are shared
    context. Bare slots (kind None) inherit the paired subject's leaf,
    so they drop nothing here."""
    kinds = set()
    for d in dests:
        if isinstance(d, dict):
            if d:
                kinds.add(max(
                    d, key=lambda k: _REDESIG_DEPTH.get(k, 0)))
        else:
            k, _v = d
            if k is not None:
                kinds.add(k)
    return kinds


def _subject_mentions(text: str) -> dict:
    """Mentions that may compose this clause's subjects.

    Everything outside structural redesignation segments, PLUS the
    shared-context declarations inside them: 'las letras e) y f) de
    dicho apartado 2' declares apartado 2 as the parent of BOTH
    endpoints, so it legitimately composes the old locators' path;
    only the destination leaf enumeration is excluded, so new-side
    locators never compose as subjects."""
    mentions = _extract_mentions(_subject_zone(text))
    for _vs, ve, se, dests in redesignation_segments(text):
        if not dests:
            continue
        leaf = _dest_leaf_kinds(dests)
        for k, vals in _extract_mentions(text[ve:se]).items():
            if k in leaf:
                continue
            merged = list(mentions.get(k) or [])
            merged.extend(vals)
            mentions[k] = merged
    return mentions


def _mention_pos(clause_text: str, locator_key: str) -> int | None:
    """Position of the locator's deepest mention in the clause — the
    same derivation ``subject_operation_kind`` uses."""
    poss = _mention_positions(clause_text, locator_key)
    return max(poss) if poss else None


def _mention_positions(clause_text: str, locator_key: str) -> list:
    """All positions where the locator's deepest component is
    mentioned. Short values ('13', 'n') use a plain word boundary
    rather than the strictest ``subject_operation_kind`` lookahead —
    for pairing, any left-of-verb occurrence proves the subject was
    addressed ('los números 13, 14, 15 y 16')."""
    _, deep = _locator_mentions(locator_key)
    og = active_profile().operative_grammar
    leaf_kind, leaf_val = _leaf_parts(locator_key)
    poss: list[int] = []
    if leaf_kind in og.redesig_name_kinds:
        # name-carried kinds (fichero) only ever occur inside «» —
        # quote masking would erase the only mention, and the value
        # is a denomination, not a code, so identity is proven by
        # normalised quoted-span equality; right-of-verb hits are
        # filtered by the caller's bound/verb window
        tn = active_profile().text_normalization
        for qm in tn.quoted_span.finditer(clause_text):
            inner = qm.group(0)[1:-1] if len(qm.group(0)) >= 2 \
                else qm.group(0)
            if _norm(inner) == _norm(leaf_val):
                poss.append(qm.start())
        return poss
    low = _mask_quoted(clause_text).lower()
    for d in deep:
        d = d.strip()
        if not d:
            continue
        # a bare single letter needs its marker — 'letras d) y e)'
        # mentions d and e, but 'y' followed by a space is the
        # conjunction, not a letra occurrence
        tail = r"(?=[).,;:])" if len(d) == 1 and d.isalpha() \
            else r"(?!\w)"
        for m in re.finditer(
                rf"(?<!\w){re.escape(d)}{tail}", low):
            poss.append(m.start())
    return poss


def _leaf_parts(locator_key: str) -> tuple[str, str]:
    """(kind, value) of the locator's deepest component. The leaf is
    the last kind-bearing component plus any trailing kind-less
    suffixes — 'disp:adicional.única' has leaf kind 'disp' with value
    'adicional.única', not a kind-less 'única'."""
    parts = locator_key.split(".")
    i = max((i for i, p in enumerate(parts) if ":" in p),
            default=-1)
    if i < 0:
        return parts[-1], ""
    k, _, v = parts[i].partition(":")
    if i < len(parts) - 1:
        v = ".".join([v] + parts[i + 1:])
    return k, v


def _dest_code(leaf_kind: str, dest) -> str | None:
    """The new-side code a destination declares for ``leaf_kind`` —
    the EXP-B1 mechanism: a typed slot matching the leaf kind carries
    its code directly; a bare token inherits the leaf kind; a bare
    denomination resolves through the profile's name-keyed kinds
    (fichero identity IS its rubric) or its name-code extractor
    (a quoted denomination may still carry the code). None = unprovable."""
    og = active_profile().operative_grammar
    if isinstance(dest, dict):
        for k, v in dest.items():
            if _REDESIG_KIND_ALIAS.get(k, k) == leaf_kind:
                return str(v)
        return None
    kind, value = dest
    if kind is not None:
        return str(value) \
            if _REDESIG_KIND_ALIAS.get(kind, kind) == leaf_kind \
            else None
    v = str(value)
    if re.fullmatch(r"[\d.]+|[A-Za-z]", v):
        return v
    if leaf_kind in (og.redesig_name_kinds or ()):
        return re.sub(r"\s+", " ", v).strip()
    rx = (og.redesig_name_code or {}).get(leaf_kind)
    if rx is not None:
        m = rx.search(v)
        if m:
            g = m.group(1)
            mm = re.match(r"\s*([A-Za-z]+)\s*(.*)", g)
            if leaf_kind == "estado" and mm:
                return _norm_state_code(mm.group(1), mm.group(2))
            return g
    return None


def _redesig_new_key(old_key: str, dest) -> str | None:
    """Apply one destination slot to an old locator path.

    (kind, value): replace the kind's component — bare slots inherit
    the leaf kind — and drop deeper components. dict: full-path
    destination, every kind must already appear in the old path.
    Returns None when the destination cannot be anchored (fail
    closed)."""
    # components split on '.', but values may themselves carry dots
    # ('apartado:II.B.2', 'disp:adicional.única') — a component without
    # a kind prefix continues the previous component's value
    parts: list[list[str]] = []
    for p in old_key.split("."):
        if ":" in p:
            k, _, v = p.partition(":")
            parts.append([k, v])
        elif parts:
            parts[-1][1] += "." + p
        else:
            return None
    kinds = [k for k, _ in parts]

    def idx_of(k):
        kk = _REDESIG_KIND_ALIAS.get(k, k)
        return kinds.index(kk) if kk in kinds else -1

    if isinstance(dest, dict):
        idxs = [idx_of(k) for k in dest]
        if not dest or -1 in idxs:
            return None
        deepest = max(idxs)
        for k, v in dest.items():
            parts[idx_of(k)] = (_REDESIG_KIND_ALIAS.get(k, k), str(v))
        return ".".join(f"{k}:{v}" for k, v in parts[:deepest + 1])
    kind, value = dest
    i = idx_of(kind) if kind is not None else len(parts) - 1
    if i < 0:
        return None
    parts[i] = (kinds[i], str(value))
    return ".".join(f"{k}:{v}" for k, v in parts[:i + 1])


def redesignation_pairs(clause_text: str, subjects) -> list:
    """Pair provable old-side subjects with their destination slots.

    Positional rule (EXP-B1): a subject pairs with the first
    structural redesig verb AFTER its deepest mention, inside the
    clause region opened by the previous segment's end. Destinations
    pair in order — N old locators need N slots. Each pair is
    classified:

      CODE_REDESIGNATION — destination declares a different code for
                           the subject's leaf kind; emits an edge
      RELABEL_SAME_CODE  — same code, denomination changed; the
                           ordinary relation stands (no edge)
      UNPROVABLE         — structural verb but the new code cannot
                           be proven from the segment; refusal

    Returns a list of dicts with keys ``subject`` (SubjectRef),
    ``dest``, ``cls``, ``new_key`` (None unless CODE_REDESIGNATION
    and anchored), ``verb_start``."""
    segs = redesignation_segments(clause_text)
    if not segs:
        return []
    poss = {s.locator_key: _mention_positions(clause_text,
                                              s.locator_key)
            for s in subjects}
    masked = _mask_quoted(clause_text)
    pairs: list = []
    lower = 0
    for vs, _ve, se, dests in segs:
        # left scope is the current sentence: mentions before the
        # last unquoted '. '/' ; ' boundary (or the previous segment's
        # end) belong to a different operation — 'la letra c) debe
        # finalizar… . las letras d) y e) pasan a ser…'
        bound = lower
        for bm in re.finditer(r"[.;]\s", masked[:vs]):
            bound = max(bound, bm.end())
        left = [s for s in subjects
                if any(bound <= p < vs
                       for p in poss.get(s.locator_key, ()))]
        left.sort(key=lambda s: min(
            p for p in poss[s.locator_key] if bound <= p < vs))
        if len(left) != len(dests):
            # ambiguous pairing (or a segment whose destinations were
            # unprovable): every left subject of this verb is refused
            for s in left:
                pairs.append({"subject": s, "dest": None,
                              "cls": "UNPROVABLE", "new_key": None,
                              "verb_start": vs})
            lower = se
            continue
        for s, dest in zip(left, dests):
            leaf_kind, leaf_val = _leaf_parts(s.locator_key)
            code = _dest_code(leaf_kind, dest)
            # a bare-name destination contributes the PROVEN code as
            # the new leaf value, never the raw denomination text
            anchor = dest
            if code is not None and not isinstance(dest, dict) \
                    and dest[0] is None:
                anchor = (None, code)
            new_key = _redesig_new_key(s.locator_key, anchor) \
                if code is not None else None
            if code is None or new_key is None:
                cls, new_key = "UNPROVABLE", None
            elif _norm(code) == _norm(leaf_val):
                cls, new_key = "RELABEL_SAME_CODE", None
            else:
                cls = "CODE_REDESIGNATION"
            pairs.append({"subject": s, "dest": dest, "cls": cls,
                          "new_key": new_key, "verb_start": vs})
        lower = se
    return pairs


def redesignation_destinations(clause_text: str):
    """Destination slots of the clause's FIRST structural redesig
    segment (compat shim for probe accounting). Returns None when no
    structural segment exists."""
    segs = redesignation_segments(clause_text)
    return segs[0][3] if segs else None


def _expand_numlist(raw: str) -> list:
    """Expand the numeric enumerations the corpus demonstrates:
    '17 a 20' → [17..20]; '3, 6 y 7' / '13, 18 y 19' → each element.
    A hierarchical dotted identifier ('1.3.2') is a single value, never
    a range or list (G2.1 §25). A non-numeric capture (e.g. the anejo
    path 'II.B.2') returns [].
    No linguistic range forms beyond explicit digits."""
    lg = active_profile().locator_grammar
    out: list = []
    for part in re.split(lg.expand_split, raw):
        part = part.strip()
        m = lg.expand_range.match(part)
        if m:
            out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.isdigit():
            out.append(int(part))
        elif lg.expand_atom.fullmatch(part):
            out.append(part)
        elif part:
            return []
    return out


# root locator families (G2.1 §22): an explicit root of one family
# displaces inherited roots of the other families — 'En el anejo 3,
# apartado …' under a stale 'norma N' context resolves under the anejo,
# never under norma.
def _context_update(ctx: dict[str, str],
                    mentions: dict[str, object]) -> dict[str, str]:
    new = dict(ctx)
    declared: set[str] = set()
    norma = mentions.get("norma")
    if norma:
        n = _ordinal_num(str(norma[0][0]))
        if n is not None:
            declared.add("norma")
            new["norma"] = str(n)
    anejo = mentions.get("anejo")
    if anejo:
        declared.add("anejo")
        new["anejo"] = re.sub(r"\s+", "", str(anejo[0][0]))
    disp = mentions.get("disposicion")
    if disp:
        declared.add("disposicion")
        new["disposicion"] = (str(disp[0][0]).lower() + "." +
                              str(disp[0][1]).lower())
    if declared:
        # the clause's own root displaces every inherited root of a
        # different family, and any inherited composed subject whose
        # path was built under the displaced root
        for k in active_profile().operative_grammar.root_families:
            if k not in declared:
                new.pop(k, None)
        new.pop("subject", None)
    pagina = mentions.get("pagina")
    if pagina:
        new["pagina"] = str(pagina[0][0])
    estados = mentions.get("estado")
    if estados and len(estados) == 1:
        new["estado"] = estados[0]
    return new


def _ctx_update_scoped(flat: dict[str, str], scope: dict,
                       mentions: dict[str, object], node_index: int,
                       scope_name: str) -> tuple[dict, dict]:
    """_context_update with per-key provenance (G2.1 §21): each context
    key records the node and scope frame that last declared it."""
    new = _context_update(flat, mentions)
    sc = {k: v for k, v in scope.items() if k in new}
    for k, v in new.items():
        if flat.get(k) != v:
            sc[k] = {"node_index": node_index, "scope": scope_name}
    return new, sc


def _merge_frames(frames: list) -> tuple[dict, dict]:
    """Fold scope frames outermost→innermost into (flat ctx, scope map).

    A frame declaring a root-family key displaces the other root
    families accumulated so far, plus any inherited composed subject —
    a deeper 'anejo' scope can never inherit a sibling/parent 'norma'.
    """
    out: dict[str, str] = {}
    scope: dict = {}
    roots = active_profile().operative_grammar.root_families
    for flat, sc in frames:
        declared = set(flat) & set(roots)
        if declared:
            for k in roots:
                if k not in declared:
                    out.pop(k, None)
                    scope.pop(k, None)
            out.pop("subject", None)
            scope.pop("subject", None)
        out.update(flat)
        scope.update(sc)
    return out, scope


def _has_unmodelled_qualifier(masked: str, key: str) -> bool:
    """The recorded locator's mention carries a suffix the model cannot
    express — 'norma N ter', 'apartado N.x)' — so the real subject is a
    different (sub-)entity than the recorded parent locator."""
    lg = active_profile().locator_grammar
    for part in re.split(r"\.(?=[a-z]+:)", key):
        kind, _, val = part.partition(":")
        kind_rx = lg.kind_words.get(kind)
        if not val or kind_rx is None:
            continue
        vals = {re.escape(val)}
        if val.isdigit():
            vals |= {re.escape(w) for w, n in
                     lg.ordinals.items() if n == int(val)}
        pat = re.compile(
            rf"\b{kind_rx}\s+(?:{'|'.join(sorted(vals))})"
            rf"{active_profile().operative_grammar.qualifier_src}",
            re.IGNORECASE)
        if pat.search(masked):
            return True
    return False


def _masked_clause(text: str) -> str:
    """Quoted spans blanked position-preserving — offsets in the result
    still index the original clause."""
    return active_profile().text_normalization.quoted_span.sub(
        lambda mm: " " * len(mm.group(0)), text)


def _literals(text: str) -> list[tuple[str, str]]:
    og = active_profile().operative_grammar
    pairs = [tuple(m.groups()) for m in og.donde_dice.finditer(text)]
    pairs += [tuple(m.groups()) for m in og.literal_pairs.finditer(text)]
    return pairs


def _mentions_or_literals(text: str) -> dict[str, object] | None:
    mentions = _extract_mentions(text)
    if mentions or _literals(text):
        return mentions
    return None


def _unmarked_op(node: Node) -> tuple[str, str] | None:
    """Recognize an operative paragraph without a list marker.

    BdE instruments carry three unmarked shapes inside the dispositive
    part: (a) a container intro fused with the first operation —
    "Se introducen las siguientes modificaciones en la Circular N/AAAA:
    se suprimen los apartados ..."; (b) a direct amendment clause —
    "Se modifica el fichero «X» ..." or "En la página N ... donde
    dice". Exposición prose before the first articulo is out of scope:
    unmarked ops are only sought inside sections, and a subject mention
    or a declared literal pair is mandatory.

    Returns ``(context_prefix, clause)`` — the prefix feeds section
    context/targets — or None if the paragraph is not operative.
    """
    p = active_profile()
    dm = p.document_model
    if node.kind != dm.kinds["paragraph"] \
            or node.cls not in dm.locator_classes:
        return None
    text = node.text
    if not _has_operative_verb(text):
        return None
    if p.operative_grammar.container.search(text):
        idx = text.find(":")
        if idx < 0 or not _has_operative_verb(text[idx + 1:]):
            return None
        clause = text[idx + 1:].strip()
        if _mentions_or_literals(clause) is None:
            return None
        return text[:idx + 1], clause
    if p.operative_grammar.unmarked_opener.match(text) \
            and _mentions_or_literals(text) is not None:
        return "", text
    return None


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------


def split_sections(doc: DiarioDoc) -> list[Section]:
    """Split the document body at ``articulo`` headings."""
    art_cls = active_profile().document_model.classes["articulo"]
    arts = [n for n in doc.nodes if n.cls == art_cls]
    if not arts:
        return []
    sections = []
    bounds = [a.index for a in arts] + [len(doc.nodes)]
    for i, a in enumerate(arts):
        targets = [(int(n), int(y)) for n, y in
                   active_profile().identity_reference.target_ref
                   .findall(a.text)]
        sections.append(Section(a.text, a.index, bounds[i + 1], targets))
    return sections


def _preamble_targets(doc: DiarioDoc, sec: Section) -> list[tuple[int, int]]:
    """Circular refs in a section's leading preamble paragraphs.

    Sections like "Norma segunda." carry no target in the heading; the
    operative announcement paragraph does — "Se introducen las
    siguientes modificaciones en la Circular N/AAAA:". Only leading
    preamble-shaped nodes (ending ':' or announcing 'siguientes') count,
    so a circular cited as replacement content is never read as a
    target.
    """
    p = active_profile()
    dm = p.document_model
    tn = p.text_normalization
    ir = p.identity_reference
    out: list[tuple[int, int]] = []
    for n in doc.nodes[sec.node_start + 1:sec.node_end]:
        if n.kind != dm.kinds["paragraph"] \
                or n.cls not in (dm.classes["parrafo"],
                                 dm.classes["parrafo_2"]) \
                or _marker_parts(n.text) is not None:
            break
        text = n.text.rstrip()
        if not (text.endswith(":")
                or p.operative_grammar.siguientes in text.lower()):
            break
        for m in ir.target_ref.finditer(tn.quoted_span.sub("", n.text)):
            ref = (int(m.group(1)), int(m.group(2)))
            if ref not in out:
                out.append(ref)
    return out


def parse_all_operations(doc: DiarioDoc) -> OpsResult:
    """Parse every candidate amendment operation in the document —
    target-agnostic (G2.1 §10).

    The parser describes document structure; deciding whether an
    operation belongs to the instrument being reconstructed is the
    ownership layer's job. Every op carries its section evidence
    (heading + section targets) so attribution is derivable afterwards.
    """
    sections = split_sections(doc)
    if not sections:
        # no articulo structure (e.g. correction orders): the whole body
        # is one implicit section
        sections = [Section("", 0, len(doc.nodes), [])]
    selected: list[tuple[Section, list[Operation]]] = []
    for s in sections:
        for ref in _preamble_targets(doc, s):
            if ref not in s.targets:
                s.targets.append(ref)
        selected.append((s, _parse_section(doc, s)))

    operations: list[Operation] = []
    for _, ops in selected:
        operations.extend(ops)

    # content spans: a leaf op's content runs until the next locator of
    # the same section or the section end
    locator_idx = {op.node_index for op in operations}
    sec_end = {op.node_index: sec.node_end
               for sec, ops in selected for op in ops}
    for op in operations:
        if op.is_container:
            op.content_span = (op.node_index + 1, op.node_index + 1)
            continue
        if not op.marker:
            # unmarked clauses are self-contained: their span, computed
            # in _parse_section, is empty unless the clause declares
            # trailing quoted content (ends ':')
            continue
        end = sec_end.get(op.node_index, len(doc.nodes))
        for j in range(op.node_index + 1, end):
            if j in locator_idx:
                end = j
                break
        op.content_span = (op.node_index + 1, end)

    for op in operations:
        _content_link(doc, op)

    return OpsResult(operations, sections, 0)


def parse_operations(doc: DiarioDoc,
                     target_ref: tuple[int, int] | None) -> OpsResult:
    """Legacy target-filtered view over :func:`parse_all_operations`.

    Compatibility wrapper for callers/tests that still want the
    pre-G2 semantics: a section belongs to the target when its heading
    or leading preamble names it; in sections naming no circular at
    all, an operation that names the target in its own clause is still
    kept when its subjects are FICHERO entities owned by that circular.
    ``target_ref=None`` matches every section.

    ``history.reconstruct`` MUST NOT use this — ownership attribution
    is a separate layer (G2.1 §11).
    """
    res = parse_all_operations(doc)
    if target_ref is None:
        return res
    if not res.sections or (
            len(res.sections) == 1 and not res.sections[0].heading):
        # no articulo structure: the implicit whole-body section was
        # always selected under the legacy semantics
        return res
    by_section: dict[int, list[Operation]] = {}
    for op in res.operations:
        by_section.setdefault(op.section_index, []).append(op)
    target_ranges = []
    kept: list[Operation] = []
    for s in res.sections:
        ops = by_section.get(s.node_start, [])
        if target_ref in s.targets:
            target_ranges.append((s.node_start, s.node_end))
            kept.extend(ops)
        elif not s.targets:
            kept.extend(
                op for op in ops
                if target_ref in op.targets and op.subjects
                and all(sub.kind == "FICHERO" for sub in op.subjects))
    out_of_target = sum(
        1 for n in doc.nodes
        if _is_locator(n) and not any(
            a <= n.index < b for a, b in target_ranges))
    return OpsResult(kept, res.sections, out_of_target)


def _content_link(doc: DiarioDoc, op: Operation) -> None:
    """Classify how this operation owns replacement content (G1 §17–18).

    ``EXPLICIT_FOLLOWING_CONTENT`` requires: (1) a recognized pointer or
    a structurally valid ':'; (2) non-empty content inside the operation's
    own span — which by construction lies in the same section, follows
    the locator node, and stops before the next sibling locator or the
    next articulo scope. A literal-only clause (donde dice / debe decir)
    never claims following blocks as its content.
    """
    if op.is_container:
        return
    if op.inline_content:
        op.content_link_method = "INLINE_QUOTED_CONTENT"
        op.content_link_evidence = {"inline": True}
        return
    if op.annex_ref:
        op.content_link_method = "EXPLICIT_ANNEX_REFERENCE"
        op.content_link_evidence = {"annex_ref": True}
        return
    s, e = op.content_span
    tbl = active_profile().document_model.kinds["table"]
    has_content = e > s and any(
        (doc.nodes[i].text or "").strip() or doc.nodes[i].kind == tbl
        for i in range(s, e))
    colon = op.clause_text.rstrip().endswith(":")
    pointer = bool(active_profile().operative_grammar.content_pointer
                   .search(op.clause_text))
    if op.literals and not colon:
        op.content_link_method = "DECLARED_LITERAL_ONLY"
        op.content_link_evidence = {"literal_pairs": len(op.literals)}
        return
    if has_content and (colon or pointer):
        op.content_link_method = "EXPLICIT_FOLLOWING_CONTENT"
        op.content_link_evidence = {
            "content_span": [s, e], "colon": colon,
            "pointer": pointer}
        return
    if op.literals:
        op.content_link_method = "DECLARED_LITERAL_ONLY"
        op.content_link_evidence = {"literal_pairs": len(op.literals)}
        return
    op.content_link_method = "NO_PROVEN_CONTENT"
    op.content_link_evidence = {
        "content_span": [s, e], "has_content": has_content,
        "colon": colon, "pointer": pointer}


def _alpha_value(tok: str) -> int:
    v = 0
    for ch in tok.lower():
        if not ch.isalpha():
            return 0
        v = v * 26 + (ord(ch) - 96)
    return v


def _compatible(style: str, level_style: str) -> bool:
    if style == level_style:
        return True
    return (style in ("alpha", "amb") and level_style in ("alpha", "amb")) \
        or (style in ("roman", "amb") and level_style in ("roman", "amb"))


def _parse_section(doc: DiarioDoc, sec: Section) -> list[Operation]:
    ops: list[Operation] = []
    # scoped context frames (G2.1 §21-24), outermost first:
    #   section — preamble setters before the first ordinal-word item;
    #   item    — the most recent unmarked ordinal-word setter
    #             ("Cinco.", "Seis."); a new ordinal item replaces it;
    #   levels  — marker ancestors; each frame stores only the context
    #             ITS clause declares, so _merge_frames can apply
    #             root-family exclusivity per frame.
    section_ctx: dict[str, str] = {}
    section_scope: dict = {}
    item_ctx: dict[str, str] = {}
    item_scope: dict = {}
    item_active = False
    levels: list[tuple[str, int, dict, dict]] = []
    top_alpha = 0  # value of the last top-level lettered item (a=1, aa=27)

    def merged_ctx() -> tuple[dict, dict]:
        frames = [(section_ctx, section_scope), (item_ctx, item_scope)]
        frames += [(lf, ls) for _, _, lf, ls in levels]
        return _merge_frames(frames)

    prof = active_profile()
    dm, lg, tn = prof.document_model, prof.locator_grammar, \
        prof.text_normalization
    og, ir = prof.operative_grammar, prof.identity_reference
    prev_container = False
    for i in range(sec.node_start + 1, sec.node_end):
        n = doc.nodes[i]
        if n.kind not in (dm.kinds["paragraph"],
                          dm.kinds["blockquote"]):
            continue
        parts = _marker_parts(n.text)
        if parts is None:
            unmarked = _unmarked_op(n)
            if unmarked is not None:
                prefix, clause = unmarked
                op_targets = _target_refs(tn.quoted_span.sub("", prefix))
                if prefix:
                    # unmarked-op prefix is a context setter inside the
                    # active scope (item if one is open, else section)
                    if item_active:
                        item_ctx, item_scope = _ctx_update_scoped(
                            item_ctx, item_scope,
                            _extract_mentions(prefix), i, "ITEM")
                    else:
                        section_ctx, section_scope = _ctx_update_scoped(
                            section_ctx, section_scope,
                            _extract_mentions(prefix), i, "SECTION")
                tail = og.non_op_tail.search(clause)
                zone = clause[:tail.start()] if tail else clause
                mentions = _extract_mentions(zone)
                ctx, cscope = merged_ctx()
                subjects = _compose_keys(
                    _subject_mentions(zone), ctx, cscope, i)
                page = mentions.get("pagina")
                page_ref = int(str(page[0][0])) if page else (
                    int(ctx["pagina"]) if "pagina" in ctx else None)
                if page_ref:
                    subjects = [SubjectRef(
                        s.locator_key, s.label, s.kind,
                        s.page_ref or page_ref, s.proof_components)
                        for s in subjects]
                for ref in _clause_targets(clause):
                    if ref not in op_targets:
                        op_targets.append(ref)
                # an unmarked clause ending ':' declares replacement
                # text in the following quote/indented nodes
                # ('Se da nueva redacción al apartado X: «...»')
                cend = i + 1
                if clause.rstrip().endswith(":"):
                    j = i + 1
                    while j < sec.node_end:
                        nxt = doc.nodes[j]
                        if nxt.kind == dm.kinds["paragraph"] and (
                                nxt.cls.startswith(
                                    dm.class_prefixes["sangrado"])
                                or (nxt.text or "").lstrip()
                                .startswith(tn.quote_open)):
                            cend = j + 1
                            j += 1
                        else:
                            break
                ops.append(Operation(
                    node_index=i,
                    marker="",
                    clause_text=clause,
                    operation_kind=_op_kind(clause),
                    subjects=subjects,
                    content_span=(i + 1, cend),
                    is_container=False,
                    annex_ref=bool(og.annex_ref.search(n.text)),
                    literals=_literals(clause),
                    context=ctx,
                    section_index=sec.node_start,
                    targets=op_targets,
                    prefix=prefix,
                    section_heading=sec.heading,
                    section_targets=list(sec.targets),
                    context_scope=cscope,
                ))
                continue
            # preamble context setter, e.g. "Se introducen los siguientes
            # cambios en el anejo 9 ... :" before lettered point clauses
            if n.cls in (dm.classes["parrafo"], dm.classes["parrafo_2"]) \
                    and (n.text.rstrip().endswith(":")
                         or og.siguientes in n.text.lower()):
                # an unmarked ordinal-word item ('Cinco.', 'Seis.')
                # opens a fresh sibling scope: the previous item's
                # context dies (G2.1 §23)
                if lg.ordinal_item.match(n.text):
                    item_ctx, item_scope = _ctx_update_scoped(
                        {}, {}, _extract_mentions(n.text), i, "ITEM")
                    item_active = True
                elif item_active:
                    # non-ordinal setters after the first item merge
                    # into the active item's context
                    item_ctx, item_scope = _ctx_update_scoped(
                        item_ctx, item_scope, _extract_mentions(n.text),
                        i, "ITEM")
                else:
                    section_ctx, section_scope = _ctx_update_scoped(
                        section_ctx, section_scope,
                        _extract_mentions(n.text), i, "SECTION")
            continue
        if not _is_locator(n):
            continue

        style, marker_val = parts
        text = n.text
        inline = ""
        if n.kind == dm.kinds["blockquote"]:
            # locator clause and quoted replacement content share the node;
            # the clause keeps only the part before «, the rest is content
            qpos = text.find(tn.quote_open)
            if qpos >= 0:
                text, inline = text[:qpos].rstrip(), text[qpos:]
        mentions = _extract_mentions(n.text)
        container = _is_container(text)

        if prev_container:
            # first child of an open container: ambiguous markers read as
            # roman sub-items under an alpha parent
            child_style = "roman" if style == "amb" else style
            levels.append((child_style, i, {}, {}))
        else:
            # an ambiguous marker (i), v), x)...) that continues the
            # top-level alpha sequence is a top-level letter, not a
            # roman child ("v) En la norma 70" after "u) En la norma 68")
            aval = _alpha_value(marker_val)
            force_top = (style == "amb" and levels
                         and levels[0][0] == "alpha"
                         and aval == top_alpha + 1)
            if force_top:
                del levels[1:]
                levels[0] = ("alpha", i, {}, {})
                top_alpha = aval
                style = "alpha"
            else:
                # find the deepest level this marker can continue
                depth = None
                for d in range(len(levels) - 1, -1, -1):
                    if _compatible(style, levels[d][0]):
                        depth = d
                        break
                if depth is None:
                    levels.append((style, i, {}, {}))
                    if len(levels) == 1 and style == "alpha":
                        top_alpha = aval
                else:
                    # an ambiguous marker adopts the style of the level
                    # it replaces (roman children vs. top-level alpha)
                    adopted = levels[depth][0]
                    del levels[depth:]
                    resolved = adopted if style == "amb" else style
                    levels.append((resolved, i, {}, {}))
                    if depth == 0 and resolved == "alpha":
                        top_alpha = aval

        # the level frame stores only the context this clause declares;
        # _merge_frames applies root exclusivity against ancestors
        own_flat, own_scope = _ctx_update_scoped(
            {}, {}, mentions, i, "LEVEL")
        levels[-1] = (levels[-1][0], i, own_flat, own_scope)
        ctx, cscope = merged_ctx()

        subjects = _compose_keys(
            _subject_mentions(n.text), ctx, cscope, i)
        if subjects:
            # children clauses without own subject inherit this level's
            levels[-1][2]["subject"] = subjects[0].locator_key
            levels[-1][3]["subject"] = {"node_index": i, "scope": "LEVEL"}
        page = mentions.get("pagina")
        page_ref = int(str(page[0][0])) if page else (
            int(ctx["pagina"]) if "pagina" in ctx else None)
        if page_ref:
            subjects = [SubjectRef(s.locator_key, s.label, s.kind,
                                   s.page_ref or page_ref,
                                   s.proof_components)
                        for s in subjects]

        ops.append(Operation(
            node_index=i,
            marker=lg.clause_marker.match(text).group("m"),
            clause_text=text,
            operation_kind=_op_kind(text),
            subjects=subjects,
            content_span=(i + 1, i + 1),
            is_container=container,
            annex_ref=bool(og.annex_ref.search(n.text)),
            literals=_literals(n.text),
            context=ctx,
            section_index=sec.node_start,
            inline_content=inline,
            targets=[(int(a), int(b)) for a, b in
                     ir.target_ref.findall(
                         tn.quoted_span.sub("", n.text))],
            section_heading=sec.heading,
            section_targets=list(sec.targets),
            context_scope=cscope,
        ))
        prev_container = container

    return ops

# Frozen-evaluator compatibility (PORT-2R): pre-PORT internal names
# resolve to the active profile's grammar so frozen evaluators keep
# working byte-for-byte without importing SourceProfile.
def __getattr__(name: str):
    p = active_profile()
    aliases = {
        "_ORDINALS": p.locator_grammar.ordinals,
        "_QUOTED_SPAN_RE": p.text_normalization.quoted_span,
        "_OP_KINDS": p.operative_grammar.op_kinds,
        "_MARKER_RE": p.locator_grammar.clause_marker,
        "_FICHERO_OWNER_RE": p.identity_reference.fichero_owner,
    }
    try:
        return aliases[name]
    except KeyError:
        raise AttributeError(name) from None
