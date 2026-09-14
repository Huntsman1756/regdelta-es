"""G1.0 regression corpus integrity.

The frozen G0-G.2 audit (evidence/g0g/g0g2/audit.jsonl — immutable)
contains exactly 73 FALSE_FACT rows. The G1 corpus at
evidence/g1/dev/g0-false-binding-corpus.json must reproduce every one
of them 1:1 so the G1.1 hard requirement
OLD_FALSE_FACT_REPRODUCTION_COUNT = 0 covers exactly the original set.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "evidence" / "g0g" / "g0g2" / "audit.jsonl"
CORPUS = ROOT / "evidence" / "g1" / "dev" / \
    "g0-false-binding-corpus.json"

_REQUIRED = {"target", "modifier", "relation_id", "locator_key",
             "claim_types", "expected_evidence_span",
             "emitted_representation", "truth_verdict"}


def _false_facts() -> list[dict]:
    return [json.loads(l) for l in AUDIT.read_text(
        encoding="utf-8").splitlines()
            if l.strip() and json.loads(l)["verdict"] == "FALSE_FACT"]


def test_corpus_covers_every_g0g2_false_fact() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert corpus["count"] == len(corpus["cases"])
    by_id = {c["relation_id"]: c for c in corpus["cases"]}
    ff = _false_facts()
    assert len(ff) == 73
    assert set(by_id) == {r["relation_id"] for r in ff}
    for r in ff:
        c = by_id[r["relation_id"]]
        assert c["target"] == r["target"]
        assert c["truth_verdict"] == "FALSE_FACT"
        assert _REQUIRED <= set(c)
        assert c["claim_types"]
