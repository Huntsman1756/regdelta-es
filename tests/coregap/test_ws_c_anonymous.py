"""CORE-GAP WS-C: anonymous structural identity.

Three identity regimes, all fail-closed:

  * ``disp:<tipo>`` — a bare 'Norma/Disposición <tipo>' head is a
    source-declared class identity. It resolves only when the head is
    unique in the target; a repeated bare head is ambiguous and the
    key never resolves.
  * ``parrafo:N`` / ``guion:N`` — positional kinds. They compose as
    the leaf of a declared inside-out chain or under a proven
    root/context; binding proves ordinal position inside the parent
    span. They can never head a locator.
  * Anonymous items ('los dos guiones', 'el último párrafo') carry no
    modelable ordinal — they surface as ``op.unkeyed`` and are
    journaled UNKEYED_ANONYMOUS_ITEM; a positional anchor captured for
    them is suppressed, never bound as the subject.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import regdelta.profiles  # noqa: E402,F401  (registers bde-circular)
import regdelta.profiles.cnmv  # noqa: E402,F401  (registers cnmv)
from regdelta import operations, ownership  # noqa: E402
from regdelta.document import DiarioDoc, Node  # noqa: E402
from regdelta.profile import use_profile  # noqa: E402

# registering a second profile disables lazy single-profile
# resolution — pin the default so unrelated tests keep resolving
# bde-circular exactly as before
use_profile("bde-circular")


def _subjects(clause: str, ctx=None):
    zone = operations._subject_zone(clause)
    return operations._compose_keys(
        operations._subject_mentions(zone), ctx or {}, {}, 0,
        clause_text=zone)


def _doc(specs):
    """specs: [(cls, text), ...] — all nodes are paragraph kind."""
    return DiarioDoc(nodes=[
        Node(index=i, kind="p", cls=c, text=t)
        for i, (c, t) in enumerate(specs)])


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


# -- positive: unnumbered disposition class identity ------------------------


def test_bare_disposicion_class_key(cnmv):
    subs = _subjects("Se modifica la norma transitoria.")
    assert [s.locator_key for s in subs] == ["disp:transitoria"]
    assert subs[0].kind == "DISPOSICION"


def test_numbered_disposicion_keeps_ordinal(cnmv):
    subs = _subjects(
        "Se modifica la disposición transitoria primera.")
    assert [s.locator_key for s in subs] == [
        "disp:transitoria.primera"]


def test_bare_disposicion_norma_spelling(cnmv):
    subs = _subjects("Se añade un apartado a la norma final.")
    keys = [s.locator_key for s in subs]
    assert "disp:final" in keys


# -- positive: positional leaves --------------------------------------------


def test_guion_leaf_full_chain(cnmv):
    subs = _subjects(
        "Se elimina el tercer guión del número 4 del apartado 12 "
        "de la norma 30.")
    assert [s.locator_key for s in subs] == [
        "norma:30.apartado:12.numero:4.guion:3"]
    assert subs[0].kind == "GUION"


def test_parrafo_kind_first_order(cnmv):
    subs = _subjects(
        "Se modifica el párrafo segundo de la norma 7.ª.")
    assert [s.locator_key for s in subs] == ["norma:7.parrafo:2"]


def test_parrafo_ordinal_first_order(cnmv):
    subs = _subjects(
        "Se modifica el segundo párrafo de la norma 7.ª.")
    assert [s.locator_key for s in subs] == ["norma:7.parrafo:2"]


def test_parrafo_a_destination_link(cnmv):
    subs = _subjects(
        "Se añade un nuevo párrafo tercero a la letra d) del "
        "apartado 2 de la norma 5.")
    assert [s.locator_key for s in subs] == [
        "norma:5.apartado:2.letra:d.parrafo:3"]


def test_parrafo_enum_under_shared_parent(cnmv):
    subs = _subjects(
        "Se da nueva redacción a los párrafos primero y tercero del "
        "punto 1 del apartado 1 de la norma 4.")
    assert [s.locator_key for s in subs] == [
        "norma:4.apartado:1.punto:1.parrafo:1",
        "norma:4.apartado:1.punto:1.parrafo:3"]


def test_positional_under_context_root(cnmv):
    subs = _subjects(
        "En el primer párrafo de esta norma se sustituye "
        "«pesetas» por «euros».", ctx={"norma": "7"})
    assert "norma:7.parrafo:1" in [s.locator_key for s in subs]


def test_positional_under_disposicion(cnmv):
    subs = _subjects(
        "Se elimina el guión segundo de la disposición transitoria.")
    assert [s.locator_key for s in subs] == ["disp:transitoria.guion:2"]


# -- negative: anonymous and non-modelable forms ----------------------------


def test_cardinality_only_guiones_no_key(cnmv):
    subs = _subjects(
        "Se da una nueva redacción a los dos guiones que se "
        "incluyen a continuación del primer párrafo:")
    assert not any("guion:" in s.locator_key for s in subs)


def test_ultimo_parrafo_no_key(cnmv):
    subs = _subjects(
        "Se modifica el último párrafo de la norma 3.")
    assert not any("parrafo:" in s.locator_key for s in subs)


def test_positional_never_heads_locator(cnmv):
    assert not ownership.locator_resolves_in_doc(
        _doc([("parrafo", "- primer item"),
              ("parrafo", "- segundo item")]),
        "guion:2")


def test_rootless_positional_abstains(cnmv):
    # 'parrafo:1' with no proven parent scope cannot resolve —
    # no head declares it
    doc = _doc([("parrafo", "Texto uno."), ("parrafo", "Texto dos.")])
    assert not ownership.locator_resolves_in_doc(doc, "parrafo:1")


# -- ambiguous: repeated bare class heads fail closed -----------------------


def test_unique_bare_disp_resolves(cnmv):
    doc = _doc([
        ("articulo", "Norma primera. Algo."),
        ("parrafo", "contenido"),
        ("centro_cursiva", "Norma transitoria."),
        ("parrafo", "La disposición ordena."),
        ("articulo", "Norma segunda. Fin."),
    ])
    assert ownership.locator_resolves_in_doc(doc, "disp:transitoria")


def test_two_bare_disp_heads_ambiguous(cnmv):
    doc = _doc([
        ("centro_cursiva", "Norma transitoria."),
        ("parrafo", "uno"),
        ("centro_cursiva", "Norma transitoria."),
        ("parrafo", "dos"),
    ])
    assert not ownership.locator_resolves_in_doc(doc,
                                                 "disp:transitoria")


def test_ordinal_tail_rejects_bare_key(cnmv):
    # 'Norma transitoria primera' is the NUMBERED disposition — the
    # bare class key 'disp:transitoria' must not resolve against it
    doc = _doc([
        ("articulo", "Norma transitoria primera. Algo."),
        ("parrafo", "contenido"),
    ])
    assert not ownership.locator_resolves_in_doc(doc,
                                                 "disp:transitoria")
    assert ownership.locator_resolves_in_doc(
        doc, "disp:transitoria.primera")


def test_positional_component_inside_proven_disp(cnmv):
    doc = _doc([
        ("centro_cursiva", "Norma transitoria."),
        ("parrafo", "- primer guion"),
        ("parrafo", "- segundo guion"),
        ("articulo", "Norma final. Fin."),
    ])
    assert ownership.locator_resolves_in_doc(
        doc, "disp:transitoria.guion:2")
    assert not ownership.locator_resolves_in_doc(
        doc, "disp:transitoria.guion:3")


# -- unkeyed anonymous items -------------------------------------------------


def test_unkeyed_flags_cardinality_guion(cnmv):
    zone = operations._subject_zone(
        "Se da una nueva redacción a los dos guiones que se "
        "incluyen a continuación del primer párrafo:")
    mentions = operations._extract_mentions(zone)
    uk = operations._unkeyed_kinds(zone, mentions)
    assert "guion" in uk


def test_unkeyed_flags_ultimo_parrafo(cnmv):
    zone = operations._subject_zone(
        "Se modifica el último párrafo del artículo 20.")
    mentions = operations._extract_mentions(zone)
    uk = operations._unkeyed_kinds(zone, mentions)
    assert "parrafo" in uk
    assert "articulo" in uk


def test_unkeyed_silent_when_captured(cnmv):
    zone = operations._subject_zone(
        "Se elimina el tercer guión del número 4 del apartado 12 "
        "de la norma 30.")
    mentions = operations._extract_mentions(zone)
    assert "guion" not in operations._unkeyed_kinds(zone, mentions)


def test_anchor_subject_suppressed_for_unkeyed(cnmv):
    """'los dos guiones ... del primer párrafo' — the párrafo is the
    unkeyed items' anchor, not the amended entity."""
    subs = _subjects(
        "Se da una nueva redacción a los dos guiones que se "
        "incluyen a continuación del primer párrafo:",
        ctx={"norma": "1"})
    keys = [s.locator_key for s in subs]
    suppressed = operations._suppress_anchor_subjects(
        subs, ("guion",))
    assert "norma:1.parrafo:1" in keys
    assert all("parrafo:" not in s.locator_key for s in suppressed)


def test_nonpositional_unkeyed_keeps_positional_subjects(cnmv):
    """An unrelated opaque kind ('estado') does not suppress keyed
    positional subjects."""
    subs = _subjects(
        "Se da una nueva redacción a los párrafos primero y "
        "tercero del punto 1 del apartado 1 de la norma 4 "
        "del estado M.4.")
    kept = operations._suppress_anchor_subjects(subs, ("estado",))
    assert [s.locator_key for s in kept] == [
        s.locator_key for s in subs]


# -- positional node classification ------------------------------------------


def test_dash_node_is_guion_not_parrafo(cnmv):
    dash = Node(index=0, kind="p", cls="parrafo",
                text="- item de lista")
    prose = Node(index=1, kind="p", cls="parrafo",
                 text="párrafo normal")
    assert operations._positional_node(dash, "guion")
    assert not operations._positional_node(dash, "parrafo")
    assert operations._positional_node(prose, "parrafo")
    assert not operations._positional_node(prose, "guion")


# -- determinism and provenance ----------------------------------------------


def test_positional_composition_deterministic(cnmv):
    clause = ("Se elimina el tercer guión del número 4 del "
              "apartado 12 de la norma 30.")
    a = [s.locator_key for s in _subjects(clause)]
    b = [s.locator_key for s in _subjects(clause)]
    assert a == b


def test_positional_proof_components(cnmv):
    subs = _subjects(
        "En el primer párrafo de esta norma se sustituye "
        "«a» por «b».", ctx={"norma": "7"})
    sub = next(s for s in subs
               if s.locator_key == "norma:7.parrafo:1")
    kinds = {c[0]: c[2] for c in sub.proof_components}
    assert kinds["parrafo"] == "EXPLICIT_CLAUSE"
    assert kinds["norma"] == "INHERITED"


# -- profile isolation: BdE unchanged -----------------------------------------


def test_bde_no_positional_kinds(bde):
    subs = _subjects(
        "Se elimina el tercer guión del número 4 del apartado 12 "
        "de la norma 30.")
    assert not any("guion" in s.locator_key
                   or "parrafo" in s.locator_key for s in subs)


def test_bde_bare_disposicion_unchanged(bde):
    subs = _subjects("Se modifica la disposición transitoria.")
    keys = [s.locator_key for s in subs]
    # the BdE declaration requires an ordinal — a bare 'disposición
    # transitoria' was invisible to the baseline and stays invisible
    assert "disp:transitoria" not in keys
    subs = _subjects("Se modifica la disposición transitoria primera.")
    assert "disp:transitoria.primera" in [s.locator_key
                                        for s in subs]
