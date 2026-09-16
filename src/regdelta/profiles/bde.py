"""BdE Circular source profile (BOE/BdE) — immutable data only.

Every value here was moved verbatim from the core modules that used
it (PORT-2 extraction); the compiled patterns are byte-for-byte the
previous module-level constants. The core owns the semantic names
(the dict keys); this file owns the BdE spellings.
"""

from __future__ import annotations

import re

from ..profile import (
    AnnexStateGrammar, DocumentModel, FicheroGrammar, LocatorGrammar,
    SourceProfile, TextNormalization, register_profile)

# ---------------------------------------------------------------------------
# F1 document_model — node-stream vocabulary (produced by sources/boe_*)
# ---------------------------------------------------------------------------

_DOCUMENT_MODEL = DocumentModel(
    kinds={"paragraph": "p", "blockquote": "blockquote",
           "table": "table"},
    classes={"articulo": "articulo", "anexo": "anexo",
             "capitulo_num": "capitulo_num",
             "capitulo_tit": "capitulo_tit", "anexo_tit": "anexo_tit",
             "parrafo": "parrafo", "parrafo_2": "parrafo_2"},
    class_prefixes={"centro": "centro", "sangrado": "sangrado"},
    # node classes that may carry a locator clause
    locator_classes=frozenset(
        {"parrafo", "parrafo_2", "sangrado", "sangrado_2", "cita"}),
    boundary={
        # signature block closing the document ("Madrid, 12 de ...")
        "signature": re.compile(r"^Madrid, \d+ de \w+ de \d{4}"),
    },
    # bare annex heading inside the diario XML stream
    annex_literal="ANEJO",
)

# ---------------------------------------------------------------------------
# F2 text_normalization — normalize/compare parameters + «» convention
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
# F3 locator_grammar — declaration, heading and marker grammar
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

_ROMAN_NUM = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
              "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x",
              "11": "xi", "12": "xii", "13": "xiii", "14": "xiv",
              "15": "xv", "16": "xvi", "17": "xvii", "18": "xviii",
              "19": "xix", "20": "xx"}

# enumeration-aware declaration pieces (G2.1 §25): 'anejos 1 y 2',
# 'normas 60, 62 y 64', 'apartados 12 a 17' declare every enumerated
# value; a hierarchical dotted identifier is one value, never a range
_NUM_SEQ = r"\d+(?:\s*\.\s*\d+)*"
_ROMAN_SEQ = r"[IVX]+(?:\.[A-Z0-9]+)*"
_ORD_SEQ = "|".join(_ORDINALS)
_ENUM_SEP = r"(?:\s*(?:a|al|,|y|e)\s+)"

_DECLARATIONS = {
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

_LOCATOR_GRAMMAR = LocatorGrammar(
    ordinals=_ORDINALS,
    ordinal_words=_ORDINAL_WORDS,
    roman=_ROMAN_NUM,
    # unmarked ordinal-word items ('Cinco.', 'Seis.') open a sibling
    # scope (G2.1 §23)
    ordinal_item=re.compile(
        r"^(primer[oa]?|segund[oa]|tercer[oa]?|tercer|cuart[oa]|quint[oa]|"
        r"sext[oa]|s[eé]ptim[oa]|octav[oa]|noven[oa]|d[eé]cim[oa]|"
        r"und[eé]cim[oa]?|duod[eé]cim[oa]|uno|una|dos|tres|cuatro|cinco|"
        r"seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince)\."
        r"\s", re.IGNORECASE),
    clause_marker=re.compile(
        r"^(?P<m>(?:[a-z]{1,2}\)|[ivxlcdm]+\s*[.)]|\d+\s*[.)]))\s*",
        re.IGNORECASE),
    # roman-numeral clause markers indistinguishable from letters
    marker_amb_values=frozenset(
        {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
         "xi", "xii", "xiii", "xiv", "xv"}),
    declarations=_DECLARATIONS,
    # mention kinds whose captured text is an enumeration to tokenize
    enum_kinds=("norma", "anejo", "apartado", "punto"),
    numlist_split=r"\s*(?:,|y|e)\s+",
    numlist_range=re.compile(r"(\d+)\s+(?:a|al)\s+(\d+)"),
    numlist_atom=(
        r"\d+(?:\.\d+)*|[IVX]+(?:\.[A-Z0-9]+)*|" + _ORD_SEQ),
    expand_split=r",|\s+[ye]\s+",
    expand_range=re.compile(r"^(\d+)\s+(?:a|al)\s+(\d+)$"),
    expand_atom=re.compile(r"\d+(?:\.\d+)+"),
    letra_list=re.compile(
        r"\bletras?\s+((?:\(?[a-z]\)?\s*(?:,|\sy\s|\se\s|\sa\s))*"
        r"\(?[a-z]\)?)", re.IGNORECASE),
    letra_item=re.compile(r"\(?[a-z]\)?"),
    # mention head spellings used to re-find a declared locator inside
    # its clause (disp heads expand with the tipo word)
    head_forms={
        "norma": ("norma",),
        "anejo": ("anejo", "anexo"),
        "disp": ("disposicion",),
        "articulo": ("articulo",),
        "estado": ("estado",),
        "fichero": ("fichero",),
    },
    # '<word> <ordinal>' articulo-class heading grammar
    articulo_head=re.compile(
        r"^(?:\[[^\]]*\]\s*)?([A-Za-zÁÉÍÓÚáéíóúñü]+)\s+(\S+)",
        re.IGNORECASE),
    # heading templates interpolated by the core enumerators
    norma_head=r"^(?:\[[^\]]*\]\s*)?norma\s+{alt}\b",
    disposicion_head=(
        r"^(?:\[[^\]]*\]\s*)?disposici[oó]n\s+{tipo}\s+{ord}\b"),
    anejo_head=r"^anejo\s+{num}\b",
    anejo_boundary=re.compile(
        r"^anejo\s+\S|^anexos?\b|madrid\s*,", re.IGNORECASE),
    # ownership _sub_present: how a kinded component shows inside a
    # headed span — per-kind template tuples ('{v}' = escaped value)
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
    # a candidate region ends at the next marker of its own level or
    # any outer level — never at a child marker
    level_boundary={
        "apartado": ("numeric",),
        "punto": ("numeric",),
        "letra": ("numeric", "letra"),
    },
    default_boundary="sibling",
    # sub-locator start markers ('{v}' = escaped declared value)
    sub_markers={
        # official markers: '2.' / '2. ' dotted, or '2 Texto' undotted —
        # the undotted form requires capitalised text so that '2 de
        # julio' / '2 000' prose is never a structural marker
        "apartado": (r"^{v}(?!\d)(?:\s*\.|\s+[A-ZÁÉÍÓÚÑ¿«(]|$)", 0),
        "punto": (r"^{v}(?!\d)(?:\s*\.|\s+[A-ZÁÉÍÓÚÑ¿«(]|$)", 0),
        "letra": (r"^{v}\s*\)", 0),
        "nota": (r"^[«(]+\s*\(?{v}\)?", re.IGNORECASE),
        "numeral": (r"^{v}\s*[.)]", re.IGNORECASE),
    },
    # a compound code ('9.1', 'II.B.2') must not prefix-match a deeper
    # sibling code ('9.10', '9.1.2')
    sub_markers_compound={
        "apartado": (r"^{v}(?!\.\d|\w)(?:\s*\.|\s|$)", 0),
        "punto": (r"^{v}(?!\.\d|\w)(?:\s*\.|\s|$)", 0),
    },
    # a bare locator-key segment starting with one of these continues
    # the previous component's dotted value
    value_continuation=re.compile(r"[\dA-ZÁÉÍÓÚÑ]"),
    # kind -> lexeme used to detect unmodelled ordinal qualifiers
    # ('norma 64 bis', 'apartado 2.e)')
    kind_words={
        "apartado": r"apartados?", "letra": r"letras?",
        "punto": r"puntos?", "numeral": r"numerales?",
        "nota": r"notas?", "norma": r"normas?",
        "anejo": r"(?:anejos?|anexos?)", "seccion": r"secciones?",
        "indice": r"[íi]ndices?",
    },
)

# ---------------------------------------------------------------------------
# F6 annex_state — estado/fichero code families and annex page grammar
# ---------------------------------------------------------------------------

_FICHERO = FicheroGrammar(
    word="fichero",
    # connective stop-list dropped from token comparison
    connectors=frozenset(
        {"a", "ante", "con", "de", "del", "e", "el", "en", "la", "las",
         "los", "para", "por", "sobre", "y"}),
    head=re.compile(r"^fichero\s*:"),
    head_value=re.compile(r"^fichero\s*:\s*(.*)$"),
    boundary=re.compile(r"^(?:fichero\s*:|madrid\s*,)"),
    # data-file subjects: 'el fichero «Expedientes sancionadores»'
    subject=re.compile(r"\bficheros?\s+«([^»]+)»", re.IGNORECASE),
    dash_collapse=re.compile(r"\s*-\s*"),
    note_strip=re.compile(r"\s*\(\s*\*+\s*\)\s*$"),
    token_split=r"[^\wáéíóúñü]+",
    token_split_norm=r"[^\w]+",
)

_ANNEX_STATE = AnnexStateGrammar(
    # BdE reporting-state code families. Consumed by operations,
    # annexmap, binding and applicability_parser — the single
    # profile-owned copy replacing four module-local ones (C-016).
    state_code_families=("FI", "FC", "PI", "PC", "PA", "UEM", "AVE"),
    # pages listing >= this many distinct codes are "índice" pages —
    # a calibrated BOE-annex format heuristic (A4: the value is
    # profile data; the threshold decision stays core).
    index_code_threshold=10,
    fichero=_FICHERO,
    patterns={
        # \bFI 150-9 — clause-level code mention
        "state_code": re.compile(
            r"\b(FI|FC|PI|PC|PA|UEM|AVE)\s*(\d[\d.]*(?:-\s*[\d.]+)?)"),
        # positional anchors, not subjects: 'a continuación del estado
        # FI 150-9', 'las correspondientes a los estados FI 150 y FI
        # 160', 'por el formato de estado FI 142-1.1'
        "state_anchor_span": re.compile(
            r"(?:a\s+continuaci[oó]n\s+(?:del|de\s+los|de\s+las)|"
            r"correspondiente\w*\s+a|formato\s+de|"
            r"entre\s+las\s+correspondientes\s+a)"
            r"\s*(?:del|de\s+los|de\s+las|los|las|el|la|l)?\s*"
            r"estados?\s+((?:FI|FC|PI|PC|PA|UEM|AVE)\s*[\d.\-]+"
            r"(?:\s*[ye,]\s*(?:(?:FI|FC|PI|PC|PA|UEM|AVE)\s*)?"
            r"[\d.\-]+)*)",
            re.IGNORECASE),
        # «FI 151 ...» codes introduced as new states: "se incluyen
        # los nuevos estados «FI 151 ...», «FI 151-1 ...»"
        "quoted_state": re.compile(
            r"estados?\s+(«(?:FI|FC|PI|PC|PA|UEM|AVE)[^»]*»"
            r"(?:\s*[ye,]\s*«(?:FI|FC|PI|PC|PA|UEM|AVE)[^»]*»)*)",
            re.IGNORECASE),
        "quoted_code": re.compile(
            r"«\s*(FI|FC|PI|PC|PA|UEM|AVE)\s*(\d[\d.\-]*)"),
        # parenthetical errata locators: "en la página 18938 (Estado
        # T.17-2)"; a code outside the documented families can never
        # be declared or resolved, so it is never a subject
        "paren_state": re.compile(
            r"\(\s*estados?\s+([^)]*)\)", re.IGNORECASE),
        "paren_code": re.compile(
            r"(FI|FC|PI|PC|PA|UEM|AVE)\s*\.?\s*(\d[\d.\-]*)"),
        # estado code at the start of an annex page's embedded text
        # layer; the layer sometimes letter-spaces codes ("F I  101")
        "pdf_page_code": re.compile(
            r"\b(F\s*I|F\s*C|P\s*I|P\s*C|P\s*A|U\s*E\s*M|A\s*V\s*E|"
            r"A\s*N\s*E\s*J\s*O)\s+(\d[\d\- .]*\d|\d)"),
        "page_num": re.compile(r"P[áa]g\.\s*([\d\s]+)"),
        "anejo_head": re.compile(
            r"A\s*N\s*E\s*J\s*O\s+(\d+(?:\s*\.\s*\d+)*)"),
        # estado code heading inside a diario XML annex block
        "annex_code_header": re.compile(
            r"^(FI|FC|PI|PC|PA|UEM|AVE)\s+(\d[\d.\-]*)"),
        # applicability-scope 'estados FI 1, FI 2 y FI 3' lists
        "estados_list": re.compile(
            r"estados ((?:[A-Z]{1,3} \d+(?:[\-.]\d+(?:\.\d+)?)?"
            r"(?:,? y? )?)+)"),
        "estado_token": re.compile(
            r"[A-Z]{1,3} \d+(?:[\-.]\d+(?:\.\d+)?)?"),
    },
)

BDE_PROFILE = SourceProfile(
    profile_id="bde-circular",
    profile_version="bde-v1",
    document_model=_DOCUMENT_MODEL,
    text_normalization=_TEXT_NORMALIZATION,
    locator_grammar=_LOCATOR_GRAMMAR,
    annex_state=_ANNEX_STATE,
)

register_profile(BDE_PROFILE)
