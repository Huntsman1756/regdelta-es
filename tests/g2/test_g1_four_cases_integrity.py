"""G2.0 integrity of the G1.2 four-case re-adjudication.

Verifies evidence/g2/root-cause/g1-four-cases.json is complete, uses
only the frozen taxonomies, preserves the historical G1 verdicts and
carries the O1/O2/O3 fields required by the G2 preregistration.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evidence" / "g2" / "root-cause" / "g1-four-cases.json"

EXPECTED_IDS = {
    "0dcde453e170d0b37cd0b18d2cf859fabd5703e241ff054a342289f0bdfd1483",
    "e4c75192a90248d368b9b208950cf2b1e4c886b620c9cdc1d7307951cf7bb224",
    "149762c5a18bb955e7d91b73dd8676e23e3d46ae5a956aae166141d62353ba99",
    "704ffae9f4df9f1cb18cacfa576ed752f58d92318314af9735a65e1c01cf58b4",
}
EXPECTED_TUPLES = {
    ("BOE-A-2012-9058", "BOE-A-2019-6888", "disp:final.primera",
     "MODIFY"),
    ("BOE-A-2012-9058", "BOE-A-2022-5524", "norma:11.apartado:1.letra:c",
     "MODIFY"),
    ("BOE-A-2012-9058", "BOE-A-2022-5524", "norma:11.apartado:9",
     "MODIFY"),
}
NEW_ROOT_CAUSES = {
    "RUNTIME_WRONG_TARGET_ATTRIBUTION",
    "RUNTIME_WRONG_LOCATOR",
    "VALID_CHAIN_BORN_LOCATOR",
    "G1_EVALUATOR_MODEL_ERROR",
    "OTHER",
}
EXISTENCE = {
    "PROVEN_PRESENT", "PROVEN_ABSENT", "UNKNOWN", "NOT_APPLICABLE"}
REQUIRED_FIELDS = {
    "old_relation_id", "target", "modifier", "locator_key",
    "operation_kind", "old_g1_verdict", "operation_owner",
    "owner_evidence", "operation_declares_locator",
    "locator_evidence", "subject_existence_before",
    "lifecycle_evidence", "new_root_cause"}


def _cases() -> list[dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))["cases"]


def test_exactly_four_cases_with_expected_ids() -> None:
    cases = _cases()
    assert len(cases) == 4
    assert {c["old_relation_id"] for c in cases} == EXPECTED_IDS
    # all ids are full 64-char sha256 hex, not truncated prefixes
    for c in cases:
        assert len(c["old_relation_id"]) == 64
        int(c["old_relation_id"], 16)


def test_expected_target_modifier_locator_tuples() -> None:
    got = {(c["target"], c["modifier"], c["locator_key"],
            c["operation_kind"]) for c in _cases()}
    assert got == EXPECTED_TUPLES


def test_historical_g1_verdict_preserved() -> None:
    for c in _cases():
        assert c["old_g1_verdict"] == "FALSE_FACT"
        assert c["old_g1_claims"]["target_locator_resolves"] == \
            "CONTRADICTED"


def test_o1_o2_o3_fields_present_and_typed() -> None:
    for c in _cases():
        assert REQUIRED_FIELDS <= set(c)
        assert isinstance(c["operation_declares_locator"], bool)
        assert c["subject_existence_before"] in EXISTENCE
        assert c["new_root_cause"] in NEW_ROOT_CAUSES
        for f in ("operation_owner", "owner_evidence",
                  "locator_evidence", "lifecycle_evidence"):
            assert isinstance(c[f], str) and c[f].strip()


def test_no_unsupported_adjudication() -> None:
    # every case must carry a closed-taxonomy root cause; UNKNOWN
    # existence must not have been converted into a false fact
    for c in _cases():
        assert c["new_root_cause"] in NEW_ROOT_CAUSES
        assert not (c["subject_existence_before"] == "UNKNOWN"
                    and "FALSE" in c["new_root_cause"])
