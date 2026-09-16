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

    enabled_kinds: frozenset            # core LocatorKinds recognized
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
class ApplicabilityLanguage:
    """F7 — disposición/clause vocabulary: date, frequency, temporal
    and modal lexemes, subject-reference and introducer patterns.

    Emitted effect names, modality names, epistemic labels and
    clause-key spellings are core; the source phrases that produce
    them are profile data. ``temporal_markers``/``modality_markers``
    keep their ordered first-match semantics as data.
    """

    disp_head: re.Pattern               # disposicion heading grammar
    disp_prefix: Mapping[str, str]      # 'transitoria' -> 'dt' etc.
    disp_ordinal: Mapping[str, str]     # ordinal word -> emitted code
    months: Mapping[str, int]
    temporal_markers: tuple             # ordered ((effect, Pattern))
    modality_markers: tuple             # ordered ((modality, Pattern))
    conditional_opener: re.Pattern      # '^(?:Si[ ,]|Cuando )'
    freq_map: Mapping[str, str]         # 'mensual' -> 'MONTHLY'
    freq_word_scan: re.Pattern          # freq tokens inside a capture
    freq_date_pair: re.Pattern          # 'de <date> para los ... de frecuencias'
    subject_refs: Mapping[str, re.Pattern]   # norma/anejo/apartado refs
    introducer_patterns: Mapping[str, re.Pattern]
    rule_patterns: Mapping[str, re.Pattern]  # exceptions, rule-ref ctx
    sin_perjuicio_targets: Mapping[str, str]  # 'primera' -> 'dt1' etc.
    opt_out_phrase: str                     # 'no estará obligada a reexpresar'
    periodicity_header: str                 # norma-67 table header word
    date_inner: str                     # '(\d{1,2} de \w+ de \d{4})'
    pub_relative: str                   # 'día siguiente al de su publicación'
    condition_scan: re.Pattern          # '(?:Si|Cuando) [^.]*?(?:,|\.)'
    exercise_literal: str               # 'cuentas anuales ... ejercicio N'
    exercise_value: int
    exercise_pattern: re.Pattern        # 'cuentas anuales \w+ y \w+ ...'
    sentence_boundary: re.Pattern
    marker_only: str                    # marker-only merge source
    nums_split: str                     # enumeration separator source
    nums_range: re.Pattern              # 'lo a hi' range pair
    num_item: str                       # '^\d+\.\s' numbered style detect
    item_markers: Mapping[str, str]     # style -> item marker source
    effect_date_patterns: Mapping[str, str]  # effect -> capture source


@dataclass(frozen=True)
class SourceDescriptors:
    """F8 — source registry/acquisition descriptors: data rows, never
    DDL text or integrity policy (contract A5). The core renders its
    own constraints from ``source_ids`` and controls what registry
    validity means."""

    source_ids: tuple                   # registry-recognized ids
    base_url: str
    url_templates: Mapping[str, str]    # role -> '{boe}'/'{y}{m}{d}' form
    media_types: Mapping[str, str]      # source_id -> media type
    capture_rules: tuple                # (name_prefix, path_suffix, src_id)
    capture_default: str                # fallback source_id
    imagen_parser: tuple                # parser identity without a module
    legacy_parser_names: Mapping[str, str]   # pre-provenance backfill
    legacy_parser_default: str
    metadata_mapping: Mapping[str, str]   # raw source field -> canonical
    relation_mapping: Mapping[str, str]   # raw container -> direction


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
    applicability_language: ApplicabilityLanguage
    source_descriptors: SourceDescriptors


# ---------------------------------------------------------------------------
# Core kind registries (PORT-1 A1). The core owns the semantic kind
# taxonomy and its canonical emitted spellings; a profile may *enable*
# a subset and map source lexemes onto it, but may never mint a kind.
# ---------------------------------------------------------------------------

LOCATOR_KINDS = frozenset({
    "norma", "anejo", "anexo", "articulo", "capitulo", "titulo",
    "seccion", "disp", "disposicion", "pagina",
    "apartado", "punto", "letra", "numeral", "nota", "indice",
    "estado", "fichero",
})

OP_KINDS = frozenset({"ADD", "DELETE", "MODIFY", "SUBSTITUTE"})


def validate_profile(profile: SourceProfile) -> None:
    """Well-formedness check run at registration. Fails closed: a
    profile that references kinds outside the core registry, or whose
    descriptors are internally inconsistent, is rejected before any
    consumer can resolve it."""
    lg = profile.locator_grammar
    unknown = set(lg.enabled_kinds) - LOCATOR_KINDS
    if unknown:
        raise ValueError(f"UNKNOWN_CORE_KIND: {sorted(unknown)}")
    kind_keyed = (
        set(lg.declarations), set(lg.enum_kinds), set(lg.head_forms),
        set(lg.level_boundary), set(lg.sub_markers),
        set(lg.sub_markers_compound), set(lg.kind_words),
        set(lg.coverage_heads),
        set(lg.presence) - {"_default"},
    )
    for keys in kind_keyed:
        unknown = keys - LOCATOR_KINDS
        if unknown:
            raise ValueError(f"UNKNOWN_CORE_KIND: {sorted(unknown)}")
        disabled = keys - set(lg.enabled_kinds)
        if disabled:
            raise ValueError(
                f"locator kind used but not enabled: {sorted(disabled)}")
    bad_ops = {k for k, _ in profile.operative_grammar.op_kinds} - OP_KINDS
    if bad_ops:
        raise ValueError(f"UNKNOWN_CORE_KIND: {sorted(bad_ops)}")
    sd = profile.source_descriptors
    ids = tuple(sd.source_ids)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("source_ids must be non-empty and unique")
    declared = set(ids)
    if sd.capture_default not in declared:
        raise ValueError("capture_default not in source_ids")
    for *_, sid in sd.capture_rules:
        if sid not in declared:
            raise ValueError(f"capture rule targets undeclared {sid!r}")
    if set(sd.media_types) - declared:
        raise ValueError("media_types for undeclared source_ids")
    if not sd.url_templates or not sd.base_url:
        raise ValueError("source_descriptors missing base_url/templates")
    bad_dirs = set(sd.relation_mapping.values()) - {"anterior", "posterior"}
    if bad_dirs:
        raise ValueError(f"relation_mapping targets: {sorted(bad_dirs)}")


_PROFILES: dict[str, SourceProfile] = {}
_ACTIVE_ID: str | None = None


def register_profile(profile: SourceProfile) -> None:
    if profile.profile_id in _PROFILES:
        raise ValueError(f"duplicate profile_id {profile.profile_id!r}")
    validate_profile(profile)
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
