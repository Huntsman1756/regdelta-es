"""CNMV Circular source profile (BOE/CNMV) — immutable data only.

PORT-CNMV-1 minimal profile. Every value below is either:

  * shared BOE-platform vocabulary evidenced in DEV bytes
    (``evidence/port-cnmv/split-v2/dev/**``): node classes, signature
    block, ELI scheme, capture layout, ``<referencias>`` containers,
    correction ``palabra`` words; or
  * generic Spanish legislative vocabulary evidenced in DEV text:
    ordinals, months, markers, operative verbs, locator spellings
    ("Norma N.º", "ANEXO", "apartado", "letra", ...); or
  * a never-match pattern / empty container where DEV shows no
    evidence — the falsification journal then records the gap as
    PROFILE_DATA_MISSING instead of guessing.

Deliberately NOT registered in ``profiles/__init__.py``: the probe
runner imports this module and calls ``use_profile("cnmv-circular")``
explicitly, so default BdE single-profile behavior is unchanged.
"""

from __future__ import annotations

import re

from ..profile import (
    AnnexStateGrammar, ApplicabilityLanguage, DocumentModel,
    FicheroGrammar, IdentityReference, LocatorGrammar, OperativeGrammar,
    SourceDescriptors, SourceProfile, TextNormalization,
    register_profile)

# never-match: the honest value for "no DEV evidence for this pattern"
_NEVER = r"(?!x)x"


def _never() -> re.Pattern:
    return re.compile(_NEVER)


# ---------------------------------------------------------------------------
# F1 document_model — node-stream vocabulary (produced by sources/boe_*)
#
# DEV evidence: parsed diario XML emits classes articulo, anexo,
# anexo_num, anexo_tit, parrafo, parrafo_2, sangrado, cita, tabla,
# seccion, centro_*; every document ends with "Madrid, N de mes de
# YYYY."; bare annex headings spell "ANEXO"/"ANEXOS" (never "ANEJO").
# ---------------------------------------------------------------------------

_DOCUMENT_MODEL = DocumentModel(
    kinds={"paragraph": "p", "blockquote": "blockquote",
           "table": "table"},
    classes={"articulo": "articulo", "anexo": "anexo",
             "capitulo_num": "capitulo_num",
             "capitulo_tit": "capitulo_tit", "anexo_tit": "anexo_tit",
             "parrafo": "parrafo", "parrafo_2": "parrafo_2"},
    class_prefixes={"centro": "centro", "sangrado": "sangrado"},
    locator_classes=frozenset(
        {"parrafo", "parrafo_2", "sangrado", "cita"}),
    boundary={
        "signature": re.compile(r"^Madrid, \d+ de \w+ de \d{4}"),
    },
    annex_literal="ANEXO",
)

# ---------------------------------------------------------------------------
# F2 text_normalization — BOE conventions; «» quoting is present in
# 25/26 DEV diario documents.
# ---------------------------------------------------------------------------

_TEXT_NORMALIZATION = TextNormalization(
    form="NFKD",
    strip_combining=True,
    fold="lower",
    collapse_ws=True,
    quote_open="«",
    quote_close="»",
    quoted_span=re.compile(r"«[^»]*»"),
)

# ---------------------------------------------------------------------------
# F3 locator_grammar — DEV-evidenced locators only.
#
# Observed: "Norma 1.º"/"Norma primera" headings (node class articulo),
# "Norma adicional/transitoria/derogatoria/final" (CNMV disposicion
# equivalents), "ANEXO"/"ANEXO I"/"ANEXO 0" (arabic + roman), and text
# references "norma 20", "anexo 1", "anexos V y VI", "apartado",
# "letra", "punto", "numeral", "nota", "sección", "artículo",
# "capítulo", "disposición", "página". "anejo", "estado" and "fichero"
# are NOT evidenced in CNMV DEV bytes and stay disabled.
# ---------------------------------------------------------------------------

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

_ORDINAL_WORDS = {
    "1": "primera", "2": "segunda", "3": "tercera", "4": "cuarta",
    "5": "quinta", "6": "sexta", "7": "septima", "8": "octava",
    "9": "novena", "10": "decima", "11": "undecima", "12": "duodecima",
    "13": "decima tercera", "14": "decima cuarta", "15": "decima quinta",
    "16": "decima sexta", "17": "decima septima", "18": "decima octava",
    "19": "decima novena", "20": "vigesima",
}

# Digit + flying ordinal marker head forms observed in DEV
# ("Norma 5.ª"): markers .ª ª .º º over the DEV-observed norma range
# 1..62. Kept out of _ORDINALS so _ORD_SEQ stays a word alternation.
_ORDINALS_MARKED = {
    f"{n}{s}": n for n in range(1, 63) for s in (".ª", "ª", ".º", "º")}

_ROMAN_NUM = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
              "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x",
              "11": "xi", "12": "xii", "13": "xiii", "14": "xiv",
              "15": "xv", "16": "xvi", "17": "xvii", "18": "xviii",
              "19": "xix", "20": "xx"}

_NUM_SEQ = r"\d+(?:\s*\.\s*\d+)*"
_ROMAN_SEQ = r"[IVX]+(?:\.[A-Z0-9]+)*"
_ORD_SEQ = "|".join(_ORDINALS)
_ENUM_SEP = r"(?:\s*(?:a|al|,|y|e)\s+)"

# 'normas 6 y 58', 'los anexos V y VI', 'anexos 0 y 1' — enumerations
# are evidenced in DEV <referencias> and operative text.
_DECLARATIONS = {
    "norma": re.compile(
        r"\bnormas?\s+((?:\d+[.ªº°]*\.?|" + _ORD_SEQ + r")"
        r"(?:" + _ENUM_SEP + r"(?:\d+[.ªº°]*\.?|" + _ORD_SEQ + r"))*)"
        r"(?=\s*[,.:;)(«–—-]|\s+(?:de|que|del|en|se|con|por|sin|sobre|"
        r"para|donde|queda\w*|relativ[ao]|referid[ao]|bis|"
        r"y\s+la|y\s+el|y\s+los|y\s+las)\b|\s+[A-ZÁÉÍÓÚÑ]|$)",
        re.IGNORECASE),
    # the canonical annex locator kind is "anejo"; CNMV spells it
    # "anexo" (incl. unnumbered qualified forms "Anexo bis")
    "anejo": re.compile(
        r"\banexos?\s+((?:" + _NUM_SEQ + r"|" + _ROMAN_SEQ
        + r"|bis|ter|qu[aá]ter)"
        r"(?:" + _ENUM_SEP + r"(?:" + _NUM_SEQ + r"|" + _ROMAN_SEQ
        + r"))*)"
        r"(?=\s*[,.:;)(«]|\s+(?:de|que|del|en|se|con|por|sin|sobre|donde"
        r"|y\s+el|a\s+la)\b|$)",
        re.IGNORECASE),
    # CNMV norma subdivisions spell "número" where BdE uses "apartado"
    "apartado": re.compile(
        r"\b(?:apartado|n[uú]mero)s?\s+((?:" + _NUM_SEQ + r"|"
        + _ROMAN_SEQ + r")"
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
    "numeral": re.compile(r"\bnumerales?\s+([ivxlcdm]+)\s*\)?",
                          re.IGNORECASE),
    "nota": re.compile(r"\bnotas?\s+\(?([a-z])\)?", re.IGNORECASE),
    # CNMV disposiciones spell "Norma adicional/transitoria/..." —
    # "Norma adicional bis" -> disp:adicional.bis
    "disposicion": re.compile(
        r"\b(?:disposici[oó]n|norma)\s+"
        r"(adicional|transitoria|final|derogatoria)\s+"
        r"(" + _ORD_SEQ + r"|\d+[.ªº°]*\.?|bis|ter|qu[aá]ter|"
        r"[uú]nic[oa])\b",
        re.IGNORECASE),
    "pagina": re.compile(r"\bp[aá]gina\s+(\d{3,6})", re.IGNORECASE),
    "indice": re.compile(r"\b[íi]ndice\b", re.IGNORECASE),
    # "La Sección Quinta ... queda redactada" — declared so the
    # locator is visible in the mention record even where the composer
    # cannot yet compose a seccion: subject (journaled #7)
    "seccion": re.compile(
        r"\bsecci[oó]n\s+(" + _ORD_SEQ + r"|\d+|[ivxlcdm]+)\b",
        re.IGNORECASE),
}

_LOCATOR_GRAMMAR = LocatorGrammar(
    enabled_kinds=frozenset({
        "norma", "anexo", "anejo", "articulo", "capitulo", "seccion",
        "disp", "disposicion", "pagina", "apartado", "punto", "letra",
        "numeral", "nota", "indice", "estado",
    }),
    ordinals={**_ORDINALS, **_ORDINALS_MARKED},
    ordinal_words=_ORDINAL_WORDS,
    roman=_ROMAN_NUM,
    ordinal_item=re.compile(
        r"^(primer[oa]?|segund[oa]|tercer[oa]?|tercer|cuart[oa]|quint[oa]|"
        r"sext[oa]|s[eé]ptim[oa]|octav[oa]|noven[oa]|d[eé]cim[oa]|"
        r"und[eé]cim[oa]?|duod[eé]cim[oa]|uno|una|dos|tres|cuatro|cinco|"
        r"seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince)\."
        r"\s", re.IGNORECASE),
    clause_marker=re.compile(
        r"^(?P<m>(?:[a-z]{1,2}\)|[ivxlcdm]+\s*[.)]|\d+\s*[.)]))\s*",
        re.IGNORECASE),
    marker_amb_values=frozenset(
        {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
         "xi", "xii", "xiii", "xiv", "xv"}),
    declarations=_DECLARATIONS,
    enum_kinds=("norma", "anejo", "apartado", "punto"),
    numlist_split=r"\s*(?:,|y|e)\s+",
    numlist_range=re.compile(r"(\d+)\s+(?:a|al)\s+(\d+)"),
    numlist_atom=(
        r"\d+(?:\.\d+)*[.ªº°]*\.?|[IVX]+(?:\.[A-Z0-9]+)*|"
        r"bis|ter|qu[aá]ter|" + _ORD_SEQ),
    expand_split=r",|\s+[ye]\s+",
    expand_range=re.compile(r"^(\d+)\s+(?:a|al)\s+(\d+)$"),
    expand_atom=re.compile(r"\d+(?:\.\d+)+"),
    letra_list=re.compile(
        r"\bletras?\s+((?:\(?[a-z]\)?\s*(?:,|\sy\s|\se\s|\sa\s))*"
        r"\(?[a-z]\)?)", re.IGNORECASE),
    letra_item=re.compile(r"\(?[a-z]\)?"),
    head_forms={
        "norma": ("norma",),
        "anexo": ("anexo",),
        "anejo": ("anexo",),
        # CNMV disposiciones are headed "Norma adicional/transitoria/
        # derogatoria/final" — the disp locator spells "norma"
        "disp": ("norma",),
        "articulo": ("articulo",),
        "estado": ("estado", "modelo"),
    },
    articulo_head=re.compile(
        r"^(?:\[[^\]]*\]\s*)?([A-Za-zÁÉÍÓÚáéíóúñü]+)\s+(\S+)",
        re.IGNORECASE),
    norma_head=r"^(?:\[[^\]]*\]\s*)?norma\s+{alt}\b",
    # CNMV disposicion head: "Norma transitoria primera" etc.
    disposicion_head=(
        r"^(?:\[[^\]]*\]\s*)?norma\s+{tipo}\s+{ord}\b"),
    anejo_head=r"^anexo\s+{num}\b",
    anejo_boundary=re.compile(
        r"^anexos?\s+\S|^anexos?\b|madrid\s*,", re.IGNORECASE),
    presence={
        "apartado": (r"^{v}\s*\.\s", r"\bapartados?\s+{v}\b"),
        "punto": (r"^{v}\s*\.\s", r"\bpuntos?\s+{v}\b"),
        "letra": (r"^\(?{v}\)", r"\bletras?\s+\(?{v}\)?"),
        "nota": (r"^\(?{v}\)", r"\bnotas?\s+\(?{v}\)?"),
        "numeral": (r"^{v}\s*[.)]",),
        "_default": (r"\b{v}\b",),
    },
    markers={
        "numeric": re.compile(
            r"^(?:\d+\.|\d{1,3}(?:\.\d+)*\s+[A-ZÁÉÍÓÚÑ¿«(])"),
        "letra": re.compile(r"^[a-zA-Z]\)"),
        "sibling": re.compile(
            r"^(?:\d+\.|[a-zA-Z]\)|[ivxlcdmIVXLCDM]+\s*[.)]"
            r"|\d{1,3}(?:\.\d+)*\s+[A-ZÁÉÍÓÚÑ¿«(])"),
    },
    level_boundary={
        "apartado": ("numeric",),
        "punto": ("numeric",),
        "letra": ("numeric", "letra"),
    },
    default_boundary="sibling",
    sub_markers={
        "apartado": (r"^{v}(?!\d)(?:\s*\.|\s+[A-ZÁÉÍÓÚÑ¿«(]|$)", 0),
        "punto": (r"^{v}(?!\d)(?:\s*\.|\s+[A-ZÁÉÍÓÚÑ¿«(]|$)", 0),
        "letra": (r"^{v}\s*\)", 0),
        "nota": (r"^[«(]+\s*\(?{v}\)?", re.IGNORECASE),
        "numeral": (r"^{v}\s*[.)]", re.IGNORECASE),
    },
    sub_markers_compound={
        "apartado": (r"^{v}(?!\.\d|\w)(?:\s*\.|\s|$)", 0),
        "punto": (r"^{v}(?!\.\d|\w)(?:\s*\.|\s|$)", 0),
    },
    value_continuation=re.compile(r"[\dA-ZÁÉÍÓÚÑ]"),
    kind_words={
        "apartado": r"apartados?", "letra": r"letras?",
        "punto": r"puntos?", "numeral": r"numerales?",
        "nota": r"notas?", "norma": r"normas?",
        "anexo": r"anexos?", "anejo": r"anexos?", "seccion": r"secciones?",
        "indice": r"[íi]ndices?", "estado": r"estados?",
    },
    kinded_tail=re.compile(
        r"\.(?:punto|apartado|letra|numeral|nota|indice|estado|"
        r"norma|anexo|anejo|disp|disposicion|seccion|pagina):"),
    coverage_heads=("estado", "punto", "apartado", "letra",
                    "numeral", "nota", "indice"),
)

# ---------------------------------------------------------------------------
# F6 annex_state — CNMV DEV shows no estado-code families and no
# ficheros: families empty, all code patterns never-match. Sparse
# "PC1"/"PI01"-like tokens exist in DEV text but are not evidenced as
# a code family; if they matter the journal will say so.
# ---------------------------------------------------------------------------

_FICHERO = FicheroGrammar(
    word="fichero",
    connectors=frozenset(
        {"a", "ante", "con", "de", "del", "e", "el", "en", "la", "las",
         "los", "para", "por", "sobre", "y"}),
    head=_never(),
    head_value=_never(),
    boundary=_never(),
    subject=_never(),
    dash_collapse=re.compile(r"\s*-\s*"),
    note_strip=re.compile(r"\s*\(\s*\*+\s*\)\s*$"),
    token_split=r"[^\wáéíóúñü]+",
    token_split_norm=r"[^\w]+",
)

# Estado-code families observed in DEV (clause text + legacy PDF
# headers: ESTADO A22, ESTADO CA1, ESTADO G02-, ESTADO P.2., …).
# Longest-first so multi-letter families win alternation order.
_STATE_FAMS = ("SEAFI", "BCFT", "SEAF", "SGE", "PC", "CS", "CA", "GA",
               "CR", "RM", "LI", "G", "R", "M", "T", "A", "P")
_STATE_ALT = "|".join(_STATE_FAMS)
# letter-spaced variant for pdf text layers ('T 1 6', 'S E A F I 1')
_STATE_SPACED = "|".join(r"\s*".join(f) for f in _STATE_FAMS)

_ANNEX_STATE = AnnexStateGrammar(
    state_code_families=_STATE_FAMS,
    index_code_threshold=10,
    fichero=_FICHERO,
    patterns={
        "state_code": re.compile(
            r"\b(" + _STATE_ALT + r")\s*(\d[\d.]*(?:-\s*[\d.]+)?)"),
        "state_anchor_span": re.compile(
            r"(?:a\s+continuaci[oó]n\s+(?:del|de\s+los|de\s+las)|"
            r"correspondiente\w*\s+a|formato\s+de|"
            r"entre\s+las\s+correspondientes\s+a)"
            r"\s*(?:del|de\s+los|de\s+las|los|las|el|la|l)?\s*"
            r"estados?\s+((?:" + _STATE_ALT + r")\s*[\d.\-]+"
            r"(?:\s*[ye,]\s*(?:(?:" + _STATE_ALT + r")\s*)?"
            r"[\d.\-]+)*)",
            re.IGNORECASE),
        "quoted_state": re.compile(
            r"estados?\s+(«(?:" + _STATE_ALT + r")[^»]*»"
            r"(?:\s*[ye,]\s*«(?:" + _STATE_ALT + r")[^»]*»)*)",
            re.IGNORECASE),
        "quoted_code": re.compile(
            r"«\s*(" + _STATE_ALT + r")\s*(\d[\d.\-]*)"),
        "paren_state": re.compile(
            r"\(\s*estados?\s+([^)]*)\)", re.IGNORECASE),
        "paren_code": re.compile(
            r"(" + _STATE_ALT + r")\s*\.?\s*(\d[\d.\-]*)"),
        # CNMV pdf page headers always carry the (letter-spaced) word
        # ESTADO: "E S T A D O   T 1", "ESTADO G02-", "ESTADO P.2.".
        # Requiring it keeps single-letter families (A, P) from matching
        # dates like "a 31 de diciembre" in spaced text.
        "pdf_page_code": re.compile(
            r"\bE\s*S\s*T\s*A\s*D\s*O[S]?\s+(" + _STATE_SPACED +
            r"|A\s*N\s*E\s*X\s*O)\s*\.?\s*(\d[\d .\-]*\d|\d)"),
        "estados_list": re.compile(
            r"estados ((?:[A-Z]{1,5} \d+(?:[\-.]\d+(?:\.\d+)?)?"
            r"(?:,? y? )?)+)"),
        "estado_token": re.compile(
            r"[A-Z]{1,5} \d+(?:[\-.]\d+(?:\.\d+)?)?"),
        "page_num": re.compile(r"P[áa]g\.\s*([\d\s]+)"),
        "anejo_head": re.compile(
            r"A\s*N\s*E\s*X\s*O\s+(\d+(?:\s*\.\s*\d+)*)"),
        "annex_code_header": re.compile(
            r"^(" + _STATE_ALT + r")\s+(\d[\d.\-]*)"),
    },
)

# ---------------------------------------------------------------------------
# F4 operative_grammar — DEV-evidenced verbs: modifica/n, añade/n,
# sustituye/n, suprime/n, deroga/n, queda redactad*/modificad*/
# sustituid*/derogad*/definidas.
# ---------------------------------------------------------------------------

_OPERATIVE_GRAMMAR = OperativeGrammar(
    amend_verb_active=re.compile(
        r"se\s+(?:modifica\w*|sustituye\w*|suprime\w*|elimina\w*|"
        r"añade\w*|introduce\w*|incorpora\w*|deroga\w*|"
        r"inserta\w*|crea\w*)",
        re.IGNORECASE),
    amend_verb_passive=re.compile(
        r"debe\w*\s+(?:modificarse|sustituirse|suprimirse|eliminarse|"
        r"añadirse|introducirse|incorporarse|insertarse|derogarse|"
        r"crearse)|"
        r"queda\w*\s+(?:redactad|modificad|sustituid|derogad|definid)|"
        r"pasa\w*\s+a\s+(?:ser|denominarse)|"
        r"(?:se\s+)?da\w*\s+nueva\s+redacci[oó]n|"
        r"donde\s+dice|debe\s+decir|se\s+sombrea",
        re.IGNORECASE),
    subordinator_tail=re.compile(
        r"(?:^|[,;:]\s*|\s)"
        r"(?:que|por\s+(?:el|la|los|las)\s+que|cuy[ao]s?|"
        r"donde|mediante|como|según|conforme|si|cuando|mientras|"
        r"aunque|porque|en\s+la\s+medida\s+en\s+que)\s*$",
        re.IGNORECASE),
    en_subject=re.compile(
        r"^en\s+(?:la|el|los|las)\s+(norma|anexo|estado|estados|"
        r"disposición|apartado|punto|letra|numeral|nota|p[aá]gina)\b",
        re.IGNORECASE),
    bare_subject=re.compile(
        r"^(estado|estados|anexo|norma|disposición|apartado|punto|"
        r"sección)\s+\S",
        re.IGNORECASE),
    content_pointer=re.compile(
        r"queda\w*\s+(?:redactad|modificad|sustituid)|"
        r"por\s+(?:el|los|la|las)\s+que\s+figura|"
        r"por\s+la\s+siguiente|por\s+las\s+siguientes|por\s+el\s+"
        r"siguiente|por\s+los\s+siguientes|con\s+el\s+siguiente|"
        r"con\s+la\s+siguiente|por\s+«|"
        r"donde\s+dice|debe\s+decir|siguiente\s+redacción|"
        r"siguiente\s+tenor|siguiente\s+texto|como\s+sigue|"
        r"con\s+arreglo\s+a|siguientes?\s+términos|"
        r"por\s+la\s+que\s+figura",
        re.IGNORECASE),
    container=re.compile(
        r"siguientes\s+modificaciones|siguientes\s+cambios",
        re.IGNORECASE),
    literal_pairs=re.compile(
        r"«([^»]+)»\s*(?:,?\s*se\s+(?:sustituye|sustituyen|modifica|"
        r"cambia)\w*\s+por|por)\s*«([^»]+)»"),
    donde_dice=re.compile(
        r"donde\s+dice:\s*«([^»]+)»\s*,?\s*debe\s+decir:\s*«([^»]+)»",
        re.IGNORECASE),
    annex_ref=re.compile(
        r"en\s+el\s+anexo\s+de\s+esta\s+circular|"
        r"(?:figura\w*|incluye\w*|recoge\w*)\s+en\s+el\s+anexo\b",
        re.IGNORECASE),
    op_kinds=(
        ("SUBSTITUTE", re.compile(
            r"se\s+sustituye\w*|debe\w*\s+sustituirse|"
            r"queda\w*\s+sustituid|"
            r"(?:se\s+)?da\w*\s+nueva\s+redacci[oó]n", re.IGNORECASE)),
        ("DELETE", re.compile(
            r"se\s+(?:suprime\w*|elimina\w*|deroga\w*)|"
            r"queda\w*\s+derogad|"
            r"debe\w*\s+(?:suprimirse|eliminarse|derogarse)",
            re.IGNORECASE)),
        ("ADD", re.compile(
            r"se\s+(?:añade\w*|introduce\w*|incorpora\w*|crea\w*)|"
            r"debe\w*\s+(?:añadirse|introducirse|incorporarse|"
            r"insertarse|crearse)",
            re.IGNORECASE)),
        ("MODIFY", re.compile(
            r"se\s+(?:modifica\w*|realiza\w*|sombrea)|queda\w*\s+"
            r"(?:redactad|modificad|definid)|"
            r"pasa\w*\s+a\s+(?:ser|denominarse)",
            re.IGNORECASE)),
    ),
    segment_split=re.compile(
        r"[;:]|\.\s|\s+(?:y|e|ni)\s+", re.IGNORECASE),
    non_op_tail=re.compile(r"[,;.]\s*sin\s+(?:que|perjuicio)\b",
                           re.IGNORECASE),
    root_families=("norma", "anejo", "disposicion"),
    sub_scope=re.compile(
        r"\b(?:apartado|letra|punto|numeral|"
        r"nota|secci[oó]n|cuadro|tabla|p[aá]rrafo|[íi]ndice|fila|"
        r"columna)\b",
        re.IGNORECASE),
    qualifier_src=(
        r"(?:\.\s*[a-z]\b|\s+(?:bis|ter|qu[aá]ter|quinquies|sexies|"
        r"septies|octies|nonies|decies)\b)"),
    # CNMV operative items open with ordinal words ("Uno. La Norma
    # 11.ª queda redactada del siguiente modo:") — the item itself is
    # the amendment clause. Container announcements still fail
    # _unmarked_op's post-colon verb check and stay context setters.
    # Journaled PROFILE_DATA_MISSING #7.
    unmarked_opener=re.compile(
        r"(?:en\s+(?:la|el|los|las)\s+\w|se\s+\w|"
        r"(?:primer[oa]?|segund[oa]|tercer[oa]?|tercer|cuart[oa]|"
        r"quint[oa]|sext[oa]|s[eé]ptim[oa]|octav[oa]|noven[oa]|"
        r"d[eé]cim[oa]|und[eé]cim[oa]?|duod[eé]cim[oa]|uno|una|dos|"
        r"tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|"
        r"trece|catorce|quince)\.\s)",
        re.IGNORECASE),
    container_close=re.compile(
        r"se\s+(?:modifican?|realizan?|efectúan?)\s*:$", re.IGNORECASE),
    siguientes="siguientes",
)

# ---------------------------------------------------------------------------
# F5 identity_reference — CNMV issuer forms evidenced in DEV titles:
# "Circular N/YYYY, de D de mes, de la Comisión Nacional del Mercado
# de Valores" and refs "la Circular 7/2008, de 26 de noviembre",
# "Circular 1/2010 de 28 de julio de la CNMV".
# ---------------------------------------------------------------------------

_IDENTITY_REFERENCE = IdentityReference(
    target_ref=re.compile(
        r"Circular\s+(?:de\s+la\s+Comisi[oó]n\s+Nacional\s+del\s+"
        r"Mercado\s+de\s+Valores\s+|de\s+la\s+CNMV\s+)?(\d+)\s*/\s*"
        r"(\d{4})",
        re.IGNORECASE),
    circular_ref=re.compile(
        r"Circular\s+(\d+)\s*/\s*(\d{4})", re.IGNORECASE),
    fichero_owner=_never(),
    eli_circular=re.compile(r"/cir/(\d{4})/(\d{2})/(\d{2})/(\d+)"),
    eli_corrigendum_path="/corrigendum/",
    boe_id=re.compile(r"^BOE-[A-Z]-\d{4}-\d+$"),
    circular_query=re.compile(
        r"^circular\s+(\d+)/(\d{4})$", re.IGNORECASE),
    correction_palabras=("CORREG", "CORREC"),
    correction_primary_prefix="CORRECCION DE ERRORES",
    correction_secondary_prefix="CORRIGE ERRORES",
    correction_secondary_contains="CORRECCION",
    corrigendum_marker="CORRECCI",
)

# ---------------------------------------------------------------------------
# F7 applicability_language — CNMV disposiciones are headed "Norma
# transitoria/final/adicional/derogatoria"; temporal markers limited
# to generic Spanish forms seen in DEV ("entrará en vigor", "será de
# aplicación", "a partir de").
# ---------------------------------------------------------------------------

_FREQ_WORDS = r"(?:mensual|trimestral|semestral|anual)(?:es)?"
_NUMLIST = r"(\d+(?: a \d+)?(?:(?:\s*,\s*|\s+y\s+)\d+(?: a \d+)?)*)"

_APPLICABILITY_LANGUAGE = ApplicabilityLanguage(
    disp_head=re.compile(
        r"^\s*(?:norma|disposici[oó]n)\s+"
        r"(transitoria|final|adicional|derogatoria)(?:\s+(\w+))?",
        re.IGNORECASE),
    disp_prefix={"transitoria": "dt", "final": "df", "adicional": "da",
                 "derogatoria": "dd"},
    disp_ordinal={
        "única": "u", "unica": "u", "primera": "1", "primero": "1",
        "segunda": "2", "segundo": "2", "tercera": "3", "tercero": "3",
        "cuarta": "4", "cuarto": "4", "quinta": "5", "quinto": "5",
        "sexta": "6", "sexto": "6", "séptima": "7", "septima": "7",
        "séptimo": "7", "octava": "8", "octavo": "8", "novena": "9",
        "noveno": "9", "décima": "10", "decima": "10", "décimo": "10",
        "undécima": "11", "undecima": "11", "duodécima": "12",
        "duodecima": "12",
    },
    months={
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
        "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
        "octubre": 10, "noviembre": 11, "diciembre": 12,
    },
    temporal_markers=(
        ("INSTRUMENT_EFFECTIVE_FROM",
         re.compile(
             r"entrará en vigor el día siguiente al de su publicación")),
        ("INSTRUMENT_EFFECTIVE_FROM",
         re.compile(r"entrará en vigor")),
        ("APPLY_FROM", re.compile(r"se aplicarán desde el")),
        ("APPLY_FROM", re.compile(r"será de aplicación")),
        ("FIRST_REFERENCE_DATE",
         re.compile(r"se aplicarán por primera vez")),
        ("FIRST_REFERENCE_DATE",
         re.compile(r"primera fecha de referencia")),
        ("RETROACTIVE_APPLICATION",
         re.compile(r"se aplicarán retroactivamente")),
        ("INITIAL_APPLICATION_DATE",
         re.compile(r"fecha de aplicación inicial[^.]*será el")),
        ("PROSPECTIVE_APPLICATION",
         re.compile(r"aplicar (?:las modificaciones )?prospectivamente")),
    ),
    modality_markers=(
        ("ABSENCE_OF_OBLIGATION", re.compile(r"no estará obligada? a")),
        ("NON_APPLICATION", re.compile(r"no aplicará")),
        ("OPTION", re.compile(r"podrá(?:n)? (?:optar|interrumpir)")),
        ("OBLIGATION",
         re.compile(r"(?:deberá|deberán|deben|debe|reconocerá|"
                    r"informará)\b")),
        ("DECLARED_RULE",
         re.compile(r"se aplicarán|entrará en vigor|aplicará|serán")),
    ),
    conditional_opener=re.compile(r"^(?:Si[ ,]|Cuando )\b"),
    freq_map={
        "mensual": "MONTHLY", "mensuales": "MONTHLY",
        "trimestral": "QUARTERLY", "trimestrales": "QUARTERLY",
        "semestral": "SEMIANNUAL", "semestrales": "SEMIANNUAL",
        "anual": "ANNUAL", "anuales": "ANNUAL",
    },
    freq_word_scan=re.compile(
        r"mensual(?:es)?|trimestral(?:es)?|semestral(?:es)?|"
        r"anual(?:es)?"),
    freq_date_pair=re.compile(
        r"de (\d{1,2} de \w+ de \d{4}) para los (?:estados )?de "
        r"frecuencias? (" + _FREQ_WORDS + r"(?: y " + _FREQ_WORDS +
        r")?)"),
    subject_refs={
        "apartado_de_norma": re.compile(
            r"apartados? " + _NUMLIST + r" de la norma (\d+)"),
        "apartados_norma_ref": re.compile(
            r"apartados (\d+) a (\d+) de la norma (\d+)"),
        "normas": re.compile(r"las normas " + _NUMLIST),
        "anejos": re.compile(r"los anexos " + _NUMLIST),
        "punto_de_anejo": re.compile(
            r"punto (\d+)((?:\.\d+)*)[^.]*?"
            r"(?:y el apartado ([IVX]+)[^.]*)? del anexo (\d+)"),
        "apartado_iv_anejo": re.compile(
            r"apartado ([IVX]+)[^,;.]*del anexo (\d+)"),
    },
    introducer_patterns={
        "intro": re.compile(
            r"introducid[ao]s? por (.*?),? respectivamente,? de la"
            r" norma (\d+)"),
        "intro_letra": re.compile(
            r"introducid[ao]s? por (.*?de la letra [a-z]\)),? de la"
            r" norma (\d+)"),
        "letra_single": re.compile(r"la letra ([a-z])\)"),
        "letras_multi": re.compile(
            r"las letras ((?:[a-z]\)(?:, | y )?)+)"),
        "numeral_of_letra": re.compile(
            r"numeral ([ivx]+)\)(?:, respectivamente,)? de la letra"
            r" ([a-z])\)"),
        "numerales_of_letra": re.compile(
            r"numerales ((?:[ivx]+\)(?:, | y )?)+)"
            r"(?:, respectivamente,)? de la letra ([a-z])\)"),
        "roman_token": re.compile(r"([ivx]+)\)"),
    },
    rule_patterns={
        "except_apartados": re.compile(
            r"con las excepciones establecidas en los apartados (\d+)"
            r" a (\d+) de esta (?:disposición|norma)"),
        "especificidades": re.compile(
            r"con las siguientes especificidades"),
        "sin_perjuicio": re.compile(
            r"[Ss]in perjuicio de lo establecido en la (?:disposición"
            r"|norma) (transitoria \w+|final \w+|adicional \w+|"
            r"derogatoria \w+)"),
        "rule_ref_ctx": re.compile(
            r"(?:de acuerdo con|establecido en|requerida en|dispone en)"
            r"[^.]{0,90}$"),
        "opt_out_trigger": _never(),
    },
    sin_perjuicio_targets={"primera": "dt1", "segunda": "dt2",
                           "tercera": "dt3"},
    opt_out_phrase="no estará obligada a reexpresar",
    periodicity_header="Periodicidad",
    date_inner=r"(\d{1,2} de \w+ de \d{4})",
    pub_relative="día siguiente al de su publicación",
    condition_scan=re.compile(r"(?:Si|Cuando) [^.]*?(?:,|\.)"),
    exercise_literal="@@NO_DEV_EVIDENCE@@",
    exercise_value=0,
    exercise_pattern=_never(),
    sentence_boundary=re.compile(r"\.\s+(?=[A-ZÁÉÍÓÚÑ«0-9(])"),
    marker_only=r"(?:\d+\.|[a-z]\))\.?\s*",
    nums_split=r",| y ",
    nums_range=re.compile(r"^(\d+) a (\d+)$"),
    num_item=r"^\d+\.\s",
    item_markers={"num": r"^(\d+)\.\s", "alpha": r"^([a-z])\)\s"},
    effect_date_patterns={
        "APPLY_FROM": r"se aplicarán desde el (\d{1,2} de \w+ de \d{4})",
        "FIRST_REFERENCE_DATE":
            r"(\d{1,2} de \w+ de \d{4}) como primera fecha de referencia",
        "LAST_REFERENCE_DATE":
            r"correspondientes a[l]? (\d{1,2} de \w+ de \d{4})",
        "INITIAL_APPLICATION_DATE":
            r"será el (\d{1,2} de \w+ de \d{4})",
    },
)

# ---------------------------------------------------------------------------
# F8 source_descriptors — DEV manifest evidences exactly these four
# captured sources; boe_sumario/bde_consultas are BdE endpoints and do
# not exist for CNMV.
# ---------------------------------------------------------------------------

_SOURCE_DESCRIPTORS = SourceDescriptors(
    source_ids=(
        "boe_diario", "boe_doc", "boe_pdf", "boe_imagen",
    ),
    base_url="https://www.boe.es",
    url_templates={
        "diario_xml": "https://www.boe.es/diario_boe/xml.php?id={boe}",
        "doc_html": "https://www.boe.es/buscar/doc.php?id={boe}",
        "dias_pdf":
            "https://www.boe.es/boe/dias/{y}/{m}/{d}/pdfs/{boe}.pdf",
    },
    media_types={
        "boe_diario": "application/xml",
        "boe_doc": "text/html",
        "boe_pdf": "application/pdf",
        "boe_imagen": "image/*",
    },
    capture_rules=(
        ("boe_diario_xml__", ".xml", "boe_diario"),
        ("boe_doc_html__", None, "boe_doc"),
        ("boe_dias_pdf__", ".pdf", "boe_pdf"),
        (None, (".png", ".jpg", ".gif"), "boe_imagen"),
    ),
    capture_default="boe_doc",
    imagen_parser=("boe_imagen", "v1"),
    # CNMV has no legacy capture layer; the frozen core builds a SQL
    # CASE that needs >=1 WHEN, so the map is the identity backfill
    # (source_id -> its own parser name). Journaled PROFILE_DATA_MISSING
    # #1.
    legacy_parser_names={
        "boe_diario": "boe_diario",
        "boe_doc": "boe_doc",
        "boe_pdf": "boe_pdf",
    },
    legacy_parser_default="boe_doc",
    metadata_mapping={
        "titulo": "titulo",
        "fecha_publicacion": "fecha_publicacion",
        "fecha_vigencia": "fecha_vigencia",
        "pagina_inicial": "pagina_inicial",
        "rango": "rango",
        "url_eli": "url_eli",
        "url_pdf": "url_pdf",
    },
    relation_mapping={
        "anteriores": "anterior",
        "posteriores": "posterior",
    },
)

CNMV_PROFILE = SourceProfile(
    profile_id="cnmv-circular",
    profile_version="cnmv-v1",
    document_model=_DOCUMENT_MODEL,
    text_normalization=_TEXT_NORMALIZATION,
    locator_grammar=_LOCATOR_GRAMMAR,
    operative_grammar=_OPERATIVE_GRAMMAR,
    identity_reference=_IDENTITY_REFERENCE,
    annex_state=_ANNEX_STATE,
    applicability_language=_APPLICABILITY_LANGUAGE,
    source_descriptors=_SOURCE_DESCRIPTORS,
)

register_profile(CNMV_PROFILE)
