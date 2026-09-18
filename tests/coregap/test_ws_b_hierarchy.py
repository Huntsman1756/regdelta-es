"""CORE-GAP WS-B: declared inside-out locator hierarchy.

The generic ``child_parents`` grammar composes 'X del Y' chains into
full locator paths only when every link is a pure de-connector and
every (child -> parent) pair is declared admissible by the active
profile.  Anything weaker stays on the flat cascade — never a
fabricated parent:

  * 'letra n) del número 3 del apartado C) de la norma 49' composes
    ``norma:49.apartado:C.numero:3.letra:n`` — CNMV numbering restarts
    inside each lettered apartado, so the flat 'apartado:3' collided.
  * 'normas 43 a 48 de la sección 7' keeps the normas flat: a root is
    never a child and a governed sección mention is qualifier context.
  * 'La Sección Quinta queda redactada' materializes ``seccion:5``.
  * A multi-valued parent ('de los apartados B y C') is ambiguous — no
    path is emitted for the children.
  * A profile without ``child_parents`` (BdE) composes exactly as
    before — the machinery is inert.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import regdelta.profiles  # noqa: E402,F401  (registers bde-circular)
import regdelta.profiles.cnmv  # noqa: E402,F401  (registers cnmv)
from regdelta import operations  # noqa: E402
from regdelta.profile import use_profile  # noqa: E402

# registering a second profile disables lazy single-profile
# resolution — pin the default so unrelated tests keep resolving
# bde-circular exactly as before
use_profile("bde-circular")


def _subjects(clause: str):
    """Compose exactly as _parse_section does: subject-zone text feeds
    both the mention extraction and the path binding."""
    zone = operations._subject_zone(clause)
    return operations._compose_keys(
        operations._subject_mentions(zone), {}, {}, 0,
        clause_text=zone)


@pytest.fixture
def bde():
    use_profile("bde-circular")
    yield
    use_profile("bde-circular")


@pytest.fixture
def cnmv():
    use_profile("cnmv-circular")
    yield
    use_profile("bde-circular")


# -- positive: declared inside-out chains ----------------------------------


def test_full_chain_letra_numero_apartado_norma(cnmv):
    subs = _subjects(
        "Se modifica la letra n) del número 3 del apartado C) de la "
        "norma 49.ª, que queda redactada como sigue:")
    keys = [s.locator_key for s in subs]
    assert keys == ["norma:49.apartado:C.numero:3.letra:n"]
    # every component declared in the clause -> EXPLICIT_CLAUSE proof
    comps = subs[0].proof_components
    assert [(c[0], c[1]) for c in comps] == [
        ("norma", "49"), ("apartado", "C"), ("numero", "3"),
        ("letra", "n")]
    assert all(c[2] == "EXPLICIT_CLAUSE" for c in comps)


def test_inciso_maps_to_numeral(cnmv):
    subs = _subjects(
        "Se modifica el inciso (i) de la letra a) del número 1 del "
        "apartado A) de la norma 29.ª.")
    assert [s.locator_key for s in subs] == [
        "norma:29.apartado:A.numero:1.letra:a.numeral:i"]
    assert subs[0].kind == "NUMERAL"


def test_numero_under_lettered_apartado(cnmv):
    subs = _subjects(
        "Se modifica el número 8 del apartado B) de la norma 29.ª.")
    assert [s.locator_key for s in subs] == [
        "norma:29.apartado:B.numero:8"]
    assert subs[0].kind == "NUMERO"


def test_enum_children_share_one_declared_parent(cnmv):
    subs = _subjects(
        "Se modifican los números 14, 15 y 16 del apartado F) de la "
        "norma 29.ª.")
    assert [s.locator_key for s in subs] == [
        "norma:29.apartado:F.numero:14",
        "norma:29.apartado:F.numero:15",
        "norma:29.apartado:F.numero:16"]


def test_seccion_under_capitulo(cnmv):
    subs = _subjects(
        "Se modifica la sección segunda del capítulo primero.")
    assert [s.locator_key for s in subs] == ["capitulo:1.seccion:2"]


def test_lettered_apartado_enum(cnmv):
    subs = _subjects(
        "Se modifican los apartados B, C, D y F) de la norma 29.ª.")
    assert [s.locator_key for s in subs] == [
        "norma:29.apartado:B", "norma:29.apartado:C",
        "norma:29.apartado:D", "norma:29.apartado:F"]


# -- standalone section subjects -------------------------------------------


def test_standalone_seccion_ordinal_word(cnmv):
    subs = _subjects(
        "La Sección Quinta queda redactada del siguiente modo:")
    assert [s.locator_key for s in subs] == ["seccion:5"]
    assert subs[0].kind == "SECCION"


# -- negative: governed qualifiers and ambiguous parents -------------------


def test_governed_seccion_is_qualifier_not_parent(cnmv):
    subs = _subjects(
        "Se suprimen las normas 43 a 48 de la sección 7.")
    keys = [s.locator_key for s in subs]
    assert keys == [f"norma:{n}" for n in range(43, 49)]
    # no seccion subject, no seccion parented path
    assert not any("seccion" in k for k in keys)


def test_multi_valued_parent_is_ambiguous(cnmv):
    subs = _subjects(
        "Se suprimen los números 3 y 4 de los apartados B y C).")
    keys = [s.locator_key for s in subs]
    # no composed path may pick one apartado for the números
    assert not any("apartado:B.numero" in k or "apartado:C.numero" in k
                   for k in keys)


def test_governed_tail_does_not_bind(cnmv):
    subs = _subjects(
        "Se modifica el apartado 1 de la norma 5 conforme a la "
        "sección 2.")
    keys = [s.locator_key for s in subs]
    assert "norma:5.apartado:1" in keys
    assert not any("seccion" in k for k in keys)


# -- mutation: broken connectors fall back to the flat cascade --------------


def test_missing_connector_no_chain(cnmv):
    """'letra n) número 3' without a de-link must not compose — the
    cascade emits only what it emitted before WS-B."""
    subs = _subjects(
        "Se modifica la letra n) número 3 del apartado C) de la "
        "norma 49.ª.")
    keys = [s.locator_key for s in subs]
    assert "norma:49.apartado:C.numero:3.letra:n" not in keys


def test_missing_top_link_keeps_partial_path(cnmv):
    """'número 3 del apartado C) conforme a la norma 49' — 'conforme
    a' is no de-link, so the apartado does not bind the norma; the
    declared parent still composes under the clause's root."""
    subs = _subjects(
        "Se modifica el número 3 del apartado C) conforme a la "
        "norma 49, que queda redactada.")
    assert "norma:49.apartado:C.numero:3" in [
        s.locator_key for s in subs]


# -- profile isolation: BdE composes exactly as before ----------------------


def test_bde_no_child_parents_no_paths(bde):
    """The BdE profile declares no child_parents — the machinery is
    inert and the same clause keeps its flat composition."""
    clause = ("Se modifica la letra n) del número 3 del apartado C) "
              "de la norma 49.ª.")
    subs = _subjects(clause)
    keys = [s.locator_key for s in subs]
    assert not any("numero:" in k or ".apartado:C." in k
                   for k in keys)


def test_bde_seccion_not_materialized(bde):
    subs = _subjects(
        "La Sección Quinta queda redactada del siguiente modo:")
    assert not any(s.locator_key.startswith("seccion")
                   for s in subs)
