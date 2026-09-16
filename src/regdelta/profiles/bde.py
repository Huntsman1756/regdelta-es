"""BdE Circular source profile (BOE/BdE) — immutable data only.

Every value here was moved verbatim from the core modules that used
it (PORT-2 extraction); the compiled patterns are byte-for-byte the
previous module-level constants. The core owns the semantic names
(the dict keys); this file owns the BdE spellings.
"""

from __future__ import annotations

import re

from ..profile import (
    AnnexStateGrammar, ApplicabilityLanguage, DocumentModel,
    FicheroGrammar, IdentityReference, LocatorGrammar, OperativeGrammar,
    SourceDescriptors, SourceProfile, TextNormalization,
    register_profile)

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
    # '.kind:' component split inside composed locator keys
    kinded_tail=re.compile(
        r"\.(?:punto|apartado|letra|numeral|nota|indice|estado|"
        r"fichero|norma|anejo|disp|disposicion|seccion|pagina):"),
    # kinds whose binding span must restate the subject token
    coverage_heads=("estado", "punto", "apartado", "letra", "numeral",
                    "nota", "indice"),
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

# ---------------------------------------------------------------------------
# F4 operative_grammar — amendment-verb lexicon + clause grammar
# ---------------------------------------------------------------------------

# 'incluir' amends only with a structural direct object
_INCLU_OBJ = (
    r"(?=\s+(?:unas?|una?|el|la|los|las|otras?|nuev[ao]s?|send[ao]s?)"
    r"\s+(?:nuev[ao]s?\s+)?(?:normas?|anejos?|anexos?|apartados?|"
    r"letras?|puntos?|numeral(?:es)?|notas?|estados?|ficheros?|"
    r"disposici[oó]n(?:es)?|secci[oó]n(?:es)?|[ií]ndices?|"
    r"p[aá]ginas?)\b)")

_OPERATIVE_GRAMMAR = OperativeGrammar(
    amend_verb_active=re.compile(
        r"se\s+(?:modifica\w*|sustituye\w*|suprime\w*|elimina\w*|"
        r"añade\w*|introduce\w*|incorpora\w*|inclu\w*" + _INCLU_OBJ +
        r"|realiza\w*|inserta\w*|crea\w*)",
        re.IGNORECASE),
    amend_verb_passive=re.compile(
        r"debe\w*\s+(?:modificarse|sustituirse|suprimirse|eliminarse|"
        r"añadirse|introducirse|incorporarse|incluirse" + _INCLU_OBJ +
        r"|insertarse|crearse)|"
        r"queda\w*\s+redactad|pasa\w*\s+a\s+(?:ser|denominarse)|"
        r"(?:se\s+)?da\w*\s+nueva\s+redacci[oó]n|"
        r"donde\s+dice|debe\s+decir|se\s+sombrea",
        re.IGNORECASE),
    subordinator_tail=re.compile(
        r"(?:^|[,;:]\s*|\s)"
        r"(?:que|por\s+(?:el|la|los|las)\s+que|cuy[ao]s?|cuy[ao]s?|"
        r"donde|mediante|como|según|conforme|si|cuando|mientras|"
        r"aunque|porque|en\s+la\s+medida\s+en\s+que)\s*$",
        re.IGNORECASE),
    en_subject=re.compile(
        r"^en\s+(?:la|el|los|las)\s+(norma|anejo|anexo|estado|estados|"
        r"disposición|apartado|punto|letra|numeral|nota|p[aá]gina)\b",
        re.IGNORECASE),
    bare_subject=re.compile(
        r"^(estado|estados|anejo|anexo|norma|disposición|apartado|punto|"
        r"sección)\s+\S",
        re.IGNORECASE),
    content_pointer=re.compile(
        r"queda\w*\s+redactad|por\s+(?:el|los|la|las)\s+que\s+figura|"
        r"por\s+la\s+siguiente|por\s+las\s+siguientes|por\s+el\s+"
        r"siguiente|por\s+los\s+siguientes|con\s+el\s+siguiente|"
        r"con\s+la\s+siguiente|con\s+el\s+formato|por\s+«|"
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
        r"en\s+el\s+anejo\s+de\s+esta\s+circular|"
        r"(?:figura\w*|incluye\w*|recoge\w*)\s+en\s+el\s+anejo\b",
        re.IGNORECASE),
    op_kinds=(
        ("SUBSTITUTE", re.compile(
            r"se\s+sustituye\w*|debe\w*\s+sustituirse|"
            r"(?:se\s+)?da\w*\s+nueva\s+redacci[oó]n", re.IGNORECASE)),
        ("DELETE", re.compile(
            r"se\s+(?:suprime\w*|elimina\w*)|debe\w*\s+(?:suprimirse|"
            r"eliminarse)", re.IGNORECASE)),
        ("ADD", re.compile(
            r"se\s+(?:añade\w*|introduce\w*|incorpora\w*|inclu\w*"
            + _INCLU_OBJ + r"|crea\w*)|"
            r"debe\w*\s+(?:añadirse|introducirse|incorporarse|"
            r"incluirse" + _INCLU_OBJ + r"|insertarse|crearse)",
            re.IGNORECASE)),
        ("MODIFY", re.compile(
            r"se\s+(?:modifica\w*|realiza\w*|sombrea)|queda\w*\s+"
            r"redactad|pasa\w*\s+a\s+(?:ser|denominarse)",
            re.IGNORECASE)),
    ),
    segment_split=re.compile(
        r"[;:]|\.\s|\s+(?:y|e|ni)\s+", re.IGNORECASE),
    non_op_tail=re.compile(r"[,;.]\s*sin\s+(?:que|perjuicio)\b",
                           re.IGNORECASE),
    root_families=("norma", "anejo", "disposicion"),
    sub_scope=re.compile(
        r"\b(?:m[oó]dulo|dimensi[oó]n|apartado|letra|punto|numeral|"
        r"nota|secci[oó]n|cuadro|tabla|p[aá]rrafo|[íi]ndice|fila|"
        r"columna)\b",
        re.IGNORECASE),
    qualifier_src=(
        r"(?:\.\s*[a-z]\b|\s+(?:bis|ter|qu[aá]ter|quinquies|sexies|"
        r"septies|octies|nonies|decies)\b)"),
    unmarked_opener=re.compile(
        r"(?:en\s+(?:la|el|los|las)\s+\w|se\s+\w)", re.IGNORECASE),
    container_close=re.compile(
        r"se\s+(?:modifican?|realizan?|efectúan?)\s*:$", re.IGNORECASE),
    siguientes="siguientes",
)

# ---------------------------------------------------------------------------
# F5 identity_reference — which-instrument grammar + correction vocab
# ---------------------------------------------------------------------------

_IDENTITY_REFERENCE = IdentityReference(
    target_ref=re.compile(
        r"Circular\s+(?:del\s+Banco\s+de\s+Espa[ñn]a\s+)?(\d+)\s*/\s*"
        r"(\d{4})",
        re.IGNORECASE),
    circular_ref=re.compile(
        r"Circular\s+(\d+)\s*/\s*(\d{4})", re.IGNORECASE),
    fichero_owner=re.compile(
        r"anejo\s+de\s+la\s+Circular\s+(?:del\s+Banco\s+de\s+Espa[ñn]a"
        r"\s+)?(\d+)\s*/\s*(\d{4})", re.IGNORECASE),
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
# F7 applicability_language — disposicion/clause vocabulary
# ---------------------------------------------------------------------------

_FREQ_WORDS = r"(?:mensual|trimestral|semestral|anual)(?:es)?"
_NUMLIST = r"(\d+(?: a \d+)?(?:(?:\s*,\s*|\s+y\s+)\d+(?: a \d+)?)*)"

_APPLICABILITY_LANGUAGE = ApplicabilityLanguage(
    disp_head=re.compile(
        r"^\s*disposici[oó]n\s+(transitoria|final|adicional|derogatoria)"
        r"(?:\s+(\w+))?", re.IGNORECASE),
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
        ("APPLY_FROM", re.compile(r"se aplicarán desde el")),
        ("FIRST_REFERENCE_DATE",
         re.compile(r"se aplicarán por primera vez para los datos")),
        ("FIRST_REFERENCE_DATE",
         re.compile(r"primera fecha de referencia")),
        ("LAST_REFERENCE_DATE", re.compile(r"últimos datos")),
        ("RETROACTIVE_APPLICATION",
         re.compile(r"se aplicarán retroactivamente")),
        ("INITIAL_APPLICATION_DATE",
         re.compile(r"fecha de aplicación inicial[^.]*será el")),
        ("PROSPECTIVE_APPLICATION",
         re.compile(r"aplicar (?:las modificaciones )?prospectivamente")),
        ("SCOPE_PERIOD",
         re.compile(r"aplicará esta disposición transitoria")),
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
        "anejos": re.compile(r"los anejos " + _NUMLIST),
        "punto_de_anejo": re.compile(
            r"punto (\d+)((?:\.\d+)*)[^.]*?"
            r"(?:y el apartado ([IVX]+)[^.]*)? del anejo (\d+)"),
        "apartado_iv_anejo": re.compile(
            r"apartado ([IVX]+)[^,;.]*del anejo (\d+)"),
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
            r" a (\d+) de esta disposición"),
        "especificidades": re.compile(
            r"con las siguientes especificidades"),
        "sin_perjuicio": re.compile(
            r"[Ss]in perjuicio de lo establecido en la (disposición"
            r" transitoria \w+)"),
        "rule_ref_ctx": re.compile(
            r"(?:de acuerdo con|establecido en|requerida en|dispone en)"
            r"[^.]{0,90}$"),
        "opt_out_trigger": re.compile(
            r"(?:Si optara|Cuando haya optado) por no reexpresar"),
    },
    sin_perjuicio_targets={"primera": "dt1", "segunda": "dt2",
                           "tercera": "dt3"},
    opt_out_phrase="no estará obligada a reexpresar",
    periodicity_header="Periodicidad",
    date_inner=r"(\d{1,2} de \w+ de \d{4})",
    pub_relative="día siguiente al de su publicación",
    condition_scan=re.compile(r"(?:Si|Cuando) [^.]*?(?:,|\.)"),
    exercise_literal=(
        "cuentas anuales correspondientes al ejercicio 2026"),
    exercise_value=2026,
    exercise_pattern=re.compile(
        r"cuentas anuales \w+ y \w+ correspondientes al"
        r" (ejercicio \d{4})"),
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
# F8 source_descriptors — registry ids + acquisition endpoints
# ---------------------------------------------------------------------------

_SOURCE_DESCRIPTORS = SourceDescriptors(
    source_ids=(
        "boe_sumario", "bde_consultas",
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
    legacy_parser_names={"boe_sumario": "boe_sumario"},
    legacy_parser_default="bde_consultas",
)

BDE_PROFILE = SourceProfile(
    profile_id="bde-circular",
    profile_version="bde-v1",
    document_model=_DOCUMENT_MODEL,
    text_normalization=_TEXT_NORMALIZATION,
    locator_grammar=_LOCATOR_GRAMMAR,
    operative_grammar=_OPERATIVE_GRAMMAR,
    identity_reference=_IDENTITY_REFERENCE,
    annex_state=_ANNEX_STATE,
    applicability_language=_APPLICABILITY_LANGUAGE,
    source_descriptors=_SOURCE_DESCRIPTORS,
)

register_profile(BDE_PROFILE)
