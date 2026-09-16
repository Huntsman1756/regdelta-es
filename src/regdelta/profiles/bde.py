"""BdE Circular source profile (BOE/BdE) — immutable data only.

Every value here was moved verbatim from the core modules that used
it (PORT-2 extraction); the compiled patterns are byte-for-byte the
previous module-level constants. The core owns the semantic names
(the dict keys); this file owns the BdE spellings.
"""

from __future__ import annotations

import re

from ..profile import AnnexStateGrammar, SourceProfile, register_profile

# ---------------------------------------------------------------------------
# F6 annex_state — estado/fichero code families and annex page grammar
# ---------------------------------------------------------------------------

_ANNEX_STATE = AnnexStateGrammar(
    # BdE reporting-state code families. Consumed by operations,
    # annexmap, binding and applicability_parser — the single
    # profile-owned copy replacing four module-local ones (C-016).
    state_code_families=("FI", "FC", "PI", "PC", "PA", "UEM", "AVE"),
    # pages listing >= this many distinct codes are "índice" pages —
    # a calibrated BOE-annex format heuristic (A4: the value is
    # profile data; the threshold decision stays core).
    index_code_threshold=10,
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
    annex_state=_ANNEX_STATE,
)

register_profile(BDE_PROFILE)
