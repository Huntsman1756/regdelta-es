"""G0-D discovery tests: applicability clauses of Circular 1/2025.

Runs the discovery probe (scripts/g0d/probe_applicability.py) against the
captured G0-C evidence — no network, no LLM, no OCR. Asserts the preregistered
D1–D11 expectations plus structural invariants (evidence spans, epistemic
labels, honest gap reporting).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "g0d"))

import probe_applicability as P  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (ROOT / "evidence/g0c/raw/boe_diario_xml__BOE-A-2025-26847.xml")
    .exists(),
    reason="G0-C evidence for BOE-A-2025-26847 not captured",
)

M = P.MODIFIER_BOE


@pytest.fixture(scope="module")
def a():
    clauses, matrix, freq, rel_rows = P.run()
    return {
        "clauses": clauses,
        "by_id": {c.clause_id: c for c in clauses},
        "matrix": matrix,
        "mat_by_id": {m["clause_id"]: m for m in matrix},
        "freq": freq,
        "rel_rows": rel_rows,
        "rel_ids": {r["relation_id"] for r in rel_rows},
    }


def _effs(c):
    return {e["effect"]: e for e in c.temporal_effects}


def _bound(a, cid):
    m = a["mat_by_id"].get(cid)
    return sorted({r for b in (m or {}).get("bindings", [])
                   for r in b["relation_ids"]})


def test_clause_inventory(a):
    """Every disposition section produced clauses."""
    secs = {c.section for c in a["clauses"]}
    assert secs == {"dt1", "dt2", "dt3", "dfu"}
    heads = {(c.section, c.item) for c in a["clauses"] if c.sub == 1}
    for expected in [("dt1", "1"), ("dt1", "6"), ("dt2", "1"),
                     ("dt2", "5"), ("dt3", "único"), ("dfu", "base"),
                     ("dfu", "a"), ("dfu", "f")]:
        assert expected in heads


def test_d1_general_effective_date(a):
    c = a["by_id"][f"{M}:dfu:base:s1"]
    e = _effs(c)["INSTRUMENT_EFFECTIVE_FROM"]
    assert e["date_value"] == "2025-12-30"
    assert e["epistemic"] == "DERIVED"  # publication + 1
    assert c.relation_to_parent == "BASE"


def test_d2_apply_from_2026_01_01(a):
    for letter in "abcd":
        c = a["by_id"][f"{M}:dfu:{letter}:s1"]
        e = _effs(c)["APPLY_FROM"]
        assert e["date_value"] == "2026-01-01"
        assert c.relation_to_parent == "EXCEPTION"
        assert c.parent_clause_id == f"{M}:dfu:base:s1"
        assert _bound(a, c.clause_id)


def test_d3_d5_frequency_first_reference(a):
    c = a["by_id"][f"{M}:dfu:e:s1"]
    frs = [e for e in c.temporal_effects
           if e["effect"] == "FIRST_REFERENCE_DATE"]
    by_date = {e["date_value"]: e["condition_normalized"]["frequency_in"]
               for e in frs}
    assert by_date == {"2026-03-31": ["MONTHLY", "QUARTERLY"],
                       "2026-06-30": ["SEMIANNUAL"],
                       "2026-12-31": ["ANNUAL"]}
    # DECLARED frequency resolution via norma 67 table
    assert a["freq"]["FI 105"] == "MONTHLY"
    assert a["freq"]["FI 160"] == "SEMIANNUAL"
    assert a["freq"]["FI 40"] == "ANNUAL"


def test_d6_riesgo_pais(a):
    c = a["by_id"][f"{M}:dfu:f:s1"]
    assert _effs(c)["FIRST_REFERENCE_DATE"]["date_value"] == "2026-06-30"
    m = a["mat_by_id"][c.clause_id]
    assert set(m["introducer_paths_cited"]) == {"p/vii", "p/viii"}
    bound_keys = {b["locator_key"] for b in m["bindings"]
                  if b["relation_ids"]}
    assert bound_keys == {"anejo:9.punto:132", "anejo:9.apartado:IV"}


def test_d7_last_reference_coexists(a):
    c = a["by_id"][f"{M}:dt3:único:s1"]
    e = _effs(c)["LAST_REFERENCE_DATE"]
    assert e["date_value"] == "2026-06-30"
    assert c.modality == "OBLIGATION"
    bound = _bound(a, c.clause_id)
    assert len(bound) == 4  # FI 131 + FI 141, two ops each
    # sin-perjuicio carve-out under dfu:e
    co = a["by_id"][f"{M}:dfu:e:s1:carveout"]
    assert co.relation_to_parent == "EXCEPTION"
    assert co.parent_clause_id == f"{M}:dfu:e:s1"
    assert co.conditions[0]["normalized"]["cites_section"] == "dt3"


def test_d8_retroactivity_and_initial_date(a):
    r = a["by_id"][f"{M}:dt1:1:s2"]
    i = a["by_id"][f"{M}:dt1:1:s3"]
    assert "RETROACTIVE_APPLICATION" in _effs(r)
    assert _effs(i)["INITIAL_APPLICATION_DATE"]["date_value"] == "2026-01-01"
    assert i.clause_id != r.clause_id


def test_d9_option_absence_of_obligation(a):
    c = a["by_id"][f"{M}:dt1:2:s1"]
    assert c.modality == "ABSENCE_OF_OBLIGATION"
    assert "no estará obligada a reexpresar" in c.text
    assert c.relation_to_parent == "EXCEPTION"


def test_d10_consequence_is_child_of_option(a):
    c = a["by_id"][f"{M}:dt1:2:s2"]
    assert c.relation_to_parent == "QUALIFIER"
    assert c.parent_clause_id == f"{M}:dt1:2:s1"
    assert "Si optara por no reexpresarla" in c.text


def test_d11_transitoria_segunda_same_model(a):
    for item in ("1", "2", "3", "4", "5"):
        c = a["by_id"][f"{M}:dt2:{item}:s1"]
        assert c.relation_to_parent in ("BASE", "EXCEPTION", "QUALIFIER")
    r = a["by_id"][f"{M}:dt2:1:s2"]
    assert "RETROACTIVE_APPLICATION" in _effs(r)
    assert a["by_id"][f"{M}:dt2:2:s1"].modality == "ABSENCE_OF_OBLIGATION"
    assert a["by_id"][f"{M}:dt2:2:s2"].relation_to_parent == "QUALIFIER"


def test_multiple_clauses_per_relation(a):
    """FI 131/141 relations are bound by dt3 (last ref) and inside dfu:e's
    scope — one relation may carry several applicability clauses."""
    e = _bound(a, f"{M}:dfu:e:s1")
    t3 = _bound(a, f"{M}:dt3:único:s1")
    overlap = set(e) & set(t3)
    assert overlap  # same relation governed by both clauses


def test_evidence_spans_and_epistemic(a):
    for c in a["clauses"]:
        assert c.text.strip()
        assert c.node_span[0] > 0
        assert c.char_span[1] > c.char_span[0]
        assert c.epistemic in ("OBSERVED", "DERIVED")


def test_no_scalar_flattening(a):
    """No clause collapses frequency-conditioned dates into one scalar."""
    c = a["by_id"][f"{M}:dfu:e:s1"]
    assert len([e for e in c.temporal_effects
                if e["effect"] == "FIRST_REFERENCE_DATE"]) == 3


def test_gaps_are_reported_not_invented(a):
    """The two real G0-C.2 recall gaps surface as MISSING, never fabricated."""
    missing = {k for m in a["matrix"]
               for k in m["subjects_cited_without_relation"]}
    assert missing == {"norma:31.apartado:3",
                       "norma:22.apartado:18",
                       "norma:22.apartado:19",
                       "norma:22.apartado:20"}
    # applied-rule citations are not mistaken for modification targets
    rule_refs = {k for m in a["matrix"] for k in m["cited_rule_references"]}
    assert {"norma:17.apartado:6", "norma:17.apartado:7",
            "norma:17.apartado:8"} <= rule_refs
    # every bound relation actually exists
    for m in a["matrix"]:
        for b in m["bindings"]:
            for rid in b["relation_ids"]:
                assert rid in a["rel_ids"]
