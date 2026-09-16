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
from .sources.boe_diario import DiarioDoc, Node, normalize

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
# ---------------------------------------------------------------------------

_MARKER_RE = re.compile(
    r"^(?P<m>(?:[a-z]{1,2}\)|[ivxlcdm]+\s*[.)]|\d+\s*[.)]))\s*", re.IGNORECASE
)

# 'desglosa' is never an amendment verb in BOE drafting ("la
# información se desglosará de acuerdo con ..." describes content);
# it is excluded from the operative verb set. 'incluir' amends only
# with a structural direct object ('se incluye la nota a)') — 'se
# incluyen los importes' / 'se incluye como anejo 1' describe content
# or placement, not an amendment.
_INCLU_OBJ_RE = (
    r"(?=\s+(?:unas?|una?|el|la|los|las|otras?|nuev[ao]s?|send[ao]s?)"
    r"\s+(?:nuev[ao]s?\s+)?(?:normas?|anejos?|anexos?|apartados?|"
    r"letras?|puntos?|numeral(?:es)?|notas?|estados?|ficheros?|"
    r"disposici[oó]n(?:es)?|secci[oó]n(?:es)?|[ií]ndices?|"
    r"p[aá]ginas?)\b)")
_AMEND_VERB_ACTIVE_RE = re.compile(
    r"se\s+(?:modifica\w*|sustituye\w*|suprime\w*|elimina\w*|añade\w*|"
    r"introduce\w*|incorpora\w*|inclu\w*" + _INCLU_OBJ_RE +
    r"|realiza\w*|inserta\w*|crea\w*)",
    re.IGNORECASE,
)

# subordinators: an active 'se <verb>' inside a relative/complement
# clause ("que se introduce en la Circular N/AAAA", "en la medida en
# que se modifican mediante ...") is referential, not operative.
_SUBORDINATOR_TAIL_RE = re.compile(
    r"(?:^|[,;:]\s*|\s)"
    r"(?:que|por\s+(?:el|la|los|las)\s+que|cuy[ao]s?|cuy[ao]s?|donde|"
    r"mediante|como|según|conforme|si|cuando|mientras|aunque|porque|"
    r"en\s+la\s+medida\s+en\s+que)\s*$",
    re.IGNORECASE,
)

_AMEND_VERB_PASSIVE_RE = re.compile(
    r"debe\w*\s+(?:modificarse|sustituirse|suprimirse|eliminarse|"
    r"añadirse|introducirse|incorporarse|incluirse" + _INCLU_OBJ_RE +
    r"|insertarse|crearse)|"
    r"queda\w*\s+redactad|pasa\w*\s+a\s+(?:ser|denominarse)|"
    r"(?:se\s+)?da\w*\s+nueva\s+redacci[oó]n|"
    r"donde\s+dice|debe\s+decir|se\s+sombrea",
    re.IGNORECASE,
)

_AMEND_VERB_RE = re.compile(
    _AMEND_VERB_ACTIVE_RE.pattern + "|" + _AMEND_VERB_PASSIVE_RE.pattern,
    re.IGNORECASE,
)


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
    if _AMEND_VERB_PASSIVE_RE.search(head):
        return True
    for m in _AMEND_VERB_ACTIVE_RE.finditer(head):
        seg = head[:m.start()]
        if not _SUBORDINATOR_TAIL_RE.search(seg):
            return True
    return False

_EN_SUBJECT_RE = re.compile(
    r"^en\s+(?:la|el|los|las)\s+(norma|anejo|anexo|estado|estados|"
    r"disposición|apartado|punto|letra|numeral|nota|p[aá]gina)\b",
    re.IGNORECASE,
)

# "Estado PI 2:", "Anejo 7.1:" — bare subject containers without verb/En
_BARE_SUBJECT_RE = re.compile(
    r"^(estado|estados|anejo|anexo|norma|disposición|apartado|punto|"
    r"sección)\s+\S",
    re.IGNORECASE,
)

_CONTENT_POINTER_RE = re.compile(
    r"queda\w*\s+redactad|por\s+(?:el|los|la|las)\s+que\s+figura|"
    r"por\s+la\s+siguiente|por\s+las\s+siguientes|por\s+el\s+siguiente|"
    r"por\s+los\s+siguientes|con\s+el\s+siguiente|con\s+la\s+siguiente|"
    r"con\s+el\s+formato|por\s+«|donde\s+dice|debe\s+decir|"
    r"siguiente\s+redacción|siguiente\s+tenor|siguiente\s+texto|"
    r"como\s+sigue|con\s+arreglo\s+a|siguientes?\s+términos|"
    r"por\s+la\s+que\s+figura",
    re.IGNORECASE,
)

_CONTAINER_RE = re.compile(
    r"siguientes\s+modificaciones|siguientes\s+cambios",
    re.IGNORECASE,
)

_TARGET_RE = re.compile(
    r"Circular\s+(?:del\s+Banco\s+de\s+Espa[ñn]a\s+)?(\d+)\s*/\s*(\d{4})",
    re.IGNORECASE)


def _target_refs(text: str) -> list[tuple[int, int]]:
    """All 'Circular N/AAAA' references in text, incl. the
    'Circular del Banco de España N/AAAA' word order."""
    return [(int(a), int(b)) for a, b in _TARGET_RE.findall(text)]


# "...que consta en el anejo de la Circular del Banco de España
# 4/2008, de actualización de la Circular 2/2005" — the ref governed by
# "anejo de la Circular" names the instrument whose annex holds the
# fichero; a second ref nested in its description is not an owner.
_FICHERO_OWNER_RE = re.compile(
    r"anejo\s+de\s+la\s+Circular\s+(?:del\s+Banco\s+de\s+Espa[ñn]a\s+)?"
    r"(\d+)\s*/\s*(\d{4})", re.IGNORECASE)


def _clause_targets(text: str) -> list[tuple[int, int]]:
    """Circular refs that attribute a clause to another instrument.

    An owner construction ('...que consta/figura en el anejo de la
    Circular N/AAAA') wins over every other mention; without it, only a
    single unambiguous ref attributes the clause — multiple competing
    refs are descriptive, not attributive.
    """
    owners = [(int(m.group(1)), int(m.group(2)))
              for m in _FICHERO_OWNER_RE.finditer(text)]
    if owners:
        return owners
    refs = _target_refs(_QUOTED_SPAN_RE.sub("", text))
    uniq = list(dict.fromkeys(refs))
    return uniq if len(uniq) == 1 else []

_ORDINALS = {
    "primera": 1, "primero": 1, "primer": 1, "segunda": 2, "segundo": 2,
    "tercera": 3, "tercero": 3, "tercer": 3, "cuarta": 4, "cuarto": 4,
    "quinta": 5, "quinto": 5, "sexta": 6, "sexto": 6, "séptima": 7,
    "septima": 7, "séptimo": 7, "octava": 8, "octavo": 8, "novena": 9,
    "noveno": 9, "décima": 10, "decima": 10, "décimo": 10,
    "undécima": 11, "duodécima": 12, "decimotercera": 13,
    "decimocuarta": 14, "decimoquinta": 15, "decimosexta": 16,
    "decimoséptima": 17, "decimoctava": 18, "decimonovena": 19,
    "vigésima": 20, "vigesima": 20, "única": 1, "unica": 1,
}

_QUOTED_SPAN_RE = re.compile(r"«[^»]*»")

# data-file subjects: 'el fichero «Expedientes sancionadores»'
_FICHERO_RE = re.compile(r"\bficheros?\s+«([^»]+)»", re.IGNORECASE)
# non-operative qualifier that closes an unmarked clause's subject zone:
# "se suprimen los apartados 4 y 5 ..., sin que se introduzca ningún
# cambio en los apartados 1 a 3"
_NON_OP_TAIL_RE = re.compile(r"[,;.]\s*sin\s+(?:que|perjuicio)\b",
                             re.IGNORECASE)

# hierarchical apartado values ('apartado 1.3.2', 'apartado II.B.2')
# are single identifiers, not lists (G2.1 §25)
_APART_ATOM = r"(?:\d+(?:\s*\.\s*\d+)*|[IVX]+(?:\.[A-Z0-9]+)*)"

# enumeration-aware mention patterns (G2.1 §25): 'anejos 1 y 2',
# 'normas 60, 62 y 64', 'apartados 12 a 17' declare every enumerated
# value; a hierarchical dotted identifier is one value, never a range
_NUM_SEQ = r"\d+(?:\s*\.\s*\d+)*"
_ROMAN_SEQ = r"[IVX]+(?:\.[A-Z0-9]+)*"
_ORD_SEQ = "|".join(_ORDINALS)
_ENUM_SEP = r"(?:\s*(?:a|al|,|y|e)\s+)"

_LET_LIST_RE = re.compile(
    r"\bletras?\s+((?:\(?[a-z]\)?\s*(?:,|\sy\s|\se\s|\sa\s))*"
    r"\(?[a-z]\)?)", re.IGNORECASE)


def _letters(raw: str) -> list[str]:
    # case-sensitive on purpose: 'letra B)' is an ordinal-style
    # reference the corpus never uses as a locator declaration
    return [m.group(0).lstrip("(").rstrip(")")
            for m in re.finditer(r"\(?[a-z]\)?", raw)]


def _numlist(raw: str) -> list[tuple[str, ...]]:
    """Tokenize a numeric enumeration preserving ranges and
    hierarchical values: a 'lo a hi' pair stays a 2-tuple; each other
    element is a singleton, dotted identifiers included."""
    out: list[tuple[str, ...]] = []
    for tok in re.split(r"\s*(?:,|y|e)\s+", raw):
        tok = re.sub(r"\s*\.\s*", ".", tok.strip())
        m = re.fullmatch(r"(\d+)\s+(?:a|al)\s+(\d+)", tok)
        if m:
            out.append((m.group(1), m.group(2)))
        elif re.fullmatch(r"\d+(?:\.\d+)*|[IVX]+(?:\.[A-Z0-9]+)*|" +
                          _ORD_SEQ, tok, re.IGNORECASE):
            out.append((tok,))
    return out


_PATTERNS = {
    "norma": re.compile(
        r"\bnormas?\s+((?:\d+|" + _ORD_SEQ + r")"
        r"(?:" + _ENUM_SEP + r"(?:\d+|" + _ORD_SEQ + r"))*)"
        r"(?=\s*[,.:;)(«]|\s+(?:de|que|del|en|se|con|por|sin|donde|"
        r"y\s+la|y\s+el|y\s+los|y\s+las)\b|$)",
        re.IGNORECASE),
    "anejo": re.compile(
        r"\banejos?\s+(" + _NUM_SEQ +
        r"(?:" + _ENUM_SEP + _NUM_SEQ + r")*)"
        r"(?=\s*[,.:;)(«]|\s+(?:de|que|del|en|se|con|por|sin|sobre|donde"
        r"|y\s+el)\b|$)",
        re.IGNORECASE),
    "apartado": re.compile(
        r"\bapartados?\s+((?:" + _NUM_SEQ + r"|" + _ROMAN_SEQ + r")"
        r"(?:" + _ENUM_SEP + r"(?:" + _NUM_SEQ + r"|" + _ROMAN_SEQ
        + r"))*)"
        r"(?=\s*[,.:;)(«]|\s+(?:de|que|del|en|se|con|por|sin|donde|"
        r"y\s+el)\b|$)",
        re.IGNORECASE),
    "punto": re.compile(
        r"\bpuntos?\s+(" + _NUM_SEQ +
        r"(?:" + _ENUM_SEP + _NUM_SEQ + r")*)"
        r"(?=\s*[,.:;)(«]|\s+(?:de|que|del|en|se|con|por|sin|donde|"
        r"y\s+el|sin\s+que)\b|$)",
        re.IGNORECASE),
    "numeral": re.compile(r"\bnumerales?\s+([ivxlcdm]+)\s*\)?", re.IGNORECASE),
    "nota": re.compile(r"\bnotas?\s+\(?([a-z])\)?", re.IGNORECASE),
    "disposicion": re.compile(
        r"\bdisposici[oó]n\s+(adicional|transitoria|final|derogatoria)\s+"
        r"(\w+)", re.IGNORECASE),
    "pagina": re.compile(r"\bp[aá]gina\s+(\d{3,6})", re.IGNORECASE),
    "indice": re.compile(r"\b[íi]ndice\b", re.IGNORECASE),
}

# mention kinds whose captured text is an enumeration to tokenize
_ENUM_MENTION_KINDS = ("norma", "anejo", "apartado", "punto")

_LITERAL_PAIRS_RE = re.compile(
    r"«([^»]+)»\s*(?:,?\s*se\s+(?:sustituye|sustituyen|modifica|cambia)\w*"
    r"\s+por|por)\s*«([^»]+)»"
)
_DONDE_DICE_RE = re.compile(
    r"donde\s+dice:\s*«([^»]+)»\s*,?\s*debe\s+decir:\s*«([^»]+)»",
    re.IGNORECASE,
)
_ANNEX_REF_RE = re.compile(
    r"en\s+el\s+anejo\s+de\s+esta\s+circular|"
    r"(?:figura\w*|incluye\w*|recoge\w*)\s+en\s+el\s+anejo\b",
    re.IGNORECASE,
)

_OP_KINDS = [
    ("SUBSTITUTE", re.compile(
        r"se\s+sustituye\w*|debe\w*\s+sustituirse|"
        r"(?:se\s+)?da\w*\s+nueva\s+redacci[oó]n", re.IGNORECASE)),
    ("DELETE", re.compile(
        r"se\s+(?:suprime\w*|elimina\w*)|debe\w*\s+(?:suprimirse|"
        r"eliminarse)", re.IGNORECASE)),
    ("ADD", re.compile(
        r"se\s+(?:añade\w*|introduce\w*|incorpora\w*|inclu\w*"
        + _INCLU_OBJ_RE + r"|crea\w*)|"
        r"debe\w*\s+(?:añadirse|introducirse|incorporarse|incluirse"
        + _INCLU_OBJ_RE + r"|insertarse|crearse)",
        re.IGNORECASE)),
    ("MODIFY", re.compile(
        r"se\s+(?:modifica\w*|realiza\w*|sombrea)|queda\w*\s+redactad|"
        r"pasa\w*\s+a\s+(?:ser|denominarse)", re.IGNORECASE)),
]


# sub-clause boundaries for per-subject verb scoping
_SEG_SPLIT_RE = re.compile(
    r"[;:]|\.\s|\s+(?:y|e|ni)\s+", re.IGNORECASE)

_ROMAN_NUM = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
              "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x",
              "11": "xi", "12": "xii", "13": "xiii", "14": "xiv",
              "15": "xv", "16": "xvi", "17": "xvii", "18": "xviii",
              "19": "xix", "20": "xx"}

_HEAD_FORMS = {
    "norma": ("norma",),
    "anejo": ("anejo", "anexo"),
    "disp": ("disposicion",),
    "articulo": ("articulo",),
    "estado": ("estado",),
    "fichero": ("fichero",),
}

_ORDINAL_WORDS = {
    "1": "primera", "2": "segunda", "3": "tercera", "4": "cuarta",
    "5": "quinta", "6": "sexta", "7": "septima", "8": "octava",
    "9": "novena", "10": "decima", "11": "undecima", "12": "duodecima",
    "13": "decima tercera", "14": "decima cuarta", "15": "decima quinta",
    "16": "decima sexta", "17": "decima septima", "18": "decima octava",
    "19": "decima novena", "20": "vigesima",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).lower().strip()


def _locator_mentions(key: str) -> tuple[list[str], list[str]]:
    """(head mention alternatives, deep mention alternatives) for an
    operative-clause search — the deep list carries one normalized
    'kind val' pair plus the bare value for each sub-locator part, and
    falls back to the head alternatives when the key has none."""
    parts = key.split(".")
    kind, _, body = parts[0].partition(":")
    tok = _norm(body)
    heads = []
    for h in _HEAD_FORMS.get(kind, (kind,)):
        heads.append(f"{h} {tok}")
        if kind == "disp" and len(parts) > 1:
            heads.append(f"{h} {tok} {_norm(parts[1])}")
    if kind in ("norma", "anejo", "anexo", "articulo"):
        word = _ORDINAL_WORDS.get(tok)
        for h in _HEAD_FORMS.get(kind, (kind,)):
            if word:
                heads.append(f"{h} {word}")
            if tok in _ROMAN_NUM:
                heads.append(f"{h} {_ROMAN_NUM[tok]}")
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
    masked = _QUOTED_SPAN_RE.sub(" ", text)
    best: tuple[int, str] | None = None
    for kind, rx in _OP_KINDS:
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
    masked = _QUOTED_SPAN_RE.sub(
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
    for kind, rx in _OP_KINDS:
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
    return _ORDINALS.get(w)


def _marker_parts(text: str) -> tuple[str, str] | None:
    m = _MARKER_RE.match(text)
    if not m:
        return None
    tok = m.group("m").replace(" ", "")
    body = tok.rstrip(").")
    if body.isdigit():
        return "num", body
    return "amb" if body.lower() in {
        "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
        "xi", "xii", "xiii", "xiv", "xv",
    } else "alpha", body


_LOCATOR_CLASSES = {"parrafo", "parrafo_2", "sangrado", "sangrado_2", "cita"}


def _is_locator(node: Node) -> bool:
    if node.kind not in ("p", "blockquote") \
            or node.cls not in _LOCATOR_CLASSES:
        return False
    # a blockquote may fuse the locator clause and its quoted replacement
    # content into a single node; only the span before « is locator prose
    text = node.text.split("«", 1)[0] if node.kind == "blockquote" \
        else node.text
    m = _MARKER_RE.match(text)
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
            _EN_SUBJECT_RE.search(rest) or _BARE_SUBJECT_RE.match(rest)):
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
    if not t.endswith(":") or _CONTENT_POINTER_RE.search(t):
        return False
    if _CONTAINER_RE.search(t):
        return True
    if not _AMEND_VERB_RE.search(t):
        return True
    # "se modifican:" with no object announces nested clauses
    return bool(re.search(r"se\s+(?:modifican?|realizan?|efectúan?)\s*:$",
                          t, re.IGNORECASE))


def _op_kind(text: str) -> str:
    for kind, rx in _OP_KINDS:
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
    # state-code grammar lives in the active profile's annex_state
    # facet (PORT-2 C-016); the mention/anchor policy below is core
    pats = active_profile().annex_state.patterns
    quoted_states: list[str] = []
    for m in pats["quoted_state"].finditer(text):
        for qm in pats["quoted_code"].finditer(m.group(1)):
            quoted_states.append(
                _norm_state_code(qm.group(1), qm.group(2)))

    stripped = _QUOTED_SPAN_RE.sub("«»", text)

    # positional anchors are excluded by span range, not by code value
    # ("por el formato de estado FI 142-1.1" must not kill the subject
    # mention of the same code earlier in the clause)
    anchor_spans = [m.span(1)
                    for m in pats["state_anchor_span"].finditer(stripped)]

    out: dict[str, object] = {}
    for key, rx in _PATTERNS.items():
        if key in _ENUM_MENTION_KINDS:
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
    for m in _LET_LIST_RE.finditer(stripped):
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
                for m in _FICHERO_RE.finditer(text)]
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
    clause_roots = {r for r in _CTX_ROOTS if mentions.get(r)}

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


def _expand_numlist(raw: str) -> list:
    """Expand the numeric enumerations the corpus demonstrates:
    '17 a 20' → [17..20]; '3, 6 y 7' / '13, 18 y 19' → each element.
    A hierarchical dotted identifier ('1.3.2') is a single value, never
    a range or list (G2.1 §25). A non-numeric capture (e.g. the anejo
    path 'II.B.2') returns [].
    No linguistic range forms beyond explicit digits."""
    out: list = []
    for part in re.split(r",|\s+[ye]\s+", raw):
        part = part.strip()
        m = re.match(r"^(\d+)\s+(?:a|al)\s+(\d+)$", part)
        if m:
            out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.isdigit():
            out.append(int(part))
        elif re.fullmatch(r"\d+(?:\.\d+)+", part):
            out.append(part)
        elif part:
            return []
    return out


# root locator families (G2.1 §22): an explicit root of one family
# displaces inherited roots of the other families — 'En el anejo 3,
# apartado …' under a stale 'norma N' context resolves under the anejo,
# never under norma.
_CTX_ROOTS = ("norma", "anejo", "disposicion")

# unmarked ordinal-word items ('Cinco.', 'Seis.') open a sibling scope:
# the previous ordinal item's context dies when the next one appears
# (G2.1 §23); non-ordinal setters after the first item merge into the
# active item's context.
_ORDINAL_WORD_ITEM_RE = re.compile(
    r"^(primer[oa]?|segund[oa]|tercer[oa]?|tercer|cuart[oa]|quint[oa]|"
    r"sext[oa]|s[eé]ptim[oa]|octav[oa]|noven[oa]|d[eé]cim[oa]|"
    r"und[eé]cim[oa]?|duod[eé]cim[oa]|uno|una|dos|tres|cuatro|cinco|"
    r"seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince)\."
    r"\s", re.IGNORECASE)


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
        for k in _CTX_ROOTS:
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
    for flat, sc in frames:
        declared = set(flat) & set(_CTX_ROOTS)
        if declared:
            for k in _CTX_ROOTS:
                if k not in declared:
                    out.pop(k, None)
                    scope.pop(k, None)
            out.pop("subject", None)
            scope.pop("subject", None)
        out.update(flat)
        scope.update(sc)
    return out, scope


# operative qualifiers that scope an operation below the locator model:
# a clause acting on a módulo/dimensión/cuadro/etc. targets an element
# the locator cannot express (moved from history for ownership reuse)
_SUB_SCOPE_RE = re.compile(
    r"\b(?:m[oó]dulo|dimensi[oó]n|apartado|letra|punto|numeral|nota|"
    r"secci[oó]n|cuadro|tabla|p[aá]rrafo|[íi]ndice|fila|columna)\b",
    re.IGNORECASE)

# unmodelled ordinal qualifiers that make a recorded locator coarser
# than the actual subject: 'norma 64 bis', 'apartado 2.e)', 'punto 4 ter'
_QUALIFIER_SRC = r"(?:\.\s*[a-z]\b|\s+(?:bis|ter|qu[aá]ter|quinquies|" \
    r"sexies|septies|octies|nonies|decies)\b)"

_KIND_WORDS = {
    "apartado": r"apartados?", "letra": r"letras?", "punto": r"puntos?",
    "numeral": r"numerales?", "nota": r"notas?", "norma": r"normas?",
    "anejo": r"(?:anejos?|anexos?)", "seccion": r"secciones?",
    "indice": r"[íi]ndices?",
}


def _has_unmodelled_qualifier(masked: str, key: str) -> bool:
    """The recorded locator's mention carries a suffix the model cannot
    express — 'norma N ter', 'apartado N.x)' — so the real subject is a
    different (sub-)entity than the recorded parent locator."""
    for part in re.split(r"\.(?=[a-z]+:)", key):
        kind, _, val = part.partition(":")
        kind_rx = _KIND_WORDS.get(kind)
        if not val or kind_rx is None:
            continue
        vals = {re.escape(val)}
        if val.isdigit():
            vals |= {re.escape(w) for w, n in
                     _ORDINALS.items() if n == int(val)}
        pat = re.compile(rf"\b{kind_rx}\s+(?:{'|'.join(sorted(vals))})"
                         rf"{_QUALIFIER_SRC}", re.IGNORECASE)
        if pat.search(masked):
            return True
    return False


def _masked_clause(text: str) -> str:
    """Quoted spans blanked position-preserving — offsets in the result
    still index the original clause."""
    return _QUOTED_SPAN_RE.sub(
        lambda mm: " " * len(mm.group(0)), text)


def _literals(text: str) -> list[tuple[str, str]]:
    pairs = [tuple(m.groups()) for m in _DONDE_DICE_RE.finditer(text)]
    pairs += [tuple(m.groups()) for m in _LITERAL_PAIRS_RE.finditer(text)]
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
    if node.kind != "p" or node.cls not in _LOCATOR_CLASSES:
        return None
    text = node.text
    if not _has_operative_verb(text):
        return None
    if _CONTAINER_RE.search(text):
        idx = text.find(":")
        if idx < 0 or not _has_operative_verb(text[idx + 1:]):
            return None
        clause = text[idx + 1:].strip()
        if _mentions_or_literals(clause) is None:
            return None
        return text[:idx + 1], clause
    if re.match(r"(?:en\s+(?:la|el|los|las)\s+\w|se\s+\w)", text,
                re.IGNORECASE) \
            and _mentions_or_literals(text) is not None:
        return "", text
    return None


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------


def split_sections(doc: DiarioDoc) -> list[Section]:
    """Split the document body at ``articulo`` headings."""
    arts = [n for n in doc.nodes if n.cls == "articulo"]
    if not arts:
        return []
    sections = []
    bounds = [a.index for a in arts] + [len(doc.nodes)]
    for i, a in enumerate(arts):
        targets = [(int(n), int(y)) for n, y in _TARGET_RE.findall(a.text)]
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
    out: list[tuple[int, int]] = []
    for n in doc.nodes[sec.node_start + 1:sec.node_end]:
        if n.kind != "p" or n.cls not in ("parrafo", "parrafo_2") \
                or _marker_parts(n.text) is not None:
            break
        text = n.text.rstrip()
        if not (text.endswith(":") or "siguientes" in text.lower()):
            break
        for m in _TARGET_RE.finditer(_QUOTED_SPAN_RE.sub("", n.text)):
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
    has_content = e > s and any(
        (doc.nodes[i].text or "").strip() or doc.nodes[i].kind == "table"
        for i in range(s, e))
    colon = op.clause_text.rstrip().endswith(":")
    pointer = bool(_CONTENT_POINTER_RE.search(op.clause_text))
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

    prev_container = False
    for i in range(sec.node_start + 1, sec.node_end):
        n = doc.nodes[i]
        if n.kind not in ("p", "blockquote"):
            continue
        parts = _marker_parts(n.text)
        if parts is None:
            unmarked = _unmarked_op(n)
            if unmarked is not None:
                prefix, clause = unmarked
                op_targets = _target_refs(_QUOTED_SPAN_RE.sub("", prefix))
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
                tail = _NON_OP_TAIL_RE.search(clause)
                zone = clause[:tail.start()] if tail else clause
                mentions = _extract_mentions(zone)
                ctx, cscope = merged_ctx()
                subjects = _compose_keys(mentions, ctx, cscope, i)
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
                        if nxt.kind == "p" and (
                                nxt.cls.startswith("sangrado")
                                or (nxt.text or "").lstrip()
                                .startswith("«")):
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
                    annex_ref=bool(_ANNEX_REF_RE.search(n.text)),
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
            if n.cls in ("parrafo", "parrafo_2") and (
                    n.text.rstrip().endswith(":")
                    or "siguientes" in n.text.lower()):
                if _ORDINAL_WORD_ITEM_RE.match(n.text):
                    # a new ordinal-word item opens a fresh sibling
                    # scope: the previous item's context dies (G2.1 §23)
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
        if n.kind == "blockquote":
            # locator clause and quoted replacement content share the node;
            # the clause keeps only the part before «, the rest is content
            qpos = text.find("«")
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

        subjects = _compose_keys(mentions, ctx, cscope, i)
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
            marker=_MARKER_RE.match(text).group("m"),
            clause_text=text,
            operation_kind=_op_kind(text),
            subjects=subjects,
            content_span=(i + 1, i + 1),
            is_container=container,
            annex_ref=bool(_ANNEX_REF_RE.search(n.text)),
            literals=_literals(n.text),
            context=ctx,
            section_index=sec.node_start,
            inline_content=inline,
            targets=[(int(a), int(b)) for a, b in _TARGET_RE.findall(
                _QUOTED_SPAN_RE.sub("", n.text))],
            section_heading=sec.heading,
            section_targets=list(sec.targets),
            context_scope=cscope,
        ))
        prev_container = container

    return ops
