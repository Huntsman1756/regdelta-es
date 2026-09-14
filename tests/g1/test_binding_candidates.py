"""G1 §34: structural candidate enumeration (B1/B2/B5)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from regdelta import binding
from regdelta.sources.boe_diario import DiarioDoc, Node


def doc(*nodes) -> DiarioDoc:
    return DiarioDoc(nodes=[Node(i, *n) for i, n in enumerate(nodes)])


def test_unique_norma_binds():
    d = doc(("p", "articulo", "Norma primera. Alcance."),
            ("p", "parrafo", "1. Texto uno."),
            ("p", "articulo", "Norma segunda. Objeto."),
            ("p", "parrafo", "1. Otro."))
    res = binding.decide(
        [binding.Candidate("T", None, "TEXT", "norma:2", s, {}, "t")
         for s in binding.text_region_candidates(d, "norma:2")],
        "UNIQUE_STRUCTURAL_TARGET", "norma:2")
    assert res.status == binding.BOUND
    assert res.candidate_count == 1


def test_duplicate_norma_heading_ambiguous():
    d = doc(("p", "articulo", "Norma primera. A."),
            ("p", "parrafo", "contenido a"),
            ("p", "articulo", "Norma primera. B duplicada."),
            ("p", "parrafo", "contenido b"),
            ("p", "articulo", "Norma segunda. C."))
    res = binding.decide(
        [binding.Candidate("T", None, "TEXT", "norma:1", s, {}, "t")
         for s in binding.text_region_candidates(d, "norma:1")],
        "UNIQUE_STRUCTURAL_TARGET", "norma:1")
    assert res.status == binding.AMBIGUOUS
    assert res.candidate_count == 2


def test_duplicate_anejo_heading_ambiguous():
    d = doc(("p", "parrafo", "ANEJO 2. Tablas."),
            ("p", "parrafo", "x"),
            ("p", "parrafo", "ANEJO 2. Repetido."),
            ("p", "parrafo", "y"),
            ("p", "parrafo", "ANEJO 3. Otro."))
    res = binding.decide(
        [binding.Candidate("T", None, "TEXT", "anejo:2", s, {}, "t")
         for s in binding.text_region_candidates(d, "anejo:2")],
        "UNIQUE_STRUCTURAL_TARGET", "anejo:2")
    assert res.status == binding.AMBIGUOUS
    assert res.candidate_count == 2


def test_duplicate_sub_apartado_ambiguous():
    d = doc(("p", "articulo", "Norma tercera. X."),
            ("p", "parrafo", "4. Primera aparicion."),
            ("p", "parrafo", "texto"),
            ("p", "parrafo", "4. Segunda aparicion duplicada."),
            ("p", "articulo", "Norma cuarta. Y."))
    res = binding.decide(
        [binding.Candidate("T", None, "TEXT", "n", s, {}, "t")
         for s in binding.text_region_candidates(
             d, "norma:3.apartado:4")],
        "UNIQUE_STRUCTURAL_TARGET", "norma:3.apartado:4")
    assert res.status == binding.AMBIGUOUS
    assert res.candidate_count == 2


def test_parent_scope_confines_sub_locator():
    """'4.' inside Norma primera must not leak into Norma segunda's
    apartado:4 resolution (B2)."""
    d = doc(("p", "articulo", "Norma primera. A."),
            ("p", "parrafo", "4. Este apartado es de norma primera."),
            ("p", "articulo", "Norma segunda. B."),
            ("p", "parrafo", "1. Sin apartado cuatro."))
    res = binding.decide(
        [binding.Candidate("T", None, "TEXT", "n", s, {}, "t")
         for s in binding.text_region_candidates(
             d, "norma:2.apartado:4")],
        "UNIQUE_STRUCTURAL_TARGET", "norma:2.apartado:4")
    assert res.status == binding.NOT_FOUND
    assert res.candidate_count == 0


def test_zero_candidates_not_found():
    d = doc(("p", "articulo", "Norma primera. A."),
            ("p", "parrafo", "1. Texto."))
    res = binding.decide(
        [binding.Candidate("T", None, "TEXT", "n", s, {}, "t")
         for s in binding.text_region_candidates(d, "norma:9")],
        "UNIQUE_STRUCTURAL_TARGET", "norma:9")
    assert res.status == binding.NOT_FOUND


def test_roman_anejo_not_normalized():
    """'ANEJO II' does not satisfy 'anejo:2' (no roman/arabic
    normalization without a declared renumbering — B5/§14)."""
    d = doc(("p", "parrafo", "ANEJO II. Tablas."),
            ("p", "parrafo", "x"))
    res = binding.decide(
        [binding.Candidate("T", None, "TEXT", "a", s, {}, "t")
         for s in binding.text_region_candidates(d, "anejo:2")],
        "UNIQUE_STRUCTURAL_TARGET", "anejo:2")
    assert res.status == binding.NOT_FOUND


def test_annex_code_duplicate_not_collapsed():
    d = doc(("p", "anexo", "ANEJO"),
            ("p", "parrafo", "FI 100 Primero."),
            ("p", "parrafo", "cuerpo"),
            ("p", "parrafo", "FI 100 Duplicado."),
            ("p", "parrafo", "cuerpo2"),
            ("p", "parrafo", "FI 101 Otro."))
    regions = binding.annex_code_regions(d)
    assert len(regions["FI 100"]) == 2
    res = binding.decide(
        [binding.Candidate("T", None, "TEXT", "e", s, {}, "t")
         for s in regions["FI 100"]],
        "EXPLICIT_ANNEX_REFERENCE", "estado:FI 100")
    assert res.status == binding.AMBIGUOUS
    assert res.candidate_count == 2


def test_ordinal_word_matches_same_number():
    d = doc(("p", "articulo", "Norma cuarta. D."),
            ("p", "parrafo", "x"))
    res = binding.decide(
        [binding.Candidate("T", None, "TEXT", "n", s, {}, "t")
         for s in binding.text_region_candidates(d, "norma:4")],
        "UNIQUE_STRUCTURAL_TARGET", "norma:4")
    assert res.status == binding.BOUND
