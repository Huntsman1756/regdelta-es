"""G1 §35: chain state machine (SubjectState + chain_update)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from regdelta import binding
from regdelta.history import SubjectState, chain_update

K = "norma:4"


def test_bound_after_becomes_present():
    c = {}
    chain_update(c, K, "SUBSTITUTE", binding.BOUND, "rep1", "rel1", None)
    assert c[K].status == "PRESENT"
    assert c[K].representation_id == "rep1"


def test_proven_after_reused_as_next_before():
    c = {}
    chain_update(c, K, "ADD", binding.BOUND, "repA", "relA", None)
    assert c[K].representation_id == "repA"
    assert c[K].relation_id == "relA"


def test_substitute_unproven_poisons_to_unknown():
    c = {K: SubjectState("PRESENT", "repOld", "rel0")}
    chain_update(c, K, "SUBSTITUTE", binding.NOT_PROVABLE, None,
                 "rel1", None)
    assert c[K].status == "UNKNOWN"
    assert c[K].representation_id is None


def test_modify_without_literals_unproven_unknown():
    c = {K: SubjectState("PRESENT", "repOld", "rel0")}
    chain_update(c, K, "MODIFY", binding.NOT_PROVABLE, None,
                 "rel1", None)
    assert c[K].status == "UNKNOWN"


def test_modify_with_literals_keeps_state():
    c = {K: SubjectState("PRESENT", "repOld", "rel0")}
    chain_update(c, K, "MODIFY", binding.NOT_PROVABLE, None,
                 "rel1", [("a", "b")])
    assert c[K].status == "PRESENT"
    assert c[K].representation_id == "repOld"


def test_delete_then_non_add_does_not_resurrect():
    c = {}
    chain_update(c, K, "DELETE", binding.NOT_APPLICABLE, None,
                 "relD", None)
    assert c[K].status == "DELETED"
    chain_update(c, K, "MODIFY", binding.NOT_PROVABLE, None,
                 "rel2", None)
    # still not PRESENT with the pre-delete representation
    assert c[K].status != "PRESENT"
    assert c[K].representation_id is None


def test_delete_then_add_starts_new_chain():
    c = {}
    chain_update(c, K, "DELETE", binding.NOT_APPLICABLE, None,
                 "relD", None)
    chain_update(c, K, "ADD", binding.BOUND, "repNew", "relA", None)
    assert c[K].status == "PRESENT"
    assert c[K].representation_id == "repNew"


def test_unknown_stays_unknown_on_non_add():
    c = {K: SubjectState("UNKNOWN", None, "rel0")}
    chain_update(c, K, "MODIFY", binding.NOT_PROVABLE, None,
                 "rel1", None)
    assert c[K].status == "UNKNOWN"


def test_add_with_unproven_after_marks_unknown():
    c = {}
    chain_update(c, K, "ADD", binding.NOT_PROVABLE, None,
                 "relA", None)
    assert c[K].status == "UNKNOWN"
    assert c[K].representation_id is None
