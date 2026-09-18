"""PORT-CNMV-1 boundary adapter: legacy BOE stylesheet normalization.

JUSTIFICATION (required by PORT-CNMV-1-PREREG §5)
------------------------------------------------
CNMV circulars are published in BOE under (at least) two distinct
stylesheet families. 25/26 DEV documents emit canonical node classes
(``articulo``, ``parrafo``, ``anexo``); BOE-A-2008-20895 emits the
legacy family (``RBF_SFRANySIG_ARTICULO``, ``ATEXTO_*``, ``LINEA_ANEXO``,
``RVC_CAPITULO``, ``RHC_SEC_VERSALITAS``, ``RBC_RED_CENTRO``,
``NBC_SUBCAPITULO``, ``ACITAS``). The profile contract's
``DocumentModel.classes`` maps each canonical role to exactly one class
token, so a single profile cannot name both spellings — and no profile
slot or profile-data trick can express "either of two class names for
the same role".

This adapter is a pure format transform at the parse boundary: it
renames legacy stylesheet tokens to the canonical vocabulary the CNMV
profile already declares. It decides nothing — no facts, no ownership,
no locators, no bindings, no abstentions. Substitution test: if this
adapter were replaced by any other producing exactly the same
``DiarioDoc``/canonical metadata, no adjudication would change.

Attachment: ``history.reconstruct`` hardcodes ``boe_diario.parse_diario``
(frozen core), but resolves it as a module attribute at call time. The
probe runner installs ``parse_diario`` below as that attribute before
importing the pipeline — a runtime composition seam, not a modification
of any frozen file. Raw evidence bytes are never touched: normalization
applies only to the parsed ``DiarioDoc`` (provenance hashes unchanged).

The rename table below is generic CNMV source-format data — stylesheet
tokens, not BOE-IDs, years, or circular numbers. Unknown classes pass
through unchanged (fail-closed: an unrecognized style is not silently
reclassified).
"""

from dataclasses import replace

from regdelta.sources import boe_diario

# legacy stylesheet token -> canonical class, derived from observed DEV
# artifacts only. Tokens not listed pass through verbatim.
_LEGACY_CLASS_MAP = {
    # norma heads ("Norma N.ª …") — style literally named *_ARTICULO
    "RBF_SFRANySIG_ARTICULO": "articulo",
    "RBF_SFRAN_SOLA": "articulo",
    # annex head line ("ANEXO III")
    "LINEA_ANEXO": "anexo",
    # capitulo head ("CAPÍTULO INTRODUCTORIO" — combined num+title node;
    # canonical capitulo_num/capitulo_tit pairing simply does not fire)
    "RVC_CAPITULO": "capitulo_num",
    # heading-level markers (seccion versalitas, centered heads,
    # subcapitulo) — canonical heading marker class is 'centro'
    "RHC_SEC_VERSALITAS": "centro",
    "RBC_RED_CENTRO": "centro",
    "NBC_SUBCAPITULO": "centro",
    # body text
    "ATEXTO_NORMAL": "parrafo",
    "ATEXTO_BLANCO_4": "parrafo",
    "ATEXTO_BLANCO_6": "parrafo",
    "ATEXTOySIGUIENTE": "parrafo",
    "ACITAS": "parrafo",
    "[No paragraph style]": "parrafo",
}

# rename counts (audit trail): last_renames = most recent call,
# renames_total = cumulative since install()
last_renames: dict[str, int] = {}
renames_total: dict[str, int] = {}


def normalize_stylesheet(doc) -> None:
    """Rename legacy stylesheet classes to canonical vocabulary in-place."""
    global last_renames
    renames: dict[str, int] = {}
    for i, n in enumerate(doc.nodes):
        new = _LEGACY_CLASS_MAP.get(n.cls)
        if new is not None:
            doc.nodes[i] = replace(n, cls=new)
            renames[n.cls] = renames.get(n.cls, 0) + 1
            renames_total[n.cls] = renames_total.get(n.cls, 0) + 1
    last_renames = renames


_real_parse_diario = boe_diario.parse_diario


def parse_diario(body: bytes):
    """Parse-boundary wrapper: canonical parse + stylesheet normalization."""
    res = _real_parse_diario(body)
    if res.doc is not None:
        normalize_stylesheet(res.doc)
    else:
        last_renames = {}
    return res


def install() -> None:
    """Attach the adapter at the parse boundary (module-attribute seam)."""
    boe_diario.parse_diario = parse_diario
