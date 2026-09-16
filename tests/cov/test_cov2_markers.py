"""COV-2 F2: tolerant structural marker enumeration.

BOE circulars mark up sub-locators in more than one typographic form:
apartados appear as '1.' *and* as '1 La cuenta…', compound codes as
'9.1 …', and disposición ordinals travel as bare dotted segments
('disp:transitoria.primera').  The binder must enumerate every
candidate under each form and still decide strictly by count (B1/B5):
one candidate binds, several abstain AMBIGUOUS.

A candidate region ends at the next marker of its own level or any
outer level — never at a child marker: 'a)' opens content *inside*
apartado 1, it does not start a new apartado.  Without that, nested
keys like 'norma:55.apartado:1.letra:h' can never resolve.

Unit tests use synthetic documents; the integration test reconstructs
a DEV target purely from the frozen evidence manifest.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from regdelta import binding  # noqa: E402
from regdelta.sources.boe_diario import DiarioDoc, Node  # noqa: E402


def _p(i: int, text: str, cls: str = "parrafo") -> Node:
    return Node(index=i, kind="p", cls=cls, text=text)


def _doc(*nodes: Node) -> DiarioDoc:
    return DiarioDoc(nodes=list(nodes))


def _decide(doc: DiarioDoc, key: str) -> binding.BindingResult:
    cands = [
        binding.Candidate("T", None, "TEXT", key, sp, {}, "probe")
        for sp in binding.text_region_candidates(doc, key)]
    return binding.decide(cands, key, "PROBE")


# -- undotted numeric markers ---------------------------------------------


def test_undotted_numeric_marker_is_a_candidate():
    doc = _doc(
        _p(0, "Norma 55. Cuenta de pérdidas y ganancias.", "articulo"),
        _p(1, "1 La cuenta de pérdidas y ganancias se presentará"),
        _p(2, "a) Ingresos por intereses"),
        _p(3, "b) Gastos por intereses"),
        _p(4, "2 Otra cuestión distinta"),
    )
    res = _decide(doc, "norma:55.apartado:1")
    assert res.status == binding.BOUND
    assert res.chosen.node_span == (1, 4)


def test_dotted_numeric_marker_still_binds():
    doc = _doc(
        _p(0, "Norma 5. Disposiciones.", "articulo"),
        _p(1, "1. Primer apartado"),
        _p(2, "2. Segundo apartado"),
    )
    res = _decide(doc, "norma:5.apartado:1")
    assert res.status == binding.BOUND
    assert res.chosen.node_span == (1, 2)


def test_prose_number_is_not_a_marker():
    doc = _doc(
        _p(0, "Norma 5. Disposiciones.", "articulo"),
        _p(1, "2 de julio de 2010 entró en vigor"),
        _p(2, "2 000 euros será la cuantía"),
    )
    assert _decide(doc, "norma:5.apartado:2").status == \
        binding.NOT_FOUND


def test_union_of_marker_forms_yields_ambiguity():
    """Both '2.' and '2 Texto' present in one scope: two candidates —
    B5 degrades to AMBIGUOUS, never first-wins."""
    doc = _doc(
        _p(0, "Norma 5. Disposiciones.", "articulo"),
        _p(1, "2. Primer apartado"),
        _p(2, "2 Texto sin punto"),
    )
    res = _decide(doc, "norma:5.apartado:2")
    assert res.status == binding.AMBIGUOUS
    assert res.candidate_count == 2


# -- compound (dotted) codes ------------------------------------------------


def test_compound_apartado_code_binds():
    doc = _doc(
        _p(0, "ANEJO 4", "anexo_num"),
        _p(1, "9.1 Primer subapartado"),
        _p(2, "9.2 Segundo subapartado"),
    )
    res = _decide(doc, "anejo:4.apartado:9.1")
    assert res.status == binding.BOUND
    assert res.chosen.node_span == (1, 2)


def test_compound_code_does_not_prefix_match_deeper_sibling():
    doc = _doc(
        _p(0, "ANEJO 4", "anexo_num"),
        _p(1, "9.10 Otro código"),
        _p(2, "9.1.2 Nivel más profundo"),
    )
    assert _decide(doc, "anejo:4.apartado:9.1").status == \
        binding.NOT_FOUND


def test_dotted_anejo_head_resolves():
    doc = _doc(
        _p(0, "ANEJO 7.1 Primero", "anexo_num"),
        _p(1, "contenido"),
        _p(2, "ANEJO 7.3 Tercero", "anexo_num"),
        _p(3, "contenido"),
    )
    res = _decide(doc, "anejo:7.3")
    assert res.status == binding.BOUND
    assert res.chosen.node_span == (2, 4)


# -- bare ordinal segments ---------------------------------------------------


def test_disp_ordinal_bare_segment_resolves():
    doc = _doc(
        _p(0, "Disposición transitoria primera. Régimen.", "articulo"),
        _p(1, "1. Primer apartado"),
        _p(2, "2. Segundo apartado"),
    )
    res = _decide(doc, "disp:transitoria.primera.apartado:1")
    assert res.status == binding.BOUND
    assert res.chosen.node_span == (1, 2)


def test_unmodelled_bare_kind_still_fails():
    doc = _doc(
        _p(0, "ANEJO 5", "anexo_num"),
        _p(1, "contenido"),
    )
    assert _decide(doc, "anejo:5.indice").status == binding.NOT_FOUND


# -- nested levels ----------------------------------------------------------


def test_letra_inside_undotted_apartado_binds():
    """'norma:55.apartado:1.letra:h': the apartado's region runs to the
    next numeric marker, so its letra children are searchable."""
    doc = _doc(
        _p(0, "Norma 55. Cuenta de pérdidas y ganancias.", "articulo"),
        _p(1, "1 La cuenta de pérdidas y ganancias se presentará"),
        _p(2, "a) Ingresos por intereses"),
        _p(3, "h) Otros gastos de gestión"),
        _p(4, "2 Resultado del ejercicio"),
    )
    res = _decide(doc, "norma:55.apartado:1.letra:h")
    assert res.status == binding.BOUND
    assert res.chosen.node_span == (3, 4)


def test_letra_region_ends_at_next_numeric_marker():
    doc = _doc(
        _p(0, "Norma 5. Disposiciones.", "articulo"),
        _p(1, "a) Primero"),
        _p(2, "b) Segundo"),
        _p(3, "1. Otro apartado"),
    )
    res = _decide(doc, "norma:5.letra:a")
    assert res.status == binding.BOUND
    assert res.chosen.node_span == (1, 2)


def test_roman_i_is_indistinguishable_from_letra_i():
    """'i)' is textually both letra-i and roman numeral-i: it is a
    same-level marker, so it bounds a letra region — and searching
    'letra:i' over roman enumerations yields several candidates that
    degrade to AMBIGUOUS rather than first-win (B5)."""
    doc = _doc(
        _p(0, "Norma 5. Disposiciones.", "articulo"),
        _p(1, "1. Apartado"),
        _p(2, "a) Primera letra"),
        _p(3, "i) primer inciso"),
        _p(4, "b) Segunda letra"),
        _p(5, "i) otro inciso romano"),
    )
    res = _decide(doc, "norma:5.apartado:1.letra:a")
    assert res.status == binding.BOUND
    assert res.chosen.node_span == (2, 3)
    res = _decide(doc, "norma:5.apartado:1.letra:i")
    assert res.status == binding.AMBIGUOUS


# -- frozen-evidence integration --------------------------------------------

from regdelta import db as dbm, history  # noqa: E402,E501
from regdelta.http import EVIDENCE_IMPORT, FetchResult  # noqa: E402

MANIFEST = ROOT / "evidence" / "g2" / "dev" / "manifest.json"

_BY_URL: dict[str, dict] = {}
if MANIFEST.exists():
    _m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for e in _m["entries"].values():
        _BY_URL[e["url"]] = e


def _fetch(url: str, accept: str) -> FetchResult:
    e = _BY_URL.get(url)
    if e is None or "path" not in e:
        return FetchResult(url, None, None, None, "MISSING",
                           "url not in dev evidence", via=EVIDENCE_IMPORT)
    return FetchResult(url, 200, "application/octet-stream",
                       (ROOT / e["path"]).read_bytes(), None, None,
                       via=EVIDENCE_IMPORT)


@pytest.mark.skipif(not MANIFEST.exists(),
                    reason="G2 dev evidence not captured")
def test_norma55_undotted_apartado_binds_before(tmp_path):
    """Real debt case: '1 La cuenta…' / 'h) Otros…' inside norma 55 of
    BOE-A-2017-14334 — before side must bind on a unique candidate."""
    conn = dbm.connect(tmp_path / "r.sqlite")
    conn.row_factory = sqlite3.Row
    report = history.reconstruct(conn, tmp_path, "BOE-A-2017-14334",
                                 _fetch)
    conn.commit()
    assert "error" not in report, report.get("error")
    rows = conn.execute(
        """SELECT mr.binding_proof, s.locator_key
           FROM modification_relations mr
           JOIN subjects s ON s.subject_id = mr.target_subject_id
           WHERE s.locator_key = 'norma:55.apartado:1.letra:h'"""
    ).fetchall()
    conn.close()
    assert rows
    statuses = {json.loads(r["binding_proof"])["before"]["status"]
                for r in rows}
    assert "BOUND" in statuses
    for r in rows:
        before = json.loads(r["binding_proof"])["before"]
        if before["status"] == "BOUND":
            assert before["candidate_count"] == 1
