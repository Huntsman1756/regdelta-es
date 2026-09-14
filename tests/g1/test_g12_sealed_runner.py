"""G1.2 pre-open tests — sealed runner contract.

These tests exercise the runner shell (split derivation, fail-closed
target checks, taxonomy constants, binding_proof consistency verifier,
B1-B6 invariants, DEV equivalence artifacts). None of them may parse
semantic content of the fresh sealed corpus: they read only
selection-v2, the DEV manifest, committed run artifacts and synthetic
rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "g0g"))
sys.path.insert(0, str(ROOT / "scripts" / "g1"))

import evaluate_sealed_g1 as sealed  # noqa: E402

SEL = json.loads((ROOT / "evidence" / "g1" / "selection-v2.json")
                 .read_text(encoding="utf-8"))
DEV_MAN = json.loads((ROOT / "evidence" / "g1" / "dev" / "manifest.json")
                     .read_text(encoding="utf-8"))
EQ_DIR = ROOT / "evidence" / "g1" / "g1.2" / "dev-equivalence"
FINAL_DIR = ROOT / "evidence" / "g1" / "dev" / "runs" / "006-final"


def _row(**kw):
    r = {"relation_id": "r1", "operation_kind": "SUBSTITUTE",
         "locator_key": "norma:1", "modifier_boe": "BOE-A-1",
         "publication_date": "2020-01-01",
         "before_representation_id": None,
         "after_representation_id": None,
         "binding_proof": {}}
    r.update(kw)
    return r


def _proof(status, method="M", count=0, chosen=None, pred_rel=None,
           pred_rep=None):
    return {"status": status, "method": method,
            "locator_key": "norma:1", "candidate_count": count,
            "candidates": [], "chosen": chosen,
            "predecessor_relation_id": pred_rel,
            "predecessor_representation_id": pred_rep,
            "reason": None}


# ---------------------------------------------------------------------------
# split derivation + fail-closed checks
# ---------------------------------------------------------------------------


def test_holdout_targets_derived_from_selection_v2() -> None:
    allow = sealed.split_allowlist(SEL, DEV_MAN, "SEALED_HOLDOUT")
    assert sorted(allow) == sorted(SEL["SEALED_HOLDOUT"])
    assert set(SEL["SEALED_HOLDOUT"]) == {
        "BOE-A-2010-15521", "BOE-A-2012-9058", "BOE-A-2014-1183"}
    for b, cell in allow.items():
        meta = SEL["targets"][b]
        assert cell == (meta["group"] + "x" + (
            "CONSOLIDATED" if meta["consolidated"]
            else "NON_CONSOLIDATED"))


def test_dev_targets_derived_from_manifest() -> None:
    allow = sealed.split_allowlist(SEL, DEV_MAN, "DEV")
    assert len(allow) == 12
    assert set(SEL["SEALED_HOLDOUT"]).isdisjoint(allow)


def test_runner_rejects_ids_outside_split() -> None:
    # a sealed-holdout id under DEV -> fail closed
    with pytest.raises(sealed.FailClosed):
        sealed.resolve_targets(SEL, DEV_MAN, "DEV",
                               ["BOE-A-2010-15521"])
    # a DEV id under SEALED_HOLDOUT -> fail closed
    with pytest.raises(sealed.FailClosed):
        sealed.resolve_targets(SEL, DEV_MAN, "SEALED_HOLDOUT",
                               ["BOE-A-2013-5720"])
    # unknown id -> fail closed
    with pytest.raises(sealed.FailClosed):
        sealed.resolve_targets(SEL, DEV_MAN, "SEALED_HOLDOUT",
                               ["BOE-A-9999-1"])
    # valid subset accepted
    allow = sealed.resolve_targets(SEL, DEV_MAN, "SEALED_HOLDOUT",
                                   ["BOE-A-2012-9058"])
    assert list(allow) == ["BOE-A-2012-9058"]


def test_unknown_split_fails_closed() -> None:
    with pytest.raises(sealed.FailClosed):
        sealed.split_allowlist(SEL, DEV_MAN, "GENERALIZATION_DEV")


# ---------------------------------------------------------------------------
# taxonomy constants (frozen vocabularies)
# ---------------------------------------------------------------------------


def test_taxonomies_exact() -> None:
    assert sealed.TRUTH_VERDICTS == {"PASS", "FALSE_FACT"}
    assert sealed.BINDING_VERDICTS == {
        "BINDING_CORRECT", "BINDING_FALSE",
        "BINDING_NOT_CHECKABLE", "NO_BINDING_CLAIM"}
    assert sealed.ROOT_CAUSES == {
        "SOURCE_LIMITATION", "ACQUISITION_FAILURE",
        "OPERATION_PARSER_FAILURE", "LOCATOR_RESOLUTION_FAILURE",
        "REPRESENTATION_BINDING_FAILURE", "CHAIN_FAILURE",
        "SCHEMA_FAILURE", "QUERY_EVALUATION_FAILURE"}
    assert sealed.B_KEYS == ("B1", "B2", "B3", "B4", "B5", "B6")


# ---------------------------------------------------------------------------
# binding_proof consistency verifier
# ---------------------------------------------------------------------------


def test_proof_bound_with_rep_ok() -> None:
    r = _row(before_representation_id="rep1",
             binding_proof={"before": _proof(
                 "BOUND", "UNIQUE_STRUCTURAL_TARGET", 1,
                 chosen={"instrument": "X"})})
    assert sealed.proof_violations(r) == []


def test_proof_bound_without_rep_fails() -> None:
    r = _row(binding_proof={"before": _proof(
        "BOUND", "UNIQUE_STRUCTURAL_TARGET", 1,
        chosen={"instrument": "X"})})
    assert "before:BOUND_without_representation" in \
        sealed.proof_violations(r)


def test_proof_abstain_with_rep_fails() -> None:
    for st in ("AMBIGUOUS", "NOT_FOUND", "NOT_PROVABLE"):
        r = _row(after_representation_id="rep1",
                 binding_proof={"after": _proof(
                     st, "M", 2 if st == "AMBIGUOUS" else 0)})
        assert f"after:{st}_persisted_representation" in \
            sealed.proof_violations(r)


def test_proof_ambiguous_needs_multiple_candidates() -> None:
    r = _row(binding_proof={"before": _proof("AMBIGUOUS", "M", 1)})
    assert "before:AMBIGUOUS_bad_candidate_count" in \
        sealed.proof_violations(r)


def test_proof_not_applicable_semantics() -> None:
    # ADD -> before NOT_APPLICABLE is consistent
    r = _row(operation_kind="ADD",
             binding_proof={"before": _proof(
                 "NOT_APPLICABLE", "ADD_NO_BEFORE")})
    assert sealed.proof_violations(r) == []
    # NOT_APPLICABLE on before of a SUBSTITUTE is a violation
    r2 = _row(operation_kind="SUBSTITUTE",
              binding_proof={"before": _proof(
                  "NOT_APPLICABLE", "ADD_NO_BEFORE")})
    assert "before:NOT_APPLICABLE_op_mismatch" in \
        sealed.proof_violations(r2)
    # DELETE -> after NOT_APPLICABLE consistent
    r3 = _row(operation_kind="DELETE",
              binding_proof={"after": _proof(
                  "NOT_APPLICABLE", "DELETE_NO_AFTER")})
    assert sealed.proof_violations(r3) == []


def test_proof_chain_predecessor_must_match_rep() -> None:
    ok = _row(before_representation_id="repP",
              binding_proof={"before": _proof(
                  "BOUND", "CHAIN_PREDECESSOR", 1,
                  pred_rel="rel0", pred_rep="repP")})
    assert sealed.proof_violations(ok) == []
    bad = _row(before_representation_id="repX",
               binding_proof={"before": _proof(
                   "BOUND", "CHAIN_PREDECESSOR", 1,
                   pred_rel="rel0", pred_rep="repP")})
    assert "before:chain_predecessor_mismatch" in \
        sealed.proof_violations(bad)


def test_proof_rep_without_proof_fails() -> None:
    r = _row(before_representation_id="rep1", binding_proof={})
    assert "before:representation_without_proof" in \
        sealed.proof_violations(r)


# ---------------------------------------------------------------------------
# B1-B6 invariants
# ---------------------------------------------------------------------------


def _audit(claims: dict) -> dict:
    return {"claims_checked": dict(claims)}


def test_b_invariants_clean_bound_relation() -> None:
    r = _row(before_representation_id="rep1",
             after_representation_id="rep2",
             after_instrument="BOE-A-1",
             binding_proof={
                 "before": _proof("BOUND", "CHAIN_PREDECESSOR", 1,
                                  pred_rel="r0", pred_rep="rep1"),
                 "after": _proof("BOUND", "INLINE_QUOTED_CONTENT", 1,
                                 chosen={"instrument": "BOE-A-1"})})
    a = _audit({"before_binding": "BINDING_CORRECT",
                "after_binding": "BINDING_CORRECT",
                "chain_predecessor": "VERIFIED",
                "resolution_consistent": "VERIFIED"})
    inv = sealed.binding_invariants(r, a, {})
    assert inv == {"B1": "PASS", "B2": "PASS", "B3": "PASS",
                   "B4": "PASS", "B5": "NOT_APPLICABLE",
                   "B6": "PASS"}


def test_b_invariants_abstained_relation() -> None:
    r = _row(binding_proof={
        "before": _proof("NOT_PROVABLE", "SUBJECT_SCOPE"),
        "after": _proof("NOT_PROVABLE", "SUBJECT_SCOPE")})
    a = _audit({"before_binding": "NO_BINDING_CLAIM",
                "after_binding": "NO_BINDING_CLAIM",
                "resolution_consistent": "VERIFIED"})
    inv = sealed.binding_invariants(r, a, {})
    assert inv["B1"] == "NOT_APPLICABLE"
    assert inv["B5"] == "PASS"


def test_b2_fails_on_binding_false() -> None:
    r = _row(before_representation_id="rep1",
             binding_proof={"before": _proof(
                 "BOUND", "M", 1, chosen={"instrument": "X"})})
    a = _audit({"before_binding": "BINDING_FALSE",
                "after_binding": "NO_BINDING_CLAIM"})
    inv = sealed.binding_invariants(r, a, {})
    assert inv["B2"] == "FAIL"


def test_b4_fails_on_contradicted_chain() -> None:
    r = _row(before_representation_id="rep1",
             binding_proof={"before": _proof(
                 "BOUND", "CHAIN_PREDECESSOR", 1,
                 pred_rel="r0", pred_rep="rep1")})
    a = _audit({"chain_predecessor": "CONTRADICTED"})
    inv = sealed.binding_invariants(r, a, {})
    assert inv["B4"] == "FAIL"


def test_b5_fails_when_abstain_persists_rep() -> None:
    r = _row(after_representation_id="rep9",
             binding_proof={"after": _proof("AMBIGUOUS", "M", 3)})
    a = _audit({"after_binding": "BINDING_CORRECT"})
    inv = sealed.binding_invariants(r, a, {})
    assert inv["B5"] == "FAIL"


def test_verifiers_deterministic() -> None:
    r = _row(after_representation_id="rep9",
             binding_proof={"after": _proof("AMBIGUOUS", "M", 3)})
    a = _audit({"after_binding": "BINDING_CORRECT"})
    assert sealed.proof_violations(r) == sealed.proof_violations(r)
    assert sealed.binding_invariants(r, a, {}) == \
        sealed.binding_invariants(r, a, {})


# ---------------------------------------------------------------------------
# DEV equivalence — the sealed runner over the 12 DEV targets must
# reproduce run 006-final exactly (§9-10)
# ---------------------------------------------------------------------------


_CONTRACT_METRICS = (
    "declared_modifier_recall", "operation_parsing_rate",
    "subject_locator_resolution", "representation_binding",
    "chain_reconstruction", "applicability_extraction",
    "query_execution", "false_positive_facts",
    "false_binding_count", "source_limitations",
    "old_false_fact_reproduction_count")


def _load(d: Path, name: str):
    return json.loads((d / name).read_text(encoding="utf-8"))


def test_dev_equivalence_aggregate_metrics() -> None:
    eq = _load(EQ_DIR, "metrics.json")
    fin = _load(FINAL_DIR, "metrics.json")
    for k in _CONTRACT_METRICS:
        assert eq["aggregate"][k] == fin["aggregate"][k], k


def test_dev_equivalence_per_target_metrics() -> None:
    eq = _load(EQ_DIR, "metrics.json")
    fin = _load(FINAL_DIR, "metrics.json")
    assert set(eq["per_target"]) == set(fin["per_target"])
    for t in fin["per_target"]:
        for k in _CONTRACT_METRICS:
            if k in fin["per_target"][t]:
                assert eq["per_target"][t][k] == \
                    fin["per_target"][t][k], (t, k)


def test_dev_equivalence_audit_verdicts() -> None:
    def load(d):
        out = {}
        for l in (d / "audit.jsonl").read_text(
                encoding="utf-8").splitlines():
            a = json.loads(l)
            out[a["relation_id"]] = (a["truth_verdict"],
                                     a["false_binding"],
                                     a["root_cause_class"])
        return out
    eq, fin = load(EQ_DIR), load(FINAL_DIR)
    assert set(eq) == set(fin)
    assert eq == fin
    assert len(eq) == 219


def test_dev_equivalence_corpus_73() -> None:
    eq = _load(EQ_DIR, "corpus-73.json")
    fin = _load(FINAL_DIR, "corpus-73.json")
    assert eq["counts"] == fin["counts"] == {
        "ABSTAINED": 57,
        "ALREADY_CORRECT_G0_EVALUATOR_ERROR": 16}
    eq_out = {tuple(sorted(c["signature"].items())): c["outcome"]
              for c in eq["cases"]}
    fin_out = {tuple(sorted(c["signature"].items())): c["outcome"]
               for c in fin["cases"]}
    assert eq_out == fin_out


def test_dev_equivalence_relations_and_resolution() -> None:
    def rels(d):
        return {json.loads(l)["relation_id"]: json.loads(l)
                for l in (d / "relations.jsonl").read_text(
                    encoding="utf-8").splitlines()}
    eq, fin = rels(EQ_DIR), rels(FINAL_DIR)
    assert eq == fin
    assert len(eq) == 219
    eq_t = _load(EQ_DIR, "targets.json")
    fin_t = _load(FINAL_DIR, "targets.json")
    for t in fin_t:
        assert eq_t[t]["inventory"]["resolution"] == \
            fin_t[t]["inventory"]["resolution"], t
        assert eq_t[t]["inventory"]["relations"] == \
            fin_t[t]["inventory"]["relations"], t
        assert eq_t[t]["NON_GATE_DIAGNOSTIC"]["chains"] == \
            fin_t[t]["NON_GATE_DIAGNOSTIC"]["chains"], t
        assert {k: v["status"] for k, v in
                eq_t[t]["query_execution"].items()} == \
            {k: v["status"] for k, v in
             fin_t[t]["query_execution"].items()}, t


def test_dev_equivalence_no_false_ids() -> None:
    for l in (EQ_DIR / "audit.jsonl").read_text(
            encoding="utf-8").splitlines():
        a = json.loads(l)
        assert a["truth_verdict"] == "PASS"
        assert not a["false_binding"]
        assert a["claims_checked"]["binding_proof_consistent"] == \
            "VERIFIED"
        assert all(v != "FAIL"
                   for v in a["binding_invariants"].values())


def test_evidence_fetch_is_import_only() -> None:
    from regdelta.http import EVIDENCE_IMPORT
    import evaluate_dev as ev
    fetch = ev.evidence_fetch({})
    res = fetch("https://example.invalid/x", "*/*")
    assert res.via == EVIDENCE_IMPORT
    assert res.error_class == "MISSING"
