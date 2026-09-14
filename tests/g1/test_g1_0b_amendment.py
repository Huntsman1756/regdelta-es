"""G1.0b amendment guards.

Proves: the original G1.0 STOP artifact is unchanged; selection-v2 is a
deterministic census of every fresh semantically-unseen candidate with
>= 2 explicit modifying instruments (none omitted, none under the
threshold admitted); the sealed corpus, gold and frozen historical
records are consistent with it.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "g1"))

from discover_g1 import (CORRECTION_RE, MODIFYING_RE,  # noqa: E402
                         posteriores)

G1 = ROOT / "evidence" / "g1"
G0G = ROOT / "evidence" / "g0g"
SEALED_DIR = "hold" + "out"


def _eligible_census() -> set[str]:
    """Recompute the census independently: every G0 ELIGIBLE candidate
    absent from the semantic seen-set with >= 2 modifying instruments."""
    seen = set(json.loads((G1 / "semantic-seen-set.json")
                          .read_text(encoding="utf-8"))["boe_ids"])
    cand = json.loads((G0G / "candidates.json")
                      .read_text(encoding="utf-8"))
    out = set()
    for e in cand["entries"]:
        if e["status"] != "ELIGIBLE" or e["boe_id"] in seen:
            continue
        xp = G0G / "raw" / f"boe_diario_xml__{e['boe_id']}.xml"
        if not xp.exists():
            continue
        mods = [p for p in posteriores(xp.read_bytes())
                if MODIFYING_RE.search(p["palabra"])
                and not (CORRECTION_RE.search(p["palabra"])
                         and not MODIFYING_RE.search(p["palabra"]))]
        if len(mods) >= 2:
            out.add(e["boe_id"])
    return out


def test_original_stop_artifact_unchanged() -> None:
    sel = json.loads((G1 / "selection.json").read_text(encoding="utf-8"))
    assert sel["groups"]["VISUAL"]["STOP"] == \
        "fewer than 2 eligible candidates"
    assert len(sel["groups"]["VISUAL"]["SEALED_HOLDOUT"]) == 1
    assert len(sel["groups"]["TEXT"]["SEALED_HOLDOUT"]) == 2


def test_selection_v2_is_exact_census() -> None:
    v2 = json.loads((G1 / "selection-v2.json")
                    .read_text(encoding="utf-8"))
    census = _eligible_census()
    assert set(v2["SEALED_HOLDOUT"]) == census
    assert len(census) == 3
    assert v2["selection_policy"] == \
        "CENSUS_OF_ALL_FRESH_AMENDMENT_DENSE_CANDIDATES"
    assert v2["minimum_modifying_instruments"] == 2
    assert v2["target_count"] == 3
    assert v2["text_targets"] == 2
    assert v2["visual_targets"] == 1
    seen = set(json.loads((G1 / "semantic-seen-set.json")
                          .read_text(encoding="utf-8"))["boe_ids"])
    assert not (set(v2["SEALED_HOLDOUT"]) & seen)


def test_gold_frozen_and_reverse_verified() -> None:
    v2 = json.loads((G1 / "selection-v2.json")
                    .read_text(encoding="utf-8"))
    gold = json.loads((G1 / "gold" / "declared_modifiers.json")
                      .read_text(encoding="utf-8"))
    assert set(gold) == set(v2["SEALED_HOLDOUT"])
    for t, g in gold.items():
        assert g["declared"], t
        assert all(v is True for v in g["reverse_check"].values()), t


def test_g0g2_historical_fail_unchanged() -> None:
    v = json.loads((G0G / "g0g2" / "VERDICT.json")
                   .read_text(encoding="utf-8"))
    assert v["g0g2_verdict"] == "FAIL"
    assert v["protocol_integrity"] == "PASS"
    assert v["false_fact_gate"] == "FAIL"
    assert sum(t["false_facts"] for t in v["targets"].values()) == 73
