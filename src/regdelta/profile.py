"""Core-side SourceProfile contract and registry (PORT-2).

A ``SourceProfile`` is immutable data: source lexemes, compiled
patterns, vocabularies, identifier syntax and mappings from source
forms to core semantic kinds. It contains no callables and decides
nothing — the core's enumeration, adjudication and abstention
policies consume it.

Profiles live in ``regdelta.profiles`` (the boundary package); that
package's ``__init__`` is the composition manifest importing each
installed profile module, which self-registers here. The core
depends on the registry only.

Registry invariants: ``profile_id`` unique; an active profile must
be resolvable before any profile-consuming engine runs; with more
than one registered profile an explicit ``use_profile`` selection
is required — ambiguity fails closed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class DocumentModel:
    """F1 facet: node-stream vocabulary — kinds, classes, boundaries.

    The typed node stream (``DiarioDoc``/``Node``) is the core
    contract; the kind/class *spellings* a source parser emits are
    profile data keyed by core semantic role. ``boundary`` holds
    document-level delimiter patterns (signature block, etc.).
    """

    kinds: Mapping[str, str]
    classes: Mapping[str, str]
    class_prefixes: Mapping[str, str]
    locator_classes: frozenset
    boundary: Mapping[str, re.Pattern]
    annex_literal: str


@dataclass(frozen=True)
class TextNormalization:
    """F2 facet: normalization parameters + the «» quoting convention.

    The deterministic normalize/compare algorithms stay core
    (C-021/C-005 split); these are the parameters they run with.
    """

    form: str                       # unicodedata form, e.g. "NFKD"
    strip_combining: bool
    fold: str                       # "lower" | "casefold"
    collapse_ws: bool
    quote_open: str
    quote_close: str
    quoted_span: re.Pattern


@dataclass(frozen=True)
class FicheroGrammar:
    """BdE data-file ('fichero') vocabulary — F6 annex_state member.

    The name-equality policy (normalized name or token multiset)
    stays core; the lexemes, connective stop-list and split
    charsets are profile data.
    """

    word: str                       # normalized bare heading literal
    connectors: frozenset
    head: re.Pattern                # '^fichero\s*:' block heading
    head_value: re.Pattern          # heading + captured name
    boundary: re.Pattern            # block-closing boundary
    subject: re.Pattern             # 'fichero «Name»' subject form
    dash_collapse: re.Pattern
    note_strip: re.Pattern
    token_split: str                # on casefolded text (keeps accents)
    token_split_norm: str           # on accent-stripped text


@dataclass(frozen=True)
class AnnexStateGrammar:
    """F6 facet: annex/state-code vocabulary and format parameters.

    ``patterns`` maps core semantic names -> compiled patterns.
    Compiled ``re.Pattern`` objects are immutable pattern data; the
    matching flags are part of the pattern's meaning and travel
    with it.
    """

    state_code_families: tuple[str, ...]
    index_code_threshold: int
    fichero: FicheroGrammar
    patterns: Mapping[str, re.Pattern] = field(default_factory=dict)


@dataclass(frozen=True)
class LocatorGrammar:
    """F3 facet: locator declaration, heading and marker grammar.

    Every member is source vocabulary consumed by core enumeration
    policy. Templates are format strings interpolated by the core
    (``{v}`` = escaped value, ``{alt}``/``{tipo}``/``{ord}``/``{num}``
    = caller-built alternations); compile flags at a call site are
    part of that site's matching policy.
    """

    ordinals: Mapping[str, int]         # word -> number
    ordinal_words: Mapping[str, str]    # number -> feminine word
    roman: Mapping[str, str]            # digit -> roman numeral
    ordinal_item: re.Pattern            # 'Cinco.'-style ordinal items
    clause_marker: re.Pattern           # 'a)'/'i.'/'3.' clause markers
    marker_amb_values: frozenset        # roman-ambiguous marker values
    declarations: Mapping[str, re.Pattern]   # 'kind <vals>' mentions
    enum_kinds: tuple                   # kinds whose capture enumerates
    numlist_split: str                  # enumeration separator source
    numlist_range: re.Pattern           # 'lo a hi' range pair
    numlist_atom: str                   # single-value fullmatch source
    expand_split: str                   # coarser enumeration separator
    expand_range: re.Pattern
    expand_atom: re.Pattern
    letra_list: re.Pattern              # 'letras a), b) y c)'
    letra_item: re.Pattern              # '(?a)?' item inside the list
    head_forms: Mapping[str, tuple]     # kind -> mention head spellings
    articulo_head: re.Pattern           # '<word> <ordinal>' head grammar
    norma_head: str                     # template, {alt} alternation
    disposicion_head: str               # template, {tipo} {ord}
    anejo_head: str                     # template, {num}
    anejo_boundary: re.Pattern
    presence: Mapping[str, tuple]       # kind -> sub-presence templates
    markers: Mapping[str, re.Pattern]   # numeric/letra/sibling markers
    level_boundary: Mapping[str, tuple]  # kind -> marker names
    default_boundary: str               # marker name for unlisted kinds
    sub_markers: Mapping[str, tuple]    # kind -> (template, flags)
    sub_markers_compound: Mapping[str, tuple]
    value_continuation: re.Pattern      # dotted-value fragment chars
    kind_words: Mapping[str, str]       # kind -> lexeme pattern source
    kinded_tail: re.Pattern             # ownership _KINDED_TAIL_RE:
                                        # '.kind:' component split
    coverage_heads: tuple               # history _COVER_HEADS: kinds whose
                                        # span must restate the token


@dataclass(frozen=True)
class OperativeGrammar:
    """F4 — operative-language vocabulary and patterns. The ordered
    ``op_kinds`` mapping pairs profile verb lexemes with core
    OperationKind tokens; ordering is part of the vocabulary data
    (first-match lexeme priority), never of adjudication policy."""

    amend_verb_active: re.Pattern      # _AMEND_VERB_ACTIVE_RE
    amend_verb_passive: re.Pattern     # _AMEND_VERB_PASSIVE_RE
    subordinator_tail: re.Pattern      # _SUBORDINATOR_TAIL_RE
    en_subject: re.Pattern             # _EN_SUBJECT_RE
    bare_subject: re.Pattern           # _BARE_SUBJECT_RE
    content_pointer: re.Pattern        # _CONTENT_POINTER_RE
    container: re.Pattern              # _CONTAINER_RE
    literal_pairs: re.Pattern          # _LITERAL_PAIRS_RE
    donde_dice: re.Pattern             # _DONDE_DICE_RE
    annex_ref: re.Pattern              # _ANNEX_REF_RE
    op_kinds: tuple                    # ordered ((kind_token, Pattern), ...)
    segment_split: re.Pattern          # _SEG_SPLIT_RE
    non_op_tail: re.Pattern            # _NON_OP_TAIL_RE
    root_families: tuple               # _CTX_ROOTS: kinds that only nest
                                       # under their own family
    sub_scope: re.Pattern              # _SUB_SCOPE_RE
    qualifier_src: str                 # _QUALIFIER_SRC pattern source
    unmarked_opener: re.Pattern        # _unmarked_op inline clause opener
    container_close: re.Pattern        # 'se modifican:$' container form
    siguientes: str                    # enumeration head word 'siguientes'


@dataclass(frozen=True)
class IdentityReference:
    """F5 — which-instrument reference grammar and correction
    vocabulary. Parsed metadata/relation vocabulary only: raw field
    names are the profile package's mapping problem (contract A3).
    Identity hashing and attribution policy stay core."""

    target_ref: re.Pattern             # operations _TARGET_RE
    circular_ref: re.Pattern           # history _CIRCULAR_RE
    fichero_owner: re.Pattern          # _FICHERO_OWNER_RE
    eli_circular: re.Pattern           # ownership _ELI_CIR_RE
    eli_corrigendum_path: str          # '/corrigendum/'
    boe_id: re.Pattern                 # query BOE_ID_RE
    circular_query: re.Pattern         # query CIRCULAR_RE
    correction_palabras: tuple         # palabra substrings -> CORRECTION
    correction_primary_prefix: str     # 'CORRECCION DE ERRORES'
    correction_secondary_prefix: str   # 'CORRIGE ERRORES'
    correction_secondary_contains: str # 'CORRECCION'
    corrigendum_marker: str            # rango/titulo prefix 'CORRECCI'


@dataclass(frozen=True)
class SourceProfile:
    """Immutable profile data. Grows facet-by-facet as PORT-2
    extraction proceeds; a facet is added only when the core
    actually consumes it."""

    profile_id: str
    profile_version: str
    document_model: DocumentModel
    text_normalization: TextNormalization
    locator_grammar: LocatorGrammar
    operative_grammar: OperativeGrammar
    identity_reference: IdentityReference
    annex_state: AnnexStateGrammar


_PROFILES: dict[str, SourceProfile] = {}
_ACTIVE_ID: str | None = None


def register_profile(profile: SourceProfile) -> None:
    if profile.profile_id in _PROFILES:
        raise ValueError(f"duplicate profile_id {profile.profile_id!r}")
    _PROFILES[profile.profile_id] = profile


def use_profile(profile_id: str) -> SourceProfile:
    """Explicitly select the active profile (required when more than
    one is registered)."""
    global _ACTIVE_ID
    p = _PROFILES.get(profile_id)
    if p is None:
        raise LookupError(f"unknown profile_id {profile_id!r}")
    _ACTIVE_ID = profile_id
    return p


def active_profile() -> SourceProfile:
    """The run's active profile, resolved through the registry.

    An empty registry lazily imports ``regdelta.profiles`` — the
    installed-profiles manifest — which registers its members.
    Zero registered or multiple unselected profiles both fail
    closed.
    """
    if _ACTIVE_ID is not None:
        return _PROFILES[_ACTIVE_ID]
    if not _PROFILES:
        import regdelta.profiles  # noqa: F401  (composition manifest)
    if len(_PROFILES) == 1:
        return next(iter(_PROFILES.values()))
    if not _PROFILES:
        raise LookupError("no SourceProfile registered")
    raise LookupError(
        "multiple SourceProfiles registered; use_profile() required")
