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
