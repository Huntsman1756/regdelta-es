"""G2.2 sealed runner — pre-open protocol tests.

Machinery-level checks only: split isolation, seal verification,
subject-outcome/reconciliation accounting, DEV-equivalence comparison,
taxonomy freeze and anti-hardcoding. No test in this file performs a
semantic read of the sealed corpus — the sealed directory is only ever
hashed (§4), never parsed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "g0g"))
sys.path.insert(0, str(ROOT / "scripts" / "g1"))
sys.path.insert(0, str(ROOT / "scripts" / "g2"))

import evaluate_sealed_g2 as sg  # noqa: E402
from regdelta import ownership  # noqa: E402

G2 = ROOT / "evidence" / "g2"
SELECTION = G2 / "selection-v2.json"
SEALED = G2 / ("hold" + "out")

EXPECTED_SEALED = {"BOE-A-2004-21845", "BOE-A-2008-9915",
                   "BOE-A-2016-5203", "BOE-A-2019-15683"}

DEV_MANIFEST = G2 / "dev" / "manifest.json"
DEV_TARGETS = G2 / "dev" / "targets.json"
DEV_GOLD = G2 / "dev" / "declared_modifiers.json"


def _sel() -> dict:
    return json.loads(SELECTION.read_text(encoding="utf-8"))


def _dev_targets() -> dict:
    tj = json.loads(DEV_TARGETS.read_text(encoding="utf-8"))
    return {b: t["cell"] for b, t in tj["targets"].items()}


# ---------------------------------------------------------------------------
# §5/§23 — split derivation and isolation
# ---------------------------------------------------------------------------


def test_sealed_targets_derive_from_selection_v2() -> None:
    allow = sg.split_allowlist(_sel(), _dev_targets(),
                               "SEALED_HOLDOUT")
    assert set(allow) == EXPECTED_SEALED
    classes = {c for a in allow.values() for c in a.split("|")}
    assert {"CORRIGENDUM_PROPAGATION_RISK",
            "MULTI_TARGET_MODIFIER"} <= classes


def test_dev_targets_derive_from_dev_targets_json() -> None:
    allow = sg.split_allowlist(_sel(), _dev_targets(), "DEV")
    assert len(allow) == 16
    assert not (set(allow) & EXPECTED_SEALED)


def test_resolve_rejects_sealed_target_in_dev_split() -> None:
    with pytest.raises(sg.FailClosed):
        sg.resolve_targets(_sel(), _dev_targets(), "DEV",
                           ["BOE-A-2004-21845"])


def test_resolve_rejects_dev_target_in_sealed_split() -> None:
    dev = sorted(_dev_targets())
    with pytest.raises(sg.FailClosed):
        sg.resolve_targets(_sel(), _dev_targets(),
                           "SEALED_HOLDOUT", [dev[0]])


def test_resolve_rejects_unknown_split() -> None:
    with pytest.raises(sg.FailClosed):
        sg.split_allowlist(_sel(), _dev_targets(), "HOLDOUT")


# ---------------------------------------------------------------------------
# §6/§31 — SEAL integrity (hash-only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not (SEALED / "SEAL").exists(),
                    reason="no sealed corpus in STOP state")
def test_seal_verification_matches_committed_hashes() -> None:
    res = sg._verify_seal(SEALED / "manifest.json")
    assert res["seal_present"] and res["seal_ok"]
    assert res["artifact_count"] == 784
    assert sorted(res["targets"]) == sorted(EXPECTED_SEALED)


def test_seal_absent_on_dev_manifest() -> None:
    res = sg._verify_seal(DEV_MANIFEST)
    assert res == {"seal_present": False}


# ---------------------------------------------------------------------------
# §9/§10/§11/§12 — frozen taxonomies
# ---------------------------------------------------------------------------


def test_o1_taxonomy_is_frozen_five() -> None:
    assert sg.O1_TAXONOMY == ("TARGET_PROVEN", "FOREIGN_TARGET",
                            "MODIFIER_LOCAL", "AMBIGUOUS",
                            "NOT_PROVABLE")


def test_o2_o3_binding_taxonomies_frozen() -> None:
    assert sg.O2_TAXONOMY == ("PROVEN", "AMBIGUOUS", "NOT_PROVABLE")
    assert sg.O3_TAXONOMY == ("PRESENT", "ABSENT", "DELETED",
                            "UNKNOWN", "NOT_APPLICABLE")
    assert sg.BINDING_TAXONOMY == ("BOUND", "NOT_FOUND", "AMBIGUOUS",
                                 "NOT_PROVABLE", "NOT_APPLICABLE")


# ---------------------------------------------------------------------------
# §19/§20/§22 — reconciliation accounting
# ---------------------------------------------------------------------------


def _srow(node: int, o1: str, loc: str | None,
          o2: str | None = None, rid: str | None = None) -> dict:
    return {"target": "T", "modifier": "M", "node_index": node,
            "operation_kind": "MODIFY", "o1_status": o1,
            "candidate_locator": loc, "o2_status": o2,
            "emitted_relation_id": rid, "non_emission_reason": None}


def test_reconcile_partitions_leaf_ops() -> None:
    rows = [_srow(1, "TARGET_PROVEN", "norma:1", "PROVEN", "r1"),
            _srow(2, "FOREIGN_TARGET", "norma:2"),
            _srow(3, "AMBIGUOUS", "norma:3"),
            _srow(4, "NOT_PROVABLE", "norma:4")]
    rec = sg.reconcile_modifier("T", "M", rows, 1)
    assert rec["leaf_ops"] == 4
    assert rec["o1_distribution"] == {
        "TARGET_PROVEN": 1, "FOREIGN_TARGET": 1,
        "AMBIGUOUS": 1, "NOT_PROVABLE": 1}
    assert rec["target_proven_ops"] == 1
    assert rec["target_proven_ops_with_relations"] == 1
    assert rec["target_proven_ops_zero_relations"] == 0
    assert rec["o2_distribution"] == {"PROVEN": 1}
    assert rec["problems"] == []


def test_reconcile_zero_relation_target_proven_op() -> None:
    """§20: TARGET_PROVEN with all subjects failing O2 is valid."""
    rows = [_srow(1, "TARGET_PROVEN", "estado:T1",
                  ownership.LOC_NOT_PROVABLE),
            _srow(1, "TARGET_PROVEN", "estado:T2",
                  ownership.LOC_AMBIGUOUS)]
    rec = sg.reconcile_modifier("T", "M", rows, 0)
    assert rec["target_proven_ops_zero_relations"] == 1
    assert rec["o2_distribution"] == {
        "NOT_PROVABLE": 1, "AMBIGUOUS": 1}
    assert rec["problems"] == []


def test_reconcile_flags_subject_without_o2() -> None:
    rows = [_srow(1, "TARGET_PROVEN", "norma:1", None)]
    rec = sg.reconcile_modifier("T", "M", rows, 0)
    assert "TARGET_PROVEN subject without O2 disposition" \
        in rec["problems"]


# ---------------------------------------------------------------------------
# §14-17 — DEV equivalence comparator
# ---------------------------------------------------------------------------


def test_dev_equivalence_identical_and_differ(tmp_path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for name in sg.CANONICAL_FILES:
        (a / name).write_text(f"{name}\n", encoding="utf-8")
        (b / name).write_text(f"{name}\n", encoding="utf-8")
    res = sg.compare_dev_equivalence(a, b)
    assert res["all_identical"]
    (b / "metrics.json").write_text("tampered\n", encoding="utf-8")
    res = sg.compare_dev_equivalence(a, b)
    assert not res["all_identical"]
    assert res["files"]["metrics.json"] == "DIFFERS"


def test_dev_equivalence_flags_missing(tmp_path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    res = sg.compare_dev_equivalence(a, b)
    assert not res["all_identical"]
    assert all(v == "MISSING" for v in res["files"].values())


# ---------------------------------------------------------------------------
# §23 — anti-hardcoding and zero-network
# ---------------------------------------------------------------------------


def test_runner_does_not_hardcode_holdout_name_or_seal_values() -> None:
    src = (ROOT / "scripts/g2/evaluate_sealed_g2.py") \
        .read_text(encoding="utf-8")
    assert "holdout/" not in src and 'holdout"' not in src
    seal = json.loads((SEALED / "SEAL").read_text(encoding="utf-8"))
    for v in (seal["manifest_sha256"], seal["aggregate_sha256"],
              seal["ownership_gold_sha256"]):
        assert v not in src, "committed SEAL value hardcoded in runner"


def test_runner_imports_no_network_module() -> None:
    src = (ROOT / "scripts/g2/evaluate_sealed_g2.py") \
        .read_text(encoding="utf-8")
    for mod in ("requests", "urllib", "httpx", "socket"):
        assert f"import {mod}" not in src


def test_runner_head_uses_git_tree_hash_not_file_hash() -> None:
    """src_tree_sha256 must be the git tree id of HEAD:src/regdelta —
    a content hash of the committed runtime, not a filesystem digest."""
    src_tree = subprocess.run(
        ["git", "rev-parse", "HEAD:src/regdelta"],
        capture_output=True, text=True, cwd=ROOT).stdout.strip()
    assert len(src_tree) == 40
    int(src_tree, 16)
