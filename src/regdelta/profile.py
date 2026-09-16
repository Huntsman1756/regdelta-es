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
class AnnexStateGrammar:
    """F6 facet: annex/state-code vocabulary and format parameters.

    ``patterns`` maps core semantic names -> compiled patterns.
    Compiled ``re.Pattern`` objects are immutable pattern data; the
    matching flags are part of the pattern's meaning and travel
    with it.
    """

    state_code_families: tuple[str, ...]
    index_code_threshold: int
    patterns: Mapping[str, re.Pattern] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceProfile:
    """Immutable profile data. Grows facet-by-facet as PORT-2
    extraction proceeds; a facet is added only when the core
    actually consumes it."""

    profile_id: str
    profile_version: str
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
