"""CORE-GAP mutation/adversarial coverage for the new semantics.

Every test perturbs an input or drives a boundary the happy-path
tests never reach, and asserts the system fails closed: abstain,
journal, refuse — never fabricate identity, binding, or continuity.

Covered seams:
  * redesignation edge refusals (cycle, self, collision,
    destination-already-exists, unanchored destination)
  * image representation failure modes (missing page map, alt out of
    range, acquisition failure) — no partial locator is ever emitted
  * annex map adversarial inputs (declared vs positional identity,
    tampered/garbled page numbers, mismatched anchors)
  * positional leaf boundaries (index 0, out-of-range, non-ordinal)
  * unnumbered disposition ambiguity and qualifier mutation
  * scope-word normalization adversarial values
  * provenance fail-closed (no components / unmodelled qualifier)
  * determinism under repetition
"""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# redesignation edge refusals (WS-A adversarial)
# ---------------------------------------------------------------------------


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
    return history._Ctx(conn=conn, acquirer=None, checked_at="t"), conn


def _entry(old_key, new_key):
    sub = operations.SubjectRef(old_key, old_key.replace(":", " "),
                                "ESTADO")
    decl = ownership.LocatorDeclaration(
        ownership.LOC_PROVEN, old_key, (), 0, "COMPOSED", None)
    pair = {"cls": "CODE_REDESIGNATION", "new_key": new_key,
            "dest": {"kind": "estado",
                     "value": new_key.split(":", 1)[1]
                     if new_key else None}}
    return (sub, decl, pair)


def _emit(ctx, conn, entries, chain):
    pm = {"boe_id": "MOD-1", "snapshot": "snap-mod",
          "pub": "2020-01-01",
          "inventory": {"redesignation_edges": 0}}
    op = SimpleNamespace(clause_text="pasa a ser", node_index=0)
    history._emit_redesignation_edges(
        ctx, conn, pm, op, entries, chain, "T-1", "snap-xml")


def _refusals(ctx):
    return [a["detail"]["reason"] for a in ctx.anomalies
            if a["kind"] == "REDESIGNATION_REFUSED"]


def test_edge_cycle_a_b_b_a_refused(bde):
    ctx, conn = _edge_ctx()
    chain = {}
    _emit(ctx, conn,
          [_entry("estado:FI 1", "estado:FI 2"),
           _entry("estado:FI 2", "estado:FI 1")],
          chain)
    assert _refusals(ctx).count("redesignation_cycle") == 2
    assert conn.execute(
        "SELECT count(*) FROM subject_redesignations").fetchone()[0] == 0
    assert chain == {}


def test_edge_self_redesignation_refused(bde):
    ctx, conn = _edge_ctx()
    _emit(ctx, conn, [_entry("estado:FI 1", "estado:FI 1")], {})
    assert _refusals(ctx) == ["self_redesignation"]
    assert conn.execute(
        "SELECT count(*) FROM subject_redesignations").fetchone()[0] == 0


def test_edge_new_key_collision_refused(bde):
    """Two different old locators redesignated onto the same new key —
    the second is refused; the first still emits."""
    ctx, conn = _edge_ctx()
    chain = {"estado:FI 1": history.SubjectState("PRESENT", "r1", "x"),
             "estado:FI 9": history.SubjectState("PRESENT", "r9", "y")}
    _emit(ctx, conn,
          [_entry("estado:FI 1", "estado:FI 2"),
           _entry("estado:FI 9", "estado:FI 2")],
          chain)
    assert _refusals(ctx) == ["new_key_collision"]
    rows = conn.execute(
        "SELECT old_locator_key FROM subject_redesignations").fetchall()
    assert rows == [("estado:FI 1",)]


def test_edge_destination_already_exists_refused(bde):
    """new_key already has a proven independent existence — merging
    would fabricate identity."""
    ctx, conn = _edge_ctx()
    chain = {"estado:FI 1": history.SubjectState("PRESENT", "r1", "x"),
             "estado:FI 2": history.SubjectState("PRESENT", "r2", "y")}
    _emit(ctx, conn, [_entry("estado:FI 1", "estado:FI 2")], chain)
    assert _refusals(ctx) == ["destination_already_exists"]
    assert conn.execute(
        "SELECT count(*) FROM subject_redesignations").fetchone()[0] == 0


def test_edge_unanchored_destination_refused(bde):
    ctx, conn = _edge_ctx()
    sub = operations.SubjectRef("estado:FI 1", "estado FI 1", "ESTADO")
    decl = ownership.LocatorDeclaration(
        ownership.LOC_PROVEN, "estado:FI 1", (), 0, "COMPOSED", None)
    pair = {"cls": "UNPROVABLE", "new_key": None, "dest": None}
    _emit(ctx, conn, [(sub, decl, pair)], {})
    assert _refusals(ctx) == ["destination_not_anchored"]


def test_edge_emission_deterministic(bde):
    ctx1, conn1 = _edge_ctx()
    ctx2, conn2 = _edge_ctx()
    for ctx, conn in ((ctx1, conn1), (ctx2, conn2)):
        chain = {"estado:FI 1": history.SubjectState(
            "PRESENT", "rid", "rel")}
        _emit(ctx, conn, [_entry("estado:FI 1", "estado:FI 2")], chain)
    r1 = conn1.execute("SELECT * FROM subject_redesignations").fetchall()
    r2 = conn2.execute("SELECT * FROM subject_redesignations").fetchall()
    assert r1 == r2


# ---------------------------------------------------------------------------
# image representation failure modes (WS-D adversarial)
# ---------------------------------------------------------------------------


class _Art:
    def __init__(self, snap="s", sha="a" * 64):
        self.snapshot_id = snap
        self.blob_sha256 = sha


class _Acq:
    def __init__(self, fail=False):
        self.fail = fail

    def get(self, *a, **k):
        return None if self.fail else _Art()


def _img_ctx(conn, n_imgs=2, fail=False):
    ctx = history._Ctx(conn=conn, acquirer=_Acq(fail), checked_at="t")
    ctx.doc_images["X"] = [
        SimpleNamespace(src=f"/datos/imagenes/disp/x/{i}.png")
        for i in range(1, n_imgs + 1)]
    ctx.annex_pdf_sha["X"] = "f" * 64
    return ctx


def _rep_schema():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE representations (representation_id TEXT,"
        " subject_id TEXT, representation_kind TEXT, content_sha256"
        " TEXT, text_content TEXT, artifact_locator TEXT,"
        " source_snapshot_id TEXT, binding TEXT, binding_evidence"
        " TEXT, parser_name TEXT, parser_version TEXT)")
    return conn


def _amap_for(img_by_page):
    return annexmap.AnnexMap(
        pages=[annexmap.PageEntry(9, p, "CONTENT", "FI 1", img_alt=a)
               for p, a in img_by_page.items()],
        img_by_page=img_by_page, anchored=True)


def test_image_missing_page_map_returns_none(bde):
    conn = _rep_schema()
    ctx = _img_ctx(conn)
    rid = history._image_representation(
        ctx, "sid", "X", [100, 999], _amap_for({100: 1}),
        "ANCHORED_DERIVED", {})
    assert rid is None
    assert conn.execute(
        "SELECT count(*) FROM representations").fetchone()[0] == 0


def test_image_alt_out_of_range_returns_none(bde):
    conn = _rep_schema()
    ctx = _img_ctx(conn, n_imgs=1)
    rid = history._image_representation(
        ctx, "sid", "X", [100], _amap_for({100: 5}),
        "ANCHORED_DERIVED", {})
    assert rid is None


def test_image_acquisition_failure_returns_none(bde):
    conn = _rep_schema()
    ctx = _img_ctx(conn, fail=True)
    rid = history._image_representation(
        ctx, "sid", "X", [100], _amap_for({100: 1}),
        "ANCHORED_DERIVED", {})
    assert rid is None


# ---------------------------------------------------------------------------
# annex map adversarial (declared vs positional, garbled numbers, anchors)
# ---------------------------------------------------------------------------


def _annex_texts():
    return [
        "texto previo",
        "mas texto previo",
        "FI 1 FI 2 FI 3 FI 4 FI 5 FI 6 FI 7 FI 8 FI 9 FI 10",
        "FI 11 FI 12 FI 13 FI 14 FI 15 FI 16 FI 17 FI 18 FI 19 FI 20",
        "ANEJO 2\ncontenido",
        "contenido",
        "contenido",
        "contenido",
    ]


def test_annex_map_deterministic_twice(bde):
    a = annexmap.build_annex_map(_annex_texts(), 100, 6, [])
    b = annexmap.build_annex_map(_annex_texts(), 100, 6, [])
    assert a.declared_anejos == b.declared_anejos
    assert a.anejo_pages == b.anejo_pages
    assert a.img_by_page == b.img_by_page


def test_annex_map_anchor_mismatch_not_anchored(bde):
    """A correction citation that does not match the detected span
    keeps the map UNANCHORED — the derived binding is not promoted."""
    amap = annexmap.build_annex_map(
        _annex_texts(), 100, 6, [(104, "UEM 99")])
    assert amap.anchored is False
    assert amap.anchors[0]["match"] is False


def test_annex_map_garbled_page_numbers_fall_back(bde):
    """Garbled embedded page numbers fall back to the sequential
    issue-page derivation — never a fabricated number."""
    texts = _annex_texts()
    texts[4] = "Pág. ZZZZZ\nANEJO 2\ncontenido"  # no valid number
    amap = annexmap.build_annex_map(texts, 100, 6, [])
    assert [p.boe_page for p in amap.pages] == list(range(100, 108))


def test_annex_map_heading_without_number_not_declared(bde):
    texts = _annex_texts()
    texts[4] = "ANEJO\ncontenido"   # bare 'ANEJO' declares no number
    amap = annexmap.build_annex_map(texts, 100, 6, [])
    assert "2" not in amap.declared_anejos


# ---------------------------------------------------------------------------
# positional leaf boundaries (WS-C adversarial)
# ---------------------------------------------------------------------------


def _guion_doc():
    return _doc([
        ("articulo", "Norma 5. Título"),
        ("parrafo", "– ítem uno"),
        ("parrafo", "– ítem dos"),
        ("parrafo", "– ítem tres"),
        ("articulo", "Norma 6. Otro"),
    ])


def test_positional_index_zero_never_resolves(cnmv):
    assert not ownership.locator_resolves_in_doc(
        _guion_doc(), "norma:5.guion:0")


def test_positional_out_of_range_never_resolves(cnmv):
    assert not ownership.locator_resolves_in_doc(
        _guion_doc(), "norma:5.guion:4")
    assert not ownership.locator_resolves_in_doc(
        _guion_doc(), "norma:5.guion:99")


def test_positional_span_boundary_exact(cnmv):
    """guion:3 does not bleed across the next norma head — the
    positional count is bounded by the parent span."""
    assert ownership.locator_resolves_in_doc(
        _guion_doc(), "norma:5.guion:3")
    assert not ownership.locator_resolves_in_doc(
        _guion_doc(), "norma:6.guion:1")


# ---------------------------------------------------------------------------
# unnumbered disposition ambiguity / qualifier mutation (WS-C adversarial)
# ---------------------------------------------------------------------------


def test_two_bare_heads_same_class_unresolvable(cnmv):
    doc = _doc([
        ("articulo", "Norma transitoria. Primera"),
        ("parrafo", "contenido"),
        ("articulo", "Norma transitoria. Segunda"),
        ("parrafo", "contenido"),
    ])
    assert not ownership.locator_resolves_in_doc(
        doc, "disp:transitoria")


def test_unmodelled_qualifier_not_provable(cnmv):
    """'la norma 64 bis' — a qualifier the locator model cannot
    express: prove_locator abstains rather than degrade to norma:64."""
    op = SimpleNamespace(
        clause_text="Se modifica la norma 64 bis.", node_index=0)
    sub = operations.SubjectRef("norma:64", "norma 64", "NORMA",
                                proof_components=(
                                    ("norma", "64", "EXPLICIT_CLAUSE",
                                     0, None),))
    decl = ownership.prove_locator(op, sub)
    assert decl.status == ownership.LOC_NOT_PROVABLE


def test_no_components_not_provable(cnmv):
    op = SimpleNamespace(clause_text="Se modifica.", node_index=0)
    sub = operations.SubjectRef("norma:1", "norma 1", "NORMA")
    decl = ownership.prove_locator(op, sub)
    assert decl.status == ownership.LOC_NOT_PROVABLE
    assert decl.method == "NO_COMPONENT_PROOF"


# ---------------------------------------------------------------------------
# scope-word normalization adversarial (WS-C)
# ---------------------------------------------------------------------------


def test_scope_word_anejo_number_normalizes_to_punto(cnmv):
    kinds = {"anejo", "punto"}
    assert history._scope_word_kind(
        "números", kinds, "anejo:3.punto:2") == "punto"
    assert history._scope_word_kind(
        "número", kinds, "anejo:3.punto:2") == "punto"


def test_scope_word_unknown_passthrough(bde):
    """An unrecognized scope word passes through — the caller decides
    suppression; the mapper never invents a kind."""
    assert history._scope_word_kind(
        "recuadro", {"anejo"}, "anejo:1") == "recuadro"


def test_scope_word_plural_accent(cnmv):
    assert history._scope_word_kind(
        "secciones", {"seccion"}, "seccion:1") == "seccion"
    assert history._scope_word_kind(
        "índice", {"indice"}, "anejo:9.indice") == "indice"


# ---------------------------------------------------------------------------
# continuation / unkeyed anonymous items (WS-C adversarial)
# ---------------------------------------------------------------------------


def test_cardinality_variants_all_unkeyed(cnmv):
    for word in ("los dos guiones", "los tres guiones",
                 "los cuatro guiones"):
        zone = operations._subject_zone(
            f"Se da una nueva redacción a {word} del primer "
            "párrafo.")
        flagged = operations._unkeyed_kinds(
            zone, operations._extract_mentions(zone))
        assert "guion" in flagged


def test_composition_deterministic_repeated(cnmv):
    zone = operations._subject_zone(
        "Se modifica el tercer guión del número 4 del apartado 12 "
        "de la norma 30.")
    first = None
    for _ in range(20):
        subs = operations._compose_keys(
            operations._subject_mentions(zone), {}, {}, 0,
            clause_text=zone)
        keys = [s.locator_key for s in subs]
        if first is None:
            first = keys
        assert keys == first
