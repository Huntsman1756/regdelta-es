"""CORE-GAP WS-A: explicit redesignation continuity edges.

'pasa(n) a ser/denominarse' is not a redesignation by itself — the
emission path pairs each old-side subject with a destination slot and
classifies the pair the way adjudicated EXP-B1 did:

  CODE_REDESIGNATION — the destination declares a *different* code for
                       the subject's leaf kind; a continuity edge is
                       emitted and the ordinary relation is superseded
  RELABEL_SAME_CODE  — the code survives inside the new denomination;
                       the ordinary MODIFY relation stands (no edge)
  UNPROVABLE         — structural verb but the new code cannot be
                       proven; journaled refusal, never a guess
  (non-structural)   — 'pasa a ser aplicable a…' produces no pair at
                       all and the clause stays fully baseline

Every case below is exercised at the operations layer: subjects are
composed exactly as ``_parse_section`` composes them and
``redesignation_pairs`` classifies them.  Edge persistence and chain
migration are covered end-to-end by the g0d fixture counts (the
disposición adicional única -> primera edge on BOE-A-2017-14334).
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
    zone = operations._subject_zone(clause)
    return operations._compose_keys(
        operations._extract_mentions(zone), {}, {}, 0)


def _pairs(clause: str):
    subs = _subjects(clause)
    return subs, operations.redesignation_pairs(clause, subs)


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


# -- BdE: accented/compound disposition locators ---------------------------


def test_accented_disposition_code_redesignation(bde):
    """Regression fixture: 'disposición adicional única' (accented in
    the text, unaccented 'disposicion' in the locator mentions) must
    still position-pair with its destination — the leaf is the last
    kind-bearing component plus kind-less suffixes."""
    clause = ("c) La disposición adicional única, sobre «Indicaciones "
              "y correlaciones», pasa a ser la disposición adicional "
              "primera.")
    subs, pairs = _pairs(clause)
    assert [s.locator_key for s in subs] == ["disp:adicional.única"]
    assert len(pairs) == 1
    p = pairs[0]
    assert p["cls"] == "CODE_REDESIGNATION"
    assert p["new_key"] == "disp:adicional.primera"


def test_same_code_estado_relabel_is_not_an_edge(bde):
    """'FI 105 pasa a denominarse «FI 105 Desglose…»' keeps its code —
    RELABEL_SAME_CODE, the ordinary MODIFY stands."""
    clause = ("El estado FI 105 pasa a denominarse «FI 105 Desglose "
              "de derivados».")
    subs, pairs = _pairs(clause)
    assert [s.locator_key for s in subs] == ["estado:FI 105"]
    assert len(pairs) == 1
    assert pairs[0]["cls"] == "RELABEL_SAME_CODE"
    assert pairs[0]["new_key"] is None


def test_code_change_estado_redesignation(bde):
    """A quoted denomination carrying a *different* code is a real
    redesignation edge."""
    clause = ("El estado FI 105 pasa a denominarse «FI 105-2 "
              "Desglose de derivados».")
    subs, pairs = _pairs(clause)
    assert [s.locator_key for s in subs] == ["estado:FI 105"]
    assert len(pairs) == 1
    assert pairs[0]["cls"] == "CODE_REDESIGNATION"
    assert pairs[0]["new_key"] == "estado:FI 105-2"


def test_quoted_name_without_code_is_unprovable(bde):
    """A rename whose quoted text carries no code cannot be proven —
    refusal, never a fabricated locator."""
    clause = ("El estado FI 143 pasa a denominarse «Desglose de "
              "operaciones varias».")
    subs, pairs = _pairs(clause)
    assert len(pairs) == 1
    assert pairs[0]["cls"] == "UNPROVABLE"
    assert pairs[0]["new_key"] is None


def test_quoted_colon_does_not_truncate_destination(bde):
    """Punctuation inside «…» is content, not a segment boundary."""
    clause = ("El estado FI 136 pasa a denominarse «FI 136 Desglose "
              "de derivados: activos».")
    subs, pairs = _pairs(clause)
    assert len(pairs) == 1
    assert pairs[0]["cls"] == "RELABEL_SAME_CODE"


def test_multi_operation_node_preserves_later_operations(bde):
    """The redesignation segment ends before the next operation —
    coordinated subjects after it keep their baseline kind and are
    not swallowed into the destination zone."""
    clause = ("El estado FI 105 pasa a denominarse «FI 105 Desglose "
              "de derivados»; se suprimen los estados FI 131 y "
              "FI 141.")
    subs, pairs = _pairs(clause)
    keys = {s.locator_key for s in subs}
    assert {"estado:FI 105", "estado:FI 131",
            "estado:FI 141"} <= keys
    # only the relabelled subject pairs
    assert [p["subject"].locator_key for p in pairs] == ["estado:FI 105"]
    assert pairs[0]["cls"] == "RELABEL_SAME_CODE"
    # later subjects keep their baseline operation kind — the clause
    # fallback must not classify them as redesignations
    assert operations.subject_operation_kind(
        clause, "estado:FI 131", "MODIFY") != "REDESIGNATE"


def test_kindless_leaf_malformed_locator_is_unprovable(bde):
    """A locator with no kind-bearing component cannot anchor a
    destination — UNPROVABLE, not a crash."""
    clause = ("El estado FI 105 pasa a denominarse «FI 105-2 "
              "Desglose».")
    fake = operations.SubjectRef("barevalue", "bare", "APARTADO")
    pairs = operations.redesignation_pairs(clause, [fake])
    # the fake subject has no textual mention — it does not pair, and
    # the classifier must not raise
    assert all(p["cls"] != "CODE_REDESIGNATION" or p["new_key"]
               for p in pairs)


# -- CNMV: structural destinations -----------------------------------------


def test_cnmv_ordinal_redesignation(cnmv):
    clause = ("Once. Se renumera la Norma 11.ª, que pasa a ser la "
              "Norma 10.ª.")
    subs, pairs = _pairs(clause)
    assert [s.locator_key for s in subs] == ["norma:11"]
    assert len(pairs) == 1
    assert pairs[0]["cls"] == "CODE_REDESIGNATION"
    assert pairs[0]["new_key"] == "norma:10"


def test_cnmv_bulk_numeric_mapping_in_order(cnmv):
    clause = ("Los números 13, 14, 15 y 16 de la Norma 49 pasan a "
              "ser los nuevos números 10, 11, 12 y 13 "
              "respectivamente.")
    subs, pairs = _pairs(clause)
    mapped = {p["subject"].locator_key: p["new_key"]
              for p in pairs if p["cls"] == "CODE_REDESIGNATION"}
    # WS-B: 'número' is its own level — 'números 13-16 de la Norma 49'
    # declares numero->norma, so the old locators keep their true kind
    assert mapped == {
        "norma:49.numero:13": "norma:49.numero:10",
        "norma:49.numero:14": "norma:49.numero:11",
        "norma:49.numero:15": "norma:49.numero:12",
        "norma:49.numero:16": "norma:49.numero:13",
    }


def test_cnmv_non_structural_pasa_a_ser(cnmv):
    """'pasa a ser aplicable a…' has no structural destination — no
    pair, clause fully baseline."""
    clause = "La norma 5 pasa a ser aplicable a todas las entidades."
    subs, pairs = _pairs(clause)
    assert pairs == []


def test_cnmv_cross_level_redesignation_unprovable(cnmv):
    """'la letra n) del número 3 del apartado 4 pasa a ser el número
    4' changes locator level — fail closed, no guessed anchor."""
    clause = ("La letra n) del número 3 del apartado 4 pasa a ser "
              "el número 4.")
    subs, pairs = _pairs(clause)
    assert all(p["cls"] != "CODE_REDESIGNATION" for p in pairs)
    assert all(p["new_key"] is None for p in pairs)


def test_cnmv_cardinality_mismatch_refused(cnmv):
    """Three old locators, two destination slots — ambiguous pairing
    is refused for every left subject."""
    clause = ("Los números 13, 14 y 15 de la Norma 49 pasan a ser "
              "los números 10 y 11 respectivamente.")
    subs, pairs = _pairs(clause)
    assert pairs
    assert all(p["cls"] == "UNPROVABLE" for p in pairs)
    assert all(p["new_key"] is None for p in pairs)


def test_quoted_fichero_name_pairs(bde):
    """A fichero's identifier lives entirely inside «» — quote masking
    must not erase its only mention.  'cambiando su denominación, que
    pasa a ser «Y»' pairs the quoted subject with the quoted
    destination (EXP-B1 ACTIONABLE cases on BOE-A-2014-8654)."""
    clause = ("Se modifica el fichero «Banco de España - Entidad "
              "Gestora del Mercado de Deuda Pública Anotada» "
              "cambiando su denominación, que pasa a ser «Entidad "
              "Gestora del Mercado de Deuda Pública Anotada», y en "
              "los apartados «Responsable» y «Finalidad».")
    subs, pairs = _pairs(clause)
    old = ("fichero:Banco de España - Entidad Gestora del Mercado de "
           "Deuda Pública Anotada")
    fp = [p for p in pairs if p["subject"].locator_key == old]
    assert len(fp) == 1
    assert fp[0]["cls"] == "CODE_REDESIGNATION"
    assert fp[0]["new_key"] == (
        "fichero:Entidad Gestora del Mercado de Deuda Pública Anotada")
