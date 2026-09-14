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
from dataclasses import dataclass, field

from .sources.boe_diario import DiarioDoc, Node, normalize

PARSER_NAME = "boe_operations"
PARSER_VERSION = "v3"

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

_AMEND_VERB_RE = re.compile(
    r"se\s+(modifica\w*|sustituye\w*|suprime\w*|elimina\w*|añade\w*|"
    r"introduce\w*|incorpora\w*|incluye\w*|realiza\w*|desglosa\w*|"
    r"inserta\w*|crea\w*)|"
    r"debe\w*\s+(modificarse|sustituirse|suprimirse|eliminarse|"
    r"añadirse|introducirse|incorporarse|incluirse|insertarse|"
    r"crearse)|"
    r"queda\w*\s+redactad|pasa\w*\s+a\s+(?:ser|denominarse)|"
    r"(?:se\s+)?da\w*\s+nueva\s+redacci[oó]n|"
    r"donde\s+dice|debe\s+decir|se\s+sombrea",
    re.IGNORECASE,
)

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

_STATE_CODE_RE = re.compile(
    r"\b(FI|FC|PI|PC|PA|UEM|AVE)\s*(\d[\d.]*(?:-\s*[\d.]+)?)"
)

# estado mentions that are positional anchors, not subjects:
# "a continuación del estado FI 150-9", "las correspondientes a los
# estados FI 150 y FI 160", "por el formato de estado FI 142-1.1"
_STATE_ANCHOR_SPAN_RE = re.compile(
    r"(?:a\s+continuaci[oó]n\s+(?:del|de\s+los|de\s+las)|"
    r"correspondiente\w*\s+a|formato\s+de|entre\s+las\s+correspondientes\s+a)"
    r"\s*(?:del|de\s+los|de\s+las|los|las|el|la|l)?\s*"
    r"estados?\s+((?:FI|FC|PI|PC|PA|UEM|AVE)\s*[\d.\-]+"
    r"(?:\s*[ye,]\s*(?:(?:FI|FC|PI|PC|PA|UEM|AVE)\s*)?[\d.\-]+)*)",
    re.IGNORECASE,
)

_QUOTED_SPAN_RE = re.compile(r"«[^»]*»")
# «FI 151 Información ...» codes introduced as new states:
# "se incluyen los nuevos estados «FI 151 ...», «FI 151-1 ...»"
_QUOTED_STATE_RE = re.compile(
    r"estados?\s+(«(?:FI|FC|PI|PC|PA|UEM|AVE)[^»]*»(?:\s*[ye,]\s*"
    r"«(?:FI|FC|PI|PC|PA|UEM|AVE)[^»]*»)*)",
    re.IGNORECASE,
)
_QUOTED_CODE_RE = re.compile(
    r"«\s*(FI|FC|PI|PC|PA|UEM|AVE)\s*(\d[\d.\-]*)")

# data-file subjects: 'el fichero «Expedientes sancionadores»'
_FICHERO_RE = re.compile(r"\bficheros?\s+«([^»]+)»", re.IGNORECASE)
# parenthetical errata locators: "en la página 18938 (Estado T.17-2)"
_PAREN_STATE_RE = re.compile(r"\(\s*estados?\s+([^)]*)\)", re.IGNORECASE)
_PAREN_CODE_RE = re.compile(r"([A-ZÁÉÍÓÚÑ]{1,5})\s*\.?\s*(\d[\d.\-]*)")
# non-operative qualifier that closes an unmarked clause's subject zone:
# "se suprimen los apartados 4 y 5 ..., sin que se introduzca ningún
# cambio en los apartados 1 a 3"
_NON_OP_TAIL_RE = re.compile(r"[,;.]\s*sin\s+(?:que|perjuicio)\b",
                             re.IGNORECASE)

_PATTERNS = {
    "norma": re.compile(
        r"\bnormas?\s+(\d+|" + "|".join(_ORDINALS) + r")", re.IGNORECASE),
    "anejo": re.compile(r"\banejo\s+(\d+(?:\s*\.\s*\d+)*)", re.IGNORECASE),
    "apartado": re.compile(
        r"\bapartados?\s+([IVX]+(?:\.[A-Z0-9]+)*|"
        r"\d+(?:\s+a\s+\d+)?(?:\s*[ye,]\s*\d+(?:\s+a\s+\d+)?)*)"
        r"(?=\s*[,.:;)]|\s+(?:de|que|del|en|se|y\s+el|con|por|a)\b|$)",
        re.IGNORECASE),
    "punto": re.compile(
        r"\bpuntos?\s+(\d+)(?:\s+a\s+(\d+))?", re.IGNORECASE),
    "letra": re.compile(r"\bletras?\s+\(?([a-z])\)?", re.IGNORECASE),
    "numeral": re.compile(r"\bnumerales?\s+([ivxlcdm]+)\s*\)?", re.IGNORECASE),
    "nota": re.compile(r"\bnotas?\s+\(?([a-z])\)?", re.IGNORECASE),
    "disposicion": re.compile(
        r"\bdisposici[oó]n\s+(adicional|transitoria|final|derogatoria)\s+"
        r"(\w+)", re.IGNORECASE),
    "pagina": re.compile(r"\bp[aá]gina\s+(\d{5,6})", re.IGNORECASE),
    "indice": re.compile(r"\b[íi]ndice\b", re.IGNORECASE),
}

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
        r"se\s+(?:añade\w*|introduce\w*|incorpora\w*|incluye\w*|crea\w*)|"
        r"debe\w*\s+(?:añadirse|introducirse|incorporarse|incluirse|"
        r"insertarse|crearse)",
        re.IGNORECASE)),
    ("MODIFY", re.compile(
        r"se\s+(?:modifica\w*|realiza\w*|sombrea)|queda\w*\s+redactad|"
        r"pasa\w*\s+a\s+(?:ser|denominarse)", re.IGNORECASE)),
]


# sub-clause boundaries for per-subject verb scoping
_SEG_SPLIT_RE = re.compile(
    r"[;:]|\.\s|\s+(?:y|e|ni)\s+", re.IGNORECASE)


def subject_operation_kind(clause_text: str, locator_key: str,
                           default: str) -> str:
    """Per-subject operation kind inside a mixed-verb clause.

    Index/cuadro clauses combine verbs: "el estado FI 105 pasa a
    denominarse «...»; se eliminan los estados FI 105-1, FI 105-2". The
    clause-level kind (DELETE) must not be imputed to subjects only
    renamed. Each verb owns the segment it opens; a subject adopts the
    kind of the nearest preceding verb.
    """
    key_body = locator_key.split(":", 1)[-1]
    if not locator_key.startswith("estado:"):
        # strip sub-locators ('9.punto:46' -> '9'); keep '.' inside codes
        key_body = re.split(r"\.(?:punto|apartado|letra|numeral|nota|"
                            r"indice)\b", key_body)[0]
    if locator_key.startswith("estado:"):
        pat = re.compile(
            r"(?<![A-Z\d])" + re.escape(key_body).replace("\\ ", r"\s+")
            + r"(?![\d.\-])")
    elif locator_key.startswith(("norma:", "anejo:")):
        pat = re.compile(
            r"\b(?:norma|anejo)\s+" + re.escape(key_body) + r"(?![\d.])",
            re.IGNORECASE)
    elif locator_key.startswith("fichero:"):
        pat = re.compile(r"\bfichero\s+«?\s*" + re.escape(key_body),
                         re.IGNORECASE)
    else:
        return default
    # Mask quoted spans so «...» content never supplies verbs or clause
    # boundaries ("se sustituye «donde dice...»").
    masked = _QUOTED_SPAN_RE.sub(
        lambda mm: " " * len(mm.group(0)), clause_text)
    verbs: list[tuple[int, str]] = []
    for kind, rx in _OP_KINDS:
        verbs.extend((m.start(), kind) for m in rx.finditer(masked))
    verbs.sort()
    m = pat.search(clause_text)
    if m is None or not verbs:
        return default
    if locator_key.startswith("fichero:"):
        preceding = [v for v in verbs if v[0] <= m.start()]
        following = [v for v in verbs if v[0] > m.start()]
        # "Se <verb> el fichero «X»": the «name» is the direct object of
        # a preceding verb; a later verb opens a coordinated action on a
        # different subject ('Se modifica el fichero «X» ... y se incluye
        # un nuevo apartado' leaves X MODIFY, not ADD).
        if preceding:
            return preceding[-1][1]
        if following:
            return following[0][1]
        return default
    # Sub-clause scoping: a mention is governed by the verb of its own
    # sub-clause (split at ';', ':', '.', ' y/e/ni '). "Se sustituye el
    # estado X por el formato de estado X que se incluye en el anejo"
    # leaves X SUBSTITUTE — 'se incluye' describes the replacement, not
    # the subject. A mention in a verb-free sub-clause (the second item
    # of an enumeration, 'los estados FI 105 y FI 142-1.1') inherits the
    # nearest shared verb before its sub-clause.
    seg_start, seg_end = 0, len(masked)
    for sm in _SEG_SPLIT_RE.finditer(masked):
        if sm.end() <= m.start():
            seg_start = sm.end()
        else:
            seg_end = sm.start()
            break
    preceding = [v for v in verbs if seg_start <= v[0] < m.start()]
    following = [v for v in verbs if m.end() <= v[0] < seg_end]
    if preceding:
        return preceding[-1][1]
    if following:
        return following[0][1]
    shared = [v for v in verbs if v[0] < seg_start]
    if shared:
        return shared[-1][1]
    after = [v for v in verbs if v[0] >= seg_end]
    if after:
        return after[0][1]
    return default


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
    if _AMEND_VERB_RE.search(head) or _EN_SUBJECT_RE.search(rest):
        return True
    # bare subject container: "ii) Estado PI 2:"
    return bool(_BARE_SUBJECT_RE.match(rest) and text.rstrip().endswith(":"))


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
    quoted_states: list[str] = []
    for m in _QUOTED_STATE_RE.finditer(text):
        for qm in _QUOTED_CODE_RE.finditer(m.group(1)):
            quoted_states.append(
                _norm_state_code(qm.group(1), qm.group(2)))

    stripped = _QUOTED_SPAN_RE.sub("«»", text)

    # positional anchors are excluded by span range, not by code value
    # ("por el formato de estado FI 142-1.1" must not kill the subject
    # mention of the same code earlier in the clause)
    anchor_spans = [m.span(1)
                    for m in _STATE_ANCHOR_SPAN_RE.finditer(stripped)]

    out: dict[str, object] = {}
    for key, rx in _PATTERNS.items():
        vals = [tuple(g for g in m.groups()) for m in rx.finditer(stripped)]
        if vals:
            out[key] = vals
    estados: list[str] = []
    for m in _STATE_CODE_RE.finditer(stripped):
        code = _norm_state_code(m.group(1), m.group(2))
        if any(a <= m.start() < b for a, b in anchor_spans):
            continue
        if code not in estados:
            estados.append(code)
    for pm in _PAREN_STATE_RE.finditer(stripped):
        for cm in _PAREN_CODE_RE.finditer(pm.group(1)):
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
                  ctx: dict[str, str]) -> list[SubjectRef]:
    """Compose locator keys from clause mentions + inherited context."""
    subs: list[SubjectRef] = []

    estados = mentions.get("estado") or []
    for code in estados:
        subs.append(SubjectRef(f"estado:{code}", f"estado {code}", "ESTADO"))
    if estados:
        return subs

    ficheros = mentions.get("fichero") or []
    for name in ficheros:
        subs.append(SubjectRef(f"fichero:{name}", f"fichero {name}",
                               "FICHERO"))
    if ficheros:
        return subs

    def first(key):
        v = mentions.get(key)
        return v[0] if v else None

    norma = first("norma")
    norma_n = None
    if norma:
        norma_n = _ordinal_num(str(norma[0]))
    if norma_n is None and "norma" in ctx:
        norma_n = int(ctx["norma"])

    anejo = first("anejo")
    anejo_n = None
    if anejo:
        anejo_n = re.sub(r"\s+", "", str(anejo[0]))
    if anejo_n is None:
        anejo_n = ctx.get("anejo")

    disp = first("disposicion")
    disp_key = None
    if disp:
        tipo = str(disp[0]).lower()
        ordinal = str(disp[1]).lower()
        disp_key = f"disp:{tipo}.{ordinal}"
        # a sub-locator under a disposición composes with it
        # ('apartado 1 de la disposición transitoria primera'); the bare
        # disposición key is emitted only when it is itself the subject
        if not any(mentions.get(k) for k in
                   ("apartado", "punto", "letra", "numeral", "nota")):
            subs.append(SubjectRef(
                disp_key, f"disposición {tipo} {ordinal}", "DISPOSICION"))

    indice = mentions.get("indice")
    if indice is not None and anejo_n:
        subs.append(SubjectRef(
            f"anejo:{anejo_n}.indice", f"índice del anejo {anejo_n}",
            "INDICE"))

    punto = first("punto")
    punto_keys: list[str] = []
    if punto:
        for p in mentions.get("punto") or []:
            lo = int(p[0])
            hi = int(p[1]) if len(p) > 1 and p[1] else lo
            for v in range(lo, hi + 1):
                if disp_key is not None:
                    punto_keys.append(f"{disp_key}.punto:{v}")
                elif anejo_n:
                    punto_keys.append(f"anejo:{anejo_n}.punto:{v}")
                elif norma_n:
                    punto_keys.append(f"norma:{norma_n}.punto:{v}")
                else:
                    punto_keys.append(f"punto:{v}")

    apartado = first("apartado")
    letra = first("letra")
    numeral = first("numeral")
    nota = first("nota")

    if apartado is not None:
        raw = str(apartado[0])
        nums = [str(v) for v in _expand_numlist(raw)]
        values = nums or [raw]
        for n in values:
            if disp_key is not None:
                key = f"{disp_key}.apartado:{n}"
            elif norma_n is not None:
                key = f"norma:{norma_n}.apartado:{n}"
            elif anejo_n is not None and n.isdigit():
                # numbered units inside an anejo are its "puntos" even
                # when the clause calls them "apartado"
                key = f"anejo:{anejo_n}.punto:{n}"
            elif anejo_n is not None:
                key = f"anejo:{anejo_n}.apartado:{n}"
            else:
                key = f"apartado:{n}"
            if letra is not None:
                key += f".letra:{letra[0]}"
            if numeral is not None:
                key += f".numeral:{numeral[0].lower()}"
            if nota is not None:
                key += f".nota:{nota[0]}"
            subs.append(SubjectRef(key, key.replace(":", " "), "APARTADO"))
    elif punto_keys:
        for key in punto_keys:
            if letra is not None:
                key += f".letra:{letra[0]}"
            subs.append(SubjectRef(key, key.replace(":", " "), "PUNTO"))
    elif letra is not None and norma_n is not None:
        subs.append(SubjectRef(f"norma:{norma_n}.letra:{letra[0]}",
                               f"norma {norma_n} letra {letra[0]}",
                               "APARTADO"))
    elif numeral is not None and norma_n is not None:
        subs.append(SubjectRef(
            f"norma:{norma_n}.numeral:{numeral[0].lower()}",
            f"norma {norma_n} numeral {numeral[0]}", "APARTADO"))
    elif nota is not None and norma_n is not None:
        subs.append(SubjectRef(f"norma:{norma_n}.nota:{nota[0]}",
                               f"norma {norma_n} nota {nota[0]}", "NOTA"))

    if not subs:
        if norma_n is not None and anejo_n is not None:
            subs.append(SubjectRef(f"anejo:{anejo_n}", f"anejo {anejo_n}",
                                   "ANEJO"))
        elif anejo_n is not None:
            subs.append(SubjectRef(f"anejo:{anejo_n}", f"anejo {anejo_n}",
                                   "ANEJO"))
        elif norma_n is not None:
            subs.append(SubjectRef(f"norma:{norma_n}", f"norma {norma_n}",
                                   "NORMA"))
        elif ctx.get("subject"):
            key = ctx["subject"]
            subs.append(SubjectRef(key, key.replace(":", " "),
                                   key.split(":", 1)[0].upper()))

    return subs


def _expand_numlist(raw: str) -> list[int]:
    """Expand the numeric enumerations the corpus demonstrates:
    '17 a 20' → [17..20]; '3, 6 y 7' / '13, 18 y 19' → each element.
    A non-numeric capture (e.g. the anejo path 'II.B.2') returns [].
    No linguistic range forms beyond explicit digits."""
    out: list[int] = []
    for part in re.split(r",|\s+[ye]\s+", raw):
        part = part.strip()
        m = re.match(r"^(\d+)\s+a\s+(\d+)$", part)
        if m:
            out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.isdigit():
            out.append(int(part))
        elif part:
            return []
    return out


def _context_update(ctx: dict[str, str],
                    mentions: dict[str, object]) -> dict[str, str]:
    new = dict(ctx)
    norma = mentions.get("norma")
    if norma:
        n = _ordinal_num(str(norma[0][0]))
        if n is not None:
            new["norma"] = str(n)
    anejo = mentions.get("anejo")
    if anejo:
        new["anejo"] = re.sub(r"\s+", "", str(anejo[0][0]))
    pagina = mentions.get("pagina")
    if pagina:
        new["pagina"] = str(pagina[0][0])
    estados = mentions.get("estado")
    if estados and len(estados) == 1:
        new["estado"] = estados[0]
    return new


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
    if not _AMEND_VERB_RE.search(text):
        return None
    if _CONTAINER_RE.search(text):
        idx = text.find(":")
        if idx < 0 or not _AMEND_VERB_RE.search(text[idx + 1:]):
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


def parse_operations(doc: DiarioDoc,
                     target_ref: tuple[int, int] | None) -> OpsResult:
    """Parse amendment operations targeting ``target_ref``=(num, year).

    ``target_ref=None`` matches every section (used for the correction
    document whose preamble names the target in prose, not headings).
    A section belongs to the target when its heading or leading
    preamble names it; in sections naming no circular at all, an
    operation that names the target in its own clause is still kept.
    """
    sections = split_sections(doc)
    target_sections: list[Section] = []
    out_of_target = 0

    selected: list[tuple[Section, list[Operation]]] = []
    if sections:
        for s in sections:
            for ref in _preamble_targets(doc, s):
                if ref not in s.targets:
                    s.targets.append(ref)
            if target_ref is None or target_ref in s.targets:
                target_sections.append(s)
                selected.append((s, _parse_section(doc, s)))
            elif not s.targets and target_ref is not None:
                # unnamed section: an inline ref attributes the op only
                # when its subjects are named entities owned by that
                # circular ('Se modifica el fichero «X» ... que consta
                # en el anejo de la Circular N/AAAA'). A structural
                # locator plus an inline ref is a cross-reference —
                # e.g. transitoria items citing 'los apartados 1 a 9 de
                # la disposición transitoria primera de la Circular X'.
                kept = [op for op in _parse_section(doc, s)
                        if target_ref in op.targets and op.subjects
                        and all(sub.kind == "FICHERO"
                                for sub in op.subjects)]
                if kept:
                    selected.append((s, kept))
    else:
        # no articulo structure (e.g. correction orders): the whole body is
        # one implicit section; caller must ensure target naming upstream
        target_sections = [Section("", 0, len(doc.nodes), [])]
        selected.append((target_sections[0],
                         _parse_section(doc, target_sections[0])))

    # count marker+verb paragraphs outside target sections for auditing
    target_ranges = [(s.node_start, s.node_end) for s in target_sections]
    for n in doc.nodes:
        if _is_locator(n) and not any(
                a <= n.index < b for a, b in target_ranges):
            out_of_target += 1

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

    return OpsResult(operations, sections, out_of_target)


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
    base_ctx: dict[str, str] = {}
    # open locator levels, outermost first: [(marker_style, ctx), ...]
    levels: list[tuple[str, dict[str, str]]] = []
    top_alpha = 0  # value of the last top-level lettered item (a=1, aa=27)

    def merged_ctx() -> dict[str, str]:
        c = dict(base_ctx)
        for _, lctx in levels:
            c.update(lctx)
        return c

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
                    base_ctx = _context_update(
                        base_ctx, _extract_mentions(prefix))
                tail = _NON_OP_TAIL_RE.search(clause)
                zone = clause[:tail.start()] if tail else clause
                mentions = _extract_mentions(zone)
                ctx = merged_ctx()
                subjects = _compose_keys(mentions, ctx)
                page = mentions.get("pagina")
                page_ref = int(str(page[0][0])) if page else (
                    int(ctx["pagina"]) if "pagina" in ctx else None)
                if page_ref:
                    subjects = [SubjectRef(s.locator_key, s.label, s.kind,
                                           s.page_ref or page_ref)
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
                ))
                continue
            # preamble context setter, e.g. "Se introducen los siguientes
            # cambios en el anejo 9 ... :" before lettered point clauses
            if n.cls in ("parrafo", "parrafo_2") and (
                    n.text.rstrip().endswith(":")
                    or "siguientes" in n.text.lower()):
                base_ctx = _context_update(
                    base_ctx, _extract_mentions(n.text))
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
            levels.append((child_style, {}))
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
                levels[0] = ("alpha", {})
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
                    levels.append((style, {}))   # deeper, unmarked level
                    if len(levels) == 1 and style == "alpha":
                        top_alpha = aval
                else:
                    # an ambiguous marker adopts the style of the level
                    # it replaces (roman children vs. top-level alpha)
                    adopted = levels[depth][0]
                    del levels[depth:]
                    resolved = adopted if style == "amb" else style
                    levels.append((resolved, {}))
                    if depth == 0 and resolved == "alpha":
                        top_alpha = aval

        levels[-1] = (levels[-1][0],
                      _context_update(merged_ctx(), mentions))
        ctx = merged_ctx()

        subjects = _compose_keys(mentions, ctx)
        if subjects:
            # children clauses without own subject inherit this level's
            levels[-1][1]["subject"] = subjects[0].locator_key
        page = mentions.get("pagina")
        page_ref = int(str(page[0][0])) if page else (
            int(ctx["pagina"]) if "pagina" in ctx else None)
        if page_ref:
            subjects = [SubjectRef(s.locator_key, s.label, s.kind,
                                   s.page_ref or page_ref)
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
        ))
        prev_container = container

    return ops
