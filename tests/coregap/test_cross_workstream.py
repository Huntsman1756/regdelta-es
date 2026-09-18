"""CORE-GAP cross-workstream interaction tests (WS-A x WS-B x WS-C x WS-D).

Each test exercises a seam where two workstreams' semantics meet:

  A+B   redesignation of hierarchical locators — the edge must carry
        the full composed path on both sides, not just the leaf
  A+C   redesignation touching anonymous/class identity — an
        unnumbered class subject cannot pair with a destination it
        cannot anchor; positional leaves never redesignate
  C+A   scope/context normalization + redesignation — a scoped
        'punto' under an inherited anejo redesignates with the whole
        path
  B+D   hierarchical composition over image-backed evidence — only
        the declared anejo key binds image pages; deeper leaves and
        positionally filled anejos never image-bind
  C+D   declared vs positional annex identity — the declared_anejos
        gate after WS-C
  A+D   chain continuity across representation types — the edge
        migrates chain state verbatim (an IMAGE before-representation
        migrates to the new key; an unproven representation migrates
        as UNKNOWN, never resurrected)
  B     richer composition must not fabricate binding — a positional
        leaf cannot head a locator or resolve without a proven parent
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import regdelta.profiles  # noqa: E402,F401
import regdelta.profiles.cnmv  # noqa: E402,F401
from regdelta.profile import use_profile  # noqa: E402

use_profile("bde-circular")

from regdelta import annexmap, history, operations, ownership  # noqa: E402
from regdelta.document import DiarioDoc, Node  # noqa: E402


def _subjects(clause: str, ctx=None):
    zone = operations._subject_zone(clause)
    return operations._compose_keys(
        operations._subject_mentions(zone), ctx or {}, {}, 0,
        clause_text=zone)


def _pairs(clause: str, ctx=None):
    subs = _subjects(clause, ctx)
    return subs, operations.redesignation_pairs(clause, subs)


def _doc(specs):
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


# -- A+B: hierarchical redesignation ----------------------------------------


def test_ab_deep_hierarchy_redesignation_keeps_parent(cnmv):
    """'el apartado 2 de la Norma 5 pasa a ser el apartado 3' — the
    edge carries norma:5.apartado:2 -> norma:5.apartado:3, not a flat
    leaf swap."""
    subs, pairs = _pairs(
        "El apartado 2 de la Norma 5 pasa a ser el apartado 3.")
    assert [s.locator_key for s in subs] == ["norma:5.apartado:2"]
    assert len(pairs) == 1
    assert pairs[0]["cls"] == "CODE_REDESIGNATION"
    assert pairs[0]["new_key"] == "norma:5.apartado:3"


def test_ab_three_level_redesignation_inherits_parent(cnmv):
    """'el número 3 del apartado 4 de la Norma 30 pasa a ser el
    número 5' — a bare destination code inherits the subject's
    proven parent path: the edge is the full three-level path."""
    subs, pairs = _pairs(
        "El número 3 del apartado 4 de la Norma 30 pasa a ser "
        "el número 5.")
    assert [s.locator_key for s in subs] == [
        "norma:30.apartado:4.numero:3"]
    assert len(pairs) == 1
    assert pairs[0]["cls"] == "CODE_REDESIGNATION"
    assert pairs[0]["new_key"] == "norma:30.apartado:4.numero:5"


# -- A+C: redesignation touching anonymous identity --------------------------


def test_ac_unnumbered_disp_class_no_redesignation(cnmv):
    """'la disposición transitoria pasa a ser la disposición
    transitoria segunda' — the bare class subject composes
    (disp:transitoria) but cannot pair: the destination is a *new*
    member of the class, not a redesignation of this one. No edge,
    no fabricated continuity."""
    subs, pairs = _pairs(
        "La disposición transitoria pasa a ser la disposición "
        "transitoria segunda.")
    assert [s.locator_key for s in subs] == ["disp:transitoria"]
    assert all(p["cls"] != "CODE_REDESIGNATION" for p in pairs)


def test_ac_numbered_disp_class_redesignation(cnmv):
    subs, pairs = _pairs(
        "La disposición transitoria única pasa a ser la disposición "
        "transitoria segunda.")
    assert [s.locator_key for s in subs] == ["disp:transitoria.única"]
    assert len(pairs) == 1
    assert pairs[0]["cls"] == "CODE_REDESIGNATION"
    assert pairs[0]["new_key"] == "disp:transitoria.segunda"


def test_ac_positional_leaf_never_redesignates(cnmv):
    """'el tercer guión … pasa a ser el segundo guión' — positional
    identity is a derived address inside a parent; it cannot be the
    endpoint of a continuity edge. No pair, no fabricated key."""
    subs, pairs = _pairs(
        "El tercer guión del número 4 del apartado 12 de la norma "
        "30 pasa a ser el segundo guión.")
    assert all(p["cls"] != "CODE_REDESIGNATION" for p in pairs)


# -- C+A: scope/context normalization + redesignation -------------------------


def test_ca_context_scoped_punto_redesignation(cnmv):
    """'punto 3 pasa a ser el punto 4' inside an inherited anejo:2
    scope — both sides compose under the scoped parent."""
    subs, pairs = _pairs(
        "El punto 3 pasa a ser el punto 4.", ctx={"anejo": "2"})
    assert [s.locator_key for s in subs] == ["anejo:2.punto:3"]
    assert len(pairs) == 1
    assert pairs[0]["cls"] == "CODE_REDESIGNATION"
    assert pairs[0]["new_key"] == "anejo:2.punto:4"


# -- B+D / C+D: image binding over declared vs positional identity ------------


def _synthetic_amap():
    """8-page annex: pages 0-1 preannex, pages 2-3 an INDEX run (10+
    codes, no ANEJO heading — positional boundary), page 4 declares
    'ANEJO 2', pages 4-7 its content."""
    texts = [
        "texto previo",
        "mas texto previo",
        "FI 1 FI 2 FI 3 FI 4 FI 5 FI 6 FI 7 FI 8 FI 9 FI 10",
        "FI 11 FI 12 FI 13 FI 14 FI 15 FI 16 FI 17 FI 18 FI 19 FI 20",
        "ANEJO 2\ncontenido",
        "contenido",
        "contenido",
        "contenido",
    ]
    return annexmap.build_annex_map(texts, 100, 6, [])


def test_bd_declared_anejo_binds_image_pages(bde):
    amap = _synthetic_amap()
    pages = amap.subject_pages("anejo:2")
    assert pages == [104, 105, 106, 107]


def test_bd_nested_leaf_never_image_binds(bde):
    """A deeper component under a declared anejo does not image-bind
    — 'anejo:2.punto:1' is a structural address, not a page set."""
    amap = _synthetic_amap()
    assert amap.subject_pages("anejo:2.punto:1") is None
    assert amap.subject_pages("anejo:2.nota:a") is None


def test_cd_positional_fill_anejo_never_binds(bde):
    """The index-run boundary mints 'anejo:1' positionally — a derived
    address, never a declared identity: subject_pages refuses it."""
    amap = _synthetic_amap()
    assert "1" not in amap.declared_anejos
    assert "2" in amap.declared_anejos
    assert amap.subject_pages("anejo:1") is None
    # the derived span exists for structural use but feeds no image
    assert amap.anejo_pages.get("1") == [102, 103]


# -- A+D: chain continuity across representation types ------------------------


def _edge_ctx():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE subjects (subject_id TEXT, instrument_id TEXT,"
        " locator_key TEXT, label TEXT, subject_kind TEXT)")
    conn.execute(
        "CREATE TABLE subject_redesignations (edge_id TEXT,"
        " target_instrument_id TEXT, modifier_instrument_id TEXT,"
        " old_locator_key TEXT, new_locator_key TEXT,"
        " old_subject_id TEXT, new_subject_id TEXT, clause_text TEXT,"
        " node_index INTEGER, publication_date TEXT, resolution TEXT,"
        " edge_proof TEXT, source_snapshot_ids TEXT,"
        " parser_name TEXT, parser_version TEXT)")
    ctx = history._Ctx(conn=conn, acquirer=None, checked_at="t")
    return ctx, conn


def _edge_entries(old_key, new_key):
    sub = operations.SubjectRef(old_key, old_key.replace(":", " "),
                                "ESTADO")
    decl = ownership.LocatorDeclaration(
        ownership.LOC_PROVEN, old_key, (), 0, "COMPOSED", None)
    pair = {"cls": "CODE_REDESIGNATION", "new_key": new_key,
            "dest": {"kind": "estado", "value": new_key.split(":")[1]}}
    return sub, [(sub, decl, pair)]


def _emit(ctx, conn, entries, chain):
    sub, ents = entries
    pm = {"boe_id": "MOD-1", "snapshot": "snap-mod",
          "pub": "2020-01-01",
          "inventory": {"redesignation_edges": 0}}
    op = SimpleNamespace(clause_text="pasa a ser", node_index=0)
    history._emit_redesignation_edges(
        ctx, conn, pm, op, ents, chain, "T-1", "snap-xml")


def test_ad_edge_migrates_image_representation(bde):
    """An IMAGE before-representation migrates to the new key as-is —
    the redesignation changes the address, not the bytes. The edge
    resolves because the old state was PRESENT."""
    ctx, conn = _edge_ctx()
    chain = {"estado:FI 1": history.SubjectState(
        "PRESENT", "img-rep-id", "rel-1")}
    _emit(ctx, conn, _edge_entries("estado:FI 1", "estado:FI 2"), chain)
    assert chain["estado:FI 2"].status == "PRESENT"
    assert chain["estado:FI 2"].representation_id == "img-rep-id"
    assert chain["estado:FI 1"].status == "DELETED"
    row = conn.execute(
        "SELECT resolution, old_locator_key, new_locator_key"
        " FROM subject_redesignations").fetchone()
    assert row == ("RESOLVED", "estado:FI 1", "estado:FI 2")


def test_ad_edge_continuity_when_representation_unproven(bde):
    """Old state UNKNOWN (representation could not be proven): the new
    key inherits UNKNOWN — continuity is recorded without resurrecting
    or fabricating a representation."""
    ctx, conn = _edge_ctx()
    chain = {"estado:FI 1": history.SubjectState(
        "UNKNOWN", None, "rel-0")}
    _emit(ctx, conn, _edge_entries("estado:FI 1", "estado:FI 2"), chain)
    assert chain["estado:FI 2"].status == "UNKNOWN"
    assert chain["estado:FI 2"].representation_id is None
    assert chain["estado:FI 1"].status == "DELETED"
    row = conn.execute(
        "SELECT resolution FROM subject_redesignations").fetchone()
    assert row[0] == "DECLARED"


# -- B: richer composition must not fabricate binding -------------------------


def test_b_positional_leaf_cannot_head_locator(cnmv):
    doc = _doc([
        ("articulo", "Norma 5. Título"),
        ("parrafo", "– ítem uno"),
        ("parrafo", "– ítem dos"),
        ("parrafo", "– ítem tres"),
    ])
    assert not ownership.locator_resolves_in_doc(doc, "guion:3")
    assert not ownership.locator_resolves_in_doc(doc, "parrafo:2")


def test_b_positional_leaf_resolves_only_inside_proven_parent(cnmv):
    doc = _doc([
        ("articulo", "Norma 5. Título"),
        ("parrafo", "– ítem uno"),
        ("parrafo", "– ítem dos"),
        ("parrafo", "– ítem tres"),
        ("articulo", "Norma 6. Otro"),
        ("parrafo", "– único ítem"),
    ])
    assert ownership.locator_resolves_in_doc(doc, "norma:5.guion:3")
    assert not ownership.locator_resolves_in_doc(doc, "norma:5.guion:4")
    # absent parent -> no positional resolution
    assert not ownership.locator_resolves_in_doc(doc, "norma:9.guion:1")
